"""Ingest dilf QA oracle claims (E1 endgames + E2 locks) → data/pcblues_oracles.jsonl.

Self-contained pour le job de revalidation moteur (d14+TB) : fen + book verdict
(`expected`) + piece-count (`tb_eligible` = <=7 pièces → TB exact). Source =
dilf/data/exports (contrat INTEROP EXPORTS-bis). verified_engine reste FALSE ici :
c'est le job jass qui le passe true/quarantaine.
"""
import json, sys
from pathlib import Path

DILF = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/user/dilf/data/exports")
SRCS = [
    ("dubois", DILF / "dubois/endgame_dubois_apprentissage_finales.jsonl"),
    ("cid_endgame", DILF / "cid/endgame_cid_endgame.jsonl"),
    ("cid_locks", DILF / "cid/locks_cid_locks.jsonl"),
]

def pieces(fen: str) -> int:
    body = fen.split(":", 1)[1]
    return sum(len([t for t in part[1:].split(",") if t]) for part in body.split(":"))

def main() -> int:
    out = []
    for fam, path in SRCS:
        if not path.exists():
            continue
        for line in path.open():
            d = json.loads(line)
            p = pieces(d["fen"])
            out.append({
                "fen": d["fen"], "side_to_move": d["side_to_move"], "expected": d.get("expected"),
                "source": d.get("source", fam), "family": fam, "position_hash": d["position_hash"],
                "pieces": p, "tb_eligible": p <= 7,
            })
    with open("data/pcblues_oracles.jsonl", "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tb = sum(1 for r in out if r["tb_eligible"])
    print(f"oracles={len(out)} tb_eligible={tb} search={len(out)-tb}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
