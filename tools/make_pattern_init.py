#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
G4 self-play bootstrap — create a fresh JPAT v5 PatternNetwork with
handcrafted-like skeleton init and zero patterns, ready to play the
first self-play iteration.

Layout: pattern v2 (16 patterns × 8 squares, base-3) + hybrid skeleton
(material/king count, balance, king PST) + skeleton phase split (MG/EG).

Init values match a basic handcrafted eval: man_value=100,
king_value=300 (both phases), balance/PST/patterns = 0. The first
self-play iteration with this net plays like pure material counting
— weak but informative WDL labels for training the next iteration.

Usage:
    python3 tools/make_pattern_init.py --out pattern-v0.jpat \\
        [--init-man 100] [--init-king 300]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reuse train_pattern's model + saver for consistency.
sys.path.insert(0, str(Path(__file__).parent))
from train_pattern import (HybridPatternModel, PATTERN_SETS,  # noqa: E402
                           save_jpat)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", required=True, type=Path,
                   help="output JPAT v5 file")
    p.add_argument("--patterns", choices=list(PATTERN_SETS.keys()), default="v2",
                   help="pattern geometry: v1/v2 (block) or v3 (Scan vertical strips)")
    p.add_argument("--init-man",  type=float, default=100.0)
    p.add_argument("--init-king", type=float, default=300.0)
    args = p.parse_args(argv)

    patterns = PATTERN_SETS[args.patterns]
    model = HybridPatternModel(
        patterns,
        base=3,
        init_man=args.init_man,
        init_king=args.init_king,
        extras=True,
        phase_split=True,
    )
    # EG counterparts mirror MG so the starter net is mono-phase
    # (interpolation reduces to acc_mg). The self-play loop's subsequent
    # iterations will let the trainer deviate EG from MG as it sees fit.
    import torch
    with torch.no_grad():
        model.man_value_eg.copy_(model.man_value)
        model.king_value_eg.copy_(model.king_value)

    save_jpat(model, patterns, args.out)
    sz = args.out.stat().st_size
    print(f"wrote {args.out} ({sz} bytes, JPAT v5 init "
          f"patterns={args.patterns} man={args.init_man} king={args.init_king})",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
