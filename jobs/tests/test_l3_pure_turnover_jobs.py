from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TRAIN_TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-train-v1.sh"
EVAL_TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-eval-v1.sh"
TRAIN_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-turnover-20260726"
    / "home-0977-l3-pure-turnover1to1-train-v1.sh"
)
EVAL_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-turnover-20260726"
    / "home-0978-l3-pure-turnover1to1-independent-eval-v1.sh"
)
PROTOCOL = ROOT / "docs/experiments/L3_PURE_TURNOVER_PROTOCOL_20260726.md"


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


class L3PureTurnoverJobTests(unittest.TestCase):
    def test_shell_and_embedded_python_contracts(self):
        for script in (TRAIN_TEMPLATE, EVAL_TEMPLATE, TRAIN_WRAPPER, EVAL_WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        for template in (TRAIN_TEMPLATE, EVAL_TEMPLATE):
            blocks = embedded_python(template)
            self.assertGreaterEqual(len(blocks), 6)
            for index, block in enumerate(blocks):
                compile(block, f"{template}:heredoc-{index}", "exec")

    def test_training_changes_only_temporal_distribution(self):
        text = TRAIN_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("TURNOVER_1_1:8)", text)
        self.assertIn('--source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 1', text)
        self.assertIn('--source FRESH "$W/m2-d8.jnnw" "$W/m2-d8.jsm" 1', text)
        self.assertIn('--target-records "$TOTAL_RECORDS" --seed 141421 --namespace-openings', text)
        self.assertIn('get("selected_records") != 1_000_000', text)
        self.assertIn(
            '"temporal_distribution_records": (',
            text,
        )
        self.assertIn('"new_generation_performed": not (is_depth_mix or is_turnover)', text)
        self.assertIn("TURNOVER_APPROVED=1 missing", text)

    def test_depth_factor_closure_is_fail_closed(self):
        text = TRAIN_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('failed != ["f2m_q00_regression_not_established"]', text)
        self.assertIn('d12_evaluation.get("all_guardrails_pass") is not False', text)
        self.assertIn("depth factor was not closed exactly as preregistered", text)

    def test_evaluation_uses_m2_f2m_gen2_and_disjoint_pool(self):
        text = EVAL_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("CANDIDATE_LABEL=TURNOVER", text)
        self.assertIn("run_gate q00 M2", text)
        self.assertIn("run_gate native M2", text)
        self.assertIn("prior-m2-independent.fen", text)
        self.assertIn("prior-d10-independent.fen", text)
        self.assertIn("prior-d12-independent.fen", text)
        self.assertIn("l3_turnover_evaluation.py", text)
        wrapper = EVAL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("OPENING_SEED_OVERRIDE=732051", wrapper)
        self.assertIn(
            "6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d",
            wrapper,
        )

    def test_wrappers_pin_sources_and_forbid_automatic_continuation(self):
        train = TRAIN_WRAPPER.read_text(encoding="utf-8")
        for value in (
            "home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1",
            "012b9c716dadf2c3df668c23a7dd9d5ece423b8c",
            "home-0970bis-l3-pure-m2-independent-eval-v3",
            "home-0974bis-l3-pure-d12-causal-independent-eval-v1",
            "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d",
            "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682",
            "NO_AUTOMATIC_CONTINUATION=1",
        ):
            self.assertIn(value, train)
        evaluation = EVAL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            ': "${EXPECTED_CANDIDATE_MODEL_SHA256:?set after completed 0977}"',
            evaluation,
        )
        self.assertIn("EXPECTED_M2_D8_CODE_SHA", evaluation)
        self.assertIn(': "${M2_PREFIX:?set exact completed 0977 result prefix}"', evaluation)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", evaluation)

    def test_protocol_records_sizing_and_nonpromotion(self):
        text = PROTOCOL.read_text(encoding="utf-8")
        for value in (
            "1 000 000",
            "external_teacher_inputs=0",
            "45–70 minutes",
            "35–55 minutes",
            "promotion_authorized=false",
            "automatic_next_job=null",
        ):
            self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
