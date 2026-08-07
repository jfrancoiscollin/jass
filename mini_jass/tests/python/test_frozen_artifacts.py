from __future__ import annotations

import json
from pathlib import Path


def test_frozen_m3_artifacts_are_internally_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    split = json.loads((root / "artefacts/split_manifest.v1.json").read_text(encoding="utf-8"))
    baseline = json.loads((root / "artefacts/m3_baseline.v1.json").read_text(encoding="utf-8"))
    assert split["schema"] == "mini_jass.split_manifest.v1"
    assert split["canonical_state_count"] == 218305
    assert split["raw_state_count"] == 263829
    assert baseline["split_manifest_hash"] == split["manifest_hash"]
    assert baseline["split_assignment_hash"] == split["assignment_hash"]
    assert baseline["model"]["parameter_count"] == 5225
    assert baseline["exact_supervised"]["gate"] == "PASS"
    assert baseline["all_state_fit"]["gate"] == "PASS"
    assert baseline["all_state_fit"]["failed_runs"][0]["gate"] == "FAIL"
