import argparse
import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reverse_scale_diagnostic",
    ROOT / "jobs/tools/l3_reverse_seed_scale_diagnostic.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
CODE_SHA = "a" * 40


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model(path: Path, weights: list[int]) -> None:
    path.write_bytes(struct.pack("<5I", 0x57544A50, 3, 100, 2, 1) + struct.pack("<6i", *weights))


def atlas(path: Path, records: int, treatment: bool) -> None:
    win = records // 3 + (100 if treatment else 0)
    draw = records // 3
    loss = records - win - draw
    row = {
        "bucket": "midgame",
        "conversion": {
            "converted_records": records // 4 + (50 if treatment else 0),
            "drawn_records": records // 8,
            "eligible_records": records // 2,
            "rate": 0.5,
            "reversed_records": records // 8,
        },
        "dimension": "phase",
        "game_share": 1.0,
        "games": records // 10,
        "opening_share": 1.0,
        "openings": records // 20,
        "record_share": 1.0,
        "records": records,
        "terminal_winner_records": {"black": loss, "draw": draw, "white": win},
        "wdl_stm_rates": {"draw": draw / records, "loss": loss / records, "win": win / records},
        "wdl_stm_records": {"draw": draw, "loss": loss, "win": win},
    }
    payload = {
        "schema": "l3_blind_spot_atlas",
        "records": records,
        "games": records // 10,
        "openings": records // 20,
        "code_sha": CODE_SHA,
        "diagnostic_only": True,
        "gate_authorized": False,
        "promotion_authorized": False,
        "atlas": [row],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def source(stage: str, records: int, parent_sha: str, control_sha: str, treatment_sha: str) -> dict:
    verdict = {
        "stage2": "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
        "stage4": "L3_PURE_REVERSE_SEED_SCALE4M_CAUSAL_AB_ARMS_READY",
    }[stage]
    return {
        "verdict": verdict,
        "primary_contrast": "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY",
        "design": {"records_per_arm": records},
        "parent": {"model_sha256": parent_sha},
        "arms": {
            "control": {"model_sha256": control_sha, "fit": {"converged": True}},
            "treatment": {"model_sha256": treatment_sha, "fit": {"converged": True}},
        },
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def readout(stage: str, records: int, control_sha: str, treatment_sha: str) -> dict:
    verdict = {
        "stage2": "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95",
        "stage4": "L3_PURE_REVERSE_SEED_SCALE4M_BELOW_MATCHED_CONTROL",
    }[stage]
    return {
        "verdict": verdict,
        "protocol": {"records_per_arm": records, "fresh_disjoint_openings": True},
        "models": {"control_sha256": control_sha, "treatment_sha256": treatment_sha},
        "force_views_summed": {"n": 6000, "rate_treatment": 0.51 if stage == "stage2" else 0.48},
        "scientific_result": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


class ReverseSeedScaleDiagnosticTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> argparse.Namespace:
        model_paths = {}
        values = {
            "parent": [0, 0, 0, 0, 0, 0],
            "stage2_control": [1, 0, 0, 0, 0, 0],
            "stage2_treatment": [2, 1, 0, 0, 0, 0],
            "stage4_control": [2, 0, 1, 0, 0, 0],
            "stage4_treatment": [1, -1, 1, 0, 0, 0],
        }
        for label, weights in values.items():
            path = root / f"{label}.pjtw"
            model(path, weights)
            model_paths[label] = path
        atlases = []
        for stage, checkpoints in (("stage2", (1_000_000, 2_000_000)), ("stage4", (1_000_000, 2_000_000, 3_000_000, 4_000_000))):
            for arm in ("control", "treatment"):
                for records in checkpoints:
                    label = f"{stage}_{arm}_{records}"
                    path = root / f"{label}.json"
                    atlas(path, records, arm == "treatment")
                    atlases.append((label, path))
        source2 = source("stage2", 2_000_000, sha(model_paths["parent"]), sha(model_paths["stage2_control"]), sha(model_paths["stage2_treatment"]))
        source4 = source("stage4", 4_000_000, sha(model_paths["parent"]), sha(model_paths["stage4_control"]), sha(model_paths["stage4_treatment"]))
        paths = {}
        for name, payload in (
            ("source2", source2), ("source4", source4),
            ("readout2", readout("stage2", 2_000_000, sha(model_paths["stage2_control"]), sha(model_paths["stage2_treatment"]))),
            ("readout4", readout("stage4", 4_000_000, sha(model_paths["stage4_control"]), sha(model_paths["stage4_treatment"]))),
        ):
            path = root / f"{name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            paths[name] = path
        return argparse.Namespace(
            code_sha=CODE_SHA,
            atlas=atlases,
            model=list(model_paths.items()),
            stage2_summary=paths["source2"],
            stage4_summary=paths["source4"],
            readout2=paths["readout2"],
            readout4=paths["readout4"],
        )

    def test_builds_diagnostic_without_gate(self):
        with tempfile.TemporaryDirectory() as raw:
            args = self.build_fixture(Path(raw))
            report = MODULE.build_report(args)
            self.assertEqual(report["verdict"], "L3_PURE_REVERSE_SEED_SCALE_DIAGNOSTIC_COMPLETE")
            self.assertFalse(report["scientific_result"])
            self.assertFalse(report["promotion_authorized"])
            self.assertIsNone(report["automatic_next_job"])
            self.assertEqual(report["paired_prefix_diagnostics"]["stage4"]["4000000"]["records_per_arm"], 4_000_000)
            self.assertLess(report["model_geometry"]["treatment_minus_control"]["cosine_stage2_vs_stage4"], 0)

    def test_rejects_readout_model_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            args = self.build_fixture(root)
            payload = json.loads(args.readout4.read_text(encoding="utf-8"))
            payload["models"]["treatment_sha256"] = "0" * 64
            args.readout4.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "model mismatch"):
                MODULE.build_report(args)


if __name__ == "__main__":
    unittest.main()
