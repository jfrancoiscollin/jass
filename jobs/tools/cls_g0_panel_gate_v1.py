#!/usr/bin/env python3
"""Closed, versioned admission for the frozen CLS G0 panel.

This is deliberately separate from Launch V2: the one published readiness
attempt can admit the two already-declared, differently timed main phases only
through a sealed common plan and typed published dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.launch_runtime_v2 import atomic_json
from jobs.tools import cls_g0_panel_readiness as readiness

SCHEMA = "jass.cls_panel_admission.v1"
PLAN_SCHEMA = "jass.cls_panel_common_plan.v1"
CONTEXT_SCHEMA = "jass.cls_panel_admission_context.v1"
PUBLISHED_SCHEMA = "jass.cls_panel_published_result.v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,180}$")

PHASES = {
    "readiness": {"games": 56, "player_searches_max": 9072, "stage_seconds": 1800,
                  "dispatcher_seconds": 2400, "mode": "rehearsal", "arms": ["CURRICULUM", "LOCAL", "WDL"]},
    "local": {"games": 576, "player_searches_max": 93312, "stage_seconds": 3600,
              "dispatcher_seconds": 4200, "mode": "production", "arms": ["LOCAL", "CURRICULUM"]},
    "wdl": {"games": 576, "player_searches_max": 93312, "stage_seconds": 3600,
            "dispatcher_seconds": 4200, "mode": "production", "arms": ["WDL", "CURRICULUM"]},
}
OUTPUTS = ["source-authentication.json", "runtime-identity.json", "opening-freeze.json",
           "stage-games.json.gz", "study-report.json", "progress.json", "scientific-summary.json",
           "manifest.json", "RESULTS.md"]
EFFECTS = ("fits", "new_scan_searches", "new_jass_searches", "strength_games", "selfplay_games", "promotions", "bakes", "test_target_reads")


class GateError(RuntimeError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise GateError(code)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink(), "FILE_MISSING_OR_SYMLINK")
    need(path.stat().st_size < 4_000_000, "JSON_TOO_LARGE")
    from jobs.tools.cls_g0_panel_raw_audit import decode
    value = decode(path.read_bytes())
    need(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def relative_file(root: Path, value: object, code: str) -> Path:
    need(isinstance(value, str), code)
    candidate = Path(value)
    need(not candidate.is_absolute() and ".." not in candidate.parts, code)
    need(not (root / candidate).is_symlink(), code)
    resolved = (root / candidate).resolve(strict=True)
    need(resolved.is_relative_to(root.resolve()) and not resolved.is_symlink(), code)
    return resolved


def phase_template(phase: str) -> dict:
    need(phase in PHASES, "PANEL_PHASE")
    p = dict(PHASES[phase])
    p["phase"] = phase
    p["outputs"] = list(OUTPUTS)
    p["dependency_slot"] = None if phase == "readiness" else "authenticated_readiness"
    return p


def validate_profile(profile: dict) -> None:
    need(profile.get("schema") == "jass.launch_profile.v2", "PROFILE_SCHEMA")
    need(profile.get("campaign") == "cls-g0-rejection-panel-v1", "PROFILE_CAMPAIGN")
    need(profile.get("stage") == "cls-g0-panel-v1", "PROFILE_STAGE")
    need(profile.get("command") == ["/usr/bin/python3", "jobs/tools/cls_g0_panel_stage.py"], "PROFILE_COMMAND")
    need(profile.get("required_phases") == ["authenticate", "build", "seal", "execute", "validate", "publish"], "PROFILE_PHASES")
    need(profile.get("evidence_outputs") == OUTPUTS, "PROFILE_OUTPUTS")
    need("code_sha" not in profile, "PROFILE_CODE_SHA_CIRCLE")
    need(profile.get("regressions") == ["jobs.tests.test_cls_g0_panel_readiness", "jobs.tests.test_cls_g0_panel_gate_v1",
         "jobs.tests.test_cls_g0_panel_stage", "jobs.tests.test_cls_g0_panel_pipeline"], "PROFILE_REGRESSIONS")
    for mode, phase in (("rehearsal", "readiness"), ("production", "local")):
        expected = {k: 0 for k in EFFECTS}
        expected.update(strength_games=PHASES[phase]["games"], new_jass_searches=PHASES[phase]["player_searches_max"])
        need(profile.get(mode + "_max_effects") == expected, "PROFILE_EFFECT_BOUNDS")


def frozen_contract() -> dict:
    from jobs.tools import cls_g0_panel_audit_stage as historical
    raw = historical.git_bytes("show", "HEAD:" + historical.CONTRACT)
    need(historical.audit.git_blob(raw) == historical.CONTRACT_BLOB, "FROZEN_CONTRACT")
    return json.loads(raw)


def generic_base() -> dict:
    return {"schema": "jass.stage_spec.v1", "campaign": "cls-g0-rejection-panel-v1",
        "stage": "cls-g0-panel-v1", "working_directory": ".", "inputs": [],
        "outputs": [{"scope": "artifact", "path": n, "kind": "file", "required": True, "nonempty": True}
                    for n in OUTPUTS + ["execution-evidence.json"]],
        "resources": {"hostname": "cpx62", "nproc": 16, "clean_worktree": True},
        "timeouts": {"stage_seconds": 1800, "terminate_grace_seconds": 30},
        "artifact_directory_contract": "empty_or_runner_launch",
        "environment": {"inherit": ["RCLONE_CONFIG_R2_TYPE", "RCLONE_CONFIG_R2_PROVIDER", "RCLONE_CONFIG_R2_ENDPOINT",
            "RCLONE_CONFIG_R2_ACCESS_KEY_ID", "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY"],
            "set": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                    "PYTHONDONTWRITEBYTECODE": "1"}},
        "scientific_side_effects": {"fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0},
        "success": {"required_exit_code": 0, "next_stage": None}}


def build_plan(code_sha: str, profile_raw_hash: str, stage_spec_base: dict | None = None,
               source_contract: dict | None = None) -> dict:
    c = frozen_contract()
    need(stage_spec_base is None or stage_spec_base == generic_base(), "GENERIC_BASE_DRIFT")
    need(source_contract is None or source_contract == c["sources"], "SOURCE_IDENTITY_DRIFT")
    return {"schema": PLAN_SCHEMA, "code_sha": code_sha,
        "command": ["/usr/bin/python3", "jobs/tools/cls_g0_panel_stage.py"], "profile_sha256": profile_raw_hash,
        "phase_order": list(PHASES), "phase_templates": {p: phase_template(p) for p in PHASES},
        "all_branches_present": True, "actual_opening_seal_before_games": True,
        "dependency_type": "authenticated_readiness", "native_identity": {"anchor": readiness.NATIVE_SOURCE_ANCHOR},
        "models": dict(readiness.MODELS), "source_identities": c["sources"], "runtime_identity": c["runtime"],
        "opening_recipe": c["openings"], "statistics": c["statistics"], "readiness": c["readiness"],
        "budget": c["budget"], "stage_spec_base": generic_base(),
        "audit_2072": {"job_id": readiness.AUDIT_2072_JOB, "attempt_id": readiness.AUDIT_2072_ATTEMPT,
                       "launch_receipt_sha256": readiness.AUDIT_2072_LAUNCH_RECEIPT}}


def validate_plan(plan: dict, profile: dict, profile_sha256: str | None = None) -> None:
    need(HEX40.fullmatch(plan.get("code_sha", "")) is not None, "PLAN_CODE_SHA")
    raw_profile = profile_sha256 or digest(profile)
    need(plan == build_plan(plan["code_sha"], raw_profile), "PLAN_TEMPLATE_DRIFT")
    need(plan["command"] == profile["command"], "PLAN_COMMAND")


def build_stage_spec(plan: dict, phase: str, base: dict | None = None) -> dict:
    import copy
    need(base is None or base == plan["stage_spec_base"], "GENERIC_BASE_DRIFT")
    result = copy.deepcopy(plan["stage_spec_base"])
    result.update(code_sha=plan["code_sha"], command=plan["command"])
    result["timeouts"]["stage_seconds"] = PHASES[phase]["stage_seconds"]
    result["environment"]["set"].update(PANEL_PHASE=phase, LAUNCH_MODE=PHASES[phase]["mode"])
    result["scientific_side_effects"]["strength_games"] = PHASES[phase]["games"]
    return result


def materialize(plan: dict, phase: str, dependencies: dict) -> dict:
    need(phase in PHASES, "PANEL_PHASE")
    material = {"schema": "jass.cls_panel_materialized_spec.v1", "common_plan_sha256": digest(plan),
        "code_sha": plan["code_sha"], "command": plan["command"], "profile_sha256": plan["profile_sha256"],
        "phase": phase, "template": phase_template(phase), "runtime_identity": plan["runtime_identity"],
        "native_identity": plan["native_identity"], "models": plan["models"], "source_identities": plan["source_identities"],
        "generic_spec": build_stage_spec(plan, phase)}
    if phase == "readiness":
        need(not dependencies, "READINESS_DEPENDENCY_FORBIDDEN")
    else:
        need(set(dependencies) == {"authenticated_readiness"}, "READINESS_DEPENDENCY_REQUIRED")
        material["authenticated_readiness"] = readiness_identity(dependencies["authenticated_readiness"])
    return material


def readiness_identity(record: dict) -> dict:
    keys = {"job_id", "attempt_id", "launch_receipt_sha256", "publisher_manifest_sha256", "opening_selection_sha256"}
    need(isinstance(record, dict) and set(record) == keys, "READINESS_IDENTITY")
    need(all(isinstance(record[k], str) and IDENT.fullmatch(record[k]) for k in ("job_id", "attempt_id")), "READINESS_RECORD_IDENTITY")
    need(all(isinstance(record[k], str) and HEX64.fullmatch(record[k]) for k in keys - {"job_id", "attempt_id"}), "READINESS_RECORD_HASH")
    return dict(record)


def validate_regressions(value: dict, profile: dict) -> None:
    need(value.get("schema") == "jass.launch_regressions.v2" and value.get("passed") is True and
         all(type(value.get(k)) is int and value[k] == 0 for k in ("skipped", "failures", "errors")) and
         type(value.get("tests")) is int and value["tests"] > 0 and value.get("suites") == profile["regressions"],
         "REGRESSION_SUITE_FAILED")


def fetch_panel_proof(*, pointer: dict, plan: dict, profile: dict, out_dir: Path,
                      technical_only: bool = False) -> dict:
    """Authenticate the real publisher envelope and every gate/core artifact."""
    from jobs.tools import fetch_result_files as transport
    from jobs.tools.launch_gate_v2 import runtime_identity
    need(set(pointer) == {"job_id", "attempt_id"} and all(IDENT.fullmatch(pointer[k]) for k in pointer), "PUBLISHED_POINTER")
    names = OUTPUTS + ["execution-evidence.json", "panel-regressions.json", "panel-admission-receipt.json"]
    prefix = f"r2:jass-data/runs/{pointer['job_id']}/{pointer['attempt_id']}"
    verified = transport.fetch_files(rclone=os.environ.get("RCLONE_BIN", "rclone"), prefix=prefix,
        selections=[("artefacts/" + n, n) for n in names] +
                   [("stage-receipt.json", "stage-receipt.json"), ("manifest.json", "publisher-manifest.json")], out_dir=out_dir)
    need(tuple(verified.get(k) for k in ("job_id", "attempt_id", "code_sha", "host", "result_state", "exit_code")) ==
         (pointer["job_id"], pointer["attempt_id"], plan["code_sha"], "cpx62", "completed", 0), "PUBLISHED_IDENTITY")
    receipt = read(out_dir / "panel-admission-receipt.json")
    phase = receipt.get("phase"); need(phase in PHASES, "PUBLISHED_PHASE")
    need(receipt.get("schema") == "jass.cls_panel_receipt.v1" and receipt.get("code_sha") == plan["code_sha"] and
         receipt.get("common_plan_sha256") == digest(plan) and receipt.get("profile_sha256") == plan["profile_sha256"] and
         all(receipt.get(k) == pointer[k] for k in pointer), "PUBLISHED_RECEIPT_IDENTITY")
    need(receipt.get("gate_runtime") == runtime_identity(profile["command"][0]), "PUBLISHED_GATE_RUNTIME")
    hashes = {n: sha(out_dir / n) for n in OUTPUTS + ["execution-evidence.json", "panel-regressions.json"]}
    need(receipt.get("outputs") == hashes, "PUBLISHED_OUTPUT_HASHES")
    need(receipt.get("stage_receipt_sha256") == sha(out_dir / "stage-receipt.json"), "PUBLISHED_CORE_HASH")
    core = read(out_dir / "stage-receipt.json")
    expected_spec = build_stage_spec(plan, phase)
    need(core.get("state") == "completed" and core.get("exit_code") == 0 and core.get("timed_out") is False and
         core.get("code_sha") == plan["code_sha"] and core.get("spec_sha256") == digest(expected_spec) and
         core.get("inputs_authenticated") is True and core.get("outputs_authenticated") is True and
         0 < core.get("duration_seconds", 0) <= PHASES[phase]["stage_seconds"], "PUBLISHED_CORE_RECEIPT")
    validate_regressions(read(out_dir / "panel-regressions.json"), profile)
    evidence = validate_evidence(out_dir / "execution-evidence.json", profile, phase)
    need(receipt.get("actual_side_effects") == evidence["actual_side_effects"], "PUBLISHED_EFFECT_IDENTITY")
    runtime = read(out_dir / "runtime-identity.json")
    need(runtime.get("context_runtime_identity") == plan["runtime_identity"] and runtime.get("models") == readiness.MODELS and
         runtime.get("native_source_anchor") == readiness.NATIVE_SOURCE_ANCHOR, "PUBLISHED_RUNTIME")
    manifest = read(out_dir / "manifest.json")
    need(manifest.get("output_sha256") == {n: hashes[n] for n in OUTPUTS if n != "manifest.json"}, "PUBLISHED_STAGE_MANIFEST")
    opening = read(out_dir / "opening-freeze.json")
    need(opening.get("selection_sha256") == digest({k: v for k, v in opening.items() if k != "selection_sha256"}) and
         opening["selection_sha256"] == receipt.get("opening_selection_sha256"), "PUBLISHED_OPENING_SEAL")
    result = {"receipt": receipt, "evidence": evidence, "opening": opening, "runtime": runtime,
        "games_path": out_dir / "stage-games.json.gz", "publisher_manifest_sha256": sha(out_dir / "publisher-manifest.json")}
    if not technical_only:
        result["study"] = read(out_dir / "study-report.json")
    return result


def readiness_from_r2(pointer: dict, plan: dict, profile: dict, out_dir: Path) -> dict:
    proof = fetch_panel_proof(pointer=pointer, plan=plan, profile=profile, out_dir=out_dir)
    r, study = proof["receipt"], proof["study"]
    need(r["phase"] == "readiness" and study.get("games") == 56 and study.get("pairs") == 28 and
         study.get("timed_pairs") == 24 and study.get("deterministic_pairs") == 4, "READINESS_COVERAGE")
    projection = study.get("projected_main_work_seconds", {})
    need(set(projection) == {"LOCAL", "WDL"} and all(type(v) in (int, float) and 0 < v <= 3000 for v in projection.values()),
         "READINESS_PROJECTION")
    need(r.get("materialized_spec_sha256") == digest(materialize(plan, "readiness", {})), "READINESS_MATERIALIZED_SPEC")
    trajectories = set(study.get("trajectory_canonicals", []))
    need(bool(trajectories), "READINESS_TRAJECTORIES_MISSING")
    readiness.validate_freshness(proof["opening"], {"trajectory_canonicals": trajectories})
    return readiness_identity({**pointer, "launch_receipt_sha256": sha(out_dir / "panel-admission-receipt.json"),
        "publisher_manifest_sha256": proof["publisher_manifest_sha256"],
        "opening_selection_sha256": proof["opening"]["selection_sha256"]})


def local_technical_from_r2(pointer: dict, plan: dict, profile: dict, out_dir: Path,
                           prebound_job: str, prebound_admission_sha: str, activation_sha: str,
                           materialized_sha: str) -> dict:
    need(pointer.get("job_id") == prebound_job, "LOCAL_JOB_PREBIND")
    proof = fetch_panel_proof(pointer=pointer, plan=plan, profile=profile, out_dir=out_dir, technical_only=True)
    receipt = proof["receipt"]
    need(receipt["phase"] == "local" and receipt.get("admission_sha256") == prebound_admission_sha and
         receipt.get("main_activation_sha256") == activation_sha and
         receipt.get("materialized_spec_sha256") == materialized_sha, "LOCAL_TECHNICAL_IDENTITY")
    return {"prebound_local_job_id": prebound_job, "prebound_local_admission_sha256": prebound_admission_sha,
        **pointer, "code_sha": plan["code_sha"], "launch_receipt_sha256": sha(out_dir / "panel-admission-receipt.json"),
        "stage_games_sha256": sha(proof["games_path"]), "scientific_verdict": None,
        "effects": proof["evidence"]["actual_side_effects"], "games_path": str(proof["games_path"])}


def validate_main_activation(path: Path, plan: dict, admission: dict, admission_raw_sha: str,
                             control: Path) -> dict:
    activation = read(path)
    need(activation.get("schema") == "jass.cls_panel_main_activation.v1" and activation.get("common_plan_sha256") == digest(plan)
         and activation.get("code_sha") == plan["code_sha"] and activation.get("profile_sha256") == plan["profile_sha256"], "MAIN_ACTIVATION_SCHEMA")
    records = {}
    for phase in ("local", "wdl"):
        entry = activation.get(phase, {})
        target = relative_file(control, entry.get("admission"), "MAIN_ADMISSION_PATH")
        record = read(target)
        need(sha(target) == entry.get("admission_sha256") and record.get("phase") == phase and
             record.get("common_plan_sha256") == digest(plan) and record.get("profile_sha256") == plan["profile_sha256"], "MAIN_ACTIVATION_HASH")
        need(record.get("schema") == SCHEMA, "MAIN_ADMISSION_SCHEMA")
        spec_path = relative_file(control, entry.get("spec"), "MAIN_SPEC_PATH")
        need(sha(spec_path) == record.get("spec_sha256") and read(spec_path) == build_stage_spec(plan, phase), "MAIN_SPEC_IDENTITY")
        material = materialize(plan, phase, {"authenticated_readiness": record["authenticated_readiness"]})
        need(record.get("materialized_spec_sha256") == entry.get("materialized_spec_sha256") == digest(material), "MAIN_ACTIVATION_MATERIAL")
        records[phase] = record
    need(records["local"]["authenticated_readiness"] == records["wdl"]["authenticated_readiness"], "MAIN_READINESS_MISMATCH")
    need(records["wdl"].get("prebound_local_job_id") == records["local"]["job_id"] and
         records["wdl"].get("prebound_local_admission_sha256") == activation["local"]["admission_sha256"], "MAIN_PREBIND")
    need(activation[admission["phase"]]["admission_sha256"] == admission_raw_sha, "CURRENT_ACTIVATION_HASH")
    return activation


def validate_admission(admission: dict, plan: dict, profile: dict, code_sha: str,
                       profile_sha256: str | None = None) -> tuple[dict, dict]:
    need(admission.get("schema") == SCHEMA, "ADMISSION_SCHEMA")
    phase = admission.get("phase")
    need(phase in PHASES and admission.get("common_plan_sha256") == digest(plan), "ADMISSION_PLAN_OR_PHASE")
    expected_profile = profile_sha256 or digest(profile)
    need(admission.get("profile_sha256") == expected_profile and code_sha == plan["code_sha"], "ADMISSION_IDENTITY")
    dependencies: dict = {}
    if phase == "readiness":
        audit = admission.get("authenticated_audit_2072")
        need(isinstance(audit, dict), "AUDIT_2072_DEPENDENCY_REQUIRED")
        # A full R2 envelope is parsed here as well as by the stage.  The small
        # typed fallback still pins the sole authenticated historical audit.
        if "readback" in audit or "summary" in audit:
            readiness.require_authenticated_audit_2072(audit)
        else:
            need((audit.get("job_id"), audit.get("attempt_id"), audit.get("launch_receipt_sha256")) ==
                 (readiness.AUDIT_2072_JOB, readiness.AUDIT_2072_ATTEMPT, readiness.AUDIT_2072_LAUNCH_RECEIPT),
                 "AUDIT_2072_PIN")
        dependencies["authenticated_readiness"] = audit
    if phase in ("local", "wdl"):
        dependencies["authenticated_readiness"] = readiness_identity(admission.get("authenticated_readiness", {}))
    if phase == "wdl":
        need(IDENT.fullmatch(admission.get("prebound_local_job_id", "")) is not None and
             HEX64.fullmatch(admission.get("prebound_local_admission_sha256", "")) is not None, "WDL_PREBIND_REQUIRED")
    else:
        need("prebound_local_job_id" not in admission and "prebound_local_admission_sha256" not in admission,
             "UNEXPECTED_LOCAL_PREBIND")
    spec = materialize(plan, phase, {k: v for k, v in dependencies.items() if k == "authenticated_readiness"}
                       if phase != "readiness" else {})
    need(admission.get("materialized_spec_sha256") == digest(spec), "MATERIALIZED_SPEC_HASH")
    return spec, dependencies


def validate_external_spec(path: Path, admission: dict, materialized: dict) -> None:
    """The dispatcher-owned file remains byte-addressed and carries no free panel field."""
    need(HEX64.fullmatch(admission.get("spec_sha256", "")) is not None and sha(path) == admission["spec_sha256"],
         "SPEC_FILE_HASH")
    spec = read(path)
    need(spec == materialized["generic_spec"], "SPEC_PROJECTION_DRIFT")
    from jobs.tools.run_experiment_stage import validate_spec
    validate_spec(spec)
    need(os.environ.get("EXPECTED_LAUNCH_TIMEOUT_SECONDS") == str(materialized["template"]["dispatcher_seconds"]),
         "OUTER_TIMEOUT_CONTRACT")


def validate_evidence(path: Path, profile: dict, phase: str) -> dict:
    value = read(path)
    need(value.get("schema") == "jass.execution_evidence.v2" and value.get("state") == "completed", "EXECUTION_EVIDENCE")
    need(value.get("completed_phases") == profile["required_phases"] and value.get("mode") == PHASES[phase]["mode"], "INCOMPLETE_PIPELINE")
    effects = value.get("actual_side_effects", {})
    need(set(effects) == set(EFFECTS) and all(type(v) is int and v >= 0 for v in effects.values()), "EFFECT_COUNTERS")
    template = phase_template(phase)
    need(effects["strength_games"] == template["games"] and template["games"] * 2 <= effects["new_jass_searches"] <= template["player_searches_max"],
         "PHASE_EFFECTS")
    need(all(effects[key] == 0 for key in EFFECTS if key not in ("strength_games", "new_jass_searches")),
         "UNAUTHORIZED_EFFECT")
    return value


def build_context(plan: dict, profile: dict, admission: dict, code_sha: str, paths: dict | None = None,
                  profile_sha256: str | None = None) -> dict:
    spec, dependencies = validate_admission(admission, plan, profile, code_sha, profile_sha256)
    return {"schema": CONTEXT_SCHEMA, "phase": admission["phase"], "common_plan": plan,
            "common_plan_sha256": digest(plan), "materialized_spec": spec,
            "materialized_spec_sha256": digest(spec), "profile_sha256": profile_sha256 or digest(profile), "code_sha": code_sha,
            "command": profile["command"], "runtime_identity": plan["runtime_identity"],
            # Readiness has no actual seal yet. The stage binds its one generated
            # seal before its first game; main phases carry the published value.
            "opening_selection_sha256": dependencies.get("authenticated_readiness", {}).get("opening_selection_sha256"),
            "authenticated_dependencies": dependencies, "paths": paths or {}}


def reject_prior_attempts(control: Path, admission: dict) -> None:
    """No second claimed attempt for this phase, including failed starts."""
    current = os.environ.get("JASS_ATTEMPT_ID")
    job = os.environ.get("JASS_JOB_ID")
    need(isinstance(current, str) and IDENT.fullmatch(current) and admission.get("job_id") == job, "CURRENT_ATTEMPT_IDENTITY")
    for path in (control / "specs").rglob("*.admission.json"):
        other = read(path)
        if other.get("schema") != SCHEMA or other.get("phase") != admission["phase"]:
            continue
        other_job = other.get("job_id")
        need(isinstance(other_job, str) and IDENT.fullmatch(other_job), "ADMISSION_JOB")
        status_path = "status/" + other_job + ".json"
        history = subprocess.check_output(["git", "-C", str(control), "log", "--format=%H", "--", status_path], text=True).splitlines()
        for commit in history:
            raw = subprocess.check_output(["git", "-C", str(control), "show", commit + ":" + status_path])
            status = json.loads(raw)
            if status.get("attempt_id"):
                need(other_job == job and status["attempt_id"] == current, "PHASE_PREVIOUS_ATTEMPT_NO_RETRY")


def execute(args: argparse.Namespace) -> int:
    from jobs.tools import run_experiment_stage as core
    from jobs.tools.launch_gate_v2 import runtime_identity
    import shutil
    admission = read(args.admission)
    need(sha(args.admission) == args.admission_sha256, "ADMISSION_HASH")
    repo = args.repo_root.resolve(strict=True)
    control = Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control")).resolve(strict=True)
    plan_path = relative_file(control, admission.get("common_plan"), "COMMON_PLAN_PATH")
    profile_path = relative_file(repo, admission.get("profile"), "PROFILE_PATH")
    plan, profile = read(plan_path), read(profile_path)
    raw_profile_sha = sha(profile_path)
    validate_profile(profile); validate_plan(plan, profile, raw_profile_sha)
    code_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    need(not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip(), "DIRTY_CHECKOUT")
    need(code_sha == plan["code_sha"], "CODE_IDENTITY")
    reject_prior_attempts(control, admission)
    material, dependencies = validate_admission(admission, plan, profile, code_sha, raw_profile_sha)
    validate_external_spec(args.spec, admission, material)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    paths = {"common_plan": str(plan_path), "profile": str(profile_path),
             "spec": str(args.result_dir / "panel-materialized-spec.json"), "admission": str(args.admission)}
    activation_sha = None
    if admission["phase"] in ("local", "wdl"):
        activation_path = plan_path.with_name("main-activation.json")
        activation = validate_main_activation(activation_path, plan, admission, args.admission_sha256, control)
        activation_sha = sha(activation_path)
        ready_dir = args.result_dir / "authenticated-readiness"
        typed = admission["authenticated_readiness"]
        resolved = readiness_from_r2({k: typed[k] for k in ("job_id", "attempt_id")}, plan, profile, ready_dir)
        need(resolved == typed, "READINESS_PUBLISHED_TUPLE_MISMATCH")
        paths.update(opening_seal=str(ready_dir / "opening-freeze.json"), readiness_runtime=str(ready_dir / "runtime-identity.json"))
        if admission["phase"] == "wdl":
            status = read(relative_file(control, "status/" + admission["prebound_local_job_id"] + ".json", "LOCAL_STATUS_PATH"))
            need(status.get("job_id") == admission["prebound_local_job_id"] and status.get("code_sha") == code_sha and
                 status.get("state") == "completed" and status.get("exit_code") == 0, "LOCAL_STATUS_IDENTITY")
            local = local_technical_from_r2({k: status[k] for k in ("job_id", "attempt_id")}, plan, profile,
                args.result_dir / "authenticated-local", admission["prebound_local_job_id"],
                admission["prebound_local_admission_sha256"], activation_sha, activation["local"]["materialized_spec_sha256"])
            paths["local_stage_games"] = local.pop("games_path")
            dependencies["local_technical_completion"] = local
    atomic_json(Path(paths["spec"]), material)
    context = build_context(plan, profile, admission, code_sha, paths, raw_profile_sha)
    context["authenticated_dependencies"] = dependencies
    atomic_json(args.result_dir / "panel-admission-context.json", context)
    regressions = args.result_dir / "panel-regressions.json"
    cp = subprocess.run([profile["command"][0], str(repo / "jobs/tools/launch_regressions_v2.py"), "--profile", str(profile_path),
                         "--out", str(regressions)], cwd=repo, timeout=300)
    need(cp.returncode == 0, "REGRESSION_PROCESS_FAILED")
    validate_regressions(read(regressions), profile)
    rc, core_receipt = core.run_stage(spec_path=args.spec, repo_root=repo, result_dir=args.result_dir, artifact_dir=args.artifact_dir)
    need(rc == 0 and core_receipt.get("state") == "completed", "STAGE_FAILED")
    evidence = validate_evidence(args.artifact_dir / "execution-evidence.json", profile, admission["phase"])
    shutil.copyfile(regressions, args.artifact_dir / "panel-regressions.json")
    hashes = {name: sha(args.artifact_dir / name) for name in OUTPUTS + ["execution-evidence.json", "panel-regressions.json"]}
    selection = read(args.artifact_dir / "opening-freeze.json")["selection_sha256"]
    bound = read(args.result_dir / "panel-admission-context.json")
    need(bound["opening_selection_sha256"] == selection, "PREGAME_SELECTION_CHECKPOINT")
    atomic_json(args.artifact_dir / "panel-admission-receipt.json", {"schema": "jass.cls_panel_receipt.v1", "phase": admission["phase"],
        "code_sha": code_sha, "common_plan_sha256": digest(plan), "profile_sha256": raw_profile_sha,
        "materialized_spec_sha256": digest(material), "admission_sha256": args.admission_sha256,
        "stage_receipt_sha256": sha(args.result_dir / "stage-receipt.json"), "main_activation_sha256": activation_sha,
        "outputs": hashes, "actual_side_effects": evidence["actual_side_effects"], "opening_selection_sha256": selection,
        "gate_runtime": runtime_identity(profile["command"][0]),
        "job_id": os.environ["JASS_JOB_ID"], "attempt_id": os.environ["JASS_ATTEMPT_ID"]})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("admission", "spec", "repo-root", "result-dir", "artifact-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--admission-sha256", required=True)
    args = parser.parse_args()
    try:
        return execute(args)
    except Exception as exc:
        print("CLS_PANEL_ADMISSION_BLOCKED: " + (str(exc) if isinstance(exc, GateError) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
