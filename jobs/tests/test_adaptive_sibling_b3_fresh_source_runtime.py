from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b3_fresh_source_runtime as runtime
from jobs.tools import adaptive_sibling_b3_fresh_source_stage as stage
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_json_bytes


def config() -> dict[str, object]:
    return {
        "schema": "jass.b3_fresh_corpus_preregistration.v1",
        "source_selection": {
            "source_seed_base": 2026110800,
            "selection_seed": 2026110816,
            "source_shards": 16,
            "raw_records_per_shard": 10000,
            "cell_quota": 500,
            "selected_parents": 4000,
            "top_up": False,
        },
        "exclusion": {
            "job_id": "cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1",
            "attempt_id": "20260906T134208Z-c553a572",
            "code_sha": "c553a572ed8ada9c49f8ebbefa3db22a9b6ca739",
            "prefix": "r2:jass-data/runs/cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1/20260906T134208Z-c553a572",
            "manifest_artifact_path": "artefacts/b3-fresh-exclusion-manifest.json",
            "manifest_sha256": "f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c",
            "manifest_schema": "jass.adaptive_sibling_b3_fresh_exclusion_manifest.v1",
            "union_artifact_path": "artefacts/b3-fresh-exclusion-union.txt",
            "union_sha256": "b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb",
            "union_unique_canonical": 227317,
            "universe": "DECISION_INFORMATION_B3_FRESH_V1_EXCLUSION",
        },
        "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
        "teacher_budgets_nodes": [5000, 50000, 200000],
        "audit": {
            "seed": 2026110817,
            "parents": 1000,
            "per_cell": 125,
            "selection": "sha256(seed_decimal:canonical_fingerprint), lowest per cell",
            "full_ladder_backfill_forbidden": True,
        },
    }


class B3FreshSourceRuntimeTests(unittest.TestCase):
    def test_derive_contract_changes_only_frozen_b3_dimensions(self) -> None:
        value = config()
        contract = runtime.derive_selection_contract(value)
        self.assertEqual(contract["schema"], runtime.CONTRACT_SCHEMA)
        self.assertEqual(contract["producer"]["seed_base"], 2026110800)
        self.assertEqual(contract["hash"]["selection_seed"], 2026110816)
        self.assertEqual(contract["producer"]["barrier"]["seeds"], "2026110800+source_shard")
        self.assertEqual(contract["producer"]["argv_template"][7], "{2026110800_plus_source_shard}")
        self.assertEqual(contract["cell_quota"], 500)
        self.assertFalse(contract["top_up"])
        self.assertEqual(contract["exclusion"]["union_unique_canonical"], 227317)

    def test_rendered_modules_bind_new_seeds_and_exclusion_contract(self) -> None:
        contract = runtime.derive_selection_contract(config())
        selector_text = runtime.render_selector(contract)
        launcher_text = runtime.render_launcher()
        self.assertIn("SELECTION_SEED = 2_026_110_816", selector_text)
        self.assertIn("SOURCE_SEED_BASE = 2_026_110_800", selector_text)
        self.assertIn('"seeds": f"{SOURCE_SEED_BASE}+source_shard"', selector_text)
        self.assertIn("B3 exclusion manifest component set mismatch", selector_text)
        self.assertIn("SOURCE_SEED_BASE = 2_026_110_800", launcher_text)
        self.assertNotIn('"seeds": "2026110700+source_shard"', launcher_text)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selector, launcher, receipt = runtime.load_runtime(root, contract)
            contract_path = root / "contract.json"
            contract_path.write_bytes(canonical_json_bytes(contract))
            loaded, raw = selector.load_contract(contract_path)
            self.assertEqual(loaded, contract)
            self.assertEqual(raw, canonical_json_bytes(contract))
            self.assertIs(launcher.selector, selector)
            self.assertEqual(len(receipt["selector_sha256"]), 64)

    def test_b3_exclusion_loader_is_exact_manifest_bound(self) -> None:
        contract = runtime.derive_selection_contract(config())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selector, _launcher, _receipt = runtime.load_runtime(root, contract)
            manifest = {
                "schema": runtime.EXCLUSION_MANIFEST_SCHEMA,
                "universe": "DECISION_INFORMATION_B3_FRESH_V1_EXCLUSION",
                "canonicalization": contract["canonicalization"],
                "components": [
                    {"kind": "historical_b1_b2_exclusion"},
                    {"kind": "b2_confirmation_parents"},
                ],
                "component_overlap": 0,
                "union_unique_canonical": 227317,
                "union_sha256": contract["exclusion"]["union_sha256"],
                "scores_or_labels_read": 0,
                "fresh_b3_parents_generated": 0,
                "fits": 0,
                "strength_games": 0,
                "promotions": 0,
                "bakes": 0,
            }
            path = root / "manifest.json"
            path.write_bytes(canonical_json_bytes(manifest))
            adapted = copy.deepcopy(contract)
            adapted["exclusion"]["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            parsed, raw = selector._load_exclusion_manifest(path, adapted)
            self.assertEqual(parsed, manifest)
            self.assertEqual(raw, canonical_json_bytes(manifest))

    def test_stage_config_binds_contract_hash_policy_and_audit(self) -> None:
        value = config()
        contract = runtime.derive_selection_contract(value)
        value["derived_selection_contract_sha256"] = hashlib.sha256(
            canonical_json_bytes(contract)).hexdigest()
        stage.validate_config(value, contract)
        value["policy"] = {"M5": 101, "M50": 60, "minimum_survivors": 2}
        with self.assertRaisesRegex(stage.StageError, "policy drift"):
            stage.validate_config(value, contract)


if __name__ == "__main__":
    unittest.main()
