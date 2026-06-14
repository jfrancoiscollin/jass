#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Autopsie des parties Jass vs Scan : « capter ce qui nous manque ».

Lit les JSONs produits par `calibrate_vs_scan.py --dump-games-dir` (chaque partie
= openings + fens[] + moves[] + outcome + jass_is_white). Pour CHACUN de nos coups,
on interroge Scan comme ORACLE (profondeur fixe) sur la position : son meilleur coup
et son éval. On en tire :

  1. ACCORD DE COUP  — a-t-on joué le coup de Scan ? ventilé par
       phase (nb de pièces) × présence de rois × tactique (capture dispo) ×
       parties perdues vs gagnées.  → localise OÙ on diverge.
  2. PERTE D'ÉVAL    — si Scan émet un score : « éval jetée » par coup
       = eval(meilleur de Scan) − eval(après notre coup), POV Jass.  → COMBIEN
       et où on saigne. (Best-effort ; sinon on s'en tient à l'accord.)
  3. GALERIE DES PIRES BÉVUES — top-N positions (FEN) où on a le plus dévié /
       perdu, pour inspection humaine (souvent LE motif récurrent saute aux yeux).

Hypothèse à tester en priorité : nos patterns sont men-only → on devrait
s'effondrer DÈS QU'IL Y A DES ROIS et en finale.

Usage:
   python3 tools/game_autopsy.py --games-dir DIR --jass ./build/jass \\
       --scan /root/jass-scan/scan_linux [--scan-depth 11] [--max-games 0] \\
       [--worst 25] [--out report.txt]
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from calibrate_vs_scan import (  # noqa: E402
    ScanEngine, parse_scan_move, parse_jass_fen, jass_fen_to_scan_pos, DONE_RE,
)

SCORE_RE = re.compile(r"score=([+-]?[0-9]+(?:\.[0-9]+)?)")

PHASES = [("opening", 30, 99), ("midgame", 22, 29), ("late-mid", 15, 21),
          ("endgame", 8, 14), ("deep-eg", 0, 7)]


def piece_count(fen: str) -> int:
    _s, wm, wk, bm, bk = parse_jass_fen(fen)
    return len(wm) + len(wk) + len(bm) + len(bk)


def has_king(fen: str) -> bool:
    _s, wm, wk, bm, bk = parse_jass_fen(fen)
    return bool(wk or bk)


def phase_of(fen: str) -> str:
    n = piece_count(fen)
    for name, lo, hi in PHASES:
        if lo <= n <= hi:
            return name
    return "deep-eg"


def is_capture(mv) -> bool:
    return bool(getattr(mv, "captures", ()))


def scan_oracle(scan: ScanEngine, fen: str, depth: int):
    """Best move + eval (Scan's score, side-to-move POV) for a jass FEN."""
    scan._drain()
    scan._send(f"pos pos={jass_fen_to_scan_pos(fen)}")
    scan._send(f"level depth={depth}")
    scan._send("go think")
    try:
        lines = scan._read_until(
            lambda l: l.startswith("done") or l.startswith("error"),
            timeout_s=120.0)
    except TimeoutError:
        return None, None
    if not lines or lines[-1].startswith("error"):
        return None, None
    m = DONE_RE.search(lines[-1])
    mv = parse_scan_move(m.group(1)) if m else None
    score = None
    for ln in lines:                       # last info score before `done`
        sm = SCORE_RE.search(ln)
        if sm:
            score = float(sm.group(1))
    return mv, score


def same_move(a, b) -> bool:
    return a is not None and b is not None and (a.frm, a.to) == (b.frm, b.to)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--games-dir", required=True)
    p.add_argument("--jass", required=True, help="(unused for oracle, kept for symmetry)")
    p.add_argument("--scan", required=True)
    p.add_argument("--scan-depth", type=int, default=11)
    p.add_argument("--scan-bb-size", type=int, default=0)
    p.add_argument("--max-games", type=int, default=0, help="0 = all")
    p.add_argument("--worst", type=int, default=25)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    games = sorted(Path(args.games_dir).glob("game-*.json"))
    if args.max_games:
        games = games[:args.max_games]
    if not games:
        sys.exit(f"no game-*.json in {args.games_dir}")

    scan = ScanEngine(args.scan, label="Scan-oracle",
                      no_book=True, bb_size=args.scan_bb_size)

    # counters[(bucket_key)] = [n_jass_moves, n_agree, sum_loss, n_loss_scored]
    by_phase = defaultdict(lambda: [0, 0, 0.0, 0])
    by_king  = defaultdict(lambda: [0, 0, 0.0, 0])   # key: "kings" / "no-kings"
    by_tac   = defaultdict(lambda: [0, 0, 0.0, 0])   # key: "capture-avail" / "quiet"
    by_res   = defaultdict(lambda: [0, 0, 0.0, 0])   # key: "lost" / "drawn" / "won"
    tot = [0, 0, 0.0, 0]
    worst = []   # (severity, fen, our, scan, phase, kings, loss, game_id, result)

    def bump(c, agree, loss):
        c[0] += 1; c[1] += int(agree)
        if loss is not None:
            c[2] += loss; c[3] += 1

    try:
        for gi, gp in enumerate(games):
            g = json.loads(gp.read_text())
            fens, moves = g.get("fens", []), g.get("moves", [])
            jw, sc = g["jass_is_white"], g.get("jass_score", 0.5)
            res = "won" if sc == 1.0 else ("lost" if sc == 0.0 else "drawn")
            if not fens or not moves:
                continue
            # cache Scan oracle per position (move+score), reused for before/after
            cache = {}
            def oracle(i):
                if i not in cache and 0 <= i < len(fens):
                    cache[i] = scan_oracle(scan, fens[i], args.scan_depth)
                return cache.get(i, (None, None))
            for i in range(len(moves)):
                side = parse_jass_fen(fens[i])[0]
                if (side == "W") != jw:        # not our move
                    continue
                our_mv = parse_scan_move(moves[i])
                sbest, sbefore = oracle(i)
                agree = same_move(our_mv, sbest)
                # eval thrown away (POV Jass) : best vs after-our-move
                loss = None
                if sbefore is not None:
                    _af_mv, safter = oracle(i + 1)
                    if safter is not None:
                        loss = max(0.0, sbefore - (-safter))
                kings = has_king(fens[i])
                ph = phase_of(fens[i])
                cap = is_capture(sbest) or is_capture(our_mv)
                bump(tot, agree, loss)
                bump(by_phase[ph], agree, loss)
                bump(by_king["kings" if kings else "no-kings"], agree, loss)
                bump(by_tac["capture-avail" if cap else "quiet"], agree, loss)
                bump(by_res[res], agree, loss)
                if not agree:
                    sev = (loss if loss is not None else 0.0) \
                        + (5.0 if res == "lost" else 0.0) \
                        + (3.0 if is_capture(sbest) and not is_capture(our_mv) else 0.0)
                    worst.append((sev, fens[i], moves[i],
                                  sbest.jass_str() if sbest else "?",
                                  ph, kings, loss, g.get("game_id", gi), res))
            print(f"  autopsied {gp.name}  ({res}, {len(moves)} plies)", file=sys.stderr)
    finally:
        scan.close()

    def line(key, c):
        rate = c[1] / c[0] if c[0] else 0.0
        avg = (c[2] / c[3]) if c[3] else float("nan")
        return f"  {key:16s} n={c[0]:5d}  accord={rate:.3f}  perte_moy={avg:7.2f}"

    out = []
    out.append("=" * 64)
    out.append("  AUTOPSIE vs SCAN — où et combien on perd (oracle depth "
               f"{args.scan_depth}, {len(games)} parties)")
    out.append("=" * 64)
    out.append(line("GLOBAL", tot))
    out.append("\n-- par PHASE --")
    for name, _lo, _hi in PHASES:
        if name in by_phase: out.append(line(name, by_phase[name]))
    out.append("\n-- par ROIS (hypothèse men-only) --")
    for k in ("no-kings", "kings"):
        if k in by_king: out.append(line(k, by_king[k]))
    out.append("\n-- par TACTIQUE --")
    for k in ("quiet", "capture-avail"):
        if k in by_tac: out.append(line(k, by_tac[k]))
    out.append("\n-- par RÉSULTAT --")
    for k in ("won", "drawn", "lost"):
        if k in by_res: out.append(line(k, by_res[k]))
    out.append(f"\n-- {args.worst} PIRES BÉVUES (FEN · notre coup → coup de Scan · "
               "phase · rois · perte) --")
    for sev, fen, our, sbest, ph, kings, loss, gid, res in \
            sorted(worst, key=lambda x: -x[0])[:args.worst]:
        ls = f"{loss:.1f}" if loss is not None else "  ?"
        out.append(f"  g{gid:<3d}[{res:5s}] {ph:8s} {'K' if kings else ' '} "
                   f"perte={ls:>5s}  {our:>9s} → {sbest:<9s}  {fen}")
    report = "\n".join(out)
    print(report)
    if args.out:
        Path(args.out).write_text(report + "\n")
        print(f"\nrapport écrit : {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
