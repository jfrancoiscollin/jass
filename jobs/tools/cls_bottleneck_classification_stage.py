#!/usr/bin/env python3
"""Terminal read-only CLS-D bottleneck classification over four authenticated productions."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import cls_depth_growth_stage as base  # noqa: E402

SCHEMA = "jass.cls_bottleneck_classification.v1"
REHEARSAL_TERMINAL = "CLS_BOTTLENECK_CLASSIFICATION_REHEARSAL_READY_V1"
PRODUCTION_TERMINAL = "CLS_DIAGNOSIS_COMPLETE_V1"
TECHNICAL_TERMINAL = "CLS_BOTTLENECK_CLASSIFICATION_TECHNICAL_FAILURE_V1"
BUDGET = 200_000

SOURCES = {
    "depth": {
        "job": "cpx62-2000-l3-cls-depth-growth-full-production-v2",
        "attempt": "20260916T083204Z-7a5f44ec",
        "code": "7a5f44ec1681c2471b1815f8767b4008b11e3a54",
        "receipt": "3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42",
        "terminal": "DEPTH_GROWTH_JASS_VS_SCAN_V2_COMPLETE",
        "files": ["bootstrap.json", "bottleneck-evidence.json"],
    },
    "mirror": {
        "job": "cpx62-2008-l3-cls-mirror-scale-production-v3",
        "attempt": "20260916T161938Z-92984c1f",
        "code": "92984c1f8ac9563225f930c1c3d77b80e581e05d",
        "receipt": "2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004",
        "terminal": "CLS_MIRROR_SCALE_DIAGNOSTIC_COMPLETE_V1",
        "files": ["bootstrap.json", "mirror-evidence.json", "aggregates.json"],
    },
    "profile": {
        "job": "cpx62-2010-l3-cls-search-profile-production-v1",
        "attempt": "20260916T170101Z-bd9e7ddd",
        "code": "bd9e7ddd160bca5b08fc5803850e6c65f3070fd3",
        "receipt": "2c209ed6f618a1ca49c67f4224c2dbfaa680a53208e485b9689c7f885c184178",
        "terminal": "CLS_SEARCH_PROFILE_DIAGNOSTIC_COMPLETE_V1",
        "files": ["bootstrap.json", "search-profile.json"],
    },
    "draw": {
        "job": "cpx62-2013-l3-cls-draw-pentanomial-throughput-production-v1",
        "attempt": "20260916T194330Z-1cd72e5a",
        "code": "1cd72e5a3001a0c3944ec61db8519265048a690e",
        "receipt": "b8df0cc6f5ebf25f7e52c165e9c6b6c88e952b1d6882de5c6dd91d3c1402f450",
        "terminal": "CLS_DRAW_PENTANOMIAL_THROUGHPUT_DIAGNOSTIC_COMPLETE_V1",
        "files": ["bootstrap.json", "draw-pentanomial-throughput.json"],
    },
}


class StageError(RuntimeError):
    pass


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StageError(f"not_object:{path.name}")
    return value


def _metric(payload: dict, name: str) -> dict[str, float]:
    try:
        raw = payload["metrics"][name]
        out = {k: float(raw[k]) for k in ("q025", "median", "q975")}
    except (KeyError, TypeError, ValueError) as exc:
        raise StageError(f"missing_metric:{name}") from exc
    if not all(math.isfinite(v) for v in out.values()) or not (out["q025"] <= out["median"] <= out["q975"]):
        raise StageError(f"invalid_metric:{name}")
    return out


def classify(*, search_ci: dict[str, float], decision_ci: dict[str, float], cost_ci: dict[str, float]) -> tuple[str, list[str], str]:
    supported: list[str] = []
    if search_ci["q975"] < 0.0:
        supported.append("SEARCH")
    if decision_ci["q025"] > 0.0:
        supported.append("DECISION-EVAL")
    if cost_ci["q975"] < 0.0:
        supported.append("COST")
    if len(supported) == 1:
        return supported[0], supported, "SINGLE_SUPPORTED_AXIS"
    if len(supported) >= 2:
        return "mixed", supported, "MULTIPLE_SUPPORTED_AXES"
    return "mixed", supported, "NO_SINGLE_AXIS_ISOLATED_UNDER_FROZEN_RULE"


def authenticate_sources(work: Path, artifacts: Path) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    auth_sources = {}
    for name, spec in SOURCES.items():
        prefix = f"r2:jass-data/runs/{spec['job']}/{spec['attempt']}"
        out = work / name
        mappings = [(f"artefacts/{filename}", filename) for filename in spec["files"]]
        mappings += [("artefacts/scientific-summary.json", "scientific-summary.json"),
                     ("artefacts/launch-receipt.json", "launch-receipt.json")]
        base.fetch_completed(prefix, job=spec["job"], attempt=spec["attempt"], code=spec["code"],
                             mappings=mappings, out_dir=out, report=work / f"verified-{name}.json")
        if base.sha_file(out / "launch-receipt.json") != spec["receipt"]:
            raise StageError(f"receipt_drift:{name}")
        summary = read_json(out / "scientific-summary.json")
        required = {
            "state": "completed", "terminal": spec["terminal"], "mode": "production",
            "diagnostic_only": True, "scientific_verdict": None,
            "target_reads": 0, "fits": 0, "strength_games": 0, "alpha_spent": 0,
        }
        for key, expected in required.items():
            if summary.get(key) != expected:
                raise StageError(f"summary_drift:{name}:{key}")
        launch = summary.get("launch") or {}
        if launch.get("receipt_sha256") != spec["receipt"] or launch.get("mode") != "production" \
                or launch.get("production_admitted") is not True:
            raise StageError(f"launch_drift:{name}")
        roots[name] = out
        auth_sources[name] = {
            "job_id": spec["job"], "attempt_id": spec["attempt"], "code_sha": spec["code"],
            "receipt_sha256": spec["receipt"], "terminal": spec["terminal"],
            "files": {filename: base.sha_file(out / filename) for filename in spec["files"]},
        }
    auth = {
        "schema": "jass.cls_bottleneck_source_authentication.v1",
        "authenticated": True,
        "sources": auth_sources,
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 0, "new_scan_searches": 0, "fits": 0,
        "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0,
        "promotions": 0, "bakes": 0,
    }
    base.atomic_write(artifacts / "source-authentication.json", base.canonical_json(auth))
    return roots


def manifest_for(artifacts: Path) -> dict:
    names = ["classification.json", "source-authentication.json", "RESULTS.md", "scientific-summary.json"]
    return {"schema": "jass.cls_bottleneck_classification_manifest.v1",
            "files": {name: base.sha_file(artifacts / name) for name in names}}


def run_stage(work: Path, artifacts: Path) -> dict:
    mode = os.environ.get("LAUNCH_MODE", "")
    if mode not in {"rehearsal", "production"}:
        raise StageError("LAUNCH_MODE must be rehearsal or production")
    work.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    roots = authenticate_sources(work, artifacts)

    profile_boot = read_json(roots["profile"] / "bootstrap.json")
    mirror_boot = read_json(roots["mirror"] / "bootstrap.json")
    draw = read_json(roots["draw"] / "draw-pentanomial-throughput.json")
    search_ci = _metric(profile_boot, f"completed_depth_delta_jass_scan_{BUDGET}")
    cost_ci = _metric(profile_boot, f"log_nps_ratio_jass_scan_{BUDGET}")
    decision_ci = _metric(mirror_boot, f"mirror_excess_{BUDGET}")
    classification, supported, reason = classify(search_ci=search_ci, decision_ci=decision_ci, cost_ci=cost_ci)

    payload = {
        "schema": SCHEMA,
        "classification": classification,
        "classification_reason": reason,
        "supported_axes": supported,
        "frozen_budget_nodes": BUDGET,
        "evidence": {
            "SEARCH": {"metric": f"completed_depth_delta_jass_scan_{BUDGET}", "ci95": search_ci,
                       "supported": "SEARCH" in supported, "rule": "q975 < 0"},
            "DECISION-EVAL": {"metric": f"mirror_excess_{BUDGET}", "ci95": decision_ci,
                              "supported": "DECISION-EVAL" in supported, "rule": "q025 > 0"},
            "COST": {"metric": f"log_nps_ratio_jass_scan_{BUDGET}", "ci95": cost_ci,
                     "supported": "COST" in supported, "rule": "q975 < 0"},
        },
        "strength_harness_context": {
            "draw_rate": draw.get("pooled", {}).get("draw_rate"),
            "pentanomial_available_for_future_strength_gate": draw.get("pentanomial_available_for_future_strength_gate"),
            "native_search_throughput_available": draw.get("native_search_throughput_available"),
            "future_sprt_sizing_inputs_ready": draw.get("future_sprt_sizing_inputs_ready"),
            "throughput_limitation": draw.get("throughput_limitation"),
        },
        "limitations": {
            "same_search_nodes_to_depth_available": False,
            "legacy_native_search_wall_telemetry_available": bool(draw.get("native_search_throughput_available")),
            "limitations_do_not_change_classification_rule": True,
        },
        "diagnostic_only": True,
        "alpha_spent": 0,
        "generation_1_authorized": False,
        "promotion_authorized": False,
        "next_stage": "AMEND_NEXT_CANDIDATE_CONTRACT_RUNTIME_CATASTROPHE_GATE_AND_CURRICULUM_ANCHOR",
    }
    base.atomic_write(artifacts / "classification.json", base.canonical_json(payload))
    results = (
        "# CLS-D terminal bottleneck classification V1\n\n"
        f"- classification: **{classification}**\n"
        f"- supported axes under frozen 200k rule: {', '.join(supported) if supported else 'none'}\n"
        f"- reason: `{reason}`\n"
        f"- SEARCH CI: [{search_ci['q025']:.6f}, {search_ci['q975']:.6f}] depth delta Jass-Scan\n"
        f"- DECISION-EVAL CI: [{decision_ci['q025']:.6f}, {decision_ci['q975']:.6f}] mirror excess\n"
        f"- COST CI: [{cost_ci['q025']:.6f}, {cost_ci['q975']:.6f}] log NPS ratio Jass/Scan\n"
        "- terminal diagnosis only; CLS generation 1 remains blocked until the next-candidate contract is prospectively amended.\n"
    )
    base.atomic_write(artifacts / "RESULTS.md", results.encode())
    summary = {
        "schema": SCHEMA, "state": "completed",
        "terminal": REHEARSAL_TERMINAL if mode == "rehearsal" else PRODUCTION_TERMINAL,
        "mode": mode, "diagnostic_only": True, "scientific_verdict": None,
        "classification": classification, "supported_axes": supported,
        "generation_1_authorized": False,
        "next_stage": payload["next_stage"],
        "target_reads": 0, "candidate_reads": 0, "control_evaluations": 0,
        "new_jass_searches": 0, "new_scan_searches": 0, "fits": 0,
        "strength_games": 0, "selfplay_games": 0, "alpha_spent": 0,
        "promotions": 0, "bakes": 0,
    }
    base.atomic_write(artifacts / "scientific-summary.json", base.canonical_json(summary))
    base.atomic_write(artifacts / "manifest.json", base.canonical_json(manifest_for(artifacts)))
    return payload


if __name__ == "__main__":
    try:
        run_stage(Path(os.environ["JASS_RESULT_DIR"]) / "cls-bottleneck-work", Path(os.environ["JASS_ARTEFACT_DIR"]))
    except Exception as exc:
        print(f"CLS bottleneck classification TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
