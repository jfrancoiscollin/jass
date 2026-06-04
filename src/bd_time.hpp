// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Time-breakdown instrumentation, shared across translation units (so
// search.cpp + movegen.cpp can write to the same buckets).
//
// Only active when built with `-DJASS_TIME_BREAKDOWN`. Without it, the
// `BD_TIME(bucket)` macro expands to a no-op so there is no overhead on
// production builds.
//
// Atomics are `inline` (C++17 inline variables) so they have a single
// definition across all TUs that include this header.

#pragma once

#ifdef JASS_TIME_BREAKDOWN

#include <atomic>
#include <chrono>
#include <cstdint>

namespace jass::bd {

// Top-level buckets : already produced by search.cpp call sites.
inline std::atomic<std::uint64_t> g_eval_ns{0};
inline std::atomic<std::uint64_t> g_movegen_ns{0};
inline std::atomic<std::uint64_t> g_apply_ns{0};
inline std::atomic<std::uint64_t> g_accumulator_ns{0};
inline std::atomic<std::uint64_t> g_tt_ns{0};
inline std::atomic<std::uint64_t> g_zobrist_ns{0};
inline std::atomic<std::uint64_t> g_total_ns{0};
inline std::atomic<std::uint64_t> g_total_started{0};

// Movegen sub-buckets : populated from movegen.cpp. Their sum should
// approximately equal g_movegen_ns (modulo the small overhead of the
// outer wrapper itself).
inline std::atomic<std::uint64_t> g_movegen_capture_ns{0};
inline std::atomic<std::uint64_t> g_movegen_quiet_ns{0};

// "other-unaccounted" sub-buckets, added 0102 to investigate the
// ~17% bucket that previously had no decomposition :
//  - move_ordering : selection sort + order_score per node
//  - path_check    : 3-fold repetition (path_contains) + hash_path
//                    push/pop overhead per node
inline std::atomic<std::uint64_t> g_move_ordering_ns{0};
inline std::atomic<std::uint64_t> g_path_check_ns{0};

inline std::uint64_t now_ns() noexcept {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
}

struct ScopedTimer {
    std::atomic<std::uint64_t>& bucket;
    std::uint64_t t0;
    explicit ScopedTimer(std::atomic<std::uint64_t>& b) noexcept
        : bucket(b), t0(now_ns()) {}
    ~ScopedTimer() {
        bucket.fetch_add(now_ns() - t0, std::memory_order_relaxed);
    }
};

}  // namespace jass::bd

#define JASS_BD_TIME_CAT_(a, b) a##b
#define JASS_BD_TIME_CAT(a, b)  JASS_BD_TIME_CAT_(a, b)
#define BD_TIME(bucket) ::jass::bd::ScopedTimer \
    JASS_BD_TIME_CAT(__bd_, __COUNTER__)(::jass::bd::g_##bucket##_ns)

#else
#define BD_TIME(bucket) ((void)0)
#endif
