#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# eval_calibration.py — briefing externe #5, version HONNÊTE.
#
# Le #5 littéral (« fitter la constante K du sigmoïde, codée à 2.0 ») NE
# S'APPLIQUE PAS à notre trainer : `train.py` fait une RÉGRESSION LOGISTIQUE
# COMPLÈTE (z = w·x est le logit ; gradient = sigmoid(z) − y). La « température »
# est donc DÉJÀ fittée (absorbée dans la magnitude de w), et l'échelle
# train↔inférence est cohérente par construction (quantisation `--scale` stockée
# dans le header, redivisée dans scan_eval.cpp). Il n'y a pas de K=2.0 codé en
# dur à fitter, et re-pondérer le gradient vers le milieu = `--phase-weight` =
# levier MORT (−210 Elo, 0261).
#
# CE QUI EST légitime et utile (le vrai cœur de #5) : fitter le K de
# CALIBRATION (le « Texel K ») qui mappe eval→winprob a POSTERIORI (ne
# ré-entraîne RIEN), et MESURER si l'éval est bien calibrée par PHASE — c.-à-d.
# si les milieux serrés/sharp (notre faiblesse) sont mal servis. Si la
# calibration est bonne, #5 est confirmé non-levier ; si une phase est
# systématiquement sur/sous-confiante, c'est un VRAI signal (distinct du K).
#
# Entrée = un JNNW dont le champ `score` = l'éval (STM-POV cp) et `wdl` = le
# label résultat. Produire un tel fichier avec l'éval d'un champion :
#   jass --rewrite-scores-with-nnue corpus.jnnw scored.jnnw --nnue champ.pjtw
# (ou passer --jass/--pjtw ci-dessous pour l'enchaîner automatiquement).
import argparse
import math
import os
import struct
import subprocess
import sys
import tempfile

REC = struct.Struct("<QQQQBib")   # wm,wk,bm,bk,stm,score(int32),wdl(int8)


def _read_scored(path: str):
    raw = open(path, "rb").read()
    if raw[:4] != b"JNNW":
        raise ValueError("not a JNNW file")
    n = struct.unpack_from("<I", raw, 4)[0]
    scores = []
    ys = []
    pcs = []
    for i in range(n):
        wm, wk, bm, bk, stm, score, wdl = REC.unpack_from(raw, 8 + i * REC.size)
        if wdl == 0:
            continue                      # draws carry no W/L calibration signal
        scores.append(float(score))
        ys.append(1.0 if wdl > 0 else 0.0)   # STM-POV win=1, loss=0
        pcs.append(bin(wm).count("1") + bin(wk).count("1")
                   + bin(bm).count("1") + bin(bk).count("1"))
    return scores, ys, pcs


def _logloss(scores, ys, K):
    if K <= 1e-9:
        return float("inf")
    s = 0.0
    for x, y in zip(scores, ys):
        p = 1.0 / (1.0 + math.exp(-x / K))
        p = min(max(p, 1e-12), 1 - 1e-12)
        s -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return s / max(1, len(ys))


def fit_K(scores, ys, lo=1.0, hi=2000.0, iters=60):
    """Golden-section search for the calibration K minimizing logloss."""
    gr = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c = b - gr * (b - a)
    d = a + gr * (b - a)
    fc, fd = _logloss(scores, ys, c), _logloss(scores, ys, d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - gr * (b - a)
            fc = _logloss(scores, ys, c)
        else:
            a, c, fc = c, d, fd
            d = a + gr * (b - a)
            fd = _logloss(scores, ys, d)
    return (a + b) / 2


def reliability(scores, ys, K, nbins=10):
    """Expected Calibration Error over `nbins` equal-width prob bins."""
    bins = [[0.0, 0.0, 0] for _ in range(nbins)]   # sum_p, sum_y, count
    for x, y in zip(scores, ys):
        p = 1.0 / (1.0 + math.exp(-x / K))
        b = min(nbins - 1, int(p * nbins))
        bins[b][0] += p
        bins[b][1] += y
        bins[b][2] += 1
    ece = 0.0
    n = len(ys)
    rows = []
    for b in bins:
        if b[2] == 0:
            continue
        conf, acc, cnt = b[0] / b[2], b[1] / b[2], b[2]
        ece += cnt / n * abs(conf - acc)
        rows.append((conf, acc, cnt))
    return ece, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scored", help="JNNW with score=eval, wdl=label")
    ap.add_argument("--jnnw", help="raw JNNW (will be re-scored via --jass/--pjtw)")
    ap.add_argument("--jass", help="jass binary (to rescore --jnnw)")
    ap.add_argument("--pjtw", help="champion .pjtw eval (to rescore --jnnw)")
    ap.add_argument("--phase-edges", default="30,20,10",
                    help="piece-count cut points opening/mid/late/end (default 30,20,10)")
    args = ap.parse_args(argv)

    scored = args.scored
    tmp = None
    if scored is None:
        if not (args.jnnw and args.jass and args.pjtw):
            ap.error("give --scored, or --jnnw + --jass + --pjtw")
        tmp = tempfile.NamedTemporaryFile(suffix=".jnnw", delete=False).name
        subprocess.run([args.jass, "--rewrite-scores-with-nnue", args.jnnw, tmp,
                        "--nnue", args.pjtw], check=True)
        scored = tmp

    scores, ys, pcs = _read_scored(scored)
    if tmp and os.path.exists(tmp):
        os.unlink(tmp)
    if not ys:
        print("no decisive positions — nothing to calibrate")
        return 0

    K = fit_K(scores, ys)
    ece, _ = reliability(scores, ys, K)
    print(f"calibration : N={len(ys)}  K*={K:.1f}  logloss={_logloss(scores, ys, K):.4f}  ECE={ece:.4f}")

    # per-phase calibration : does a phase carry systematically worse calibration?
    edges = [int(x) for x in args.phase_edges.split(",")]
    names = ["opening", "midgame", "late-mid", "endgame"]
    def phase(pc):
        if pc >= edges[0]:
            return 0
        if pc >= edges[1]:
            return 1
        if pc >= edges[2]:
            return 2
        return 3
    print("  phase      N      K*(global)  logloss   ECE   mean|eval|")
    for ph in range(4):
        idx = [i for i, pc in enumerate(pcs) if phase(pc) == ph]
        if not idx:
            continue
        ss = [scores[i] for i in idx]
        yy = [ys[i] for i in idx]
        ll = _logloss(ss, yy, K)
        ec, _ = reliability(ss, yy, K)
        meanabs = sum(abs(s) for s in ss) / len(ss)
        print(f"  {names[ph]:<9} {len(idx):<6} {K:<11.1f} {ll:<9.4f} {ec:<6.3f} {meanabs:.0f}")
    print("  LECTURE : ECE plat sur les phases => calibration uniforme, #5 non-levier confirme.")
    print("            ECE du midgame >> autres => l'eval est mal calibree au milieu (vrai signal, != K).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
