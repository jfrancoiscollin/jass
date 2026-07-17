#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FETCHER = ROOT / "jobs/tools/fetch_t1bis_inputs.py"
FULL = ROOT / "jobs/templates/t1bis-adj-g1-runner-v3-native.sh"
SMOKE = ROOT / "jobs/templates/t1bis-adj-g1-runner-v3-smoke.sh"
NEXT = ROOT / "jobs/templates/probe-adj-g1-next-tour-runner-v3.sh"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NativeT1BisTest(unittest.TestCase):
    def fake_rclone(self, root: Path) -> Path:
        path = root / "rclone"
        path.write_text(
            """#!/usr/bin/env python3
import shutil,sys
from pathlib import Path
cmd=sys.argv[1]
if cmd=='cat':
    sys.stdout.buffer.write(Path(sys.argv[2]).read_bytes())
elif cmd=='copyto':
    src,dst=Path(sys.argv[2]),Path(sys.argv[3])
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
else:
    print('unsupported '+cmd,file=sys.stderr); raise SystemExit(9)
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def build_remote(self, root: Path) -> Path:
        prefix = root / "inputs/t1bis-adj-g1/v1"
        files = prefix / "files"
        files.mkdir(parents=True)
        roles = {
            "parent_pattern": "parent.pjtw.gz",
            "fixed_pattern": "fixed.pjtw.gz",
            "gen2_pattern": "gen2.pjtw.gz",
            "seed_corpus": "seeds.jnnw.gz",
            "g1_pool": "g1_pool.fen",
            "conversion_gauge": "gauge.fen",
        }
        objects = []
        for index, (role, name) in enumerate(roles.items(), 1):
            payload = (f"payload-{index}-{role}\n").encode()
            target = files / name
            target.write_bytes(payload)
            objects.append({
                "role": role,
                "target_name": name,
                "remote": str(target),
                "size_bytes": len(payload),
                "sha256": digest(payload),
                "source_commit": "a" * 40,
                "source_blob": "b" * 40,
            })
        manifest = {
            "schema": 1,
            "dataset": "t1bis-adj-g1-inputs",
            "version": "v1",
            "source_commit": "a" * 40,
            "objects": objects,
        }
        raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        (prefix / "manifest.json").write_bytes(raw)
        success = {
            "state": "completed",
            "dataset": "t1bis-adj-g1-inputs",
            "version": "v1",
            "manifest_sha256": digest(raw),
            "manifest_size_bytes": len(raw),
            "object_count": len(objects),
        }
        (prefix / "_SUCCESS").write_text(json.dumps(success), encoding="utf-8")
        return prefix

    def build_previous_run(
        self,
        root: Path,
        *,
        tour: str = "T1-bis",
        decision: str = "promote",
        status: str = "continue_probe",
        declared_sha: bool = True,
    ) -> tuple[Path, bytes]:
        job_id = "ccx33-0756-t1bis-adj-g1-native-full-v2"
        attempt_id = "20260717T074749Z-6d90e72d"
        prefix = root / "runs" / job_id / attempt_id
        artefacts = prefix / "artefacts"
        artefacts.mkdir(parents=True)

        payload = b"promoted-candidate-weights\n"
        with gzip.open(artefacts / "candidate.pjtw.gz", "wb") as handle:
            handle.write(payload)
        promotion = {
            "regime": "young",
            "tour": tour,
            "candidate_sha": digest(payload) if declared_sha else "...",
            "promotion_decision": decision,
            "scientific_status": status,
        }
        (artefacts / "promotion.json").write_text(
            json.dumps(promotion, indent=2), encoding="utf-8"
        )
        manifest = {
            "job_id": job_id,
            "attempt_id": attempt_id,
            "state": "completed",
            "exit_code": 0,
            "code_sha": "6d90e72ded1cd01055be197817123fe9740c0816",
        }
        (prefix / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Forme reelle d'un run_dir : le launcher cree un job.lock VIDE que
        # l'inventaire du runner liste avec size_bytes=0 (bug T2 des runs 0758).
        (prefix / "job.lock").write_bytes(b"")
        inventory_files = []
        for path in sorted(prefix.rglob("*")):
            if path.is_file():
                raw = path.read_bytes()
                inventory_files.append({
                    "path": str(path.relative_to(prefix)),
                    "size_bytes": len(raw),
                    "sha256": digest(raw),
                })
        inventory = {"files": inventory_files}
        (prefix / "inventory.json").write_text(
            json.dumps(inventory, indent=2), encoding="utf-8"
        )

        checksum_lines = []
        for path in sorted(prefix.rglob("*")):
            if path.is_file() and path.name not in {"checksums.sha256", "_SUCCESS"}:
                checksum_lines.append(
                    f"{digest(path.read_bytes())}  {path.relative_to(prefix)}\n"
                )
        (prefix / "checksums.sha256").write_text("".join(checksum_lines), encoding="utf-8")
        (prefix / "_SUCCESS").write_text("2026-07-17T09:04:46+00:00\n", encoding="utf-8")
        return prefix, payload

    def run_fetcher(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(FETCHER), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_fetcher_accepts_verified_set_and_rejects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prefix = self.build_remote(root)
            rclone = self.fake_rclone(root)
            out = root / "out"
            ok = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(prefix),
                "--out-dir", str(out),
            )
            self.assertEqual(ok.returncode, 0, ok.stderr.decode())
            report = json.loads((out / "verified-inputs.json").read_text())
            self.assertEqual(report["state"], "verified")
            self.assertEqual(report["schema"], 2)
            self.assertEqual(report["parent_chain"]["source"], "frozen_baseline_bundle")
            self.assertEqual(len(report["objects"]), 6)

            (prefix / "files/gauge.fen").write_text("tampered", encoding="utf-8")
            failed = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(prefix),
                "--out-dir", str(root / "out2"),
            )
            self.assertNotEqual(failed.returncode, 0)

    def test_t2_replaces_only_parent_with_promoted_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.build_remote(root)
            previous, payload = self.build_previous_run(root, declared_sha=False)
            rclone = self.fake_rclone(root)
            out = root / "out"
            result = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(baseline),
                "--out-dir", str(out),
                "--tour", "T2",
                "--parent-run-prefix", str(previous),
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            with gzip.open(out / "parent.pjtw.gz", "rb") as handle:
                self.assertEqual(handle.read(), payload)
            report = json.loads((out / "verified-inputs.json").read_text())
            self.assertEqual(report["tour"], "T2")
            self.assertEqual(report["parent_chain"]["previous_tour"], "T1-bis")
            self.assertEqual(
                report["parent_chain"]["candidate_payload_sha256"], digest(payload)
            )
            fixed = (out / "fixed.pjtw.gz").read_bytes()
            self.assertIn(b"fixed_pattern", fixed)

    def test_t2_requires_previous_run(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.build_remote(root)
            rclone = self.fake_rclone(root)
            result = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(baseline),
                "--out-dir", str(root / "out"),
                "--tour", "T2",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"requires --parent-run-prefix", result.stderr)

    def test_previous_run_must_be_promoted_continue_probe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.build_remote(root)
            previous, _ = self.build_previous_run(
                root, decision="reject", status="stop_regression"
            )
            rclone = self.fake_rclone(root)
            result = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(baseline),
                "--out-dir", str(root / "out"),
                "--tour", "T2",
                "--parent-run-prefix", str(previous),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"was not promoted", result.stderr)

    def test_previous_tour_must_match_chain(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.build_remote(root)
            previous, _ = self.build_previous_run(root, tour="T2")
            rclone = self.fake_rclone(root)
            result = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(baseline),
                "--out-dir", str(root / "out"),
                "--tour", "T2",
                "--parent-run-prefix", str(previous),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"tour mismatch", result.stderr)

    def test_previous_candidate_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = self.build_remote(root)
            previous, _ = self.build_previous_run(root)
            with (previous / "artefacts/candidate.pjtw.gz").open("ab") as handle:
                handle.write(b"tamper")
            rclone = self.fake_rclone(root)
            result = self.run_fetcher(
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(baseline),
                "--out-dir", str(root / "out"),
                "--tour", "T2",
                "--parent-run-prefix", str(previous),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"download verification failed", result.stderr)

    def test_launchers_are_native_and_shell_valid(self) -> None:
        for script in (FULL, SMOKE, NEXT):
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = FULL.read_text(encoding="utf-8")
        blocked = [
            "/" + "/".join(("root", "jass")),
            "origin/" + "".join(("ma", "in")),
            "HEAD:" + "".join(("ma", "in")),
            "refs/heads/" + "".join(("ma", "in")),
            "replace_once",
            "t1bis-adj-g1-v2.sh",
        ]
        for token in blocked:
            self.assertNotIn(token, text)
        self.assertIn("fetch_t1bis_inputs.py", text)
        self.assertIn("jobs/tools/calibrate_vs_scan.py", text)
        self.assertNotIn("--calibrate-tool tools/", text)
        self.assertIn('GAMES="${GAMES:-300}"', text)
        self.assertIn('PLAYD="${PLAYD:-10}"', text)
        self.assertIn('ARB_DEPTH="${ARB_DEPTH:-14}"', text)
        self.assertIn('ANCHOR="${ANCHOR:-0.05}"', text)
        self.assertIn('CONV_DEPTH="${CONV_DEPTH:-10}"', text)
        self.assertIn('NOPEN="${NOPEN:-300}"', text)
        self.assertIn('DEPTH="${DEPTH:-9}"', text)

        next_text = NEXT.read_text(encoding="utf-8")
        self.assertIn("PROBE_PARENT_RUN_PREFIX", next_text)
        self.assertIn("T2|T3", next_text)
        self.assertIn("t1bis-adj-g1-runner-v3-native.sh", next_text)


if __name__ == "__main__":
    unittest.main()
