#!/usr/bin/env python3
"""Materialize the preregistered 0958 Jass-search intervention ladder.

The base fingerprint is the immutable Q00 string reused by 0957.  Every arm
changes only search parameters; the exact Scan evaluation, gauge, defender and
depth remain fixed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


VARIANT_ORDER = (
    "NO_FORWARD",
    "SCAN_EXT_QS",
    "SCAN_LMR",
    "FULL_WIDTH",
)

NO_FORWARD = {
    "rfp_max_depth": 0,
    "nmp_min_depth": 99,
    "razor_max_depth": 0,
    "probcut_min_depth": 0,
    "multicut_min_depth": 0,
}

SCAN_EXT_QS = {
    **NO_FORWARD,
    # Scan 3.1 extends every single-reply node and recursively follows its
    # selective quiet sacrifices in qsearch.
    "ext_single_reply": 1,
    "qs_sacs": 1,
    "qs_sacs_depth0_only": 0,
    "qs_threat_ext": 1,
}

SCAN_LMR = {
    **SCAN_EXT_QS,
    # Scan: depth >=2; fourth PV move / second non-PV move; reduction 1,
    # or 2 for non-PV moves from index four. lmr_formula=3 implements the
    # frozen conditional shape without changing the production formula.
    "lmr_min_depth": 2,
    "lmr_first_full_pv": 3,
    "lmr_first_full_nonpv": 1,
    "lmr_formula": 3,
    "use_improving": 0,
}

FULL_WIDTH = {
    **SCAN_EXT_QS,
    # Remove all main-tree selectivity while retaining Scan-like qsearch and
    # the single-reply extension. PVS/aspiration are disabled as additional
    # exactness checks; move ordering may change cost, not minimax value.
    "lmr_min_depth": 99,
    "lmp_max_depth": 0,
    "use_improving": 0,
    "use_pvs": 0,
    "aspiration_initial": 20000,
    "use_conthist": 0,
}

OVERRIDES = {
    "NO_FORWARD": NO_FORWARD,
    "SCAN_EXT_QS": SCAN_EXT_QS,
    "SCAN_LMR": SCAN_LMR,
    "FULL_WIDTH": FULL_WIDTH,
}


def parse_fingerprint(spec: str) -> tuple[list[str], dict[str, str]]:
    order: list[str] = []
    values: dict[str, str] = {}
    for token in spec.strip().split(","):
        if not token or "=" not in token:
            raise ValueError(f"malformed search token {token!r}")
        key, value = token.split("=", 1)
        if not key or key in values:
            raise ValueError(f"duplicate/empty search key {key!r}")
        int(value)
        order.append(key)
        values[key] = value
    if len(order) != 63:
        raise ValueError(f"Q00 must contain 63 keys, found {len(order)}")
    return order, values


def render(order: list[str], base: dict[str, str], overrides: dict[str, int]) -> str:
    unknown = sorted(set(overrides) - set(base))
    if unknown:
        raise ValueError(f"variant contains unknown keys: {unknown}")
    values = dict(base)
    values.update({key: str(value) for key, value in overrides.items()})
    return ",".join(f"{key}={values[key]}" for key in order)


def build_manifest(base_spec: str) -> dict[str, object]:
    order, base = parse_fingerprint(base_spec)
    arms: dict[str, object] = {}
    for name in VARIANT_ORDER:
        spec = render(order, base, OVERRIDES[name])
        arms[name] = {
            "search_params": spec,
            "sha256": hashlib.sha256(spec.encode()).hexdigest(),
            "overrides": OVERRIDES[name],
            "key_count": len(order),
        }
    return {
        "schema": 1,
        "protocol": "l3-pure-m1-search-tree-audit-search-ladder-v1",
        "base": {
            "name": "Q00",
            "search_params": base_spec.strip(),
            "sha256": hashlib.sha256(base_spec.strip().encode()).hexdigest(),
            "key_count": len(order),
        },
        "variant_order": list(VARIANT_ORDER),
        "arms": arms,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    payload = build_manifest(args.base_file.read_text(encoding="utf-8").strip())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, arm in payload["arms"].items():
        (args.out_dir / f"{name}.txt").write_text(
            str(arm["search_params"]) + "\n", encoding="utf-8"
        )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("SEARCH_VARIANT_LADDER_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
