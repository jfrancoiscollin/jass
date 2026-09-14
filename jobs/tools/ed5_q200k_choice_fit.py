#!/usr/bin/env python3
"""ED5 k=2 candidate fit using sealed TRAIN Q200k exact-max choice sets.

The optimization path is intentionally the ED4 path: same representation, WDL
replay, coefficients, ridge, trust-exact solver and quantization.  The only
scientific intervention is the already-sealed TRAIN admissible set A_p.
No ED5 confirmation target is fetched or read by this stage.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed2_preflight as ep
from jobs.tools import ed2_value_math as native
from jobs.tools import ed3_label_pressure as audit
from jobs.tools import ed4_choice_math as math
from jobs.tools import ed4_choice_value_fit as ed4fit
from jobs.tools import ed5_q200k_choice as qchoice
from jobs.tools import ed5_q200k_teacher_stage as teacher
from jobs.tools.ed3_soft_value_fit import unpack, write_records, run_probe, check_table
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES = ["authenticate", "verify-inputs", "native-base", "fit-choice-set", "serialize-and-reload", "seal-and-publish"]
TRAIN_PARENTS = teacher.TRAIN_PARENTS
TRAIN_ROWS = teacher.TRAIN_ROWS
REPLAY_N = ed4fit.REPLAY_N
CELL_QUOTA = teacher.CELL_QUOTA
MODEL_HASH = ed4fit.MODEL_HASH
RECIPE = ed4fit.RECIPE  # exact same object/bytes as ED4 scientific recipe
P0_NAMES = ed4fit.P0_NAMES
N1_NAMES = [
    "wdl-selection.json", "wdl-selection.seal.json", "replay.jnnw",
    "native/train-native.tsv.gz", "native/replay-native.tsv.gz",
    "build-outputs/jass_ed2_value_probe.gz", "scratch-cleanup.json",
]
TEACHER_ID = (
    "cpx62-1972-l3-ed5-q200k-train-teacher-production-v1",
    "20260914T180109Z-70225e9b",
    "70225e9b4a76b4998f2914eae563087a47d8383a",
)
TEACHER_NAMES = ["teacher-seal.json", "choice-sets.json"] + [f"train-q200k-{i}.jsonl" for i in range(teacher.WORKERS)]
MODEL_NAME = "ED5_Q200K_CHOICE.pjtw"
OUTPUTS = [MODEL_NAME, "beta.npy", "solver-diagnostic.json", "fit-report.json", "native-roundtrip.json", "train-contract.json", "candidate-seal.json"]


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def recipe_sha() -> str:
    return ed4fit.recipe_sha()


def solve_once(design):
    """One and only optimizer invocation for one ED5 fit execution."""
    return math.fit(design)


def validate_teacher_binding(root: Path, groups: list[dict]) -> tuple[list[dict], dict, int]:
    seal = audit.load_json(root / "teacher-seal.json")
    need(seal.get("schema") == "jass.ed5.q200k_teacher_seal.v1", "teacher_seal_schema")
    need(seal.get("role") == "train_teacher_only" and seal.get("mode") == "production", "teacher_seal_role")
    need(seal.get("source_seal_sha256") == audit.SOURCE_SEAL, "teacher_source_identity")
    need(seal.get("scan_sha256") == teacher.SCAN_SHA256 and seal.get("node_budget") == teacher.NODE_BUDGET, "teacher_scan_identity")
    need(seal.get("train_parents") == TRAIN_PARENTS and seal.get("train_rows") == TRAIN_ROWS, "teacher_train_shape")
    need(seal.get("confirmation_target_reads") == 0 and seal.get("candidate_reads") == 0 and seal.get("fits") == 0, "teacher_boundary")
    need(seal.get("alpha_spent") == 0.0 and seal.get("runtime_authorized") is False and seal.get("promotion_authorized") is False, "teacher_authorization_boundary")
    need(audit.sha(root / "choice-sets.json") == seal.get("choice_sets_sha256"), "choice_sets_hash")
    for name, digest in seal.get("teacher_files", {}).items():
        need(name in TEACHER_NAMES and audit.sha(root / name) == digest, "teacher_file_hash")
    need(set(seal.get("teacher_files", {})) == {f"train-q200k-{i}.jsonl" for i in range(teacher.WORKERS)}, "teacher_file_set")

    paths = [root / f"train-q200k-{i}.jsonl" for i in range(teacher.WORKERS)]
    high, calls = teacher.load_teacher(paths, groups)
    expected = qchoice.groups_from_q200k(groups, high)
    expected_payload = [
        {"parent_id": group["id"], "stm": group["stm"], "V": group["V"], "A": group["A"]}
        for group in expected
    ]
    stored = audit.load_json(root / "choice-sets.json")
    need(stored.get("schema") == "jass.ed5.q200k_choice_sets.v1" and stored.get("node_budget") == teacher.NODE_BUDGET, "choice_sets_schema")
    need(stored.get("parents") == expected_payload, "choice_sets_not_reproducible")
    need(calls == 4972, "teacher_scan_call_accounting")
    return expected, seal, calls


def load_inputs(roots: dict[str, Path], work: Path, mode: str):
    need(mode in ("rehearsal", "production"), "mode")
    p0, n1, base, target, teacher_root = (roots[k] for k in ("p0", "n1", "base", "target", "teacher"))
    need(audit.sha(p0 / "ed2-source-seal.json") == audit.SOURCE_SEAL, "p0_seal_identity")
    source = audit.load_json(p0 / "ed2-source-seal.json")
    for name in ("groups.tsv", "children.jnnw"):
        need(audit.sha(p0 / "source" / name) == source["files"][name], "source_bytes")
    groups = teacher.load_train_groups(p0 / "source")
    choices, teacher_seal, scan_calls = validate_teacher_binding(teacher_root, groups)

    x, z = audit.table(n1 / "native/train-native.tsv.gz", TRAIN_ROWS)
    rx, rz = audit.table(n1 / "native/replay-native.tsv.gz", REPLAY_N)
    children = ep.records(p0 / "source/children.jnnw")
    selection = audit.load_json(n1 / "wdl-selection.json")
    need(audit.load_json(n1 / "wdl-selection.seal.json")["sha256"] == audit.sha(n1 / "wdl-selection.json"), "wdl_selection_seal")
    selected = selection["subsets"]["replay"]
    ids = selected["indices"]
    need(len(ids) == REPLAY_N and all(type(i) is int for i in ids) and len(set(ids)) == REPLAY_N and min(ids) >= 0 and max(ids) < 1800796, "replay_indices")
    need(audit.sha(n1 / "replay.jnnw") == selected["data_sha256"], "replay_bytes")
    replay = ep.records(n1 / "replay.jnnw")
    need(len(replay) == REPLAY_N, "replay_count")

    unpack(target / "current_2m-context30.npy.gz", work / "targets.npy")
    targets = np.load(work / "targets.npy", mmap_mode="r", allow_pickle=False)
    need(targets.shape == (2000000,) and targets.dtype == np.float32, "target_layout")
    y = np.asarray(targets[ids], dtype=np.float64)
    need(np.isfinite(y).all() and ((0 <= y) & (y <= 1)).all(), "replay_values")

    unpack(base / "WDL_CONTROL.pjtw.gz", work / "BASE.pjtw")
    audit.weights(work / "BASE.pjtw", MODEL_HASH["BASE"])
    archive = n1 / "build-outputs/jass_ed2_value_probe.gz"
    receipt = audit.load_json(n1 / "scratch-cleanup.json")["retained_binaries"]["jass_ed2_value_probe"]
    need(audit.sha(archive) == receipt["archive_sha256"], "native_archive_identity")
    unpack(archive, work / "native-probe")
    need(audit.sha(work / "native-probe") == receipt["sha256"], "native_binary_identity")
    (work / "native-probe").chmod(0o500)

    row_ids = [r for group in groups for r in group["rows"]]
    mapping = {r: i for i, r in enumerate(row_ids)}
    need(len(mapping) == TRAIN_ROWS and all(type(r) is int and 0 <= r < len(children) for r in row_ids), "train_row_mapping")
    local = []
    for group in choices:
        local.append({
            "id": group["id"], "stm": group["stm"],
            "rows": [mapping[r] for r in group["rows"]],
            "V": [mapping[r] for r in group["V"]],
            "A": [mapping[r] for r in group["A"]],
            "edges": [],
        })
    design = math.design(x, z, local, rx, rz, y)
    write_records(work / "train.jnnw", [children[r] for r in row_ids])
    write_records(work / "replay.jnnw", replay)
    contract = {
        "schema": "jass.ed5.q200k_choice_train_contract.v1",
        "recipe": RECIPE,
        "recipe_sha256": recipe_sha(),
        "ed4_recipe_sha256": ed4fit.recipe_sha(),
        "source_seal_sha256": audit.SOURCE_SEAL,
        "teacher_identity": {"job_id": TEACHER_ID[0], "attempt_id": TEACHER_ID[1], "code_sha": TEACHER_ID[2]},
        "teacher_seal_sha256": audit.sha(teacher_root / "teacher-seal.json"),
        "choice_sets_sha256": audit.sha(teacher_root / "choice-sets.json"),
        "scan_sha256": teacher_seal["scan_sha256"],
        "teacher_scan_calls": scan_calls,
        "wdl_selection_sha256": audit.sha(n1 / "wdl-selection.json"),
        "controls_sha256": MODEL_HASH,
        "native_binary_sha256": receipt["sha256"],
        "fit_parents": len(groups),
        "parent_normalizer": len(groups),
        "train_rows": len(row_ids),
        "replay_rows": len(ids),
        "supported_parents": sum(bool(g["V"]) and g["A"] != g["V"] for g in local),
        "train_parent_ids": [g["id"] for g in groups],
        "ordered_original_row_ids": row_ids,
        "row_mapping_sha256": hashlib.sha256(canonical(row_ids)).hexdigest(),
        "train_rows_sha256": audit.sha(work / "train.jnnw"),
        "replay_rows_sha256": audit.sha(work / "replay.jnnw"),
        "target_indices_sha256": hashlib.sha256(canonical(ids)).hexdigest(),
        "target_values_dereferenced": len(ids),
        "test_target_reads": 0,
        "confirmation_target_reads": 0,
        "new_scan_searches": 0,
        "new_jass_searches": 0,
    }
    return {
        "design": design, "x": x, "z": z, "rx": rx, "rz": rz, "y": y,
        "base": work / "BASE.pjtw", "probe": work / "native-probe",
        "train": work / "train.jnnw", "replay": work / "replay.jnnw", "contract": contract,
    }


def verify_candidate(artifact: Path, mode: str):
    seal = audit.load_json(artifact / "candidate-seal.json")
    need(seal.get("schema") == "jass.ed5.q200k_choice_candidate_seal.v1" and seal.get("mode") == mode, "candidate_schema_mode")
    need(seal.get("role") == ("candidate" if mode == "production" else "development_only"), "candidate_role")
    need(seal.get("model_sha256") == audit.sha(artifact / MODEL_NAME), "candidate_hash")
    need(seal.get("beta_file_sha256") == audit.sha(artifact / "beta.npy"), "candidate_beta_hash")
    need(seal.get("recipe_sha256") == recipe_sha() == ed4fit.recipe_sha() and seal.get("controls_sha256") == MODEL_HASH, "candidate_recipe_controls")
    need(seal.get("test_target_reads") == 0 and seal.get("confirmation_target_reads") == 0 and seal.get("runtime_authorized") is False, "candidate_boundary")
    for file, digest in seal.get("evidence_sha256", {}).items():
        need(audit.sha(artifact / file) == digest, "candidate_evidence_changed")
    return seal


def verify_prerequisite(result: Path):
    meta = audit.load_json(result / "launch-prerequisite.json")
    need(meta.get("verdict") == "FULL_PIPELINE_REHEARSAL_PASS" and meta.get("published_roundtrip") is True, "missing_authenticated_rehearsal")
    root = result / "launch-prerequisite"
    verify_candidate(root, "rehearsal")
    return root


def run(result: Path, artifact: Path, mode: str, downloader=audit.fetch_existing, loader=load_inputs, probe=run_probe):
    evidence = StageEvidence(artifact, mode)
    work = result / "work"
    work.mkdir(parents=True, exist_ok=True)
    roots = {name: result / "inputs" / name for name in ("p0", "n1", "base", "target", "teacher")}
    try:
        evidence.begin("authenticate")
        for path in (result, artifact):
            need(shutil.disk_usage(path).free >= 3 * 1024**3, "disk_space_below_3gib")
        prerequisite = verify_prerequisite(result) if mode == "production" else None
        for key, identity, names in [
            ("p0", audit.P0, P0_NAMES),
            ("n1", audit.N1, N1_NAMES),
            ("base", audit.BASE, ["WDL_CONTROL.pjtw.gz"]),
            ("target", audit.TARGET, ["current_2m-context30.npy.gz"]),
            ("teacher", TEACHER_ID, TEACHER_NAMES),
        ]:
            downloader(identity, names, roots[key], artifact / ("verified-" + key + ".json"))
        evidence.complete()

        evidence.begin("verify-inputs")
        d = loader(roots, work, mode)
        need(d["design"]["normalizer"] == TRAIN_PARENTS, "real_normalizer")
        atomic_json(artifact / "train-contract.json", d["contract"])
        if prerequisite:
            need(audit.load_json(prerequisite / "train-contract.json") == d["contract"], "rehearsal_train_contract_mismatch")
        evidence.complete()

        evidence.begin("native-base")
        errors = {}
        for name, x, z in [("train", d["x"], d["z"]), ("replay", d["rx"], d["rz"])]:
            errors["base_" + name] = check_table(probe(d["probe"], d[name], d["base"], work / (name + "-base.tsv")), x, z)
        native.quantize(d["base"], np.zeros(math.WIDTH), work / "zero-residual.pjtw")
        need(audit.sha(work / "zero-residual.pjtw") == MODEL_HASH["BASE"], "zero_roundtrip")
        evidence.complete()

        evidence.begin("fit-choice-set")
        evidence.value["actual_side_effects"]["fits"] = 1
        evidence.save()
        def too_long(_signal, _frame):
            raise TimeoutError("ED5_FIT_300S_LIMIT")
        previous = signal.signal(signal.SIGALRM, too_long)
        signal.alarm(300)
        try:
            beta, solver = solve_once(d["design"])
        except math.NumericalFailure as exc:
            atomic_json(artifact / "solver-diagnostic.json", exc.report)
            raise
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            report = {"success": False, "error_type": type(exc).__name__, "finite_solution_available": False}
            atomic_json(artifact / "solver-diagnostic.json", report)
            raise math.NumericalFailure(report) from exc
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        atomic_json(artifact / "solver-diagnostic.json", solver)
        evidence.complete()

        evidence.begin("serialize-and-reload")
        model = work / MODEL_NAME
        quantization = native.quantize(d["base"], beta, model)
        raw, off, bw = native.read_model(d["base"])
        new, n_off, cw = native.read_model(model)
        need(raw[:off] == new[:n_off], "pattern_prefix_changed")
        qbeta = cw - bw
        qvalue = math.derivatives(qbeta, d["design"])[0]
        if not np.isfinite(qvalue) or qvalue > solver["initial_value"] + 1e-12:
            raise math.NumericalFailure({"success": False, "reason": "quantized_objective", "initial_value": solver["initial_value"], "quantized_value": float(qvalue) if np.isfinite(qvalue) else None})
        for name, x, z in [("train", d["x"], d["z"]), ("replay", d["rx"], d["rz"])]:
            observed = probe(d["probe"], d[name], model, work / (name + "-choice.tsv"))
            errors["choice_" + name] = check_table(observed, x, z + x @ qbeta)
            repeated = probe(d["probe"], d[name], model, work / (name + "-reloaded.tsv"))
            need(all(np.array_equal(a, b) for a, b in zip(observed, repeated)), "native_reload_mismatch")
        need(audit.sha(d["base"]) == MODEL_HASH["BASE"], "base_mutated")
        np.save(work / "beta.npy", np.asarray(beta, dtype="<f8"), allow_pickle=False)
        report = {
            "solver": solver,
            "recipe_sha256": recipe_sha(),
            "ed4_recipe_sha256": ed4fit.recipe_sha(),
            "teacher_choice_sets_sha256": d["contract"]["choice_sets_sha256"],
            "optimizer_invocations": 1,
            "quantization": quantization,
            "beta_sha256": hashlib.sha256(np.asarray(beta, dtype="<f8").tobytes()).hexdigest(),
            "quantized_beta_sha256": hashlib.sha256(np.asarray(qbeta, dtype="<f8").tobytes()).hexdigest(),
            "quantized_objective": float(qvalue),
            "scientific_verdict": None,
            "training_only": True,
            "heldout_evaluation_performed": False,
            "confirmation_target_reads": 0,
        }
        atomic_json(artifact / "fit-report.json", report)
        atomic_json(artifact / "native-roundtrip.json", {
            "schema": "jass.ed5.q200k_native_roundtrip.v1",
            "native_binary_sha256": audit.sha(d["probe"]),
            "rows": len(d["x"]) + len(d["rx"]),
            "maximum_logit_errors": errors,
            "native_reload_mismatches": 0,
            "zero_residual_byte_identical": True,
            "pattern_prefix_byte_identical": True,
            "probe_calls": 6,
            "searches": 0,
            "confirmation_target_reads": 0,
        })
        if prerequisite:
            need(audit.load_json(prerequisite / "fit-report.json") == report, "rehearsal_pure_report_mismatch")
            need((prerequisite / "beta.npy").read_bytes() == (work / "beta.npy").read_bytes(), "rehearsal_float64_beta_mismatch")
            need((prerequisite / MODEL_NAME).read_bytes() == model.read_bytes(), "rehearsal_candidate_bytes_mismatch")
        evidence.complete()

        evidence.begin("seal-and-publish")
        shutil.copyfile(model, artifact / MODEL_NAME)
        shutil.copyfile(work / "beta.npy", artifact / "beta.npy")
        seal = {
            "schema": "jass.ed5.q200k_choice_candidate_seal.v1",
            "mode": mode,
            "role": "candidate" if mode == "production" else "development_only",
            "model_sha256": audit.sha(artifact / MODEL_NAME),
            "beta_file_sha256": audit.sha(artifact / "beta.npy"),
            "recipe_sha256": recipe_sha(),
            "controls_sha256": MODEL_HASH,
            "source_seal_sha256": audit.SOURCE_SEAL,
            "teacher_identity": d["contract"]["teacher_identity"],
            "teacher_seal_sha256": d["contract"]["teacher_seal_sha256"],
            "choice_sets_sha256": d["contract"]["choice_sets_sha256"],
            "test_target_reads": 0,
            "confirmation_target_reads": 0,
            "runtime_authorized": False,
            "promotion_authorized": False,
            "automatic_continuation": False,
            "production_rehearsal_identity_verified": prerequisite is not None,
            "evidence_sha256": {f: audit.sha(artifact / f) for f in ("solver-diagnostic.json", "fit-report.json", "native-roundtrip.json", "train-contract.json")},
        }
        atomic_json(artifact / "candidate-seal.json", seal)
        verify_candidate(artifact, mode)
        summary = {
            "schema": "jass.ed5.q200k_choice_value_build.v1",
            "mode": mode,
            "verdict": "ED5_Q200K_CHOICE_CANDIDATE_SEALED_V1" if mode == "production" else "ED5_Q200K_CHOICE_FIT_REHEARSAL_COMPLETE_V1",
            "scientific_verdict": None,
            "scientific_success_established": False,
            "fits": 1,
            "optimizer_invocations": 1,
            "fit_role": seal["role"],
            "train_parents": TRAIN_PARENTS,
            "train_rows": TRAIN_ROWS,
            "replay_rows": REPLAY_N,
            "model_sha256": seal["model_sha256"],
            "candidate_seal_sha256": audit.sha(artifact / "candidate-seal.json"),
            "gradient_l2": solver["gradient_l2"],
            "minimum_hessian_eigenvalue": solver["minimum_hessian_eigenvalue"],
            "heldout_evaluation_performed": False,
            "confirmation_target_reads": 0,
            "alpha_spent": 0.0,
            "runtime_authorized": False,
            "promotion_authorized": False,
            "automatic_continuation": False,
            "actual_side_effects": dict(evidence.value["actual_side_effects"]),
            "next_stage": "GENERATE_FRESH_ED5_DWS_SOURCES" if mode == "production" else "AUTHENTICATE_REHEARSAL_BEFORE_PRODUCTION",
        }
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return summary
    except BaseException as exc:
        if isinstance(exc, math.NumericalFailure):
            atomic_json(artifact / "numerical-failure.json", exc.report)
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed5.q200k_choice_value_build.v1",
            "mode": mode,
            "verdict": "ED5_Q200K_CHOICE_FIT_NUMERICAL_FAILURE_V1" if isinstance(exc, math.NumericalFailure) else "ED5_Q200K_CHOICE_FIT_TECHNICAL_FAILURE_V1",
            "scientific_verdict": None,
            "automatic_continuation": False,
            "runtime_authorized": False,
            "promotion_authorized": False,
            "confirmation_target_reads": 0,
            "alpha_spent": 0.0,
            "actual_side_effects": dict(evidence.value["actual_side_effects"]),
        })
        raise


def main() -> int:
    from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
    install_shutdown_handlers()
    try:
        report = run(Path(os.environ["JASS_RESULT_DIR"]), Path(os.environ["JASS_ARTEFACT_DIR"]), os.environ["LAUNCH_MODE"])
        print(report["verdict"])
        return 0
    except Exception:
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
