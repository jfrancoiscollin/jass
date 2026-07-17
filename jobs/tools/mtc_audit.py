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
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import cache_guard  # type: ignore
except Exception:
    cache_guard = None


def inventory_fingerprint(path: Path) -> tuple[int, int, str | None]:
    """Fingerprint the installed MTC set from names and sizes, not 29 GB of data."""
    try:
        files = [path] if path.is_file() else sorted(
            item for item in path.rglob("*") if item.is_file()
        )
        digest = hashlib.sha256()
        total_bytes = 0
        for item in files:
            size = item.stat().st_size
            relative = item.name if path.is_file() else str(item.relative_to(path))
            digest.update(f"{relative}\0{size}\n".encode("utf-8"))
            total_bytes += size
        return len(files), total_bytes, digest.hexdigest() if files else None
    except OSError:
        return -1, -1, None


def verify_recorded_audit(
    manifest: dict,
    expected_path: str,
    expected_host: str | None = None,
) -> dict:
    """Verify that a complete audit still describes this host and MTC set."""
    host = expected_host or socket.gethostname()
    path = Path(expected_path)
    entries, total_bytes, fingerprint = inventory_fingerprint(path)
    reasons: list[str] = []
    if manifest.get("audit_ok") is not True:
        reasons.append("recorded audit is not green")
    if manifest.get("audit_level") != "complete":
        reasons.append("recorded audit is not complete")
    if manifest.get("concurrent_smoke_ok") is not True:
        reasons.append("recorded concurrent smoke did not pass")
    if manifest.get("host") != host:
        reasons.append(f"audit host {manifest.get('host')!r} != current host {host!r}")
    if manifest.get("mtc_path") != expected_path:
        reasons.append(
            f"audit path {manifest.get('mtc_path')!r} != expected path {expected_path!r}"
        )
    if entries <= 0 or not path.exists() or not os.access(path, os.R_OK):
        reasons.append("current MTC path is absent, empty or unreadable")
    recorded_inventory = (
        int(manifest.get("mtc_entries", -1) or -1),
        int(manifest.get("mtc_total_bytes", -1) or -1),
        manifest.get("mtc_inventory_sha256"),
    )
    current_inventory = (entries, total_bytes, fingerprint)
    if current_inventory != recorded_inventory:
        reasons.append("current MTC inventory differs from the recorded audit")
    return {
        "schema": 1,
        "verification": "mtc-recorded-audit",
        "verification_ok": not reasons,
        "host": host,
        "mtc_path": expected_path,
        "mtc_entries": entries,
        "mtc_total_bytes": total_bytes,
        "mtc_inventory_sha256": fingerprint,
        "reasons": reasons,
    }


def audit(cache_mb: int, procs: int, mem_mb: int, mtc_env: str = "JASS_EGDB_MTC_PATH",
          smoke_ok: bool | None = None, require_smoke: bool = False,
          smoke_procs: int | None = None) -> dict:
    reasons: list[str] = []
    mtc_path = os.environ.get(mtc_env, "")
    mtc_active = bool(mtc_path)
    mtc_readable = False
    entries = 0
    total_bytes = 0
    fingerprint = None
    if mtc_active:
        p = Path(mtc_path)
        mtc_readable = p.exists() and os.access(p, os.R_OK)
        if not mtc_readable:
            reasons.append(f"{mtc_env}={mtc_path!r} non lisible/inexistant")
        else:
            entries, total_bytes, fingerprint = inventory_fingerprint(p)
            if entries <= 0:
                reasons.append(f"{mtc_env} ne contient aucun fichier MTC inventoriable")
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
    elif require_smoke and smoke_ok is not True:
        reasons.append("smoke concurrent EGDB requis mais non exécuté")
    if require_smoke and (smoke_procs is None or smoke_procs < 2):
        reasons.append("smoke concurrent EGDB requis avec au moins deux processus")

    ok = (
        mtc_active
        and mtc_readable
        and entries > 0
        and (cache_rep is None or cache_rep["ok"])
        and (smoke_ok is not False)
        and (
            not require_smoke
            or (smoke_ok is True and smoke_procs is not None and smoke_procs >= 2)
        )
    )
    return {
        "schema": 1,
        "host": socket.gethostname(),
        "mtc_env": mtc_env,
        "mtc_path": mtc_path,
        "mtc_active": mtc_active,
        "mtc_readable": mtc_readable,
        "mtc_entries": entries,
        "mtc_total_bytes": total_bytes,
        "mtc_inventory_sha256": fingerprint,
        "cache_check": cache_rep,
        "concurrent_smoke_ok": smoke_ok,
        "concurrent_smoke_required": require_smoke,
        "concurrent_smoke_procs": smoke_procs,
        "audit_level": "complete" if smoke_ok is True else "path_and_cache_only",
        "audit_ok": ok,
        "reasons": reasons,
    }


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-mb", type=int)
    ap.add_argument("--procs", type=int)
    ap.add_argument("--mem-mb", type=int, default=0)
    ap.add_argument("--smoke-ok", choices=["true", "false", "skip"], default="skip")
    ap.add_argument("--smoke-procs", type=int)
    ap.add_argument("--require-smoke", action="store_true")
    ap.add_argument("--verify-manifest", type=Path)
    ap.add_argument("--expected-path")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.verify_manifest:
        if not a.expected_path:
            ap.error("--verify-manifest requires --expected-path")
        rep = verify_recorded_audit(
            json.loads(a.verify_manifest.read_text(encoding="utf-8")),
            a.expected_path,
        )
        ok = rep["verification_ok"]
    else:
        if a.cache_mb is None or a.procs is None:
            ap.error("audit mode requires --cache-mb and --procs")
        mem = a.mem_mb or (cache_guard.detect_mem_mb() if cache_guard else 0) or 0
        smoke = {"true": True, "false": False, "skip": None}[a.smoke_ok]
        rep = audit(
            a.cache_mb,
            a.procs,
            mem,
            smoke_ok=smoke,
            require_smoke=a.require_smoke,
            smoke_procs=a.smoke_procs,
        )
        ok = rep["audit_ok"]
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(json.dumps(rep, ensure_ascii=False))
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(_cli())
