# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "jass_megacorpus_catalog.py"
SPEC = importlib.util.spec_from_file_location("jass_megacorpus_catalog", TOOL)
assert SPEC is not None and SPEC.loader is not None
CATALOG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CATALOG)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def add_attempt(
    metadata: Path,
    objects: list[dict],
    *,
    job: str,
    attempt: str,
    state: str,
    data_name: str,
    meta_name: str | None,
    tamper_inventory_digest: bool = False,
) -> None:
    root = f"runs/{job}/{attempt}"
    local = metadata / "runs" / job / attempt
    local.mkdir(parents=True)
    exit_code = 0 if state == "completed" else 9
    manifest = {
        "job_id": job,
        "attempt_id": attempt,
        "state": state,
        "exit_code": exit_code,
        "code_sha": "a" * 40,
        "host": "User",
        "started_at": "2026-08-01T00:00:00+00:00",
        "ended_at": "2026-08-01T00:01:00+00:00",
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    (local / "manifest.json").write_bytes(manifest_raw)
    fake_data_sha = digest(data_name.encode())
    rows = [
        {
            "path": "manifest.json",
            "size_bytes": len(manifest_raw),
            "sha256": digest(manifest_raw),
        },
        {"path": data_name, "size_bytes": 3808, "sha256": fake_data_sha},
    ]
    if meta_name:
        rows.append({"path": meta_name, "size_bytes": 1708, "sha256": digest(meta_name.encode())})
    inventory_raw = (json.dumps({"files": rows}, sort_keys=True) + "\n").encode()
    (local / "inventory.json").write_bytes(inventory_raw)
    checksums = {
        row["path"]: row["sha256"] for row in rows
    }
    checksums["inventory.json"] = (
        "0" * 64 if tamper_inventory_digest else digest(inventory_raw)
    )
    checksums_raw = "".join(
        f"{value}  {name}\n" for name, value in sorted(checksums.items())
    ).encode()
    (local / "checksums.sha256").write_bytes(checksums_raw)
    marker = "_SUCCESS" if state == "completed" else "_FAILED"
    (local / marker).write_text("done\n", encoding="utf-8")

    for name, size in (
        ("manifest.json", len(manifest_raw)),
        ("inventory.json", len(inventory_raw)),
        ("checksums.sha256", len(checksums_raw)),
        (marker, 5),
        (data_name, 3808),
    ):
        objects.append({"Path": f"{root}/{name}", "Size": size, "ModTime": "2026-08-01T00:01:00Z"})
    if meta_name:
        objects.append({"Path": f"{root}/{meta_name}", "Size": 1708, "ModTime": "2026-08-01T00:01:00Z"})


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class MegaCorpusCatalogTest(unittest.TestCase):
    def test_catalog_separates_review_quarantine_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            metadata = tmp_path / "metadata"
            objects: list[dict] = []
            add_attempt(
                metadata, objects, job="home-clean",
                attempt="20260801T000000Z-aaaaaaaa", state="completed",
                data_name="artefacts/current.jnnw.gz",
                meta_name="artefacts/current.jsm.gz",
            )
            add_attempt(
                metadata, objects, job="home-derived",
                attempt="20260801T010000Z-aaaaaaaa", state="completed",
                data_name="artefacts/replay-mix.jnnw.gz",
                meta_name="artefacts/replay-mix.jsm.gz",
            )
            add_attempt(
                metadata, objects, job="home-failed",
                attempt="20260801T020000Z-aaaaaaaa", state="failed",
                data_name="artefacts/broken.jnnw.gz",
                meta_name="artefacts/broken.jsm.gz",
            )
            objects.append({
                "Path": "historical/legacy/selfplay.jnnw.gz", "Size": 999,
                "ModTime": "2025-01-01T00:00:00Z",
            })
            snapshot_manifest = (
                metadata / "historical" / "snapshot-a" / "manifests" / "paths.jsonl.gz"
            )
            snapshot_manifest.parent.mkdir(parents=True)
            snapshot_entries = [
                {"branch": "develop", "path": "artefacts/old.jnnw.gz", "oid": "b" * 40},
                {"branch": "develop", "path": "artefacts/old.jsm.gz", "oid": "c" * 40},
            ]
            with gzip.open(snapshot_manifest, "wt", encoding="utf-8") as handle:
                for entry in snapshot_entries:
                    handle.write(json.dumps(entry) + "\n")
            objects.append({
                "Path": "historical/snapshot-a/manifests/paths.jsonl.gz",
                "Size": snapshot_manifest.stat().st_size,
                "ModTime": "2026-07-01T00:00:00Z",
            })
            index = tmp_path / "objects.json"
            index.write_text(json.dumps(objects), encoding="utf-8")
            out = tmp_path / "out"
            summary = CATALOG.run(type("Args", (), {
                "object_index": str(index), "metadata_root": str(metadata),
                "remote_root": "r2:jass-data", "out_dir": str(out),
            })())
            candidates = {
                row["data"]["path"]: row
                for row in read_jsonl(out / "corpus-candidates.jsonl")
            }
            self.assertEqual(candidates[
                "runs/home-clean/20260801T000000Z-aaaaaaaa/artefacts/current.jnnw.gz"
            ]["quality"]["disposition"], "review")
            self.assertEqual(candidates[
                "runs/home-derived/20260801T010000Z-aaaaaaaa/artefacts/replay-mix.jnnw.gz"
            ]["quality"]["disposition"], "quarantine")
            self.assertEqual(candidates[
                "runs/home-failed/20260801T020000Z-aaaaaaaa/artefacts/broken.jnnw.gz"
            ]["quality"]["disposition"], "reject")
            historical = candidates["historical/legacy/selfplay.jnnw.gz"]
            self.assertEqual(historical["quality"]["disposition"], "quarantine")
            self.assertIsNone(historical["origin"]["generator_model_sha256"])
            archived = next(
                row for row in candidates.values()
                if row["source_class"] == "historical_git_snapshot"
            )
            self.assertEqual(archived["metadata"]["path"], "artefacts/old.jsm.gz")
            self.assertEqual(
                archived["data"]["archive_locator"]["branch"], "develop"
            )
            self.assertEqual(summary["candidates_by_disposition"], {
                "quarantine": 3, "reject": 1, "review": 1,
            })
            self.assertEqual(summary["historical_snapshot_candidate_count"], 1)
            self.assertEqual(summary["payload_objects_downloaded"], 0)
            self.assertFalse(summary["training_authorized"])

    def test_metadata_tamper_quarantines_otherwise_clean_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            metadata = tmp_path / "metadata"
            objects: list[dict] = []
            add_attempt(
                metadata, objects, job="home-tampered",
                attempt="20260801T030000Z-aaaaaaaa", state="completed",
                data_name="artefacts/current.jnnw.gz",
                meta_name="artefacts/current.jsm.gz",
                tamper_inventory_digest=True,
            )
            index = tmp_path / "objects.json"
            index.write_text(json.dumps(objects), encoding="utf-8")
            out = tmp_path / "out"
            CATALOG.run(type("Args", (), {
                "object_index": str(index), "metadata_root": str(metadata),
                "remote_root": "r2:jass-data", "out_dir": str(out),
            })())
            attempt = read_jsonl(out / "runner-attempts.jsonl")[0]
            candidate = read_jsonl(out / "corpus-candidates.jsonl")[0]
            self.assertEqual(attempt["audit_state"], "unverified")
            self.assertTrue(any(
                "inventory digest" in error for error in attempt["audit_errors"]
            ))
            self.assertEqual(candidate["quality"]["disposition"], "quarantine")

    def test_object_index_rejects_duplicate_or_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            index = Path(td) / "objects.json"
            index.write_text(json.dumps([
                {"Path": "runs/a/b/manifest.json", "Size": 1},
                {"Path": "runs/a/b/manifest.json", "Size": 1},
            ]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                CATALOG.load_object_index(index)
            index.write_text(
                json.dumps([{"Path": "../escape", "Size": 1}]), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsafe"):
                CATALOG.load_object_index(index)


if __name__ == "__main__":
    unittest.main()
