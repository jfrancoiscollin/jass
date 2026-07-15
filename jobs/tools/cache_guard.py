#!/usr/bin/env python3
"""Phase 0 (spec codex_review_v3_2 §3.1 infra / §11.4) — garde cache×processus.

Incident 0723 : 16 shards × cache EGDB 2048 Mo = 32 Go = RAM entière → OOM.
Règle gravée : `cache_mb × nb_max_processus_EGDB_simultanés < budget mémoire`,
avec marge OS/workers/buffers/arbitres. Sur box 32 Go : rester nettement sous
~24 Go de cache EGDB agrégé.

Usage job : `python3 cache_guard.py --cache-mb 512 --procs 16 --mem-mb <total> || exit 3`.
"""
from __future__ import annotations

import argparse
import json
import sys


def check(cache_mb: int, procs: int, mem_mb: int, reserve_frac: float = 0.30,
          hard_cap_mb: int | None = None) -> dict:
    """Retourne {ok, aggregate_mb, budget_mb, reasons}. ok=False si dépassement."""
    aggregate = cache_mb * procs
    budget = int(mem_mb * (1.0 - reserve_frac))
    if hard_cap_mb is not None:
        budget = min(budget, hard_cap_mb)
    reasons = []
    ok = aggregate <= budget
    if not ok:
        reasons.append(f"cache agrégé {aggregate} Mo > budget {budget} Mo "
                       f"({cache_mb}×{procs} ; RAM {mem_mb} Mo, réserve {reserve_frac:.0%})")
        # suggestion
        safe = max(1, budget // max(1, procs))
        reasons.append(f"suggestion : --cache-mb ≤ {safe} pour {procs} procs")
    return {"ok": ok, "aggregate_mb": aggregate, "budget_mb": budget,
            "cache_mb": cache_mb, "procs": procs, "mem_mb": mem_mb, "reasons": reasons}


def detect_mem_mb() -> int | None:
    """Lit MemTotal de /proc/meminfo (Mo). None si indisponible."""
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    except Exception:
        return None
    return None


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-mb", type=int, required=True)
    ap.add_argument("--procs", type=int, required=True)
    ap.add_argument("--mem-mb", type=int, default=0, help="0 = auto (/proc/meminfo)")
    ap.add_argument("--reserve-frac", type=float, default=0.30)
    ap.add_argument("--hard-cap-mb", type=int, default=24576, help="plafond dur agrégé (box 32Go → 24Go)")
    a = ap.parse_args(argv)
    mem = a.mem_mb or detect_mem_mb() or 0
    if mem <= 0:
        print(json.dumps({"ok": False, "reasons": ["mémoire indéterminée (passer --mem-mb)"]}))
        return 3
    rep = check(a.cache_mb, a.procs, mem, a.reserve_frac, a.hard_cap_mb)
    print(json.dumps(rep))
    return 0 if rep["ok"] else 3


if __name__ == "__main__":
    sys.exit(_cli())
