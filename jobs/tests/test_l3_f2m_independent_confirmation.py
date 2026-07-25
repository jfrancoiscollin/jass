from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs/tools"))

from l3_f2m_independent_confirmation import (  # noqa: E402
    CONFIRMED,
    NOT_CONFIRMED,
    build_confirmation,
)


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def force(rate: float, low: float, high: float) -> dict:
    wins = int(rate * 1_000)
    return {
        "n": 1_000,
        "wins_a": wins,
        "draws": 0,
        "wins_b": 1_000 - wins,
        "rate": rate,
        "elo": 0.0,
        "ci_low": low,
        "ci_high": high,
    }


class F2MIndependentConfirmationTests(unittest.TestCase):
    def prepare(self, root: Path) -> tuple[Path, Path, Path, Path]:
        force_dir = root / "force"
        force_dir.mkdir()
        review = root / "review.json"
        matrix = root / "matrix.json"
        openings = root / "openings.json"
        write(
            review,
            {
                "verdict": "M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY",
                "selected_m1_arm_for_confirmation": "F2M",
                "eligible_arms": ["F2M", "R2M"],
            },
        )
        write(
            matrix,
            {
                "verdict": "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW",
                "m1_arms_passing_floor": ["F500", "F2M", "R2M"],
            },
        )
        write(
            openings,
            {"records": 500, "unique_records": 500, "overlap_records": 0},
        )
        return review, matrix, openings, force_dir

    def test_confirms_when_primary_views_and_guardrails_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review, matrix, openings, force_dir = self.prepare(root)
            rows = {
                "force-q00-F2M-vs-C0.json": force(0.60, 0.57, 0.63),
                "force-native-F2M-vs-C0.json": force(0.59, 0.56, 0.62),
                "force-q00-F2M-vs-R2M.json": force(0.51, 0.48, 0.54),
                "force-native-F2M-vs-R2M.json": force(0.50, 0.47, 0.53),
            }
            for name, payload in rows.items():
                write(force_dir / name, payload)
            payload = build_confirmation(
                review_path=review,
                matrix_path=matrix,
                force_dir=force_dir,
                opening_manifest_path=openings,
            )

        self.assertEqual(payload["verdict"], CONFIRMED)
        self.assertTrue(payload["confirmed"])
        self.assertEqual(payload["selected_generalist_candidate"], "F2M")
        self.assertFalse(payload["promotion_authorized"])
        self.assertIsNone(payload["automatic_next_job"])

    def test_retains_c0_when_native_superiority_is_not_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review, matrix, openings, force_dir = self.prepare(root)
            rows = {
                "force-q00-F2M-vs-C0.json": force(0.60, 0.57, 0.63),
                "force-native-F2M-vs-C0.json": force(0.52, 0.49, 0.55),
                "force-q00-F2M-vs-R2M.json": force(0.51, 0.48, 0.54),
                "force-native-F2M-vs-R2M.json": force(0.50, 0.47, 0.53),
            }
            for name, payload in rows.items():
                write(force_dir / name, payload)
            payload = build_confirmation(
                review_path=review,
                matrix_path=matrix,
                force_dir=force_dir,
                opening_manifest_path=openings,
            )

        self.assertEqual(payload["verdict"], NOT_CONFIRMED)
        self.assertFalse(payload["confirmed"])
        self.assertIsNone(payload["selected_generalist_candidate"])
        self.assertEqual(payload["generalist_parent_remains"], "C0_A_G3")


if __name__ == "__main__":
    unittest.main()
