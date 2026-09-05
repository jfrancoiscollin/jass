from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jobs.tools import adaptive_sibling_b2_statistics as subject


ROOT = Path(__file__).resolve().parents[2]


class PrimitiveTests(unittest.TestCase):
    def test_splitmix_vectors_and_unbiased_indices(self):
        expected_uint64 = [
            12190517145770752659, 17056246690006036188,
            6697740309985992035, 3790258129315742819,
            3813716183820301013, 16892144174123549047,
            4563586569523810623, 11919103764564493305,
            11423604901004298786, 6083973601287406282,
            15537584579802632926, 11808120023216637524,
            6252377709549218322, 5269630383170036733,
            275585058478309439, 7829160013152048777,
            10956957404772350331, 4592729468793784319,
            17829457990175366761, 10179070114036765784,
        ]
        generator = subject.SplitMix64(subject.BOOTSTRAP_SEED)
        self.assertEqual(
            [generator.next_uint64() for _ in range(20)],
            expected_uint64,
        )
        expected_indices = [
            159, 188, 35, 319, 13, 47, 123, 305, 286, 282,
            426, 24, 322, 233, 439, 277, 331, 319, 261, 284,
        ]
        generator = subject.SplitMix64(subject.BOOTSTRAP_SEED)
        self.assertEqual(
            [generator.randbelow(500) for _ in range(20)],
            expected_indices,
        )
        self.assertEqual(generator.generated, 20)
        self.assertEqual(generator.rejected, 0)

    def test_type1_quantile_has_no_interpolation(self):
        values = [4.0, 1.0, 3.0, 2.0]
        self.assertEqual(subject.inverse_edf_type1(values, 0.25), 1.0)
        self.assertEqual(subject.inverse_edf_type1(values, 0.50), 2.0)
        self.assertEqual(subject.inverse_edf_type1(values, 0.51), 3.0)
        self.assertEqual(subject.inverse_edf_type1(values, 1.00), 4.0)
        with self.assertRaises(subject.StatisticsContractError):
            subject.inverse_edf_type1([], 0.5)

    def test_clopper_pearson_reference_values(self):
        references = [
            (subject.clopper_pearson_upper, 0, 250, 0.020096023480),
            (subject.clopper_pearson_upper, 0, 500, 0.010099006708),
            (subject.clopper_pearson_upper, 5, 500, 0.027393870699),
            (subject.clopper_pearson_upper, 9, 500, 0.038810264081),
            (subject.clopper_pearson_lower, 467, 500, 0.901155260433),
            (subject.clopper_pearson_lower, 466, 500, 0.898794333267),
        ]
        for function, x, n, expected in references:
            with self.subTest(function=function.__name__, x=x, n=n):
                self.assertAlmostEqual(
                    function(x, n, subject.ALPHA_CELL),
                    expected,
                    delta=1e-12,
                )
        self.assertEqual(
            subject.clopper_pearson_upper(500, 500, subject.ALPHA_CELL), 1.0
        )
        self.assertEqual(
            subject.clopper_pearson_lower(0, 500, subject.ALPHA_CELL), 0.0
        )


class ParentContractTests(unittest.TestCase):
    def test_parent_semantics_and_integer_types_fail_closed(self):
        base = subject.build_synthetic_parent_stats()[0]
        with self.assertRaisesRegex(
            subject.StatisticsContractError, "same_row requires"
        ):
            dataclasses.replace(base, same_row=True, value_equivalent=False)
        with self.assertRaisesRegex(
            subject.StatisticsContractError, "signal direction cannot be numeric"
        ):
            dataclasses.replace(
                base,
                value_equivalent=False,
                signal_event=True,
                signal_direction_code=1,
                numeric_eligible=True,
            )
        with self.assertRaisesRegex(
            subject.StatisticsContractError,
            "exact_mismatch cannot be numeric-eligible",
        ):
            dataclasses.replace(
                base,
                exact_mismatch=True,
                numeric_eligible=True,
                numeric_component=1,
            )
        with self.assertRaisesRegex(subject.StatisticsContractError, "must be boolean"):
            subject.ParentStatsSufficientV1.from_mapping({
                **base.to_mapping(),
                "same_row": 1,
            })
        with self.assertRaisesRegex(subject.StatisticsContractError, "fields mismatch"):
            subject.ParentStatsSufficientV1.from_mapping({
                **base.to_mapping(),
                "unexpected": 0,
            })

    def test_jsonl_round_trip_is_canonical_and_exact(self):
        rows = subject.build_synthetic_parent_stats()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "parents.jsonl"
            raw = subject.write_parent_stats_sufficient_jsonl(path, rows)
            loaded, observed = subject.load_parent_stats_sufficient_jsonl(path)
            self.assertEqual(observed, raw)
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r", raw)
            self.assertEqual(loaded, rows)
            first = raw.splitlines()[0]
            self.assertEqual(
                first,
                json.dumps(
                    rows[0].to_mapping(),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode(),
            )

    def test_jsonl_rejects_noncanonical_and_duplicate_keys(self):
        row = subject.build_synthetic_parent_stats()[0].to_mapping()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "parents.jsonl"
            path.write_bytes((json.dumps(row) + "\n").encode())
            with self.assertRaisesRegex(subject.StatisticsContractError, "not canonical"):
                subject.load_parent_stats_sufficient_jsonl(path)
            canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
            duplicate = canonical[:-1] + ',"cell":"P0_stm0"}\n'
            path.write_bytes(duplicate.encode())
            with self.assertRaisesRegex(subject.StatisticsContractError, "duplicate key"):
                subject.load_parent_stats_sufficient_jsonl(path)

    def test_population_and_bootstrap_overflow_fail_closed(self):
        rows = subject.build_synthetic_parent_stats()
        with self.assertRaisesRegex(subject.StatisticsContractError, "expected 4000"):
            subject.validate_parent_population(rows[:-1])
        unsafe_fields = {
            "full_nodes": subject.UINT64_MAX // subject.CELL_SIZE + 1,
            "shadow_nodes": subject.UINT64_MAX // subject.CELL_SIZE + 1,
            "numeric_component": subject.INT64_MAX // subject.CELL_SIZE + 1,
        }
        for field, value in unsafe_fields.items():
            with self.subTest(field=field):
                unsafe = list(rows)
                unsafe[0] = dataclasses.replace(unsafe[0], **{field: value})
                with self.assertRaisesRegex(
                    subject.StatisticsContractError, "may overflow"
                ):
                    subject.validate_parent_population(unsafe)


class SyntheticFixtureTests(unittest.TestCase):
    def test_fixture_has_explicit_expected_integer_truth(self):
        rows = subject.build_synthetic_parent_stats()
        truth = subject.verify_synthetic_truth(rows)
        self.assertEqual(len(rows), 4000)
        self.assertEqual(truth["global"], {
            "rows": 4000,
            "full_nodes": 4_014_998_000,
            "shadow_nodes": 2_007_998_000,
            "fully_nonexact": 3200,
            "fully_nonexact_full_nodes": 3_212_000_000,
            "fully_nonexact_shadow_nodes": 1_606_400_000,
            "same_row": 3680,
            "value_equivalent": 3840,
            "exact_mismatch": 0,
            "signal_event": 24,
            "signal_win_to_unresolved": 8,
            "signal_win_to_loss": 8,
            "signal_unresolved_to_loss": 8,
            "signal_loss_to_unresolved": 0,
            "signal_loss_to_win": 8,
            "signal_unresolved_to_win": 0,
            "numeric_eligible": 2000,
            "numeric_delta": 7128,
            "moderate_1_99": 2752,
            "numeric_ge_100": 32,
            "maximum_numeric_delta": 150,
        })
        for cell_index, cell in enumerate(subject.CELL_ORDER):
            expected = truth["cells"][cell]
            self.assertEqual(expected["rows"], 500)
            self.assertEqual(expected["full_nodes"], 500_124_750 + 500_000 * cell_index)
            self.assertEqual(expected["shadow_nodes"], 250_124_750 + 250_000 * cell_index)
            self.assertEqual(expected["fully_nonexact"], 400)
            self.assertEqual(expected["same_row"], 460)
            self.assertEqual(expected["value_equivalent"], 480)
            self.assertEqual(expected["signal_event"], 3)
            self.assertEqual(expected["signal_win_to_unresolved"], 1)
            self.assertEqual(expected["signal_win_to_loss"], 1)
            self.assertEqual(expected["signal_unresolved_to_loss"], 1)
            self.assertEqual(expected["signal_loss_to_win"], 1)
            self.assertEqual(expected["numeric_eligible"], 250)
            self.assertEqual(expected["numeric_delta"], 891)
            self.assertEqual(expected["moderate_1_99"], 344)
            self.assertEqual(expected["numeric_ge_100"], 4)

    def test_small_internal_bootstrap_is_deterministic_and_has_seven_families(self):
        rows = subject.build_synthetic_parent_stats()
        progress = []
        first = subject._analyze_parent_stats_for_test(
            rows,
            replications=20,
            progress_callback=progress.append,
        )
        second = subject._analyze_parent_stats_for_test(rows, replications=20)
        self.assertEqual(first, second)
        # Keep the fixed stream/quantile checksum independent of libm's lgamma.
        # Clopper-Pearson is checked separately to the normative 1e-12 tolerance.
        encoded = json.dumps({
            "bootstrap_intervals": first["bootstrap_intervals"],
            "bootstrap_stream": first["bootstrap_stream"],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            "6843f938dc56b61680f78e99819dff4d98e4d7c18fc65dcfbaf1801e938b34d8",
        )
        self.assertEqual(first["status"], "VALID")
        self.assertEqual(first["bootstrap_stream"]["accepted_draws"], 80_000)
        self.assertEqual(progress, [{
            "completed_replications": 20,
            "total_replications": 20,
            "accepted_draws": 80_000,
            "generated_uint64": 80_000,
            "rejected_uint64": 0,
        }])
        self.assertEqual(
            tuple(first["gates"]["cell_families"]),
            subject.FAMILY_ORDER,
        )
        self.assertTrue(all(
            family["alpha_cell"] == subject.ALPHA_CELL
            for family in first["gates"]["cell_families"].values()
        ))
        self.assertFalse(first["gates"]["all_passed"])
        self.assertFalse(first["gates"]["cell_families"]["signal_event"]["passed"])
        self.assertFalse(first["gates"]["cell_families"]["numeric_ge_100"]["passed"])

    def test_zero_cell_support_returns_invalid_without_bootstrap(self):
        rows = subject.build_synthetic_parent_stats()
        alterations = {
            "numeric": (
                lambda row: dataclasses.replace(
                    row, numeric_eligible=False, numeric_component=0
                ),
                "P0_stm0 numeric_eligible below 50",
            ),
            "fully_nonexact": (
                lambda row: dataclasses.replace(row, fully_nonexact=False),
                "P0_stm0 fully_nonexact below 100",
            ),
            "shadow_nodes": (
                lambda row: dataclasses.replace(row, shadow_nodes=0),
                "P0_stm0 node support is zero",
            ),
        }
        for label, (alter, reason) in alterations.items():
            with self.subTest(label=label):
                altered = [
                    alter(row) if row.cell == subject.CELL_ORDER[0] else row
                    for row in rows
                ]
                report = subject._analyze_parent_stats_for_test(
                    altered, replications=20
                )
                self.assertEqual(report["status"], "INVALID_UNKNOWN")
                self.assertFalse(report["scientific_gates_evaluated"])
                self.assertIn(reason, report["support"]["reasons"])
                self.assertNotIn("bootstrap_stream", report)

    def test_supported_population_with_zero_bootstrap_denominator_is_invalid(self):
        rows = subject.build_synthetic_parent_stats()
        generator = subject.SplitMix64(subject.BOOTSTRAP_SEED)
        first_cell_draws = {
            generator.randbelow(subject.CELL_SIZE)
            for _ in range(subject.CELL_SIZE)
        }
        eligible_indices = set()
        for index in range(subject.CELL_SIZE):
            if index not in first_cell_draws and index not in (25, 125, 225, 325):
                eligible_indices.add(index)
                if len(eligible_indices) == 50:
                    break
        self.assertEqual(len(eligible_indices), 50)
        altered = []
        for row in rows:
            if row.cell != subject.CELL_ORDER[0]:
                altered.append(row)
                continue
            local_index = row.parent_id % subject.CELL_SIZE
            altered.append(dataclasses.replace(
                row,
                numeric_eligible=local_index in eligible_indices,
                numeric_component=0,
            ))
        report = subject._analyze_parent_stats_for_test(altered, replications=1)
        self.assertTrue(report["support"]["valid"])
        self.assertEqual(report["status"], "INVALID_UNKNOWN")
        self.assertFalse(report["scientific_gates_evaluated"])
        self.assertEqual(
            report["runtime_failure"],
            "bootstrap zero denominator in P0_stm0",
        )

    def test_all_gate_thresholds_are_inclusive(self):
        global_intervals = {
            "all_parent_saving": {"lcb95": 0.30},
            "fully_nonexact_saving": {"lcb95": 0.30},
            "same_row_rate": {"lcb95": 0.94},
            "value_equivalence_rate": {"lcb95": 0.96},
            "conditional_numeric_mean": {"ucb95": 2.0},
        }
        cell_intervals = {
            "all_parent_saving": {},
            "fully_nonexact_saving": {},
            "moderate_1_99": {},
            "total_component": {},
        }
        cp_cells = {}
        for cell_index, cell in enumerate(subject.CELL_ORDER):
            cell_intervals["all_parent_saving"][cell] = {"lcb_sim95": 0.20}
            cell_intervals["fully_nonexact_saving"][cell] = {"lcb_sim95": 0.20}
            cell_intervals["moderate_1_99"][cell] = {"ucb_sim95": 4.0}
            cell_intervals["total_component"][cell] = {"ucb_sim95": 6.0}
            cp_cells[cell] = {
                "value_equivalence_lcb_sim95": 0.90,
                "signal_event_ucb_sim95": 0.040 if cell_index == 0 else 0.017,
                "numeric_ge_100_ucb_sim95": 0.030 if cell_index == 0 else 0.012,
            }
        gates = subject._gate_report(
            {"exact_mismatch": 0, "maximum_numeric_delta": 1000},
            {"global": global_intervals, "cells": cell_intervals},
            cp_cells,
        )
        self.assertTrue(gates["all_passed"])
        self.assertTrue(all(gates["global_gates"].values()))
        self.assertTrue(all(
            family["passed"] for family in gates["cell_families"].values()
        ))
        cp_cells[subject.CELL_ORDER[0]]["signal_event_ucb_sim95"] = 0.0400001
        signal_failure = subject._gate_report(
            {"exact_mismatch": 0, "maximum_numeric_delta": 1000},
            {"global": global_intervals, "cells": cell_intervals},
            cp_cells,
        )
        self.assertFalse(signal_failure["cell_families"]["signal_event"]["passed"])
        cp_cells[subject.CELL_ORDER[0]]["signal_event_ucb_sim95"] = 0.040
        cp_cells[subject.CELL_ORDER[0]]["numeric_ge_100_ucb_sim95"] = 0.0300001
        numeric_failure = subject._gate_report(
            {"exact_mismatch": 0, "maximum_numeric_delta": 1000},
            {"global": global_intervals, "cells": cell_intervals},
            cp_cells,
        )
        self.assertFalse(
            numeric_failure["cell_families"]["numeric_ge_100"]["passed"]
        )


class KernelReceiptAndCliTests(unittest.TestCase):
    def valid_kernel_receipt(self) -> dict:
        return {
            "kind": "SYNTHETIC_ARITHMETIC_ONLY",
            "scientific_parents": 0,
            "draws": 2_000_000,
            "integer_accumulations_per_draw": 10,
            "splitmix_test_vector_pass": True,
            "elapsed_seconds": 3.5,
            "draws_per_second": 571_428.5,
            "extrapolated_800m_draw_kernel_seconds": 1400.0,
            "kernel_only_excludes_parsing_ratios_quantiles_and_final_validation": True,
            "synthetic_accumulator_checksums": list(
                subject.KERNEL_EXPECTED_CHECKSUMS
            ),
            "environment": {
                "python_version": "observed-by-1773",
                "python_implementation": "CPython",
            },
        }

    def test_kernel_receipt_is_linked_without_pinning_a_guessed_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kernel.json"
            raw = (
                json.dumps(self.valid_kernel_receipt(), sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode()
            path.write_bytes(raw)
            receipt, digest = subject.load_kernel_receipt(path)
            self.assertEqual(receipt["draws"], 2_000_000)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertEqual(
                receipt["environment"]["python_version"],
                "observed-by-1773",
            )
            bad = self.valid_kernel_receipt()
            bad["draws"] = 20
            path.write_bytes((
                json.dumps(bad, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode())
            with self.assertRaisesRegex(subject.StatisticsContractError, "draws mismatch"):
                subject.load_kernel_receipt(path)
            bad = self.valid_kernel_receipt()
            bad["synthetic_accumulator_checksums"][0] += 1
            path.write_bytes((
                json.dumps(bad, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode())
            with self.assertRaisesRegex(
                subject.StatisticsContractError, "checksums invalid"
            ):
                subject.load_kernel_receipt(path)

    def test_cli_exposes_no_replication_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([
                sys.executable,
                str(ROOT / "jobs/tools/adaptive_sibling_b2_statistics.py"),
                "--preflight-synthetic",
                "--kernel-receipt", str(Path(temporary) / "kernel.json"),
                "--out-dir", str(Path(temporary) / "out"),
                "--replications", "20",
            ], check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("unrecognized arguments: --replications 20", result.stderr)
            self.assertFalse((Path(temporary) / "out").exists())
        self.assertEqual(subject.BOOTSTRAP_REPLICATIONS, 200_000)
        self.assertEqual(subject.BOOTSTRAP_SEED, 2026110717)

    def test_preflight_runtime_must_match_authenticated_kernel_environment(self):
        observed = subject.runtime_environment()
        receipt = self.valid_kernel_receipt()
        receipt["environment"] = {
            key: observed[key] for key in (
                "python_version", "python_implementation", "python_executable",
                "platform", "machine", "libc", "nproc",
            )
        }
        validated = subject.validate_runtime_against_kernel(receipt)
        self.assertEqual(validated["python_version"], observed["python_version"])
        receipt["environment"]["python_version"] = "different"
        with self.assertRaisesRegex(
            subject.StatisticsContractError, "runtime differs.*python_version"
        ):
            subject.validate_runtime_against_kernel(receipt)
        rss = subject.peak_rss_bytes()
        self.assertTrue(rss is None or type(rss) is int and rss >= 0)


if __name__ == "__main__":
    unittest.main()
