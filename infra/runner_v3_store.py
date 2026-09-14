#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import hmac
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from runner_v3_common import Config, run, utcnow, write_json


# The runner is a five-minute oneshot and must never be held indefinitely by a
# wedged object-store socket. These are rclone inactivity/connection bounds,
# not total transfer deadlines: healthy large uploads may continue for as long
# as bytes keep flowing. Internal rclone retries are deliberately minimized
# because RcloneResultStore already owns the bounded outer retry loop.
RCLONE_TRANSPORT_ARGS = (
    "--contimeout", "30s",
    "--timeout", "2m",
    "--retries", "1",
    "--low-level-retries", "2",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_files(root: Path) -> list[dict]:
    result = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"checksums.sha256", "_SUCCESS", "_FAILED"}:
            continue
        result.append({"path": str(path.relative_to(root)),
                       "size_bytes": path.stat().st_size,
                       "sha256": sha256_file(path)})
    return result


def write_checksums(root: Path, files: list[dict]) -> None:
    (root / "checksums.sha256").write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in files),
        encoding="utf-8")


def truncate_and_gzip(raw: Path, output: Path, max_bytes: int) -> None:
    data = b""
    if raw.exists():
        size = raw.stat().st_size
        with raw.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                data = b"...[truncated]...\n" + handle.read()
            else:
                data = handle.read()
    with gzip.open(output, "wb", compresslevel=6) as handle:
        handle.write(data)


def remote_join(base: str, *parts: str) -> str:
    return base.rstrip("/") + "/" + "/".join(p.strip("/") for p in parts if p)


def rclone_rcat_file(cfg: Config, source: Path, remote: str) -> subprocess.CompletedProcess:
    """Generic fallback for non-Cloudflare object stores."""
    with source.open("rb") as handle:
        return subprocess.run(
            [cfg.rclone_bin, "rcat", remote, *RCLONE_TRANSPORT_ARGS],
            stdin=handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def _sigv4_sign(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def cloudflare_r2_put_file(source: Path, remote: str) -> subprocess.CompletedProcess:
    """PUT one small object directly to Cloudflare R2 using AWS SigV4.

    CPX62 proved that rclone directory copy/check succeeds against the configured
    R2 endpoint, while three marker-only paths (copyto, one-file copy and rcat)
    return HTTP 501. The terminal marker is deliberately tiny and append-last,
    so use R2's supported S3 PutObject operation directly instead of another
    rclone transfer primitive. Credentials remain only in headers and are never
    included in returned diagnostics.
    """
    endpoint = os.environ.get("RCLONE_CONFIG_R2_ENDPOINT", "").rstrip("/")
    access_key = os.environ.get("RCLONE_CONFIG_R2_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("RCLONE_CONFIG_R2_SECRET_ACCESS_KEY", "")
    if not endpoint or not access_key or not secret_key:
        return subprocess.CompletedProcess([], 2, "", "missing Cloudflare R2 marker credentials")

    parsed_endpoint = urllib.parse.urlsplit(endpoint)
    if parsed_endpoint.scheme != "https" or not parsed_endpoint.netloc:
        return subprocess.CompletedProcess([], 2, "", "invalid Cloudflare R2 endpoint")
    if ":" not in remote:
        return subprocess.CompletedProcess([], 2, "", "invalid rclone remote")
    remote_path = remote.split(":", 1)[1].lstrip("/")
    bucket, separator, key = remote_path.partition("/")
    if not separator or not bucket or not key:
        return subprocess.CompletedProcess([], 2, "", "invalid R2 bucket/object path")

    payload = source.read_bytes()
    payload_hash = hashlib.sha256(payload).hexdigest()
    now = dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = os.environ.get("RCLONE_CONFIG_R2_REGION", "auto") or "auto"
    service = "s3"
    host = parsed_endpoint.netloc
    canonical_uri = "/" + urllib.parse.quote(bucket, safe="-_.~") + "/" + urllib.parse.quote(
        key, safe="/-_.~"
    )
    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = (
        "PUT\n" + canonical_uri + "\n\n" + canonical_headers + "\n" +
        signed_headers + "\n" + payload_hash
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n" + amz_date + "\n" + credential_scope + "\n" +
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )
    date_key = _sigv4_sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    region_key = _sigv4_sign(date_key, region)
    service_key = _sigv4_sign(region_key, service)
    signing_key = _sigv4_sign(service_key, "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    url = endpoint + canonical_uri
    request = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={
            "Authorization": authorization,
            "Host": host,
            "X-Amz-Content-Sha256": payload_hash,
            "X-Amz-Date": amz_date,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(getattr(response, "status", 200))
        if 200 <= status < 300:
            return subprocess.CompletedProcess([], 0, "", "")
        return subprocess.CompletedProcess([], 1, "", f"R2 PutObject HTTP {status}")
    except urllib.error.HTTPError as exc:
        return subprocess.CompletedProcess([], 1, "", f"R2 PutObject HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return subprocess.CompletedProcess([], 1, "", f"R2 PutObject {type(exc).__name__}")


def publish_terminal_marker(cfg: Config, source: Path, remote: str) -> subprocess.CompletedProcess:
    provider = os.environ.get("RCLONE_CONFIG_R2_PROVIDER", "").strip().lower()
    if provider == "cloudflare" and remote.startswith("r2:"):
        return cloudflare_r2_put_file(source, remote)
    return rclone_rcat_file(cfg, source, remote)


class ResultStore:
    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        raise NotImplementedError


class FilesystemResultStore(ResultStore):
    def __init__(self, root: Path):
        self.root = root

    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        destination = self.root / job_id / attempt_id
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run_dir, destination)
        (destination / ("_SUCCESS" if success else "_FAILED")).write_text(
            utcnow() + "\n", encoding="utf-8")
        return destination.as_uri()


class RcloneResultStore(ResultStore):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def publish(self, run_dir: Path, job_id: str, attempt_id: str, success: bool) -> str:
        remote = remote_join(self.cfg.objstore_remote, self.cfg.objstore_prefix,
                             job_id, attempt_id)
        marker_name = "_SUCCESS" if success else "_FAILED"
        marker = run_dir / marker_name
        marker.unlink(missing_ok=True)
        last_error = ""
        transport = list(RCLONE_TRANSPORT_ARGS)
        for attempt in range(1, self.cfg.upload_retries + 1):
            copy = run([self.cfg.rclone_bin, "copy", str(run_dir), remote,
                        "--checksum", "--immutable", *transport], check=False)
            if copy.returncode == 0:
                check = run([self.cfg.rclone_bin, "check", str(run_dir), remote,
                             "--one-way", "--checksum", *transport], check=False)
                if check.returncode == 0:
                    marker.write_text(utcnow() + "\n", encoding="utf-8")
                    final = publish_terminal_marker(
                        self.cfg, marker, remote_join(remote, marker_name)
                    )
                    if final.returncode == 0:
                        return remote
                    last_error = final.stderr or final.stdout
                else:
                    last_error = check.stderr or check.stdout
            else:
                last_error = copy.stderr or copy.stdout
            time.sleep(attempt * 2)
        raise RuntimeError(f"object-store publish failed: {last_error.strip()}")


def result_store(cfg: Config) -> ResultStore:
    return FilesystemResultStore(cfg.result_fs_root) if cfg.result_backend == "filesystem" else RcloneResultStore(cfg)


def prepare_run_dir(run_dir: Path, manifest: dict, max_log_bytes: int) -> None:
    raw = run_dir / "output.log.raw"
    truncate_and_gzip(raw, run_dir / "output.log.gz", max_log_bytes)
    raw.unlink(missing_ok=True)
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "inventory.json", {"files": inventory_files(run_dir)})
    write_checksums(run_dir, inventory_files(run_dir))
