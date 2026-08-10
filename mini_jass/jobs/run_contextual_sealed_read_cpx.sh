#!/usr/bin/env bash
# Single descriptive frozen_test read for the two frozen contextual C2 arms.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
job_id=${JASS_JOB_ID:?JASS_JOB_ID is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
implementation_sha=${CONTEXTUAL_SEALED_IMPLEMENTATION_SHA:?CONTEXTUAL_SEALED_IMPLEMENTATION_SHA is required}
c2_result=${CONTEXTUAL_C2_RESULT_PATH:?CONTEXTUAL_C2_RESULT_PATH is required}
c2_freeze=${CONTEXTUAL_C2_FREEZE_REPORT_PATH:?CONTEXTUAL_C2_FREEZE_REPORT_PATH is required}
checkpoint_dir=${CONTEXTUAL_C2_CHECKPOINT_DIR:?CONTEXTUAL_C2_CHECKPOINT_DIR is required}
host=$(hostname)

if [[ "$job_id" != cpx62-* || "$host" != cpx62 ]]; then
  echo "contextual sealed read requires cpx62 (job=$job_id host=$host)" >&2
  exit 2
fi
if [[ ! "$implementation_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "CONTEXTUAL_SEALED_IMPLEMENTATION_SHA must be a full Git SHA" >&2
  exit 3
fi
actual_sha=$(git -C "$repo" rev-parse HEAD)
if [[ "$actual_sha" != "$implementation_sha" ]]; then
  echo "sealed-read implementation mismatch: $actual_sha != $implementation_sha" >&2
  exit 4
fi
for source in "$c2_result" "$c2_freeze" "$checkpoint_dir"; do
  if [[ ! -e "$source" ]]; then
    echo "missing sealed-read input: $source" >&2
    exit 5
  fi
done

work="$result_root/mini-jass-contextual-sealed-read"
build="$work/build"
venv="$work/venv"
oracle="$repo/mini_jass/artefacts/oracle.contextual-sealed-$job_id.jsonl"
run_dir="$work/result"
compact="$work/scientific-summary.json"
mkdir -p "$work" "$run_dir" "$artefact_root"

phase_log="$work/phase_timings.txt"
: >"$phase_log"
phase_start=$(date +%s)
phase() {
  local now
  now=$(date +%s)
  echo "$1=$((now - phase_start))" >>"$phase_log"
  phase_start=$now
}

publish_failure_diagnostics() {
  local rc=$?
  local sealed_started=false
  trap - ERR
  set +e
  if [[ -f "$run_dir/SEALED_READ_STARTED.json" ]]; then
    sealed_started=true
    cp "$run_dir/SEALED_READ_STARTED.json" "$artefact_root/"
  fi
  cp "$phase_log" "$artefact_root/PHASE_TIMINGS.partial.txt"
  if [[ -f "$run_dir/sealed-arena-start-manifest.json" ]]; then
    cp "$run_dir/sealed-arena-start-manifest.json" "$artefact_root/"
  fi
  partial_count=$(find "$run_dir" -maxdepth 1 -name 'seed-*.json' -type f | wc -l)
  if [[ "$partial_count" -gt 0 ]]; then
    shopt -s nullglob
    partial_rows=("$run_dir"/seed-*.json)
    partial_names=("${partial_rows[@]##*/}")
    tar -C "$run_dir" -czf "$artefact_root/SEALED_READ_PARTIAL.tgz" \
      "${partial_names[@]}"
  fi
  printf '%s\n' "$implementation_sha" >"$artefact_root/IMPLEMENTATION_SHA.txt"
  cat >"$artefact_root/attempt-diagnostic.json" <<EOF
{
  "schema": "mini_jass.contextual_sealed_read_attempt_diagnostic.v1",
  "job_id": "$job_id",
  "implementation_sha": "$implementation_sha",
  "exit_code": $rc,
  "sealed_test_read_started": $sealed_started,
  "completed_seed_rows": $partial_count,
  "scientific_result_published": false,
  "retry_without_protocol_review_forbidden_if_read_started": true
}
EOF
  exit "$rc"
}
trap publish_failure_diagnostics ERR

cmake -S "$repo/mini_jass" -B "$build" \
  -DCMAKE_BUILD_TYPE=Release -DMINI_JASS_BUILD_TESTS=ON
cmake --build "$build" --parallel "$(nproc)"
ctest --test-dir "$build" --output-on-failure
phase build_and_ctest

python3 -m venv --system-site-packages "$venv"
python_bin="$venv/bin/python"
if ! "$python_bin" -c 'import torch' >/dev/null 2>&1; then
  "$python_bin" -m pip install --index-url https://download.pytorch.org/whl/cpu \
    'torch==2.13.0'
fi
if ! "$python_bin" -c 'import numpy, pytest, yaml' >/dev/null 2>&1; then
  "$python_bin" -m pip install 'numpy>=1.26,<3' 'PyYAML>=6,<7' 'pytest>=8,<10'
fi
phase venv_and_dependencies

export PYTHONPATH="$repo/mini_jass/python"
"$python_bin" -m pytest \
  "$repo/mini_jass/tests/python/test_context.py" \
  "$repo/mini_jass/tests/python/test_context_decision.py" \
  "$repo/mini_jass/tests/python/test_context_power.py" \
  "$repo/mini_jass/tests/python/test_context_scaffold.py" \
  "$repo/mini_jass/tests/python/test_context_training.py" \
  "$repo/mini_jass/tests/python/test_pattern_reconstruction_program.py"
phase contextual_pytest

"$python_bin" "$repo/mini_jass/tools/export_oracle.py" \
  --level l1 --executable "$build/mini_jass_cli" --output "$oracle"
phase oracle_export_l1

timeout -k 120s 7200s \
  "$python_bin" "$repo/mini_jass/tools/run_contextual_sealed_read.py" \
    --config "$repo/mini_jass/configs/contextual_outcome_supervision.yaml" \
    --oracle "$oracle" --c2-result "$c2_result" \
    --c2-freeze-report "$c2_freeze" --checkpoint-dir "$checkpoint_dir" \
    --run-dir "$run_dir" --compact-output "$compact" \
    --execution-host "$host" --implementation-sha "$implementation_sha"
phase contextual_sealed_read

cp "$compact" "$artefact_root/scientific-summary.json"
cp "$run_dir/result.full.json" "$artefact_root/contextual-sealed-read.full.json"
cp "$run_dir/sealed-arena-start-manifest.json" "$artefact_root/"
cp "$run_dir/SEALED_READ_STARTED.json" "$artefact_root/"
cp "$run_dir/SEALED_READ_COMPLETE.json" "$artefact_root/"
cp "$phase_log" "$artefact_root/PHASE_TIMINGS.txt"
printf '%s\n' "$implementation_sha" >"$artefact_root/IMPLEMENTATION_SHA.txt"

"$python_bin" - "$compact" "$artefact_root/RESULTS.txt" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
primary = report["aggregate"]["primary_common_search_arena_score"]
lines = [
    "milestone=CONTEXTUAL_SEALED_READ",
    f"status={report['status']}",
    f"protocol_hash={report['protocol_hash']}",
    f"result_hash={report['result_hash']}",
    f"primary_mean={primary['mean']}",
    f"primary_ci95_lower={primary['lower']}",
    f"primary_ci95_upper={primary['upper']}",
    "sealed_test_read_count=1",
    f"final_chained_decision_unchanged={report['final_chained_decision_unchanged']}",
    "descriptive_only=true",
    "promotable=false",
]
Path(sys.argv[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

summary_bytes=$(stat -c %s "$artefact_root/scientific-summary.json")
if [[ "$summary_bytes" -gt 65536 ]]; then
  echo "scientific-summary.json exceeds 64 KiB: $summary_bytes" >&2
  exit 6
fi
