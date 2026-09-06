from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import technical_incident_register as subject


class TechnicalIncidentRegisterTests(unittest.TestCase):
    def _ledger(self):
        return {
            "schema": subject.SCHEMA,
            "incidents": [
                {
                    "id": "TI-001",
                    "dedupe_key": "job:1",
                    "context": "job 1",
                    "symptom": "failed",
                    "root_cause": "bad contract",
                    "invariant": "contract fixed",
                    "evidence": "PR #1",
                    "status": "CLOSED",
                }
            ],
        }

    def test_merge_allocates_next_id_and_dedupes(self):
        ledger = self._ledger()
        payload = {
            "dedupe_key": "job:2",
            "context": "job 2",
            "symptom": "boom",
            "root_cause": "cause",
            "invariant": "guard",
            "evidence": "PR #2",
            "status": "MITIGATED — RERUN PENDING",
        }
        incident_id, changed = subject.merge_incident(ledger, payload)
        self.assertEqual((incident_id, changed), ("TI-002", True))
        incident_id, changed = subject.merge_incident(ledger, payload)
        self.assertEqual((incident_id, changed), ("TI-002", False))
        self.assertEqual(len(ledger["incidents"]), 2)

    def test_render_replaces_only_generated_region(self):
        ledger = self._ledger()
        template = (
            "before\n" + subject.TABLE_START + "\nold\n" + subject.TABLE_END + "\nafter\n"
        )
        rendered = subject.render_register_text(template, ledger)
        self.assertTrue(rendered.startswith("before\n" + subject.TABLE_START))
        self.assertTrue(rendered.endswith(subject.TABLE_END + "\nafter\n"))
        self.assertIn("| TI-001 | job 1 |", rendered)
        self.assertNotIn("\nold\n", rendered)

    def test_sync_pr_adds_pr_evidence_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger_path = root / "ledger.json"
            register_path = root / "register.md"
            ledger_path.write_text(subject.canonical_json(self._ledger()), encoding="utf-8")
            register_path.write_text(
                "head\n" + subject.TABLE_START + "\n"
                + subject.render_table(self._ledger()["incidents"])
                + "\n" + subject.TABLE_END + "\ntail\n",
                encoding="utf-8",
            )
            payload = {
                "dedupe_key": "job:2",
                "context": "job 2",
                "symptom": "failed",
                "root_cause": "root",
                "invariant": "guard",
                "evidence": "runtime log",
                "status": "MITIGATED — RERUN PENDING",
            }
            body = (
                subject.PR_BLOCK_START + "\n"
                + json.dumps(payload)
                + "\n" + subject.PR_BLOCK_END
            )
            event = {"number": 42, "pull_request": {"number": 42, "body": body}}
            incident_id, changed = subject.sync_pr_event(
                event, ledger_path=ledger_path, register_path=register_path
            )
            self.assertEqual((incident_id, changed), ("TI-002", True))
            value = subject.read_ledger(ledger_path)
            self.assertIn("PR #42", value["incidents"][1]["evidence"])
            incident_id, changed = subject.sync_pr_event(
                event, ledger_path=ledger_path, register_path=register_path
            )
            self.assertEqual((incident_id, changed), ("TI-002", False))
            subject.check_files(ledger_path, register_path)

    def test_technical_classification_without_block_fails_closed(self):
        event = {"pull_request": {"body": "Classification: TECHNICAL\nfix follows"}}
        with self.assertRaises(subject.IncidentError):
            subject.sync_pr_event(event)


if __name__ == "__main__":
    unittest.main()
