#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "selfplay_information_gain.py"
spec = importlib.util.spec_from_file_location("ig", MODULE_PATH)
ig = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ig)


def write_jnnw(path: Path, rows: list[tuple[int, int, int, int, int, int, int]]) -> None:
    body = b"".join(ig.REC.pack(*row) for row in rows)
    path.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + body)


def row(seed: int) -> tuple[int, int, int, int, int, int, int]:
    return (seed & 0xFFFFFFFF, 0, (seed * 2654435761) & 0xFFFFFFFF, 0, seed % 2, 0, seed % 3 - 1)


def test_js_identity_and_separation() -> None:
    a = ig.Counter({"x": 10, "y": 10})
    assert ig.js_divergence(a, a) == 0.0
    assert 0.99 <= ig.js_divergence(ig.Counter({"x": 10}), ig.Counter({"y": 10})) <= 1.0


def test_greedy_prefers_novel_corpus() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = [(1 << i, 0, 1 << (i + 10), 0, i % 2, 0, 0) for i in range(6)]
        near = base[:5] + [(1 << 20, 0, 1 << 21, 0, 0, 0, 0)]
        far = [(1 << (25 + i), 0, 1 << (35 + i), 0, i % 2, 0, 1) for i in range(6)]
        paths = []
        for name, rows in (("zbase", base), ("near", near), ("far", far)):
            path = root / f"{name}.jnnw"
            write_jnnw(path, rows)
            paths.append((name, str(path)))
        items = [ig.describe(name, Path(path), 0) for name, path in paths]
        order = ig.greedy_order(items, 1.0)
        assert order[1]["name"] == "far"
        assert order[1]["marginal_exact_novelty"] == 1.0


def test_rank_one_reports_no_js_against_an_empty_pool() -> None:
    """Rank 1 has no pool, so its JS is undefined -- not 1.0.

    A hard-coded 1.0 would put a fabricated number in a scientific artefact, and
    it would contradict this module's own js_divergence, which returns 0.0
    against an empty counter.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths = []
        for name, offset in (("a", 0), ("b", 500)):
            path = root / f"{name}.jnnw"
            write_jnnw(path, [row(offset + i) for i in range(8)])
            paths.append((name, str(path)))
        items = [ig.describe(name, Path(path), 0) for name, path in paths]
        order = ig.greedy_order(items, 0.7)
        assert order[0]["state_js_vs_pool_bits"] is None
        assert order[0]["marginal_exact_novelty"] == 1.0
        assert order[1]["state_js_vs_pool_bits"] is not None


def test_shards_are_disjoint_and_interleaved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "big.jnnw"
        write_jnnw(path, [row(i) for i in range(60)])
        shards = [ig.deterministic_sample(path, 0, shard=i, shards=3) for i in range(3)]
        assert sum(len(s) for s in shards) == 60
        seen: set[tuple] = set()
        for shard in shards:
            assert not (set(shard) & seen)
            seen |= set(shard)
        # Interleaved, not contiguous: no shard is a single block of the file.
        assert shards[0][0] != shards[0][1]


def test_sampling_is_deterministic_and_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "big.jnnw"
        write_jnnw(path, [row(i) for i in range(200)])
        first = ig.deterministic_sample(path, 40)
        second = ig.deterministic_sample(path, 40)
        assert first == second
        assert len(first) == 40


def test_cli_refuses_a_verdict_without_a_null_control() -> None:
    """Fail-closed: an absolute novelty level passes under H0 just as readily."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b, out = root / "a.jnnw", root / "b.jnnw", root / "report.json"
        write_jnnw(a, [row(i) for i in range(20)])
        write_jnnw(b, [row(1000 + i) for i in range(20)])
        rc = ig.main(["--corpus", f"a={a}", "--corpus", f"b={b}",
                      "--sample-per-corpus", "0", "--out", str(out)])
        assert rc == 0
        report = json.loads(out.read_text())
        assert report["schema"] == "jass.selfplay_information_gain.v2"
        assert report["summary"]["corpus_count"] == 2
        assert report["null_screen"] is None
        assert report["summary"]["diversity_screen_pass"] is None
        assert report["summary"]["novelty_excess_over_null"] is None
        assert "no --null-split" in report["summary"]["diversity_screen_reason"]


def test_null_split_makes_the_gate_fail_when_corpora_are_no_better_than_a_resample() -> None:
    """The decisive case, and the one an absolute threshold gets wrong.

    Both "independent" corpora are disjoint slices of the same population, so
    they are exactly as novel to each other as two shards of one corpus. Marginal
    novelty is high in absolute terms -- and the excess over the null is nil, so
    the screen must FAIL.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b, pool, out = (root / "a.jnnw", root / "b.jnnw",
                           root / "pool.jnnw", root / "report.json")
        write_jnnw(a, [row(i) for i in range(0, 60)])
        write_jnnw(b, [row(i) for i in range(60, 120)])
        write_jnnw(pool, [row(i) for i in range(200, 440)])
        rc = ig.main(["--corpus", f"a={a}", "--corpus", f"b={b}",
                      "--null-split", f"pool={pool}",
                      "--sample-per-corpus", "60", "--out", str(out)])
        assert rc == 0
        report = json.loads(out.read_text())
        summary = report["summary"]
        assert summary["final_marginal_exact_novelty"] == 1.0
        assert report["null_screen"]["shards"] == 2
        assert report["null_screen"]["records_per_shard"] == 60
        assert summary["null_final_marginal_exact_novelty"] == 1.0
        assert summary["novelty_excess_over_null"] == 0.0
        # High absolute novelty, zero excess: the old absolute gate said PASS.
        assert summary["diversity_screen_pass"] is False


def test_null_split_lets_the_gate_pass_when_the_pool_really_is_more_diverse() -> None:
    """The gate must be able to say yes, or it is a rubber stamp the other way.

    The null corpus draws from a NARROW population, so its shards overlap and its
    marginal novelty is well under 1. The two real corpora are drawn from wide
    disjoint populations, so they clear it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b, pool, out = (root / "a.jnnw", root / "b.jnnw",
                           root / "pool.jnnw", root / "report.json")
        write_jnnw(a, [row(i) for i in range(0, 60)])
        write_jnnw(b, [row(1000 + i) for i in range(60)])
        # 120 records over only 12 distinct positions: shards overlap heavily.
        write_jnnw(pool, [row(9000 + (i % 12)) for i in range(120)])
        rc = ig.main(["--corpus", f"a={a}", "--corpus", f"b={b}",
                      "--null-split", f"pool={pool}",
                      "--sample-per-corpus", "60", "--out", str(out)])
        assert rc == 0
        summary = json.loads(out.read_text())["summary"]
        assert summary["null_final_marginal_exact_novelty"] < 1.0
        assert summary["novelty_excess_over_null"] > 0.0
        assert summary["diversity_screen_pass"] is True


def test_null_split_refuses_a_control_smaller_than_the_real_corpora() -> None:
    """Marginal novelty is not scale-free, so a thinner null would flatter the pool."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b, pool, out = (root / "a.jnnw", root / "b.jnnw",
                           root / "pool.jnnw", root / "report.json")
        write_jnnw(a, [row(i) for i in range(40)])
        write_jnnw(b, [row(100 + i) for i in range(40)])
        write_jnnw(pool, [row(300 + i) for i in range(50)])
        try:
            ig.main(["--corpus", f"a={a}", "--corpus", f"b={b}",
                     "--null-split", f"pool={pool}",
                     "--sample-per-corpus", "40", "--out", str(out)])
        except SystemExit as exc:
            assert "disjoint shards" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("undersized null control was accepted")


if __name__ == "__main__":
    test_js_identity_and_separation()
    test_greedy_prefers_novel_corpus()
    test_rank_one_reports_no_js_against_an_empty_pool()
    test_shards_are_disjoint_and_interleaved()
    test_sampling_is_deterministic_and_bounded()
    test_cli_refuses_a_verdict_without_a_null_control()
    test_null_split_makes_the_gate_fail_when_corpora_are_no_better_than_a_resample()
    test_null_split_lets_the_gate_pass_when_the_pool_really_is_more_diverse()
    test_null_split_refuses_a_control_smaller_than_the_real_corpora()
    print("ok")
