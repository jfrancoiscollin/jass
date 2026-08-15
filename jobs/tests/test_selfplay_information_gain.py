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


def test_cli_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows_a = [(1, 0, 2, 0, 0, 0, -1), (4, 0, 8, 0, 1, 0, 0)]
        rows_b = [(16, 0, 32, 0, 0, 0, 1), (64, 0, 128, 0, 1, 0, 1)]
        a = root / "a.jnnw"
        b = root / "b.jnnw"
        out = root / "report.json"
        write_jnnw(a, rows_a)
        write_jnnw(b, rows_b)
        rc = ig.main([
            "--corpus", f"a={a}",
            "--corpus", f"b={b}",
            "--sample-per-corpus", "0",
            "--out", str(out),
        ])
        assert rc == 0
        report = json.loads(out.read_text())
        assert report["schema"] == "jass.selfplay_information_gain.v1"
        assert report["summary"]["corpus_count"] == 2
        assert report["summary"]["diversity_screen_pass"] is True


if __name__ == "__main__":
    test_js_identity_and_separation()
    test_greedy_prefers_novel_corpus()
    test_cli_report()
    print("ok")
