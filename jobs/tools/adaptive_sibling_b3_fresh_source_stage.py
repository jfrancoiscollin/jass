#!/usr/bin/env python3
"""Generate and seal the first preregistered fresh B3 parent cohort.

The stage reuses the audited B2 target-blind source/filter/selection pipeline via
the B3 runtime adapter. It may generate fresh parent positions only after the
preregistration commit and exact 1835 exclusion identities are authenticated.
No teacher search, fit, game, promotion or bake is reachable from this stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_source_publish as publisher  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_source_runtime as runtime_adapter  # noqa: E402
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_json_bytes  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_fresh_source_stage.v1"
PREREG_SCHEMA = "jass.b3_fresh_corpus_preregistration.v1"
SUCCESS_VERDICT = "B3_FRESH_SOURCE_SELECTION_SEALED_V1"
SUPPORT_VERDICT = "B3_FRESH_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1"
CONFIG_BEGIN = "B3_FRESH_CORPUS_CONFIG_V1_BEGIN\n"
CONFIG_END = "B3_FRESH_CORPUS_CONFIG_V1_END\n"

PINNED_IMPLEMENTATION_PATHS = (
    "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json",
    "jobs/tools/adaptive_sibling_b2_select.py",
    "jobs/tools/adaptive_sibling_b2_source_launcher.py",
    "jobs/tools/adaptive_sibling_b2_source_publish.py",
    "jobs/tools/adaptive_sibling_b3_fresh_source_runtime.py",
    "jobs/tools/adaptive_sibling_b3_fresh_source_stage.py",
    "jobs/tools/fetch_result_files.py",
)


class StageError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise StageError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise StageError(f"refusing existing temporary {tmp}")
    try:
        tmp.write_bytes(raw)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def git_bytes(*args: str) -> bytes:
    completed = subprocess.run(["/usr/bin/git", *args], cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=False, timeout=60)
    if completed.returncode != 0:
        raise StageError(
            f"git {' '.join(args)} failed: {completed.stderr.decode(errors='replace')[-2000:]}"
        )
    return completed.stdout


def git_ancestor(ancestor: str, descendant: str) -> None:
    completed = subprocess.run(["/usr/bin/git", "merge-base", "--is-ancestor", ancestor, descendant],
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=False, timeout=30)
    if completed.returncode != 0:
        raise StageError(f"{ancestor} is not an ancestor of {descendant}")


def authenticate_provenance(implementation: str, preregistration: str,
                            prereg_path: str, prereg_sha: str) -> tuple[bytes, str]:
    if len(implementation) != 40 or len(preregistration) != 40:
        raise StageError("implementation/preregistration commits must be 40-hex")
    head = git_bytes("rev-parse", "HEAD").decode("ascii").strip()
    git_ancestor(implementation, preregistration)
    git_ancestor(preregistration, head)

    changed = git_bytes("diff", "--name-only", implementation, preregistration).decode("utf-8").splitlines()
    if changed != [prereg_path]:
        raise StageError(f"preregistration commit must change only {prereg_path}; got {changed}")
    for rel in PINNED_IMPLEMENTATION_PATHS:
        frozen = git_bytes("show", f"{implementation}:{rel}")
        current = (ROOT / rel).read_bytes()
        if current != frozen:
            raise StageError(f"implementation path drift after X: {rel}")

    raw = git_bytes("show", f"{preregistration}:{prereg_path}")
    if hashlib.sha256(raw).hexdigest() != prereg_sha:
        raise StageError("preregistration SHA256 mismatch")
    if (ROOT / prereg_path).read_bytes() != raw:
        raise StageError("worktree preregistration differs from Y")
    return raw, head


def extract_config(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StageError("preregistration is not UTF-8") from exc
    if text.count(CONFIG_BEGIN) != 1 or text.count(CONFIG_END) != 1:
        raise StageError("B3 fresh corpus config marker count mismatch")
    block = text.split(CONFIG_BEGIN, 1)[1].split(CONFIG_END, 1)[0]
    try:
        value = json.loads(block)
    except json.JSONDecodeError as exc:
        raise StageError(f"invalid preregistration config JSON: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != PREREG_SCHEMA:
        raise StageError("preregistration config schema mismatch")
    if block.encode("ascii") != canonical_json_bytes(value):
        raise StageError("preregistration config block must be canonical JSON")
    return value


def validate_config(config: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    if config.get("policy") != {"M5": 100, "M50": 60, "minimum_survivors": 2}:
        raise StageError("B3 100/60/2 policy drift")
    if config.get("teacher_budgets_nodes") != [5000, 50000, 200000]:
        raise StageError("B3 teacher budget drift")
    if config.get("audit") != {
        "seed": runtime_adapter.AUDIT_SEED,
        "parents": 1000,
        "per_cell": 125,
        "selection": "sha256(seed_decimal:canonical_fingerprint), lowest per cell",
        "full_ladder_backfill_forbidden": True,
    }:
        raise StageError("B3 audit contract drift")
    expected_contract_sha = config.get("derived_selection_contract_sha256")
    actual_contract_sha = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    if expected_contract_sha != actual_contract_sha:
        raise StageError("derived B3 selection contract SHA mismatch")
    exclusion = config["exclusion"]
    fixed_exclusion = {
        "job_id": "cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1",
        "attempt_id": "20260906T134208Z-c553a572",
        "code_sha": "c553a572ed8ada9c49f8ebbefa3db22a9b6ca739",
        "prefix": "r2:jass-data/runs/cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1/20260906T134208Z-c553a572",
        "manifest_artifact_path": "artefacts/b3-fresh-exclusion-manifest.json",
        "manifest_sha256": "f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c",
        "manifest_schema": runtime_adapter.EXCLUSION_MANIFEST_SCHEMA,
        "union_artifact_path": "artefacts/b3-fresh-exclusion-union.txt",
        "union_sha256": "b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb",
        "union_unique_canonical": 227317,
        "universe": "DECISION_INFORMATION_B3_FRESH_V1_EXCLUSION",
    }
    if exclusion != fixed_exclusion:
        raise StageError("B3 exclusion identity drift")


def _prepare_artifact_dir(path: Path) -> None:
    if path.is_symlink():
        raise StageError("artifact directory cannot be symlink")
    if path.exists():
        if not path.is_dir():
            raise StageError("artifact path is not directory")
        names = {item.name for item in path.iterdir()}
        if names not in (set(), {"runner-launch.json"}):
            raise StageError(f"artifact directory is not clean: {sorted(names)}")
    else:
        path.mkdir(parents=True)


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise StageError("work directory must be absent")
    args.work_dir.mkdir(parents=True)
    _prepare_artifact_dir(args.artifact_dir)

    prereg_raw, runner_sha = authenticate_provenance(
        args.implementation_commit, args.preregistration_commit,
        args.preregistration_path, args.preregistration_sha256,
    )
    config = extract_config(prereg_raw)
    contract = runtime_adapter.derive_selection_contract(config)
    validate_config(config, contract)

    prereg_copy = args.artifact_dir / Path(args.preregistration_path).name
    write_new(prereg_copy, prereg_raw)
    preregistration = {
        "commit": args.preregistration_commit,
        "path": args.preregistration_path,
        "file": publisher._descriptor(prereg_copy, schema=PREREG_SCHEMA),
        "implementation_ancestor": args.implementation_commit,
        "runner_sha": runner_sha,
    }

    runtime = publisher.validate_runtime(ROOT, args.git_timeout_seconds)
    exclusion = dict(config["exclusion"])
    exclusion_fetch, exclusion_paths = publisher.fetch_source(
        ROOT, args.work_dir, args.artifact_dir, "exclusion", exclusion,
        [(exclusion["union_artifact_path"], "b3-fresh-exclusion-union.txt"),
         (exclusion["manifest_artifact_path"], "b3-fresh-exclusion-manifest.json")],
        args.rclone_bin, args.fetch_timeout_seconds,
    )
    curriculum_fetch, curriculum_paths = publisher.fetch_source(
        ROOT, args.work_dir, args.artifact_dir, "curriculum", publisher.CURRICULUM,
        [(publisher.CURRICULUM["remote"], publisher.CURRICULUM["local"])],
        args.rclone_bin, args.fetch_timeout_seconds,
    )
    curriculum_path = args.work_dir / "curriculum.pjtw"
    curriculum_material = publisher.materialize_curriculum(
        curriculum_paths[publisher.CURRICULUM["remote"]], curriculum_path)
    curriculum = {**curriculum_fetch, **curriculum_material}

    build, jass, parent_filter, cache = publisher.build_source(
        ROOT, args.work_dir, args.artifact_dir,
        args.configure_timeout_seconds, args.build_timeout_seconds,
    )
    publisher._copy_new(cache, args.artifact_dir / "CMakeCache.txt")
    write_new(args.artifact_dir / "build-receipt.json", canonical_json_bytes(build))

    contract_path = args.work_dir / "adaptive_sibling_b3_fresh_selection_contract_v1.json"
    write_new(contract_path, canonical_json_bytes(contract))
    selector, launcher, adapter_receipt = runtime_adapter.load_runtime(args.work_dir, contract)
    write_new(args.artifact_dir / "b3-runtime-adapter.json", canonical_json_bytes(adapter_receipt))

    source_dir = args.work_dir / "source"
    source_dir.mkdir()
    manifest = source_dir / "source-manifest.json"
    launcher_args = argparse.Namespace(
        selection_contract=contract_path,
        jass_exe=jass,
        parent_filter_exe=parent_filter,
        curriculum=curriculum_path,
        cmake_cache=cache,
        code_sha=runner_sha,
        build_type="Release",
        compiler_id="GNU",
        compiler_version=runtime["cxx_version"],
        cmake_option=sorted(publisher.CMK_OPTIONS),
        output_dir=source_dir,
        manifest=manifest,
        barrier_timeout_seconds=30,
        exec_verify_timeout_seconds=30,
        producer_timeout_seconds=413,
        filter_timeout_seconds=1,
    )
    started = time.monotonic_ns()
    source_result = launcher.run(launcher_args, contract_override=contract)
    source_execution = {
        "duration_milliseconds": (time.monotonic_ns() - started) // 1_000_000,
        "result": source_result,
    }
    write_new(args.artifact_dir / "source-launcher-receipt.json",
              canonical_json_bytes(source_execution))

    runtime["operational_timeouts_seconds"] = {
        "git": args.git_timeout_seconds,
        "fetch": args.fetch_timeout_seconds,
        "configure": args.configure_timeout_seconds,
        "build": args.build_timeout_seconds,
        "barrier": 30,
        "exec_verify": 30,
        "producer": 413,
        "filter": 1,
        "outer": args.outer_timeout_seconds,
    }
    implementation = {
        "commit": args.implementation_commit,
        "runner_sha": runner_sha,
        "selection_contract_sha256": hashlib.sha256(canonical_json_bytes(contract)).hexdigest(),
        "runtime_adapter": adapter_receipt,
    }
    technical = {
        prereg_copy.name,
        "verified-exclusion.json", "verified-curriculum.json",
        "fetch-exclusion.log", "fetch-curriculum.log",
        "cmake-configure.log", "cmake-build.log", "CMakeCache.txt", "build-receipt.json",
        "b3-runtime-adapter.json", "source-launcher-receipt.json",
    }
    with runtime_adapter.configured_publisher(publisher, selector):
        result = publisher.publish_prepared(
            repo=ROOT, scratch=args.work_dir, artifacts=args.artifact_dir,
            job_id=args.job_id, attempt_id=args.attempt_id,
            implementation=implementation, preregistration=preregistration,
            runtime=runtime, historical=exclusion_fetch, curriculum=curriculum,
            build=build, source_execution=source_execution,
            contract_path=contract_path, source_dir=source_dir,
            exclusion_union=exclusion_paths[exclusion["union_artifact_path"]],
            exclusion_manifest=exclusion_paths[exclusion["manifest_artifact_path"]],
            exclusion_receipt=args.artifact_dir / "verified-exclusion.json",
            contract_override=contract, selector_cli_outcome=None,
            required_technical_artifacts=technical,
        )

    kind = result["kind"]
    if kind == "success":
        receipt = result["receipt"]
        summary = {
            "schema": SCHEMA,
            "state": "completed",
            "verdict": SUCCESS_VERDICT,
            "fresh_b3_parents": 4000,
            "cells": receipt["selection"]["cells"],
            "forbidden_overlap": receipt["selection"]["forbidden_overlap"],
            "target_blind": receipt["selection"]["target_blind"],
            "selection_contract_sha256": implementation["selection_contract_sha256"],
            "parents_jnnw_sha256": receipt["selection"]["parents_jnnw"]["sha256"],
            "ordered_identities_sha256": receipt["selection"]["ordered_identities"]["sha256"],
            "teacher_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "bakes": 0,
            "next_stage": "B3_FRESH_ADAPTIVE_TEACHER",
        }
    else:
        summary = {
            "schema": SCHEMA,
            "state": "completed",
            "verdict": SUPPORT_VERDICT,
            "fresh_b3_parents": 0,
            "support": result["receipt"]["support"],
            "teacher_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "bakes": 0,
            "next_stage": "STOP_B3_FRESH_SOURCE_SUPPORT",
        }
    stage_result = {"schema": SCHEMA, "kind": kind,
                    "publication": Path(result["receipt_path"]).name,
                    "summary_verdict": summary["verdict"]}
    write_new(args.artifact_dir / "b3-source-stage-result.json", canonical_json_bytes(stage_result))
    write_new(args.artifact_dir / "scientific-summary.json", canonical_json_bytes(summary))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--preregistration-path", required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--rclone-bin", default="/usr/bin/rclone")
    parser.add_argument("--git-timeout-seconds", type=int, default=30)
    parser.add_argument("--fetch-timeout-seconds", type=int, default=600)
    parser.add_argument("--configure-timeout-seconds", type=int, default=240)
    parser.add_argument("--build-timeout-seconds", type=int, default=900)
    parser.add_argument("--outer-timeout-seconds", type=int, default=1800)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        summary = execute(args)
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_source_stage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
