#!/usr/bin/env python3
"""Run the deterministic M4 self-play loop."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.argv.insert(1, "selfplay")

from mini_jass_lab.cli import main  # noqa: E402

raise SystemExit(main())
