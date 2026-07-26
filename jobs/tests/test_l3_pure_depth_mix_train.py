from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-train-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-depth-mix-20260726"
    / "home-0975-l3-pure-d10-d12-mix5to1-train-v1.sh"
)
PROTOCOL = ROOT / "docs/experiments/L3_PURE_DEPTH_MIX_PROTOCOL_20260726.md"


class L3PureDepthMixTrainingTests(unittest.TestCase):
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

    def test_exact_single_factor_mix_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("D10_D12_MIX_5_1:0)", text)
        self.assertIn('--source D10 "$W/d10.jnnw" "$W/d10.jsm" 5', text)
        self.assertIn('--source D12 "$W/d12.jnnw" "$W/d12.jsm" 1', text)
        self.assertIn('--target-records "$TOTAL_RECORDS" --seed 271828', text)
        self.assertIn('get("selected_records") != 1_666_667', text)
        self.assertIn('get("selected_records") != 333_333', text)
        self.assertIn("opening identities are not sufficiently aligned", text)
        self.assertIn('"depth_distribution_records": (', text)
        self.assertIn('"historical_replay_records": 0', text)

    def test_trigger_is_fail_closed_on_flat_d12_only(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('evaluation.get("verdict") != "D12_PLATEAU_OR_REGRESSION_REVIEW"', text)
        self.assertIn(
            '"stop_single_depth_escalation_and_prepare_distribution_factor"',
            text,
        )
        self.assertIn('evaluation.get("all_guardrails_pass") is not True', text)
        self.assertIn("DEPTH_MIX_APPROVED=1 missing", text)

    def test_wrapper_is_draft_with_exact_d10_and_d12_placeholders(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("Draft only", text)
        self.assertIn("home-0971-l3-pure-d10-causal-fresh2m-train-v1", text)
        self.assertIn("home-0973-l3-pure-d12-causal-fresh2m-train-v1", text)
        self.assertIn("home-0974-l3-pure-d12-causal-independent-eval-v1", text)
        self.assertIn(
            "f14bab1eca1988fa9fae9bd69f718d434d5e808cfb68b11e12a47fa211aa65a6",
            text,
        )
        self.assertIn(
            ': "${EXPECTED_MIX_CORPUS_SHA256:?set after deterministic mix preflight}"',
            text,
        )
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)

    def test_protocol_forbids_confounded_factors_and_promotion(self):
        text = PROTOCOL.read_text(encoding="utf-8")
        for forbidden in (
            "augmentation de volume",
            "replay historique",
            "oracle",
            "teacher",
            "TOP3",
            "reweight V2",
        ):
            self.assertIn(forbidden, text)
        self.assertIn("Aucune promotion ni continuation n'est automatique", text)


if __name__ == "__main__":
    unittest.main()
