from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools import l3_failed_conversion_weights as weights


CODE_SHA = "a" * 40


def _record(
    *,
    white_men: int,
    white_kings: int = 0,
    black_men: int,
    black_kings: int = 0,
    stm: int = 0,
    wdl: int = 0,
) -> bytes:
    return struct.pack(
        "<QQQQBib",
        white_men,
        white_kings,
        black_men,
        black_kings,
        stm,
        0,
        wdl,
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    # Train: white converts, white draws, black loses, equal material.
    # Holdout: failed conversion (must nevertheless receive raw weight 1).
    rows = [
        _record(white_men=0b111, black_men=0b1, stm=0, wdl=1),
        _record(white_men=0b111, black_men=0b1, stm=0, wdl=0),
        _record(white_men=0b1, black_men=0b111, stm=0, wdl=1),
        _record(white_men=0b11, black_men=0b11, stm=1, wdl=-1),
        _record(white_men=0b111, black_men=0b1, stm=1, wdl=1),
    ]
    data = tmp_path / "corpus.jnnw"
    data.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + b"".join(rows))
    split = tmp_path / "split.json"
    split.write_text(
        json.dumps(
            {
                "schema": 1,
                "operation": "split",
                "split_unit": "opening_id",
                "holdout_mod": 20,
                "seed": 314159,
                "records": 5,
                "train_records": 4,
                "holdout_records": 1,
                "train_openings": 4,
                "holdout_openings": 1,
                "tail_is_holdout": True,
            }
        ),
        encoding="utf-8",
    )
    return data, split


def _build(
    tmp_path: Path,
    name: str = "a",
    failed_weight: float = 2.0,
) -> tuple[Path, Path, dict]:
    data, split = _fixture(tmp_path)
    out = tmp_path / f"{name}.npy"
    report = tmp_path / f"{name}.json"
    payload = weights.build_weights(
        data_path=data,
        split_path=split,
        output_path=out,
        report_path=report,
        failed_weight=failed_weight,
        code_sha=CODE_SHA,
    )
    return out, report, payload


class FailedConversionWeightsTests(unittest.TestCase):
    def test_formula_is_train_only_aligned_float32_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out, report, payload = _build(Path(directory))
            observed = np.load(out, allow_pickle=False)
            np.testing.assert_array_equal(
                observed,
                np.asarray([1.0, 2.0, 2.0, 1.0, 1.0], dtype=np.float32),
            )
            self.assertEqual(observed.dtype, np.float32)
            self.assertEqual(
                payload["train_counts"],
                {
                    "failed_conversion": 2,
                    "converted_material_leader": 1,
                    "equal_material": 1,
                },
            )
            self.assertTrue(payload["holdout"]["all_raw_weights_one"])
            self.assertFalse(
                payload["holdout"]["formula_evaluated_for_weighting"]
            )
            self.assertEqual(payload["raw_train_weights"]["mean"], 1.5)
            self.assertEqual(
                payload["effective_sample_size_before_normalization"]["ess"],
                3.6,
            )
            self.assertEqual(
                payload["output"]["sha256"],
                hashlib.sha256(out.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                json.loads(report.read_text(encoding="utf-8")), payload
            )

    def test_output_is_bit_deterministic_across_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, first_report, first_payload = _build(
                root / "first", "weights"
            )
            second, second_report, second_payload = _build(
                root / "second", "weights"
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_report.read_bytes(), second_report.read_bytes())
            self.assertEqual(first_payload, second_payload)

    def test_multiplier_one_builds_uniform_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out, _, payload = _build(
                Path(directory),
                failed_weight=1.0,
            )
            np.testing.assert_array_equal(
                np.load(out, allow_pickle=False),
                np.ones(5, dtype=np.float32),
            )
            self.assertEqual(payload["raw_train_weights"]["mean"], 1.0)
            self.assertEqual(
                payload["effective_sample_size_before_normalization"][
                    "ess_fraction"
                ],
                1.0,
            )

    def test_existing_outputs_are_never_overwritten(self) -> None:
        for target in ("weights", "report"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data, split = _fixture(root)
                out = root / "weights.npy"
                report = root / "weights.json"
                protected = out if target == "weights" else report
                protected.write_bytes(b"sentinel")
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    weights.build_weights(
                        data_path=data,
                        split_path=split,
                        output_path=out,
                        report_path=report,
                        failed_weight=2.0,
                        code_sha=CODE_SHA,
                    )
                self.assertEqual(protected.read_bytes(), b"sentinel")

    def test_pair_publication_rolls_back_first_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weights_temporary = root / "weights.tmp"
            report_temporary = root / "report.tmp"
            weights_target = root / "weights.npy"
            report_target = root / "weights.json"
            weights_temporary.write_bytes(b"weights")
            report_temporary.write_bytes(b"report")
            report_target.write_bytes(b"sentinel")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                weights._publish_pair(
                    weights_temporary,
                    weights_target,
                    report_temporary,
                    report_target,
                )
            self.assertFalse(weights_target.exists())
            self.assertEqual(report_target.read_bytes(), b"sentinel")
            self.assertTrue(weights_temporary.exists())
            self.assertTrue(report_temporary.exists())

    def test_invalid_multipliers_fail_closed(self) -> None:
        for value in (0.0, 0.999, 4.1, float("nan"), float("inf")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data, split = _fixture(root)
                with self.assertRaisesRegex(ValueError, "failed weight"):
                    weights.build_weights(
                        data_path=data,
                        split_path=split,
                        output_path=root / "weights.npy",
                        report_path=root / "weights.json",
                        failed_weight=value,
                        code_sha=CODE_SHA,
                    )

    def test_truncated_input_and_bad_split_fail_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, split = _fixture(root)
            data.write_bytes(data.read_bytes()[:-1])
            out = root / "weights.npy"
            report = root / "weights.json"
            with self.assertRaisesRegex(ValueError, "size"):
                weights.build_weights(
                    data_path=data,
                    split_path=split,
                    output_path=out,
                    report_path=report,
                    failed_weight=2.0,
                    code_sha=CODE_SHA,
                )
            self.assertFalse(out.exists())
            self.assertFalse(report.exists())

            data, split = _fixture(root)
            manifest = json.loads(split.read_text(encoding="utf-8"))
            manifest["tail_is_holdout"] = False
            split.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "tail_is_holdout"):
                weights.build_weights(
                    data_path=data,
                    split_path=split,
                    output_path=out,
                    report_path=report,
                    failed_weight=2.0,
                    code_sha=CODE_SHA,
                )


if __name__ == "__main__":
    unittest.main()
