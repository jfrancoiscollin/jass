from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs/tools"))

from l3_f2m_gen2_repaired_benchmark import (  # noqa: E402
    GEN2_RETAINS,
    INCONCLUSIVE,
    NEW_CHAMPION,
    build_benchmark,
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


class F2MGen2RepairedBenchmarkTests(unittest.TestCase):
    def run_case(self, root: Path, q00: dict, native: dict) -> dict:
        force_dir = root / "force"
        force_dir.mkdir()
        confirmation = root / "confirmation.json"
        openings = root / "openings.json"
        write(
            confirmation,
            {
                "verdict": "F2M_CONFIRMED_FOR_HUMAN_PROMOTION_REVIEW",
                "selected_generalist_candidate": "F2M",
            },
        )
        write(
            openings,
            {"records": 500, "unique_records": 500, "overlap_records": 0},
        )
        write(force_dir / "force-q00-F2M-vs-GEN2.json", q00)
        write(force_dir / "force-native-F2M-vs-GEN2.json", native)
        return build_benchmark(
            confirmation_path=confirmation,
            force_dir=force_dir,
            opening_manifest_path=openings,
            engine_code_sha="a" * 40,
        )

    def test_f2m_requires_two_established_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = self.run_case(
                Path(temporary),
                force(0.58, 0.55, 0.61),
                force(0.57, 0.54, 0.60),
            )
        self.assertEqual(payload["verdict"], NEW_CHAMPION)
        self.assertEqual(payload["recommended_general_champion"], "F2M")
        self.assertFalse(payload["general_champion_promotion_authorized"])
        self.assertFalse(payload["m2_launch_authorized"])

    def test_incumbent_survives_inconclusive_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = self.run_case(
                Path(temporary),
                force(0.53, 0.50, 0.56),
                force(0.51, 0.48, 0.54),
            )
        self.assertEqual(payload["verdict"], INCONCLUSIVE)
        self.assertEqual(payload["recommended_general_champion"], "GEN2_MMTO")

    def test_established_loss_keeps_gen2(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = self.run_case(
                Path(temporary),
                force(0.47, 0.44, 0.50),
                force(0.45, 0.42, 0.48),
            )
        self.assertEqual(payload["verdict"], GEN2_RETAINS)
        self.assertEqual(payload["l3_pure_champion"], "F2M")
        self.assertEqual(payload["m2_parent"], "F2M")


if __name__ == "__main__":
    unittest.main()
