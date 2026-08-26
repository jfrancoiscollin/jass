// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-Francois Collin
//
// Technical compatibility entry point for the DSSD teacher.
//
// The frozen CURRICULUM champion is a self-describing ScanEval PJTW v3 file
// (version word 0x203 = 515), so it must be loaded through Jass's unified
// load_eval_network() dispatcher rather than the legacy PJTW-v1-only
// load_pattern_jass_network() helper.  This translation-unit shim deliberately
// changes only that loader dispatch; the teacher implementation, search
// budgets, TT semantics, sibling ordering, score convention, and outputs remain
// byte-for-byte the implementation in deep_sibling_teacher.cpp.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

// Both declarations are parsed before the macro is introduced.  The included
// implementation's call site is then redirected to the unified loader without
// altering any other teacher code.
#define load_pattern_jass_network load_eval_network
#include "deep_sibling_teacher.cpp"
#undef load_pattern_jass_network
