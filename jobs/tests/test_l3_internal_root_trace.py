import unittest

from jobs.tools.l3_internal_root_trace import parse_root_events
from jobs.tools.l3_internal_root_trace_report import (
    classify,
    compare_attempts,
    final_attempt,
)
from collections import Counter


def attempt(order, scores=None, alpha=-30000, beta=30000):
    scores = scores or list(range(len(order)))
    moves = [
        {
            "event": "move",
            "depth": 1,
            "attempt": 1,
            "index": index,
            "move": move,
            "alpha_before": alpha if index == 1 else max(scores[: index - 1]),
            "beta": beta,
            "score": scores[index - 1],
            "best": max(scores[:index]),
            "cutoff": 0,
        }
        for index, move in enumerate(order, 1)
    ]
    return {
        "attempt": 1,
        "begin": {
            "event": "begin",
            "depth": 1,
            "attempt": 1,
            "alpha": alpha,
            "beta": beta,
            "moves": len(order),
        },
        "moves": moves,
        "end": {
            "event": "end",
            "depth": 1,
            "attempt": 1,
            "searched": len(order),
            "bestmove": order[scores.index(max(scores))],
            "score": max(scores),
        },
    }


class InternalRootTraceTests(unittest.TestCase):
    def test_trace_parser_validates_all_depths_and_attempts(self):
        lines = []
        for depth in range(1, 13):
            lines.extend(
                [
                    f"info roottrace event=begin depth={depth} attempt=1 alpha=-30000 beta=30000 moves=1",
                    f"info roottrace event=move depth={depth} attempt=1 index=1 move=31-26 alpha_before=-30000 beta=30000 score=7 best=7 cutoff=0",
                    f"info roottrace event=end depth={depth} attempt=1 searched=1 bestmove=31-26 score=7 alpha=-30000 beta=30000 complete=1",
                ]
            )
        events = parse_root_events(lines)
        self.assertEqual(len(events), 36)
        self.assertEqual(final_attempt(events, 12)["end"]["bestmove"], "31-26")

    def test_terminal_score_scales_are_normalized(self):
        result = compare_attempts(
            attempt(["31-26"], [29_999]),
            attempt(["31-26"], [9_999], alpha=-10_000, beta=10_000),
        )
        self.assertIsNone(result["first_divergence"])

    def test_order_is_localized_before_bound_score_differences(self):
        result = compare_attempts(
            attempt(["31-26", "32-27"], [10, 12]),
            attempt(["32-27", "31-26"], [12, 10]),
        )
        self.assertEqual(result["first_divergence"], "ROOT_ORDER")
        self.assertEqual(
            classify(Counter({"ROOT_ORDER": 48}), 48),
            "ROOT_ORDERING_SELECTIVITY_DIVERGENCE",
        )

    def test_recursive_score_difference_is_distinct(self):
        result = compare_attempts(
            attempt(["31-26", "32-27"], [10, 12]),
            attempt(["31-26", "32-27"], [10, 13]),
        )
        self.assertEqual(result["first_divergence"], "RECURSIVE_SCORE")


if __name__ == "__main__":
    unittest.main()
