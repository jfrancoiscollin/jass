from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import runner_v3_store as store


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class CloudflareMarkerPutTests(unittest.TestCase):
    def test_direct_put_signs_exact_marker_without_exposing_secret(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "_SUCCESS"
            marker.write_bytes(b"2026-09-14T05:00:00+00:00\n")
            env = {
                "RCLONE_CONFIG_R2_PROVIDER": "Cloudflare",
                "RCLONE_CONFIG_R2_ENDPOINT": "https://account.example.r2.cloudflarestorage.com",
                "RCLONE_CONFIG_R2_ACCESS_KEY_ID": "ACCESS123",
                "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "super-secret",
                "RCLONE_CONFIG_R2_REGION": "auto",
            }
            captured = {}

            def fake_urlopen(request, timeout):
                captured["request"] = request
                captured["timeout"] = timeout
                return FakeResponse()

            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(store.urllib.request, "urlopen", side_effect=fake_urlopen):
                result = store.cloudflare_r2_put_file(
                    marker, "r2:jass-data/runs/job/attempt/_SUCCESS"
                )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(captured["timeout"], 30)
            request = captured["request"]
            self.assertEqual(
                request.full_url,
                "https://account.example.r2.cloudflarestorage.com/"
                "jass-data/runs/job/attempt/_SUCCESS",
            )
            self.assertEqual(request.data, marker.read_bytes())
            authorization = request.get_header("Authorization")
            self.assertIn("Credential=ACCESS123/", authorization)
            self.assertIn("SignedHeaders=host;x-amz-content-sha256;x-amz-date", authorization)
            self.assertNotIn("super-secret", authorization)

    def test_http_failure_is_bounded_and_sanitized(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "_SUCCESS"
            marker.write_text("ok\n", encoding="utf-8")
            env = {
                "RCLONE_CONFIG_R2_ENDPOINT": "https://account.example.r2.cloudflarestorage.com",
                "RCLONE_CONFIG_R2_ACCESS_KEY_ID": "ACCESS123",
                "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "super-secret",
            }
            error = store.urllib.error.HTTPError(
                "https://account.example/", 501, "Not Implemented", {}, None
            )
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(store.urllib.request, "urlopen", side_effect=error):
                result = store.cloudflare_r2_put_file(
                    marker, "r2:jass-data/runs/job/attempt/_SUCCESS"
                )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, "R2 PutObject HTTP 501")
            self.assertNotIn("super-secret", result.stderr)

    def test_cloudflare_uses_direct_put_and_other_providers_keep_rcat(self):
        marker = Path("/tmp/marker")
        cfg = mock.Mock()
        with mock.patch.dict(os.environ, {"RCLONE_CONFIG_R2_PROVIDER": "Cloudflare"}, clear=True), \
             mock.patch.object(
                 store, "cloudflare_r2_put_file",
                 return_value=subprocess.CompletedProcess([], 0, "", ""),
             ) as direct, \
             mock.patch.object(store, "rclone_rcat_file") as rcat:
            store.publish_terminal_marker(cfg, marker, "r2:jass-data/a/_SUCCESS")
            direct.assert_called_once_with(marker, "r2:jass-data/a/_SUCCESS")
            rcat.assert_not_called()

        with mock.patch.dict(os.environ, {"RCLONE_CONFIG_R2_PROVIDER": "AWS"}, clear=True), \
             mock.patch.object(
                 store, "rclone_rcat_file",
                 return_value=subprocess.CompletedProcess([], 0, "", ""),
             ) as rcat:
            store.publish_terminal_marker(cfg, marker, "s3:bucket/a/_SUCCESS")
            rcat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
