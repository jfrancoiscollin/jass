#!/usr/bin/env python3
"""Materialize the preregistered 0959 Scan node-semantics ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from l3_search_variants import SCAN_LMR
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_search_variants import SCAN_LMR


VARIANT_ORDER = (
    "SCAN_CORE",
    "SCAN_VERIFY",
    "SCAN_VERIFY_THREAT",
)

DIAGNOSTIC_DEFAULTS = {
    "scan_verify_pruning": 0,
    "scan_threat_reentry": 0,
}

OVERRIDES = {
    "SCAN_CORE": {
        **SCAN_LMR,
        **DIAGNOSTIC_DEFAULTS,
    },
    "SCAN_VERIFY": {
        **SCAN_LMR,
        **DIAGNOSTIC_DEFAULTS,
        "scan_verify_pruning": 1,
    },
    "SCAN_VERIFY_THREAT": {
        **SCAN_LMR,
        **DIAGNOSTIC_DEFAULTS,
        "scan_verify_pruning": 1,
        # Replace the historical qsearch emulation with Scan's exact
        # same-position depth-1 re-entry.
        "qs_threat_ext": 0,
        "scan_threat_reentry": 1,
    },
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
        raise ValueError(f"immutable Q00 must contain 63 keys, found {len(order)}")
    for key, value in DIAGNOSTIC_DEFAULTS.items():
        order.append(key)
        values[key] = str(value)
    return order, values


def render(
    order: list[str], base: dict[str, str], overrides: dict[str, int]
) -> str:
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
        "protocol": "l3-pure-m1-scan-node-semantics-ladder-v1",
        "base": {
            "name": "Q00",
            "search_params": base_spec.strip(),
            "sha256": hashlib.sha256(base_spec.strip().encode()).hexdigest(),
            "source_key_count": 63,
            "resolved_key_count": len(order),
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
    print("SCAN_NODE_SEMANTICS_LADDER_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
