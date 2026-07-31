#!/usr/bin/env bash
# L3-PURE — read-only diagnostic of the reverse-seed 2M/4M force inversion.
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"
: "${STAGE2_PREFIX:?}"
: "${EXPECTED_STAGE2_JOB:?}"
: "${EXPECTED_STAGE2_ATTEMPT:?}"
: "${EXPECTED_STAGE2_CODE_SHA:?}"
: "${READOUT2_PREFIX:?}"
: "${EXPECTED_READOUT2_JOB:?}"
: "${EXPECTED_READOUT2_ATTEMPT:?}"
: "${EXPECTED_READOUT2_CODE_SHA:?}"
: "${STAGE4_PREFIX:?}"
: "${EXPECTED_STAGE4_JOB:?}"
: "${EXPECTED_STAGE4_ATTEMPT:?}"
: "${EXPECTED_STAGE4_CODE_SHA:?}"
: "${READOUT4_PREFIX:?}"
: "${EXPECTED_READOUT4_JOB:?}"
: "${EXPECTED_READOUT4_ATTEMPT:?}"
: "${EXPECTED_READOUT4_CODE_SHA:?}"
: "${PARENT_PREFIX:?}"
: "${EXPECTED_PARENT_JOB:?}"
: "${EXPECTED_PARENT_ATTEMPT:?}"
: "${EXPECTED_PARENT_CODE_SHA:?}"
: "${PARENT_ARTEFACT:?}"
: "${PARENT_MODEL_SHA:?}"
: "${STAGE2_CONTROL_SHA:?}"
: "${STAGE2_TREATMENT_SHA:?}"
: "${STAGE4_CONTROL_SHA:?}"
: "${STAGE4_TREATMENT_SHA:?}"
: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || exit 2
[ "$(git -C "$JASS_CODE_DIR" rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || exit 2
[ -z "$(git -C "$JASS_CODE_DIR" branch --show-current)" ] || exit 2

W="$JASS_RESULT_DIR/work"
IN="$W/input"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$IN" "$ART/atlases" "$ART/prefix-manifests"

progress(){ printf 'phase=%s\n' "$1" > "$ART/PROGRESS.txt"; }
die(){ echo "ABORT: $*" >&2; exit 3; }

finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ "$rc" -eq 0 ] || touch "$ART/FAILED__RC_${rc}"
  rm -rf "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

progress preflight
free_mib=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${free_mib:-0}" -ge 8192 ] || die "disk below 8192 MiB"

fetch_stage(){
  local prefix="$1" label="$2"
  python3 "$JASS_CODE_DIR/jobs/tools/fetch_result_files.py" \
    --prefix "$prefix" --expected-state completed \
    --file artefacts/JASS_CONTROL_SUMMARY.json="$label-summary.json" \
    --file artefacts/control.jnnw.gz="$label-control.jnnw.gz" \
    --file artefacts/control.jsm.gz="$label-control.jsm.gz" \
    --file artefacts/control.pjtw.gz="$label-control.pjtw.gz" \
    --file artefacts/treatment.jnnw.gz="$label-treatment.jnnw.gz" \
    --file artefacts/treatment.jsm.gz="$label-treatment.jsm.gz" \
    --file artefacts/treatment.pjtw.gz="$label-treatment.pjtw.gz" \
    --out-dir "$IN" --report "$ART/verified-$label.json" \
    > "$W/fetch-$label.log" 2>&1
}

progress fetch-authenticated-inputs
fetch_stage "$STAGE2_PREFIX" stage2
fetch_stage "$STAGE4_PREFIX" stage4
python3 "$JASS_CODE_DIR/jobs/tools/fetch_result_files.py" \
  --prefix "$READOUT2_PREFIX" --expected-state completed \
  --file artefacts/JASS_CONTROL_SUMMARY.json=readout2.json \
  --out-dir "$IN" --report "$ART/verified-readout2.json" \
  > "$W/fetch-readout2.log" 2>&1
python3 "$JASS_CODE_DIR/jobs/tools/fetch_result_files.py" \
  --prefix "$READOUT4_PREFIX" --expected-state completed \
  --file artefacts/JASS_CONTROL_SUMMARY.json=readout4.json \
  --out-dir "$IN" --report "$ART/verified-readout4.json" \
  > "$W/fetch-readout4.log" 2>&1
python3 "$JASS_CODE_DIR/jobs/tools/fetch_result_files.py" \
  --prefix "$PARENT_PREFIX" --expected-state completed \
  --file "artefacts/$PARENT_ARTEFACT=parent.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  > "$W/fetch-parent.log" 2>&1

python3 - "$ART" <<'PY'
import json, os, pathlib
art = pathlib.Path(__import__('sys').argv[1])
for label in ('stage2','readout2','stage4','readout4','parent'):
    report=json.loads((art/f'verified-{label}.json').read_text())
    for key, expected in (
        ('job_id',os.environ[f'EXPECTED_{label.upper()}_JOB']),
        ('attempt_id',os.environ[f'EXPECTED_{label.upper()}_ATTEMPT']),
        ('code_sha',os.environ[f'EXPECTED_{label.upper()}_CODE_SHA']),
        ('result_state','completed'),('exit_code',0)):
        if report.get(key) != expected:
            raise SystemExit(f'{label}: {key}={report.get(key)!r} expected={expected!r}')
PY

progress decompress-and-hash
for stage in stage2 stage4; do
  for arm in control treatment; do
    gunzip -c "$IN/$stage-$arm.jnnw.gz" > "$W/$stage-$arm.jnnw"
    gunzip -c "$IN/$stage-$arm.jsm.gz" > "$W/$stage-$arm.jsm"
    gunzip -c "$IN/$stage-$arm.pjtw.gz" > "$W/$stage-$arm.pjtw"
  done
done
gunzip -c "$IN/parent.pjtw.gz" > "$W/parent.pjtw"
for check in \
  "parent.pjtw:$PARENT_MODEL_SHA" \
  "stage2-control.pjtw:$STAGE2_CONTROL_SHA" \
  "stage2-treatment.pjtw:$STAGE2_TREATMENT_SHA" \
  "stage4-control.pjtw:$STAGE4_CONTROL_SHA" \
  "stage4-treatment.pjtw:$STAGE4_TREATMENT_SHA"; do
  file=${check%%:*}; expected=${check#*:}
  actual=$(sha256sum "$W/$file" | awk '{print $1}')
  [ "$actual" = "$expected" ] || die "$file SHA drift"
done

progress tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check \
  --only-binary=:all: "numpy==${NUMPY_VERSION:-2.5.1}" \
  > "$W/pip.log" 2>&1
"$W/venv/bin/python" -m py_compile \
  jobs/tools/l3_aligned_prefix.py \
  jobs/tools/l3_reverse_seed_scale_diagnostic.py \
  tools/blind_spot_atlas.py
"$W/venv/bin/python" -m unittest \
  jobs.tests.test_l3_aligned_prefix \
  jobs.tests.test_l3_reverse_seed_scale_diagnostic \
  jobs.tests.test_blind_spot_atlas \
  > "$W/tests.log" 2>&1

run_atlas(){
  local stage="$1" arm="$2" records="$3" total="$4"
  local label="${stage}_${arm}_${records}"
  local data="$W/$stage-$arm.jnnw" meta="$W/$stage-$arm.jsm"
  if [ "$records" -ne "$total" ]; then
    data="$W/$label.jnnw"; meta="$W/$label.jsm"
    "$W/venv/bin/python" jobs/tools/l3_aligned_prefix.py \
      --data "$W/$stage-$arm.jnnw" --meta "$W/$stage-$arm.jsm" \
      --out-data "$data" --out-meta "$meta" --records "$records" \
      --report "$ART/prefix-manifests/$label.json" \
      > "$W/prefix-$label.log" 2>&1
  fi
  progress "atlas-$label"
  "$W/venv/bin/python" tools/blind_spot_atlas.py \
    --data "$data" --meta "$meta" \
    --json-out "$ART/atlases/$label.json" \
    --csv-out "$ART/atlases/$label.csv" \
    --code-sha "$EXPECTED_CODE_SHA" --probe-size 256 --probe-seed 20260731 \
    > "$W/atlas-$label.log" 2>&1
  if [ "$records" -ne "$total" ]; then rm -f "$data" "$meta"; fi
}

for arm in control treatment; do
  for records in 1000000 2000000; do run_atlas stage2 "$arm" "$records" 2000000; done
  for records in 1000000 2000000 3000000 4000000; do run_atlas stage4 "$arm" "$records" 4000000; done
done

progress compare
atlas_args=()
for stage in stage2 stage4; do
  for arm in control treatment; do
    if [ "$stage" = stage2 ]; then counts="1000000 2000000"; else counts="1000000 2000000 3000000 4000000"; fi
    for records in $counts; do
      label="${stage}_${arm}_${records}"
      atlas_args+=(--atlas "$label=$ART/atlases/$label.json")
    done
  done
done
"$W/venv/bin/python" jobs/tools/l3_reverse_seed_scale_diagnostic.py \
  "${atlas_args[@]}" \
  --model "parent=$W/parent.pjtw" \
  --model "stage2_control=$W/stage2-control.pjtw" \
  --model "stage2_treatment=$W/stage2-treatment.pjtw" \
  --model "stage4_control=$W/stage4-control.pjtw" \
  --model "stage4_treatment=$W/stage4-treatment.pjtw" \
  --stage2-summary "$IN/stage2-summary.json" \
  --stage4-summary "$IN/stage4-summary.json" \
  --readout2 "$IN/readout2.json" --readout4 "$IN/readout4.json" \
  --code-sha "$EXPECTED_CODE_SHA" --out "$ART/reverse-seed-scale-diagnostic.json" \
  > "$W/compare.log" 2>&1

cp "$ART/reverse-seed-scale-diagnostic.json" "$ART/JASS_CONTROL_SUMMARY.json"
"$W/venv/bin/python" - "$ART/JASS_CONTROL_SUMMARY.json" "$ART/RESULTS.txt" <<'PY'
import json, pathlib, sys
p=json.loads(pathlib.Path(sys.argv[1]).read_text())
f2=p['authenticated_force']['stage2']; f4=p['authenticated_force']['stage4']
g=p['model_geometry']['treatment_minus_control']
lines=[
  f"verdict={p['verdict']}",
  f"stage2_summed rate={f2['rate_treatment']:.6f} elo={f2['elo']:.2f} ci95={f2['ci95']}",
  f"stage4_summed rate={f4['rate_treatment']:.6f} elo={f4['elo']:.2f} ci95={f4['ci95']}",
  f"model_delta_cosine_stage2_vs_stage4={g['cosine_stage2_vs_stage4']}",
  "record_order_prefixes_are_not_learning_curves=true",
  "causal_attribution_authorized=false",
  "scientific_result=false",
  "promotion_authorized=false",
  "automatic_next_job=null",
]
pathlib.Path(sys.argv[2]).write_text('\n'.join(lines)+'\n',encoding='utf-8')
PY
touch "$ART/VERDICT__L3_PURE_REVERSE_SEED_SCALE_DIAGNOSTIC_COMPLETE"
touch "$ART/DIAGNOSTIC_ONLY__TRUE" "$ART/SCIENTIFIC_RESULT__FALSE"
touch "$ART/PROMOTION_AUTHORIZED__FALSE" "$ART/AUTOMATIC_NEXT_JOB__NULL"
progress complete
