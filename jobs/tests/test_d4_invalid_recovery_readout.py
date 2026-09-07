from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class D4InvalidRecoveryReadoutTests(unittest.TestCase):
    def test_recovery_consumes_failed_1862_without_reexecuting_science(self) -> None:
        text = (ROOT / "jobs/templates/l3-d4-offline-invalid-recovery-readout-v1.sh").read_text(encoding="utf-8")
        self.assertIn("--expected-state failed", text)
        self.assertIn("20260907T182914Z-1c779cc8", text)
        self.assertIn("D4_SEARCH_UTILITY_OFFLINE_INVALID_V1", text)
        self.assertIn("teacher.get('teacher_searches')!=4000", text)
        self.assertIn("source_exit_code':4", text)
        self.assertNotIn("d4_search_utility_trace_export", text)
        self.assertNotIn("--gen-opening-pool", text)
        self.assertNotIn("d4_search_utility_offline.py fit", text)
        self.assertNotIn("strength_games=", text.replace("strength_games=0", ""))

    def test_known_err_trap_failure_shape_is_documented_by_recovery(self) -> None:
        source = (ROOT / "jobs/templates/l3-d4-search-utility-offline-v1.sh").read_text(encoding="utf-8")
        # Bash ERR traps still fire for a failing simple command under `set +e`.
        # The sealed 1862 attempt therefore exited 4 before the intended rc=4 branch.
        self.assertIn("set +e\n\"$PY\" jobs/tools/d4_search_utility_offline.py prepare", source)
        self.assertIn("if [ \"$prep_rc\" -eq 4 ]; then", source)
        recovery = (ROOT / "jobs/templates/l3-d4-offline-invalid-recovery-readout-v1.sh").read_text(encoding="utf-8")
        self.assertIn("prepare.get('verdict')!='D4_SEARCH_UTILITY_OFFLINE_INVALID_V1'", recovery)


if __name__ == "__main__":
    unittest.main()
