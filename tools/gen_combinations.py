#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Depth-GRADED combination generator + detector (JFC 2026-07-01).

Goal : build a curriculum/gauge of FORCED combinations of CONTROLLED complexity
(2..12 tempi) from imbalanced games, verified by a strong oracle (Scan deep +
egdb), so we can (a) MEASURE jass's tactical detection near-certainly by depth
and (b) feed the eval with combination-rich positions at a controlled quantity
per length.

Combination (JFC-chosen definition) : the side to move plays a SACRIFICE or
forcing non-capturing 1st move, then a FORCED line yields a NET material gain
>= +1 man (or a safe promotion to king). "Forced" = it holds under the oracle's
best defence.

Grading by D_min (scale-FREE) : D_min = the shallowest oracle depth whose best
move equals the combination's 1st move — i.e. the depth at which the payoff
first becomes visible. A 2-tempi combo shows at d2 ; a 12-tempi combo needs d12.
That D_min IS the complexity bin, and it is exactly the depth jass must reach to
detect it (time-agnostic : search deep enough).

This module is oracle-agnostic : the Scan/egdb driving lives in ScanOracle (a
thin HUB adapter, validated on-box), while the pure CLASSIFIER (material
trajectory -> is-combo / gain / sac, and D_min from a per-depth move map) is
unit-tested here with a mock oracle (`--self-test`).
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

KING_VAL = 3            # a king ≈ 3 men for the material-gain threshold (matches gen recipes)
DEEP_DEFAULT = 20       # oracle "ground-truth" depth for the forced line
MAXTEMPI_DEFAULT = 12   # grade combos of length 2..12
GAIN_THRESH = 1         # net material gain (men-equivalents) that qualifies as a combination


# --------------------------------------------------------------------------- #
#  Pure, scale-free classifier (UNIT-TESTED ; no engine needed).
# --------------------------------------------------------------------------- #
@dataclass
class ComboVerdict:
    is_combo: bool
    tempi: int              # forced-line length in plies (D of the payoff)
    gain: int              # net material gain for the mover (men-equivalents)
    sacrificed: bool       # material dipped below the start (a real sacrifice)
    d_min: int             # shallowest oracle depth that picks the combo's 1st move
    reason: str
    first_move: str = ""   # the combination's winning 1st move (jass 'from-to'), for the detection test


def classify_combo(net_traj: list[int], first_move_is_capture: bool,
                   move_by_depth: dict[int, bool], max_tempi: int,
                   gain_thresh: int = GAIN_THRESH) -> ComboVerdict:
    """Classify from SCALE-FREE signals :
      net_traj[k] = mover-POV net material AFTER k plies of the oracle's forced
                    line (net_traj[0] = at the position, mover to move) ;
      first_move_is_capture = was the mover's 1st move a capture? (non-capture or
                    material-losing 1st move => candidate sacrifice) ;
      move_by_depth[d] = True iff the oracle's best move at depth d equals the
                    combo's 1st move (the deep line's 1st move).
    A combination requires : (1) net gain >= gain_thresh at the forced-line end
    AND (2) the line either DIPS below the start (a sacrifice) or opens with a
    forcing NON-capture (first_move_is_capture is False). D_min = min d with
    move_by_depth[d] True (else the deepest tried)."""
    if not net_traj or len(net_traj) < 2:
        return ComboVerdict(False, 0, 0, False, 0, "no line")
    start = net_traj[0]
    line_len = min(len(net_traj) - 1, max_tempi)
    end = net_traj[line_len]
    gain = end - start
    dipped = min(net_traj[1:line_len + 1]) < start
    # combination LENGTH in tempi = the ply at which the net gain is first REALISED
    # (material won and kept), NOT the full played-out line. This is the "N temps"
    # JFC grades by (a sac→recapture combo lands when the material comes back). D_min
    # (the oracle's detection depth) is kept as separate metadata.
    tempi = next((k for k in range(1, line_len + 1) if net_traj[k] >= start + gain_thresh),
                 line_len)
    sacrificed = dipped or (not first_move_is_capture and gain >= gain_thresh)
    d_hits = sorted(d for d, hit in move_by_depth.items() if hit)
    d_min = d_hits[0] if d_hits else (max(move_by_depth) if move_by_depth else tempi)
    if gain < gain_thresh:
        return ComboVerdict(False, tempi, gain, dipped, d_min, f"gain {gain} < {gain_thresh}")
    if not sacrificed:
        return ComboVerdict(False, tempi, gain, dipped, d_min,
                            "won material with a plain capture (not a combination)")
    if not (2 <= tempi <= max_tempi):
        return ComboVerdict(False, tempi, gain, dipped, d_min, f"tempi {tempi} out of [2,{max_tempi}]")
    return ComboVerdict(True, tempi, gain, sacrificed, d_min, "ok")


# --------------------------------------------------------------------------- #
#  FEN material (scale-free ground truth from the board).
# --------------------------------------------------------------------------- #
def net_material_stmpov(fen: str) -> int:
    """mover-POV net material (men + KING_VAL·kings), from a jass/FMJD FEN
    'W:Wa,b,Kc:Bd,Ke'. Positive = mover is up material."""
    from calibrate_vs_scan import parse_jass_fen
    stm, wm, wk, bm, bk = parse_jass_fen(fen)
    white = len(wm) + KING_VAL * len(wk)
    black = len(bm) + KING_VAL * len(bk)
    net_white = white - black
    return net_white if stm == "W" else -net_white


# --------------------------------------------------------------------------- #
#  Scan+egdb oracle adapter (thin ; validated on-box by the 0528 job).
# --------------------------------------------------------------------------- #
class ScanOracle:
    """Drives Scan (HUB) for depth-controlled best moves and a jass Referee to
    apply moves / read FENs (material). egdb, if the jass build has it, makes the
    <=7-piece tail exact. Kept small : the interesting logic is the classifier."""
    def __init__(self, scan_bin: str, jass_bin: str, deep: int = DEEP_DEFAULT):
        from calibrate_vs_scan import ScanEngine, Referee
        self.scan = ScanEngine(scan_bin, bb_size=0)
        self.ref = Referee(jass_bin)
        self.deep = deep

    def best_move_at(self, fen: str, depth: int):
        """Scan's best move (jass 'from-to' string) at a fixed depth, or None."""
        self.ref.set_position_fen(fen)
        sp, hist = self.ref.scan_pos()
        mv = self.scan.go_from(sp, hist, depth=depth)
        return mv.jass_str() if mv is not None else None

    def forced_line(self, fen: str, max_plies: int):
        """Play the oracle's deep best line for up to max_plies ; return
        (net_traj[mover-POV, len<=max_plies+1], first_move_is_capture)."""
        self.ref.set_position_fen(fen)
        net_traj = [net_material_stmpov(fen)]
        first_cap = None
        mover_is_white = fen.strip()[0].upper() == "W"
        for _ply in range(max_plies):
            sp, hist = self.ref.scan_pos()
            mv = self.scan.go_from(sp, hist, depth=self.deep)
            if mv is None:
                break
            if first_cap is None:
                first_cap = mv.is_capture         # property, not a method
            if not self.ref.apply_move(mv):
                break
            fen_now = self.ref.current_fen()
            net_now = net_material_stmpov(fen_now)
            # normalise every entry to the ORIGINAL mover's POV.
            now_is_white = fen_now.strip()[0].upper() == "W"
            net_traj.append(net_now if (now_is_white == mover_is_white) else -net_now)
        return net_traj, bool(first_cap)

    def close(self):
        try: self.scan.close()
        except Exception: pass
        try: self.ref.close()
        except Exception: pass


def analyse_position(oracle: ScanOracle, fen: str, max_tempi: int,
                     with_dmin: bool = False) -> ComboVerdict:
    """Full pipeline for one candidate FEN : forced line -> material trajectory,
    then D_min via per-depth move-match, then classify."""
    net_traj, first_cap = oracle.forced_line(fen, max_tempi)
    if len(net_traj) < 2:
        return ComboVerdict(False, 0, 0, False, 0, "no oracle line")
    combo_first = oracle.best_move_at(fen, oracle.deep)      # the deep line's 1st move
    # D_min (oracle detection depth) is METADATA since we grade by tempi ; the 12
    # per-depth probes are the cost bottleneck, so skip them unless with_dmin.
    move_by_depth = {}
    if with_dmin:
        for d in range(1, max_tempi + 1):
            bm = oracle.best_move_at(fen, d)
            move_by_depth[d] = (bm is not None and combo_first is not None and bm == combo_first)
    v = classify_combo(net_traj, first_cap, move_by_depth, max_tempi)
    v.first_move = combo_first or ""
    return v


# --------------------------------------------------------------------------- #
#  Candidate feed : FENs from a file (one per line) or a JNNW corpus.
# --------------------------------------------------------------------------- #
def iter_fens_from_file(path: str):
    for ln in open(path):
        b = ln.split('#', 1)[0].strip()
        if b:
            yield b


def iter_fens_from_jnnw(path: str, max_records: int = 0, start: int = 0,
                        piece_lo: int = 0, piece_hi: int = 50):
    """Yield FENs from a JNNW corpus in [start, start+max_records), optionally
    filtered to a piece-count window (for midgame-combo candidates). `start`
    enables sharding across parallel generator instances."""
    raw = open(path, 'rb').read()
    if raw[:4] != b'JNNW':
        raise SystemExit(f'{path}: not JNNW')
    total = struct.unpack_from('<I', raw, 4)[0]
    end = total if not max_records else min(start + max_records, total)
    REC = 38
    for i in range(start, end):
        o = 8 + i * REC
        wm, wk, bm, bk = struct.unpack_from('<QQQQ', raw, o)
        stm = raw[o + 32]
        pc = bin(wm).count('1') + bin(wk).count('1') + bin(bm).count('1') + bin(bk).count('1')
        if not (piece_lo <= pc <= piece_hi):
            continue
        sl = lambda bb: [s + 1 for s in range(50) if (bb >> s) & 1]
        W = [str(s) for s in sl(wm)] + [f"K{s}" for s in sl(wk)]
        B = [str(s) for s in sl(bm)] + [f"K{s}" for s in sl(bk)]
        yield f"{'W' if stm == 0 else 'B'}:W{','.join(W)}:B{','.join(B)}"


# --------------------------------------------------------------------------- #
#  Self-test of the pure classifier (no engine).
# --------------------------------------------------------------------------- #
def _self_test():
    # 4-tempi combo : sac a man (start 0 -> -1) then win 2 back (net +1), 1st move
    # a non-capture forcing move ; oracle sees it only from depth 4.
    v = classify_combo([0, -1, -1, 1, 1], first_move_is_capture=False,
                        move_by_depth={1: False, 2: False, 3: False, 4: True, 5: True},
                        max_tempi=12)
    # gain realised at ply 3 (net back to +1) => tempi=3 ; oracle sees it at d4 => d_min=4.
    assert v.is_combo and v.tempi == 3 and v.gain == 1 and v.sacrificed and v.d_min == 4, v
    # plain capture-up (won a hanging man, no sac) : NOT a combination.
    v = classify_combo([0, 1, 1], first_move_is_capture=True,
                        move_by_depth={1: True, 2: True}, max_tempi=12)
    assert not v.is_combo and 'plain capture' in v.reason, v
    # sac that never regains : NOT a combination (gain 0).
    v = classify_combo([0, -1, -1, 0], first_move_is_capture=False,
                        move_by_depth={2: True}, max_tempi=12)
    assert not v.is_combo and 'gain' in v.reason, v
    # deep 11-tempi combo : D_min at the edge of the window.
    v = classify_combo([0, -2] + [-2] * 9 + [2], first_move_is_capture=False,
                        move_by_depth={d: (d >= 11) for d in range(1, 13)}, max_tempi=12)
    assert v.is_combo and v.tempi == 11 and v.d_min == 11 and v.gain == 2, v
    # king-gain via promotion sac counts (KING_VAL) : start 0 -> sac -1 -> +3 (a king).
    v = classify_combo([0, -1, 3], first_move_is_capture=False,
                        move_by_depth={2: True}, max_tempi=12)
    assert v.is_combo and v.gain == 3 and v.tempi == 2, v
    print("gen_combinations self-test: ALL PASS")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--self-test', action='store_true', help='run the pure-classifier unit tests and exit')
    ap.add_argument('--scan', help='scan_linux binary (oracle)')
    ap.add_argument('--jass', help='jass binary (referee ; egdb build for the <=7 tail)')
    ap.add_argument('--fens', help='candidate FENs, one per line')
    ap.add_argument('--jnnw', help='candidate positions from a JNNW corpus')
    ap.add_argument('--max-records', type=int, default=0)
    ap.add_argument('--start', type=int, default=0, help='JNNW shard start offset (parallel gen)')
    ap.add_argument('--with-dmin', action='store_true',
                    help='also probe the oracle at each depth for D_min metadata (slow ; grading '
                         'is by tempi regardless)')
    ap.add_argument('--piece-lo', type=int, default=0, help='min pieces (midgame candidate filter)')
    ap.add_argument('--piece-hi', type=int, default=50, help='max pieces')
    ap.add_argument('--deep', type=int, default=DEEP_DEFAULT, help='oracle ground-truth depth')
    ap.add_argument('--max-tempi', type=int, default=MAXTEMPI_DEFAULT, help='grade combos 2..this')
    ap.add_argument('--per-bin', type=int, default=0, help='stop once every D_min bin has this many (0=all candidates)')
    ap.add_argument('--out-fens', help='write graded combo FENs here (with # D_min=.. gain=.. tempi=..)')
    ap.add_argument('--limit', type=int, default=0, help='cap #candidates scanned (0=all)')
    args = ap.parse_args(argv)

    if args.self_test:
        _self_test(); return 0
    if not (args.scan and args.jass and (args.fens or args.jnnw)):
        ap.error('need --scan --jass and one of --fens/--jnnw (or --self-test)')

    cand = (iter_fens_from_file(args.fens) if args.fens else
            iter_fens_from_jnnw(args.jnnw, args.max_records, args.start, args.piece_lo, args.piece_hi))
    oracle = ScanOracle(args.scan, args.jass, deep=args.deep)
    bins: dict[int, list] = {n: [] for n in range(2, args.max_tempi + 1)}
    out = open(args.out_fens, 'w') if args.out_fens else None
    scanned = kept = 0
    try:
        for fen in cand:
            if args.limit and scanned >= args.limit:
                break
            scanned += 1
            v = analyse_position(oracle, fen, args.max_tempi, with_dmin=args.with_dmin)
            if not v.is_combo:
                continue
            if args.per_bin and len(bins[v.tempi]) >= args.per_bin:
                continue
            bins[v.tempi].append(fen); kept += 1
            if out:
                out.write(f"{fen}  # D_min={v.d_min} gain={v.gain} tempi={v.tempi} "
                          f"sac={v.sacrificed} win={v.first_move}\n"); out.flush()
            if args.per_bin and all(len(bins[n]) >= args.per_bin for n in bins):
                break
    finally:
        oracle.close()
        if out: out.close()
    print(f"scanned={scanned} kept={kept}")
    for n in range(2, args.max_tempi + 1):
        print(f"  {n:2d} tempi : {len(bins[n])} combos")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
