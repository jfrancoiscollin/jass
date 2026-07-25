from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-eval-v1.sh"
WRAPPERS = tuple(
    ROOT
    / "jobs/prepared/l3-pure-m2-20260725"
    / name
    for name in (
        "home-0967-l3-pure-m2-independent-eval-v1.sh",
        "home-0970-l3-pure-m2-independent-eval-v2.sh",
        "home-0970bis-l3-pure-m2-independent-eval-v3.sh",
    )
)


class M2EvaluationJobTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, *WRAPPERS):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_independent_force_and_guardrail_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("NOPEN=500", text)
        self.assertIn("OPENING_CANDIDATES=2000", text)
        self.assertIn("OPENING_SEED=244949", text)
        self.assertIn("select_independent_opening_pool.py", text)
        self.assertIn('--out "$W/open-m2.fen"', text)
        self.assertIn("run_gate q00 F2M", text)
        self.assertIn("run_gate q00 GEN2", text)
        self.assertIn("run_gate native F2M", text)
        self.assertIn("run_gate native GEN2", text)
        self.assertIn("--depth \"$FORCE_DEPTH\"", text)
        self.assertIn("--movetime \"$MOVETIME\"", text)
        self.assertIn("--pairs 1", text)

    def test_conversion_and_coverage_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("p3_mince-stable.jnnw.gz", text)
        self.assertIn("p4_egal-stable.jnnw.gz", text)
        self.assertIn("F2M-p3_mince.json", text)
        self.assertIn("F2M-p4_egal.json", text)
        self.assertIn("run_conv p3_mince", text)
        self.assertIn("run_conv p4_egal", text)
        self.assertIn("l3_bucket_visits.py", text)
        self.assertIn("F2M-coverage.json", text)
        self.assertIn("M2-coverage.json", text)
        self.assertIn('J32FIXED="$W/build32fixed/jass"', text)
        self.assertIn('--defender-jass "$J32FIXED"', text)
        self.assertIn("FIXED_DEFENDER_CODE_SHA", text)
        self.assertIn('(cd "$W/fixed-defender-code" &&', text)

    def test_nonpromotion_and_sources(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        wrappers = "\n".join(
            wrapper.read_text(encoding="utf-8") for wrapper in WRAPPERS
        )
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)
        self.assertIn("l3_m2_evaluation.py", text)
        self.assertIn("home-0966bis", wrappers)
        self.assertIn("home-0965", wrappers)
        self.assertIn("home-0962", wrappers)
        self.assertIn(
            'EXPECTED_JOB_ID="home-0970-l3-pure-m2-independent-eval-v2"',
            wrappers,
        )
        self.assertIn(
            'EXPECTED_JOB_ID="home-0970bis-l3-pure-m2-independent-eval-v3"',
            wrappers,
        )


if __name__ == "__main__":
    unittest.main()
