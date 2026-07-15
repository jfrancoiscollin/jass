#!/usr/bin/env python3
"""B3 (v2, défenseur-fixe) — conv_self : instrument PUR de compétence de CONVERSION (escalier d'adjud, L3).

⚠ v1 (self-play) était CONFONDU (gate 0708 : aveugle 0.88 > gen2 0.75 — une éval forte a une défense
forte + plus de nulles → conv_self BAS ; anti-corrélé à la force → ferait fader l'adjud TROP TÔT = échec
0702). **Fix (JFC) : défenseur FIXE fort.** Le champion testé joue le camp qui a l'AVANTAGE matériel d'une
position GAGNÉE du pool ; un **défenseur fixe fort** (gen2-mmto) joue la défense. Défense constante ⟹
conv_self = P(le champion convertit la position gagnée) ⟹ **monotone en force** (un champion plus fort
convertit plus des MÊMES positions vs le MÊME défenseur). Critère escalier : conv_self ≥ 70-75 % → cran.
Le pool de positions gagnées (|Δ pièces| ≥ lead) converge avec le gymnase B2.

Réutilise ``calibrate_vs_scan.play_game`` (adjud-OFF). Sharding par index de position. Jamais fité.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_vs_scan as cv


def _pieces(fen: str) -> tuple[int, int]:
    try:
        _, wpart, bpart = fen.split(":")
    except ValueError:
        return (0, 0)
    def cnt(part: str) -> int:
        body = part[1:] if part[:1] in ("W", "B") else part
        return sum(1 for tok in body.split(",") if tok.strip())
    return cnt(wpart), cnt(bpart)


def load_pool(path: str):
    """Pool de positions gagnées : FEN par ligne (commentaires # tolérés)."""
    out = []
    for ln in open(path):
        fen = ln.split("#", 1)[0].strip()
        if fen:
            out.append(fen)
    return out


def measure(jass_bin, champ_pat, def_pat, pool, depth, movetime, max_plies, lead,
            shard=0, nshards=1):
    champ = cv.JassEngine(jass_bin, pattern_path=champ_pat)
    defender = cv.JassEngine(jass_bin, pattern_path=def_pat)
    referee = cv.Referee(jass_bin)
    n_pos = n_win = n_draw = n_loss = 0
    for i, fen in enumerate(pool):
        if i % nshards != shard:
            continue
        w, b = _pieces(fen)
        adv = "W" if (w - b) >= lead else ("B" if (b - w) >= lead else None)
        if adv is None:
            continue                       # position pas assez gagnée (garde)
        # le CHAMPION joue le camp avantagé ; le DÉFENSEUR FIXE joue l'autre
        white, black = (champ, defender) if adv == "W" else (defender, champ)
        try:
            kw = {"movetime": movetime} if movetime else {"depth": depth}
            r = cv.play_game(white, black, referee, fen, max_plies=max_plies, **kw)
        except Exception as exc:  # noqa: BLE001
            print(f"  pos {i}: {exc}", file=sys.stderr)
            continue
        n_pos += 1
        champ_won = (adv == "W" and r.outcome == "W") or (adv == "B" and r.outcome == "L")
        if r.outcome == "D":
            n_draw += 1
        elif champ_won:
            n_win += 1
        else:
            n_loss += 1
    champ.close(); defender.close(); referee.close()
    conv = (n_win / n_pos) if n_pos else float("nan")
    return {
        "conv_self": None if n_pos == 0 else round(conv, 4),
        "n_pos": n_pos, "n_win": n_win, "n_draw": n_draw, "n_loss": n_loss,
        "lead_threshold": lead, "depth": depth, "movetime": movetime,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jass", required=True)
    ap.add_argument("--pattern", required=True, help="champion TESTÉ (joue le camp avantagé)")
    ap.add_argument("--defender-pattern", required=True, help="défenseur FIXE fort (gen2-mmto)")
    ap.add_argument("--pool-file", required=True, help="FEN de positions gagnées (|Δ pièces|≥lead)")
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--movetime", type=float, default=None)
    ap.add_argument("--max-plies", type=int, default=260)
    ap.add_argument("--lead", type=int, default=3, help="avantage matériel min (pièces) du pool")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    pool = load_pool(a.pool_file)
    if not pool:
        sys.exit("ABORT: pool vide")
    res = measure(a.jass, a.pattern, a.defender_pattern, pool, a.depth, a.movetime,
                  a.max_plies, a.lead, a.shard, a.nshards)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
