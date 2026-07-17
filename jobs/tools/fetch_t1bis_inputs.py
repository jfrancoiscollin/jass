#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Download and verify immutable ADJ+G1 probe inputs from R2.

T1-bis consumes the immutable baseline bundle. T2 and T3 consume the same
bundle, but replace only ``parent_pattern`` with the promoted candidate from
the previous completed runner-v3 result. The previous run is accepted only
when its marker, manifest, inventory, checksums and promotion verdict are
coherent. The fixed T0 reference, generation seed corpus, G1 pool and
conversion gauge therefore remain frozen across the bounded probe.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_ROLES = {
    "parent_pattern",
    "fixed_pattern",
    "gen2_pattern",
    "seed_corpus",
    "g1_pool",
    "conversion_gauge",
}
PROBE_PREDECESSOR = {"T1-bis": None, "T2": "T1-bis", "T3": "T2"}
CANDIDATE_PATH = "artefacts/candidate.pjtw.gz"
PROMOTION_PATH = "artefacts/promotion.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_gzip_payload(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size <= 0:
        raise RuntimeError(f"empty gzip payload: {path}")
    return digest.hexdigest(), size


def run_capture(args: list[str]) -> bytes:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        tail = proc.stderr[-1000:].decode("utf-8", "replace")
        raise RuntimeError(f"command failed rc={proc.returncode}: {args[0]} …; {tail}")
    return proc.stdout


def remote_bytes(rclone: str, remote: str) -> bytes:
    raw = run_capture([rclone, "cat", remote])
    if not raw:
        raise RuntimeError(f"empty remote object: {remote}")
    return raw


def remote_json(rclone: str, remote: str) -> tuple[dict, bytes]:
    raw = remote_bytes(rclone, remote)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"remote JSON is not an object: {remote}")
    return value, raw


def download_verified(
    rclone: str,
    remote: str,
    local: Path,
    expected_hash: str,
    expected_size: int,
) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    local.unlink(missing_ok=True)
    proc = subprocess.run(
        [
            rclone,
            "copyto",
            remote,
            str(local),
            "--checksum",
            "--retries",
            "8",
            "--low-level-retries",
            "10",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        tail = proc.stderr[-1000:].decode("utf-8", "replace")
        raise RuntimeError(f"download failed: {remote}; {tail}")
    if not local.is_file():
        raise RuntimeError(f"download did not create file: {remote}")
    size = local.stat().st_size
    digest = sha256_file(local)
    if size != expected_size or digest != expected_hash:
        local.unlink(missing_ok=True)
        raise RuntimeError(
            f"download verification failed: {remote}; got={size}/{digest} "
            f"expected={expected_size}/{expected_hash}"
        )


def resolve_prefix(cli_prefix: str | None) -> str:
    if cli_prefix:
        return cli_prefix.rstrip("/")
    base = os.environ.get("JASS_OBJSTORE_REMOTE", "").rstrip("/")
    if not base:
        raise RuntimeError("--remote-prefix or JASS_OBJSTORE_REMOTE is required")
    return base + "/inputs/t1bis-adj-g1/v1"


def resolve_manifest_name(success: dict) -> str:
    name = str(success.get("manifest_name") or "manifest.json")
    if not name or Path(name).name != name or name in {".", "..", "_SUCCESS"}:
        raise RuntimeError(f"unsafe manifest name in _SUCCESS: {name!r}")
    return name


def parse_checksums(raw: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line:
            continue
        try:
            digest, path = line.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError(f"malformed checksums line {lineno}") from exc
        if len(digest) != 64 or path in result or not path:
            raise RuntimeError(f"invalid checksums entry line {lineno}")
        result[path] = digest
    if not result:
        raise RuntimeError("empty checksums.sha256")
    return result


def inventory_map(inventory: dict) -> dict[str, dict]:
    files = inventory.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("result inventory has no files")
    result: dict[str, dict] = {}
    for item in files:
        if not isinstance(item, dict):
            raise RuntimeError("invalid result inventory entry")
        path = str(item.get("path", ""))
        digest = str(item.get("sha256", ""))
        size = int(item.get("size_bytes", 0))
        if not path or path.startswith("/") or ".." in Path(path).parts:
            raise RuntimeError(f"unsafe result path: {path!r}")
        # size == 0 est legal dans un run_dir reel (ex. job.lock du launcher) ;
        # les objets requis sont verifies non-vides plus bas.
        if path in result or len(digest) != 64 or size < 0:
            raise RuntimeError(f"invalid result inventory metadata: {path!r}")
        result[path] = {"sha256": digest, "size_bytes": size}
    return result


def verify_result_identity(prefix: str, manifest: dict) -> None:
    job_id = str(manifest.get("job_id", ""))
    attempt_id = str(manifest.get("attempt_id", ""))
    if not job_id or not attempt_id:
        raise RuntimeError("previous run manifest misses job_id/attempt_id")
    expected_suffix = f"/{job_id}/{attempt_id}"
    if not prefix.rstrip("/").endswith(expected_suffix):
        raise RuntimeError(
            f"previous run prefix does not match manifest identity: expected suffix {expected_suffix}"
        )
    if manifest.get("state") != "completed" or int(manifest.get("exit_code", -1)) != 0:
        raise RuntimeError("previous runner-v3 result is not completed with exit_code=0")


def fetch_promoted_parent(
    *,
    rclone: str,
    prefix: str,
    out_dir: Path,
    expected_tour: str,
) -> dict:
    prefix = prefix.rstrip("/")
    remote_bytes(rclone, prefix + "/_SUCCESS")

    manifest, manifest_raw = remote_json(rclone, prefix + "/manifest.json")
    verify_result_identity(prefix, manifest)

    inventory, inventory_raw = remote_json(rclone, prefix + "/inventory.json")
    checksums_raw = remote_bytes(rclone, prefix + "/checksums.sha256")
    checksums = parse_checksums(checksums_raw)
    files = inventory_map(inventory)

    inventory_digest = hashlib.sha256(inventory_raw).hexdigest()
    if checksums.get("inventory.json") != inventory_digest:
        raise RuntimeError("inventory.json digest differs from checksums.sha256")

    manifest_meta = files.get("manifest.json")
    if manifest_meta is None:
        raise RuntimeError("manifest.json absent from result inventory")
    if (
        manifest_meta["sha256"] != hashlib.sha256(manifest_raw).hexdigest()
        or manifest_meta["size_bytes"] != len(manifest_raw)
        or checksums.get("manifest.json") != manifest_meta["sha256"]
    ):
        raise RuntimeError("manifest.json metadata is inconsistent")

    for required in (CANDIDATE_PATH, PROMOTION_PATH):
        meta = files.get(required)
        if meta is None:
            raise RuntimeError(f"{required} absent from previous result inventory")
        if meta["size_bytes"] <= 0:
            raise RuntimeError(f"{required} is empty in previous result inventory")
        if checksums.get(required) != meta["sha256"]:
            raise RuntimeError(f"{required} digest differs between inventory and checksums")

    candidate_tmp = out_dir / ".parent-from-previous-run.pjtw.gz"
    promotion_tmp = out_dir / ".previous-promotion.json"
    download_verified(
        rclone,
        prefix + "/" + CANDIDATE_PATH,
        candidate_tmp,
        files[CANDIDATE_PATH]["sha256"],
        files[CANDIDATE_PATH]["size_bytes"],
    )
    download_verified(
        rclone,
        prefix + "/" + PROMOTION_PATH,
        promotion_tmp,
        files[PROMOTION_PATH]["sha256"],
        files[PROMOTION_PATH]["size_bytes"],
    )

    promotion = json.loads(promotion_tmp.read_text(encoding="utf-8"))
    if not isinstance(promotion, dict):
        raise RuntimeError("previous promotion manifest is not an object")
    if promotion.get("tour") != expected_tour:
        raise RuntimeError(
            f"previous promotion tour mismatch: {promotion.get('tour')!r} != {expected_tour!r}"
        )
    if promotion.get("promotion_decision") != "promote":
        raise RuntimeError("previous candidate was not promoted")
    if promotion.get("scientific_status") != "continue_probe":
        raise RuntimeError("previous promotion does not authorize another probe tour")

    payload_sha256, payload_size = sha256_gzip_payload(candidate_tmp)
    declared_payload_sha = promotion.get("candidate_sha")
    if declared_payload_sha not in (None, "", "...") and declared_payload_sha != payload_sha256:
        raise RuntimeError("previous promotion candidate_sha differs from candidate payload")

    target = out_dir / "parent.pjtw.gz"
    os.replace(candidate_tmp, target)
    promotion_tmp.unlink(missing_ok=True)
    return {
        "source": "promoted_runner_v3_result",
        "run_prefix": prefix,
        "job_id": manifest["job_id"],
        "attempt_id": manifest["attempt_id"],
        "code_sha": manifest.get("code_sha"),
        "previous_tour": expected_tour,
        "promotion_decision": promotion["promotion_decision"],
        "scientific_status": promotion["scientific_status"],
        "candidate_object_path": CANDIDATE_PATH,
        "candidate_object_sha256": files[CANDIDATE_PATH]["sha256"],
        "candidate_object_size_bytes": files[CANDIDATE_PATH]["size_bytes"],
        "candidate_payload_sha256": payload_sha256,
        "candidate_payload_size_bytes": payload_size,
    }


def validate_probe_chain(tour: str, parent_run_prefix: str | None) -> str | None:
    if tour not in PROBE_PREDECESSOR:
        raise RuntimeError(f"unsupported probe tour: {tour!r}")
    predecessor = PROBE_PREDECESSOR[tour]
    if predecessor is None:
        if parent_run_prefix:
            raise RuntimeError("T1-bis must use the frozen baseline parent, not a previous run")
        return None
    if not parent_run_prefix:
        raise RuntimeError(f"{tour} requires --parent-run-prefix / PROBE_PARENT_RUN_PREFIX")
    return predecessor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-prefix")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rclone-bin", default=os.environ.get("RCLONE_BIN", "rclone"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--tour", default=os.environ.get("TOUR", "T1-bis"))
    parser.add_argument(
        "--parent-run-prefix",
        default=os.environ.get("PROBE_PARENT_RUN_PREFIX"),
        help="runner-v3 result prefix whose promoted candidate becomes the next parent",
    )
    args = parser.parse_args(argv)

    predecessor = validate_probe_chain(args.tour, args.parent_run_prefix)
    prefix = resolve_prefix(args.remote_prefix)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    success, _ = remote_json(args.rclone_bin, prefix + "/_SUCCESS")
    if success.get("state") != "completed" or success.get("dataset") != "t1bis-adj-g1-inputs":
        raise RuntimeError("T1-bis input marker is not completed")
    if success.get("version") != "v1":
        raise RuntimeError(f"unsupported T1-bis input version: {success.get('version')!r}")

    manifest_name = resolve_manifest_name(success)
    manifest_raw = remote_bytes(args.rclone_bin, prefix + "/" + manifest_name)
    manifest_hash = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_hash != success.get("manifest_sha256"):
        raise RuntimeError("manifest digest differs from _SUCCESS")
    if len(manifest_raw) != int(success.get("manifest_size_bytes", -1)):
        raise RuntimeError("manifest size differs from _SUCCESS")
    manifest = json.loads(manifest_raw)
    objects = manifest.get("objects")
    if not isinstance(objects, list) or not objects:
        raise RuntimeError("input manifest has no objects")

    roles = [str(item.get("role")) for item in objects]
    if set(roles) != REQUIRED_ROLES or len(roles) != len(REQUIRED_ROLES):
        raise RuntimeError(f"input role set mismatch: {sorted(roles)}")

    files: dict[str, str] = {}
    verified: list[dict] = []
    baseline_parent: dict | None = None
    for item in objects:
        role = str(item["role"])
        name = str(item["target_name"])
        if Path(name).name != name:
            raise RuntimeError(f"unsafe target name: {name}")
        remote = str(item["remote"])
        if not remote.startswith(prefix + "/files/"):
            raise RuntimeError(f"object outside input prefix: {remote}")
        expected_hash = str(item["sha256"])
        expected_size = int(item["size_bytes"])
        if len(expected_hash) != 64 or expected_size <= 0:
            raise RuntimeError(f"invalid manifest metadata for role={role}")
        local = out_dir / name
        download_verified(args.rclone_bin, remote, local, expected_hash, expected_size)
        files[role] = str(local)
        entry = {
            "role": role,
            "path": str(local),
            "size_bytes": expected_size,
            "sha256": expected_hash,
            "source_commit": item.get("source_commit"),
            "source_blob": item.get("source_blob"),
            "source": "frozen_baseline_bundle",
        }
        verified.append(entry)
        if role == "parent_pattern":
            baseline_parent = dict(entry)

    parent_chain = {
        "source": "frozen_baseline_bundle",
        "tour": args.tour,
        "previous_tour": None,
    }
    if predecessor is not None:
        parent_chain = fetch_promoted_parent(
            rclone=args.rclone_bin,
            prefix=str(args.parent_run_prefix),
            out_dir=out_dir,
            expected_tour=predecessor,
        )
        parent_chain["tour"] = args.tour
        final_parent = out_dir / "parent.pjtw.gz"
        for entry in verified:
            if entry["role"] == "parent_pattern":
                entry.update(
                    {
                        "path": str(final_parent),
                        "size_bytes": parent_chain["candidate_object_size_bytes"],
                        "sha256": parent_chain["candidate_object_sha256"],
                        "source_commit": parent_chain.get("code_sha"),
                        "source_blob": None,
                        "source": "promoted_runner_v3_result",
                        "payload_sha256": parent_chain["candidate_payload_sha256"],
                    }
                )
                break

    report = {
        "schema": 2,
        "state": "verified",
        "tour": args.tour,
        "remote_prefix": prefix,
        "source_commit": manifest.get("source_commit"),
        "manifest_name": manifest_name,
        "manifest_sha256": manifest_hash,
        "files": files,
        "objects": verified,
        "baseline_parent": baseline_parent,
        "parent_chain": parent_chain,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_path = args.report or (out_dir / "verified-inputs.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
