#!/usr/bin/env bash
# L3 — quel bouton d'exploration achète le plus de COUVERTURE à volume constant.
#
# `cpx62-1130` a nommé le verrou : à 2 M records identiques, le corpus on-policy
# visite 124 948 buckets contre 130 086, soit −3,9 %. Un générateur plus fort
# joue plus étroit ; il échange de la couverture contre de la qualité
# d'étiquette, et la couverture est la ressource rare (~4,3 observations par
# paramètre libre). Faire tourner la manivelle de l'autojeu ne rouvre donc rien.
#
# Cette sonde ne joue AUCUNE partie de porte et ne fitte RIEN. Elle engendre le
# même volume sous plusieurs réglages d'exploration et compte les buckets
# atteints — la mesure qui décide, avant de dépenser un fit et une porte.
#
# ⚠️ DEUX POINTS DE MÉTHODE, tous deux payés ailleurs :
#
# 1. **`--split-selfplay-rngs` sur TOUTES les cellules.** Sans lui, ouvertures,
#    échantillonnage et exploration tirent dans UN flux partagé : une cellule qui
#    consomme un nombre différent de tirages (top-k en consomme, l'uniforme non)
#    désynchronise toutes les ouvertures suivantes, et les cellules cessent
#    d'être appariées sur ce qu'on voulait justement tenir fixe. Le commentaire
#    de `main.cpp` le dit explicitement ; l'ignorer confondrait « bouton » et
#    « ouvertures ».
# 2. **Une cellule RÉPLIQUE** (`BASEBIS`, même réglage, autre graine). Sans elle
#    on ne sait pas ce que « différent » veut dire : l'écart mesuré à
#    `cpx62-1130` était de 3,9 %, donc l'écart graine-à-graine doit être connu
#    avant d'appeler un classement.
#
# Le fold compte : la couverture est un nombre de buckets canoniques DISTINCTS,
# donc elle est définie par le pliage. Tout fit L3 tourne sous `--exact-fold`
# depuis le 1er août, la sonde compte donc en `--fold exact`. Un chiffre
# color-fold n'est pas comparable et ne doit jamais l'être.
#
# Aucune promotion, aucun chaînage automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${CHAMPION_PREFIX:?}"; : "${EXPECTED_CHAMPION_JOB:?}"; : "${CHAMPION_FILE:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$ART/cells"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

RECORDS_PER_CELL="${RECORDS_PER_CELL:-500000}"
PRODUCERS="${PRODUCERS:-12}"
LABEL_DEPTH=4; PLAY_DEPTH=8; MAXPLIES=260     # recette de génération, inchangée
GEN_TIMEOUT="${GEN_TIMEOUT:-1800}"            # par shard, pas pour le job
MIN_RECORDS_FRAC="${MIN_RECORDS_FRAC:-95}"    # plancher : < 95 % du visé = cellule morte
MAX_SIDE_SKEW="${MAX_SIDE_SKEW:-0.10}"        # canari WDL du registre §5.2 bis
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

# nom  rop  eps  decay  topk  margin  seed   — UN facteur bouge par cellule
# BASE = la recette courante ; BASEBIS = même recette, autre graine (bruit).
CELLS="${CELLS:-\
BASE     8  8  60 0 0  1618033
BASEBIS  8  8  60 0 0  2718281
ROP16   16  8  60 0 0  1618033
EPS16    8 16  60 0 0  1618033
NODECAY  8  8   0 0 0  1618033
TOPK     8  8  60 3 30 1618033}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'cells_done=%s\n' "$(find "$ART/cells" -name '*.json' 2>/dev/null | wc -l || true)"
        awk '/positions$/ { d[FILENAME]=$4; t[FILENAME]=$6 }
             END { for (k in d) { s+=d[k]; u+=t[k] }
                   if (u>0) printf "cell_positions=%d/%d (%.1f%%)\n", s, u, 100*s/u }' \
          "$W"/gen-s*.log 2>/dev/null || true
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 5000 ] || die "moins de 5 Go libres (${DFA} Mo)"
NCELLS=$(printf '%s\n' "$CELLS" | grep -c . || true)
NCPU=$(nproc)
say "  nproc=$NCPU libre=${DFA}Mo producteurs=$PRODUCERS cellules=$NCELLS × ${RECORDS_PER_CELL} records"
monitor

stage fetch-champion
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_PREFIX" \
  --file "artefacts/$CHAMPION_FILE=champion.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-champion.json" \
  --expected-state completed > "$W/fetch.log" 2>&1 || die "fetch du champion en échec"
python3 - "$ART/verified-champion.json" "$EXPECTED_CHAMPION_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("champion identity/state mismatch")
PY
gunzip -c "$IN/champion.pjtw.gz" > "$W/CHAMPION.pjtw"
say "  champion ✓ ($EXPECTED_CHAMPION_JOB)"

stage build
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cp pattern_jass/tools/symmetry.py "$GEOM/symmetry.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
grep -q "warm_kings_endgame_bitbases" src/hub.cpp ||
  { restore_src; die "engine predates the movetime endgame bake"; }
grep -q '"--split-selfplay-rngs"' src/main.cpp ||
  { restore_src; die "le moteur ignore --split-selfplay-rngs : cellules non appariables"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/CHAMPION.pjtw" > "$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "le binaire ne charge pas le champion"
say "  build ✓, champion chargeable, --split-selfplay-rngs présent"

# Round-trip écriture→lecture AVANT de dépenser six cellules : la sonde de
# couverture doit savoir lire ce que le moteur écrit, au format qu'il écrit.
stage smoke-roundtrip
timeout 600 "$J" --gen-data-wdl 2000 "$W/smoke.jnnw" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" 42 \
  --nnue "$W/CHAMPION.pjtw" --search-params-play "$Q00" --wdl-zero-score \
  --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 --split-selfplay-rngs \
  --pair-openings --drop-plycap --sample-meta-out "$W/smoke.jsm" \
  > "$W/smoke.log" 2>&1 || die "smoke de génération en échec"
PYTHONPATH="$GEOM" python3 jobs/tools/l3_bucket_visits.py --fold exact \
  --data "$W/smoke.jnnw" --out "$W/smoke-cov.json" > "$W/smoke-cov.log" 2>&1 ||
  die "smoke de couverture en échec — le parseur ne lit pas ce que le moteur écrit"
python3 - "$W/smoke-cov.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["fold"] == "exact", r["fold"]
assert r["geometry"]["trained_buckets_total"] == 2125764, r["geometry"]
assert r["coverage"]["visited_buckets"] > 0, "aucun bucket visité sur le smoke"
PY
rm -f "$W/smoke.jnnw" "$W/smoke.jsm"
say "  round-trip écriture→lecture ✓ (fold=exact, TB=2 125 764)"

stage measure-cells
: > "$W/cells.tsv"
while read -r NAME ROP EPS DECAY TOPK MARGIN SEED; do
  [ -n "${NAME:-}" ] || continue
  echo "cell=$NAME" > "$STAGE"
  rm -f "$W"/gen-s*.log "$W"/gen-s*.jnnw "$W"/done-s*
  base=$((RECORDS_PER_CELL / PRODUCERS)); rem=$((RECORDS_PER_CELL % PRODUCERS))
  pids=(); parts=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$W/gen-s$shard.jnnw"
    ( timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" "$data" \
        "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((SEED+shard)) \
        --nnue "$W/CHAMPION.pjtw" --search-params-play "$Q00" --wdl-zero-score \
        --random-open-plies "$ROP" --explore-eps "$EPS" --explore-decay-plies "$DECAY" \
        --explore-topk "$TOPK" --explore-margin "$MARGIN" --split-selfplay-rngs \
        --pair-openings --drop-plycap \
        > "$W/gen-s$shard.log" 2>&1 < /dev/null
      echo "$?" > "$W/done-s$shard" ) &
    pids+=("$!"); parts+=("$data")
  done
  # ⚠️ JAMAIS `wait` nu tant que le monitor tourne : il attendrait aussi le
  # monitor, qui boucle jusqu'au finalize → interblocage circulaire (0665/0668).
  wait "${pids[@]}"
  bad=0
  for shard in $(seq 0 $((PRODUCERS-1))); do
    [ "$(cat "$W/done-s$shard" 2>/dev/null || echo 1)" = 0 ] || bad=$((bad+1))
  done
  [ "$bad" -eq 0 ] || die "cellule $NAME : $bad producteur(s) en échec sur $PRODUCERS"
  for log in "$W"/gen-s*.log; do
    grep -q 'label_score_searches=0' "$log" ||
      die "cellule $NAME : recherche d'étiquette par score dans $log"
  done
  cat "$W"/gen-s*.log > "$W/cell-$NAME.log"
  PYTHONPATH="$GEOM" python3 jobs/tools/l3_bucket_visits.py --fold exact \
    --data "${parts[@]}" --out "$ART/cells/$NAME-coverage.json" \
    > "$W/cov-$NAME.log" 2>&1 || die "cellule $NAME : mesure de couverture en échec"
  python3 - "$NAME" "$ART/cells/$NAME-coverage.json" "$W/cell-$NAME.log" \
           "$RECORDS_PER_CELL" "$MIN_RECORDS_FRAC" "$MAX_SIDE_SKEW" "$W/cells.tsv" <<'PY'
import json, re, sys
name, cov_path, log_path, target, min_frac, max_skew, out = sys.argv[1:8]
cov = json.load(open(cov_path))
log = open(log_path, encoding="utf-8", errors="replace").read()

records = cov["corpus"]["total_records"]
# Plancher explicite : une cellule sous-produite n'est PAS « neutre », elle est
# morte, et un classement qui l'inclut compare deux volumes différents.
if records < int(target) * int(min_frac) / 100:
    raise SystemExit(f"{name}: {records} records < plancher {min_frac} % de {target}")

w = sum(int(m) for m in re.findall(r"win=(\d+)", log))
l = sum(int(m) for m in re.findall(r"loss=(\d+)", log))
d = sum(int(m) for m in re.findall(r"draw=(\d+)", log))
tot = w + l + d
if tot == 0:
    raise SystemExit(f"{name}: aucune ligne WDLDIST lisible")
skew = abs(w - l) / tot
# Canari WDL du registre : un corpus décalibré peut monter en couverture tout
# en détruisant le signal de valeur (hard replay v1, −648 Elo, couverture EN
# HAUSSE). La couverture seule ne suffit donc jamais à élire une cellule.
flag = "OK" if skew <= float(max_skew) else "WDL_SKEW"

eps_events = sum(int(m) for m in re.findall(r"eps_events=(\d+)", log))
eps_changed = sum(int(m) for m in re.findall(r"eps_changed_best=(\d+)", log))
plies = sum(int(m) for m in re.findall(r"play_plies=(\d+)", log))
openings = sum(int(m) for m in re.findall(r" openings=(\d+)", log))

row = dict(cell=name, records=records,
           visited=cov["coverage"]["visited_buckets"],
           per_100k=round(cov["coverage"]["visited_buckets"] / records * 100000, 1),
           coverage=cov["coverage"]["coverage_fraction"],
           ge_10=cov["coverage"]["buckets_with_at_least"]["ge_10"],
           ge_100=cov["coverage"]["buckets_with_at_least"]["ge_100"],
           gini=cov["concentration"]["gini"],
           draws=round(d / tot, 4), skew=round(skew, 4),
           openings=openings, plies=plies,
           eps_events=eps_events, eps_changed_best=eps_changed, guard=flag)
with open(out, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(row, sort_keys=True) + "\n")
print(f"  {name:8s} buckets={row['visited']:>8,} /100k={row['per_100k']:>7} "
      f"gini={row['gini']:.3f} nulles={row['draws']:.3f} skew={row['skew']:.3f} {flag}")
PY
  tail -1 "$W/cells.tsv" > /dev/null   # échoue si la cellule n'a rien écrit
  say "  cellule $NAME mesurée"
done <<< "$CELLS"

stage rank
python3 - "$W/cells.tsv" "$ART/coverage-ranking.json" "$ART/JASS_CONTROL_SUMMARY.json" \
         "$RECORDS_PER_CELL" <<'PY' | tee -a "$RES"
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
out_rank, out_sum, target = sys.argv[2], sys.argv[3], int(sys.argv[4])
by = {r["cell"]: r for r in rows}
if "BASE" not in by or "BASEBIS" not in by:
    raise SystemExit("BASE et BASEBIS obligatoires : sans réplique, aucun écart n'est interprétable")

base = by["BASE"]["visited"]
noise = abs(by["BASEBIS"]["visited"] - base) / base      # écart graine-à-graine
print(f"  bruit graine-à-graine (BASE vs BASEBIS) = {noise*100:.2f} %")
print(f"  {'cellule':8s} {'buckets':>9s} {'Δ vs BASE':>10s} {'gini':>6s} {'nulles':>7s} {'garde':>9s}")
ranked = sorted(rows, key=lambda r: -r["visited"])
for r in ranked:
    delta = (r["visited"] - base) / base
    verdict = "="
    if r["cell"] not in ("BASE", "BASEBIS"):
        verdict = ">" if delta > 2 * noise else ("<" if delta < -2 * noise else "~")
    print(f"  {r['cell']:8s} {r['visited']:>9,} {delta*100:>9.2f}% "
          f"{r['gini']:>6.3f} {r['draws']:>7.3f} {r['guard']:>9s} {verdict}")

clean = [r for r in ranked if r["guard"] == "OK" and r["cell"] not in ("BASE", "BASEBIS")]
best = clean[0] if clean else None
gain = (best["visited"] - base) / base if best else 0.0
# Le seuil est le bruit mesuré, pas un chiffre choisi : sous 2x l'écart
# graine-à-graine, un classement ne distingue rien.
if best and gain > 2 * noise:
    verdict = f"COVERAGE_KNOB_FOUND_{best['cell']}"
else:
    verdict = "COVERAGE_KNOBS_ALL_WITHIN_NOISE"
print(f"  {verdict}")

json.dump({"schema": 1, "cells": rows, "base_visited": base,
           "seed_to_seed_noise": round(noise, 6),
           "threshold_is_twice_the_measured_noise": round(2 * noise, 6),
           "records_per_cell": target, "fold": "exact", "verdict": verdict},
          open(out_rank, "w"), indent=2, sort_keys=True)
json.dump({"schema": 1, "verdict": verdict, "diagnostic_only": True,
           "plays_no_gate_games": True, "fits_nothing": True,
           "promotion_authorized": False, "automatic_next_job": None,
           "seed_to_seed_noise": round(noise, 6),
           "cells": {r["cell"]: {"visited": r["visited"], "guard": r["guard"]} for r in rows}},
          open(out_sum, "w"), indent=2, sort_keys=True)
open(sys.argv[3], "a").write("\n")
PY

stage report
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/coverage-ranking.json")"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
