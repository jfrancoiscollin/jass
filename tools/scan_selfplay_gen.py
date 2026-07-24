#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Generate STRONG-distribution training positions by having Scan play itself.

Distillation only teaches the teacher's eval on the positions you show it; if those
positions come from weak self-play (covariate shift), you learn Scan's eval where it
does not matter. This tool produces positions from Scan's OWN play: it seeds games
from a pool of opening positions (sampled from a JNNW, high piece-count = early game),
has Scan play BOTH sides (reusing tools/calibrate_vs_scan's jass-referee + Scan player),
and dumps every position visited, labelled with the game outcome (WDL, stm-POV).

Output JNNW (score=0, wdl=game outcome). Distill with `--target wdl`, or relabel with
tools/relabel_with_scan.py to add Scan's eval score and `--target score`.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv  # noqa: E402

REC = 38


def trajectory_record(*, game_index: int, shard: int, opening: str,
                      seed_source: str, outcome: str, reason: str,
                      fens: list[str], moves: list[str]) -> dict:
    """Build the stable, replayable sidecar consumed by conversion mining.

    The JNNW stream intentionally remains unchanged.  This sidecar carries the
    missing game boundaries and played actions, so a future teacher never has
    to guess whether two adjacent binary records belong to the same game.
    """
    payload = json.dumps(
        {"opening": opening, "fens": fens, "moves": moves},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    trajectory_hash = hashlib.sha256(payload).hexdigest()
    source_game_id = hashlib.sha256(
        f"{shard}:{game_index}:{opening}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "schema": 1,
        "source_game_id": source_game_id,
        "game_index": game_index,
        "shard": shard,
        "seed_source": seed_source,
        "opening": opening,
        "outcome": outcome,
        "reason": reason,
        "fens": list(fens),
        "moves": list(moves),
        "trajectory_hash": trajectory_hash,
    }


def open_trajectory_output(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        return gzip.open(path, "wt", encoding="utf-8")
    return path.open("w", encoding="utf-8")


def _sqs(bb: int) -> list[int]:
    return [b + 1 for b in range(50) if (bb >> b) & 1]


def _popcount(*bbs: int) -> int:
    return sum(bin(b).count("1") for b in bbs)


def record_to_fen(rec: bytes) -> tuple[str, int]:
    """JNNW 38-byte record -> (jass FEN, piece count)."""
    wm, wk, bm, bk = struct.unpack("<4Q", rec[0:32])
    stm = rec[32]
    side = "W" if stm == 0 else "B"
    w = [f"K{s}" for s in _sqs(wk)] + [str(s) for s in _sqs(wm)]
    b = [f"K{s}" for s in _sqs(bk)] + [str(s) for s in _sqs(bm)]
    return f"{side}:W{','.join(w)}:B{','.join(b)}", _popcount(wm, wk, bm, bk)


def fen_to_record(fen: str, wdl_stm: int) -> bytes:
    side, wm, wk, bm, bk = cv.parse_jass_fen(fen)
    def bb(squares):
        v = 0
        for s in squares:
            v |= 1 << (s - 1)
        return v
    return (struct.pack("<4Q", bb(wm), bb(wk), bb(bm), bb(bk))
            + struct.pack("<B", 0 if side == "W" else 1)
            + struct.pack("<i", 0)
            + struct.pack("<b", wdl_stm))


def mirror_fen(fen: str) -> str:
    """B2 pairing — position couleurs ÉCHANGÉES (rotation 180° FMJD : case s→51-s,
    W↔B, STM flip). Donne une position DISTINCTE (convertir ET défendre l'équivalent)."""
    try:
        stm, wp, bp = fen.split(":")
    except ValueError:
        return fen
    def flip(part):
        body = part[1:] if part[:1] in ("W", "B") else part
        out = []
        for t in body.split(","):
            t = t.strip()
            if not t:
                continue
            k = t[0] == "K"
            num = int(t[1:] if k else t)
            out.append(("K" if k else "") + str(51 - num))
        return out
    nw = flip(bp)  # ancien noir -> nouveau blanc (miroir)
    nb = flip(wp)
    ns = "B" if stm.strip()[:1] == "W" else "W"
    return f"{ns}:W{','.join(nw)}:B{','.join(nb)}"


def load_pool(path: Path, rng: random.Random, n_pairs: int,
              shard: int = 0, nshards: int = 1) -> list[str]:
    """B2 — charge le pool gymnase (FEN) et retourne jusqu'à 2·n_pairs graines : chaque
    position jouée en PAIRE (originale + miroir couleurs). Sharding disjoint (stripe) car
    le self-play est déterministe → deux shards sur la même graine = parties identiques."""
    fens = [ln.split("#", 1)[0].strip() for ln in open(path, encoding="utf-8")]
    fens = [f for f in fens if f]
    rng.shuffle(fens)                       # identique sur tous les shards (rng partagé)
    if nshards > 1:
        fens = fens[shard::nshards]         # stripe disjointe
    out = []
    for f in fens[:max(1, n_pairs)]:
        out.append(f)
        out.append(mirror_fen(f))
    return out


def load_seeds(path: Path, min_pieces: int, rng: random.Random, n: int,
               shard: int = 0, nshards: int = 1) -> list[str]:
    """Sample up to `n` early-game (>= min_pieces) seed FENs.

    For parallel generation, pass nshards>1 with a SHARED rng seed across all
    shards: every shard shuffles the index list identically, then takes the
    disjoint stripe `idx[shard::nshards]`. This guarantees no two shards ever
    seed from the same opening — critical because Scan at a fixed depth is
    deterministic, so a shared opening would yield byte-identical games.
    """
    b = path.read_bytes()
    total = struct.unpack("<I", b[4:8])[0]
    body = b[8:]
    idx = list(range(total))
    rng.shuffle(idx)
    if nshards > 1:
        idx = idx[shard::nshards]
    seeds: list[str] = []
    for i in idx:
        rec = body[i * REC:(i + 1) * REC]
        if len(rec) < REC:
            continue
        fen, pc = record_to_fen(rec)
        if pc >= min_pieces:
            seeds.append(fen)
            if len(seeds) >= n:
                break
    return seeds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", required=False, default=None, help="Scan binary (player, unless --player-jass-bin)")
    ap.add_argument("--jass", required=True, help="jass binary (neutral referee)")
    # CHAMPION self-play (chaîne itérative longue : pilote = champion(t), distribution MOBILE) : le PLAYER
    # devient jass avec le pattern champion, pas Scan. asym par depth/movetime = TEACHER autonome (côté fort =
    # recherche plus profonde que la feuille d5). Le referee reste --jass. Scan devient inutile.
    ap.add_argument("--player-jass-bin", default=None,
                    help="jass binary to use as the PLAYER (champion self-play) instead of Scan")
    ap.add_argument("--player-pattern", default=None,
                    help="pattern (.pjtw) the jass player uses (the champion), with --player-jass-bin")
    ap.add_argument("--seeds", required=True, type=Path, help="JNNW to sample opening seeds from")
    ap.add_argument("--out", required=True, type=Path, help="output JNNW")
    ap.add_argument("--games", type=int, default=2000)
    ap.add_argument("--depth", type=int, default=8, help="Scan search depth per move")
    ap.add_argument("--max-plies", type=int, default=200)
    ap.add_argument("--min-pieces", type=int, default=40, help="seed piece-count floor (early game)")
    ap.add_argument("--sample-every", type=int, default=1, help="keep 1 position in N")
    # DIVERSITY (piste 3) — force decisive, varied self-play instead of quiet/drawish
    # Scan-vs-equal-Scan games (the 0327 low-contrast problem). Two knobs:
    #   --weak-depth D2 : the two sides play at DIFFERENT depths (strong --depth vs
    #     weak D2), the strong side randomized per game → decisive games, gradient.
    #   --depth-jitter J: per game, the (strong) depth is drawn from [depth-J, depth].
    ap.add_argument("--weak-depth", type=int, default=None,
                    help="weaker side's Scan depth (strong=--depth); asymmetric self-play")
    ap.add_argument("--depth-jitter", type=int, default=0,
                    help="per-game random depth reduction in [0, J] on the strong side")
    # ASYMMETRY BY MOVETIME (Scan-prof briefing phase 0): strong side plays with a
    # long move-time, weak side with a very short one. Overrides depth-based asym
    # when both are set. The STRONG side's moves are the only ones extracted as
    # preferences (the weak side is deliberately degraded → its moves are noise).
    ap.add_argument("--strong-movetime", type=float, default=None,
                    help="strong side Scan move-time (s); enables movetime asymmetry")
    ap.add_argument("--weak-movetime", type=float, default=None,
                    help="weak side Scan move-time (s); pair with --strong-movetime")
    # PREFERENCE EXTRACTION (bras-M format): for every STRONG-side quiet ply out of
    # book, emit (parent JNNW record, played from/to) — consumed downstream by
    # `jass --gen-siblings --played-moves` to build (played ≻ sibling) pairs.
    ap.add_argument("--pref-parents", type=Path, default=None,
                    help="output JNNW of parent positions (strong side to move)")
    ap.add_argument("--pref-moves", type=Path, default=None,
                    help="output raw 2-byte from/to per parent (aligned with --pref-parents)")
    ap.add_argument("--holdout-parents", type=Path, default=None,
                    help="optional by-game holdout split of parents (md5(opening)%%mod==0)")
    ap.add_argument("--holdout-moves", type=Path, default=None,
                    help="optional by-game holdout split of moves")
    ap.add_argument("--holdout-mod", type=int, default=10,
                    help="1/mod of games (by opening hash) routed to holdout")
    ap.add_argument("--skip-book", type=int, default=8,
                    help="skip the first N plies (book/theory) when extracting prefs")
    ap.add_argument("--keep-draw-frac", type=float, default=0.2,
                    help="fraction of DRAWN games to keep (decisive-first filter)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--nshards", type=int, default=1,
                    help="total parallel shards (all must share the SAME --seed)")
    ap.add_argument("--shard", type=int, default=0, help="this shard's index in [0,nshards)")
    # ---- L3 : gymnase de conversion (B2) + arbitre-au-cap (B1). Défauts OFF = comportement identique. ----
    ap.add_argument("--seed-pool", type=Path, default=None,
                    help="B2: FEN pool de positions GAGNÉES (gymnase conversion, ex. data/conversion_pool.fen)")
    ap.add_argument("--seed-frac", type=float, default=0.0,
                    help="B2: fraction des parties démarrées sur le pool (chaque graine jouée en PAIRE couleurs)")
    ap.add_argument("--cap-arbiter", choices=["none", "d14"], default="none",
                    help="B1: adjuger les nulles d'ÉPUISEMENT (ply-cap + 25-move) par deep-relabel d14+egdb au lieu de nulle")
    ap.add_argument("--egdb-dir", default=None, help="répertoire egdb pour --cap-arbiter (TB-exact si atteignable)")
    ap.add_argument("--arb-depth", type=int, default=14, help="profondeur de l'arbitre-au-cap")
    ap.add_argument("--label-src-out", type=Path, default=None,
                    help="D1: sidecar 1 octet/position aligné au JNNW (0=ONP on-policy, 1=GYM gymnase, 2=CAP arbitre)")
    ap.add_argument("--trajectory-out", type=Path, default=None,
                    help="JSONL(.gz) replayable: one complete game with boundaries, FENs and played moves per line")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    seeds = load_seeds(args.seeds, args.min_pieces, rng, args.games,
                       shard=args.shard, nshards=args.nshards)
    if not seeds:
        print("error: no seed positions found", file=sys.stderr)
        return 1
    n_pool_seeds = 0   # D1: nombre de parties gymnase EN TÊTE de `seeds` (tag GYM vs ONP)
    if args.seed_pool and args.seed_frac > 0:
        pool_games = round(len(seeds) * args.seed_frac)
        seeds = seeds[:max(0, len(seeds) - pool_games)]                 # réduit l'on-policy d'autant
        pool_seeds = load_pool(args.seed_pool, rng, max(1, pool_games // 2),
                               shard=args.shard, nshards=args.nshards)
        seeds = pool_seeds + seeds                                      # gymnase en tête
        n_pool_seeds = len(pool_seeds)
        print(f"  seed-pool (B2): {len(pool_seeds)} parties gymnase (paires) + "
              f"{len(seeds) - len(pool_seeds)} on-policy (frac~{args.seed_frac})")
    print(f"scan-selfplay: {len(seeds)} seeds (>= {args.min_pieces}p), Scan depth {args.depth}")

    mt_asym = args.strong_movetime is not None and args.weak_movetime is not None
    pref = args.pref_parents is not None and args.pref_moves is not None
    scan_peer = None
    if args.player_jass_bin:
        # CHAMPION self-play : le player = jass + pattern champion (distribution mobile).
        def _mk_player():
            return cv.JassEngine(args.player_jass_bin, pattern_path=args.player_pattern)
        scan = _mk_player()
        scan_weak = (_mk_player() if (args.weak_depth or mt_asym) else None)
        # A stateful HUB engine cannot play both colours through the same
        # process: play_game synchronizes every Jass player after each move,
        # so aliasing white and black applies the move twice. Keep an
        # independent peer for symmetric champion self-play.
        scan_peer = (_mk_player() if scan_weak is None else None)
        print(f"  player=JASS(champion) pattern={args.player_pattern}")
    else:
        if not args.scan:
            print("error: --scan required unless --player-jass-bin is set", file=sys.stderr)
            return 1
        scan = cv.ScanEngine(args.scan, bb_size=0)
        # Asymmetric-strength self-play (diversity): a SECOND Scan, weaker by depth OR movetime.
        scan_weak = (cv.ScanEngine(args.scan, bb_size=0)
                     if (args.weak_depth or mt_asym) else None)
    if scan_weak is not None:
        if mt_asym:
            print(f"  asym-movetime: strong mt {args.strong_movetime}s vs weak mt "
                  f"{args.weak_movetime}s (strong side randomized per game)")
        else:
            print(f"  asym-depth: strong depth {args.depth} vs weak depth {args.weak_depth} "
                  f"(strong side randomized per game)")
    if pref:
        print(f"  pref-extract: strong-side quiet plies, skip-book={args.skip_book}, "
              f"keep-draw-frac={args.keep_draw_frac}, holdout 1/{args.holdout_mod} by opening")
    referee = cv.Referee(args.jass)
    records = bytearray()
    labels = bytearray()   # D1: 1 octet/position aligné à `records` (0=ONP, 1=GYM, 2=CAP)
    n_pos = 0
    exhaust_games = []   # B1: (final_fen, [(k,fen) échantillonnés]) des nulles d'épuisement à adjuger
    # preference buffers (train + optional by-game holdout)
    tr_par, tr_mov, ho_par, ho_mov = bytearray(), bytearray(), bytearray(), bytearray()
    n_tr = n_ho = n_dec = n_drawkept = 0
    wmap = {"W": 1, "D": 0, "L": -1}
    trajectory_handle = (open_trajectory_output(args.trajectory_out)
                         if args.trajectory_out else None)
    try:
        for g, opening in enumerate(seeds):
            # per-game depth jitter on the strong side
            sd = args.depth - (rng.randint(0, args.depth_jitter) if args.depth_jitter else 0)
            sd = max(2, sd)
            strong_color = None  # None => symmetric (extract all sides)
            try:
                if scan_weak is not None:
                    # assign strong/weak to the two sides, randomized per game
                    if mt_asym:
                        scan.default_movetime = args.strong_movetime; scan.default_depth = None
                        scan_weak.default_movetime = args.weak_movetime; scan_weak.default_depth = None
                    else:
                        scan.default_depth = sd; scan.default_movetime = None
                        scan_weak.default_depth = args.weak_depth; scan_weak.default_movetime = None
                    if rng.random() < 0.5:
                        white, black = scan, scan_weak; strong_color = "W"
                    else:
                        white, black = scan_weak, scan; strong_color = "B"
                    r = cv.play_game(white, black, referee, opening,
                                     max_plies=args.max_plies)
                elif args.strong_movetime is not None:
                    # SYMÉTRIQUE-MOVETIME (parties ÉQUILIBRÉES fort-vs-fort) : les 2 côtés jouent à strong-movetime,
                    # strong_color=None => on extrait LES 2 CÔTÉS (2× de data/partie ; positions contestées à égalité).
                    r = cv.play_game(scan, scan_peer or scan, referee, opening,
                                     movetime=args.strong_movetime, max_plies=args.max_plies)
                else:
                    r = cv.play_game(scan, scan_peer or scan, referee, opening,
                                     depth=sd, max_plies=args.max_plies)
            except Exception as exc:  # noqa: BLE001 — keep going on a flaky game
                print(f"  game {g}: {exc}", file=sys.stderr)
                continue
            _reason = getattr(r, "reason", "") or ""
            if trajectory_handle is not None:
                row = trajectory_record(
                    game_index=g,
                    shard=args.shard,
                    opening=opening,
                    seed_source="GYM" if g < n_pool_seeds else "ONP",
                    outcome=r.outcome,
                    reason=_reason,
                    fens=r.fens,
                    moves=r.moves,
                )
                trajectory_handle.write(
                    json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
                )
            _exhaust = (args.cap_arbiter != "none" and r.outcome == "D" and r.fens
                        and (_reason.startswith("ply cap") or _reason.startswith("25-move")))
            if _exhaust:
                # B1 : ne PAS étiqueter nulle ; bufferiser pour adjuger la finale par d14+egdb
                kept = [(k, fen) for k, fen in enumerate(r.fens) if not (k % args.sample_every)]
                exhaust_games.append((r.fens[-1], kept))
            else:
                _tag = 1 if g < n_pool_seeds else 0   # D1: GYM (partie gymnase) vs ONP (on-policy)
                ow = wmap.get(r.outcome, 0)
                for k, fen in enumerate(r.fens):
                    if k % args.sample_every:
                        continue
                    try:
                        side = fen.split(":", 1)[0].strip()
                    except Exception:
                        continue
                    wdl = ow if side == "W" else -ow
                    records += fen_to_record(fen, wdl)
                    labels.append(_tag)
                    n_pos += 1

            # ---- preference extraction (strong-side quiet plies, decisive-first) ----
            if pref:
                decisive = r.outcome in ("W", "L")
                keep = decisive or (rng.random() < args.keep_draw_frac)
                if keep:
                    if decisive: n_dec += 1
                    else: n_drawkept += 1
                    hold = (int(hashlib.md5(opening.encode()).hexdigest(), 16)
                            % max(1, args.holdout_mod) == 0) and args.holdout_parents
                    for k, mv_str in enumerate(r.moves):
                        parent = r.fens[k]
                        side = parent.split(":", 1)[0].strip()
                        if strong_color is not None and side != strong_color:
                            continue
                        if k < args.skip_book:
                            continue
                        if "x" in mv_str:  # quiet-only (captures = trivial/forced)
                            continue
                        try:
                            frm, to = (int(x) for x in mv_str.split("-"))
                        except Exception:
                            continue
                        if not (1 <= frm <= 50 and 1 <= to <= 50):
                            continue
                        rec = fen_to_record(parent, 0)
                        if hold:
                            ho_par += rec; ho_mov += bytes([frm, to]); n_ho += 1
                        else:
                            tr_par += rec; tr_mov += bytes([frm, to]); n_tr += 1

            if (g + 1) % 50 == 0:
                print(f"  {g+1}/{len(seeds)} games, {n_pos} positions"
                      + (f", prefs tr={n_tr} ho={n_ho}" if pref else ""), flush=True)
    finally:
        try: scan.close()
        except Exception: pass
        if scan_peer is not None:
            try: scan_peer.close()
            except Exception: pass
        if scan_weak is not None:
            try: scan_weak.close()
            except Exception: pass
        try: referee.close()
        except Exception: pass
        if trajectory_handle is not None:
            trajectory_handle.close()

    # ---- B1 : arbitre-au-cap — adjuge les finales d'ÉPUISEMENT par deep-relabel d14+egdb ----
    # (TB-exact si atteignable, sinon signe d14) et relabelle TOUTE la partie avec l'issue vraie,
    # au lieu de « nulle par épuisement » (le mensonge ~19% que la position gagnée n'a pas été convertie).
    if args.cap_arbiter == "d14" and exhaust_games:
        finals = b"".join(fen_to_record(fg[0], 0) for fg in exhaust_games)
        tin = f"{args.out}.caps.{args.shard}.in"
        tout = f"{args.out}.caps.{args.shard}.out"
        Path(tin).write_bytes(b"JNNW" + struct.pack("<I", len(exhaust_games)) + finals)
        cmd = [args.jass, "--deep-relabel", tin, tout, str(args.arb_depth)]
        if args.egdb_dir:
            cmd += ["--egdb", args.egdb_dir]
        ok = False
        try:
            subprocess.run(cmd, capture_output=True, timeout=len(exhaust_games) * 30 + 120)
            ok = Path(tout).exists()
        except Exception as exc:  # noqa: BLE001
            print(f"  cap-arbiter FAIL ({exc}); fallback nulle", file=sys.stderr)
        rel = Path(tout).read_bytes() if ok else b""
        cap_fires = cap_decisive = cap_draw = 0
        for gi, (final_fen, kept) in enumerate(exhaust_games):
            wdl_stm = (struct.unpack_from("<b", rel, 8 + gi * REC + 37)[0]
                       if ok and 8 + gi * REC + REC <= len(rel) else 0)
            fside = final_fen.split(":", 1)[0].strip()[:1]
            ow = wdl_stm if fside == "W" else -wdl_stm   # issue partie en blanc-POV
            cap_fires += 1
            cap_decisive += (wdl_stm != 0)
            cap_draw += (wdl_stm == 0)
            for k, fen in kept:
                side = fen.split(":", 1)[0].strip()
                records += fen_to_record(fen, ow if side == "W" else -ow)
                labels.append(2)   # D1: CAP (arbitre-au-cap, label TB/d14)
                n_pos += 1
        for p in (tin, tout):
            try: os.remove(p)
            except OSError: pass
        print(f"  cap-arbiter d{args.arb_depth}: {cap_fires} nulles d'épuisement adjugées "
              f"({cap_decisive} décisives = mensonge corrigé, {cap_draw} confirmées nulles)", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", n_pos))
        f.write(records)
    print(f"wrote {args.out} ({n_pos} positions from {len(seeds)} Scan self-play games)")
    if args.label_src_out:
        assert len(labels) == n_pos, f"label/record désalignés: {len(labels)} != {n_pos}"
        Path(args.label_src_out).write_bytes(bytes(labels))
        import collections as _c
        dist = dict(_c.Counter(labels))
        print(f"wrote {args.label_src_out} ({len(labels)} label bytes ; ONP/GYM/CAP = "
              f"{dist.get(0,0)}/{dist.get(1,0)}/{dist.get(2,0)})")
    if args.trajectory_out:
        print(f"wrote {args.trajectory_out} (replayable trajectory sidecar)")

    if pref:
        def _write_pref(par_path, mov_path, par_buf, mov_buf, n):
            par_path.parent.mkdir(parents=True, exist_ok=True)
            with par_path.open("wb") as f:
                f.write(b"JNNW"); f.write(struct.pack("<I", n)); f.write(par_buf)
            mov_path.write_bytes(bytes(mov_buf))
        _write_pref(args.pref_parents, args.pref_moves, tr_par, tr_mov, n_tr)
        print(f"wrote {args.pref_parents} ({n_tr} strong-side quiet parents; "
              f"decisive-games={n_dec}, draws-kept={n_drawkept})")
        if args.holdout_parents and args.holdout_moves:
            _write_pref(args.holdout_parents, args.holdout_moves, ho_par, ho_mov, n_ho)
            print(f"wrote {args.holdout_parents} ({n_ho} held-out parents by opening hash)")

    return 0 if n_pos else 1


if __name__ == "__main__":
    raise SystemExit(main())
