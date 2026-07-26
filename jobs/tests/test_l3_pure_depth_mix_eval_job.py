from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-eval-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-depth-mix-20260726"
    / "home-0976-l3-pure-d10-d12-mix5to1-independent-eval-v1.sh"
)


class DepthMixEvaluationJobTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_embedded_python_is_syntactically_valid(self):
        blocks = []
        current = None
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
            if current is None and "<<'PY'" in line:
                current = []
            elif current is not None and line == "PY":
                blocks.append("\n".join(current))
                current = None
            elif current is not None:
                current.append(line)
        self.assertIsNone(current)
        self.assertGreaterEqual(len(blocks), 6)
        for index, block in enumerate(blocks):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_four_way_force_and_coverage_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("DEPTH_MIX)", text)
        self.assertIn("CANDIDATE_LABEL=MIX", text)
        for view in ("q00", "native"):
            self.assertIn(f"run_gate {view} D10", text)
            self.assertIn(f"run_gate {view} D12", text)
        self.assertIn('pattern="$W/D12.pjtw"', text)
        self.assertIn('"$W/D10.jnnw"', text)
        self.assertIn('"$W/D12.jnnw"', text)
        self.assertIn('"$ART/coverage/D10-coverage.json"', text)
        self.assertIn('"$ART/coverage/D12-coverage.json"', text)

    def test_pool_reconstructs_and_excludes_all_prior_causal_pools(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("prior-m2-independent.fen", text)
        self.assertIn("prior-d10-independent.fen", text)
        self.assertIn("prior-d12-independent.fen", text)
        self.assertIn("--generator-seed 424243", text)
        self.assertIn("EXPECTED_D12_OPENING_SHA256", text)
        self.assertIn("OPENING_SEED_OVERRIDE=577217", WRAPPER.read_text(encoding="utf-8"))

    def test_preregistered_aggregator_and_nonpromotion(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("l3_depth_mix_evaluation.py", text)
        self.assertIn("depth-mix-evaluation.json", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_wrapper_remains_blocked_until_exact_results_exist(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("Draft only", text)
        self.assertIn("home-0975-l3-pure-d10-d12-mix5to1-train-v1", text)
        self.assertIn("home-0973-l3-pure-d12-causal-fresh2m-train-v1", text)
        self.assertIn("home-0974-l3-pure-d12-causal-independent-eval-v1", text)
        for name in (
            "EXPECTED_CANDIDATE_MODEL_SHA256",
            "EXPECTED_CANDIDATE_CORPUS_SHA256",
            "EXPECTED_D12_OPENING_SHA256",
            "EXPECTED_OPENING_SHA256",
        ):
            self.assertIn(f': "${{{name}:?', text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)


if __name__ == "__main__":
    unittest.main()
