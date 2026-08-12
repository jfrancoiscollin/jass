#!/usr/bin/env bash
# Recover M15-C6 aggregation from authenticated per-seed results after a
# post-seed reporting crash. This path performs no scientific recomputation.
set -Eeuo pipefail

repo=${JASS_CODE_DIR:?JASS_CODE_DIR is required}
result_root=${JASS_RESULT_DIR:?JASS_RESULT_DIR is required}
artefact_root=${JASS_ARTEFACT_DIR:?JASS_ARTEFACT_DIR is required}
source_uri=${M15C6_RECOVERY_SOURCE_URI:?M15C6_RECOVERY_SOURCE_URI is required}
source_job=${M15C6_RECOVERY_SOURCE_JOB:?M15C6_RECOVERY_SOURCE_JOB is required}
source_attempt=${M15C6_RECOVERY_SOURCE_ATTEMPT:?M15C6_RECOVERY_SOURCE_ATTEMPT is required}
source_code_sha=${M15C6_RECOVERY_SOURCE_CODE_SHA:?M15C6_RECOVERY_SOURCE_CODE_SHA is required}
venv=${MINI_JASS_PATTERN_VENV:-/home/jf/.cache/mj-m15p-venv}

[[ "$(hostname)" == User && "$(nproc)" -eq 16 ]] || exit 2
[[ "$source_uri" == "r2:jass-data/runs/$source_job/$source_attempt" ]] || exit 2
[[ "$source_job" == home-1260-mini-jass-pattern-m15c6-full-v2 ]] || exit 2
[[ "$source_attempt" == 20260812T061436Z-85e428bb ]] || exit 2
[[ "$source_code_sha" == 85e428bba2d8e0452dc09dea6e624d0812a7dfec ]] || exit 2
[[ -x "$venv/bin/python" ]] || {
  echo "persistent HOME venv missing; refusing dependency reinstall" >&2
  exit 3
}
command -v rclone >/dev/null || exit 3

work="$result_root/m15c6-aggregate-recovery"
source_root="$work/source"
run_dir="$work/run"
full_result="$work/result.full.json"
mkdir -p "$source_root" "$run_dir" "$artefact_root"
files="$work/source-files.txt"
{
  printf '%s\n' manifest.json inventory.json checksums.sha256
  for seed in $(seq 279001 279024); do
    printf 'mini-jass-pattern-m15c6-full/run/seed-%s.json\n' "$seed"
  done
} >"$files"

# Exact metadata/result reads only. No corpus, model, oracle, frozen cohort or
# game payload is selected by this list.
timeout 300s rclone copy "$source_uri" "$source_root" \
  --files-from-raw "$files" --no-traverse
[[ "$(find "$source_root/mini-jass-pattern-m15c6-full/run" -name 'seed-*.json' -type f | wc -l)" -eq 24 ]] || {
  echo "M15-C6 recovery did not fetch exactly 24 seed results" >&2
  exit 4
}

export PYTHONPATH="$repo/mini_jass/python"
"$venv/bin/python" -m py_compile \
  "$repo/mini_jass/tools/run_pattern_contextual_decision_channel.py"
"$venv/bin/python" -m pytest -q \
  "$repo/mini_jass/tests/python/test_pattern_contextual_decision_channel.py"
"$venv/bin/python" \
  "$repo/mini_jass/tools/run_pattern_contextual_decision_channel.py" \
  --config "$repo/mini_jass/configs/l1_pattern_contextual_decision_channel.yaml" \
  --run-dir "$run_dir" --compact-output "$full_result" \
  --execution-host User --recover-source-root "$source_root" \
  --recovery-source-job "$source_job" \
  --recovery-source-attempt "$source_attempt" \
  --recovery-source-code-sha "$source_code_sha"

cp "$full_result" "$artefact_root/result.full.json"
"$venv/bin/python" - "$full_result" "$artefact_root" <<'PY'
import json
from pathlib import Path
import sys

full = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])
if int(full.get("aggregate", {}).get("paired_seed_count", 0)) != 24:
    raise SystemExit("M15-C6 recovery n != 24")
recovery = full.get("recovery_contract", {})
if (
    recovery.get("authenticated_seed_count") != 24
    or recovery.get("scientific_compute_repeated") is not False
    or recovery.get("additional_frozen_test_reads") != 0
):
    raise SystemExit("invalid M15-C6 recovery contract")
summary = {
    "schema": full["schema"],
    "milestone": full["milestone"],
    "status": full["status"],
    "protocol_hash": full["protocol_hash"],
    "result_hash": full["result_hash"],
    "aggregate": full["aggregate"],
    "recommendation": full["recommendation"],
    "sealed_cohort_contract": full["sealed_cohort_contract"],
    "recovery_contract": recovery,
    "promotable": False,
}
(out / "scientific-summary.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
(out / "RESULTS.txt").write_text(
    "cell=m15c6\n"
    f"status={full['status']}\n"
    f"result_hash={full['result_hash']}\n"
    f"finding={full['recommendation']['finding']}\n"
    "n=24\n"
    f"aligned_minus_shuffled={full['recommendation']['aligned_minus_shuffled_mean']}\n"
    f"aligned_minus_lambda={full['recommendation']['aligned_minus_lambda_mean']}\n"
    "recovered_authenticated_seed_results=24\n"
    "scientific_compute_repeated=false\n"
    "additional_frozen_test_reads=0\n"
    "promotable=false\n",
    encoding="utf-8",
)
if (out / "scientific-summary.json").stat().st_size > 65536:
    raise SystemExit("scientific-summary.json exceeds 64 KiB")
PY
touch "$artefact_root/VERDICT__M15C6_RECOVERED"
touch "$artefact_root/PROMOTION_AUTHORIZED__FALSE"
