// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include <array>
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace jass::d4b_runtime_order {

inline constexpr std::size_t FEATURE_WIDTH = 24;
inline constexpr std::size_t PHASES = 4;
inline constexpr std::size_t WIDTH = FEATURE_WIDTH * PHASES;

struct Runtime {
    bool active{false};
    std::array<double, WIDTH> beta{};
};

inline std::atomic<std::uint64_t> g_eligible_nodes{0};
inline std::atomic<std::uint64_t> g_hoists{0};

inline int phase_index(int pieces) noexcept {
    if (33 <= pieces && pieces <= 40) return 0;
    if (25 <= pieces && pieces <= 32) return 1;
    if (17 <= pieces && pieces <= 24) return 2;
    if (9 <= pieces && pieces <= 16) return 3;
    return -1;
}

inline bool read_npy96(const std::string& path, std::array<double, WIDTH>& out,
                       std::string& err) {
    static_assert(std::endian::native == std::endian::little,
                  "D4b sealed npy runtime requires little-endian host");
    std::ifstream f(path, std::ios::binary);
    if (!f) { err = "cannot open model " + path; return false; }
    f.seekg(0, std::ios::end); const auto n = f.tellg(); f.seekg(0, std::ios::beg);
    if (n < 16) { err = "model npy too short"; return false; }
    std::vector<unsigned char> raw(static_cast<std::size_t>(n));
    f.read(reinterpret_cast<char*>(raw.data()), n);
    if (!f) { err = "model npy read failure"; return false; }
    const unsigned char magic[6] = {0x93, 'N', 'U', 'M', 'P', 'Y'};
    if (std::memcmp(raw.data(), magic, 6) != 0) { err = "model npy magic mismatch"; return false; }
    const unsigned major = raw[6]; std::size_t hlen = 0, hoff = 0;
    if (major == 1) {
        if (raw.size() < 10) { err = "model npy v1 header truncated"; return false; }
        hlen = static_cast<std::size_t>(raw[8]) | (static_cast<std::size_t>(raw[9]) << 8); hoff = 10;
    } else if (major == 2 || major == 3) {
        if (raw.size() < 12) { err = "model npy v2/v3 header truncated"; return false; }
        hlen = static_cast<std::size_t>(raw[8]) | (static_cast<std::size_t>(raw[9]) << 8)
             | (static_cast<std::size_t>(raw[10]) << 16) | (static_cast<std::size_t>(raw[11]) << 24); hoff = 12;
    } else { err = "unsupported model npy version"; return false; }
    if (hoff + hlen > raw.size()) { err = "model npy header overflow"; return false; }
    const std::string header(reinterpret_cast<const char*>(raw.data() + hoff), hlen);
    const bool descr_ok = header.find("'<f8'") != std::string::npos || header.find("\"<f8\"") != std::string::npos;
    if (!descr_ok || header.find("False") == std::string::npos || header.find("96") == std::string::npos) {
        err = "model npy dtype/order/shape mismatch"; return false;
    }
    const std::size_t data = hoff + hlen;
    if (raw.size() != data + WIDTH * sizeof(double)) { err = "model npy payload size mismatch"; return false; }
    std::memcpy(out.data(), raw.data() + data, WIDTH * sizeof(double));
    for (double v : out) if (!std::isfinite(v)) { err = "model contains non-finite weight"; return false; }
    return true;
}

inline const Runtime& runtime() {
    static const Runtime rt = [] {
        Runtime out;
        const char* path = std::getenv("JASS_D4B_RUNTIME_MODEL");
        if (!path) return out;
        std::string err;
        if (!read_npy96(path, out.beta, err)) {
            std::cerr << "D4B_RUNTIME_INVALID: " << err << '\n'; std::abort();
        }
        out.active = true; return out;
    }();
    return rt;
}

inline double logit(const Runtime& rt, int phase, int legacy_rank,
                    const std::array<double, FEATURE_WIDTH>& features) noexcept {
    const std::size_t base = static_cast<std::size_t>(phase) * FEATURE_WIDTH;
    double s = -static_cast<double>(legacy_rank - 1);
    for (std::size_t i = 0; i < FEATURE_WIDTH; ++i) s += rt.beta[base + i] * features[i];
    return s;
}

inline void reset_counters() noexcept { g_eligible_nodes.store(0); g_hoists.store(0); }
inline void note_eligible() noexcept { g_eligible_nodes.fetch_add(1, std::memory_order_relaxed); }
inline void note_hoist() noexcept { g_hoists.fetch_add(1, std::memory_order_relaxed); }
inline std::uint64_t eligible_nodes() noexcept { return g_eligible_nodes.load(std::memory_order_relaxed); }
inline std::uint64_t hoists() noexcept { return g_hoists.load(std::memory_order_relaxed); }

}  // namespace jass::d4b_runtime_order
