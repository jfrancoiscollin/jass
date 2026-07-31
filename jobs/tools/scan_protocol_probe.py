#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture VERBATIM ce que Scan 3.1 émet, pour écrire le juge contre du réel.

L'atlas de points aveugles a besoin du **score** de Scan sur une position. Scan
ne le met pas sur `done` (qui ne porte que `move=`) mais sur les lignes émises
pendant la réflexion — et le format exact n'a jamais été capturé dans ce projet :
`calibrate_vs_scan` ne lit que le coup et jette le reste.

Écrire le lecteur de score contre une supposition, c'est ce qui a fait tomber
`cpx62-1110` : un schéma supposé au lieu d'être vérifié, découvert onze minutes
après le lancement. Cette sonde supprime la supposition.

Elle ne joue aucune partie, n'entraîne rien, ne compare aucun modèle. Elle
ouvre Scan, lui donne quelques positions, et **écrit tout ce qu'il répond**,
ligne par ligne. Puis elle teste le motif d'extraction de
`scan_blind_spot_atlas.py` contre ces lignes et dit s'il fonctionne.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_by_path(name: str, relative: str):
    """`jobs/tools` n'est pas un package : on importe par chemin.

    Le module DOIT être enregistré dans `sys.modules` avant `exec_module` —
    `@dataclass` va chercher `sys.modules[cls.__module__].__dict__` pour
    résoudre ses annotations, et échoue sur un `None` sinon. C'est ce qui a
    cassé au premier essai sur `calibrate_vs_scan`."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_atlas_module():
    return _load_by_path("scan_blind_spot_atlas",
                         "jobs/tools/scan_blind_spot_atlas.py")


# Positions de sonde, données en FEN et converties par le convertisseur DÉJÀ
# éprouvé de `calibrate_vs_scan` — pas par un encodage réinventé ici. Trois
# régimes, parce qu'une ligne de score peut avoir un gabarit différent selon que
# Scan annonce une évaluation ordinaire ou un gain forcé.
PROBE_FENS = [
    ("initiale",
     "W:W31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50:"
     "B1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20"),
    ("milieu_calme", "W:W31,32,33,34,35,36,37:B14,15,16,17,18,19,20"),
    ("finale_dames", "W:WK46,K47,K48:BK3,K4,K5"),
    ("gain_force",   "W:WK46,31:BK5"),
]


def load_fen_converter():
    return _load_by_path("calibrate_vs_scan",
                         "jobs/tools/calibrate_vs_scan.py").jass_fen_to_scan_pos


class ScanProbe:
    """Pilote Scan en capturant CHAQUE ligne reçue, sans filtre."""

    def __init__(self, path: Path, log: list[str]):
        self.log = log
        self.proc = subprocess.Popen(
            [str(path), "hub"], cwd=str(path.resolve().parent),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.lines: deque[str] = deque()
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self) -> None:
        for raw in self.proc.stdout:
            line = raw.rstrip("\n")
            with self.lock:
                self.lines.append(line)
                self.log.append(f"    < {line}")

    def send(self, cmd: str) -> None:
        self.log.append(f"    > {cmd}")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def collect_until(self, prefixes: tuple[str, ...],
                      timeout_s: float) -> list[str]:
        """Toutes les lignes jusqu'à l'une des sentinelles, incluse."""
        got: list[str] = []
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self.lock:
                while self.lines:
                    line = self.lines.popleft()
                    got.append(line)
                    if line.startswith(prefixes):
                        return got
            time.sleep(0.02)
        return got

    def close(self) -> None:
        try:
            self.send("quit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scan", required=True, type=Path)
    p.add_argument("--depth", type=int, default=10)
    p.add_argument("--transcript", required=True, type=Path,
                   help="où écrire la transcription verbatim")
    p.add_argument("--out", required=True, type=Path,
                   help="rapport JSON : le motif de score marche-t-il")
    args = p.parse_args(argv)

    if not args.scan.is_file():
        print(f"scan_protocol_probe: binaire absent {args.scan}", file=sys.stderr)
        return 2

    atlas = load_atlas_module()
    transcript: list[str] = []
    findings = []

    probe = ScanProbe(args.scan, transcript)
    try:
        transcript.append("== handshake")
        probe.send("hub")
        probe.collect_until(("wait",), 20)
        # Mêmes paramètres épinglés que calibrate_vs_scan : pas de livre, pas de
        # bitbase. La sonde doit voir le Scan que nos mesures utilisent.
        for name, value in (("variant", "normal"), ("book", "false"),
                            ("book-ply", "4"), ("book-margin", "4"),
                            ("ponder", "false"), ("threads", "1"),
                            ("tt-size", "24"), ("bb-size", "0")):
            probe.send(f"set-param name={name} value={value}")
        probe.send("init")
        probe.collect_until(("ready", "error"), 30)

        to_scan_pos = load_fen_converter()
        for label, fen in PROBE_FENS:
            pos = to_scan_pos(fen)
            transcript.append(f"== position {label}")
            probe.send("new-game")
            probe.send(f"pos pos={pos}")
            probe.send(f"level depth={args.depth}")
            probe.send("go think")
            lines = probe.collect_until(("done", "error"), 120)
            score = atlas.extract_scan_score(lines)
            findings.append({
                "position": label,
                "fen": fen,
                "lines_received": len(lines),
                "reached_done": any(l.startswith("done") for l in lines),
                "score_extracted": score,
                # Les lignes qui contiennent « score » quel qu'en soit le format,
                # pour qu'un humain voie le vrai gabarit même si le motif rate.
                "lines_mentioning_score": [l for l in lines
                                           if "score" in l.lower()][:5],
                "last_three_lines": lines[-3:],
            })
    finally:
        probe.close()

    args.transcript.write_text("\n".join(transcript) + "\n", encoding="utf-8")

    ok = [f for f in findings if f["score_extracted"] is not None]
    report = {
        "schema": "l3_scan_protocol_probe",
        "version": 1,
        "scan_binary": str(args.scan),
        "judge_depth": args.depth,
        "pattern_under_test": atlas.SCAN_SCORE_RE.pattern,
        "positions_probed": len(findings),
        "positions_with_score_extracted": len(ok),
        "findings": findings,
        "verdict": ("SCAN_SCORE_PATTERN_WORKS" if len(ok) == len(findings)
                    else "SCAN_SCORE_PATTERN_NEEDS_REWORK"),
        "diagnostic_only": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:1500])

    # Le motif qui rate n'est PAS un échec du job : c'est son résultat. La
    # transcription est là pour qu'on écrive le bon motif. On sort 0 dans les
    # deux cas, le verdict porte l'information.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
