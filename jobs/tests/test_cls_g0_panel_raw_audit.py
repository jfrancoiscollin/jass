"""Synthetic unit/integration tests; no historical outcomes or new native searches."""
from __future__ import annotations
from copy import deepcopy
import csv
import gzip
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from jobs.tools import cls_g0_panel_raw_audit as a
from jobs.tools import cls_g0_panel_audit_stage as stage
from jobs.tools.launch_runtime_v2 import StageEvidence


def load_tests(loader, tests, pattern):
    """Existing panel-audit CI also exercises the new readiness contract."""
    from jobs.tests import (test_cls_g0_panel_readiness, test_cls_g0_panel_gate_v1,
                           test_cls_g0_panel_stage, test_cls_g0_panel_pipeline)
    for module in (test_cls_g0_panel_readiness, test_cls_g0_panel_gate_v1, test_cls_g0_panel_stage, test_cls_g0_panel_pipeline):
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


def q(side, move="31-26", wall=.07):
    return {"side": side, "move": move, "wall_seconds": wall,
            "nodes": 12, "depth": 1, "eval_calls": 9}


def game(opening="W:W32:B27", white=True, cap=False):
    side, whites, _, blacks, _ = a.fen_state(opening)
    x, y = whites[0], blacks[0]
    fens, moves, requests = [opening], [], []
    if cap:
        # Structurally complete synthetic trajectories. The injected oracle is
        # explicitly a fixture; these paths do not claim native move legality.
        for i in range(160):
            stm = "W" if i % 2 == 0 else "B"
            old = x if stm == "W" else y
            if stm == "W":
                x = 30 + (x - 30 + 1) % 20
            else:
                y = 1 + (y - 1 + 1) % 19
            move = f"{old}-{x if stm == 'W' else y}"
            requests.append(q("A" if ((stm == "W") == white) else "B", move))
            moves.append(move)
            fens.append(f"{'B' if stm == 'W' else 'W'}:W{x}:B{y}")
        outcome, reason = "D", "ply cap"
    else:
        requests = [q("A" if white else "B", f"{x}x{x} captures={y}"),
                    q("B" if white else "A", "0-0")]
        moves = [f"{x}x{x}"]
        fens.append(f"B:W{x}:B")
        outcome = "W"
        reason = "no legal move from " + ("B" if white else "A")
    return {"opening": opening, "a_is_white": white, "plies": len(moves),
            "fens": fens, "moves": moves, "requests": requests,
            "warmup_requests": [q("A"), q("B")], "game_wall_seconds": 12.0,
            "outcome": outcome, "reason": reason,
            "score_a": .5 if cap else float(white)}


def fixture():
    openings = [f"W:W{x}:B{y}" for x in range(30, 50) for y in range(1, 21)][:296]
    rs = [{"fen": f, "canonical": a.canonical_identity(f)} for f in openings]
    seal = {"main": rs[:288], "representative": rs[288:], "pool_seed": 2026092007,
            "order_seed": 2026092008, "score_reads_for_selection": 0}
    seal["selection_sha256"] = a.digest(seal)
    pairs = [{"task_id": f"pair-{i:04d}-HIER", "opening": row["fen"],
              "arm_a": "HIER", "arm_b": "CURRICULUM",
              "games": [game(row["fen"], w, cap=i < 5) for w in (True, False)]}
             for i, row in enumerate(rs[:288])]
    bounds = [(0., 1.) if i < 5 else (.5, .5) for i in range(288)]
    summary = {"models": {k: a.MODELS[k] for k in ("CURRICULUM", "HIER")},
               "opening_selection_sha256": seal["selection_sha256"],
               **a.independent_interval(bounds, .05), "pairs": 288, "games": 576,
               "administratively_censored_games": 10,
               "descriptive_half_point_ply_cap_score": .5,
               "descriptive_pentanomial_counts": {"1.0": 288},
               "actual_side_effects": {"new_jass_searches": sum(len(g["requests"]) + 2 for p in pairs for g in p["games"])}}
    return {"mode": "production", "pairs": pairs}, seal, summary


def oracle(games, metas):
    return [2 if g["reason"] == "ply cap" else 0 for g in games]


class RawAuditTests(unittest.TestCase):
    def test_exact_capture_identity(self):
        self.assertEqual(a.exact_move("32x21 captures=27"), (32, 21, (27,)))
        for bad in ("32x21", "32-21 captures=27", "32x21 captures=27,27", "0-0", "32-21\ngo depth 2"):
            with self.subTest(bad=bad), self.assertRaises(a.AuditError):
                a.exact_move(bad)

    def test_fen_and_symmetry(self):
        self.assertEqual(a.fen_state("W:W31-32,K33:B1,K2"), ("W", (31,32), (33,), (1,), (2,)))
        self.assertEqual(a.canonical_identity("W:W32:B27"), a.canonical_identity("B:W24:B19"))
        for bad in ("W:W32:B32", "W:W51:B1", "W:W1,,2:B3", "W:W32:B27\nquit"):
            with self.assertRaises(a.AuditError):
                a.fen_state(bad)

    def test_duplicate_nonfinite_json(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'):
            with self.assertRaises(a.AuditError):
                a.decode(raw)

    def test_gzip_size_bound(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/"data.gz"
            path.write_bytes(gzip.compress(b'{"x":"'+b'a'*1000+b'"}'))
            with self.assertRaises(a.AuditError):
                a.read(path, expanded_limit=32)

    def test_raw_model_sha_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t)/"m.gz", Path(t)/"m"
            src.write_bytes(gzip.compress(b"model"))
            expected = __import__("hashlib").sha256(b"model").hexdigest()
            self.assertEqual(a.unpack_model(src,dst,expected)["raw_bytes"], 5)
            with self.assertRaises(a.AuditError):
                a.unpack_model(src,dst,expected)

    def test_model_wrong_sha_fails(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t)/"m.gz", Path(t)/"m"
            src.write_bytes(gzip.compress(b"model"))
            with self.assertRaises(a.AuditError):
                a.unpack_model(src,dst,"0"*64)

    def test_colour_and_terminal(self):
        for white in (True, False):
            g = game(white=white)
            m = a.inspect_game(g)
            a.check_terminal(g,m,0)
            with self.assertRaises(a.AuditError):
                a.check_terminal(g,m,1)

    def test_null_request_not_legal_loss(self):
        g = game()
        m = a.inspect_game(g)
        with self.assertRaises(a.AuditError):
            a.check_terminal(g,m,3)

    def test_wrong_capture_log_rejected(self):
        g = game()
        g["moves"][0] = "32x21"
        with self.assertRaises(a.AuditError):
            a.inspect_game(g)

    def test_colour_request_order_rejected(self):
        g = game()
        g["requests"][0]["side"] = "B"
        with self.assertRaises(a.AuditError):
            a.inspect_game(g)

    def test_cadence_warmup_separate(self):
        g = game()
        g["warmup_requests"][0]["wall_seconds"] = 2.0
        a.inspect_game(g)
        g["requests"][0]["wall_seconds"] = .120001
        with self.assertRaises(a.AuditError):
            a.inspect_game(g)

    def test_missing_telemetry_rejected(self):
        g = game()
        del g["requests"][0]["nodes"]
        with self.assertRaises(a.AuditError):
            a.inspect_game(g)

    def test_cap_cannot_be_early_or_loss(self):
        g = game()
        g.update(reason="ply cap",outcome="D",score_a=.5)
        g["requests"] = g["requests"][:1]
        with self.assertRaises(a.AuditError):
            a.check_terminal(g,a.inspect_game(g),1)

    def test_draw_repetition_continuation_rejected(self):
        g = game("W:W32:B12", cap=True)
        g["fens"][3] = g["fens"][1]
        # Early board origin/clock mismatch or eventual duplicate is fail-closed.
        g["fens"][5] = g["fens"][1]
        with self.assertRaises(a.AuditError):
            a.inspect_game(g)

    def test_nonfinite_wall_rejected(self):
        for value in (float('nan'), float('inf'), -1, 0):
            bad = q("A",wall=value)
            with self.assertRaises(a.AuditError):
                a.check_telemetry(bad)

    def test_original_interval_not_panel_alpha(self):
        result = a.independent_interval([(.5,.5)]*288,.05)
        self.assertAlmostEqual(result["hoeffding_radius"], .08002689927666005)
        self.assertEqual(result["statistical_verdict"], "SUBSTANTIAL_LOSS_EXCLUDED")
        self.assertEqual(a.independent_interval([(0,0)]*288,.05)["statistical_verdict"], "SUBSTANTIAL_LOSS_SUPPORTED")
        self.assertEqual(a.independent_interval([(0,1)]*288,.05)["statistical_verdict"], "INDETERMINATE")

    def test_complete_fixed_n_only(self):
        for n in (0,287,289):
            with self.assertRaises(a.AuditError):
                a.independent_interval([(.5,.5)]*n,.05)

    def test_whole_raw_fixture_roundtrip(self):
        raw,seal,s = fixture()
        result = a.audit_match(raw,seal,s,oracle)
        self.assertTrue(result["passed"])
        self.assertEqual(result["recomputed_original_readout"]["administratively_censored_games"],10)
        self.assertEqual(result["new_engine_searches"],0)

    def test_native_replay_required(self):
        raw,seal,s = fixture()
        with self.assertRaises(a.AuditError):
            a.audit_match(raw,seal,s,lambda games,metas: [])

    def test_missing_pair_and_order_rejected(self):
        raw,seal,s = fixture()
        raw["pairs"][0],raw["pairs"][1] = raw["pairs"][1],raw["pairs"][0]
        with self.assertRaises(a.AuditError):
            a.audit_match(raw,seal,s,oracle)
        raw["pairs"].pop()
        with self.assertRaises(a.AuditError):
            a.audit_match(raw,seal,s,oracle)

    def test_tampered_summary_rejected(self):
        raw,seal,s = fixture()
        s["score_interval"][0] += .01
        with self.assertRaises(a.AuditError):
            a.audit_match(raw,seal,s,oracle)

    def test_tampered_seal_rejected(self):
        raw,seal,s = fixture()
        seal["main"][0]["fen"] = "W:W32:B27"
        with self.assertRaises(a.AuditError):
            a.audit_match(raw,seal,s,oracle)

    def test_never_reuses_historical_analyzer(self):
        source = Path(a.__file__).read_text()
        self.assertNotIn("analyze_main(", source)
        self.assertNotIn("from jobs.tools.cls_g0_strength_main", source)


class G0Tests(unittest.TestCase):
    def inputs(self):
        roots = [str(i) for i in range(512)]
        rows, phases = [], []
        for i,r in enumerate(roots):
            phases.append({"parent_id":r,"phase":f"P{i//128}","canonical_fingerprint":f"fp{i}"})
            for role in ("parent","candidate"):
                depth = 8 if role == "candidate" and i < 28 else 10
                receipt = "" if role == "candidate" and i < 56 else "150000"
                rows.append({"root_id":r,"arm":role,"completed_nominal_depth":str(depth),
                    "target_depth":"9","nodes_observed":"200000","wall_us":"50000","nps":"4000000",
                    "trace_attempts":"10","bestmove_canonical":"32-28","nodes_to_target":receipt})
        probe = {"parent_nodes_to_depth_missing_roots":[],"candidate_nodes_to_depth_missing_roots":roots[:56],
            "budget_nodes":200000,"roots":512,"trace_parity_mismatches":0,"nodes_to_depth_surrogate_used":False}
        summary = {"candidate_arm":"LOCAL","candidate_sha256":a.MODELS["LOCAL"],
            "direct_parent_sha256":a.MODELS["CURRICULUM"],"terminal":a.G0_FAIL}
        return rows,roots,phases,probe,summary

    def test_all_roots_and_two_missing_mechanisms(self):
        rows,desc = a.g0_rows("LOCAL",*self.inputs())
        self.assertEqual(len(rows),512)
        self.assertEqual(desc["categories"]["profondeur_cible_non_atteinte"],28)
        self.assertEqual(desc["categories"]["profondeur_atteinte_sans_recu_exact"],28)
        self.assertEqual(desc["imputed_receipts"],0)

    def test_incomplete_g0_fails(self):
        args = self.inputs()
        args[0].pop()
        with self.assertRaises(a.AuditError):
            a.g0_rows("LOCAL",*args)

    def test_invalid_receipt_not_surrogated(self):
        args = self.inputs()
        args[0][0]["nodes_to_target"] = "200001"
        with self.assertRaises(a.AuditError):
            a.g0_rows("LOCAL",*args)

    def test_g0_source_drift(self):
        args = self.inputs()
        args[-1]["candidate_sha256"] = a.MODELS["WDL"]
        with self.assertRaises(a.AuditError):
            a.g0_rows("LOCAL",*args)


class StageTests(unittest.TestCase):
    def test_subprocess_timeout_and_nonzero(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(subprocess.TimeoutExpired):
                stage.command(["/usr/bin/python3","-c","import time; time.sleep(10)"],Path(t)/"timeout.log",1)
            with self.assertRaises(a.AuditError):
                stage.command(["/usr/bin/python3","-c","raise SystemExit(3)"],Path(t)/"fail.log",2)

    def test_no_clobber(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"o.json"
            stage.put(p,{"ok":True})
            with self.assertRaises(a.AuditError):
                stage.put(p,{"ok":False})
            stage.put(p,{"ok":False},replace=True)
            self.assertFalse(a.read(p)["ok"])

    def test_search_environment_sanitized(self):
        with patch.dict("os.environ",{"JASS_T3_F6_MODEL":"evil", "JASS_EGDB_PATH":"other"}):
            self.assertFalse(any(k.startswith("JASS_") for k in stage.env()))

    def test_native_batch_contains_no_search_command(self):
        g=game()
        meta=a.inspect_game(g)
        with tempfile.TemporaryDirectory() as t:
            def call(argv,log,timeout,stdin=None):
                if "--perft" in argv:
                    self.assertEqual(argv[1:3],["--perft","1"])
                    return b"perft(1) = 0\n"
                self.assertNotIn(b"go ",stdin)
                return ("ready\nok\nfen "+g["opening"]+"\nok\nfen "+g["fens"][-1]+"\n").encode()
            with patch.object(stage,"command",side_effect=call):
                self.assertEqual(stage.replay_native(Path("jass"),Path(t),[g],[meta],lambda _:None),[0])

    def test_native_wrong_trajectory_fails(self):
        g=game()
        with tempfile.TemporaryDirectory() as t, patch.object(stage,"command",return_value=b"ready\nerror illegal move\n"):
            with self.assertRaises(a.AuditError):
                stage.replay_native(Path("jass"),Path(t),[g],[a.inspect_game(g)],lambda _:None)

    def test_module_import_without_repository_adapters(self):
        self.assertEqual(stage.TERMINAL,"CLS_G0_PANEL_HISTORICAL_RAW_AUDIT_COMPLETE_V1")
        self.assertEqual(len(stage.PHASES),5)
        source=Path(stage.__file__).read_text()
        self.assertNotIn("record_effect(", source)
        self.assertNotIn("run_candidate_probe(",source)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


class PanelFinalizationTests(unittest.TestCase):
    def _sources(self, root: Path) -> dict[str, Path]:
        raw, seal, summary = fixture()
        historical = root / "historical"
        historical.mkdir()
        with gzip.open(historical / "stage-games.json.gz", "wt", encoding="utf-8") as f:
            json.dump(raw, f)
        write_json(historical / "opening-freeze.json", seal)
        write_json(historical / "scientific-summary.json", summary)
        write_json(historical / "study-report.json", summary)
        write_json(historical / "runtime-identity.json", {})
        out = {"historical_match": historical}
        inputs = G0Tests().inputs()
        for arm in ("LOCAL", "WDL"):
            directory = root / arm.lower()
            directory.mkdir()
            rows, roots, phases, probe, g0_summary = inputs
            with (directory / "probe.tsv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0], delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
            with (directory / "g0-deep512.tsv").open("w", encoding="utf-8") as f:
                f.write("parent_id\tphase\tcanonical_fingerprint\n")
                for phase in phases:
                    f.write(f"{phase['parent_id']}\t{phase['phase']}\t{phase['canonical_fingerprint']}\n")
            (directory / "g0-root-ids.txt").write_text("\n".join(roots) + "\n", encoding="utf-8")
            write_json(directory / "probe-report.json", probe)
            write_json(directory / "scientific-summary.json", {**g0_summary, "candidate_arm": arm,
                       "candidate_sha256": stage.audit.MODELS[arm]})
            write_json(directory / "candidate-authentication.json", {
                "model_sha256": stage.audit.MODELS[arm], "job_id": "synthetic"})
            out["local_g0" if arm == "LOCAL" else "wdl_g0"] = directory
        return out

    def test_stage_run_replaces_only_owned_progress_and_hashes_final_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            art, work = root / "art", root / "work"
            art.mkdir()
            sources = self._sources(root)
            evidence = StageEvidence(art, "rehearsal")
            with patch.object(stage, "authenticate", return_value=(sources, {})), \
                 patch.object(stage, "continuity", return_value=(Path("jass"), {"passed": True})), \
                 patch.object(stage, "replay_native", side_effect=lambda _exe, _work, games, metas, _progress: oracle(games, metas)):
                result = stage.run(work, art, evidence, {"sources": {
                        "valid_arms": {"job_id": "synthetic"}, "historical_match": {"job_id": "synthetic"}}})
                self.assertEqual(result["terminal"], stage.TERMINAL)
                evidence_value = json.loads((art / "execution-evidence.json").read_text())
                self.assertEqual(evidence_value["state"], "completed")
                self.assertEqual(evidence_value["completed_phases"], stage.PHASES)
                self.assertTrue(all(value == 0 for value in evidence_value["actual_side_effects"].values()))
                published = json.loads((art / "scientific-summary.json").read_text())
                self.assertEqual(published["schema"], "jass.cls_g0_panel_historical_audit.v1")
                manifest = json.loads((art / "manifest.json").read_text())
                for name in stage.OUTPUTS:
                    self.assertTrue((art / name).is_file(), name)
                    self.assertGreater((art / name).stat().st_size, 0, name)
                for name, expected_hash in manifest["output_sha256"].items():
                    self.assertEqual(expected_hash, stage.audit.sha(art / name), name)
                self.assertEqual(set(manifest["output_sha256"]), set(stage.OUTPUTS) - {"manifest.json"})

    def test_finalized_or_foreign_summary_collision_remains_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            art = Path(temporary)
            evidence = StageEvidence(art, "rehearsal")
            path = art / "scientific-summary.json"
            path.write_text(json.dumps({"schema": "jass.cls_g0_panel_historical_audit.v1", "state": "completed"}), encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises(stage.audit.AuditError):
                stage.put_final_summary(path, {"schema": "replacement"}, evidence)
            self.assertEqual(path.read_bytes(), before)

    def test_progress_ownership_rejects_stale_or_foreign_placeholders(self):
        with tempfile.TemporaryDirectory() as temporary:
            art = Path(temporary)
            evidence = StageEvidence(art, "rehearsal")
            for phase in stage.PHASES:
                evidence.begin(phase)
                if phase != stage.PHASES[-1]:
                    evidence.complete()
            path = art / "scientific-summary.json"
            baseline = json.loads(path.read_text())
            final_value = {"schema": "final"}
            cases = {
                "stale snapshot": {"snapshot_at": "stale"},
                "mismatched phase": {"phase": "foreign"},
                "mismatched effects": {"actual_side_effects": {"fits": 1}},
                "unexpected field": {"foreign": True},
            }
            for label, mutation in cases.items():
                with self.subTest(label=label):
                    candidate = dict(baseline)
                    candidate.update(mutation)
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    before = path.read_bytes()
                    with self.assertRaises(stage.audit.AuditError):
                        stage.put_final_summary(path, final_value, evidence)
                    self.assertEqual(path.read_bytes(), before)
            wrong_path = art / "wrong-summary.json"
            wrong_path.write_text(json.dumps(baseline), encoding="utf-8")
            before = wrong_path.read_bytes()
            with self.assertRaises(stage.audit.AuditError):
                stage.put_final_summary(wrong_path, final_value, evidence)
            self.assertEqual(wrong_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
