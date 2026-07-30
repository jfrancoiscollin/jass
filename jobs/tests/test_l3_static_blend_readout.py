#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_static_blend_readout.py"

CODE = "a" * 40
CHAMPION = "b" * 64
REVERSE = "c" * 64
BLEND = "d" * 64


def force(path: Path, wins: int, draws: int, losses: int) -> None:
    path.write_text(
        json.dumps(
            {
                "complete": True,
                "n": wins + draws + losses,
                "wins_a": wins,
                "draws": draws,
                "wins_b": losses,
                "rate": (wins + 0.5 * draws) / (wins + draws + losses),
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fdir = root / "force"
        fdir.mkdir()
        force(fdir / "force-q00-BLEND50-vs-TURNOVER.json", 112, 8, 80)
        force(fdir / "force-native-BLEND50-vs-TURNOVER.json", 110, 10, 80)
        build = root / "build.json"
        build.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "verdict": "L3_PURE_REVERSE_SEED_BLEND50_READY",
                    "code_sha": CODE,
                    "primary_contrast":
                    "BLEND50(TURNOVER,REVERSE_SEED) minus TURNOVER",
                    "construction": {
                        "mode": "convex-weight-interpolation",
                        "single_factor": "static_pjtw_weight_blend",
                        "alpha_champion": 0.5,
                        "alpha_reverse_seed": 0.5,
                        "training_records": 0,
                        "self_play_games": 0,
                    },
                    "models": {
                        "champion_sha256": CHAMPION,
                        "reverse_seed_sha256": REVERSE,
                        "blend_sha256": BLEND,
                    },
                    "static_linearity_probe": {
                        "passed": True,
                        "positions": 64,
                        "max_abs_residual": 1.0,
                    },
                    "scientific_result": False,
                    "promotion_authorized": False,
                    "automatic_next_job": None,
                }
            ),
            encoding="utf-8",
        )
        openings = root / "openings.json"
        openings.write_text(
            json.dumps(
                {"records": 100, "unique_records": 100, "overlap_records": 0}
            ),
            encoding="utf-8",
        )
        out = root / "out.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "jobs.tools.l3_static_blend_readout",
                "--force-dir",
                str(fdir),
                "--build-summary",
                str(build),
                "--opening-manifest",
                str(openings),
                "--expected-games-per-view",
                "200",
                "--expected-openings",
                "100",
                "--code-sha",
                CODE,
                "--source-job",
                "cpx62-test",
                "--source-attempt",
                "attempt",
                "--source-code-sha",
                CODE,
                "--champion-model-sha",
                CHAMPION,
                "--reverse-model-sha",
                REVERSE,
                "--blend-model-sha",
                BLEND,
                "--out",
                str(out),
            ],
            check=True,
            cwd=ROOT,
        )
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["verdict"] == "L3_PURE_BLEND50_ABOVE_TURNOVER_IC95"
        assert result["force_views_summed"]["n"] == 400
        assert result["force_views_summed"]["ci95"][0] > 0.5
        assert result["promotion_authorized"] is False
        assert result["automatic_next_job"] is None
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
