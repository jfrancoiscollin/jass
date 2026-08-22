#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Search-aware attribution of CURRICULUM errors to PatternEval weights.

The earlier error-region screen counted buckets active in the *root* position.
That is useful for prevalence, but it cannot say which coefficients ranked the
two competing actions inside search.  This screen follows the fixed-depth PV
of the exact teacher action and its rival, extracts the exact-fold PatternEval
design vectors at both PV leaves, and forms the signed local Jacobian

    d(root_value(teacher) - root_value(rival)) / d(weight).

Discovery fixes one bounded direction and one region.  Confirmation evaluates
that frozen direction once on unseen opening/transposition components and on
their matched non-loss controls.  No model is fitted and no game is played.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_learning as learning
    from jobs.tools import l3_curriculum_search_error_atlas as search_atlas
    from jobs.tools import l3_context3_decision_flip_autopsy as ctx
    from jobs.tools import calibrate_vs_scan as cv
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import l3_curriculum_error_learning as learning  # type: ignore
    import l3_curriculum_search_error_atlas as search_atlas  # type: ignore
    import l3_context3_decision_flip_autopsy as ctx  # type: ignore
    import calibrate_vs_scan as cv  # type: ignore


SCHEMA_SOURCE = "jass.l3_curriculum_search_error_atlas_shard.v1"
SCHEMA_SHARD = "jass.l3_curriculum_error_residual_leaf_shard.v1"
SCHEMA_REPORT = "jass.l3_curriculum_error_residual_atlas.v1"
SCHEMA_REGION = "jass.l3_curriculum_error_region.v1"
EXACT_ERROR_THRESHOLD_CP = 50.0


def _patterns_module() -> Any:
    tools = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
    sys.path.insert(0, str(tools))
    import patterns  # type: ignore
    return patterns


def _pattern_modules() -> tuple[Any, Any, Any]:
    patterns = _patterns_module()
    import train_stream  # type: ignore
    import eval_phase  # type: ignore
    return patterns, train_stream, eval_phase


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _root_sign(fen: str) -> float:
    return 1.0 if fen.split(":", 1)[0] == "B" else -1.0


class ExactFeatureExtractor:
    """Exact-fold MG/EG sparse design vectors plus unfolded representatives."""

    def __init__(self) -> None:
        self.patterns, train_stream, self.eval_phase = _pattern_modules()
        self.folder = train_stream.Folder("exact")
        self.total = int(self.patterns.TOTAL_BUCKETS)

    def vector(self, fen: str) -> tuple[dict[int, float], dict[int, int]]:
        wm, _wk, bm, _bk, _stm = learning._fen_bits(fen)
        black = np.asarray([bm], dtype=np.uint64)
        white = np.asarray([wm], dtype=np.uint64)
        indices = self.patterns.extract_indices(black, white)
        full = self.patterns.flat_feature_columns(indices)[0]
        cols, signs = self.folder.cols_signs(black, white)
        wmg = float(self.eval_phase.tempo_wmg_bb(white, black)[0])
        result: dict[int, float] = defaultdict(float)
        representatives: dict[int, int] = {}
        for canonical, sign, unfolded in zip(cols[0], signs[0], full, strict=True):
            col = int(canonical)
            representatives[col] = min(representatives.get(col, int(unfolded)), int(unfolded))
            result[col] += float(sign) * wmg
            result[self.total + col] += float(sign) * (1.0 - wmg)
        return dict(result), representatives


def _subtract(
    teacher: dict[int, float], rival: dict[int, float], *, sign: float
) -> dict[int, float]:
    keys = set(teacher) | set(rival)
    return {
        key: sign * (teacher.get(key, 0.0) - rival.get(key, 0.0))
        for key in keys
        if abs(teacher.get(key, 0.0) - rival.get(key, 0.0)) > 1e-15
    }


def _mean_vectors(left: dict[int, float], right: dict[int, float]) -> dict[int, float]:
    return {
        key: (left.get(key, 0.0) + right.get(key, 0.0)) / 2.0
        for key in set(left) | set(right)
        if abs(left.get(key, 0.0) + right.get(key, 0.0)) > 1e-15
    }


def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
    keys = set(left) | set(right)
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    ln = math.sqrt(sum(value * value for value in left.values()))
    rn = math.sqrt(sum(value * value for value in right.values()))
    return dot / (ln * rn) if ln and rn else 0.0


def _normalise(values: dict[int, float]) -> dict[int, float]:
    norm = math.sqrt(sum(value * value for value in values.values()))
    return {key: value / norm for key, value in values.items()} if norm else {}


def _ranked_actions(decision: dict[str, Any]) -> list[str]:
    values = decision.get("action_values") or {}
    return sorted(
        values,
        key=lambda action: (int(values[action]["twice_root_cp"]), str(action)),
        reverse=True,
    )


def _rival(decision: dict[str, Any], *, label: str) -> tuple[str | None, str]:
    teacher = str(decision["exact_teacher_action"])
    historical = str(decision["historical_action"])
    if label == "error" and float(decision["historical_regret_cp"]) < EXACT_ERROR_THRESHOLD_CP:
        mode = (
            "exact_reclassified_historical_optimal"
            if historical == teacher else "exact_reclassified_below_50cp"
        )
        return None, mode
    if historical != teacher:
        rival = historical
        mode = "historical_action"
    elif label == "error":
        raise ValueError("exact error above threshold cannot equal its teacher")
    else:
        rival = next((action for action in _ranked_actions(decision) if action != teacher), "")
        mode = "exact_runner_up" if rival else "forced_single_legal_action"
    if rival == teacher:
        raise ValueError(f"{label}: rival unexpectedly equals teacher")
    if not rival:
        values = decision.get("action_values") or {}
        if label != "control" or historical != teacher or set(values) != {teacher}:
            raise ValueError(f"{label}: no distinct teacher/rival action outside a forced control")
        return None, mode
    return rival, mode


def _search_leaf(engine: Any, fen: str, depth: int) -> dict[str, Any]:
    _move, result = ctx._search(engine, fen, depth)
    leaf = result.get("pv_leaf_fen")
    if not isinstance(leaf, str) or not leaf:
        raise ValueError("instrumented search did not publish pv_leaf_fen")
    learning._fen_bits(leaf)  # parser/round-trip guard
    return result


def _orientation(
    *,
    engine: Any,
    referee: Any,
    extractor: ExactFeatureExtractor,
    root_fen: str,
    teacher_action: str,
    rival_action: str,
    depth: int,
    expected_values: dict[str, Any],
    image: bool,
) -> dict[str, Any]:
    teacher_move = search_atlas._parse_action(teacher_action)
    rival_move = search_atlas._parse_action(rival_action)
    teacher_child = ctx._child_fen(referee, root_fen, teacher_move)
    rival_child = ctx._child_fen(referee, root_fen, rival_move)
    teacher_result = _search_leaf(engine, teacher_child, depth)
    rival_result = _search_leaf(engine, rival_child, depth)
    expected_teacher = expected_values[teacher_action][
        "child_exact_image" if image else "child_original"
    ]
    expected_rival = expected_values[rival_action][
        "child_exact_image" if image else "child_original"
    ]
    if int(teacher_result["score"]) != int(expected_teacher["score"]):
        raise ValueError("teacher child score drift from certified atlas")
    if int(rival_result["score"]) != int(expected_rival["score"]):
        raise ValueError("rival child score drift from certified atlas")
    teacher_vec, teacher_reps = extractor.vector(str(teacher_result["pv_leaf_fen"]))
    rival_vec, rival_reps = extractor.vector(str(rival_result["pv_leaf_fen"]))
    gradient = _subtract(teacher_vec, rival_vec, sign=_root_sign(root_fen))
    representatives = dict(teacher_reps)
    for key, value in rival_reps.items():
        representatives[key] = min(representatives.get(key, value), value)
    return {
        "root_fen": root_fen,
        "teacher_action": teacher_action,
        "rival_action": rival_action,
        "teacher_child_fen": teacher_child,
        "rival_child_fen": rival_child,
        "teacher_pv_leaf_fen": teacher_result["pv_leaf_fen"],
        "rival_pv_leaf_fen": rival_result["pv_leaf_fen"],
        "teacher_score": int(teacher_result["score"]),
        "rival_score": int(rival_result["score"]),
        "teacher_nodes": int(teacher_result["nodes"]),
        "rival_nodes": int(rival_result["nodes"]),
        "gradient": gradient,
        "representatives": representatives,
    }


def analyse_decision(
    decision: dict[str, Any],
    *,
    label: str,
    engine: Any,
    referee: Any,
    extractor: ExactFeatureExtractor,
    depth: int,
) -> dict[str, Any]:
    teacher = str(decision["exact_teacher_action"])
    rival, rival_mode = _rival(decision, label=label)
    fen = str(decision["source"]["fen"])
    if rival is None:
        if label == "error":
            if rival_mode not in {
                "exact_reclassified_historical_optimal",
                "exact_reclassified_below_50cp",
            }:
                raise ValueError("non-rival error has an unexpected reclassification mode")
            regret = float(decision["historical_regret_cp"])
            if not 0.0 <= regret < EXACT_ERROR_THRESHOLD_CP:
                raise ValueError("reclassified exact error is not below 50 cp")
            historical_equal = teacher == str(decision["historical_action"])
            if historical_equal != (rival_mode == "exact_reclassified_historical_optimal"):
                raise ValueError("reclassified error reason/action identity drift")
            if historical_equal and regret != 0.0:
                raise ValueError("historical-optimal exact row has non-zero regret")
            return {
                "label": label,
                "source": decision["source"],
                "teacher_action": teacher,
                "rival_action": None,
                "rival_mode": rival_mode,
                "reclassification_reason": rival_mode,
                "informative_ranking": False,
                "reclassified_exact_non_error": True,
                "forced_single_action": False,
                "historical_regret_cp": regret,
                "orientation_cosine": None,
                "original": None,
                "exact_image": None,
                "gradient": [],
            }
        # A single-legal-action control has no ranking that a coefficient
        # update can damage.  It remains authenticated in the population but
        # contributes neither a fabricated zero margin nor an observation to
        # the paired control test.  The aggregate caps this population at 5%.
        image_actions = {
            search_atlas._mapped_image_action(action)
            for action in decision["action_values"]
        }
        if image_actions != {search_atlas._mapped_image_action(teacher)}:
            raise ValueError("forced control exact-image action cardinality drift")
        return {
            "label": label,
            "source": decision["source"],
            "teacher_action": teacher,
            "rival_action": None,
            "rival_mode": rival_mode,
            "reclassification_reason": None,
            "informative_ranking": False,
            "reclassified_exact_non_error": False,
            "forced_single_action": True,
            "historical_regret_cp": float(decision["historical_regret_cp"]),
            "orientation_cosine": None,
            "original": None,
            "exact_image": None,
            "gradient": [],
        }
    original = _orientation(
        engine=engine, referee=referee, extractor=extractor,
        root_fen=fen, teacher_action=teacher, rival_action=rival,
        depth=depth, expected_values=decision["action_values"], image=False,
    )
    image_fen = ctx.exact_image_fen(fen)
    image_teacher = search_atlas._mapped_image_action(teacher)
    image_rival = search_atlas._mapped_image_action(rival)
    image_values = {
        search_atlas._mapped_image_action(action): value
        for action, value in decision["action_values"].items()
    }
    exact_image = _orientation(
        engine=engine, referee=referee, extractor=extractor,
        root_fen=image_fen, teacher_action=image_teacher, rival_action=image_rival,
        depth=depth, expected_values=image_values, image=True,
    )
    gradient = _mean_vectors(original["gradient"], exact_image["gradient"])
    representatives = dict(original["representatives"])
    for key, value in exact_image["representatives"].items():
        representatives[key] = min(representatives.get(key, value), value)
    return {
        "label": label,
        "source": decision["source"],
        "teacher_action": teacher,
        "rival_action": rival,
        "rival_mode": rival_mode,
        "reclassification_reason": None,
        "informative_ranking": True,
        "reclassified_exact_non_error": False,
        "forced_single_action": False,
        "historical_regret_cp": float(decision["historical_regret_cp"]),
        "orientation_cosine": _cosine(original["gradient"], exact_image["gradient"]),
        "original": original,
        "exact_image": exact_image,
        "gradient": [
            {
                "coordinate": int(key),
                "value": float(value),
                "representative_full_column": int(representatives[key % extractor.total]),
            }
            for key, value in sorted(gradient.items())
        ],
    }


def worker(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.atlas_shard)
    source = json.loads(source_path.read_text())
    if source.get("schema") != SCHEMA_SOURCE:
        raise ValueError("source atlas shard schema drift")
    if int(source.get("shard", -1)) != args.shard or int(source.get("nshards", -1)) != args.nshards:
        raise ValueError("source atlas shard identity drift")
    if sha256(Path(args.champion)) != source.get("champion_sha256"):
        raise ValueError("champion differs from certified atlas")
    if sha256(Path(args.search_params)) != source.get("search_params_sha256"):
        raise ValueError("search parameters differ from certified atlas")
    depth = int(source.get("judge_depth", -1))
    if depth <= 0:
        raise ValueError("invalid certified judge depth")
    rows = list(source.get("rows") or [])
    if args.max_pairs:
        rows = rows[: args.max_pairs]
    spec = Path(args.search_params).read_text().strip()
    engine = cv.JassEngine(
        args.jass, label=f"curriculum-residual-s{args.shard}",
        pattern_path=args.champion, search_params=spec,
    )
    referee = cv.Referee(args.jass)
    extractor = ExactFeatureExtractor()
    output = []
    try:
        for pair in rows:
            output.append({
                "pair_id": int(pair["pair_id"]),
                "split": str(pair["split"]),
                "error": analyse_decision(
                    pair["error"], label="error", engine=engine,
                    referee=referee, extractor=extractor, depth=depth,
                ),
                "control": analyse_decision(
                    pair["control"], label="control", engine=engine,
                    referee=referee, extractor=extractor, depth=depth,
                ),
            })
    finally:
        referee.close(); engine.close()
    return {
        "schema": SCHEMA_SHARD,
        "source_atlas_sha256": sha256(source_path),
        "source_jass_sha256": str(source.get("jass_sha256")),
        "champion_sha256": sha256(Path(args.champion)),
        "jass_sha256": sha256(Path(args.jass)),
        "search_params_sha256": sha256(Path(args.search_params)),
        "shard": args.shard,"nshards": args.nshards,"max_pairs": args.max_pairs,
        "judge_depth": depth,"pairs": len(output),"rows": output,
        "fits": 0,"strength_games": 0,"selfplay_games": 0,
        "frozen_reads": 0,"promotion_authorized": False,
    }


def _gradient(row: dict[str, Any]) -> dict[int, float]:
    values = {int(item["coordinate"]): float(item["value"]) for item in row["gradient"]}
    return _normalise(values)


def _bootstrap(values: Iterable[float], *, samples: int, seed: int) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {"n": 0,"mean": None,"ci95": [None,None],"probability_positive": None}
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=np.float64)
    for start in range(0, samples, 2048):
        stop = min(samples, start + 2048)
        idx = rng.integers(0, len(array), size=(stop-start, len(array)))
        means[start:stop] = array[idx].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return {
        "n": len(array),"mean": float(array.mean()),
        "ci95": [float(low),float(high)],
        "probability_positive": float(np.mean(means > 0.0)),
    }


def _sign_flip_pvalue(values: list[float], *, samples: int, seed: int) -> float:
    array = np.asarray(values, dtype=np.float64)
    if not len(array): return 1.0
    observed = float(array.mean())
    rng = np.random.default_rng(seed)
    exceed = 1
    done = 0
    while done < samples:
        size = min(4096, samples-done)
        signs = rng.choice(np.asarray([-1.0,1.0]), size=(size,len(array)))
        exceed += int(np.count_nonzero((signs*array).mean(axis=1) >= observed))
        done += size
    return exceed / (samples + 1)


def _project(vector: dict[int, float], direction: dict[int, float]) -> float:
    return sum(vector.get(key, 0.0) * value for key, value in direction.items())


def aggregate(
    shards: list[dict[str, Any]], *,
    min_discovery_hits: int,
    min_region_buckets: int,
    max_region_buckets: int,
    min_orientation_cosine: float,
    min_coordinate_replication: float,
    bootstrap_samples: int,
    permutation_samples: int,
    seed: int,
    expected_informative_errors: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not shards or {int(row.get("shard",-1)) for row in shards} != set(range(len(shards))):
        raise ValueError("residual shards are incomplete")
    if any(row.get("schema") != SCHEMA_SHARD for row in shards):
        raise ValueError("residual shard schema drift")
    if any(int(row.get("nshards",-1)) != len(shards) for row in shards):
        raise ValueError("residual shard count drift")
    if any(int(row.get("max_pairs",-1)) != 0 for row in shards):
        raise ValueError("aggregate refuses preflight shards")
    identities = {}
    for key in ("champion_sha256","source_jass_sha256","jass_sha256","search_params_sha256"):
        values = {str(row.get(key,"")) for row in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"shards do not authenticate one {key}")
        identities[key] = next(iter(values))
    rows = [item for shard in shards for item in shard["rows"]]
    rows.sort(key=lambda row: int(row["pair_id"]))
    if [int(row["pair_id"]) for row in rows] != list(range(len(rows))):
        raise ValueError("residual shards do not cover contiguous matched pairs")
    all_by_split = {
        split:[row for row in rows if row["split"]==split]
        for split in ("discovery","confirm")
    }
    reclassified_rows = [
        row for row in rows
        if bool(row["error"].get("reclassified_exact_non_error",False))
    ]
    reclassified_ids = {int(row["pair_id"]) for row in reclassified_rows}
    eligible_rows = [row for row in rows if int(row["pair_id"]) not in reclassified_ids]
    by_split = {
        split:[row for row in eligible_rows if row["split"]==split]
        for split in ("discovery","confirm")
    }
    if any(not by_split[split] for split in by_split):
        raise ValueError("eligible exact-error split is empty")

    vectors: dict[tuple[int,str],dict[int,float]] = {}
    representatives: dict[int,int] = {}
    cosines: dict[str,list[float]] = defaultdict(list)
    forced_controls: dict[str,int] = defaultdict(int)
    reclassified_by_split: dict[str,int] = defaultdict(int)
    total_buckets = int(_patterns_module().TOTAL_BUCKETS)
    for pair in rows:
        error_reclassified = int(pair["pair_id"]) in reclassified_ids
        if error_reclassified:
            error = pair["error"]
            if (
                error.get("rival_mode") not in {
                    "exact_reclassified_historical_optimal",
                    "exact_reclassified_below_50cp",
                }
                or error.get("rival_action") is not None
                or error.get("informative_ranking") is not False
                or error.get("gradient") != []
                or not 0.0 <= float(error.get("historical_regret_cp",-1.0)) < EXACT_ERROR_THRESHOLD_CP
            ):
                raise ValueError("reclassified exact non-error contract drift")
            reclassified_by_split[str(pair["split"])] += 1
        for label in ("error","control"):
            decision=pair[label]
            vectors[(int(pair["pair_id"]),label)] = _gradient(decision)
            forced = bool(decision.get("forced_single_action", False))
            if forced:
                if label != "control" or decision.get("rival_mode") != "forced_single_legal_action":
                    raise ValueError("forced-action marker outside a certified control")
                if not error_reclassified:
                    forced_controls[str(pair["split"])] += 1
            elif label == "error" and error_reclassified:
                pass
            else:
                if decision.get("informative_ranking") is not True:
                    raise ValueError("non-forced ranking lacks informative marker")
                if not error_reclassified:
                    cosines[f"{pair['split']}:{label}"].append(float(decision["orientation_cosine"]))
            if not error_reclassified:
                for item in decision["gradient"]:
                    bucket=int(item["coordinate"]) % total_buckets
                    rep=int(item["representative_full_column"])
                    representatives[bucket]=min(representatives.get(bucket,rep),rep)
        if not error_reclassified and float(pair["error"].get("historical_regret_cp",-1.0)) < EXACT_ERROR_THRESHOLD_CP:
            raise ValueError("informative error fell below the preregistered 50 cp threshold")

    discovery_errors=[vectors[(int(row["pair_id"]),"error")] for row in by_split["discovery"]]
    sums: dict[int,float]=defaultdict(float); hits: dict[int,int]=defaultdict(int)
    positive: dict[int,int]=defaultdict(int); negative: dict[int,int]=defaultdict(int)
    for vector in discovery_errors:
        for key,value in vector.items():
            sums[key]+=value; hits[key]+=1
            positive[key]+=int(value>0); negative[key]+=int(value<0)
    candidates=[]
    for key,count in hits.items():
        if count < min_discovery_hits: continue
        consistency=max(positive[key],negative[key])/count
        if consistency < 0.75: continue
        mean=sums[key]/len(discovery_errors)
        candidates.append((abs(mean),count,consistency,key,1.0 if mean>0 else -1.0))
    candidates.sort(reverse=True)
    # Region size is counted by canonical bucket, while direction may contain
    # separate MG and EG coordinates for a selected bucket.
    selected=[]; selected_buckets=set()
    for _score,count,consistency,key,direction_sign in candidates:
        bucket=key % total_buckets
        if bucket not in selected_buckets and len(selected_buckets)>=max_region_buckets:
            continue
        selected_buckets.add(bucket)
        selected.append({"coordinate":key,"bucket":bucket,"sign":direction_sign,
                         "discovery_hits":count,"discovery_sign_consistency":consistency})
    direction_norm=math.sqrt(max(len(selected),1))
    direction={int(item["coordinate"]):float(item["sign"])/direction_norm for item in selected}

    confirm_rows=by_split["confirm"]
    informative_confirm=[
        row for row in confirm_rows
        if not bool(row["control"].get("forced_single_action",False))
    ]
    error_projection=[_project(vectors[(int(row["pair_id"]),"error")],direction) for row in confirm_rows]
    paired_error_projection=[
        _project(vectors[(int(row["pair_id"]),"error")],direction)
        for row in informative_confirm
    ]
    control_projection=[
        _project(vectors[(int(row["pair_id"]),"control")],direction)
        for row in informative_confirm
    ]
    paired=[left-right for left,right in zip(paired_error_projection,control_projection,strict=True)]
    error_boot=_bootstrap(error_projection,samples=bootstrap_samples,seed=seed)
    control_boot=_bootstrap(control_projection,samples=bootstrap_samples,seed=seed+1)
    paired_boot=_bootstrap(paired,samples=bootstrap_samples,seed=seed+2)
    pvalue=_sign_flip_pvalue(paired,samples=permutation_samples,seed=seed+3)

    confirm_errors=[vectors[(int(row["pair_id"]),"error")] for row in confirm_rows]
    replicated=0
    coordinate_evidence=[]
    for item in selected:
        key=int(item["coordinate"]); sign=float(item["sign"])
        observed=[vector.get(key,0.0) for vector in confirm_errors]
        nonzero=[value for value in observed if value]
        same=sum((value>0)==(sign>0) for value in nonzero)
        fraction=same/len(nonzero) if nonzero else 0.0
        ok=len(nonzero)>=max(2,min_discovery_hits//2) and fraction>=0.6
        replicated+=int(ok)
        coordinate_evidence.append({**item,"confirm_hits":len(nonzero),
                                    "confirm_sign_consistency":fraction,"replicated":ok})
    replication=replicated/len(selected) if selected else 0.0
    all_cosines=[value for values in cosines.values() for value in values]
    symmetry_fraction=(sum(value>=min_orientation_cosine for value in all_cosines)/len(all_cosines)
                       if all_cosines else 0.0)
    forced_total=sum(forced_controls.values())
    forced_fraction=forced_total/len(eligible_rows) if eligible_rows else 1.0
    informative_confirm_fraction=len(informative_confirm)/len(confirm_rows)
    full_columns=sorted({representatives[int(item["bucket"])] for item in selected})

    gates={
        "region_bucket_count": min_region_buckets <= len(selected_buckets) <= max_region_buckets,
        "orientation_symmetry_fraction_ge_0_90": symmetry_fraction >= 0.90,
        "coordinate_replication_fraction": replication >= min_coordinate_replication,
        "confirm_error_projection_positive_95": bool(error_boot["ci95"][0] is not None and error_boot["ci95"][0] > 0.0),
        "confirm_controls_not_harmed_95": bool(control_boot["ci95"][0] is not None and control_boot["ci95"][0] >= -0.02),
        "paired_error_minus_control_positive_95": bool(paired_boot["ci95"][0] is not None and paired_boot["ci95"][0] > 0.0),
        "paired_sign_flip_p_le_0_025": pvalue <= 0.025,
        "forced_control_fraction_le_0_05": forced_fraction <= 0.05,
        "informative_confirm_pair_fraction_ge_0_95": informative_confirm_fraction >= 0.95,
        "informative_exact_error_pairs_match_preregistered_290": len(eligible_rows) == expected_informative_errors,
    }
    passed=all(gates.values())
    region={
        "schema":SCHEMA_REGION,"fold":"exact_rot180_colour_swap",
        "fit_authorized":passed,"champion_sha256":identities["champion_sha256"],
        "jass_sha256":identities["jass_sha256"],
        "search_params_sha256":identities["search_params_sha256"],
        "pattern_columns_full":full_columns if passed else [],"extras":[],
        "selection":{"kind":"discovery_pv_leaf_jacobian_then_sealed_confirmation",
                     "unit":"opening_transposition_component","confirm_used_for_selection":False,
                     "terminal_loss_alone_is_not_a_training_signal":True},
        "confirmation":([
            {"full_pattern_column":column,"evidence":"fixed_direction_confirmed"}
            for column in full_columns
        ] if passed else []),
        "strict_fit_contract":{"train_dense_extras":False,"train_pattern_mg_and_eg":True,
                               "freeze_everything_else_at_champion":True},
        "promotion_authorized":False,
    }
    report={
        "schema":SCHEMA_REPORT,
        "verdict":("JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED" if passed
                   else "JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED"),
        "passed":passed,**identities,"pairs":len(rows),
        "informative_error_pairs":len(eligible_rows),
        "reclassified_exact_non_errors":{
            "total":len(reclassified_rows),
            "fraction":len(reclassified_rows)/len(rows),
            "by_split":{split:int(reclassified_by_split.get(split,0)) for split in all_by_split},
            "excluded_with_their_controls_from_fit_statistics":True,
            "zero_vectors_used_as_observations":False,
        },
        "all_splits":{split:len(values) for split,values in all_by_split.items()},
        "splits":{split:len(values) for split,values in by_split.items()},
        "selected_coordinates":coordinate_evidence,
        "selected_canonical_buckets":len(selected_buckets),
        "selected_full_columns":len(full_columns),
        "orientation_cosines":{
            key:{"n":len(values),"mean":float(np.mean(values)),"min":float(np.min(values))}
            for key,values in sorted(cosines.items())
        },
        "orientation_symmetry_fraction":symmetry_fraction,
        "forced_controls":{
            "total":forced_total,"fraction":forced_fraction,
            "by_split":{split:int(forced_controls.get(split,0)) for split in by_split},
            "excluded_from_control_and_paired_statistics":True,
            "informative_confirm_pairs":len(informative_confirm),
            "informative_confirm_fraction":informative_confirm_fraction,
        },
        "coordinate_replication_fraction":replication,
        "confirm":{
            "error_projection":error_boot,"control_projection":control_boot,
            "paired_error_minus_control":paired_boot,"sign_flip_pvalue":pvalue,
        },
        "gates":gates,"failed_gates":[key for key,value in gates.items() if not value],
        "fit_authorized":passed,"next_stage":("local_residual_refit" if passed else None),
        "fits":0,"strength_games":0,"selfplay_games":0,"frozen_reads":0,
        "promotion_authorized":False,"automatic_continuation":False,
    }
    return report,region


def _publish(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists(): raise FileExistsError(f"refusing to overwrite {path}")
    temporary=path.with_name(path.name+f".tmp.{hashlib.sha256(_canonical(value)).hexdigest()[:12]}")
    temporary.write_bytes(_canonical(value)); temporary.replace(path)


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(description=__doc__)
    sub=root.add_subparsers(dest="command",required=True)
    work=sub.add_parser("worker")
    work.add_argument("--atlas-shard",type=Path,required=True)
    work.add_argument("--jass",required=True); work.add_argument("--champion",required=True)
    work.add_argument("--search-params",required=True); work.add_argument("--shard",type=int,required=True)
    work.add_argument("--nshards",type=int,required=True); work.add_argument("--max-pairs",type=int,default=0)
    work.add_argument("--out",type=Path,required=True)
    combine=sub.add_parser("aggregate")
    combine.add_argument("--shard",action="append",type=Path,required=True)
    combine.add_argument("--min-discovery-hits",type=int,default=6)
    combine.add_argument("--min-region-buckets",type=int,default=8)
    combine.add_argument("--max-region-buckets",type=int,default=128)
    combine.add_argument("--min-orientation-cosine",type=float,default=0.0)
    combine.add_argument("--min-coordinate-replication",type=float,default=0.70)
    combine.add_argument("--bootstrap-samples",type=int,default=100000)
    combine.add_argument("--permutation-samples",type=int,default=10000)
    combine.add_argument("--seed",type=int,default=2026082222)
    combine.add_argument("--expected-informative-errors",type=int,required=True)
    combine.add_argument("--report",type=Path,required=True); combine.add_argument("--region",type=Path,required=True)
    return root


def main() -> int:
    args=parser().parse_args()
    if args.command=="worker":
        result=worker(args); _publish(args.out,result)
        print(json.dumps({"schema":result["schema"],"pairs":result["pairs"],"shard":result["shard"]},sort_keys=True))
    else:
        shards=[json.loads(path.read_text()) for path in args.shard]
        report,region=aggregate(
            shards,min_discovery_hits=args.min_discovery_hits,
            min_region_buckets=args.min_region_buckets,max_region_buckets=args.max_region_buckets,
            min_orientation_cosine=args.min_orientation_cosine,
            min_coordinate_replication=args.min_coordinate_replication,
            bootstrap_samples=args.bootstrap_samples,permutation_samples=args.permutation_samples,
            seed=args.seed,expected_informative_errors=args.expected_informative_errors,
        )
        _publish(args.report,report); _publish(args.region,region)
        print(json.dumps({"verdict":report["verdict"],"failed_gates":report["failed_gates"]},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
