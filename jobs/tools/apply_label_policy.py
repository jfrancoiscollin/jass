#!/usr/bin/env python3
"""Merge a deep-relabelled JNNW with proof-bearing labels.

Source tags are telemetry only (0=ONP, 1=GYM, 2=CAP). They never grant
CERT_PROOF authority by themselves. A label blocks the deep draw-band only
when an aligned certificate is valid and ``oracle_cert.can_block_draw_band``
returns true.

The command is deliberately fail-closed: position misalignment, malformed
certificates, invalid blocking claims, or a missed protected-tip threshold
produce a non-zero exit code and no scientific PASS.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle_cert  # type: ignore  # noqa: E402

MAGIC = b"JNNW"
REC = 38
WDL_OFFSET = 37
TAG_NAMES = {0: "ONP", 1: "GYM", 2: "CAP"}


def read_jnnw(path: str | Path) -> list[bytearray]:
    raw = Path(path).read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW header")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC:
        raise ValueError(f"{path}: expected {count * REC} body bytes, got {len(body)}")
    return [bytearray(body[i * REC:(i + 1) * REC]) for i in range(count)]


def write_jnnw(path: str | Path, records: list[bytearray]) -> None:
    body = b"".join(bytes(record) for record in records)
    Path(path).write_bytes(MAGIC + struct.pack("<I", len(records)) + body)


def read_certificates(path: str | Path | None, count: int) -> list[dict | None]:
    if path is None:
        return [None] * count
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return [None] * count
    if text.startswith("["):
        values = json.loads(text)
    else:
        values = [json.loads(line) if line.strip() else None for line in text.splitlines()]
    if len(values) != count:
        raise ValueError(f"certificate count {len(values)} != record count {count}")
    return values


def merge_policy(
    original: list[bytearray],
    relabelled: list[bytearray],
    tags: bytes,
    certificates: list[dict | None],
    min_protected_tip_rate: float = 0.0,
) -> tuple[list[bytearray], dict]:
    count = len(original)
    if len(relabelled) != count or len(tags) != count or len(certificates) != count:
        raise ValueError("original/relabel/tags/certificates are not aligned")

    by_tag: Counter[str] = Counter()
    by_tier: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    protected_tip = 0
    tip_total = 0
    invalid_certificates = 0
    output: list[bytearray] = []

    for index, (before, deep, tag, cert) in enumerate(
        zip(original, relabelled, tags, certificates, strict=True)
    ):
        if bytes(before[:33]) != bytes(deep[:33]):
            raise ValueError(f"record {index}: position/STM changed during deep relabel")
        tag_name = TAG_NAMES.get(tag, f"UNKNOWN_{tag}")
        by_tag[tag_name] += 1
        if tag != 0:
            tip_total += 1

        chosen = bytearray(deep)
        source = "DEEP_RELABEL"
        if cert is not None:
            valid, reasons = oracle_cert.validate_certificate(cert)
            tier = str(cert.get("oracle_tier", "UNKNOWN"))
            by_tier[tier] += 1
            if not valid:
                invalid_certificates += 1
                if cert.get("blocks_draw_band"):
                    raise ValueError(
                        f"record {index}: invalid certificate attempted to block draw-band: {reasons}"
                    )
            elif oracle_cert.can_block_draw_band(cert):
                result = oracle_cert.resolve_label(
                    cert,
                    on_policy_wdl=struct.unpack_from("<b", before, WDL_OFFSET)[0],
                    draw_band_wdl=struct.unpack_from("<b", deep, WDL_OFFSET)[0],
                )
                struct.pack_into("<b", chosen, WDL_OFFSET, int(result["wdl"]))
                source = str(result["source"])
                if tag != 0:
                    protected_tip += 1

        by_source[source] += 1
        output.append(chosen)

    protected_rate = protected_tip / tip_total if tip_total else 1.0
    manifest = {
        "records": count,
        "by_tag": dict(sorted(by_tag.items())),
        "by_certificate_tier": dict(sorted(by_tier.items())),
        "by_final_source": dict(sorted(by_source.items())),
        "tip_total": tip_total,
        "protected_tip": protected_tip,
        "protected_tip_rate": round(protected_rate, 6),
        "invalid_certificates": invalid_certificates,
        "min_protected_tip_rate": min_protected_tip_rate,
        "policy_ok": protected_rate >= min_protected_tip_rate,
    }
    if protected_rate < min_protected_tip_rate:
        raise ValueError(
            f"protected tip rate {protected_rate:.3%} < required {min_protected_tip_rate:.3%}"
        )
    return output, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True)
    parser.add_argument("--relabelled", required=True)
    parser.add_argument("--source-tags", required=True)
    parser.add_argument("--certificates", help="JSON list or JSONL aligned one-per-record")
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--min-protected-tip-rate", type=float, default=0.0)
    args = parser.parse_args(argv)

    try:
        original = read_jnnw(args.original)
        relabelled = read_jnnw(args.relabelled)
        tags = Path(args.source_tags).read_bytes()
        certificates = read_certificates(args.certificates, len(original))
        output, manifest = merge_policy(
            original,
            relabelled,
            tags,
            certificates,
            args.min_protected_tip_rate,
        )
        write_jnnw(args.out, output)
        Path(args.manifest).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
