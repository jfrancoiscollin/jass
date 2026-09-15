#!/usr/bin/env python3
"""ED5 k=2 fresh-D confirmation over the proven ED4 D machinery.

This adapter preserves the already-vetted ED4 D target implementation and changes
only prospectively preregistered ED5 identities/accounting: repaired D1990,
sealed ED5 candidate 1974, authenticated D/W/S+historical barrier 1995,
k=2 alpha, and the three frozen ED5 bootstrap seeds.  Rehearsal performs no
confirmation-target read.  Production is the first target-consuming ED5 stage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_d_confirmation_stage as base
from jobs.tools.launch_runtime_v2 import atomic_json

D_SOURCE = (
    "cpx62-1990-l3-ed5-fresh-d-source-production-v2",
    "20260915T155218Z-f746408f",
    "f746408fcd8aaaa046bdeb479fe54c6b7edca39e",
)
CANDIDATE_SOURCE = (
    "cpx62-1974-l3-ed5-q200k-choice-fit-production-v1",
    "20260914T183838Z-3b116639",
    "3b1166398b8c78c5e1bb0355cf6fbc39e04c8ce6",
)
DISJOINTNESS_SOURCE = (
    "cpx62-1995-l3-ed5-fresh-dws-historical-disjointness-rehearsal-v3",
    "20260915T185720Z-b64ae6e8",
    "b64ae6e8b76260684227dd5312a08e9d980d7570",
)
W_SOURCE = (
    "cpx62-1988-l3-ed5-fresh-w-source-production-v5",
    "20260915T130012Z-da8aa733",
    "da8aa7334f2873ca17ca353b3df2fa4f4a562d47",
)
S_SOURCE = (
    "cpx62-1984-l3-ed5-fresh-s-source-production-v2",
    "20260915T084337Z-9e8eb2a3",
    "9e8eb2a32d80f15491ef1ff6bb5aa3b95edcdc49",
)
CANDIDATE_NAME = "ED5_Q200K_CHOICE.pjtw"
CANDIDATE_SHA256 = "f4e35ad02704f822614eb5a0be6ce33fa21f7187c452cbef7819f91242812ea5"
CANDIDATE_SEAL_SHA256 = "f3df0dc30fe676676ff6e9ded5e10fb5470df493ad55305a46d94620b5e16295"
D_MASTER_SEED = 202609140511
FAMILY_ALPHA_K = 0.0125
BLOCK_ALPHA = 0.004166666666666667
ONE_SIDED_LEVEL = 0.9958333333333333
BOOTSTRAP_BASE = 202609141101
BOOTSTRAP_HARD = 202609141102
BOOTSTRAP_SOFT = 202609141103


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_d_source(root: Path) -> tuple[dict, list[dict]]:
    from jobs.tools.ed4_fresh_decision_source_stage import records

    seal = _read(root / "cohort-seal.json")
    base.need(seal.get("schema") == "jass.ed5.fresh_d_source_seal.v1", "ed5_d_seal_schema")
    base.need(
        seal.get("terminal") == "ED5_FRESH_D_SOURCE_SEALED_V1"
        and seal.get("state") == "completed"
        and seal.get("mode") == "production",
        "ed5_d_seal_state",
    )
    base.need(seal.get("master_seed") == D_MASTER_SEED, "ed5_d_seed")
    base.need(seal.get("reserve_seed_used") is True, "ed5_d_reserve_required")
    exclusion = seal.get("canonical_exclusion") or {}
    base.need(exclusion.get("enabled") is True, "ed5_d_full_exclusion_not_proven")
    base.need(int(exclusion.get("forbidden_identity_count", 0)) > 0, "ed5_d_forbidden_universe_empty")
    base.need(
        seal.get("target_reads") == 0
        and seal.get("candidate_reads") == 0
        and seal.get("control_evaluations") == 0
        and seal.get("fits") == 0
        and seal.get("scan_searches") == 0
        and seal.get("jass_searches") == 0
        and seal.get("alpha_spent") == 0,
        "ed5_d_information_boundary",
    )
    base.need(seal.get("confirmation_target_consumed") is False, "ed5_d_consumed")
    for name in base.D_FILES:
        base.need(base.sha(root / "source" / name) == seal["files"][name], "ed5_d_source_hash")
    records(root / "source" / "parents.jnnw")
    children = records(root / "source" / "children.jnnw")
    groups = base.decision_groups(root / "source")
    base.need(max(r for group in groups for r in group["rows"]) < len(children), "ed5_d_row_bounds")
    return seal, groups


def _verify_barrier(path: Path) -> dict:
    barrier = _read(path)
    base.need(barrier.get("schema") == "jass.ed5.fresh_dws_historical_disjointness.v1", "ed5_barrier_schema")
    base.need(barrier.get("state") == "completed", "ed5_barrier_state")
    base.need(barrier.get("terminal") == "ED5_FRESH_DWS_HISTORICAL_DISJOINTNESS_ESTABLISHED_V1", "ed5_barrier_terminal")
    base.need(barrier.get("pairwise_and_historical_disjoint") is True, "ed5_barrier_not_clear")
    base.need(
        barrier.get("target_reads") == 0
        and barrier.get("candidate_reads") == 0
        and barrier.get("control_evaluations") == 0
        and barrier.get("scan_searches") == 0
        and barrier.get("jass_searches") == 0
        and barrier.get("fits") == 0
        and barrier.get("alpha_spent") == 0,
        "ed5_barrier_information_boundary",
    )
    expected = {"D": D_SOURCE, "W": W_SOURCE, "S": S_SOURCE}
    for role, identity in expected.items():
        observed = barrier.get("sources", {}).get(role, {})
        base.need(
            (observed.get("job_id"), observed.get("attempt_id"), observed.get("code_sha")) == identity,
            f"ed5_barrier_{role.lower()}_identity",
        )
    for overlap in barrier.get("pairwise_overlaps", {}).values():
        base.need(overlap.get("count") == 0, "ed5_pairwise_overlap")
    for role in ("D", "W", "S"):
        for overlap in barrier.get("historical_overlaps", {}).get(role, {}).values():
            base.need(overlap.get("count") == 0, "ed5_historical_overlap")
    return barrier


def authenticate(result: Path, art: Path) -> dict:
    from jobs.tools import ed3_label_pressure as audit
    from jobs.tools.ed2_value_math import read_model

    work = result / "work"
    work.mkdir(parents=True, exist_ok=True)
    roots = {name: result / "inputs" / name for name in ("D", "candidate", "base", "n1", "soft", "scan", "barrier")}
    base.fetch_exact(D_SOURCE, ["cohort-seal.json"] + [f"source/{name}" for name in base.D_FILES], roots["D"], art / "verified-d.json")
    base.fetch_exact(CANDIDATE_SOURCE, [CANDIDATE_NAME, "candidate-seal.json"], roots["candidate"], art / "verified-candidate.json")
    base.fetch_exact(audit.BASE, ["WDL_CONTROL.pjtw.gz"], roots["base"], art / "verified-base.json")
    base.fetch_exact(audit.N1, ["PARTIAL.pjtw", "build-outputs/jass_ed2_value_probe.gz", "scratch-cleanup.json"], roots["n1"], art / "verified-n1.json")
    base.fetch_exact(base.SOFT_SOURCE, ["SOFT.pjtw", "candidate-seal.json"], roots["soft"], art / "verified-soft.json")
    base.fetch_scan(roots["scan"], art / "verified-scan.json")
    base.fetch_exact(DISJOINTNESS_SOURCE, ["scientific-summary.json"], roots["barrier"], art / "verified-disjointness.json")

    d_seal, groups = verify_d_source(roots["D"])
    barrier = _verify_barrier(roots["barrier"] / "scientific-summary.json")

    candidate_seal = _read(roots["candidate"] / "candidate-seal.json")
    base.need(base.sha(roots["candidate"] / "candidate-seal.json") == CANDIDATE_SEAL_SHA256, "ed5_candidate_seal_hash")
    base.need(
        candidate_seal.get("schema") == "jass.ed5.q200k_choice_candidate_seal.v1"
        and candidate_seal.get("mode") == "production"
        and candidate_seal.get("role") == "candidate",
        "ed5_candidate_seal",
    )
    base.need(candidate_seal.get("model_sha256") == CANDIDATE_SHA256, "ed5_candidate_seal_model")
    base.need(base.sha(roots["candidate"] / CANDIDATE_NAME) == CANDIDATE_SHA256, "ed5_candidate_identity")

    base.unzip(roots["base"] / "WDL_CONTROL.pjtw.gz", work / "BASE.pjtw")
    models = {
        "BASE": work / "BASE.pjtw",
        "HARD": roots["n1"] / "PARTIAL.pjtw",
        "SOFT": roots["soft"] / "SOFT.pjtw",
        "CANDIDATE": roots["candidate"] / CANDIDATE_NAME,
    }
    expected = {
        "BASE": audit.MODEL_HASH["BASE"],
        "HARD": audit.MODEL_HASH["PARTIAL"],
        "SOFT": base.SOFT_SHA256,
        "CANDIDATE": CANDIDATE_SHA256,
    }
    base.need({name: base.sha(path) for name, path in models.items()} == expected, "ed5_model_identity")
    base_raw, base_offset, _ = read_model(models["BASE"])
    for model in models.values():
        raw, offset, _ = read_model(model)
        base.need(offset == base_offset and raw[:offset] == base_raw[:base_offset], "ed5_model_pattern_prefix")

    cleanup = _read(roots["n1"] / "scratch-cleanup.json")["retained_binaries"]["jass_ed2_value_probe"]
    archive = roots["n1"] / "build-outputs/jass_ed2_value_probe.gz"
    base.need(base.sha(archive) == cleanup["archive_sha256"], "ed5_probe_archive")
    base.unzip(archive, work / "native-probe")
    base.need(base.sha(work / "native-probe") == cleanup["sha256"], "ed5_probe_identity")
    (work / "native-probe").chmod(0o500)

    scan_root = work / "scan"
    (scan_root / "data").mkdir(parents=True, exist_ok=True)
    base.unzip(roots["scan"] / "scan-home-compiled.gz", scan_root / "scan")
    (scan_root / "scan").chmod(0o500)
    shutil.copyfile(roots["scan"] / "scan-data-eval", scan_root / "data" / "eval")
    shutil.copyfile(roots["scan"] / "scan.ini", scan_root / "scan.ini")
    scan_manifest = _read(roots["scan"] / "scan-build-manifest.json")
    base.need(scan_manifest.get("scan_binary_sha256") == base.SCAN_SHA256 and base.sha(scan_root / "scan") == base.SCAN_SHA256, "ed5_scan_identity")

    source_art = art / "source"
    source_art.mkdir()
    for name in base.D_FILES:
        shutil.copyfile(roots["D"] / "source" / name, source_art / name)
    shutil.copyfile(roots["D"] / "cohort-seal.json", art / "source-cohort-seal.json")

    auth = {
        "schema": "jass.ed5.fresh_d_confirmation_auth.v1",
        "d_source": {"job_id": D_SOURCE[0], "attempt_id": D_SOURCE[1], "code_sha": D_SOURCE[2], "seal_sha256": base.sha(roots["D"] / "cohort-seal.json")},
        "candidate": {"job_id": CANDIDATE_SOURCE[0], "attempt_id": CANDIDATE_SOURCE[1], "code_sha": CANDIDATE_SOURCE[2], "sha256": CANDIDATE_SHA256},
        "disjointness": {"job_id": DISJOINTNESS_SOURCE[0], "attempt_id": DISJOINTNESS_SOURCE[1], "code_sha": DISJOINTNESS_SOURCE[2], "terminal": barrier["terminal"]},
        "models": expected,
        "native_probe_sha256": cleanup["sha256"],
        "scan_sha256": base.SCAN_SHA256,
        "decision_parents": len(groups),
        "node_budget": base.NODE_BUDGET,
        "multiplicity": {"attempt_k": 2, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA, "one_sided_level": ONE_SIDED_LEVEL},
        "bootstrap_seeds": {"BASE": BOOTSTRAP_BASE, "HARD": BOOTSTRAP_HARD, "SOFT_descriptive": BOOTSTRAP_SOFT},
        "source_files": {name: base.sha(source_art / name) for name in base.D_FILES},
        "target_reads": 0,
        "candidate_reads_before_target": 0,
        "control_evaluations_before_target": 0,
        "alpha_spent_before_target": 0,
    }
    atomic_json(art / "cohort-authentication.json", auth)
    return {"groups": groups, "models": models, "probe": work / "native-probe", "scan": scan_root / "scan", "auth": auth, "d_seal": d_seal}


def verify_sealed_source(art: Path) -> dict:
    auth = _read(art / "cohort-authentication.json")
    base.need(auth.get("schema") == "jass.ed5.fresh_d_confirmation_auth.v1", "ed5_auth_schema")
    for name, digest in auth["source_files"].items():
        base.need(base.sha(art / "source" / name) == digest, "ed5_sealed_source_mutation")
    base.need(auth["candidate"]["sha256"] == CANDIDATE_SHA256, "ed5_sealed_candidate_mutation")
    base.need(auth["scan_sha256"] == base.SCAN_SHA256, "ed5_sealed_scan_mutation")
    base.need(auth["disjointness"]["terminal"] == "ED5_FRESH_DWS_HISTORICAL_DISJOINTNESS_ESTABLISHED_V1", "ed5_sealed_barrier_mutation")
    return auth


def statistics(groups: list[dict], high: dict[tuple[int, int], int], scores: dict[str, np.ndarray]) -> tuple[dict, dict[str, list[dict]]]:
    from jobs.tools.ed2_value_math import decision_rows

    rows = {arm: decision_rows(groups, high, cp) for arm, cp in scores.items()}
    base.need(rows["BASE"] == decision_rows(groups, high, scores["BASE"]), "ed5_base_identity_sanity")
    vs_base = base.comparison(rows["BASE"], rows["CANDIDATE"], BOOTSTRAP_BASE)
    vs_hard = base.comparison(rows["HARD"], rows["CANDIDATE"], BOOTSTRAP_HARD)
    vs_soft = base.comparison(rows["SOFT"], rows["CANDIDATE"], BOOTSTRAP_SOFT)
    gates = {
        "regret_beats_base_positive_lower_bound": vs_base["lower"] > 0.0,
        "regret_beats_hard_positive_lower_bound": vs_hard["lower"] > 0.0,
        "top_hit_non_degradation_vs_best_mandatory_control": vs_base["top_hit_delta"] >= 0.0 and vs_hard["top_hit_delta"] >= 0.0,
        "harms_not_more_than_improvements_vs_base": vs_base["harmed"] <= vs_base["improved"],
    }
    aggregates = {
        arm: {
            "regret_mean": float(np.mean([row["regret"] for row in arm_rows])),
            "top_hit": float(np.mean([row["hit"] for row in arm_rows])),
        }
        for arm, arm_rows in rows.items()
    }
    report = {
        "schema": "jass.ed5.fresh_d_confirmation_readout.v1",
        "mode": "production",
        "target_read": True,
        "decision_parents": len(groups),
        "node_budget": base.NODE_BUDGET,
        "multiplicity": {"attempt_k": 2, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA, "one_sided_level": ONE_SIDED_LEVEL},
        "bootstrap_replicates": base.BOOTSTRAPS,
        "bootstrap_seeds": {"BASE": BOOTSTRAP_BASE, "HARD": BOOTSTRAP_HARD, "SOFT_descriptive": BOOTSTRAP_SOFT},
        "aggregates": aggregates,
        "candidate_vs_base": vs_base,
        "candidate_vs_hard": vs_hard,
        "candidate_vs_soft_descriptive": vs_soft,
        "gates": gates,
        "soft_is_descriptive_only": True,
        "scan_is_reference_teacher_not_exact_truth": True,
    }
    return report, rows


def rehearsal_report(d: dict) -> dict:
    return {
        "schema": "jass.ed5.fresh_d_confirmation_readout.v1",
        "mode": "rehearsal",
        "target_read": False,
        "decision_parents": len(d["groups"]),
        "node_budget": base.NODE_BUDGET,
        "multiplicity": {"attempt_k": 2, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA, "one_sided_level": ONE_SIDED_LEVEL},
        "bootstrap_replicates": base.BOOTSTRAPS,
        "bootstrap_seeds": {"BASE": BOOTSTRAP_BASE, "HARD": BOOTSTRAP_HARD, "SOFT_descriptive": BOOTSTRAP_SOFT},
        "gates": None,
        "planned_target_reads": sum(len(group["rows"]) for group in d["groups"]),
        "planned_scan_searches": sum(r not in group["terminals"] for group in d["groups"] for r in group["rows"]),
    }


def normalize_terminal(art: Path, mode: str) -> None:
    path = art / "scientific-summary.json"
    summary = _read(path)
    summary["schema"] = "jass.ed5.fresh_d_confirmation_terminal.v1"
    summary["multiplicity"] = {"attempt_k": 2, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA, "one_sided_level": ONE_SIDED_LEVEL}
    summary["bootstrap_seeds"] = {"BASE": BOOTSTRAP_BASE, "HARD": BOOTSTRAP_HARD, "SOFT_descriptive": BOOTSTRAP_SOFT}
    summary["candidate_sha256"] = CANDIDATE_SHA256
    summary["d_source"] = {"job_id": D_SOURCE[0], "attempt_id": D_SOURCE[1], "code_sha": D_SOURCE[2]}
    summary["disjointness"] = {"job_id": DISJOINTNESS_SOURCE[0], "attempt_id": DISJOINTNESS_SOURCE[1], "code_sha": DISJOINTNESS_SOURCE[2]}
    if mode == "production":
        readout = _read(art / "confirmation-readout.json")
        supported = all(readout.get("gates", {}).values())
        if supported:
            summary["block_verdict"] = "ED5_FRESH_D_CONFIRMATION_SUPPORTED_V1"
            summary["terminal"] = "ED5_FRESH_D_CONFIRMATION_SUPPORTED_V1"
            summary["scientific_verdict"] = "ED5_FRESH_D_CONFIRMATION_SUPPORTED_V1"
            summary["next_stage"] = "RUN_ED5_W_CONFIRMATION"
        else:
            summary["block_verdict"] = "ED5_FRESH_D_CONFIRMATION_NOT_SUPPORTED_V1"
            summary["terminal"] = "CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1"
            summary["scientific_verdict"] = "CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1"
            summary["next_stage"] = "STOP_ED5_K2_SCIENTIFIC_NOT_SUPPORTED"
        summary["alpha_spent"] = BLOCK_ALPHA
        summary["confirmation_target_consumed"] = True
    else:
        summary["block_verdict"] = "ED5_FRESH_D_CONFIRMATION_REHEARSAL_COMPLETE_V1"
        summary["terminal"] = "ED5_FRESH_D_CONFIRMATION_REHEARSAL_COMPLETE_V1"
        summary["scientific_verdict"] = None
        summary["next_stage"] = "RUN_AUTHENTICATED_ED5_D_CONFIRMATION_PRODUCTION"
        summary["alpha_spent"] = 0.0
        summary["confirmation_target_consumed"] = False
    atomic_json(path, summary)


def install() -> None:
    base.D_SOURCE = D_SOURCE
    base.CANDIDATE_SOURCE = CANDIDATE_SOURCE
    base.CANDIDATE_SHA256 = CANDIDATE_SHA256
    base.D_MASTER_SEED = D_MASTER_SEED
    base.FAMILY_ALPHA_K = FAMILY_ALPHA_K
    base.BLOCK_ALPHA = BLOCK_ALPHA
    base.verify_d_source = verify_d_source
    base.authenticate = authenticate
    base.verify_sealed_source = verify_sealed_source
    base.statistics = statistics
    base.rehearsal_report = rehearsal_report
    # base.reference launches Path(base.__file__) as score workers. Point it to
    # this adapter so worker processes install the same immutable ED5 bindings.
    base.__file__ = str(Path(__file__).resolve())
    from jobs.tools import ed4_fresh_d_confirmation_target_host as compat
    compat.install()


def main() -> int:
    install()
    rc = base.main()
    if len(sys.argv) < 2 or sys.argv[1] != "score":
        normalize_terminal(Path(os.environ["JASS_ARTEFACT_DIR"]), os.environ["LAUNCH_MODE"])
    return rc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
