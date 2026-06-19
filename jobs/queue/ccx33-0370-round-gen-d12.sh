#!/usr/bin/env bash
# id: ccx33-0370-round-gen-d12
# description: TOUR 1 boucle distribuée poolée (CAP RELEVÉ). ccx33 génère sa part : self-play d12 piloté par le CHAMPION
# (de 0369, tiré de git), au cap relevé (NPER = débit×30min, plafond 800k au lieu de 160k), et committe le shard
# `round1-d12.jnnw` dans git pour que cpx62-0371 le poole. Self-play piloté par le meilleur = positions on-distribution.
# DÉPLOYER après 0369. Aucun Scan.
# expected_duration: ~40 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0370-round-gen-d12/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
PLAY_DEPTH=12; EVAL_DEPTH=4; TARGET_GEN_MIN=30; CAP=800000
CHAMP_PATH=jobs/results/cpx62-0369-merge-champion/artefacts/champion.pjtw
preflight_build 1; preflight_note "gen d12 cap relevé + commit shard" 60; preflight_check

echo "=== récupère le champion (0369) ==="
ok=0; for i in $(seq 1 20); do git fetch origin main >/dev/null 2>&1 || true
  git cat-file -e "origin/main:$CHAMP_PATH" 2>/dev/null && { ok=1; break; }; echo "  attente champion 0369 ($i/20)"; sleep 30; done
[ "$ok" = 1 ] || { echo "ABORT: champion 0369 absent"; exit 4; }
git show "origin/main:$CHAMP_PATH" > "$ART/champion.pjtw"

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted

gen(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$out.$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >"$out.$s.log" 2>&1 &
  done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*.jnnw"),key=lambda p:int(re.search(r"\.(\d+)\.jnnw$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print('shard',tot)
PY
  rm -f "$out".*.jnnw
}
echo "=== sonde débit @ d${PLAY_DEPTH} → NPER (cap relevé ${CAP}) ==="
t0=$(date +%s); gen "$ART/champion.pjtw" $((NCPU*120)) "$ART/probe" >/dev/null 2>&1; dt=$(( $(date +%s) - t0 )); [ "$dt" -lt 1 ] && dt=1
RATE=$(( NCPU*120*60/dt )); NPER=$(( RATE*TARGET_GEN_MIN )); [ "$NPER" -lt 50000 ] && NPER=50000; [ "$NPER" -gt "$CAP" ] && NPER="$CAP"
echo "  débit ≈ ${RATE} pos/min @ d12 → NPER=${NPER}"
rm -f "$ART/probe"

echo "=== génération d12 du tour (NPER=${NPER}) ==="
gen "$ART/champion.pjtw" "$NPER" "$ART/round1-d12.jnnw"
echo; echo "=== shard d12 committé ($(python3 -c "import struct;print(struct.unpack('<I',open('$ART/round1-d12.jnnw','rb').read(8)[4:8])[0])") positions) → prêt pour cpx62-0371 ==="