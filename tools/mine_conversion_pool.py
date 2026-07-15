#!/usr/bin/env python3
"""G2/G3 — mine + certifie le pool du gymnase de conversion (L3), et gèle un set conv_self DISJOINT.

Le gymnase enseigne (conv_self +0.065) mais est AFFAMÉ (0.04% du corpus). Le goulot n'est pas de
TROUVER des positions gagnées, c'est de les CERTIFIER — or l'arbitre d14+egdb coûte ~0,025 s/pos (B1)
→ pool de milliers de positions certifiées en une nuit. Ce module :
  --extract : MOISSONNE le corpus committé (on-distribution ⭐) → candidats à N_TB+1/+2/+3 pièces
              (HORS TB : la traversée vers la base enseigne ; une graine DANS la TB = 0 trajectoire)
              avec avantage matériel ≥ min-adv. Sortie candidats JNNW (le job les certifie par
              `jass --deep-relabel 14 --egdb`).
  --filter  : lit les candidats CERTIFIÉS (wdl rempli), garde WIN-pour-le-camp-avantagé (pas de
              « probablement gagné »), stratifie par pièces, dédup, ASSERTIONS D'INTÉGRITÉ (G3 :
              pool ∩ thermomètre-224 = ∅ ET pool ∩ set-conv_self = ∅ — sinon la jauge maîtresse
              ment par mémorisation), puis CARVE un set conv_self FIGÉ disjoint + le pool training.

Livrables : conversion_pool_v2.fen (training, versionné) + conv_self_eval_set.fen (FIGÉ, disjoint)
+ manifest (sources, taux de certif, strates).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

TB_MAX = 7  # egdb ≤ 7 pièces
REC = 38


def _sqs(v):
    return [s for s in range(1, 51) if (v >> (s - 1)) & 1]


def _pc(v):
    c = 0
    while v:
        v &= v - 1
        c += 1
    return c


def rec_to_fen(rec: bytes):
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    Wl = [f"K{s}" for s in _sqs(wk)] + [str(s) for s in _sqs(wm)]
    Bl = [f"K{s}" for s in _sqs(bm)] + [str(s) for s in _sqs(bk)]
    fen = f"{'B' if stm else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
    wp, bp = _pc(wm) + _pc(wk), _pc(bm) + _pc(bk)
    return fen, wp, bp, stm


def material(fen: str):
    """(#W valeur, #B valeur) — homme=1, dame=3 (la marge de conversion = VALEUR, pas pièces :
    +1 homme est mince/difficile (le trou Scan-vs-jass) ; +1 dame est gagné)."""
    try:
        _, wp, bp = fen.split(":")
    except ValueError:
        return (0, 0)
    def v(part):
        s = 0
        for t in part[1:].split(","):
            t = t.strip()
            if t:
                s += 3 if t[0] == "K" else 1
        return s
    return v(wp), v(bp)


def value_margin(fen: str):
    """(camp avantagé 'W'/'B'/None, marge matérielle |ΔV|)."""
    vw, vb = material(fen)
    if vw > vb:
        return "W", vw - vb
    if vb > vw:
        return "B", vb - vw
    return None, 0   # matériel ÉGAL (gagné par position/dames = conversion la + fine)


def canon(fen: str) -> str:
    try:
        stm, wp, bp = fen.split(":")
    except ValueError:
        return fen.strip()
    def norm(part):
        body = part[1:] if part[:1] in ("W", "B") else part
        toks = [t.strip() for t in body.split(",") if t.strip()]
        return ",".join(sorted(toks, key=lambda t: (t[0] == "K", int(t[1:] if t[0] == "K" else t))))
    return f"{stm.strip()[:1]}:W{norm(wp)}:B{norm(bp)}"


def load_canon_set(path):
    s = set()
    if path and Path(path).exists():
        for ln in open(path, encoding="utf-8"):
            f = ln.split("#", 1)[0].strip()
            if f:
                s.add(canon(f))
    return s


def do_extract(a):
    b = Path(a.corpus).read_bytes()
    n = struct.unpack_from("<I", b, 4)[0]
    body = b[8:]
    lo, hi = TB_MAX + 1, TB_MAX + a.max_over    # HORS TB (≥ N_TB+1) — la frontière
    seen = set()
    out = bytearray()
    kept = 0
    vmax = getattr(a, "val_margin_max", None)   # minage TIP : marge-VALEUR ≤ vmax (0/1 = p4/p3)
    step = 1 if vmax is not None else max(1, n // (a.n_cand * 40))
    for i in range(0, n, step):
        if kept >= a.n_cand:
            break
        rec = body[i * REC:(i + 1) * REC]
        if len(rec) < REC:
            continue
        fen, wp, bp, stm = rec_to_fen(rec)
        tp = wp + bp
        if not (lo <= tp <= hi):
            continue
        if vmax is not None:
            _, mm = value_margin(fen)           # tip : garde marge-VALEUR fine (≤ vmax)
            if mm > vmax:
                continue
        elif abs(wp - bp) < a.min_adv:          # (défaut) avantage en #pièces requis
            continue
        c = canon(fen)
        if c in seen:
            continue
        seen.add(c)
        out += rec
        kept += 1
    Path(a.out).write_bytes(b"JNNW" + struct.pack("<I", kept) + bytes(out))
    print(json.dumps({"candidates": kept, "piece_range": [lo, hi], "min_adv": a.min_adv}))
    return 0


def do_filter(a):
    thermo = load_canon_set(a.thermo)
    existing_eval = load_canon_set(a.eval_set_in)   # pour dédup vs set conv_self déjà figé
    b = Path(a.certified).read_bytes()
    n = struct.unpack_from("<I", b, 4)[0]
    body = b[8:]
    strata = {}      # (pieces) -> list of (fen, adv)
    seen = set()
    n_dec = n_win_adv = 0
    for i in range(n):
        rec = body[i * REC:(i + 1) * REC]
        fen, wp, bp, stm = rec_to_fen(rec)
        wdl = struct.unpack_from("<b", rec, 37)[0]
        if wdl == 0:
            continue                            # pas décisif -> pas « probablement gagné »
        n_dec += 1
        stm_side = "W" if stm == 0 else "B"
        winner = stm_side if wdl > 0 else ("B" if stm_side == "W" else "W")
        if getattr(a, "value_adv", False):
            # minage TIP p3/p4 : avantage par VALEUR (homme=1, dame=3), pas par #pièces.
            # marge 0 (matériel valeur-égal, gain technique le + dur) : le GAGNANT est le camp à enseigner.
            adv, mm = value_margin(fen)
            if mm == 0:
                adv = winner
            elif mm < a.min_adv:
                adv = None
        else:
            adv = "W" if wp - bp >= a.min_adv else ("B" if bp - wp >= a.min_adv else None)
        if adv is None or winner != adv:        # WIN pour le camp AVANTAGÉ seulement
            continue
        n_win_adv += 1
        c = canon(fen)
        if c in seen or c in thermo or c in existing_eval:   # dédup + G3 assertions
            continue
        seen.add(c)
        strata.setdefault(wp + bp, []).append((fen, adv))
    # carve : set conv_self figé (disjoint) puis training pool ; échantillonné à travers les strates
    allpos = [(fen, adv, pc) for pc, lst in sorted(strata.items()) for (fen, adv) in lst]
    # G3 : assertions dures
    cset = {canon(f) for f, _, _ in allpos}
    assert not (cset & thermo), f"POOL ∩ thermo != ∅ ({len(cset & thermo)})"
    assert not (cset & existing_eval), f"POOL ∩ set-conv_self != ∅ ({len(cset & existing_eval)})"
    evaln = min(a.eval_n, len(allpos) // 3)     # ≤ 1/3 réservé à la jauge, jamais au training
    eval_set = allpos[::max(1, len(allpos) // max(1, evaln))][:evaln]
    eval_canon = {canon(f) for f, _, _ in eval_set}
    train = [(f, adv, pc) for (f, adv, pc) in allpos if canon(f) not in eval_canon]
    # écriture
    def write(path, rows, title):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {title} — {len(rows)} positions ; ∩thermo=∅ ∩conv_self-eval=∅\n")
            for f, adv, pc in rows:
                _, m = value_margin(f)   # marge MATÉRIELLE (axe palier G4)
                fh.write(f"{f}  # adv={adv} pc={pc} margin={m}\n")
    write(a.out_pool, train, "conversion_pool_v2 (training, certifié WIN camp-avantagé)")
    write(a.out_eval, eval_set, "conv_self_eval_set (FIGÉ, disjoint du training)")
    import collections as _c
    smargin = _c.Counter(value_margin(f)[1] for f, _, _ in allpos)   # strate MARGE-VALEUR (palier G4)
    man = {"certified_input": n, "decisive": n_dec, "win_for_advantaged": n_win_adv,
           "pool_v2": len(train), "eval_set": len(eval_set),
           "strata_pieces": {str(pc): len(lst) for pc, lst in sorted(strata.items())},
           "strata_value_margin": {str(k): v for k, v in sorted(smargin.items())},
           "palier_hint": {"p3_marge+1_mince": smargin.get(1, 0), "p4_marge0_egal": smargin.get(0, 0),
                           "p1_marge>=2_net": sum(v for k, v in smargin.items() if k >= 2)},
           "thermo_disjoint": True, "eval_disjoint_from_training": True}
    Path(a.manifest).write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(json.dumps(man, ensure_ascii=False))
    return 0


def do_reannotate(a):
    """Ré-annote un pool .fen existant avec la MARGE MATÉRIELLE (axe palier G4) —
    zéro re-minage, l'info est dans le FEN. Émet un manifest de strates marge-valeur."""
    import collections as _c
    rows = []
    for ln in open(a.pool, encoding="utf-8"):
        if ln.startswith("#"):
            continue
        fen = ln.split("#", 1)[0].strip()
        if not fen:
            continue
        adv, m = value_margin(fen)
        wp, bp = 0, 0
        try:
            _, w, b = fen.split(":")
            wp = sum(1 for x in w[1:].split(",") if x.strip())
            bp = sum(1 for x in b[1:].split(",") if x.strip())
        except ValueError:
            pass
        rows.append((fen, adv or "=", wp + bp, m))
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(f"# {Path(a.pool).name} ré-annoté (marge MATÉRIELLE, axe palier G4) — {len(rows)} positions\n")
        for fen, adv, pc, m in rows:
            fh.write(f"{fen}  # adv={adv} pc={pc} margin={m}\n")
    smargin = _c.Counter(m for _, _, _, m in rows)
    man = {"positions": len(rows),
           "strata_value_margin": {str(k): v for k, v in sorted(smargin.items())},
           "palier_hint": {"p3_marge+1_mince": smargin.get(1, 0), "p4_marge0_egal": smargin.get(0, 0),
                           "p1_marge>=2_net": sum(v for k, v in smargin.items() if k >= 2)}}
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(json.dumps(man, ensure_ascii=False))
    return 0


def _palier(margin: int) -> str:
    """Palier de difficulté de conversion (axe marge matérielle, mémo G4)."""
    if margin == 0:
        return "p4_egal"          # matériel égal (technique pure) — le + dur
    if margin == 1:
        return "p3_mince"         # +1 homme (le trou Scan-vs-jass)
    if margin <= 3:
        return "p2_moyen"
    return "p1_net"               # ≥+4 (donné)


def do_carve(a):
    """Carve un set conv_self STRATIFIÉ (N par palier) DISJOINT du pool training, pour
    lire la courbe de conversion palier-par-palier (mémo : avant le 1er tour nourri).
    Sortie : eval-set stratifié + pool training amputé (disjonction dure)."""
    import collections as _c
    rows = []
    for ln in open(a.pool, encoding="utf-8"):
        if ln.startswith("#"):
            continue
        fen = ln.split("#", 1)[0].strip()
        if not fen:
            continue
        _, m = value_margin(fen)
        rows.append((fen, m, _palier(m)))
    by_pal = _c.defaultdict(list)
    for fen, m, pal in rows:
        by_pal[pal].append((fen, m))
    eval_rows = []
    eval_canon = set()
    for pal, lst in by_pal.items():
        take = min(a.per_palier, len(lst) // 2)   # ≤ moitié d'un palier réservé au témoin
        step = max(1, len(lst) // max(1, take))
        for fen, m in lst[::step][:take]:
            eval_rows.append((fen, m, pal))
            eval_canon.add(canon(fen))
    train_rows = [(fen, m, pal) for (fen, m, pal) in rows if canon(fen) not in eval_canon]
    def wr(path, rr, title):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {title} — {len(rr)} positions\n")
            for fen, m, pal in rr:
                fh.write(f"{fen}  # margin={m} palier={pal}\n")
    wr(a.out_eval, eval_rows, "conv_self_eval_set STRATIFIÉ (disjoint du training, N/palier)")
    wr(a.out_train, train_rows, "conversion_pool training (amputé du témoin stratifié)")
    man = {"eval_set": len(eval_rows), "training": len(train_rows),
           "eval_par_palier": {p: sum(1 for _, _, q in eval_rows if q == p) for p in
                               ("p1_net", "p2_moyen", "p3_mince", "p4_egal")},
           "train_par_palier": {p: sum(1 for _, _, q in train_rows if q == p) for p in
                               ("p1_net", "p2_moyen", "p3_mince", "p4_egal")}}
    assert not (eval_canon & {canon(f) for f, _, _ in train_rows}), "eval ∩ training != ∅"
    if a.manifest:
        Path(a.manifest).write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(json.dumps(man, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)
    cv = sub.add_parser("carve")
    cv.add_argument("--pool", required=True)
    cv.add_argument("--per-palier", type=int, default=200)
    cv.add_argument("--out-eval", required=True)
    cv.add_argument("--out-train", required=True)
    cv.add_argument("--manifest", default=None)
    ra = sub.add_parser("reannotate")
    ra.add_argument("--pool", required=True)
    ra.add_argument("--out", required=True)
    ra.add_argument("--manifest", default=None)
    e = sub.add_parser("extract")
    e.add_argument("--corpus", required=True, help="JNNW committé (moisson on-distribution)")
    e.add_argument("--out", required=True, help="candidats JNNW (à certifier par deep-relabel)")
    e.add_argument("--n-cand", type=int, default=40000)
    e.add_argument("--max-over", type=int, default=3, help="N_TB+max-over pièces (def 3 → ≤10)")
    e.add_argument("--min-adv", type=int, default=1)
    e.add_argument("--val-margin-max", type=int, default=None,
                   help="minage TIP p3/p4 : ne garder que marge-VALEUR ≤ N (0=p4_egal,1=p3_mince) ; balaye TOUT le corpus")
    f = sub.add_parser("filter")
    f.add_argument("--certified", required=True, help="candidats CERTIFIÉS (wdl rempli par deep-relabel)")
    f.add_argument("--thermo", required=True)
    f.add_argument("--eval-set-in", default=None, help="set conv_self déjà figé (dédup)")
    f.add_argument("--min-adv", type=int, default=1)
    f.add_argument("--value-adv", action="store_true",
                   help="minage TIP : avantage par VALEUR (homme=1,dame=3) + marge0 enseigne le gagnant (compat 0717 = OFF)")
    f.add_argument("--eval-n", type=int, default=400, help="taille du set conv_self figé à carver")
    f.add_argument("--out-pool", required=True)
    f.add_argument("--out-eval", required=True)
    f.add_argument("--manifest", required=True)
    a = ap.parse_args(argv)
    if a.mode == "extract":
        return do_extract(a)
    if a.mode == "reannotate":
        return do_reannotate(a)
    if a.mode == "carve":
        return do_carve(a)
    return do_filter(a)


if __name__ == "__main__":
    sys.exit(main())
