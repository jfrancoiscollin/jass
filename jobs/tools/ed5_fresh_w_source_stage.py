#!/usr/bin/env python3
"""ED5 fresh W score-free source with preregistered collision-only reserve fallback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_w_source_stage as base
from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PRIMARY = 202609140502
RESERVE = 202609140512
ED4_SIZING_SEED = 202609120402
D = (
    "cpx62-1976-l3-ed5-fresh-d-source-production-v1",
    "20260914T204738Z-955314d0",
    "955314d0db9e1399f12dc5f5f6b7897a3bacd33e",
)
D_DIGEST = "8a94d101a1a439e710d9dfefbc3cb0f17cc78deee0c5905d20ac0d29b4c1bf71"
D_UNIQUE = 8022
JNNW_REC = 38
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical_set(path: Path) -> set[str]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("jnnw_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * JNNW_REC:
        raise ValueError("jnnw_size")
    values: set[str] = set()
    for index in range(count):
        record = raw[8 + index * JNNW_REC:8 + (index + 1) * JNNW_REC]
        if record[33:38] != b"\0" * 5:
            raise ValueError("target_bytes_nonzero")
        values.add(base.canonical_position(record))
    return values


def digest(values: set[str]) -> str:
    if not values:
        return EMPTY_DIGEST
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def fetch_d(result: Path) -> set[str]:
    root = result / "ed5-w-d-source"
    receipt = fetch_files(
        rclone="rclone",
        prefix=f"r2:jass-data/runs/{D[0]}/{D[1]}",
        selections=[
            ("artefacts/cohort-seal.json", "cohort-seal.json"),
            ("artefacts/source/parents.jnnw", "source/parents.jnnw"),
            ("artefacts/source/children.jnnw", "source/children.jnnw"),
        ],
        out_dir=root,
        expected_state="completed",
    )
    observed = (receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"), receipt.get("result_state"), receipt.get("exit_code"))
    if observed != (D[0], D[1], D[2], "completed", 0):
        raise ValueError("d_result_identity")
    seal = json.loads((root / "cohort-seal.json").read_text())
    required = {
        "schema": "jass.ed5.fresh_d_source_seal.v1",
        "terminal": "ED5_FRESH_D_SOURCE_SEALED_V1",
        "state": "completed",
        "mode": "production",
        "master_seed": 202609140501,
        "target_reads": 0,
        "scan_searches": 0,
        "jass_searches": 0,
        "fits": 0,
        "alpha_spent": 0,
        "confirmation_target_consumed": False,
    }
    for key, value in required.items():
        if seal.get(key) != value:
            raise ValueError(f"d_seal_{key}")
    values = canonical_set(root / "source/parents.jnnw") | canonical_set(root / "source/children.jnnw")
    if len(values) != D_UNIQUE or digest(values) != D_DIGEST:
        raise ValueError("d_canonical_identity")
    return values


def configure_base(seed: int, record_budget: int) -> None:
    original_derive = getattr(configure_base, "original_derive", None)
    if original_derive is None:
        original_derive = base.derive_plan
        setattr(configure_base, "original_derive", original_derive)

        def derive_ed5(report: dict) -> dict:
            saved = base.SEED
            base.SEED = ED4_SIZING_SEED
            try:
                return original_derive(report)
            finally:
                base.SEED = saved
        base.derive_plan = derive_ed5

    base.SEED = seed
    base.RESERVE_SEED = RESERVE
    base.REHEARSAL_OPENINGS = base.PRODUCTION_OPENINGS
    base.REHEARSAL_POSITIONS = base.PRODUCTION_POSITIONS
    base.REHEARSAL_RECORD_BUDGET = record_budget

    original_run = getattr(configure_base, "original_run", None)
    if original_run is None:
        original_run = base.subprocess.run
        setattr(configure_base, "original_run", original_run)

        def run_with_full_timeout(*args, **kwargs):
            command = args[0] if args else kwargs.get("args")
            if isinstance(command, (list, tuple)) and "--gen-data-wdl" in command and kwargs.get("timeout") == 900:
                kwargs = dict(kwargs)
                kwargs["timeout"] = 2100
            return original_run(*args, **kwargs)
        base.subprocess.run = run_with_full_timeout


def run_attempt(seed: int, budget: int, root: Path) -> tuple[int, int]:
    configure_base(seed, budget)
    root.mkdir(parents=True)
    previous_art = os.environ["JASS_ARTEFACT_DIR"]
    previous_budget = os.environ.get("ED4_FRESH_W_RECORD_BUDGET")
    os.environ["JASS_ARTEFACT_DIR"] = str(root)
    os.environ["ED4_FRESH_W_RECORD_BUDGET"] = str(budget)
    try:
        rc = base.main()
    finally:
        os.environ["JASS_ARTEFACT_DIR"] = previous_art
        if previous_budget is None:
            os.environ.pop("ED4_FRESH_W_RECORD_BUDGET", None)
        else:
            os.environ["ED4_FRESH_W_RECORD_BUDGET"] = previous_budget
    effects = 0
    evidence = root / "execution-evidence.json"
    if evidence.exists():
        effects = int(json.loads(evidence.read_text()).get("actual_side_effects", {}).get("selfplay_games", 0))
    return rc, effects


def generate_seed(seed: int, work: Path) -> tuple[Path, int]:
    total_effects = 0
    for budget in base.PRODUCTION_RECORD_BUDGETS:
        root = work / f"seed-{seed}-budget-{budget}"
        rc, effects = run_attempt(seed, budget, root)
        total_effects += effects
        if rc == 0:
            return root, total_effects
        support = root / "support-report.json"
        if not support.exists():
            raise ValueError("w_generation_technical_failure")
        report = json.loads(support.read_text())
        if report.get("terminal") != "ED4_FRESH_W_SOURCE_COMPLETION_REQUIRED_V1" or report.get("next_record_budget") is None:
            raise ValueError("w_source_support_insufficient")
    raise ValueError("w_source_ladder_exhausted")


def promote_ed5(root: Path, *, seed: int, reserve_used: bool, overlap: set[str], extra_selfplay: int) -> None:
    source_json = root / "source/source.json"
    meta = json.loads(source_json.read_text())
    meta.update({
        "schema": "jass.ed5.fresh_w_source.v1",
        "parent_preregistered_seed": PRIMARY,
        "master_seed": seed,
        "reserve_seed": RESERVE,
        "reserve_seed_used": reserve_used,
        "reserve_reason": "PRIMARY_W_CANONICAL_COLLISION_WITH_ED5_D_PRE_TARGET" if reserve_used else None,
        "pre_target_d_collision": {"count": len(overlap), "digest": digest(overlap)},
        "scan_searches": 0,
        "jass_searches": 0,
        "target_reads": 0,
        "fits": 0,
        "alpha_spent": 0,
        "confirmation_target_consumed": False,
    })
    atomic_json(source_json, meta)

    seal_path = root / "cohort-seal.json"
    seal = json.loads(seal_path.read_text())
    seal.update({
        "schema": "jass.ed5.fresh_w_source_seal.v1",
        "terminal": "ED5_FRESH_W_SOURCE_SEALED_V1",
        "parent_preregistered_seed": PRIMARY,
        "master_seed": seed,
        "reserve_seed_used": reserve_used,
        "reserve_reason": "PRIMARY_W_CANONICAL_COLLISION_WITH_ED5_D_PRE_TARGET" if reserve_used else None,
        "pre_target_d_collision": {"count": len(overlap), "digest": digest(overlap)},
        "scan_searches": 0,
        "jass_searches": 0,
        "target_reads": 0,
        "fits": 0,
        "alpha_spent": 0,
        "confirmation_target_consumed": False,
        "next_stage": "GENERATE_AND_SEAL_ED5_S_SOURCE",
    })
    seal["files"]["source.json"] = sha(source_json)
    atomic_json(seal_path, seal)
    atomic_json(root / "scientific-summary.json", seal)

    evidence_path = root / "execution-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["actual_side_effects"]["selfplay_games"] = int(evidence["actual_side_effects"].get("selfplay_games", 0)) + extra_selfplay
    atomic_json(evidence_path, evidence)


def copy_outputs(source: Path, dest: Path) -> None:
    for child in source.iterdir():
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        d_ids = fetch_d(result)
        work = Path(tempfile.mkdtemp(prefix="ed5-w-source-", dir=str(result)))
        try:
            primary_root, primary_effects = generate_seed(PRIMARY, work)
            primary_ids = canonical_set(primary_root / "source/positions.jnnw")
            primary_overlap = primary_ids & d_ids
            if primary_overlap:
                selected_root, reserve_effects = generate_seed(RESERVE, work)
                selected_ids = canonical_set(selected_root / "source/positions.jnnw")
                reserve_overlap = selected_ids & d_ids
                if reserve_overlap:
                    raise ValueError("w_reserve_canonical_collision_with_d")
                promote_ed5(selected_root, seed=RESERVE, reserve_used=True, overlap=primary_overlap, extra_selfplay=primary_effects)
            else:
                selected_root = primary_root
                reserve_effects = 0
                promote_ed5(selected_root, seed=PRIMARY, reserve_used=False, overlap=primary_overlap, extra_selfplay=0)
            copy_outputs(selected_root, art)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return 0
    except Exception as exc:
        if not (art / "execution-evidence.json").exists():
            ev = StageEvidence(art, mode)
            ev.fail(exc)
        atomic_json(art / "scientific-summary.json", {
            "schema": "jass.ed5.fresh_w_source_failure.v1",
            "state": "failed",
            "terminal": "ED5_FRESH_W_SOURCE_TECHNICAL_FAILURE_V1",
            "error_type": type(exc).__name__,
            "target_reads": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
