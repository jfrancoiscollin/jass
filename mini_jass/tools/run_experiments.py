#!/usr/bin/env python3
"""Run the paired-seed M5 E1-E4 experiment pack."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.argv.insert(1, "experiment-pack")

from mini_jass_lab.cli import main  # noqa: E402

raise SystemExit(main())
