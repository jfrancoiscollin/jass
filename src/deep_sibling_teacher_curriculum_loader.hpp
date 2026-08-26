// SPDX-License-Identifier: AGPL-3.0-or-later
// Technical compatibility shim for the frozen DSSD teacher.
//
// CURRICULUM is the production ScanEval PJTW (self-describing v3, version
// word 0x203/515), not the legacy PatternJass v1 layout.  Pre-include this
// header when building src/deep_sibling_teacher.cpp so its historical
// load_pattern_jass_network(...) call resolves to the same unified production
// loader used by Jass for modern PJTW files.  This changes no search, label,
// budget, feature, split, or acceptance rule.
#pragma once

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
