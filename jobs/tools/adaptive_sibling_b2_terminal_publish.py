#!/usr/bin/env python3
"""Fail-closed publisher for a completed prospective PR771 B2 terminal readout.

This tool never evaluates the B2 policy and never calls the statistical kernel.
It accepts only a terminal directory already produced by
``adaptive_sibling_b2_readout.py finalize``, re-authenticates the terminal
manifest binding and closed verdict map, copies the immutable terminal payloads,
and publishes a portable receipt.  It cannot launch B3, promote, or bake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_readout as readout  # noqa: E402


PUBLICATION_SCHEMA = "jass.adaptive_sibling_b2_terminal_publication.v1"
ALLOWED_VERDICTS = {
    "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1",
    "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1",
    "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1",
}
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_RE = re.compile(r"[0-9a-f]{40}\Z")
REPORT_KEYS = {"schema", "code_sha", "input_manifest_sha256", "outputs",
               "support", "statistics", "actions", "verdict"}
SUPPORT_KEYS = {"authentication_valid", "selection_valid", "teacher_valid",
                "observations_valid", "projection_invariance_valid",
                "rich_ledger_valid", "sufficient_projection_valid",
                "statistics_support_valid", "all_valid"}


class PublishError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PublishError(f"{label} must be a regular non-symlink file")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise PublishError(f"cannot resolve {label}: {exc}") from exc


def _expect_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        actual = sorted(value) if isinstance(value, Mapping) else type(value).__name__
        raise PublishError(f"{label} keys mismatch: {actual}")
    return value


def _sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise PublishError(f"{label} must be lowercase SHA256")
    return value


def _git_sha(value: object, label: str) -> str:
    if type(value) is not str or not GIT_RE.fullmatch(value):
        raise PublishError(f"{label} must be a full lowercase Git SHA")
    return value


def _read_canonical(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    path = _strict_file(path, label)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"invalid {label}: {exc}") from exc
    if type(value) is not dict or raw != canonical_json_bytes(value):
        raise PublishError(f"{label} must be canonical compact JSON/LF")
    return value, raw


def descriptor(path: Path) -> dict[str, Any]:
    path = _strict_file(path, path.name)
    return {"local_name": path.name, "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size}


def _check_descriptor(path: Path, declared: object, label: str) -> Mapping[str, Any]:
    item = _expect_keys(declared, {"local_name", "sha256", "size_bytes"}, label)
    if item["local_name"] != path.name:
        raise PublishError(f"{label} local_name mismatch")
    _sha(item["sha256"], f"{label}.sha256")
    if type(item["size_bytes"]) is not int or item["size_bytes"] <= 0:
        raise PublishError(f"{label}.size_bytes invalid")
    path = _strict_file(path, label)
    if path.stat().st_size != item["size_bytes"] or sha256_file(path) != item["sha256"]:
        raise PublishError(f"{label} byte descriptor mismatch")
    return item


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink() or os.path.lexists(path):
        raise PublishError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-b2-publish")
    if temporary.exists() or temporary.is_symlink() or os.path.lexists(temporary):
        raise PublishError(f"refusing existing temporary {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if path.is_symlink() or path.read_bytes() != raw:
            raise PublishError(f"published bytes differ: {path.name}")
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def _copy_new(source: Path, destination: Path) -> dict[str, Any]:
    raw = _strict_file(source, source.name).read_bytes()
    _write_new(destination, raw)
    return descriptor(destination)


def _prepare_artifact_dir(path: Path) -> None:
    if path.is_symlink():
        raise PublishError("artifact directory cannot be a symlink")
    if not path.exists():
        path.mkdir(parents=True)
        return
    if not path.is_dir():
        raise PublishError("artifact path is not a directory")
    entries = list(path.iterdir())
    if entries and not (len(entries) == 1 and entries[0].name == "runner-launch.json"
                        and entries[0].is_file() and not entries[0].is_symlink()):
        raise PublishError("artifact directory must be empty or contain only runner-launch.json")


def _validate_report(report: Mapping[str, Any], *, code_sha: str,
                     input_sha: str, terminal_dir: Path) -> tuple[list[Path], str]:
    _expect_keys(report, REPORT_KEYS, "terminal report")
    if report.get("schema") != readout.TERMINAL_SCHEMA or report.get("code_sha") != code_sha:
        raise PublishError("terminal report schema/code mismatch")
    if report.get("input_manifest_sha256") != input_sha:
        raise PublishError("terminal report input manifest SHA mismatch")
    verdict = report.get("verdict")
    if verdict not in ALLOWED_VERDICTS:
        raise PublishError("terminal verdict outside closed B2 map")
    actions = report.get("actions")
    expected_actions = {"searches": 0, "fits": 0, "games": 0, "promotions": 0,
                        "bakes": 0, "automatic_downstream_jobs": 0}
    if actions != expected_actions:
        raise PublishError("terminal actions are not all zero")
    support = _expect_keys(report.get("support"), SUPPORT_KEYS, "terminal support")
    for key in SUPPORT_KEYS:
        if type(support[key]) is not bool:
            raise PublishError(f"terminal support {key} must be boolean")
    if support["all_valid"] != all(support[key] for key in SUPPORT_KEYS if key != "all_valid"):
        raise PublishError("terminal support all_valid mismatch")
    statistics = _expect_keys(report.get("statistics"),
                              {"status", "scientific_gates_evaluated", "all_gates_passed"},
                              "terminal statistics summary")
    outputs = _expect_keys(report.get("outputs"), {"statistics", "progress"},
                           "terminal outputs")
    files = [terminal_dir / "b2-terminal-report-v1.json"]
    if outputs["statistics"] is None or outputs["progress"] is None:
        if outputs != {"statistics": None, "progress": None}:
            raise PublishError("terminal outputs must be both present or both null")
        if verdict != "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1":
            raise PublishError("scientific verdict requires statistics payloads")
        if statistics["status"] is not None \
                or statistics["scientific_gates_evaluated"] is not False \
                or statistics["all_gates_passed"] is not None:
            raise PublishError("no-analysis support terminal summary mismatch")
        expected_names = {"b2-terminal-report-v1.json"}
    else:
        stats_path = terminal_dir / "b2-statistics-v1.json"
        progress_path = terminal_dir / "progress.json"
        _check_descriptor(stats_path, outputs["statistics"], "statistics output")
        _check_descriptor(progress_path, outputs["progress"], "progress output")
        files.extend([stats_path, progress_path])
        expected_names = {"b2-terminal-report-v1.json", "b2-statistics-v1.json", "progress.json"}
        if statistics["status"] == "VALID":
            if statistics["scientific_gates_evaluated"] is not True \
                    or type(statistics["all_gates_passed"]) is not bool:
                raise PublishError("VALID statistics lack evaluated boolean gate")
            expected_verdict = ("B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1"
                                if statistics["all_gates_passed"]
                                else "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1")
            if verdict != expected_verdict:
                raise PublishError("terminal verdict disagrees with gate result")
        elif statistics["status"] == "INVALID_UNKNOWN":
            if statistics["scientific_gates_evaluated"] is not False \
                    or statistics["all_gates_passed"] is not None \
                    or verdict != "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1":
                raise PublishError("INVALID_UNKNOWN terminal route mismatch")
        else:
            raise PublishError("terminal statistics status outside closed map")
    if {entry.name for entry in terminal_dir.iterdir()} != expected_names:
        raise PublishError("terminal directory contains unexpected files")
    return files, verdict


def publish(*, input_manifest: Path, expected_input_manifest_sha256: str,
            terminal_dir: Path, code_sha: str, artifact_dir: Path) -> dict[str, Any]:
    _git_sha(code_sha, "code SHA")
    _sha(expected_input_manifest_sha256, "expected input manifest SHA")
    input_manifest = _strict_file(input_manifest, "terminal input manifest")
    if sha256_file(input_manifest) != expected_input_manifest_sha256:
        raise PublishError("terminal input manifest external SHA mismatch")
    if terminal_dir.is_symlink() or not terminal_dir.is_dir():
        raise PublishError("terminal directory must be a real directory")
    terminal_dir = terminal_dir.resolve(strict=True)
    report_path = terminal_dir / "b2-terminal-report-v1.json"
    report, _ = _read_canonical(report_path, "terminal report")
    payloads, verdict = _validate_report(
        report, code_sha=code_sha, input_sha=expected_input_manifest_sha256,
        terminal_dir=terminal_dir)

    _prepare_artifact_dir(artifact_dir)
    input_desc = _copy_new(input_manifest, artifact_dir / input_manifest.name)
    copied: dict[str, Any] = {}
    for source in payloads:
        copied[source.name] = _copy_new(source, artifact_dir / source.name)
    publication = {
        "schema": PUBLICATION_SCHEMA,
        "code_sha": code_sha,
        "input_manifest": input_desc,
        "terminal_report": copied["b2-terminal-report-v1.json"],
        "artifacts": {
            "statistics": copied.get("b2-statistics-v1.json"),
            "progress": copied.get("progress.json"),
        },
        "verdict": verdict,
        "byte_roundtrip_verified": True,
        "automatic_downstream_jobs": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    receipt_path = artifact_dir / "terminal-publication-receipt.json"
    _write_new(receipt_path, canonical_json_bytes(publication))
    reread, raw = _read_canonical(receipt_path, "terminal publication receipt")
    if reread != publication or raw != canonical_json_bytes(publication):
        raise PublishError("terminal publication receipt roundtrip mismatch")
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--terminal-dir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        publication = publish(
            input_manifest=args.input_manifest,
            expected_input_manifest_sha256=args.expected_input_manifest_sha256,
            terminal_dir=args.terminal_dir,
            code_sha=args.code_sha,
            artifact_dir=args.artifact_dir,
        )
    except (PublishError, OSError, ValueError) as exc:
        print(f"adaptive_sibling_b2_terminal_publish: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({"schema": PUBLICATION_SCHEMA,
                                "verdict": publication["verdict"],
                                "receipt": "terminal-publication-receipt.json"}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
