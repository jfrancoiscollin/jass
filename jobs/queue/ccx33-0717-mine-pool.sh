#!/usr/bin/env bash
# id: ccx33-0717-mine-pool
# description: G2/G3 (mémo nourrir-gymnase) — mine un POOL de conversion certifié + gèle un set conv_self DISJOINT.
# OFFLINE (ne touche pas la boucle, tourne // de 0716). Moissonne le corpus T1 committé (on-distribution) → candidats
# HORS-TB (N_TB+1/+2/+3, avantage ≥+1) → certifie par deep-relabel d14+egdb (WIN-camp-avantagé, pas de « probablement
# gagné ») → filtre + strates + ASSERTIONS G3 (∩thermo-224=∅, ∩conv_self-eval=∅) → carve conv_self_eval_set FIGÉ
# disjoint du training. ⚠ CRITIQUE : conv_self était mesuré sur le MÊME pool que le training (train-on-test) — ce set
# figé le corrige. Livrables committés : conversion_pool_v2.fen + conv_self_eval_set.fen + manifest. Build egdb.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0717.lock
if ! flock -n 9; then echo "ABORT 0717 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0717-mine-pool/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0717-mine-pool/artefacts"
W=/root/cw-0717
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
NCAND=48000; MAX_OVER=3; MIN_ADV=1; ARB_DEPTH=14; EVAL_N=400; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== G2 MINAGE POOL CONVERSION + G3 gel conv_self — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show "origin/$SRC_BRANCH:tools/mine_conversion_pool.py" > tools/mine_conversion_pool.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src 2>/dev/null||true; rm -f tools/mine_conversion_pool.py; }
[ -s tools/mine_conversion_pool.py ] || { say "ABORT: mine_conversion_pool.py absent"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/mine_conversion_pool.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0717 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0717 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }

# --- extract candidats HORS-TB + avantage (moisson on-distribution) ---
say ""; say "=== extract candidats (HORS-TB N_TB+1..+$MAX_OVER, avantage ≥$MIN_ADV) du corpus T1 ==="
python3 tools/mine_conversion_pool.py extract --corpus "$W/corpus.jnnw" --out "$W/cand.jnnw" \
  --n-cand "$NCAND" --max-over "$MAX_OVER" --min-adv "$MIN_ADV" | tee -a "$RES"
NCA=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/cand.jnnw','rb').read(8)[4:8])[0])")

# --- certif : deep-relabel d$ARB_DEPTH + egdb, shardé ---
say ""; say "=== certif d$ARB_DEPTH+egdb sur $NCA candidats ($NSH shards) ==="
python3 - "$W/cand.jnnw" "$W/cc" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3])
for s in range(nsh):
    idx=[i for i in range(n) if i%nsh==s]
    out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out)
PY
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout 4000 "$J" --deep-relabel "$W/cc.$s.jnnw" "$W/cc_rel.$s.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
python3 - "$W/certified.jnnw" "$W/cc_rel" <<'PY'
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*.jnnw")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY

# --- filter + assertions G3 + carve conv_self figé disjoint ---
say ""; say "=== filter (WIN-camp-avantagé) + G3 (∩thermo=∅, ∩eval=∅) + carve set conv_self FIGÉ ($EVAL_N) ==="
python3 tools/mine_conversion_pool.py filter --certified "$W/certified.jnnw" --thermo data/pcblues_thermometre.fen \
  --min-adv "$MIN_ADV" --eval-n "$EVAL_N" --out-pool "$ART/conversion_pool_v2.fen" \
  --out-eval "$ART/conv_self_eval_set.fen" --manifest "$ART/mine_manifest.json" 2>&1 | tee -a "$RES" || { say "ABORT filter (assertion G3 ?)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0717 ABORT filter/assert"; exit 8; }
NV2=$(grep -cvE '^\s*#' "$ART/conversion_pool_v2.fen" 2>/dev/null||echo 0)
NEV=$(grep -cvE '^\s*#' "$ART/conv_self_eval_set.fen" 2>/dev/null||echo 0)
say "  pool_v2=$NV2 positions ; conv_self_eval_set=$NEV positions (FIGÉ, disjoint)"

commit_to_main "$ART/conversion_pool_v2.fen" "$ARTREL/conversion_pool_v2.fen" "0717 conversion_pool_v2 (certifié, HORS-TB, ∩thermo=∅)" >/dev/null 2>&1||true
commit_to_main "$ART/conv_self_eval_set.fen" "$ARTREL/conv_self_eval_set.fen" "0717 conv_self_eval_set FIGÉ (disjoint training, corrige train-on-test)" >/dev/null 2>&1||true
commit_to_main "$ART/mine_manifest.json" "$ARTREL/mine_manifest.json" "0717 mine manifest" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0717 FIN minage : pool_v2=$NV2 eval_set=$NEV (cand=$NCA)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0717 FINI ==="
rm -rf "$W"
