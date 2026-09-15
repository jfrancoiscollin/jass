from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jobs.tools import ed5_fresh_w_source_seedfix_stage as repair
from jobs.tools import ed5_fresh_w_source_stage as ed5_w


class Ed5WSeedWidthRepairTests(unittest.TestCase):
    def test_frozen_seeds_exceed_int32_and_remain_unchanged(self) -> None:
        self.assertEqual(ed5_w.PRIMARY, 202609140502)
        self.assertEqual(ed5_w.RESERVE, 202609140512)
        self.assertGreater(ed5_w.PRIMARY, 2**31 - 1)
        self.assertGreater(ed5_w.RESERVE, 2**31 - 1)

    def test_isolated_patch_uses_full_uint64_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            source = root / "src/main.cpp"
            source.write_text(
                "before\n"
                + repair._OLD_DECL
                + "\n"
                + repair._OLD_PARSE
                + "middle\n"
                + repair._OLD_MIX
                + "after\n"
            )
            repair.patch_seed_width(root)
            text = source.read_text()
            self.assertIn(repair._NEW_DECL, text)
            self.assertIn(repair._NEW_PARSE, text)
            self.assertIn(repair._NEW_MIX, text)
            self.assertNotIn(repair._OLD_DECL, text)
            self.assertNotIn("parse_int_or(p_argv[7]", text)
            self.assertNotIn("static_cast<std::uint32_t>(random_seed)", text)

    def test_patch_fails_closed_on_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src/main.cpp").write_text("unexpected source\n")
            with self.assertRaisesRegex(ValueError, "seed declaration"):
                repair.patch_seed_width(root)


if __name__ == "__main__":
    unittest.main()
