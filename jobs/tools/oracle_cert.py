#!/usr/bin/env python3
"""Phase 0 (spec codex_review_v3_2 §3) — hiérarchie d'autorité des labels,
règle `blocks_draw_band`, vérificateur de certificat, résolution de label et
compteurs de survie du tip.

Principe gravé (§3) : SEULES une preuve EXACTE (TB) ou une preuve CERT_PROOF
VÉRIFIÉE peuvent bloquer le draw-band. Une simple stabilité de recherche
(SEARCH_STABLE d14/d16) NE le peut PAS — elle peut dominer un label on-policy
mais laisse le draw-band autorisé.

Certificat = dict (schéma §3.3). Ce module est PUR (aucun moteur) → testable.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Autorité décroissante (§3.1)
TIER_ORDER = ["TB_EXACT", "CERT_PROOF", "SEARCH_STABLE", "ON_POLICY", "AMBIGUOUS"]
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}          # 0 = plus fort
BLOCKING_TIERS = {"TB_EXACT", "CERT_PROOF"}                    # peuvent bloquer le draw-band
PROOF_TYPES = {"tb_direct", "pv_to_tb", "reproducible_proof", "search_stable", "none"}


def validate_certificate(cert: dict) -> tuple[bool, list[str]]:
    """Retourne (ok, raisons). Rejette les combinaisons incohérentes (§3.3)."""
    reasons: list[str] = []
    tier = cert.get("oracle_tier")
    if tier not in TIER_RANK:
        reasons.append(f"oracle_tier invalide: {tier!r}")
        return False, reasons
    ptype = cert.get("proof_type", "none")
    if ptype not in PROOF_TYPES:
        reasons.append(f"proof_type invalide: {ptype!r}")
    validated = bool(cert.get("proof_validated", False))
    blocks = bool(cert.get("blocks_draw_band", False))

    # CERT_PROOF exige proof_validated=true (§3.3)
    if tier == "CERT_PROOF" and not validated:
        reasons.append("CERT_PROOF avec proof_validated=false")
    # TB_EXACT : preuve directe tablebase attendue
    if tier == "TB_EXACT":
        if ptype != "tb_direct":
            reasons.append("TB_EXACT sans proof_type=tb_direct")
        if not cert.get("tb_reached", False):
            reasons.append("TB_EXACT sans tb_reached=true")
    # blocks_draw_band réservé aux tiers bloquants ET cohérent (§3.2/§3.3)
    if blocks and tier not in BLOCKING_TIERS:
        reasons.append(f"blocks_draw_band=true interdit pour oracle_tier={tier}")
    if blocks and tier == "CERT_PROOF" and not validated:
        reasons.append("blocks_draw_band=true sur CERT_PROOF non vérifié")
    if tier == "SEARCH_STABLE" and blocks:
        reasons.append("SEARCH_STABLE ne peut pas poser blocks_draw_band=true")
    return (len(reasons) == 0), reasons


def can_block_draw_band(cert: dict) -> bool:
    """VÉRITÉ dérivée (ne fait pas confiance au champ stocké seul) : True
    seulement pour un TB_EXACT valide ou un CERT_PROOF vérifié valide (§3.2)."""
    ok, _ = validate_certificate(cert)
    if not ok:
        return False
    tier = cert["oracle_tier"]
    if tier == "TB_EXACT":
        return bool(cert.get("tb_reached", False))
    if tier == "CERT_PROOF":
        return bool(cert.get("proof_validated", False))
    return False


def resolve_label(cert: dict, on_policy_wdl: int, draw_band_wdl: int) -> dict:
    """Algorithme §3.4. Retourne {wdl, source, blocks_draw_band}.
    `on_policy_wdl`/`draw_band_wdl` = issues candidates (STM-POV, {-1,0,+1}).
    `cert['score']`/cert result = résultat certifié pour TB/CERT."""
    ok, reasons = validate_certificate(cert)
    tier = cert.get("oracle_tier")
    cert_wdl = int(cert.get("result_wdl", cert.get("score_sign", 0)))
    if ok and tier == "TB_EXACT" and cert.get("tb_reached"):
        return {"wdl": cert_wdl, "source": "TB_EXACT", "blocks_draw_band": True}
    if ok and tier == "CERT_PROOF" and cert.get("proof_validated"):
        return {"wdl": cert_wdl, "source": "CERT_PROOF", "blocks_draw_band": True}
    if ok and tier == "SEARCH_STABLE":
        # politique documentée : domine l'on-policy, mais draw-band autorisé
        return {"wdl": cert_wdl, "source": "SEARCH_STABLE", "blocks_draw_band": False}
    # défaut : relabel d14+egdb + draw-band normal
    return {"wdl": draw_band_wdl, "source": "DRAW_BAND", "blocks_draw_band": False}


def tip_survival(records: list[dict]) -> dict:
    """Compteurs de survie du tip (§3.5). Chaque record :
    {oracle_tier, blocks_draw_band(bool cert), survived(bool), strata, provenance, tour, cert_valid(bool)}.
    Invariants DURS : 100% TB_EXACT/CERT_PROOF valides survivent ; 0 certificat
    invalide ne bloque le draw-band. Lève AssertionError si violé."""
    by_tier = defaultdict(lambda: [0, 0])        # tier -> [survived, total]
    by_strata = defaultdict(lambda: [0, 0])
    by_prov = defaultdict(lambda: [0, 0])
    tot = [0, 0]
    invalid_blocking = 0
    for r in records:
        surv = bool(r.get("survived", False))
        tier = r.get("oracle_tier", "ON_POLICY")
        strata = r.get("strata", "unknown")
        prov = f"{r.get('provenance','?')}@{r.get('tour','?')}"
        for bucket in (tot, by_tier[tier], by_strata[strata], by_prov[prov]):
            bucket[0] += int(surv); bucket[1] += 1
        # invariant : un certificat INVALIDE ne doit jamais bloquer
        if r.get("blocks_draw_band") and not r.get("cert_valid", True):
            invalid_blocking += 1
    # invariants durs
    for tier in BLOCKING_TIERS:
        s, n = by_tier.get(tier, [0, 0])
        assert s == n, f"INVARIANT VIOLÉ: {tier} survie {s}/{n} != 100%"
    assert invalid_blocking == 0, f"INVARIANT VIOLÉ: {invalid_blocking} certificats invalides bloquent le draw-band"

    def rate(b):
        return round(b[0] / b[1], 4) if b[1] else None
    total_rate = rate(tot)
    return {
        "tip_total": {"survived": tot[0], "total": tot[1], "rate": total_rate},
        "by_tier": {t: {"survived": v[0], "total": v[1], "rate": rate(v)} for t, v in sorted(by_tier.items())},
        "by_strata": {t: {"survived": v[0], "total": v[1], "rate": rate(v)} for t, v in sorted(by_strata.items())},
        "by_provenance_tour": {t: {"survived": v[0], "total": v[1], "rate": rate(v)} for t, v in sorted(by_prov.items())},
        "invalid_blocking": invalid_blocking,
        "investigate": bool(total_rate is not None and total_rate < 0.90),   # §3.5 seuil 90%
    }


def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("--cert", required=True)
    s = sub.add_parser("tip-survival"); s.add_argument("--records", required=True); s.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        cert = json.loads(Path(a.cert).read_text())
        ok, reasons = validate_certificate(cert)
        print(json.dumps({"valid": ok, "can_block_draw_band": can_block_draw_band(cert), "reasons": reasons}))
        return 0 if ok else 2
    if a.cmd == "tip-survival":
        recs = json.loads(Path(a.records).read_text())
        rep = tip_survival(recs)
        if a.out:
            Path(a.out).write_text(json.dumps(rep, indent=2))
        print(json.dumps(rep))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_cli())
