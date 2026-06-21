#!/usr/bin/env python3
"""Validation de l'extension --king-patterns de train_stream.py (sans build C++).

Le seul code nouveau = l'occupancy men|kings a l'extraction (copie exacte de
train.py:597-598). Le men-only train_stream<->train.py est deja valide byte-compatible.
On verifie ici les invariants decisifs du wiring + du marqueur :

  (1) DONNEES SANS ROI : le payload de poids du run --king-patterns est OCTET-IDENTIQUE
      au run men-only (bm|bk==bm, wm|wk==wm) ; seul le bit-marqueur du header differe.
  (2) DONNEES AVEC ROIS : les payloads DIFFERENT (le flag a bien un effet).
  (3) Le bit king est correctement ecrit dans le champ version du header PJTW v3.

Pur Python/numpy : on fabrique un JNNW + FEAT synthetiques, on appelle le CLI.
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
sys.path.insert(0, str(TOOLS))
os.environ.pop("JASS_PATTERNS_DIR", None)
import patterns  # noqa: E402
import train     # noqa: E402

REC = 38
NUM_EXTRAS = 110  # arbitraire : train_stream lit k depuis le header FEAT


def make_jnnw(path, n, seed, with_kings):
    """JNNW synthetique : chaque case 1..50 (bit sq-1) recoit une categorie
    {vide, pion noir, pion blanc, [roi noir, roi blanc]} -> occupancy disjointe valide."""
    rng = np.random.default_rng(seed)
    wm = np.zeros(n, dtype=np.uint64); wk = np.zeros(n, dtype=np.uint64)
    bm = np.zeros(n, dtype=np.uint64); bk = np.zeros(n, dtype=np.uint64)
    ncat = 5 if with_kings else 3
    for sq in range(1, 51):
        bit = np.uint64(1) << np.uint64(sq - 1)
        cat = rng.integers(0, ncat, size=n)  # 0 vide,1 bm,2 wm,3 bk,4 wk
        bm |= np.where(cat == 1, bit, np.uint64(0))
        wm |= np.where(cat == 2, bit, np.uint64(0))
        if with_kings:
            bk |= np.where(cat == 3, bit, np.uint64(0))
            wk |= np.where(cat == 4, bit, np.uint64(0))
    stm = rng.integers(0, 2, size=n).astype(np.uint8)
    score = rng.integers(-500, 500, size=n).astype(np.int32)
    wdl = rng.integers(-1, 2, size=n).astype(np.int8)
    dt = np.dtype([('wm', '<u8'), ('wk', '<u8'), ('bm', '<u8'), ('bk', '<u8'),
                   ('stm', 'u1'), ('score', '<i4'), ('wdl', 'i1')])
    rec = np.zeros(n, dtype=dt)
    rec['wm'] = wm; rec['wk'] = wk; rec['bm'] = bm; rec['bk'] = bk
    rec['stm'] = stm; rec['score'] = score; rec['wdl'] = wdl
    with open(path, 'wb') as f:
        f.write(b'JNNW' + struct.pack('<I', n))
        f.write(rec.tobytes())


def make_feat(path, n, seed, k=NUM_EXTRAS):
    rng = np.random.default_rng(seed + 999)
    arr = rng.standard_normal((n, k)).astype('<f4')
    with open(path, 'wb') as f:
        f.write(b'FEAT' + struct.pack('<II', n, k))
        f.write(arr.tobytes())


def run_stream(data, feat, out, king):
    cmd = [sys.executable, str(TOOLS / "train_stream.py"),
           "--data", data, "--feat", feat, "--color-fold", "--loss", "logistic",
           "--l2", "1e-4", "--max-iter", "5", "--chunk", "1000", "--out", out]
    if king:
        cmd.append("--king-patterns")
    env = dict(os.environ); env.pop("JASS_PATTERNS_DIR", None)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"train_stream a echoue (king={king}):\n{r.stdout}\n{r.stderr}"
    return r.stdout


def header_version(path):
    with open(path, 'rb') as f:
        magic, ver, scale, n_pat, n_ext = struct.unpack('<IIIII', f.read(20))
    return magic, ver, scale, n_pat, n_ext


def payload_sha(path):
    """sha256 du payload de poids (apres le header de 20 octets)."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        f.seek(20)
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    n = 3000
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # --- jeux synthetiques : avec rois et sans rois ---
        jk = str(d / "kings.jnnw"); fk = str(d / "kings.feat")
        jf = str(d / "free.jnnw");  ff = str(d / "free.feat")
        make_jnnw(jk, n, seed=1, with_kings=True);  make_feat(fk, n, seed=1)
        make_jnnw(jf, n, seed=2, with_kings=False); make_feat(ff, n, seed=2)

        out = {k: str(d / f"{k}.pjtw") for k in
               ("km_men", "km_king", "fr_men", "fr_king")}
        run_stream(jk, fk, out["km_men"],  king=False)
        run_stream(jk, fk, out["km_king"], king=True)
        run_stream(jf, ff, out["fr_men"],  king=False)
        run_stream(jf, ff, out["fr_king"], king=True)

        v3_men  = train._pjtw_version(train.WEIGHTS_VERSION_V3, False)
        v3_king = train._pjtw_version(train.WEIGHTS_VERSION_V3, True)

        # (3) marqueur king dans le header
        assert header_version(out["km_men"])[1]  == v3_men,  "header men-only faux"
        assert header_version(out["km_king"])[1] == v3_king, "header king faux"
        assert v3_men != v3_king, "le bit king ne change pas la version (impossible)"
        print(f"[OK] (3) marqueur header : men ver={v3_men}  king ver={v3_king}")

        # tailles coherentes (color-fold -> 17M expanded, meme n_pat/n_ext partout)
        hp = {k: header_version(p) for k, p in out.items()}
        npat = {hp[k][3] for k in hp}; next_ = {hp[k][4] for k in hp}
        assert len(npat) == 1 and len(next_) == 1, f"n_pat/n_ext incoherents : {hp}"
        assert next_.pop() == NUM_EXTRAS
        print(f"[OK] tailles : n_pat={npat.pop():,} (17M attendu) n_ext={NUM_EXTRAS}")

        # (1) SANS ROI : payload king == payload men (octet pour octet)
        s_fr_men  = payload_sha(out["fr_men"])
        s_fr_king = payload_sha(out["fr_king"])
        assert s_fr_men == s_fr_king, (
            "INVARIANT CASSE : sur donnees sans roi, --king-patterns doit donner un "
            "payload IDENTIQUE au men-only (bm|bk==bm). sha men=%s king=%s"
            % (s_fr_men[:16], s_fr_king[:16]))
        print(f"[OK] (1) sans-roi : payload king == men  (sha {s_fr_men[:16]})")

        # (2) AVEC ROIS : payload king != payload men (le flag agit)
        s_km_men  = payload_sha(out["km_men"])
        s_km_king = payload_sha(out["km_king"])
        assert s_km_men != s_km_king, (
            "le flag --king-patterns n'a AUCUN effet sur donnees avec rois "
            "(extraction non cablee ?)")
        print(f"[OK] (2) avec-rois : payload king != men  "
              f"(men {s_km_men[:12]} / king {s_km_king[:12]})")

    print("\nTOUS LES INVARIANTS PASSENT — extension --king-patterns valide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
