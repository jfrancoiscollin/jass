from __future__ import annotations

import copy
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_statistics as statistics


def observation_group(score: int = 10, *, exact: str | None = None) -> dict[str, str]:
    row = {field: "0" for field in readout.GROUP_FIELDS}
    row.update({
        "parent_id": "0", "parent_fingerprint": "raw", "parent_stm": "0",
        "parent_pieces": "20", "from": "1", "to": "2", "num_captures": "0",
        "promotes": "0", "moving_king": "0", "captured_kings": "0",
        "material_count_delta_parent": "0", "child_pieces": "20",
        "child_legal_moves": "2", "child_forced_capture": "0",
        "child_rule_terminal": "1" if exact == "rule" else "0",
        "child_tb_exact": "1" if exact == "tb" else "0",
        "exact_parent_utility": "1" if exact else "2", "t_baseline_parent": "0",
    })
    for horizon, budget in (("5k", 5_000), ("50k", 50_000), ("200k", 200_000)):
        score_name = {"5k": "q5k_parent", "50k": "q50_parent", "200k": "q200_parent"}[horizon]
        if exact == "rule":
            row.update({score_name: "30000", f"nodes{horizon}": "0",
                        f"completed_depth{horizon}": "0", f"effective_depth{horizon}": "0",
                        f"aborted{horizon}": "0", f"stop{horizon}": "none"})
        else:
            row.update({score_name: str(score), f"nodes{horizon}": str(budget),
                        f"completed_depth{horizon}": "63", f"effective_depth{horizon}": "64",
                        f"aborted{horizon}": "1", f"stop{horizon}": "nodes"})
        row[f"elapsed_us{horizon}"] = "1"
        row[f"pv{horizon}_enters_egdb"] = "0"
    return row


def semantic(parent_id: int, row_index: int, *, from_sq: int) -> dict[str, object]:
    return {
        "schema": readout.SEMANTIC_SCHEMA, "parent_id": parent_id,
        "global_row_index": row_index, "local_row_index": row_index,
        "source_shard": parent_id % 16, "parent_fingerprint": f"raw-{parent_id}",
        "parent_pieces": 20, "parent_legal_moves": 2, "from": from_sq,
        "to": from_sq + 1, "num_captures": 0, "promotes": False,
        "captured_kings": 0, "captured_square_bitboard": 0,
        "material_count_delta_parent": 0, "child_fingerprint": f"child-{row_index}",
        "child_pieces": 20,
    }


def compared_row(score: int, *, row_index: int, exact: bool = False,
                 utility: int = 2, mechanism_exact: str = "tb") -> dict[str, object]:
    group = observation_group(score, exact=mechanism_exact if exact else None)
    return {"row_index": row_index, "exact": exact, "utility": utility,
            "rule_terminal": exact and mechanism_exact == "rule",
            "tb_exact": exact and mechanism_exact == "tb",
            "semantic": semantic(0, row_index, from_sq=1 + row_index),
            "observations": {h: readout.validate_observation(
                group, h, exact=exact, rule_terminal=exact and mechanism_exact == "rule")
                for h in ("5k", "50k", "200k")}}


def parent_fixture(parent_id: int) -> tuple[dict[str, str], bytes, list[dict[str, str]],
                                             list[bytes], list[dict[str, object]], list[bytes],
                                             dict[str, object], bytes, dict[str, object], bytes]:
    phase = f"P{parent_id // 1000}"
    stm = (parent_id // 500) % 2
    selection = {
        "parent_id": str(parent_id), "canonical_fingerprint": f"canonical-{parent_id}",
        "raw_fingerprint": f"raw-{parent_id}", "parent_stm": str(stm),
        "pieces": "20", "legal_moves": "2", "phase": phase,
        "source_shard": str(parent_id % 16), "source_row_index": str(parent_id),
        "selection_hash": hashlib.sha256(str(parent_id).encode()).hexdigest(),
    }
    selection_line = ("\t".join(selection[field] for field in readout.SELECTION_FIELDS) + "\n").encode()
    groups = []
    semantics = []
    for offset, score in enumerate((10, 0)):
        row_index = parent_id * 2 + offset
        group = observation_group(score)
        group.update({"row_index": str(row_index), "parent_id": str(parent_id),
                      "parent_fingerprint": selection["raw_fingerprint"],
                      "parent_stm": str(stm), "from": str(1 + offset * 2),
                      "to": str(2 + offset * 2)})
        groups.append(group)
        semantics.append(semantic(parent_id, row_index, from_sq=1 + offset * 2))
    group_lines = [("\t".join(row[field] for field in readout.GROUP_FIELDS) + "\n").encode()
                   for row in groups]
    semantic_lines = [readout.canonical_json_bytes(row) for row in semantics]
    allocation_rows = [{
        "row_index": int(row["row_index"]),
        "child_rule_terminal": False, "child_tb_exact": False,
        "exact_parent_utility": 2, "q5k_parent": int(row["q5k_parent"]),
        "q50_parent": int(row["q50_parent"]), "nodes5k": int(row["nodes5k"]),
        "nodes50k": int(row["nodes50k"]), "nodes200k": int(row["nodes200k"]),
    } for row in groups]
    allocation = {"schema": readout.ALLOCATION_INPUT_SCHEMA, "parent_id": parent_id,
                  "phase": phase, "stm": stm, "rows": allocation_rows}
    allocation_line = readout.canonical_json_bytes(allocation)
    ordered = [parent_id * 2, parent_id * 2 + 1]
    decision_view = copy.deepcopy(allocation)
    for row in decision_view["rows"]:
        del row["nodes200k"]
    decision_output = {
        "parent_id": parent_id, "ordered_rows": ordered, "S5_rows": ordered,
        "S50_rows": ordered, "S200_charge_rows": ordered,
        "pre_q200_choice_row_or_null": None, "exact_shortcut_reason": None,
        "sole_survivor_reason": None, "uncertified_shadow": False,
    }
    receipt = {
        "schema": readout.ALLOCATION_RECEIPT_SCHEMA, **decision_output,
        "shadow_nodes5": 10_000, "shadow_nodes50": 100_000,
        "shadow_nodes200": 400_000, "shadow_nodes_total": 510_000,
        "projection_input_sha256": readout.sha256_bytes(allocation_line),
        "decision_input_sha256": readout.sha256_bytes(readout.canonical_json_bytes(decision_view)),
        "decision_output_sha256": readout.sha256_bytes(readout.canonical_json_bytes(decision_output)),
        "nodes200k_validated_rows": 2, "nodes200k_policy_reads": 0,
        "nodes200k_policy_branches": 0, "nodes200k_preseal_aggregation_reads": 0,
        "nodes200k_aggregation_reads": 2, "q200_value_reads": 0,
        "q200_label_reads": 0, "q200_branches": 0,
    }
    receipt_line = readout.canonical_json_bytes(receipt)
    return (selection, selection_line, groups, group_lines, semantics, semantic_lines,
            allocation, allocation_line, receipt, receipt_line)


class ObservationTests(unittest.TestCase):
    def test_score_band_boundaries(self):
        expected = {
            0: "EVAL_COMPATIBLE", 20_000: "EVAL_COMPATIBLE", -20_000: "EVAL_COMPATIBLE",
            29_372: "TB_DIRECT_COMPATIBLE", -29_935: "TB_DIRECT_COMPATIBLE",
            29_937: "REAL_MATE_BAND", -30_000: "REAL_MATE_BAND",
        }
        for score, band in expected.items():
            with self.subTest(score=score):
                self.assertEqual(readout.classify_score(score)[0], band)
        for score in (20_001, -29_371, 29_936, -29_936, 30_001):
            with self.subTest(score=score), self.assertRaises(readout.ReadoutError):
                readout.classify_score(score)

    def test_transport_depth_stop_nodes_and_abort_boundaries(self):
        base = observation_group(0)
        for horizon, budget in (("5k", 5_000), ("50k", 50_000), ("200k", 200_000)):
            with self.subTest(horizon=horizon):
                self.assertEqual(readout.validate_observation(
                    base, horizon, exact=False, rule_terminal=False)["nodes"], budget)
                broken = dict(base)
                broken[f"nodes{horizon}"] = str(budget + 1)
                with self.assertRaises(readout.ReadoutError):
                    readout.validate_observation(broken, horizon, exact=False,
                                                 rule_terminal=False)
        mutations = [
            ("nodes5k", "5001"), ("completed_depth5k", "65"),
            ("effective_depth5k", "62"), ("stop5k", "time"),
            ("aborted5k", "0"),
        ]
        for field, value in mutations:
            broken = dict(base)
            broken[field] = value
            with self.subTest(field=field), self.assertRaises(readout.ReadoutError):
                readout.validate_observation(broken, "5k", exact=False, rule_terminal=False)
        completed = dict(base)
        completed.update({"stop5k": "none", "aborted5k": "0",
                          "completed_depth5k": "63", "effective_depth5k": "63",
                          "nodes5k": "1"})
        with self.assertRaises(readout.ReadoutError):
            readout.validate_observation(completed, "5k", exact=False, rule_terminal=False)

    def test_exact_rows_transport_without_score_classification(self):
        for exact in ("rule", "tb"):
            row = observation_group(20_001, exact=exact)
            result = readout.validate_observation(row, "200k", exact=True,
                                                  rule_terminal=exact == "rule")
            self.assertFalse(result["decision_score_applicable"])
            self.assertIsNone(result["score_band"])
            self.assertIsNone(result["score_family"])
            self.assertIsNone(result["score_mechanism"])
        broken = observation_group(0, exact="rule")
        broken["q200_parent"] = "29999"
        with self.assertRaises(readout.ReadoutError):
            readout.validate_observation(broken, "200k", exact=True, rule_terminal=True)

    def test_choice_revalidates_q200_transport(self):
        choice = readout._choice(compared_row(0, row_index=0))
        choice["q200"]["nodes"] = 199_999
        with self.assertRaises(readout.ReadoutError):
            readout._validate_choice(choice, "choice")
        rule = readout._choice(compared_row(30_000, row_index=0, exact=True,
                                            utility=1, mechanism_exact="rule"))
        rule["q200"]["score"] = 29_999
        with self.assertRaises(readout.ReadoutError):
            readout._validate_choice(rule, "choice")


class ComparisonTests(unittest.TestCase):
    def test_all_signal_directions(self):
        representatives = {"LOSS_SCORE_SIGNAL": -29_372,
                           "UNRESOLVED_NUMERIC": 0,
                           "WIN_SCORE_SIGNAL": 29_372}
        expected = {
            ("WIN_SCORE_SIGNAL", "UNRESOLVED_NUMERIC"): 1,
            ("WIN_SCORE_SIGNAL", "LOSS_SCORE_SIGNAL"): 2,
            ("UNRESOLVED_NUMERIC", "LOSS_SCORE_SIGNAL"): 3,
            ("LOSS_SCORE_SIGNAL", "UNRESOLVED_NUMERIC"): 4,
            ("LOSS_SCORE_SIGNAL", "WIN_SCORE_SIGNAL"): 5,
            ("UNRESOLVED_NUMERIC", "WIN_SCORE_SIGNAL"): 6,
        }
        for pair, code in expected.items():
            result = readout._comparison(compared_row(representatives[pair[0]], row_index=0),
                                         compared_row(representatives[pair[1]], row_index=1))
            self.assertEqual(result["signal_direction_code"], code)
            self.assertEqual(result["signal_event"], code in {1, 2, 3})

    def test_exact_mixed_ties_numeric_and_fallback(self):
        exact_a = compared_row(0, row_index=0, exact=True, utility=1)
        exact_b = compared_row(0, row_index=1, exact=True, utility=1)
        self.assertEqual(readout._comparison(exact_a, exact_b)["comparison"]["first_level"],
                         "DIFFERENT_ROW_VALUE_EQUIVALENT_TIE")
        mixed = readout._comparison(exact_a, compared_row(0, row_index=1))
        self.assertTrue(mixed["exact_mismatch"])
        self.assertEqual(mixed["comparison"]["subcategory"], "EXACT_OR_MIXED_MISMATCH")
        for delta, category in ((1, "FINITE_NUMERIC_1_99"), (99, "FINITE_NUMERIC_1_99"),
                                (100, "FINITE_NUMERIC_GE100")):
            result = readout._comparison(compared_row(delta, row_index=0),
                                         compared_row(0, row_index=1))
            self.assertEqual(result["numeric"]["delta"], delta)
            self.assertEqual(result["comparison"]["subcategory"], category)
        better_shadow = readout._comparison(compared_row(0, row_index=0),
                                            compared_row(1, row_index=1))
        self.assertEqual(better_shadow["numeric"]["delta"], 0)
        self.assertEqual(better_shadow["comparison"]["subcategory"],
                         "OTHER_INCOMPATIBLE_SCORE_MECHANISM")

    def test_encoded_and_mechanism_categories(self):
        tb = readout._comparison(compared_row(29_373, row_index=0),
                                 compared_row(29_372, row_index=1))
        self.assertEqual(tb["comparison"]["subcategory"], "WITHIN_TB_ENCODED_ORDER")
        mate = readout._comparison(compared_row(29_938, row_index=0),
                                   compared_row(29_937, row_index=1))
        self.assertEqual(mate["comparison"]["subcategory"], "WITHIN_MATE_ENCODED_ORDER")
        mechanism = readout._comparison(compared_row(29_372, row_index=0),
                                        compared_row(29_937, row_index=1))
        self.assertEqual(mechanism["comparison"]["subcategory"],
                         "SAME_SIGNAL_FAMILY_DIFFERENT_MECHANISM")

    def test_reference_and_shadow_tie_breaks(self):
        rows = [compared_row(10, row_index=8), compared_row(10, row_index=3)]
        self.assertEqual(readout._reference_row(rows)["row_index"], 3)
        self.assertEqual(readout._shadow_row({row["row_index"]: row for row in rows},
                                             {"pre_q200_choice_row_or_null": None,
                                              "S200_charge_rows": [8, 3]})["row_index"], 3)
        with self.assertRaises(readout.ReadoutError):
            readout._shadow_row({}, {"pre_q200_choice_row_or_null": None,
                                     "S200_charge_rows": []})

    def test_reference_priority_and_pre_q200_shadow(self):
        loss = compared_row(0, row_index=9, exact=True, utility=-1)
        draw = compared_row(0, row_index=8, exact=True, utility=0)
        nonexact = compared_row(-30_000, row_index=7)
        win = compared_row(0, row_index=6, exact=True, utility=1)
        self.assertIs(readout._reference_row([loss, draw, nonexact, win]), win)
        self.assertIs(readout._reference_row([loss, draw, nonexact]), nonexact)
        self.assertIs(readout._reference_row([loss, draw]), draw)
        self.assertIs(readout._reference_row([loss]), loss)
        rows = {row["row_index"]: row for row in (loss, draw)}
        self.assertIs(readout._shadow_row(rows, {
            "pre_q200_choice_row_or_null": 9, "S200_charge_rows": []}), loss)


class RichBuildTests(unittest.TestCase):
    def test_one_parent_hash_cost_and_tamper_checks(self):
        fixture = parent_fixture(0)
        rich, sufficient, counts = readout.build_rich_parent(
            selection=fixture[0], selection_line=fixture[1], groups=fixture[2],
            group_lines=fixture[3], semantics=fixture[4], semantic_lines=fixture[5],
            allocation=fixture[6], allocation_line=fixture[7], receipt=fixture[8],
            receipt_line=fixture[9])
        self.assertEqual(rich["costs"]["full_nodes_total"], 510_000)
        self.assertEqual(sufficient.full_nodes, 510_000)
        self.assertEqual(counts["exact_score_endpoint_uses"], 0)
        provenance = list(fixture)
        provenance[0] = dict(provenance[0])
        provenance[0]["source_shard"] = "7"
        provenance[1] = ("\t".join(provenance[0][field]
                                    for field in readout.SELECTION_FIELDS) + "\n").encode()
        readout.build_rich_parent(
            selection=provenance[0], selection_line=provenance[1], groups=provenance[2],
            group_lines=provenance[3], semantics=provenance[4],
            semantic_lines=provenance[5], allocation=provenance[6],
            allocation_line=provenance[7], receipt=provenance[8], receipt_line=provenance[9])
        broken = copy.deepcopy(fixture[8])
        broken["decision_output_sha256"] = "0" * 64
        with self.assertRaises(readout.ReadoutError):
            readout.build_rich_parent(
                selection=fixture[0], selection_line=fixture[1], groups=fixture[2],
                group_lines=fixture[3], semantics=fixture[4], semantic_lines=fixture[5],
                allocation=fixture[6], allocation_line=fixture[7], receipt=broken,
                receipt_line=readout.canonical_json_bytes(broken))
        for index, value in ((6, False), (4, False)):
            mutated = list(fixture)
            mutated[index] = copy.deepcopy(mutated[index])
            if index == 6:
                mutated[index]["parent_id"] = value
            else:
                mutated[index][0]["parent_id"] = value
            with self.subTest(index=index), self.assertRaises(readout.ReadoutError):
                readout.build_rich_parent(
                    selection=mutated[0], selection_line=mutated[1], groups=mutated[2],
                    group_lines=mutated[3], semantics=mutated[4],
                    semantic_lines=mutated[5], allocation=mutated[6],
                    allocation_line=mutated[7], receipt=mutated[8],
                    receipt_line=mutated[9])
        nested = list(fixture)
        nested[6] = copy.deepcopy(nested[6])
        nested[6]["rows"][0]["nodes5k"] = True
        with self.assertRaises(readout.ReadoutError):
            readout.build_rich_parent(
                selection=nested[0], selection_line=nested[1], groups=nested[2],
                group_lines=nested[3], semantics=nested[4], semantic_lines=nested[5],
                allocation=nested[6], allocation_line=nested[7], receipt=nested[8],
                receipt_line=nested[9])

    def test_complete_4000_population_is_deterministic_and_8x500(self):
        fixtures = [parent_fixture(parent_id) for parent_id in range(readout.PARENTS)]
        columns = list(zip(*fixtures))
        result1 = readout.build_from_components(
            code_sha="1" * 40, input_manifest_sha256="2" * 64,
            selections=columns[0], selection_lines=columns[1], groups_by_parent=columns[2],
            group_lines_by_parent=columns[3], semantics_by_parent=columns[4],
            semantic_lines_by_parent=columns[5], allocations=columns[6],
            allocation_lines=columns[7], receipts=columns[8], receipt_lines=columns[9])
        result2 = readout.build_from_components(
            code_sha="1" * 40, input_manifest_sha256="2" * 64,
            selections=columns[0], selection_lines=columns[1], groups_by_parent=columns[2],
            group_lines_by_parent=columns[3], semantics_by_parent=columns[4],
            semantic_lines_by_parent=columns[5], allocations=columns[6],
            allocation_lines=columns[7], receipts=columns[8], receipt_lines=columns[9])
        self.assertEqual([hashlib.sha256(raw).hexdigest() for raw in result1],
                         [hashlib.sha256(raw).hexdigest() for raw in result2])
        report = json.loads(result1[2])
        self.assertEqual(report["population"]["cells"],
                         {cell: 500 for cell in readout.CELL_ORDER})
        self.assertEqual(report["ledger"]["first_level_sum"], 4_000)
        self.assertEqual(report["barrier"]["allocation_q200_value_reads"], 0)

    def test_exact_shortcut_keeps_full_cost_and_never_classifies_exact_score(self):
        fixture = list(parent_fixture(0))
        groups = copy.deepcopy(fixture[2])
        groups[0].update({"child_tb_exact": "1", "exact_parent_utility": "1",
                          "q5k_parent": "20001", "q50_parent": "29371",
                          "q200_parent": "29936"})
        group_lines = [("\t".join(row[field] for field in readout.GROUP_FIELDS) + "\n").encode()
                       for row in groups]
        allocation = copy.deepcopy(fixture[6])
        allocation["rows"][0].update({"child_tb_exact": True,
                                       "exact_parent_utility": 1,
                                       "q5k_parent": 20_001,
                                       "q50_parent": 29_371})
        allocation_line = readout.canonical_json_bytes(allocation)
        receipt = copy.deepcopy(fixture[8])
        row_index = allocation["rows"][0]["row_index"]
        receipt.update({"S5_rows": [], "S50_rows": [], "S200_charge_rows": [],
                        "pre_q200_choice_row_or_null": row_index,
                        "exact_shortcut_reason": "EXACT_WIN",
                        "shadow_nodes5": 0, "shadow_nodes50": 0,
                        "shadow_nodes200": 0, "shadow_nodes_total": 0,
                        "nodes200k_aggregation_reads": 0,
                        "projection_input_sha256": readout.sha256_bytes(allocation_line)})
        decision_view = copy.deepcopy(allocation)
        for row in decision_view["rows"]:
            del row["nodes200k"]
        receipt["decision_input_sha256"] = readout.sha256_bytes(
            readout.canonical_json_bytes(decision_view))
        decision_output = {key: receipt[key] for key in (
            "parent_id", "ordered_rows", "S5_rows", "S50_rows", "S200_charge_rows",
            "pre_q200_choice_row_or_null", "exact_shortcut_reason",
            "sole_survivor_reason", "uncertified_shadow")}
        receipt["decision_output_sha256"] = readout.sha256_bytes(
            readout.canonical_json_bytes(decision_output))
        rich, sufficient, counts = readout.build_rich_parent(
            selection=fixture[0], selection_line=fixture[1], groups=groups,
            group_lines=group_lines, semantics=fixture[4], semantic_lines=fixture[5],
            allocation=allocation, allocation_line=allocation_line, receipt=receipt,
            receipt_line=readout.canonical_json_bytes(receipt))
        self.assertEqual(rich["costs"]["full_nodes_total"], 510_000)
        self.assertEqual(sufficient.full_nodes, 510_000)
        self.assertEqual(rich["costs"]["shadow_nodes_total"], 0)
        self.assertEqual(counts["exact_transport_valid"], 3)
        self.assertEqual(counts["exact_score_endpoint_uses"], 0)

    def test_rich_projection_detects_tamper_and_uint64_overflow(self):
        fixture = parent_fixture(0)
        rich, _, _ = readout.build_rich_parent(
            selection=fixture[0], selection_line=fixture[1], groups=fixture[2],
            group_lines=fixture[3], semantics=fixture[4], semantic_lines=fixture[5],
            allocation=fixture[6], allocation_line=fixture[7], receipt=fixture[8],
            receipt_line=fixture[9])
        tampered = copy.deepcopy(rich)
        tampered["numeric"]["component"] += 1
        with self.assertRaises(readout.ReadoutError):
            readout.sufficient_from_rich(tampered)
        boolean_alias = copy.deepcopy(rich)
        boolean_alias["numeric"]["component"] = False
        with self.assertRaises(readout.ReadoutError):
            readout.sufficient_from_rich(boolean_alias)
        overflowing = copy.deepcopy(rich)
        overflowing["costs"].update({"full_nodes5": readout.UINT64_MAX,
                                      "full_nodes50": 1})
        with self.assertRaises(readout.ReadoutError):
            readout.sufficient_from_rich(overflowing)

    def test_existing_output_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "out"
            path.mkdir()
            marker = path / "sentinel"
            marker.write_text("keep")
            with self.assertRaises(readout.ReadoutError):
                readout._write_new_directory(path, {"x": b"x"})
            self.assertEqual(marker.read_text(), "keep")

    def test_cleanup_never_deletes_a_concurrent_third_party_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out"
            original = readout.os.link

            def link_with_sentinel(source, destination):
                original(source, destination)
                (out / "third-party-sentinel").write_text("keep")

            with mock.patch.object(readout.os, "link", side_effect=link_with_sentinel):
                with self.assertRaises(readout.ReadoutError):
                    readout._write_new_directory(out, {"owned": b"owned"})
            self.assertEqual((out / "third-party-sentinel").read_text(), "keep")
            self.assertFalse((out / "owned").exists())

    def test_known_output_injected_before_publish_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out"
            original = readout._write_exclusive

            def inject_final(path, raw):
                identity = original(path, raw)
                (out / "owned").write_text("third-party")
                return identity

            with mock.patch.object(readout, "_write_exclusive", side_effect=inject_final):
                with self.assertRaises(FileExistsError):
                    readout._write_new_directory(out, {"owned": b"owned"})
            self.assertEqual((out / "owned").read_text(), "third-party")

    def test_partial_write_failure_cleans_only_the_owned_temporary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "owned.tmp"
            original = Path.open

            class PartialWriter:
                def __init__(self, handle):
                    self.handle = handle

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.handle.close()

                def fileno(self):
                    return self.handle.fileno()

                def write(self, raw):
                    self.handle.write(raw[:1])
                    self.handle.flush()
                    raise OSError("synthetic partial write")

            def failing_open(target, *args, **kwargs):
                handle = original(target, *args, **kwargs)
                return PartialWriter(handle) if target == path else handle

            with mock.patch.object(Path, "open", failing_open):
                with self.assertRaises(readout.TechnicalIOError):
                    readout._write_exclusive(path, b"complete")
            self.assertFalse(path.exists())

    def test_nested_bool_aliases_in_allocation_and_semantics_are_rejected(self):
        for index, value in ((6, False), (4, False)):
            fixture = list(parent_fixture(0))
            fixture[index] = copy.deepcopy(fixture[index])
            if index == 6:
                fixture[index]["parent_id"] = value
                fixture[7] = readout.canonical_json_bytes(fixture[index])
            else:
                fixture[index][0]["parent_id"] = value
                fixture[5] = [readout.canonical_json_bytes(row) for row in fixture[index]]
            with self.subTest(index=index), self.assertRaises(readout.BuildValidationFailure):
                readout.build_rich_parent(
                    selection=fixture[0], selection_line=fixture[1], groups=fixture[2],
                    group_lines=fixture[3], semantics=fixture[4],
                    semantic_lines=fixture[5], allocation=fixture[6],
                    allocation_line=fixture[7], receipt=fixture[8], receipt_line=fixture[9])


class BuildFailureTests(unittest.TestCase):
    def receipt(self, *, authenticated: bool = True):
        failure = readout.BuildValidationFailure(
            "TEACHER_OBSERVATION_TRANSPORT_INVALID" if authenticated
            else "INPUT_AUTHENTICATION_FAILED",
            parent_id=0 if authenticated else None,
            global_row_index=0 if authenticated else None,
            horizon="5k" if authenticated else None)
        return readout._build_failure_receipt(
            failure=failure, expected_input_sha256="a" * 64,
            actual_input_sha256="b" * 64, input_authenticated=authenticated,
            manifest_code_sha="c" * 40 if authenticated else None,
            tool_binding_authenticated=authenticated,
            preregistration_authenticated=authenticated)

    def test_closed_failure_receipt_and_exclusive_publication(self):
        receipt = self.receipt()
        self.assertEqual(readout._validate_build_failure_receipt(receipt), receipt)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "failure.json"
            readout._publish_build_failure(path, receipt)
            self.assertEqual(path.read_bytes(), readout.canonical_json_bytes(receipt))
            with self.assertRaises(FileExistsError):
                readout._publish_build_failure(path, receipt)

    def test_preexisting_failure_temporary_is_never_deleted(self):
        receipt = self.receipt()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "failure.json"
            temp = Path(str(path) + ".tmp")
            temp.write_text("third-party")
            with self.assertRaises(FileExistsError):
                readout._publish_build_failure(path, receipt)
            self.assertEqual(temp.read_text(), "third-party")
            self.assertFalse(path.exists())

    def test_failure_receipt_rejects_bool_enum_context_counter_and_output(self):
        mutations = [
            (("running_tool", "size_bytes"), True),
            (("failure", "class"), "FREE_TEXT"),
            (("failure", "parent_id"), 4_000),
            (("counters", "bootstrap_draws"), False),
            (("outputs", "statistics"), {"sha256": "a" * 64}),
        ]
        for path, value in mutations:
            receipt = self.receipt()
            cursor = receipt
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(readout.ReadoutError):
                readout._validate_build_failure_receipt(receipt)

    def test_observation_failure_has_typed_parent_row_and_horizon(self):
        for horizon in ("5k", "50k", "200k"):
            fixture = list(parent_fixture(0))
            fixture[2] = copy.deepcopy(fixture[2])
            fixture[2][0][f"nodes{horizon}"] = "1"
            fixture[3] = [("\t".join(row[field] for field in readout.GROUP_FIELDS) + "\n").encode()
                          for row in fixture[2]]
            fixture[6] = copy.deepcopy(fixture[6])
            fixture[6]["rows"][0][f"nodes{horizon}"] = 1
            fixture[7] = readout.canonical_json_bytes(fixture[6])
            with self.subTest(horizon=horizon), self.assertRaises(
                    readout.BuildValidationFailure) as caught:
                readout.build_rich_parent(
                    selection=fixture[0], selection_line=fixture[1], groups=fixture[2],
                    group_lines=fixture[3], semantics=fixture[4],
                    semantic_lines=fixture[5], allocation=fixture[6],
                    allocation_line=fixture[7], receipt=fixture[8], receipt_line=fixture[9])
            self.assertEqual(caught.exception.failure_class,
                             "TEACHER_OBSERVATION_TRANSPORT_INVALID")
            self.assertEqual((caught.exception.parent_id,
                              caught.exception.global_row_index,
                              caught.exception.horizon), (0, 0, horizon))

    def test_destination_collision_is_technical_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifest = base / "input.json"
            manifest.write_text("input")
            with self.assertRaises(readout.ReadoutError):
                readout._guard_build_destinations(manifest, base / "out", manifest)
            self.assertEqual(manifest.read_text(), "input")

    def test_build_returns_four_only_for_typed_support_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifest = base / "input.json"
            manifest.write_bytes(readout.canonical_json_bytes({}))
            args = argparse.Namespace(
                input_manifest=manifest, expected_input_manifest_sha256="a" * 64,
                out_dir=base / "success", failure_receipt=base / "failure.json")

            def fail(_args, state):
                state.update({"authenticated": True, "manifest_code_sha": "c" * 40,
                              "tool_binding_authenticated": True,
                              "preregistration_authenticated": True})
                raise readout.BuildValidationFailure(
                    "TEACHER_OBSERVATION_TRANSPORT_INVALID", parent_id=0,
                    global_row_index=0, horizon="50k")

            with mock.patch.object(readout, "_build_success", side_effect=fail):
                self.assertEqual(readout.build_command(args), 4)
            receipt = json.loads(args.failure_receipt.read_bytes())
            self.assertEqual(receipt["failure"], {
                "class": "TEACHER_OBSERVATION_TRANSPORT_INVALID",
                "stage": "TEACHER_GROUP", "parent_id": 0,
                "global_row_index": 0, "horizon": "50k"})
            self.assertFalse(args.out_dir.exists())

    def test_free_text_and_technical_io_never_publish_failure_receipt(self):
        for error in (RuntimeError("TEACHER_OBSERVATION_TRANSPORT_INVALID"),
                      readout.TechnicalIOError("read failed")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                manifest = base / "input.json"
                manifest.write_bytes(readout.canonical_json_bytes({}))
                args = argparse.Namespace(
                    input_manifest=manifest, expected_input_manifest_sha256="a" * 64,
                    out_dir=base / "success", failure_receipt=base / "failure.json")
                with mock.patch.object(readout, "_build_success", side_effect=error):
                    with self.assertRaises(type(error)):
                        readout.build_command(args)
                self.assertFalse(args.failure_receipt.exists())
                self.assertFalse(args.out_dir.exists())


def terminal_pipeline_fixture(base: Path):
    """Build one fully authenticated synthetic 4000-parent terminal graph."""
    from jobs.tests import test_adaptive_sibling_b2_pipeline as pipeline
    from jobs.tests.test_adaptive_sibling_b2_teacher_merge import Fixture
    from jobs.tools import adaptive_sibling_b2_allocation_input as allocation
    from jobs.tools import adaptive_sibling_b2_projection as projection
    from jobs.tools import adaptive_sibling_b2_teacher_merge as merger

    helper = pipeline.find_native(
        "adaptive_sibling_b2_native_fixture", "JASS_B2_NATIVE_FIXTURE_HELPER")
    verifier = pipeline.find_native(
        "jass_adaptive_sibling_b2_teacher_merge_verify", "JASS_B2_NATIVE_VERIFIER")
    if helper is None or verifier is None:
        raise unittest.SkipTest("published native fixture helper/verifier are unavailable")
    teacher_root = base / "teacher"
    teacher_root.mkdir()
    fixture = Fixture(teacher_root)
    historical = {
        "schema": 1, "state": "verified", "result_state": "completed", "exit_code": 0,
        "job_id": "cpx62-1773-l3-decision-math-b2-historical-identities-v1",
        "attempt_id": "synthetic-terminal-fixture", "prefix": "r2:jass-data/synthetic",
        "code_sha": "b" * 40,
        "files": [{"path": f"artefacts/{name}", "local_name": name,
                   "sha256": "c" * 64, "size_bytes": 1} for name in (
                       "historical-parent-exclusion-manifest.json",
                       "historical-parent-canonical-union.txt")],
    }
    historical_path = fixture.inputs / "historical-receipt.json"
    pipeline.write_json(historical_path, historical)
    source = {
        "schema": "jass.adaptive_sibling_b2_source_preparation.v1",
        "producer_environment": {"transmitted_names": [], "jass_prefixed_environment": []},
        "producer_barrier": {"passed": True, "child_count": 16,
                             "alive_barrier_count": 16},
        "shards": [{"source_shard": shard} for shard in range(16)],
    }
    source_path = fixture.inputs / "source-manifest.json"
    pipeline.write_json(source_path, source)
    fixture.install_real_native_catalogues(helper, verifier)
    selection = json.loads(fixture.selection_report.read_text(encoding="ascii"))
    selection["source_manifest_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    selection["exclusion"]["receipt_sha256"] = hashlib.sha256(
        historical_path.read_bytes()).hexdigest()
    fixture.selection_report.write_bytes(merger.canonical_json_bytes(selection))
    fixture.write_manifest()
    pipeline.make_observations_transport_valid(fixture)
    merge_report = merger.run(fixture.args())

    common_dir = base / "common"
    common_values = pipeline.materialize_common_inputs(fixture, common_dir)
    runtime = {"python_executable": "/usr/bin/python3", "python_implementation": "CPython",
               "python_version": "3.14.4", "platform": "Linux-test",
               "machine": "x86_64", "libc": ["glibc", "2.43"], "nproc": 16}
    preflight = common_dir / common_values["tools"]["statistical_preflight_receipt"]["local_name"]
    pipeline.write_json(preflight, {
        "schema": "jass.adaptive_sibling_b2_statistical_preflight.v1", "status": "VALID",
        "synthetic_only": True, "scientific_parents": 0,
        "bootstrap_replications": statistics.BOOTSTRAP_REPLICATIONS,
        "accepted_draws": statistics.BOOTSTRAP_REPLICATIONS * readout.PARENTS,
        "runtime_matches_kernel_environment": True, "runtime": {**runtime, "pid": 123},
        "fresh_data_reads": 0, "fits": 0, "games": 0, "promotion": False,
        "bake": False, "gate_exercise_only": True, "scientific_verdict": None,
    })
    common_values["tools"]["statistical_preflight_receipt"] = pipeline.descriptor(preflight)
    allocation_manifest = {
        "schema": allocation.INPUT_SCHEMA, "code_sha": common_values["code_sha"],
        "preregistration": common_values["preregistration"],
        "legacy_equivalence": pipeline.make_legacy_files(common_dir),
        "selection": common_values["selection"],
        "teacher_merge": common_values["teacher_merge"],
        "tools": {name: common_values["tools"][name]
                  for name in ("allocation_input", "projection")},
    }
    allocation_manifest_path = common_dir / "allocation-inputs.json"
    allocation_raw = pipeline.write_json(allocation_manifest_path, allocation_manifest)
    allocation_dir = base / "allocation"
    allocation.prepare(allocation_manifest_path,
                       hashlib.sha256(allocation_raw).hexdigest(), allocation_dir)
    projection_dir = base / "projection"
    projection_dir.mkdir()
    receipts = projection_dir / "allocation-receipts-v1.jsonl"
    projection_manifest_path = projection_dir / "projection-manifest-v1.json"
    if projection.main([
            "--input", str(allocation_dir / "allocation-parents-v1.jsonl"),
            "--out-receipts", str(receipts),
            "--out-manifest", str(projection_manifest_path)]) != 0:
        raise AssertionError("synthetic projection failed")

    inputs = base / "readout-inputs"
    shutil.copytree(common_dir, inputs)
    allocation_rows = pipeline.copy_as(
        allocation_dir / "allocation-parents-v1.jsonl", inputs)
    allocation_report = pipeline.copy_as(
        allocation_dir / "allocation-input-report-v1.json", inputs)
    projection_receipts = pipeline.copy_as(receipts, inputs)
    projection_manifest = pipeline.copy_as(projection_manifest_path, inputs)
    historical_copy = pipeline.copy_as(historical_path, inputs)
    source_copy = pipeline.copy_as(source_path, inputs)
    readout_manifest = {
        "schema": readout.BUILD_INPUT_SCHEMA, "code_sha": common_values["code_sha"],
        "preregistration": common_values["preregistration"],
        "selection": common_values["selection"], "teacher_merge": common_values["teacher_merge"],
        "allocation": {"input_jsonl": pipeline.descriptor(
            allocation_rows, rows=4000, row_schema=projection.INPUT_SCHEMA),
            "report": pipeline.descriptor(allocation_report),
            "report_schema": allocation.REPORT_SCHEMA},
        "projection": {"receipts_jsonl": pipeline.descriptor(
            projection_receipts, rows=4000, row_schema=projection.RECEIPT_SCHEMA),
            "manifest": pipeline.descriptor(projection_manifest),
            "manifest_schema": projection.MANIFEST_SCHEMA},
        "tools": common_values["tools"],
    }
    readout_manifest_path = inputs / "readout-inputs.json"
    readout_raw = pipeline.write_json(readout_manifest_path, readout_manifest)
    rich_dir = base / "rich"
    self_failure = base / "build-failure.json"
    result = readout.build_command(argparse.Namespace(
        input_manifest=readout_manifest_path,
        expected_input_manifest_sha256=hashlib.sha256(readout_raw).hexdigest(),
        out_dir=rich_dir, failure_receipt=self_failure))
    if result != 0:
        raise AssertionError("synthetic terminal rich build failed")
    rich_report_copy = pipeline.copy_as(
        rich_dir / "rich-to-sufficient-report-v1.json", inputs)
    rich_jsonl_copy = pipeline.copy_as(
        rich_dir / "parent-stats-rich-v1.jsonl", inputs)
    sufficient_jsonl_copy = pipeline.copy_as(
        rich_dir / "parent-stats-sufficient-v1.jsonl", inputs)

    legacy_report = json.loads((common_dir / "legacy-equivalence-report.json").read_text())
    legacy_terminal = inputs / "legacy-terminal-control.json"
    pipeline.write_json(legacy_terminal, {
        "schema": "jass.decision_math.b2_legacy_equivalence_publisher.v1",
        "verdict": "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE",
        "equivalence_report": legacy_report})
    terminal_manifest = {
        "schema": readout.TERMINAL_INPUT_SCHEMA, "code_sha": common_values["code_sha"],
        "preregistration": common_values["preregistration"],
        "rich_input_manifest": pipeline.descriptor(readout_manifest_path),
        "rich_to_sufficient_report": pipeline.descriptor(
            rich_report_copy),
        "rich_jsonl": pipeline.descriptor(
            rich_jsonl_copy, rows=4000,
            row_schema=readout.RICH_SCHEMA),
        "sufficient_jsonl": pipeline.descriptor(
            sufficient_jsonl_copy, rows=4000,
            row_schema=statistics.INPUT_SCHEMA),
        "statistics_tool": common_values["tools"]["statistics"],
        "terminal_tool": common_values["tools"]["readout"],
        "preflight": {"receipt": common_values["tools"]["statistical_preflight_receipt"],
                      "verdict": readout.PREFLIGHT_VERDICT, "runtime": runtime},
        "support": {
            "historical_exclusion_receipt": pipeline.descriptor(historical_copy),
            "source_manifest": pipeline.descriptor(source_copy),
            "selection_report": common_values["selection"]["report"],
            "teacher_merge_report": common_values["teacher_merge"]["report"],
            "teacher_merge_publication_receipt":
                common_values["teacher_merge"]["publication_receipt"],
            "teacher_native_verification_receipt":
                common_values["teacher_merge"]["native_verification_receipt"],
            "allocation_input_report": readout_manifest["allocation"]["report"],
            "projection_manifest": readout_manifest["projection"]["manifest"],
            "legacy_equivalence_terminal_summary": pipeline.descriptor(legacy_terminal),
        },
    }
    terminal_path = inputs / "terminal-inputs.json"
    terminal_raw = pipeline.write_json(terminal_path, terminal_manifest)
    return (terminal_path, terminal_raw, terminal_manifest, runtime,
            readout_manifest_path, readout_manifest, merge_report)


class TerminalTests(unittest.TestCase):
    def rows(self):
        return statistics.build_synthetic_parent_stats()

    def support(self, value: bool = True):
        return {key: value for key in {
            "authentication_valid", "selection_valid", "teacher_valid",
            "observations_valid", "projection_invariance_valid", "rich_ledger_valid",
            "sufficient_projection_valid", "statistics_support_valid"}}

    def run_terminal(self, analysis: dict[str, object], support=None):
        calls = []

        def analyzer(rows, *, progress_callback=None):
            calls.append((rows, progress_callback))
            if progress_callback:
                progress_callback({"completed_replications": 7, "total_replications": 7})
            return analysis

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        report = readout._finalize_from_authenticated_for_test(
            code_sha="1" * 40, input_manifest_sha256="2" * 64, rows=self.rows(),
            support=self.support() if support is None else support,
            out_dir=Path(temporary.name) / "out", analyzer=analyzer)
        return report, calls, Path(temporary.name) / "out"

    def test_three_terminal_verdicts_and_single_analysis_call(self):
        valid_base = {"status": "VALID", "scientific_gates_evaluated": True,
                      "gates": {"all_passed": False}}
        report, calls, out = self.run_terminal(valid_base)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["verdict"], "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1")
        self.assertEqual((out / "b2-statistics-v1.json").read_bytes(),
                         readout.canonical_json_bytes(valid_base))
        passed = copy.deepcopy(valid_base)
        passed["gates"]["all_passed"] = True
        report, calls, _ = self.run_terminal(passed)
        self.assertEqual(report["verdict"], "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1")
        self.assertEqual(len(calls), 1)
        invalid = {"status": "INVALID_UNKNOWN", "scientific_gates_evaluated": False}
        report, calls, _ = self.run_terminal(invalid)
        self.assertEqual(report["verdict"], "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1")
        self.assertEqual(len(calls), 1)

    def test_stability_is_checked_before_and_after_the_single_analysis(self):
        checks = []
        analyses = []

        def check():
            checks.append(len(analyses))

        def analyzer(rows, *, progress_callback=None):
            analyses.append(len(rows))
            return {"status": "VALID", "scientific_gates_evaluated": True,
                    "gates": {"all_passed": False}}

        with tempfile.TemporaryDirectory() as temporary:
            readout._finalize_with_analyzer(
                code_sha="1" * 40, input_manifest_sha256="2" * 64,
                rows=self.rows(), support=self.support(),
                out_dir=Path(temporary) / "out", analyzer=analyzer,
                stability_check=check)
        self.assertEqual(analyses, [readout.PARENTS])
        self.assertEqual(checks, [0, 1])

    def test_external_support_failure_skips_statistics(self):
        support = self.support()
        support["teacher_valid"] = False
        report, calls, out = self.run_terminal({}, support)
        self.assertFalse(calls)
        self.assertEqual(report["verdict"], "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1")
        self.assertFalse((out / "b2-statistics-v1.json").exists())
        self.assertFalse((out / "progress.json").exists())
        self.assertIsNone(report["outputs"]["statistics"])

    def test_terminal_known_output_collision_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out"

            def analyzer(rows, *, progress_callback=None):
                if progress_callback:
                    progress_callback({"completed_replications": 1,
                                       "total_replications": 1})
                (out / "b2-statistics-v1.json").write_text("third-party")
                return {"status": "VALID", "scientific_gates_evaluated": True,
                        "gates": {"all_passed": False}}

            with self.assertRaises(FileExistsError):
                readout._finalize_from_authenticated_for_test(
                    code_sha="1" * 40, input_manifest_sha256="2" * 64,
                    rows=self.rows(), support=self.support(), out_dir=out,
                    analyzer=analyzer)
            self.assertEqual((out / "b2-statistics-v1.json").read_text(), "third-party")
            self.assertFalse((out / "progress.json").exists())

    def test_ordinary_finalize_does_not_accept_missing_authenticated_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(readout.ReadoutError):
                readout._terminal_inputs({}, Path(temporary))

    def test_cli_has_no_scientific_overrides(self):
        with self.assertRaises(SystemExit):
            readout.parse_args(["finalize", "--input-manifest", "x",
                                "--expected-input-manifest-sha256", "0" * 64,
                                "--out-dir", "out", "--R", "2"])

    def test_legacy_receipt_requires_actual_1775_equivalence_evidence(self):
        zero_barrier = {
            "allocation_hash_excludes_q200_values": True,
            "q200_fields_in_projection_decision": 0,
            "q200_value_reads": 0, "q200_label_reads": 0,
            "q200_policy_reads": 0, "q200_policy_branches": 0,
            "nodes200k_policy_reads": 0, "nodes200k_policy_branches": 0,
            "nodes200k_preseal_aggregation_reads": 0,
        }
        legacy = {
            "schema": "jass.decision_math.b2_legacy_equivalence_publisher.v1",
            "verdict": "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE",
            "equivalence_report": {
                "schema": "jass.adaptive_sibling_b2_legacy_equivalence.v1",
                "verdict": "B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE",
                "equivalence": {"parents_compared": 8_000,
                                "allocation_decision_matches": 8_000,
                                "final_b1_result_matches": 8_000},
                "information_barrier": zero_barrier,
            },
        }
        self.assertTrue(readout._legacy_equivalence_valid(legacy))
        for path, bad in [
                (("equivalence_report", "equivalence", "allocation_decision_matches"), 7_999),
                (("equivalence_report", "information_barrier", "q200_policy_reads"), 1),
                (("equivalence_report", "information_barrier",
                  "q200_fields_in_projection_decision"), False)]:
            broken = copy.deepcopy(legacy)
            cursor = broken
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = bad
            self.assertFalse(readout._legacy_equivalence_valid(broken))

    def test_historical_receipt_is_the_verified_fetch_receipt(self):
        files = []
        for name in ("historical-parent-exclusion-manifest.json",
                     "historical-parent-canonical-union.txt"):
            files.append({"path": f"artefacts/{name}", "local_name": name,
                          "sha256": "a" * 64, "size_bytes": 1})
        receipt = {"schema": 1, "state": "verified", "result_state": "completed",
                   "exit_code": 0,
                   "job_id": "cpx62-1773-l3-decision-math-b2-historical-identities-v1",
                   "attempt_id": "20260905T012244Z-1490b353",
                   "prefix": "r2:jass-data/runs/job/attempt", "code_sha": "b" * 40,
                   "files": files}
        self.assertTrue(readout._historical_receipt_valid(receipt))
        broken = copy.deepcopy(receipt)
        broken["schema"] = True
        self.assertFalse(readout._historical_receipt_valid(broken))
        broken = copy.deepcopy(receipt)
        broken["files"][1]["path"] = broken["files"][0]["path"]
        self.assertFalse(readout._historical_receipt_valid(broken))

    def test_preflight_accepts_authenticated_pid_but_rejects_type_aliases(self):
        runtime = {"python_executable": "/usr/bin/python3",
                   "python_implementation": "CPython", "python_version": "3.14.4",
                   "platform": "Linux-test", "machine": "x86_64",
                   "libc": ["glibc", "2.43"], "nproc": 16}
        receipt = {
            "schema": "jass.adaptive_sibling_b2_statistical_preflight.v1",
            "status": "VALID", "synthetic_only": True, "scientific_parents": 0,
            "bootstrap_replications": statistics.BOOTSTRAP_REPLICATIONS,
            "accepted_draws": statistics.BOOTSTRAP_REPLICATIONS * readout.PARENTS,
            "runtime_matches_kernel_environment": True,
            "runtime": {**runtime, "pid": 123}, "fresh_data_reads": 0,
            "fits": 0, "games": 0, "promotion": False, "bake": False,
            "gate_exercise_only": True, "scientific_verdict": None,
        }
        self.assertTrue(readout._preflight_support_valid(receipt, runtime))
        broken = copy.deepcopy(receipt)
        broken["scientific_parents"] = False
        self.assertFalse(readout._preflight_support_valid(broken, runtime))
        broken = copy.deepcopy(receipt)
        broken["runtime"]["pid"] = True
        self.assertFalse(readout._preflight_support_valid(broken, runtime))

    def test_current_runtime_match_is_exact_and_ignores_pid(self):
        runtime = {"python_executable": "/usr/bin/python3",
                   "python_implementation": "CPython", "python_version": "3.14.4",
                   "platform": "Linux-test", "machine": "x86_64",
                   "libc": ["glibc", "2.43"], "nproc": 16}
        with mock.patch.object(statistics, "runtime_environment",
                               return_value={**runtime, "pid": 999}):
            self.assertTrue(readout._runtime_matches_current(runtime))
            alias = copy.deepcopy(runtime)
            alias["nproc"] = True
            self.assertFalse(readout._runtime_matches_current(alias))

    def test_terminal_identity_snapshot_detects_same_bytes_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            rich = base / "rich-input.json"
            rich_raw = readout.canonical_json_bytes({})
            rich.write_bytes(rich_raw)
            manifest = {"rich_input_manifest": {
                "local_name": rich.name, "sha256": readout.sha256_bytes(rich_raw),
                "size_bytes": len(rich_raw)}}
            terminal = base / "terminal.json"
            terminal.write_bytes(readout.canonical_json_bytes(manifest))
            before = readout._terminal_identity_snapshot(terminal, manifest, base)
            replacement = base / "replacement.tmp"
            replacement.write_bytes(rich_raw)
            readout.os.replace(replacement, rich)
            after = readout._terminal_identity_snapshot(terminal, manifest, base)
            self.assertNotEqual(before, after)


class FullTerminalPipelineTests(unittest.TestCase):
    def test_real_4000_terminal_success_and_closed_manifest_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (terminal_path, terminal_raw, terminal_manifest, runtime,
             readout_manifest_path, readout_manifest, _merge_report) = \
                terminal_pipeline_fixture(base)

            analysis = {"status": "VALID", "scientific_gates_evaluated": True,
                        "gates": {"all_passed": False}}

            def bounded_analyzer(rows, *, progress_callback=None):
                self.assertEqual(len(rows), 4_000)
                if progress_callback:
                    progress_callback({"completed_replications": 1,
                                       "total_replications": 1})
                return analysis

            terminal_out = base / "terminal-out"
            args = argparse.Namespace(
                input_manifest=terminal_path,
                expected_input_manifest_sha256=hashlib.sha256(terminal_raw).hexdigest(),
                out_dir=terminal_out)
            with mock.patch.object(statistics, "runtime_environment",
                                   return_value={**runtime, "pid": os.getpid()}), \
                    mock.patch.object(statistics, "analyze_parent_stats",
                                      side_effect=bounded_analyzer) as analyzer:
                readout.finalize_command(args)
            report = json.loads((terminal_out / "b2-terminal-report-v1.json").read_bytes())
            self.assertTrue(report["support"]["all_valid"], report)
            analyzer.assert_called_once()
            self.assertEqual(report["verdict"],
                             "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1")

            for label, mutation in (
                    ("rich-manifest", lambda value: value["rich_input_manifest"].update(
                        {"sha256": "0" * 64})),
                    ("preregistration", lambda value: value["preregistration"].update(
                        {"schema": "invalid"})),
                    ("tool", lambda value: value.update(
                        {"terminal_tool": value["statistics_tool"]})),
                    ("same-path", lambda value: value["support"].update(
                        {"source_manifest": value["support"]["historical_exclusion_receipt"]})),
                    ):
                broken = copy.deepcopy(terminal_manifest)
                mutation(broken)
                with self.subTest(label=label), self.assertRaises(readout.ReadoutError):
                    readout._terminal_inputs(broken, terminal_path.parent)

            for section, failure_class in (
                    ("allocation", "ALLOCATION_BINDING_INVALID"),
                    ("projection", "PROJECTION_BINDING_INVALID")):
                broken = copy.deepcopy(readout_manifest)
                broken[section]["report_schema" if section == "allocation"
                                else "manifest_schema"] = "invalid"
                path = terminal_path.parent / f"broken-{section}.json"
                raw = readout.canonical_json_bytes(broken)
                path.write_bytes(raw)
                failure_path = base / f"failure-{section}.json"
                rc = readout.build_command(argparse.Namespace(
                    input_manifest=path,
                    expected_input_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                    out_dir=base / f"out-{section}", failure_receipt=failure_path))
                self.assertEqual(rc, 4)
                failure = json.loads(failure_path.read_bytes())
                self.assertEqual(failure["failure"]["class"], failure_class)
                self.assertTrue(failure["input_manifest_authenticated"])

            aliased = copy.deepcopy(readout_manifest)
            aliased["projection"]["manifest"] = copy.deepcopy(
                aliased["allocation"]["report"])
            alias_path = terminal_path.parent / "aliased-build-input.json"
            alias_raw = readout.canonical_json_bytes(aliased)
            alias_path.write_bytes(alias_raw)
            alias_failure = base / "alias-failure.json"
            alias_out = base / "alias-out"
            with self.assertRaises(readout.OutputSafetyError):
                readout.build_command(argparse.Namespace(
                    input_manifest=alias_path,
                    expected_input_manifest_sha256=hashlib.sha256(alias_raw).hexdigest(),
                    out_dir=alias_out, failure_receipt=alias_failure))
            self.assertFalse(alias_failure.exists())
            self.assertFalse(alias_out.exists())


if __name__ == "__main__":
    unittest.main()
