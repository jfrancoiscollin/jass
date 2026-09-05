#!/usr/bin/env python3
"""Prepare the 16 authenticated PR771 B2 source shards on Linux.

This program is an implementation component, not authorization to generate B2
data.  Its production CLI may only be invoked by the future reviewed and
preregistered wrapper.  It has no network access, teacher step, selection step,
label read, fitting path, or scientific parameter override.

Each producer is a direct forked child held behind a pipe barrier before exec.
The parent records one live /proc snapshot for all children, releases the
barrier, verifies the exact executable and argv after exec, and waits for each
recorded PID.  Only then are the fixed board/STM filters run per shard and the
source manifest accepted by adaptive_sibling_b2_select.validate_source_manifest.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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


SOURCE_SHARDS = 16
RAW_ROWS = 10_000
RECORD_SIZE = 38
SOURCE_SEED_BASE = 2_026_110_700
TIMEOUT_MAX_SECONDS = 86_400
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
LIVE_PROC_STATES = {"R", "S", "D", "T", "t", "W", "K", "P", "I"}
PROCESS_GROUP_TERM_SECONDS = 1.0
PROCESS_GROUP_KILL_SECONDS = 1.0


class LauncherError(RuntimeError):
    """A build, process, output, provenance, or manifest contract violation."""


@contextmanager
def _termination_signals_as_errors() -> Iterable[None]:
    previous: dict[int, Any] = {}
    handling = False

    def handle(signum: int, _frame: Any) -> None:
        nonlocal handling
        if handling:
            return
        handling = True
        raise LauncherError(f"launcher received termination signal {signum}")

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handle)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


@dataclass(frozen=True, slots=True)
class ProcSnapshot:
    pid: int
    state: str
    ppid: int
    starttime: int


@dataclass(frozen=True, slots=True)
class ProducerSpec:
    source_shard: int
    seed: int
    argv: tuple[str, ...]
    argv_sha256: str
    raw_name: str
    log_name: str
    launch_monotonic_ns: int


@dataclass(frozen=True, slots=True)
class ProducerResult:
    spec: ProducerSpec
    snapshot: ProcSnapshot
    duration_milliseconds: int


def _positive_timeout(text: str) -> int:
    if not text.isascii() or not text.isdigit() or text.startswith("0"):
        raise argparse.ArgumentTypeError("timeout must be a canonical positive integer")
    value = int(text)
    if not 1 <= value <= TIMEOUT_MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"timeout must be in 1..{TIMEOUT_MAX_SECONDS}")
    return value


def _nonempty(text: str) -> str:
    if not text or "\x00" in text or "\n" in text or "\r" in text:
        raise argparse.ArgumentTypeError("value must be a non-empty single-line string")
    return text


def _argv_sha256(argv: Iterable[str]) -> str:
    return sha256_bytes(canonical_json_bytes(list(argv)))


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).casefold()


def _read_proc_stat(pid: int) -> ProcSnapshot:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise LauncherError(f"cannot read /proc/{pid}/stat") from exc
    close = raw.rfind(")")
    if close < 2 or close + 2 >= len(raw):
        raise LauncherError(f"malformed /proc/{pid}/stat")
    fields = raw[close + 2:].split()
    if len(fields) < 20:
        raise LauncherError(f"short /proc/{pid}/stat")
    try:
        state = fields[0]
        ppid = int(fields[1])
        starttime = int(fields[19])
    except (ValueError, IndexError) as exc:
        raise LauncherError(f"invalid /proc/{pid}/stat fields") from exc
    if len(state) != 1 or ppid <= 0 or starttime <= 0:
        raise LauncherError(f"invalid /proc/{pid}/stat identity")
    return ProcSnapshot(pid=pid, state=state, ppid=ppid, starttime=starttime)


def _read_proc_cmdline(pid: int) -> list[bytes]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError as exc:
        raise LauncherError(f"cannot read /proc/{pid}/cmdline") from exc
    if not raw or not raw.endswith(b"\0"):
        raise LauncherError(f"invalid /proc/{pid}/cmdline")
    return raw[:-1].split(b"\0")


def _resolved_proc_exe(pid: int) -> Path:
    try:
        return Path(os.readlink(f"/proc/{pid}/exe")).resolve(strict=True)
    except OSError as exc:
        raise LauncherError(f"cannot read /proc/{pid}/exe") from exc


def _clean_environment(pass_names: list[str]) -> tuple[dict[str, str], list[str]]:
    if pass_names:
        raise LauncherError("producer and filter environment must be exactly empty")
    return {}, []


def _check_regular_file(path: Path, label: str, *, executable: bool = False) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LauncherError(f"missing {label}: {path}") from exc
    if not resolved.is_file():
        raise LauncherError(f"{label} is not a regular file: {resolved}")
    if executable and not os.access(resolved, os.X_OK):
        raise LauncherError(f"{label} is not executable: {resolved}")
    return resolved


def _expected_output_paths(output_dir: Path, manifest: Path) -> list[Path]:
    paths = [manifest, Path(str(manifest) + ".tmp")]
    for shard in range(SOURCE_SHARDS):
        paths.extend([
            output_dir / f"shard-{shard:02d}.jnnw",
            output_dir / f"shard-{shard:02d}.log",
            output_dir / f"shard-{shard:02d}.filtered.jnnw",
            output_dir / f"shard-{shard:02d}.filtered.tsv",
            output_dir / f"shard-{shard:02d}.filter-report.json",
        ])
    return paths


def _preflight_paths(inputs: list[Path], outputs: list[Path]) -> None:
    seen: dict[str, Path] = {}
    for path in [*inputs, *outputs]:
        key = _path_key(path)
        if key in seen:
            raise LauncherError(f"input/output path alias: {seen[key]} and {path}")
        seen[key] = path
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise LauncherError(f"refusing existing source output paths: {existing}")


def _producer_argv(jass: Path, curriculum: Path, shard: int) -> list[str]:
    seed = SOURCE_SEED_BASE + shard
    return [
        str(jass), "--gen-data-wdl", "10000", f"shard-{shard:02d}.jnnw",
        "4", "8", "260", str(seed), "--nnue", str(curriculum),
        "--wdl-zero-score", "--random-open-plies", "8", "--explore-eps", "8",
        "--explore-decay-plies", "60", "--pair-openings", "--drop-plycap",
    ]


def _filter_argv(parent_filter: Path, shard: int) -> list[str]:
    prefix = f"shard-{shard:02d}"
    return [
        str(parent_filter), f"{prefix}.jnnw", f"{prefix}.filtered.jnnw",
        f"{prefix}.filtered.tsv", f"{prefix}.filter-report.json", "9", "40", "2", "16",
    ]


def _snapshot_barrier(pids: list[int], launcher_pid: int, deadline: float) -> dict[int, ProcSnapshot]:
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            snapshots = {pid: _read_proc_stat(pid) for pid in pids}
            if len(snapshots) != SOURCE_SHARDS:
                raise LauncherError("barrier snapshot does not contain 16 children")
            if len(set(snapshots)) != SOURCE_SHARDS:
                raise LauncherError("barrier PIDs are not unique")
            identities = {(item.pid, item.starttime) for item in snapshots.values()}
            if len(identities) != SOURCE_SHARDS:
                raise LauncherError("barrier PID/starttime identities are not unique")
            if any(item.ppid != launcher_pid for item in snapshots.values()):
                raise LauncherError("barrier child is not a direct launcher child")
            if any(os.getpgid(item.pid) != item.pid for item in snapshots.values()):
                raise LauncherError("barrier child is not leader of its own process group")
            if any(item.state not in LIVE_PROC_STATES for item in snapshots.values()):
                raise LauncherError("barrier contains a dead or zombie child")
            return snapshots
        except LauncherError as exc:
            last_error = exc
            time.sleep(0.005)
    raise LauncherError(f"producer barrier did not become valid: {last_error}")


def _verify_post_exec(
    specs: dict[int, ProducerSpec], jass: Path, jass_sha256: str, deadline: float
) -> None:
    pending = set(specs)
    expected_exe = jass.resolve(strict=True)
    while pending and time.monotonic() < deadline:
        progressed = False
        for pid in list(pending):
            try:
                actual_exe = _resolved_proc_exe(pid)
                actual_argv = _read_proc_cmdline(pid)
            except LauncherError:
                continue
            expected_argv = [os.fsencode(token) for token in specs[pid].argv]
            if (
                actual_exe == expected_exe
                and sha256_file(actual_exe) == jass_sha256
                and actual_argv == expected_argv
            ):
                pending.remove(pid)
                progressed = True
        if pending and not progressed:
            time.sleep(0.005)
    if pending:
        raise LauncherError(f"post-exec executable/argv verification failed for PIDs {sorted(pending)}")


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _reap_direct_children(pids: set[int]) -> None:
    for pid in list(pids):
        try:
            waited, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pids.remove(pid)
            continue
        if waited == pid:
            pids.remove(pid)


def _signal_groups(pgids: set[int], sig: int) -> None:
    own_group = os.getpgrp()
    for pgid in pgids:
        if pgid <= 0 or pgid == own_group:
            raise LauncherError("refusing to signal launcher process group")
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass


def _wait_groups_gone(pgids: set[int], children: set[int], deadline: float) -> set[int]:
    while time.monotonic() < deadline:
        _reap_direct_children(children)
        remaining_groups = {pgid for pgid in pgids if _process_group_exists(pgid)}
        if not remaining_groups and not children:
            return set()
        time.sleep(0.01)
    _reap_direct_children(children)
    return {pgid for pgid in pgids if _process_group_exists(pgid)}


def _terminate_process_groups(pids: Iterable[int]) -> None:
    pgids = set(pids)
    children = set(pgids)
    if not pgids:
        return
    _signal_groups(pgids, signal.SIGTERM)
    remaining_groups = _wait_groups_gone(
        pgids, children, time.monotonic() + PROCESS_GROUP_TERM_SECONDS
    )
    if remaining_groups:
        _signal_groups(remaining_groups, signal.SIGKILL)
    remaining_groups = _wait_groups_gone(
        pgids, children, time.monotonic() + PROCESS_GROUP_KILL_SECONDS
    )
    if remaining_groups or children:
        raise LauncherError(
            f"process-group cleanup failed: groups={sorted(remaining_groups)} "
            f"children={sorted(children)}"
        )


def _terminate_popen_process_group(process: subprocess.Popen[bytes]) -> None:
    pgid = process.pid
    try:
        _signal_groups({pgid}, signal.SIGTERM)
        try:
            process.wait(timeout=PROCESS_GROUP_TERM_SECONDS)
        except subprocess.TimeoutExpired:
            _signal_groups({pgid}, signal.SIGKILL)
            try:
                process.wait(timeout=PROCESS_GROUP_KILL_SECONDS)
            except subprocess.TimeoutExpired as exc:
                raise LauncherError(f"process-group leader {pgid} did not terminate") from exc
        if _process_group_exists(pgid):
            _signal_groups({pgid}, signal.SIGKILL)
            deadline = time.monotonic() + PROCESS_GROUP_KILL_SECONDS
            while _process_group_exists(pgid) and time.monotonic() < deadline:
                time.sleep(0.01)
            if _process_group_exists(pgid):
                raise LauncherError(f"process group {pgid} still exists after SIGKILL")
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def _wait_exact_children(
    specs: dict[int, ProducerSpec], snapshots: dict[int, ProcSnapshot], deadline: float
) -> list[ProducerResult]:
    pending = set(specs)
    statuses: dict[int, int] = {}
    ended_ns: dict[int, int] = {}
    while pending and time.monotonic() < deadline:
        for pid in list(pending):
            try:
                waited, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError as exc:
                raise LauncherError(f"producer PID {pid} is no longer an exact child") from exc
            if waited == pid:
                statuses[pid] = os.waitstatus_to_exitcode(status)
                ended_ns[pid] = time.monotonic_ns()
                pending.remove(pid)
        if pending:
            time.sleep(0.01)
    if pending:
        raise LauncherError(f"producer deadline exceeded for PIDs {sorted(pending)}")
    failures = {pid: code for pid, code in statuses.items() if code != 0}
    if failures:
        raise LauncherError(f"producer exit codes are nonzero: {failures}")
    lingering = {pid for pid in specs if _process_group_exists(pid)}
    if lingering:
        _terminate_process_groups(lingering)
        raise LauncherError(f"producer left descendant processes: {sorted(lingering)}")
    return [
        ProducerResult(
            spec=specs[pid], snapshot=snapshots[pid],
            duration_milliseconds=max(0, (ended_ns[pid] - specs[pid].launch_monotonic_ns) // 1_000_000),
        )
        for pid in sorted(specs, key=lambda item: specs[item].source_shard)
    ]


def launch_producers(
    *, jass: Path, jass_sha256: str, curriculum: Path, output_dir: Path,
    environment: dict[str, str],
    barrier_timeout_seconds: int, exec_verify_timeout_seconds: int,
    producer_timeout_seconds: int,
) -> list[ProducerResult]:
    if sys.platform != "linux" or not hasattr(os, "fork"):
        raise LauncherError("the 16-process /proc barrier requires Linux")
    pipes = [os.pipe() for _ in range(SOURCE_SHARDS)]
    specs: dict[int, ProducerSpec] = {}
    pids: list[int] = []
    launcher_pid = os.getpid()
    try:
        for shard in range(SOURCE_SHARDS):
            argv = _producer_argv(jass, curriculum, shard)
            launch_ns = time.monotonic_ns()
            pid = os.fork()
            if pid == 0:  # pragma: no cover - child is observed through its receipt/output
                try:
                    os.setpgid(0, 0)
                    read_fd = pipes[shard][0]
                    for candidate_read, candidate_write in pipes:
                        if candidate_read != read_fd:
                            os.close(candidate_read)
                        os.close(candidate_write)
                    os.chdir(output_dir)
                    log_fd = os.open(
                        f"shard-{shard:02d}.log",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                    )
                    os.dup2(log_fd, 1)
                    os.dup2(log_fd, 2)
                    if log_fd > 2:
                        os.close(log_fd)
                    released = os.read(read_fd, 1)
                    os.close(read_fd)
                    if released != b"G":
                        os._exit(126)
                    os.execve(str(jass), argv, environment)
                except BaseException as exc:
                    try:
                        os.write(2, f"pre-exec failure: {exc}\n".encode("utf-8", "replace"))
                    except OSError:
                        pass
                    os._exit(127)
            pids.append(pid)
            os.setpgid(pid, pid)
            specs[pid] = ProducerSpec(
                source_shard=shard,
                seed=SOURCE_SEED_BASE + shard,
                argv=tuple(argv),
                argv_sha256=_argv_sha256(argv),
                raw_name=f"shard-{shard:02d}.jnnw",
                log_name=f"shard-{shard:02d}.log",
                launch_monotonic_ns=launch_ns,
            )
        for read_fd, _ in pipes:
            os.close(read_fd)
        snapshots = _snapshot_barrier(
            pids, launcher_pid, time.monotonic() + barrier_timeout_seconds
        )
        release_ns = time.monotonic_ns()
        for _, write_fd in pipes:
            os.write(write_fd, b"G")
            os.close(write_fd)
        _verify_post_exec(
            specs, jass, jass_sha256, time.monotonic() + exec_verify_timeout_seconds
        )
        results = _wait_exact_children(
            specs, snapshots, release_ns / 1_000_000_000 + producer_timeout_seconds
        )
        return results
    except BaseException:
        for read_fd, write_fd in pipes:
            for descriptor in (read_fd, write_fd):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        _terminate_process_groups(pids)
        raise


def _validate_raw_jnnw(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(8)
    except OSError as exc:
        raise LauncherError(f"cannot read producer output {path}") from exc
    if len(header) != 8 or header[:4] != b"JNNW":
        raise LauncherError(f"producer output has bad JNNW header: {path.name}")
    count = struct.unpack_from("<I", header, 4)[0]
    expected_size = 8 + RAW_ROWS * RECORD_SIZE
    if count != RAW_ROWS or size != expected_size:
        raise LauncherError(
            f"producer output count/size mismatch: {path.name} count={count} size={size}"
        )
    return {
        "local_name": path.name,
        "sha256": sha256_file(path),
        "size_bytes": size,
        "magic": "JNNW",
        "header_count": count,
        "record_size_bytes": RECORD_SIZE,
        "trailing_bytes": 0,
    }


def _counted_jnnw_rows(path: Path) -> int:
    try:
        with path.open("rb") as stream:
            header = stream.read(8)
    except OSError as exc:
        raise LauncherError(f"cannot read counted JNNW {path}") from exc
    if len(header) != 8 or header[:4] != b"JNNW":
        raise LauncherError(f"invalid counted JNNW {path}")
    count = struct.unpack_from("<I", header, 4)[0]
    if path.stat().st_size != 8 + count * RECORD_SIZE:
        raise LauncherError(f"counted JNNW size mismatch {path}")
    return count


def _file_descriptor(path: Path, *, allow_empty: bool = False) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LauncherError(f"missing output file: {path}") from exc
    if size < (0 if allow_empty else 1):
        raise LauncherError(f"empty output file: {path}")
    return {"local_name": path.name, "sha256": sha256_file(path), "size_bytes": size}


def run_filters(
    *, parent_filter: Path, output_dir: Path, environment: dict[str, str],
    filter_timeout_seconds: int,
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    process: subprocess.Popen[bytes] | None = None
    try:
        for shard in range(SOURCE_SHARDS):
            argv = _filter_argv(parent_filter, shard)
            started = time.monotonic_ns()
            process = subprocess.Popen(
                argv, cwd=output_dir, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            try:
                _stdout, stderr = process.communicate(timeout=filter_timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise LauncherError(f"parent filter timeout for shard {shard}") from exc
            if _process_group_exists(process.pid):
                raise LauncherError(f"parent filter shard {shard} left descendant processes")
            duration_ms = max(0, (time.monotonic_ns() - started) // 1_000_000)
            if process.returncode != 0:
                stderr_tail = stderr.decode("utf-8", "replace")[-2000:]
                raise LauncherError(f"parent filter shard {shard} exit {process.returncode}: {stderr_tail}")
            prefix = output_dir / f"shard-{shard:02d}"
            jnnw = Path(str(prefix) + ".filtered.jnnw")
            meta = Path(str(prefix) + ".filtered.tsv")
            report = Path(str(prefix) + ".filter-report.json")
            candidates, declared = selector._load_filtered_shard(jnnw, meta, shard)
            if len(candidates) != declared:
                raise LauncherError(f"filter shard {shard} candidate count mismatch")
            selector._load_filter_report(report, f"shard-{shard:02d}.jnnw", declared)
            receipts.append({
                "argv": argv,
                "argv_sha256": _argv_sha256(argv),
                "duration_milliseconds": duration_ms,
                "exit_code": 0,
                "filtered_jnnw": _file_descriptor(jnnw),
                "filtered_meta": _file_descriptor(meta),
                "report": _file_descriptor(report),
            })
            process = None
        return receipts
    except BaseException:
        if process is not None and (
            process.returncode is None or _process_group_exists(process.pid)
        ):
            _terminate_popen_process_group(process)
        raise


def build_manifest(
    *, contract: dict[str, Any], contract_raw: bytes, code_sha: str,
    build_type: str, cmake_cache_sha256: str, cmake_options: list[str],
    compiler_id: str, compiler_version: str, curriculum: Path,
    curriculum_sha256: str, jass: Path, jass_sha256: str, parent_filter: Path,
    parent_filter_sha256: str, transmitted_names: list[str], launcher_pid: int,
    output_dir: Path, producers: list[ProducerResult], filters: list[dict[str, Any]],
    raw_descriptors: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if len(producers) != SOURCE_SHARDS or len(filters) != SOURCE_SHARDS:
        raise LauncherError("manifest requires exactly 16 producer/filter receipts")
    producer_by_shard = {item.spec.source_shard: item for item in producers}
    if set(producer_by_shard) != set(range(SOURCE_SHARDS)):
        raise LauncherError("producer shard receipt set is incomplete")
    if set(raw_descriptors) != set(range(SOURCE_SHARDS)):
        raise LauncherError("raw source descriptor set is incomplete")
    shards = []
    raw_hashes: set[str] = set()
    for shard in range(SOURCE_SHARDS):
        result = producer_by_shard[shard]
        raw = raw_descriptors[shard]
        current_raw = _validate_raw_jnnw(output_dir / result.spec.raw_name)
        if current_raw != raw:
            raise LauncherError(f"raw source shard {shard} changed during filtering")
        if raw["sha256"] in raw_hashes:
            raise LauncherError("duplicate raw source shard SHA")
        raw_hashes.add(raw["sha256"])
        log = _file_descriptor(output_dir / result.spec.log_name, allow_empty=True)
        filter_receipt = dict(filters[shard])
        for descriptor_name in ("filtered_jnnw", "filtered_meta", "report"):
            descriptor = filter_receipt[descriptor_name]
            current = _file_descriptor(output_dir / descriptor["local_name"])
            if current != descriptor:
                raise LauncherError(
                    f"filter shard {shard} {descriptor_name} changed before manifest publication"
                )
        filter_receipt["source_jnnw_sha256"] = raw["sha256"]
        shards.append({
            "source_shard": shard,
            "seed": result.spec.seed,
            "producer": {
                "argv": list(result.spec.argv),
                "argv_sha256": result.spec.argv_sha256,
                "duration_milliseconds": result.duration_milliseconds,
                "exit_code": 0,
                "launch_monotonic_ns": result.spec.launch_monotonic_ns,
                "log": log,
                "pid": result.snapshot.pid,
                "post_exec": {
                    "argv_sha256": result.spec.argv_sha256,
                    "executable_sha256": jass_sha256,
                    "resolved_executable": str(jass),
                    "verified": True,
                },
                "ppid": result.snapshot.ppid,
                "proc_starttime": result.snapshot.starttime,
                "process_state": result.snapshot.state,
                "raw_jnnw": raw,
            },
            "filter": filter_receipt,
        })
    manifest = {
        "schema": selector.SOURCE_MANIFEST_SCHEMA,
        "selection_contract_sha256": sha256_bytes(contract_raw),
        "build": {
            "build_type": build_type,
            "cmake_cache_sha256": cmake_cache_sha256,
            "cmake_options": cmake_options,
            "code_sha": code_sha,
            "compiler_id": compiler_id,
            "compiler_version": compiler_version,
        },
        "curriculum": {"resolved_path": str(curriculum), "sha256": curriculum_sha256},
        "jass_executable": {"resolved_path": str(jass), "sha256": jass_sha256},
        "parent_filter_executable": {
            "resolved_path": str(parent_filter), "sha256": parent_filter_sha256,
        },
        "producer_environment": {
            "egdb_source": "none",
            "jass_prefixed_environment": [],
            "required_absent": selector.REQUIRED_ABSENT_ENV,
            "transmitted_names": transmitted_names,
        },
        "producer_barrier": {
            "alive_barrier_count": SOURCE_SHARDS,
            "child_count": SOURCE_SHARDS,
            "child_exec_preserves_pid": True,
            "distinct_identity": ["pid", "proc_starttime"],
            "direct_child_ppid_required": True,
            "launcher_pid": launcher_pid,
            "non_zombie_required": True,
            "passed": True,
            "records_per_child": RAW_ROWS,
            "seeds": "2026110700+source_shard",
            "unique_pids_at_barrier": True,
        },
        "shards": shards,
    }
    # The selector's parser is the normative consumer of this manifest.
    if manifest["selection_contract_sha256"] != sha256_bytes(canonical_json_bytes(contract)):
        raise LauncherError("contract bytes are not canonical")
    return manifest


def _run(args: argparse.Namespace, *, contract_override: dict[str, Any] | None = None) -> dict[str, Any]:
    if sys.platform != "linux":
        raise LauncherError("adaptive_sibling_b2_source_launcher requires Linux")
    output_dir = args.output_dir.resolve(strict=True)
    if not output_dir.is_dir():
        raise LauncherError("--output-dir must be an existing directory")
    manifest_path = args.manifest.resolve(strict=False)
    if manifest_path.parent != output_dir or manifest_path.name != "source-manifest.json":
        raise LauncherError("--manifest must be OUTPUT_DIR/source-manifest.json")
    if contract_override is None:
        contract, contract_raw = selector.load_contract(args.selection_contract)
    else:
        contract = contract_override
        contract_raw = canonical_json_bytes(contract)
    jass = _check_regular_file(args.jass_exe, "jass executable", executable=True)
    parent_filter = _check_regular_file(args.parent_filter_exe, "parent filter executable", executable=True)
    curriculum = _check_regular_file(args.curriculum, "CURRICULUM")
    cmake_cache = _check_regular_file(args.cmake_cache, "CMake cache")
    expected_curriculum_sha = contract["curriculum"]["decompressed_sha256"]
    curriculum_sha = sha256_file(curriculum)
    if curriculum_sha != expected_curriculum_sha:
        raise LauncherError("CURRICULUM decompressed-byte SHA mismatch")
    if not isinstance(args.code_sha, str) or not GIT_SHA_RE.fullmatch(args.code_sha):
        raise LauncherError("--code-sha must be a lowercase 40-hex commit")
    options = list(args.cmake_option)
    if options != sorted(set(options)) or any(not option for option in options):
        raise LauncherError("--cmake-option values must be non-empty, sorted, and unique")
    environment, transmitted_names = _clean_environment([])
    outputs = _expected_output_paths(output_dir, manifest_path)
    _preflight_paths(
        [args.selection_contract, jass, parent_filter, curriculum, cmake_cache], outputs
    )
    jass_sha = sha256_file(jass)
    filter_sha = sha256_file(parent_filter)
    cache_sha = sha256_file(cmake_cache)
    producers = launch_producers(
        jass=jass,
        jass_sha256=jass_sha,
        curriculum=curriculum,
        output_dir=output_dir,
        environment=environment,
        barrier_timeout_seconds=args.barrier_timeout_seconds,
        exec_verify_timeout_seconds=args.exec_verify_timeout_seconds,
        producer_timeout_seconds=args.producer_timeout_seconds,
    )
    # Validate all producer files before starting the filters.
    raw_descriptors = {
        result.spec.source_shard: _validate_raw_jnnw(output_dir / result.spec.raw_name)
        for result in producers
    }
    filters = run_filters(
        parent_filter=parent_filter,
        output_dir=output_dir,
        environment=environment,
        filter_timeout_seconds=args.filter_timeout_seconds,
    )
    stable_inputs = {
        "jass executable": (jass, jass_sha),
        "parent filter executable": (parent_filter, filter_sha),
        "CURRICULUM": (curriculum, curriculum_sha),
        "CMake cache": (cmake_cache, cache_sha),
    }
    for label, (path, expected_sha) in stable_inputs.items():
        if sha256_file(path) != expected_sha:
            raise LauncherError(f"{label} changed during source preparation")
    if contract_override is None and args.selection_contract.read_bytes() != contract_raw:
        raise LauncherError("selection contract changed during source preparation")
    manifest = build_manifest(
        contract=contract,
        contract_raw=contract_raw,
        code_sha=args.code_sha,
        build_type=args.build_type,
        cmake_cache_sha256=cache_sha,
        cmake_options=options,
        compiler_id=args.compiler_id,
        compiler_version=args.compiler_version,
        curriculum=curriculum,
        curriculum_sha256=curriculum_sha,
        jass=jass,
        jass_sha256=jass_sha,
        parent_filter=parent_filter,
        parent_filter_sha256=filter_sha,
        transmitted_names=transmitted_names,
        launcher_pid=os.getpid(),
        output_dir=output_dir,
        producers=producers,
        filters=filters,
        raw_descriptors=raw_descriptors,
    )
    temporary = Path(str(manifest_path) + ".tmp")
    raw = canonical_json_bytes(manifest)
    try:
        temporary.write_bytes(raw)
        parsed, parsed_raw = selector.validate_source_manifest(temporary, contract)
        if parsed != manifest or parsed_raw != raw:
            raise LauncherError("source manifest parser roundtrip mismatch")
        os.replace(temporary, manifest_path)
        final, final_raw = selector.validate_source_manifest(manifest_path, contract)
        if final != manifest or final_raw != raw:
            raise LauncherError("published source manifest roundtrip mismatch")
    except BaseException:
        temporary.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    return {
        "schema": selector.SOURCE_MANIFEST_SCHEMA,
        "manifest_sha256": sha256_bytes(raw),
        "source_shards": SOURCE_SHARDS,
        "raw_records": SOURCE_SHARDS * RAW_ROWS,
        "filtered_records": sum(
            _counted_jnnw_rows(output_dir / item["filtered_jnnw"]["local_name"])
            for item in filters
        ),
        "authorization": "IMPLEMENTATION_ONLY_REQUIRES_FUTURE_PREREGISTERED_WRAPPER",
    }


def run(args: argparse.Namespace, *, contract_override: dict[str, Any] | None = None) -> dict[str, Any]:
    with _termination_signals_as_errors():
        return _run(args, contract_override=contract_override)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-contract", type=Path, required=True)
    parser.add_argument("--jass-exe", type=Path, required=True)
    parser.add_argument("--parent-filter-exe", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--cmake-cache", type=Path, required=True)
    parser.add_argument("--code-sha", type=_nonempty, required=True)
    parser.add_argument("--build-type", type=_nonempty, required=True)
    parser.add_argument("--compiler-id", type=_nonempty, required=True)
    parser.add_argument("--compiler-version", type=_nonempty, required=True)
    parser.add_argument("--cmake-option", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--barrier-timeout-seconds", type=_positive_timeout, required=True)
    parser.add_argument("--exec-verify-timeout-seconds", type=_positive_timeout, required=True)
    parser.add_argument("--producer-timeout-seconds", type=_positive_timeout, required=True)
    parser.add_argument("--filter-timeout-seconds", type=_positive_timeout, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parse_args(argv))
    except (LauncherError, ContractError, OSError, subprocess.SubprocessError) as exc:
        print(f"adaptive_sibling_b2_source_launcher: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
