from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-replay25-eval-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-replay25-20260726"
    / "home-0983-l3-pure-replay25-independent-eval-v1.sh"
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


class Replay25EvalJobTests(unittest.TestCase):
    def test_shell_and_embedded_python_contracts(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        blocks = embedded_python(TEMPLATE)
        self.assertGreaterEqual(len(blocks), 4)
        for index, block in enumerate(blocks):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_all_preregistered_force_cells_share_one_pool(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("for opponent in M2 TURNOVER F2M GEN2", text)
        self.assertIn("for view in q00 native", text)
        self.assertIn('--openings-file "$W/open-eval.fen"', text)
        self.assertIn("FORCE_DEPTH=9", text)
        self.assertIn("MOVETIME=0.1", text)
        self.assertIn("NOPEN=500", text)
        self.assertIn("OPENING_SEED=1836311", text)
        self.assertIn(
            "a0af38e81ea457b5f95a12d3166b7103e922627c4771d6351057de1ad7ced2c2",
            text,
        )

    def test_controls_conversion_and_coverage_are_fail_closed(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW",
            "REPLAY25_TRAINING_SCREEN_READY",
            "TURNOVER-p3_mince.json",
            "M2-p3_mince.json",
            "F2M-p3_mince.json",
            "REPLAY25-coverage.json",
            "--require-position-results",
            "l3_replay25_evaluation.py",
            'fixed.get("state") != "verified"',
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(value, text)

    def test_repaired_symmetric_build_and_resource_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('cmake --build "$W/build8" -j4', text)
        self.assertIn('cmake --build "$W/build32" -j4', text)
        self.assertIn('cmake --build "$W/build32fixed" -j4', text)
        self.assertIn("FIXED_DEFENDER_CODE_SHA", text)
        self.assertIn("has_any_capture", text)
        self.assertIn("g_emasks", text)
        self.assertIn('NSH_GATE=16', text)
        self.assertIn('PAR_GATE=4', text)

    def test_wrapper_is_draft_until_training_is_completed(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            ': "${TRAIN_PREFIX:?set completed home-0982 result prefix}"',
            text,
        )
        self.assertIn(
            ': "${EXPECTED_CANDIDATE_MODEL_SHA256:?set completed home-0982 model SHA}"',
            text,
        )
        self.assertIn(
            'export EXPECTED_TRAIN_JOB="home-0982-l3-pure-replay25-train-v1"',
            text,
        )
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)


if __name__ == "__main__":
    unittest.main()
