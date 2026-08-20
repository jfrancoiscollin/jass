#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Certified source-contract checks for the CTX4 read-only screen."""

from __future__ import annotations

import json
from typing import Any


def validate_1428_force_summary(force: dict[str, Any]) -> None:
    """Validate the immutable 1428 ``JASS_CONTROL_SUMMARY`` artefact.

    The certified 1428 force template writes the scientific readout first and
    then copies it byte-for-byte to ``JASS_CONTROL_SUMMARY.json``.  The summary
    therefore carries the exact scientific readout schema; it is not a separate
    runner wrapper with nested ``fits``/``new_selfplay``/``frozen_cohorts``
    receipts.  Reuse the scientific validator so both immutable paths are held
    to the same fail-closed execution, promotion and continuation contract.
    """
    validate_1428_force_readout(force)


def validate_1428_force_readout(readout: dict[str, Any]) -> None:
    """Validate the immutable scientific 1428 force readout and promotion scope.

    ``context3-two-pool-force-readout.json`` is the scientific artefact that
    1430 independently authenticated.  The certified 1428 template also copies
    this payload byte-for-byte to ``JASS_CONTROL_SUMMARY.json``.
    """
    if readout.get("schema") != "jass.l3_context3_two_pool_force_readout.v1":
        raise ValueError("1428 scientific readout schema drift")
    if readout.get("verdict") != "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED":
        raise ValueError("1428 scientific readout verdict drift")

    protocol = readout.get("protocol")
    if not isinstance(protocol, dict):
        raise ValueError("1428 scientific protocol scope missing")
    if protocol.get("models_reused") is not True:
        raise ValueError("1428 scientific readout violated model-reuse contract")
    if protocol.get("refits") != 0:
        raise ValueError("1428 scientific readout unexpectedly refit")
    if protocol.get("new_selfplay") != 0:
        raise ValueError("1428 scientific readout unexpectedly self-played")
    if protocol.get("frozen_cohorts_read") != 0:
        raise ValueError("1428 scientific readout violated frozen-read contract")
    if readout.get("promotion_authorized") is not False:
        raise ValueError("1428 scientific readout promotion scope drift")
    if readout.get("automatic_next_job") is not None:
        raise ValueError("1428 scientific readout continuation scope drift")


def validate_1428_pool_certificate(pool: dict[str, Any]) -> None:
    """Validate the certified 1428 fresh-pool contract used by CTX4."""
    if not isinstance(pool, dict):
        raise ValueError("1428 pool certificate missing")
    if pool.get("schema") != "jass.context3.two_fresh_pools.v1":
        raise ValueError("1428 pool certificate schema drift")
    if pool.get("verdict") != "JASS_CONTEXT3_TWO_FRESH_POOLS_READY":
        raise ValueError("1428 pool certificate verdict drift")
    if pool.get("mutually_disjoint") is not True or pool.get("mutual_overlap") != 0:
        raise ValueError("1428 pool disjointness drift")
    if pool.get("all_historical_overlaps_zero") is not True:
        raise ValueError("1428 historical overlap drift")
    if pool.get("historical_exclusion_count") != 17:
        raise ValueError("1428 historical exclusion count drift")
    if pool.get("deterministic_generation_repeated") is not True:
        raise ValueError("1428 pool deterministic-generation drift")
    if pool.get("promotion_authorized") is not False:
        raise ValueError("1428 pool promotion scope drift")

    exclusions = pool.get("historical_exclusions")
    if not isinstance(exclusions, list) or len(exclusions) != 17:
        raise ValueError("1428 historical exclusion receipt drift")
    blob = json.dumps(exclusions, sort_keys=True)
    if (
        "pool-context3-1419-force-pool1" not in blob
        or "pool-context3-1419-force-pool2" not in blob
    ):
        raise ValueError("1428 missing 1419 pool exclusions")

    pools = pool.get("pools")
    if not isinstance(pools, list) or len(pools) != 2:
        raise ValueError("1428 fresh pool count drift")
    if [item.get("seed") for item in pools] != [2026082001, 2026082002]:
        raise ValueError("1428 fresh pool seed drift")
    if any(item.get("openings") != 3000 for item in pools):
        raise ValueError("1428 fresh pool cardinality drift")


def pool_certificate_canonical_fingerprint(pool: dict[str, Any]) -> str:
    """Canonical full-certificate fingerprint used for cross-authentication.

    Read-only diagnostic 1440 proved the direct immutable 1428 certificate and
    the copy embedded by authenticated 1430 have zero structural/value
    differences and the same canonical SHA-256 source representation.  We
    therefore canonicalize the *entire* validated certificate rather than
    dropping or normalizing any field.  This preserves every pool ID/hash,
    exclusion receipt, overlap guard and metadata field fail-closed while
    avoiding dependence on Python mapping insertion order or raw object identity.
    """
    validate_1428_pool_certificate(pool)
    return json.dumps(
        pool,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def validate_equivalent_1428_pool_certificates(
    direct: dict[str, Any], embedded: dict[str, Any]
) -> None:
    """Fail closed unless both certified receipts are canonically identical."""
    direct_fp = pool_certificate_canonical_fingerprint(direct)
    embedded_fp = pool_certificate_canonical_fingerprint(embedded)
    if direct_fp != embedded_fp:
        raise ValueError("1428 pool canonical fingerprint drift")
