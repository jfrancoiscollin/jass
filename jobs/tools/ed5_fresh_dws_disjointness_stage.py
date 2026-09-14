#!/usr/bin/env python3
"""Read-only ED5 D/W/S plus historical canonical disjointness barrier."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed5_fresh_w_source_stage as util
from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

D = util.D
HISTORICAL = {
    "ED2_P0": {
        "identity": ("cpx62-1875-l3-ed2-data-teacher-preflight-v1", "20260908T171140Z-bc30d685", "bc30d6858c4d590625f8831c4995f055816b95c2"),
        "kind": "ds",
        "digest": None,
    },
    "ED3_CONFIRMATION_1884": {
        "identity": ("cpx62-1884-l3-ed3-confirmation-production-v1", "20260909T051901Z-0946f57d", "0946f57d5443c0507fd9210371396bdf1c49abd2"),
        "kind": "ds",
        "digest": None,
    },
    "ED4_D1937": {
        "identity": ("cpx62-1937-l3-ed4-fresh-d-source-production-v1", "20260913T073800Z-9673030c", "9673030cc00b753d919403a0dc08f14d3f4154a0"),
        "kind": "ds",
        "digest": "6a3194f0ca6d0db95a87d3c01bcce33f6cfb2c35e4b55dd7f43c7568125b3634",
    },
    "ED4_W1959": {
        "identity": ("cpx62-1959-l3-ed4-fresh-w-source-production-v3", "20260914T065838Z-4a610fc0", "4a610fc0976cbb5d016cfbda6d1800b4d65fd8ce"),
        "kind": "w",
        "digest": "25dc7654ff5423fb132d2060f137c077bf4f326a55b26218ef06736178d2361a",
    },
    "ED4_S1949": {
        "identity": ("cpx62-1949-l3-ed4-fresh-s-source-production-v1", "20260913T220903Z-665ed70f", "665ed70ffba9a05dfc964fcac2b44e133604b320"),
        "kind": "ds",
        "digest": "6bee36811ced2b4622169a67a3a2e4c0b6b737ded6633070c1041d0ba96e5615",
    },
}
PHASES = ["authenticate-seals", "recompute-canonical-identities", "prove-current-and-historical-disjointness"]


def identity_from_env(prefix: str) -> tuple[str, str, str]:
    values = tuple(os.environ.get(f"ED5_FRESH_{prefix}_{field}", "").strip() for field in ("JOB", "ATTEMPT", "CODE_SHA"))
    if not all(values) or len(values[2]) != 40:
        raise ValueError(f"{prefix.lower()}_identity_env")
    return values  # type: ignore[return-value]


def verify_receipt(receipt: dict, identity: tuple[str, str, str]) -> None:
    observed = (receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"), receipt.get("result_state"), receipt.get("exit_code"))
    if observed != (identity[0], identity[1], identity[2], "completed", 0):
        raise ValueError("result_identity")


def fetch_ds(root: Path, identity: tuple[str, str, str], *, current_role: str | None = None) -> tuple[dict | None, set[str]]:
    selections = [
        ("artefacts/source/parents.jnnw", "source/parents.jnnw"),
        ("artefacts/source/children.jnnw", "source/children.jnnw"),
    ]
    if current_role:
        selections.insert(0, ("artefacts/cohort-seal.json", "cohort-seal.json"))
    receipt = fetch_files(rclone="rclone", prefix=f"r2:jass-data/runs/{identity[0]}/{identity[1]}", selections=selections, out_dir=root, expected_state="completed")
    verify_receipt(receipt, identity)
    seal = None
    if current_role:
        seal = json.loads((root / "cohort-seal.json").read_text())
        required = {
            "schema": f"jass.ed5.fresh_{current_role.lower()}_source_seal.v1",
            "terminal": f"ED5_FRESH_{current_role}_SOURCE_SEALED_V1",
            "state": "completed",
            "mode": "production",
            "target_reads": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        }
        for key, value in required.items():
            if seal.get(key) != value:
                raise ValueError(f"{current_role.lower()}_seal_{key}")
    values = util.canonical_set(root / "source/parents.jnnw") | util.canonical_set(root / "source/children.jnnw")
    if seal is not None:
        if len(values) != int(seal["unique_canonical_identities"]) or util.digest(values) != seal["canonical_identity_digest"]:
            raise ValueError(f"{current_role.lower()}_canonical_identity")
    return seal, values


def fetch_w(root: Path, identity: tuple[str, str, str], *, current: bool) -> tuple[dict | None, set[str]]:
    selections = [("artefacts/source/positions.jnnw", "source/positions.jnnw")]
    if current:
        selections.insert(0, ("artefacts/cohort-seal.json", "cohort-seal.json"))
    receipt = fetch_files(rclone="rclone", prefix=f"r2:jass-data/runs/{identity[0]}/{identity[1]}", selections=selections, out_dir=root, expected_state="completed")
    verify_receipt(receipt, identity)
    seal = None
    if current:
        seal = json.loads((root / "cohort-seal.json").read_text())
        required = {
            "schema": "jass.ed5.fresh_w_source_seal.v1",
            "terminal": "ED5_FRESH_W_SOURCE_SEALED_V1",
            "state": "completed",
            "mode": "production",
            "positions": 8192,
            "opening_groups": 512,
            "game_groups": 1024,
            "rows_per_game": 8,
            "cluster_unit": "opening_id",
            "target_reads": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        }
        for key, value in required.items():
            if seal.get(key) != value:
                raise ValueError(f"w_seal_{key}")
    values = util.canonical_set(root / "source/positions.jnnw")
    if seal is not None:
        if len(values) != int(seal["unique_canonical_identities"]) or util.digest(values) != seal["canonical_identity_digest"]:
            raise ValueError("w_canonical_identity")
    return seal, values


def overlap_entry(values: set[str]) -> dict:
    return {"count": len(values), "digest": util.digest(values)}


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(art, mode)
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        w_identity = identity_from_env("W")
        s_identity = identity_from_env("S")

        ev.begin(PHASES[0])
        roots = {name: result / "inputs" / name for name in ("D", "W", "S")}
        d_seal, d_ids = fetch_ds(roots["D"], D, current_role="D")
        w_seal, w_ids = fetch_w(roots["W"], w_identity, current=True)
        s_seal, s_ids = fetch_ds(roots["S"], s_identity, current_role="S")
        ev.complete()

        ev.begin(PHASES[1])
        historical: dict[str, set[str]] = {}
        for name, descriptor in HISTORICAL.items():
            root = result / "inputs" / "historical" / name
            identity = descriptor["identity"]
            if descriptor["kind"] == "w":
                _, values = fetch_w(root, identity, current=False)
            else:
                _, values = fetch_ds(root, identity, current_role=None)
            expected_digest = descriptor["digest"]
            if expected_digest is not None and util.digest(values) != expected_digest:
                raise ValueError(f"historical_digest_{name}")
            historical[name] = values
        ev.complete()

        ev.begin(PHASES[2])
        pairwise_sets = {"D_W": d_ids & w_ids, "D_S": d_ids & s_ids, "W_S": w_ids & s_ids}
        historical_report: dict[str, dict[str, dict]] = {}
        all_clear = all(not values for values in pairwise_sets.values())
        for role, current in (("D", d_ids), ("W", w_ids), ("S", s_ids)):
            historical_report[role] = {}
            for name, old in historical.items():
                overlap = current & old
                historical_report[role][name] = overlap_entry(overlap)
                all_clear = all_clear and not overlap

        terminal = "ED5_FRESH_DWS_HISTORICAL_DISJOINTNESS_ESTABLISHED_V1" if all_clear else "ED5_FRESH_DWS_HISTORICAL_COLLISION_TECHNICAL_FAILURE_V1"
        summary = {
            "schema": "jass.ed5.fresh_dws_historical_disjointness.v1",
            "state": "completed" if all_clear else "failed",
            "terminal": terminal,
            "mode": mode,
            "sources": {
                "D": {"job_id": D[0], "attempt_id": D[1], "code_sha": D[2], "seed": d_seal["master_seed"], "digest": util.digest(d_ids)},
                "W": {"job_id": w_identity[0], "attempt_id": w_identity[1], "code_sha": w_identity[2], "seed": w_seal["master_seed"], "digest": util.digest(w_ids)},
                "S": {"job_id": s_identity[0], "attempt_id": s_identity[1], "code_sha": s_identity[2], "seed": s_seal["master_seed"], "digest": util.digest(s_ids)},
            },
            "counts": {"D": len(d_ids), "W": len(w_ids), "S": len(s_ids)},
            "pairwise_overlaps": {key: overlap_entry(values) for key, values in pairwise_sets.items()},
            "historical_overlaps": historical_report,
            "historical_sources": {name: {"job_id": d["identity"][0], "attempt_id": d["identity"][1], "code_sha": d["identity"][2], "digest": util.digest(historical[name])} for name, d in HISTORICAL.items()},
            "pairwise_and_historical_disjoint": all_clear,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "next_stage": "RUN_ED5_D_CONFIRMATION" if all_clear else "PRE_TARGET_COLLISION_RECOVERY_ONLY",
        }
        atomic_json(art / "dws-historical-disjointness.json", summary)
        atomic_json(art / "scientific-summary.json", summary)
        if not all_clear:
            raise ValueError("current_or_historical_canonical_collision")
        ev.complete()
        ev.finish()
        return 0
    except Exception as exc:
        ev.fail(exc)
        if not (art / "scientific-summary.json").exists():
            atomic_json(art / "scientific-summary.json", {
                "schema": "jass.ed5.fresh_dws_historical_disjointness_failure.v1",
                "state": "failed",
                "terminal": "ED5_FRESH_DWS_HISTORICAL_DISJOINTNESS_TECHNICAL_FAILURE_V1",
                "error_type": type(exc).__name__,
                "target_reads": 0,
                "candidate_reads": 0,
                "control_evaluations": 0,
                "scan_searches": 0,
                "jass_searches": 0,
                "fits": 0,
                "alpha_spent": 0,
                "confirmation_target_consumed": False,
            })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
