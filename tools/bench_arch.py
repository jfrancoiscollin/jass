#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
End-to-end bench of a candidate NNUE network against Scan.

Usage
-----
    # Bench an already-quantised JNNQ:
    python3 tools/bench_arch.py \\
        --model trained_v3/nnue-256-128-q.bin \\
        --jass  ./build/jass \\
        --scan  /path/to/scan/scan \\
        --movetime 1.0 --pairs 1

    # Bench a JNNM directly (auto-quantises first using --data):
    python3 tools/bench_arch.py \\
        --model trained_v3/nnue-256-128.bin \\
        --data  selfplay-wdl.bin \\
        --jass  ./build/jass --scan /path/to/scan/scan

What it does
------------
1. Sniffs the model's 4-byte magic.
   * `JNNQ` → run as-is.
   * `JNNM` → call `tools/quantize_mlp.py` to produce a temp JNNQ,
              using `--data` as the calibration slice.
   * Anything else → forwarded as-is and assumed to be a LinearNetwork.
2. Spawns `tools/calibrate_vs_scan.py` with `--nnue <model>`, capturing
   the per-game output and the final ELO summary.
3. Prints a compact one-block summary so the result fits in a chat /
   notification: arch (from the JNNM/JNNQ header), score rate, ELO.

The whole point is that Cycle-5 ("is this trained network actually
better than the previous one?") becomes a one-command turnaround
once `train_v3.py` picks a winner.
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


MAGIC_JNNM = b"JNNM"
MAGIC_JNNQ = b"JNNQ"

TOOLS_DIR = Path(__file__).resolve().parent


def sniff_magic(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read(4)


def read_header_dims(path: Path) -> tuple[int, int, int] | None:
    """Return (input_dim, hidden1, hidden2) for a JNNM/JNNQ file, or
    None for any other format. Both formats put the same 5 uint32 at
    the same offsets, so one reader covers both."""
    with path.open("rb") as f:
        raw = f.read(24)
    if len(raw) < 24:
        return None
    if raw[:4] not in (MAGIC_JNNM, MAGIC_JNNQ):
        return None
    _ver, in_dim, h1, h2, _out = struct.unpack_from("<IIIII", raw, 4)
    return (in_dim, h1, h2)


def quantise(model: Path, data: Path, out: Path) -> None:
    cmd = [
        sys.executable,
        str(TOOLS_DIR / "quantize_mlp.py"),
        "--in",  str(model),
        "--data", str(data),
        "--out",  str(out),
    ]
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        sys.exit(f"quantize_mlp.py failed (exit {r.returncode})")


# Match the last "ELO estimate: ..." line emitted by calibrate_vs_scan.
ELO_RE   = re.compile(r"^\s*ELO estimate:\s*([+-]?\d+)\s*\(95%.*?±(\d+)")
RATE_RE  = re.compile(r"^\s*Jass score rate:\s*([\d.]+)\s*\(([\d.]+)\s*/\s*(\d+)\)")
SCORE_RE = re.compile(r"^\s*Jass=(\d+)\s+Scan=(\d+)\s+Draws=(\d+)")


def run_calibration(jass: Path, scan: Path, nnue: Path,
                    movetime: float | None, depth: int | None,
                    pairs: int, max_plies: int) -> dict:
    cmd = [
        sys.executable,
        str(TOOLS_DIR / "calibrate_vs_scan.py"),
        "--jass",  str(jass),
        "--scan",  str(scan),
        "--nnue",  str(nnue),
        "--pairs", str(pairs),
        "--max-plies", str(max_plies),
    ]
    if movetime is not None:
        cmd += ["--movetime", str(movetime)]
    elif depth is not None:
        cmd += ["--depth", str(depth)]
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)

    result: dict = {}
    assert proc.stdout is not None
    for line in proc.stdout:
        # Stream the calibration's per-game log straight through so the
        # operator can watch progress.
        print(line, end="")
        if (m := ELO_RE.match(line)):
            result["elo"] = int(m.group(1))
            result["ci"]  = int(m.group(2))
        elif (m := RATE_RE.match(line)):
            result["rate"]  = float(m.group(1))
            result["score"] = float(m.group(2))
            result["games"] = int(m.group(3))
        elif (m := SCORE_RE.match(line)):
            result["wins"]   = int(m.group(1))
            result["losses"] = int(m.group(2))
            result["draws"]  = int(m.group(3))
    proc.wait()
    if proc.returncode != 0:
        sys.exit(f"calibrate_vs_scan.py failed (exit {proc.returncode})")
    if "elo" not in result:
        sys.exit("calibrate_vs_scan.py did not emit a recognised ELO line")
    return result


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--model", type=Path, required=True,
                   help="JNNM (float) or JNNQ (quantised) network to bench")
    p.add_argument("--data", type=Path,
                   help="JNNW/JNNT dataset for the JNNM → JNNQ calibration "
                        "step (required if --model is a JNNM)")
    p.add_argument("--jass", type=Path, default=Path("./build/jass"))
    p.add_argument("--scan", type=Path, required=True,
                   help="path to the Scan binary")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--depth",    type=int)
    g.add_argument("--movetime", type=float, default=1.0,
                   help="per-move budget in seconds (default 1.0)")
    p.add_argument("--pairs", type=int, default=1,
                   help="colour-swap pairs per opening (total = 18 × pairs)")
    p.add_argument("--max-plies", type=int, default=200)
    p.add_argument("--keep-quantised", action="store_true",
                   help="don't delete the temporary JNNQ produced from a "
                        "JNNM input (useful to inspect after the bench)")
    args = p.parse_args(argv)

    model = args.model.resolve()
    if not model.exists():
        sys.exit(f"--model {model} does not exist")
    if not args.jass.exists():
        sys.exit(f"--jass {args.jass} does not exist (try cmake --build build)")
    if not args.scan.exists():
        sys.exit(f"--scan {args.scan} does not exist")

    magic = sniff_magic(model)
    dims = read_header_dims(model)
    arch_str = f"{dims[1]}-{dims[2]}" if dims else "?"
    print(f"=== bench {model.name} (magic={magic!r}, arch={arch_str}) ===")

    quant_tmp: Path | None = None
    if magic == MAGIC_JNNM:
        if args.data is None:
            sys.exit("--data is required when --model is a JNNM file")
        tmpdir = Path(tempfile.mkdtemp(prefix="bench-arch-"))
        quant_tmp = tmpdir / f"{model.stem}-q.bin"
        quantise(model, args.data, quant_tmp)
        bench_model = quant_tmp
    elif magic == MAGIC_JNNQ:
        bench_model = model
    else:
        # Pass through anything else as-is — the engine's load_network
        # will treat unknown magic as a LinearNetwork.
        print(f"  (unknown magic, passing through as Linear)")
        bench_model = model

    res = run_calibration(
        jass=args.jass, scan=args.scan, nnue=bench_model,
        movetime=args.movetime, depth=args.depth,
        pairs=args.pairs, max_plies=args.max_plies,
    )

    if quant_tmp is not None and not args.keep_quantised:
        try:
            quant_tmp.unlink()
            quant_tmp.parent.rmdir()
        except OSError:
            pass

    print()
    print("┌─ bench summary " + "─" * 40)
    print(f"│ model       {model.name}")
    print(f"│ arch        {arch_str}")
    if quant_tmp is not None:
        print(f"│ quantised   {bench_model.name}"
              f"{' (kept)' if args.keep_quantised else ' (deleted)'}")
    budget = (f"movetime {args.movetime}s" if args.movetime else f"depth {args.depth}")
    print(f"│ budget      {budget}")
    print(f"│ games       {res.get('games', '?')}")
    print(f"│ W/D/L       {res.get('wins', '?')}/{res.get('draws', '?')}/{res.get('losses', '?')}")
    print(f"│ rate        {res.get('rate', 0.0):.3f}")
    print(f"│ ELO vs Scan {res['elo']:+d} (±{res.get('ci', '?')})")
    print("└" + "─" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
