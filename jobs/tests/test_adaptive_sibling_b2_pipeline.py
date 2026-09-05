from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from jobs.tests.test_adaptive_sibling_b2_teacher_merge import Fixture
from jobs.tools import adaptive_sibling_b2_allocation_input as allocation
from jobs.tools import adaptive_sibling_b2_projection as projection
from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_statistics as statistics
from jobs.tools import adaptive_sibling_b2_teacher_merge as merger


ROOT = Path(__file__).resolve().parents[2]
CODE_SHA = "a" * 40


def canonical(value: object) -> bytes:
    return allocation.canonical_json_bytes(value)


def write_json(path: Path, value: object) -> bytes:
    raw = canonical(value)
    path.write_bytes(raw)
    return raw


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "local_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        **extra,
    }


def find_native(name: str, environment: str) -> Path | None:
    configured = os.environ.get(environment)
    candidates = [] if configured is None else [Path(configured)]
    candidates.extend((ROOT / "build-b2-merge" / name,
                       ROOT / "build-b2-merge" / f"{name}.exe"))
    for candidate in candidates:
        native_for_host = os.name != "nt" or candidate.suffix.lower() == ".exe"
        if candidate.is_file() and native_for_host \
                and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return candidate.resolve()
    return None


def make_observations_transport_valid(fixture: Fixture) -> None:
    """Turn fixture scores into valid, interrupted exact-node observations."""
    for shard, groups_path in enumerate(fixture.shard_paths["groups"]):
        lines = groups_path.read_text(encoding="ascii").splitlines()
        if not lines or lines[0].split("\t") != list(merger.GROUP_FIELDS):
            raise AssertionError("fixture groups header drift")
        rows: list[str] = []
        for line in lines[1:]:
            values = line.split("\t")
            row = dict(zip(merger.GROUP_FIELDS, values, strict=True))
            for horizon in ("5k", "50k", "200k"):
                row[f"effective_depth{horizon}"] = str(
                    int(row[f"completed_depth{horizon}"]) + 1)
                row[f"aborted{horizon}"] = "1"
            rows.append("\t".join(row[field] for field in merger.GROUP_FIELDS))
        groups_path.write_text(
            "\t".join(merger.GROUP_FIELDS) + "\n" + "\n".join(rows) + "\n",
            encoding="ascii", newline="",
        )
        fixture.shards[shard]["groups_tsv"] = descriptor(groups_path, rows=len(rows))
    fixture.write_manifest()


def copy_as(source: Path, directory: Path, name: str | None = None) -> Path:
    target = directory / (source.name if name is None else name)
    shutil.copyfile(source, target)
    return target


def make_legacy_files(directory: Path) -> dict[str, object]:
    report = {
        "schema": allocation.LEGACY_SCHEMA,
        "verdict": allocation.LEGACY_VERDICT,
        "source": {"parents": 8_000, "rows": 74_449},
        "equivalence": {"parents_compared": 8_000,
                        "allocation_decision_matches": 8_000,
                        "final_b1_result_matches": 8_000},
        "information_barrier": {
            "q200_fields_in_projection_decision": 0,
            "q200_policy_reads": 0, "q200_value_reads": 0,
            "q200_label_reads": 0, "q200_policy_branches": 0,
            "nodes200k_policy_reads": 0, "nodes200k_policy_branches": 0,
            "nodes200k_preseal_aggregation_reads": 0,
            "nodes200k_validated_rows": 74_449,
            "allocation_hash_excludes_q200_values": True,
            "postseal_join_hash_includes_q200_results": True,
        },
        "published_artifacts": {"empty_diff": {"sha256": "6" * 64}},
        "searches": 0, "fits": 0, "strength_games": 0,
        "promotion_authorized": False, "real_adaptive_teacher_authorized": False,
    }
    report_path = directory / "legacy-equivalence-report.json"
    summary_path = directory / "legacy-terminal-summary.json"
    write_json(report_path, report)
    write_json(summary_path, {"verdict": allocation.LEGACY_VERDICT})
    return {
        "report": descriptor(report_path), "report_schema": allocation.LEGACY_SCHEMA,
        "terminal_summary": descriptor(summary_path),
        "verdict": allocation.LEGACY_VERDICT,
        "parents": 8_000, "rows": 74_449, "differences": 0,
    }


def materialize_common_inputs(fixture: Fixture, directory: Path) -> dict[str, object]:
    directory.mkdir()
    report_source = fixture.outputs / "teacher-merge-report.json"
    report = json.loads(report_source.read_text(encoding="ascii"))

    parents_jnnw = copy_as(fixture.parents_jnnw, directory)
    parents_tsv = copy_as(fixture.parents_tsv, directory)
    selection_report = copy_as(fixture.selection_report, directory)
    teacher_manifest = copy_as(fixture.manifest, directory)
    children = copy_as(fixture.outputs / "children.jnnw", directory)
    groups = copy_as(fixture.outputs / "groups.tsv", directory)
    semantics = copy_as(fixture.outputs / "semantic-actions.jsonl", directory)
    merge_report = copy_as(report_source, directory)

    identities_path = directory / "ordered-identities.txt"
    identities_path.write_bytes(b"".join(
        f"{parent['canonical_fingerprint']}\n".encode("ascii")
        for parent in fixture.parents))
    ordered = descriptor(
        identities_path, rows=allocation.PARENT_COUNT,
        serialization="canonical_fingerprint_ascii, one per line, LF terminated")

    native_path = directory / "native-verification-receipt.json"
    native_raw = write_json(native_path, report["native_verification"]["receipt"])
    if hashlib.sha256(native_raw).hexdigest() != report["native_verification"]["sha256"]:
        raise AssertionError("native receipt materialization drift")

    preregistration = directory / "preregistration.md"
    preregistration.write_text("# Synthetic pre-registered pipeline fixture\n", encoding="utf-8")
    allocation_tool = copy_as(Path(allocation.__file__), directory, "allocation-input-tool.py")
    projection_tool = copy_as(Path(projection.__file__), directory, "projection-tool.py")
    readout_tool = copy_as(Path(readout.__file__), directory, "readout-tool.py")
    statistics_tool = copy_as(Path(statistics.__file__), directory, "statistics-tool.py")
    preflight = directory / "statistical-preflight-receipt.json"
    write_json(preflight, {"fixture": "no bootstrap invoked"})

    report_desc = descriptor(merge_report)
    teacher_input_desc = descriptor(teacher_manifest)
    children_desc = dict(report["outputs"]["children_jnnw"])
    groups_desc = dict(report["outputs"]["groups_tsv"])
    semantic_desc = dict(report["outputs"]["semantic_actions"])
    for path, desc in ((children, children_desc), (groups, groups_desc),
                       (semantics, semantic_desc)):
        if descriptor(path, **{key: value for key, value in desc.items()
                              if key not in {"local_name", "sha256", "size_bytes"}}) != desc:
            raise AssertionError("copied teacher payload descriptor drift")

    publication = {
        "artifacts": {
            "children_jnnw": {key: children_desc[key]
                              for key in ("local_name", "sha256", "size_bytes")},
            "groups_tsv": {key: groups_desc[key]
                           for key in ("local_name", "sha256", "size_bytes")},
            "merge_report": report_desc,
            "semantic_actions": {key: semantic_desc[key]
                                 for key in ("local_name", "sha256", "size_bytes")},
        },
        "byte_roundtrip_verified": True, "code_sha": CODE_SHA,
        "input_manifest": teacher_input_desc,
        "schema": allocation.MERGE_PUBLICATION_SCHEMA,
    }
    publication_path = directory / "teacher-publication-receipt.json"
    write_json(publication_path, publication)

    selection = {
        "report": descriptor(selection_report),
        "report_schema": allocation.SELECTION_SCHEMA,
        "parents_jnnw": descriptor(
            parents_jnnw, records=allocation.PARENT_COUNT, record_size_bytes=38),
        "parents_tsv": descriptor(parents_tsv, rows=allocation.PARENT_COUNT),
        "ordered_identities": ordered, "selected": allocation.PARENT_COUNT,
        "cell_quota": allocation.CELL_QUOTA,
        "cell_order": list(allocation.CELL_ORDER),
    }
    teacher = {
        "input_manifest": teacher_input_desc,
        "report": report_desc, "report_schema": allocation.MERGE_SCHEMA,
        "publication_receipt": descriptor(publication_path),
        "publication_schema": allocation.MERGE_PUBLICATION_SCHEMA,
        "native_verification_receipt": descriptor(native_path),
        "native_verification_schema": allocation.NATIVE_SCHEMA,
        "children_jnnw": children_desc, "groups_tsv": groups_desc,
        "semantic_actions": semantic_desc,
    }
    tools = {
        "allocation_input": descriptor(allocation_tool),
        "projection": descriptor(projection_tool),
        "readout": descriptor(readout_tool),
        "statistics": descriptor(statistics_tool),
        "statistical_preflight_receipt": descriptor(preflight),
    }
    return {
        "code_sha": CODE_SHA,
        "preregistration": {"file": descriptor(preregistration),
                            "schema": allocation.PREREGISTRATION_SCHEMA},
        "selection": selection, "teacher_merge": teacher, "tools": tools,
    }


class AdaptiveSiblingB2PipelineTests(unittest.TestCase):
    def test_real_4000_parent_pipeline_through_rich_readout(self) -> None:
        helper = find_native("adaptive_sibling_b2_native_fixture",
                             "JASS_B2_NATIVE_FIXTURE_HELPER")
        verifier = find_native("jass_adaptive_sibling_b2_teacher_merge_verify",
                               "JASS_B2_NATIVE_VERIFIER")
        if helper is None or verifier is None:
            self.skipTest("published native fixture helper/verifier are unavailable")

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            teacher_root = base / "teacher"
            teacher_root.mkdir()
            fixture = Fixture(teacher_root)
            fixture.install_real_native_catalogues(helper, verifier)
            make_observations_transport_valid(fixture)
            merge_report = merger.run(fixture.args())
            teacher_rows = merge_report["counters"]["groups_rows"]
            self.assertEqual(merge_report["counters"]["parents"], 4_000)
            self.assertEqual(merge_report["counters"]["shards"], 16)
            self.assertGreaterEqual(teacher_rows, 8_000)
            self.assertLessEqual(teacher_rows, 64_000)

            common_dir = base / "common"
            common = materialize_common_inputs(fixture, common_dir)
            allocation_manifest = {
                "schema": allocation.INPUT_SCHEMA,
                "code_sha": common["code_sha"],
                "preregistration": common["preregistration"],
                "legacy_equivalence": make_legacy_files(common_dir),
                "selection": common["selection"],
                "teacher_merge": common["teacher_merge"],
                "tools": {name: common["tools"][name]
                          for name in ("allocation_input", "projection")},
            }
            allocation_manifest_path = common_dir / "allocation-inputs.json"
            allocation_manifest_raw = write_json(allocation_manifest_path, allocation_manifest)
            allocation_dir = base / "allocation"
            completed = subprocess.run([
                sys.executable, str(Path(allocation.__file__)), "prepare",
                "--input-manifest", str(allocation_manifest_path),
                "--expected-input-manifest-sha256",
                hashlib.sha256(allocation_manifest_raw).hexdigest(),
                "--out-dir", str(allocation_dir),
            ], cwd=ROOT, capture_output=True, text=True, timeout=180, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)

            projection_dir = base / "projection"
            projection_dir.mkdir()
            receipts_path = projection_dir / "allocation-receipts-v1.jsonl"
            projection_manifest_path = projection_dir / "projection-manifest-v1.json"
            completed = subprocess.run([
                sys.executable, str(Path(projection.__file__)),
                "--input", str(allocation_dir / "allocation-parents-v1.jsonl"),
                "--out-receipts", str(receipts_path),
                "--out-manifest", str(projection_manifest_path),
            ], cwd=ROOT, capture_output=True, text=True, timeout=180, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)

            readout_inputs = base / "readout-inputs"
            shutil.copytree(common_dir, readout_inputs)
            allocation_rows = copy_as(
                allocation_dir / "allocation-parents-v1.jsonl", readout_inputs)
            allocation_report = copy_as(
                allocation_dir / "allocation-input-report-v1.json", readout_inputs)
            projection_receipts = copy_as(receipts_path, readout_inputs)
            projection_manifest = copy_as(projection_manifest_path, readout_inputs)
            readout_manifest = {
                "schema": readout.BUILD_INPUT_SCHEMA,
                "code_sha": common["code_sha"],
                "preregistration": common["preregistration"],
                "selection": common["selection"],
                "teacher_merge": common["teacher_merge"],
                "allocation": {
                    "input_jsonl": descriptor(
                        allocation_rows, rows=4_000,
                        row_schema=projection.INPUT_SCHEMA),
                    "report": descriptor(allocation_report),
                    "report_schema": allocation.REPORT_SCHEMA,
                },
                "projection": {
                    "receipts_jsonl": descriptor(
                        projection_receipts, rows=4_000,
                        row_schema=projection.RECEIPT_SCHEMA),
                    "manifest": descriptor(projection_manifest),
                    "manifest_schema": projection.MANIFEST_SCHEMA,
                },
                "tools": common["tools"],
            }
            readout_manifest_path = readout_inputs / "readout-inputs.json"
            readout_manifest_raw = write_json(readout_manifest_path, readout_manifest)
            rich_dir = base / "rich"
            failure_receipt = base / "readout-build-failure-v1.json"
            completed = subprocess.run([
                sys.executable, str(Path(readout.__file__)), "build",
                "--input-manifest", str(readout_manifest_path),
                "--expected-input-manifest-sha256",
                hashlib.sha256(readout_manifest_raw).hexdigest(),
                "--out-dir", str(rich_dir),
                "--failure-receipt", str(failure_receipt),
            ], cwd=ROOT, capture_output=True, text=True, timeout=240, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(failure_receipt.exists())

            rich_lines = (rich_dir / "parent-stats-rich-v1.jsonl").read_bytes().splitlines()
            sufficient_lines = (
                rich_dir / "parent-stats-sufficient-v1.jsonl").read_bytes().splitlines()
            self.assertEqual(len(rich_lines), 4_000)
            self.assertEqual(len(sufficient_lines), 4_000)
            report = json.loads(
                (rich_dir / "rich-to-sufficient-report-v1.json").read_text(encoding="ascii"))
            self.assertEqual(report["status"], "VALID")
            self.assertEqual(report["population"]["parents"], 4_000)
            self.assertEqual(report["population"]["teacher_rows"], teacher_rows)
            self.assertEqual(
                report["population"]["cells"],
                {cell: 500 for cell in allocation.CELL_ORDER})
            self.assertEqual(report["barrier"]["allocation_q200_value_reads"], 0)
            self.assertEqual(report["barrier"]["postseal_q200_score_decodes"], teacher_rows)
            self.assertEqual(report["actions"], {
                "searches": 0, "fits": 0, "games": 0,
                "promotions": 0, "bakes": 0,
            })

            failed_dir = base / "rich-auth-failure"
            classified_failure = base / "classified-build-failure.json"
            completed = subprocess.run([
                sys.executable, str(Path(readout.__file__)), "build",
                "--input-manifest", str(readout_manifest_path),
                "--expected-input-manifest-sha256", "0" * 64,
                "--out-dir", str(failed_dir),
                "--failure-receipt", str(classified_failure),
            ], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(completed.returncode, 4, completed.stderr)
            self.assertFalse(failed_dir.exists())
            failure = json.loads(classified_failure.read_text(encoding="ascii"))
            self.assertEqual(failure["schema"], readout.BUILD_FAILURE_SCHEMA)
            self.assertEqual(failure["status"], "SUPPORT_NOT_ESTABLISHED")
            self.assertEqual(failure["failure"], {
                "class": "INPUT_AUTHENTICATION_FAILED",
                "stage": "COMMON_MANIFEST",
                "parent_id": None, "global_row_index": None, "horizon": None,
            })
            self.assertFalse(failure["input_manifest_authenticated"])
            self.assertIsNone(failure["manifest_code_sha"])
            self.assertTrue(all(value is None for value in failure["outputs"].values()))
            self.assertTrue(all(value == 0 for value in failure["counters"].values()))


if __name__ == "__main__":
    unittest.main()
