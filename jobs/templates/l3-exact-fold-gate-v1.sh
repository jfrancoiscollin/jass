#!/usr/bin/env bash
# L3 — porte appariée EXACT contre CONTROL, les deux modèles de `cpx62-1115`.
#
# Les deux bras sortent du MÊME corpus, du MÊME parent, des MÊMES hyperparamètres
# et de la MÊME machine. Le seul écart est le fold : `--color-fold` (contrainte
# approximative, celle de TURNOVER) contre `--exact-fold` (`rot180∘cs`, la seule
# symétrie que les règles garantissent).
#
# Deux vues, comme les portes précédentes : `q00` à profondeur 9 fixe et `native`
# à movetime 0,1. Les compteurs BRUTS sont sommés — moyenner deux taux de n
# différents pondérerait mal et rendrait un intervalle faux.
#
# ⚠️ C'est la porte qui tranche, pas la perte en holdout. Ce projet a mesuré
# quatre fois que la perte ne prédit pas la force ; le holdout des deux bras est
# rapporté comme information, jamais comme verdict.
#
# Aucune promotion automatique. Un bras qui gagne devient un candidat à revue.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"; : "${REFIT_PREFIX:?}"
: "${EXPECTED_REFIT_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$ART/force"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

PREFLIGHT_PREFIX="${PREFLIGHT_PREFIX:-r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1}"
EXPECTED_PREFLIGHT_JOB="${EXPECTED_PREFLIGHT_JOB:-home-1004-l3-pure-volume8m-preflight-v2}"
NSH_GATE="${NSH_GATE:-12}"; PAR_GATE="${PAR_GATE:-12}"
FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'views_done=%s\n' "$(find "$ART/force" -name '*.json' 2>/dev/null | wc -l)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
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
  rm -rf "$W/build" "$IN" "$W"/gate-* 2>/dev/null || true
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
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo shards=$NSH_GATE"
monitor

stage fetch-models-and-openings
python3 jobs/tools/fetch_result_files.py --prefix "$REFIT_PREFIX" \
  --file artefacts/control.pjtw.gz=control.pjtw.gz \
  --file artefacts/exact.pjtw.gz=exact.pjtw.gz \
  --file artefacts/symmetry-report.json=symmetry.json \
  --out-dir "$IN" --report "$ART/verified-refit.json" \
  --expected-state completed > "$W/fetch-refit.log" 2>&1 || die "fetch des modèles en échec"
python3 - "$ART/verified-refit.json" "$EXPECTED_REFIT_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("refit source identity/state mismatch")
PY
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/vol8m-eval-openings.fen=open-eval.fen \
  --out-dir "$IN" --report "$ART/verified-openings.json" \
  --expected-state completed > "$W/fetch-openings.log" 2>&1 || die "fetch des ouvertures en échec"
gunzip -c "$IN/control.pjtw.gz" > "$W/CONTROL.pjtw"
gunzip -c "$IN/exact.pjtw.gz"   > "$W/EXACT.pjtw"
cp "$IN/open-eval.fen" "$W/open-eval.fen"
NOPEN=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' "$W/open-eval.fen")
[ "$NOPEN" -gt 0 ] || die "aucune ouverture"
GAMES_PER_VIEW=$((NOPEN * 2))
say "  modèles ✓, $NOPEN ouvertures → $GAMES_PER_VIEW parties/vue, 2 vues"
# Les deux bras DOIVENT différer sur la symétrie, sinon la porte compare deux
# fois la même chose et son verdict n'a aucun sens.
python3 - "$IN/symmetry.json" <<'PY' | tee -a "$RES"
import json, sys
d = json.load(open(sys.argv[1]))
e = d["exact"]["violation_rot180_cs_EXACT"]; c = d["control"]["violation_rot180_cs_EXACT"]
print(f"  symétrie : exact viole rot180∘cs à {100*e:.4f} %, control à {100*c:.2f} %")
if e > 1e-9 or c < 1e-3:
    raise SystemExit("les deux bras ne diffèrent pas comme attendu — porte sans objet")
PY

stage build
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
grep -q "warm_kings_endgame_bitbases" src/hub.cpp ||
  { restore_src; die "engine predates the movetime endgame bake"; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# EGDB si la box l'a, sinon on s'en passe. Les DEUX bras partagent le binaire,
# donc la comparaison interne tient dans les deux cas ; seule la comparabilité
# avec les portes antérieures dépend de sa présence, et on l'écrit dans le rapport.
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
if [ -n "$EGDIR" ]; then
  FLAGS="$FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl"
  export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
  say "  EGDB présent ($EGDIR) — comparable aux portes antérieures"
else
  say "  ⚠️ EGDB ABSENT — comparaison interne valide, Elo non comparable aux portes antérieures"
fi
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J8="$W/build/jass"; [ -x "$J8" ] || { restore_src; die "build sans binaire"; }
restore_src
printf 'hello\nquit\n' | timeout 60 "$J8" --pattern "$W/EXACT.pjtw" > "$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "le binaire ne charge pas le modèle exact"
say "  build ✓, modèles chargeables"

run_view(){
  local view="$1"; local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  timeout 10800 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/EXACT.pjtw" --pattern-b "$W/CONTROL.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 9000 --game-timeout 180 \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/$view-EXACT-vs-CONTROL.json" \
    > "$W/gate-$view.log" 2>&1
}

stage play-both-views
# Une vue qui tombe ne tue pas le job : le bloc de lecture rend INCONCLUANT sur
# vue manquante, et ce verdict vaut mieux qu'un abort muet.
for view in q00 native; do
  stage "view-$view"
  if run_view "$view"; then say "  vue $view jouée"; else say "  vue $view ÉCHOUÉE (rc=$?)"; fi
done

stage readout
python3 - "$ART" "$GAMES_PER_VIEW" "$EXPECTED_CODE_SHA" "$IN/symmetry.json" <<'PY' | tee -a "$RES"
import json, math, pathlib, sys
art = pathlib.Path(sys.argv[1]); per_view = int(sys.argv[2])
code_sha = sys.argv[3]; sym = json.load(open(sys.argv[4]))
views = {}
for v in ("q00", "native"):
    p = art / "force" / f"{v}-EXACT-vs-CONTROL.json"
    views[v] = json.load(open(p)) if p.exists() else None
missing = [v for v, d in views.items() if d is None]
short = [v for v, d in views.items() if d and d.get("n", 0) < int(0.9 * per_view)]
# Compteurs BRUTS sommés : moyenner deux taux de n différents pondérerait mal.
wins = sum(d["wins_a"] for d in views.values() if d)
draws = sum(d["draws"] for d in views.values() if d)
losses = sum(d["wins_b"] for d in views.values() if d)
n = wins + draws + losses
rate = se = lo = hi = None
if n:
    rate = (wins + 0.5 * draws) / n
    var = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(var / n)
    lo, hi = max(0.0, rate - 1.96 * se), min(1.0, rate + 1.96 * se)
def elo(r):
    return -400 * math.log10(1 / r - 1) if r and 0 < r < 1 else None
if missing or short or not n:
    verdict = "L3_EXACT_FOLD_GATE_INCONCLUSIVE"
elif lo > 0.5:
    verdict = "EXACT_FOLD_BEATS_CONTROL_HUMAN_REVIEW"
elif hi < 0.5:
    verdict = "EXACT_FOLD_BELOW_CONTROL"
else:
    verdict = "EXACT_FOLD_FLAT_NO_ESTABLISHED_GAIN"
payload = {
    "schema": 1, "verdict": verdict, "code_sha": code_sha,
    "matchup": "EXACT (rot180 o cs) vs CONTROL (colour-swap only)",
    "views_summed": {
        "wins_exact": wins, "draws": draws, "wins_control": losses, "n": n,
        "rate": round(rate, 6) if rate else None,
        "ci95": [round(lo, 6), round(hi, 6)] if rate else None,
        "elo": round(elo(rate), 2) if elo(rate) is not None else None,
        "elo_ci95": ([round(elo(lo), 1), round(elo(hi), 1)]
                     if elo(lo) is not None and elo(hi) is not None else None)},
    "per_view": {v: d for v, d in views.items()},
    "symmetry_of_the_two_arms": sym,
    "what_this_isolates": (
        "Both arms come from the same corpus, parent, hyperparameters and "
        "machine. The only difference is which symmetry the fit imposes: the "
        "approximate colour-swap that TURNOVER used, or rot180 o colour-swap, "
        "the one the rules of draughts guarantee."),
    "holdout_is_not_the_arbiter": (
        "This project has measured four times that holdout loss does not "
        "predict strength. The gate decides; the loglosses are context."),
    "diagnostic_only": True, "gate_authorized": True,
    "promotion_authorized": False, "automatic_next_job": None,
}
(art / "JASS_CONTROL_SUMMARY.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(f"  n={n}  exact {wins}W {draws}D {losses}L")
if rate:
    print(f"  taux={rate:.4f}  IC95=[{lo:.4f} ; {hi:.4f}]")
    print(f"  Elo={elo(rate):+.2f}  IC95=[{elo(lo):+.1f} ; {elo(hi):+.1f}]")
print(f"  VERDICT {verdict}")
PY
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
