#!/usr/bin/env python3
"""Launch-V2 Python entrypoint for the frozen CLS-L normalization shell stage.

Launch-V2 fingerprints its command interpreter as the numerical runtime. The
scientific stage itself remains the existing immutable shell template; this thin
entrypoint exists so the gate fingerprints /usr/bin/python3 rather than trying
to execute Python runtime-identification code through /usr/bin/bash.

``run_experiment_stage.py`` deliberately sanitizes the stage environment, so an
outer runner's ``EXPECTED_CODE_SHA`` is not propagated.  The historical shell
still consumes that variable as a defence-in-depth assertion.  Reconstruct it
only from the already-authenticated ``JASS_STAGE_SPEC``, verify it against HEAD,
then exec the unchanged frozen shell.
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


def main() -> int:
    if not SCRIPT.is_file():
        raise FileNotFoundError(SCRIPT)
    os.environ["EXPECTED_CODE_SHA"] = authenticated_code_sha()
    os.execv("/usr/bin/bash", ["/usr/bin/bash", str(SCRIPT)])
    return 127  # pragma: no cover - execv replaces the process on success.


if __name__ == "__main__":
    raise SystemExit(main())
