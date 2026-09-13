#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Restricted local control plane for Jass CPX hosts.

This deliberately exposes a tiny allow-listed API. There is no arbitrary shell
or command endpoint. Bind to loopback by default and put an authenticated
transport/tunnel in front of it before remote use.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RUNNER_UNIT = "jass-runner-v3.service"
JOB_UNIT_RE = re.compile(r"^jass-job-[0-9a-f]{20}\.service$")
DEFAULT_TOKEN_FILE = Path("/etc/jass-control-plane/token")
DEFAULT_AUDIT_FILE = Path("/var/lib/jass-control-plane/audit.jsonl")
MAX_LOG_LINES = 500


def run(argv: list[str], timeout: int = 20) -> dict:
    p = subprocess.run(argv, text=True, capture_output=True, check=False, timeout=timeout)
    return {
        "argv": argv,
        "returncode": p.returncode,
        "stdout": p.stdout[-50000:],
        "stderr": p.stderr[-12000:],
    }


def read_token(path: Path) -> str:
    token = os.environ.get("JASS_CONTROL_TOKEN", "").strip()
    if token:
        return token
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"control token unavailable: {path}: {exc}") from exc
    if len(token) < 32:
        raise RuntimeError("control token must contain at least 32 characters")
    return token


def systemctl_state(unit: str) -> dict:
    show = run([
        "systemctl", "show", unit,
        "--property=Id,ActiveState,SubState,Result,MainPID,ExecMainStatus,StateChangeTimestamp",
        "--no-pager",
    ])
    props: dict[str, str] = {}
    for line in show["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return {"unit": unit, "returncode": show["returncode"], "properties": props}


def list_jobs() -> list[dict]:
    p = run([
        "systemctl", "list-units", "--all", "--type=service",
        "--no-legend", "--no-pager", "jass-job-*.service",
    ])
    jobs = []
    for line in p["stdout"].splitlines():
        cols = line.split()
        if not cols:
            continue
        unit = cols[0]
        if JOB_UNIT_RE.fullmatch(unit):
            jobs.append(systemctl_state(unit))
    return jobs


def audit(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": int(time.time()), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "JassControlPlane/1"

    @property
    def cfg(self):
        return self.server.cfg  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        body = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.cfg['token']}"
        return hmac.compare_digest(header, expected)

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        audit(self.cfg["audit"], {"action": "auth_failed", "path": self.path, "peer": self.client_address[0]})
        self._json(401, {"ok": False, "error": "unauthorized"})
        return False

    def _body(self) -> dict:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length")
        if size < 0 or size > 8192:
            raise ValueError("request body too large")
        if not size:
            return {}
        raw = self.rfile.read(size)
        obj = json.loads(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("JSON body must be an object")
        return obj

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "jass-control-plane", "version": 1})
            return
        if not self._require_auth():
            return
        if parsed.path == "/v1/status":
            payload = {
                "ok": True,
                "host": os.uname().nodename,
                "runner": systemctl_state(RUNNER_UNIT),
                "jobs": list_jobs(),
            }
            self._json(200, payload)
            return
        if parsed.path == "/v1/logs":
            q = parse_qs(parsed.query)
            try:
                lines = max(1, min(MAX_LOG_LINES, int(q.get("lines", ["100"])[0])))
            except ValueError:
                self._json(400, {"ok": False, "error": "invalid lines"})
                return
            unit = q.get("unit", [RUNNER_UNIT])[0]
            if unit != RUNNER_UNIT and not JOB_UNIT_RE.fullmatch(unit):
                self._json(400, {"ok": False, "error": "unit not allowed"})
                return
            result = run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso-precise"])
            self._json(200, {"ok": result["returncode"] == 0, "unit": unit, "result": result})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        try:
            body = self._body()
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/v1/runner/restart":
            result = run(["systemctl", "restart", RUNNER_UNIT], timeout=120)
            audit(self.cfg["audit"], {"action": "runner_restart", "ok": result["returncode"] == 0})
            self._json(200 if result["returncode"] == 0 else 500, {"ok": result["returncode"] == 0, "result": result})
            return

        if parsed.path == "/v1/job/kill":
            unit = str(body.get("unit", ""))
            if not JOB_UNIT_RE.fullmatch(unit):
                self._json(400, {"ok": False, "error": "job unit not allowed"})
                return
            result = run(["systemctl", "kill", "--kill-who=all", "--signal=TERM", unit])
            audit(self.cfg["audit"], {"action": "job_kill", "unit": unit, "ok": result["returncode"] == 0})
            self._json(200 if result["returncode"] == 0 else 500, {"ok": result["returncode"] == 0, "unit": unit, "result": result})
            return

        if parsed.path == "/v1/server/reboot":
            if not self.cfg["allow_reboot"]:
                self._json(403, {"ok": False, "error": "reboot disabled"})
                return
            if self.headers.get("X-Jass-Confirm", "") != "REBOOT":
                self._json(400, {"ok": False, "error": "missing reboot confirmation"})
                return
            audit(self.cfg["audit"], {"action": "server_reboot", "ok": True})
            self._json(202, {"ok": True, "accepted": "reboot"})
            subprocess.Popen(["systemctl", "reboot", "--no-wall"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        self._json(404, {"ok": False, "error": "not found"})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bind", default=os.environ.get("JASS_CONTROL_BIND", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("JASS_CONTROL_PORT", "8765")))
    p.add_argument("--token-file", type=Path, default=Path(os.environ.get("JASS_CONTROL_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))))
    p.add_argument("--audit-file", type=Path, default=Path(os.environ.get("JASS_CONTROL_AUDIT_FILE", str(DEFAULT_AUDIT_FILE))))
    args = p.parse_args()
    cfg = {
        "token": read_token(args.token_file),
        "audit": args.audit_file,
        "allow_reboot": os.environ.get("JASS_CONTROL_ALLOW_REBOOT", "0") == "1",
    }
    server = ThreadingHTTPServer((args.bind, args.port), ControlHandler)
    server.cfg = cfg  # type: ignore[attr-defined]
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
