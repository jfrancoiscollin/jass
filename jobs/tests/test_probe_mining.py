#!/usr/bin/env python3
"""Tests §11.3 — mining passif HORS BOUCLE."""
from __future__ import annotations
import ast, importlib.util, struct, tempfile, unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
M = TOOLS / "probe_mining.py"
spec = importlib.util.spec_from_file_location("probe_mining", M); PM = importlib.util.module_from_spec(spec); spec.loader.exec_module(PM)

FORBIDDEN = {"wdl_finetune", "scan_selfplay_gen", "promotion_gate", "train_stream", "train"}


class MiningTests(unittest.TestCase):
    def test_hors_boucle_no_forbidden_imports(self):
        # garantie architecturale : le module de mining n'importe AUCUN outil de fit/gen/promotion
        tree = ast.parse(M.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & FORBIDDEN, set(), f"import hors-boucle interdit: {imported & FORBIDDEN}")

    def test_win_to_draw_and_loss_present(self):
        trajs = [
            dict(parent_oracle="WIN", played_child_oracle="DRAW", parent_id="p1", source_game_id="g1"),
            dict(parent_oracle="WIN", played_child_oracle="LOSS", parent_id="p2", source_game_id="g1"),
            dict(parent_oracle="WIN", played_child_oracle="WIN", parent_id="p3", source_game_id="g1"),   # non-événement
            dict(parent_oracle="DRAW", played_child_oracle="LOSS", parent_id="p4", source_game_id="g2"),  # parent non-WIN
        ]
        ev = PM.extract_events(trajs, "T1-bis")
        types = {e["event_type"] for e in ev}
        self.assertEqual(types, {"WIN_TO_DRAW", "WIN_TO_LOSS"})
        self.assertEqual(len(ev), 2)

    def test_cap_per_parent(self):
        trajs = [dict(parent_oracle="WIN", played_child_oracle="DRAW", parent_id="p1", source_game_id=f"g{i}") for i in range(5)]
        ev = PM.extract_events(trajs, "T2", cap_per_parent=2)
        self.assertEqual(len(ev), 2)

    def test_summary_split_metadata(self):
        trajs = [dict(parent_oracle="WIN", played_child_oracle="DRAW", parent_id="p1",
                      source_game_id="g1", oracle_provenance={"pieces": 8, "strata": "p4_egal", "tier": "TB_EXACT"})]
        ev = PM.extract_events(trajs, "T1-bis")
        s = PM.summarize(ev, n_games_inspected=10, n_parents_win=1)
        self.assertEqual(s["win_to_draw"], 1); self.assertEqual(s["unique_parents"], 1)
        self.assertEqual(s["by_strata"]["p4_egal"], 1); self.assertEqual(s["by_tier"]["TB_EXACT"], 1)
        # split-ready : chaque event porte parent_id + source_game_id
        self.assertTrue(all(e.get("parent_id") and e.get("source_game_id") for e in ev))

    def test_raw_sidecar_normalizes_child_to_parent_pov(self):
        parent = "W:W31,32:B1,2"
        child_draw = "B:W26,32:B1,2"
        child_loss_for_parent = "B:W27,31:B1,2"
        pkey, _ = PM.fen_key_and_pieces(parent)
        dkey, _ = PM.fen_key_and_pieces(child_draw)
        lkey, _ = PM.fen_key_and_pieces(child_loss_for_parent)
        rows = [{
            "source_game_id": "g1",
            "fens": [parent, child_draw, child_loss_for_parent],
            "moves": ["31-26", "1-6"],
            "trajectory_hash": "t",
        }]
        # child STM DRAW=0; next child STM WIN=+1 => parent actor LOSS.
        annotated = PM.annotate_raw_trajectories(rows, {pkey: 1, dkey: 0, lkey: 1})
        self.assertEqual([row["played_child_oracle"] for row in annotated], ["DRAW"])

        rows[0]["fens"] = [parent, child_loss_for_parent]
        rows[0]["moves"] = ["31-27"]
        annotated = PM.annotate_raw_trajectories(rows, {pkey: 1, lkey: 1})
        self.assertEqual(annotated[0]["played_child_oracle"], "LOSS")

    def test_oracle_jnnw_map_is_fail_closed_on_conflict(self):
        fen = "W:W31,32:B1,2"
        key, _ = PM.fen_key_and_pieces(fen)
        def rec(wdl):
            return key + struct.pack("<i", 0) + struct.pack("<b", wdl)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "deep.jnnw"
            path.write_bytes(b"JNNW" + struct.pack("<I", 2) + rec(1) + rec(0))
            with self.assertRaises(ValueError):
                PM.oracle_label_map(path)


if __name__ == "__main__":
    unittest.main()
