// SPDX-License-Identifier: AGPL-3.0-or-later
// HOME-only compilation shim: the frozen Attribution V1 search implementation
// is compiled under private public-symbol names. This avoids any mutation or
// replacement of the production develop/V4 search linked in jass_lib.

#define search attribution_search_internal
#define extract_pv attribution_extract_pv_internal
#define breakdown_reset attribution_breakdown_reset_internal
#define breakdown_snapshot attribution_breakdown_snapshot_internal
#include "search_semantics_alt_search_body.inc"
#undef breakdown_snapshot
#undef breakdown_reset
#undef extract_pv
#undef search
