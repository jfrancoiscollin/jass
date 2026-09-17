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
module had no ``ndarray``).  Validate the complete numeric API needed by the
normalization and later fit path before any scientific source is read; only when
that tooling probe fails, rebuild the same venv with the repository's historical
numeric stack pins.
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
DEFAULT_NUMERIC_VENV = Path("/var/tmp/jass-l3-numeric-venv-current-v1")
NUMPY_PIN = "1.26.4"
SCIPY_PIN = "1.14.1"
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


def ensure_numeric_runtime() -> Path:
    """Return a healthy numeric venv, repairing only a failed tooling probe."""
    venv = Path(os.environ.get("JASS_L3_NUMERIC_VENV", str(DEFAULT_NUMERIC_VENV)))
    if numeric_runtime_healthy(venv):
        return venv

    subprocess.run(
        ["/usr/bin/python3", "-m", "venv", "--clear", str(venv)],
        check=True,
        timeout=120,
    )
    python = venv / "bin" / "python"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            f"numpy=={NUMPY_PIN}",
            f"scipy=={SCIPY_PIN}",
        ],
        check=True,
        timeout=900,
    )
    if not numeric_runtime_healthy(venv):
        raise RuntimeError("CLS-L numeric runtime repair did not produce required NumPy/SciPy API")
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
