#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Étape (6) — SPARRING vs Scan : générer des positions labellées par l'ISSUE RÉELLE
de parties jass(champion) CONTRE Scan (adversaire plus fort).

Contrairement au self-play (labels auto-référentiels → plafond), ici jass joue vs
Scan et CHAQUE position visitée est labellée par le résultat de la partie (WDL,
stm-POV). Parties en PAIRES ÉQUILIBRÉES-COULEUR (jass blanc/Scan noir, puis
Scan blanc/jass noir) depuis chaque opening.

Sortie : JNNW (score=0, wdl=issue). Distiller avec `wdl_finetune --target wdl`
(le rééquilibrage de classes W/D/L se fait au FIT, pas ici).

Réutilise le player Scan + le referee jass de calibrate_vs_scan et l'encodeur de
record 38 o de scan_selfplay_gen (importés — le blob de ces outils est inchangé).
"""
from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv          # noqa: E402  JassEngine/ScanEngine/Referee/play_game
import scan_selfplay_gen as ssg         # noqa: E402  fen_to_record / record_to_fen (38 o)

REC = 38
WMAP = {"W": 1, "D": 0, "L": -1}


def load_seed_fens(path: Path, min_pieces: int) -> list[str]:
    """Lit un JNNW de seeds → FENs (>= min_pieces pièces), via l'décodeur partagé."""
    raw = path.read_bytes()
    if raw[:4] != b"JNNW":
        raise SystemExit(f"{path}: magic JNNW invalide")
    n = struct.unpack("<I", raw[4:8])[0]
    body = raw[8:]
    if len(body) != n * REC:
        raise SystemExit(f"{path}: taille invalide ({len(body)} != {n * REC})")
    fens = []
    for i in range(n):
        fen, pc = ssg.record_to_fen(body[i * REC:(i + 1) * REC])
        if pc >= min_pieces:
            fens.append(fen)
    return fens


def wdl_stm_from_outcome(fen: str, outcome: str) -> int:
    """Issue blanc-POV ("W"/"D"/"L") → WDL du côté au trait dans `fen`."""
    wdl_white = WMAP[outcome]
    if wdl_white == 0:
        return 0
    return wdl_white if fen[0] == "W" else -wdl_white


def game_records(fens: list[str], outcome: str, sample_every: int) -> bytearray:
    out = bytearray()
    for i in range(0, len(fens), max(1, sample_every)):
        out += ssg.fen_to_record(fens[i], wdl_stm_from_outcome(fens[i], outcome))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jass", required=True, help="binaire jass (referee ET player-champion)")
    ap.add_argument("--player-pattern", required=True, help="pattern .pjtw du champion jass")
    ap.add_argument("--scan", required=True, help="binaire Scan (adversaire fort)")
    ap.add_argument("--seeds", required=True, type=Path, help="JNNW d'openings à échantillonner")
    ap.add_argument("--out", required=True, type=Path, help="JNNW de sortie (positions vs Scan)")
    ap.add_argument("--games", type=int, default=400, help="nb d'OPENINGS ; 2 parties/opening (couleurs)")
    ap.add_argument("--depth", type=int, default=9, help="profondeur FIXE des deux côtés (méthodo)")
    ap.add_argument("--max-plies", type=int, default=200)
    ap.add_argument("--min-pieces", type=int, default=30, help="plancher pièces des seeds")
    ap.add_argument("--sample-every", type=int, default=1, help="garder 1 position sur N")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--progress-every", type=int, default=25)
    a = ap.parse_args(argv)

    import random
    rng = random.Random(a.seed + a.shard)
    seeds = load_seed_fens(a.seeds, a.min_pieces)
    if not seeds:
        raise SystemExit("aucun seed >= min_pieces")
    rng.shuffle(seeds)
    seeds = seeds[a.shard::a.nshards][:a.games]
    print(f"sparring vs Scan: {len(seeds)} openings (shard {a.shard}/{a.nshards}), "
          f"champion={a.player_pattern}, depth={a.depth}", flush=True)

    jass = cv.JassEngine(a.jass, label="Jass-champion", pattern_path=a.player_pattern)
    scan = cv.ScanEngine(a.scan, label="Scan", bb_size=0)
    referee = cv.Referee(a.jass)

    records = bytearray()
    n_pos = 0
    w = d = l = 0  # issues jass-POV (agrégat sanity)
    t0 = time.time()
    try:
        for gi, opening in enumerate(seeds):
            for jass_is_white in (True, False):
                white, black = (jass, scan) if jass_is_white else (scan, jass)
                try:
                    r = cv.play_game(white, black, referee, opening,
                                     depth=a.depth, max_plies=a.max_plies)
                except Exception as exc:  # noqa: BLE001 — un jeu bancal ne gèle pas le shard
                    print(f"  game {gi}: {exc}", file=sys.stderr, flush=True)
                    continue
                fens = list(getattr(r, "fens", []))
                if not fens:
                    continue
                records += game_records(fens, r.outcome, a.sample_every)
                n_pos = len(records) // REC
                # sanity issue jass-POV
                jp = 0.5 if r.outcome == "D" else (
                    1.0 if (r.outcome == "W") == jass_is_white else 0.0)
                w += jp == 1.0; d += jp == 0.5; l += jp == 0.0
            if a.progress_every and (gi + 1) % a.progress_every == 0:
                el = time.time() - t0
                print(f"  {gi + 1}/{len(seeds)} openings, {n_pos} pos, "
                      f"jass W/D/L={w}/{d}/{l}  [{el:.0f}s]", flush=True)
    finally:
        jass.close(); scan.close(); referee.close()

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(b"JNNW" + struct.pack("<I", n_pos) + bytes(records))
    tot = w + d + l
    rate = (w + 0.5 * d) / tot if tot else 0.0
    print(f"=== SPARRING vs Scan : {n_pos} positions, {tot} parties, "
          f"jass score-rate {rate:.3f} (W={w} D={d} L={l}) → {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
