#!/usr/bin/env python3
"""Phase 0 (spec codex_review_v3_2 §10) — audit MTC / ressources EGDB.

Vérification d'ENVIRONNEMENT (pas un objectif d'apprentissage) :
  - JASS_EGDB_MTC_PATH réellement défini + valeur/version consignées ;
  - accès en LECTURE par les workers (le chemin existe et est lisible) ;
  - cache agrégé maximal calculé (délègue à cache_guard) ;
  - le smoke concurrent court reste côté job (nécessite le moteur) — ce module
    en prépare/valide la config et consigne le verdict.

Sort un manifest JSON et un code retour non-nul si l'environnement est KO.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import cache_guard  # type: ignore
except Exception:
    cache_guard = None


def audit(cache_mb: int, procs: int, mem_mb: int, mtc_env: str = "JASS_EGDB_MTC_PATH",
          smoke_ok: bool | None = None) -> dict:
    reasons: list[str] = []
    mtc_path = os.environ.get(mtc_env, "")
    mtc_active = bool(mtc_path)
    mtc_readable = False
    entries = 0
    if mtc_active:
        p = Path(mtc_path)
        mtc_readable = p.exists() and os.access(p, os.R_OK)
        if not mtc_readable:
            reasons.append(f"{mtc_env}={mtc_path!r} non lisible/inexistant")
        else:
            try:
                entries = sum(1 for _ in p.iterdir()) if p.is_dir() else 1
            except Exception:
                entries = -1
    else:
        reasons.append(f"{mtc_env} non défini")

    cache_rep = None
    if cache_guard is not None and mem_mb > 0:
        cache_rep = cache_guard.check(cache_mb, procs, mem_mb)
        if not cache_rep["ok"]:
            reasons.extend(cache_rep["reasons"])
    elif mem_mb <= 0:
        reasons.append("mémoire indéterminée pour le calcul de cache agrégé")

    if smoke_ok is False:
        reasons.append("smoke concurrent EGDB a échoué")

    ok = mtc_active and mtc_readable and (cache_rep is None or cache_rep["ok"]) and (smoke_ok is not False)
    return {
        "mtc_env": mtc_env,
        "mtc_path": mtc_path,
        "mtc_active": mtc_active,
        "mtc_readable": mtc_readable,
        "mtc_entries": entries,
        "cache_check": cache_rep,
        "concurrent_smoke_ok": smoke_ok,
        "audit_ok": ok,
        "reasons": reasons,
    }


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-mb", type=int, required=True)
    ap.add_argument("--procs", type=int, required=True)
    ap.add_argument("--mem-mb", type=int, default=0)
    ap.add_argument("--smoke-ok", choices=["true", "false", "skip"], default="skip")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    mem = a.mem_mb or (cache_guard.detect_mem_mb() if cache_guard else 0) or 0
    smoke = {"true": True, "false": False, "skip": None}[a.smoke_ok]
    rep = audit(a.cache_mb, a.procs, mem, smoke_ok=smoke)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(json.dumps(rep, ensure_ascii=False))
    return 0 if rep["audit_ok"] else 4


if __name__ == "__main__":
    sys.exit(_cli())
