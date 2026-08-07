from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.argv.insert(1, "l2-transfer-gate")

from mini_jass_lab.cli import main  # noqa: E402

raise SystemExit(main())
