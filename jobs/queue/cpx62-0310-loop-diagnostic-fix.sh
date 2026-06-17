#!/usr/bin/env bash
# id: cpx62-0310-loop-diagnostic-fix
# description: REPRISE de 0309 (bug : extension .jnnw manquante dans l'appel train → NO-EG/ENDGAME-ONLY
# ont planté). 0309 a déjà établi : 0 contradiction ≤7p (labels exacts propres). Reste la VRAIE question :
# ablation FULL vs NO-ENDGAME(>7p) vs ENDGAME-ONLY(≤7p) — Elo_vs_hc + endgame_mse chacun. Réutilise les
# splits de 0309 s'ils sont sur le disque, sinon re-split. Verdict : ENDGAME-ONLY endgame_mse plancher
# HAUT → SATURATION représentationnelle (capacité) ; NO-EG Elo ≫ FULL → finales tirent le fit global.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0310-loop-diagnostic-fix/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CUM=/root/jass/jobs/results/cpx62-0297-saturate-loop/artefacts.src/cumulative.jnnw
[ -f "$CUM" ] || { echo "ABORT: cumulatif 0297 absent ($CUM)"; exit 3; }

rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- splits : réutiliser ceux de 0309 si présents, sinon re-split ---
PREV=/root/jass/jobs/results/cpx62-0309-loop-diagnostic/artefacts.src
NOEND="$ART/noend.jnnw"; ENDONLY="$ART/endonly.jnnw"
if [ -f "$PREV/noend.jnnw" ] && [ -f "$PREV/endonly.jnnw" ]; then
  NOEND="$PREV/noend.jnnw"; ENDONLY="$PREV/endonly.jnnw"; echo "réutilise les splits de 0309"
else
  echo "re-split du cumulatif (≤7p vs >7p)"
  python3 - "$CUM" "$ART" <<'PY'
import sys,struct
src,art=sys.argv[1],sys.argv[2]
b=open(src,'rb').read(); head=b[:8]; n=struct.unpack('<I',head[4:8])[0]; body=b[8:]; REC=38
def pieces(rec):
    wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32]); return bin(wm|wk|bm|bk).count('1')
rn=bytearray(); re=bytearray(); nn=ne=0
for i in range(n):
    rec=body[i*REC:(i+1)*REC]
    if len(rec)<REC: break
    if pieces(rec)<=7: re+=rec; ne+=1
    else: rn+=rec; nn+=1
open(art+'/noend.jnnw','wb').write(head[:4]+struct.pack('<I',nn)+bytes(rn))
open(art+'/endonly.jnnw','wb').write(head[:4]+struct.pack('<I',ne)+bytes(re))
print(f"split: no-endgame(>7p)={nn}  endgame-only(≤7p)={ne}")
PY
fi

CFOLD="--full-fold --king-patterns"
# train <data.jnnw> <out_prefix>  → echoes endgame_mse
train(){
  "$JASS" --dump-eval-features "$1" "$2.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2.feat" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD --out "$2.pjtw" >"$2-train.log" 2>&1
  grep -oE 'val/phase mse : .*' "$2-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2
}
elo(){ local lg="$1-elo.log"; "$JASS" --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

echo "=== FULL ==="
EG_F=$(train "$CUM" "$ART/full");        [ -f "$ART/full.pjtw" ]    && EL_F=$(elo "$ART/full")    || EL_F=NA
echo "  FULL         endgame_mse=$EG_F  Elo_vs_hc=$EL_F"
echo "=== NO-ENDGAME (>7p) ==="
EG_N=$(train "$NOEND" "$ART/noend");     [ -f "$ART/noend.pjtw" ]   && EL_N=$(elo "$ART/noend")   || EL_N=NA
echo "  NO-ENDGAME   endgame_mse=$EG_N  Elo_vs_hc=$EL_N"
echo "=== ENDGAME-ONLY (≤7p, labels exacts) ==="
EG_E=$(train "$ENDONLY" "$ART/endonly"); [ -f "$ART/endonly.pjtw" ] && EL_E=$(elo "$ART/endonly") || EL_E=NA
echo "  ENDGAME-ONLY endgame_mse=$EG_E  Elo_vs_hc=$EL_E"

echo; echo "=========================================================="
echo "   cpx62-0310 — DIAGNOSTIC du drift 0297 (reprise, ablation complète)"
echo "   rappel 0309 : 0 contradiction ≤7p (labels exacts propres) ; ≤7p=11.3% des données."
echo "----------------------------------------------------------"
echo "  FULL         : mse=$EG_F  Elo=$EL_F"
echo "  NO-ENDGAME   : mse=$EG_N  Elo=$EL_N"
echo "  ENDGAME-ONLY : mse=$EG_E  Elo=$EL_E"
echo "----------------------------------------------------------"
echo "  ENDGAME-ONLY endgame_mse HAUT (le linéaire ne descend pas même sur finales-seules)"
echo "     → SATURATION représentationnelle CONFIRMÉE → capacité (FM/MLP)."
echo "  NO-ENDGAME Elo ≫ FULL Elo → les finales TIRENT le fit global vers le bas (conflit linéaire)."
echo "  ENDGAME-ONLY mse BAS mais FULL mse HAUT → ce n'est PAS la capacité, c'est un CONFLIT de"
echo "     données (le midgame écrase la finale) → re-pondérer / phase-split, 2.04 récupérable."
echo "=========================================================="
