#!/usr/bin/env bash
# id: ccx33-0313-endgame-data-gen
# description: LEAD 3 — dataset FINALE-ENRICHI (auto-contenu, egdb local ccx33). 0310 : la finale est
# sous-peuplée (≤7p=11%) et le bank eg sous-entraîné → générer beaucoup de finales EXACTES pour nourrir
# le prochain run COMBINÉ phase-split + king-features. Produit : coverage ≤7p exacte (1.0M) + self-play
# egdb-perfect + terminate-at-TB + depth-ramp (1.5M, shardé) → fusion → endgame-cumulative.jnnw (~45% ≤7p).
# Reste sur ccx33 (trop gros pour git) ; le run combiné tournera ici. Pré-flight + rapport de phase.
# expected_duration: ~2-3 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-300}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0313-endgame-data-gen/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base egdb absente sur ccx33 ($APP)"; exit 4; }

EVAL_DEPTH=6; PLAY_DEPTH=8; RAMP="late-mid=12,endgame=16"
COV=1000000; SELF=1500000

preflight_build 1
preflight_note "coverage ≤7p exacte (${COV})" 8
preflight_note "self-play ${SELF} (egdb-perfect + ramp endgame=16, shardé ×$NCPU)" 150
preflight_check

# --- build egdb-ON ---
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off (voir cmake.log)"; exit 5; }
cmake --build build-egdb -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 6; }
JASS=/root/jass/build-egdb/jass
"$JASS" --egdb-selfcheck "$APP" 1 >/dev/null 2>&1 || { echo "ABORT: egdb ne s'ouvre pas"; exit 7; }

# --- coverage ≤7p exacte ---
echo "=== coverage ≤7p exacte (${COV}) ==="
"$JASS" --gen-egdb-wld "$COV" "$ART/cov.jnnw" "$APP" 7 256 12345 2>&1 | tail -1

# --- self-play egdb-perfect + terminate-at-TB + depth-ramp, shardé ---
echo "=== self-play (${SELF}, egdb-perfect + ramp $RAMP, ×$NCPU shards) ==="
PER=$(( (SELF + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do
  JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=256 \
    "$JASS" --gen-data-wdl "$PER" "$ART/self-$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 $((RANDOM*s+s)) \
      --play-depth-by-phase "$RAMP" --label-depth-by-phase "$RAMP" >"$ART/self-$s.log" 2>&1 &
done
wait
echo "self-play shards: $(ls "$ART"/self-*.jnnw 2>/dev/null | wc -l)/$NCPU"

# --- fusion cov + shards → endgame-cumulative.jnnw + rapport de phase ---
python3 - "$ART" <<'PY'
import sys,glob,struct,collections
art=sys.argv[1]; REC=38
files=[art+'/cov.jnnw']+sorted(glob.glob(art+'/self-*.jnnw'))
out=open(art+'/endgame-cumulative.jnnw','wb'); total=0
out.write(b'JNNW'+struct.pack('<I',0))  # placeholder count
def pieces(rec):
    wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32]); return bin(wm|wk|bm|bk).count('1')
phase=collections.Counter()
for f in files:
    try: b=open(f,'rb').read()
    except FileNotFoundError: print("  (manquant:",f,")"); continue
    n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]
        if len(rec)<REC: break
        out.write(rec); phase[pieces(rec)]+=1; total+=1
out.seek(4); out.write(struct.pack('<I',total)); out.close()
le7=sum(v for k,v in phase.items() if k<=7); le10=sum(v for k,v in phase.items() if k<=10); le12=sum(v for k,v in phase.items() if k<=12)
print(f"FUSION  total={total}  → {art}/endgame-cumulative.jnnw")
print(f"PHASE   ≤7p={le7} ({le7/total*100:.1f}%)  ≤10p={le10} ({le10/total*100:.1f}%)  ≤12p={le12} ({le12/total*100:.1f}%)")
print(f"        (cible LEAD 3 : ≤7p ~30-40% vs 11% du cumulatif 0297)")
PY

echo; echo "=========================================================="
echo "   ccx33-0313 — dataset FINALE-ENRICHI (LEAD 3)"
echo "   endgame-cumulative.jnnw prêt sur ccx33 pour le run COMBINÉ phase-split + king-features."
echo "=========================================================="
