#!/usr/bin/env python3
"""Bound residual CONTROL mismatch to fit/input provenance after 2057.

2057 proved that 2056 completed the CONTROL fit under the exact historical
NumPy/SciPy package versions but still produced the same non-parent model SHA
seen in earlier replays.  This diagnostic is deliberately zero-effect: it reads
only small published fit metadata from failed 2056 and authoritative 1341 and
compares target-consumption, optimizer and convergence receipts.  It never
reads target arrays, corpus rows, feature matrices, model bytes, search/game
payloads, or promotion/bake state, and it performs no fit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_2031_failure_diagnostic as base  # noqa: E402
from launch_runtime_v2 import StageEvidence, atomic_json as runtime_atomic_json  # noqa: E402

FAILED_JOB = "cpx62-2056-l3-cls-hier-l2-control-reproduction-rehearsal-v3"
FAILED_ATTEMPT = "20260919T043639Z-4ed47cc5"
FAILED_CODE = "4ed47cc53d5bd0da708f7ad1324f9da213c4c215"
FAILED_PREFIX = f"r2:jass-data/runs/{FAILED_JOB}/{FAILED_ATTEMPT}"

HIST_JOB = "cpx62-1341-jass-megacorpus-arm-d-fit-v1"
HIST_ATTEMPT = "20260814T191555Z-18c38a33"
HIST_CODE = "18c38a33ae78c9c2e8e2df62fca266da28dacead"
HIST_PREFIX = f"r2:jass-data/runs/{HIST_JOB}/{HIST_ATTEMPT}"

ACTUAL_2056_SHA = "499a213cbc96fdd43956a9b2f757104970b5afe0817979126c1f7eb92b0aa504"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
TERMINAL = "CLS_HIER_L2_2056_FIT_PROVENANCE_DIAGNOSTIC_COMPLETE_V1"
PHASE = "execute-cls-hier-l2-2056-fit-provenance-diagnostic"

FAILED_FILES = (
    ("artefacts/optimizer.json", "failed/optimizer.json"),
    ("artefacts/fit-receipt.json", "failed/convergence.json"),
    ("artefacts/target-consumption.json", "failed/target-consumption.json"),
    ("artefacts/runtime-authentication.json", "failed/runtime-authentication.json"),
)
HIST_FILES = (
    ("artefacts/D-optimizer.json", "historical/optimizer.json"),
    ("artefacts/D-convergence.json", "historical/convergence.json"),
    ("artefacts/D-target-consumption.json", "historical/target-consumption.json"),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def differing_top_level_keys(left: dict, right: dict) -> list[str]:
    keys = sorted(set(left) | set(right))
    return [key for key in keys if left.get(key) != right.get(key)]


def without_cosmetic_fields(payload: dict) -> dict:
    # Convergence receipts can carry an arm/label while certifying the same
    # optimizer mechanics. Do not erase any numeric or success field.
    return {k: v for k, v in payload.items() if k not in {"label", "arm", "model"}}


def target_view(payload: dict) -> dict[str, object]:
    source = payload.get("source") or {}
    if not isinstance(source, dict):
        raise RuntimeError("target-consumption source must be an object")
    return {
        "source_sha256": source.get("sha256"),
        "source_size_bytes": source.get("size_bytes"),
        "source_shape": source.get("shape"),
        "source_dtype": source.get("dtype"),
        "records": payload.get("records"),
        "train_records": payload.get("train_records"),
        "holdout_records": payload.get("holdout_records"),
        "consumed": payload.get("consumed"),
        "target": payload.get("target"),
        "loss": payload.get("loss"),
    }


def authenticate_result(*, rclone: str, prefix: str, job: str, attempt: str, code: str, state: str) -> dict:
    inventory = base.fetch.inspect_result_inventory(
        rclone=rclone, prefix=prefix, expected_state=state
    )
    got = (
        inventory.get("job_id"), inventory.get("attempt_id"),
        inventory.get("code_sha"), inventory.get("result_state"),
    )
    want = (job, attempt, code, state)
    if got != want:
        raise RuntimeError(f"fit provenance source identity drift: got={got} want={want}")
    return inventory


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    work = result_dir / "work" / "fit-provenance"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    evidence.begin(PHASE)
    rclone = os.environ.get("RCLONE_BIN", "rclone")

    failed_inventory = authenticate_result(
        rclone=rclone, prefix=FAILED_PREFIX, job=FAILED_JOB,
        attempt=FAILED_ATTEMPT, code=FAILED_CODE, state="failed",
    )
    hist_inventory = authenticate_result(
        rclone=rclone, prefix=HIST_PREFIX, job=HIST_JOB,
        attempt=HIST_ATTEMPT, code=HIST_CODE, state="completed",
    )

    failed_paths = {x.get("path") for x in failed_inventory.get("files", [])}
    hist_paths = {x.get("path") for x in hist_inventory.get("files", [])}
    missing_failed = [remote for remote, _ in FAILED_FILES if remote not in failed_paths]
    missing_hist = [remote for remote, _ in HIST_FILES if remote not in hist_paths]
    if missing_failed or missing_hist:
        raise RuntimeError(
            f"required bounded fit provenance missing: failed={missing_failed} historical={missing_hist}"
        )

    failed_fetch = base.fetch.fetch_files(
        rclone=rclone, prefix=FAILED_PREFIX, expected_state="failed",
        selections=list(FAILED_FILES), out_dir=work,
    )
    hist_fetch = base.fetch.fetch_files(
        rclone=rclone, prefix=HIST_PREFIX, expected_state="completed",
        selections=list(HIST_FILES), out_dir=work,
    )

    f_opt = load(work / "failed" / "optimizer.json")
    h_opt = load(work / "historical" / "optimizer.json")
    f_conv = load(work / "failed" / "convergence.json")
    h_conv = load(work / "historical" / "convergence.json")
    f_target = load(work / "failed" / "target-consumption.json")
    h_target = load(work / "historical" / "target-consumption.json")
    runtime = load(work / "failed" / "runtime-authentication.json")

    runtime_pair = (runtime.get("numpy"), runtime.get("scipy"))
    if runtime_pair != ("2.5.2", "1.18.0"):
        raise RuntimeError(f"2056 exact historical numeric runtime drift: {runtime_pair}")

    f_target_view = target_view(f_target)
    h_target_view = target_view(h_target)
    target_source_equal = (
        isinstance(f_target_view["source_sha256"], str)
        and f_target_view["source_sha256"] == h_target_view["source_sha256"]
    )
    target_contract_equal = f_target_view == h_target_view
    optimizer_exact_equal = canonical(f_opt) == canonical(h_opt)
    convergence_semantic_equal = (
        canonical(without_cosmetic_fields(f_conv))
        == canonical(without_cosmetic_fields(h_conv))
    )

    if not target_source_equal:
        next_stage = "RECOVER_TARGET_INPUT_REPRODUCTION_MECHANICS"
        bounded_class = "TARGET_INPUT_DRIFT"
    elif not target_contract_equal:
        next_stage = "RECOVER_TARGET_CONSUMPTION_CONTRACT_MECHANICS"
        bounded_class = "TARGET_CONSUMPTION_DRIFT"
    elif not optimizer_exact_equal or not convergence_semantic_equal:
        next_stage = "RECOVER_NUMERIC_OPTIMIZER_PROVENANCE_BEYOND_PACKAGE_VERSIONS"
        bounded_class = "OPTIMIZER_TRAJECTORY_DRIFT"
    else:
        next_stage = "RECOVER_FEATURE_OR_SERIALIZATION_PROVENANCE"
        bounded_class = "POST_OPTIMIZER_BYTE_DRIFT"

    comparison = {
        "schema": "jass.cls_hier_l2_2056_fit_provenance_comparison.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_model_sha256_from_authenticated_2057": ACTUAL_2056_SHA,
        "expected_parent_sha256": CURRICULUM_SHA,
        "failed_runtime": {
            "numpy": runtime.get("numpy"),
            "scipy": runtime.get("scipy"),
            "historical_recipe_code_sha": runtime.get("historical_recipe_code_sha"),
        },
        "target_comparison": {
            "historical": h_target_view,
            "failed_2056": f_target_view,
            "source_sha256_equal": target_source_equal,
            "contract_view_equal": target_contract_equal,
            "historical_file_sha256": sha256(work / "historical" / "target-consumption.json"),
            "failed_file_sha256": sha256(work / "failed" / "target-consumption.json"),
            "differing_top_level_keys": differing_top_level_keys(h_target, f_target),
        },
        "optimizer_comparison": {
            "exact_json_equal": optimizer_exact_equal,
            "historical_file_sha256": sha256(work / "historical" / "optimizer.json"),
            "failed_file_sha256": sha256(work / "failed" / "optimizer.json"),
            "differing_top_level_keys": differing_top_level_keys(h_opt, f_opt),
            "historical": h_opt,
            "failed_2056": f_opt,
        },
        "convergence_comparison": {
            "semantic_equal_ignoring_only_label_arm_model": convergence_semantic_equal,
            "historical_file_sha256": sha256(work / "historical" / "convergence.json"),
            "failed_file_sha256": sha256(work / "failed" / "convergence.json"),
            "differing_top_level_keys": differing_top_level_keys(h_conv, f_conv),
            "historical": h_conv,
            "failed_2056": f_conv,
        },
        "bounded_class": bounded_class,
        "next_stage": next_stage,
        "boundary": {
            "corpus_rows_read": 0,
            "target_arrays_read": 0,
            "feature_matrices_read": 0,
            "model_bytes_read": 0,
            "fit_logs_read": 0,
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
    write_json(art / "fit-provenance-comparison.json", comparison)
    write_json(
        art / "source-authentication.json",
        {
            "schema": "jass.cls_hier_l2_2056_fit_provenance_authentication.v1",
            "failed_2056": failed_fetch,
            "historical_1341": hist_fetch,
            "bounded_metadata_only": True,
        },
    )
    summary = {
        "schema": "jass.cls_hier_l2_2056_fit_provenance_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "bounded_class": bounded_class,
        "target_source_sha256_equal": target_source_equal,
        "target_contract_view_equal": target_contract_equal,
        "optimizer_exact_json_equal": optimizer_exact_equal,
        "convergence_semantic_equal": convergence_semantic_equal,
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
            "schema": "jass.cls_hier_l2_2056_fit_provenance_manifest.v1",
            "terminal": TERMINAL,
            "diagnostic_only": True,
            "published_metadata_files_read": len(FAILED_FILES) + len(HIST_FILES),
            "target_arrays_read": 0,
            "model_bytes_read": 0,
            "fits": 0,
            "promotion_authorized": False,
            "bake_authorized": False,
        },
    )
    (art / "RESULTS.md").write_text(
        "# CLS HIER-L2 2056 fit provenance diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- target source SHA equal to authoritative 1341: `{target_source_equal}`\n"
        f"- target contract view equal: `{target_contract_equal}`\n"
        f"- optimizer JSON exact equal: `{optimizer_exact_equal}`\n"
        f"- convergence receipt semantically equal: `{convergence_semantic_equal}`\n"
        f"- bounded class: `{bounded_class}`\n"
        f"- next stage: `{next_stage}`\n"
        "- corpus/target-array/feature/model/fit-log reads: `0`\n"
        "- fits/searches/games/alpha/promotion/bake: `0`\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
