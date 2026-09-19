#!/usr/bin/env python3
"""Prove runner-managed numeric-runtime continuity from historical jobs 1340 to 1341.

This is a bounded technical diagnostic following 2054. It authenticates only:
- the immutable 1340 technical ``python-runtime.json`` receipt;
- the exact jass-control first-parent chain from 1340 completion to 1341 running;
- the exact historical 1340/1341 template runtime contracts at their frozen Jass SHAs.

No corpus, target, model, optimizer/fit log, search/game, alpha, promotion or bake
payload is read. The proof scope is the runner-managed control plane: the chain
shows no intervening runner job between 1340 completion and 1341 claim/start, the
1340 template has no numeric-runtime mutator after its receipt is written, and the
1341 template requires the already-ready same persistent venv and never reinstalls
it. This does not assert forensic knowledge of hypothetical out-of-band manual host
mutation; no such mutation is evidenced by the authenticated runner/control chain.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_2031_failure_diagnostic as base  # noqa: E402
from launch_runtime_v2 import StageEvidence, atomic_json as runtime_atomic_json  # noqa: E402

ABC_JOB = "cpx62-1340-jass-megacorpus-comparative-fit-v1"
ABC_ATTEMPT = "20260814T123246Z-2ce07222"
ABC_CODE = "2ce07222f86c1468a1081fbdc53e9e17a0c5326e"
ABC_PREFIX = f"r2:jass-data/runs/{ABC_JOB}/{ABC_ATTEMPT}"

CURR_JOB = "cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURR_ATTEMPT = "20260814T191555Z-18c38a33"
CURR_CODE = "18c38a33ae78c9c2e8e2df62fca266da28dacead"

CONTROL_DONE_1340 = "2324bb7286d2ee90bd9e4c7d4715facba4e45540"
CONTROL_LAUNCH_1341 = "01da25fae2d0156fdab3f0ea4cda90022fd3b56e"
CONTROL_ROUTE_1341 = "ebb00815e1b771c2db02a6ceed2cd1c20d3ac874"
CONTROL_CLAIM_1341 = "44a5e3a35aec0e81f78fa18432f9ef5c3314d286"
CONTROL_RUNNING_1341 = "deaae085df08b75852878161a2be4b647ab95098"
CONTROL_CHAIN = [
    CONTROL_LAUNCH_1341,
    CONTROL_ROUTE_1341,
    CONTROL_CLAIM_1341,
    CONTROL_RUNNING_1341,
]

ABC_TEMPLATE = "jobs/templates/jass-megacorpus-comparative-fit-v1.sh"
CURR_TEMPLATE = "jobs/templates/jass-megacorpus-arm-d-fit-v1.sh"
VENV = "/var/tmp/jass-l3-numeric-venv-current-v1"
READY = ".jass-runtime-ready-v1"
EXPECTED_NUMPY = "2.5.2"
EXPECTED_SCIPY = "1.18.0"

TERMINAL = "CLS_HIER_L2_1340_1341_RUNTIME_CONTINUITY_PROVEN_V1"
PHASE = "execute-cls-hier-l2-1340-1341-runtime-continuity-diagnostic"
NEXT_STAGE = "REPLAY_CONTROL_WITH_HISTORICAL_NUMERIC_RUNTIME_EXACT_PINS"


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc.stdout


def git_blob(repo: Path, commit: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=repo, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return proc.stdout


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def authenticate_control_chain(control: Path) -> dict[str, object]:
    if not (control / ".git").exists():
        raise RuntimeError(f"control checkout unavailable: {control}")
    for commit in [CONTROL_DONE_1340, *CONTROL_CHAIN]:
        run_git(control, "cat-file", "-e", f"{commit}^{{commit}}")

    actual = [x for x in run_git(
        control, "rev-list", "--first-parent", "--reverse",
        f"{CONTROL_DONE_1340}..{CONTROL_RUNNING_1341}",
    ).splitlines() if x]
    if actual != CONTROL_CHAIN:
        raise RuntimeError(f"1340->1341 first-parent chain drift: {actual}")

    messages = {
        commit: run_git(control, "show", "-s", "--format=%s", commit).strip()
        for commit in [CONTROL_DONE_1340, *CONTROL_CHAIN]
    }
    expected_messages = {
        CONTROL_DONE_1340: f"runner: done {ABC_JOB}",
        CONTROL_LAUNCH_1341: "Launch audited MegaCorpus arm D fit",
        CONTROL_ROUTE_1341: "Route CPX to MegaCorpus arm D",
        CONTROL_CLAIM_1341: f"runner: claim {CURR_JOB}",
        CONTROL_RUNNING_1341: f"runner: running {CURR_JOB}",
    }
    if messages != expected_messages:
        raise RuntimeError(f"historical control messages drift: {messages}")

    pending = f"queue/pending/{CURR_JOB}.sh"
    running = f"queue/running/{CURR_JOB}.sh"
    launch_script = git_blob(control, CONTROL_LAUNCH_1341, pending).decode("utf-8")
    if f'export EXPECTED_CODE_SHA="{CURR_CODE}"' not in launch_script:
        raise RuntimeError("1341 launch code SHA drift")
    if f'export EXPECTED_ABC_JOB="{ABC_JOB}"' not in launch_script:
        raise RuntimeError("1341 launch parent job drift")
    if f'export EXPECTED_ABC_ATTEMPT="{ABC_ATTEMPT}"' not in launch_script:
        raise RuntimeError("1341 launch parent attempt drift")
    if f'export EXPECTED_ABC_CODE_SHA="{ABC_CODE}"' not in launch_script:
        raise RuntimeError("1341 launch parent code drift")

    route = git_blob(control, CONTROL_ROUTE_1341, "state/host-filter/cpx62").decode("utf-8").strip()
    if route != CURR_JOB:
        raise RuntimeError(f"1341 host-route drift: {route}")
    running_script = git_blob(control, CONTROL_CLAIM_1341, running)
    if running_script != launch_script.encode("utf-8"):
        raise RuntimeError("1341 queue claim changed script bytes")

    status_1340 = json.loads(git_blob(
        control, CONTROL_DONE_1340, f"status/{ABC_JOB}.json"
    ).decode("utf-8"))
    status_1341 = json.loads(git_blob(
        control, CONTROL_RUNNING_1341, f"status/{CURR_JOB}.json"
    ).decode("utf-8"))
    if (status_1340.get("host"), status_1340.get("state"), status_1340.get("code_sha")) != (
        "cpx62", "completed", ABC_CODE
    ):
        raise RuntimeError("1340 completion status identity drift")
    if (status_1341.get("host"), status_1341.get("state"), status_1341.get("code_sha"), status_1341.get("control_sha")) != (
        "cpx62", "running", CURR_CODE, CONTROL_CLAIM_1341
    ):
        raise RuntimeError("1341 running status identity drift")
    if status_1341.get("attempt_id") != CURR_ATTEMPT:
        raise RuntimeError("1341 attempt identity drift")

    ended = parse_iso(status_1340["ended_at"])
    started = parse_iso(status_1341["started_at"])
    gap = int((started - ended).total_seconds())
    if gap != 318:
        raise RuntimeError(f"historical 1340->1341 start gap drift: {gap}s")

    return {
        "scope": "runner-managed-control-plane",
        "control_done_1340": CONTROL_DONE_1340,
        "control_chain_to_1341_running": CONTROL_CHAIN,
        "messages": messages,
        "same_host": "cpx62",
        "gap_seconds_1340_end_to_1341_start": gap,
        "intervening_runner_jobs": 0,
        "1341_launch_script_sha256": sha_bytes(launch_script.encode("utf-8")),
        "1341_claim_preserved_script_bytes": True,
    }


def authenticate_template_runtime_contracts() -> dict[str, object]:
    abc = git_blob(ROOT, ABC_CODE, ABC_TEMPLATE)
    curr = git_blob(ROOT, CURR_CODE, CURR_TEMPLATE)
    a = abc.decode("utf-8", errors="strict")
    c = curr.decode("utf-8", errors="strict")
    if VENV not in a or VENV not in c or READY not in a or READY not in c:
        raise RuntimeError("historical persistent numeric runtime path/marker drift")

    receipt_marker = '"$PY" - "$ART/python-runtime.json" "$VENV"'
    if receipt_marker not in a:
        raise RuntimeError("1340 python-runtime receipt marker drift")
    before, after = a.split(receipt_marker, 1)
    if before.count("pip install") != 1:
        raise RuntimeError("1340 bootstrap install-count drift")
    forbidden_mutators = ("pip install", "pip uninstall", "venv --clear", "pip wheel")
    if any(token in after for token in forbidden_mutators):
        raise RuntimeError("1340 numeric runtime mutated after runtime receipt")
    if "persistent numeric runtime absent; do not reinstall in this job" not in c:
        raise RuntimeError("1341 ready-runtime-only guard drift")
    if any(token in c for token in ("pip install", "pip uninstall", "venv --clear")):
        raise RuntimeError("1341 unexpectedly mutates numeric runtime")

    return {
        "venv": VENV,
        "ready_marker": f"{VENV}/{READY}",
        "1340_code_sha": ABC_CODE,
        "1340_template": ABC_TEMPLATE,
        "1340_template_sha256": sha_bytes(abc),
        "1340_bootstrap_install_count_before_receipt": 1,
        "1340_runtime_mutators_after_receipt": 0,
        "1341_code_sha": CURR_CODE,
        "1341_template": CURR_TEMPLATE,
        "1341_template_sha256": sha_bytes(curr),
        "1341_requires_preexisting_ready_runtime": True,
        "1341_runtime_mutators": 0,
    }


def authenticate_1340_runtime(rclone: str, work: Path) -> tuple[dict, dict]:
    inv = base.fetch.inspect_result_inventory(
        rclone=rclone, prefix=ABC_PREFIX, expected_state="completed"
    )
    got = (inv.get("job_id"), inv.get("attempt_id"), inv.get("code_sha"), inv.get("result_state"))
    want = (ABC_JOB, ABC_ATTEMPT, ABC_CODE, "completed")
    if got != want:
        raise RuntimeError(f"1340 runtime source identity drift: got={got} want={want}")
    files = {x.get("path"): x for x in inv.get("files", [])}
    if "artefacts/python-runtime.json" not in files:
        raise RuntimeError("1340 python-runtime artifact missing")
    fetched = base.fetch.fetch_files(
        rclone=rclone, prefix=ABC_PREFIX, expected_state="completed",
        selections=[("artefacts/python-runtime.json", "runtime-1340.json")], out_dir=work,
    )
    payload = json.loads((work / "runtime-1340.json").read_text(encoding="utf-8"))
    got_runtime = (payload.get("venv"), payload.get("numpy"), payload.get("scipy"), payload.get("persistent_cache"))
    want_runtime = (VENV, EXPECTED_NUMPY, EXPECTED_SCIPY, True)
    if got_runtime != want_runtime:
        raise RuntimeError(f"1340 historical numeric runtime drift: got={got_runtime} want={want_runtime}")
    return payload, fetched


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    control = Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control"))
    work = result_dir / "work" / "runtime-continuity"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    evidence.begin(PHASE)

    runtime, runtime_fetch = authenticate_1340_runtime(os.environ.get("RCLONE_BIN", "rclone"), work)
    chain = authenticate_control_chain(control)
    templates = authenticate_template_runtime_contracts()

    proof = {
        "schema": "jass.cls_hier_l2_1340_1341_runtime_continuity.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "continuity_scope": "runner-managed-control-plane",
        "runner_managed_runtime_continuity_proven": True,
        "out_of_band_host_mutation_observed": False,
        "historical_numeric_runtime": {
            "venv": runtime["venv"],
            "numpy": runtime["numpy"],
            "scipy": runtime["scipy"],
        },
        "control_chain": chain,
        "template_runtime_contracts": templates,
        "reason": (
            "1340 sealed the persistent venv runtime; its frozen template contains no runtime mutator after that receipt; "
            "the exact first-parent jass-control chain contains no intervening runner job before 1341; 1341 claimed on the same "
            "cpx62 host, required the existing READY-marked same venv, and contains no reinstall/mutation path."
        ),
        "next_stage": NEXT_STAGE,
        "boundary": {
            "scientific_payloads_read": 0,
            "candidate_model_payloads_read": 0,
            "fit_log_payloads_read": 0,
            "target_reads": 0,
            "fits": 0,
            "new_jass_searches": 0,
            "new_scan_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        },
    }
    write_json(art / "runtime-continuity.json", proof)
    write_json(art / "source-authentication.json", {
        "schema": "jass.cls_hier_l2_1340_1341_runtime_continuity_authentication.v1",
        "historical_1340_runtime": runtime_fetch,
        "control_commits": [CONTROL_DONE_1340, *CONTROL_CHAIN],
        "technical_source_only": True,
    })
    summary = {
        "schema": "jass.cls_hier_l2_1340_1341_runtime_continuity_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "runner_managed_runtime_continuity_proven": True,
        "historical_numpy": EXPECTED_NUMPY,
        "historical_scipy": EXPECTED_SCIPY,
        "gap_seconds_1340_end_to_1341_start": chain["gap_seconds_1340_end_to_1341_start"],
        "intervening_runner_jobs": 0,
        "next_stage": NEXT_STAGE,
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    runtime_atomic_json(art / "scientific-summary.json", summary)
    write_json(art / "manifest.json", {
        "schema": "jass.cls_hier_l2_1340_1341_runtime_continuity_manifest.v1",
        "terminal": TERMINAL,
        "diagnostic_only": True,
        "technical_runtime_receipts_read": 1,
        "scientific_payloads_read": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    })
    (art / "RESULTS.md").write_text(
        "# CLS HIER-L2 1340→1341 runtime continuity diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        "- runner-managed runtime continuity proven: `True`\n"
        f"- historical NumPy/SciPy: `{EXPECTED_NUMPY}` / `{EXPECTED_SCIPY}`\n"
        f"- 1340 end → 1341 start gap: `{chain['gap_seconds_1340_end_to_1341_start']}s`\n"
        "- intervening runner jobs: `0`\n"
        f"- next stage: `{NEXT_STAGE}`\n"
        "- scientific payload reads/fits/searches/games/targets/alpha/promotion/bake: `0`\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
