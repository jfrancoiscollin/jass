#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copy a frozen PJTW champion and attach a CVH1 sibling sidecar.

The output PJTW bytes must be identical to the champion. Runtime activation is
by the optional ``<output>.cvh`` file, which keeps Gen2-MMTO immutable and makes
``lambda_cp=0`` a clean technical control.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conversion_head import BINARY_SIZE, encode_model, load_json, sha256_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--champion", required=True)
    ap.add_argument("--head-json", required=True)
    ap.add_argument("--out", required=True, help="copied PJTW path; sidecar is OUT.cvh")
    ap.add_argument("--lambda-cp", type=float, default=None,
                    help="optional deployment amplitude override")
    ap.add_argument("--manifest", default="")
    args = ap.parse_args()

    champion = Path(args.champion).resolve()
    head_json = Path(args.head_json).resolve()
    out = Path(args.out).resolve()
    sidecar = Path(str(out) + ".cvh")
    if champion == out:
        raise SystemExit("--out must differ from --champion")
    if not champion.is_file() or champion.stat().st_size <= 20:
        raise SystemExit(f"invalid champion: {champion}")
    if not head_json.is_file():
        raise SystemExit(f"missing head JSON: {head_json}")

    model = load_json(head_json)
    if args.lambda_cp is not None:
        if args.lambda_cp < 0:
            raise SystemExit("--lambda-cp must be non-negative")
        model["lambda_cp"] = float(args.lambda_cp)
    payload = encode_model(model)
    if len(payload) != BINARY_SIZE:
        raise AssertionError("CVH1 encoder emitted wrong size")

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(champion, out)
    sidecar.write_bytes(payload)
    if sha256_file(champion) != sha256_file(out):
        out.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise SystemExit("ABORT: copied PJTW differs from frozen champion")

    manifest = {
        "format": "gen2-mmto-conversion-head-sidecar-v1",
        "champion": str(champion),
        "head_json": str(head_json),
        "output": str(out),
        "sidecar": str(sidecar),
        "champion_sha256": sha256_file(champion),
        "output_sha256": sha256_file(out),
        "head_json_sha256": sha256_file(head_json),
        "sidecar_sha256": sha256_file(sidecar),
        "base_identical": True,
        "sidecar_bytes": sidecar.stat().st_size,
        "lambda_cp": model["lambda_cp"],
    }
    manifest_path = Path(args.manifest) if args.manifest else Path(str(out) + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
