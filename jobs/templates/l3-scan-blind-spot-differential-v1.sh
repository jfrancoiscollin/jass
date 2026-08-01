#!/usr/bin/env bash
# L3 — readout descriptif EXACT/8cf moins Gen2/32cf des atlas jugés par Scan.
#
# Aucun jeu, aucun fit, aucune promotion. Le tool refuse le readout si le SHA
# moteur, Scan, les 120 extras, les profondeurs, le budget, les shards ou les
# seeds diffèrent entre les deux passes.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXACT_ATLAS_PREFIX:?}"; : "${EXPECTED_EXACT_ATLAS_JOB:?}"
: "${GEN2_ATLAS_PREFIX:?}"; : "${EXPECTED_GEN2_ATLAS_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${READOUT_APPROVED:-0}" = 1 ] || die "readout authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

fetch_arm(){
  local label="$1" prefix="$2" expected_job="$3"
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
    --file artefacts/atlas.json="$label-atlas.json" \
    --file artefacts/protocol.json="$label-protocol.json" \
    --out-dir "$IN" --report "$ART/verified-$label.json" \
    --expected-state completed > "$W/fetch-$label.log" 2>&1 ||
    die "fetch atlas $label en échec"
  python3 - "$ART/verified-$label.json" "$expected_job" "$label" <<'PY'
import json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[3]} atlas identity/state mismatch")
PY
}

say "phase=fetch-two-atlases"
fetch_arm exact "$EXACT_ATLAS_PREFIX" "$EXPECTED_EXACT_ATLAS_JOB"
fetch_arm gen2 "$GEN2_ATLAS_PREFIX" "$EXPECTED_GEN2_ATLAS_JOB"

say "phase=smoke-readout"
python3 -m unittest jobs.tests.test_scan_blind_spot_differential \
  > "$W/selftest.log" 2>&1 || die "tests du différentiel en échec"

say "phase=differential"
python3 jobs/tools/scan_blind_spot_differential.py \
  --exact-atlas "$IN/exact-atlas.json" \
  --exact-protocol "$IN/exact-protocol.json" \
  --gen2-atlas "$IN/gen2-atlas.json" \
  --gen2-protocol "$IN/gen2-protocol.json" \
  --out "$ART/differential.json" > "$W/differential.log" 2>&1 ||
  die "différentiel refusé — voir differential.log"

python3 - "$ART/differential.json" <<'PY' | tee -a "$RES"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
e, g = d["arms"]["exact"]["global"], d["arms"]["gen2"]["global"]
x = d["global_differential_exact_minus_gen2"]
def fmt(value, digits=6, signed=False):
    if value is None:
        return "n/a"
    sign = "+" if signed else ""
    return format(value, f"{sign}.{digits}f")
print(f"  EXACT positions={e['positions']} coût/position={fmt(e['ordinary_cost_per_position'])} "
      f"désaccord={fmt(e['disagreement_rate'], 4)}")
print(f"  GEN2  positions={g['positions']} coût/position={fmt(g['ordinary_cost_per_position'])} "
      f"désaccord={fmt(g['disagreement_rate'], 4)}")
print(f"  Δ EXACT−GEN2 coût/position={fmt(x['ordinary_cost_per_position'], signed=True)} "
      f"désaccord={fmt(x['disagreement_rate'], signed=True)}")
print(f"  buckets classés dans les deux bras={d['common_ranked_bucket_count']}")
for axis in ("phase", "kings", "material", "tactical"):
    print(f"  AXE {axis} (plus grands |Δ part de masse|) :")
    for row in d["axis_differentials"][axis][:5]:
        print(f"    {fmt(row['delta_cost_mass_share_exact_minus_gen2'], signed=True)} masse  "
              f"{fmt(row['delta_cost_per_position_exact_minus_gen2'], signed=True)} coût/pos  "
              f"{row['value']}")
print(f"  buckets conversion classés dans les deux bras="
      f"{d['common_ranked_conversion_bucket_count']}")
for row in d["conversion_bucket_differentials"][:5]:
    print(f"    {fmt(row['delta_miss_rate_over_positions_exact_minus_gen2'], signed=True)} "
          f"Δ taux conversion ratée  {row['bucket']}")
print("  PORTÉE : géométrie/profil OUI ; features NON (tenues constantes) ; "
      "classe linéaire vs non-linéaire NON (deux bras linéaires).")
print("  LIMITATION : trajectoires et poids propres à chaque modèle ; différentiel "
      "descriptif, pas ablation causale des poids ni test iid.")
PY

cp "$ART/differential.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=L3_SCAN_BLIND_SPOT_DIFFERENTIAL_MEASURED
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
