#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Technical wrapper for loss-first labels that enforces true fixed-depth search.

The scientific protocol is unchanged.  The underlying labeling implementation
requests fixed depths 9/10/12, so the built-in opening book must be disabled:
a book hit returns depth=0 and is not a completed fixed-depth teacher search.
"""
from __future__ import annotations

# This wrapper is invoked both as ``python -m ...`` and directly by the
# preregistered shell template after a technical-only path substitution.
# Direct script execution sets sys.path[0] to jobs/tools, so make the repo root
# importable without changing any scientific inputs or runtime behaviour.
if __package__ in (None, ""):
    import sys
    from pathlib import Path

    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from jobs.tools import l3_curriculum_error_loss_first_sibling_labels as base


_ORIGINAL_JASS_ENGINE = base.cv.JassEngine


class NoBookJassEngine(_ORIGINAL_JASS_ENGINE):
    def __init__(self, *args, **kwargs):
        kwargs["enforce_no_book"] = True
        super().__init__(*args, **kwargs)
        if not self.book_disabled:
            self.close()
            raise RuntimeError("loss-first fixed-depth engine failed to disable book")


def main() -> int:
    original = base.cv.JassEngine
    base.cv.JassEngine = NoBookJassEngine
    try:
        return base.main()
    finally:
        base.cv.JassEngine = original


if __name__ == "__main__":
    raise SystemExit(main())
