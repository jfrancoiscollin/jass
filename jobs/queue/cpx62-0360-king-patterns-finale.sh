#!/usr/bin/env bash
# id: cpx62-0360-king-patterns-finale
# description: LE vrai levier finale (PAS l'élagage — branche morte 0230/0234/0190). Le trou finale (0349 : corr ≤7p
# effondrée à 0.39) vient de patterns MEN-ONLY aveugles aux ROIS, alors que la finale est DOMINÉE par les rois.
# 0240 avait montré +37 Elo (patterns men|kings) MAIS en distillation jugée Elo_hc (SCREEN) puis mis OFF sous le
# régime logistic-WDL. On est REVENU en distillation de score (son régime favorable) + recherche réglée → on re-juge
# proprement : evalK (king-aware) vs eval0 (men-only), MÊME data/recette, vs Scan d9 (DECISION_GATE), 216 p/arm.
# + DIAGNOSTIC mécanisme : corr(éval↔Scan-d9) par bande de pièces sur un set finale HELD-OUT (0328) — la corr ≤7p
# remonte-t-elle au-dessus de 0.39 ? Le guard SELFDESC (scan_eval.cpp) rend un no-op type 0355 IMPOSSIBLE (mismatch
# king-aware → ABORT). evalK > eval0 net vs Scan ET corr finale qui remonte → baker JASS_KING_PATTERNS. ≈ → les rois
# ne sont pas le levier finale dans ce régime non plus → renforce le verdict plafond linéaire (→ pivot NN).
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/cpx62-0360-king-patterns-finale/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
N=14000
[ -f "$DATA" ] && [ -f "$CORPUS" ] || { echo "ABORT: data manquante"; exit 4; }

preflight_build 2; preflight_train 240000 2; preflight_note "2×216 parties vs Scan + relabel d9 + corr finale" 90; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

# build_jass <dir> <king:0|1> : MÊMES flags que 0353 ; seul JASS_KING_PATTERNS varie entre les arms.
build_jass(){ local B="$1" king="$2"; rm -rf "$B"
  cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
        -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
        -DJASS_KING_PATTERNS="$([ "$king" = 1 ] && echo ON || echo OFF)" >"$ART/cmake-$B.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake-$B.log" || { echo "ABORT: egdb off ($B)"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build-$B.log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$ART/build-$B.log"; exit 6; }
}
# train_arm <jass-bin> <king:0|1> <out.pjtw> : recette 0353 ; --king-patterns SSI king=1 (DOIT matcher le build).
train_arm(){ local J="$1" king="$2" out="$3"
  "$J" --dump-eval-features "$DATA" "$ART/feat-$king" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/feat-$king" \
    --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
    $([ "$king" = 1 ] && echo --king-patterns) --out "$out" >"$ART/train-$(basename "$out").log" 2>&1
  [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -8 "$ART/train-$(basename "$out").log"; exit 9; }
}
rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
vs_scan(){ local J="$1" pj="$2" lg="$3"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$pj" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 12 --max-plies 160 >"$lg" 2>&1 || true; }

echo "=== ARM 0 : men-only (baseline) ==="
build_jass build-men 0; J0="$PWD/build-men/jass"; train_arm "$J0" 0 "$ART/eval0.pjtw"
echo "=== ARM K : king-aware (patterns men|kings) ==="
build_jass build-king 1; JK="$PWD/build-king/jass"; train_arm "$JK" 1 "$ART/evalK.pjtw"

echo "=== DECISION : vs Scan d9 — 216 parties/arm (depth-égale, openings appariés) ==="
vs_scan "$J0" "$ART/eval0.pjtw" "$ART/vs0.log"
vs_scan "$JK" "$ART/evalK.pjtw" "$ART/vsK.log"

echo "=== DIAGNOSTIC mécanisme : corr(éval↔Scan-d9) par bande, set finale HELD-OUT (0328, <=14p) ==="
python3 - "$CORPUS" "$ART/test.jnnw" "$N" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]; r=bytearray(); k=0
for i in range(tot):
    rec=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if pc<=14:
        r+=rec; k+=1
        if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r)); print('test finale (<=14p)',k)
PY
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan.jnnw" "$SCAN_BIN" 9 "$NCPU" || true
# rewrite-scores ALIGNÉ : chaque éval réévalue le MÊME fichier Scan (ordre/bitboards identiques → pas le bug 0347).
"$J0" --rewrite-scores-with-nnue "$ART/scan.jnnw" "$ART/jass0.jnnw" --nnue "$ART/eval0.pjtw" >"$ART/rw0.log" 2>&1 || true
"$JK" --rewrite-scores-with-nnue "$ART/scan.jnnw" "$ART/jassK.jnnw" --nnue "$ART/evalK.pjtw" >"$ART/rwK.log" 2>&1 || true
python3 - "$ART/scan.jnnw" "$ART/jass0.jnnw" "$ART/jassK.jnnw" <<'PY' || true
import sys,struct
import numpy as np
REC=38
def load(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    sc=np.empty(n,np.float64); pc=np.empty(n,np.int32); bb=np.empty((n,4),np.uint64)
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32]); bb[i]=(wm,wk,bm,bk)
        pc[i]=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        sc[i]=struct.unpack('<i',rec[33:37])[0]
    return sc,pc,bb
ss,spc,sbb=load(sys.argv[1]); j0,_,b0=load(sys.argv[2]); jk,_,bk=load(sys.argv[3])
n=min(len(ss),len(j0),len(jk))
assert (sbb[:n]==b0[:n]).all() and (sbb[:n]==bk[:n]).all(), "MISALIGNED"
ss,spc,j0,jk=ss[:n],spc[:n],j0[:n],jk[:n]
def corr(a,m): return float(np.corrcoef(a[m],ss[m])[0,1]) if m.sum()>30 else float('nan')
print(f"n={n}  corr(éval-jass ↔ Scan-d9) par bande de pièces :")
for lbl,m in [("<=7p",spc<=7),("8-14p",(spc>=8)&(spc<=14))]:
    print(f"  {lbl:7s} n={int(m.sum()):5d}  men-only={corr(j0,m):+.3f}  king-aware={corr(jk,m):+.3f}")
PY

echo; echo "=========================================================="
echo "   cpx62-0360 — ROIS dans les patterns (vrai levier finale, PAS l'élagage)"
echo "----------------------------------------------------------"
echo "   vs Scan d9 :  men-only=$(rate "$ART/vs0.log")   king-aware=$(rate "$ART/vsK.log")"
echo "   (corr finale par bande ci-dessus : ≤7p men-only ~0.39 attendu — remonte-t-elle ?)"
echo "----------------------------------------------------------"
echo "   king-aware > men-only net + corr finale qui remonte → baker JASS_KING_PATTERNS."
echo "   ≈ → les rois ne lèvent pas la finale dans ce régime → renforce le plafond linéaire (pivot NN)."
echo "=========================================================="
