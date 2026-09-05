#!/usr/bin/env python3
"""Offline orchestration tests; no Jass, network, search, or fresh B2 source runs."""
from __future__ import annotations

import hashlib
import contextlib
import io
import json
import os
import tempfile
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from jobs.tests.test_adaptive_sibling_b2_select import SyntheticInputs
from jobs.tools import adaptive_sibling_b2_source_publish as tool
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_json_bytes, sha256_file


ROOT = Path(__file__).resolve().parents[2]


class PublisherFixture:
    """Synthetic selector fixture plus declarative launcher bytes, never a quality proof."""

    def __init__(self, root: Path, *, insufficient: bool = False):
        self.root = root
        self.scratch = root / "scratch"
        self.artifacts = root / "artifacts"
        self.source = self.scratch / "source"
        self.scratch.mkdir()
        self.artifacts.mkdir()
        self.launcher_log = self.artifacts / "source-launcher.log"
        self.launcher_log.write_bytes(b"offline stub launcher\n")
        self.source.mkdir()
        self.selection = SyntheticInputs(self.source)
        if insufficient:
            self.selection.remove_one_from_cell("P3", 1)
        self.contract = root / "selection-contract.json"
        self.contract.write_bytes(canonical_json_bytes(self.selection.contract))
        self._materialize_declared_source_bytes()

    def _materialize_declared_source_bytes(self) -> None:
        manifest = json.loads(self.selection.source_manifest.read_text(encoding="utf-8"))
        for shard in manifest["shards"]:
            index = shard["source_shard"]
            raw = self.source / shard["producer"]["raw_jnnw"]["local_name"]
            # Targets are opaque here.  The publisher checks only bytes/size/hash and never parses them.
            raw.write_bytes((f"raw-{index}".encode() * 60_000)[:380_008].ljust(380_008, b"x"))
            shard["producer"]["raw_jnnw"]["sha256"] = sha256_file(raw)
            log = self.source / shard["producer"]["log"]["local_name"]
            log.write_bytes(b"")
            shard["producer"]["log"]["sha256"] = hashlib.sha256(b"").hexdigest()
            shard["producer"]["log"]["size_bytes"] = 0
            shard["filter"]["source_jnnw_sha256"] = sha256_file(raw)
        self.selection.source_manifest.write_bytes(canonical_json_bytes(manifest))

    def invoke(self, selector_cli_outcome=None) -> dict:
        common = {"fixture": True}
        return tool.publish_prepared(
            repo=ROOT,
            scratch=self.scratch,
            artifacts=self.artifacts,
            job_id="offline-stub-job",
            attempt_id="offline-stub-attempt",
            implementation={"commit": "a" * 40, "tools": {}, "contract": {}},
            preregistration={"commit": "b" * 40, "file": {}, "ancestor": True,
                             "blobs_equal": True},
            runtime={"offline_stub": True},
            historical=common,
            curriculum=common,
            build=common,
            source_execution={"duration_milliseconds": 1,
                              "log": tool._descriptor(self.launcher_log)},
            contract_path=self.contract,
            source_dir=self.source,
            exclusion_union=self.selection.exclusion_union,
            exclusion_manifest=self.selection.exclusion_manifest,
            exclusion_receipt=self.selection.exclusion_receipt,
            contract_override=self.selection.contract,
            selector_cli_outcome=selector_cli_outcome,
            required_technical_artifacts={"source-launcher.log"},
        )


class SourcePublisherTests(unittest.TestCase):
    def test_success_replays_seals_publishes_allowlist_and_removes_raw(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            result = fixture.invoke()
            self.assertEqual(result["kind"], "success")
            receipt = result["receipt"]
            self.assertEqual(receipt["schema"], tool.SUCCESS_SCHEMA)
            self.assertEqual(receipt["verdict"], tool.SUCCESS_VERDICT)
            self.assertEqual(receipt["selection"]["cells"],
                             {cell: 500 for cell in tool.selector.CELL_ORDER})
            self.assertTrue(receipt["selection"]["target_blind"])
            self.assertEqual(receipt["cleanup"], {
                "raw_expected": 16, "raw_published": 0, "raw_removed": 16,
                "raw_remaining": 0, "target_bytes_parsed": 0,
            })
            self.assertEqual(receipt["scientific_scope"]["teacher_searches"], 0)
            self.assertIsNone(receipt["scientific_scope"]["scientific_verdict"])
            self.assertEqual(receipt["scientific_scope"]["source_generation"]
                             ["internal_search_count"], None)
            self.assertFalse(any((fixture.artifacts / f"shard-{i:02d}.jnnw").exists()
                                 for i in range(16)))
            self.assertFalse(any((fixture.source / f"shard-{i:02d}.jnnw").exists()
                                 for i in range(16)))
            identities = (fixture.artifacts / "ordered-identities.txt").read_bytes()
            self.assertEqual(hashlib.sha256(identities).hexdigest(),
                             receipt["selection"]["ordered_identities"]["sha256"])
            self.assertEqual(len(identities.splitlines()), 4000)

    def test_typed_support_is_replayed_and_never_creates_parent_or_success_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary), insufficient=True)
            result = fixture.invoke()
            self.assertEqual(result["kind"], "support")
            receipt = result["receipt"]
            self.assertEqual(receipt["schema"], tool.SUPPORT_SCHEMA)
            self.assertEqual(receipt["verdict"], tool.SUPPORT_VERDICT)
            self.assertEqual(receipt["support"]["insufficient_cells"], ["P3_stm1"])
            self.assertEqual(receipt["parents_outputs"], 0)
            self.assertFalse((fixture.artifacts / "parents.jnnw").exists())
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())
            self.assertFalse(any((fixture.source / f"shard-{i:02d}.jnnw").exists()
                                 for i in range(16)))

    def test_raw_manifest_tamper_is_technical_and_publishes_no_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            raw = fixture.source / "shard-00.jnnw"
            raw.write_bytes(raw.read_bytes() + b"tamper")
            with self.assertRaisesRegex(tool.PublishError, "source manifest descriptor"):
                fixture.invoke()
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())
            self.assertFalse((fixture.artifacts / "source-selection-support-failure.json").exists())

    def test_input_mutation_after_selection_is_technical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            original = tool.selector.run

            def mutate(args, **kwargs):
                result = original(args, **kwargs)
                args.exclusion_union.write_bytes(args.exclusion_union.read_bytes() + b"\n")
                return result

            with mock.patch.object(tool.selector, "run", side_effect=mutate):
                with self.assertRaisesRegex(tool.PublishError, "changed after validation"):
                    fixture.invoke()
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())

    def test_selected_output_mutation_after_seal_is_technical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            original = tool._copy_new
            changed = False

            def mutate_after_copy(source, destination):
                nonlocal changed
                result = original(source, destination)
                if source.name == "parents.jnnw" and not changed:
                    changed = True
                    source.write_bytes(source.read_bytes() + b"tamper")
                return result

            with mock.patch.object(tool, "_copy_new", side_effect=mutate_after_copy):
                with self.assertRaisesRegex(tool.PublishError, "changed after validation"):
                    fixture.invoke()
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())

    def test_published_local_seal_mutation_is_technical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            original = tool._copy_new
            changed = False

            def mutate_after_copy(source, destination):
                nonlocal changed
                result = original(source, destination)
                if source.name == "local-selection-seal.json" and not changed:
                    changed = True
                    destination.write_bytes(destination.read_bytes() + b"tamper")
                return result

            with mock.patch.object(tool, "_copy_new", side_effect=mutate_after_copy):
                with self.assertRaisesRegex(tool.PublishError,
                                            "published local seal differs"):
                    fixture.invoke()
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())

    def test_output_collision_and_dangling_symlink_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            (fixture.artifacts / "source-manifest.json").write_bytes(b"occupied")
            with self.assertRaisesRegex(tool.PublishError, "existing output"):
                fixture.invoke()
        if os.name != "nt":
            with tempfile.TemporaryDirectory() as temporary:
                fixture = PublisherFixture(Path(temporary))
                os.symlink("missing", fixture.artifacts / "source-manifest.json")
                with self.assertRaisesRegex(tool.PublishError, "existing output"):
                    fixture.invoke()

    def test_hardlink_input_alias_and_unexpected_artifact_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            second = fixture.source / "shard-01.log"
            second.unlink()
            os.link(fixture.source / "shard-00.log", second)
            with self.assertRaisesRegex(tool.PublishError, "hardlink alias"):
                fixture.invoke()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary))
            (fixture.artifacts / "unexpected.bin").write_bytes(b"no")
            with self.assertRaisesRegex(tool.PublishError, "closed allowlist"):
                fixture.invoke()
            self.assertFalse((fixture.artifacts / "source-selection-publication.json").exists())

    def test_typed_support_rejects_any_forbidden_selector_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = PublisherFixture(Path(temporary), insufficient=True)
            probe = fixture.selection.args("-probe")
            probe.contract = fixture.contract
            try:
                tool.selector.run(probe, contract_override=fixture.selection.contract)
            except tool.selector.InsufficientSupportError as exc:
                payload = exc.payload()
            else:
                self.fail("support fixture unexpectedly selected")
            select_dir = fixture.scratch / "selection"
            select_dir.mkdir()
            (select_dir / "parents.jnnw").write_bytes(b"forbidden")
            with self.assertRaisesRegex(tool.PublishError, "forbidden outputs"):
                fixture.invoke((4, payload))
            self.assertFalse((fixture.artifacts / "source-selection-support-failure.json").exists())

    def test_all_operational_timeouts_are_required_and_have_no_defaults(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tool.parse_args([])
        parser_args = [
            "--repo-root", "/repo", "--scratch-dir", "/scratch", "--artifact-dir", "/art",
            "--job-id", "j", "--attempt-id", "a", "--implementation-commit", "a" * 40,
            "--preregistration-commit", "b" * 40, "--preregistration-path", "docs/p.md",
            "--preregistration-sha256", "c" * 64, "--rclone-bin", "/usr/bin/rclone",
        ]
        for name in ("git", "fetch", "configure", "build", "launcher", "selector",
                     "barrier", "exec-verify", "producer", "filter", "outer"):
            parser_args += [f"--{name}-timeout-seconds", "17"]
        args = tool.parse_args(parser_args)
        self.assertEqual(args.filter_timeout_seconds, 17)
        self.assertEqual(args.outer_timeout_seconds, 17)

    def test_operational_pin_block_is_unique_canonical_and_strictly_typed(self) -> None:
        pins = {"schema": tool.PINS_SCHEMA, "filter_timeout_seconds": 19,
                "launcher_timeout_seconds": 23, "outer_timeout_seconds": 29}
        document = b"prose\n" + tool.PINS_BEGIN + canonical_json_bytes(pins) + tool.PINS_END + b"end\n"
        self.assertEqual(tool.extract_operational_pins(document), pins)
        with self.assertRaisesRegex(tool.PublishError, "exactly one"):
            tool.extract_operational_pins(document + tool.PINS_BEGIN + canonical_json_bytes(pins) + tool.PINS_END)
        noncanonical = json.dumps(pins, indent=2).encode() + b"\n"
        with self.assertRaisesRegex(tool.PublishError, "canonical"):
            tool.extract_operational_pins(tool.PINS_BEGIN + noncanonical + tool.PINS_END)
        invalid = dict(pins)
        invalid["filter_timeout_seconds"] = True
        with self.assertRaisesRegex(tool.PublishError, "integer"):
            tool.extract_operational_pins(tool.PINS_BEGIN + canonical_json_bytes(invalid) + tool.PINS_END)

    def test_atomic_writer_never_adopts_or_removes_replacement_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out.json"
            real_link = os.link

            def replace_after_link(source, destination):
                real_link(source, destination)
                Path(destination).unlink()
                Path(destination).write_bytes(b"concurrent owner")

            with mock.patch.object(tool.os, "link", side_effect=replace_after_link):
                with self.assertRaisesRegex(tool.PublishError, "ownership changed"):
                    tool._write_new(output, b"publisher bytes")
            self.assertEqual(output.read_bytes(), b"concurrent owner")

    @unittest.skipUnless(sys.platform == "linux", "Linux process-group semantics")
    def test_command_timeout_kills_stubborn_descendant_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "pid"
            program = (
                "import pathlib,signal,subprocess,sys,time;"
                "p=subprocess.Popen([sys.executable,'-c',"
                "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'],"
                "start_new_session=True);"
                "pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                tool._run([sys.executable, "-c", program, str(pid_file)], timeout=1,
                          cwd=Path(temporary))
            child = int(pid_file.read_text())
            for _ in range(50):
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("stubborn descendant survived timeout cleanup")
            exit_pid = Path(temporary) / "exit-pid"
            exit_program = (
                "import pathlib,subprocess,sys,time;"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
                "start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
                "stderr=subprocess.DEVNULL);pathlib.Path(sys.argv[1]).write_text(str(p.pid));"
                "time.sleep(.2)"
            )
            with self.assertRaisesRegex(tool.PublishError, "live descendant"):
                tool._run([sys.executable, "-c", exit_program, str(exit_pid)], timeout=2,
                          cwd=Path(temporary))
            detached = int(exit_pid.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(detached, 0)

    def test_production_orchestration_accepts_only_reserved_runner_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            scratch = root / "scratch"
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "runner-launch.json").write_text("{}\n")
            pins = {"schema": tool.PINS_SCHEMA, "filter_timeout_seconds": 19,
                    "launcher_timeout_seconds": 23, "outer_timeout_seconds": 29}
            prereg = b"p\n" + tool.PINS_BEGIN + canonical_json_bytes(pins) + tool.PINS_END
            args = tool.parse_args([
                "--repo-root", str(repo), "--scratch-dir", str(scratch),
                "--artifact-dir", str(artifacts), "--job-id", "j", "--attempt-id", "a",
                "--implementation-commit", "a" * 40, "--preregistration-commit", "b" * 40,
                "--preregistration-path", "docs/p.md", "--preregistration-sha256",
                hashlib.sha256(prereg).hexdigest(), "--rclone-bin", "/usr/bin/rclone",
                "--git-timeout-seconds", "7", "--fetch-timeout-seconds", "11",
                "--configure-timeout-seconds", "13", "--build-timeout-seconds", "17",
                "--launcher-timeout-seconds", "23", "--selector-timeout-seconds", "31",
                "--barrier-timeout-seconds", "30", "--exec-verify-timeout-seconds", "30",
                "--producer-timeout-seconds", "413", "--filter-timeout-seconds", "19",
                "--outer-timeout-seconds", "29",
            ])

            def fake_fetch(_repo, scratch_dir, artifact_dir, name, source, selections, rclone, timeout):
                destination = scratch_dir / f"fetch-{name}"
                destination.mkdir()
                receipt = artifact_dir / f"verified-{name}.json"
                receipt.write_text("{}\n")
                paths = {}
                for remote, local in selections:
                    path = destination / local
                    path.write_bytes(b"stub")
                    paths[remote] = path
                return ({"stub": name}, paths)

            def fake_materialize(_gzip, output):
                output.write_bytes(b"PJTW" + (0x203).to_bytes(4, "little"))
                return {"stub": True}

            def fake_build(_repo, scratch_dir, _artifacts, _configure, _build):
                build_dir = scratch_dir / "build"
                build_dir.mkdir()
                paths = []
                for name in ("jass", "jass_scan_ceiling_parent_filter", "CMakeCache.txt"):
                    path = build_dir / name
                    path.write_bytes(name.encode())
                    paths.append(path)
                return ({"stub": True}, *paths)

            def fake_run(_argv, **kwargs):
                log = kwargs.get("log")
                if log is not None:
                    log.write_bytes(b"offline command stub\n")
                return subprocess.CompletedProcess([], 0, b"", b"")

            historical = {**tool.HISTORICAL,
                "files": {remote: (local, hashlib.sha256(b"stub").hexdigest())
                          for remote, (local, _sha) in tool.HISTORICAL["files"].items()}}
            with mock.patch.object(tool, "HISTORICAL", historical), \
                    mock.patch.object(tool.sys, "platform", "linux"), \
                    mock.patch.object(tool, "validate_runtime",
                                      return_value={"stub": True, "cxx_version": "stub-c++"}), \
                    mock.patch.object(tool, "validate_git_provenance",
                                      return_value=({"commit": "a" * 40}, prereg)), \
                    mock.patch.object(tool, "fetch_source", side_effect=fake_fetch), \
                    mock.patch.object(tool, "materialize_curriculum", side_effect=fake_materialize), \
                    mock.patch.object(tool, "build_source", side_effect=fake_build), \
                    mock.patch.object(tool, "_run", side_effect=fake_run), \
                    mock.patch.object(tool, "run_selector_cli", return_value=(4, {"stub": True})), \
                    mock.patch.object(tool, "publish_prepared",
                                      return_value={"kind": "support", "receipt_path": artifacts / "r.json"}) as publish:
                result = tool.run(args)
            self.assertEqual(result["kind"], "support")
            self.assertTrue((artifacts / "runner-launch.json").is_file())
            self.assertEqual(publish.call_args.kwargs["selector_cli_outcome"], (4, {"stub": True}))


if __name__ == "__main__":
    unittest.main()
