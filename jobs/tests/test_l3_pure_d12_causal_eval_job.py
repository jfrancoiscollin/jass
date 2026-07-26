from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-eval-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-d12-causal-20260726"
    / "home-0974-l3-pure-d12-causal-independent-eval-v1.sh"
)


class D12CausalEvaluationJobTests(unittest.TestCase):
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
        self.assertGreaterEqual(len(blocks), 5)
        for index, block in enumerate(blocks):
            compile(block, f"{TEMPLATE}:heredoc-{index}", "exec")

    def test_three_way_force_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("D12_CAUSAL)", text)
        self.assertIn("CANDIDATE_LABEL=D12", text)
        self.assertIn("run_gate q00 D10", text)
        self.assertIn("run_gate native D10", text)
        self.assertIn('force-$view-$CANDIDATE_LABEL-vs-$opponent.json', text)

    def test_d10_control_and_conversion_are_exact(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("d10.pjtw.gz", text)
        self.assertIn("d10-fresh-2m.jnnw.gz", text)
        self.assertIn(
            "18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f",
            text,
        )
        self.assertIn(
            "3351cb8aebd33c417de179d72f4483193ae67f05f723c520190ed2a118fc9297",
            text,
        )
        self.assertIn("D10-p3_mince.json", text)
        self.assertIn("D10-p4_egal.json", text)
        self.assertIn("D10-coverage.json", text)

    def test_pool_excludes_m2_and_d10_independent_pools(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("prior-m2-independent.fen", text)
        self.assertIn("prior-d10-independent.fen", text)
        self.assertIn("M2_INDEPENDENT_OPENINGS_SHA", text)
        self.assertIn("D10_INDEPENDENT_OPENINGS_SHA", text)
        self.assertIn('opening_args+=(--exclude "$W/prior-m2-independent.fen")', text)
        self.assertIn('opening_args+=(--exclude "$W/prior-d10-independent.fen")', text)
        self.assertIn("EXPECTED_OPENING_SHA256", text)
        self.assertIn("OPENING_SEED_OVERRIDE=424243", wrapper)

    def test_preregistered_aggregator_and_nonpromotion(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("l3_d12_causal_evaluation.py", text)
        self.assertIn("d12-causal-evaluation.json", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_wrapper_pins_certified_d12_inputs(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("home-0971-l3-pure-d10-causal-fresh2m-train-v1", text)
        self.assertIn("home-0972-l3-pure-d10-causal-independent-eval-v1", text)
        self.assertIn("home-0973-l3-pure-d12-causal-fresh2m-train-v1", text)
        self.assertIn(
            'export EXPECTED_CANDIDATE_MODEL_SHA256="'
            '2541774af6ecdb832e4cb99723cc95880b7d940c042da32e7d4b270ac2464263"',
            text,
        )
        self.assertIn(
            'export EXPECTED_CANDIDATE_CORPUS_SHA256="'
            '45cc916a0d398efd48aadb322c7e1be86db49b6d18d7626edf5f3f3d493ea802"',
            text,
        )
        self.assertIn(
            'export EXPECTED_OPENING_SHA256="'
            '0f7af083406063719717190cab7f983bee6d0f49b552f42ca4d05d81dce7cf7f"',
            text,
        )
        self.assertIn(
            "r2:jass-data/runs/"
            "home-0973-l3-pure-d12-causal-fresh2m-train-v1/"
            "20260726T001956Z-d4896990",
            text,
        )
        self.assertNotIn("set after completed 0973", text)
        self.assertNotIn("set after independent-pool preflight", text)


if __name__ == "__main__":
    unittest.main()
