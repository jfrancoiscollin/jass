#!/usr/bin/env python3
"""Validate immutable C0/P1 sources for the L3-PURE M0 triangle.

C0 A-G3 predates the fully self-describing manifest schema.  Its immutable
0790 run is accepted through one explicit compatibility contract keyed by job
id and code SHA; every other source must carry its own search fingerprint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

C0_LEGACY_JOB = "ccx33-0790-l3-pure-c0-a-v1"
C0_LEGACY_CODE_SHA = "8fc4eacbb7d99edb5aadc9db7caeb93abc8c85a2"
C0_REVIEWED_SEARCH = (
    "qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,"
    "qs_forcing_depth=0,qs_promo_depth=0"
)
C0_REVIEWED_SEARCH_SHA256 = "525bbdc8a5e6b4413b6dc2635206b16f3d6d64d6993407b83d4121c817145609"
GEN2_SEARCH = "qs_forcing_depth=6,qs_promo_depth=6"
Q00_REQUIRED = {
    "qs_threat_ext": "0",
    "qs_sacs": "0",
    "qs_sacs_depth0_only": "1",
    "qs_forcing_depth": "0",
    "qs_promo_depth": "0",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_search(spec: str, expected_count: int, label: str) -> dict[str, str]:
    tokens = spec.split(",") if spec else []
    if len(tokens) != expected_count:
        raise ValueError(f"{label}: expected {expected_count} search keys, got {len(tokens)}")
    values: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"{label}: malformed search token {token!r}")
        key, value = token.split("=", 1)
        if key in values:
            raise ValueError(f"{label}: duplicate search key {key}")
        int(value)
        values[key] = value
    return values


def resolve_c0_search(manifest: dict, verified: dict, expected_job: str) -> tuple[str, str]:
    declared = str(manifest.get("search_params") or "")
    if declared:
        return declared, "manifest"
    compatible = (
        expected_job == C0_LEGACY_JOB
        and verified.get("job_id") == C0_LEGACY_JOB
        and verified.get("code_sha") == C0_LEGACY_CODE_SHA
        and manifest.get("schema") == 1
        and manifest.get("lineage") == "L3-PURE"
        and manifest.get("arm") == "A"
        and manifest.get("generations") == 3
    )
    if not compatible:
        raise ValueError("C0 manifest lacks search_params outside the reviewed 0790 schema-1 contract")
    return C0_REVIEWED_SEARCH, "reviewed_0790_schema1_compatibility"


def validate(args: argparse.Namespace) -> dict:
    c0_dir = Path(args.c0_dir)
    p1_dir = Path(args.p1_dir)
    c0m = load(c0_dir / "manifest.json")
    p1m = load(p1_dir / "manifest.json")
    c0v = load(Path(args.verified_c0))
    p1v = load(Path(args.verified_p1))

    if c0v.get("job_id") != args.expected_c0_job or p1v.get("job_id") != args.expected_p1_job:
        raise ValueError("source job mismatch")
    if c0v.get("result_state") != "completed" or p1v.get("result_state") != "completed":
        raise ValueError("source result is not completed")
    if not (
        c0m.get("lineage") == "L3-PURE"
        and c0m.get("arm") == "A"
        and c0m.get("generations") == 3
        and c0m.get("scientific_status") == "complete_generation_chain"
    ):
        raise ValueError("invalid C0 A manifest")
    recipe = p1m.get("recipe", {})
    if not (
        p1m.get("experiment") == "L3-PURE-P1"
        and p1m.get("variant") == "FROZEN_BASELINE"
        and p1m.get("scientific_status") == "complete_p1_training"
        and recipe.get("lineage") == "L3-PURE"
        and recipe.get("variant") == "FROZEN_BASELINE"
        and recipe.get("geometry") == "8cf"
        and recipe.get("generations") == 4
    ):
        raise ValueError("invalid P1 G1-G4 manifest")

    c0_model = c0_dir / "g3.pjtw.gz"
    p1_model = p1_dir / "g4.pjtw.gz"
    c0_model_sha = sha256(c0_model)
    p1_model_sha = sha256(p1_model)
    if c0m.get("champion_sha256", {}).get(c0_model.name) != c0_model_sha:
        raise ValueError("g3.pjtw.gz checksum mismatch")
    if p1m.get("student_sha256", {}).get(p1_model.name) != p1_model_sha:
        raise ValueError("g4.pjtw.gz checksum mismatch")

    c0_search, c0_search_source = resolve_c0_search(c0m, c0v, args.expected_c0_job)
    c0_values = parse_search(c0_search, 5, "C0")
    if c0_search != C0_REVIEWED_SEARCH:
        raise ValueError("C0 fingerprint differs from the reviewed five-key contract")
    if hashlib.sha256(c0_search.encode()).hexdigest() != C0_REVIEWED_SEARCH_SHA256:
        raise ValueError("C0 fingerprint digest mismatch")

    p1_search = str(p1m.get("search_params") or recipe.get("search_params") or "")
    p1_values = parse_search(p1_search, 63, "P1 Q00")
    if any(p1_values.get(key) != value for key, value in Q00_REQUIRED.items()):
        raise ValueError("P1 fingerprint is not Q00")
    declared_p1_sha = p1m.get("search_params_sha256")
    p1_search_sha = hashlib.sha256(p1_search.encode()).hexdigest()
    if declared_p1_sha and declared_p1_sha != p1_search_sha:
        raise ValueError("P1 fingerprint digest mismatch")

    return {
        "schema": 2,
        "protocol": "l3-pure-m0-source-contract",
        "c0_job": args.expected_c0_job,
        "p1_job": args.expected_p1_job,
        "c0_code_sha": c0v.get("code_sha"),
        "p1_code_sha": p1v.get("code_sha"),
        "c0_model_sha256": c0_model_sha,
        "p1_model_sha256": p1_model_sha,
        "c0_search_params": c0_search,
        "c0_search_params_sha256": C0_REVIEWED_SEARCH_SHA256,
        "c0_search_params_source": c0_search_source,
        "p1_q00_search_params": p1_search,
        "p1_q00_search_params_sha256": p1_search_sha,
        "gen2_search_params": GEN2_SEARCH,
        "source_bytes_reused": True,
        "training_records": 0,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c0-dir", required=True)
    parser.add_argument("--p1-dir", required=True)
    parser.add_argument("--verified-c0", required=True)
    parser.add_argument("--verified-p1", required=True)
    parser.add_argument("--expected-c0-job", required=True)
    parser.add_argument("--expected-p1-job", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = validate(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"l3_pure_m0_sources: {exc}", file=__import__("sys").stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("M0_SOURCE_CONTRACT_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
