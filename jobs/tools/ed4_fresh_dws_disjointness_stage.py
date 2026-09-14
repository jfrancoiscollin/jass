#!/usr/bin/env python3
"""Authenticate ED4-FRESH D/W/S canonical disjointness before any target read."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
from jobs.tools.ed4_fresh_w_source_stage import canonical_position

D = (
    "cpx62-1937-l3-ed4-fresh-d-source-production-v1",
    "20260913T073800Z-9673030c",
    "9673030cc00b753d919403a0dc08f14d3f4154a0",
)
S = (
    "cpx62-1949-l3-ed4-fresh-s-source-production-v1",
    "20260913T220903Z-665ed70f",
    "665ed70ffba9a05dfc964fcac2b44e133604b320",
)
PHASES = ["authenticate-seals", "recompute-canonical-identities", "prove-pairwise-disjointness"]
JNNW_REC = 38


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_set(path: Path) -> set[str]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("jnnw_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * JNNW_REC:
        raise ValueError("jnnw_size")
    result: set[str] = set()
    for i in range(count):
        rec = raw[8 + i * JNNW_REC:8 + (i + 1) * JNNW_REC]
        if rec[33:38] != b"\0" * 5:
            raise ValueError("target_bytes_nonzero")
        result.add(canonical_position(rec))
    return result


def digest_identities(values: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def overlap_digest(values: set[str]) -> str:
    if not values:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode()).hexdigest()


def verify_result(receipt: dict, identity: tuple[str, str, str]) -> None:
    job, attempt, code = identity
    observed = (
        receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"),
        receipt.get("result_state"), receipt.get("exit_code"),
    )
    if observed != (job, attempt, code, "completed", 0):
        raise ValueError("result_identity")


def verify_ds_seal(root: Path, role: str, identity: tuple[str, str, str]) -> tuple[dict, set[str]]:
    seal = read_json(root / "cohort-seal.json")
    expected_schema = f"jass.ed4.fresh_{role.lower()}_source_seal.v1"
    expected_terminal = f"ED4_FRESH_{role}_SOURCE_SEALED_V1"
    if seal.get("schema") != expected_schema or seal.get("terminal") != expected_terminal:
        raise ValueError(f"{role.lower()}_seal_schema")
    if seal.get("state") != "completed" or seal.get("mode") != "production":
        raise ValueError(f"{role.lower()}_seal_state")
    if any(seal.get(k) != 0 for k in ("target_reads", "fits", "scan_searches", "jass_searches", "alpha_spent")):
        raise ValueError(f"{role.lower()}_information_boundary")
    if seal.get("confirmation_target_consumed") is not False:
        raise ValueError(f"{role.lower()}_consumed")
    for name in ("parents.jnnw", "children.jnnw"):
        if sha(root / "source" / name) != seal["files"][name]:
            raise ValueError(f"{role.lower()}_file_hash")
    identities = canonical_set(root / "source/parents.jnnw") | canonical_set(root / "source/children.jnnw")
    if len(identities) != int(seal["unique_canonical_identities"]):
        raise ValueError(f"{role.lower()}_unique_count")
    if digest_identities(identities) != seal["canonical_identity_digest"]:
        raise ValueError(f"{role.lower()}_identity_digest")
    return seal, identities


def verify_w_seal(root: Path) -> tuple[dict, set[str]]:
    seal = read_json(root / "cohort-seal.json")
    if seal.get("schema") != "jass.ed4.fresh_w_source_seal.v1" or seal.get("terminal") != "ED4_FRESH_W_SOURCE_SEALED_V1":
        raise ValueError("w_seal_schema")
    required = {
        "state": "completed", "mode": "production", "positions": 8192,
        "opening_groups": 512, "game_groups": 1024, "rows_per_game": 8,
        "cluster_unit": "opening_id", "target_reads": 0, "candidate_reads": 0,
        "control_evaluations": 0, "fits": 0, "alpha_spent": 0,
        "confirmation_target_consumed": False, "raw_wdl_parsed": False,
        "raw_game_result_parsed": False, "target_bytes_zeroed": True,
    }
    for key, value in required.items():
        if seal.get(key) != value:
            raise ValueError(f"w_{key}")
    positions = root / "source/positions.jnnw"
    if sha(positions) != seal["files"]["positions.jnnw"]:
        raise ValueError("w_file_hash")
    identities = canonical_set(positions)
    if len(identities) != int(seal["unique_canonical_identities"]):
        raise ValueError("w_unique_count")
    if digest_identities(identities) != seal["canonical_identity_digest"]:
        raise ValueError("w_identity_digest")
    return seal, identities


def pairwise_report(d: set[str], w: set[str], s: set[str]) -> dict:
    overlaps = {"D_W": d & w, "D_S": d & s, "W_S": w & s}
    return {
        "counts": {"D": len(d), "W": len(w), "S": len(s)},
        "overlaps": {
            key: {"count": len(values), "digest": overlap_digest(values)}
            for key, values in overlaps.items()
        },
        "pairwise_disjoint": all(not values for values in overlaps.values()),
    }


def w_identity_from_env() -> tuple[str, str, str]:
    values = tuple(os.environ.get(key, "").strip() for key in (
        "ED4_FRESH_W_JOB", "ED4_FRESH_W_ATTEMPT", "ED4_FRESH_W_CODE_SHA"))
    if not all(values) or len(values[2]) != 40:
        raise ValueError("w_identity_env")
    return values  # type: ignore[return-value]


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(art, mode)
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        w_identity = w_identity_from_env()
        ev.begin(PHASES[0])
        roots = {name: result / "inputs" / name for name in ("D", "W", "S")}
        ds_files = ["cohort-seal.json", "source/parents.jnnw", "source/children.jnnw"]
        for role, identity in (("D", D), ("S", S)):
            receipt = fetch_files(
                rclone="rclone", prefix=f"r2:jass-data/runs/{identity[0]}/{identity[1]}",
                selections=[(f"artefacts/{path}", path) for path in ds_files],
                out_dir=roots[role], expected_state="completed")
            verify_result(receipt, identity)
        w_files = ["cohort-seal.json", "source/positions.jnnw"]
        w_receipt = fetch_files(
            rclone="rclone", prefix=f"r2:jass-data/runs/{w_identity[0]}/{w_identity[1]}",
            selections=[(f"artefacts/{path}", path) for path in w_files],
            out_dir=roots["W"], expected_state="completed")
        verify_result(w_receipt, w_identity)
        ev.complete()

        ev.begin(PHASES[1])
        d_seal, d_ids = verify_ds_seal(roots["D"], "D", D)
        w_seal, w_ids = verify_w_seal(roots["W"])
        s_seal, s_ids = verify_ds_seal(roots["S"], "S", S)
        ev.complete()

        ev.begin(PHASES[2])
        pairwise = pairwise_report(d_ids, w_ids, s_ids)
        verdict = "ED4_FRESH_DWS_DISJOINTNESS_ESTABLISHED_V1" if pairwise["pairwise_disjoint"] else "ED4_FRESH_DWS_COLLISION_TECHNICAL_FAILURE_V1"
        summary = {
            "schema": "jass.ed4.fresh_dws_disjointness.v1",
            "state": "completed" if pairwise["pairwise_disjoint"] else "failed",
            "terminal": verdict,
            "mode": mode,
            "sources": {
                "D": {"job_id": D[0], "attempt_id": D[1], "code_sha": D[2], "seed": d_seal["master_seed"], "seal_digest": sha(roots["D"] / "cohort-seal.json")},
                "W": {"job_id": w_identity[0], "attempt_id": w_identity[1], "code_sha": w_identity[2], "seed": w_seal["master_seed"], "seal_digest": sha(roots["W"] / "cohort-seal.json")},
                "S": {"job_id": S[0], "attempt_id": S[1], "code_sha": S[2], "seed": s_seal["master_seed"], "seal_digest": sha(roots["S"] / "cohort-seal.json")},
            },
            **pairwise,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "next_stage": "RUN_ED4_FRESH_CONFIRMATION_TARGETS" if pairwise["pairwise_disjoint"] else "PRE_TARGET_COLLISION_RECOVERY_ONLY",
        }
        atomic_json(art / "dws-disjointness.json", summary)
        atomic_json(art / "scientific-summary.json", summary)
        if not pairwise["pairwise_disjoint"]:
            raise ValueError("dws_canonical_collision")
        ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc)
        if not (art / "scientific-summary.json").exists():
            atomic_json(art / "scientific-summary.json", {
                "schema": "jass.ed4.fresh_dws_disjointness_failure.v1",
                "state": "failed", "terminal": "ED4_FRESH_DWS_DISJOINTNESS_TECHNICAL_FAILURE_V1",
                "error_type": type(exc).__name__, "target_reads": 0, "candidate_reads": 0,
                "control_evaluations": 0, "fits": 0, "alpha_spent": 0,
                "confirmation_target_consumed": False,
            })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
