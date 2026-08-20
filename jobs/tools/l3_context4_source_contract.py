#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Certified source-contract checks for the CTX4 read-only screen."""

from __future__ import annotations

from typing import Any


def validate_1428_force_summary(force: dict[str, Any]) -> None:
    """Validate the immutable 1428 force-summary scope used by CTX4.

    The certified 1428 schema stores execution-scope guards under ``protocol``.
    Keeping this check in one tested function prevents a silent return to the
    obsolete top-level fields that caused the technical 1431 abort.
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
