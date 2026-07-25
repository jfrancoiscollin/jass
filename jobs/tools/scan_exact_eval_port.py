#!/usr/bin/env python3
"""Port Scan 3.1's frozen raw ``data/eval`` to an 8cf PJTW v3.

The conversion is algebraic, not a distillation:

* Scan's four canonical 12-square tables are expanded to Jass's eight
  top/bottom vertical bands.
* Scan's ternary convention and square permutations are converted exactly.
* Scan's 56 dense variables are embedded in the 120-extra 8cf/Q00 layout;
  Jass-only extras receive zero weight.
* The sign is changed from Scan white-POV to Jass black-POV.

The resulting file is only meaningful with an 8cf, men-only build using
KING_MOBILITY + SCAN_PARITY + TEMPO_STAGE + DRAWISH_SCALING and the
diagnostic JASS_SCAN_EXACT_EVAL runtime flag.
"""

from __future__ import annotations

import argparse
from array import array
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable, Sequence


BUCKETS = 3**12
SCAN_DENSE_VARS = 56
SCAN_PATTERN_TABLES = 4
SCAN_PARAMETERS = SCAN_DENSE_VARS + SCAN_PATTERN_TABLES * BUCKETS
SCAN_FILE_BYTES = SCAN_PARAMETERS * 2 * 2  # (mg, eg) int16 per parameter
SCAN_EVAL_SHA256 = "0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"

PJTW_MAGIC = 0x57544A50
PJTW_VERSION = 3 | 0x200  # self-describing, men-only
PJTW_SCALE = 1000
PJTW_PATTERNS = 8

PERM_TOP = (11, 10, 7, 6, 3, 2, 9, 8, 5, 4, 1, 0)
PERM_BOTTOM = (0, 1, 4, 5, 8, 9, 2, 3, 6, 7, 10, 11)
LEFT_MASK = 0x0C3061830C1860C3
SQUARE_SPARSE = (
    0, 1, 2, 3, 4,
    6, 7, 8, 9, 10,
    13, 14, 15, 16, 17,
    19, 20, 21, 22, 23,
    26, 27, 28, 29, 30,
    32, 33, 34, 35, 36,
    39, 40, 41, 42, 43,
    45, 46, 47, 48, 49,
    52, 53, 54, 55, 56,
    58, 59, 60, 61, 62,
)

PATTERNS_8CF = (
    (1, 2, 6, 7, 11, 12, 16, 17, 21, 22, 26, 27),
    (2, 3, 7, 8, 12, 13, 17, 18, 22, 23, 27, 28),
    (3, 4, 8, 9, 13, 14, 18, 19, 23, 24, 28, 29),
    (4, 5, 9, 10, 14, 15, 19, 20, 24, 25, 29, 30),
    (21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47),
    (22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48),
    (23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49),
    (24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50),
)

# 120-extra layout from scan_eval.hpp with ENDGAME + KING_MOBILITY + PARITY.
E_BK_PST = 0
E_WK_PST = 50
E_BLACK_MEN = 100
E_WHITE_MEN = 101
E_BK_SAFE = 110
E_WK_SAFE = 111
E_BK_DENIED = 112
E_WK_DENIED = 113
E_BK_SKEW = 114
E_WK_SKEW = 115
E_BK_HAS_KING = 116
E_WK_HAS_KING = 117
E_BK_EXTRA_KING = 118
E_WK_EXTRA_KING = 119
REQUIRED_EXTRAS = 120


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode_scan_int16(payload: bytes) -> array:
    """Decode Scan's big-endian signed int16 stream."""
    if len(payload) % 2:
        raise ValueError("Scan int16 payload has an odd byte count")
    raw = array("h")
    raw.frombytes(payload)
    # Scan's ml::get_bytes() consumes the most-significant byte first.
    if sys.byteorder == "little":
        raw.byteswap()
    return raw


def load_scan_weights(path: Path, expected_sha256: str | None) -> array:
    if path.stat().st_size != SCAN_FILE_BYTES:
        raise ValueError(
            f"{path}: {path.stat().st_size} bytes, expected {SCAN_FILE_BYTES}"
        )
    digest = sha256_file(path)
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(
            f"{path}: sha256 {digest}, expected {expected_sha256}"
        )
    with path.open("rb") as stream:
        raw = decode_scan_int16(stream.read())
    if len(raw) != SCAN_PARAMETERS * 2:
        raise ValueError(f"{path}: truncated int16 payload")
    return raw


def scan_exponents(
    pattern: Sequence[int], column: int, *, bottom: bool
) -> tuple[int, ...]:
    """Return the Scan trit exponent for every sorted 8cf pattern square."""
    exponents: list[int] = []
    perm = PERM_BOTTOM if bottom else PERM_TOP
    extract_shift = 26 if bottom else 0
    for square in pattern:
        bitboard = 1 << SQUARE_SPARSE[square - 1]
        shifted = bitboard >> column
        left = shifted & LEFT_MASK
        shuffled = left | (left >> 11) | (left >> 22)
        bits = (shuffled >> extract_shift) & ((1 << 12) - 1)
        if bits == 0 or bits & (bits - 1):
            raise ValueError(
                f"square {square} column {column} bottom={bottom}: "
                f"not one Scan pattern bit ({bits:#x})"
            )
        exponents.append(perm[bits.bit_length() - 1])
    if sorted(exponents) != list(range(12)):
        raise ValueError(
            f"column {column} bottom={bottom}: not a trit permutation "
            f"{exponents}"
        )
    return tuple(exponents)


def bucket_map(
    exponents: Sequence[int], digit_map: Sequence[int]
) -> array:
    """Map all Jass bucket ids to one canonical Scan table bucket id."""
    if sorted(exponents) != list(range(12)):
        raise ValueError("exponents must be a permutation of 0..11")
    if len(digit_map) != 3 or sorted(digit_map) != [0, 1, 2]:
        raise ValueError("digit_map must be a permutation of 0,1,2")
    powers = tuple(3**e for e in exponents)
    out = array("I", [0]) * BUCKETS
    for bucket in range(BUCKETS):
        value = bucket
        mapped = 0
        for power in powers:
            digit = value % 3
            value //= 3
            mapped += digit_map[digit] * power
        out[bucket] = mapped
    return out


def pattern_contracts() -> list[dict[str, object]]:
    contracts: list[dict[str, object]] = []
    for pattern_index, pattern in enumerate(PATTERNS_8CF):
        bottom = pattern_index >= 4
        column = pattern_index % 4
        exponents = scan_exponents(pattern, column, bottom=bottom)
        contracts.append(
            {
                "pattern": pattern_index,
                "half": "bottom" if bottom else "top",
                "column": column,
                "scan_table": 7 - pattern_index if bottom else pattern_index,
                "sign_scan_to_black_pov": 1 if bottom else -1,
                "exponents": list(exponents),
                # Scan centers each trit at 1. Top uses +black-white;
                # bottom uses -black+white.
                "digit_map": [1, 0, 2] if bottom else [1, 2, 0],
            }
        )
    return contracts


def map_extras(raw: Sequence[int], bank: int, n_ext: int) -> array:
    if n_ext < REQUIRED_EXTRAS:
        raise ValueError(f"n_ext={n_ext}, exact port requires >= {REQUIRED_EXTRAS}")

    def weight(var: int) -> int:
        return int(raw[var * 2 + bank])

    out = array("i", [0]) * n_ext

    # Scan feature 0 = white men - black men; negate to Jass black POV.
    out[E_BLACK_MEN] = +weight(0)
    out[E_WHITE_MEN] = -weight(0)

    # King PST: Scan mirrors black squares into the white-square table.
    for square0 in range(50):
        out[E_BK_PST + square0] = +weight(3 + (49 - square0))
        out[E_WK_PST + square0] = -weight(3 + square0)

    # Scan features 53/54 are white-safe/denied minus black-safe/denied.
    out[E_BK_SAFE] = +weight(53)
    out[E_WK_SAFE] = -weight(53)
    out[E_BK_DENIED] = +weight(54)
    out[E_WK_DENIED] = -weight(54)

    # Scan feature 55 = |white skew| - |black skew|.
    out[E_BK_SKEW] = +weight(55)
    out[E_WK_SKEW] = -weight(55)

    # Scan features 1/2 split first king from surplus kings.
    out[E_BK_HAS_KING] = +weight(1)
    out[E_WK_HAS_KING] = -weight(1)
    out[E_BK_EXTRA_KING] = +weight(2)
    out[E_WK_EXTRA_KING] = -weight(2)
    return out


def _write_i32(stream, values: Iterable[int]) -> None:
    payload = array("i", values)
    if payload.itemsize != 4:
        raise RuntimeError("platform int is not 32-bit")
    if sys.byteorder != "little":
        payload.byteswap()
    payload.tofile(stream)


def convert(
    scan_eval: Path,
    output: Path,
    *,
    n_ext: int = REQUIRED_EXTRAS,
    expected_sha256: str | None = SCAN_EVAL_SHA256,
    manifest: Path | None = None,
) -> dict[str, object]:
    raw = load_scan_weights(scan_eval, expected_sha256)
    contracts = pattern_contracts()
    maps: dict[tuple[tuple[int, ...], tuple[int, ...]], array] = {}
    for contract in contracts:
        key = (
            tuple(int(x) for x in contract["exponents"]),
            tuple(int(x) for x in contract["digit_map"]),
        )
        if key not in maps:
            maps[key] = bucket_map(*key)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as stream:
        stream.write(
            struct.pack(
                "<IIIII",
                PJTW_MAGIC,
                PJTW_VERSION,
                PJTW_SCALE,
                PJTW_PATTERNS * BUCKETS,
                n_ext,
            )
        )
        for bank in (0, 1):
            for contract in contracts:
                table = int(contract["scan_table"])
                sign = int(contract["sign_scan_to_black_pov"])
                key = (
                    tuple(int(x) for x in contract["exponents"]),
                    tuple(int(x) for x in contract["digit_map"]),
                )
                mapping = maps[key]
                source_base = SCAN_DENSE_VARS + table * BUCKETS
                _write_i32(
                    stream,
                    (
                        sign * int(raw[(source_base + source_bucket) * 2 + bank])
                        for source_bucket in mapping
                    ),
                )
        _write_i32(stream, map_extras(raw, 0, n_ext))
        _write_i32(stream, map_extras(raw, 1, n_ext))

    expected_bytes = (
        20 + 2 * (PJTW_PATTERNS * BUCKETS + n_ext) * 4
    )
    if output.stat().st_size != expected_bytes:
        raise RuntimeError(
            f"{output}: {output.stat().st_size} bytes, expected {expected_bytes}"
        )
    payload: dict[str, object] = {
        "schema": 1,
        "kind": "scan-3.1-raw-eval-to-8cf-pjtw-v3",
        "source": {
            "path": str(scan_eval),
            "bytes": scan_eval.stat().st_size,
            "sha256": sha256_file(scan_eval),
            "parameters": SCAN_PARAMETERS,
            "storage": "big-endian interleaved int16 [parameter][mg,eg]",
            "pov": "white",
        },
        "output": {
            "path": str(output),
            "bytes": output.stat().st_size,
            "sha256": sha256_file(output),
            "magic": "PJTW",
            "version": PJTW_VERSION,
            "scale": PJTW_SCALE,
            "n_patterns": PJTW_PATTERNS,
            "n_pat": PJTW_PATTERNS * BUCKETS,
            "n_ext": n_ext,
            "pov": "black",
        },
        "contracts": contracts,
        "runtime_requirements": [
            "8cf men-only pattern geometry",
            "JASS_ENDGAME_FEATURES=ON",
            "JASS_KING_MOBILITY=ON",
            "JASS_SCAN_PARITY=ON",
            "JASS_TEMPO_STAGE=ON",
            "JASS_DRAWISH_SCALING=ON",
            "JASS_SCAN_EXACT_EVAL=ON",
        ],
        "distillation": False,
    }
    if manifest:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-eval", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--n-ext", type=int, default=REQUIRED_EXTRAS)
    parser.add_argument(
        "--expected-sha256",
        default=SCAN_EVAL_SHA256,
        help="empty string disables the source hash check",
    )
    args = parser.parse_args()
    payload = convert(
        args.scan_eval,
        args.out,
        n_ext=args.n_ext,
        expected_sha256=args.expected_sha256 or None,
        manifest=args.manifest,
    )
    print(json.dumps(payload["output"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
