#!/usr/bin/env python3
"""B4 — écrit une éval SEED artisanale ``bootstrap.pjtw`` (L3, porte-1 « Samuel assumé »).

But : donner à la lignée from-scratch un eval(0) qui CONNAÎT DÉJÀ LE MATÉRIEL, pour
économiser les tours T0-T2 (le matériel n'est plus ré-appris par adjudication). Ce n'est
PAS un champion — c'est une graine à valeurs RONDES. **Buckets patterns = 0** (le positionnel
des hommes vit dans les patterns → s'apprend en boucle) ; seuls les EXTRAS structurels sont
posés à la main : matériel (hommes = comptage, dames = PST uniforme + bonus centre léger),
mobilité légère (le « tempo »). Rien d'autre (balance/skew/endgame/king-mob = 0, appris).

Format PJTW v3/v4 (identique wdl_finetune._load_champion / src/scan_eval.cpp) :
  header 20 o : <IIIII> = magic, ver (base 3, bit 0x100=king-patterns), scale, n_pat, n_ext
  corps int32 : [pat_mg(n_pat) | pat_eg(n_pat) | ext_mg(n_ext) | ext_eg(n_ext)] / scale
Convention de signe : **eval BLACK-POV** (src/scan_eval.cpp : eval_black = wmg·(pat+ext)_mg +
weg·(pat+ext)_eg). extras[EXTRA_BLACK_MEN]=#hommes noirs, [EXTRA_WHITE_MEN]=#hommes blancs →
poids noir positif / blanc négatif. Idem PST dames : noir [0..49] positif, blanc [50..99] négatif.

Dimensions : passer --like <ref.pjtw> pour copier EXACTEMENT (magic,ver,scale,n_pat,n_ext) de
la géométrie du build cible (recommandé : le header de gen2-mmto, DIMENSIONS SEULES, aucun
poids lu → zéro fuite dans la lignée from-scratch), sinon fournir --n-pat/--n-ext/--scale/--ver.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

# --- ext feature layout (src/scan_eval.hpp, build ENDGAME+KING_MOBILITY, NUM_EXTRAS=120) ---
EXTRA_BK_PST_BASE = 0     # [0..49]  dame noire sur case FMJD (idx = case-1)
EXTRA_WK_PST_BASE = 50    # [50..99] dame blanche
EXTRA_BLACK_MEN   = 100
EXTRA_WHITE_MEN   = 101
EXTRA_BLACK_MOB   = 102
EXTRA_WHITE_MOB   = 103
# 104..119 = balance/endgame/king-mob/skew/king-material = 0 (appris en boucle)

# cases centrales FMJD (bonus PST dame léger) — cœur du damier 10x10
_CENTRAL = frozenset({22, 23, 24, 27, 28, 29})


def _read_header(path: Path):
    raw = path.read_bytes()[:20]
    magic, ver, scale, n_pat, n_ext = struct.unpack("<IIIII", raw)
    return magic, ver, scale, n_pat, n_ext


def build_ext(n_ext: int, scale: int, men: float, king: float,
              king_center: float, mobility: float) -> tuple[np.ndarray, np.ndarray]:
    """Retourne (ext_mg, ext_eg) int32, black-POV, valeurs = piece-units × scale."""
    mg = np.zeros(n_ext, dtype=np.int64)
    # --- matériel hommes : noir +, blanc − ---
    mg[EXTRA_BLACK_MEN] = round(+men * scale)
    mg[EXTRA_WHITE_MEN] = round(-men * scale)
    # --- matériel dames : PST uniforme (valeur dame) + bonus centre léger ---
    for sq in range(1, 51):
        bonus = king_center if sq in _CENTRAL else 0.0
        mg[EXTRA_BK_PST_BASE + (sq - 1)] = round(+(king + bonus) * scale)   # dame noire
        mg[EXTRA_WK_PST_BASE + (sq - 1)] = round(-(king + bonus) * scale)   # dame blanche
    # --- « tempo léger » = mobilité (noir +, blanc −) ---
    mg[EXTRA_BLACK_MOB] = round(+mobility * scale)
    mg[EXTRA_WHITE_MOB] = round(-mobility * scale)
    # matériel = invariant de phase → eg identique à mg (graine ronde)
    eg = mg.copy()
    # garde-fou int32
    if np.abs(mg).max() > np.iinfo(np.int32).max:
        sys.exit("ABORT: poids dépasse int32 (baisser --scale ou les valeurs)")
    return mg.astype("<i4"), eg.astype("<i4")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="chemin bootstrap.pjtw")
    ap.add_argument("--like", default=None, help="pjtw de référence : copie (magic,ver,scale,n_pat,n_ext)")
    ap.add_argument("--magic", type=lambda s: int(s, 0), default=0x57544A50)
    ap.add_argument("--ver", type=int, default=515)      # base 3 + bit v4 (0x200)
    ap.add_argument("--scale", type=int, default=1000)
    ap.add_argument("--n-pat", type=int, default=17006112)
    ap.add_argument("--n-ext", type=int, default=120)
    ap.add_argument("--men", type=float, default=1.0, help="valeur homme (piece-units)")
    ap.add_argument("--king", type=float, default=3.0, help="valeur dame (piece-units, PST uniforme)")
    ap.add_argument("--king-center", type=float, default=0.2, help="bonus centre dame léger")
    ap.add_argument("--mobility", type=float, default=0.05, help="poids mobilité léger (« tempo »)")
    a = ap.parse_args(argv)

    if a.like:
        magic, ver, scale, n_pat, n_ext = _read_header(Path(a.like))
        print(f"--like {a.like} : magic={magic:#x} ver={ver} scale={scale} n_pat={n_pat:,} n_ext={n_ext}")
    else:
        magic, ver, scale, n_pat, n_ext = a.magic, a.ver, a.scale, a.n_pat, a.n_ext

    if magic not in (0x57544A50, 0x57534A50):
        sys.exit(f"ABORT: magic inattendu {magic:#x}")
    if (ver & 0xFF) != 3:
        sys.exit(f"ABORT: version base {ver & 0xFF} != 3")

    ext_mg, ext_eg = build_ext(n_ext, scale, a.men, a.king, a.king_center, a.mobility)

    out = Path(a.out)
    with out.open("wb") as fh:
        fh.write(struct.pack("<IIIII", magic, ver, scale, n_pat, n_ext))
        # corps : [pat_mg | pat_eg | ext_mg | ext_eg] — patterns TOUS À ZÉRO
        zeros = np.zeros(n_pat, dtype="<i4")
        zeros.tofile(fh)   # pat_mg
        zeros.tofile(fh)   # pat_eg
        ext_mg.tofile(fh)  # ext_mg
        ext_eg.tofile(fh)  # ext_eg
    nbytes = out.stat().st_size
    expect = 20 + 4 * (2 * n_pat + 2 * n_ext)
    ok = nbytes == expect
    print(f"écrit {out} : {nbytes:,} o (attendu {expect:,} {'✓' if ok else '✗ TAILLE FAUSSE'})")
    print(f"  matériel black-POV : homme=±{a.men} dame=±{a.king}(+centre {a.king_center}) mob=±{a.mobility} ; patterns=0 ; scale={scale}")
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
