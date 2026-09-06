#!/usr/bin/env python3
"""Narrow B2 terminal compatibility for immutable legacy support JSON formatting.

Job 1829 proved that the frozen terminal support bundle contains valid historical
JSON whose serialization predates the compact canonical-JSON requirement used by
the current B2 terminal authenticator.  This module does not rewrite those bytes.
It permits non-canonical *formatting* only for the three immutable support
artefacts already named by the terminal manifest, while preserving strict JSON
semantics and returning the original raw bytes so all descriptor identities stay
unchanged.

Everything else continues through the exact frozen readout parser unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from jobs.tools import adaptive_sibling_b2_readout as readout

ALLOWED_LEGACY_BASENAMES = frozenset({
    "verified-historical.json",
    "source-manifest.json",
    "legacy-terminal-summary.json",
})


class LegacySupportJsonCompatError(RuntimeError):
    pass


_ORIGINAL_READ_CANONICAL_JSON: Callable[[Path], tuple[dict[str, Any], bytes]] | None = None
_INSTALLED = False


def _strict_legacy_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=readout._pairs,
            parse_constant=readout._constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise readout.ReadoutError(f"cannot read legacy support JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise readout.ReadoutError(f"legacy support JSON root is not object: {path}")
    if raw == readout.canonical_json_bytes(value):
        raise LegacySupportJsonCompatError(
            f"legacy compatibility reached for already-canonical JSON: {path}"
        )
    return value, raw


def install() -> None:
    """Install formatting-only compatibility in the current recovery process."""
    global _INSTALLED, _ORIGINAL_READ_CANONICAL_JSON
    if _INSTALLED:
        return
    _ORIGINAL_READ_CANONICAL_JSON = readout.read_canonical_json

    def compatible_read(path: Path) -> tuple[dict[str, Any], bytes]:
        assert _ORIGINAL_READ_CANONICAL_JSON is not None
        try:
            return _ORIGINAL_READ_CANONICAL_JSON(path)
        except readout.ReadoutError as exc:
            if path.name not in ALLOWED_LEGACY_BASENAMES \
                    or not str(exc).startswith("non-canonical JSON:"):
                raise
            return _strict_legacy_json(path)

    readout.read_canonical_json = compatible_read
    _INSTALLED = True


def uninstall() -> None:
    """Restore the exact frozen canonical parser; intended for contract tests."""
    global _INSTALLED
    if not _INSTALLED:
        return
    assert _ORIGINAL_READ_CANONICAL_JSON is not None
    readout.read_canonical_json = _ORIGINAL_READ_CANONICAL_JSON
    _INSTALLED = False
