#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/tb_frontier_catalog_mine.py"
spec = importlib.util.spec_from_file_location("tb_frontier_catalog_mine", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(cid: str, path: str, uri: str | None, disposition: str, sha: str | None = None):
    return {
        "candidate_id": cid,
        "source_class": "runner_attempt" if uri else "historical_git_snapshot",
        "data": {
            "path": path,
            "r2_uri": uri,
            "declared_sha256": sha,
            "size_bytes": 1234,
        },
        "quality": {
            "disposition": disposition,
            "risk_tags": ["external_or_teacher"] if "teacher" in path else [],
        },
    }


def main() -> int:
    sha = "a" * 64
    rows = [
        # Risk-tagged / quarantined direct payload is intentionally INCLUDED:
        # source labels are not trusted; EGDB re-labels sibling decisions exactly.
        row("teacher", "runs/x/a/artefacts/teacher.jnnw.gz", "r2:jass-data/runs/x/a/artefacts/teacher.jnnw.gz", "quarantine", sha),
        # Same payload SHA must not inflate support.
        row("teacher-copy", "runs/y/b/artefacts/copy.jnnw.gz", "r2:jass-data/runs/y/b/artefacts/copy.jnnw.gz", "quarantine", sha),
        # A clean direct payload is included.
        row("clean", "runs/z/c/artefacts/data.jnnw", "r2:jass-data/runs/z/c/artefacts/data.jnnw", "review", "b" * 64),
        # Failed/rejected data is excluded.
        row("bad", "runs/q/d/artefacts/bad.jnnw.gz", "r2:jass-data/runs/q/d/artefacts/bad.jnnw.gz", "reject", "c" * 64),
        # Historical snapshot has no direct R2 URI and belongs to predefined layer 2.
        row("snapshot", "jobs/results/old/data.jnnw.gz", None, "quarantine", None),
    ]
    selected, counts = mod.select_direct_candidates(rows)
    assert [r["candidate_id"] for r in selected] == ["teacher", "clean"]
    assert counts == {
        "catalog_rows": 5,
        "direct_rows": 4,
        "rejected_rows": 1,
        "duplicate_payload_rows": 1,
        "selected_rows": 2,
    }
    assert selected[0]["quality"]["risk_tags"] == ["external_or_teacher"]

    fp = "0011223344556:0000000000000:0000000000001:0000000000000:0"
    a = mod.split_is_holdout(fp, 2026082801, 5)
    b = mod.split_is_holdout(fp, 2026082801, 5)
    assert a == b
    # The split must depend on fingerprint rather than source/candidate provenance.
    assert mod.split_is_holdout(fp, 2026082801, 5) == mod.split_is_holdout(fp, 2026082801, 5)

    print("TB_FRONTIER_CATALOG_MINE_TESTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
