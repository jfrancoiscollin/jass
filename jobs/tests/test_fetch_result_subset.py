import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobs.tools import fetch_result_subset as subset


class FetchResultSubsetTests(unittest.TestCase):
    def test_safe_paths_rejects_escape_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paths.txt"
            path.write_text("artefacts/a.json\nartefacts/a.json\n")
            with self.assertRaisesRegex(RuntimeError, "duplicates"):
                subset._safe_paths(path)
            path.write_text("../secret\n")
            with self.assertRaisesRegex(RuntimeError, "unsafe"):
                subset._safe_paths(path)

    @mock.patch.object(subset, "_metadata")
    @mock.patch("subprocess.run")
    def test_fetches_once_and_verifies_preserved_paths(self, run, metadata):
        payloads = {"artefacts/games-pool1/game-1.json": b"{}\n"}
        items = {
            name: {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in payloads.items()
        }
        metadata.return_value = (
            {"job_id": "job", "attempt_id": "attempt", "code_sha": "a" * 40,
             "host": "cpx62", "state": "completed", "exit_code": 0},
            items,
            {name: item["sha256"] for name, item in items.items()},
        )

        def fake_run(args, **_kwargs):
            out = Path(args[3])
            for name, raw in payloads.items():
                target = out.joinpath(*name.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as tmp:
            report = subset.fetch_subset(
                rclone="rclone", prefix="r2:run", paths=list(payloads),
                out_dir=Path(tmp),
            )
            self.assertEqual(report["requested_files"], 1)
            self.assertTrue((Path(tmp) / "artefacts/games-pool1/game-1.json").is_file())
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
