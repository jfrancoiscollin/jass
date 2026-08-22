#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fresh, leakage-safe action-level residual ranker screen for CURRICULUM.

The scalar PatternEval and fixed root-slope routes are closed.  This tool fits
only a diagnostic linear residual over legal actions at one root.  CURRICULUM
and its d9 score remain the anchor.  The learned correction is bounded, uses
only completed d6..d9 root traces, and is evaluated out of opening/exact-state
components.  A PASS authorizes implementation work, never promotion.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import l3_curriculum_search_error_atlas as source
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_search_error_atlas as source  # type: ignore


SCHEMA = "jass.l3_curriculum_error_action_ranker_screen.v1"
MODEL_SCHEMA = "jass.l3_curriculum_error_action_ranker.v1"
FEATURE_DEPTHS = (6, 7, 8, 9)
RIDGE_ALPHAS = (1.0, 10.0, 100.0)
ADVANTAGE_THRESHOLDS_CP = (25.0, 50.0, 100.0)
MARGIN_BANDS_CP = (50.0, 100.0, 200.0)
CORRECTION_CAP_CP = 75.0
SCORE_CLIP_CP = 400.0
SLOPE_CLIP_CP = 200.0
SHAM_REPLICATES = 100

FEATURE_NAMES = tuple(
    [f"centered_score_d{depth}" for depth in FEATURE_DEPTHS]
    + [f"present_d{depth}" for depth in FEATURE_DEPTHS]
    + [f"rank_fraction_d{depth}" for depth in FEATURE_DEPTHS]
    + ["slope_d6_d7", "slope_d7_d8", "slope_d8_d9"]
    + ["curvature_d7_d9", "trajectory_volatility", "top_frequency"]
    + ["capture", "baseline_d9"]
)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp." + hashlib.sha256(_canonical(value)).hexdigest()[:12])
    tmp.write_bytes(_canonical(value))
    tmp.replace(path)


def _bootstrap(values: Iterable[float], *, samples: int, seed: int) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size == 0:
        return {"n": 0, "mean": None, "ci95": [None, None], "probability_positive": None}
    rng = np.random.default_rng(seed)
    means = array[rng.integers(0, array.size, size=(samples, array.size))].mean(axis=1)
    return {
        "n": int(array.size), "mean": float(array.mean()),
        "ci95": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
        "probability_positive": float(np.mean(means > 0.0)),
    }


def _sign_flip(values: list[float], *, samples: int, seed: int) -> float:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return 1.0
    observed = abs(float(array.mean()))
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(samples):
        signs = rng.choice(np.asarray([-1.0, 1.0]), size=array.size)
        extreme += abs(float(np.mean(array * signs))) >= observed
    return (extreme + 1.0) / (samples + 1.0)


def _load_source(
    pairs: dict[str, Any], shards: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, str], dict[str, Any]]:
    if pairs.get("schema") != source.SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("action ranker requires passed fresh matching")
    expected = len(shards)
    if expected != 16 or {int(row.get("shard", -1)) for row in shards} != set(range(expected)):
        raise ValueError("fresh action atlas shards incomplete")
    if any(row.get("schema") != source.SCHEMA_ATLAS_SHARD for row in shards):
        raise ValueError("fresh action atlas shard schema drift")
    if any(int(row.get("nshards", -1)) != expected or int(row.get("max_pairs", -1)) != 0 for row in shards):
        raise ValueError("fresh action atlas execution drift")
    digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    if any(row.get("pairs_sha256") != digest for row in shards):
        raise ValueError("fresh action atlas pair hash drift")
    identities: dict[str, str] = {}
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        values = {str(row.get(key, "")) for row in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"fresh action atlas {key} identity drift")
        identities[key] = next(iter(values))
    atlas_rows = [item for shard in shards for item in shard["rows"]]
    atlas_rows.sort(key=lambda row: int(row["pair_id"]))
    matched_rows = sorted(pairs["pairs"], key=lambda row: int(row["pair_id"]))
    expected_ids = list(range(int(pairs["matched_pairs"])))
    if [int(row["pair_id"]) for row in atlas_rows] != expected_ids:
        raise ValueError("fresh action atlas pair coverage drift")
    if [int(row["pair_id"]) for row in matched_rows] != expected_ids:
        raise ValueError("fresh action matched pair coverage drift")
    split_names = ("discovery", "confirm")
    unknown_splits = sorted(
        {str(row.get("split", "")) for row in matched_rows} - set(split_names)
    )
    if unknown_splits:
        raise ValueError(f"fresh action matched pair split drift: {unknown_splits}")
    matched = {int(row["pair_id"]): row for row in matched_rows}
    judged = {int(row["pair_id"]): row for row in atlas_rows}
    counts = {
        "matched_pairs": int(pairs["matched_pairs"]),
        "pairs_by_split": {
            key: len([row for row in matched_rows if row.get("split") == key])
            for key in split_names
        },
        "informative_errors_by_split": {}, "reclassified_by_split": {},
    }
    return matched, judged, identities, counts


def _join_split(
    matched: dict[int, dict[str, Any]], judged: dict[int, dict[str, Any]], *, split: str
) -> tuple[list[dict[str, Any]], int]:
    """Dereference decision payloads for exactly one already-sealed split."""
    rows=[]; reclassified=0
    ids=[pair_id for pair_id,row in matched.items() if row.get("split")==split]
    for pair_id in sorted(ids):
        raw,exact=matched[pair_id],judged[pair_id]
        if float(exact["error"]["historical_regret_cp"])<50.0:
            reclassified+=1; continue
        rows.append({"pair_id":pair_id,
            "error":{"profile":raw["error"],"judged":exact["error"]},
            "control":{"profile":raw["control"],"judged":exact["control"]}})
    return rows,reclassified


def _components(rows: list[dict[str, Any]]) -> list[list[int]]:
    parent = {int(row["pair_id"]): int(row["pair_id"]) for row in rows}

    def find(value: int) -> int:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            nxt = parent[value]; parent[value] = root; value = nxt
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            low, high = sorted((a, b)); parent[high] = low

    owners: dict[tuple[str, str], int] = {}
    for pair in rows:
        pair_id = int(pair["pair_id"])
        for role in ("error", "control"):
            src = pair[role]["profile"]["source"]
            for kind, value in (("opening", src["opening_id"]), ("state", src["exact_state_key"])):
                key = (kind, str(value)); previous = owners.setdefault(key, pair_id); union(previous, pair_id)
    grouped: dict[int, list[int]] = defaultdict(list)
    for pair_id in parent:
        grouped[find(pair_id)].append(pair_id)
    return sorted((sorted(value) for value in grouped.values()), key=tuple)


def _inner_split(
    rows: list[dict[str, Any]], *, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validation: set[int] = set(); manifest = []
    for members in _components(rows):
        digest = hashlib.sha256(f"{seed}|{','.join(map(str, members))}".encode()).digest()
        split = "validation" if int.from_bytes(digest[:8], "big") % 4 == 0 else "fit"
        if split == "validation": validation.update(members)
        manifest.append({"members": members, "split": split})
    fit = [row for row in rows if int(row["pair_id"]) not in validation]
    holdout = [row for row in rows if int(row["pair_id"]) in validation]
    return fit, holdout, {
        "method": "paired_opening_exact_state_components_sha256_mod4",
        "seed": seed, "components": len(manifest), "fit_pairs": len(fit),
        "validation_pairs": len(holdout), "overlap": 0,
        "manifest_sha256": hashlib.sha256(_canonical(manifest)).hexdigest(),
    }


def _cv_folds(rows: list[dict[str, Any]], *, seed: int) -> dict[int, int]:
    folds: dict[int, int] = {}
    for members in _components(rows):
        digest = hashlib.sha256(f"{seed}|{','.join(map(str, members))}".encode()).digest()
        fold = int.from_bytes(digest[:8], "big") % 4
        for pair_id in members: folds[pair_id] = fold
    return folds


def _score_maps(profile: dict[str, Any], *, image: bool) -> dict[int, dict[str, float]]:
    orientation = "exact_image" if image else "original"
    result: dict[int, dict[str, float]] = {}
    for depth in FEATURE_DEPTHS:
        values: dict[str, float] = {}
        for row in profile["trace"][orientation]["depths"][str(depth)]["moves"]:
            action = str(row["action"])
            if image: action = source._mapped_image_action(action)
            if action in values: raise ValueError("duplicate root action after image mapping")
            values[action] = float(row["score"])
        result[depth] = values
    if not result[9]: raise ValueError("empty d9 root action set")
    return result


def _raw_features(profile: dict[str, Any], *, image: bool) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    maps = _score_maps(profile, image=image); actions = sorted(maps[9])
    ranks: dict[int, dict[str, int]] = {}
    for depth, values in maps.items():
        ordered = sorted(values, key=lambda action: (values[action], action), reverse=True)
        ranks[depth] = {action: index for index, action in enumerate(ordered)}
    best9 = max(maps[9].values())
    baseline = sorted(maps[9], key=lambda action: (maps[9][action], action), reverse=True)[0]
    features: dict[str, np.ndarray] = {}
    for action in actions:
        centered=[]; present=[]; rank_fraction=[]; trajectory=[]
        for depth in FEATURE_DEPTHS:
            values=maps[depth]; exists=action in values; present.append(float(exists))
            if exists:
                best=max(values.values()); value=values[action]
                centered.append(max(-SCORE_CLIP_CP, min(0.0, value-best))/100.0)
                rank_fraction.append(-float(ranks[depth][action])/max(len(values)-1,1))
                trajectory.append(value)
            else:
                centered.append(-SCORE_CLIP_CP/100.0); rank_fraction.append(-1.0); trajectory.append(np.nan)
        slopes=[]
        for left,right in zip(FEATURE_DEPTHS[:-1],FEATURE_DEPTHS[1:]):
            if action in maps[left] and action in maps[right]:
                value=maps[right][action]-maps[left][action]
                slopes.append(max(-SLOPE_CLIP_CP,min(SLOPE_CLIP_CP,value))/100.0)
            else: slopes.append(0.0)
        curvature=max(-2.0,min(2.0,slopes[2]-slopes[1]))
        finite=[value for value in trajectory if np.isfinite(value)]
        volatility=min(float(np.std(finite)) if len(finite)>1 else 0.0,SLOPE_CLIP_CP)/100.0
        top_frequency=float(sum(ranks[d].get(action,-1)==0 for d in FEATURE_DEPTHS))/len(FEATURE_DEPTHS)
        vector=np.asarray(centered+present+rank_fraction+slopes+[curvature,volatility,top_frequency,float('x' in action),float(action==baseline)],dtype=np.float64)
        if vector.size!=len(FEATURE_NAMES): raise AssertionError("feature width drift")
        features[action]=vector
    return features, {action: maps[9][action] for action in actions}


def _true_values(judged: dict[str, Any]) -> dict[str, float]:
    return {str(action): float(row["root_cp"]) for action,row in judged["action_values"].items()}


def _permuted_values(values: dict[str, float], *, seed: int, state_key: str) -> dict[str, float]:
    actions=sorted(values); payload=[values[action] for action in actions]
    digest=hashlib.sha256(f"{seed}|{state_key}".encode()).digest()
    rng=np.random.default_rng(int.from_bytes(digest[:8],"big")); rng.shuffle(payload)
    return dict(zip(actions,payload,strict=True))


def _states(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result=[]
    for pair in rows:
        for role in ("error","control"):
            entry=pair[role]; judged=entry["judged"]
            for image in (False,True):
                features,scores=_raw_features(entry["profile"],image=image)
                values=_true_values(judged)
                if set(features)!=set(values): raise ValueError("feature/judge legal action set drift")
                result.append({"pair_id":int(pair["pair_id"]),"role":role,"image":image,
                    "state_key":f"{pair['pair_id']}|{role}|{int(image)}", "features":features,
                    "scores":scores,"values":values,"teacher":str(judged["exact_teacher_action"])})
    return result


def _fit(rows: list[dict[str, Any]], *, alpha: float, sham_seed: int | None = None) -> dict[str, Any]:
    states=_states(rows); all_features=np.vstack([vector for state in states for vector in state["features"].values()])
    mean=all_features.mean(axis=0); scale=all_features.std(axis=0); scale[scale<1e-6]=1.0
    a=np.zeros((len(FEATURE_NAMES),len(FEATURE_NAMES))); b=np.zeros(len(FEATURE_NAMES)); total=0.0; comparisons=0
    for state in states:
        values=state["values"] if sham_seed is None else _permuted_values(state["values"],seed=sham_seed,state_key=state["state_key"])
        teacher=sorted(values,key=lambda action:(values[action],action),reverse=True)[0]
        others=[action for action in sorted(values) if action!=teacher]
        if not others: continue
        weight=1.0/len(others)
        for other in others:
            x=(state["features"][teacher]-state["features"][other])/scale
            judge_delta=values[teacher]-values[other]
            q00_delta=state["scores"][teacher]-state["scores"][other]
            y=judge_delta-q00_delta
            a+=weight*np.outer(x,x); b+=weight*x*y; total+=weight; comparisons+=1
    if total<=0: raise ValueError("ranker fit has zero comparisons")
    a=a/total+alpha*np.eye(len(FEATURE_NAMES)); b=b/total
    coef=np.linalg.solve(a,b)
    return {"schema":MODEL_SCHEMA,"feature_names":list(FEATURE_NAMES),"mean":mean.tolist(),
        "scale":scale.tolist(),"coef":coef.tolist(),"alpha":alpha,"correction_cap_cp":CORRECTION_CAP_CP,
        "states":len(states),"comparisons":comparisons,"coefficient_l2":float(np.linalg.norm(coef)),
        "sham_seed":sham_seed}


def _correction(model: dict[str, Any], vector: np.ndarray) -> float:
    mean=np.asarray(model["mean"]); scale=np.asarray(model["scale"]); coef=np.asarray(model["coef"])
    value=float(((vector-mean)/scale)@coef)
    return max(-CORRECTION_CAP_CP,min(CORRECTION_CAP_CP,value))


def _choose(entry: dict[str, Any], model: dict[str, Any], *, image: bool, threshold: float, margin_band: float) -> dict[str, Any]:
    features,scores=_raw_features(entry["profile"],image=image)
    ranked=sorted(scores,key=lambda action:(scores[action],action),reverse=True); baseline=ranked[0]
    margin=scores[ranked[0]]-scores[ranked[1]] if len(ranked)>1 else float("inf")
    corrected={action:scores[action]+_correction(model,features[action]) for action in scores}
    proposed=sorted(corrected,key=lambda action:(corrected[action],action),reverse=True)[0]
    predicted_advantage=corrected[proposed]-corrected[baseline]
    intervene=proposed!=baseline and margin<=margin_band and predicted_advantage>=threshold
    return {"baseline":baseline,"proposed":proposed,"chosen":proposed if intervene else baseline,
        "changed":intervene,"margin_cp":margin,"predicted_advantage_cp":predicted_advantage}


def _decision(entry: dict[str, Any], model: dict[str, Any], *, threshold: float, margin_band: float) -> dict[str, Any]:
    original=_choose(entry,model,image=False,threshold=threshold,margin_band=margin_band)
    image=_choose(entry,model,image=True,threshold=threshold,margin_band=margin_band)
    values=_true_values(entry["judged"]); teacher=str(entry["judged"]["exact_teacher_action"]); best=values[teacher]
    baseline=[best-values[original["baseline"]],best-values[image["baseline"]]]
    chosen=[best-values[original["chosen"]],best-values[image["chosen"]]]
    return {"baseline_mean_regret_cp":float(np.mean(baseline)),"candidate_mean_regret_cp":float(np.mean(chosen)),
        "improvement_cp":float(np.mean(baseline)-np.mean(chosen)),
        "baseline_error_50cp":float(np.mean([value>=50 for value in baseline])),
        "candidate_error_50cp":float(np.mean([value>=50 for value in chosen])),
        "baseline_teacher_hit":float(np.mean([original["baseline"]==teacher,image["baseline"]==teacher])),
        "candidate_teacher_hit":float(np.mean([original["chosen"]==teacher,image["chosen"]==teacher])),
        "baseline_symmetry":original["baseline"]==image["baseline"],"candidate_symmetry":original["chosen"]==image["chosen"],
        "changed_pair":original["changed"] or image["changed"],"changed_orientations":int(original["changed"])+int(image["changed"])}


def _evaluate(rows: list[dict[str, Any]], models: dict[int,dict[str,Any]] | dict[str,Any], *, threshold: float, margin_band: float, bootstrap_samples: int, bootstrap_seed: int) -> dict[str,Any]:
    decisions=[]
    for pair in rows:
        model=models[int(pair["pair_id"])] if isinstance(next(iter(models)),int) else models
        decisions.append({"pair_id":int(pair["pair_id"]),"error":_decision(pair["error"],model,threshold=threshold,margin_band=margin_band),
            "control":_decision(pair["control"],model,threshold=threshold,margin_band=margin_band)})
    error=[row["error"]["improvement_cp"] for row in decisions]; control=[row["control"]["improvement_cp"] for row in decisions]
    paired=[left-right for left,right in zip(error,control,strict=True)]
    error_rate=[row["error"]["baseline_error_50cp"]-row["error"]["candidate_error_50cp"] for row in decisions]
    teacher_gain=[row["error"]["candidate_teacher_hit"]-row["error"]["baseline_teacher_hit"] for row in decisions]
    rate=lambda role,key:float(np.mean([row[role][key] for row in decisions])) if decisions else 0.0
    return {"pairs":len(rows),"error_improvement":_bootstrap(error,samples=bootstrap_samples,seed=bootstrap_seed),
        "control_improvement":_bootstrap(control,samples=bootstrap_samples,seed=bootstrap_seed+1),
        "paired_error_minus_control":_bootstrap(paired,samples=bootstrap_samples,seed=bootstrap_seed+2),
        "error_rate_reduction":_bootstrap(error_rate,samples=bootstrap_samples,seed=bootstrap_seed+3),
        "teacher_hit_gain":_bootstrap(teacher_gain,samples=bootstrap_samples,seed=bootstrap_seed+4),
        "paired_sign_flip_pvalue":_sign_flip(paired,samples=min(bootstrap_samples,10000),seed=bootstrap_seed+5),
        "error_changed_pairs":sum(row["error"]["changed_pair"] for row in decisions),
        "control_changed_pairs":sum(row["control"]["changed_pair"] for row in decisions),
        "error_changed_orientations":sum(row["error"]["changed_orientations"] for row in decisions),
        "control_changed_orientations":sum(row["control"]["changed_orientations"] for row in decisions),
        "error_baseline_symmetry":rate("error","baseline_symmetry"),"error_candidate_symmetry":rate("error","candidate_symmetry"),
        "control_baseline_symmetry":rate("control","baseline_symmetry"),"control_candidate_symmetry":rate("control","candidate_symmetry")}


def _oof_models(rows: list[dict[str,Any]], *, alpha: float, folds: dict[int,int], sham_seed: int | None = None) -> dict[int,dict[str,Any]]:
    result={}
    for fold in range(4):
        train=[row for row in rows if folds[int(row["pair_id"])]!=fold]
        model=_fit(train,alpha=alpha,sham_seed=sham_seed)
        for row in rows:
            if folds[int(row["pair_id"])]==fold: result[int(row["pair_id"])]=model
    if set(result)!={int(row["pair_id"]) for row in rows}: raise ValueError("OOF model coverage drift")
    return result


def run(args: argparse.Namespace) -> tuple[dict[str,Any],dict[str,Any]]:
    pairs=json.loads(args.pairs.read_text()); shards=[json.loads(path.read_text()) for path in args.atlas_shard]
    matched,judged,identities,counts=_load_source(pairs,shards)
    discovery,reclassified_discovery=_join_split(matched,judged,split="discovery")
    counts["informative_errors_by_split"]["discovery"]=len(discovery)
    counts["reclassified_by_split"]["discovery"]=reclassified_discovery
    confirm: list[dict[str,Any]]=[]
    fit,validation,inner=_inner_split(discovery,seed=args.split_seed)
    support={"discovery":len(discovery),"inner_fit":len(fit),"inner_validation":len(validation),"outer_confirm":None}
    support_pass=len(fit)>=96 and len(validation)>=24
    candidates=[]; selected=None; validation_metrics=None; validation_gates={}; confirm_metrics=None; confirm_gates={}; final_model=None; sham=None
    if support_pass:
        folds=_cv_folds(fit,seed=args.cv_seed)
        for index,alpha in enumerate(RIDGE_ALPHAS):
            models=_oof_models(fit,alpha=alpha,folds=folds)
            for threshold in ADVANTAGE_THRESHOLDS_CP:
                for margin in MARGIN_BANDS_CP:
                    metrics=_evaluate(fit,models,threshold=threshold,margin_band=margin,bootstrap_samples=args.bootstrap_samples,bootstrap_seed=args.bootstrap_seed+index*1000+int(threshold+margin))
                    gates={"error_probability_positive_ge_0_90":metrics["error_improvement"]["probability_positive"]>=.90,
                        "paired_probability_positive_ge_0_90":metrics["paired_error_minus_control"]["probability_positive"]>=.90,
                        "controls_not_harmed_mean":metrics["control_improvement"]["mean"]>=-2.0,
                        "at_least_12_error_pairs_changed":metrics["error_changed_pairs"]>=12,
                        "candidate_symmetry_ge_0_70":metrics["error_candidate_symmetry"]>=.70,
                        "candidate_symmetry_not_worse":metrics["error_candidate_symmetry"]>=metrics["error_baseline_symmetry"]-.02}
                    score=float(metrics["paired_error_minus_control"]["mean"])+.5*float(metrics["error_improvement"]["mean"])+10*float(metrics["teacher_hit_gain"]["mean"])
                    candidates.append({"alpha":alpha,"advantage_threshold_cp":threshold,"margin_band_cp":margin,"oof":metrics,"oof_gates":gates,"oof_passed":all(gates.values()),"selection_score":score})
        passing=[row for row in candidates if row["oof_passed"]]; passing.sort(key=lambda row:(-row["selection_score"],row["alpha"],row["advantage_threshold_cp"],row["margin_band_cp"]))
        selected=passing[0] if passing else None
    if selected:
        alpha=float(selected["alpha"]); threshold=float(selected["advantage_threshold_cp"]); margin=float(selected["margin_band_cp"])
        folds=_cv_folds(fit,seed=args.cv_seed)
        sham_means=[]
        for index in range(SHAM_REPLICATES):
            models=_oof_models(fit,alpha=alpha,folds=folds,sham_seed=args.sham_seed+index)
            metrics=_evaluate(fit,models,threshold=threshold,margin_band=margin,bootstrap_samples=200,bootstrap_seed=args.sham_seed+1000+index)
            sham_means.append(float(metrics["paired_error_minus_control"]["mean"]))
        real=float(selected["oof"]["paired_error_minus_control"]["mean"]); q95=float(np.quantile(sham_means,.95))
        sham={"replicates":SHAM_REPLICATES,"seed":args.sham_seed,"real_paired_mean_cp":real,"sham_paired_mean_cp_q95":q95,"real_exceeds_sham_q95":real>q95}
        if sham["real_exceeds_sham_q95"]:
            model=_fit(fit,alpha=alpha)
            validation_metrics=_evaluate(validation,model,threshold=threshold,margin_band=margin,bootstrap_samples=args.bootstrap_samples,bootstrap_seed=args.bootstrap_seed+20000)
            validation_gates={"at_least_24_pairs":len(validation)>=24,"error_improvement_ci95_positive":validation_metrics["error_improvement"]["ci95"][0]>0,
                "paired_improvement_ci95_positive":validation_metrics["paired_error_minus_control"]["ci95"][0]>0,
                "controls_not_harmed_ci95":validation_metrics["control_improvement"]["ci95"][0]>=-2.0,
                "paired_sign_flip_p_le_0_025":validation_metrics["paired_sign_flip_pvalue"]<=.025,
                "at_least_6_error_pairs_changed":validation_metrics["error_changed_pairs"]>=6,
                "candidate_symmetry_ge_0_70":validation_metrics["error_candidate_symmetry"]>=.70,
                "candidate_symmetry_not_worse":validation_metrics["error_candidate_symmetry"]>=validation_metrics["error_baseline_symmetry"]-.02}
            if all(validation_gates.values()):
                # The confirm decision payloads are first dereferenced here,
                # after the rule and every hyperparameter are irreversibly fixed.
                confirm,reclassified_confirm=_join_split(matched,judged,split="confirm")
                counts["informative_errors_by_split"]["confirm"]=len(confirm)
                counts["reclassified_by_split"]["confirm"]=reclassified_confirm
                support["outer_confirm"]=len(confirm)
                final_model=_fit(discovery,alpha=alpha)
                confirm_metrics=_evaluate(confirm,final_model,threshold=threshold,margin_band=margin,bootstrap_samples=args.bootstrap_samples,bootstrap_seed=args.bootstrap_seed+30000)
                confirm_gates={"at_least_96_pairs":len(confirm)>=96,"error_improvement_ci95_positive":confirm_metrics["error_improvement"]["ci95"][0]>0,
                    "paired_improvement_ci95_positive":confirm_metrics["paired_error_minus_control"]["ci95"][0]>0,
                    "controls_not_harmed_ci95":confirm_metrics["control_improvement"]["ci95"][0]>=-2.0,
                    "paired_sign_flip_p_le_0_025":confirm_metrics["paired_sign_flip_pvalue"]<=.025,
                    "at_least_12_error_pairs_changed":confirm_metrics["error_changed_pairs"]>=12,
                    "candidate_symmetry_ge_0_70":confirm_metrics["error_candidate_symmetry"]>=.70,
                    "candidate_symmetry_not_worse":confirm_metrics["error_candidate_symmetry"]>=confirm_metrics["error_baseline_symmetry"]-.02}
    passed=bool(final_model) and all(confirm_gates.values())
    outer_reads=len(confirm) if confirm_metrics is not None else 0
    report={"schema":SCHEMA,"verdict":"JASS_CURRICULUM_ERROR_ACTION_RANKER_OOF_READY" if passed else "JASS_CURRICULUM_ERROR_ACTION_RANKER_NOT_ESTABLISHED","passed":passed,**identities,
        "source_pairs_sha256":sha256(args.pairs),"source_atlas_shards":[{"path":str(path),"sha256":sha256(path)} for path in args.atlas_shard],
        "source_counts":counts,"support":support,"support_passed":support_pass,"inner_split":inner,
        "protocol":{"features":list(FEATURE_NAMES),"depths":list(FEATURE_DEPTHS),"ridge_alphas":list(RIDGE_ALPHAS),"advantage_thresholds_cp":list(ADVANTAGE_THRESHOLDS_CP),"margin_bands_cp":list(MARGIN_BANDS_CP),"correction_cap_cp":CORRECTION_CAP_CP,"sham_replicates":SHAM_REPLICATES,"anchor":"CURRICULUM_Q00_d9","additional_search_nodes":0},
        "candidates":candidates,"selected_candidate":selected,"sham":sham,"inner_validation":validation_metrics,"inner_validation_gates":validation_gates,
        "outer_confirm":confirm_metrics,"outer_confirm_gates":confirm_gates,"outer_confirm_pairs_read":outer_reads,
        "diagnostic_action_ranker_fits":(len(RIDGE_ALPHAS)*4+(SHAM_REPLICATES*4 if selected else 0)+(1 if validation_metrics else 0)+(1 if final_model else 0)),
        "pattern_eval_fits":0,"production_model_fits":0,"strength_games":0,"new_selfplay_games":0,"frozen_reads":0,
        "production_rule_authorized":False,"promotion_authorized":False,"automatic_continuation":False,
        "next_stage":"implement_bounded_action_ranker_for_oof_validation" if passed else None}
    model={"schema":MODEL_SCHEMA,"authorized_for_implementation":passed,"source_verdict":report["verdict"],
        "hyperparameters":({"alpha":selected["alpha"],"advantage_threshold_cp":selected["advantage_threshold_cp"],"margin_band_cp":selected["margin_band_cp"],"correction_cap_cp":CORRECTION_CAP_CP} if passed and selected else None),
        "model":final_model if passed else None,"champion_sha256":identities["champion_sha256"],"additional_search_nodes":0,
        "bit_identical_when_abstaining":True,"production_rule_authorized":False,"promotion_authorized":False}
    return report,model


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(description=__doc__); root.add_argument("--pairs",type=Path,required=True); root.add_argument("--atlas-shard",action="append",type=Path,required=True)
    root.add_argument("--report",type=Path,required=True); root.add_argument("--model",type=Path,required=True)
    root.add_argument("--split-seed",type=int,default=2026082235); root.add_argument("--cv-seed",type=int,default=2026082236)
    root.add_argument("--bootstrap-seed",type=int,default=2026082237); root.add_argument("--sham-seed",type=int,default=2026082238)
    root.add_argument("--bootstrap-samples",type=int,default=10000); return root


def main() -> int:
    args=parser().parse_args(); report,model=run(args); _publish(args.report,report); _publish(args.model,model)
    print(json.dumps({"verdict":report["verdict"],"selected":report["selected_candidate"],"outer_confirm_pairs_read":report["outer_confirm_pairs_read"]},sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
