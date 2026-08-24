#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import struct
import tempfile
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "l3_rgsc_trajectory_archive.py"
spec = importlib.util.spec_from_file_location("rgsc", MODULE)
rgsc = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(rgsc)


def write_pair(root: Path, games: list[dict]) -> tuple[Path, Path]:
    data = root / "source.jnnw"
    meta = root / "source.jsm2"
    drows: list[bytes] = []
    mrows: list[bytes] = []
    index = 0
    for game in games:
        rows = game["rows"]
        game_plies = max(row[0] for row in rows) + 2
        for ply, score, stm, state_seed in rows:
            # Distinct legal-looking bitboards are enough for the archive tool;
            # move legality belongs to the generator, not this offline parser.
            wm = 1 << (state_seed % 20)
            wk = 0
            bm = 1 << (20 + state_seed % 20)
            bk = 0
            wdl = game["result"] if stm == 0 else -game["result"]
            drows.append(rgsc.JNNW.pack(wm, wk, bm, bk, stm, score, wdl))
            mrows.append(rgsc.JSM2.pack(
                game["id"], game["id"], 0, ply, game_plies, 0xFFFF,
                game["result"], game.get("flags", 0)))
            index += 1
    data.write_bytes(b"JNNW" + struct.pack("<I", len(drows)) + b"".join(drows))
    meta.write_bytes(b"JSM2" + struct.pack("<I", len(mrows)) + b"".join(mrows))
    return data, meta


def outputs(root: Path) -> dict[str, str]:
    return {
        "regret_buffer_out": str(root / "regret.jnnw"),
        "random_buffer_out": str(root / "random.jnnw"),
        "normal_seed_out": str(root / "normal-seeds.jnnw"),
        "random_seed_out": str(root / "random-seeds.jnnw"),
        "regret_seed_out": str(root / "regret-seeds.jnnw"),
        "report": str(root / "report.json"),
    }


def args_for(data: Path, meta: Path, root: Path, buffer_size: int = 2):
    import argparse
    return argparse.Namespace(
        data=str(data), meta=str(meta), buffer_size=buffer_size,
        seed_table_size=20, value_scale=200.0, temperature=0.1,
        restart_fraction=0.5, random_seed=2026082401, **outputs(root))


def read_seed_records(path: Path):
    raw = path.read_bytes()
    n = struct.unpack_from("<I", raw, 4)[0]
    return [rgsc.JNNW.unpack(raw[8+i*rgsc.JNNW.size:8+(i+1)*rgsc.JNNW.size]) for i in range(n)]


def test_white_pov_value_mapping() -> None:
    base = dict(index=0, game_id=1, opening_id=1, seeded=0, ply=0,
                game_plies=2, game_result=1, flags=0, wm=1, wk=0, bm=2, bk=0, wdl=1)
    white = rgsc.Row(stm=0, score=400, **base)
    black = rgsc.Row(stm=1, score=-400, **base)
    expected = math.tanh(1.0)
    assert abs(rgsc.value_white(white, 200.0) - expected) < 1e-12
    assert abs(rgsc.value_white(black, 200.0) - expected) < 1e-12


def test_selects_max_suffix_regret_and_zeroes_seed_targets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data, meta = write_pair(root, [
            {"id": 1, "result": 1, "rows": [(0, 600, 0, 1), (4, -600, 0, 2), (8, 600, 0, 3)]},
            {"id": 2, "result": -1, "rows": [(0, 500, 0, 4), (4, -500, 0, 5)]},
            {"id": 3, "result": 0, "rows": [(0, 0, 0, 6), (4, 300, 0, 7)]},
        ])
        report = rgsc.run(args_for(data, meta, root, buffer_size=2))
        assert report["schema"] == "jass.l3_rgsc_trajectory_archive.v1"
        assert report["source_games"]["eligible_games"] == 3
        regret_rows = read_seed_records(root / "regret.jnnw")
        # The deliberately wrong middle state of game 1 must survive into the
        # top-regret buffer, and every output old target is scrubbed.
        fps = []
        for wm, wk, bm, bk, stm, score, wdl in regret_rows:
            assert score == 0 and wdl == 0
            fps.append((wm, wk, bm, bk, stm))
        bad = (1 << 2, 0, 1 << 22, 0, 0)
        assert bad in fps


def test_excludes_plycap_and_adjudicated_games() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data, meta = write_pair(root, [
            {"id": 1, "result": 1, "rows": [(0, 0, 0, 1), (4, 0, 0, 2)]},
            {"id": 2, "result": 0, "flags": rgsc.PLYCAP, "rows": [(0, 0, 0, 3), (4, 0, 0, 4)]},
            {"id": 3, "result": 1, "flags": rgsc.ADJUDICATED, "rows": [(0, 0, 0, 5), (4, 0, 0, 6)]},
            {"id": 4, "result": -1, "rows": [(0, 0, 0, 7), (4, 0, 0, 8)]},
        ])
        report = rgsc.run(args_for(data, meta, root, buffer_size=2))
        assert report["source_games"]["eligible_games"] == 2
        assert report["source_games"]["excluded"]["plycap_games"] == 1
        assert report["source_games"]["excluded"]["adjudicated_games"] == 1


def test_random_and_regret_share_exact_normal_seed_prefix() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        games = []
        for gid in range(1, 7):
            # Every game has a distinct ply-0 state and later state.
            games.append({"id": gid, "result": 1 if gid % 2 else -1,
                          "rows": [(0, gid * 30, 0, gid),
                                   (4, (-1 if gid % 2 else 1) * 500, 0, gid + 20)]})
        data, meta = write_pair(root, games)
        report = rgsc.run(args_for(data, meta, root, buffer_size=4))
        random_raw = (root / "random-seeds.jnnw").read_bytes()[8:]
        regret_raw = (root / "regret-seeds.jnnw").read_bytes()[8:]
        prefix_bytes = report["restart_sampling"]["normal_entries"] * rgsc.JNNW.size
        assert random_raw[:prefix_bytes] == regret_raw[:prefix_bytes]
        assert random_raw[prefix_bytes:] != regret_raw[prefix_bytes:]
        assert report["restart_sampling"]["restart_fraction"] == 0.5


def test_rejects_jsm1_and_insufficient_unique_games() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data, meta = write_pair(root, [
            {"id": 1, "result": 1, "rows": [(0, 0, 0, 1), (4, 0, 0, 2)]},
        ])
        bad = root / "bad.jsm"
        bad.write_bytes(b"JSM1" + meta.read_bytes()[4:])
        try:
            rgsc.read_rows(data, bad)
        except ValueError as exc:
            assert "JSM2" in str(exc)
        else:
            raise AssertionError("JSM1 source was accepted")
        try:
            rgsc.run(args_for(data, meta, root / "other", buffer_size=2))
        except ValueError as exc:
            assert "regret candidates" in str(exc)
        else:
            raise AssertionError("undersized archive was accepted")


if __name__ == "__main__":
    test_white_pov_value_mapping()
    test_selects_max_suffix_regret_and_zeroes_seed_targets()
    test_excludes_plycap_and_adjudicated_games()
    test_random_and_regret_share_exact_normal_seed_prefix()
    test_rejects_jsm1_and_insufficient_unique_games()
    print("ok")
