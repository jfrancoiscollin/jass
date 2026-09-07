import unittest

from jobs.tools import d3_runtime_terminal_autopsy as subject


def telemetry(depth: int, *, d3: bool) -> dict:
    return {
        "searches": 1,
        "depth_sum": depth,
        "nodes": 20000,
        "eval_calls": 10000 if d3 else 9000,
        "wall_seconds": 0.02 if d3 else 0.01,
        "d3_feature_calls": 100 if d3 else 0,
        "mean_completed_depth": float(depth),
    }


def primary_pair(i: int) -> dict:
    fen = "W:W31-50:B1-20" if i % 2 == 0 else "W:W31-40:B1-10"
    game = lambda color: {
        "d3_color": color,
        "outcome_white": "L" if color == "white" else "W",
        "d3_wdl": "L", "d3_score": 0.0, "plies": 80,
        "reason": "ply cap",
        "d3_telemetry": telemetry(9, d3=True),
        "control_telemetry": telemetry(10, d3=False),
    }
    return {
        "schema": subject.PAIR_SCHEMA, "mode": "primary",
        "opening_index": i, "fen": fen,
        "node_budget": subject.NODE_BUDGET, "max_plies": subject.MAX_PLIES,
        "games": [game("white"), game("black")], "pair_score_d3": 0.0,
    }


def harness_pair(i: int) -> dict:
    game = lambda color: {
        "arm_a_color": color, "outcome_white": "D", "arm_a_score": 0.5,
        "plies": 80, "reason": "ply cap",
        "arm_a_telemetry": telemetry(10, d3=False),
        "arm_b_telemetry": telemetry(10, d3=False),
    }
    return {
        "schema": subject.PAIR_SCHEMA, "mode": "harness",
        "opening_index": i, "fen": "W:W31-50:B1-20",
        "node_budget": subject.NODE_BUDGET, "max_plies": subject.MAX_PLIES,
        "games": [game("white"), game("black")], "pair_score_arm_a": 0.5,
    }


class D3RuntimeTerminalAutopsyTests(unittest.TestCase):
    def test_spearman_direction(self):
        self.assertAlmostEqual(subject.spearman([0, 1, 2], [0, 2, 4]), 1.0)
        self.assertAlmostEqual(subject.spearman([0, 1, 2], [4, 2, 0]), -1.0)

    def test_frozen_terminal_autopsy_is_diagnostic_only(self):
        primary = [primary_pair(i) for i in range(subject.PRIMARY_PAIRS)]
        harness = [harness_pair(i) for i in range(subject.HARNESS_PAIRS)]
        candidate = {
            "searches": 1500, "depth_sum": 13500, "nodes": 30000000,
            "eval_calls": 15000000, "d3_feature_calls": 150000,
        }
        control = {
            "searches": 1500, "depth_sum": 15000, "nodes": 30000000,
            "eval_calls": 13500000, "d3_feature_calls": 0,
        }
        source = {
            "verdict": subject.SOURCE_VERDICT, "next_stage": "STOP",
            "strength_games": 1700, "fits": 0,
            "primary": {
                "wins": 0, "draws": 0, "losses": 1500, "score_d3": 0.0,
                "candidate_telemetry": candidate, "control_telemetry": control,
            },
        }
        pool = {
            "verdict": "D3_RUNTIME_EQUAL_NODE_POOL_READY_V1",
            "primary_openings": 750, "harness_openings": 100,
        }
        result = subject.autopsy(primary, harness, source, pool)
        self.assertEqual(result["verdict"], subject.VERDICT)
        self.assertEqual(result["classification"],
                         "BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION")
        self.assertTrue(result["flags"]["equal_node_depth_efficiency_degraded"])
        self.assertTrue(result["flags"]["runtime_cost_amplified"])
        self.assertEqual(result["strength_games"], 0)
        self.assertEqual(result["searches"], 0)
        self.assertEqual(result["fits"], 0)
        self.assertFalse(result["equal_time_authorized"])
        self.assertEqual(result["next_stage"], "D4_SEARCH_UTILITY_PREREGISTRATION_ONLY")


if __name__ == "__main__":
    unittest.main()
