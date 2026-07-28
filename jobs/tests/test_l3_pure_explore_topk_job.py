from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-explore-topk-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-explore-topk-20260728"
    / "home-1009-l3-pure-explore-topk-arms-v1.sh"
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


class ExploreTopkJobTests(unittest.TestCase):
    def test_shell_and_embedded_python_contracts(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        for index, block in enumerate(embedded_python(TEMPLATE)):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_single_factor_and_margin_are_effective_and_reported(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "EXPLORE_MARGIN=50",
            '--explore-topk "$TOPK" --explore-margin "$EXPLORE_MARGIN"',
            "margin_singleton_plies",
            "explore-margin never constrained TOPK3",
            '"explore_margin": margin',
            '"promotion_authorized": False',
            '"automatic_next_job": None',
        ):
            self.assertIn(value, text)

    def test_parent_and_other_causal_inputs_are_shared(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "RECORDS=2000000",
            "PLAY_DEPTH=9",
            "BASE_SEED=2718281",
            "SPLIT_SEED=577215",
            "TURNOVER_MODEL_SHA",
            "gen_arm uniform",
            "gen_arm topk3",
        ):
            self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
