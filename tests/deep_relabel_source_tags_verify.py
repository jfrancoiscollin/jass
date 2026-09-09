#!/usr/bin/env python3
"""Verification helper for the deep_relabel_source_tags_smoke CTest.

Reads an input JNNW, an output JNNW produced by `--deep-relabel ... --clear-tt
--source-tags-out tags`, and the tags file, and checks the invariants listed
in the task (record counts, tag alphabet, the hand-built TERMINAL record,
and the SEARCH-record wdl/score consistency).
"""
import argparse
import struct
import sys

RECORD_BYTES = 38


def read_jnnw(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"JNNW":
        raise SystemExit(f"error: {path} is not JNNW")
    (count,) = struct.unpack_from("<I", data, 4)
    body = data[8:]
    if len(body) != count * RECORD_BYTES:
        raise SystemExit(f"error: {path} size/count mismatch")
    recs = [body[i * RECORD_BYTES:(i + 1) * RECORD_BYTES] for i in range(count)]
    return count, recs


def decode(rec):
    bbs = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    (score,) = struct.unpack_from("<i", rec, 33)
    wdl = struct.unpack_from("<b", rec, 37)[0]
    return bbs, stm, score, wdl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("in_path")
    ap.add_argument("out_path")
    ap.add_argument("tags_path")
    ap.add_argument("--draw-band", type=int, default=50)
    args = ap.parse_args()

    n_in, _ = read_jnnw(args.in_path)
    n_out, out_recs = read_jnnw(args.out_path)
    if n_in != n_out:
        raise SystemExit(f"error: record count changed: in={n_in} out={n_out}")

    with open(args.tags_path, "rb") as f:
        tags = f.read()
    if len(tags) != n_out:
        raise SystemExit(f"error: tags size {len(tags)} != records {n_out}")

    band = args.draw_band
    terminal_idx = n_out - 1  # the hand-built record is appended last
    saw_terminal = False
    for i, rec in enumerate(out_recs):
        tag = tags[i]
        if tag not in (0, 1, 2):
            raise SystemExit(f"error: record {i} has invalid tag {tag}")
        _, _, score, wdl = decode(rec)
        if i == terminal_idx:
            if tag != 2:
                raise SystemExit(f"error: hand-built terminal record has tag {tag}, expected 2")
            if wdl != -1:
                raise SystemExit(f"error: terminal record wdl={wdl}, expected -1")
            if score != -10000:
                raise SystemExit(f"error: terminal record score={score}, expected -10000")
            saw_terminal = True
            continue
        if tag == 1:
            continue  # TB path: score/wdl come from egdb, not the draw-band rule
        if tag == 0:
            expect_wdl = 1 if score > band else (-1 if score < -band else 0)
            if wdl != expect_wdl:
                raise SystemExit(
                    f"error: record {i} tag=SEARCH score={score} wdl={wdl} "
                    f"expected {expect_wdl}"
                )
        elif tag == 2:
            raise SystemExit(f"error: unexpected extra TERMINAL record at {i}")

    if not saw_terminal:
        raise SystemExit("error: hand-built terminal record not found at expected index")

    print(f"deep_relabel_source_tags_verify: OK records={n_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
