#!/usr/bin/env bash
# id: cpx62-0309-loop-diagnostic
# description: DIAGNOSTIC du drift 0297 (Elo ↓ gen3→gen6, endgame_mse ↑ 1.8→5.4). Sépare BUG (données
# cumulées polluées) de SATURATION (le linéaire ne PEUT PAS représenter les labels de finale exacts).
# Sur le cumulatif 0297 : (1) scan de cohérence — positions dupliquées à WDL CONTRADICTOIRE + distrib
# par nb de pièces ; (2) ablation d'entraînement — FULL vs NO-ENDGAME(>7p) vs ENDGAME-ONLY(≤7p), Elo_vs_hc
# + endgame_mse chacun. Verdict : contradictions↑ → BUG ; contradictions~0 mais endgame_mse plancher haut
# sur ENDGAME-ONLY → SATURATION (plafond représentationnel). S'enchaîne après 0306 (même box, données là).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0309-loop-diagnostic/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CUM=/root/jass/jobs/results/cpx62-0297-saturate-loop/artefacts.src/cumulative.jnnw
[ -f "$CUM" ] || { echo "ABORT: cumulatif 0297 absent ($CUM)"; exit 3; }

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- (1) cohérence + split par nb de pièces (record JNNW = 38o : 4×u64 bitboards, stm@32, score@33, wdl@37) ---
python3 - "$CUM" "$ART" <<'PY'
import sys,struct
src,art=sys.argv[1],sys.argv[2]
b=open(src,'rb').read(); head=b[:8]; n=struct.unpack('<I',head[4:8])[0]; body=b[8:]; REC=38
def pieces(rec):
    wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32]);
    return bin(wm|wk|bm|bk).count('1')
seen={}; conflict=0; dup=0
seen_e={}; conflict_e=0   # ≤7p zone (exact TB → contradictions = BUG)
import collections
phase=collections.Counter()
rows_noend=bytearray(); rows_end=bytearray(); n_noend=0; n_end=0
for i in range(n):
    rec=body[i*REC:(i+1)*REC]
    if len(rec)<REC: break
    pc=pieces(rec); wdl=struct.unpack('<b',rec[37:38])[0]
    phase[pc]+=1
    key=rec[0:33]  # bitboards + stm
    if key in seen:
        dup+=1
        if seen[key]!=wdl: conflict+=1
    else: seen[key]=wdl
    if pc<=7:
        rows_end+=rec; n_end+=1
        if key in seen_e:
            if seen_e[key]!=wdl: conflict_e+=1
        else: seen_e[key]=wdl
    else:     rows_noend+=rec; n_noend+=1
open(art+'/noend.jnnw','wb').write(head[:4]+struct.pack('<I',n_noend)+bytes(rows_noend))
open(art+'/endonly.jnnw','wb').write(head[:4]+struct.pack('<I',n_end)+bytes(rows_end))
le7=sum(v for k,v in phase.items() if k<=7); le10=sum(v for k,v in phase.items() if k<=10)
print(f"COHERENCE  n={n}  uniques={len(seen)}  dup={dup}  CONTRADICTIONS-globales(WDL)={conflict} ({conflict/max(1,n)*100:.2f}%)")
print(f"  CONTRADICTIONS ≤7p (exact-TB → devraient être ~0, sinon BUG) = {conflict_e}")
print(f"  (>7p : quelques contradictions = bruit normal de label par résultat-de-partie)")
print(f"PIECES     ≤7p(exact-TB)={le7} ({le7/n*100:.1f}%)  ≤10p={le10} ({le10/n*100:.1f}%)  >7p={n_noend}")
print(f"SPLIT      no-endgame(>7p)={n_noend}  endgame-only(≤7p)={n_end}")
PY

CFOLD="--full-fold --king-patterns"
train(){ # <data.jnnw> <out_prefix>
  $JASS --dump-eval-features "$1" "$2.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2.feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$2.pjtw" >"$2-train.log" 2>&1
  grep -oE 'val/phase mse : .*' "$2-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2
}
elo(){ local lg="$1-elo.log"; $JASS --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

echo "=== ablation : FULL ==="
EG_FULL=$(train "$CUM" "$ART/full"); [ -f "$ART/full.pjtw" ] && EL_FULL=$(elo "$ART/full") || EL_FULL=NA
echo "  FULL      endgame_mse=$EG_FULL  Elo_vs_hc=$EL_FULL"
echo "=== ablation : NO-ENDGAME (>7p) ==="
EG_NE=$(train "$ART/noend" "$ART/noend"); [ -f "$ART/noend.pjtw" ] && EL_NE=$(elo "$ART/noend") || EL_NE=NA
echo "  NO-ENDGAME endgame_mse=$EG_NE  Elo_vs_hc=$EL_NE"
echo "=== ablation : ENDGAME-ONLY (≤7p, labels exacts) ==="
EG_EO=$(train "$ART/endonly" "$ART/endonly"); [ -f "$ART/endonly.pjtw" ] && EL_EO=$(elo "$ART/endonly") || EL_EO=NA
echo "  ENDGAME-ONLY endgame_mse=$EG_EO (= plancher représentationnel)  Elo_vs_hc=$EL_EO"

echo; echo "=========================================================="
echo "   cpx62-0309 — DIAGNOSTIC du drift 0297"
echo "----------------------------------------------------------"
echo "  FULL        : mse=$EG_FULL  Elo=$EL_FULL"
echo "  NO-ENDGAME  : mse=$EG_NE  Elo=$EL_NE"
echo "  ENDGAME-ONLY: mse=$EG_EO  Elo=$EL_EO"
echo "----------------------------------------------------------"
echo "  CONTRADICTIONS WDL élevées (≫0.1%) → BUG (données polluées) : nettoyer le cumul/relabel."
echo "  Contradictions ~0 MAIS endgame_mse(ENDGAME-ONLY) déjà HAUT (le linéaire ne descend pas même"
echo "     en n'ayant QUE les finales) → SATURATION représentationnelle confirmée → capacité (FM/MLP)."
echo "  NO-ENDGAME Elo ≫ FULL Elo → les finales TIRENT le fit global vers le bas (conflit linéaire)."
echo "=========================================================="
