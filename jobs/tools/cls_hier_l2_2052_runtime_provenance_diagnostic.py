#!/usr/bin/env python3
"""Compare bounded technical runtime provenance for failed CONTROL rehearsal 2052.

This diagnostic follows the authenticated 2053 finding that CONTROL still produced
499a... rather than immutable CURRICULUM 319d... even after the historical 1341
source recipe was materialized. It reads only two small technical runtime receipts:

* 2052 ``runtime-authentication.json`` (created by the repaired historical recipe),
* 1330 ``python-runtime.json`` (the Aug-14 current-compatible CPX runtime witness).

It also authenticates the immutable source templates at their exact commits to
show that both jobs name the same persistent numeric-venv path. It does not read
corpora, targets, model bytes, optimizer/fit logs, searches, games, alpha,
promotion or bake state. A package-version difference is technical evidence only;
it is not treated as a scientific conclusion or, by itself, as proof that the
1330 host runtime remained unchanged through 1341.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_2031_failure_diagnostic as base  # noqa: E402
from launch_runtime_v2 import StageEvidence, atomic_json as runtime_atomic_json  # noqa: E402

FAILED_JOB = "cpx62-2052-l3-cls-hier-l2-control-reproduction-rehearsal-v2"
FAILED_ATTEMPT = "20260919T004808Z-a10f9217"
FAILED_CODE = "a10f921715674eca7decfc76714637264fa4d6d2"
FAILED_PREFIX = f"r2:jass-data/runs/{FAILED_JOB}/{FAILED_ATTEMPT}"

HIST_RUNTIME_JOB = "cpx62-1330-jass-megacorpus-smoke-fit-v1"
HIST_RUNTIME_ATTEMPT = "20260814T063409Z-80f38787"
HIST_RUNTIME_CODE = "80f3878709da5df0fa449e348f8a713b399a453e"
HIST_RUNTIME_PREFIX = f"r2:jass-data/runs/{HIST_RUNTIME_JOB}/{HIST_RUNTIME_ATTEMPT}"

CURRICULUM_CODE = "18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_TEMPLATE = "jobs/templates/jass-megacorpus-arm-d-fit-v1.sh"
SMOKE_TEMPLATE = "jobs/templates/jass-megacorpus-smoke-fit-v1.sh"
VENV_PATH = "/var/tmp/jass-l3-numeric-venv-current-v1"

TERMINAL = "CLS_HIER_L2_2052_RUNTIME_PROVENANCE_DIAGNOSTIC_COMPLETE_V1"
PHASE = "execute-cls-hier-l2-2052-runtime-provenance-diagnostic"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(commit: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def authenticate_template_contracts() -> dict[str, object]:
    smoke = git_blob(HIST_RUNTIME_CODE, SMOKE_TEMPLATE)
    curriculum = git_blob(CURRICULUM_CODE, CURRICULUM_TEMPLATE)
    smoke_text = smoke.decode("utf-8", errors="strict")
    curriculum_text = curriculum.decode("utf-8", errors="strict")
    if VENV_PATH not in smoke_text or VENV_PATH not in curriculum_text:
        raise RuntimeError("historical numeric venv path drift")
    if "python3 -m venv --clear" not in smoke_text:
        raise RuntimeError("1330 runtime-creation contract drift")
    if ".jass-runtime-ready-v1" not in smoke_text or ".jass-runtime-ready-v1" not in curriculum_text:
        raise RuntimeError("historical READY-marker contract drift")
    if "persistent numeric runtime absent; do not reinstall in this job" not in curriculum_text:
        raise RuntimeError("1341 persistent-runtime-only contract drift")
    return {
        "venv_path": VENV_PATH,
        "smoke_code_sha": HIST_RUNTIME_CODE,
        "smoke_template": SMOKE_TEMPLATE,
        "smoke_template_sha256": sha_bytes(smoke),
        "smoke_creates_persistent_runtime_if_missing": True,
        "curriculum_code_sha": CURRICULUM_CODE,
        "curriculum_template": CURRICULUM_TEMPLATE,
        "curriculum_template_sha256": sha_bytes(curriculum),
        "curriculum_requires_ready_runtime_without_reinstall": True,
        "continuity_from_1330_to_1341_proven": False,
    }


def runtime_view(payload: dict, *, historical: bool) -> dict[str, object]:
    out: dict[str, object] = {
        "schema": payload.get("schema"),
        "numpy": payload.get("numpy"),
        "scipy": payload.get("scipy"),
    }
    if historical:
        out.update(
            {
                "stack": payload.get("stack"),
                "venv": payload.get("venv"),
                "persistent_cache": payload.get("persistent_cache"),
            }
        )
    else:
        out.update(
            {
                "python": payload.get("python"),
                "python_executable": payload.get("python_executable"),
                "platform": payload.get("platform"),
                "historical_recipe_code_sha": payload.get("historical_recipe_code_sha"),
                "historical_train_stream_blob_sha": payload.get("historical_train_stream_blob_sha"),
                "historical_gen_patterns_blob_sha": payload.get("historical_gen_patterns_blob_sha"),
            }
        )
    for key in ("numpy", "scipy"):
        if not isinstance(out[key], str) or not out[key]:
            raise RuntimeError(f"runtime receipt missing {key}")
    return out


def compare_runtime_versions(historical: dict, current: dict) -> dict[str, object]:
    h = runtime_view(historical, historical=True)
    c = runtime_view(current, historical=False)
    comparisons = {
        "numpy_equal": h["numpy"] == c["numpy"],
        "scipy_equal": h["scipy"] == c["scipy"],
    }
    drift = not all(comparisons.values())
    return {
        "historical_runtime": h,
        "failed_2052_runtime": c,
        "comparisons": comparisons,
        "package_version_drift_observed": drift,
        "causal_runtime_drift_proven": False,
        "reason": (
            "package versions differ between the immutable 1330 runtime witness and 2052; "
            "host-runtime continuity from 1330 through 1341 remains to be established before replay"
            if drift
            else "NumPy/SciPy versions match the immutable 1330 witness; package-version drift is not the mismatch witness"
        ),
    }


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def authenticate_result(
    *, rclone: str, prefix: str, job: str, attempt: str, code: str, state: str
) -> dict:
    inventory = base.fetch.inspect_result_inventory(
        rclone=rclone, prefix=prefix, expected_state=state
    )
    got = (
        inventory.get("job_id"),
        inventory.get("attempt_id"),
        inventory.get("code_sha"),
        inventory.get("result_state"),
    )
    want = (job, attempt, code, state)
    if got != want:
        raise RuntimeError(f"technical runtime source identity drift: got={got} want={want}")
    return inventory


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    work = result_dir / "work" / "runtime-provenance"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    evidence.begin(PHASE)
    rclone = os.environ.get("RCLONE_BIN", "rclone")

    failed_inventory = authenticate_result(
        rclone=rclone,
        prefix=FAILED_PREFIX,
        job=FAILED_JOB,
        attempt=FAILED_ATTEMPT,
        code=FAILED_CODE,
        state="failed",
    )
    historical_inventory = authenticate_result(
        rclone=rclone,
        prefix=HIST_RUNTIME_PREFIX,
        job=HIST_RUNTIME_JOB,
        attempt=HIST_RUNTIME_ATTEMPT,
        code=HIST_RUNTIME_CODE,
        state="failed",
    )

    failed_files = {item.get("path"): item for item in failed_inventory.get("files", [])}
    historical_files = {item.get("path"): item for item in historical_inventory.get("files", [])}
    if "artefacts/runtime-authentication.json" not in failed_files:
        raise RuntimeError("2052 runtime-authentication artifact missing")
    if "artefacts/python-runtime.json" not in historical_files:
        raise RuntimeError("1330 python-runtime artifact missing")

    current_fetch = base.fetch.fetch_files(
        rclone=rclone,
        prefix=FAILED_PREFIX,
        expected_state="failed",
        selections=[("artefacts/runtime-authentication.json", "runtime-2052.json")],
        out_dir=work,
    )
    historical_fetch = base.fetch.fetch_files(
        rclone=rclone,
        prefix=HIST_RUNTIME_PREFIX,
        expected_state="failed",
        selections=[("artefacts/python-runtime.json", "runtime-1330.json")],
        out_dir=work,
    )

    current = json.loads((work / "runtime-2052.json").read_text(encoding="utf-8"))
    historical = json.loads((work / "runtime-1330.json").read_text(encoding="utf-8"))
    if current.get("historical_recipe_code_sha") != CURRICULUM_CODE:
        raise RuntimeError("2052 historical recipe code authentication drift")
    if historical.get("venv") != VENV_PATH:
        raise RuntimeError("1330 persistent numeric venv path drift")

    templates = authenticate_template_contracts()
    comparison = compare_runtime_versions(historical, current)
    drift = bool(comparison["package_version_drift_observed"])
    next_stage = (
        "PROVE_1330_TO_1341_RUNTIME_CONTINUITY_BEFORE_NUMERIC_REPLAY"
        if drift
        else "RECOVER_NONPACKAGE_NUMERIC_ENVIRONMENT_PROVENANCE"
    )

    diagnostic = {
        "schema": "jass.cls_hier_l2_2052_runtime_provenance_diagnostic.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_2052_source": {
            "job_id": FAILED_JOB,
            "attempt_id": FAILED_ATTEMPT,
            "code_sha": FAILED_CODE,
            "runtime_receipt_sha256": base.sha256(work / "runtime-2052.json"),
        },
        "historical_runtime_witness": {
            "job_id": HIST_RUNTIME_JOB,
            "attempt_id": HIST_RUNTIME_ATTEMPT,
            "code_sha": HIST_RUNTIME_CODE,
            "runtime_receipt_sha256": base.sha256(work / "runtime-1330.json"),
        },
        "template_contracts": templates,
        "runtime_comparison": comparison,
        "next_stage": next_stage,
        "boundary": {
            "scientific_payloads_read": 0,
            "candidate_model_payloads_read": 0,
            "fit_log_payloads_read": 0,
            "target_reads": 0,
            "fits": 0,
            "new_jass_searches": 0,
            "new_scan_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        },
    }
    write_json(art / "runtime-provenance.json", diagnostic)
    write_json(
        art / "source-authentication.json",
        {
            "schema": "jass.cls_hier_l2_2052_runtime_provenance_authentication.v1",
            "failed_2052": current_fetch,
            "historical_1330": historical_fetch,
            "technical_source_only": True,
        },
    )
    summary = {
        "schema": "jass.cls_hier_l2_2052_runtime_provenance_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "package_version_drift_observed": drift,
        "causal_runtime_drift_proven": False,
        "historical_numpy": comparison["historical_runtime"]["numpy"],
        "historical_scipy": comparison["historical_runtime"]["scipy"],
        "failed_2052_numpy": comparison["failed_2052_runtime"]["numpy"],
        "failed_2052_scipy": comparison["failed_2052_runtime"]["scipy"],
        "historical_runtime_continuity_to_1341_proven": False,
        "next_stage": next_stage,
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    runtime_atomic_json(art / "scientific-summary.json", summary)
    write_json(
        art / "manifest.json",
        {
            "schema": "jass.cls_hier_l2_2052_runtime_provenance_manifest.v1",
            "terminal": TERMINAL,
            "diagnostic_only": True,
            "technical_runtime_receipts_read": 2,
            "scientific_payloads_read": 0,
            "promotion_authorized": False,
            "bake_authorized": False,
        },
    )
    (art / "RESULTS.md").write_text(
        "# CLS HIER-L2 2052 runtime provenance diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- 1330 runtime NumPy/SciPy: `{comparison['historical_runtime']['numpy']}` / `{comparison['historical_runtime']['scipy']}`\n"
        f"- 2052 runtime NumPy/SciPy: `{comparison['failed_2052_runtime']['numpy']}` / `{comparison['failed_2052_runtime']['scipy']}`\n"
        f"- package version drift observed: `{drift}`\n"
        "- causal runtime drift proven: `False` (1330->1341 host continuity is not assumed)\n"
        f"- next stage: `{next_stage}`\n"
        "- scientific payload reads/fits/searches/games/targets/alpha/promotion/bake: `0`\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
