#!/usr/bin/env python3
"""Adapt the audited B2 target-blind source pipeline for B3 fresh-corpus use.

This module does not launch compute. It derives the B3 selection contract from
the byte-pinned B2 contract plus the preregistered B3 delta, then renders the
B2 selector/launcher with only schema/seed/exclusion-contract changes.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator, Mapping

ROOT = Path(__file__).resolve().parents[2]
B2_CONTRACT = ROOT / "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json"
B2_SELECTOR = ROOT / "jobs/tools/adaptive_sibling_b2_select.py"
B2_LAUNCHER = ROOT / "jobs/tools/adaptive_sibling_b2_source_launcher.py"
B2_PUBLISHER = ROOT / "jobs/tools/adaptive_sibling_b2_source_publish.py"

B2_CONTRACT_SHA256 = "5e94e0b8a71089d01959212debcfe0b90700714d96693097b519090462fe0e66"
B2_SELECTOR_GIT_BLOB = "bf215add5acee2eae1fbba03fb0cc4848f90299c"
B2_LAUNCHER_GIT_BLOB = "3970cef39ce9eb2dd6f596c9432aee9ec92520e4"
B2_PUBLISHER_GIT_BLOB = "04b92b76b7d70fb60f1763f33db09ded4201e221"

CONTRACT_SCHEMA = "jass.adaptive_sibling_b3_fresh_selection_contract.v1"
SOURCE_MANIFEST_SCHEMA = "jass.adaptive_sibling_b3_fresh_source_preparation.v1"
SELECTION_REPORT_SCHEMA = "jass.adaptive_sibling_b3_fresh_target_blind_selection.v1"
EXCLUSION_MANIFEST_SCHEMA = "jass.adaptive_sibling_b3_fresh_exclusion_manifest.v1"
SUPPORT_REPORT_SCHEMA = "jass.adaptive_sibling_b3_fresh_target_blind_support.v1"
SUCCESS_SCHEMA = "jass.adaptive_sibling_b3_fresh_source_selection_publication.v1"
SUPPORT_SCHEMA = "jass.adaptive_sibling_b3_fresh_source_selection_support_failure.v1"
SEAL_SCHEMA = "jass.adaptive_sibling_b3_fresh_local_selection_seal.v1"
SUCCESS_VERDICT = "B3_FRESH_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE"
SUPPORT_VERDICT = "B3_FRESH_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1"
SOURCE_SEED_BASE = 2_026_110_800
SELECTION_SEED = 2_026_110_816
AUDIT_SEED = 2_026_110_817


class RuntimeAdapterError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob(path: Path) -> str:
    completed = subprocess.run(["/usr/bin/git", "hash-object", str(path)], cwd=ROOT,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                               timeout=30)
    if completed.returncode != 0:
        raise RuntimeAdapterError(completed.stderr.decode(errors="replace")[-2000:])
    return completed.stdout.decode("ascii").strip()


def verify_base_sources() -> None:
    expected = {
        B2_SELECTOR: B2_SELECTOR_GIT_BLOB,
        B2_LAUNCHER: B2_LAUNCHER_GIT_BLOB,
        B2_PUBLISHER: B2_PUBLISHER_GIT_BLOB,
    }
    for path, digest in expected.items():
        if _git_blob(path) != digest:
            raise RuntimeAdapterError(f"audited B2 source drift: {path.relative_to(ROOT)}")
    if sha256(B2_CONTRACT.read_bytes()) != B2_CONTRACT_SHA256:
        raise RuntimeAdapterError("audited B2 selection contract drift")


def _require_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise RuntimeAdapterError(f"{label} must be a non-negative integer")
    return value


def derive_selection_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    verify_base_sources()
    base = json.loads(B2_CONTRACT.read_text(encoding="ascii"))
    if not isinstance(base, dict) or canonical_json(base) != B2_CONTRACT.read_bytes():
        raise RuntimeAdapterError("B2 selection contract is not canonical")

    if config.get("schema") != "jass.b3_fresh_corpus_preregistration.v1":
        raise RuntimeAdapterError("B3 preregistration config schema mismatch")
    pins = config.get("source_selection")
    if not isinstance(pins, Mapping):
        raise RuntimeAdapterError("source_selection config missing")
    expected_pins = {
        "source_seed_base": SOURCE_SEED_BASE,
        "selection_seed": SELECTION_SEED,
        "source_shards": 16,
        "raw_records_per_shard": 10_000,
        "cell_quota": 500,
        "selected_parents": 4_000,
        "top_up": False,
    }
    for key, expected in expected_pins.items():
        if pins.get(key) != expected or type(pins.get(key)) is not type(expected):
            raise RuntimeAdapterError(f"source_selection.{key} mismatch")

    exclusion = config.get("exclusion")
    if not isinstance(exclusion, Mapping):
        raise RuntimeAdapterError("exclusion config missing")
    required_exclusion = (
        "job_id", "attempt_id", "code_sha", "prefix", "manifest_artifact_path",
        "manifest_sha256", "union_artifact_path", "union_sha256",
        "union_unique_canonical", "universe",
    )
    if any(not isinstance(exclusion.get(key), str) or not exclusion[key]
           for key in required_exclusion if key != "union_unique_canonical"):
        raise RuntimeAdapterError("exclusion string field invalid")
    if exclusion.get("union_unique_canonical") != 227_317:
        raise RuntimeAdapterError("B3 exclusion cardinality must be 227317")
    if exclusion.get("manifest_schema") != EXCLUSION_MANIFEST_SCHEMA:
        raise RuntimeAdapterError("B3 exclusion manifest schema mismatch")

    contract = copy.deepcopy(base)
    contract["schema"] = CONTRACT_SCHEMA
    contract["selection_report_schema"] = SELECTION_REPORT_SCHEMA
    contract["exclusion"] = dict(exclusion)
    contract["hash"]["selection_seed"] = SELECTION_SEED
    golden_fp = contract["hash"]["golden"]["canonical_fingerprint"]
    golden_payload = f"{SELECTION_SEED}:{golden_fp}"
    contract["hash"]["golden"] = {
        "canonical_fingerprint": golden_fp,
        "digest": hashlib.sha256(golden_payload.encode("ascii")).hexdigest(),
        "payload": golden_payload,
    }
    contract["producer"]["seed_base"] = SOURCE_SEED_BASE
    contract["producer"]["source_manifest_schema"] = SOURCE_MANIFEST_SCHEMA
    contract["producer"]["barrier"]["seeds"] = f"{SOURCE_SEED_BASE}+source_shard"
    argv = list(contract["producer"]["argv_template"])
    if argv[7] != "{2026110700_plus_source_shard}":
        raise RuntimeAdapterError("B2 producer seed anchor drift")
    argv[7] = "{2026110800_plus_source_shard}"
    contract["producer"]["argv_template"] = argv
    return contract


def _replace_one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeAdapterError(f"{label}: expected one anchor, got {count}")
    return text.replace(old, new, 1)


def render_selector(contract: Mapping[str, Any]) -> str:
    text = B2_SELECTOR.read_text(encoding="utf-8")
    replacements = (
        ('CONTRACT_SCHEMA = "jass.adaptive_sibling_b2_selection_contract.v1"',
         f'CONTRACT_SCHEMA = "{CONTRACT_SCHEMA}"', "contract schema"),
        ('SOURCE_MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_source_preparation.v1"',
         f'SOURCE_MANIFEST_SCHEMA = "{SOURCE_MANIFEST_SCHEMA}"', "source schema"),
        ('SELECTION_REPORT_SCHEMA = "jass.adaptive_sibling_b2_target_blind_selection.v1"',
         f'SELECTION_REPORT_SCHEMA = "{SELECTION_REPORT_SCHEMA}"', "selection schema"),
        ('EXCLUSION_MANIFEST_SCHEMA = "jass.adaptive_sibling_b2_historical_exclusion_manifest.v1"',
         f'EXCLUSION_MANIFEST_SCHEMA = "{EXCLUSION_MANIFEST_SCHEMA}"', "exclusion schema"),
        ('SUPPORT_REPORT_SCHEMA = "jass.adaptive_sibling_b2_target_blind_support.v1"',
         f'SUPPORT_REPORT_SCHEMA = "{SUPPORT_REPORT_SCHEMA}"', "support schema"),
        ('EXPECTED_CONTRACT_SHA256 = "5e94e0b8a71089d01959212debcfe0b90700714d96693097b519090462fe0e66"',
         f'EXPECTED_CONTRACT_SHA256 = "{sha256(canonical_json(contract))}"', "contract SHA"),
        ('SELECTION_SEED = 2_026_110_716', 'SELECTION_SEED = 2_026_110_816', "selection seed"),
        ('SOURCE_SEED_BASE = 2_026_110_700', 'SOURCE_SEED_BASE = 2_026_110_800', "source seed"),
        ('"seeds": "2026110700+source_shard",',
         '"seeds": f"{SOURCE_SEED_BASE}+source_shard",', "barrier seed receipt"),
    )
    for old, new, label in replacements:
        text = _replace_one(text, old, new, label)

    start = text.index("def _load_exclusion_manifest(")
    end = text.index("\ndef _load_exclusion_receipt(", start)
    replacement = '''def _load_exclusion_manifest(path: Path, contract: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    expected = contract["exclusion"]
    manifest, raw = _read_json(path, canonical=True)
    if sha256_bytes(raw) != expected["manifest_sha256"]:
        raise ContractError("B3 exclusion manifest SHA mismatch")
    checks = {
        "schema": EXCLUSION_MANIFEST_SCHEMA,
        "universe": expected["universe"],
        "canonicalization": contract["canonicalization"],
        "component_overlap": 0,
        "union_unique_canonical": expected["union_unique_canonical"],
        "union_sha256": expected["union_sha256"],
        "scores_or_labels_read": 0,
        "fresh_b3_parents_generated": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    for field, value in checks.items():
        if type(manifest.get(field)) is not type(value) or manifest.get(field) != value:
            raise ContractError(f"B3 exclusion manifest {field} mismatch")
    components = manifest.get("components")
    if not isinstance(components, list) or len(components) != 2:
        raise ContractError("B3 exclusion manifest component set mismatch")
    kinds = [item.get("kind") if isinstance(item, dict) else None for item in components]
    if kinds != ["historical_b1_b2_exclusion", "b2_confirmation_parents"]:
        raise ContractError("B3 exclusion component identity mismatch")
    return manifest, raw
'''
    return text[:start] + replacement + text[end:]


def render_launcher() -> str:
    text = B2_LAUNCHER.read_text(encoding="utf-8")
    text = _replace_one(
        text,
        "from jobs.tools import adaptive_sibling_b2_select as selector  # noqa: E402",
        "import adaptive_sibling_b3_runtime_selector as selector  # noqa: E402",
        "selector import",
    )
    text = _replace_one(text, "SOURCE_SEED_BASE = 2_026_110_700",
                        "SOURCE_SEED_BASE = 2_026_110_800", "launcher source seed")
    text = _replace_one(text, '"seeds": "2026110700+source_shard",',
                        '"seeds": f"{SOURCE_SEED_BASE}+source_shard",',
                        "launcher barrier seed receipt")
    return text


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeAdapterError(f"cannot load runtime module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_runtime(work_dir: Path, contract: Mapping[str, Any]):
    verify_base_sources()
    runtime_dir = work_dir / "runtime-adapter"
    runtime_dir.mkdir(parents=True, exist_ok=False)
    selector_path = runtime_dir / "adaptive_sibling_b3_runtime_selector.py"
    launcher_path = runtime_dir / "adaptive_sibling_b3_runtime_launcher.py"
    selector_path.write_text(render_selector(contract), encoding="utf-8")
    launcher_path.write_text(render_launcher(), encoding="utf-8")
    sys.path.insert(0, str(runtime_dir))
    try:
        selector = _load_module("adaptive_sibling_b3_runtime_selector", selector_path)
        launcher = _load_module("adaptive_sibling_b3_runtime_launcher", launcher_path)
    finally:
        if sys.path and sys.path[0] == str(runtime_dir):
            sys.path.pop(0)
    if selector.SELECTION_SEED != SELECTION_SEED or selector.SOURCE_SEED_BASE != SOURCE_SEED_BASE:
        raise RuntimeAdapterError("rendered selector seed mismatch")
    if launcher.SOURCE_SEED_BASE != SOURCE_SEED_BASE or launcher.selector is not selector:
        raise RuntimeAdapterError("rendered launcher binding mismatch")
    return selector, launcher, {
        "selector_sha256": sha256(selector_path.read_bytes()),
        "launcher_sha256": sha256(launcher_path.read_bytes()),
        "base_selector_git_blob": B2_SELECTOR_GIT_BLOB,
        "base_launcher_git_blob": B2_LAUNCHER_GIT_BLOB,
        "base_publisher_git_blob": B2_PUBLISHER_GIT_BLOB,
    }


@contextmanager
def configured_publisher(publisher, selector) -> Iterator[None]:
    fields = {
        "selector": selector,
        "SUCCESS_SCHEMA": SUCCESS_SCHEMA,
        "SUPPORT_SCHEMA": SUPPORT_SCHEMA,
        "SEAL_SCHEMA": SEAL_SCHEMA,
        "SUCCESS_VERDICT": SUCCESS_VERDICT,
        "SUPPORT_VERDICT": SUPPORT_VERDICT,
    }
    previous = {key: getattr(publisher, key) for key in fields}
    try:
        for key, value in fields.items():
            setattr(publisher, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(publisher, key, value)
