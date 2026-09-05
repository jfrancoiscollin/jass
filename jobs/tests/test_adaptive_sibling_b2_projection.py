from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobs.tools import adaptive_sibling_b2_projection as subject
from jobs.tools import adaptive_sibling_teacher_shadow as legacy


def row(
    row_index: int,
    q5: int = 0,
    q50: int = 0,
    *,
    utility: int = 2,
    terminal: bool = False,
    tb: bool = False,
    n5: int = 5_000,
    n50: int = 50_000,
    n200: int = 200_000,
) -> dict[str, object]:
    return {
        "row_index": row_index,
        "child_rule_terminal": terminal,
        "child_tb_exact": tb,
        "exact_parent_utility": utility,
        "q5k_parent": q5,
        "q50_parent": q50,
        "nodes5k": n5,
        "nodes50k": n50,
        "nodes200k": n200,
    }


def parent(rows: list[dict[str, object]], parent_id: int = 7) -> dict[str, object]:
    return {
        "schema": subject.INPUT_SCHEMA,
        "parent_id": parent_id,
        "phase": "P2",
        "stm": 1,
        "rows": rows,
    }


def project(value: dict[str, object]) -> tuple[dict[str, object], bytes]:
    return subject.project_parent(subject.parse_parent(value))


def legacy_result(value: dict[str, object]) -> legacy.ParentResult:
    rows = []
    for item in value["rows"]:
        exact = bool(item["child_rule_terminal"] or item["child_tb_exact"])
        rows.append(legacy.Row(
            row_index=item["row_index"],
            parent_id=value["parent_id"],
            exact=exact,
            exact_utility=item["exact_parent_utility"] if exact else None,
            q5=item["q5k_parent"],
            q50=item["q50_parent"],
            q200=0,
            n5=item["nodes5k"],
            n50=item["nodes50k"],
            n200=item["nodes200k"],
        ))
    return legacy.simulate_parent(value["parent_id"], rows)


class LegacyEquivalenceTests(unittest.TestCase):
    def assert_legacy_projection(self, value: dict[str, object]) -> dict[str, object]:
        receipt, _ = project(value)
        old = legacy_result(value)
        self.assertEqual(receipt["ordered_rows"], sorted(r["row_index"] for r in value["rows"]))
        self.assertEqual(receipt["S5_rows"], sorted(old.survivors50))
        self.assertEqual(receipt["S50_rows"], sorted(old.survivors200))
        expected_charge = [] if old.uncertified_shadow else sorted(old.survivors200)
        self.assertEqual(receipt["S200_charge_rows"], expected_charge)
        expected_prechoice = old.shadow_choice if old.exact_win_shortcut or old.uncertified_shadow \
            or not old.survivors200 else None
        self.assertEqual(receipt["pre_q200_choice_row_or_null"], expected_prechoice)
        self.assertEqual(receipt["uncertified_shadow"], old.uncertified_shadow)
        if old.exact_win_shortcut or all(
            r["child_rule_terminal"] or r["child_tb_exact"] for r in value["rows"]
        ):
            expected_nodes5 = expected_nodes50 = expected_nodes200 = 0
        else:
            by_index = {r["row_index"]: r for r in value["rows"]}
            expected_nodes5 = sum(
                r["nodes5k"] for r in value["rows"]
                if not (r["child_rule_terminal"] or r["child_tb_exact"])
            )
            expected_nodes50 = sum(by_index[index]["nodes50k"] for index in old.survivors50)
            expected_nodes200 = 0 if old.uncertified_shadow else sum(
                by_index[index]["nodes200k"] for index in old.survivors200
            )
        self.assertEqual(receipt["shadow_nodes5"], expected_nodes5)
        self.assertEqual(receipt["shadow_nodes50"], expected_nodes50)
        self.assertEqual(receipt["shadow_nodes200"], expected_nodes200)
        self.assertEqual(receipt["shadow_nodes_total"], old.shadow_nodes)
        return receipt

    def test_exact_win_draw_loss_and_mixed_precedence(self):
        self.assertEqual(subject.EXACT_SHORTCUT_REASONS, {
            "EXACT_WIN", "ALL_EXACT_DRAW", "ALL_EXACT_LOSS",
        })
        self.assertEqual(subject.SOLE_SURVIVOR_REASONS, {
            "SOLE_UNRESOLVED_BEFORE_Q200",
        })
        exact_win = parent([
            row(5, utility=1, terminal=True), row(2, utility=1, tb=True), row(8, 900, 900),
        ])
        receipt = self.assert_legacy_projection(exact_win)
        self.assertEqual(receipt["pre_q200_choice_row_or_null"], 2)
        self.assertEqual(receipt["exact_shortcut_reason"], "EXACT_WIN")
        self.assertEqual(receipt["shadow_nodes_total"], 0)

        exact_draw = parent([row(4, utility=-1, terminal=True), row(3, utility=0, tb=True)])
        receipt = self.assert_legacy_projection(exact_draw)
        self.assertEqual(receipt["pre_q200_choice_row_or_null"], 3)
        self.assertEqual(receipt["exact_shortcut_reason"], "ALL_EXACT_DRAW")

        exact_loss = parent([row(9, utility=-1, terminal=True), row(1, utility=-1, tb=True)])
        receipt = self.assert_legacy_projection(exact_loss)
        self.assertEqual(receipt["pre_q200_choice_row_or_null"], 1)
        self.assertEqual(receipt["exact_shortcut_reason"], "ALL_EXACT_LOSS")

        mixed = parent([
            row(0, utility=0, tb=True), row(2, 300, 500), row(1, 250, 400),
        ])
        receipt = self.assert_legacy_projection(mixed)
        self.assertIsNone(receipt["exact_shortcut_reason"])
        self.assertEqual(receipt["S200_charge_rows"], [1, 2])

    def test_sole_unresolved_ties_and_margin_boundaries(self):
        sole = parent([row(0, utility=0, tb=True), row(1, 10, 20)])
        receipt = self.assert_legacy_projection(sole)
        self.assertEqual(receipt["S5_rows"], [1])
        self.assertEqual(receipt["S50_rows"], [1])
        self.assertEqual(receipt["S200_charge_rows"], [])
        self.assertEqual(receipt["pre_q200_choice_row_or_null"], 1)
        self.assertEqual(receipt["sole_survivor_reason"], "SOLE_UNRESOLVED_BEFORE_Q200")
        self.assertTrue(receipt["uncertified_shadow"])
        self.assertEqual(receipt["shadow_nodes_total"], 55_000)

        ties = parent([row(5, 300, 500), row(3, 300, 100), row(8, 0, 0)])
        receipt = self.assert_legacy_projection(ties)
        self.assertEqual(receipt["S5_rows"], [3, 5])
        self.assertEqual(receipt["S50_rows"], [3, 5])

        margins = parent([
            row(0, 300, 500), row(1, 200, 440), row(2, 199, 439), row(3, 0, 0),
        ])
        receipt = self.assert_legacy_projection(margins)
        self.assertEqual(receipt["S5_rows"], [0, 1])
        self.assertEqual(receipt["S50_rows"], [0, 1])


class BarrierTests(unittest.TestCase):
    def test_schema_has_no_q200_value_and_poison_is_never_consulted(self):
        fields = {field.name for field in dataclasses.fields(subject.DecisionRowV1)}
        self.assertEqual(fields, subject.DECISION_ROW_FIELDS)
        self.assertFalse(any("q200" in name.lower() for name in fields))

        class Poison:
            reads = 0

            def __getattribute__(self, name):
                if name == "reads":
                    return object.__getattribute__(self, name)
                type(self).reads += 1
                raise AssertionError("forbidden q200 poison consulted")

            def __str__(self):
                type(self).reads += 1
                raise AssertionError("forbidden q200 poison rendered")

        poison = Poison()
        bad = parent([row(0), row(1)])
        bad["rows"][0]["q200_parent"] = poison
        with self.assertRaisesRegex(subject.ProjectionError, "forbidden q200 key"):
            subject.parse_parent(bad)
        self.assertEqual(Poison.reads, 0)

        external_full_ladder = {"q200_parent": poison, "q200_family": poison, "q200_label": poison}
        receipt, _ = project(parent([row(0, 100, 100), row(1, 90, 90)]))
        self.assertEqual(Poison.reads, 0)
        self.assertEqual(set(external_full_ladder), {"q200_parent", "q200_family", "q200_label"})
        self.assertNotIn("nodes200k", subject.DecisionRowV1.__slots__)
        self.assertIsNone(receipt["pre_q200_choice_row_or_null"])

    def test_nodes200_perturbation_changes_only_clarified_fields(self):
        base = parent([
            row(0, 300, 500, n200=10),
            row(1, 250, 450, n200=20),
            row(2, 0, 0, n200=30),
        ])
        original, original_raw = project(base)

        charged = copy.deepcopy(base)
        charged["rows"][0]["nodes200k"] += 7
        changed, changed_raw = project(charged)
        differing = {key for key in original if original[key] != changed[key]}
        self.assertEqual(differing, {
            "projection_input_sha256", "shadow_nodes200", "shadow_nodes_total",
        })
        self.assertEqual(changed["shadow_nodes200"] - original["shadow_nodes200"], 7)
        self.assertEqual(changed["shadow_nodes_total"] - original["shadow_nodes_total"], 7)
        self.assertNotEqual(hashlib.sha256(original_raw).hexdigest(),
                            hashlib.sha256(changed_raw).hexdigest())
        self.assertEqual(original["nodes200k_validated_rows"], 3)
        self.assertEqual(original["nodes200k_aggregation_reads"], 2)
        self.assertEqual(
            (original["nodes200k_policy_reads"], original["nodes200k_policy_branches"],
             original["nodes200k_preseal_aggregation_reads"]),
            (0, 0, 0),
        )

        uncharged = copy.deepcopy(base)
        uncharged["rows"][2]["nodes200k"] += 11
        unchanged_cost, unchanged_cost_raw = project(uncharged)
        differing = {key for key in original if original[key] != unchanged_cost[key]}
        self.assertEqual(differing, {"projection_input_sha256"})
        self.assertNotEqual(hashlib.sha256(original_raw).hexdigest(),
                            hashlib.sha256(unchanged_cost_raw).hexdigest())

    def test_q200_external_value_family_label_perturbation_is_byte_invariant(self):
        projection = parent([row(0, 100, 100), row(1, 90, 90)])
        before_external = {"q200_parent": 9, "q200_family": "WIN", "q200_label": 1}
        after_external = {"q200_parent": -9, "q200_family": "LOSS", "q200_label": -1}
        before, before_raw = project(projection)
        after, after_raw = project(projection)
        self.assertNotEqual(before_external, after_external)
        self.assertEqual(before, after)
        self.assertEqual(before_raw, after_raw)

    def test_invalid_nodes200_fails_at_ingress_before_policy(self):
        for invalid_cost in (True, 1.0, "1", -1, subject.UINT64_MAX + 1):
            invalid = parent([row(0), row(1)])
            invalid["rows"][0]["nodes200k"] = invalid_cost
            with self.subTest(invalid_cost=invalid_cost), \
                    mock.patch.object(subject, "seal_decision") as policy:
                with self.assertRaisesRegex(subject.ProjectionError, "nodes200k"):
                    project(invalid)
                policy.assert_not_called()


class StrictTypesAndArithmeticTests(unittest.TestCase):
    def test_strict_types_ranges_exactness_and_schema(self):
        cases = []
        value = parent([row(0), row(1)]); value["parent_id"] = True
        cases.append(value)
        value = parent([row(0), row(1)]); value["stm"] = 1.0
        cases.append(value)
        value = parent([row(0), row(1)]); value["rows"][0]["q5k_parent"] = 1 << 31
        cases.append(value)
        value = parent([row(0), row(1)]); value["rows"][0]["nodes200k"] = -1
        cases.append(value)
        value = parent([row(0), row(1)]); value["rows"][0]["child_tb_exact"] = 1
        cases.append(value)
        value = parent([row(0), row(1)]); value["rows"][0]["exact_parent_utility"] = 0
        cases.append(value)
        value = parent([row(0), row(1)]); value["rows"][0]["mystery"] = 0
        cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(subject.ProjectionError):
                subject.parse_parent(value)

    def test_uint64_component_and_total_overflow_fail_closed(self):
        n5_overflow = parent([row(0, n5=subject.UINT64_MAX), row(1, n5=1)])
        with self.assertRaisesRegex(subject.ProjectionError, "shadow_nodes5 uint64 overflow"):
            project(n5_overflow)

        n200_overflow = parent([
            row(0, 100, 100, n5=0, n50=0, n200=subject.UINT64_MAX),
            row(1, 90, 90, n5=0, n50=0, n200=1),
        ])
        with self.assertRaisesRegex(subject.ProjectionError, "shadow_nodes200 uint64 overflow"):
            project(n200_overflow)

        total_overflow = parent([
            row(0, 100, 100, n5=subject.UINT64_MAX, n50=0, n200=0),
            row(1, 90, 90, n5=0, n50=1, n200=0),
        ])
        with self.assertRaisesRegex(subject.ProjectionError, "shadow_nodes_total uint64 overflow"):
            project(total_overflow)


class SerializationTests(unittest.TestCase):
    def test_parent_row_order_is_canonical_and_hashes_are_sealed(self):
        forward = parent([row(1, 90, 90), row(0, 100, 100)])
        reverse = parent(list(reversed(forward["rows"])))
        receipt_a, raw_a = project(forward)
        receipt_b, raw_b = project(reverse)
        self.assertEqual(receipt_a, receipt_b)
        self.assertEqual(raw_a, raw_b)
        self.assertEqual(receipt_a["ordered_rows"], [0, 1])
        self.assertEqual(raw_a, subject.canonical_json_line(receipt_a))
        self.assertNotIn(b"NaN", raw_a)
        parsed = subject.parse_parent(forward)
        decision = parsed.decision
        sealed = subject.seal_decision(decision)
        canonical_full = copy.deepcopy(forward)
        canonical_full["rows"].sort(key=lambda item: item["row_index"])
        expected_decision = copy.deepcopy(canonical_full)
        for item in expected_decision["rows"]:
            del item["nodes200k"]
        self.assertEqual(subject.decision_input_object(decision), expected_decision)
        self.assertEqual(
            receipt_a["projection_input_sha256"],
            subject.sha256(subject.canonical_json_line(canonical_full)),
        )
        self.assertEqual(
            receipt_a["decision_input_sha256"],
            subject.sha256(subject.canonical_json_line(subject.decision_input_object(decision))),
        )
        self.assertEqual(
            receipt_a["decision_output_sha256"],
            subject.sha256(subject.canonical_json_line(subject.decision_output_object(sealed))),
        )

    def test_file_receipts_are_parent_sorted_canonical_and_manifested(self):
        values = [parent([row(0), row(1)], parent_id=9),
                  parent([row(2), row(3)], parent_id=2)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.jsonl"
            source.write_bytes(b"".join(subject.canonical_json_line(value) for value in values))
            receipts = root / "allocation-receipts.jsonl"
            manifest_path = root / "manifest.json"
            manifest = subject.project_file(source, receipts, manifest_path)
            lines = receipts.read_bytes().splitlines(keepends=True)
            parsed = [json.loads(line) for line in lines]
            self.assertEqual([item["parent_id"] for item in parsed], [2, 9])
            self.assertTrue(all(line == subject.canonical_json_line(value)
                                for line, value in zip(lines, parsed)))
            self.assertEqual(manifest["allocation_receipts_jsonl_sha256"],
                             hashlib.sha256(receipts.read_bytes()).hexdigest())
            self.assertEqual(manifest_path.read_bytes(), subject.canonical_json_line(manifest))
            self.assertEqual(
                (manifest["q200_value_reads"], manifest["q200_label_reads"],
                 manifest["q200_branches"]), (0, 0, 0),
            )
            self.assertEqual(manifest["nodes200k_validated_rows"], 4)
            self.assertEqual(manifest["nodes200k_aggregation_reads"], 4)
            self.assertEqual(
                (manifest["nodes200k_policy_reads"], manifest["nodes200k_policy_branches"],
                 manifest["nodes200k_preseal_aggregation_reads"]),
                (0, 0, 0),
            )
            for record, sealed in zip(manifest["parent_receipts"], parsed):
                line = subject.canonical_json_line(sealed)
                self.assertEqual(record["allocation_receipt_sha256"],
                                 hashlib.sha256(line).hexdigest())

    def test_empty_malformed_and_duplicate_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in (
                ("empty", b""),
                ("no-lf", subject.canonical_json_line(parent([row(0), row(1)])).rstrip(b"\n")),
                ("blank", b"\n"),
                ("nan", b'{"value":NaN}\n'),
                ("duplicate-key", b'{"schema":"a","schema":"b"}\n'),
            ):
                path = root / name
                path.write_bytes(raw)
                with self.subTest(name=name), self.assertRaises(subject.ProjectionError):
                    subject.load_jsonl(path)
            duplicate = root / "duplicate.jsonl"
            value = parent([row(0), row(1)])
            duplicate.write_bytes(subject.canonical_json_line(value) * 2)
            with self.assertRaisesRegex(subject.ProjectionError, "duplicate parent_id"):
                subject.load_jsonl(duplicate)

    def test_input_output_and_temporary_aliases_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.jsonl"
            original = subject.canonical_json_line(parent([row(0), row(1)]))
            source.write_bytes(original)
            manifest = root / "manifest.json"
            with self.assertRaisesRegex(subject.ProjectionError, "pairwise distinct"):
                subject.project_file(source, source, manifest)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(manifest.exists())

            receipts = root / "x"
            colliding_manifest = root / "x.tmp"
            with self.assertRaisesRegex(subject.ProjectionError, "pairwise distinct"):
                subject.project_file(source, receipts, colliding_manifest)
            self.assertFalse(receipts.exists())
            self.assertFalse(colliding_manifest.exists())


if __name__ == "__main__":
    unittest.main()
