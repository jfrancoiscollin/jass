#!/usr/bin/env python3
"""ED5 D reserve-source repair after authenticated pre-target historical collision.

1986 authenticated that the original D1976 primary source (seed 202609140501)
intersected ED3_CONFIRMATION_1884 by 12 canonical identities while all target,
candidate/control, search, fit and alpha counters remained zero. This stage uses
only the preregistered D reserve seed 202609140511 and the existing C++ source
generator exclusions input. It excludes the complete authenticated historical
confirmation universe plus repaired W1988 and unchanged S1984 before source
selection. No target/result bytes are read and no scientific gate changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_decision_source_stage as base
from jobs.tools import ed5_fresh_decision_source_stage as parent
from jobs.tools import ed5_fresh_dws_disjointness_stage as barrier
from jobs.tools import ed5_fresh_w_source_stage as util
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

W1988 = (
    "cpx62-1988-l3-ed5-fresh-w-source-production-v5",
    "20260915T130012Z-da8aa733",
    "da8aa7334f2873ca17ca353b3df2fa4f4a562d47",
)
W1988_DIGEST = "15391429f5b16c4840cb1baed07a314aed244d1e9d9670a25e24fa49c9dd3dcd"
W1988_UNIQUE = 7977
S1984 = (
    "cpx62-1984-l3-ed5-fresh-s-source-production-v2",
    "20260915T084337Z-9e8eb2a3",
    "9e8eb2a32d80f15491ef1ff6bb5aa3b95edcdc49",
)
S1984_DIGEST = "90a84f2452a67722fd7514737a2b382ef20b992050b0c1ee6ce3c5464e9c983d"
S1984_UNIQUE = 8208
HISTORICAL_DIGESTS = {
    "ED2_P0": "cdeb5ceb5232f560addaed3202112084c9985078a4dd582e246cfdb6ca35c9ec",
    "ED3_CONFIRMATION_1884": "15a64da084b98f314c27d2f5487a689b109d7f378f9a461b3ad7a3ebc5a26463",
    "ED4_D1937": "6a3194f0ca6d0db95a87d3c01bcce33f6cfb2c35e4b55dd7f43c7568125b3634",
    "ED4_W1959": "25dc7654ff5423fb132d2060f137c077bf4f326a55b26218ef06736178d2361a",
    "ED4_S1949": "6bee36811ced2b4622169a67a3a2e4c0b6b737ded6633070c1041d0ba96e5615",
}
PRIMARY_DIAGNOSIS = {
    "source": "ED3_CONFIRMATION_1884",
    "count": 12,
    "digest": "b2ee650ab4b82c501a7116c236d8e64f70ca628639986a2f5fd4d4d83cbfc863",
}
REQUIRED_FORBIDDEN_SOURCES = (
    "ED5_W1988",
    "ED5_S1984",
    "ED2_P0",
    "ED3_CONFIRMATION_1884",
    "ED4_D1937",
    "ED4_W1959",
    "ED4_S1949",
)


def _verify(name: str, values: set[str], digest: str, unique: int | None = None) -> None:
    if util.digest(values) != digest:
        raise ValueError(f"d_reserve_authenticated_digest_{name}")
    if unique is not None and len(values) != unique:
        raise ValueError(f"d_reserve_authenticated_count_{name}")


def build_forbidden_universe(source_sets: dict[str, set[str]]) -> set[str]:
    missing = [name for name in REQUIRED_FORBIDDEN_SOURCES if name not in source_sets]
    if missing:
        raise ValueError("d_reserve_forbidden_sources_missing:" + ",".join(missing))
    empty = [name for name in REQUIRED_FORBIDDEN_SOURCES if not source_sets[name]]
    if empty:
        raise ValueError("d_reserve_forbidden_sources_empty:" + ",".join(empty))
    forbidden: set[str] = set()
    for name in REQUIRED_FORBIDDEN_SOURCES:
        forbidden |= source_sets[name]
    if not forbidden:
        raise ValueError("d_reserve_forbidden_universe_empty")
    return forbidden


def assert_disjoint(values: set[str], forbidden: set[str]) -> None:
    overlap = values & forbidden
    if overlap:
        raise ValueError("d_reserve_canonical_collision_with_forbidden_universe")


def fetch_forbidden(result: Path) -> tuple[set[str], dict[str, dict[str, object]]]:
    sources: dict[str, set[str]] = {}

    _, w_values = barrier.fetch_w(result / "inputs" / "ED5_W1988", W1988, current=True)
    _verify("ED5_W1988", w_values, W1988_DIGEST, W1988_UNIQUE)
    sources["ED5_W1988"] = w_values

    _, s_values = barrier.fetch_ds(result / "inputs" / "ED5_S1984", S1984, current_role="S")
    _verify("ED5_S1984", s_values, S1984_DIGEST, S1984_UNIQUE)
    sources["ED5_S1984"] = s_values

    for name, descriptor in barrier.HISTORICAL.items():
        root = result / "inputs" / "historical" / name
        identity = descriptor["identity"]
        if descriptor["kind"] == "w":
            _, values = barrier.fetch_w(root, identity, current=False)
        else:
            _, values = barrier.fetch_ds(root, identity, current_role=None)
        _verify(name, values, HISTORICAL_DIGESTS[name])
        sources[name] = values

    forbidden = build_forbidden_universe(sources)
    detail = {
        name: {"count": len(values), "digest": util.digest(values)}
        for name, values in sources.items()
    }
    return forbidden, detail


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(art, mode)
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        requested = int(os.environ.get("ED5_FRESH_D_MASTER_SEED", str(parent.RESERVE)))
        if requested != parent.RESERVE:
            raise ValueError("d_repair_requires_preregistered_reserve_seed")
        parent.validate_seed(requested)

        ev.begin("authenticate-forbidden-universe")
        forbidden, forbidden_sources = fetch_forbidden(result)
        ev.complete()

        ev.begin("build-seeded-source")
        work = result / "work"
        src = work / "src"
        build = work / "build"
        source = art / "source"
        work.mkdir(parents=True, exist_ok=True)
        with (work / "repo.tar").open("wb") as stream:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=stream, check=True)
        src.mkdir()
        subprocess.run(["tar", "-xf", str(work / "repo.tar"), "-C", str(src)], check=True)
        with (src / "CMakeLists.txt").open("a") as handle:
            handle.write("\nadd_executable(jass_ed5_fresh_source jobs/tools/ed4_fresh_source.cpp)\n")
            handle.write("target_link_libraries(jass_ed5_fresh_source PRIVATE jass_lib)\n")
        subprocess.run([
            "cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
            "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
            "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
        ], check=True, timeout=180)
        subprocess.run(["cmake", "--build", str(build), "-j2", "--target", "jass_ed5_fresh_source"], check=True, timeout=180)
        binary = build / "jass_ed5_fresh_source"
        ev.complete()

        ev.begin("generate-score-free-source")
        exclusions = work / "exclusions.txt"
        exclusions.write_text("\n".join(sorted(forbidden)) + "\n")
        generator_mode = "production" if mode == "production" else "smoke"
        subprocess.run([str(binary), str(exclusions), str(source), generator_mode, str(parent.RESERVE)], check=True, timeout=240)
        ev.complete()

        ev.begin("validate-and-seal")
        validated = base.validate(source, mode, parent.RESERVE)
        generated = set()
        for path in (source / "parents.jnnw", source / "children.jnnw"):
            generated |= {base.canon(record) for record in base.records(path)}
        assert_disjoint(generated, forbidden)
        meta = json.loads((source / "source.json").read_text())
        if int(meta.get("excluded_identities", -1)) != len(forbidden):
            raise ValueError("d_reserve_exclusion_count")

        seal = {
            "schema": "jass.ed5.fresh_d_source_seal.v1",
            "state": "completed",
            "terminal": "ED5_FRESH_D_SOURCE_SEALED_V1",
            "mode": mode,
            "parent_preregistered_seed": parent.MASTER,
            "master_seed": parent.RESERVE,
            "reserve_seed_used": True,
            "reserve_reason": "PRIMARY_D_CANONICAL_COLLISION_WITH_HISTORICAL_PRE_TARGET",
            "pre_target_primary_historical_collision": dict(PRIMARY_DIAGNOSIS),
            "canonical_exclusion": {
                "enabled": True,
                "forbidden_identity_count": len(forbidden),
                "forbidden_sources": forbidden_sources,
                "selection_repair": "existing_cpp_exclusions_before_preregistered_reserve_selection",
            },
            "generator_sha256": base.sha(binary),
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "created_at_unix": int(time.time()),
            "files": {name: base.sha(source / name) for name in parent.FILES},
            **validated,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "automatic_target_scoring": False,
            "next_stage": "RERUN_ED5_DWS_HISTORICAL_DISJOINTNESS",
        }
        atomic_json(art / "cohort-seal.json", seal)
        atomic_json(art / "scientific-summary.json", seal)
        atomic_json(art / "reserve-disjoint-filter.json", {
            "schema": "jass.ed5.d_reserve_disjoint_filter.v1",
            "classification": "TECHNICAL_SOURCE_RECOVERY",
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "seed": parent.RESERVE,
            "primary_collision": dict(PRIMARY_DIAGNOSIS),
            "forbidden_identity_count": len(forbidden),
            "forbidden_sources": forbidden_sources,
        })
        ev.complete()
        ev.finish()
        return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art / "scientific-summary.json", {
            "schema": "jass.ed5.fresh_d_source_failure.v1",
            "state": "failed",
            "terminal": "ED5_FRESH_D_SOURCE_TECHNICAL_FAILURE_V1",
            "error_type": type(exc).__name__,
            "scientific_verdict": None,
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
