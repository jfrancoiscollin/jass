from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-volume8m-eval-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-volume8m-20260728"
    / "home-1007-l3-pure-volume8m-independent-eval-v1.sh"
)


def embedded_python(path: Path) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if current is None and "<<'PY'" in line:
            current = []
        elif current is not None and line == "PY":
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    if current is not None:
        raise AssertionError(f"{path}: unterminated Python heredoc")
    return blocks


class Volume8mEvalJobTests(unittest.TestCase):
    def test_shell_and_embedded_python_contracts(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        for index, block in enumerate(embedded_python(TEMPLATE)):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_independent_force_conversion_and_coverage_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "NOPEN=1500",
            "OPENING_SEED=2236068",
            "for opp in M2 TURNOVER F2M GEN2",
            "for view in q00 native",
            "--movetime \"$MOVETIME\"",
            "--require-position-results",
            "FIXED_DEFENDER_CODE_SHA",
            "VOL8M_MODEL_SHA256.txt",
            "vol8m-coverage.json",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(value, text)

    def test_wrapper_pins_authoritative_sources(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("home-1006-l3-pure-volume8m-train-v2", text)
        self.assertIn("20260728T024741Z-a5a7301f", text)
        self.assertIn("home-1004-l3-pure-volume8m-preflight-v2", text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)


if __name__ == "__main__":
    unittest.main()
