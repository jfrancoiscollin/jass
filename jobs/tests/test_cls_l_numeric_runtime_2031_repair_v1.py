from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from jobs.tools import cls_l_source_normalization_preflight_launch as launch


class CLSLNumericRuntime2031RepairV1Tests(unittest.TestCase):
    def test_2033_proven_historical_wheel_failure_resolves_once_then_locks(self):
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "numeric"
            historical_failure = subprocess.CalledProcessError(
                1,
                [str(venv / "bin/python"), "-m", "pip", "install"],
            )
            with mock.patch.dict(
                launch.os.environ,
                {"JASS_L3_NUMERIC_VENV": str(venv)},
                clear=True,
            ), mock.patch.object(
                launch, "numeric_runtime_healthy", side_effect=[False, True]
            ) as healthy, mock.patch.object(
                launch, "clear_numeric_venv"
            ) as clear, mock.patch.object(
                launch,
                "install_numeric_stack",
                side_effect=[historical_failure, None],
            ) as install, mock.patch.object(
                launch,
                "resolved_numeric_versions",
                return_value=("2.5.3", "1.17.0"),
            ) as versions:
                got = launch.ensure_numeric_runtime()

            self.assertEqual(got, venv)
            self.assertEqual(healthy.call_args_list, [mock.call(venv), mock.call(venv)])
            self.assertEqual(clear.call_args_list, [mock.call(venv), mock.call(venv)])
            self.assertEqual(
                install.call_args_list,
                [
                    mock.call(venv, ["numpy==1.26.4", "scipy==1.14.1"]),
                    mock.call(venv, ["numpy", "scipy"]),
                ],
            )
            versions.assert_called_once_with(venv)
            lock = json.loads(launch.runtime_lock_path(venv).read_text(encoding="ascii"))
            self.assertEqual(lock["schema"], launch.RUNTIME_LOCK_SCHEMA)
            self.assertEqual(lock["source"], "current-compatible-after-historical-unavailable")
            self.assertEqual(lock["numpy"], "2.5.3")
            self.assertEqual(lock["scipy"], "1.17.0")

    def test_existing_compatible_lock_is_reinstalled_exactly_without_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "numeric"
            launch.write_runtime_lock(venv, "2.5.3", "1.17.0")
            with mock.patch.dict(
                launch.os.environ,
                {"JASS_L3_NUMERIC_VENV": str(venv)},
                clear=True,
            ), mock.patch.object(
                launch, "numeric_runtime_healthy", side_effect=[False, True]
            ), mock.patch.object(
                launch, "clear_numeric_venv"
            ) as clear, mock.patch.object(
                launch, "install_numeric_stack"
            ) as install, mock.patch.object(
                launch, "resolved_numeric_versions"
            ) as versions:
                got = launch.ensure_numeric_runtime()

            self.assertEqual(got, venv)
            clear.assert_called_once_with(venv)
            install.assert_called_once_with(venv, ["numpy==2.5.3", "scipy==1.17.0"])
            versions.assert_not_called()

    def test_only_called_process_error_authorizes_current_compatible_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "numeric"
            with mock.patch.dict(
                launch.os.environ,
                {"JASS_L3_NUMERIC_VENV": str(venv)},
                clear=True,
            ), mock.patch.object(
                launch, "numeric_runtime_healthy", return_value=False
            ), mock.patch.object(
                launch, "clear_numeric_venv"
            ), mock.patch.object(
                launch,
                "install_numeric_stack",
                side_effect=subprocess.TimeoutExpired(["pip"], 900),
            ) as install:
                with self.assertRaises(subprocess.TimeoutExpired):
                    launch.ensure_numeric_runtime()

            install.assert_called_once_with(venv, ["numpy==1.26.4", "scipy==1.14.1"])

    def test_healthy_runtime_remains_byte_untouched(self):
        requested = Path("/var/tmp/already-healthy-2031")
        with mock.patch.dict(
            launch.os.environ,
            {"JASS_L3_NUMERIC_VENV": str(requested)},
            clear=True,
        ), mock.patch.object(
            launch, "numeric_runtime_healthy", return_value=True
        ), mock.patch.object(
            launch, "clear_numeric_venv"
        ) as clear, mock.patch.object(
            launch, "install_numeric_stack"
        ) as install:
            self.assertEqual(launch.ensure_numeric_runtime(), requested)

        clear.assert_not_called()
        install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
