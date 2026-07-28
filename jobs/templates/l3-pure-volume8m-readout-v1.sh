#!/usr/bin/env bash
# L3-PURE — VOL8M contre TURNOVER : le volume achète-t-il de la FORCE ?
#
# `home-1004` a montré que le volume achète de la couverture (9,8 % -> 13,5 %
# de buckets) et surtout de la DENSITÉ (4,3 -> 41,7 observations par paramètre
# libre). `home-1006` a fait converger le fit. Rien de tout cela n'est un
# résultat de force : ce projet a trois confirmations que la loss holdout ne
# prédit pas la force (rank statique −847, PC Blues −135, WS-ON −354), et
# REPLAY75 avait la MEILLEURE loss des quatre doses tout en étant le plus
# faible des quatre.
#
# Ce job joue les parties. C'est le seul qui tranche.
#
# ⚠️ Les deux loglosses publiées ne sont PAS comparables et ne doivent pas être
# citées l'une contre l'autre : le holdout de TURNOVER vient de son corpus 2 M,
# celui de VOL8M du corpus 12 M — deux distributions différentes. Le certificat
# de ce job le redit pour que le raccourci ne se propage pas.
#
# Estimateur à vues additionnées (cf L3_VIEW_AGREEMENT_AND_POWER_20260726) :
# q00 = profondeur fixe 9 (déterministe), native = movetime 0,1. Les deux vues
# mesurent la même chose (r=+0,885, p≈0,88) et les sommer double la puissance.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"
: "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force"
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
        for f in "$ART"/force/*.json; do
          [ -e "$f" ] || continue
          printf 'done_%s\n' "$(basename "$f" .json)"
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
  rm -rf "$W/build8" "$IN" "$GEOM" "$W"/gate-* 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=1500
GAMES_PER_VIEW=$((NOPEN * 2))
NSH_GATE=12
PAR_GATE=12
FORCE_DEPTH=9
MOVETIME=0.1
CACHE_MB=128
TURNOVER_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
VOL8M_MODEL_SHA="7a7c552df513e2725ef328815ab4c4c8e68166a370356e6d113117bd164930f9"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 8000 ] ||
  die "need 8 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
# Les readouts antérieurs asseyaient leur comparabilité sur un `git diff` contre
# la SHA du champion réparé. Ce garde-fou ne peut plus tenir : le moteur a
# changé depuis (correctif racine-nulle 9c1d1e8e, --explore-topk, --explore-
# margin). Les deux bras partagent le MÊME binaire, donc la comparaison interne
# reste propre ; c'est la comparabilité avec les portes d'AVANT le correctif qui
# est rompue, et il vaut mieux l'assumer que de la maquiller.
grep -q "root_is_drawn" src/search.cpp ||
  die "engine predates the drawn-root fix"
monitor

stage fetch-and-authenticate-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preflight.json \
  --file artefacts/vol8m-eval-openings.fen=open-eval.fen \
  --file artefacts/vol8m-eval-openings.json=openings-manifest.json \
  --out-dir "$IN" --report "$ART/verified-preflight.json" \
  > "$W/fetch-preflight.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TRAIN_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training.json \
  --file artefacts/vol8m.pjtw.gz=VOL8M.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-training.json" \
  > "$W/fetch-training.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" \
  > "$W/fetch-turnover.log" 2>&1
for spec in "verified-preflight.json:$EXPECTED_PREFLIGHT_JOB" \
            "verified-training.json:$EXPECTED_TRAIN_JOB" \
            "verified-turnover.json:$EXPECTED_TURNOVER_TRAIN_JOB"; do
  python3 - "$ART/${spec%%:*}" "${spec#*:}" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
done
python3 - "$IN/training.json" "$IN/preflight.json" <<'PY'
import json
import sys
train, pre = (json.load(open(p)) for p in sys.argv[1:3])
if train.get("verdict") != "L3_PURE_VOLUME8M_FIT_CONVERGED":
    raise SystemExit("training verdict mismatch")
if train.get("training", {}).get("converged") is not True:
    raise SystemExit("the fit did not converge — nothing to read out")
if pre.get("verdict") != "L3_PURE_VOLUME8M_PREFLIGHT_READY":
    raise SystemExit("preflight verdict mismatch")
PY
gunzip -c "$IN/VOL8M.pjtw.gz"    > "$W/VOL8M.pjtw"
gunzip -c "$IN/TURNOVER.pjtw.gz" > "$W/TURNOVER.pjtw"
[ "$(sha256sum "$W/VOL8M.pjtw"    | awk '{print $1}')" = "$VOL8M_MODEL_SHA" ] ||
  die "VOL8M model hash drift"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_MODEL_SHA" ] ||
  die "TURNOVER model hash drift"
cp "$IN/open-eval.fen" "$W/open-eval.fen"
cp "$IN/openings-manifest.json" "$ART/eval-openings-manifest.json"
NPOS=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' \
  "$W/open-eval.fen")
[ "$NPOS" -eq "$NOPEN" ] || die "eval pool count drift: $NPOS != $NOPEN"
say "  entrées ✓ : VOL8M + TURNOVER, pool neuf de $NPOS ouvertures"

stage build-8cf-engine
# Mêmes FLAGS et même EGDB que toutes les portes précédentes (0978, 1007) : un
# gate sans base de finales ne joue pas les mêmes fins de partie, et on perdrait
# la comparabilité avec la seule chose à laquelle ce readout se compare.
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
[ "$("$J8" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture witness failed"
say "  moteur ✓ : 8cf, un seul binaire pour les deux bras"

run_gate(){
  local view="$1" arm="$2" opponent="$3"
  local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/$arm.pjtw" --pattern-b "$W/$opponent.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/force-$view-$arm-vs-$opponent.json" \
    > "$W/force-$view.log" 2>&1
}

stage play-both-views
# Une cellule qui tombe ne doit PAS tuer le job : le bloc de lecture sait déjà
# rendre INCONCLUSIVE sur vue manquante ou n insuffisant, et ce verdict-là a
# plus de valeur qu'un ABORT muet. On note l'échec et on continue.
for view in q00 native; do
  stage "view-$view-${GAMES_PER_VIEW}-games"
  if run_gate "$view" VOL8M TURNOVER; then
    say "  vue $view jouée"
  else
    say "  vue $view ÉCHOUÉE (rc=$?) — readout inconclusif"
  fi
done

stage publish-readout
python3 - "$ART" "$EXPECTED_CODE_SHA" "$GAMES_PER_VIEW" "$IN/preflight.json" \
  "$IN/training.json" <<'PY'
import json
import math
import pathlib
import sys

art = pathlib.Path(sys.argv[1])
code_sha = sys.argv[2]
per_view = int(sys.argv[3])
pre, train = (json.load(open(p)) for p in sys.argv[4:6])

views = {}
for view in ("q00", "native"):
    p = art / "force" / f"force-{view}-VOL8M-vs-TURNOVER.json"
    if not p.exists():
        views[view] = None
        continue
    views[view] = json.load(open(p))

missing = [v for v, d in views.items() if d is None]
short = [v for v, d in views.items()
         if d is not None and d.get("n", 0) < int(0.9 * per_view)]

# Vues additionnées : on somme les compteurs BRUTS, on ne moyenne pas les taux.
# Moyenner deux taux de n différents pondérerait mal, et le n effectif servant
# à l'intervalle serait faux.
wins = sum(d["wins_a"] for d in views.values() if d)
draws = sum(d["draws"] for d in views.values() if d)
losses = sum(d["wins_b"] for d in views.values() if d)
n = wins + draws + losses
if n:
    rate = (wins + 0.5 * draws) / n
    var = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(var / n)
    lo, hi = max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)

    def elo(r):
        return -400 * math.log10(1 / r - 1) if 0 < r < 1 else None
else:
    rate = se = lo = hi = None

if missing or short:
    verdict = "L3_PURE_VOLUME8M_READOUT_INCONCLUSIVE_CELL_FAILED"
elif lo > 0.5:
    verdict = "VOLUME8M_BEATS_TURNOVER_HUMAN_REVIEW"
elif hi < 0.5:
    verdict = "VOLUME8M_BELOW_TURNOVER_VOLUME_AXIS_CLOSED"
else:
    verdict = "VOLUME8M_FLAT_VOLUME_AXIS_NO_ESTABLISHED_GAIN"

cov = pre["coverage"]
payload = {
    "schema": 1,
    "verdict": verdict,
    "code_sha": code_sha,
    "matchup": "VOL8M vs TURNOVER",
    "views_summed": {
        "wins_vol8m": wins, "draws": draws, "wins_turnover": losses,
        "n": n,
        "rate": round(rate, 6) if rate else None,
        "ci95": [round(lo, 6), round(hi, 6)] if rate else None,
        "elo": round(elo(rate), 2) if rate and elo(rate) is not None else None,
        "elo_ci95": ([round(elo(lo), 1), round(elo(hi), 1)]
                     if rate and elo(lo) is not None and elo(hi) is not None
                     else None),
    },
    "per_view": {v: d for v, d in views.items()},
    "mechanism_from_preflight": {
        "visited_pct": cov["visited_pct"],
        "observations_per_free_parameter": cov["observations_per_free_parameter"],
        "turnover_reference": cov["turnover_reference"],
    },
    "holdout_losses_are_not_comparable": (
        "TURNOVER's holdout comes from its own 2M corpus, VOL8M's from the 12M "
        "corpus — different distributions. The two loglosses must not be cited "
        "against each other, and loss does not predict strength in this project "
        "regardless."
    ),
    "engine_note": (
        "Both arms share one binary, so the comparison is internally clean, but "
        "the engine changed since the pre-9c1d1e8e gates (drawn-root fix) and "
        "this readout is not byte-comparable with them."
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "vol8m-readout.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / f"VERDICT__{verdict}").write_text(verdict + "\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

for v, d in sorted(views.items()):
    if d:
        print(f"  {v:7s} n={d['n']:>5} {d['wins_a']}-{d['draws']}-{d['wins_b']} "
              f"rate={d['rate']} elo={d['elo']}")
    else:
        print(f"  {v:7s} MANQUANTE")
if n:
    print(f"\n  vues additionnées : n={n} {wins}-{draws}-{losses} "
          f"rate={rate:.4f} IC95 [{lo:.4f} ; {hi:.4f}]")
    e = elo(rate)
    if e is not None:
        print(f"  Elo {e:+.2f} IC95 [{elo(lo):+.1f} ; {elo(hi):+.1f}]")
print(f"\n  verdict={verdict}")
PY
stage complete
VERDICT=$(ls "$ART" | sed -n 's/^VERDICT__//p' | head -1)
say "$VERDICT promotion=false automatic_next_job=null"
