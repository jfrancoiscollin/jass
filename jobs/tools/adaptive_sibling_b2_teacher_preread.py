#!/usr/bin/env python3
"""Authenticate prospective B2 X/Y/S/F and sealed selection before teacher read.

This process is the mandatory barrier immediately before launching the full B2
teacher.  It performs no teacher search itself.  It requires the execution
checkout at implementation commit X, verifies preregistration Y differs from X
only by the normative Markdown file, verifies documentary commit S differs from
Y only by the audited source-publication receipt F, validates F's essential
closed scientific scope, re-hashes the locally fetched selection payloads, and
runs the existing teacher selection-input verifier while target bytes are still
zero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_source_publish as source_publish  # noqa: E402
from jobs.tools import adaptive_sibling_b2_teacher_source as teacher  # noqa: E402


RECEIPT_SCHEMA = "jass.adaptive_sibling_b2_teacher_preread_auth.v1"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
GIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class PreReadError(RuntimeError):
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


def _git_sha(value: object, label: str) -> str:
    if type(value) is not str or not GIT_RE.fullmatch(value):
        raise PreReadError(f"{label} must be a full lowercase Git SHA")
    return value


def _sha(value: object, label: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise PreReadError(f"{label} must be lowercase SHA256")
    return value


def _repo_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or str(path) != value:
        raise PreReadError(f"{label} must be a normalized repository-relative POSIX path")
    return value


def _strict_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PreReadError(f"{label} must be a regular non-symlink file")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise PreReadError(f"cannot resolve {label}: {exc}") from exc


def _git(repo: Path, args: Sequence[str], timeout: int = 30,
         *, allow_rc1: bool = False) -> bytes:
    env = {"LC_ALL": "C", "LANG": "C"}
    try:
        completed = subprocess.run(
            ["git", *args], cwd=repo, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            check=False)
    except subprocess.SubprocessError as exc:
        raise PreReadError(f"git command failed to execute: {args}") from exc
    if completed.returncode != 0 and not (allow_rc1 and completed.returncode == 1):
        raise PreReadError(
            f"git {' '.join(args)} failed rc={completed.returncode}: "
            f"{completed.stderr.decode('utf-8', 'replace')[-1000:]}")
    return completed.stdout


def _git_text(repo: Path, args: Sequence[str], timeout: int = 30) -> str:
    try:
        return _git(repo, args, timeout).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreReadError(f"git output is not UTF-8: {args}") from exc


def _ancestor(repo: Path, older: str, newer: str, timeout: int) -> None:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=repo,
        env={"LC_ALL": "C", "LANG": "C"}, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout,
        check=False)
    if completed.returncode != 0:
        raise PreReadError(f"{older} is not an ancestor of {newer}")


def _diff_names(repo: Path, older: str, newer: str, timeout: int) -> list[str]:
    raw = _git_text(repo, ["diff", "--name-only", "--no-renames", older, newer], timeout)
    return [line for line in raw.splitlines() if line]


def _show(repo: Path, commit: str, path: str, timeout: int) -> bytes:
    return _git(repo, ["show", f"{commit}:{path}"], timeout)


def _read_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreReadError(f"invalid {label} JSON") from exc
    if type(value) is not dict or raw != canonical_json_bytes(value):
        raise PreReadError(f"{label} must be canonical compact JSON/LF")
    return value


def _expect_descriptor(value: object, path: Path, label: str,
                       extras: Mapping[str, object] | None = None) -> Mapping[str, Any]:
    extra = {} if extras is None else dict(extras)
    expected_keys = {"local_name", "sha256", "size_bytes", *extra}
    if type(value) is not dict or set(value) != expected_keys:
        raise PreReadError(f"{label} descriptor shape mismatch")
    path = _strict_file(path, label)
    if value["local_name"] != path.name or value["sha256"] != sha256_file(path) \
            or value["size_bytes"] != path.stat().st_size:
        raise PreReadError(f"{label} descriptor bytes mismatch")
    _sha(value["sha256"], f"{label}.sha256")
    for key, expected in extra.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise PreReadError(f"{label}.{key} mismatch")
    return value


def _validate_f(receipt: Mapping[str, Any], *, x: str, y: str,
                prereg_path: str, prereg_sha: str, parents: Path,
                parents_tsv: Path, selection_report: Path,
                identities: Path) -> None:
    if receipt.get("schema") != source_publish.SUCCESS_SCHEMA \
            or receipt.get("status") != "VALID" \
            or receipt.get("verdict") != source_publish.SUCCESS_VERDICT:
        raise PreReadError("F is not a successful source-selection publication")
    implementation = receipt.get("implementation")
    prereg = receipt.get("preregistration")
    if type(implementation) is not dict or implementation.get("commit") != x:
        raise PreReadError("F implementation commit is not X")
    if type(prereg) is not dict or prereg.get("commit") != y \
            or prereg.get("path") != prereg_path:
        raise PreReadError("F preregistration identity is not Y")
    prereg_file = prereg.get("file")
    if type(prereg_file) is not dict or prereg_file.get("sha256") != prereg_sha:
        raise PreReadError("F preregistration bytes differ from Y")
    if receipt.get("top_up") is not False or receipt.get("regeneration") is not False \
            or receipt.get("new_seed") is not False:
        raise PreReadError("F claims forbidden source recovery action")
    scope = receipt.get("scientific_scope")
    if type(scope) is not dict or any(scope.get(key) != expected for key, expected in {
            "teacher_rows": 0, "teacher_searches": 0, "fits": 0,
            "strength_games": 0, "promotions": 0, "bakes": 0}.items()):
        raise PreReadError("F scientific scope is not pre-teacher")
    selection = receipt.get("selection")
    if type(selection) is not dict or selection.get("parents") != teacher.SELECTED_PARENTS \
            or selection.get("forbidden_overlap") != 0 \
            or selection.get("target_blind") is not True:
        raise PreReadError("F selection contract mismatch")
    cells = selection.get("cells")
    if type(cells) is not dict or len(cells) != 8 \
            or any(type(value) is not int or value != 500 for value in cells.values()):
        raise PreReadError("F cell allocation is not 8x500")
    _expect_descriptor(selection.get("parents_jnnw"), parents, "parents JNNW",
                       {"records": 4_000, "record_size_bytes": 38})
    _expect_descriptor(selection.get("parents_tsv"), parents_tsv, "parents TSV",
                       {"rows": 4_000})
    _expect_descriptor(selection.get("report"), selection_report, "selection report")
    _expect_descriptor(selection.get("ordered_identities"), identities, "ordered identities",
                       {"rows": 4_000,
                        "serialization": "canonical_fingerprint_ascii, one per line, LF terminated"})


def authenticate(*, repo_root: Path, implementation_commit: str,
                 preregistration_commit: str, preregistration_path: str,
                 preregistration_sha256: str, source_documentary_commit: str,
                 source_publication_path: str, source_publication_sha256: str,
                 parents_jnnw: Path, parents_tsv: Path, selection_report: Path,
                 ordered_identities: Path, receipt_path: Path,
                 git_timeout_seconds: int = 30) -> dict[str, Any]:
    x = _git_sha(implementation_commit, "X")
    y = _git_sha(preregistration_commit, "Y")
    s = _git_sha(source_documentary_commit, "S")
    prereg_path = _repo_path(preregistration_path, "preregistration path")
    f_path = _repo_path(source_publication_path, "source publication path")
    prereg_sha = _sha(preregistration_sha256, "preregistration SHA")
    f_sha = _sha(source_publication_sha256, "F SHA")
    if type(git_timeout_seconds) is not int or not 1 <= git_timeout_seconds <= 600:
        raise PreReadError("git timeout must be integer in 1..600")
    repo = repo_root.resolve(strict=True)
    if not (repo / ".git").exists():
        raise PreReadError("repo root is not a Git checkout")
    head = _git_text(repo, ["rev-parse", "HEAD"], git_timeout_seconds).strip()
    if head != x:
        raise PreReadError("teacher execution checkout is not X")
    _ancestor(repo, x, y, git_timeout_seconds)
    _ancestor(repo, y, s, git_timeout_seconds)
    if _diff_names(repo, x, y, git_timeout_seconds) != [prereg_path]:
        raise PreReadError("Y differs from X by more than the normative preregistration file")
    if _diff_names(repo, y, s, git_timeout_seconds) != [f_path]:
        raise PreReadError("S differs from Y by more than the audited F receipt")
    prereg_raw = _show(repo, y, prereg_path, git_timeout_seconds)
    if sha256_bytes(prereg_raw) != prereg_sha:
        raise PreReadError("Y preregistration SHA mismatch")
    f_raw = _show(repo, s, f_path, git_timeout_seconds)
    if sha256_bytes(f_raw) != f_sha:
        raise PreReadError("S F-receipt SHA mismatch")
    f = _read_json_bytes(f_raw, "F")
    parents = _strict_file(parents_jnnw, "parents JNNW")
    parents_meta = _strict_file(parents_tsv, "parents TSV")
    report = _strict_file(selection_report, "selection report")
    identities = _strict_file(ordered_identities, "ordered identities")
    _validate_f(f, x=x, y=y, prereg_path=prereg_path, prereg_sha=prereg_sha,
                parents=parents, parents_tsv=parents_meta,
                selection_report=report, identities=identities)
    teacher_auth = teacher.verify_selection_input(
        parents, report, f["selection"]["report"]["sha256"])
    if teacher_auth.get("authenticated_before_teacher") is not True \
            or teacher_auth.get("teacher_scores_read") != 0 \
            or teacher_auth.get("target_bytes_nonzero") != 0:
        raise PreReadError("teacher selection verifier did not preserve pre-read barrier")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "implementation_commit_X": x,
        "preregistration_commit_Y": y,
        "source_documentary_commit_S": s,
        "preregistration": {"path": prereg_path, "sha256": prereg_sha},
        "source_publication_F": {"path": f_path, "sha256": f_sha,
                                 "job_id": f.get("job_id"),
                                 "attempt_id": f.get("attempt_id")},
        "selection": {
            "parents_jnnw": f["selection"]["parents_jnnw"],
            "parents_tsv": f["selection"]["parents_tsv"],
            "selection_report": f["selection"]["report"],
            "ordered_identities": f["selection"]["ordered_identities"],
            "cells": f["selection"]["cells"],
        },
        "teacher_input_auth": teacher_auth,
        "barrier": {"x_y_only_prereg": True, "y_s_only_f_receipt": True,
                    "selection_bytes_authenticated": True,
                    "target_bytes_nonzero": 0, "teacher_scores_read": 0,
                    "teacher_searches": 0},
        "status": "VALID",
        "verdict": "B2_TEACHER_PREREAD_AUTH_COMPLETE",
    }
    if receipt_path.exists() or receipt_path.is_symlink() or os.path.lexists(receipt_path):
        raise PreReadError("refusing existing pre-read receipt")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(receipt)
    temporary = receipt_path.with_name(receipt_path.name + ".tmp-b2-preread")
    if temporary.exists() or temporary.is_symlink() or os.path.lexists(temporary):
        raise PreReadError("refusing existing pre-read temporary")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, receipt_path)
        if receipt_path.read_bytes() != raw:
            raise PreReadError("pre-read receipt roundtrip mismatch")
    except BaseException:
        temporary.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--preregistration-path", required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--source-documentary-commit", required=True)
    parser.add_argument("--source-publication-path", required=True)
    parser.add_argument("--source-publication-sha256", required=True)
    parser.add_argument("--parents-jnnw", type=Path, required=True)
    parser.add_argument("--parents-tsv", type=Path, required=True)
    parser.add_argument("--selection-report", type=Path, required=True)
    parser.add_argument("--ordered-identities", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--git-timeout-seconds", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        receipt = authenticate(
            repo_root=args.repo_root, implementation_commit=args.implementation_commit,
            preregistration_commit=args.preregistration_commit,
            preregistration_path=args.preregistration_path,
            preregistration_sha256=args.preregistration_sha256,
            source_documentary_commit=args.source_documentary_commit,
            source_publication_path=args.source_publication_path,
            source_publication_sha256=args.source_publication_sha256,
            parents_jnnw=args.parents_jnnw, parents_tsv=args.parents_tsv,
            selection_report=args.selection_report,
            ordered_identities=args.ordered_identities, receipt_path=args.receipt,
            git_timeout_seconds=args.git_timeout_seconds)
    except (PreReadError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"adaptive_sibling_b2_teacher_preread: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({"schema": RECEIPT_SCHEMA,
                                "verdict": receipt["verdict"]}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
