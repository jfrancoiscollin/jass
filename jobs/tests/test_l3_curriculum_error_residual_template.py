from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-residual-atlas-v1.sh"
SPEC = ROOT / "docs/experiments/L3_CURRICULUM_ERROR_RESIDUAL_ATLAS_20260822.md"


class CurriculumErrorResidualTemplateTests(unittest.TestCase):
    def test_template_pins_source_and_forbidden_actions(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for needle in (
            'SOURCE_JOB="cpx62-1476-l3-curriculum-search-error-atlas-v1"',
            'SOURCE_ATTEMPT="20260822T170608Z-92a7f393"',
            'CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"',
            'NO_SELFPLAY', 'NO_FIT', 'NO_STRENGTH_GAMES', 'NO_FROZEN_READ',
            'NO_AUTOMATIC_PROMOTION', 'NO_AUTOMATIC_CONTINUATION',
            '--bootstrap-samples 100000', '--permutation-samples 10000',
            '--seed 2026082222', '--max-region-buckets 128',
        ):
            self.assertIn(needle, text)

    def test_spec_documents_fail_closed_contract(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        for needle in (
            "pvleaf=<FEN>", "p <= 0,025", "byte-identiques",
            "NEXT_STAGE__NONE", "zéro self-play", "aucun fit",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
