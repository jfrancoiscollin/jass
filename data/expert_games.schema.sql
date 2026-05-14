-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Copyright (c) 2026 Jean-François Collin
--
-- Schema for the expert-games SQLite store on the Hetzner runner.
--
-- Populated by `tools/fetch_lidraughts_games.py` (Cycle 8-pre):
-- streams of PDN games from Lidraughts, deduplicated on
-- `UNIQUE (source, source_id)` so re-running the fetcher is
-- idempotent / resumable.
--
-- Consumed by `tools/pdn_to_jnnw.py` (Cycle 8): bulk SELECT of
-- rows matching rating / variant / ply filters, each PDN parsed
-- into a per-position JNNW record stream with the game's final
-- result as the WDL label.
--
-- Path on the runner: /root/jass/data/expert_games.db (WAL mode).

CREATE TABLE IF NOT EXISTS expert_games (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Provenance.  source ∈ {'lidraughts', 'toernooibase', 'manual', ...}.
    -- source_id is the upstream's unique identifier (Lidraughts game id,
    -- toernooibase URL fragment, etc.) — used for the UNIQUE constraint
    -- so re-fetching the same upstream is a no-op.
    source        TEXT NOT NULL,
    source_id     TEXT,

    -- Per-game metadata extracted from the PDN at INSERT time.  NULL when
    -- the upstream didn't carry the field.
    date          TEXT,                   -- ISO 8601 YYYY-MM-DD if known
    white_name    TEXT,
    black_name    TEXT,
    white_rating  INTEGER,
    black_rating  INTEGER,
    result        TEXT NOT NULL,          -- normalised to '1-0' | '0-1' | '1/2-1/2'
    num_plies     INTEGER,                -- count of half-moves, pre-computed

    -- Tournament context if known.
    event         TEXT,

    -- 'standard' (international 10×10) | 'frisian' | 'antidraughts' | …
    -- jass training filters on 'standard' only; other variants kept so the
    -- table is reusable for future work / other engines.
    variant       TEXT NOT NULL DEFAULT 'standard',

    -- Full PDN body, raw as received from the source.  Stored unmodified
    -- so we can re-normalise later if jass changes its FEN/move conventions.
    -- ~5-15 kB per game at ~80 plies.
    pdn           TEXT NOT NULL,

    ingested_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source, source_id)
);

-- Filter by rating floor: the typical Cycle-8 export query is
--   WHERE MIN(white_rating, black_rating) >= :threshold
-- but SQLite doesn't index MIN-of-two-columns directly, so we use two
-- single-column indexes and let the planner intersect.  Equivalent perf
-- on this query shape in practice.
CREATE INDEX IF NOT EXISTS idx_eg_white_rating ON expert_games(white_rating);
CREATE INDEX IF NOT EXISTS idx_eg_black_rating ON expert_games(black_rating);

CREATE INDEX IF NOT EXISTS idx_eg_variant      ON expert_games(variant);
CREATE INDEX IF NOT EXISTS idx_eg_result       ON expert_games(result);
CREATE INDEX IF NOT EXISTS idx_eg_date         ON expert_games(date);
CREATE INDEX IF NOT EXISTS idx_eg_source       ON expert_games(source);

-- A tiny housekeeping table so the fetcher can record which Lidraughts
-- usernames it has already drained, what the last seen game id was, etc.
-- Keeps the main `expert_games` table free of per-source bookkeeping.
CREATE TABLE IF NOT EXISTS fetcher_state (
    key           TEXT PRIMARY KEY,
    value         TEXT NOT NULL,
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
