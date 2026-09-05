from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from jobs.tools import adaptive_sibling_b2_select as selector
from jobs.tools import adaptive_sibling_b2_source_launcher as launcher
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_json_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json"


PRODUCER_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc != 19 || strcmp(argv[1], "--gen-data-wdl") || strcmp(argv[2], "10000") ||
        strcmp(argv[4], "4") || strcmp(argv[5], "8") || strcmp(argv[6], "260") ||
        strcmp(argv[8], "--nnue") || strcmp(argv[10], "--wdl-zero-score") ||
        strcmp(argv[11], "--random-open-plies") || strcmp(argv[12], "8") ||
        strcmp(argv[13], "--explore-eps") || strcmp(argv[14], "8") ||
        strcmp(argv[15], "--explore-decay-plies") || strcmp(argv[16], "60") ||
        strcmp(argv[17], "--pair-openings") || strcmp(argv[18], "--drop-plycap")) return 41;
    usleep(300000);
    FILE *out = fopen(argv[3], "wb");
    if (!out) return 42;
    const unsigned char magic[4] = {'J','N','N','W'};
    uint32_t count = 10000;
    unsigned char record[38] = {0};
    record[0] = (unsigned char)(strtoul(argv[7], NULL, 10) & 255u);
    fwrite(magic, 1, 4, out); fwrite(&count, 4, 1, out);
    for (uint32_t i = 0; i < count; ++i) fwrite(record, 1, 38, out);
    return fclose(out) ? 43 : 0;
}
"""


FILTER_C = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc != 9 || strcmp(argv[5], "9") || strcmp(argv[6], "40") ||
        strcmp(argv[7], "2") || strcmp(argv[8], "16")) return 51;
    unsigned shard = 0; if (sscanf(argv[1], "shard-%u.jnnw", &shard) != 1) return 52;
    FILE *data = fopen(argv[2], "wb"); if (!data) return 53;
    const unsigned char magic[4] = {'J','N','N','W'}; uint32_t count = 1;
    uint64_t wm = 0xFULL, wk = 0, bm = 0x7C00ULL, bk = 0;
    unsigned char stm = (unsigned char)(shard & 1u), targets[5] = {0};
    fwrite(magic,1,4,data); fwrite(&count,4,1,data);
    fwrite(&wm,8,1,data); fwrite(&wk,8,1,data); fwrite(&bm,8,1,data); fwrite(&bk,8,1,data);
    fwrite(&stm,1,1,data); fwrite(targets,1,5,data); if (fclose(data)) return 54;
    FILE *meta = fopen(argv[3], "w"); if (!meta) return 55;
    fprintf(meta, "row_index\tsource_row_index\tparent_fingerprint\tparent_stm\tpieces\tlegal_moves\n");
    fprintf(meta, "0\t0\t%013llx:%013llx:%013llx:%013llx:%u\t%u\t9\t2\n",
            (unsigned long long)wm, (unsigned long long)wk, (unsigned long long)bm,
            (unsigned long long)bk, stm, stm); if (fclose(meta)) return 56;
    FILE *report = fopen(argv[4], "w"); if (!report) return 57;
    fprintf(report,
      "{\n  \"schema\": \"jass.deep_sibling.parent_filter.v1\",\n"
      "  \"input\": \"%s\",\n  \"labels_used_from_sources\": false,\n"
      "  \"source_score_bytes_read\": false,\n  \"source_wdl_bytes_read\": false,\n"
      "  \"min_pieces\": 9,\n  \"max_pieces\": 40,\n"
      "  \"min_semantic_legal_moves\": 2,\n  \"max_semantic_legal_moves\": 16,\n"
      "  \"source_rows\": 10000,\n  \"invalid_rows\": 0,\n"
      "  \"piece_eligible_rows\": 1,\n  \"exact_duplicates\": 0,\n"
      "  \"below_min_moves\": 0,\n  \"above_max_moves\": 0,\n"
      "  \"duplicate_move_entries\": 0,\n  \"selected_parents\": 1\n}\n", argv[1]);
    return fclose(report) ? 58 : 0;
}
"""


FORKING_PRODUCER_C = PRODUCER_C.replace(
    "#include <string.h>", "#include <string.h>\n#include <signal.h>"
).replace(
    "    usleep(300000);",
    r"""
    pid_t descendant = fork();
    if (descendant < 0) return 44;
    if (descendant == 0) {
        char path[128]; snprintf(path, sizeof(path), "%s.descendant-pid", argv[3]);
        FILE *pidfile = fopen(path, "w"); if (!pidfile) return 45;
        fprintf(pidfile, "%ld\n", (long)getpid()); fclose(pidfile);
        signal(SIGTERM, SIG_IGN);
        for (;;) pause();
    }
    usleep(5000000);
""",
)


FORKING_FILTER_C = FILTER_C.replace(
    "#include <string.h>", "#include <string.h>\n#include <signal.h>\n#include <unistd.h>"
).replace(
    "    if (argc != 9 ||",
    r"""
    pid_t descendant = fork();
    if (descendant < 0) return 59;
    if (descendant == 0) {
        FILE *pidfile = fopen("filter-descendant.pid", "w"); if (!pidfile) return 60;
        fprintf(pidfile, "%ld\n", (long)getpid()); fclose(pidfile);
        signal(SIGTERM, SIG_IGN);
        for (;;) pause();
    }
    usleep(5000000);
    if (argc != 9 ||""",
)


MUTATING_FILTER_C = FILTER_C.replace(
    "    FILE *data = fopen(argv[2], \"wb\"); if (!data) return 53;",
    r"""
    FILE *raw = fopen(argv[1], "r+b"); if (!raw) return 61;
    if (fseek(raw, 8, SEEK_SET) || fputc((int)(shard ^ 0x80u), raw) == EOF || fclose(raw)) return 62;
    FILE *data = fopen(argv[2], "wb"); if (!data) return 53;""",
)


def compile_stub(root: Path, name: str, source: str) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        raise unittest.SkipTest("C compiler unavailable for Linux process-barrier stub")
    source_path = root / f"{name}.c"
    executable = root / name
    source_path.write_text(textwrap.dedent(source), encoding="utf-8")
    completed = subprocess.run(
        [compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-O0", str(source_path), "-o", str(executable)],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr)
    return executable


def run_worker(args: argparse.Namespace, contract: dict[str, object]) -> None:
    try:
        launcher.run(args, contract_override=contract)
    except launcher.LauncherError:
        return
    raise AssertionError("signal-interruption worker unexpectedly completed")


class PureContractTests(unittest.TestCase):
    def test_producer_argv_is_exact_and_has_no_science_override(self) -> None:
        argv = launcher._producer_argv(Path("/bin/jass"), Path("/models/curriculum.pjtw"), 15)
        self.assertEqual(argv[2:8], ["10000", "shard-15.jnnw", "4", "8", "260", "2026110715"])
        self.assertEqual(argv[-9:], [
            "--wdl-zero-score", "--random-open-plies", "8", "--explore-eps", "8",
            "--explore-decay-plies", "60", "--pair-openings", "--drop-plycap",
        ])
        self.assertNotIn("--seed", argv)
        self.assertNotIn("--nodes", argv)

    def test_timeout_parser_is_explicit_and_strict(self) -> None:
        self.assertEqual(launcher._positive_timeout("1"), 1)
        self.assertEqual(launcher._positive_timeout("86400"), 86400)
        for value in ("0", "01", "-1", "1.5", "86401", ""):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                launcher._positive_timeout(value)

    def test_environment_is_exactly_empty(self) -> None:
        for names in (["PATH"], ["LD_PRELOAD"], ["JASS_TRACE_ROOT"]):
            with self.subTest(names=names), self.assertRaisesRegex(
                launcher.LauncherError, "exactly empty"
            ):
                launcher._clean_environment(names)
        env, names = launcher._clean_environment([])
        self.assertEqual((env, names), ({}, []))

    def test_raw_jnnw_requires_exact_10000_by_38(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "short.jnnw"
            path.write_bytes(b"JNNW" + struct.pack("<I", 9999) + b"\0" * (9999 * 38))
            with self.assertRaisesRegex(launcher.LauncherError, "count/size"):
                launcher._validate_raw_jnnw(path)

    def test_standalone_help_states_wrapper_authorization_and_has_no_size_flags(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(Path(launcher.__file__).resolve()), "--help"],
            cwd=tempfile.gettempdir(), capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("preregistered wrapper", " ".join(completed.stdout.split()))
        self.assertNotIn("--seed", completed.stdout)
        self.assertNotIn("--records", completed.stdout)
        self.assertNotIn("--pass-env", completed.stdout)

    @unittest.skipUnless(sys.platform == "linux", "Linux /proc parser")
    def test_proc_stat_parser_observes_current_process(self) -> None:
        snapshot = launcher._read_proc_stat(os.getpid())
        self.assertEqual(snapshot.pid, os.getpid())
        self.assertGreater(snapshot.ppid, 0)
        self.assertGreater(snapshot.starttime, 0)
        self.assertIn(snapshot.state, launcher.LIVE_PROC_STATES)


@unittest.skipUnless(sys.platform == "linux", "16-child integration requires Linux")
class LinuxBarrierIntegrationTests(unittest.TestCase):
    def recorded_pids(self, paths: list[Path]) -> list[int]:
        self.assertTrue(paths)
        return [int(path.read_text(encoding="ascii")) for path in paths]

    def assert_pids_gone(self, pids: list[int]) -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and any(Path(f"/proc/{pid}").exists() for pid in pids):
            time.sleep(0.01)
        self.assertFalse([pid for pid in pids if Path(f"/proc/{pid}").exists()])

    def assert_recorded_descendants_gone(self, paths: list[Path]) -> None:
        self.assert_pids_gone(self.recorded_pids(paths))

    def make_run_case(
        self, root: Path, producer_source: str, filter_source: str
    ) -> tuple[argparse.Namespace, dict[str, object]]:
        output = root / "output"
        output.mkdir()
        producer = compile_stub(root, "producer-stub", producer_source)
        parent_filter = compile_stub(root, "filter-stub", filter_source)
        curriculum = root / "curriculum.pjtw"
        curriculum.write_bytes(b"synthetic curriculum; no model semantics")
        cmake_cache = root / "CMakeCache.txt"
        cmake_cache.write_text("JASS_NNUE:BOOL=ON\n", encoding="utf-8")
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract["curriculum"]["decompressed_sha256"] = hashlib.sha256(
            curriculum.read_bytes()
        ).hexdigest()
        args = argparse.Namespace(
            selection_contract=CONTRACT,
            jass_exe=producer,
            parent_filter_exe=parent_filter,
            curriculum=curriculum,
            cmake_cache=cmake_cache,
            code_sha="b" * 40,
            build_type="Release",
            compiler_id="SyntheticCC",
            compiler_version="1",
            cmake_option=["-DJASS_NNUE=ON"],
            output_dir=output,
            manifest=output / "source-manifest.json",
            barrier_timeout_seconds=5,
            exec_verify_timeout_seconds=5,
            producer_timeout_seconds=30,
            filter_timeout_seconds=30,
        )
        return args, contract

    def wait_for_paths(self, pattern: str, count: int, root: Path) -> list[Path]:
        deadline = time.monotonic() + 10.0
        paths: list[Path] = []
        while time.monotonic() < deadline:
            paths = sorted(root.glob(pattern))
            if len(paths) == count:
                return paths
            time.sleep(0.01)
        self.fail(f"expected {count} paths matching {pattern}, got {len(paths)}")

    def test_synthetic_stubs_prove_barrier_filter_and_manifest_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            producer = compile_stub(root, "producer-stub", PRODUCER_C)
            parent_filter = compile_stub(root, "filter-stub", FILTER_C)
            curriculum = root / "curriculum.pjtw"
            curriculum.write_bytes(b"synthetic curriculum; no model semantics")
            cmake_cache = root / "CMakeCache.txt"
            cmake_cache.write_text("JASS_NNUE:BOOL=ON\n", encoding="utf-8")
            contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
            contract["curriculum"]["decompressed_sha256"] = hashlib.sha256(curriculum.read_bytes()).hexdigest()
            args = argparse.Namespace(
                selection_contract=CONTRACT,
                jass_exe=producer,
                parent_filter_exe=parent_filter,
                curriculum=curriculum,
                cmake_cache=cmake_cache,
                code_sha="b" * 40,
                build_type="Release",
                compiler_id="SyntheticCC",
                compiler_version="1",
                cmake_option=["-DJASS_NNUE=ON"],
                pass_env=[],
                output_dir=output,
                manifest=output / "source-manifest.json",
                barrier_timeout_seconds=5,
                exec_verify_timeout_seconds=5,
                producer_timeout_seconds=10,
                filter_timeout_seconds=5,
            )
            result = launcher.run(args, contract_override=contract)
            self.assertEqual(result["source_shards"], 16)
            self.assertEqual(result["raw_records"], 160000)
            self.assertEqual(result["filtered_records"], 16)
            manifest_raw = args.manifest.read_bytes()
            manifest = json.loads(manifest_raw)
            parsed, parsed_raw = selector.validate_source_manifest(args.manifest, contract)
            self.assertEqual((parsed, parsed_raw), (manifest, manifest_raw))
            self.assertEqual(result["manifest_sha256"], sha256_bytes(manifest_raw))
            self.assertEqual(manifest["producer_environment"]["jass_prefixed_environment"], [])
            self.assertEqual(len({row["producer"]["pid"] for row in manifest["shards"]}), 16)
            self.assertEqual(len({
                (row["producer"]["pid"], row["producer"]["proc_starttime"])
                for row in manifest["shards"]
            }), 16)
            self.assertTrue(all(
                row["producer"]["ppid"] == manifest["producer_barrier"]["launcher_pid"]
                and row["producer"]["post_exec"]["verified"]
                and row["producer"]["exit_code"] == 0
                and row["filter"]["exit_code"] == 0
                for row in manifest["shards"]
            ))

    def test_producer_deadline_terminates_and_reaps_exact_children(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            slow = compile_stub(root, "slow-producer", PRODUCER_C.replace("usleep(300000);", "usleep(5000000);"))
            curriculum = root / "curriculum.pjtw"
            curriculum.write_bytes(b"synthetic")
            started = time.monotonic()
            with self.assertRaisesRegex(launcher.LauncherError, "deadline"):
                launcher.launch_producers(
                    jass=slow,
                    jass_sha256=hashlib.sha256(slow.read_bytes()).hexdigest(),
                    curriculum=curriculum,
                    output_dir=output,
                    environment={},
                    barrier_timeout_seconds=3,
                    exec_verify_timeout_seconds=3,
                    producer_timeout_seconds=1,
                )
            self.assertLess(time.monotonic() - started, 4.0)
            for proc_cmdline in Path("/proc").glob("[0-9]*/cmdline"):
                try:
                    command = proc_cmdline.read_bytes().split(b"\0")
                except OSError:
                    continue
                self.assertNotIn(os.fsencode(str(slow)), command)

    def test_producer_timeout_kills_descendant_process_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            producer = compile_stub(root, "forking-producer", FORKING_PRODUCER_C)
            curriculum = root / "curriculum.pjtw"
            curriculum.write_bytes(b"synthetic")
            with self.assertRaisesRegex(launcher.LauncherError, "deadline"):
                launcher.launch_producers(
                    jass=producer,
                    jass_sha256=hashlib.sha256(producer.read_bytes()).hexdigest(),
                    curriculum=curriculum,
                    output_dir=output,
                    environment={},
                    barrier_timeout_seconds=3,
                    exec_verify_timeout_seconds=3,
                    producer_timeout_seconds=1,
                )
            self.assert_recorded_descendants_gone(
                sorted(output.glob("*.descendant-pid"))
            )

    def test_filter_timeout_kills_descendant_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            parent_filter = compile_stub(root, "forking-filter", FORKING_FILTER_C)
            with self.assertRaisesRegex(launcher.LauncherError, "timeout"):
                launcher.run_filters(
                    parent_filter=parent_filter,
                    output_dir=output,
                    environment={},
                    filter_timeout_seconds=1,
                )
            self.assert_recorded_descendants_gone(
                sorted(output.glob("filter-descendant.pid"))
            )

    def test_structurally_valid_raw_mutation_during_filter_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            producer = compile_stub(root, "producer-stub", PRODUCER_C)
            parent_filter = compile_stub(root, "mutating-filter", MUTATING_FILTER_C)
            curriculum = root / "curriculum.pjtw"
            curriculum.write_bytes(b"synthetic curriculum; no model semantics")
            cmake_cache = root / "CMakeCache.txt"
            cmake_cache.write_text("JASS_NNUE:BOOL=ON\n", encoding="utf-8")
            contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
            contract["curriculum"]["decompressed_sha256"] = hashlib.sha256(
                curriculum.read_bytes()
            ).hexdigest()
            args = argparse.Namespace(
                selection_contract=CONTRACT,
                jass_exe=producer,
                parent_filter_exe=parent_filter,
                curriculum=curriculum,
                cmake_cache=cmake_cache,
                code_sha="b" * 40,
                build_type="Release",
                compiler_id="SyntheticCC",
                compiler_version="1",
                cmake_option=["-DJASS_NNUE=ON"],
                output_dir=output,
                manifest=output / "source-manifest.json",
                barrier_timeout_seconds=5,
                exec_verify_timeout_seconds=5,
                producer_timeout_seconds=10,
                filter_timeout_seconds=5,
            )
            with self.assertRaisesRegex(launcher.LauncherError, "changed during filtering"):
                launcher.run(args, contract_override=contract)
            self.assertFalse(args.manifest.exists())

    def test_sigterm_during_producers_cleans_all_process_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args, contract = self.make_run_case(root, FORKING_PRODUCER_C, FILTER_C)
            worker = multiprocessing.get_context("fork").Process(
                target=run_worker, args=(args, contract)
            )
            worker.start()
            descendants = self.wait_for_paths(
                "*.descendant-pid", launcher.SOURCE_SHARDS, args.output_dir
            )
            descendant_pids = self.recorded_pids(descendants)
            leaders = [os.getpgid(pid) for pid in descendant_pids]
            self.assertEqual(len(set(leaders)), launcher.SOURCE_SHARDS)
            os.kill(worker.pid, signal.SIGTERM)
            worker.join(8.0)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
            self.assert_pids_gone(descendant_pids + leaders)
            self.assertFalse(args.manifest.exists())

    def test_sigterm_during_filter_cleans_its_process_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args, contract = self.make_run_case(root, PRODUCER_C, FORKING_FILTER_C)
            worker = multiprocessing.get_context("fork").Process(
                target=run_worker, args=(args, contract)
            )
            worker.start()
            descendants = self.wait_for_paths(
                "filter-descendant.pid", 1, args.output_dir
            )
            descendant_pids = self.recorded_pids(descendants)
            leaders = [os.getpgid(pid) for pid in descendant_pids]
            os.kill(worker.pid, signal.SIGTERM)
            worker.join(8.0)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
            self.assert_pids_gone(descendant_pids + leaders)
            self.assertFalse(args.manifest.exists())

    def test_existing_output_fails_before_fork(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "source-manifest.json"
            sentinel = root / "shard-00.log"
            sentinel.write_text("keep", encoding="utf-8")
            outputs = launcher._expected_output_paths(root, manifest)
            with self.assertRaisesRegex(launcher.LauncherError, "existing"):
                launcher._preflight_paths([], outputs)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
