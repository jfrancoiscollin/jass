from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-replay25-preflight-v1.sh"
TRAIN_TEMPLATE = ROOT / "jobs/templates/l3-pure-replay25-train-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-replay25-20260726"
    / "home-0981-l3-pure-replay25-preflight-v1.sh"
)
RELAUNCH_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-replay25-20260726"
    / "home-0981ter-l3-pure-replay25-preflight-v1.sh"
)
TRAIN_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-replay25-20260726"
    / "home-0982-l3-pure-replay25-train-v1.sh"
)
PROTOCOL = ROOT / "docs/experiments/L3_PURE_REPLAY25_PROTOCOL_20260726.md"


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


class L3PureReplay25PreflightTests(unittest.TestCase):
    def test_shell_and_embedded_python_contracts(self):
        for script in (
            TEMPLATE,
            TRAIN_TEMPLATE,
            WRAPPER,
            RELAUNCH_WRAPPER,
            TRAIN_WRAPPER,
        ):
            subprocess.run(["bash", "-n", str(script)], check=True)
        for template in (TEMPLATE, TRAIN_TEMPLATE):
            blocks = embedded_python(template)
            self.assertGreaterEqual(len(blocks), 4)
            for index, block in enumerate(blocks):
                compile(block, f"{template}:heredoc-{index}", "exec")

    def test_single_factor_exact_mix_is_reconstructed_twice(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            '--source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 1',
            text,
        )
        self.assertIn(
            '--source FRESH "$W/m2.raw.jnnw" "$W/m2.raw.jsm" 3',
            text,
        )
        self.assertEqual(text.count('--target-records "$TOTAL_RECORDS"'), 2)
        self.assertIn("PARENT_RECORDS=500000", text)
        self.assertIn("FRESH_RECORDS=1500000", text)
        self.assertIn('get("selected_records") != 500_000', text)
        self.assertIn('get("selected_records") != 1_500_000', text)
        self.assertIn("cmp -s \"$W/replay25.raw.jnnw\"", text)
        self.assertIn("cmp -s \"$W/replay25.fit.jnnw\"", text)
        self.assertIn("--namespace-openings", text)
        self.assertIn("external_teacher_inputs", text)

    def test_trigger_is_fail_closed_on_completed_confirmation(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW", text)
        self.assertIn("TURNOVER_DIRECTION_REPLICATED_REVIEW", text)
        self.assertIn('confirmation.get("all_guardrails_pass") is not True', text)
        self.assertIn('confirmation.get("promotion_authorized") is not False', text)
        self.assertIn("turnover confirmation does not authorize REPLAY25 preflight", text)
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            'export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/'
            "home-0980-l3-pure-turnover-confirmation-v2/"
            '20260726T085020Z-aef92679"',
            wrapper,
        )
        self.assertIn("home-0980-l3-pure-turnover-confirmation-v2", wrapper)
        relaunch = RELAUNCH_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            'export EXPECTED_JOB_ID="home-0981ter-l3-pure-replay25-preflight-v1"',
            relaunch,
        )

    def test_runtime_roundtrip_and_independent_pool_are_measured(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("numpy==1.26.4 scipy==1.14.1", text)
        self.assertIn('cmake --build "$W/build" -j4 --target jass', text)
        self.assertIn("--dump-eval-features", text)
        self.assertIn("--max-iter 2", text)
        self.assertIn("OPENING_SEED=1836311", text)
        self.assertIn("prior-turnover-confirmation.fen", text)
        self.assertIn("opening candidates are not byte-identical", text)
        self.assertIn("selected evaluation pool is not byte-identical", text)
        self.assertIn(
            'coverage.get("corpus", {}).get("total_records") != 2_000_000',
            text,
        )
        self.assertIn("home_training_eta_minutes", text)
        self.assertIn("home_evaluation_eta_minutes", text)

    def test_training_reuses_exact_preflight_and_requires_convergence(self):
        text = TRAIN_TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "REPLAY25_PREFLIGHT_READY",
            "historical_replay_records",
            "500_000",
            "1_500_000",
            "numpy==1.26.4 scipy==1.14.1",
            "--warm-start \"$W/f2m.pjtw\"",
            "--l2 \"$L2\"",
            "--max-iter \"$MAXIT\"",
            "--optimizer-report",
            "REPLAY25 optimiser did not converge",
            "REPLAY25_TRAINING_SCREEN_READY",
            "external_teacher_inputs",
            "promotion_authorized",
            "automatic_next_job",
        ):
            self.assertIn(value, text)
        self.assertNotIn("--gen-data-wdl", text)
        wrapper = TRAIN_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            ': "${PREFLIGHT_PREFIX:?set completed home-0981 result prefix}"',
            wrapper,
        )
        self.assertIn(
            'export TURNOVER_CONFIRM_PREFIX="r2:jass-data/runs/'
            "home-0980-l3-pure-turnover-confirmation-v2/"
            '20260726T085020Z-aef92679"',
            wrapper,
        )

    def test_protocol_keeps_forbidden_factors_out_and_no_promotion(self):
        text = PROTOCOL.read_text(encoding="utf-8")
        for value in (
            "500 000",
            "1 500 000",
            "2 000 000",
            "618034",
            "1836311",
            "aucun teacher",
            "ni TOP3",
            "ni reweight V2",
            "promotion_authorized=false",
            "automatic_next_job=null",
        ):
            self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
