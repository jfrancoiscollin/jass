#!/usr/bin/env bash
# L3 — PROFIL de cadence (profondeur / nœuds / NPS), pas une matrice de calibration d'un modèle contre Scan, sur le harnais réparé.
#
# Le modèle est paramétré depuis le 3 août (`MODEL_LABEL`/`MODEL_FILE`/
# `MODEL_SHA256`) : le template ne savait lire que TURNOVER, et comparer un
# nouveau champion à la matrice de juillet aurait remis le défenseur d'un
# instrument dans le passé pendant que l'attaquant suit `develop` — la faute
# exacte qui a fabriqué le faux repère de conversion (cf.
# L3_EXACT_PROMOTION_20260801.md). Un contrôle contemporain se joue donc en
# relançant CE template sur l'ancien modèle, le même jour et le même build.
#
# ⚠️ Les rangées A et B sont à PROFONDEUR FIXE, donc insensibles au correctif
# `16f8c151` (`has_deadline` n'est armé que si `movetime_ms > 0`) : elles se
# comparent à juillet. La rangée C est au MOVETIME et ne s'y compare PAS.
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
MODEL_LABEL="${MODEL_LABEL:-TURNOVER}"
MODEL_FILE="${MODEL_FILE:-turnover1to1.pjtw.gz}"
MODEL_SHA256="${MODEL_SHA256:-b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16}"
# Grilles Scan par rangée. Défauts = la matrice de home-1002, à l'identique,
# pour que toute cellule ajoutée n'en déplace aucune. Les cellules à bras
# égaux (A d9/d9, B d11/d11, C mt0.2/mt0.2) DOIVENT rester dans la grille.
ROW_A_SCAN_DEPTHS="${ROW_A_SCAN_DEPTHS:-3 5 6 7 9}"
ROW_B_SCAN_DEPTHS="${ROW_B_SCAN_DEPTHS:-5 7 9 11}"
ROW_C_SCAN_MOVETIMES="${ROW_C_SCAN_MOVETIMES:-0.02 0.05 0.1 0.2}"
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
  --file "artefacts/$MODEL_FILE=model.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-champion-train.json" \
  > "$W/fetch-model.log" 2>&1
python3 - "$ART/verified-champion-train.json" "$EXPECTED_CHAMPION_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
gunzip -c "$IN/model.pjtw.gz" > "$W/model.pjtw"
[ "$(sha256sum "$W/model.pjtw" | awk '{print $1}')" = "$MODEL_SHA256" ] ||
  die "$MODEL_LABEL model hash drift"
say "  champion ✓ : $MODEL_LABEL $MODEL_SHA256"

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
"$J8" --eval-position "$W/model.pjtw" 'W:W31,32,33:B18,19,20' >/dev/null 2>&1 ||
  die "8cf engine cannot load $MODEL_LABEL"
say "  moteur ✓ : 8cf, correctif racine-nulle présent"

stage profile
# Aucune partie n'est jouee : on pose les MEMES positions aux deux moteurs a une
# grille de cadences et on lit ce que chacun rend. Le temps est mesure autour de
# l'appel, identiquement des deux cotes — Scan rapporte `time=`, Jass non, donc
# la seule mesure comparable est la notre.
NPOS="${NPOS:-200}"
JASS_MOVETIMES="${JASS_MOVETIMES:-0.05,0.1,0.2,0.5,1.0}"
SCAN_MOVETIMES="${SCAN_MOVETIMES:-0.01,0.05,0.1,0.2}"
PREFLIGHT_PREFIX="${PREFLIGHT_PREFIX:?}"; PREFLIGHT_FILE="${PREFLIGHT_FILE:?}"
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file "artefacts/$PREFLIGHT_FILE=open-profile.fen" \
  --out-dir "$IN" --report "$ART/verified-openings.json" \
  --expected-state completed > "$W/fetch-openings.log" 2>&1 ||
  die "fetch des ouvertures en échec"
NOPEN=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' "$IN/open-profile.fen")
[ "$NOPEN" -gt 0 ] || die "aucune ouverture"
say "  $NOPEN ouvertures disponibles, $NPOS utilisées"
say "  cadences Jass : $JASS_MOVETIMES"
say "  cadences Scan : $SCAN_MOVETIMES"

timeout 5400 python3 jobs/tools/movetime_profile.py \
  --jass "$J8" --scan "$SCAN_BIN" --pattern "$W/model.pjtw" \
  --openings-file "$IN/open-profile.fen" --positions "$NPOS" \
  --jass-movetimes "$JASS_MOVETIMES" --scan-movetimes "$SCAN_MOVETIMES" \
  --search-params "$Q00" \
  --out "$ART/movetime-profile.json" \
  --transcript-out "$ART/first-probe-transcripts.json" \
  > "$W/profile.log" 2>&1 || {
    say "  ⚠️ profil en échec — 40 dernières lignes :"
    tail -n 40 "$W/profile.log" | tee -a "$RES"
    die "movetime_profile.py rc!=0"; }
grep -q MOVETIME_PROFILE_OK "$W/profile.log" || die "profil sans marqueur de fin"

stage readout
python3 - "$ART/movetime-profile.json" "$ART" <<'PYRD' | tee -a "$RES"
import json, pathlib, sys
d = json.load(open(sys.argv[1])); art = pathlib.Path(sys.argv[2])
cells = d["cells"]
print(f"  positions={d['positions']}")
rows = []
for name in sorted(cells, key=lambda k: (k.split('-')[0], float(k.split('mt')[1]))):
    eng, mt = name.split("-mt")
    c = cells[name]; rows.append((eng, float(mt), c))
    print(f"  {eng:5s} mt={mt:<5} depth_mean={c['depth_mean']:<7} "
          f"median={c['depth_median']:<5} nodes_mean={c['nodes_mean']:<12} "
          f"nps={c['nps']:<12} wall={c['wall_s_mean']}")
j = {mt: c for e, mt, c in rows if e == "jass"}
s = {mt: c for e, mt, c in rows if e == "scan"}
if j and s:
    jn = max(c["nps"] for c in j.values()); sn = max(c["nps"] for c in s.values())
    print(f"  NPS max  jass={jn}  scan={sn}  rapport scan/jass={sn / jn:.1f}x"
          if jn else "  NPS jass nul")
    if 0.2 in j and 0.01 in s:
        a, b = j[0.2], s[0.01]
        print(f"  CELLULE MOTIVANTE  jass mt0.2 depth={a['depth_mean']} "
              f"nodes={a['nodes_mean']} | scan mt0.01 depth={b['depth_mean']} "
              f"nodes={b['nodes_mean']}  ->  ecart de profondeur "
              f"{b['depth_mean'] - a['depth_mean']:+.2f} plies")
(art / "JASS_CONTROL_SUMMARY.json").write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")
PYRD
say "MOVETIME_PROFILE_READY promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__MOVETIME_PROFILE_READY"
stage complete
