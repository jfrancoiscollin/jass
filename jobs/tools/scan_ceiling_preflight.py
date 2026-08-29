#!/usr/bin/env python3
"""Technical-only fail-closed preflight for the pinned Scan ceiling benchmark.

The sentinels in this program are not members of the scientific cohort.  No
ranking accuracy or other benchmark metric is computed here.  The program
authenticates the unmodified Scan source/build, proves the Jass/Scan board and
move correspondence, and replays both one-thread node-budget adapters.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import (  # noqa: E402
    jass_fen_to_scan_pos,
    parse_scan_move,
)
from jobs.tools.scan_ceiling_fen_to_jnnw import fen_record, load_fens  # noqa: E402
from jobs.tools.scan_ceiling_scan_score import (  # noqa: E402
    SCAN_COMMIT,
    SCAN_NODE_POLL_QUANTUM,
    read_children,
    record_fingerprint,
    record_to_scan_pos,
    scan_snapshot_upper_bound,
    score_token_to_centi,
)
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint  # noqa: E402


SCAN_SOURCE_URL = "https://github.com/rhalbersma/scan"
SCAN_TREE = "023eace16a90ec543b6b6174c79cfc42488a356e"
SCAN_RELEASE = "Scan 3.1"
MAKEFILE_BLOB = "7598768214fd8b3120067b65702de4756e9d8b83"
PROTOCOL_BLOB = "a65b0943bb4e026b2d54df5b9c638e3d80de92ca"
CXXFLAGS = "-pthread -std=c++14 -fno-rtti -O2 -mpopcnt -flto -DNDEBUG"
LDFLAGS = "-pthread -O2 -flto"
POLICY_ENV = (
    "JASS_TB_MOVE_ORDER_POLICY", "JASS_DSSD_MOVE_ORDER_POLICY",
    "JASS_T3_F6_MODEL",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_output(argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(
        argv, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def git_value(source: Path, *args: str) -> str:
    return command_output(["git", "-C", str(source), *args])


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing TSV header")
        return list(reader)


def without_field(rows: Iterable[dict[str, str]], field: str) -> list[dict[str, str]]:
    return [{key: value for key, value in row.items() if key != field} for row in rows]


def captured_squares(captured_hex: str) -> tuple[int, ...]:
    value = int(captured_hex, 16)
    squares: list[int] = []
    while value:
        bit = (value & -value).bit_length() - 1
        value &= value - 1
        squares.append(bit + 1)
    return tuple(squares)


def row_move_key(row: dict[str, str]) -> tuple[int, int, tuple[int, ...]]:
    return int(row["from"]), int(row["to"]), captured_squares(row["captured_hex"])


def scan_move_key(text: str) -> tuple[int, int, tuple[int, ...]]:
    move = parse_scan_move(text)
    return move.frm, move.to, tuple(sorted(move.captures))


def source_provenance(args: argparse.Namespace) -> dict[str, object]:
    manifest = load_json(args.build_manifest)
    head = git_value(args.scan_source, "rev-parse", "HEAD")
    tree = git_value(args.scan_source, "rev-parse", "HEAD^{tree}")
    make_blob = git_value(args.scan_source, "rev-parse", "HEAD:src/Makefile")
    protocol_blob = git_value(args.scan_source, "rev-parse", "HEAD:protocol.txt")
    modified = git_value(args.scan_source, "ls-files", "-m")
    staged = git_value(args.scan_source, "diff", "--cached", "--name-only")
    if (head, tree, make_blob, protocol_blob) != (
        SCAN_COMMIT, SCAN_TREE, MAKEFILE_BLOB, PROTOCOL_BLOB,
    ):
        raise ValueError("pinned Scan commit/tree/blob provenance drift")
    if modified or staged:
        raise ValueError("tracked Scan source was modified")

    main_source = (args.scan_source / "src/main.cpp").read_text(encoding="utf-8")
    search_source = (args.scan_source / "src/search.cpp").read_text(encoding="utf-8")
    source_contract = {
        "hub_node_assignment": "if (nodes >= 0) si.nodes = nodes;" in main_source,
        "analyze_disables_move": "si.move = !analyze;" in main_source,
        "analyze_disables_book": "si.book = !analyze;" in main_source,
        "new_game_clears_tt": 'command == "new-game"' in main_source
        and "G_TT.clear();" in main_source,
        "node_counter_abort": "void Search_Local::inc_node()" in search_source
        and "m_node >= m_sg->si().nodes" in search_source
        and "m_sg->depth() > 1" in search_source,
    }
    if not all(source_contract.values()):
        raise ValueError(f"Scan node/analyze source contract drift: {source_contract}")

    binary_sha = sha256(args.scan)
    probe_sha = sha256(args.scan_probe)
    expected = {
        "source_url": SCAN_SOURCE_URL,
        "source_commit": SCAN_COMMIT,
        "source_tree": SCAN_TREE,
        "release": SCAN_RELEASE,
        "makefile_blob": MAKEFILE_BLOB,
        "protocol_blob": PROTOCOL_BLOB,
        "compiler_command": "g++",
        "cxxflags": CXXFLAGS,
        "ldflags": LDFLAGS,
        "scan_binary_sha256": binary_sha,
        "scan_move_probe_sha256": probe_sha,
        "threads_per_search": 1,
        "scan_bb_size": 0,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"build manifest {key} drift: {manifest.get(key)!r} != {value!r}")
    for key in ("compiler_version", "cpu_information", "operating_system"):
        if not isinstance(manifest.get(key), str) or not str(manifest[key]).strip():
            raise ValueError(f"build manifest missing {key}")
    if manifest.get("tracked_scan_source_modified") is not False:
        raise ValueError("build manifest does not certify unmodified Scan source")

    return {
        **expected,
        "compiler_version": manifest["compiler_version"],
        "cpu_information": manifest["cpu_information"],
        "operating_system": manifest["operating_system"],
        "source_bundle_sha256": manifest.get("source_bundle_sha256"),
        "scan_eval_sha256": manifest.get("scan_eval_sha256"),
        "scan_ini_sha256": manifest.get("scan_ini_sha256"),
        "source_contract": source_contract,
        "scan_build_manifest_sha256": sha256(args.build_manifest),
        "scan_source_tracked_clean": True,
    }


def run_probe(probe: Path, scan_pos: str) -> tuple[dict[tuple[int, int, tuple[int, ...]], str], str]:
    result = subprocess.run(
        [str(probe), scan_pos], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    lines = result.stdout.splitlines()
    if not lines or lines[0] != "move\tchild_pos":
        raise ValueError("official Scan move probe header drift")
    rows: dict[tuple[int, int, tuple[int, ...]], str] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 2 or len(parts[1]) != 51:
            raise ValueError(f"invalid Scan move-probe row: {line!r}")
        key = scan_move_key(parts[0])
        if key in rows:
            raise ValueError("duplicate semantic move from official Scan generator")
        rows[key] = parts[1]
    return rows, result.stdout


def normalized_groups(path: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "row_index", "sibling_identity", "parent_id", "child_fingerprint",
        "child_legal_moves", "child_forced_capture", "child_rule_terminal",
        "child_tb_exact", "exact_parent_utility",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            writer.writerow({
                "row_index": index,
                "sibling_identity": f"technical-smoke-{index:04d}",
                "parent_id": row["parent_id"],
                "child_fingerprint": row["child_fingerprint"],
                "child_legal_moves": row["child_legal_moves"],
                "child_forced_capture": row["child_forced_capture"],
                "child_rule_terminal": row["child_rule_terminal"],
                "child_tb_exact": row["child_tb_exact"],
                "exact_parent_utility": row["exact_parent_utility"],
            })


def run_logged(argv: list[str], log: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        argv, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(argv)}")


def validate_ladder_rows(
    rows_a: list[dict[str, str]], rows_b: list[dict[str, str]],
    groups: list[dict[str, str]],
) -> dict[str, int]:
    if without_field(rows_a, "elapsed_us") != without_field(rows_b, "elapsed_us"):
        raise ValueError("Jass exact-node deterministic replay drift")
    if len(rows_a) != len(groups):
        raise ValueError("Jass technical ladder cardinality drift")
    searched = terminal = tb = max_depth_exhausted = 0
    for index, (row, group) in enumerate(zip(rows_a, groups)):
        if int(row["row_index"]) != index or int(row["budget_nodes"]) != 1000:
            raise ValueError("Jass ladder row alignment/budget drift")
        is_terminal = int(group["child_rule_terminal"]) == 1
        is_tb = int(group["child_tb_exact"]) == 1
        nodes = int(row["nodes"])
        if is_terminal or is_tb:
            if nodes != 0 or int(row["terminal_exact"]) != int(is_terminal) \
                    or int(row["tb_exact"]) != int(is_tb) \
                    or row["budget_status"] != ("terminal_exact" if is_terminal else "tb_exact"):
                raise ValueError("Jass terminal/TB exact handling drift")
            terminal += int(is_terminal)
            tb += int(is_tb)
        else:
            status = row["budget_status"]
            requested_reached = (
                nodes == 1000 and status == "requested_nodes_reached"
                and row["stop_reason"] == "nodes"
                and int(row["aborted_iteration"]) == 1
            )
            max_depth = (
                0 < nodes < 1000 and status == "max_depth_exhausted"
                and row["stop_reason"] == "none"
                and int(row["completed_depth"]) == 64
                and int(row["effective_depth"]) == 64
                and int(row["aborted_iteration"]) == 0
            )
            if not requested_reached and not max_depth:
                raise ValueError("Jass exact node-budget contract drift")
            searched += 1
            max_depth_exhausted += int(max_depth)
    if searched == 0 or terminal == 0 or tb == 0 or max_depth_exhausted == 0:
        raise ValueError("technical fixture lacks Jass searched/terminal/TB coverage")
    return {
        "searched_rows": searched,
        "requested_nodes_reached_rows": searched - max_depth_exhausted,
        "max_depth_exhausted_rows": max_depth_exhausted,
        "terminal_exact_rows": terminal,
        "tb_exact_rows": tb,
    }


def validate_scan_rows(
    rows_a: list[dict[str, str]], rows_b: list[dict[str, str]],
    groups: list[dict[str, str]], records: list[bytes], probe: Path,
) -> dict[str, int]:
    if without_field(rows_a, "elapsed_seconds") != without_field(rows_b, "elapsed_seconds"):
        raise ValueError("Scan deterministic fresh-state replay drift")
    if len(rows_a) != len(groups):
        raise ValueError("Scan technical ladder cardinality drift")
    searched = terminal = forced_nonterminal = snapshot_above_requested = 0
    legal_cache: dict[str, set[tuple[int, int, tuple[int, ...]]]] = {}
    for index, (row, group, record) in enumerate(zip(rows_a, groups, records)):
        if int(row["row_index"]) != index or int(row["budget_nodes"]) != 1000 \
                or int(row["requested_nodes"]) != 1000:
            raise ValueError("Scan ladder row alignment/request drift")
        child_score = score_token_to_centi(row["child_score_token"])
        if int(row["parent_score_centi"]) != -child_score:
            raise ValueError("Scan child-to-parent POV sign drift")
        is_terminal = int(group["child_rule_terminal"]) == 1
        if is_terminal:
            if int(row["terminal_exact"]) != 1 or int(row["last_info_nodes"]) != 0 \
                    or row["done_move"]:
                raise ValueError("Scan terminal child was searched")
            terminal += 1
            continue
        nodes = int(row["last_info_nodes"])
        snapshot_upper = scan_snapshot_upper_bound(1000)
        above_requested = int(nodes > 1000)
        if not 0 < nodes <= snapshot_upper or int(row["terminal_exact"]) != 0 \
                or int(row["snapshot_upper_bound"]) != snapshot_upper \
                or int(row["snapshot_above_requested"]) != above_requested:
            raise ValueError("Scan progressive node snapshot contract drift")
        pos = record_to_scan_pos(record)
        if pos not in legal_cache:
            legal_cache[pos] = set(run_probe(probe, pos)[0])
        if scan_move_key(row["done_move"]) not in legal_cache[pos]:
            raise ValueError("Scan search returned a move outside its pinned legal generator")
        searched += 1
        snapshot_above_requested += above_requested
        if int(group["child_forced_capture"]) == 1:
            forced_nonterminal += 1
    if searched == 0 or terminal == 0 or forced_nonterminal == 0:
        raise ValueError("technical fixture lacks Scan searched/terminal/forced coverage")
    return {
        "searched_rows": searched, "terminal_exact_rows": terminal,
        "forced_nonterminal_search_rows": forced_nonterminal,
        "snapshot_above_requested_rows": snapshot_above_requested,
        "node_poll_quantum": SCAN_NODE_POLL_QUANTUM,
        "snapshot_upper_bound": scan_snapshot_upper_bound(1000),
    }


def technical_planning_estimates(
    jass_rows: list[dict[str, str]], scan_rows: list[dict[str, str]],
) -> dict[str, object]:
    """Turn the 1k smoke into transparent, non-scientific planning ranges."""
    jass_searched = [row for row in jass_rows if int(row["nodes"]) > 0]
    scan_searched = [row for row in scan_rows if int(row["terminal_exact"]) == 0]
    jass_elapsed = sum(int(row["elapsed_us"]) for row in jass_searched) / 1_000_000.0
    scan_elapsed = sum(float(row["elapsed_seconds"]) for row in scan_searched)
    jass_requested = sum(int(row["budget_nodes"]) for row in jass_searched)
    scan_requested = sum(int(row["requested_nodes"]) for row in scan_searched)
    if not jass_searched or not scan_searched or jass_elapsed <= 0 or scan_elapsed <= 0:
        raise ValueError("technical smoke cannot establish positive planning throughput")
    jass_nps = jass_requested / jass_elapsed
    scan_nps = scan_requested / scan_elapsed
    workers = 15  # preregistered one-logical-CPU margin on the 16-CPU HOME host.

    def estimate(label: str, engine: str, siblings: tuple[int, int], nodes_per_sibling: int) -> tuple[str, dict[str, object]]:
        nps = jass_nps if engine == "Jass" else scan_nps
        low_nodes = siblings[0] * nodes_per_sibling
        high_nodes = siblings[1] * nodes_per_sibling
        return label, {
            "engine": engine,
            "sibling_count_range": list(siblings),
            "requested_node_work_range": [low_nodes, high_nodes],
            "eta_seconds_range_at_smoke_nps_and_15_workers": [
                low_nodes / (nps * workers), high_nodes / (nps * workers),
            ],
        }

    stages = dict([
        estimate("Jass_BASE2000", "Jass", (4_000, 32_000), 256_000),
        estimate("Jass_DEEP512", "Jass", (1_024, 8_192), 1_000_000),
        estimate("Scan_BASE2000", "Scan", (4_000, 32_000), 256_000),
        estimate("Scan_DEEP512", "Scan", (1_024, 8_192), 3_000_000),
        estimate("Scan_ULTRA256", "Scan", (512, 4_096), 5_000_000),
    ])
    stages.update({
        "selection": {"eta": "not_node_based"},
        "static_inference": {"eta": "not_node_based"},
        "readout_bootstrap": {"eta": "not_node_based"},
    })
    return {
        "planning_only_not_scientific_metric": True,
        "worker_cap": workers,
        "logical_cpu_margin": 1,
        "observed_1k_smoke": {
            "Jass": {
                "searches": len(jass_searched), "requested_nodes": jass_requested,
                "wall_seconds_sum": jass_elapsed, "requested_nodes_per_second": jass_nps,
            },
            "Scan": {
                "searches": len(scan_searched), "requested_nodes": scan_requested,
                "wall_seconds_sum": scan_elapsed, "requested_nodes_per_second": scan_nps,
                "stock_info_nodes_are_progressive_snapshots": True,
            },
        },
        "stage_eta_ranges": stages,
        "caveat": "1k sentinel throughput is an operational estimate; immutable node budgets and cohort never depend on it",
    }


def symmetry_replay(
    records: list[bytes], groups: list[dict[str, str]],
    jass_rows: list[dict[str, str]], scan_rows: list[dict[str, str]],
) -> dict[str, object]:
    parents: dict[int, list[int]] = defaultdict(list)
    for index, row in enumerate(groups):
        parents[int(row["parent_id"])].append(index)
    shared: tuple[int, int] | None = None
    for left in sorted(parents):
        left_children = {
            canonical_fingerprint(record_fingerprint(records[index])): index
            for index in parents[left]
        }
        for right in sorted(parents):
            if right <= left:
                continue
            right_children = {
                canonical_fingerprint(record_fingerprint(records[index])): index
                for index in parents[right]
            }
            overlap = sorted(set(left_children) & set(right_children))
            if overlap:
                shared = left_children[overlap[0]], right_children[overlap[0]]
                break
        if shared is not None:
            break
    if shared is None:
        raise ValueError("technical fixture lacks a colour-swap symmetry child pair")
    a, b = shared
    if jass_rows[a]["parent_score"] != jass_rows[b]["parent_score"]:
        raise ValueError("Jass parent-POV colour-swap replay drift")
    if scan_rows[a]["parent_score_centi"] != scan_rows[b]["parent_score_centi"]:
        raise ValueError("Scan parent-POV colour-swap replay drift")
    return {
        "colour_swap_child_pair_found": True,
        "jass_parent_scores_equal": True,
        "scan_parent_scores_equal": True,
    }


def execute(args: argparse.Namespace, transcript: list[str]) -> dict[str, object]:
    provenance = source_provenance(args)
    fens = load_fens(args.parents_fen)
    parent_records = read_children(args.parents_jnnw)
    child_records = read_children(args.children_jnnw)
    groups = read_tsv(args.groups)
    export = load_json(args.export_report)
    if len(fens) != len(parent_records) or len(child_records) != len(groups):
        raise ValueError("technical sentinel cardinality drift")
    if export.get("schema") != "jass.scan_ceiling_sibling_export.v1" \
            or export.get("input_parents") != len(parent_records) \
            or export.get("emitted_siblings") != len(child_records):
        raise ValueError("technical sibling export report drift")

    for fen, record in zip(fens, parent_records):
        if fen_record(fen) != record or jass_fen_to_scan_pos(fen) != record_to_scan_pos(record):
            raise ValueError("Jass FEN/JNNW/Scan 51-character board+STM roundtrip drift")

    by_parent: dict[int, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for index, row in enumerate(groups):
        if int(row["local_row_index"]) != index:
            raise ValueError("technical sibling rows are not aligned")
        if record_fingerprint(child_records[index]) != row["child_fingerprint"]:
            raise ValueError("technical child record/fingerprint drift")
        by_parent[int(row["parent_id"])].append((index, row))
    if sorted(by_parent) != list(range(len(parent_records))):
        raise ValueError("technical parent IDs drift")

    probe_transcripts: list[str] = []
    for parent_id, parent_record in enumerate(parent_records):
        scan_moves, raw = run_probe(args.scan_probe, record_to_scan_pos(parent_record))
        probe_transcripts.append(f"## parent {parent_id}\n{raw}")
        jass_moves: dict[tuple[int, int, tuple[int, ...]], str] = {}
        for index, row in by_parent[parent_id]:
            key = row_move_key(row)
            if key in jass_moves:
                raise ValueError("duplicate semantic move from Jass generator")
            jass_moves[key] = record_to_scan_pos(child_records[index])
        if jass_moves != scan_moves:
            missing = sorted(set(jass_moves) - set(scan_moves))
            extra = sorted(set(scan_moves) - set(jass_moves))
            mismatch = sorted(key for key in set(jass_moves) & set(scan_moves)
                              if jass_moves[key] != scan_moves[key])
            raise ValueError(
                f"Jass/Scan legal-child mapping drift at sentinel {parent_id}: "
                f"missing={missing}, extra={extra}, child_mismatch={mismatch}"
            )
    transcript.extend(probe_transcripts)

    requirements = {
        "both_parent_colours": {record[32] for record in parent_records} == {0, 1},
        "promotion_move": any(int(row["promotes"]) == 1 for row in groups),
        "multi_capture_move": any(int(row["num_captures"]) >= 2 for row in groups),
        "terminal_child": any(int(row["child_rule_terminal"]) == 1 for row in groups),
        "forced_capture_nonterminal_child": any(
            int(row["child_forced_capture"]) == 1
            and int(row["child_rule_terminal"]) == 0 for row in groups
        ),
        "jass_tablebase_exact_child": any(int(row["child_tb_exact"]) == 1 for row in groups),
    }
    if not all(requirements.values()):
        raise ValueError(f"technical sentinel coverage incomplete: {requirements}")

    env = os.environ.copy()
    for name in POLICY_ENV:
        env.pop(name, None)
    env["SCAN_BENCHMARK_ONLY"] = "true"
    with tempfile.TemporaryDirectory(prefix="scan-ceiling-preflight-", dir=args.workdir) as directory:
        work = Path(directory)
        normalized = work / "groups.tsv"
        normalized_groups(normalized, groups)
        jass_paths = [work / f"jass-{suffix}" for suffix in ("a.tsv", "a.json", "b.tsv", "b.json")]
        for label, score_path, report_path in (
            ("a", jass_paths[0], jass_paths[1]), ("b", jass_paths[2], jass_paths[3]),
        ):
            run_logged([
                str(args.jass_ladder), str(args.children_jnnw), str(normalized),
                str(score_path), str(report_path), str(args.curriculum), str(args.egdb),
                "1000", "-", "0", "1", "16", "256",
            ], work / f"jass-{label}.log", env)
        jass_rows_a = read_tsv(jass_paths[0]); jass_rows_b = read_tsv(jass_paths[2])
        jass_counts = validate_ladder_rows(jass_rows_a, jass_rows_b, groups)
        for report_path in (jass_paths[1], jass_paths[3]):
            report = load_json(report_path)
            if report.get("threads_per_search") != 1 or report.get("book_enabled") is not False \
                    or report.get("node_limit_mode") != "exact" \
                    or report.get("requested_node_caps_exactly_configured") is not True \
                    or report.get("node_stopped_rows_equal_requested") is not True \
                    or report.get("max_depth_exhaustion_allowed") is not True \
                    or report.get("max_ply") != 64:
                raise ValueError("Jass technical runtime contract drift")

        scan_paths = [work / f"scan-{suffix}" for suffix in ("a.tsv", "a.json", "b.tsv", "b.json")]
        for label, score_path, report_path in (
            ("a", scan_paths[0], scan_paths[1]), ("b", scan_paths[2], scan_paths[3]),
        ):
            run_logged([
                sys.executable, str(args.scan_score_script), "--scan", str(args.scan),
                "--children", str(args.children_jnnw), "--groups", str(normalized),
                "--budgets", "1000", "--timeout-seconds", str(args.timeout_seconds),
                "--output", str(score_path), "--report", str(report_path),
                "--source-commit", SCAN_COMMIT,
            ], work / f"scan-{label}.log", env)
        scan_rows_a = read_tsv(scan_paths[0]); scan_rows_b = read_tsv(scan_paths[2])
        scan_counts = validate_scan_rows(
            scan_rows_a, scan_rows_b, groups, child_records, args.scan_probe,
        )
        for report_path in (scan_paths[1], scan_paths[3]):
            report = load_json(report_path)
            params = report.get("runtime_params")
            if report.get("threads_per_search") != 1 or report.get("book_enabled") is not False \
                    or report.get("bb_size") != 0 or not isinstance(params, dict) \
                    or report.get("requested_nodes_exactly_configured") is not True \
                    or report.get("scan_source_algorithms_modified") is not False \
                    or report.get("node_poll_quantum") != SCAN_NODE_POLL_QUANTUM:
                raise ValueError("Scan technical runtime report drift")
            if params.get("threads") != "1" or params.get("book") != "false" \
                    or params.get("bb-size") != "0":
                raise ValueError("Scan effective one-thread/no-book/no-bitbase drift")
        symmetry = symmetry_replay(child_records, groups, jass_rows_a, scan_rows_a)
        planning = technical_planning_estimates(jass_rows_a, scan_rows_a)

        for name in ("jass-a.log", "jass-b.log", "scan-a.log", "scan-b.log"):
            transcript.append(f"## {name}\n{(work / name).read_text(encoding='utf-8')}")

    return {
        "schema": "jass.scan_ceiling_technical_preflight.v1",
        "verdict": "SCAN_MAPPING_TECHNICAL_PASS",
        "passed": True,
        "benchmark_only": True,
        "scan_benchmark_only": True,
        "scientific_metrics_published": 0,
        **provenance,
        "scan_runtime_params": {
            "variant": "normal", "book": False, "book_ply": 4,
            "book_margin": 4, "ponder": False, "threads": 1,
            "tt_size": 24, "bb_size": 0, "mode": "go analyze",
            "fresh_state": "new-game before every sibling/budget",
            "node_budget_contract": (
                "exact requested N; stock last-info snapshot bounded by next 16-node poll"
            ),
        },
        "jass_runtime_params": {
            "book": False, "threads": 1, "fresh_engine_each_sibling_budget": True,
            "node_limit_mode": "exact", "egdb_path": str(args.egdb),
            "max_depth_exhaustion": (
                "allowed below N only after a complete MAX_PLY=64 search with no stop"
            ),
        },
        "technical_sentinels": {
            "parents": len(parent_records), "siblings": len(child_records),
            "requirements": requirements, "jass": jass_counts, "scan": scan_counts,
            "symmetry": symmetry,
        },
        "throughput_and_eta": planning,
        "guards": {
            "fits": 0, "refits": 0, "calibrations": 0,
            "feature_selections": 0, "model_selections": 0,
            "strength_games": 0, "bakes": 0, "promotions": 0,
            "promotion_authorized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--scan-source", type=Path, required=True)
    parser.add_argument("--scan-probe", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--parents-fen", type=Path, required=True)
    parser.add_argument("--parents-jnnw", type=Path, required=True)
    parser.add_argument("--children-jnnw", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--export-report", type=Path, required=True)
    parser.add_argument("--jass-ladder", type=Path, required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--egdb", type=Path, required=True)
    parser.add_argument("--scan-score-script", type=Path,
                        default=ROOT / "jobs/tools/scan_ceiling_scan_score.py")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript.parent.mkdir(parents=True, exist_ok=True)
    args.workdir.mkdir(parents=True, exist_ok=True)
    transcript: list[str] = []
    try:
        payload = execute(args, transcript)
        rc = 0
    except BaseException as error:  # fail closed and preserve the technical diagnosis
        payload = {
            "schema": "jass.scan_ceiling_technical_preflight.v1",
            "verdict": "SCAN_MAPPING_TECHNICAL_STOP",
            "passed": False,
            "benchmark_only": True,
            "scan_benchmark_only": True,
            "scientific_metrics_published": 0,
            "error_type": type(error).__name__, "error": str(error),
            "guards": {"fits": 0, "calibrations": 0, "strength_games": 0,
                       "promotions": 0, "promotion_authorized": False},
        }
        transcript.append(f"## FAILURE\n{type(error).__name__}: {error}\n")
        rc = 4
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript.write_text("\n".join(transcript), encoding="utf-8")
    print(json.dumps({"verdict": payload["verdict"], "passed": payload["passed"]}, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
