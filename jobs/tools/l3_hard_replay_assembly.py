#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assemble the causal UNIFORM_REPLAY vs HARD_REPLAY fit corpora.

The historical source is split before mining.  Both replay policies consume
only its train prefix.  A separate fresh corpus supplies a common,
opening-disjoint holdout tail which is copied bit-for-bit into both arms.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path

from tools import selfplay_frontier as frontier


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _namespace_rows(rows: list[frontier.Meta], namespace: int) -> list[frontier.Meta]:
    if not 0 < namespace < 256:
        raise ValueError("namespace must fit in one non-zero byte")
    games: dict[int, int] = {}
    openings: dict[int, int] = {}
    out: list[frontier.Meta] = []
    prefix = namespace << 56
    for row in rows:
        game = games.setdefault(row.game_id, len(games))
        opening = openings.setdefault(row.opening_id, len(openings))
        if game >= (1 << 56) or opening >= (1 << 56):
            raise ValueError("too many game/opening IDs for namespace")
        out.append(frontier.Meta(prefix | game, prefix | opening, row.seeded))
    return out


def _records_digest(records: list[bytes]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
    return digest.hexdigest()


def _meta_digest(rows: list[frontier.Meta]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(struct.pack("<QQB", row.game_id, row.opening_id, row.seeded))
    return digest.hexdigest()


def _wdl_canary(records: list[bytes]) -> dict:
    canary = frontier._load_canary()
    return canary.evaluate(canary.histogram_from_records(records))


def _verify_hard_manifest(
    manifest: dict,
    *,
    manifest_path: Path,
    history_data: Path,
    history_meta: Path,
    history_split: Path,
    hard_data: Path,
    hard_meta: Path,
    manifest_code_sha: str,
    replay_records: int,
) -> None:
    outputs = manifest.get("outputs", {})
    if (
        manifest.get("schema") != 1
        or manifest.get("operation") != "mine-hard"
        or manifest.get("signal") != "failed_conversion"
        or manifest.get("selection_scope") != "train_only"
        or manifest.get("holdout_records_examined_for_signal") != 0
        or manifest.get("external_teacher_inputs") != 0
        or manifest.get("one_per_game") is not True
        or manifest.get("colour_mirror") is not True
        or manifest.get("code_sha") != manifest_code_sha
        or manifest.get("max_records_including_colour_mirrors") != replay_records
        or manifest.get("selection", {}).get("output_records") != replay_records
        or manifest.get("input", {}).get("data_sha256") != _sha256(history_data)
        or manifest.get("input", {}).get("meta_sha256") != _sha256(history_meta)
        or manifest.get("input", {}).get("split_manifest_sha256")
        != _sha256(history_split)
        or outputs.get("hard_replay", {}).get("sha256") != _sha256(hard_data)
        or outputs.get("hard_replay_meta", {}).get("sha256") != _sha256(hard_meta)
        or outputs.get("hard_replay", {}).get("records") != replay_records
        or outputs.get("hard_replay_meta", {}).get("records") != replay_records
    ):
        raise ValueError(f"{manifest_path}: hard-mining certificate mismatch")


def assemble(args: argparse.Namespace) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_sha):
        raise ValueError("--code-sha must be a full lowercase 40-hex commit SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", args.hard_manifest_code_sha):
        raise ValueError(
            "--hard-manifest-code-sha must be a full lowercase 40-hex commit SHA"
        )
    if args.replay_records < 2 or args.replay_records % 2:
        raise ValueError("--replay-records must be an even integer >= 2")
    if args.fresh_records < 2:
        raise ValueError("--fresh-records must be >= 2")

    paths = {
        "history_data": Path(args.history_data),
        "history_meta": Path(args.history_meta),
        "history_split": Path(args.history_split_manifest),
        "fresh_data": Path(args.fresh_data),
        "fresh_meta": Path(args.fresh_meta),
        "fresh_split": Path(args.fresh_split_manifest),
        "hard_data": Path(args.hard_data),
        "hard_meta": Path(args.hard_meta),
        "hard_manifest": Path(args.hard_manifest),
        "control_data": Path(args.out_control_data),
        "control_meta": Path(args.out_control_meta),
        "treatment_data": Path(args.out_treatment_data),
        "treatment_meta": Path(args.out_treatment_meta),
        "manifest": Path(args.manifest),
    }
    resolved = [path.resolve() for path in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("all input and output paths must be distinct")
    for name in (
        "control_data",
        "control_meta",
        "treatment_data",
        "treatment_meta",
        "manifest",
    ):
        if paths[name].exists():
            raise ValueError(f"refusing to overwrite existing output: {paths[name]}")

    history_records, history_rows = frontier.read_pair(
        paths["history_data"], paths["history_meta"]
    )
    history_split, history_train_count = frontier._load_split_contract(
        paths["history_split"], history_records, history_rows
    )
    if history_train_count < args.replay_records:
        raise ValueError(
            "historical train partition is smaller than the requested replay dose"
        )

    fresh_records, fresh_rows = frontier.read_pair(
        paths["fresh_data"], paths["fresh_meta"]
    )
    fresh_split, fresh_train_count = frontier._load_split_contract(
        paths["fresh_split"], fresh_records, fresh_rows
    )
    if len(fresh_records) != args.fresh_records:
        raise ValueError(
            f"fresh corpus count {len(fresh_records)} != {args.fresh_records}"
        )
    fresh_holdout_count = len(fresh_records) - fresh_train_count
    if fresh_train_count == 0 or fresh_holdout_count == 0:
        raise ValueError("fresh train and common holdout must both be non-empty")

    hard_records, hard_rows = frontier.read_pair(
        paths["hard_data"], paths["hard_meta"]
    )
    if len(hard_records) != args.replay_records:
        raise ValueError(
            f"hard replay count {len(hard_records)} != {args.replay_records}"
        )
    hard_manifest = _read_json(paths["hard_manifest"])
    _verify_hard_manifest(
        hard_manifest,
        manifest_path=paths["hard_manifest"],
        history_data=paths["history_data"],
        history_meta=paths["history_meta"],
        history_split=paths["history_split"],
        hard_data=paths["hard_data"],
        hard_meta=paths["hard_meta"],
        manifest_code_sha=args.hard_manifest_code_sha,
        replay_records=args.replay_records,
    )

    uniform_indices = sorted(
        frontier._sample_indices(
            history_train_count, args.replay_records, args.uniform_seed
        )
    )
    uniform_records = [history_records[index] for index in uniform_indices]
    uniform_rows = [history_rows[index] for index in uniform_indices]

    control_replay_rows = _namespace_rows(uniform_rows, 1)
    treatment_replay_rows = _namespace_rows(hard_rows, 1)
    common_fresh_rows = _namespace_rows(fresh_rows, 2)
    fresh_train_records = fresh_records[:fresh_train_count]
    fresh_holdout_records = fresh_records[fresh_train_count:]
    fresh_train_rows = common_fresh_rows[:fresh_train_count]
    fresh_holdout_rows = common_fresh_rows[fresh_train_count:]

    control_records = (
        uniform_records + fresh_train_records + fresh_holdout_records
    )
    treatment_records = (
        hard_records + fresh_train_records + fresh_holdout_records
    )
    control_rows = control_replay_rows + fresh_train_rows + fresh_holdout_rows
    treatment_rows = treatment_replay_rows + fresh_train_rows + fresh_holdout_rows

    expected_total = args.replay_records + args.fresh_records
    if (
        len(control_records) != expected_total
        or len(treatment_records) != expected_total
        or control_records[-fresh_holdout_count:]
        != treatment_records[-fresh_holdout_count:]
        or control_rows[-fresh_holdout_count:]
        != treatment_rows[-fresh_holdout_count:]
    ):
        raise ValueError("internal error: common-tail assembly mismatch")

    control_train_openings = {
        row.opening_id for row in control_rows[:-fresh_holdout_count]
    }
    treatment_train_openings = {
        row.opening_id for row in treatment_rows[:-fresh_holdout_count]
    }
    holdout_openings = {
        row.opening_id for row in control_rows[-fresh_holdout_count:]
    }
    if control_train_openings & holdout_openings:
        raise ValueError("control train leaks into common holdout")
    if treatment_train_openings & holdout_openings:
        raise ValueError("treatment train leaks into common holdout")

    control_wdl = _wdl_canary(control_records)
    treatment_wdl = _wdl_canary(treatment_records)
    if not control_wdl["ok"] or not treatment_wdl["ok"]:
        problems = control_wdl["problems"] + treatment_wdl["problems"]
        raise ValueError("assembled corpus WDL canary failed: " + "; ".join(problems))

    frontier._write_pair_atomic(
        paths["control_data"], paths["control_meta"], control_records, control_rows
    )
    frontier._write_pair_atomic(
        paths["treatment_data"],
        paths["treatment_meta"],
        treatment_records,
        treatment_rows,
    )

    checked_control, checked_control_meta = frontier.read_pair(
        paths["control_data"], paths["control_meta"]
    )
    checked_treatment, checked_treatment_meta = frontier.read_pair(
        paths["treatment_data"], paths["treatment_meta"]
    )
    if (
        checked_control != control_records
        or checked_control_meta != control_rows
        or checked_treatment != treatment_records
        or checked_treatment_meta != treatment_rows
    ):
        raise ValueError("assembled corpus read-back verification failed")

    common_holdout_data_sha = _records_digest(fresh_holdout_records)
    common_holdout_meta_sha = _meta_digest(fresh_holdout_rows)
    payload = {
        "schema": 1,
        "operation": "l3-hard-replay-causal-assembly",
        "code_sha": args.code_sha,
        "primary_contrast": "HARD_REPLAY minus UNIFORM_REPLAY",
        "single_factor": "historical_replay_selection_policy",
        "external_teacher_inputs": 0,
        "records": {
            "per_arm": expected_total,
            "fresh_per_arm": args.fresh_records,
            "historical_replay_per_arm": args.replay_records,
            "common_holdout": fresh_holdout_count,
            "fit_train_per_arm": expected_total - fresh_holdout_count,
        },
        "seeds": {
            "uniform_replay": args.uniform_seed,
            "history_split": history_split.get("seed"),
            "fresh_split": fresh_split.get("seed"),
        },
        "history": {
            "data_sha256": _sha256(paths["history_data"]),
            "meta_sha256": _sha256(paths["history_meta"]),
            "split_manifest_sha256": _sha256(paths["history_split"]),
            "records": len(history_records),
            "train_records": history_train_count,
            "holdout_records": len(history_records) - history_train_count,
            "holdout_examined_for_selection": False,
        },
        "fresh": {
            "data_sha256": _sha256(paths["fresh_data"]),
            "meta_sha256": _sha256(paths["fresh_meta"]),
            "split_manifest_sha256": _sha256(paths["fresh_split"]),
            "records": len(fresh_records),
            "train_records": fresh_train_count,
            "holdout_records": fresh_holdout_count,
        },
        "common_holdout": {
            "data_payload_sha256": common_holdout_data_sha,
            "meta_payload_sha256": common_holdout_meta_sha,
            "opening_disjoint_from_both_train_arms": True,
            "bit_identical_between_arms": True,
        },
        "control": {
            "name": "UNIFORM_REPLAY",
            "selection": "exact_uniform_record_sample_from_historical_train",
            "sampled_records": len(uniform_records),
            "sampled_games": len({row.game_id for row in uniform_rows}),
            "sampled_openings": len({row.opening_id for row in uniform_rows}),
            "wdl_canary": control_wdl,
            "data_sha256": _sha256(paths["control_data"]),
            "meta_sha256": _sha256(paths["control_meta"]),
        },
        "treatment": {
            "name": "HARD_REPLAY",
            "selection": "failed_conversion_train_only_v1",
            "sampled_records": len(hard_records),
            "sampled_games": len({row.game_id for row in hard_rows}),
            "sampled_openings": len({row.opening_id for row in hard_rows}),
            "hard_manifest_sha256": _sha256(paths["hard_manifest"]),
            "hard_manifest_code_sha": args.hard_manifest_code_sha,
            "hard_manifest": hard_manifest,
            "wdl_canary": treatment_wdl,
            "data_sha256": _sha256(paths["treatment_data"]),
            "meta_sha256": _sha256(paths["treatment_meta"]),
        },
        "causal_certificate": {
            "same_parent": True,
            "same_fresh_records": True,
            "same_fresh_order": True,
            "same_common_holdout": True,
            "same_total_records": True,
            "same_fit_recipe_required": True,
            "historical_holdout_excluded_from_both_arms": True,
            "only_replay_selection_policy_differs": True,
        },
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    frontier._atomic_write_text(
        paths["manifest"],
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble causal uniform-vs-hard replay fit corpora"
    )
    parser.add_argument("--history-data", required=True)
    parser.add_argument("--history-meta", required=True)
    parser.add_argument("--history-split-manifest", required=True)
    parser.add_argument("--fresh-data", required=True)
    parser.add_argument("--fresh-meta", required=True)
    parser.add_argument("--fresh-split-manifest", required=True)
    parser.add_argument("--hard-data", required=True)
    parser.add_argument("--hard-meta", required=True)
    parser.add_argument("--hard-manifest", required=True)
    parser.add_argument("--replay-records", type=int, required=True)
    parser.add_argument("--fresh-records", type=int, required=True)
    parser.add_argument("--uniform-seed", type=int, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--hard-manifest-code-sha", required=True)
    parser.add_argument("--out-control-data", required=True)
    parser.add_argument("--out-control-meta", required=True)
    parser.add_argument("--out-treatment-data", required=True)
    parser.add_argument("--out-treatment-meta", required=True)
    parser.add_argument("--manifest", required=True)
    return parser


def main() -> int:
    assemble(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
