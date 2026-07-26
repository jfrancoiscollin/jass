import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_turnover_confirmation import (
    CHAMPION_REVIEW,
    DIRECTION_REPLICATED,
    EFFECT_CONFIRMED,
    NOT_REPLICATED,
    PREVIOUS_OPENING_SEED,
    PREVIOUS_OPENING_SHA,
    TURNOVER_CODE_SHA,
    TURNOVER_CORPUS_SHA,
    TURNOVER_META_SHA,
    TURNOVER_MODEL_SHA,
    build_confirmation,
    summarize_counts,
)


OPENING_SEED = 11_235_813
OPENING_SHA = "a" * 64
CANDIDATE_SHA = "b" * 64


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def report(rate_wins: int, draws: int, n: int) -> dict:
    value = summarize_counts(rate_wins, draws, n - rate_wins - draws)
    value["complete"] = True
    return value


def previous() -> dict:
    force = {
        "q00_vs_M2": report(515, 14, 1_000),
        "native_vs_M2": report(502, 17, 1_000),
        "q00_vs_F2M": report(511, 20, 1_000),
        "native_vs_F2M": report(505, 13, 1_000),
    }
    for row in force.values():
        row.pop("complete")
    checks = {
        control: {
            view: {
                "positive_point_estimate": True,
                "superiority_established": False,
                "regression_not_established": True,
            }
            for view in ("q00", "native")
        }
        for control in ("M2", "F2M")
    }
    return {
        "verdict": "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW",
        "recommendation": "independent_turnover_confirmation",
        "all_guardrails_pass": True,
        "guardrails": {"static": True},
        "promotion_authorized": False,
        "automatic_next_job": None,
        "training_summary": {
            "code_sha": TURNOVER_CODE_SHA,
            "model_sha256": TURNOVER_MODEL_SHA,
            "training_corpus_sha256": TURNOVER_CORPUS_SHA,
            "training_meta_sha256": TURNOVER_META_SHA,
            "experiment_variant": "TURNOVER_1_1",
            "parent": "F2M",
            "fresh_only": False,
            "training_records": 2_000_000,
            "historical_replay_records": 1_000_000,
            "fresh_records": 1_000_000,
            "temporal_distribution_records": {
                "fresh_m2": 1_000_000,
                "parent_f2m": 1_000_000,
            },
            "new_generation_performed": False,
        },
        "opening_manifest": {
            "records": 500,
            "unique_records": 500,
            "overlap_records": 0,
            "generator_seed": PREVIOUS_OPENING_SEED,
            "sha256": PREVIOUS_OPENING_SHA,
        },
        "force": force,
        "primary_checks": checks,
    }


def openings() -> dict:
    return {
        "records": 1_000,
        "unique_records": 1_000,
        "overlap_records": 0,
        "generator_seed": OPENING_SEED,
        "sha256": OPENING_SHA,
        "candidate_sha256": CANDIDATE_SHA,
        "excluded_sources": {
            "/tmp/prior-m2-independent.fen": 500,
            "/tmp/prior-d10-independent.fen": 500,
            "/tmp/prior-d12-independent.fen": 500,
            "/tmp/prior-turnover-independent.fen": 500,
        },
    }


class TurnoverConfirmationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        m2_q00: tuple[int, int],
        m2_native: tuple[int, int],
        f2m_q00: tuple[int, int],
        f2m_native: tuple[int, int],
    ):
        force_dir = root / "force"
        force_dir.mkdir()
        previous_path = root / "previous.json"
        openings_path = root / "openings.json"
        write(previous_path, previous())
        write(openings_path, openings())
        for control, view, (wins, draws) in (
            ("M2", "q00", m2_q00),
            ("M2", "native", m2_native),
            ("F2M", "q00", f2m_q00),
            ("F2M", "native", f2m_native),
        ):
            write(
                force_dir / f"force-{view}-TURNOVER-vs-{control}.json",
                report(wins, draws, 2_000),
            )
        return force_dir, previous_path, openings_path

    def build(self, prepared):
        force_dir, previous_path, openings_path = prepared
        return build_confirmation(
            force_dir=force_dir,
            previous_evaluation_path=previous_path,
            opening_manifest_path=openings_path,
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
            expected_candidate_sha256=CANDIDATE_SHA,
        )

    def test_champion_review_needs_pooled_superiority_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    m2_q00=(1_080, 20),
                    m2_native=(1_075, 20),
                    f2m_q00=(1_075, 20),
                    f2m_native=(1_075, 20),
                )
            )
        self.assertEqual(result["verdict"], CHAMPION_REVIEW)
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["pooled_force"]["q00_vs_M2"]["n"], 3_000)

    def test_effect_can_be_confirmed_before_champion_superiority(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    m2_q00=(1_080, 20),
                    m2_native=(1_075, 20),
                    f2m_q00=(1_005, 20),
                    f2m_native=(1_005, 20),
                )
            )
        self.assertEqual(result["verdict"], EFFECT_CONFIRMED)

    def test_positive_replication_can_remain_underpowered(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    m2_q00=(1_020, 20),
                    m2_native=(1_015, 20),
                    f2m_q00=(1_010, 20),
                    f2m_native=(1_005, 20),
                )
            )
        self.assertEqual(result["verdict"], DIRECTION_REPLICATED)

    def test_missing_direction_closes_one_to_one_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    m2_q00=(980, 20),
                    m2_native=(1_015, 20),
                    f2m_q00=(1_010, 20),
                    f2m_native=(1_005, 20),
                )
            )
        self.assertEqual(result["verdict"], NOT_REPLICATED)

    def test_previous_certificate_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2_q00=(1_020, 20),
                m2_native=(1_015, 20),
                f2m_q00=(1_010, 20),
                f2m_native=(1_005, 20),
            )
            value = json.loads(prepared[1].read_text(encoding="utf-8"))
            value["training_summary"]["model_sha256"] = "0" * 64
            write(prepared[1], value)
            with self.assertRaisesRegex(ValueError, "model/training"):
                self.build(prepared)

    def test_confirmation_pool_must_exclude_previous_turnover_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2_q00=(1_020, 20),
                m2_native=(1_015, 20),
                f2m_q00=(1_010, 20),
                f2m_native=(1_005, 20),
            )
            value = json.loads(prepared[2].read_text(encoding="utf-8"))
            value["excluded_sources"].pop("/tmp/prior-turnover-independent.fen")
            write(prepared[2], value)
            with self.assertRaisesRegex(ValueError, "opening-pool"):
                self.build(prepared)


if __name__ == "__main__":
    unittest.main()
