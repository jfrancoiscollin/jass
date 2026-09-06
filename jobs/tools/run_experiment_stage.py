#!/usr/bin/env python3
"""Run one experiment stage from a strict machine-readable stage specification.

The runner owns orchestration only. It authenticates the repository, inputs,
runtime facts, artifact-directory precondition and declared outputs, then
executes one argv vector without a shell. It never pre-populates
``JASS_ARTEFACT_DIR``; that directory belongs to the stage/publisher. A
machine-readable receipt is always written under ``JASS_RESULT_DIR``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

SPEC_SCHEMA = "jass.stage_spec.v1"
RECEIPT_SCHEMA = "jass.stage_receipt.v1"
SHA40_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ENV_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ALLOWED_SCOPES = {"repo", "result", "artifact"}
ALLOWED_OUTPUT_KINDS = {"file", "directory"}
ARTIFACT_CONTRACT = "empty_or_runner_launch"
SAFE_RUNNER_JASS_ENV = ("JASS_JOB_ID", "JASS_ATTEMPT_ID")

ROOT_KEYS = {
    "schema", "campaign", "stage", "code_sha", "command", "working_directory",
    "inputs", "outputs", "resources", "timeouts", "artifact_directory_contract",
    "environment", "scientific_side_effects", "success",
}
RESOURCE_KEYS = {"hostname", "nproc", "clean_worktree"}
TIMEOUT_KEYS = {"stage_seconds", "terminate_grace_seconds"}
ENVIRONMENT_KEYS = {"inherit", "set"}
SIDE_EFFECT_KEYS = {"fits", "strength_games", "promotions", "bakes"}
SUCCESS_KEYS = {"required_exit_code", "next_stage"}
INPUT_KEYS = {"scope", "path", "required", "sha256", "size_bytes"}
OUTPUT_KEYS = {"scope", "path", "kind", "required", "nonempty"}


class StageSpecError(RuntimeError):
    """Invalid spec or pre-execution contract."""


class StageExecutionError(RuntimeError):
    """Execution or post-execution output contract failure."""


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ) + "\n").encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StageSpecError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_object(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise StageSpecError(f"{label} keys mismatch")
    return value


def _strict_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise StageSpecError(f"{label} must be boolean")
    return value


def _strict_int(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise StageSpecError(f"{label} must be integer in [{low},{high}]")
    return value


def _relative_path(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise StageSpecError(f"{label} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value in {".", "./"}:
        raise StageSpecError(f"{label} must be a child path without '..'")
    return value


def _nullable_sha256(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise StageSpecError(f"{label} must be null or lowercase SHA256")
    return value


def _nullable_size(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _strict_int(value, label, 0, (1 << 63) - 1)


def read_spec(path: Path) -> tuple[dict[str, Any], bytes, str]:
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                StageSpecError(f"forbidden JSON constant {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StageSpecError(f"invalid stage spec JSON: {exc}") from exc
    if type(value) is not dict:
        raise StageSpecError("stage spec root must be object")
    validate_spec(value)
    canonical = canonical_json_bytes(value)
    return value, canonical, sha256_bytes(canonical)


def validate_spec(spec: Mapping[str, Any]) -> None:
    _strict_object(spec, ROOT_KEYS, "stage spec")
    if spec["schema"] != SPEC_SCHEMA:
        raise StageSpecError("stage spec schema mismatch")
    for name in ("campaign", "stage"):
        if type(spec[name]) is not str or not spec[name].strip():
            raise StageSpecError(f"{name} must be non-empty string")
    if type(spec["code_sha"]) is not str or not SHA40_RE.fullmatch(spec["code_sha"]):
        raise StageSpecError("code_sha must be full lowercase Git SHA")

    command = spec["command"]
    if type(command) is not list or not command \
            or any(type(token) is not str or not token for token in command):
        raise StageSpecError("command must be a non-empty argv string list")
    working = spec["working_directory"]
    if working != ".":
        _relative_path(working, "working_directory")

    inputs = spec["inputs"]
    if type(inputs) is not list:
        raise StageSpecError("inputs must be list")
    for index, item in enumerate(inputs):
        obj = _strict_object(item, INPUT_KEYS, f"inputs[{index}]")
        if obj["scope"] not in ALLOWED_SCOPES:
            raise StageSpecError(f"inputs[{index}].scope invalid")
        _relative_path(obj["path"], f"inputs[{index}].path")
        _strict_bool(obj["required"], f"inputs[{index}].required")
        _nullable_sha256(obj["sha256"], f"inputs[{index}].sha256")
        _nullable_size(obj["size_bytes"], f"inputs[{index}].size_bytes")

    outputs = spec["outputs"]
    if type(outputs) is not list:
        raise StageSpecError("outputs must be list")
    seen_outputs: set[tuple[str, str]] = set()
    for index, item in enumerate(outputs):
        obj = _strict_object(item, OUTPUT_KEYS, f"outputs[{index}]")
        if obj["scope"] not in ALLOWED_SCOPES:
            raise StageSpecError(f"outputs[{index}].scope invalid")
        path = _relative_path(obj["path"], f"outputs[{index}].path")
        if obj["kind"] not in ALLOWED_OUTPUT_KINDS:
            raise StageSpecError(f"outputs[{index}].kind invalid")
        _strict_bool(obj["required"], f"outputs[{index}].required")
        _strict_bool(obj["nonempty"], f"outputs[{index}].nonempty")
        key = (obj["scope"], path)
        if key in seen_outputs:
            raise StageSpecError(f"duplicate output contract {key}")
        seen_outputs.add(key)

    resources = _strict_object(spec["resources"], RESOURCE_KEYS, "resources")
    if resources["hostname"] is not None and (
        type(resources["hostname"]) is not str or not resources["hostname"]
    ):
        raise StageSpecError("resources.hostname must be null or non-empty string")
    if resources["nproc"] is not None:
        _strict_int(resources["nproc"], "resources.nproc", 1, 4096)
    _strict_bool(resources["clean_worktree"], "resources.clean_worktree")

    timeouts = _strict_object(spec["timeouts"], TIMEOUT_KEYS, "timeouts")
    _strict_int(timeouts["stage_seconds"], "timeouts.stage_seconds", 1, 7 * 24 * 3600)
    _strict_int(
        timeouts["terminate_grace_seconds"], "timeouts.terminate_grace_seconds", 1, 600,
    )

    if spec["artifact_directory_contract"] != ARTIFACT_CONTRACT:
        raise StageSpecError("unsupported artifact_directory_contract")

    environment = _strict_object(spec["environment"], ENVIRONMENT_KEYS, "environment")
    if type(environment["inherit"]) is not list:
        raise StageSpecError("environment.inherit must be list")
    seen_env: set[str] = set()
    for name in environment["inherit"]:
        if type(name) is not str or not ENV_RE.fullmatch(name) or name.startswith("JASS_"):
            raise StageSpecError("environment.inherit contains invalid/forbidden name")
        if name in seen_env:
            raise StageSpecError("environment.inherit contains duplicate")
        seen_env.add(name)
    if type(environment["set"]) is not dict:
        raise StageSpecError("environment.set must be object")
    for name, value in environment["set"].items():
        if not ENV_RE.fullmatch(name) or name.startswith("JASS_") or type(value) is not str:
            raise StageSpecError("environment.set contains invalid/forbidden entry")
        if name in seen_env:
            raise StageSpecError("environment variable cannot be both inherited and set")

    side = _strict_object(
        spec["scientific_side_effects"], SIDE_EFFECT_KEYS, "scientific_side_effects",
    )
    for key in SIDE_EFFECT_KEYS:
        _strict_int(side[key], f"scientific_side_effects.{key}", 0, (1 << 31) - 1)

    success = _strict_object(spec["success"], SUCCESS_KEYS, "success")
    _strict_int(success["required_exit_code"], "success.required_exit_code", 0, 255)
    if success["next_stage"] is not None and (
        type(success["next_stage"]) is not str or not success["next_stage"]
    ):
        raise StageSpecError("success.next_stage must be null or non-empty string")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise StageSpecError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def authenticate_repo(repo: Path, spec: Mapping[str, Any]) -> None:
    if not repo.is_dir():
        raise StageSpecError("repo root missing")
    head = _git(repo, "rev-parse", "HEAD")
    if head != spec["code_sha"]:
        raise StageSpecError(f"repository HEAD mismatch: {head}")
    if spec["resources"]["clean_worktree"]:
        dirty = _git(repo, "status", "--porcelain", "--untracked-files=normal")
        if dirty:
            raise StageSpecError("repository worktree is not clean")


def _scope_root(scope: str, repo: Path, result: Path, artifact: Path) -> Path:
    return {"repo": repo, "result": result, "artifact": artifact}[scope]


def _resolve_scoped(
    item: Mapping[str, Any], repo: Path, result: Path, artifact: Path,
) -> Path:
    root = _scope_root(item["scope"], repo, result, artifact).resolve()
    path = (root / item["path"]).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise StageSpecError("scoped path escapes root") from exc
    return path


def authenticate_inputs(
    spec: Mapping[str, Any], repo: Path, result: Path, artifact: Path,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for item in spec["inputs"]:
        path = _resolve_scoped(item, repo, result, artifact)
        exists = path.exists() and not path.is_symlink()
        if item["required"] and not exists:
            raise StageSpecError(f"required input missing: {item['scope']}:{item['path']}")
        receipt: dict[str, Any] = {
            "scope": item["scope"], "path": item["path"], "exists": exists,
            "sha256": None, "size_bytes": None,
        }
        if exists:
            if not path.is_file():
                raise StageSpecError(f"input must be regular file: {item['path']}")
            size = path.stat().st_size
            digest = sha256_file(path)
            if item["size_bytes"] is not None and size != item["size_bytes"]:
                raise StageSpecError(f"input size mismatch: {item['path']}")
            if item["sha256"] is not None and digest != item["sha256"]:
                raise StageSpecError(f"input SHA mismatch: {item['path']}")
            receipt.update(sha256=digest, size_bytes=size)
        receipts.append(receipt)
    return receipts


def validate_artifact_dir(artifact: Path) -> dict[str, Any]:
    if artifact.is_symlink():
        raise StageSpecError("artifact directory cannot be symlink")
    artifact.mkdir(parents=True, exist_ok=True)
    if not artifact.is_dir():
        raise StageSpecError("artifact path is not directory")
    entries = sorted(entry.name for entry in artifact.iterdir())
    if entries not in ([], ["runner-launch.json"]):
        raise StageSpecError(
            "artifact directory must be empty or contain only runner-launch.json",
        )
    return {"contract": ARTIFACT_CONTRACT, "initial_entries": entries}


def validate_resources(spec: Mapping[str, Any]) -> dict[str, Any]:
    hostname = socket.gethostname()
    nproc = os.cpu_count() or 1
    expected_host = spec["resources"]["hostname"]
    expected_nproc = spec["resources"]["nproc"]
    if expected_host is not None and hostname != expected_host:
        raise StageSpecError(f"hostname mismatch: {hostname}")
    if expected_nproc is not None and nproc != expected_nproc:
        raise StageSpecError(f"nproc mismatch: {nproc}")
    machine = os.uname().machine if hasattr(os, "uname") else "unknown"
    return {"hostname": hostname, "nproc": nproc, "machine": machine}


def _expand_token(
    token: str, *, repo: Path, result: Path, artifact: Path, spec_path: Path,
) -> str:
    replacements = {
        "{repo}": str(repo),
        "{result_dir}": str(result),
        "{artifact_dir}": str(artifact),
        "{stage_spec}": str(spec_path),
    }
    for key, value in replacements.items():
        token = token.replace(key, value)
    if "{" in token or "}" in token:
        raise StageSpecError(f"unknown command placeholder in {token!r}")
    return token


def build_command(
    spec: Mapping[str, Any], *, repo: Path, result: Path, artifact: Path,
    spec_path: Path,
) -> tuple[list[str], Path, dict[str, str]]:
    command = [
        _expand_token(
            token, repo=repo, result=result, artifact=artifact, spec_path=spec_path,
        )
        for token in spec["command"]
    ]
    working = repo if spec["working_directory"] == "." \
        else (repo / spec["working_directory"])
    working = working.resolve()
    try:
        working.relative_to(repo.resolve())
    except ValueError as exc:
        raise StageSpecError("working_directory escapes repo") from exc
    if not working.is_dir():
        raise StageSpecError("working_directory missing")

    # Stages run under a deliberately sanitized environment, but removing PATH
    # makes standard native build tools unusable and removing the outer runner's
    # TMPDIR breaks detached jobs under systemd PrivateTmp. Supply a deterministic
    # system PATH and preserve only the runner-owned durable TMPDIR automatically.
    env: dict[str, str] = {"PATH": os.defpath}
    for name in spec["environment"]["inherit"]:
        if name in os.environ:
            env[name] = os.environ[name]
    env.update(spec["environment"]["set"])
    if "TMPDIR" in os.environ:
        env["TMPDIR"] = os.environ["TMPDIR"]
    env.update({
        "JASS_CODE_DIR": str(repo),
        "JASS_RESULT_DIR": str(result),
        "JASS_ARTEFACT_DIR": str(artifact),
        "JASS_STAGE_SPEC": str(spec_path),
    })
    # These two values are runner-owned provenance, not user-selectable stage
    # environment. Preserve them when the outer runner provided them.
    for name in SAFE_RUNNER_JASS_ENV:
        if name in os.environ:
            env[name] = os.environ[name]
    return command, working, env


def _terminate_process_group(proc: subprocess.Popen[Any], grace: int) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, AttributeError):
        proc.terminate()
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, AttributeError):
        proc.kill()
    proc.wait()


def execute(
    command: Sequence[str], cwd: Path, env: Mapping[str, str], stdout_path: Path,
    stderr_path: Path, timeout_seconds: int, grace_seconds: int,
) -> tuple[int, bool]:
    timed_out = False
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            list(command), cwd=str(cwd), env=dict(env),
            stdout=stdout, stderr=stderr, start_new_session=True,
        )
        try:
            returncode = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(proc, grace_seconds)
            returncode = 124
    return returncode, timed_out


def validate_outputs(
    spec: Mapping[str, Any], repo: Path, result: Path, artifact: Path,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for item in spec["outputs"]:
        path = _resolve_scoped(item, repo, result, artifact)
        exists = path.exists() and not path.is_symlink()
        if item["required"] and not exists:
            raise StageExecutionError(
                f"required output missing: {item['scope']}:{item['path']}",
            )
        receipt: dict[str, Any] = {
            "scope": item["scope"], "path": item["path"], "kind": item["kind"],
            "exists": exists, "sha256": None, "size_bytes": None,
        }
        if exists:
            if item["kind"] == "file":
                if not path.is_file():
                    raise StageExecutionError(f"output kind mismatch: {item['path']}")
                size = path.stat().st_size
                if item["nonempty"] and size == 0:
                    raise StageExecutionError(f"output unexpectedly empty: {item['path']}")
                receipt.update(sha256=sha256_file(path), size_bytes=size)
            else:
                if not path.is_dir():
                    raise StageExecutionError(f"output kind mismatch: {item['path']}")
                entries = sum(1 for _ in path.iterdir())
                if item["nonempty"] and entries == 0:
                    raise StageExecutionError(
                        f"output directory unexpectedly empty: {item['path']}",
                    )
                receipt["entries"] = entries
        receipts.append(receipt)
    return receipts


def _file_descriptor(path: Path) -> dict[str, Any]:
    return {
        "local_name": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    raw = canonical_json_bytes(receipt)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(raw)
    os.replace(temporary, path)
    if path.read_bytes() != raw:
        raise StageExecutionError("stage receipt roundtrip mismatch")


def run_stage(
    *, spec_path: Path, repo_root: Path, result_dir: Path, artifact_dir: Path,
) -> tuple[int, dict[str, Any]]:
    started_wall = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_wall))
    result_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = result_dir / "stage.stdout.log"
    stderr_path = result_dir / "stage.stderr.log"
    receipt_path = result_dir / "stage-receipt.json"
    for path in (
        stdout_path, stderr_path, receipt_path,
        receipt_path.with_name(receipt_path.name + ".tmp"),
    ):
        if path.exists() or path.is_symlink():
            raise StageSpecError(f"runner-owned output already exists: {path.name}")

    spec: dict[str, Any] | None = None
    spec_sha: str | None = None
    command: list[str] | None = None
    cwd: Path | None = None
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    inputs_validated = False
    runtime: dict[str, Any] | None = None
    artifact_precondition: dict[str, Any] | None = None
    failure_class: str | None = None
    failure_stage: str | None = None
    exit_code: int | None = None
    timed_out = False
    state = "failed"

    try:
        failure_stage = "SPEC"
        spec, _canonical, spec_sha = read_spec(spec_path)
        repo_root = repo_root.resolve(strict=True)
        result_dir = result_dir.resolve()
        artifact_dir = artifact_dir.resolve()

        failure_stage = "REPOSITORY"
        authenticate_repo(repo_root, spec)
        failure_stage = "RESOURCES"
        runtime = validate_resources(spec)
        failure_stage = "ARTIFACT_PRECONDITION"
        artifact_precondition = validate_artifact_dir(artifact_dir)
        failure_stage = "INPUTS"
        inputs = authenticate_inputs(spec, repo_root, result_dir, artifact_dir)
        inputs_validated = True
        failure_stage = "COMMAND"
        command, cwd, env = build_command(
            spec, repo=repo_root, result=result_dir, artifact=artifact_dir,
            spec_path=spec_path.resolve(strict=True),
        )
        failure_stage = "EXECUTE"
        exit_code, timed_out = execute(
            command, cwd, env, stdout_path, stderr_path,
            spec["timeouts"]["stage_seconds"],
            spec["timeouts"]["terminate_grace_seconds"],
        )
        if exit_code != spec["success"]["required_exit_code"]:
            failure_class = "STAGE_TIMEOUT" if timed_out else "STAGE_EXIT_CODE"
            raise StageExecutionError(
                f"stage exit {exit_code}, expected {spec['success']['required_exit_code']}",
            )
        failure_stage = "OUTPUTS"
        outputs = validate_outputs(spec, repo_root, result_dir, artifact_dir)
        state = "completed"
        failure_class = None
        failure_stage = None
    except StageSpecError as exc:
        failure_class = failure_class or "PRECONDITION"
        error_text = str(exc)
    except StageExecutionError as exc:
        failure_class = failure_class or "EXECUTION"
        error_text = str(exc)
    except Exception as exc:
        failure_class = "UNEXPECTED"
        error_text = f"{type(exc).__name__}: {exc}"
    else:
        error_text = None

    if not stdout_path.exists():
        stdout_path.write_bytes(b"")
    if not stderr_path.exists():
        stderr_path.write_bytes(b"")
    ended_wall = time.time()
    ended_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended_wall))
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "spec_sha256": spec_sha,
        "campaign": None if spec is None else spec["campaign"],
        "stage": None if spec is None else spec["stage"],
        "code_sha": None if spec is None else spec["code_sha"],
        "started_at": started_iso,
        "ended_at": ended_iso,
        "duration_seconds": round(ended_wall - started_wall, 6),
        "state": state,
        "failure_class": failure_class,
        "failure_stage": failure_stage,
        "error": error_text,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "inputs_authenticated": inputs_validated,
        "outputs_authenticated": state == "completed",
        "inputs": inputs,
        "outputs": outputs,
        "runtime": runtime,
        "artifact_directory_precondition": artifact_precondition,
        "command": command,
        "working_directory": None if cwd is None else str(cwd),
        "stdout": _file_descriptor(stdout_path),
        "stderr": _file_descriptor(stderr_path),
        "declared_scientific_side_effects": (
            None if spec is None else dict(spec["scientific_side_effects"])
        ),
        "next_stage": (
            spec["success"]["next_stage"]
            if state == "completed" and spec is not None else None
        ),
    }
    write_receipt(receipt_path, receipt)
    return (0 if state == "completed" else 2), receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rc, receipt = run_stage(
            spec_path=args.spec,
            repo_root=args.repo_root,
            result_dir=args.result_dir,
            artifact_dir=args.artifact_dir,
        )
    except Exception as exc:
        print(f"run_experiment_stage: fatal runner error: {exc}", file=sys.stderr)
        return 3
    print(canonical_json_bytes({
        "schema": RECEIPT_SCHEMA,
        "state": receipt["state"],
        "failure_class": receipt["failure_class"],
        "stage": receipt["stage"],
        "next_stage": receipt["next_stage"],
    }).decode("ascii"), end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
