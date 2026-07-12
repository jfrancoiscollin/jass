#!/usr/bin/env python3
"""PDN (Portable Draughts Notation) -> clean movetext lines for jass --replay-moves.

Reads one or more .pdn files (each may hold many games) and emits ONE game per
output line: whitespace-separated move tokens, nothing else. Everything that is
not a move is stripped: [tag] pairs, {comments}, (variations), move numbers
("12."), NAGs ($3), and game terminators (2-0, 1-1, 0-2, 1-0, 0-1, 1/2-1/2, *).

Move tokens are kept verbatim (e.g. "32-28", "17x28", "16x27x38"); jass only
reads the first and last square of each, so any capture punctuation is fine.

The pipeline this feeds:
    clean_pdn.py corpus.pdn > games.txt
    jass --replay-moves games.txt parents.jnnw moves.bin
    jass --gen-siblings parents.jnnw sib.jnnw <depth> --played-moves moves.bin --leaf-mode
    rank_finetune ... --leaf-pov            # elite played move = preferred, siblings dominated

Role guardrail (memo D): elite games are a PREFERENCE teacher (played move > the
alternatives). The WDL RESULT is deliberately DISCARDED here — never a training
label (human WDL killed us twice).
"""

from __future__ import annotations

import re
import sys

_RESULTS = {"2-0", "0-2", "1-1", "1-0", "0-1", "1/2-1/2", "2-2", "*"}
_MOVE_RE = re.compile(r"^\d{1,2}[-x:]\d{1,2}([-x:]\d{1,2})*$")


def clean_movetext(movetext: str) -> list[str]:
    """Return the ordered list of move tokens in one game's movetext."""
    # drop {…} comments and (…) variations (non-nested is the common case; strip greedily per line)
    movetext = re.sub(r"\{[^}]*\}", " ", movetext)
    movetext = re.sub(r"\([^)]*\)", " ", movetext)
    out: list[str] = []
    for raw in movetext.replace("\n", " ").split():
        tok = raw.strip()
        if not tok:
            continue
        if tok in _RESULTS:
            continue
        if tok.startswith("$"):            # NAG annotation
            continue
        # move number like "12." or "12" possibly glued: "12.32-28"
        if "." in tok:
            tok = tok.split(".", 1)[1]
            if not tok:
                continue
        # strip trailing annotation glyphs (!, ?, +, #)
        tok = tok.rstrip("!?+#")
        if _MOVE_RE.match(tok):
            out.append(tok)
    return out


def split_games(text: str) -> list[str]:
    """Split a multi-game PDN blob into per-game movetext blobs.

    A game starts at the first move after its tag block; games are delimited by
    the tag block of the next game. We split on the [Event tag as a boundary and
    then drop remaining [tag] lines inside each chunk.
    """
    # normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # split into chunks each beginning at an [Event "…"] (or the whole thing if none)
    chunks = re.split(r"(?=^\[Event\b)", text, flags=re.MULTILINE)
    games: list[str] = []
    for ch in chunks:
        # remove all [tag ...] lines; the remainder is movetext
        movetext = re.sub(r"^\s*\[[^\]]*\]\s*$", "", ch, flags=re.MULTILINE)
        toks = clean_movetext(movetext)
        if toks:
            games.append(" ".join(toks))
    return games


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: clean_pdn.py <in.pdn> [more.pdn ...] > games.txt\n")
        return 1
    total = 0
    for path in argv[1:]:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for game in split_games(fh.read()):
                sys.stdout.write(game + "\n")
                total += 1
    sys.stderr.write(f"clean_pdn: {total} games -> stdout\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
