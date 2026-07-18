#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Relabel a JNNW dataset using Scan as the eval oracle (paradigm shift G —
distillation depuis Scan, cf. docs/archives/PARADIGM_SHIFT_OPTIONS.md option G).

For each position in the input JNNW, query Scan via the HUB v2 protocol
(`pos pos=… ; level depth=N ; go think`), parse the deepest `info` line
for the score, and write the same position with the Scan score replacing
the original score field. Output JNNW has identical layout — drop-in
replacement for train_v3.py.

Usage :
   python3 tools/relabel_with_scan.py \\
       --in   v8-quiet-pv-1M.bin \\
       --out  v10-scan-labelled.bin \\
       --scan /tmp/scan/scan_linux --depth 16 \\
       [--max-records N] [--start N] [--threads K]

Scan is GPL3 — its scores ARE the protected output of GPL code. The
derived dataset inherits GPL3 obligations ; jass itself is already
AGPL3, no conflict.
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))


RECORD_SZ = 38
HEADER_SZ = 8
# JNNW record layout :
#   0..32   uint64×4   bbs (wm, wk, bm, bk)
#   32..33  uint8      stm (0=W, 1=B)
#   33..37  int32      score (centipawns, STM-POV)
#   37..38  int8       wdl (-1, 0, +1, STM-POV)


# Scan HUB v2 emits `info` lines during search with score=, depth=, nodes=
# and a final `done move=…` line. We take the score from the deepest info
# line seen.
SCAN_INFO_RE  = re.compile(r"\bscore=([-+]?\d+(?:\.\d+)?)\b")
SCAN_DEPTH_RE = re.compile(r"\bdepth=(\d+)\b")
SCAN_DONE_RE  = re.compile(r"^done\b")


def bbs_to_scan_pos(wm: int, wk: int, bm: int, bk: int, stm: int) -> str:
    """Build Scan's 51-char position string from 4 uint64 bitboards + stm.
    Scan square numbering matches FMJD 1..50 directly (same as ours)."""
    chars = ["e"] * 51
    chars[0] = "B" if stm == 1 else "W"
    for sq in range(1, 51):
        bit = 1 << (sq - 1)
        if   wm & bit: chars[sq] = "w"
        elif wk & bit: chars[sq] = "W"
        elif bm & bit: chars[sq] = "b"
        elif bk & bit: chars[sq] = "B"
    return "".join(chars)


class ScanScorer:
    """Subprocess Scan in HUB mode, query eval scores."""
    def __init__(self, scan_path: str, bb_size: int = 0,
                 tt_size_log2: int = 24):
        scan_dir = str(Path(scan_path).resolve().parent)
        self.proc = subprocess.Popen(
            [scan_path, "hub"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, cwd=scan_dir)
        self._send("hub")
        self._read_until(lambda l: l.startswith("wait"))
        # CRITICAL : disable book (else Scan returns book moves with
        # score=0 for opening positions, biasing the labelled dataset).
        self._send("set-param name=book value=false")
        # tt-size = 2^N bytes ; 24 → 16 MiB. Big enough to amortize over
        # batched positions (cf. --newgame-every).
        self._send(f"set-param name=tt-size value={tt_size_log2}")
        if bb_size > 0:
            self._send(f"set-param name=bb-size value={bb_size}")
        self._send("init")
        self._read_until(lambda l: l.startswith("ready"))
        # Initialise game state once ; subsequent new-game calls are
        # gated by --newgame-every to preserve TT across nearby positions.
        self._since_newgame = 0
        self._send("new-game")

    def _send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _read_until(self, pred, timeout_s: float = 30.0) -> list[str]:
        assert self.proc.stdout is not None
        lines: list[str] = []
        deadline = time.monotonic() + timeout_s
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Scan timeout: last lines={lines[-3:]}")
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Scan stdout closed unexpectedly")
            line = line.rstrip("\n")
            lines.append(line)
            if pred(line):
                return lines

    def eval_position(self, scan_pos: str, depth: int,
                      timeout_s: float = 60.0,
                      newgame_every: int = 50) -> Optional[int]:
        """Set the position, search to `depth`, return the deepest score
        from `info` lines (Scan emits float pawn units ; we ×100 to
        centipawns, STM-POV like our JNNW convention)."""
        # Clear TT only every N positions — preserves caches across
        # similar (typically same-game-source) positions ; per-position
        # newgame wipes useful entries.
        self._since_newgame += 1
        if newgame_every > 0 and self._since_newgame >= newgame_every:
            self._send("new-game")
            self._since_newgame = 0
        self._send(f"pos pos={scan_pos}")
        self._send(f"level depth={depth}")
        self._send("go think")
        try:
            lines = self._read_until(
                lambda l: SCAN_DONE_RE.search(l) or l.startswith("error"),
                timeout_s=timeout_s)
        except (TimeoutError, RuntimeError):
            return None
        if lines[-1].startswith("error"):
            return None
        best_score: Optional[int] = None
        best_depth = -1
        for ln in lines:
            s_match = SCAN_INFO_RE.search(ln)
            if not s_match:
                continue
            # Forced-move positions (mandatory capture) make Scan emit a
            # single `info score=… pv=<capture>` line with NO `depth=`
            # field, then `done`. The score is still valid (eval after the
            # forced move) — treat a depth-less scored line as depth 0 so
            # it is used when no deeper search line exists, but is
            # overridden by any real depth>=1 info. Previously these lines
            # were dropped (requiring depth=), so ~18% of positions
            # (capture-forced) silently fell back to their ORIGINAL label
            # instead of the Scan score — corrupting the distilled dataset.
            d_match = SCAN_DEPTH_RE.search(ln)
            d = int(d_match.group(1)) if d_match else 0
            if d >= best_depth:  # >= : keep the LAST info at max depth
                best_depth = d
                try:
                    # Scan emits scores in PAWN UNITS as floats
                    # (e.g. `score=-0.04` = -4 cp). Multiply by 100
                    # to get centipawns matching jass's convention.
                    s = float(s_match.group(1))
                    best_score = int(round(s * 100.0))
                except ValueError:
                    pass
        return best_score

    def close(self) -> None:
        try:
            self._send("quit")
        except BrokenPipeError:
            pass
        try:
            self.proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def relabel(in_path: Path, out_path: Path, scan_path: str,
            depth: int, max_records: int, start: int,
            timeout_s: float, progress_every: int,
            newgame_every: int, drop_skipped: bool = True) -> int:
    raw = in_path.read_bytes()
    assert raw[:4] == b"JNNW", f"{in_path}: bad magic"
    total = struct.unpack_from("<I", raw, 4)[0]
    end = total if max_records == 0 else min(start + max_records, total)
    n_to_do = end - start
    print(f"input : {in_path} ({total} records, processing {n_to_do} "
          f"from offset {start}, drop_skipped={drop_skipped})", flush=True)

    scorer = ScanScorer(scan_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as out:
        out.write(b"JNNW")
        out.write(struct.pack("<I", n_to_do))  # backpatched at the end

        t0 = time.monotonic()
        n_ok = 0
        n_skip = 0
        for i in range(start, end):
            rec_off = HEADER_SZ + i * RECORD_SZ
            rec = raw[rec_off:rec_off + RECORD_SZ]
            wm, wk, bm, bk = struct.unpack("<QQQQ", rec[:32])
            stm = rec[32]
            score_orig = struct.unpack("<i", rec[33:37])[0]
            wdl = rec[37]

            scan_pos = bbs_to_scan_pos(wm, wk, bm, bk, stm)
            new_score = scorer.eval_position(scan_pos, depth,
                                             timeout_s=timeout_s,
                                             newgame_every=newgame_every)
            if new_score is None:
                # Scan gave no score (forced single-move position with a
                # `info pv=…` line carrying no score). Keeping the ORIGINAL
                # (non-Scan) label corrupts the distilled set, so by default
                # we DROP the record — a forced position needs no learned
                # eval anyway. --keep-skipped-original restores the old
                # (buggy) fall-back behaviour.
                n_skip += 1
                if drop_skipped:
                    continue
                new_score = score_orig

            new_rec = rec[:33] + struct.pack("<i", int(new_score)) \
                              + rec[37:38]
            out.write(new_rec)
            n_ok += 1

            n_proc = i - start + 1
            if n_proc % progress_every == 0:
                elapsed = time.monotonic() - t0
                rate = n_proc / elapsed if elapsed > 0 else 0.0
                eta = (n_to_do - n_proc) / rate if rate > 0 else float("inf")
                print(f"  {n_proc}/{n_to_do}  ({100*n_proc/n_to_do:.1f}%)  "
                      f"rate={rate:.1f} pos/s  eta={eta/60:.1f} min  "
                      f"written={n_ok} skipped={n_skip}", flush=True)

        # Backpatch the real written count (records may have been dropped).
        out.flush()
        out.seek(4)
        out.write(struct.pack("<I", n_ok))

    scorer.close()
    print(f"wrote {out_path} ({n_ok} records written, {n_skip} skipped"
          f" / {n_to_do} processed)", flush=True)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in",   dest="in_path", required=True, type=Path)
    ap.add_argument("--out",  dest="out_path", required=True, type=Path)
    ap.add_argument("--scan", dest="scan_path", required=True, type=str,
                    help="path to scan_linux binary (its dir holds scan.ini)")
    ap.add_argument("--depth", type=int, default=16,
                    help="Scan search depth per position (default 16)")
    ap.add_argument("--max-records", type=int, default=0,
                    help="0 = all records (after --start)")
    ap.add_argument("--start", type=int, default=0,
                    help="skip this many records (resumable batching)")
    ap.add_argument("--timeout", type=float, default=60.0,
                    help="per-position timeout seconds")
    ap.add_argument("--progress-every", type=int, default=1000)
    ap.add_argument("--newgame-every", type=int, default=50,
                    help="emit `new-game` (clear Scan TT) every N positions ; "
                         "0 = never (single game session for the full shard).")
    ap.add_argument("--keep-skipped-original", action="store_true",
                    help="legacy: for positions Scan can't score (forced "
                         "single-move), keep the ORIGINAL (non-Scan) label "
                         "instead of dropping the record. Off by default "
                         "because keeping non-Scan labels corrupts the "
                         "distilled dataset (~8%% of master positions).")
    args = ap.parse_args(argv)

    return relabel(args.in_path, args.out_path, args.scan_path,
                   args.depth, args.max_records, args.start,
                   args.timeout, args.progress_every,
                   args.newgame_every,
                   drop_skipped=not args.keep_skipped_original)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
