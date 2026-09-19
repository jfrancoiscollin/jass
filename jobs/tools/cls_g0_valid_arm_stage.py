#!/usr/bin/env python3
"""Frozen CLS-G0 runtime catastrophe gate for one sealed valid candidate.

Consumes only the already-authenticated FULL-512 diagnostic cohort/deep reference,
the immutable CURRICULUM parent, the authenticated green G0 tooling preflight,
and one exact sealed LOCAL/WDL model from CLS-L recovery 2041 or HIER model from
the prospectively frozen HIER-L2 candidate fit 2062. The runtime gate itself is
unchanged; the only semantic difference between parent and candidate is evaluator bytes.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
from pathlib import Path
import shutil
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402
from jobs.tools import cls_g0_runtime_gate as gate  # noqa: E402
from jobs.tools import cls_g0_runtime_preflight_stage as tooling  # noqa: E402
from jobs.tools import cls_search_profile_stage as profile  # noqa: E402

SCHEMA = "jass.cls_g0_valid_arm_runtime.v1"
TECHNICAL_TERMINAL = "CLS_G0_VALID_ARM_RUNTIME_TECHNICAL_FAILURE_V1"
PHASE = "execute-g0-valid-arm-runtime"

SOURCE_JOB = "cpx62-2041-l3-cls-l-valid-arms-recovery-2038-v1"
SOURCE_ATTEMPT = "20260918T065139Z-c5067fce"
SOURCE_CODE = "c5067fcefddb48b49313686473d7b0c057a14028"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
SOURCE_LAUNCH_RECEIPT = "0925f7e1bcf537e26b22a91a151c438fae70f14a770b8324c5b708a3ae9e1ef2"

HIER_SOURCE_JOB = "cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1"
HIER_SOURCE_ATTEMPT = "20260919T142226Z-a28f1049"
HIER_SOURCE_CODE = "a28f10491d94ca451932b0e7b46df7cdf3b7e1c8"
HIER_SOURCE_PREFIX = f"r2:jass-data/runs/{HIER_SOURCE_JOB}/{HIER_SOURCE_ATTEMPT}"
HIER_SOURCE_LAUNCH_RECEIPT = "68203e5cd3fe40ea92c24bc2dfdc83c94cc52c257bbea871ed4e149b0873194e"

ARM_MODEL_SHA = {
    "LOCAL": "197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450",
    "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6",
    "HIER": "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628",
}

TOOLING_JOB = "cpx62-2018-l3-cls-g0-runtime-tooling-preflight-v3"
TOOLING_ATTEMPT = "20260917T001938Z-ad151a09"
TOOLING_CODE = "ad151a0961a077e5c95a5503a8ee734f5c4cf0b6"
TOOLING_PREFIX = f"r2:jass-data/runs/{TOOLING_JOB}/{TOOLING_ATTEMPT}"
TOOLING_LAUNCH_RECEIPT = "887f9f46adc3bf2cd014dd3a5cd8361ebe8c6ad84833f14099beba3e1e165d52"

CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
EXPECTED_SEARCHES = gate.ROOTS * 3


class StageError(RuntimeError):
    pass


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageError(f"not_object:{path}")
    return value


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise StageError(f"empty_tsv:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def hard_nodes_to_depth_failure_result(report: dict, root_ids: list[str]) -> dict[str, object] | None:
    """Map preregistered missing same-search d* receipts to terminal scientific FAIL.

    Section 5/7 of the frozen G0 contract says a missing exact/full-root d* receipt
    in either arm is a hard G0-C failure and forbids any surrogate. Invalid numeric
    receipts remain technical failures in the native probe.
    """
    root_set = set(root_ids)

    def checked_roots(name: str) -> list[str]:
        raw = report.get(name)
        if not isinstance(raw, list):
            raise StageError(f"probe missing-root inventory drift:{name}")
        values = [str(value) for value in raw]
        if len(values) != len(set(values)) or not set(values).issubset(root_set):
            raise StageError(f"probe missing-root identity drift:{name}")
        return values

    parent_missing = checked_roots("parent_nodes_to_depth_missing_roots")
    candidate_missing = checked_roots("candidate_nodes_to_depth_missing_roots")
    hard_reported = checked_roots("hard_nodes_to_depth_failure_roots")
    hard = [root for root in root_ids if root in set(parent_missing) | set(candidate_missing)]
    if hard_reported != hard:
        raise StageError("probe hard nodes-to-depth root-order drift")
    if report.get("hard_nodes_to_depth_failure_count") != len(hard):
        raise StageError("probe hard nodes-to-depth count drift")
    if report.get("nodes_to_depth_surrogate_used") is not False:
        raise StageError("probe nodes-to-depth surrogate drift")
    if not hard:
        return None

    reason = "missing_same_search_exact_full_root_receipt_no_surrogate"
    return {
        "schema": "jass.cls_g0_runtime_gate.v1",
        "state": "completed",
        "terminal": gate.FAIL_TERMINAL,
        "pass": False,
        "gates": {
            "nps": {
                "evaluated": False,
                "pass": None,
                "reason": "terminal_hard_nodes_to_depth_failure",
            },
            "completed_nominal_depth": {
                "evaluated": False,
                "pass": None,
                "reason": "terminal_hard_nodes_to_depth_failure",
            },
            "nodes_to_depth": {
                "evaluated": True,
                "value": None,
                "operator": "<=",
                "threshold": gate.NODES_TO_DEPTH_CEILING,
                "pass": False,
                "reason": reason,
                "hard_failure_roots": hard,
                "parent_missing_roots": parent_missing,
                "candidate_missing_roots": candidate_missing,
                "surrogate_used": False,
            },
            "search_transfer": {
                "evaluated": False,
                "pass": None,
                "reason": "terminal_hard_nodes_to_depth_failure",
            },
        },
        "bootstrap": {
            "performed": False,
            "replicates": gate.BOOTSTRAP_REPLICATES,
            "seed": gate.BOOTSTRAP_SEED,
            "unit": "root_id",
            "phase_stratified": True,
            "quantile": "numpy_type_7",
            "reason": reason,
        },
        "hard_nodes_to_depth_failure": {
            "count": len(hard),
            "roots": hard,
            "parent_missing_roots": parent_missing,
            "candidate_missing_roots": candidate_missing,
            "surrogate_used": False,
        },
        "alpha_spent": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }


def freeze_full_root_order(deep512: Path, root_selection: Path, deep_reference: Path,
                           ids_out: Path, deep512_out: Path, deep_out: Path) -> list[str]:
    selection = _json(root_selection)
    raw_ids = selection.get("parent_ids")
    if not isinstance(raw_ids, list) or len(raw_ids) != gate.ROOTS:
        raise StageError("FULL-512 root-order cardinality drift")
    ids = [str(value) for value in raw_ids]
    if len(set(ids)) != gate.ROOTS:
        raise StageError("FULL-512 duplicate root id")

    phase_rows = base.read_tsv(deep512)
    by_parent = {row.get("parent_id", ""): row for row in phase_rows}
    if len(by_parent) != gate.ROOTS or set(by_parent) != set(ids):
        raise StageError("FULL-512 cohort/root-order set drift")
    ordered_phase = [by_parent[root] for root in ids]
    counts = {phase: sum(row.get("phase") == phase for row in ordered_phase) for phase in gate.PHASES}
    if counts != {phase: gate.ROOTS_PER_PHASE for phase in gate.PHASES}:
        raise StageError(f"FULL-512 phase quota drift:{counts}")

    deep_rows = base.read_tsv(deep_reference)
    by_deep = {row.get("root_id", ""): row for row in deep_rows}
    if len(by_deep) != gate.ROOTS or set(by_deep) != set(ids):
        raise StageError("deep-reference root/order set drift")
    ordered_deep = [by_deep[root] for root in ids]
    if any(int(row.get("budget", "0")) != gate.DEEP_BUDGET for row in ordered_deep):
        raise StageError("deep-reference budget drift")

    base.atomic_write(ids_out, ("\n".join(ids) + "\n").encode("ascii"))
    _write_tsv(deep512_out, ordered_phase)
    _write_tsv(deep_out, ordered_deep)
    return ids


def authenticate_tooling(work: Path) -> dict:
    out = work / "tooling-2018"
    report = work / "verified-tooling-2018.json"
    base.fetch_completed(
        TOOLING_PREFIX, job=TOOLING_JOB, attempt=TOOLING_ATTEMPT, code=TOOLING_CODE,
        mappings=[
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
        ], out_dir=out, report=report,
    )
    if base.sha_file(out / "launch-receipt.json") != TOOLING_LAUNCH_RECEIPT:
        raise StageError("G0 tooling launch receipt drift")
    summary = _json(out / "scientific-summary.json")
    required = {
        "state": "completed",
        "terminal": "CLS_G0_RUNTIME_TOOLING_PREFLIGHT_READY_V1",
        "g0_identity_pass": True,
        "trace_parity_mismatches": 0,
        "new_jass_searches": 96,
        "new_scan_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise StageError(f"G0 tooling preflight drift:{key}")
    if summary.get("target_reads") != 0 or summary.get("candidate_reads") != 0:
        raise StageError("G0 tooling data-read boundary drift")
    return {
        "job_id": TOOLING_JOB,
        "attempt_id": TOOLING_ATTEMPT,
        "code_sha": TOOLING_CODE,
        "launch_receipt_sha256": TOOLING_LAUNCH_RECEIPT,
        "terminal": summary["terminal"],
    }


def authenticate_hier_candidate(work: Path) -> tuple[Path, dict]:
    out = work / "candidate-2062"
    report = work / "verified-candidate-2062.json"
    model_name = "model.pjtw.gz"
    receipt_name = "fit-receipt.json"
    base.fetch_completed(
        HIER_SOURCE_PREFIX,
        job=HIER_SOURCE_JOB,
        attempt=HIER_SOURCE_ATTEMPT,
        code=HIER_SOURCE_CODE,
        mappings=[
            (f"artefacts/{model_name}", model_name),
            (f"artefacts/{receipt_name}", receipt_name),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
        ],
        out_dir=out,
        report=report,
    )
    if base.sha_file(out / "launch-receipt.json") != HIER_SOURCE_LAUNCH_RECEIPT:
        raise StageError("2062 launch receipt drift")

    summary = _json(out / "scientific-summary.json")
    required = {
        "state": "completed",
        "terminal": "CLS_HIER_CANDIDATE_FIT_READY_V1",
        "arm": "HIER",
        "mode": "rehearsal",
        "fits": 1,
        "hier_l2": 1e-5,
        "l2": 1e-5,
        "model_sha256": ARM_MODEL_SHA["HIER"],
        "direct_parent_sha256": CURRICULUM_SHA,
        "fixed_curriculum_anchor_sha256": CURRICULUM_SHA,
        "varied_factor": "hier_l2",
        "next_stage": "RUN_FROZEN_CLS_G0",
        "target_reads": 0,
        "confirmation_target_reads": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise StageError(f"2062 HIER candidate source drift:{key}")

    model = work / "HIER.pjtw"
    with gzip.open(out / model_name, "rb") as source, model.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    if base.sha_file(model) != ARM_MODEL_SHA["HIER"]:
        raise StageError("2062 HIER raw model SHA drift")

    fit_receipt = _json(out / receipt_name)
    return model, {
        "job_id": HIER_SOURCE_JOB,
        "attempt_id": HIER_SOURCE_ATTEMPT,
        "code_sha": HIER_SOURCE_CODE,
        "launch_receipt_sha256": HIER_SOURCE_LAUNCH_RECEIPT,
        "terminal": summary["terminal"],
        "arm": "HIER",
        "model_sha256": ARM_MODEL_SHA["HIER"],
        "fit_receipt_sha256": base.sha_file(out / receipt_name),
        "fit_receipt_terminal": fit_receipt.get("terminal"),
        "source_mode": summary.get("mode"),
        "hier_l2": summary.get("hier_l2"),
        "direct_parent_sha256": summary.get("direct_parent_sha256"),
    }


def authenticate_candidate(work: Path, arm: str) -> tuple[Path, dict]:
    if arm not in ARM_MODEL_SHA:
        raise StageError(f"unsupported CLS-G0 candidate arm:{arm}")
    if arm == "HIER":
        return authenticate_hier_candidate(work)
    out = work / "candidate-2041"
    report = work / "verified-candidate-2041.json"
    model_name = f"{arm}.pjtw.gz"
    receipt_name = f"{arm}-fit-receipt.json"
    base.fetch_completed(
        SOURCE_PREFIX, job=SOURCE_JOB, attempt=SOURCE_ATTEMPT, code=SOURCE_CODE,
        mappings=[
            (f"artefacts/{model_name}", model_name),
            (f"artefacts/{receipt_name}", receipt_name),
            ("artefacts/scientific-summary.json", "scientific-summary.json"),
            ("artefacts/launch-receipt.json", "launch-receipt.json"),
        ], out_dir=out, report=report,
    )
    if base.sha_file(out / "launch-receipt.json") != SOURCE_LAUNCH_RECEIPT:
        raise StageError("2041 launch receipt drift")
    summary = _json(out / "scientific-summary.json")
    required = {
        "state": "completed",
        "terminal": "CLS_L_VALID_ARMS_RECOVERED_V1",
        "scientific_verdict": None,
        "fits": 2,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "attribution_complete": False,
        "technical_failed_arms": ["MIXED"],
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise StageError(f"2041 candidate source drift:{key}")
    if summary.get("confirmation_target_reads") != 0 or summary.get("arm_order") != ["LOCAL", "WDL"]:
        raise StageError("2041 candidate source read/order drift")
    if (summary.get("common_recipe") or {}).get("parent_sha256") != CURRICULUM_SHA:
        raise StageError("2041 parent anchor drift")
    if (summary.get("recovery_2038") or {}).get("retuning_performed") is not False:
        raise StageError("2041 retuning guard drift")
    arm_summary = (summary.get("arms") or {}).get(arm)
    if not isinstance(arm_summary, dict) or arm_summary.get("model_sha256") != ARM_MODEL_SHA[arm]:
        raise StageError(f"2041 {arm} model identity drift")

    model = work / f"{arm}.pjtw"
    with gzip.open(out / model_name, "rb") as source, model.open("wb") as dest:
        shutil.copyfileobj(source, dest)
    if base.sha_file(model) != ARM_MODEL_SHA[arm]:
        raise StageError(f"2041 {arm} raw model SHA drift")
    if model.stat().st_size != int(arm_summary.get("model_size_bytes", -1)):
        raise StageError(f"2041 {arm} model size drift")
    fit_receipt = _json(out / receipt_name)
    return model, {
        "job_id": SOURCE_JOB,
        "attempt_id": SOURCE_ATTEMPT,
        "code_sha": SOURCE_CODE,
        "launch_receipt_sha256": SOURCE_LAUNCH_RECEIPT,
        "terminal": summary["terminal"],
        "arm": arm,
        "model_sha256": ARM_MODEL_SHA[arm],
        "fit_receipt_sha256": base.sha_file(out / receipt_name),
        "fit_receipt_terminal": fit_receipt.get("terminal"),
        "source_mode": summary.get("mode"),
    }


def run_candidate_probe(exe: Path, parents: Path, ids: Path, parent: Path, candidate: Path,
                        output: Path, report: Path, log: Path) -> None:
    env = base.sanitized_env()
    base.run([
        str(exe), str(parents), str(ids), str(output), str(report),
        str(parent), str(candidate), str(base.EGDB_DIR),
    ], timeout=21600, log=log, env=env)


def run_stage(work: Path, artifacts: Path, arm: str, mode: str) -> dict[str, object]:
    if mode not in {"rehearsal", "production"}:
        raise StageError(f"invalid LAUNCH_MODE:{mode}")
    if arm not in ARM_MODEL_SHA:
        raise StageError(f"invalid candidate arm:{arm}")
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    tooling_auth = authenticate_tooling(work)
    candidate, candidate_auth = authenticate_candidate(work, arm)

    base_inputs = work / "base-inputs"
    source_work = work / "diagnostic-sources"
    source_artifacts = work / "diagnostic-source-artifacts"
    base_inputs.mkdir(parents=True, exist_ok=True)
    source_work.mkdir(parents=True, exist_ok=True)
    source_artifacts.mkdir(parents=True, exist_ok=True)
    parents, _parents_meta, deep512, curriculum, _scan = base.fetch_inputs(base_inputs)
    _depth_per_root, deep_reference = profile.authenticate_sources(source_work, source_artifacts)
    if base.sha_file(curriculum) != CURRICULUM_SHA:
        raise StageError("CURRICULUM parent bytes drift")

    depth_root_selection = source_work / "depth-2000" / "root-selection.json"
    ids = work / "g0-root-ids.txt"
    ordered_deep512 = work / "g0-deep512.tsv"
    ordered_deep = work / "g0-deep-reference.tsv"
    root_ids = freeze_full_root_order(
        deep512, depth_root_selection, deep_reference, ids, ordered_deep512, ordered_deep,
    )

    probe_exe = tooling.build_probe(work / "build")
    probe_tsv = work / "probe.tsv"
    probe_report = work / "probe-report.json"
    run_candidate_probe(
        probe_exe, parents, ids, curriculum, candidate,
        probe_tsv, probe_report, work / "probe.log",
    )
    report = _json(probe_report)
    required_probe = {
        "roots": gate.ROOTS,
        "budget_nodes": gate.PRIMARY_BUDGET,
        "threads": 1,
        "tt_mb": 16,
        "book_enabled": False,
        "trace_parity_roots": gate.ROOTS,
        "trace_parity_mismatches": 0,
        "nodes_to_depth_rule": "LAST_COMPLETED_EXACT_ALL_ACTIONS_SEARCHED_AT_TARGET_DEPTH",
        "parent_searches": gate.ROOTS * 2,
        "candidate_searches": gate.ROOTS,
        "alpha_spent": 0,
        "promotion_authorized": False,
    }
    for key, expected in required_probe.items():
        if report.get(key) != expected:
            raise StageError(f"probe contract drift:{key}")

    gate_result = hard_nodes_to_depth_failure_result(report, root_ids)
    if gate_result is None:
        vectors = gate.paired_vectors(
            gate.read_tsv(probe_tsv), gate.read_tsv(ordered_deep512), gate.read_tsv(ordered_deep)
        )
        metrics = gate.bootstrap(vectors)
        gate_result = gate.decide(metrics)

    for name, source in {
        "g0-root-ids.txt": ids,
        "g0-deep512.tsv": ordered_deep512,
        "g0-deep-reference.tsv": ordered_deep,
        "probe.tsv": probe_tsv,
        "probe-report.json": probe_report,
    }.items():
        shutil.copy2(source, artifacts / name)
    base.atomic_write(artifacts / "gate-readout.json", base.canonical_json(gate_result))

    diagnostic_auth = _json(source_artifacts / "source-authentication.json")
    source_auth = {
        "schema": "jass.cls_g0_valid_arm_source_authentication.v1",
        "authenticated": True,
        "cohort_identity_sha256": profile.COHORT_SHA,
        "curriculum_sha256": CURRICULUM_SHA,
        "roots": gate.ROOTS,
        "root_order_sha256": base.sha_file(ids),
        "diagnostic_sources": diagnostic_auth,
        "g0_tooling_preflight": tooling_auth,
        "candidate_source": candidate_auth,
        "fresh_scan_searches": 0,
        "target_reads": 0,
        "strength_games": 0,
        "alpha_spent": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(source_auth))
    base.atomic_write(artifacts / "candidate-authentication.json", base.canonical_json(candidate_auth))

    passed = bool(gate_result.get("pass"))
    summary: dict[str, object] = {
        "schema": SCHEMA,
        "state": "completed",
        "terminal": gate_result["terminal"],
        "scientific_verdict": "PASS" if passed else "FAIL",
        "diagnostic_only": False,
        "mode": mode,
        "candidate_arm": arm,
        "candidate_sha256": ARM_MODEL_SHA[arm],
        "direct_parent_sha256": CURRICULUM_SHA,
        "fixed_curriculum_anchor_sha256": CURRICULUM_SHA,
        "cohort_identity_sha256": profile.COHORT_SHA,
        "roots": gate.ROOTS,
        "roots_per_phase": gate.ROOTS_PER_PHASE,
        "budget_nodes": gate.PRIMARY_BUDGET,
        "bootstrap_replicates": gate.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": gate.BOOTSTRAP_SEED,
        "trace_parity_mismatches": 0,
        "gate": gate_result,
        "next_stage": (
            "PREREGISTER_STRENGTH_AT_TIME_FOR_EXACT_G0_PASS_CANDIDATE"
            if passed else "TERMINAL_CANDIDATE_RUNTIME_CATASTROPHE_FAIL"
        ),
        "target_reads": 0,
        "confirmation_target_reads": 0,
        "fits": 0,
        "new_jass_searches": EXPECTED_SEARCHES,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    hard = gate_result.get("hard_nodes_to_depth_failure")
    hard_note = ""
    if isinstance(hard, dict) and hard.get("count"):
        hard_note = (
            f"\nG0-C hard failure roots: {hard['count']}; at least one arm had no exact "
            "same-search full-root receipt at parent-defined d*. No surrogate was used.\n"
        )
    results = (
        "# CLS-G0 runtime catastrophe gate — sealed valid arm\n\n"
        f"Arm: `{arm}`  \n"
        f"Candidate SHA256: `{ARM_MODEL_SHA[arm]}`  \n"
        f"Parent / fixed anchor SHA256: `{CURRICULUM_SHA}`  \n"
        f"Roots: {gate.ROOTS} ({gate.ROOTS_PER_PHASE}/phase), exact node budget: {gate.PRIMARY_BUDGET}.  \n"
        f"Terminal: `{gate_result['terminal']}`.\n"
        f"{hard_note}\n"
        "The same executable/search configuration was used for parent and candidate; evaluator bytes "
        "were the only semantic difference. SearchDecisionTrace passivity was proved on all parent "
        "roots before candidate measurement, and nodes-to-depth came only from the same search.\n\n"
        "No Scan search, fit, target read, strength game, alpha, promotion or bake was consumed.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results.encode("utf-8"))
    return summary
