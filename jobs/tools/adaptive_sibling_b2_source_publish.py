#!/usr/bin/env python3
"""Fail-closed publisher for the preregistered PR771 B2 source and selection stage.

The executable orchestrates authenticated historical fetches, the pinned build,
the published source launcher, and the target-blind selector.  Raw generator
JNNW files remain scratch-only.  A successful selection is independently
replayed before its portable files are copied and the raw files are removed.

Operational timeouts are all required CLI arguments.  This module deliberately
contains no fallback timeout and no scientific parameter override.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_select as selector  # noqa: E402
from jobs.tools.adaptive_sibling_b2_exclusions import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


SUCCESS_SCHEMA = "jass.adaptive_sibling_b2_source_selection_publication.v1"
SUPPORT_SCHEMA = "jass.adaptive_sibling_b2_source_selection_support_failure.v1"
SEAL_SCHEMA = "jass.adaptive_sibling_b2_local_selection_seal.v1"
PREREG_SCHEMA = "jass.pr771_b2_preregistration.v1"
SUCCESS_VERDICT = "B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE"
SUPPORT_VERDICT = "B2_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1"
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
UINT64_MAX = (1 << 64) - 1
PINS_SCHEMA = "jass.pr771_b2_source_operational_pins.v1"
PINS_BEGIN = b"B2_SOURCE_OPERATIONAL_PINS_V1_BEGIN\n"
PINS_END = b"B2_SOURCE_OPERATIONAL_PINS_V1_END\n"
MINIMAL_TOOL_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}

HISTORICAL = {
    "job_id": "cpx62-1773-l3-decision-math-b2-historical-identities-v1",
    "attempt_id": "20260905T012244Z-1490b353",
    "code_sha": "1490b3536f6943ec5eab62578ea7d42a29395a27",
    "prefix": "r2:jass-data/runs/cpx62-1773-l3-decision-math-b2-historical-identities-v1/20260905T012244Z-1490b353",
    "files": {
        "artefacts/historical-parent-exclusion-manifest.json":
            ("historical-parent-exclusion-manifest.json", "2f1a551bf6fe020e6436689dc8ef8c95940f473d79a2ebc8613e6c15447cff16"),
        "artefacts/historical-parent-canonical-union.txt":
            ("historical-parent-canonical-union.txt", "3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f"),
    },
}
CURRICULUM = {
    "job_id": "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
    "attempt_id": "20260814T191555Z-18c38a33",
    "code_sha": "18c38a33ae78c9c2e8e2df62fca266da28dacead",
    "prefix": "r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33",
    "remote": "artefacts/D-c-prior-then-current.pjtw.gz",
    "local": "D-c-prior-then-current.pjtw.gz",
    "gzip_sha256": "59114babe3724e17ce145616d23e34b8cd90459b7a8e0c224505d258c2b1e597",
    "gzip_size_bytes": 1_323_949,
    "raw_sha256": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
}
CMK_OPTIONS = [
    "CMAKE_BUILD_TYPE=Release",
    "JASS_EGDB=ON",
    "JASS_EGDB_SRC_DIR=/root/egdb_intl",
    "JASS_ENDGAME_FEATURES=ON",
    "JASS_KING_MOBILITY=ON",
    "JASS_SCAN_PARITY=ON",
    "JASS_TEMPO_STAGE=ON",
]
IMPLEMENTATION_PATHS = (
    "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json",
    "jobs/tools/adaptive_sibling_b2_exclusions.py",
    "jobs/tools/adaptive_sibling_b2_source_launcher.py",
    "jobs/tools/adaptive_sibling_b2_select.py",
    "jobs/tools/adaptive_sibling_b2_source_publish.py",
    "jobs/tools/fetch_result_files.py",
    "jobs/tests/test_adaptive_sibling_b2_source_launcher.py",
    "jobs/tests/test_adaptive_sibling_b2_select.py",
    "jobs/tests/test_adaptive_sibling_b2_source_publish.py",
)


class PublishError(RuntimeError):
    pass


@contextlib.contextmanager
def _termination_signals_as_errors():
    if sys.platform != "linux":
        yield
        return
    previous: dict[int, Any] = {}
    handling = False

    def handler(signum: int, _frame: Any) -> None:
        nonlocal handling
        if not handling:
            handling = True
            raise PublishError(f"publisher interrupted by signal {signum}")

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handler)
        yield
    finally:
        for signum, old in previous.items():
            signal.signal(signum, old)


@contextlib.contextmanager
def _global_deadline(seconds: int):
    _strict_int(seconds, "outer timeout", 1, 86_400)
    if os.name != "posix" or not hasattr(signal, "setitimer"):
        yield
        return
    previous = signal.getsignal(signal.SIGALRM)

    def expired(_signum: int, _frame: Any) -> None:
        raise PublishError("publisher outer timeout expired")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def _strict_int(value: object, label: str, lo: int = 0, hi: int = UINT64_MAX) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise PublishError(f"{label} must be an integer in [{lo},{hi}]")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise PublishError(f"invalid {label}")
    return value


def _expect_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PublishError(f"{label} keys mismatch")
    return value


def _read_json(path: Path, *, canonical: bool = False) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                            parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"invalid JSON: {path.name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PublishError(f"JSON root must be an object: {path.name}")
    if canonical and raw != canonical_json_bytes(parsed):
        raise PublishError(f"JSON is not canonical UTF-8/LF: {path.name}")
    return parsed, raw


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PublishError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise PublishError(f"invalid JSON constant: {value}")


def _regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PublishError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _descriptor(path: Path, **extra: object) -> dict[str, Any]:
    path = _regular(path, path.name)
    return {"local_name": path.name, "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size, **extra}


@dataclass(frozen=True)
class Snapshot:
    path: Path
    device: int
    inode: int
    size: int
    sha256: str


def _snapshot(path: Path, label: str) -> Snapshot:
    path = _regular(path, label)
    st = path.stat()
    return Snapshot(path, st.st_dev, st.st_ino, st.st_size, sha256_file(path))


def _reauth(snapshot: Snapshot, label: str) -> None:
    current = _snapshot(snapshot.path, label)
    if current != snapshot:
        raise PublishError(f"{label} changed after validation")


def _samefile_guard(inputs: Sequence[Path], outputs: Sequence[Path]) -> None:
    keys: set[str] = set()
    stats: set[tuple[int, int]] = set()
    for path in inputs:
        snap = _snapshot(path, path.name)
        key = os.path.normcase(str(snap.path))
        identity = (snap.device, snap.inode)
        if key in keys or identity in stats:
            raise PublishError("input path or hardlink alias")
        keys.add(key)
        stats.add(identity)
    for path in outputs:
        if path.is_symlink() or path.exists() or os.path.lexists(path):
            raise PublishError(f"output already exists or is a symlink: {path.name}")
        key = os.path.normcase(str(path.resolve(strict=False)))
        if key in keys:
            raise PublishError("output aliases an input")


def _write_new(path: Path, raw: bytes) -> None:
    if path.is_symlink() or path.exists() or os.path.lexists(path):
        raise PublishError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-publisher")
    if temp.is_symlink() or temp.exists() or os.path.lexists(temp):
        raise PublishError(f"refusing existing temporary {temp}")
    owned_temp: tuple[int, int] | None = None
    final_identity: tuple[int, int] | None = None
    try:
        with temp.open("xb") as handle:
            st = os.fstat(handle.fileno())
            owned_temp = (st.st_dev, st.st_ino)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        st = temp.stat(follow_symlinks=False)
        if (st.st_dev, st.st_ino) != owned_temp or temp.is_symlink():
            raise PublishError(f"temporary ownership changed: {temp}")
        os.link(temp, path)
        st = path.stat(follow_symlinks=False)
        linked_identity = (st.st_dev, st.st_ino)
        if linked_identity != owned_temp or path.is_symlink():
            raise PublishError(f"final output ownership changed after link: {path}")
        final_identity = owned_temp
    finally:
        if owned_temp is not None:
            try:
                st = temp.stat(follow_symlinks=False)
                if (st.st_dev, st.st_ino) == owned_temp and not temp.is_symlink():
                    temp.unlink()
            except FileNotFoundError:
                pass
    if path.read_bytes() != raw:
        try:
            st = path.stat(follow_symlinks=False)
            if final_identity is not None and (st.st_dev, st.st_ino) == final_identity and not path.is_symlink():
                path.unlink()
        except FileNotFoundError:
            pass
        raise PublishError(f"output reread mismatch: {path.name}")


def _copy_new(source: Path, destination: Path) -> dict[str, Any]:
    raw = _regular(source, source.name).read_bytes()
    _write_new(destination, raw)
    return _descriptor(destination)


def _process_group_exists(pgid: int) -> bool:
    if sys.platform != "linux":
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def _descendant_process_groups(root_pid: int) -> set[int]:
    if sys.platform != "linux":
        return set()
    pending = [root_pid]
    seen: set[int] = set()
    groups: set[int] = set()
    own_group = os.getpgrp()
    while pending:
        parent = pending.pop()
        try:
            text = Path(f"/proc/{parent}/task/{parent}/children").read_text(encoding="ascii")
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        for token in text.split():
            try:
                child = int(token)
            except ValueError:
                continue
            if child in seen:
                continue
            seen.add(child)
            pending.append(child)
            try:
                group = os.getpgid(child)
            except ProcessLookupError:
                continue
            if group != own_group:
                groups.add(group)
    return groups


def _signal_process_groups(groups: set[int], signum: int) -> None:
    for group in groups:
        try:
            os.killpg(group, signum)
        except ProcessLookupError:
            pass


def _cleanup_process_group(process: subprocess.Popen[bytes],
                           known_groups: set[int] | None = None) -> None:
    groups = set() if known_groups is None else set(known_groups)
    if sys.platform == "linux":
        groups.update({process.pid, *_descendant_process_groups(process.pid)})
    if process.poll() is None:
        try:
            if sys.platform == "linux":
                _signal_process_groups(groups, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if sys.platform == "linux":
                groups.update(_descendant_process_groups(process.pid))
                _signal_process_groups(groups, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    surviving = {group for group in groups if _process_group_exists(group)}
    if sys.platform == "linux" and surviving:
        _signal_process_groups(surviving, signal.SIGKILL)
        for _ in range(100):
            surviving = {group for group in surviving if _process_group_exists(group)}
            if not surviving:
                break
            time.sleep(0.01)
        if surviving:
            raise PublishError("subprocess descendant group survived bounded cleanup")


def _run(argv: list[str], *, timeout: int, cwd: Path, log: Path | None = None,
         expected: tuple[int, ...] = (0,),
         environment: dict[str, str] | None = MINIMAL_TOOL_ENV) -> subprocess.CompletedProcess[bytes]:
    _strict_int(timeout, "timeout", 1, 86_400)
    process = subprocess.Popen(argv, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=(sys.platform == "linux"))
    known_groups = {process.pid} if sys.platform == "linux" else set()
    stop_monitor = threading.Event()

    def monitor() -> None:
        while not stop_monitor.wait(0.01):
            known_groups.update(_descendant_process_groups(process.pid))

    monitor_thread = threading.Thread(target=monitor, name="b2-publisher-child-monitor",
                                      daemon=True)
    if sys.platform == "linux":
        monitor_thread.start()
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        stop_monitor.set()
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=1)
        _cleanup_process_group(process, known_groups)
        # Drain and close both PIPE objects after the bounded reap.  This keeps
        # ResourceWarning fatal in the Linux harness even on timeout/signal.
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        raise
    finally:
        stop_monitor.set()
        if monitor_thread.is_alive():
            monitor_thread.join(timeout=1)
    completed = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    surviving = {group for group in known_groups if _process_group_exists(group)}
    if sys.platform == "linux" and surviving:
        _cleanup_process_group(process, surviving)
        raise PublishError("subprocess left a live descendant group")
    if log is not None:
        _write_new(log, completed.stdout + completed.stderr)
    if completed.returncode not in expected:
        raise PublishError(f"command failed ({completed.returncode}): {argv[0]}")
    return completed


def validate_runtime(repo: Path, timeout: int) -> dict[str, Any]:
    libc_name, libc_version = platform.libc_ver()
    actual = {
        "hostname": platform.node(), "nproc": os.cpu_count(), "python_executable": sys.executable,
        "python_version": platform.python_version(), "system": platform.system(),
        "release": platform.release(), "machine": platform.machine(),
        "libc": libc_name, "libc_version": libc_version,
    }
    expected = {"hostname": "cpx62", "nproc": 16, "python_executable": "/usr/bin/python3",
                "python_version": "3.14.4", "system": "Linux",
                "release": "7.0.0-30-generic", "machine": "x86_64",
                "libc": "glibc", "libc_version": "2.43"}
    if any(type(actual[key]) is not type(value) or actual[key] != value for key, value in expected.items()):
        raise PublishError("authenticated CPX runtime identity mismatch")
    cmake_version = _run(["/usr/bin/cmake", "--version"], timeout=timeout, cwd=repo).stdout.decode(
        "utf-8", "strict").splitlines()[0]
    cxx_version = _run(["/usr/bin/c++", "--version"], timeout=timeout, cwd=repo).stdout.decode(
        "utf-8", "strict").splitlines()[0]
    if cmake_version != "cmake version 4.2.3":
        raise PublishError("CMake version mismatch")
    if cxx_version != "c++ (Ubuntu 15.2.0-16ubuntu1) 15.2.0":
        raise PublishError("C++ version mismatch")
    return {**actual, "cmake_version": cmake_version, "cxx_version": cxx_version}


def _capture_git(repo: Path, args: list[str], timeout: int) -> bytes:
    return _run(["/usr/bin/git", *args], timeout=timeout, cwd=repo).stdout


def extract_operational_pins(prereg_raw: bytes) -> dict[str, Any]:
    if prereg_raw.count(PINS_BEGIN) != 1 or prereg_raw.count(PINS_END) != 1:
        raise PublishError("preregistration must contain exactly one operational pin marker pair")
    before, tail = prereg_raw.split(PINS_BEGIN, 1)
    payload_raw, after = tail.split(PINS_END, 1)
    del before, after
    try:
        payload = json.loads(payload_raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                             parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError("invalid operational pin JSON") from exc
    expected = {"schema", "filter_timeout_seconds", "launcher_timeout_seconds",
                "outer_timeout_seconds"}
    _expect_keys(payload, expected, "operational pins")
    if payload_raw != canonical_json_bytes(payload):
        raise PublishError("operational pin JSON must be canonical UTF-8 with one LF")
    if payload["schema"] != PINS_SCHEMA:
        raise PublishError("operational pin schema mismatch")
    for field in ("filter_timeout_seconds", "launcher_timeout_seconds",
                  "outer_timeout_seconds"):
        _strict_int(payload[field], field, 1, 86_400)
    return payload


def validate_git_provenance(repo: Path, implementation: str, preregistration: str,
                            prereg_path: str, git_timeout: int,
                            prereg_expected_sha256: str) -> tuple[dict[str, Any], bytes]:
    if not GIT_SHA_RE.fullmatch(implementation) or not GIT_SHA_RE.fullmatch(preregistration):
        raise PublishError("X and Y must be full lowercase Git SHAs")
    pure = PurePosixPath(prereg_path)
    if not prereg_path or pure.is_absolute() or ".." in pure.parts or pure.suffix != ".md":
        raise PublishError("preregistration path must be a safe repository Markdown path")
    head = _capture_git(repo, ["rev-parse", "HEAD"], git_timeout).decode().strip()
    if head != implementation:
        raise PublishError("checkout is not exactly X")
    if _capture_git(repo, ["status", "--porcelain", "--untracked-files=no"], git_timeout):
        raise PublishError("tracked checkout is dirty")
    ancestry = _run(["/usr/bin/git", "merge-base", "--is-ancestor", implementation,
                     preregistration], timeout=git_timeout, cwd=repo, expected=(0, 1))
    if ancestry.returncode != 0:
        raise PublishError("X is not an ancestor of Y")
    changed_raw = _capture_git(repo, ["diff", "--name-only", "-z", implementation,
                                       preregistration], git_timeout)
    changed = [item.decode("utf-8", "strict") for item in changed_raw.split(b"\0") if item]
    if changed != [prereg_path]:
        raise PublishError("Y must differ from X only by the preregistration Markdown")
    tools: dict[str, Any] = {}
    for rel in IMPLEMENTATION_PATHS:
        x_blob = _capture_git(repo, ["show", f"{implementation}:{rel}"], git_timeout)
        y_blob = _capture_git(repo, ["show", f"{preregistration}:{rel}"], git_timeout)
        if x_blob != y_blob:
            raise PublishError(f"implementation blob differs between X and Y: {rel}")
        working = _regular(repo / rel, rel).read_bytes()
        if working != x_blob:
            raise PublishError(f"working file differs from X: {rel}")
        tools[rel] = {"sha256": sha256_bytes(x_blob), "size_bytes": len(x_blob)}
    architecture: list[dict[str, Any]] = []
    for rel, token in (("CMakeLists.txt", b"jass_scan_ceiling_parent_filter"),
                       ("src/scan_eval.cpp", b"g_emasks"),
                       ("src/search.cpp", b"has_any_capture"),
                       ("src/movegen.cpp", b"has_any_capture")):
        blob = _capture_git(repo, ["show", f"{implementation}:{rel}"], git_timeout)
        if token not in blob or _regular(repo / rel, rel).read_bytes() != blob:
            raise PublishError(f"architecture assertion failed: {rel}")
        architecture.append({"path": rel, "token": token.decode("ascii"),
                             "sha256": sha256_bytes(blob), "size_bytes": len(blob)})
    prereg_raw = _capture_git(repo, ["show", f"{preregistration}:{prereg_path}"], git_timeout)
    if sha256_bytes(prereg_raw) != _sha(prereg_expected_sha256, "preregistration SHA"):
        raise PublishError("preregistration blob SHA mismatch")
    return ({"commit": implementation, "tools": tools, "architecture": architecture,
             "contract": {"local_name": Path(IMPLEMENTATION_PATHS[0]).name,
                          **tools[IMPLEMENTATION_PATHS[0]]}}, prereg_raw)


def _validate_fetch_receipt(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    data, _ = _read_json(path)
    if (type(data.get("schema")) is not int or data.get("schema") != 1 or
            data.get("state") != "verified" or data.get("result_state") != "completed" or
            type(data.get("exit_code")) is not int or data.get("exit_code") != 0 or
            any(data.get(k) != source[k] for k in ("job_id", "attempt_id", "code_sha", "prefix"))):
        raise PublishError("fetch receipt identity mismatch")
    return data


def fetch_source(repo: Path, scratch: Path, artifacts: Path, name: str,
                 source: dict[str, Any], selections: list[tuple[str, str]],
                 rclone: str, timeout: int) -> tuple[dict[str, Any], dict[str, Path]]:
    destination = scratch / f"fetch-{name}"
    destination.mkdir(parents=False, exist_ok=False)
    receipt = artifacts / f"verified-{name}.json"
    argv = ["/usr/bin/python3", str(repo / "jobs/tools/fetch_result_files.py"),
            "--prefix", source["prefix"], "--out-dir", str(destination),
            "--report", str(receipt), "--expected-state", "completed", "--rclone-bin", rclone]
    for remote, local in selections:
        argv += ["--file", f"{remote}={local}"]
    # R2 credentials/configuration belong only to the authenticated fetch subprocess.
    _run(argv, timeout=timeout, cwd=repo, log=artifacts / f"fetch-{name}.log",
         environment=None)
    parsed = _validate_fetch_receipt(receipt, source)
    expected = {remote: local for remote, local in selections}
    entries = parsed.get("files")
    if (not isinstance(entries, list) or len(entries) != len(expected)
            or any(not isinstance(x, dict) or set(x) != {
                "path", "local_name", "sha256", "size_bytes"} for x in entries)
            or {x["path"] for x in entries} != set(expected)):
        raise PublishError("fetch receipt file set mismatch")
    paths = {remote: destination / local for remote, local in selections}
    for entry in entries:
        remote = entry["path"]
        path = paths[remote]
        if (entry.get("local_name") != expected[remote] or entry.get("sha256") != sha256_file(path)
                or type(entry.get("size_bytes")) is not int or entry["size_bytes"] != path.stat().st_size):
            raise PublishError("fetch descriptor mismatch")
    return {"job_id": source["job_id"], "attempt_id": source["attempt_id"],
            "code_sha": source["code_sha"], "prefix": source["prefix"],
            "receipt": _descriptor(receipt), "files": entries,
            "authentication_environment": "inherited_by_fetch_only_not_serialized"}, paths


def materialize_curriculum(gzip_path: Path, output: Path) -> dict[str, Any]:
    gzip_desc = _descriptor(gzip_path)
    if gzip_desc["sha256"] != CURRICULUM["gzip_sha256"] or gzip_desc["size_bytes"] != CURRICULUM["gzip_size_bytes"]:
        raise PublishError("CURRICULUM gzip identity mismatch")
    try:
        raw = gzip.decompress(gzip_path.read_bytes())
    except (OSError, EOFError) as exc:
        raise PublishError("CURRICULUM gzip invalid") from exc
    if sha256_bytes(raw) != CURRICULUM["raw_sha256"]:
        raise PublishError("CURRICULUM decompressed SHA mismatch")
    if len(raw) < 8 or raw[:4] != b"PJTW" or struct.unpack_from("<I", raw, 4)[0] != 0x203:
        raise PublishError("CURRICULUM header mismatch")
    _write_new(output, raw)
    return {"source": gzip_desc, "decompressed": _descriptor(output),
            "header": {"magic": "PJTW", "version": 0x203}}


def _parse_cache(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(("#", "//")) or "=" not in line:
            continue
        left, value = line.split("=", 1)
        if ":" in left:
            out[left.split(":", 1)[0]] = value
    return out


def build_source(repo: Path, scratch: Path, artifacts: Path, configure_timeout: int,
                 build_timeout: int) -> tuple[dict[str, Any], Path, Path, Path]:
    build = scratch / "build"
    build.mkdir(exist_ok=False)
    configure = ["/usr/bin/cmake", "-S", str(repo), "-B", str(build), "-G", "Unix Makefiles",
                 *[f"-D{x}" for x in CMK_OPTIONS]]
    started = time.monotonic_ns()
    _run(configure, timeout=configure_timeout, cwd=repo, log=artifacts / "cmake-configure.log")
    configure_ms = (time.monotonic_ns() - started) // 1_000_000
    build_argv = ["/usr/bin/cmake", "--build", str(build), "--target", "jass",
                  "jass_scan_ceiling_parent_filter", "-j", "8"]
    started = time.monotonic_ns()
    _run(build_argv, timeout=build_timeout, cwd=repo, log=artifacts / "cmake-build.log")
    build_ms = (time.monotonic_ns() - started) // 1_000_000
    cache = _regular(build / "CMakeCache.txt", "CMake cache")
    expected = {key: value for key, value in (x.split("=", 1) for x in CMK_OPTIONS)}
    actual = _parse_cache(cache)
    if any(actual.get(key) != value for key, value in expected.items()):
        raise PublishError("CMake cache option mismatch")
    jass = _regular(build / "jass", "jass executable")
    parent_filter = _regular(build / "jass_scan_ceiling_parent_filter", "parent filter executable")
    configure_template = [token.replace(str(repo), "{ROOT}").replace(str(build), "{BUILD}")
                          for token in configure]
    build_template = [token.replace(str(repo), "{ROOT}").replace(str(build), "{BUILD}")
                      for token in build_argv]
    return ({"configure_argv_template": configure_template, "build_argv_template": build_template,
             "tool_environment": dict(MINIMAL_TOOL_ENV),
             "configure_duration_milliseconds": configure_ms,
             "build_duration_milliseconds": build_ms,
             "configure_log": _descriptor(artifacts / "cmake-configure.log"),
             "build_log": _descriptor(artifacts / "cmake-build.log"),
             "cmake_options": expected, "cache": _descriptor(cache),
             "jass": _descriptor(jass), "parent_filter": _descriptor(parent_filter)},
            jass, parent_filter, cache)


def _source_paths(manifest: dict[str, Any], source_dir: Path) -> tuple[list[Path], list[Path], list[Path], list[Path]]:
    raw: list[Path] = []
    filtered: list[Path] = []
    meta: list[Path] = []
    reports: list[Path] = []
    for shard in manifest["shards"]:
        raw.append(source_dir / shard["producer"]["raw_jnnw"]["local_name"])
        filtered.append(source_dir / shard["filter"]["filtered_jnnw"]["local_name"])
        meta.append(source_dir / shard["filter"]["filtered_meta"]["local_name"])
        reports.append(source_dir / shard["filter"]["report"]["local_name"])
    return raw, filtered, meta, reports


def _verify_manifest_files(manifest: dict[str, Any], source_dir: Path) -> None:
    for shard in manifest["shards"]:
        entries = [shard["producer"]["raw_jnnw"], shard["producer"]["log"],
                   shard["filter"]["filtered_jnnw"], shard["filter"]["filtered_meta"],
                   shard["filter"]["report"]]
        for entry in entries:
            path = _regular(source_dir / entry["local_name"], entry["local_name"])
            if sha256_file(path) != entry["sha256"] or path.stat().st_size != entry["size_bytes"]:
                raise PublishError(f"source manifest descriptor mismatch: {path.name}")


def _selector_namespace(contract: Path, source_manifest: Path, filtered: list[Path],
                        meta: list[Path], reports: list[Path], union: Path,
                        exclusion_manifest: Path, exclusion_receipt: Path,
                        output_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(contract=contract, source_manifest=source_manifest,
        filtered_jnnw=filtered, filtered_meta=meta, filter_report=reports,
        exclusion_union=union, exclusion_manifest=exclusion_manifest,
        exclusion_receipt=exclusion_receipt, out_jnnw=output_dir / "parents.jnnw",
        out_tsv=output_dir / "parents.tsv", report=output_dir / "selection-report.json")


def _ordered_identities(tsv: Path) -> bytes:
    raw = tsv.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise PublishError("parents TSV must be UTF-8 LF without BOM")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("ascii")), delimiter="\t"))
    except (UnicodeError, csv.Error) as exc:
        raise PublishError("invalid parents TSV") from exc
    if len(rows) != selector.OUTPUT_RECORDS or list(rows[0]) != selector.OUTPUT_FIELDS:
        raise PublishError("parents TSV shape mismatch")
    for expected, row in enumerate(rows):
        if row["parent_id"] != str(expected):
            raise PublishError("parent_id order mismatch")
    return ("".join(row["canonical_fingerprint"] + "\n" for row in rows)).encode("ascii")


def replay_and_seal(args: argparse.Namespace, replay_dir: Path, seal_path: Path,
                    contract_override: dict[str, Any] | None = None) -> dict[str, Any]:
    replay_dir.mkdir(exist_ok=False)
    replay_args = argparse.Namespace(**vars(args))
    replay_args.out_jnnw = replay_dir / "parents.jnnw"
    replay_args.out_tsv = replay_dir / "parents.tsv"
    replay_args.report = replay_dir / "selection-report.json"
    result = selector.run(replay_args, contract_override=contract_override)
    for first, second, label in ((args.out_jnnw, replay_args.out_jnnw, "parents JNNW"),
                                 (args.out_tsv, replay_args.out_tsv, "parents TSV"),
                                 (args.report, replay_args.report, "selection report")):
        if first.read_bytes() != second.read_bytes():
            raise PublishError(f"target-blind replay mismatch: {label}")
    report, report_raw = _read_json(args.report, canonical=True)
    identities = _ordered_identities(args.out_tsv)
    expected = report["outputs"]["ordered_identities"]
    if (expected != {"sha256": sha256_bytes(identities), "size_bytes": len(identities),
                     "rows": selector.OUTPUT_RECORDS,
                     "serialization": "canonical_fingerprint_ascii, one per line, LF terminated"}):
        raise PublishError("ordered identities descriptor mismatch")
    snapshots = [_snapshot(path, path.name) for path in [args.contract, args.source_manifest,
                 *args.filtered_jnnw, *args.filtered_meta, *args.filter_report,
                 args.exclusion_union, args.exclusion_manifest, args.exclusion_receipt,
                 args.out_jnnw, args.out_tsv, args.report]]
    seal = {"schema": SEAL_SCHEMA, "target_blind_replay": True,
            "selection_report": {"local_name": args.report.name,
                                 "sha256": sha256_bytes(report_raw), "size_bytes": len(report_raw)},
            "parents_jnnw": _descriptor(args.out_jnnw, records=selector.OUTPUT_RECORDS,
                                         record_size_bytes=38),
            "parents_tsv": _descriptor(args.out_tsv, rows=selector.OUTPUT_RECORDS),
            "ordered_identities": {"local_name": "ordered-identities.txt",
                                     "sha256": sha256_bytes(identities),
                                     "size_bytes": len(identities), "rows": selector.OUTPUT_RECORDS,
                                     "serialization": expected["serialization"]},
            "inputs_reauthenticated": True, "source_labels_read": 0,
            "source_score_bytes_read": 0, "source_wdl_bytes_read": 0}
    for snap in snapshots:
        _reauth(snap, snap.path.name)
    _write_new(seal_path, canonical_json_bytes(seal))
    _read_json(seal_path, canonical=True)
    return {"seal": seal, "identities": identities, "selector_result": result}


def _validate_support(payload: dict[str, Any]) -> None:
    expected_keys = {"schema", "cell_order", "cell_quota", "support_before_sampling",
                     "insufficient_cells", "counters", "target_blind", "top_up", "outputs_created"}
    _expect_keys(payload, expected_keys, "selector support")
    if (payload["schema"] != selector.SUPPORT_REPORT_SCHEMA or
            payload["cell_order"] != selector.CELL_ORDER or
            type(payload["cell_quota"]) is not int or payload["cell_quota"] != selector.CELL_QUOTA or
            payload["target_blind"] is not True or payload["top_up"] is not False or
            type(payload["outputs_created"]) is not int or payload["outputs_created"] != 0):
        raise PublishError("selector support constants mismatch")
    supports = _expect_keys(payload["support_before_sampling"], set(selector.CELL_ORDER), "supports")
    for cell in selector.CELL_ORDER:
        _strict_int(supports[cell], f"support {cell}")
    expected_insufficient = [cell for cell in selector.CELL_ORDER if supports[cell] < selector.CELL_QUOTA]
    if payload["insufficient_cells"] != expected_insufficient or not expected_insufficient:
        raise PublishError("selector insufficient cells mismatch")
    counters = _expect_keys(payload["counters"], selector.SUPPORT_COUNTER_FIELDS,
                            "selector support counters")
    for field, value in counters.items():
        _strict_int(value, f"support counter {field}")


def _validate_selector_success(payload: dict[str, Any], args: argparse.Namespace) -> None:
    expected = {"schema", "selected", "report_sha256", "parents_jnnw_sha256",
                "parents_tsv_sha256", "ordered_identities_sha256"}
    _expect_keys(payload, expected, "selector success stdout")
    if payload["schema"] != selector.SELECTION_REPORT_SCHEMA:
        raise PublishError("selector success schema mismatch")
    if type(payload["selected"]) is not int or payload["selected"] != selector.OUTPUT_RECORDS:
        raise PublishError("selector success parent count mismatch")
    report, report_raw = _read_json(args.report, canonical=True)
    identities = _ordered_identities(args.out_tsv)
    comparisons = {
        "report_sha256": sha256_bytes(report_raw),
        "parents_jnnw_sha256": sha256_file(args.out_jnnw),
        "parents_tsv_sha256": sha256_file(args.out_tsv),
        "ordered_identities_sha256": sha256_bytes(identities),
    }
    if any(payload[field] != expected_sha for field, expected_sha in comparisons.items()):
        raise PublishError("selector success stdout/output descriptor mismatch")
    if report["outputs"]["ordered_identities"]["sha256"] != comparisons["ordered_identities_sha256"]:
        raise PublishError("selector report ordered identity SHA mismatch")


def _publish_source_files(source_manifest: dict[str, Any], source_dir: Path,
                          artifacts: Path) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    names = {"source-manifest.json"}
    for shard in source_manifest["shards"]:
        names.add(shard["producer"]["log"]["local_name"])
        for kind in ("filtered_jnnw", "filtered_meta", "report"):
            names.add(shard["filter"][kind]["local_name"])
    if any(re.fullmatch(r"shard-[0-9]{2}\.jnnw", name) for name in names):
        raise PublishError("raw source file entered publication allowlist")
    for name in sorted(names):
        published.append(_copy_new(source_dir / name, artifacts / name))
    return published


def _publish_or_describe(source: Path, artifacts: Path) -> dict[str, Any]:
    if source.resolve(strict=True).parent == artifacts.resolve(strict=True):
        return _descriptor(source)
    return _copy_new(source, artifacts / source.name)


def _artifact_inventory(artifacts: Path, excluded: set[str],
                        allowed: set[str]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    actual = {path.name for path in artifacts.iterdir()
              if path.name not in excluded and path.name != "runner-launch.json"}
    if actual != allowed:
        raise PublishError("artifact inventory does not equal the closed allowlist")
    for path in sorted(artifacts.iterdir(), key=lambda item: item.name):
        if path.name in excluded or path.name == "runner-launch.json":
            continue
        if path.is_symlink() or not path.is_file():
            raise PublishError("artifact directory contains a non-regular entry")
        if re.fullmatch(r"shard-[0-9]{2}\.jnnw", path.name):
            raise PublishError("raw source appeared in artifact inventory")
        inventory.append(_descriptor(path))
    return inventory


def _published_allowlist(portable: list[dict[str, Any]], preregistration: dict[str, Any],
                         technical: set[str]) -> set[str]:
    allowed = {entry["local_name"] for entry in portable}
    prereg_file = preregistration.get("file")
    if isinstance(prereg_file, dict) and isinstance(prereg_file.get("local_name"), str):
        allowed.add(prereg_file["local_name"])
    allowed.update(technical)
    return allowed


def _verify_empty_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise PublishError(f"{label} directory missing")
    if list(path.iterdir()):
        raise PublishError(f"{label} created forbidden outputs")


def run_selector_cli(repo: Path, contract_path: Path, source_dir: Path,
                     exclusion_union: Path, exclusion_manifest: Path,
                     exclusion_receipt: Path, output_dir: Path,
                     timeout: int) -> tuple[int, dict[str, Any]]:
    contract, _ = selector.load_contract(contract_path)
    manifest, _ = selector.validate_source_manifest(source_dir / "source-manifest.json", contract)
    _, filtered, meta, reports = _source_paths(manifest, source_dir)
    output_dir.mkdir(exist_ok=False)
    args = _selector_namespace(contract_path, source_dir / "source-manifest.json", filtered, meta,
                               reports, exclusion_union, exclusion_manifest, exclusion_receipt,
                               output_dir)
    argv = ["/usr/bin/python3", str(repo / "jobs/tools/adaptive_sibling_b2_select.py"),
            "--contract", str(args.contract), "--source-manifest", str(args.source_manifest)]
    for flag, values in (("--filtered-jnnw", args.filtered_jnnw),
                         ("--filtered-meta", args.filtered_meta),
                         ("--filter-report", args.filter_report)):
        argv += [flag, *map(str, values)]
    argv += ["--exclusion-union", str(args.exclusion_union),
             "--exclusion-manifest", str(args.exclusion_manifest),
             "--exclusion-receipt", str(args.exclusion_receipt),
             "--out-jnnw", str(args.out_jnnw), "--out-tsv", str(args.out_tsv),
             "--report", str(args.report)]
    completed = _run(argv, timeout=timeout, cwd=repo, expected=(0, 4), environment={})
    if completed.stderr:
        raise PublishError("selector emitted stderr")
    try:
        payload = json.loads(completed.stdout.decode("ascii"), object_pairs_hook=_reject_duplicates,
                             parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublishError("selector stdout is not one canonical JSON value") from exc
    if not isinstance(payload, dict) or completed.stdout != canonical_json_bytes(payload):
        raise PublishError("selector stdout is not canonical JSON/LF")
    if completed.returncode == 4:
        _validate_support(payload)
    elif payload.get("schema") != selector.SELECTION_REPORT_SCHEMA:
        raise PublishError("selector success stdout schema mismatch")
    return completed.returncode, payload


def cleanup_raw(raw_paths: list[Path], source_dir: Path,
                expected_snapshots: dict[str, Snapshot]) -> dict[str, Any]:
    if len(raw_paths) != selector.SOURCE_SHARDS:
        raise PublishError("raw cleanup requires exactly 16 paths")
    root = source_dir.resolve(strict=True)
    for shard, path in enumerate(raw_paths):
        if path.resolve(strict=True).parent != root or path.name != f"shard-{shard:02d}.jnnw":
            raise PublishError("raw cleanup path mismatch")
        key = os.path.normcase(str(path.resolve(strict=True)))
        if key not in expected_snapshots:
            raise PublishError("raw cleanup lacks owned identity snapshot")
        _reauth(expected_snapshots[key], "raw source")
    for path in raw_paths:
        path.unlink()
    remaining = sum(path.exists() or path.is_symlink() for path in raw_paths)
    if remaining:
        raise PublishError("raw cleanup incomplete")
    return {"raw_expected": 16, "raw_published": 0, "raw_removed": 16,
            "raw_remaining": 0, "target_bytes_parsed": 0}


def _verify_published_selection(artifacts: Path, report: dict[str, Any],
                                seal: dict[str, Any]) -> None:
    jnnw = _descriptor(artifacts / "parents.jnnw", records=selector.OUTPUT_RECORDS,
                       record_size_bytes=38)
    tsv = _descriptor(artifacts / "parents.tsv", rows=selector.OUTPUT_RECORDS)
    identities = _descriptor(
        artifacts / "ordered-identities.txt", rows=selector.OUTPUT_RECORDS,
        serialization="canonical_fingerprint_ascii, one per line, LF terminated")
    report_file = _descriptor(artifacts / "selection-report.json")
    seal_path = _regular(artifacts / "local-selection-seal.json", "published local seal")
    if seal_path.read_bytes() != canonical_json_bytes(seal):
        raise PublishError("published local seal differs from replay seal bytes")
    if ({key: jnnw[key] for key in ("sha256", "size_bytes", "records")}
            != report["outputs"]["parents_jnnw"]):
        raise PublishError("published parents JNNW differs from selection report")
    if ({key: tsv[key] for key in ("sha256", "size_bytes", "rows")}
            != report["outputs"]["parents_tsv"]):
        raise PublishError("published parents TSV differs from selection report")
    expected_identities = {key: identities[key] for key in (
        "sha256", "size_bytes", "rows", "serialization")}
    if expected_identities != report["outputs"]["ordered_identities"]:
        raise PublishError("published identities differ from selection report")
    if seal["parents_jnnw"] != jnnw or seal["parents_tsv"] != tsv \
            or seal["ordered_identities"] != identities \
            or seal["selection_report"] != report_file:
        raise PublishError("published selection differs from local seal")


def publish_prepared(*, repo: Path, scratch: Path, artifacts: Path, job_id: str,
                     attempt_id: str, implementation: dict[str, Any],
                     preregistration: dict[str, Any], runtime: dict[str, Any],
                     historical: dict[str, Any], curriculum: dict[str, Any],
                     build: dict[str, Any], source_execution: dict[str, Any],
                     contract_path: Path, source_dir: Path,
                     exclusion_union: Path, exclusion_manifest: Path,
                     exclusion_receipt: Path,
                     contract_override: dict[str, Any] | None = None,
                     selector_cli_outcome: tuple[int, dict[str, Any]] | None = None,
                     required_technical_artifacts: set[str] | None = None) -> dict[str, Any]:
    """Publish already prepared launcher outputs; used by production and offline tests."""
    contract = contract_override
    if contract is None:
        contract, _ = selector.load_contract(contract_path)
    source_manifest_path = source_dir / "source-manifest.json"
    preparse = [_snapshot(path, path.name) for path in (
        contract_path, source_manifest_path, exclusion_union, exclusion_manifest,
        exclusion_receipt)]
    source_manifest, source_manifest_raw = selector.validate_source_manifest(source_manifest_path, contract)
    for snap in preparse:
        _reauth(snap, snap.path.name)
    _verify_manifest_files(source_manifest, source_dir)
    raw_paths, filtered, meta, reports = _source_paths(source_manifest, source_dir)
    all_source_files = [source_manifest_path]
    for shard in source_manifest["shards"]:
        all_source_files += [source_dir / shard["producer"]["raw_jnnw"]["local_name"],
                             source_dir / shard["producer"]["log"]["local_name"]]
        all_source_files += [source_dir / shard["filter"][name]["local_name"]
                             for name in ("filtered_jnnw", "filtered_meta", "report")]
    _samefile_guard([contract_path, exclusion_union, exclusion_manifest, exclusion_receipt,
                     *all_source_files], [])
    select_dir = scratch / "selection"
    if selector_cli_outcome is None:
        select_dir.mkdir(exist_ok=False)
    elif not select_dir.is_dir() or select_dir.is_symlink():
        raise PublishError("selector CLI output directory missing")
    select_args = _selector_namespace(contract_path, source_manifest_path, filtered, meta, reports,
                                      exclusion_union, exclusion_manifest, exclusion_receipt, select_dir)
    inputs = [contract_path, exclusion_union, exclusion_manifest, exclusion_receipt,
              *all_source_files]
    input_snapshots = [_snapshot(path, path.name) for path in inputs]
    raw_snapshots = {os.path.normcase(str(snap.path)): snap for snap in input_snapshots
                     if snap.path.name in {path.name for path in raw_paths}}
    support_payload: dict[str, Any] | None = None
    if selector_cli_outcome is None:
        try:
            selector_result = selector.run(select_args, contract_override=contract_override)
        except selector.InsufficientSupportError as exc:
            support_payload = exc.payload()
            _validate_support(support_payload)
    else:
        rc, payload = selector_cli_outcome
        if rc == 4:
            support_payload = payload
            selector_result = payload
            _validate_support(payload)
        elif rc == 0:
            selector_result = payload
        else:
            raise PublishError("selector CLI outcome must be success or typed support")
    selected_snapshots: list[Snapshot] = []
    if support_payload is None:
        selected_snapshots = [_snapshot(path, path.name) for path in (
            select_args.out_jnnw, select_args.out_tsv, select_args.report)]
        if selector_cli_outcome is not None:
            _validate_selector_success(selector_result, select_args)
    if support_payload is not None:
        replay_dir = scratch / "support-replay"
        replay_dir.mkdir(exist_ok=False)
        replay_args = _selector_namespace(contract_path, source_manifest_path, filtered, meta, reports,
                                          exclusion_union, exclusion_manifest, exclusion_receipt, replay_dir)
        try:
            selector.run(replay_args, contract_override=contract_override)
        except selector.InsufficientSupportError as replay_exc:
            if replay_exc.payload() != support_payload:
                raise PublishError("support replay mismatch")
        else:
            raise PublishError("support replay unexpectedly succeeded")
        _verify_empty_directory(select_dir, "selector support")
        _verify_empty_directory(replay_dir, "selector support replay")
    for snap in input_snapshots:
        _reauth(snap, snap.path.name)
    if support_payload is not None:
        portable = _publish_source_files(source_manifest, source_dir, artifacts)
        portable += [_publish_or_describe(contract_path, artifacts),
                     _publish_or_describe(exclusion_union, artifacts),
                     _publish_or_describe(exclusion_manifest, artifacts),
                     _publish_or_describe(exclusion_receipt, artifacts)]
        for snap in input_snapshots:
            _reauth(snap, snap.path.name)
        cleanup = cleanup_raw(raw_paths, source_dir, raw_snapshots)
        receipt = {"schema": SUPPORT_SCHEMA, "job_id": job_id, "attempt_id": attempt_id,
                   "implementation": implementation, "preregistration": preregistration,
                   "source_manifest": {"local_name": source_manifest_path.name,
                                       "sha256": sha256_bytes(source_manifest_raw),
                                       "size_bytes": len(source_manifest_raw)},
                   "source_execution": source_execution,
                   "support": support_payload, "cleanup": cleanup,
                   "runtime": runtime, "historical_inputs": historical,
                   "curriculum": curriculum, "build": build,
                   "published_artifacts": _artifact_inventory(
                       artifacts, {"source-selection-support-failure.json"},
                       _published_allowlist(portable, preregistration,
                                            required_technical_artifacts or set())),
                   "parents_outputs": 0, "teacher": 0, "top_up": False,
                   "regeneration": False, "new_seed": False,
                   "status": "SUPPORT_NOT_ESTABLISHED", "verdict": SUPPORT_VERDICT}
        receipt_path = artifacts / "source-selection-support-failure.json"
        _write_new(receipt_path, canonical_json_bytes(receipt))
        reread, _ = _read_json(receipt_path, canonical=True)
        if reread != receipt:
            raise PublishError("support receipt roundtrip mismatch")
        return {"kind": "support", "receipt": receipt, "receipt_path": receipt_path}

    replay = replay_and_seal(select_args, scratch / "selection-replay",
                             select_dir / "local-selection-seal.json", contract_override)
    for snap in selected_snapshots:
        _reauth(snap, snap.path.name)
    report, _ = _read_json(select_args.report, canonical=True)
    _write_new(select_dir / "ordered-identities.txt", replay["identities"])
    selected_files = [select_args.out_jnnw, select_args.out_tsv, select_args.report,
                      select_dir / "ordered-identities.txt", select_dir / "local-selection-seal.json"]
    portable = _publish_source_files(source_manifest, source_dir, artifacts)
    portable += [_publish_or_describe(contract_path, artifacts),
                 _publish_or_describe(exclusion_union, artifacts),
                 _publish_or_describe(exclusion_manifest, artifacts),
                 _publish_or_describe(exclusion_receipt, artifacts)]
    for path in selected_files:
        portable.append(_copy_new(path, artifacts / path.name))
    _verify_published_selection(artifacts, report, replay["seal"])
    for snap in selected_snapshots:
        _reauth(snap, snap.path.name)
    for snap in input_snapshots:
        _reauth(snap, snap.path.name)
    cleanup = cleanup_raw(raw_paths, source_dir, raw_snapshots)
    cells = report["selected_by_phase_stm"]
    if cells != {cell: selector.CELL_QUOTA for cell in selector.CELL_ORDER}:
        raise PublishError("selected cells mismatch")
    success = {"schema": SUCCESS_SCHEMA, "job_id": job_id, "attempt_id": attempt_id,
        "implementation": implementation, "preregistration": preregistration,
        "runtime": runtime, "historical_inputs": historical, "curriculum": curriculum,
        "build": build,
        "source": {"shards": 16, "raw_records": 160_000,
                   "filtered_records": sum(struct.unpack_from("<I", p.read_bytes(), 4)[0] for p in filtered),
                   "manifest": _descriptor(artifacts / source_manifest_path.name),
                   "barrier_passed": True, "transmitted_names": [],
                   "launcher": source_execution},
        "selection": {"parents": 4_000, "cells": cells,
                      "report": _descriptor(artifacts / select_args.report.name),
                      "parents_jnnw": _descriptor(artifacts / select_args.out_jnnw.name,
                                                  records=4_000, record_size_bytes=38),
                      "parents_tsv": _descriptor(artifacts / select_args.out_tsv.name, rows=4_000),
                      "ordered_identities": _descriptor(
                          artifacts / "ordered-identities.txt", rows=4_000,
                          serialization="canonical_fingerprint_ascii, one per line, LF terminated"),
                      "forbidden_overlap": 0, "target_blind": True,
                      "local_seal": _descriptor(artifacts / "local-selection-seal.json")},
        "cleanup": cleanup,
        "published_artifacts": _artifact_inventory(
            artifacts, {"source-selection-publication.json"},
            _published_allowlist(portable, preregistration,
                                 required_technical_artifacts or set())),
        "scientific_scope": {"teacher_rows": 0, "teacher_searches": 0, "fits": 0,
            "strength_games": 0, "promotions": 0, "bakes": 0,
            "source_generation": {"producer_processes": 16, "raw_records": 160_000,
                                  "internal_search_count": None, "self_play_game_count": None},
            "scientific_verdict": None},
        "status": "VALID", "verdict": SUCCESS_VERDICT}
    success_path = artifacts / "source-selection-publication.json"
    _write_new(success_path, canonical_json_bytes(success))
    reread, _ = _read_json(success_path, canonical=True)
    if reread != success:
        raise PublishError("success receipt roundtrip mismatch")
    return {"kind": "success", "receipt": success, "receipt_path": success_path,
            "selector_result": selector_result}


def _positive(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--scratch-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--preregistration-commit", required=True)
    parser.add_argument("--preregistration-path", required=True)
    parser.add_argument("--preregistration-sha256", required=True)
    parser.add_argument("--rclone-bin", required=True)
    for name in ("git", "fetch", "configure", "build", "launcher", "selector",
                 "barrier", "exec-verify", "producer", "filter", "outer"):
        parser.add_argument(f"--{name}-timeout-seconds", type=_positive, required=True)
    return parser.parse_args(argv)


def _run_publisher(args: argparse.Namespace) -> dict[str, Any]:
    """Production orchestration.  The control wrapper supplies every timeout pin."""
    if sys.platform != "linux":
        raise PublishError("publisher requires Linux")
    fixed_timeouts = {"barrier_timeout_seconds": 30,
                      "exec_verify_timeout_seconds": 30,
                      "producer_timeout_seconds": 413}
    if any(getattr(args, name) != expected for name, expected in fixed_timeouts.items()):
        raise PublishError("measured launcher timeout pin mismatch")
    repo = args.repo_root.resolve(strict=True)
    scratch = args.scratch_dir
    artifacts = args.artifact_dir
    if scratch.exists() or scratch.is_symlink():
        raise PublishError("scratch directory must be absent")
    scratch.mkdir(parents=True)
    if artifacts.is_symlink():
        raise PublishError("artifact directory cannot be a symlink")
    if artifacts.exists():
        if not artifacts.is_dir():
            raise PublishError("artifact path is not a directory")
        entries = list(artifacts.iterdir())
        if len(entries) != 1 or entries[0].name != "runner-launch.json" \
                or entries[0].is_symlink() or not entries[0].is_file():
            raise PublishError("artifact directory must be new or contain only runner-launch.json")
    else:
        artifacts.mkdir(parents=True)
    runtime = validate_runtime(repo, args.git_timeout_seconds)
    implementation, prereg_raw = validate_git_provenance(
        repo, args.implementation_commit, args.preregistration_commit,
        args.preregistration_path, args.git_timeout_seconds, args.preregistration_sha256)
    operational_pins = extract_operational_pins(prereg_raw)
    for field in ("filter_timeout_seconds", "launcher_timeout_seconds", "outer_timeout_seconds"):
        if getattr(args, field) != operational_pins[field]:
            raise PublishError(f"CLI {field} differs from preregistration Y")
    prereg_path = artifacts / Path(args.preregistration_path).name
    _write_new(prereg_path, prereg_raw)
    preregistration = {"commit": args.preregistration_commit,
        "file": _descriptor(prereg_path, schema=PREREG_SCHEMA),
        "path": args.preregistration_path, "ancestor": True, "blobs_equal": True,
        "operational_pins": operational_pins}
    historical, historical_paths = fetch_source(repo, scratch, artifacts, "historical", HISTORICAL,
        [(remote, local) for remote, (local, _) in HISTORICAL["files"].items()],
        args.rclone_bin, args.fetch_timeout_seconds)
    for remote, path in historical_paths.items():
        if sha256_file(path) != HISTORICAL["files"][remote][1]:
            raise PublishError("historical payload SHA mismatch")
    curriculum_fetch, curriculum_paths = fetch_source(repo, scratch, artifacts, "curriculum", CURRICULUM,
        [(CURRICULUM["remote"], CURRICULUM["local"])], args.rclone_bin, args.fetch_timeout_seconds)
    curriculum_path = scratch / "curriculum.pjtw"
    curriculum_material = materialize_curriculum(curriculum_paths[CURRICULUM["remote"]], curriculum_path)
    curriculum = {**curriculum_fetch, **curriculum_material}
    build, jass, parent_filter, cache = build_source(repo, scratch, artifacts,
        args.configure_timeout_seconds, args.build_timeout_seconds)
    _copy_new(cache, artifacts / "CMakeCache.txt")
    _write_new(artifacts / "build-receipt.json", canonical_json_bytes(build))
    contract = repo / IMPLEMENTATION_PATHS[0]
    source_dir = scratch / "source"
    source_dir.mkdir(exist_ok=False)
    manifest = source_dir / "source-manifest.json"
    compiler_id = "GNU"
    compiler_version = runtime["cxx_version"]
    launcher = ["/usr/bin/python3", str(repo / "jobs/tools/adaptive_sibling_b2_source_launcher.py"),
        "--selection-contract", str(contract), "--jass-exe", str(jass),
        "--parent-filter-exe", str(parent_filter), "--curriculum", str(curriculum_path),
        "--cmake-cache", str(cache), "--code-sha", args.implementation_commit,
        "--build-type", "Release", "--compiler-id", compiler_id,
        "--compiler-version", compiler_version]
    for option in sorted(CMK_OPTIONS):
        launcher += ["--cmake-option", option]
    launcher += ["--output-dir", str(source_dir), "--manifest", str(manifest),
        "--barrier-timeout-seconds", str(args.barrier_timeout_seconds),
        "--exec-verify-timeout-seconds", str(args.exec_verify_timeout_seconds),
        "--producer-timeout-seconds", str(args.producer_timeout_seconds),
        "--filter-timeout-seconds", str(args.filter_timeout_seconds)]
    started = time.monotonic_ns()
    _run(launcher, timeout=args.launcher_timeout_seconds, cwd=repo,
         log=artifacts / "source-launcher.log", environment={})
    source_execution = {
        "duration_milliseconds": (time.monotonic_ns() - started) // 1_000_000,
        "log": _descriptor(artifacts / "source-launcher.log")}
    runtime["operational_timeouts_seconds"] = {
        key.removesuffix("_seconds"): getattr(args, key)
        for key in vars(args) if key.endswith("_timeout_seconds")}
    selector_outcome = run_selector_cli(repo, contract, source_dir,
        historical_paths["artefacts/historical-parent-canonical-union.txt"],
        historical_paths["artefacts/historical-parent-exclusion-manifest.json"],
        artifacts / "verified-historical.json", scratch / "selection",
        args.selector_timeout_seconds)
    technical_artifacts = {Path(args.preregistration_path).name,
        "verified-historical.json", "verified-curriculum.json",
        "fetch-historical.log", "fetch-curriculum.log", "cmake-configure.log",
        "cmake-build.log", "CMakeCache.txt", "build-receipt.json", "source-launcher.log"}
    result = publish_prepared(repo=repo, scratch=scratch, artifacts=artifacts,
        job_id=args.job_id, attempt_id=args.attempt_id, implementation=implementation,
        preregistration=preregistration, runtime=runtime, historical=historical,
        curriculum=curriculum, build=build, source_execution=source_execution,
        contract_path=contract, source_dir=source_dir,
        exclusion_union=historical_paths["artefacts/historical-parent-canonical-union.txt"],
        exclusion_manifest=historical_paths["artefacts/historical-parent-exclusion-manifest.json"],
        exclusion_receipt=artifacts / "verified-historical.json",
        selector_cli_outcome=selector_outcome,
        required_technical_artifacts=technical_artifacts)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    with _global_deadline(args.outer_timeout_seconds):
        return _run_publisher(args)


def main(argv: list[str] | None = None) -> int:
    try:
        with _termination_signals_as_errors():
            result = run(parse_args(argv))
    except (PublishError, ContractError, OSError, UnicodeError, csv.Error,
            struct.error, subprocess.SubprocessError) as exc:
        print(f"adaptive_sibling_b2_source_publish: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"kind": result["kind"], "receipt": str(result["receipt_path"])},
                     sort_keys=True, separators=(",", ":")))
    return 4 if result["kind"] == "support" else 0


if __name__ == "__main__":
    raise SystemExit(main())
