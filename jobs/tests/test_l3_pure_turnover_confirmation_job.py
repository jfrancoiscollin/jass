from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-turnover-confirmation-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-turnover-20260726"
    / "home-0980-l3-pure-turnover-confirmation-v2.sh"
)
PROTOCOL = (
    ROOT
    / "docs/experiments/L3_PURE_TURNOVER_CONFIRMATION_PROTOCOL_20260726.md"
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


class L3PureTurnoverConfirmationJobTests(unittest.TestCase):
    def test_shell_and_embedded_python_compile(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        blocks = embedded_python(TEMPLATE)
        self.assertGreaterEqual(len(blocks), 2)
        for index, block in enumerate(blocks):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_confirmation_reuses_model_and_only_reruns_force(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("NOPEN=1000", text)
        self.assertIn("OPENING_SEED=11235813", text)
        self.assertIn("force-q00-2000-games-per-cell", text)
        self.assertIn("force-native-2000-games-per-cell", text)
        self.assertIn("run_gate q00 M2", text)
        self.assertIn("run_gate q00 F2M", text)
        self.assertIn("run_gate native M2", text)
        self.assertIn("run_gate native F2M", text)
        self.assertIn(
            'local view="$1" opponent="$2"\n  local pattern="$W/$opponent.pjtw"',
            text,
        )
        self.assertNotIn(
            'local view="$1" opponent="$2" pattern="$W/$opponent.pjtw"',
            text,
        )
        self.assertIn("prior-turnover-independent.fen", text)
        self.assertIn("l3_turnover_confirmation.py", text)
        self.assertNotIn("conv_fixed_wdl.py", text)
        self.assertNotIn("l3_bucket_visits.py", text)

    def test_wrapper_pins_all_inputs_and_forbids_continuation(self):
        text = WRAPPER.read_text(encoding="utf-8")
        for value in (
            "home-0977-l3-pure-turnover1to1-train-v1",
            "home-0978-l3-pure-turnover1to1-independent-eval-v1",
            "home-0980-l3-pure-turnover-confirmation-v2",
            "home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1",
            "home-0944-l3-pure-m1-train-resume-v3",
            "c34f25f0dddf8865e90a4f149bcca0f4b40ccb32d0b5e1aff5fde6a604e92251",
            "c440f5a6818aee4b226ceb968fa2753b2d2d71b6257d9a335c1f2e96efb5a51a",
            "NO_AUTOMATIC_CONTINUATION=1",
        ):
            self.assertIn(value, text)

    def test_protocol_records_high_n_and_nonpromotion(self):
        text = PROTOCOL.read_text(encoding="utf-8")
        for value in (
            "2 000 parties par cellule",
            "3 000 parties par cellule",
            "promotion_authorized=false",
            "automatic_next_job=null",
            "40 à 55 minutes",
        ):
            self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
