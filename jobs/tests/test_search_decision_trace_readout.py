import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.search_decision_trace_readout import (
    ContractError,
    analyze_row,
    build_readout,
    load_jsonl,
    main,
    merge_intervals,
    validate_reports,
)


def move(start: int, end: int, captured: int = 0) -> dict[str, object]:
    return {
        "from": start,
        "to": end,
        "num_captures": 1 if captured else 0,
        "promotes": False,
        "captured": captured,
    }


def action(
    selected: dict[str, object], score: int, alpha: int, beta: int,
    bound: str, *, completed: bool = True, nodes: int = 1,
    pvs: int = 0,
) -> dict[str, object]:
    return {
        "move": selected,
        "score": score,
        "bound": bound,
        "alpha": alpha,
        "beta": beta,
        "nodes": nodes,
        "eval_calls": nodes,
        "pvs_researches": pvs,
        "cutoff": completed and score >= beta,
        "completed": completed,
        "pv_hash": 14_695_981_039_346_656_037 if not completed else 18_446_744_073_709_551_557,
        "pv_length": 0 if not completed else 1,
    }


def attempt(
    depth: int, number: int, alpha: int, beta: int, score: int,
    bound: str, best: dict[str, object], actions: list[dict[str, object]],
    catalogue_size: int, *, completed: bool = True, before: int = 0,
    pvs_before: int = 0,
) -> dict[str, object]:
    nodes = sum(int(item["nodes"]) for item in actions)
    evals = sum(int(item["eval_calls"]) for item in actions)
    pvs = sum(int(item["pvs_researches"]) for item in actions)
    return {
        "depth": depth,
        "attempt": number,
        "alpha": alpha,
        "beta": beta,
        "score": score,
        "bound": bound,
        "best_move": best,
        "nodes_before": before,
        "nodes_after": before + nodes,
        "eval_calls_before": before,
        "eval_calls_after": before + evals,
        "pvs_researches_before": pvs_before,
        "pvs_researches_after": pvs_before + pvs,
        "cutoff": completed and score >= beta,
        "completed": completed,
        "all_actions_searched": len(actions) == catalogue_size,
        "actions": actions,
    }


def trace(
    catalogue: list[dict[str, object]], attempts: list[dict[str, object]],
    *, draw: bool = False, no_moves: bool = False,
) -> dict[str, object]:
    best = attempts[-1]["best_move"] if attempts else move(0, 0)
    score = int(attempts[-1]["score"]) if attempts else -30_000
    completed = max(
        (int(item["depth"]) for item in attempts if item["completed"] and item["bound"] == "Exact"),
        default=0,
    )
    return {
        "schema": "jass.search-decision-trace",
        "version": 1,
        "root_rule_draw": draw,
        "no_legal_moves": no_moves,
        "semantic_root_actions": len(catalogue),
        "root_actions": catalogue,
        "attempts": attempts,
        "result": {
            "best_move": best,
            "score": -30_000 if no_moves else (0 if draw else score),
            "completed_depth": completed,
            "effective_depth": max((int(item["depth"]) for item in attempts), default=0),
            "aborted_iteration": bool(attempts and not attempts[-1]["completed"]),
            "stop_reason": "nodes" if attempts and not attempts[-1]["completed"] else "none",
            "nodes": int(attempts[-1]["nodes_after"]) if attempts else 0,
            "eval_calls": int(attempts[-1]["eval_calls_after"]) if attempts else 0,
            "pvs_researches": int(attempts[-1]["pvs_researches_after"]) if attempts else 0,
            "pv_hash": (
                18_446_744_073_709_551_557 if attempts
                else 14_695_981_039_346_656_037
            ),
            "pv_length": 1 if attempts else 0,
        },
    }


def refresh_result(payload: dict[str, object]) -> None:
    attempts = payload["attempts"]
    result = payload["result"]
    settled = [item for item in attempts if item["completed"] and item["bound"] == "Exact"]
    last = settled[-1] if settled else None
    result["completed_depth"] = int(last["depth"]) if last else 0
    result["effective_depth"] = max((int(item["depth"]) for item in attempts), default=0)
    result["best_move"] = last["best_move"] if last else payload["root_actions"][0]
    result["score"] = 0 if payload["root_rule_draw"] or last is None else int(last["score"])
    result["nodes"] = int(attempts[-1]["nodes_after"]) if attempts else 0
    result["eval_calls"] = int(attempts[-1]["eval_calls_after"]) if attempts else 0
    result["pvs_researches"] = int(attempts[-1]["pvs_researches_after"]) if attempts else 0
    interrupted = bool(attempts and not attempts[-1]["completed"])
    result["stop_reason"] = "nodes" if interrupted else "none"
    result["aborted_iteration"] = interrupted and result["effective_depth"] > result["completed_depth"]


def row(payload: dict[str, object], invocation: str = "inv-1") -> dict[str, object]:
    stopped = payload["result"]["stop_reason"] == "nodes"
    max_nodes = int(payload["result"]["nodes"]) if stopped else 0
    return {
        "schema": "jass.search-decision-trace-export-row.v1",
        "version": 1,
        "invocation_id": invocation,
        "board_identity": {
            "canonical_fen": "W:W31:B20",
            "zobrist_hash": 18_446_744_073_709_551_557,
        },
        "rule_state_identity": {
            "halfmove_clock": 50 if payload["root_rule_draw"] else 0,
            "history_hashes": [],
        },
        "search_context_identity": {
            "evaluation": {
                "kind": "handcrafted",
                "artifact_path": None,
                "artifact_sha256": None,
                "artifact_sha256_verified": False,
                "conversion_sidecar_present": False,
                "conversion_sidecar_path": None,
                "conversion_sidecar_sha256": None,
            },
            "code_provenance": {
                "declared": "test-code",
                "declared_verified_by_exporter": False,
                "executable_path": "/tmp/test-exporter",
                "executable_sha256": "a" * 64,
                "executable_sha256_verified": True,
            },
            "search_params_source": "compiled_defaults",
            "max_depth": max(1, int(payload["result"]["effective_depth"])),
            "max_nodes": max_nodes,
            "node_limit_mode": "exact" if stopped else "periodic",
            "movetime_ms": 0,
            "threads": 1,
            "book_enabled": False,
            "tt_mb": 16,
            "fresh_tt_per_invocation": True,
        },
        "trace": payload,
    }


def settled_two_action(
    competitor_score: int = 19, chosen_score: int = 20,
) -> dict[str, object]:
    chosen = move(31, 26)
    competitor = move(32, 27)
    actions = [
        action(chosen, chosen_score, -100, 100, "Exact", nodes=2, pvs=1),
        action(competitor, competitor_score, chosen_score, 100, "Upper", nodes=3),
    ]
    return trace(
        [chosen, competitor],
        [attempt(1, 1, -100, 100, chosen_score, "Exact", chosen, actions, 2)],
    )


class SearchDecisionTraceReadoutTests(unittest.TestCase):
    def test_strict_certificate_and_rmax_zero_are_distinct_from_tie(self):
        certified = analyze_row(row(settled_two_action()))
        decision = certified["horizons"][0]["decision"]
        self.assertTrue(decision["certified_at_current_horizon"])
        self.assertEqual(decision["r_max"], {"status": "FINITE", "value": 0})

        tied = analyze_row(row(settled_two_action(competitor_score=20)))
        tied_decision = tied["horizons"][0]["decision"]
        self.assertFalse(tied_decision["certified_at_current_horizon"])
        self.assertEqual(tied_decision["certification_basis"], "no_strict_separation")
        self.assertEqual(tied_decision["r_max"], {"status": "FINITE", "value": 0})

    def test_retries_merge_only_inside_one_horizon_and_contradictions_fail(self):
        chosen = move(31, 26)
        other = move(32, 27)
        first = attempt(
            1, 1, -10, 20, 30, "Lower", chosen,
            [action(chosen, 30, -10, 20, "Lower")], 2,
        )
        second_actions = [
            action(chosen, 30, -10, 100, "Exact"),
            action(other, 10, 30, 100, "Upper"),
        ]
        second = attempt(1, 2, -10, 100, 30, "Exact", chosen, second_actions, 2, before=1)
        result = analyze_row(row(trace([chosen, other], [first, second])))
        intervals = {item["move"]["from"]: item for item in result["horizons"][0]["actions"]}
        self.assertEqual((intervals[31]["lower"], intervals[31]["upper"]), (30, 30))
        self.assertTrue(intervals[32]["lower_unbounded"])
        self.assertEqual(intervals[32]["upper"], 10)
        self.assertEqual(intervals[32]["none_or_missing_attempts"], [1])

        validated = copy.deepcopy(row(trace([chosen, other], [first, second])))
        analyzed = analyze_row(validated)
        self.assertEqual(analyzed["horizons"][0]["depth"], 1)
        bad_second = copy.deepcopy(second)
        bad_second["score"] = 25
        bad_second["actions"][0]["score"] = 25
        bad_second["actions"][1]["alpha"] = 25
        with self.assertRaisesRegex(ContractError, "contradictory retry bounds"):
            analyze_row(row(trace([chosen, other], [first, bad_second])))

    def test_horizons_and_invocations_never_merge(self):
        first = settled_two_action(19, 20)
        second_attempt = copy.deepcopy(first["attempts"][0])
        second_attempt["depth"] = 2
        second_attempt["score"] = 40
        second_attempt["actions"][0]["score"] = 40
        second_attempt["actions"][1]["alpha"] = 40
        second_attempt["nodes_before"] = 5
        second_attempt["nodes_after"] = 10
        second_attempt["eval_calls_before"] = 5
        second_attempt["eval_calls_after"] = 10
        second_attempt["pvs_researches_before"] = 1
        second_attempt["pvs_researches_after"] = 2
        first["attempts"].append(second_attempt)
        refresh_result(first)
        analyzed = analyze_row(row(first))
        self.assertEqual(
            [horizon["actions"][0]["lower"] for horizon in analyzed["horizons"]],
            [20, 40],
        )
        payload = build_readout([
            row(settled_two_action(19, 20), "one"),
            row(settled_two_action(9, 10), "two"),
        ])
        self.assertEqual(len(payload["contexts"]), 2)
        self.assertEqual(payload["guards"]["cross_invocation_bound_merges"], 0)

    def test_partial_horizon_is_excluded_from_sequence(self):
        payload = settled_two_action()
        chosen = payload["root_actions"][0]
        interrupted_action = action(
            chosen, 7, -100, 100, "None", completed=False, nodes=2,
        )
        payload["attempts"].append(attempt(
            2, 1, -100, 100, 7, "None", chosen, [interrupted_action], 2,
            completed=False, before=5, pvs_before=1,
        ))
        refresh_result(payload)
        analyzed = analyze_row(row(payload))
        self.assertEqual(analyzed["sequence"]["completed_horizons"], 1)
        self.assertFalse(analyzed["horizons"][1]["settled"])
        self.assertEqual(analyzed["horizons"][1]["decision"]["status"], "INCOMPLETE_HORIZON")

    def test_flips_suffix_stability_volatility_pvs_and_pv_churn(self):
        payload = settled_two_action(19, 20)
        a, b = payload["root_actions"]
        second_actions = [
            action(a, 10, -100, 100, "Exact", pvs=1),
            action(b, 30, 10, 100, "Exact", pvs=2),
        ]
        second_actions[1]["pv_hash"] = 123
        payload["attempts"].append(
            attempt(2, 1, -100, 100, 30, "Exact", b, second_actions, 2,
                    before=5, pvs_before=1),
        )
        third_actions = [
            action(a, 9, -100, 100, "Exact"),
            action(b, 35, 9, 100, "Exact", pvs=4),
        ]
        third_actions[1]["pv_hash"] = 456
        payload["attempts"].append(
            attempt(3, 1, -100, 100, 35, "Exact", b, third_actions, 2,
                    before=7, pvs_before=4),
        )
        refresh_result(payload)
        sequence = analyze_row(row(payload))["sequence"]
        self.assertEqual(len(sequence["best_move_flips"]), 1)
        self.assertEqual(sequence["first_observed_suffix_stable_depth"], 2)
        self.assertEqual(sequence["score_steps"][0]["delta"], 10)
        self.assertEqual(sequence["score_range"], 15)
        self.assertEqual(sequence["pv_churn_transitions"], 2)
        self.assertEqual(sequence["pv_churn_same_action_transitions"], 1)

    def test_single_action_is_forced_without_certifying_its_value(self):
        only = move(31, 26)
        incomplete = action(only, 0, -100, 100, "None", completed=False)
        payload = trace(
            [only],
            [attempt(1, 1, -100, 100, 0, "None", only, [incomplete], 1, completed=False)],
        )
        decision = analyze_row(row(payload))["horizons"][0]["decision"]
        self.assertEqual(decision["status"], "SINGLE_LEGAL_ACTION")
        self.assertTrue(decision["certified_at_current_horizon"])
        self.assertFalse(decision["chosen_value_exact"])
        self.assertEqual(decision["r_max"]["value"], 0)

    def test_draw_and_no_legal_action_are_explicit(self):
        drawn = analyze_row(row(trace([], [], draw=True, no_moves=True)))
        self.assertTrue(drawn["no_legal_moves"])
        self.assertEqual(drawn["decision_scope"], "RULE_DRAW_SEARCH_OBSERVATION")
        self.assertEqual(drawn["sequence"]["completed_horizons"], 0)

        malformed = row(trace([], [], no_moves=True))
        malformed["trace"]["result"]["score"] = 123
        with self.assertRaisesRegex(ContractError, "no-legal-move result drift"):
            analyze_row(malformed)

        false_negative_clock = row(settled_two_action())
        false_negative_clock["rule_state_identity"]["halfmove_clock"] = 50
        with self.assertRaisesRegex(ContractError, "root rule-draw identity drift"):
            analyze_row(false_negative_clock)

        unsafe_clock = row(settled_two_action())
        unsafe_clock["rule_state_identity"]["halfmove_clock"] = (1 << 31) - 1
        with self.assertRaisesRegex(ContractError, "integer above"):
            analyze_row(unsafe_clock)

        false_negative_history = row(settled_two_action())
        false_negative_history["rule_state_identity"]["history_hashes"] = [
            false_negative_history["board_identity"]["zobrist_hash"],
        ]
        with self.assertRaisesRegex(ContractError, "root rule-draw identity drift"):
            analyze_row(false_negative_history)

        false_positive = row(settled_two_action())
        false_positive["trace"]["root_rule_draw"] = True
        false_positive["trace"]["result"]["score"] = 0
        with self.assertRaisesRegex(ContractError, "root rule-draw identity drift"):
            analyze_row(false_positive)

    def test_retry_state_machine_and_context_depth_fail_closed(self):
        exact_then_retry = settled_two_action()
        later = copy.deepcopy(exact_then_retry["attempts"][0])
        later["attempt"] = 2
        later["alpha"] = -100
        later["beta"] = 10
        later["actions"] = [action(
            exact_then_retry["root_actions"][0], 20, -100, 10, "Lower",
        )]
        later["score"] = 20
        later["bound"] = "Lower"
        later["best_move"] = exact_then_retry["root_actions"][0]
        later["nodes_before"] = 5
        later["nodes_after"] = 6
        later["eval_calls_before"] = 5
        later["eval_calls_after"] = 6
        later["pvs_researches_before"] = 1
        later["pvs_researches_after"] = 1
        later["all_actions_searched"] = False
        later["cutoff"] = True
        exact_then_retry["attempts"].append(later)
        refresh_result(exact_then_retry)
        with self.assertRaisesRegex(ContractError, "retry follows terminal Exact"):
            analyze_row(row(exact_then_retry))

        bad_widen = copy.deepcopy(settled_two_action())
        a, b = bad_widen["root_actions"]
        first = attempt(
            1, 1, -10, 20, 30, "Lower", a,
            [action(a, 30, -10, 20, "Lower")], 2,
        )
        second = attempt(
            1, 2, -100, 100, 30, "Exact", a,
            [action(a, 30, -100, 100, "Exact"),
             action(b, 10, 30, 100, "Upper")],
            2, before=1,
        )
        with self.assertRaisesRegex(ContractError, "widen beta only"):
            analyze_row(row(trace([a, b], [first, second])))

        partial_upper = attempt(
            1, 1, -10, 20, -20, "Upper", a,
            [action(a, -20, -10, 20, "Upper")], 2,
        )
        widened_actions = [
            action(a, -20, -100, 20, "Exact"),
            action(b, -30, -20, 20, "Upper"),
        ]
        widened = attempt(
            1, 2, -100, 20, -20, "Exact", a, widened_actions, 2, before=1,
        )
        with self.assertRaisesRegex(ContractError, "partial attempt lacks beta cutoff"):
            analyze_row(row(trace([a, b], [partial_upper, widened])))

        too_deep = settled_two_action()
        interrupted = action(a, 0, -100, 100, "None", completed=False)
        too_deep["attempts"].append(attempt(
            2, 1, -100, 100, 0, "None", a, [interrupted], 2,
            completed=False, before=5, pvs_before=1,
        ))
        refresh_result(too_deep)
        wrapped = row(too_deep)
        wrapped["search_context_identity"]["max_depth"] = 1
        with self.assertRaisesRegex(ContractError, "exceeds search context max_depth"):
            analyze_row(wrapped)

    def test_fail_closed_on_missing_action_counter_and_bound_drift(self):
        bad_counter = row(settled_two_action())
        bad_counter["trace"]["attempts"][0]["nodes_after"] += 1
        with self.assertRaisesRegex(ContractError, "delta mismatch"):
            analyze_row(bad_counter)

        overflow_counter = row(settled_two_action())
        overflow_counter["trace"]["attempts"][0]["actions"][0]["nodes"] = 1 << 64
        overflow_counter["trace"]["attempts"][0]["nodes_after"] = (1 << 64) + 3
        overflow_counter["trace"]["result"]["nodes"] = (1 << 64) + 3
        with self.assertRaisesRegex(ContractError, "integer above"):
            analyze_row(overflow_counter)

        overflow_score = row(settled_two_action())
        overflow_score["trace"]["attempts"][0]["score"] = 1 << 31
        with self.assertRaisesRegex(ContractError, "integer above"):
            analyze_row(overflow_score)

        bad_bound = row(settled_two_action())
        bad_bound["trace"]["attempts"][0]["actions"][1]["bound"] = "Exact"
        with self.assertRaisesRegex(ContractError, "bound contract drift"):
            analyze_row(bad_bound)

        impossible_move = row(settled_two_action())
        for location in (
            impossible_move["trace"]["root_actions"][0],
            impossible_move["trace"]["attempts"][0]["actions"][0]["move"],
            impossible_move["trace"]["attempts"][0]["best_move"],
            impossible_move["trace"]["result"]["best_move"],
        ):
            location["captured"] = 1
        with self.assertRaisesRegex(ContractError, "captured-square count drift"):
            analyze_row(impossible_move)

    def test_fail_closed_on_window_final_counter_and_best_reduction_drift(self):
        bad_window = row(settled_two_action())
        bad_window["trace"]["attempts"][0]["actions"][1]["alpha"] -= 1
        with self.assertRaisesRegex(ContractError, "non-sequential action alpha"):
            analyze_row(bad_window)

        bad_final = row(settled_two_action())
        bad_final["trace"]["result"]["nodes"] += 1
        with self.assertRaisesRegex(ContractError, "final nodes receipt mismatch"):
            analyze_row(bad_final)

        bad_best = row(settled_two_action())
        bad_best["trace"]["attempts"][0]["best_move"] = move(32, 27)
        with self.assertRaisesRegex(ContractError, "score/best-move reduction drift"):
            analyze_row(bad_best)

        bad_action_pv = row(settled_two_action())
        bad_action_pv["trace"]["attempts"][0]["actions"][0]["pv_length"] = 2
        with self.assertRaisesRegex(ContractError, "PV length outside horizon"):
            analyze_row(bad_action_pv)

        bad_public_pv = row(settled_two_action())
        bad_public_pv["trace"]["result"]["pv_length"] = 2
        with self.assertRaisesRegex(ContractError, "public PV length exceeds"):
            analyze_row(bad_public_pv)

        capped = row(settled_two_action())
        capped["search_context_identity"]["max_nodes"] = 4
        capped["search_context_identity"]["node_limit_mode"] = "exact"
        with self.assertRaisesRegex(ContractError, "exceeded cap"):
            analyze_row(capped)

    def test_report_is_bound_to_rows_context_cardinality_and_quarantine(self):
        payload = row(settled_two_action())
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.jsonl"
            trace_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            _, receipts = load_jsonl([trace_path])
            report = {
                "schema": "jass.search-decision-trace-export.v1",
                "version": 1,
                "diagnostic_only": True,
                "input_manifest_path": str(Path(tmp) / "manifest.tsv"),
                "input_manifest_sha256": "b" * 64,
                "input_manifest_sha256_verified": True,
                "output_jsonl_sha256": receipts[0]["sha256"],
                "output_jsonl_sha256_verified": True,
                "output_jsonl_path": str(trace_path),
                "input_invocations": 1,
                "emitted_invocations": 1,
                "search_context_identity": payload["search_context_identity"],
                "fits": 0,
                "strength_games": 0,
                "bakes": 0,
                "promotions": 0,
                "training_allowed": False,
                "tuning_allowed": False,
                "model_selection_allowed": False,
                "promotion_authorized": False,
            }
            report_path = Path(tmp) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(len(validate_reports([report_path], receipts)), 1)

            report["search_context_identity"] = copy.deepcopy(payload["search_context_identity"])
            report["search_context_identity"]["tt_mb"] = 32
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "report/row search context drift"):
                validate_reports([report_path], receipts)

            report["search_context_identity"] = payload["search_context_identity"]
            report["input_invocations"] = 2
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "identity/cardinality drift"):
                validate_reports([report_path], receipts)

            report["input_invocations"] = 1
            report["training_allowed"] = True
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "quarantine drift"):
                validate_reports([report_path], receipts)

    def test_summary_partitions_rule_draw_from_ordinary_contexts(self):
        ordinary = row(settled_two_action(), "ordinary")
        draw_trace = settled_two_action()
        draw_trace["root_rule_draw"] = True
        draw_trace["result"]["score"] = 0
        drawn = row(draw_trace, "drawn")
        summary = build_readout([ordinary, drawn])["summary"]
        self.assertEqual(summary["contexts"], 2)
        self.assertEqual(
            summary["by_scope"]["ORDINARY_SEARCH_OBSERVATION"]["certified_decisions"], 1,
        )
        self.assertEqual(
            summary["by_scope"]["RULE_DRAW_SEARCH_OBSERVATION"]["certified_decisions"], 1,
        )

    def test_each_context_keeps_unambiguous_jsonl_and_report_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace_paths = [root / "first.jsonl", root / "second.jsonl"]
            payloads = [
                row(settled_two_action(), "source-one"),
                row(settled_two_action(), "source-two"),
            ]
            for path, payload in zip(trace_paths, payloads):
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            rows, receipts = load_jsonl(trace_paths)
            report_paths = []
            for index, (trace_path, payload, receipt) in enumerate(
                zip(trace_paths, payloads, receipts), 1,
            ):
                report = {
                    "schema": "jass.search-decision-trace-export.v1",
                    "version": 1,
                    "diagnostic_only": True,
                    "input_manifest_path": str(root / f"manifest-{index}.tsv"),
                    "input_manifest_sha256": f"{index}" * 64,
                    "input_manifest_sha256_verified": True,
                    "output_jsonl_path": str(trace_path),
                    "output_jsonl_sha256": receipt["sha256"],
                    "output_jsonl_sha256_verified": True,
                    "input_invocations": 1,
                    "emitted_invocations": 1,
                    "search_context_identity": payload["search_context_identity"],
                    "fits": 0,
                    "strength_games": 0,
                    "bakes": 0,
                    "promotions": 0,
                    "training_allowed": False,
                    "tuning_allowed": False,
                    "model_selection_allowed": False,
                    "promotion_authorized": False,
                }
                report_path = root / f"report-{index}.json"
                report_path.write_text(json.dumps(report), encoding="utf-8")
                report_paths.append(report_path)
            reports = validate_reports(reversed(report_paths), receipts)
            contexts = build_readout(rows, receipts, reports)["contexts"]
            by_id = {context["invocation_id"]: context for context in contexts}
            for index, invocation in enumerate(("source-one", "source-two")):
                source = by_id[invocation]["source_receipt"]
                self.assertEqual(source["jsonl_path"], str(trace_paths[index]))
                self.assertEqual(source["jsonl_line"], 1)
                self.assertEqual(source["jsonl_sha256"], receipts[index]["sha256"])
                expected_report = report_paths[index]
                self.assertEqual(source["export_report_path"], str(expected_report))
                self.assertEqual(
                    source["export_report_sha256"],
                    hashlib.sha256(expected_report.read_bytes()).hexdigest(),
                )

    def test_jsonl_uses_real_parser_and_preserves_uint64(self):
        payload = row(settled_two_action())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            rows, receipts = load_jsonl([path])
        self.assertEqual(
            rows[0]["board_identity"]["zobrist_hash"],
            18_446_744_073_709_551_557,
        )
        self.assertEqual(receipts[0]["rows"], 1)

    def test_cli_refuses_output_alias_of_input(self):
        payload = row(settled_two_action())
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "trace.jsonl"
            original = json.dumps(payload) + "\n"
            trace_path.write_text(original, encoding="utf-8")
            digest = hashlib.sha256(original.encode()).hexdigest()
            report = {
                "schema": "jass.search-decision-trace-export.v1",
                "version": 1,
                "diagnostic_only": True,
                "input_manifest_path": str(Path(tmp) / "manifest.tsv"),
                "input_manifest_sha256": "b" * 64,
                "input_manifest_sha256_verified": True,
                "output_jsonl_sha256": digest,
                "output_jsonl_sha256_verified": True,
                "output_jsonl_path": str(trace_path),
                "input_invocations": 1,
                "emitted_invocations": 1,
                "search_context_identity": payload["search_context_identity"],
                "fits": 0,
                "strength_games": 0,
                "bakes": 0,
                "promotions": 0,
                "training_allowed": False,
                "tuning_allowed": False,
                "model_selection_allowed": False,
                "promotion_authorized": False,
            }
            report_path = Path(tmp) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "aliases an input artifact"):
                main([
                    "--input", str(trace_path),
                    "--export-report", str(report_path),
                    "--output-json", str(trace_path.parent / "." / trace_path.name),
                ])
            self.assertEqual(trace_path.read_text(encoding="utf-8"), original)

    def test_cli_refuses_output_alias_of_provenance_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "model.pjtw"
            executable = root / "exporter"
            manifest = root / "manifest.tsv"
            for path in (model, executable, manifest):
                path.write_text(f"sentinel:{path.name}", encoding="utf-8")
            payload = row(settled_two_action())
            payload["search_context_identity"]["evaluation"] = {
                "kind": "file",
                "artifact_path": str(model),
                "artifact_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "artifact_sha256_verified": True,
                "conversion_sidecar_present": False,
                "conversion_sidecar_path": None,
                "conversion_sidecar_sha256": None,
            }
            payload["search_context_identity"]["code_provenance"]["executable_path"] = str(executable)
            payload["search_context_identity"]["code_provenance"]["executable_sha256"] = hashlib.sha256(
                executable.read_bytes(),
            ).hexdigest()
            trace_path = root / "trace.jsonl"
            trace_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            report = {
                "schema": "jass.search-decision-trace-export.v1",
                "version": 1,
                "diagnostic_only": True,
                "input_manifest_path": str(manifest),
                "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "input_manifest_sha256_verified": True,
                "output_jsonl_path": str(trace_path),
                "output_jsonl_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                "output_jsonl_sha256_verified": True,
                "input_invocations": 1,
                "emitted_invocations": 1,
                "search_context_identity": payload["search_context_identity"],
                "fits": 0,
                "strength_games": 0,
                "bakes": 0,
                "promotions": 0,
                "training_allowed": False,
                "tuning_allowed": False,
                "model_selection_allowed": False,
                "promotion_authorized": False,
            }
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            sentinels = {path: path.read_bytes() for path in (model, executable, manifest)}
            future_sidecar = Path(str(model) + ".cvh")
            for protected in (
                *sentinels, future_sidecar, future_sidecar / "readout.json",
            ):
                with self.subTest(protected=protected.name):
                    with self.assertRaisesRegex(ContractError, "aliases a provenance artifact"):
                        main([
                            "--input", str(trace_path),
                            "--export-report", str(report_path),
                            "--output-json", str(protected),
                        ])
            for path, content in sentinels.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertFalse(future_sidecar.exists())

    def test_merge_intervals_treats_none_and_missing_as_unbounded(self):
        a, b = (31, 26, 0, False, 0), (32, 27, 0, False, 0)
        attempts = [{
            "_number": 1,
            "_actions": {
                a: {"completed": False, "bound": "None", "score": 99},
            },
        }]
        merged = merge_intervals(attempts, [a, b], "synthetic")
        self.assertIsNone(merged[a]["lower"])
        self.assertIsNone(merged[a]["upper"])
        self.assertIsNone(merged[b]["lower"])
        self.assertIsNone(merged[b]["upper"])


if __name__ == "__main__":
    unittest.main()
