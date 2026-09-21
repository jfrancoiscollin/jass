#!/usr/bin/env python3
"""Launch-V2, bounded raw historical audit. Never executes a search or a match."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools import cls_g0_panel_raw_audit as audit

CONTRACT = "docs/experiments/CLS_G0_REJECTION_PANEL_V1_20260920.json"
CONTRACT_BLOB = "19e39b457e86d6131d028d26b1dc0e6bac881b06"
BASE = "7b789a0c675ce08868fe4a8fcef0becaa4193286"
PHASES = ["authenticate-archives", "verify-native-continuity", "replay-2069",
          "audit-all-g0-roots", "publish-audit"]
TERMINAL = "CLS_G0_PANEL_HISTORICAL_RAW_AUDIT_COMPLETE_V1"
OUTPUTS = ["historical-2069-raw-audit.json", "source-and-model-authentication.json",
           "native-continuity.json", "historical-g0-all-roots.tsv", "g0-descriptive-summary.json",
           "historical-2069-position-identities.json", "progress.json", "scientific-summary.json",
           "manifest.json", "RESULTS.md"]
FLAGS = ["-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", "-DJASS_EGDB_SRC_DIR=/root/egdb_intl",
         "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON", "-DJASS_SCAN_PARITY=ON",
         "-DJASS_TEMPO_STAGE=ON", "-DJASS_TIME_BREAKDOWN=OFF"]


def put(path: Path, value: dict, *, replace: bool = False) -> None:
    audit.need(not path.is_symlink() and (replace or not path.exists()), "NO_CLOBBER")
    temp = path.with_name(path.name + ".tmp")
    with temp.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    temp.replace(path)


def put_final_summary(path: Path, value: dict, evidence) -> None:
    """Publish the final summary over this run's launch-progress placeholder.

    StageEvidence owns the placeholder it creates while a stage is running.  A
    completed or foreign summary remains immutable, even though this one
    publication is intentionally a replacement.
    """
    audit.need(not path.is_symlink() and path.exists(), "SUMMARY_OWNERSHIP")
    previous = audit.read(path)
    expected = evidence.value
    owned_keys = {"schema", "state", "phase", "snapshot_at", "completed_phases",
                  "scientific_verdict", "actual_side_effects"}
    expected_progress = {"schema": "jass.launch_progress.v2", "state": expected["state"],
                         "phase": expected["phase"], "snapshot_at": expected["snapshot_at"],
                         "completed_phases": expected["completed_phases"],
                         "scientific_verdict": None,
                         "actual_side_effects": expected["actual_side_effects"]}
    audit.need(path == evidence.path.parent / "scientific-summary.json", "SUMMARY_OWNERSHIP")
    audit.need(set(previous) == owned_keys and previous == expected_progress, "SUMMARY_OWNERSHIP")
    audit.need(previous["state"] == "running" and previous["phase"] == PHASES[-1] and
               previous["completed_phases"] == PHASES[:-1], "SUMMARY_OWNERSHIP")
    put(path, value, replace=True)


def env() -> dict:
    # No evaluator, time or search-policy variable is inherited by replay/build.
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
    out = {k: os.environ[k] for k in keep if k in os.environ}
    out.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONDONTWRITEBYTECODE="1")
    return out


def command(argv: list[str], log: Path, timeout: int, *, stdin: bytes | None = None) -> bytes:
    audit.need(not log.exists(), "LOG_NO_CLOBBER")
    with log.open("xb") as output:
        p = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                             stdout=output, stderr=subprocess.STDOUT, env=env(), start_new_session=True)
        try:
            p.communicate(stdin, timeout=timeout)
            audit.need(p.returncode == 0, "COMMAND_FAILED:" + log.name)
        finally:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait(timeout=10)
    audit.need(log.stat().st_size <= audit.RAW_LIMIT, "LOG_BOUND")
    return log.read_bytes()


def git_bytes(*args: str, repo: Path = ROOT) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30, check=False)
    audit.need(r.returncode == 0, "GIT_PROVENANCE_UNAVAILABLE")
    audit.need(len(r.stdout) <= audit.RAW_LIMIT, "GIT_PAYLOAD_BOUND")
    return r.stdout


def get_contract() -> dict:
    path = ROOT / CONTRACT
    raw = path.read_bytes()
    audit.need(audit.git_blob(raw) == CONTRACT_BLOB, "FROZEN_PANEL_CONTRACT_DRIFT")
    c = audit.decode(raw)
    audit.need(c["models"] == audit.MODELS and c["native_source_anchor"] == BASE, "PANEL_IDENTITY")
    audit.need(c["budget"]["read_only_audit_stage_seconds"] == 900 and c["budget"]["automatic_retries"] == 0, "AUDIT_BUDGET")
    return c


def fetch_source(work: Path, label: str, source: dict, names: list[str]) -> tuple[Path, dict]:
    from jobs.tools import fetch_result_files as transport
    prefix = f"r2:jass-data/runs/{source['job_id']}/{source['attempt_id']}"
    rclone = os.environ.get("RCLONE_BIN", "rclone")
    inv = transport.inspect_result_inventory(rclone=rclone, prefix=prefix)
    audit.need(tuple(inv[k] for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")) ==
               (source["job_id"], source["attempt_id"], source["code_sha"], "completed", 0), "SOURCE_ENVELOPE:" + label)
    files = {i["path"]: i for i in inv["files"]}
    audit.need(all(0 < files.get("artefacts/" + n, {}).get("size_bytes", 0) <= audit.RAW_LIMIT for n in names), "SOURCE_BOUND:" + label)
    out = work / label
    proof = transport.fetch_files(rclone=rclone, prefix=prefix, out_dir=out,
        selections=[("artefacts/" + n, n) for n in names])
    audit.need(all(audit.sha(out / n) == files["artefacts/" + n]["sha256"] for n in names), "LOCAL_ROUNDTRIP")
    if "receipt_sha256" in source:
        audit.need(audit.sha(out / "launch-receipt.json") == source["receipt_sha256"], "PINNED_RECEIPT:" + label)
    if "status_blob_sha" in source:
        control = Path(os.environ.get("JASS_CONTROL_REPO_DIR", "/srv/jass/control"))
        raw_status = git_bytes("cat-file", "blob", source["status_blob_sha"], repo=control)
        audit.need(audit.git_blob(raw_status) == source["status_blob_sha"], "STATUS_BLOB")
        status = audit.decode(raw_status)
        audit.need(tuple(status[k] for k in ("job_id", "attempt_id", "code_sha", "state", "exit_code")) ==
                   (source["job_id"], source["attempt_id"], source["code_sha"], "completed", 0), "PINNED_STATUS_IDENTITY")
        if "scientific-summary.json" in names:
            published = audit.read(out / "scientific-summary.json")
            snap = status["scientific_summaries"]["scientific-summary.json"]
            audit.need(all(published.get(k) == snap.get(k) for k in ("schema", "state", "terminal", "scientific_verdict")), "RAW_STATUS_SUMMARY_DRIFT")
        proof["pinned_status_blob_sha"] = source["status_blob_sha"]
    return out, proof


def authenticate(work: Path, c: dict, progress) -> tuple[dict, dict]:
    sources, proofs = {}, {}
    common_g0 = ["probe.tsv", "probe-report.json", "g0-root-ids.txt", "g0-deep512.tsv",
                 "scientific-summary.json", "source-authentication.json", "candidate-authentication.json", "launch-receipt.json"]
    groups = {
        "historical_match": ["stage-games.json.gz", "scientific-summary.json", "study-report.json", "opening-freeze.json",
                             "runtime-identity.json", "manifest.json", "launch-receipt.json", "source-authentication.json", "execution-evidence.json"],
        "valid_arms": ["LOCAL.pjtw.gz", "WDL.pjtw.gz", "scientific-summary.json", "launch-receipt.json",
                       "LOCAL-fit-receipt.json", "WDL-fit-receipt.json"],
        "curriculum": [c["sources"]["curriculum"]["artifact"]],
        "local_g0": common_g0,
        "wdl_g0": common_g0,
    }
    for label, names in groups.items():
        sources[label], proofs[label] = fetch_source(work, label, c["sources"][label], names)
        progress({"phase": "authenticate-archives", "authenticated_sources": len(sources), "new_games": 0})
    proofs["models"] = {}
    fit_summary = audit.read(sources["valid_arms"] / "scientific-summary.json")
    audit.need(fit_summary.get("terminal") == "CLS_L_VALID_ARMS_RECOVERED_V1", "VALID_ARMS_TERMINAL")
    for arm in ("LOCAL", "WDL", "CURRICULUM"):
        if arm == "CURRICULUM":
            src = sources["curriculum"] / c["sources"]["curriculum"]["artifact"]
        else:
            src = sources["valid_arms"] / (arm + ".pjtw.gz")
            audit.need(fit_summary["arms"][arm]["model_sha256"] == audit.MODELS[arm], "FIT_MODEL_IDENTITY")
        proofs["models"][arm] = audit.unpack_model(src, work / (arm + ".pjtw"), audit.MODELS[arm])
    match = sources["historical_match"]
    summary = audit.read(match / "scientific-summary.json")
    audit.need(summary.get("terminal") == c["sources"]["historical_match"]["expected_terminal"] and
               summary.get("scientific_verdict") == c["sources"]["historical_match"]["expected_verdict"] and
               summary.get("frozen_g0_verdict") == "FAIL", "HISTORICAL_RESULT")
    manifest = audit.read(match / "manifest.json")
    for name in ("stage-games.json.gz", "opening-freeze.json", "study-report.json"):
        audit.need(manifest["output_sha256"].get(name) == audit.sha(match / name), "INNER_MANIFEST:" + name)
    audit.need(manifest["models"] == summary["models"] and
               manifest["selection_sha256"] == summary["opening_selection_sha256"], "INNER_MANIFEST_IDENTITY")
    proofs["authenticated"] = True
    proofs["scope"] = "historical_archives_only_no_new_game_or_search"
    return sources, proofs


def continuity(work: Path, c: dict, runtime: dict) -> tuple[Path, dict]:
    native_paths = ["src", "pattern_jass", "CMakeLists.txt"]
    baseline = git_bytes("ls-tree", BASE, "--", *native_paths)
    refs = [BASE, c["sources"]["local_g0"]["code_sha"], c["sources"]["wdl_g0"]["code_sha"],
            c["sources"]["historical_match"]["code_sha"], "HEAD"]
    identities = {}
    for ref in refs:
        tree = git_bytes("ls-tree", ref, "--", *native_paths)
        audit.need(tree == baseline, "NATIVE_TREE_DRIFT:" + ref)
        identities[ref] = tree.decode()
    # G0 build recipe and probe bytes must be unchanged since the two G0 jobs.
    g0_paths = ["jobs/tools/cls_depth_growth_stage.py", "jobs/tools/cls_g0_runtime_preflight_stage.py",
               "jobs/tools/cls_g0_runtime_probe.cpp"]
    for path in g0_paths:
        expected = git_bytes("show", BASE + ":" + path)
        for label in ("local_g0", "wdl_g0"):
            audit.need(git_bytes("show", c["sources"][label]["code_sha"] + ":" + path) == expected, "G0_BUILD_OR_PROBE_DRIFT")
    build_recipe = git_bytes("show", BASE + ":jobs/tools/cls_depth_growth_stage.py").decode()
    for flag in FLAGS:
        if flag.startswith(("-DJASS_EGDB_SRC_DIR=", "-DJASS_TIME_BREAKDOWN=")):
            continue
        audit.need(flag in build_recipe, "G0_COMPILE_OPTION")
    audit.need("{'ON' if profile else 'OFF'}" in build_recipe, "G0_PARITY_PROFILE_OPTION")
    historical = git_bytes("show", c["sources"]["historical_match"]["code_sha"] + ":jobs/tools/cls_g0_strength_calibration.py")
    live_helper = (ROOT / "jobs/tools/cls_g0_strength_calibration.py").read_bytes()
    audit.need(historical == live_helper, "HISTORICAL_MATCH_BUILD_RECIPE_DRIFT")
    expected_runtime = {"models": {k: audit.MODELS[k] for k in ("CURRICULUM", "HIER")},
        "native_source": BASE, "movetime_ms": 100, "response_limit_ms": 120,
        "warmup": "startpos_depth1_each_player_then_reset", "book": False,
        "threads": 1, "tt_mb": 16, "egdb_cache_mb": 256, "workers": 4}
    audit.need(all(runtime.get(k) == v for k, v in expected_runtime.items()), "HISTORICAL_RUNTIME_IDENTITY")
    build = work / "build"
    command(["/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles", *FLAGS],
            work / "configure.log", 180)
    command(["/usr/bin/cmake", "--build", str(build), "--target", "jass", "-j", "4"], work / "build.log", 480)
    exe = build / "jass"
    audit.need(exe.is_file(), "REPLAY_BINARY_MISSING")
    # Same host/toolchain/source/options should reproduce the recorded match binary.
    audit.need(audit.sha(exe) == runtime["binary_sha256"], "REBUILT_MATCH_BINARY_DRIFT")
    return exe, {"schema": "jass.cls_panel_native_continuity.v1", "passed": True,
        "native_tree_identities": identities, "matched_paths": native_paths,
        "g0_probe_and_build_paths_unchanged": g0_paths, "match_cmake_flags": FLAGS,
        "rebuilt_binary_sha256": audit.sha(exe), "historical_match_runtime": runtime,
        "comparison_limit": "same_native_semantics; historical_fixed_nodes_and_fixed_time_envelopes_remain_distinct",
        "replay_only_commands": ["hello", "position fen", "apply exact-captures", "fen", "quit", "--perft 1"]}


def replay_native(exe: Path, work: Path, games: list[dict], metas: list[dict], progress) -> list[int]:
    audit.need(len(games) == len(metas) > 0, "REPLAY_INPUT_COVERAGE")
    commands, expected = ["hello"], []
    for game, meta in zip(games, metas):
        audit.fen_state(game["opening"])
        commands.extend(["position fen " + game["opening"], "fen"])
        expected.extend(["ok", audit.fen_state(game["opening"])])
        for move, fen in zip(meta["exact_moves"], game["fens"][1:]):
            audit.exact_move(move)
            audit.fen_state(fen)
            commands.extend(["apply " + move, "fen"])
            expected.extend(["ok", audit.fen_state(fen)])
    commands.append("quit")
    payload = ("\n".join(commands) + "\n").encode()
    audit.need(len(payload) <= audit.RAW_LIMIT and not any(line.startswith(("go", "eval", "neteval")) for line in commands), "REPLAY_NO_SEARCH")
    output = command([str(exe), "--no-nnue", "--no-book"], work / "native-replay.log", 180, stdin=payload)
    actual, ready = [], 0
    for line in output.decode().splitlines():
        audit.need(not line.startswith(("error", "bestmove")), "NATIVE_REPLAY_FAILURE")
        if line.startswith("ready"):
            ready += 1
        elif line == "ok":
            actual.append(line)
        elif line.startswith("fen "):
            actual.append(audit.fen_state(line[4:].strip()))
    audit.need(ready == 1 and actual == expected, "NATIVE_REPLAY_TRAJECTORY_MISMATCH")
    progress({"phase": "native-terminal-checks", "historical_games_replayed": len(games),
              "historical_moves_replayed": sum(len(m["exact_moves"]) for m in metas), "new_searches": 0})
    unique = list(dict.fromkeys(g["fens"][-1] for g in games))
    def terminal(item):
        i, fen = item
        audit.fen_state(fen)
        raw = command([str(exe), "--perft", "1", fen], work / f"terminal-{i:04d}.log", 30)
        found = re.findall(rb"perft\(1\)\s*=\s*([0-9]+)", raw)
        audit.need(len(found) == 1, "TERMINAL_LEGALITY_OUTPUT")
        return fen, int(found[0])
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = dict(pool.map(terminal, enumerate(unique)))
    return [counts[g["fens"][-1]] for g in games]


def run(work: Path, art: Path, evidence, c: dict) -> dict:
    def progress(value):
        put(art / "progress.json", value, replace=True)
    evidence.begin(PHASES[0])
    sources, proof = authenticate(work, c, progress)
    put(art / "source-and-model-authentication.json", proof)
    evidence.complete()
    match = sources["historical_match"]
    evidence.begin(PHASES[1])
    exe, native = continuity(work, c, audit.read(match / "runtime-identity.json"))
    put(art / "native-continuity.json", native)
    evidence.complete()
    evidence.begin(PHASES[2])
    raw = audit.read(match / "stage-games.json.gz")
    seal = audit.read(match / "opening-freeze.json")
    summary = audit.read(match / "scientific-summary.json")
    result = audit.audit_match(raw, seal, summary,
        lambda games, metas: replay_native(exe, work, games, metas, progress), progress)
    published_readout = audit.read(match / "study-report.json")
    audit.need(all(published_readout.get(k) == summary.get(k) for k in result["recomputed_original_readout"]), "REPORT_SUMMARY_DRIFT")
    put(art / "historical-2069-raw-audit.json", result)
    identities = sorted({audit.canonical_identity(f) for p in raw["pairs"] for g in p["games"] for f in g["fens"]})
    put(art / "historical-2069-position-identities.json", {"source": c["sources"]["historical_match"],
        "canonical_identities": identities, "identity_list_sha256": audit.digest(identities)})
    evidence.complete()
    evidence.begin(PHASES[3])
    all_rows, descriptions = [], {}
    for arm, label in (("LOCAL", "local_g0"), ("WDL", "wdl_g0")):
        directory = sources[label]
        s = audit.read(directory / "scientific-summary.json")
        roots = (directory / "g0-root-ids.txt").read_text().splitlines()
        rows, desc = audit.g0_rows(arm, audit.tsv(directory / "probe.tsv"), roots,
            audit.tsv(directory / "g0-deep512.tsv"), audit.read(directory / "probe-report.json"), s)
        candidate = audit.read(directory / "candidate-authentication.json")
        audit.need(candidate.get("model_sha256") == audit.MODELS[arm] and candidate.get("job_id") == c["sources"]["valid_arms"]["job_id"], "G0_CANDIDATE_AUTHENTICATION")
        all_rows.extend(rows)
        descriptions[arm] = desc
    with (art / "historical-g0-all-roots.tsv").open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)
    put(art / "g0-descriptive-summary.json", descriptions)
    evidence.complete()
    evidence.begin(PHASES[4])
    progress({"phase": "completed", "historical_games_replayed": 576, "g0_roots_checked": 1024,
              "new_games": 0, "new_searches": 0})
    summary = {"schema": "jass.cls_g0_panel_historical_audit.v1", "state": "completed", "terminal": TERMINAL,
        "scientific_verdict": None, "classification": "HISTORICAL_RAW_AUDIT_ONLY",
        "historical_2069_raw_audit_passed": True, "historical_games_replayed": 576,
        "historical_requests_verified": result["historical_requests_verified"],
        "historical_moves_replayed": result["native_moves_replayed"], "g0_roots_checked": 1024,
        "native_continuity_passed": True, "models": audit.MODELS, "contract_blob_sha": CONTRACT_BLOB,
        "g0_descriptive": descriptions, "frozen_g0_verdicts": {a: "FAIL" for a in ("LOCAL", "WDL", "HIER")},
        "actual_side_effects": evidence.value["actual_side_effects"], "alpha_spent": 0,
        "promotion_authorized": False, "bake_authorized": False, "new_games": 0, "new_jass_searches": 0,
        "main_match_admitted": False, "next_stage": "IMPLEMENT_FROZEN_PANEL_READINESS_NO_AUTOMATIC_MATCH"}
    put_final_summary(art / "scientific-summary.json", summary, evidence)
    (art / "RESULTS.md").write_text("# CLS panel independent historical audit\n\n" + json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    put(art / "manifest.json", {"schema": "jass.cls_panel_audit_manifest.v1", "contract_blob_sha": CONTRACT_BLOB,
        "output_sha256": {name: audit.sha(art / name) for name in OUTPUTS if name != "manifest.json"}})
    evidence.complete()
    evidence.finish()
    return summary


def main() -> int:
    from jobs.tools.launch_runtime_v2 import StageEvidence
    result = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    work = result / "work" / "panel-raw-audit"
    audit.need(not work.resolve().is_relative_to(ROOT.resolve()), "SCRATCH_OUTSIDE_REPO")
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, os.environ["LAUNCH_MODE"])
    try:
        audit.need(socket.gethostname().split(".")[0] == "cpx62" and len(os.sched_getaffinity(0)) == 16, "HOST_RESOURCES")
        audit.need(shutil.disk_usage(work).free >= 3 * 1024**3, "FREE_DISK_GUARD")
        run(work, art, evidence, get_contract())
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        log_tails = {}
        for path in sorted(work.glob("*.log")):
            if path.is_file() and not path.is_symlink():
                with path.open("rb") as f:
                    f.seek(max(0, path.stat().st_size - 8192))
                    log_tails[path.name] = f.read(8192).decode("utf-8", errors="replace")
                if len(log_tails) >= 12:
                    break
        put(art / "audit-failure.json", {"classification": "TECHNICAL_OR_AUDIT_DISCREPANCY",
            "error": str(exc), "main_match_admitted": False, "historical_result_changed": False,
            "bounded_owned_log_tails": log_tails})
        raise


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt("TERMINATED")
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
