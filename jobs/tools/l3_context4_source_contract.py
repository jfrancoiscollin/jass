#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Certified source-contract checks for the CTX4 read-only screen."""

from __future__ import annotations

from typing import Any


def validate_1428_force_summary(force: dict[str, Any]) -> None:
    """Validate the immutable 1428 runner-summary execution scope used by CTX4.

    The certified runner-controlled JASS_CONTROL_SUMMARY stores execution-scope
    guards under ``protocol``.  This is intentionally separate from the
    scientific force readout: runner post-processing can wrap/replace the
    top-level scientific fields while preserving the execution-scope receipt.
    """
    if force.get("verdict") != "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED":
        raise ValueError("1428 verdict drift")

    protocol = force.get("protocol")
    if not isinstance(protocol, dict):
        raise ValueError("1428 protocol scope missing")

    fits = protocol.get("fits")
    new_selfplay = protocol.get("new_selfplay")
    frozen = protocol.get("frozen_cohorts")
    if not isinstance(fits, dict) or fits.get("count") != 0:
        raise ValueError("1428 unexpectedly refit")
    if not isinstance(new_selfplay, dict) or new_selfplay.get("generated") != 0:
        raise ValueError("1428 unexpectedly self-played")
    if not isinstance(frozen, dict) or frozen.get("read") != 0:
        raise ValueError("1428 violated frozen-read contract")
    if protocol.get("models_reused") is not True:
        raise ValueError("1428 violated model-reuse contract")


def validate_1428_force_readout(readout: dict[str, Any]) -> None:
    """Validate the immutable scientific 1428 force readout and promotion scope.

    ``context3-two-pool-force-readout.json`` is the scientific artefact that
    1430 independently authenticated.  Promotion/continuation guards live here,
    not in the runner-controlled JASS_CONTROL_SUMMARY wrapper.  Keeping the two
    schemas separate prevents the technical 1434 failure from recurring.
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
