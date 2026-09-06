#!/usr/bin/env python3
"""Maintain Jass' machine-readable technical-incident ledger and generated register.

The ledger is canonical. The Markdown table is generated and must never be edited by
hand. Technical-fix PRs can carry a ``JASS_TECHNICAL_INCIDENT`` JSON block; CI calls
``sync-pr`` and commits the resulting ledger/register update back to same-repo branches.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "docs/operations/TECHNICAL_INCIDENTS_V1.json"
DEFAULT_REGISTER = ROOT / "docs/operations/TECHNICAL_INCIDENT_REGISTER_V1_20260906.md"
SCHEMA = "jass.technical_incident_ledger.v1"
TABLE_START = "<!-- GENERATED_TECHNICAL_INCIDENT_TABLE_START -->"
TABLE_END = "<!-- GENERATED_TECHNICAL_INCIDENT_TABLE_END -->"
PR_BLOCK_START = "<!-- JASS_TECHNICAL_INCIDENT"
PR_BLOCK_END = "JASS_TECHNICAL_INCIDENT -->"
REQUIRED = ("dedupe_key", "context", "symptom", "root_cause", "invariant", "evidence", "status")
ID_RE = re.compile(r"TI-(\d{3})\Z")


class IncidentError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IncidentError(f"{label} must be a non-empty string")
    if "\x00" in value:
        raise IncidentError(f"{label} contains NUL")
    return value.strip()


def validate_ledger(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise IncidentError(f"ledger schema must be {SCHEMA}")
    incidents = value.get("incidents")
    if not isinstance(incidents, list):
        raise IncidentError("ledger incidents must be a list")

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    numbers: list[int] = []
    for index, item in enumerate(incidents):
        if not isinstance(item, dict):
            raise IncidentError(f"incident[{index}] must be an object")
        incident_id = _nonempty(item.get("id"), f"incident[{index}].id")
        match = ID_RE.fullmatch(incident_id)
        if match is None:
            raise IncidentError(f"invalid incident id {incident_id!r}")
        if incident_id in seen_ids:
            raise IncidentError(f"duplicate incident id {incident_id}")
        seen_ids.add(incident_id)
        numbers.append(int(match.group(1)))
        key = _nonempty(item.get("dedupe_key"), f"{incident_id}.dedupe_key")
        if key in seen_keys:
            raise IncidentError(f"duplicate incident dedupe_key {key!r}")
        seen_keys.add(key)
        for field in REQUIRED[1:]:
            _nonempty(item.get(field), f"{incident_id}.{field}")

    expected = list(range(1, len(incidents) + 1))
    if numbers != expected:
        raise IncidentError(f"incident ids must be ordered and contiguous: expected {expected}, got {numbers}")
    return value


def read_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IncidentError(f"cannot read ledger {path}: {exc}") from exc
    return validate_ledger(value)


def _cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", "<br>").replace("|", "\\|").strip()


def render_table(incidents: Iterable[Mapping[str, Any]]) -> str:
    lines = [
        "| ID | Job / contexte | Symptôme | Cause racine | Invariant / garde-fou durable | Preuve / couverture | Statut |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in incidents:
        lines.append(
            "| " + " | ".join(
                _cell(str(item[field]))
                for field in ("id", "context", "symptom", "root_cause", "invariant", "evidence", "status")
            ) + " |"
        )
    return "\n".join(lines)


def render_register_text(register_text: str, ledger: Mapping[str, Any]) -> str:
    if register_text.count(TABLE_START) != 1 or register_text.count(TABLE_END) != 1:
        raise IncidentError("register must contain exactly one generated table marker pair")
    before, remainder = register_text.split(TABLE_START, 1)
    _old, after = remainder.split(TABLE_END, 1)
    table = render_table(ledger["incidents"])
    return before + TABLE_START + "\n" + table + "\n" + TABLE_END + after


def render_files(ledger_path: Path = DEFAULT_LEDGER, register_path: Path = DEFAULT_REGISTER) -> bool:
    ledger = read_ledger(ledger_path)
    current = register_path.read_text(encoding="utf-8")
    rendered = render_register_text(current, ledger)
    if rendered == current:
        return False
    register_path.write_text(rendered, encoding="utf-8")
    return True


def check_files(ledger_path: Path = DEFAULT_LEDGER, register_path: Path = DEFAULT_REGISTER) -> None:
    ledger = read_ledger(ledger_path)
    current = register_path.read_text(encoding="utf-8")
    rendered = render_register_text(current, ledger)
    if rendered != current:
        raise IncidentError(
            "technical incident register is stale; run: "
            "python jobs/tools/technical_incident_register.py render"
        )


def normalize_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    allowed = set(REQUIRED)
    unknown = set(payload) - allowed - {"id"}
    if unknown:
        raise IncidentError(f"unknown incident fields: {sorted(unknown)}")
    out = {field: _nonempty(payload.get(field), field) for field in REQUIRED}
    return out


def merge_incident(ledger: dict[str, Any], payload: Mapping[str, Any]) -> tuple[str, bool]:
    validate_ledger(ledger)
    normalized = normalize_payload(payload)
    incidents: list[dict[str, Any]] = ledger["incidents"]
    for item in incidents:
        if item["dedupe_key"] == normalized["dedupe_key"]:
            changed = any(item.get(field) != normalized[field] for field in REQUIRED)
            if changed:
                for field in REQUIRED:
                    item[field] = normalized[field]
            validate_ledger(ledger)
            return str(item["id"]), changed

    incident_id = f"TI-{len(incidents) + 1:03d}"
    incidents.append({"id": incident_id, **normalized})
    validate_ledger(ledger)
    return incident_id, True


def write_ledger(ledger: Mapping[str, Any], path: Path = DEFAULT_LEDGER) -> None:
    validate_ledger(dict(ledger))
    path.write_text(canonical_json(ledger), encoding="utf-8")


def record_payload(
    payload: Mapping[str, Any],
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    register_path: Path = DEFAULT_REGISTER,
) -> tuple[str, bool]:
    ledger = read_ledger(ledger_path)
    incident_id, changed = merge_incident(ledger, payload)
    if changed:
        write_ledger(ledger, ledger_path)
        render_files(ledger_path, register_path)
    else:
        check_files(ledger_path, register_path)
    return incident_id, changed


def extract_pr_payload(body: str) -> dict[str, Any] | None:
    start_count = body.count(PR_BLOCK_START)
    end_count = body.count(PR_BLOCK_END)
    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        raise IncidentError("PR must contain exactly one JASS_TECHNICAL_INCIDENT block")
    start = body.index(PR_BLOCK_START) + len(PR_BLOCK_START)
    end = body.index(PR_BLOCK_END, start)
    raw = body[start:end].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IncidentError(f"invalid JASS_TECHNICAL_INCIDENT JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise IncidentError("JASS_TECHNICAL_INCIDENT payload must be a JSON object")
    return payload


def sync_pr_event(
    event: Mapping[str, Any],
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    register_path: Path = DEFAULT_REGISTER,
) -> tuple[str | None, bool]:
    pr = event.get("pull_request")
    if not isinstance(pr, Mapping):
        raise IncidentError("event has no pull_request object")
    body = pr.get("body") or ""
    if not isinstance(body, str):
        raise IncidentError("pull_request.body must be text")
    payload = extract_pr_payload(body)
    if payload is None:
        if "Classification: TECHNICAL" in body or "Classification **TECHNICAL**" in body:
            raise IncidentError("technical PR classification requires JASS_TECHNICAL_INCIDENT block")
        return None, False

    number = pr.get("number") or event.get("number")
    evidence = _nonempty(payload.get("evidence"), "evidence")
    if isinstance(number, int) and f"PR #{number}" not in evidence:
        payload = dict(payload)
        payload["evidence"] = evidence + f"; PR #{number}"
    return record_payload(payload, ledger_path=ledger_path, register_path=register_path)


def set_status(
    *,
    dedupe_key: str,
    status: str,
    evidence_append: str | None = None,
    ledger_path: Path = DEFAULT_LEDGER,
    register_path: Path = DEFAULT_REGISTER,
) -> tuple[str, bool]:
    ledger = read_ledger(ledger_path)
    target = next((item for item in ledger["incidents"] if item["dedupe_key"] == dedupe_key), None)
    if target is None:
        raise IncidentError(f"unknown incident dedupe_key {dedupe_key!r}")
    changed = False
    clean_status = _nonempty(status, "status")
    if target["status"] != clean_status:
        target["status"] = clean_status
        changed = True
    if evidence_append:
        addition = _nonempty(evidence_append, "evidence_append")
        if addition not in target["evidence"]:
            target["evidence"] = target["evidence"].rstrip(" ;") + "; " + addition
            changed = True
    if changed:
        write_ledger(ledger, ledger_path)
        render_files(ledger_path, register_path)
    return str(target["id"]), changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("render")
    sub.add_parser("check")

    record = sub.add_parser("record")
    for field in REQUIRED:
        record.add_argument("--" + field.replace("_", "-"), dest=field, required=True)

    sync = sub.add_parser("sync-pr")
    sync.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))

    status = sub.add_parser("set-status")
    status.add_argument("--dedupe-key", required=True)
    status.add_argument("--status", required=True)
    status.add_argument("--evidence-append")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "render":
            changed = render_files(args.ledger, args.register)
            print(json.dumps({"changed": changed, "register": str(args.register)}, sort_keys=True))
        elif args.command == "check":
            check_files(args.ledger, args.register)
            print(json.dumps({"state": "valid", "register": str(args.register)}, sort_keys=True))
        elif args.command == "record":
            payload = {field: getattr(args, field) for field in REQUIRED}
            incident_id, changed = record_payload(payload, ledger_path=args.ledger, register_path=args.register)
            print(json.dumps({"id": incident_id, "changed": changed}, sort_keys=True))
        elif args.command == "sync-pr":
            if not str(args.event):
                raise IncidentError("--event or GITHUB_EVENT_PATH is required")
            event = json.loads(args.event.read_text(encoding="utf-8"))
            incident_id, changed = sync_pr_event(event, ledger_path=args.ledger, register_path=args.register)
            print(json.dumps({"id": incident_id, "changed": changed}, sort_keys=True))
        elif args.command == "set-status":
            incident_id, changed = set_status(
                dedupe_key=args.dedupe_key,
                status=args.status,
                evidence_append=args.evidence_append,
                ledger_path=args.ledger,
                register_path=args.register,
            )
            print(json.dumps({"id": incident_id, "changed": changed}, sort_keys=True))
        else:  # pragma: no cover
            raise IncidentError(f"unknown command {args.command}")
        return 0
    except (IncidentError, OSError, json.JSONDecodeError) as exc:
        print(f"technical_incident_register: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
