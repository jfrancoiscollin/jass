#!/usr/bin/env python3
"""Launch-V2 Python entrypoint for the frozen CLS-L normalization shell stage.

Launch-V2 fingerprints its command interpreter as the numerical runtime. The
scientific stage itself remains the existing frozen shell template; this thin
entrypoint exists so the gate fingerprints /usr/bin/python3 rather than trying
to execute Python runtime-identification code through /usr/bin/bash.

``run_experiment_stage.py`` deliberately sanitizes the stage environment, so an
outer runner's ``EXPECTED_CODE_SHA`` is not propagated.  The historical shell
still consumes that variable as a defence-in-depth assertion.  Reconstruct it
only from the already-authenticated ``JASS_STAGE_SPEC``, verify it against HEAD,
then exec the frozen shell.

The persistent Level-3 numeric venv is host tooling, not a scientific input.  A
2029 bounded diagnostic proved that its NumPy import was malformed (the imported
module had no ``ndarray``).  The follow-up 2033 stage-log diagnostic then proved
a narrower host-compatibility failure: the current /usr/bin/python3 package
index has no binary wheel for the historical NumPy 1.26.4 pin.  Preserve the
historical pair whenever it is installable; only that exact non-zero pip failure
may select a current-compatible NumPy/SciPy pair.  The first compatible pair is
immediately frozen in a host-tooling lock and any later repair must reinstall
that exact pair rather than re-resolve it.  This happens before any scientific
source is read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "jobs" / "templates" / "l3-cls-l-source-normalization-preflight-v1.sh"
SHA40_RE = re.compile(r"[0-9a-f]{40}\Z")
VERSION_RE = re.compile(r"[0-9][0-9A-Za-z.+_-]*\Z")
DEFAULT_NUMERIC_VENV = Path("/var/tmp/jass-l3-numeric-venv-current-v1")
# Tooling pins already used by the Level-3 training/preflight runtime; they are
# not a CLS-L scientific axis and remain the first-choice repair stack.
NUMPY_PIN = "1.26.4"
SCIPY_PIN = "1.14.1"
RUNTIME_LOCK_SCHEMA = "jass.cls_l_numeric_runtime_lock.v1"
NUMERIC_PROBE = (
    "import numpy as np; "
    "from scipy import sparse; "
    "from scipy.optimize import minimize; "
    "assert hasattr(np, 'ndarray') and hasattr(np, 'asarray') and hasattr(np, 'dtype'); "
    "assert hasattr(sparse, 'hstack'); "
    "assert callable(minimize)"
)


def authenticated_code_sha() -> str:
    raw_path = os.environ.get("JASS_STAGE_SPEC")
    if not raw_path:
        raise RuntimeError("JASS_STAGE_SPEC missing")
    path = Path(raw_path)
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"CLS-L stage spec unreadable: {exc}") from exc
    sha = value.get("code_sha") if isinstance(value, dict) else None
    if not isinstance(sha, str) or SHA40_RE.fullmatch(sha) is None:
        raise RuntimeError("CLS-L stage spec code_sha missing/invalid")
    head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
    ).strip()
    if head != sha:
        raise RuntimeError(f"CLS-L stage/spec code mismatch: head={head} spec={sha}")
    return sha


def numeric_runtime_healthy(venv: Path) -> bool:
    python = venv / "bin" / "python"
    if not python.is_file():
        return False
    try:
        subprocess.run(
            [str(python), "-c", NUMERIC_PROBE],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def runtime_lock_path(venv: Path) -> Path:
    return venv.with_name(f"{venv.name}.cls-l-runtime-lock.json")


def read_runtime_lock(venv: Path) -> tuple[str, str] | None:
    path = runtime_lock_path(venv)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"CLS-L numeric runtime lock unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != RUNTIME_LOCK_SCHEMA:
        raise RuntimeError("CLS-L numeric runtime lock schema mismatch")
    numpy_version = value.get("numpy")
    scipy_version = value.get("scipy")
    if (
        not isinstance(numpy_version, str)
        or VERSION_RE.fullmatch(numpy_version) is None
        or not isinstance(scipy_version, str)
        or VERSION_RE.fullmatch(scipy_version) is None
    ):
        raise RuntimeError("CLS-L numeric runtime lock versions invalid")
    return numpy_version, scipy_version


def write_runtime_lock(venv: Path, numpy_version: str, scipy_version: str) -> None:
    if VERSION_RE.fullmatch(numpy_version) is None or VERSION_RE.fullmatch(scipy_version) is None:
        raise RuntimeError("CLS-L resolved numeric versions invalid")
    path = runtime_lock_path(venv)
    payload = {
        "schema": RUNTIME_LOCK_SCHEMA,
        "source": "current-compatible-after-historical-unavailable",
        "numpy": numpy_version,
        "scipy": scipy_version,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="ascii")
    tmp.replace(path)


def resolved_numeric_versions(venv: Path) -> tuple[str, str]:
    python = venv / "bin" / "python"
    raw = subprocess.check_output(
        [
            str(python),
            "-c",
            "import json,numpy,scipy; print(json.dumps({'numpy': numpy.__version__, 'scipy': scipy.__version__}, sort_keys=True))",
        ],
        text=True,
        timeout=30,
    )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CLS-L numeric runtime version probe returned invalid JSON") from exc
    numpy_version = value.get("numpy") if isinstance(value, dict) else None
    scipy_version = value.get("scipy") if isinstance(value, dict) else None
    if (
        not isinstance(numpy_version, str)
        or VERSION_RE.fullmatch(numpy_version) is None
        or not isinstance(scipy_version, str)
        or VERSION_RE.fullmatch(scipy_version) is None
    ):
        raise RuntimeError("CLS-L numeric runtime version probe returned invalid versions")
    return numpy_version, scipy_version


def clear_numeric_venv(venv: Path) -> None:
    subprocess.run(
        ["/usr/bin/python3", "-m", "venv", "--clear", str(venv)],
        check=True,
        timeout=120,
    )


def install_numeric_stack(venv: Path, requirements: list[str]) -> None:
    python = venv / "bin" / "python"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            *requirements,
        ],
        check=True,
        timeout=900,
    )


def ensure_numeric_runtime() -> Path:
    """Return a healthy numeric venv, repairing only proven host-tooling faults."""
    venv = Path(os.environ.get("JASS_L3_NUMERIC_VENV", str(DEFAULT_NUMERIC_VENV)))
    if numeric_runtime_healthy(venv):
        return venv

    locked = read_runtime_lock(venv)
    clear_numeric_venv(venv)
    if locked is not None:
        numpy_version, scipy_version = locked
        install_numeric_stack(
            venv,
            [f"numpy=={numpy_version}", f"scipy=={scipy_version}"],
        )
        if not numeric_runtime_healthy(venv):
            raise RuntimeError("CLS-L locked numeric runtime did not produce required NumPy/SciPy API")
        return venv

    try:
        install_numeric_stack(
            venv,
            [f"numpy=={NUMPY_PIN}", f"scipy=={SCIPY_PIN}"],
        )
    except subprocess.CalledProcessError:
        # 2033 proves exactly this failure mode on CPX62: binary resolution of
        # NumPy 1.26.4 fails under the current /usr/bin/python3.  Resolve one
        # compatible pair once, validate it, and immediately freeze its exact
        # versions for all later repairs on this host.
        clear_numeric_venv(venv)
        install_numeric_stack(venv, ["numpy", "scipy"])
        if not numeric_runtime_healthy(venv):
            raise RuntimeError("CLS-L compatible numeric runtime lacks required NumPy/SciPy API")
        numpy_version, scipy_version = resolved_numeric_versions(venv)
        write_runtime_lock(venv, numpy_version, scipy_version)
        return venv

    if not numeric_runtime_healthy(venv):
        raise RuntimeError("CLS-L historical numeric runtime lacks required NumPy/SciPy API")
    return venv


def main() -> int:
    if not SCRIPT.is_file():
        raise FileNotFoundError(SCRIPT)
    os.environ["EXPECTED_CODE_SHA"] = authenticated_code_sha()
    os.environ["JASS_L3_NUMERIC_VENV"] = str(ensure_numeric_runtime())
    os.execv("/usr/bin/bash", ["/usr/bin/bash", str(SCRIPT)])
    return 127  # pragma: no cover - execv replaces the process on success.


if __name__ == "__main__":
    raise SystemExit(main())
