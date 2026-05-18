#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Fetch Lidraughts games into a local SQLite store on the Hetzner runner.

This is the Cycle-8-pre data acquisition step: build up a corpus of
rated human games (typical filter: rating 1600–2300, standard variant)
that will later be converted to JNNW training records by
`tools/pdn_to_jnnw.py` and blended into `train_v3.py`.

Adapted from the sister project `jfrancoiscollin/Ai-draught`
(`backend/lidraughts_fetcher.py`, same author): the player discovery
strategy (leaderboard + curated teams + recent tournaments + static
fallback) and the games-by-user endpoint mechanics are ported as-is.
The persistence side is rewritten: instead of returning a single PDN
text blob, we insert one row per game into the schema declared in
`data/expert_games.schema.sql`.

Why this lives in jass and not in Draught Master
------------------------------------------------
Draught Master fetches games to populate its opening-book / pedagogy
features. jass fetches games to populate its training corpus. Same
upstream, different consumers. Keeping two thin Python clients is
strictly simpler than factoring a shared library between two repos
that ship on different cadences. If a shared library ever becomes
worthwhile we can do it as a follow-up refactor.

Idempotency
-----------
The schema has `UNIQUE (source, source_id)` on `expert_games`.
`INSERT OR IGNORE` makes every re-run a true resume: already-seen
Lidraughts game ids are silently dropped, so interrupting the
fetcher mid-run and restarting it picks up exactly where it left
off. The fetcher also persists per-username progress in
`fetcher_state` so we don't re-hit the same user's games endpoint.

CLI
---
    python3 tools/fetch_lidraughts_games.py            \\
        --db /root/jass/data/expert_games.db           \\
        --min-rating 1600 --max-rating 2300            \\
        --target-games 100000                          \\
        --max-games-per-user 200                       \\
        --rate-sleep 0.5                               \\
        --schema data/expert_games.schema.sql
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

# `requests` is the only third-party dep; install via `pip install requests`.
# The Hetzner bootstrap already pulls it in transitively via the existing
# pipeline tools — we depend on the same module here.
import requests


LIDRAUGHTS_API = "https://lidraughts.org"

# Pulled verbatim from the source fetcher: known draughts-leaning teams.
KNOWN_TEAMS = [
    "lidraughts-draughts-community",
    "draughts-players",
    "international-draughts",
    "world-draughts",
    "netherlands-draughts",
    "france-draughts",
    "russia-draughts",
    "dammen",
    "draughts",
    "dam",
]

# Curated fallback list of real Lidraughts usernames with approximate
# ratings (snapshot 2025). Used only when the live API can't be reached.
# Ported as-is from the source fetcher; kept here for completeness so
# the jass fetcher remains functional even if all four discovery paths
# above fail.
STATIC_PLAYERS: list[dict] = [
    # 2400+
    {"username": "el-negron",        "rating": 2450},
    {"username": "roepstoel",        "rating": 2435},
    {"username": "roel",             "rating": 2415},
    {"username": "janko",            "rating": 2400},
    # 2300-2399
    {"username": "pbp7055",          "rating": 2385},
    {"username": "alvaro",           "rating": 2375},
    {"username": "guntis",           "rating": 2365},
    {"username": "merijn",           "rating": 2355},
    {"username": "SuperDam",         "rating": 2345},
    {"username": "Roel_Boomstra",    "rating": 2300},
    # 2200-2299
    {"username": "Sharkbite",        "rating": 2275},
    {"username": "macaca",           "rating": 2255},
    {"username": "Draughts-knight",  "rating": 2240},
    {"username": "GOAT64",           "rating": 2220},
    {"username": "Zaka",             "rating": 2205},
    {"username": "damwolf",          "rating": 2290},
    {"username": "pietje",           "rating": 2265},
    {"username": "tigran64",         "rating": 2250},
    {"username": "damlover",         "rating": 2235},
    # 2100-2199
    {"username": "DamSpeler",        "rating": 2175},
    {"username": "chessspider",      "rating": 2155},
    {"username": "damgenot",         "rating": 2140},
    {"username": "tonyp",            "rating": 2125},
    {"username": "LaCulpada",        "rating": 2105},
    # 2000-2099
    {"username": "draughts_fan",     "rating": 2080},
    {"username": "WimS",             "rating": 2065},
    {"username": "ItsHendo",         "rating": 2045},
    {"username": "Raf2000",          "rating": 2025},
    {"username": "Adri10",           "rating": 2005},
    # 1900-1999
    {"username": "damspeler2",       "rating": 1985},
    {"username": "DamTrainer",       "rating": 1965},
    {"username": "BramB",            "rating": 1940},
    {"username": "NicolaasV",        "rating": 1920},
    # 1800-1899
    {"username": "MidLevel1",        "rating": 1855},
    {"username": "Regular1",         "rating": 1800},
    # 1600-1799
    {"username": "ClubPlayer",       "rating": 1755},
    {"username": "Amateur1",         "rating": 1705},
    {"username": "Casual1",          "rating": 1605},
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, *, headers: dict | None = None,
              params: dict | None = None, timeout: int = 60,
              stream: bool = False) -> requests.Response:
    return requests.get(url, headers=headers or {}, params=params,
                        timeout=timeout, stream=stream)


# ---------------------------------------------------------------------------
# Player discovery (4 strategies, deduplicated)
# ---------------------------------------------------------------------------

def _fetch_leaderboard(perf_type: str, log: logging.Logger) -> list[dict]:
    endpoints = [
        f"{LIDRAUGHTS_API}/api/player/top/200/{perf_type}",
        f"{LIDRAUGHTS_API}/api/player/top/200/standard",
        f"{LIDRAUGHTS_API}/api/player/top/200",
        f"{LIDRAUGHTS_API}/api/player",
    ]
    for url in endpoints:
        try:
            r = _http_get(url, headers={"Accept": "application/json"}, timeout=15)
            r.raise_for_status()
            data = r.json()
            users = data if isinstance(data, list) else []
            if not users and isinstance(data, dict):
                for key in ("users", "results", "players", perf_type, "standard"):
                    val = data.get(key)
                    if isinstance(val, list):
                        users = val
                        break

            out: list[dict] = []
            for u in users:
                username = u.get("username") or u.get("id", "")
                rating = None
                perfs = u.get("perfs", {})
                for v in (perf_type, "standard", "international"):
                    r2 = perfs.get(v, {}).get("rating")
                    if r2:
                        rating = r2
                        break
                if rating is None:
                    rating = u.get("rating") or u.get("elo")
                if username and rating:
                    out.append({"username": username, "rating": int(rating)})
            if out:
                log.info("leaderboard: %d players from %s", len(out), url)
                return out
        except Exception as exc:
            log.warning("leaderboard failed (%s): %s", url, exc)
    return []


def _fetch_team_players(team_ids: list[str], log: logging.Logger) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for tid in team_ids:
        url = f"{LIDRAUGHTS_API}/api/team/{tid}/users"
        try:
            r = _http_get(url, headers={"Accept": "application/x-ndjson"},
                          timeout=20, stream=True)
            if r.status_code != 200:
                continue
            count = 0
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    username = obj.get("username") or obj.get("id", "")
                    if not username or username.lower() in seen:
                        continue
                    perfs = obj.get("perfs", {})
                    rating = None
                    for v in ("standard", "frisian", "antidraughts", "breakthrough"):
                        rr = perfs.get(v, {}).get("rating")
                        if rr and rr > 500:
                            rating = rr
                            break
                    if username and rating:
                        out.append({"username": username, "rating": int(rating)})
                        seen.add(username.lower())
                        count += 1
                except Exception:
                    pass
            if count:
                log.info("team '%s': %d players", tid, count)
        except Exception as exc:
            log.debug("team skip '%s': %s", tid, exc)
    return out


def _fetch_tournament_players(log: logging.Logger) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    try:
        r = _http_get(f"{LIDRAUGHTS_API}/api/tournament",
                      headers={"Accept": "application/json"}, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        tournaments: list = []
        if isinstance(data, list):
            tournaments = data[:10]
        elif isinstance(data, dict):
            for key in ("finished", "started", "created"):
                t = data.get(key, [])
                if isinstance(t, list):
                    tournaments.extend(t[:4])

        for t in tournaments[:8]:
            tid = t.get("id") if isinstance(t, dict) else None
            if not tid:
                continue
            try:
                r2 = _http_get(
                    f"{LIDRAUGHTS_API}/api/tournament/{tid}/results",
                    headers={"Accept": "application/x-ndjson"},
                    params={"nb": 200}, timeout=15,
                )
                for line in r2.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        username = obj.get("username", "")
                        rating = obj.get("rating")
                        if username and rating and username.lower() not in seen:
                            out.append({"username": username, "rating": int(rating)})
                            seen.add(username.lower())
                    except Exception:
                        pass
            except Exception:
                pass
        if out:
            log.info("tournaments: %d unique players", len(out))
    except Exception as exc:
        log.warning("tournament fetch failed: %s", exc)
    return out


def discover_players(rating_min: int, rating_max: int,
                     perf_type: str, log: logging.Logger) -> list[dict]:
    """Discover Lidraughts usernames in the given rating range, dedup'd.

    Combines leaderboard + teams + tournaments + static fallback. Returns
    the rating-filtered pool, unshuffled (caller decides ordering).
    """
    combined: list[dict] = []
    seen: set[str] = set()

    def _add(plist: list[dict]) -> None:
        for p in plist:
            key = p["username"].lower()
            if key not in seen:
                seen.add(key)
                combined.append(p)

    _add(_fetch_leaderboard(perf_type, log))
    _add(_fetch_team_players(KNOWN_TEAMS, log))
    _add(_fetch_tournament_players(log))
    _add(STATIC_PLAYERS)

    in_range = [p for p in combined if rating_min <= p["rating"] <= rating_max]
    log.info("discover_players: %d candidates in [%d,%d] (total seen %d)",
             len(in_range), rating_min, rating_max, len(combined))
    return in_range


# ---------------------------------------------------------------------------
# Per-user game fetching
# ---------------------------------------------------------------------------

def fetch_user_games_pdn(username: str, max_games: int,
                         log: logging.Logger) -> str:
    """Return a multi-game PDN text blob for `username`, or '' on failure.

    Tries `Accept: application/x-draughts-pdn` first (one HTTP round-trip,
    Lidraughts emits a concatenated PDN). Falls back to NDJSON + manual
    reconstruction if the PDN endpoint isn't honoured.
    """
    url = f"{LIDRAUGHTS_API}/api/games/user/{username}"
    params = {"max": min(max_games, 500), "variant": "standard"}
    try:
        r = _http_get(url, headers={"Accept": "application/x-draughts-pdn"},
                      params=params, timeout=90)
        r.raise_for_status()
        text = r.text.strip()
        if text and "[" in text:
            return text
        r2 = _http_get(url, headers={"Accept": "application/x-ndjson"},
                       params=params, timeout=90)
        r2.raise_for_status()
        return _ndjson_to_pdn(r2.text, log)
    except Exception as exc:
        log.error("fetch '%s' failed: %s", username, exc)
        return ""


def _ndjson_to_pdn(ndjson_text: str, log: logging.Logger) -> str:
    games: list[str] = []
    for line in ndjson_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            moves = (obj.get("moves") or obj.get("pgn")
                     or obj.get("pdn") or obj.get("notation") or "")
            if not moves:
                continue
            players = obj.get("players", {})
            white = (players.get("white", {}).get("user", {}).get("name")
                     or players.get("white", {}).get("name", "?"))
            black = (players.get("black", {}).get("user", {}).get("name")
                     or players.get("black", {}).get("name", "?"))
            wr = players.get("white", {}).get("rating")
            br = players.get("black", {}).get("rating")
            winner = obj.get("winner", "")
            if winner == "white":
                result_lidraughts = "2-0"
            elif winner == "black":
                result_lidraughts = "0-2"
            else:
                result_lidraughts = "1-1"
            lid = obj.get("id", "")
            date = obj.get("createdAt") or obj.get("lastMoveAt") or ""
            tags = [
                f'[Site "lidraughts.org"]',
                f'[GameId "{lid}"]',
                f'[White "{white}"]',
                f'[Black "{black}"]',
                f'[Result "{result_lidraughts}"]',
            ]
            if wr:
                tags.append(f'[WhiteElo "{wr}"]')
            if br:
                tags.append(f'[BlackElo "{br}"]')
            if date:
                tags.append(f'[UTCDate "{date}"]')
            pdn = "\n".join(tags) + "\n\n" + moves + "\n"
            games.append(pdn)
        except Exception:
            pass
    log.info("_ndjson_to_pdn: built %d games", len(games))
    return "\n\n".join(games)


# ---------------------------------------------------------------------------
# PDN → row extraction
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r'^\[\s*(\w+)\s+"([^"]*)"\s*\]\s*$', re.MULTILINE)


def split_pdn(text: str) -> list[str]:
    """Split a multi-game PDN blob into one string per game.

    PDN game shape:

        [Tag1 "val"]
        [Tag2 "val"]
        [Result "..."]

        1. move move 2. move move ... 1-0

        [Tag1 "val"]   ← next game starts here
        ...

    The boundary between two games is "a `[Tag …]` line appearing
    AFTER a move-text line". A naive split on `(?=\[Tag)` would
    cut at every tag (each game has 7+ tags), reducing a 200-game
    PDN to ~1400 fragments, none of which has a complete tag set.

    Bug diagnosed 2026-05-18: the runner's first 0014 run fetched
    228 users × ~3000 PDN games each but kept 0 — extract_row()
    returned None on every fragment because each fragment held a
    single tag with no [Result …].

    This implementation walks line by line, tracks whether we're
    in the tag block or the moves, and flushes the current game
    whenever we see a tag line transition back from moves.
    """
    games: list[str] = []
    current: list[str] = []
    in_moves = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            # Blank line: belongs to the current game (separator
            # between tag block and moves, or trailing whitespace).
            if current:
                current.append(line)
            continue
        is_tag = stripped.startswith('[')
        if is_tag and in_moves:
            # New game starts: flush the previous one.
            flushed = ''.join(current).strip()
            if flushed and '[' in flushed:
                games.append(flushed)
            current = [line]
            in_moves = False
        else:
            current.append(line)
            if not is_tag:
                in_moves = True
    # Trailing game.
    flushed = ''.join(current).strip()
    if flushed and '[' in flushed:
        games.append(flushed)
    return games


def parse_pdn_tags(game_pdn: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for m in _TAG_RE.finditer(game_pdn):
        tags[m.group(1).lower()] = m.group(2)
    return tags


_RESULT_NORMALISATION = {
    # Lidraughts / Lichess convention -> FMJD convention
    "2-0": "1-0",
    "0-2": "0-1",
    "1-1": "1/2-1/2",
    # Already FMJD
    "1-0": "1-0",
    "0-1": "0-1",
    "1/2-1/2": "1/2-1/2",
    # Sometimes seen variants
    "½-½": "1/2-1/2",
    "1/2": "1/2-1/2",
}


def normalise_result(raw: str) -> str | None:
    return _RESULT_NORMALISATION.get(raw.strip())


def count_plies(game_pdn: str) -> int:
    """Rough ply count: split moves out, ignore tag lines and comments."""
    body = _strip_pdn_body(game_pdn)
    # Strip move number prefixes like "1." or "1..." and result tokens.
    body = re.sub(r'\b\d+\.+', ' ', body)
    body = re.sub(r'\b(1-0|0-1|1/2-1/2|2-0|0-2|1-1|\*)\b', ' ', body)
    tokens = [t for t in body.split() if t and t[0].isdigit()]
    return len(tokens)


def _strip_pdn_body(game_pdn: str) -> str:
    """Drop tag lines and comments {...}, keep the move text."""
    lines: list[str] = []
    for ln in game_pdn.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("["):
            continue
        lines.append(s)
    body = " ".join(lines)
    # Strip {...} comments.
    body = re.sub(r'\{[^}]*\}', ' ', body)
    return body


def extract_row(game_pdn: str, source: str) -> dict | None:
    """Build the SQLite row dict from one game's PDN string.

    Returns None when the game is unusable (no result, no moves, etc.).
    """
    tags = parse_pdn_tags(game_pdn)
    raw_result = tags.get("result", "")
    result = normalise_result(raw_result)
    if not result:
        return None

    source_id = tags.get("gameid") or tags.get("lichessid") or None
    if source_id is None and tags.get("site", "").lower().startswith("lidraughts"):
        # Fall back: maybe the site tag carries the id (e.g. "lidraughts.org/abc123")
        m = re.search(r'lidraughts\.org/([A-Za-z0-9]+)', tags.get("site", ""))
        if m:
            source_id = m.group(1)

    # Variant: lidraughts uses "international" for our standard 10x10.
    variant_raw = tags.get("variant", "").strip().lower()
    variant = "standard"
    if variant_raw in ("frisian", "antidraughts", "breakthrough", "frysk"):
        variant = variant_raw
    elif variant_raw and variant_raw not in ("international", "standard", ""):
        variant = variant_raw

    plies = count_plies(game_pdn)
    if plies < 1:
        return None

    def _maybe_int(s: str | None) -> int | None:
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    # Date: try several common keys.
    date = (tags.get("utcdate") or tags.get("date")
            or tags.get("eventdate") or None)

    return {
        "source": source,
        "source_id": source_id,
        "date": date,
        "white_name": tags.get("white") or None,
        "black_name": tags.get("black") or None,
        "white_rating": _maybe_int(tags.get("whiteelo")),
        "black_rating": _maybe_int(tags.get("blackelo")),
        "result": result,
        "num_plies": plies,
        "event": tags.get("event") or None,
        "variant": variant,
        "pdn": game_pdn.strip(),
    }


# ---------------------------------------------------------------------------
# SQLite layer
# ---------------------------------------------------------------------------

def open_db(db_path: Path, schema_path: Path | None) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    if schema_path and schema_path.is_file():
        conn.executescript(schema_path.read_text())
    return conn


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cur = conn.executemany(
        """
        INSERT OR IGNORE INTO expert_games (
            source, source_id, date, white_name, black_name,
            white_rating, black_rating, result, num_plies,
            event, variant, pdn
        ) VALUES (
            :source, :source_id, :date, :white_name, :black_name,
            :white_rating, :black_rating, :result, :num_plies,
            :event, :variant, :pdn
        )
        """,
        rows,
    )
    conn.commit()
    return cur.rowcount or 0


def fetcher_state_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM fetcher_state WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def fetcher_state_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO fetcher_state (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE
        SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )
    conn.commit()


def total_games(conn: sqlite3.Connection, source: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM expert_games WHERE source = ?", (source,)
    ).fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db", type=Path, required=True,
                   help="SQLite path. Created if missing.")
    p.add_argument("--schema", type=Path,
                   default=Path("data/expert_games.schema.sql"),
                   help="Path to the schema .sql; applied on every run "
                        "(idempotent via IF NOT EXISTS).")
    p.add_argument("--min-rating", type=int, default=1600)
    p.add_argument("--max-rating", type=int, default=2300)
    p.add_argument("--target-games", type=int, default=100_000,
                   help="Stop when the DB holds this many `lidraughts` rows.")
    p.add_argument("--max-games-per-user", type=int, default=200,
                   help="Cap per Lidraughts API call. Lidraughts hard "
                        "limit is 500.")
    p.add_argument("--rate-sleep", type=float, default=0.5,
                   help="Sleep between per-user requests (seconds). "
                        "Lidraughts is generous; 0.5 is conservative.")
    p.add_argument("--perf-type", default="standard",
                   help="Lidraughts perf-type filter on the leaderboard.")
    p.add_argument("--shuffle-seed", type=int, default=None,
                   help="Deterministic player shuffle. Default: random.")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("fetch_lidraughts")

    conn = open_db(args.db, args.schema)
    initial = total_games(conn, "lidraughts")
    log.info("opened %s — already holds %d lidraughts games", args.db, initial)
    if initial >= args.target_games:
        log.info("target %d already met; nothing to do.", args.target_games)
        return 0

    log.info("discovering players in [%d, %d] …",
             args.min_rating, args.max_rating)
    candidates = discover_players(args.min_rating, args.max_rating,
                                  args.perf_type, log)
    if not candidates:
        log.error("no candidate players found. Lidraughts API may be down.")
        return 4

    if args.shuffle_seed is not None:
        random.Random(args.shuffle_seed).shuffle(candidates)
    else:
        random.shuffle(candidates)

    drained_set: set[str] = set()
    drained_raw = fetcher_state_get(conn, "drained_users") or ""
    if drained_raw:
        drained_set = {u for u in drained_raw.split("\n") if u}
    log.info("skipping %d already-drained users from previous runs",
             len(drained_set))

    games_in_db = initial
    for entry in candidates:
        if games_in_db >= args.target_games:
            log.info("target %d reached — stopping", args.target_games)
            break
        username = entry["username"]
        if username.lower() in drained_set:
            continue

        pdn_blob = fetch_user_games_pdn(username, args.max_games_per_user, log)
        if not pdn_blob:
            log.info("'%s': no games returned, skipping", username)
        else:
            games = split_pdn(pdn_blob)
            rows: list[dict] = []
            for g in games:
                row = extract_row(g, source="lidraughts")
                if not row:
                    continue
                # Apply rating floor / variant filter at insert time too,
                # so the DB stays tight even if the discovery step is loose.
                if row["variant"] != "standard":
                    continue
                wr, br = row["white_rating"], row["black_rating"]
                if wr is None or br is None:
                    continue
                if min(wr, br) < args.min_rating:
                    continue
                rows.append(row)
            inserted = insert_rows(conn, rows)
            games_in_db = total_games(conn, "lidraughts")
            log.info("'%s' (rating %d): %d PDN games -> %d kept, "
                     "%d new inserts. DB total = %d/%d.",
                     username, entry["rating"], len(games), len(rows),
                     inserted, games_in_db, args.target_games)

        drained_set.add(username.lower())
        fetcher_state_set(conn, "drained_users",
                          "\n".join(sorted(drained_set)))
        time.sleep(args.rate_sleep)

    final = total_games(conn, "lidraughts")
    log.info("done. %d lidraughts games in DB (added %d this run).",
             final, final - initial)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
