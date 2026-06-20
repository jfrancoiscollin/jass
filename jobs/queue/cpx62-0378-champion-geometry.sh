#!/usr/bin/env bash
# id: cpx62-0378-champion-geometry
# description: RECOVERY robuste (0376 OOM 3.456M ; 0377 le runner a NETTOYÉ les fichiers de travail dans le tree
# mid-job → feat disparu + artefacts non committés). FIX : tout le travail HORS du tree git (/root/cw-0378 : data,
# feat, builds, pjtw) → immunisé contre le clean du runner ; on copie seulement les FINAUX dans artefacts/ à la toute
# fin. Pool d10(local 0373)+d12(0375), sous-échantillonné 2M (mémoire). Sort : champion poolé (gzippé) + premier point
# géométrie 32cf vs 8cf. ⚠️ à 2M le 32cf (8,5M poids=0,24 pos/poids) est SOUS-FITTÉ → s'il perd, NE PAS le tuer (point
# de + bas volume de la courbe ; cf BOUCLE_VIRTUEUSE §7). Aucun Scan.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0378-champion-geometry/artefacts"; mkdir -p "$ART"
W=/root/cw-0378; rm -rf "$W"; mkdir -p "$W"      # WORKDIR HORS du tree git (immunisé au clean runner)
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000; GEOM=/root/jass-geom-lean8
SRC10=/root/jass/jobs/results/cpx62-0373-virtuous-loop-deep/artefacts.src
H0375=jobs/results/ccx33-0375-salvage-d12/artefacts
preflight_build 2; preflight_train 2000000 3; preflight_note "champion + géométrie (hors-tree)" 120; preflight_check

[ -d "$SRC10" ] && [ -f "$SRC10/cumulative.jnnw" ] || { echo "ABORT-SALVAGE: data d10 (0373 local) recyclée → RÉGÉNÉRER"; exit 4; }
GEN10=$(ls "$SRC10"/gen*.pjtw 2>/dev/null | sort -V | tail -1); [ -n "$GEN10" ] || { echo "ABORT: pas d'éval d10"; exit 4; }
cp "$GEN10" "$W/d10-eval.pjtw"; cp "$SRC10/cumulative.jnnw" "$W/pooled.jnnw"
echo "  d10 (local) : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/pooled.jnnw','rb').read(8)[4:8])[0])") pos"

echo "=== data d12 (0375, git) ==="
ok=0; for i in $(seq 1 120); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$H0375/d12-data.jnnw" 2>/dev/null && { ok=1; break; }; echo "  attente 0375 ($i)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: data d12 absente"; exit 4; }
git show "origin/main:$H0375/d12-data.jnnw" > "$W/d12.jnnw"
git show "origin/main:$H0375/d12-eval.pjtw.gz" 2>/dev/null | gunzip > "$W/d12-eval.pjtw"
python3 - "$W/d12.jnnw" "$W/pooled.jnnw" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC
raw=open(sys.argv[2],'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(sys.argv[2],'r+b'); o.seek(0,2); o.write(b[8:8+n*REC]); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
print(f"  pool {old}+{n}={old+n}")
PY
echo "=== sous-échantillonne le pool à 2M ==="
python3 - "$W/pooled.jnnw" 2000000 <<'PY'
import struct,sys,random
p,cap=sys.argv[1],int(sys.argv[2]); REC=38
b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
if n>cap:
    random.seed(2026); idx=sorted(random.sample(range(n),cap)); out=bytearray()
    for i in idx: out+=body[i*REC:(i+1)*REC]
    open(p,'wb').write(b'JNNW'+struct.pack('<I',cap)+bytes(out)); print(f"  {n} -> {cap}")
PY

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake_jass(){ local B="$1"; cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake-$(basename "$B").log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$W/cmake-$(basename "$B").log" || { echo "ABORT: egdb off"; exit 6; }
  cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build-$(basename "$B").log" 2>&1 || { echo "BUILD FAIL $B"; tail -8 "$W/build-$(basename "$B").log"; exit 6; }; }
echo "=== build 32-pat (hors-tree) ==="; cmake_jass "$W/build-32"; J="$W/build-32/jass"
"$J" --dump-eval-features "$W/pooled.jnnw" "$W/feat" >/dev/null 2>&1   # feat dans W (hors-tree, ne disparaît pas)
direct(){ "$J" --benchmark-nnue-vs-nnue "$1" "$2" 9 6 1 0 >"$3" 2>&1 || true; grep -E 'score rate' "$3" | grep -oE '[0-9.]+' | head -1; }
fit(){ local extra="$1" out="$2" pdir="$3"
  ${pdir:+env JASS_PATTERNS_DIR=$pdir} python3 pattern_jass/tools/train.py --data "$W/pooled.jnnw" --scan-eval \
    --eval-features-file "$W/feat" --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem $extra \
    --out "$out" >"${out%.pjtw}-train.log" 2>&1; [ -f "$out" ] || { echo "TRAIN FAIL $out"; tail -8 "${out%.pjtw}-train.log"; exit 9; }; }

echo "=== départage d10 vs d12 ==="; D=$(direct "$W/d10-eval.pjtw" "$W/d12-eval.pjtw" "$W/d10_vs_d12.log"); echo "  d10 vs d12 = ${D}"
echo "=== CHAMPION (full-fold) ==="; fit "--full-fold" "$W/champion.pjtw" ""
CD10=$(direct "$W/champion.pjtw" "$W/d10-eval.pjtw" "$W/c_d10.log"); CD12=$(direct "$W/champion.pjtw" "$W/d12-eval.pjtw" "$W/c_d12.log")
echo "=== 32+color-fold ==="; fit "--color-fold" "$W/eval32cf.pjtw" ""
echo "=== réduit à 8-pat + 8+color-fold ==="
python3 pattern_jass/tools/gen_patterns.py --emit --drop diag_0,diag_1,diag_2,diag_3,diag_4,diag_5,diag_6,anti_0,anti_1,anti_2,anti_3,anti_4,anti_5,anti_6,anti_7,horiz_0,horiz_1,horiz_2,horiz_3,horiz_4,sq_0,sq_1,sq_2,sq_3 >"$W/gen8.log" 2>&1
[ "$(grep -oE 'NUM_PATTERNS *= *[0-9]+' pattern_jass/src/pattern.hpp | grep -oE '[0-9]+' | head -1)" = "8" ] || { echo "ABORT drop8"; exit 7; }
cmake_jass "$W/build-8"; J8="$W/build-8/jass"
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
fit "--color-fold" "$W/eval8cf.pjtw" "$GEOM"
grep -qE "17M -> *8,503,072" "$W/eval8cf-train.log" && { echo "ABORT: arm-8 flippé 32"; exit 8; }
echo "=== MATCH cross-arch 32cf vs 8cf ==="
python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/eval32cf.pjtw" --jass-b "$J8" --pattern-b "$W/eval8cf.pjtw" \
  --depth 9 --pairs 8 --max-plies 160 >"$W/geo.log" 2>&1 || true
G=$(grep -E 'A score rate' "$W/geo.log" | grep -oE '[0-9.]+' | head -1)

# --- copie des FINAUX dans artefacts/ (committé) à la toute fin ---
gzip -c "$W/champion.pjtw" > "$ART/champion.pjtw.gz"
gzip -c "$W/pooled.jnnw" > "$ART/pooled-2M.jnnw.gz"
cp "$W/geo.log" "$W/d10_vs_d12.log" "$ART/" 2>/dev/null || true
echo; echo "=========================================================="
echo "   cpx62-0378 — CHAMPION + GÉOMÉTRIE (pool 2M, hors-tree)"
echo "   départage d10 vs d12 = ${D}"
echo "   champion vs d10 = ${CD10}  |  champion vs d12 = ${CD12}   (>0.5 vs LES DEUX → pooler gagne)"
echo "   GÉOMÉTRIE 32cf vs 8cf = ${G}   (⚠️ 2M = 32cf sous-fitté ; s'il perd, point bas de la courbe, NE PAS le tuer)"
echo "   champion.pjtw.gz + pooled-2M.jnnw.gz committés (gzip = fix cap 95Mo)."
echo "=========================================================="