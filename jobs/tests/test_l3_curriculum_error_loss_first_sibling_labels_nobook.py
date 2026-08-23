import pathlib
import subprocess
import sys
import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_loss_first_sibling_labels_nobook as target


class LossFirstLabelsNoBookTests(unittest.TestCase):
    def test_wrapper_forces_enforce_no_book(self):
        with mock.patch.object(target._ORIGINAL_JASS_ENGINE, "__init__", return_value=None) as init, \
             mock.patch.object(target._ORIGINAL_JASS_ENGINE, "close", return_value=None):
            engine = object.__new__(target.NoBookJassEngine)
            engine.book_disabled = True
            target.NoBookJassEngine.__init__(engine, "jass", label="x", pattern_path="p", search_params="s")
        self.assertTrue(init.call_args.kwargs["enforce_no_book"])

    def test_wrapper_fails_closed_if_book_not_disabled(self):
        with mock.patch.object(target._ORIGINAL_JASS_ENGINE, "__init__", return_value=None), \
             mock.patch.object(target._ORIGINAL_JASS_ENGINE, "close", return_value=None) as close:
            engine = object.__new__(target.NoBookJassEngine)
            engine.book_disabled = False
            with self.assertRaisesRegex(RuntimeError, "failed to disable book"):
                target.NoBookJassEngine.__init__(engine, "jass")
            close.assert_called_once_with()

    def test_direct_script_execution_can_import_jobs_package(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        script = root / "jobs/tools/l3_curriculum_error_loss_first_sibling_labels_nobook.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        combined = proc.stdout + proc.stderr
        self.assertNotIn("ModuleNotFoundError", combined)
        self.assertNotIn("No module named 'jobs'", combined)


if __name__ == "__main__":
    unittest.main()
