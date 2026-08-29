import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from jobs.tools import residual_feature_historical_screen as hs
from jobs.tools import residual_feature_probe as rf
from jobs.tools import t3_rf1_joint_ab as t3
from jobs.tools import t3_rf1_joint_ab_build_train as build


def _cohort(name, canonical, parent_stm, phase, base, offset):
    parent = hs.Parent(0, parent_stm, phase, canonical)
    meta = [SimpleNamespace(parent_id=0, parent_stm=parent_stm) for _ in range(2)]
    features = np.arange(2 * rf.TOTAL_WIDTH, dtype=np.float64).reshape(2, rf.TOTAL_WIDTH) + offset
    return hs.Cohort(
        name=name,
        parents={0: parent},
        meta=meta,
        features=features,
        eval120=np.empty((2, 120)),
        parent_rows={0: [0, 1]},
        pairs={0: [(0, 1)]},
        d1=np.asarray([offset + 0.25, offset - 0.5]),
    ), [
        build.BaselineRow(0, 0, parent_stm, base),
        build.BaselineRow(1, 0, parent_stm, base - 1.0),
    ]


def test_source_priority_deduplicates_whole_parent_and_reloads_exactly():
    a, ba = _cohort("TRAIN_A", "same", 0, "P0", 10.0, 0.0)
    b, bb = _cohort("TRAIN_B", "same", 1, "P1", 20.0, 100.0)
    c, bc = _cohort("TRAIN_C", "new", 1, "P3", 30.0, 200.0)
    data = build.assemble_union(
        [("TRAIN_A", a), ("TRAIN_B", b), ("TRAIN_C", c)],
        {"TRAIN_A": ba, "TRAIN_B": bb, "TRAIN_C": bc},
    )
    assert data.features.shape == (4, rf.TOTAL_WIDTH)
    assert [row["parent_id"] for row in data.static_rows] == [0, 0, 1, 1]
    assert len(data.pair_rows) == 2
    assert data.receipt["sources"]["TRAIN_B"]["parents_deduplicated"] == 1
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        payload = build.write_union(data, root / "u.rffd", root / "m.tsv", root / "p.tsv", root / "r.json")
        meta = t3.load_static_meta(root / "m.tsv")
        pairs = t3.load_pairs(root / "p.tsv", meta)
        xa, xb, base = t3.build_inputs(root / "u.rffd", meta)
        assert xa.shape == (4, 66) and xb.shape == (4, 67) and base.tolist() == [10.0, 9.0, 30.0, 29.0]
        assert len(pairs) == 2 and payload["reload_exact"] is True
        assert json.loads((root / "r.json").read_text())["canonical_parent_count"] == 2


def test_rejects_source_priority_drift():
    a, ba = _cohort("TRAIN_A", "a", 0, "P0", 0.0, 0.0)
    try:
        build.assemble_union([("TRAIN_B", a)], {"TRAIN_B": ba})
    except ValueError as exc:
        assert "source priority drift" in str(exc)
    else:
        raise AssertionError("source priority drift must fail closed")
