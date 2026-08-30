from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md"
R0 = ROOT / "jobs/templates/l3-t3-f6-runtime-r0-v4.sh"
P1 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool1-v4.sh"
P2 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool2-v4.sh"
ZERO_SHA = "160489327d419e3d7bbbbda900d6e0ec7bc960111149fc0a45cc27aaa55bf6aa"


class RuntimeV4ProtocolTests(unittest.TestCase):
    def test_prereg_preserves_history_and_freezes_v4(self) -> None:
        text = PREREG.read_text(encoding="utf-8")
        for token in (
            "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED",
            "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH",
            "R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE",
            "R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
            "R0_V4_ZERO_WRAPPER_SEARCH_EQUIVALENCE_FAILED",
            "T3_F6_RUNTIME_STRENGTH_SUPPORTED",
            "Aucun Pool3",
        ):
            self.assertIn(token, text)
        for seed in range(2026092501, 2026092506):
            self.assertIn(str(seed), text)
        for seed in range(2026092601, 2026092605):
            self.assertIn(str(seed), text)
        for seed in range(2026092701, 2026092705):
            self.assertIn(str(seed), text)
        for seed in (2026092801, 2026092802):
            self.assertIn(str(seed), text)

    def test_zero_artifact_is_canonical_and_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "zero.json"
            subprocess.run([
                sys.executable, str(ROOT / "jobs/tools/t3_f6_zero_artifact_v4.py"),
                "--out", str(output),
            ], cwd=ROOT, check=True)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), ZERO_SHA)
        source = (ROOT / "jobs/tools/t3_f6_zero_artifact_v4.py").read_text(encoding="utf-8")
        self.assertNotIn("numpy", source)
        self.assertNotIn("fit(", source)
        self.assertIn("zero_matrix(66, 256)", source)

    def test_zero_policy_is_not_the_production_policy(self) -> None:
        header = (ROOT / "src/t3_f6.hpp").read_text(encoding="utf-8")
        source = (ROOT / "src/t3_f6.cpp").read_text(encoding="utf-8")
        probe = (ROOT / "jobs/tools/t3_f6_runtime_contract_v4.cpp").read_text(encoding="utf-8")
        self.assertIn("ZeroProbeOnly", header)
        self.assertIn(ZERO_SHA, header)
        self.assertIn("load_model(env,LoadPolicy::FrozenOnly", source)
        self.assertNotIn("JASS_T3_F6_ZERO", source)
        self.assertIn("--zero-probe", probe)
        self.assertIn("zero_search_mismatches", probe)
        self.assertIn("same_result(off.result,z.result)", probe)

    def test_r0_template_is_target_blind_and_fail_closed(self) -> None:
        text = R0.read_text(encoding="utf-8")
        for token in (
            "e857a5a951afa3c78957c7ad92afb67e4b0dae3b",
            "CANDIDATES=40000", "GEN_SEED=2026092501",
            "SEARCH_SEED=2026092504", "BENCH_SEED=2026092505",
            "t3_f6_zero_artifact_v4.py", "--zero-probe",
            "--v4-relative-only", "t3_f6_runtime_parity_v4.py",
            "t3_f6_r0_readout_v4.py", "r0-v3-mechanics.tsv",
            "scan-parents.tsv", "scan-siblings.tsv", "STRENGTH_GAMES__0",
        ):
            self.assertIn(token, text)

    def test_runtime_probe_accepts_preregistered_v4_benchmark_seed(self) -> None:
        source = (ROOT / "jobs/tools/t3_f6_runtime_probe.cpp").read_text(encoding="utf-8")
        self.assertIn("2026092505ULL", source)
        self.assertIn("R0 benchmark order seed drift", source)

    def test_v4_strength_seeds_and_readout(self) -> None:
        for seed in (2026092601, 2026092602, 2026092603):
            self.assertIn(str(seed), P1.read_text(encoding="utf-8"))
        for seed in (2026092701, 2026092702, 2026092703, 2026092801):
            self.assertIn(str(seed), P2.read_text(encoding="utf-8"))
        readout = (ROOT / "jobs/tools/t3_f6_strength_readout_v2.py").read_text(encoding="utf-8")
        self.assertIn('"v4": ("R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED"', readout)
        self.assertIn("V4_CHAINED_BOOTSTRAP_SEED = 2026092801", readout)
        self.assertIn("if p1_rate <= 0.5", readout)
        self.assertIn("if p2_rate <= 0.5", readout)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_shell_templates_parse(self) -> None:
        for path in (R0, P1, P2):
            subprocess.run(["bash", "-n", str(path)], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
