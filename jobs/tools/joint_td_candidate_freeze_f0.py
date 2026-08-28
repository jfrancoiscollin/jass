#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""F0 entrypoint for the preregistered joint T+D fresh-q200 confirmation.

This is intentionally a thin contract shim around the frozen 1614 replay
implementation in joint_td_candidate_freeze.py. It binds the exact prereg and
source attempts requested for F0, then delegates the deterministic M3-only
freeze/replay. No fresh parent/label input surface is exposed here.
"""
from __future__ import annotations

import joint_td_candidate_freeze as freeze

PREREG_SHA = "ffa7d7c802bc2f50731a6d3bb32e80a4c02567d8"
SCREEN_JOB = "cpx62-1614-l3-transfer-capacity-joint-screen-v2"
SCREEN_ATTEMPT = "20260828T092856Z-d8241edc"
READOUT_JOB = "cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1"
READOUT_ATTEMPT = "20260828T100556Z-d8241edc"
T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
A6_G0_SHA = "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
B1_SEED = 2026090402
B1_PARAMETER_COUNT = 875601
C0_L2 = 1e-6
REPLAY_TOL = 1e-12


def verify_frozen_contract() -> None:
    assert freeze.T0_SHA == T0_SHA
    assert freeze.D1_SHA == D1_SHA
    assert freeze.A6_G0_SHA == A6_G0_SHA
    assert freeze.TOL == REPLAY_TOL
    assert freeze.s.B1_SEED == B1_SEED
    assert freeze.s.SPLIT_SEED == 2026090401
    # 1614 C0 semantics are frozen in the delegated implementation.
    src = open(freeze.__file__, "r", encoding="utf-8").read()
    assert "parameter_count\"] != 875601" in src
    assert "fit_dense_pair(c0x, good, bad_rows, l2=1e-6)" in src
    assert '"fresh_q200": 0' in src
    assert '"selfplay": 0' in src
    assert '"strength_games": 0' in src
    assert '"promotion_authorized": False' in src


def main() -> None:
    verify_frozen_contract()
    # Bind the exact preregistration named by F0 before candidate-freeze.json is
    # emitted. Candidate bytes/training semantics remain unchanged.
    freeze.PREREG_SHA = PREREG_SHA
    freeze.main()


if __name__ == "__main__":
    main()
