#!/usr/bin/env python3
"""B2 — construit le pool de positions GAGNÉES du gymnase TB-adjacent (L3, trou conversion 0703).

Le gymnase entraîne la CONVERSION : trajectoires démarrées sur des positions gagnées, labels
rendus EXACTS par TB-terminate (la trajectoire plonge dans la base en quelques plies) → exacts
quelle que soit la maladresse du pilote. **Distinction mécanique vs B1-ensemencement (mort)** :
là le générateur ne savait pas DÉMONTRER la combinaison → labels menteurs ; ICI l'oracle terminal
(TB) protège le label. Ce script bâtit le POOL (offline) ; le gymnase = gen `--seed-pool` + pairing.

Sources du pool :
  1. **Oracles certifiés WON (0699)** : `oracles_verified.jsonl` (tb_verdict==WIN) ⋈ `pcblues_oracles.jsonl`
     (position_hash → fen). = finales gagnées vérifiées-TB.
  2. **Near-TB échantillonnées** : positions d'un corpus JNNW à N_TB+1 / N_TB+2 pièces (≤ tb+2, ≥ tb+1)
     avec avantage matériel ≥ lead (proche-TB → conversion plonge vite ; vérité = TB-terminate au gen).
  3. **Assertion `pool ∩ thermomètre-224 = ∅`** (intégrité de l'instrument, gelée) — dédup FEN canonique.

Sortie : `conversion_pool.fen` (FEN par ligne + commentaire source/side avantagé) + stats.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


def canon(fen: str) -> str:
    """FEN canonique (listes de pièces triées) pour dédup / disjonction exacte."""
    try:
        stm, wp, bp = fen.split(":")
    except ValueError:
        return fen.strip()
    def norm(part):
        body = part[1:] if part[:1] in ("W", "B") else part
        toks = [t.strip() for t in body.split(",") if t.strip()]
        # trie par (est-dame, numéro) pour un ordre stable
        def key(t):
            k = t[0] == "K"
            return (k, int(t[1:] if k else t))
        return ",".join(sorted(toks, key=key))
    return f"{stm.strip()[:1]}:W{norm(wp)}:B{norm(bp)}"


def pieces(fen: str) -> tuple[int, int]:
    try:
        _, wp, bp = fen.split(":")
    except ValueError:
        return (0, 0)
    def cnt(p):
        body = p[1:] if p[:1] in ("W", "B") else p
        return sum(1 for t in body.split(",") if t.strip())
    return cnt(wp), cnt(bp)


def adv_side(fen: str, lead: int) -> str | None:
    w, b = pieces(fen)
    if w - b >= lead:
        return "W"
    if b - w >= lead:
        return "B"
    return None


def _rec_fen(rec: bytes) -> str:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    def sqs(v):
        return [s for s in range(1, 51) if (v >> (s - 1)) & 1]
    Wl = [f"K{s}" for s in sqs(wk)] + [str(s) for s in sqs(wm)]
    Bl = [f"K{s}" for s in sqs(bm)] + [str(s) for s in sqs(bk)]
    return f"{'B' if stm else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oracles-verified", required=True, help="0699 oracles_verified.jsonl (position_hash, tb_verdict)")
    ap.add_argument("--oracles-fen", required=True, help="pcblues_oracles.jsonl (position_hash, fen)")
    ap.add_argument("--corpus", default=None, help="JNNW pour échantillon near-TB (optionnel)")
    ap.add_argument("--thermo", required=True, help="pcblues_thermometre.fen (disjonction gelée)")
    ap.add_argument("--tb-max", type=int, default=7, help="taille TB (pièces)")
    ap.add_argument("--near-lead", type=int, default=3, help="avantage min des positions near-TB")
    ap.add_argument("--n-near", type=int, default=400, help="cible near-TB échantillonnées")
    ap.add_argument("--out", required=True, help="conversion_pool.fen")
    a = ap.parse_args(argv)

    # thermo canonique (interdit)
    thermo = set()
    for ln in open(a.thermo, encoding="utf-8"):
        fen = ln.split("#", 1)[0].strip()
        if fen:
            thermo.add(canon(fen))

    # 1. oracles certifiés WON : join hash
    won_hash = set()
    for ln in open(a.oracles_verified, encoding="utf-8"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("tb_verdict") == "WIN":
            won_hash.add(r["position_hash"])
    pool = {}   # canon -> (fen, source, adv)
    n_oracle = 0
    for ln in open(a.oracles_fen, encoding="utf-8"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("position_hash") in won_hash and r.get("fen"):
            fen = r["fen"]; c = canon(fen)
            if c in thermo or c in pool:
                continue
            # oracle WON = STM gagne (expected=WIN est STM-POV) → le champion joue le STM
            adv = fen.split(":", 1)[0].strip()[:1]
            pool[c] = (fen, "oracle-won", adv)
            n_oracle += 1

    # 2. near-TB échantillonnées (N_TB+1 / N_TB+2 pièces, avantage >= near-lead)
    n_near = 0
    if a.corpus:
        b = Path(a.corpus).read_bytes()
        n = struct.unpack_from("<I", b, 4)[0]; REC = 38
        lo, hi = a.tb_max + 1, a.tb_max + 2
        step = max(1, n // (a.n_near * 30))
        for i in range(0, n, step):
            if n_near >= a.n_near:
                break
            fen = _rec_fen(b[8 + i * REC: 8 + (i + 1) * REC])
            w, bl = pieces(fen); tp = w + bl
            if not (lo <= tp <= hi):
                continue
            adv = adv_side(fen, a.near_lead)
            if adv is None:
                continue
            c = canon(fen)
            if c in thermo or c in pool:
                continue
            pool[c] = (fen, "near-tb", adv)
            n_near += 1

    # 3. assertion disjonction (garde dure)
    inter = set(pool) & thermo
    assert not inter, f"POOL ∩ thermo != ∅ ({len(inter)}) — intégrité instrument violée"

    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(f"# conversion_pool — {len(pool)} positions gagnées (oracle-won={n_oracle} near-tb={n_near}) — ∩ thermo=∅\n")
        for c, (fen, src, adv) in pool.items():
            fh.write(f"{fen}  # {src} adv={adv}\n")
    stats = {"total": len(pool), "oracle_won": n_oracle, "near_tb": n_near,
             "thermo_disjoint": True, "tb_max": a.tb_max, "near_lead": a.near_lead}
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
