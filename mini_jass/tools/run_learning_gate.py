#!/usr/bin/env python3
"""Run the paired-seed M6 L1 consolidation and learning gate."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.argv.insert(1, "learning-gate")

from mini_jass_lab.cli import main  # noqa: E402

raise SystemExit(main())
