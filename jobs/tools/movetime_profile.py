#!/usr/bin/env python3
"""Profil profondeur/nœuds/NPS des deux moteurs À LEUR CADENCE.

Motif : la matrice Scan du 4 août mesure que Jass à `mt 0,2` perd `−141 Elo`
contre Scan à `mt 0,01` — un handicap de temps de 20× en notre faveur, et on
perd quand même. La rangée profondeur a bougé avec les gains d'évaluation, la
rangée cadence n'a pas bougé d'un pouce. Ce déficit n'a jamais été décomposé.

Cet outil ne joue AUCUNE partie : il pose les mêmes positions aux deux moteurs,
à une grille de cadences, et enregistre ce que chacun rend — profondeur
atteinte, nœuds, et le temps mural MESURÉ ICI pour les deux, identiquement.
Le rapport nœuds/seconde et la profondeur atteinte à temps égal séparent trois
causes qui appellent des corrections sans rapport :

  * NPS très inférieur          → coût par nœud (évaluation, mouvement, TT)
  * NPS comparable, profondeur inférieure → facteur de branchement / élagage
  * profondeur atteinte non monotone en temps → gestion du temps

⚠️ Le temps est mesuré autour de l'appel, pas lu du moteur : Scan rapporte
`time=` sur ses lignes `info` et Jass ne le rapporte pas du tout, donc la seule
mesure comparable est la nôtre, prise de la même façon des deux côtés.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_vs_scan as cvs  # noqa: E402

# Gabarit mesuré le 2026-07-31 sur le runtime épinglé, cf
# docs/experiments/L3_SCAN_SCORE_FORMAT_20260731.md :
#   info depth=10 mean-depth=11.1 score=0.00 nodes=77378 time=0.010 nps=7.6 pv="…"
# `time=`/`nps=` manquent aux profondeurs peu profondes : on ne s'appuie que sur
# `depth=` et `nodes=`, et on prend la DERNIÈRE ligne info qui porte les deux.
SCAN_INFO_RE = re.compile(r"\bdepth=(\d+)\b.*?\bnodes=(\d+)\b")
# Jass met depth= et nodes= sur sa ligne `bestmove` (src/hub.cpp emit_bestmove).
JASS_BEST_RE = re.compile(r"^bestmove\b.*?\bdepth=(\d+)\b.*?\bnodes=(\d+)\b")


def parse_jass(lines: list[str]) -> tuple[int, int]:
    for line in reversed(lines):
        m = JASS_BEST_RE.match(line.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
    raise ValueError("aucune ligne `bestmove` avec depth= et nodes=")


def parse_scan(lines: list[str]) -> tuple[int, int]:
    for line in reversed(lines):
        s = line.strip()
        if not s.startswith("info"):
            continue
        m = SCAN_INFO_RE.search(s)
        if m:
            return int(m.group(1)), int(m.group(2))
    raise ValueError("aucune ligne `info` avec depth= et nodes=")


def selftest() -> None:
    """Round-trip écriture→lecture sur les gabarits RÉELS des deux moteurs.

    Rule 9 du projet : ne rien queuer avant d'avoir vérifié que le parseur lit
    ce que l'outil écrit. Les échantillons ci-dessous sont verbatim — celui de
    Scan vient de la transcription de `scan_protocol_probe.py`, celui de Jass du
    format de `emit_bestmove`.
    """
    scan_lines = [
        'info depth=3 score=0.12 pv="34-30"',
        'info depth=10 mean-depth=11.1 score=0.00 nodes=77378 time=0.010 nps=7.6 pv="34-30 17-21"',
        "done move=34-30 ponder=17-21",
    ]
    assert parse_scan(scan_lines) == (10, 77378), parse_scan(scan_lines)
    # Une ligne info peu profonde sans nodes= ne doit pas etre retenue.
    assert parse_scan(scan_lines[:1] + scan_lines[1:]) == (10, 77378)
    jass_lines = [
        "bestmove 34-30 score=12 depth=14 nodes=482913 cutoffs=1 cut1=1 research=0 "
        "movessearched=9 scanverify=0 scanverifycuts=0 scanthreat=0 rootorder=0 rootorderfail=0",
    ]
    assert parse_jass(jass_lines) == (14, 482913), parse_jass(jass_lines)
    for bad, fn in ((["done move=1-2"], parse_scan), (["error x"], parse_jass)):
        try:
            fn(bad)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError("un parseur a accepté une entrée sans compteurs")
    print("SELFTEST_OK parseurs Jass et Scan round-trip sur gabarits réels")


def summarise(rows: list[dict]) -> dict:
    depths = [r["depth"] for r in rows]
    nodes = [r["nodes"] for r in rows]
    secs = [r["wall_s"] for r in rows]
    total_nodes, total_s = sum(nodes), sum(secs)
    return {
        "n": len(rows),
        "depth_mean": round(statistics.fmean(depths), 3),
        "depth_median": statistics.median(depths),
        "depth_min": min(depths),
        "depth_max": max(depths),
        "nodes_mean": round(statistics.fmean(nodes), 1),
        "wall_s_mean": round(statistics.fmean(secs), 4),
        "nps": round(total_nodes / total_s, 1) if total_s > 0 else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--jass")
    ap.add_argument("--scan")
    ap.add_argument("--pattern", help="modèle .pjtw du champion")
    ap.add_argument("--openings-file")
    ap.add_argument("--positions", type=int, default=200)
    ap.add_argument("--jass-movetimes", default="0.05,0.1,0.2,0.5,1.0")
    ap.add_argument("--scan-movetimes", default="0.01,0.05,0.1,0.2")
    ap.add_argument("--search-params", default=None)
    ap.add_argument("--out", required=False)
    ap.add_argument("--transcript-out", default=None,
                    help="lignes brutes de la PREMIÈRE sonde de chaque moteur ; "
                         "si un gabarit surprend, une seule itération suffit")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return 0
    for req in ("jass", "scan", "pattern", "openings_file", "out"):
        if not getattr(args, req):
            ap.error(f"--{req.replace('_', '-')} est requis hors --selftest")
    selftest()   # jamais de mesure sans le round-trip d'abord

    fens = [ln.split("#", 1)[0].strip()
            for ln in Path(args.openings_file).read_text().splitlines()]
    fens = [f for f in fens if f][: args.positions]
    if not fens:
        raise SystemExit("aucune ouverture lisible")

    jass_mts = [float(x) for x in args.jass_movetimes.split(",") if x.strip()]
    scan_mts = [float(x) for x in args.scan_movetimes.split(",") if x.strip()]
    transcripts: dict[str, list[str]] = {}
    cells: dict[str, dict] = {}

    jass = cvs.JassEngine(args.jass, label="Jass", no_book=True,
                          search_params=args.search_params,
                          pattern_path=args.pattern)
    try:
        for mt in jass_mts:
            rows = []
            for fen in fens:
                jass.new_game()
                jass.set_position_fen(fen)
                t0 = time.perf_counter()
                _, lines = jass.go_verbose(movetime=mt)
                wall = time.perf_counter() - t0
                d, n = parse_jass(lines)
                rows.append({"depth": d, "nodes": n, "wall_s": wall})
                transcripts.setdefault(f"jass-mt{mt}", lines)
            cells[f"jass-mt{mt}"] = summarise(rows)
            print(f"  jass mt={mt}: {cells[f'jass-mt{mt}']}", flush=True)
    finally:
        jass.close()

    scan = cvs.ScanEngine(args.scan, label="Scan")
    try:
        for mt in scan_mts:
            rows = []
            for fen in fens:
                pos = cvs.jass_fen_to_scan_pos(fen)
                t0 = time.perf_counter()
                _, lines = scan.go_from_verbose(pos, [], movetime=mt)
                wall = time.perf_counter() - t0
                d, n = parse_scan(lines)
                rows.append({"depth": d, "nodes": n, "wall_s": wall})
                transcripts.setdefault(f"scan-mt{mt}", lines)
            cells[f"scan-mt{mt}"] = summarise(rows)
            print(f"  scan mt={mt}: {cells[f'scan-mt{mt}']}", flush=True)
    finally:
        scan.close()

    payload = {"schema": 1, "positions": len(fens), "cells": cells,
               "jass_movetimes": jass_mts, "scan_movetimes": scan_mts}
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if args.transcript_out:
        Path(args.transcript_out).write_text(
            json.dumps(transcripts, indent=2, sort_keys=True) + "\n")
    print("MOVETIME_PROFILE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
