#!/usr/bin/env bash
# T1-bis ADJ+G1 runner v2 — à instancier sous jobs/queue avec un nouveau numéro.
#
# Corrections par rapport à 0727 :
#   * générateur L3 historique chargé depuis sa branche source et vérifié par blob SHA ;
#   * set -euo pipefail + contrôle de chaque PID et de chaque shard ;
#   * source-tags ≠ certificats : fusion via apply_label_policy.py ;
#   * quota G1 exprimé en POSITIONS et vérifié après génération ;
#   * cache contrôlé avec le nombre réel de moteurs simultanés ;
#   * conversion mesurée séparément sur p1/p2/p3/p4 ;
#   * agrégation stricte, aucun JSON manquant ignoré ;
#   * promotion fail-closed si un gate est incomplet.
set -euo pipefail
cd /root/jass

JOB_ID="${JOB_ID:?export JOB_ID, ex. cpx62-0728-t1bis-adj-g1-v2}"
TOUR="${TOUR:-T1-bis}"
PARENT_PJTW_GZ="${PARENT_PJTW_GZ:?pattern parent .pjtw.gz sur main}"
FIXED_PJTW_GZ="${FIXED_PJTW_GZ:-$PARENT_PJTW_GZ}"
GYM_MIN_POS="${GYM_MIN_POS:?quota minimum de positions G1 pré-engagé}"
TIP_CERTS_JSONL="${TIP_CERTS_JSONL:-}"
MIN_PROTECTED_TIP_RATE="${MIN_PROTECTED_TIP_RATE:-0.0}"
ALLOW_MTC_SKIP="${ALLOW_MTC_SKIP:-0}"

L3_REF="claude/pcblues-corpus-extraction-2i92bj"
L3_SCAN_BLOB="1a19b30cded45281a628d2f9b631f2719d7fbc51"

exec 9>"/root/.jass-${JOB_ID}.lock"
flock -n 9 || { echo "ABORT: instance active"; exit 0; }

NCPU=$(nproc)
NSH_GEN="${NSH_GEN:-$NCPU}"
NSH_RELABEL="${NSH_RELABEL:-$NCPU}"
NSH_CONV="${NSH_CONV:-8}"
NSH_GATE="${NSH_GATE:-$NCPU}"
CACHE_MB_RELABEL="${CACHE_MB_RELABEL:-512}"
CACHE_MB_CONV="${CACHE_MB_CONV:-256}"
export JASS_EGDB_CACHE_MB="$CACHE_MB_CONV"

GAMES="${GAMES:-300}"
PLAYD="${PLAYD:-10}"
MAXPLIES="${MAXPLIES:-200}"
MINPC="${MINPC:-36}"
SEEDFRAC="${SEEDFRAC:-0.18}"
ARB_DEPTH="${ARB_DEPTH:-14}"
ANCHOR="${ANCHOR:-0.05}"
MAXIT="${MAXIT:-60}"
CHUNK="${CHUNK:-1000000}"
CONV_DEPTH="${CONV_DEPTH:-10}"
NOPEN="${NOPEN:-300}"
PAIRS="${PAIRS:-1}"
DEPTH="${DEPTH:-9}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
RELABEL_TIMEOUT="${RELABEL_TIMEOUT:-4000}"

GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
G1POOL=jobs/results/ccx33-0718-mine-tip/artefacts/conversion_pool_train_v2.fen
GAUGE1600=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen

ART="/root/jass/jobs/results/$JOB_ID/artefacts"
W="/root/cw-$JOB_ID"
GEOM="/root/geom-$JOB_ID"
mkdir -p "$ART" "$W" "$GEOM"
RES="$W/RESULTS.txt"
: > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}

run_pids(){
  local label="$1"; shift
  local -a pids=("$@")
  local fail=0
  for pid in "${pids[@]}"; do
    if ! wait "$pid"; then fail=$((fail+1)); fi
  done
  [ "$fail" -eq 0 ] || die "$label: $fail processus en échec"
}

merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import glob,re,struct,sys
out,prefix=sys.argv[1:]
def key(p):
    m=re.search(r'\.(\d+)(?:\.jnnw)?$',p); return int(m.group(1)) if m else 10**9
files=sorted(glob.glob(prefix+'*'),key=key)
if not files: raise SystemExit('aucun shard JNNW')
body=bytearray(); total=0
for path in files:
    raw=open(path,'rb').read()
    if raw[:4]!=b'JNNW': raise SystemExit(f'{path}: magic invalide')
    n=struct.unpack('<I',raw[4:8])[0]
    if len(raw)!=8+n*38: raise SystemExit(f'{path}: taille invalide')
    body += raw[8:]; total += n
open(out,'wb').write(b'JNNW'+struct.pack('<I',total)+body)
print(total)
PY
}

merge_bytes(){ python3 - "$1" "$2" <<'PY'
import glob,re,sys
out,prefix=sys.argv[1:]
def key(p):
    m=re.search(r'\.(\d+)$',p); return int(m.group(1)) if m else 10**9
files=sorted(glob.glob(prefix+'*'),key=key)
if not files: raise SystemExit('aucun shard sidecar')
open(out,'wb').write(b''.join(open(p,'rb').read() for p in files))
PY
}

say "=== $JOB_ID / $TOUR — préflight ==="
git fetch origin main develop --quiet
git fetch origin "+refs/heads/$L3_REF:refs/remotes/origin/$L3_REF" --quiet || die "branche L3 historique inaccessible"
ACTUAL_BLOB=$(git rev-parse "origin/$L3_REF:tools/scan_selfplay_gen.py")
[ "$ACTUAL_BLOB" = "$L3_SCAN_BLOB" ] || die "blob générateur L3 inattendu: $ACTUAL_BLOB"
git show "origin/$L3_REF:tools/scan_selfplay_gen.py" > tools/scan_selfplay_gen.py
for file in tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py pattern_jass/tools/make_bootstrap_eval.py; do
  git show "origin/develop:$file" > "$file" || die "$file absent develop"
done

for test in \
  test_oracle_cert test_promotion_gate test_probe_mining test_cache_guard \
  test_apply_label_policy test_aggregate_conv_shards test_split_stratified_fen; do
  python3 "jobs/tests/$test.py" > "$W/$test.log" 2>&1 || die "test rouge: $test"
done
python3 -m py_compile \
  tools/scan_selfplay_gen.py jobs/tools/oracle_cert.py jobs/tools/apply_label_policy.py \
  jobs/tools/aggregate_conv_shards.py jobs/tools/split_stratified_fen.py \
  jobs/tools/promotion_gate.py jobs/tools/conv_fixed_wdl.py

python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB_RELABEL" --procs "$NSH_RELABEL" > "$ART/cache_relabel.json" || die "cache relabel"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB_CONV" --procs "$((NSH_CONV*3))" > "$ART/cache_conv.json" || die "cache conversion (3 moteurs/shard)"
if ! python3 jobs/tools/mtc_audit.py --cache-mb "$CACHE_MB_RELABEL" --procs "$NSH_RELABEL" --smoke-ok skip --out "$ART/mtc_audit.json"; then
  [ "$ALLOW_MTC_SKIP" = 1 ] || die "audit MTC non vert"
  say "WARN: audit MTC explicitement ignoré"
fi

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
for file in $(git diff --name-only origin/main origin/develop -- src pattern_jass/src); do git show "origin/develop:$file" > "$file"; done
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB introuvable"
export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS_EGDB > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build sans EGDB"
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1 || die "build"
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

git show "origin/main:$PARENT_PJTW_GZ" | gunzip > "$W/parent.pjtw"
git show "origin/main:$FIXED_PJTW_GZ" | gunzip > "$W/fixed.pjtw"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw"
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw"
git show "origin/main:$G1POOL" > "$W/g1_pool.fen"
git show "origin/main:$GAUGE1600" > "$W/gauge.fen"
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"

say "=== génération ADJ+G1 ==="
pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py \
    --jass "$J" --player-jass-bin "$J" --player-pattern "$W/parent.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPC" --sample-every 1 --depth "$PLAYD" \
    --seed 72800 --nshards "$NSH_GEN" --shard "$shard" \
    --seed-pool "$W/g1_pool.fen" --seed-frac "$SEEDFRAC" \
    --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \
    --label-src-out "$W/lab.$shard" > "$W/sp.$shard.log" 2>&1 &
  pids+=("$!")
done
run_pids generation "${pids[@]}"
for shard in $(seq 0 $((NSH_GEN-1))); do [ -s "$W/sp.$shard" ] && [ -s "$W/lab.$shard" ] || die "sortie génération shard $shard absente"; done
NPOS=$(merge_jnnw "$W/gen.jnnw" "$W/sp.")
merge_bytes "$W/source.tags" "$W/lab."
[ "$(wc -c < "$W/source.tags")" -eq "$NPOS" ] || die "sidecar source désaligné"
GYM_POS=$(python3 - "$W/source.tags" <<'PY'
from pathlib import Path
b=Path(__import__('sys').argv[1]).read_bytes(); print(sum(x==1 for x in b))
PY
)
[ "$GYM_POS" -ge "$GYM_MIN_POS" ] || die "quota G1 positions non atteint: $GYM_POS < $GYM_MIN_POS"
say "positions=$NPOS ; G1=$GYM_POS"

say "=== relabel profond strict ==="
python3 - "$W/gen.jnnw" "$W/rs" "$NSH_RELABEL" <<'PY'
import struct,sys
raw=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',raw[4:8])[0]; body=raw[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    seg=body[s*per*38:(s+1)*per*38]
    open(f'{sys.argv[2]}.{s}.jnnw','wb').write(b'JNNW'+struct.pack('<I',len(seg)//38)+seg)
PY
pids=()
for shard in $(seq 0 $((NSH_RELABEL-1))); do
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/rs.$shard.jnnw" "$W/rr.$shard.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/rr.$shard.log" 2>&1 &
  pids+=("$!")
done
run_pids relabel "${pids[@]}"
for shard in $(seq 0 $((NSH_RELABEL-1))); do [ -s "$W/rr.$shard.jnnw" ] || die "relabel shard $shard absent"; done
merge_jnnw "$W/deep.jnnw" "$W/rr."
[ "$(jnnw_count "$W/deep.jnnw")" -eq "$NPOS" ] || die "relabel incomplet"

POLICY_ARGS=(--original "$W/gen.jnnw" --relabelled "$W/deep.jnnw" --source-tags "$W/source.tags" --out "$W/adj.jnnw" --manifest "$ART/label_policy.json" --min-protected-tip-rate "$MIN_PROTECTED_TIP_RATE")
if [ -n "$TIP_CERTS_JSONL" ]; then POLICY_ARGS+=(--certificates "$TIP_CERTS_JSONL"); fi
python3 jobs/tools/apply_label_policy.py "${POLICY_ARGS[@]}" || die "politique labels"

say "=== fit ancré ==="
"$J" --dump-eval-features "$W/adj.jnnw" "$W/feat" > "$W/dump.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 pattern_jass/tools/wdl_finetune.py --champion "$W/parent.pjtw" --data "$W/adj.jnnw" --feat "$W/feat" \
  --out "$W/candidate.pjtw" --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage \
  --max-iter "$MAXIT" --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 > "$W/fit.log" 2>&1
[ -s "$W/candidate.pjtw" ] || die "candidate absent"

say "=== jauge p1-p4 ==="
python3 jobs/tools/split_stratified_fen.py --input "$W/gauge.fen" --out-dir "$W/strata" --manifest "$ART/gauge_strata.json"
mkdir -p "$ART/conversion"
for stratum in p1_net p2_moyen p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/$stratum.rel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  EXPECTED=$(jnnw_count "$W/$stratum.dec.jnnw")
  [ "$EXPECTED" -gt 0 ] || die "$stratum sans position décisive"
  pids=()
  inputs=()
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$stratum.conv.$shard.json"; inputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$W/candidate.pjtw" \
      --defender-pattern "$W/gen2.pjtw" --pool-jnnw "$W/$stratum.dec.jnnw" --calibrate-tool tools/calibrate_vs_scan.py \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" > "$W/$stratum.conv.$shard.log" 2>&1 &
    pids+=("$!")
  done
  run_pids "conversion $stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$EXPECTED" --max-error-rate 0.08 --stratum "$stratum" --out "$ART/conversion/$stratum.json" || die "agrégation $stratum"
done

python3 - "$ART/conversion" "$ART/conversion.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); reports={p.stem:json.loads(p.read_text()) for p in root.glob('*.json')}
required={'p1_net','p2_moyen','p3_mince','p4_egal'}
assert set(reports)==required, (set(reports),required)
n=sum(r['n_pos'] for r in reports.values()); w=sum(r['n_win'] for r in reports.values())
out={'global': None if not n else round(w/n,6), **{k:v['conversion'] for k,v in reports.items()}, 'reports':reports}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2))
PY

say "=== gates + promotion jeune ==="
# Le script d'instanciation doit utiliser le harnais jass_vs_jass_arch et produire
# deux JSON W/D/L complets : $W/gate_parent.json et $W/gate_fixed.json.
# Cette séparation est volontaire : T2/T3 ne peuvent pas réutiliser le même match.
[ -s "$W/gate_parent.json" ] || die "gate_parent.json absent — câbler le harnais avant lancement"
[ -s "$W/gate_fixed.json" ] || die "gate_fixed.json absent — câbler le harnais avant lancement"
python3 - "$W/gate_parent.json" "$W/gate_fixed.json" "$ART/conversion.json" "$W/promotion_input.json" <<'PY'
import json,sys
p,f,c,out=sys.argv[1:]; conv=json.load(open(c))
json.dump({'vs_parent':json.load(open(p)),'vs_fixed_reference':json.load(open(f)),'conversion':conv},open(out,'w'),indent=2)
PY
python3 jobs/tools/promotion_gate.py --regime young --tour "$TOUR" --input "$W/promotion_input.json" --out "$ART/promotion.json" || die "promotion rejetée/technique"

say "=== $JOB_ID prêt : aucun faux PASS possible ==="
# L'instanciation 0728 doit encore câbler explicitement les deux matches de gate
# et le commit des artefacts. Le template s'arrête plutôt que d'inventer des données.
