// SPDX-License-Identifier: AGPL-3.0-or-later
// Compile the preregistered scorer against the HOME-only AttributionEngine.
// Include the production Engine declaration first so the token substitution
// below cannot rename declarations in engine.hpp when the embedded helper is
// parsed.
#include "engine.hpp"
#include "search_semantics_alt.hpp"

#define Engine AttributionEngine
#include "search_semantics_attribution.cpp"
#undef Engine
