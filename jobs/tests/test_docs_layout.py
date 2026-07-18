#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
ACTIVE = {"L3_PURE_PLAN.md", "L3_CURRENT.md", "PROJECT_RESULTS.md"}


class DocsLayoutTests(unittest.TestCase):
    def test_only_three_active_documents(self):
        actual = {
            path.relative_to(DOCS).as_posix()
            for path in DOCS.rglob("*.md")
            if path.relative_to(DOCS).parts[0] != "archives"
        }
        self.assertEqual(actual, ACTIVE)

    def test_active_relative_links_exist(self):
        for name in sorted(ACTIVE):
            path = DOCS / name
            for line_number, line in enumerate(path.read_text().splitlines(), 1):
                for target in re.findall(r"\]\(([^)]+)\)", line):
                    target = target.split()[0].strip("<>")
                    if target.startswith(("https://", "http://", "#", "mailto:")):
                        continue
                    relative = target.split("#", 1)[0]
                    if relative:
                        self.assertTrue(
                            (path.parent / relative).exists(),
                            f"{path}:{line_number}: missing {target}",
                        )

    def test_entrypoints_name_the_new_sources_of_truth(self):
        for entrypoint in (ROOT / "README.md", ROOT / "CLAUDE.md"):
            text = entrypoint.read_text()
            for name in ACTIVE:
                self.assertIn(f"docs/{name}", text)
        archived_current = (DOCS / "archives/CURRENT.md").read_text()
        self.assertIn("ARCHIVE FIGÉE", archived_current)
        self.assertIn("../L3_CURRENT.md", archived_current)


if __name__ == "__main__":
    unittest.main()
