import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-turnover-l2-preflight-v1.sh"
TRAIN = ROOT / "jobs/templates/l3-pure-turnover-l2-train-v1.sh"
EVAL = ROOT / "jobs/templates/l3-pure-turnover-l2-eval-v1.sh"
PREFLIGHT_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-turnover-l2-20260726"
    / "home-0984-l3-pure-turnover-l2-preflight-v1.sh"
)
PREFLIGHT_RETRY_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-turnover-l2-20260726"
    / "home-0984bis-l3-pure-turnover-l2-preflight-v2.sh"
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


class TurnoverL2PreflightTests(unittest.TestCase):
    def run_trigger_contract(self, root: Path, *, truncate_cell: bool = False):
        inputs = root / "inputs"
        artefacts = root / "artefacts"
        inputs.mkdir()
        artefacts.mkdir()
        jobs = (
            "home-0983",
            "home-0981ter",
            "home-0977",
            "home-0980",
            "home-0944",
        )
        reports = (
            "verified-replay25-evaluation.json",
            "verified-replay25-preflight.json",
            "verified-turnover-training.json",
            "verified-turnover-confirmation.json",
            "verified-m1-source.json",
        )
        for report, job in zip(reports, jobs):
            (artefacts / report).write_text(
                json.dumps({"job_id": job, "result_state": "completed"}),
                encoding="utf-8",
            )
        force = {}
        for view in ("q00", "native"):
            for opponent in ("M2", "TURNOVER", "F2M", "GEN2"):
                force[f"{view}_vs_{opponent}"] = {
                    "n": 1_000,
                    "wins_a": 500,
                    "draws": 10,
                    "wins_b": 490,
                }
        if truncate_cell:
            force["native_vs_GEN2"]["wins_b"] = 489
        payloads = {
            "replay25-evaluation.json": {
                "verdict": "REPLAY25_DOSE_CLOSED_REVIEW",
                "promotion_authorized": False,
                "automatic_next_job": None,
                "protocol": {"candidate": "REPLAY25_RECENCY75"},
                "force": force,
                "opening_manifest": {"records": 500, "overlap_records": 0},
                "primary_checks": {
                    "TURNOVER": {
                        "q00": {"regression_not_established": False}
                    }
                },
            },
            "replay25-preflight.json": {
                "verdict": "REPLAY25_PREFLIGHT_READY",
                "evaluation_openings": {"seed": 1_836_311},
            },
            "turnover-training.json": {
                "experiment_variant": "TURNOVER_1_1",
                "code_sha": "336bb98451a205266d6646c4d801027af4b30294",
                "model_sha256":
                    "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16",
                "training_corpus_sha256":
                    "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d",
                "training_meta_sha256":
                    "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682",
                "training_records": 2_000_000,
                "historical_replay_records": 1_000_000,
                "fresh_records": 1_000_000,
                "parent_model_sha256":
                    "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2",
            },
            "turnover-confirmation.json": {
                "verdict": "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW",
                "all_guardrails_pass": True,
            },
            "m1-training.json": {
                "arms": {
                    "F2M": {
                        "model_sha256":
                            "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
                    }
                }
            },
        }
        for name, payload in payloads.items():
            (inputs / name).write_text(json.dumps(payload), encoding="utf-8")
        block = embedded_python(TEMPLATE)[0]
        argv = ["trigger-contract", str(inputs), str(artefacts), *jobs]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            with mock.patch.object(sys, "argv", argv):
                exec(compile(block, "turnover-l2-trigger-contract", "exec"), {})

    def test_shell_and_embedded_python_contracts(self):
        for script in (
            TEMPLATE,
            TRAIN,
            EVAL,
            PREFLIGHT_WRAPPER,
            PREFLIGHT_RETRY_WRAPPER,
        ):
            subprocess.run(["bash", "-n", str(script)], check=True)
            blocks = embedded_python(script)
            if script not in (PREFLIGHT_WRAPPER, PREFLIGHT_RETRY_WRAPPER):
                self.assertGreaterEqual(len(blocks), 3)
            for index, block in enumerate(blocks):
                compile(block, f"{script}:heredoc-{index}", "exec")

    def test_fixed_corpus_split_and_l2_levels(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d",
            "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682",
            "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16",
            "336bb98451a205266d6646c4d801027af4b30294",
            "SPLIT_SEED=577215",
            "L2_1E5:1e-5",
            "L2_1E4:1e-4",
            "--max-iter 2",
            "--lbfgs-maxcor 20",
            "--lbfgs-gtol 1e-3",
        ):
            self.assertIn(value, text)
        self.assertNotIn("--gen-selfplay", text)

    def test_trigger_and_independent_pool_fail_closed(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in (
            "REPLAY25_DOSE_CLOSED_REVIEW",
            "regression_not_established",
            "complete_force_cell",
            '("wins_a", "draws", "wins_b")',
            "OPENING_SEED=1836313",
            "--exclude \"$IN/prior-replay25.fen\"",
            "TURNOVER_L2_PREFLIGHT_READY",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(value, text)
        self.assertNotIn(
            'evaluation.get("all_guardrails_pass") is not True',
            text,
        )
        self.assertNotIn('.get("complete") is True', text)

    def test_real_force_row_schema_authorizes_completed_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_trigger_contract(Path(tmp))

    def test_force_count_mismatch_closes_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                SystemExit,
                "REPLAY25 final result does not authorize",
            ):
                self.run_trigger_contract(Path(tmp), truncate_cell=True)

    def test_home_resource_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('cmake --build "$W/test-build" -j4', text)
        self.assertIn('cmake --build "$W/build" -j4', text)
        self.assertIn('"max_parallel_fits": 2', text)
        self.assertIn('[ "$(nproc)" -ge 16 ]', text)

    def test_training_uses_one_feature_dump_and_two_converged_fits(self):
        text = TRAIN.read_text(encoding="utf-8")
        self.assertEqual(text.count("--dump-eval-features"), 1)
        self.assertIn("run_fit turnover-l2-1e5 1e-5 &", text)
        self.assertIn("run_fit turnover-l2-1e4 1e-4 &", text)
        self.assertIn('--max-iter "$MAXIT"', text)
        self.assertIn('--optimizer-report "$ART/$name-optimizer.json"', text)
        self.assertIn("TURNOVER_L2_TRAINING_SCREEN_READY", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertNotIn("--gen-selfplay", text)

    def test_evaluation_is_staged_and_fail_closed(self):
        text = EVAL.read_text(encoding="utf-8")
        primary = text.index('stage "primary-$view-vs-turnover"')
        eligibility = text.index('mapfile -t ELIGIBLE')
        secondary = text.index("if [ \"${#ELIGIBLE[@]}\" -gt 0 ]; then")
        self.assertLess(primary, eligibility)
        self.assertLess(eligibility, secondary)
        self.assertIn('if all(rate > 0.5 for rate in rates):', text)
        self.assertIn("TURNOVER_L2_", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", text)
        self.assertIn('die "need 8 GiB free"', text)
        self.assertIn('die "need 3.5 GiB available RAM"', text)
        self.assertNotIn("--gen-selfplay", text)

    def test_preflight_wrapper_pins_completed_trigger_and_controls(self):
        for wrapper, job in (
            (PREFLIGHT_WRAPPER, "home-0984-l3-pure-turnover-l2-preflight-v1"),
            (
                PREFLIGHT_RETRY_WRAPPER,
                "home-0984bis-l3-pure-turnover-l2-preflight-v2",
            ),
        ):
            text = wrapper.read_text(encoding="utf-8")
            for value in (
                job,
                "home-0983-l3-pure-replay25-independent-eval-v1/"
                "20260726T112309Z-42b9af7e",
                "home-0981ter-l3-pure-replay25-preflight-v1/"
                "20260726T104130Z-01873c15",
                "home-0977-l3-pure-turnover1to1-train-v1/"
                "20260726T071254Z-336bb984",
                "home-0980-l3-pure-turnover-confirmation-v2/"
                "20260726T085020Z-aef92679",
                "NO_AUTOMATIC_CONTINUATION=1",
            ):
                self.assertIn(value, text)
        retry = PREFLIGHT_RETRY_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            "force-row completeness is W/D/L arithmetic",
            retry,
        )


if __name__ == "__main__":
    unittest.main()
