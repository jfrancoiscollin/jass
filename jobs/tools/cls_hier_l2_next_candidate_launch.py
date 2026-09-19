#!/usr/bin/env python3
"""Launch-V2 entrypoint for the prospectively frozen CLS HIER-L2 candidate.

2054 observed that the repaired CONTROL reproduction was still using a newer
NumPy/SciPy pair than the adjacent historical CPX runtime witness, and terminal
zero-effect diagnostic 2055 proved runner-managed continuity of the historical
persistent numeric venv from 1340 through the authoritative 1341 fit.  CONTROL
replay therefore uses a dedicated, fail-closed runtime containing exactly those
historical package versions.  There is deliberately no compatible-latest fallback:
a wheel/install failure is technical evidence and must not mutate the scientific
recipe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.cls_l_source_normalization_preflight_launch import authenticated_code_sha

SCRIPT = ROOT / "jobs" / "templates" / "l3-cls-hier-l2-next-candidate-v1.sh"
HISTORICAL_NUMPY = "2.5.2"
HISTORICAL_SCIPY = "1.18.0"
DEFAULT_HISTORICAL_VENV = Path("/var/tmp/jass-cls-hier-l2-historical-1340-v1")
NUMERIC_PROBE = (
    "import numpy as np; "
    "from scipy import sparse; "
    "from scipy.optimize import minimize; "
    "assert hasattr(np, 'ndarray') and hasattr(np, 'asarray') and hasattr(np, 'dtype'); "
    "assert hasattr(sparse, 'hstack'); "
    "assert callable(minimize)"
)


def historical_runtime_versions(venv: Path) -> tuple[str, str]:
    python = venv / "bin" / "python"
    raw = subprocess.check_output(
        [
            str(python),
            "-c",
            "import json,numpy,scipy; print(json.dumps({'numpy':numpy.__version__,'scipy':scipy.__version__},sort_keys=True))",
        ],
        text=True,
        timeout=30,
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("HIER-L2 historical runtime version probe returned non-object")
    numpy_version = value.get("numpy")
    scipy_version = value.get("scipy")
    if not isinstance(numpy_version, str) or not isinstance(scipy_version, str):
        raise RuntimeError("HIER-L2 historical runtime version probe missing versions")
    return numpy_version, scipy_version


def historical_runtime_healthy(venv: Path) -> bool:
    python = venv / "bin" / "python"
    if not python.is_file():
        return False
    try:
        versions = historical_runtime_versions(venv)
        if versions != (HISTORICAL_NUMPY, HISTORICAL_SCIPY):
            return False
        subprocess.run(
            [str(python), "-c", NUMERIC_PROBE],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError, RuntimeError):
        return False
    return True


def rebuild_historical_runtime(venv: Path) -> None:
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
            f"numpy=={HISTORICAL_NUMPY}",
            f"scipy=={HISTORICAL_SCIPY}",
        ],
        check=True,
        timeout=900,
    )


def ensure_historical_numeric_runtime() -> Path:
    """Return an exact 1340/1341 NumPy/SciPy runtime or fail closed."""
    venv = Path(
        os.environ.get(
            "JASS_CLS_HIER_HISTORICAL_NUMERIC_VENV",
            str(DEFAULT_HISTORICAL_VENV),
        )
    )
    if historical_runtime_healthy(venv):
        return venv
    rebuild_historical_runtime(venv)
    if not historical_runtime_healthy(venv):
        got = None
        try:
            got = historical_runtime_versions(venv)
        except Exception:
            pass
        raise RuntimeError(
            "HIER-L2 exact historical numeric runtime unavailable: "
            f"wanted={(HISTORICAL_NUMPY, HISTORICAL_SCIPY)} got={got}"
        )
    return venv


def main() -> int:
    if not SCRIPT.is_file():
        raise FileNotFoundError(SCRIPT)
    os.environ["EXPECTED_CODE_SHA"] = authenticated_code_sha()
    os.environ["JASS_L3_NUMERIC_VENV"] = str(ensure_historical_numeric_runtime())
    os.execv("/usr/bin/bash", ["/usr/bin/bash", str(SCRIPT)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
