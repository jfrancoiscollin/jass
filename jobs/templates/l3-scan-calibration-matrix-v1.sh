#!/usr/bin/env bash
# L3 — matrice de calibration TURNOVER contre Scan, sur le harnais réparé.
#
# Débloquée par `home-1001` (`SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR`).
# Trois questions, une par rangée :
#
#   A. à quelle profondeur Scan notre d9 équivaut-il ?   (Scan d3..d9)
#   B. l'équivalence se déplace-t-elle avec NOTRE profondeur ? (Jass d11)
#   C. à quelle cadence Scan notre mt0.2 équivaut-il ?   (Scan mt0.02..mt0.2)
#
# Chaque rangée contient sa cellule « à armes égales » (d9/d9, d11/d11,
# mt0.2/mt0.2), qui donne le W-N-D brut demandé.
#
# La lecture est une INTERPOLATION du croisement à 0,5 dans chaque rangée. Si
# aucune cellule ne passe au-dessus de 0,5, le job le dit au lieu d'extrapoler :
# l'équivalence est alors seulement bornée, pas mesurée.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"
: "${CHAMPION_TRAIN_PREFIX:?}"; : "${EXPECTED_CHAMPION_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/cells"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        for f in "$W"/cell-*.log; do
          [ -e "$f" ] || continue
          n=$(grep -cE '^  game +[0-9]+:' "$f" 2>/dev/null || echo 0)
          printf 'games_%s=%s\n' "$(basename "$f" .log | sed 's/^cell-//')" "$n"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

# n=1000 en profondeur fixe (~11 min à d9, mesuré en 1001), n=200 au movetime
# (~30 min, la cadence est le seul régime qui coûte). Validé par JFC.
NOPEN_DEPTH=500
NOPEN_TIME=100
PAIRS=1
N_DEPTH=$((NOPEN_DEPTH * 2 * PAIRS))
N_TIME=$((NOPEN_TIME * 2 * PAIRS))
MIN_FRACTION_PCT=90
OPENING_SEED=2718282
MAX_PLIES=200
CACHE_MB=128
TIMEOUT_A=2400
TIMEOUT_B=5400
TIMEOUT_C=3600
TURNOVER_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 5000 ] ||
  die "need 5 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
# Le correctif du coup nul est la condition d'existence de ce job : sans lui
# toute cellule mesure l'abandon de Jass et non sa force (cf home-0999/1000).
grep -q "root_is_drawn" src/search.cpp ||
  die "engine predates the drawn-root fix — every cell would measure a forfeit"
monitor

stage verify-pinned-scan-runtime
[ -x "$SCAN_BIN" ] || die "Scan binary missing at $SCAN_BIN"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary SHA mismatch — runtime is not the pinned one"
say "  runtime Scan ✓ figé : $EXPECTED_SCAN_SHA256"

stage fetch-champion
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-champion-train.json" \
  > "$W/fetch-turnover.log" 2>&1
python3 - "$ART/verified-champion-train.json" "$EXPECTED_CHAMPION_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
gunzip -c "$IN/TURNOVER.pjtw.gz" > "$W/TURNOVER.pjtw"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] ||
  die "TURNOVER model hash drift"
say "  champion ✓ : TURNOVER $TURNOVER_SHA"

stage build-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns8.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
"$J8" --eval-position "$W/TURNOVER.pjtw" 'W:W31,32,33:B18,19,20' >/dev/null 2>&1 ||
  die "8cf engine cannot load TURNOVER"
say "  moteur ✓ : 8cf, correctif racine-nulle présent"

stage build-pools
# Deux pools de tailles différentes, tirés du même générateur et de la même
# graine : les cellules profondeur et cadence ne jouent pas le même nombre de
# parties, mais elles partent de la même distribution d'ouvertures.
for spec in "depth:$NOPEN_DEPTH" "time:$NOPEN_TIME"; do
  kind="${spec%%:*}"; n="${spec#*:}"
  "$J8" --gen-opening-pool "$n" "$W/open-$kind.fen" 8 32 20 "$OPENING_SEED" \
    > "$W/open-$kind.log" 2>&1
  got=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) c++} END {print c+0}' \
    "$W/open-$kind.fen")
  [ "$got" -eq "$n" ] || die "pool $kind count drift: $got != $n"
done
say "  pools ✓ : $NOPEN_DEPTH ouvertures (profondeur), $NOPEN_TIME (cadence)"

run_cell(){
  local name="$1" pool="$2" tmo="$3"; shift 3
  local start end rc
  start=$(date +%s)
  timeout "$tmo" python3 jobs/tools/calibrate_vs_scan.py \
    --jass "$J8" --scan "$SCAN_BIN" --jass-pattern "$W/TURNOVER.pjtw" \
    --jass-search-params "$Q00" --jass-threads 1 \
    --scan-book off --scan-bb-size 0 \
    --openings-file "$W/open-$pool.fen" --pairs "$PAIRS" \
    --max-plies "$MAX_PLIES" "$@" > "$W/cell-$name.log" 2>&1
  rc=$?
  end=$(date +%s)
  printf '%s %s %s\n' "$name" "$rc" "$((end - start))" > "$W/cell-$name.timing"
}

# Vague 1 : la rangée d9 (bon marché) et la rangée cadence (le goulot) ensemble.
# 18 processus sur 16 CPU, mais la rangée d9 libère sa moitié en ~10 min.
stage wave-1-d9-row-and-movetime-row
pids=()
for sd in 3 5 6 7 9; do
  run_cell "A-d9-vs-scan-d$sd" depth "$TIMEOUT_A" \
    --jass-depth 9 --scan-depth "$sd" & pids+=("$!")
done
for sm in 0.02 0.05 0.1 0.2; do
  run_cell "C-mt020-vs-scan-mt$sm" time "$TIMEOUT_C" \
    --jass-movetime 0.2 --scan-movetime "$sm" & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || true; done
say "  vague 1 terminée (9 cellules)"

# Vague 2 : la rangée d11, ~4x le coût de d9, seule sur la machine.
stage wave-2-d11-row
pids=()
for sd in 5 7 9 11; do
  run_cell "B-d11-vs-scan-d$sd" depth "$TIMEOUT_B" \
    --jass-depth 11 --scan-depth "$sd" & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || true; done
say "  vague 2 terminée (4 cellules)"

stage publish-matrix
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$N_DEPTH" "$N_TIME" \
  "$MIN_FRACTION_PCT" "$TURNOVER_SHA" <<'PY'
import json
import math
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
n_depth, n_time = int(sys.argv[4]), int(sys.argv[5])
min_fraction = int(sys.argv[6]) / 100.0
model_sha = sys.argv[7]

# nom de cellule -> (rangée, abscisse Scan, n visé). L'abscisse est la force de
# Scan dans le régime de la rangée : profondeur en plies, cadence en secondes.
ROWS = {
    "A": {"label": "TURNOVER d9 vs Scan à profondeur variable",
          "axis": "scan_depth", "unit": "plies", "target": n_depth},
    "B": {"label": "TURNOVER d11 vs Scan à profondeur variable",
          "axis": "scan_depth", "unit": "plies", "target": n_depth},
    "C": {"label": "TURNOVER mt0.2 vs Scan à cadence variable",
          "axis": "scan_movetime", "unit": "s", "target": n_time},
}
EQUAL_ARMS = {"A": "A-d9-vs-scan-d9", "B": "B-d11-vs-scan-d11",
              "C": "C-mt020-vs-scan-mt0.2"}


def elo(rate):
    if rate is None or rate <= 0.0 or rate >= 1.0:
        return None
    return -400.0 * math.log10(1.0 / rate - 1.0)


def abscissa(name):
    m = re.search(r"-scan-(?:d(\d+)|mt([0-9.]+))$", name)
    return float(m.group(1) if m.group(1) else m.group(2))


cells = {}
for timing in sorted(w.glob("cell-*.timing")):
    name, rc, seconds = timing.read_text().split()
    rc, seconds = int(rc), int(seconds)
    log = (w / f"cell-{name}.log").read_text(errors="replace")
    tally = re.search(r"Jass=(\d+)\s+Scan=(\d+)\s+Draws=(\d+)", log)
    rate_m = re.search(r"Jass score rate:\s*([0-9.]+)", log)
    wins, losses, draws = (
        tuple(int(g) for g in tally.groups()) if tally else (0, 0, 0))
    games = wins + losses + draws
    rate = float(rate_m.group(1)) if rate_m else None
    row = name[0]
    target = ROWS[row]["target"]
    # Le taux de nulles est le signal qui a trahi home-0999 (0 nulle sur 26).
    # La part de forfaits, elle, vaut le taux de défaites et n'apprend rien.
    usable = (rc == 0 and rate is not None
              and games >= int(min_fraction * target))
    se = math.sqrt(rate * (1 - rate) / games) if usable and games else None
    cells[name] = {
        "row": row,
        "scan_setting": abscissa(name),
        "return_code": rc,
        "timed_out": rc == 124,
        "elapsed_s": seconds,
        "games_scored": games,
        "games_target": target,
        "wins": wins, "draws": draws, "losses": losses,
        "draw_share": round(draws / games, 3) if games else None,
        "score_rate": rate,
        "score_se": round(se, 4) if se else None,
        "score_ci95": [round(max(0.0, rate - 1.96 * se), 4),
                       round(min(1.0, rate + 1.96 * se), 4)] if se else None,
        "elo": round(elo(rate), 1) if elo(rate) is not None else None,
        "usable": usable,
    }


def crossing(points):
    """Interpolation linéaire du croisement à 0,5 sur des points triés par
    force croissante de Scan. Rend None plutôt que d'extrapoler : hors de
    l'intervalle mesuré, l'équivalence n'est que bornée."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if (y0 - 0.5) * (y1 - 0.5) <= 0 and y0 != y1:
            return round(x0 + (0.5 - y0) * (x1 - x0) / (y1 - y0), 3)
    return None


rows = {}
for row, meta in ROWS.items():
    pts = sorted(((c["scan_setting"], c["score_rate"])
                  for n, c in cells.items()
                  if c["row"] == row and c["usable"]),
                 key=lambda p: p[0])
    eq_name = EQUAL_ARMS[row]
    eq = cells.get(eq_name)
    x = crossing(pts)
    if x is not None:
        verdict = "measured"
    elif pts and all(y < 0.5 for _, y in pts):
        verdict = "below_weakest_scan_tested"
    elif pts and all(y > 0.5 for _, y in pts):
        verdict = "above_strongest_scan_tested"
    else:
        verdict = "not_enough_usable_cells"
    rows[row] = {
        "label": meta["label"],
        "axis": meta["axis"],
        "unit": meta["unit"],
        "points": [{"scan": x_, "score": y_} for x_, y_ in pts],
        "equivalence": x,
        "equivalence_status": verdict,
        "equal_arms": None if not (eq and eq["usable"]) else {
            "cell": eq_name,
            "wins": eq["wins"], "draws": eq["draws"], "losses": eq["losses"],
            "score_rate": eq["score_rate"],
            "score_ci95": eq["score_ci95"],
            "elo": eq["elo"],
        },
    }

unusable = sorted(n for n, c in cells.items() if not c["usable"])
if unusable:
    verdict = "SCAN_CALIBRATION_MATRIX_PARTIAL_CELLS_FAILED"
elif all(r["equivalence_status"] == "measured" for r in rows.values()):
    verdict = "SCAN_CALIBRATION_MATRIX_EQUIVALENCE_MEASURED"
else:
    verdict = "SCAN_CALIBRATION_MATRIX_EQUIVALENCE_BOUNDED_ONLY"

payload = {
    "schema": 1,
    "verdict": verdict,
    "code_sha": code_sha,
    "model": {"name": "TURNOVER", "sha256": model_sha, "geometry": "8cf",
              "search_params": "Q00"},
    "protocol": {
        "unblocked_by": "home-1001 SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR",
        "games_per_depth_cell": n_depth,
        "games_per_movetime_cell": n_time,
        "min_fraction_of_target": min_fraction,
        "scan_book": "off", "scan_bb_size": 0, "egdb": False,
        "jass_book": "built-in",
    },
    "cells": cells,
    "rows": rows,
    "unusable_cells": unusable,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "scan-calibration-matrix.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / f"VERDICT__{verdict}").write_text(verdict + "\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

print("  cellule                     n      W-N-D          score    Elo   nulles  etat")
for name, c in sorted(cells.items()):
    if c["usable"]:
        state = "ok"
    elif c["timed_out"]:
        state = "TIMEOUT"
    elif c["return_code"]:
        state = f"ECHEC rc={c['return_code']}"
    else:
        state = f"n<{int(min_fraction * c['games_target'])}"
    print(f"  {name:26s} {c['games_scored']:>4}  "
          f"{c['wins']:>4}-{c['draws']:>4}-{c['losses']:>4}  "
          f"{str(c['score_rate']):>6}  {str(c['elo']):>6}  "
          f"{str(c['draw_share']):>6}  {state}")
print()
for row, r in sorted(rows.items()):
    print(f"  [{row}] {r['label']}")
    if r["equivalence"] is not None:
        print(f"       equivalence : Scan {r['equivalence']} {r['unit']}")
    elif r["equivalence_status"] == "below_weakest_scan_tested":
        weakest = r["points"][0]["scan"] if r["points"] else "?"
        print(f"       equivalence : SOUS Scan {weakest} {r['unit']} "
              f"(non atteinte dans la plage testee)")
    else:
        print(f"       equivalence : {r['equivalence_status']}")
    ea = r["equal_arms"]
    if ea:
        print(f"       armes egales: {ea['wins']}-{ea['draws']}-{ea['losses']} "
              f"= {ea['score_rate']:.3f} IC95 {ea['score_ci95']} "
              f"({ea['elo']:+.1f} Elo)")
    else:
        print("       armes egales: cellule inutilisable")
print()
print(f"  verdict={verdict}")
PY
cp "$W"/cell-*.timing "$ART/cells/" 2>/dev/null || true
VERDICT=$(ls "$ART" | sed -n 's/^VERDICT__//p' | head -1)
stage complete
say "$VERDICT promotion=false automatic_next_job=null"
