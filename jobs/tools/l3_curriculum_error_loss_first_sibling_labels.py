#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-blind selection and stable all-sibling labels for CURRICULUM.

This is the mechanistic data stage of the preregistered loss-first route.  It
never fits a model.  States are selected using only shallow search behaviour
and structural covariates.  The same byte-identical CURRICULUM model then
judges every legal sibling at two fixed depths and in both exact orientations.
Only depth-, WDL- and symmetry-stable orderings become labels.  Sparse exact-
fold PV-leaf Jacobians are emitted for the later cross-pool screen.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import calibrate_vs_scan as cv
    from jobs.tools import l3_context3_decision_flip_autopsy as ctx
    from jobs.tools import l3_curriculum_error_learning as learning
    from jobs.tools import l3_curriculum_search_error_atlas as atlas
    from jobs.tools.l3_curriculum_error_residual_atlas import ExactFeatureExtractor
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import calibrate_vs_scan as cv  # type: ignore
    import l3_context3_decision_flip_autopsy as ctx  # type: ignore
    import l3_curriculum_error_learning as learning  # type: ignore
    import l3_curriculum_search_error_atlas as atlas  # type: ignore
    from l3_curriculum_error_residual_atlas import ExactFeatureExtractor  # type: ignore


SCHEMA_CANDIDATES = "jass.l3_curriculum_error_loss_first_candidates.v1"
SCHEMA_PROFILE_SHARD = "jass.l3_curriculum_error_loss_first_profile_shard.v1"
SCHEMA_SELECTION = "jass.l3_curriculum_error_loss_first_selection.v1"
SCHEMA_LABEL_SHARD = "jass.l3_curriculum_error_loss_first_label_shard.v1"
SCHEMA_LABELS = "jass.l3_curriculum_error_loss_first_labels.v1"
READY = "JASS_CURRICULUM_ERROR_LOSS_FIRST_LABELS_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_LOSS_FIRST_LABEL_SUPPORT_NOT_ESTABLISHED"
SOURCE_SCHEMA = "jass.curriculum_error_loss_first_source_terminal.v1"
SOURCE_VERDICT = "JASS_CURRICULUM_ERROR_LOSS_FIRST_SOURCE_READY"
PREREG_VERDICT = "JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED"
PROFILE_DEPTH = 9
TEACHER_DEPTHS = (10, 12)
DRAW_BAND_CP = 10.0
MARGIN_CAP_CP = 200.0
MIN_STABLE_ERROR_CP = 50.0
MAX_STABLE_CONTROL_CP = 10.0
MAX_CANDIDATES_PER_OPENING = 4
MAX_CANDIDATES_PER_GAME = 2
MIN_SELECTED_PER_POOL = 320
MIN_MATCHED_PER_POOL = 32


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp." + _digest(value)[:12])
    tmp.write_bytes(_canonical(value)); tmp.replace(path)


def _pool_from_source(path: str) -> int:
    normal = path.replace("\\", "/")
    if "games-pool1/" in normal:
        return 1
    if "games-pool2/" in normal:
        return 2
    raise ValueError(f"source path does not identify a campaign pool: {path}")


def _legal_moves(line: str) -> list[Any]:
    moves = []
    for raw in line.split():
        token = raw.removesuffix("+")
        move_part, marker, capture_part = token.partition("*")
        try:
            frm, to = map(int, move_part.split(">", 1))
            captures = tuple(int(value) for value in capture_part.split(",")) if marker else ()
        except ValueError as exc:
            raise ValueError(f"malformed --dump-legal token: {raw!r}") from exc
        moves.append(cv.Move(frm=frm, to=to, captures=captures))
    keys = [move.jass_apply_str() for move in moves]
    if len(keys) != len(set(keys)) or not moves:
        raise ValueError("legal action list is empty or non-canonical")
    return moves


def _structural(fen: str, actual_apply: str, legal_count: int) -> dict[str, Any]:
    wm, wk, bm, bk, _stm = learning._fen_bits(fen)
    pieces = (wm | wk | bm | bk).bit_count()
    kings = (wk | bk).bit_count()
    branch = "b01_02" if legal_count <= 2 else "b03_05" if legal_count <= 5 else "b06_plus"
    return {
        "phase": learning._phase(pieces), "piece_count": pieces,
        "king_count": kings, "kings": "kings" if kings else "no_kings",
        "tactical": "capture" if "x" in actual_apply else "quiet",
        "legal_action_count": legal_count, "branching_bin": branch,
    }


def _source_contract(source_summary: dict[str, Any], prereg: dict[str, Any]) -> None:
    if (
        source_summary.get("schema") != SOURCE_SCHEMA
        or source_summary.get("verdict") != SOURCE_VERDICT
        or source_summary.get("passed") is not True
        or int(source_summary.get("deep_target_computations", -1)) != 0
        or int(source_summary.get("new_selfplay_games", -1)) != 1536
        or source_summary.get("next_stage") != "loss_first_all_legal_sibling_labeling"
    ):
        raise ValueError("requires the exact certified loss-first source")
    if (
        prereg.get("verdict") != PREREG_VERDICT
        or prereg.get("passed") is not True
        or prereg.get("deep_sibling_labeling_authorized_after_source_audit") is not True
        or prereg.get("anchored_local_refit_authorized") is not False
    ):
        raise ValueError("requires the exact certified loss-first preregistration")
    source_prereg = source_summary.get("preregistration", {})
    expected = prereg.get("source_campaign", {})
    if (
        source_prereg.get("job") != "cpx62-1542-l3-curriculum-error-loss-first-sibling-rank-preregistration-v1"
        or expected.get("total_games") != 1536
        or expected.get("source_stage_has_no_deep_targets") is not True
    ):
        raise ValueError("source/preregistration lineage drift")


def build_candidates(
    selection: dict[str, Any], transitions: dict[str, Any], source_summary: dict[str, Any],
    prereg: dict[str, Any], *, jass: str, seed: int,
) -> dict[str, Any]:
    _source_contract(source_summary, prereg)
    if selection.get("schema") != learning.SCHEMA_SELECTION:
        raise ValueError("source selection schema drift")
    if transitions.get("schema") != learning.SCHEMA_TRANSITIONS:
        raise ValueError("source transition schema drift")
    if transitions.get("selection_sha256") != _digest(selection):
        raise ValueError("source transition/selection hash drift")
    rows = list(selection.get("rows", [])); next_rows = list(transitions.get("transitions", []))
    if len(rows) != int(selection.get("decisions", -1)) or len(next_rows) != len(rows):
        raise ValueError("source decision cardinality drift")
    legal_lines = learning._dump_legal_lines(jass, [str(row["fen"]) for row in rows])
    calibrated = learning._cv_module()
    referee = calibrated.Referee(jass)
    materialized = []
    try:
        for index, (row, transition, legal_line) in enumerate(zip(rows, next_rows, legal_lines, strict=True)):
            if int(row.get("ordinal", -1)) != index or int(transition.get("ordinal", -1)) != index:
                raise ValueError("source ordinal drift")
            legal = _legal_moves(legal_line)
            actual, _disambiguated = learning._resolve_historical_transition(
                str(row["actual_move"]), legal_line, calibrated,
                fen=str(row["fen"]), next_fen=str(transition["next_fen"]),
                referee=referee,
            )
            actual_apply = actual.jass_apply_str()
            pool = _pool_from_source(str(row["source_file"]))
            structural = _structural(str(row["fen"]), actual_apply, len(legal))
            key = hashlib.sha256(
                f"{seed}|{pool}|{row['opening_id']}|{row['game_uid']}|{row['exact_state_key']}|{row['ply']}".encode()
            ).hexdigest()
            # Deliberately omit outcome, terminal score and source path.  Tests
            # assert invariance to arbitrary outcome permutations.
            materialized.append({
                "candidate_key": key, "source_ordinal": index, "pool": pool,
                "game_uid": str(row["game_uid"]), "opening_id": str(row["opening_id"]),
                "ply": int(row["ply"]), "fen": str(row["fen"]),
                "exact_state_key": str(row["exact_state_key"]),
                "historical_action": actual_apply,
                "legal_actions": sorted(move.jass_apply_str() for move in legal),
                "structural": structural,
            })
    finally:
        referee.close()
    selected=[]; by_opening=Counter(); by_game=Counter(); canonical=set()
    for row in sorted(materialized, key=lambda item: (item["candidate_key"], item["source_ordinal"])):
        if by_opening[(row["pool"], row["opening_id"])] >= MAX_CANDIDATES_PER_OPENING:
            continue
        if by_game[row["game_uid"]] >= MAX_CANDIDATES_PER_GAME:
            continue
        if row["exact_state_key"] in canonical:
            continue
        selected.append(row); by_opening[(row["pool"], row["opening_id"])] += 1
        by_game[row["game_uid"]] += 1; canonical.add(row["exact_state_key"])
    selected.sort(key=lambda item: (item["pool"], item["opening_id"], item["candidate_key"]))
    pools = {str(pool): sum(int(row["pool"]) == pool for row in selected) for pool in (1, 2)}
    opening_counts = {str(pool): len({row["opening_id"] for row in selected if row["pool"] == pool}) for pool in (1, 2)}
    if min(opening_counts.values()) < MIN_SELECTED_PER_POOL:
        raise ValueError(f"target-blind candidate support too small: {opening_counts}")
    return {
        "schema": SCHEMA_CANDIDATES, "seed": seed,
        "selection_sha256": _digest(selection), "transitions_sha256": _digest(transitions),
        "source_summary_sha256": _digest(source_summary), "preregistration_sha256": _digest(prereg),
        "selection_blinded_to": ["outcome", "terminal score", "deep teacher", "deep score", "regret"],
        "candidate_inputs": ["phase", "piece_count", "king_count", "capture_or_quiet", "legal_action_count", "deterministic_hash"],
        "candidate_count": len(selected), "candidates_by_pool": pools,
        "openings_by_pool": opening_counts, "per_opening_cap": MAX_CANDIDATES_PER_OPENING,
        "per_game_cap": MAX_CANDIDATES_PER_GAME, "canonical_unique": len(canonical) == len(selected),
        "candidates": selected, "deep_target_computations": 0,
        "fits": 0, "strength_games": 0, "frozen_reads": 0, "promotion_authorized": False,
    }


def _rank(trace: dict[str, Any], depth: int, *, image: bool) -> list[str]:
    rows = trace["depths"][str(depth)]["moves"]
    values = {
        atlas._mapped_image_action(str(row["action"])) if image else str(row["action"]): int(row["score"])
        for row in rows
    }
    return sorted(values, key=lambda action: (values[action], action), reverse=True)


def _instability(original: dict[str, Any], image: dict[str, Any], actual: str) -> dict[str, Any]:
    original_best = [str(original["depths"][str(depth)]["best_action"]) for depth in range(6, 10)]
    image_best = [atlas._mapped_image_action(str(image["depths"][str(depth)]["best_action"])) for depth in range(6, 10)]
    flips = sum(a != b for values in (original_best, image_best) for a, b in zip(values, values[1:]))
    disagreement = sum(a != b for a, b in zip(original_best, image_best, strict=True))
    ranks = []
    for trace, is_image in ((original, False), (image, True)):
        for depth in range(6, 10):
            ordered = _rank(trace, depth, image=is_image)
            ranks.append(ordered.index(actual) / max(len(ordered) - 1, 1))
    scores = [int(original["depths"][str(depth)]["score"]) for depth in range(6, 10)]
    scores += [-int(image["depths"][str(depth)]["score"]) for depth in range(6, 10)]
    volatility = max((abs(b - a) for a, b in zip(scores, scores[1:])), default=0)
    margins=[]
    for trace in (original, image):
        value=trace["depths"]["9"]["root_margin_proxy_cp"]
        margins.append(10_000.0 if value is None else float(value))
    score = 8.0 * flips + 5.0 * disagreement + 4.0 * float(np.mean(ranks))
    score += min(volatility, 400) / 50.0 + max(0.0, 100.0 - min(margins)) / 25.0
    return {
        "score": score, "depth_flips": flips, "orientation_disagreements": disagreement,
        "historical_mean_rank_fraction": float(np.mean(ranks)),
        "score_volatility_cp": volatility, "minimum_d9_margin_cp": min(margins),
        "uses_depths": [6, 7, 8, 9], "uses_deep_targets": False,
    }


def profile_shard(args: argparse.Namespace) -> dict[str, Any]:
    candidates=json.loads(args.candidates.read_text(encoding="utf-8"))
    if candidates.get("schema") != SCHEMA_CANDIDATES:
        raise ValueError("candidate schema drift")
    if not 0 <= args.shard < args.nshards:
        raise ValueError("invalid profile shard")
    os.environ["JASS_TRACE_ROOT"]="1"
    spec=args.search_params.read_text(encoding="utf-8").strip()
    engine=cv.JassEngine(str(args.jass),label=f"loss-first-profile-s{args.shard}",pattern_path=str(args.champion),search_params=spec)
    rows=[]
    try:
        for candidate in candidates["candidates"]:
            if int(candidate["source_ordinal"]) % args.nshards != args.shard:
                continue
            fen=str(candidate["fen"]); image_fen=ctx.exact_image_fen(fen)
            original=atlas._trace_search(engine,fen,PROFILE_DEPTH)
            image=atlas._trace_search(engine,image_fen,PROFILE_DEPTH)
            legal=set(candidate["legal_actions"])
            if set(_rank(original,PROFILE_DEPTH,image=False)) != legal:
                raise ValueError("original shallow legal action set drift")
            if set(_rank(image,PROFILE_DEPTH,image=True)) != legal:
                raise ValueError("image shallow legal action set drift")
            rows.append({
                "candidate_key":candidate["candidate_key"], "source_ordinal":candidate["source_ordinal"],
                "pool":candidate["pool"], "opening_id":candidate["opening_id"],
                "game_uid":candidate["game_uid"], "exact_state_key":candidate["exact_state_key"],
                "fen":fen, "historical_action":candidate["historical_action"],
                "legal_actions":candidate["legal_actions"], "structural":candidate["structural"],
                "shallow_trace":{"original":original,"exact_image":image},
                "instability":_instability(original,image,str(candidate["historical_action"])),
            })
    finally:
        engine.close()
    return {
        "schema":SCHEMA_PROFILE_SHARD,"shard":args.shard,"nshards":args.nshards,
        "candidates_sha256":sha256(args.candidates),"champion_sha256":sha256(args.champion),
        "jass_sha256":sha256(args.jass),"search_params_sha256":sha256(args.search_params),
        "profile_depth":PROFILE_DEPTH,"rows":rows,"deep_target_computations":0,
        "fits":0,"strength_games":0,"frozen_reads":0,"promotion_authorized":False,
    }


def combine_profiles(candidates: dict[str, Any], shards: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    if candidates.get("schema") != SCHEMA_CANDIDATES:
        raise ValueError("candidate schema drift")
    if len(shards) != 16 or {int(row.get("shard",-1)) for row in shards} != set(range(16)):
        raise ValueError("profile shards incomplete")
    expected=_digest(candidates)
    if any(row.get("schema") != SCHEMA_PROFILE_SHARD or row.get("candidates_sha256") != expected for row in shards):
        raise ValueError("profile shard identity drift")
    identities={key:{str(row.get(key,"")) for row in shards} for key in ("champion_sha256","jass_sha256","search_params_sha256")}
    if any(len(values)!=1 or not next(iter(values)) for values in identities.values()):
        raise ValueError("profile engine/model identity drift")
    rows=[item for shard in shards for item in shard["rows"]]
    if len(rows)!=int(candidates["candidate_count"]) or len({row["candidate_key"] for row in rows})!=len(rows):
        raise ValueError("profile candidate coverage drift")
    grouped=defaultdict(list)
    for row in rows: grouped[(int(row["pool"]),str(row["opening_id"]))].append(row)
    selected=[]
    for key,choices in sorted(grouped.items()):
        choices.sort(key=lambda row:(-float(row["instability"]["score"]),hashlib.sha256(f"{seed}|{row['candidate_key']}".encode()).hexdigest()))
        selected.append(choices[0])
    selected.sort(key=lambda row:(int(row["pool"]),str(row["opening_id"])))
    by_pool={str(pool):sum(int(row["pool"])==pool for row in selected) for pool in (1,2)}
    if min(by_pool.values())<MIN_SELECTED_PER_POOL:
        raise ValueError(f"profile selection support too small: {by_pool}")
    if len({row["opening_id"] for row in selected})!=len(selected):
        raise ValueError("opening ids unexpectedly overlap across pools")
    if len({row["exact_state_key"] for row in selected})!=len(selected):
        raise ValueError("selected canonical states are not unique")
    for ordinal,row in enumerate(selected): row["label_ordinal"]=ordinal
    return {
        "schema":SCHEMA_SELECTION,"seed":seed,"candidates_sha256":_digest(candidates),
        **{key:next(iter(values)) for key,values in identities.items()},
        "selection_rule":"one maximum shallow-instability state per opening",
        "selection_blinded_to":["outcome","terminal score","deep teacher","deep score","regret"],
        "selected":len(selected),"selected_by_pool":by_pool,
        "one_state_per_opening":True,"per_game_cap":MAX_CANDIDATES_PER_GAME,
        "canonical_unique":True,"rows":selected,"deep_target_computations":0,
        "fits":0,"strength_games":0,"frozen_reads":0,"promotion_authorized":False,
    }


def _wdl(score: float) -> int:
    return 1 if score > DRAW_BAND_CP else -1 if score < -DRAW_BAND_CP else 0


def _rank_values(values: dict[str,float]) -> list[str]:
    return sorted(values,key=lambda action:(values[action],action),reverse=True)


def _mean_vectors(left: dict[int,float],right: dict[int,float]) -> dict[int,float]:
    return {key:(left.get(key,0.0)+right.get(key,0.0))/2.0 for key in set(left)|set(right) if abs(left.get(key,0.0)+right.get(key,0.0))>1e-15}


def _subtract(left: dict[int,float],right: dict[int,float],*,sign:float) -> dict[int,float]:
    return {key:sign*(left.get(key,0.0)-right.get(key,0.0)) for key in set(left)|set(right) if abs(left.get(key,0.0)-right.get(key,0.0))>1e-15}


def _root_sign(fen: str) -> float:
    return 1.0 if fen.split(":",1)[0]=="B" else -1.0


def _search_leaf(engine: Any, fen: str, depth: int) -> dict[str,Any]:
    _move,result=ctx._search(engine,fen,depth)
    if int(result.get("depth",-1))!=depth:
        raise ValueError("fixed-depth search did not complete requested depth")
    leaf=result.get("pv_leaf_fen")
    if not isinstance(leaf,str) or not leaf:
        raise ValueError("instrumented search did not publish pv_leaf_fen")
    learning._fen_bits(leaf)
    return result


def _label_state(row: dict[str,Any],*,engine:Any,referee:Any,extractor:ExactFeatureExtractor) -> dict[str,Any]:
    fen=str(row["fen"]); image_fen=ctx.exact_image_fen(fen); actions=list(row["legal_actions"])
    shallow_original={
        str(item["action"]):float(item["score"])
        for item in row["shallow_trace"]["original"]["depths"]["9"]["moves"]
    }
    shallow_image={
        atlas._mapped_image_action(str(item["action"])):float(item["score"])
        for item in row["shallow_trace"]["exact_image"]["depths"]["9"]["moves"]
    }
    if set(shallow_original)!=set(actions) or set(shallow_image)!=set(actions):
        raise ValueError("shallow action values do not cover all legal siblings")
    shallow_symmetrised={
        action:(shallow_original[action]+shallow_image[action])/2.0
        for action in actions
    }
    by_depth={}; vectors={}
    for depth in TEACHER_DEPTHS:
        original_values={}; image_values={}; search_rows={}
        for action in actions:
            move=atlas._parse_action(action); image_action=atlas._image_move(move)
            child=ctx._child_fen(referee,fen,move); image_child=ctx._child_fen(referee,image_fen,image_action)
            if learning._fen_bits(image_child)!=learning._fen_bits(ctx.exact_image_fen(child)):
                raise ValueError("deep label exact-image child commutation failed")
            original=_search_leaf(engine,child,depth); image=_search_leaf(engine,image_child,depth)
            original_values[action]=-float(original["score"]); image_values[action]=-float(image["score"])
            search_rows[action]={"child_original":child,"child_exact_image":image_child,"original":original,"exact_image":image}
            if depth==12:
                ov,_=extractor.vector(str(original["pv_leaf_fen"])); iv,_=extractor.vector(str(image["pv_leaf_fen"]))
                vectors[action]={"original":ov,"exact_image":iv}
        original_rank=_rank_values(original_values); image_rank=_rank_values(image_values)
        symm={action:(original_values[action]+image_values[action])/2.0 for action in actions}
        by_depth[str(depth)]={
            "original_values_cp":original_values,"exact_image_values_cp":image_values,
            "symmetrised_values_cp":symm,"original_rank":original_rank,"mapped_image_rank":image_rank,
            "symmetry_order_agreement":original_rank==image_rank,
            "wdl":{action:_wdl(symm[action]) for action in actions},"search":search_rows,
        }
    d10,d12=by_depth["10"],by_depth["12"]
    teacher10=_rank_values(d10["symmetrised_values_cp"])[0]; teacher12=_rank_values(d12["symmetrised_values_cp"])[0]
    depth_top_agreement=teacher10==teacher12
    wdl_agreement=d10["wdl"]==d12["wdl"]
    symmetry_agreement=bool(d10["symmetry_order_agreement"] and d12["symmetry_order_agreement"])
    accepted=depth_top_agreement and wdl_agreement and symmetry_agreement
    historical=str(row["historical_action"])
    if historical not in actions: raise ValueError("historical action absent from legal siblings")
    regrets={depth:max(by_depth[str(depth)]["symmetrised_values_cp"].values())-by_depth[str(depth)]["symmetrised_values_cp"][historical] for depth in TEACHER_DEPTHS}
    label="unstable"
    if accepted and historical!=teacher12 and min(regrets.values())>=MIN_STABLE_ERROR_CP: label="error"
    elif accepted and (historical==teacher12 or max(regrets.values())<=MAX_STABLE_CONTROL_CP): label="control"
    comparisons=[]
    if accepted:
        teacher_vectors=vectors[teacher12]
        for sibling in actions:
            if sibling==teacher12: continue
            original_gradient=_subtract(teacher_vectors["original"],vectors[sibling]["original"],sign=_root_sign(fen))
            image_gradient=_subtract(teacher_vectors["exact_image"],vectors[sibling]["exact_image"],sign=_root_sign(image_fen))
            gradient=_mean_vectors(original_gradient,image_gradient)
            margin=max(0.0,float(d12["symmetrised_values_cp"][teacher12])-float(d12["symmetrised_values_cp"][sibling]))
            comparisons.append({
                "teacher":teacher12,"sibling":sibling,"teacher_margin_cp":margin,
                "bounded_margin_cp":min(MARGIN_CAP_CP,margin),
                "baseline_shallow_margin_cp":shallow_symmetrised[teacher12]-shallow_symmetrised[sibling],
                "baseline_original_margin_cp":shallow_original[teacher12]-shallow_original[sibling],
                "baseline_exact_image_margin_cp":shallow_image[teacher12]-shallow_image[sibling],
                "pair_weight":1.0/max(len(actions)-1,1),
                "original_gradient":{str(key):value for key,value in sorted(original_gradient.items())},
                "exact_image_gradient":{str(key):value for key,value in sorted(image_gradient.items())},
                "gradient":{str(key):value for key,value in sorted(gradient.items())},
            })
    listwise={action:max(-MARGIN_CAP_CP,min(0.0,float(d12["symmetrised_values_cp"][action])-max(d12["symmetrised_values_cp"].values()))) for action in actions}
    return {
        "label_ordinal":row["label_ordinal"],"pool":row["pool"],"opening_id":row["opening_id"],
        "game_uid":row["game_uid"],"exact_state_key":row["exact_state_key"],"fen":fen,
        "historical_action":historical,"structural":row["structural"],"instability":row["instability"],
        "legal_actions":actions,"teacher_action":teacher12 if accepted else None,
        "baseline_shallow_scores_cp":{
            "original":shallow_original,"exact_image":shallow_image,
            "symmetrised":shallow_symmetrised,
        },
        "accepted":accepted,"label":label,"depth_top_agreement":depth_top_agreement,
        "wdl_ordering_agreement":wdl_agreement,"symmetry_ordering_agreement":symmetry_agreement,
        "fixed_depth_exact":True,"regret_cp_by_depth":{str(k):v for k,v in regrets.items()},
        "listwise_bounded_utility":listwise,"comparisons":comparisons,
        "per_state_total_loss_mass":1.0,"per_opening_total_loss_mass":1.0,
        "teacher_depths":list(TEACHER_DEPTHS),"teacher_details":by_depth,
    }


def label_shard(args: argparse.Namespace) -> dict[str,Any]:
    selection=json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("schema")!=SCHEMA_SELECTION: raise ValueError("loss-first selection schema drift")
    if not 0<=args.shard<args.nshards: raise ValueError("invalid label shard")
    spec=args.search_params.read_text(encoding="utf-8").strip(); os.environ["JASS_TRACE_ROOT"]="0"
    engine=cv.JassEngine(str(args.jass),label=f"loss-first-label-s{args.shard}",pattern_path=str(args.champion),search_params=spec)
    referee=cv.Referee(str(args.jass)); extractor=ExactFeatureExtractor(); rows=[]
    try:
        selected_rows=[
            row for row in selection["rows"]
            if int(row["label_ordinal"])%args.nshards==args.shard
        ]
        if args.max_rows:
            selected_rows=selected_rows[:args.max_rows]
        for row in selected_rows:
            rows.append(_label_state(row,engine=engine,referee=referee,extractor=extractor))
    finally:
        engine.close(); referee.close()
    return {
        "schema":SCHEMA_LABEL_SHARD,"shard":args.shard,"nshards":args.nshards,
        "selection_sha256":sha256(args.selection),"champion_sha256":sha256(args.champion),
        "jass_sha256":sha256(args.jass),"search_params_sha256":sha256(args.search_params),
        "teacher_depths":list(TEACHER_DEPTHS),"draw_band_cp":DRAW_BAND_CP,
        "margin_cap_cp":MARGIN_CAP_CP,"max_rows":args.max_rows,
        "rows":rows,"diagnostic_label_computations":len(rows),
        "fits":0,"strength_games":0,"frozen_reads":0,"promotion_authorized":False,
    }


def _match(rows: list[dict[str,Any]], *, seed: int) -> list[dict[str,Any]]:
    errors=defaultdict(list); controls=defaultdict(list)
    for row in rows:
        structural=row["structural"]
        key=(int(row["pool"]),structural["phase"],structural["kings"],structural["tactical"],structural["branching_bin"])
        if row["label"]=="error": errors[key].append(row)
        elif row["label"]=="control": controls[key].append(row)
    pairs=[]
    for key in sorted(set(errors)|set(controls)):
        order=lambda row:hashlib.sha256(f"{seed}|{key}|{row['exact_state_key']}".encode()).hexdigest()
        left=sorted(errors[key],key=order); right=sorted(controls[key],key=order)
        for error,control in zip(left,right):
            if error["opening_id"]==control["opening_id"] or error["game_uid"]==control["game_uid"]:
                raise ValueError("matched error/control component leakage")
            pairs.append({"pair_id":len(pairs),"pool":key[0],"matching_stratum":"|".join(map(str,key[1:])),"error":error,"control":control})
    return pairs


def aggregate(selection: dict[str,Any], shards: list[dict[str,Any]], *, match_seed: int) -> tuple[dict[str,Any],dict[str,Any]]:
    if selection.get("schema")!=SCHEMA_SELECTION: raise ValueError("selection schema drift")
    if len(shards)!=16 or {int(row.get("shard",-1)) for row in shards}!=set(range(16)):
        raise ValueError("label shards incomplete")
    expected=_digest(selection)
    if any(
        row.get("schema")!=SCHEMA_LABEL_SHARD
        or row.get("selection_sha256")!=expected
        or int(row.get("max_rows",-1))!=0
        for row in shards
    ):
        raise ValueError("label shard identity drift")
    identities={key:{str(row.get(key,"")) for row in shards} for key in ("champion_sha256","jass_sha256","search_params_sha256")}
    if any(len(values)!=1 or not next(iter(values)) for values in identities.values()): raise ValueError("label identity drift")
    rows=[item for shard in shards for item in shard["rows"]]; rows.sort(key=lambda row:int(row["label_ordinal"]))
    if [int(row["label_ordinal"]) for row in rows]!=list(range(int(selection["selected"]))):
        raise ValueError("label row coverage drift")
    pairs=_match(rows,seed=match_seed); matched={str(pool):sum(int(pair["pool"])==pool for pair in pairs) for pool in (1,2)}
    counts={str(pool):dict(Counter(row["label"] for row in rows if int(row["pool"])==pool)) for pool in (1,2)}
    passed=min(matched.values())>=MIN_MATCHED_PER_POOL
    report={
        "schema":SCHEMA_LABELS,"verdict":READY if passed else NOT_ESTABLISHED,"passed":passed,
        **{key:next(iter(values)) for key,values in identities.items()},
        "selection_sha256":_digest(selection),"label_shard_sha256":[_digest(shard) for shard in shards],
        "selected_states":len(rows),"labels_by_pool":counts,"matched_pairs_by_pool":matched,
        "matched_pairs":len(pairs),"matching_without_replacement":True,
        "matching_strata":"pool x phase x kings x capture_or_quiet x branching_bin",
        "opening_game_canonical_overlap":0,"teacher_depths":list(TEACHER_DEPTHS),
        "margin_cap_cp":MARGIN_CAP_CP,"raw_cp_mean":"diagnostic_only",
        "all_accepted_labels_depth_wdl_symmetry_stable":all(
            row["depth_top_agreement"] and row["wdl_ordering_agreement"] and row["symmetry_ordering_agreement"]
            for row in rows if row["accepted"]
        ),
        "pattern_eval_fits":0,"production_model_fits":0,"strength_games":0,"new_selfplay_games":0,
        "frozen_reads":0,"anchored_local_refit_authorized":False,"production_model_authorized":False,
        "strength_gate_authorized":False,"promotion_authorized":False,"automatic_continuation":False,
        "next_stage":"loss_first_sparse_jacobian_crossfit_screen" if passed else None,
    }
    pair_payload={
        "schema":"jass.l3_curriculum_error_loss_first_matched_pairs.v1",
        "source_verdict":report["verdict"],"match_seed":match_seed,"pairs":pairs,
        "opening_game_canonical_overlap":0,"fits":0,"strength_games":0,"promotion_authorized":False,
    }
    return report,pair_payload


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(description=__doc__); sub=root.add_subparsers(dest="command",required=True)
    cand=sub.add_parser("candidates"); cand.add_argument("--selection",type=Path,required=True); cand.add_argument("--transitions",type=Path,required=True)
    cand.add_argument("--source-summary",type=Path,required=True); cand.add_argument("--preregistration",type=Path,required=True)
    cand.add_argument("--jass",type=Path,required=True); cand.add_argument("--seed",type=int,default=2026082343); cand.add_argument("--out",type=Path,required=True)
    prof=sub.add_parser("profile-worker"); prof.add_argument("--candidates",type=Path,required=True); prof.add_argument("--jass",type=Path,required=True)
    prof.add_argument("--champion",type=Path,required=True); prof.add_argument("--search-params",type=Path,required=True)
    prof.add_argument("--shard",type=int,required=True); prof.add_argument("--nshards",type=int,default=16); prof.add_argument("--out",type=Path,required=True)
    choose=sub.add_parser("select"); choose.add_argument("--candidates",type=Path,required=True); choose.add_argument("--profile-shard",action="append",type=Path,required=True)
    choose.add_argument("--seed",type=int,default=2026082343); choose.add_argument("--out",type=Path,required=True)
    label=sub.add_parser("label-worker"); label.add_argument("--selection",type=Path,required=True); label.add_argument("--jass",type=Path,required=True)
    label.add_argument("--champion",type=Path,required=True); label.add_argument("--search-params",type=Path,required=True)
    label.add_argument("--shard",type=int,required=True); label.add_argument("--nshards",type=int,default=16)
    label.add_argument("--max-rows",type=int,default=0); label.add_argument("--out",type=Path,required=True)
    agg=sub.add_parser("aggregate"); agg.add_argument("--selection",type=Path,required=True); agg.add_argument("--label-shard",action="append",type=Path,required=True)
    agg.add_argument("--match-seed",type=int,default=2026082344); agg.add_argument("--report",type=Path,required=True); agg.add_argument("--pairs",type=Path,required=True)
    return root


def main() -> int:
    args=parser().parse_args()
    if args.command=="candidates":
        payload=build_candidates(json.loads(args.selection.read_text()),json.loads(args.transitions.read_text()),json.loads(args.source_summary.read_text()),json.loads(args.preregistration.read_text()),jass=str(args.jass),seed=args.seed); _publish(args.out,payload)
    elif args.command=="profile-worker": _publish(args.out,profile_shard(args))
    elif args.command=="select": _publish(args.out,combine_profiles(json.loads(args.candidates.read_text()),[json.loads(path.read_text()) for path in args.profile_shard],seed=args.seed))
    elif args.command=="label-worker": _publish(args.out,label_shard(args))
    else:
        report,pairs=aggregate(json.loads(args.selection.read_text()),[json.loads(path.read_text()) for path in args.label_shard],match_seed=args.match_seed); _publish(args.report,report); _publish(args.pairs,pairs)
    return 0


if __name__=="__main__": raise SystemExit(main())
