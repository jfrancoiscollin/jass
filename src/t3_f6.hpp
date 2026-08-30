// SPDX-License-Identifier: AGPL-3.0-or-later
// Frozen T3-A/F6 residual leaf evaluator. Dormant unless explicitly enabled.
#pragma once

#include "nnue.hpp"
#include "residual_features.hpp"
#include "search.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace jass::t3_f6 {

inline constexpr std::size_t INPUT_WIDTH = residual_features::ALL_NEW_WIDTH;
inline constexpr std::size_t H0 = 256;
inline constexpr std::size_t H1 = 128;
inline constexpr std::size_t H2 = 64;
inline constexpr std::size_t CACHE_CAPACITY = 65536;

inline constexpr const char* FROZEN_MODEL_SHA256 =
    "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2";
inline constexpr const char* FROZEN_CURRICULUM_SHA256 =
    "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1";
inline constexpr const char* FROZEN_RF1_SHA256 =
    "0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b";
inline constexpr const char* FROZEN_D1_SHA256 =
    "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49";
inline constexpr const char* FROZEN_FEATURE_ORDER_SHA256 =
    "cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e";
// Data-free, diagnostic-only V4 artifact. The production environment loader
// never accepts this SHA; only the explicit ZeroProbeOnly policy does.
inline constexpr const char* V4_ZERO_PROBE_SHA256 =
    "160489327d419e3d7bbbbda900d6e0ec7bc960111149fc0a45cc27aaa55bf6aa";

enum class LoadPolicy { FrozenOnly, ZeroProbeOnly, SchemaOnly };

struct Model {
    std::array<double, INPUT_WIDTH> mean{};
    std::array<double, INPUT_WIDTH> stddev{};
    std::vector<double> w0;  // INPUT_WIDTH x H0, input-major
    std::array<double, H0> b0{};
    std::vector<double> w1;  // H0 x H1, input-major
    std::array<double, H1> b1{};
    std::vector<double> w2;  // H1 x H2, input-major
    std::array<double, H2> b2{};
    std::array<double, H2> w3{};
    double b3{0.0};

    double residual_parent(
        const std::array<float, INPUT_WIDTH>& features) const noexcept;
};

struct CacheStats {
    std::uint64_t lookups{0};
    std::uint64_t hits{0};
    std::uint64_t misses{0};
    std::uint64_t replacements{0};
    std::uint64_t extract_f6_executions{0};
};

std::string sha256_file(const std::string& path, std::string* err = nullptr);
std::optional<Model> load_model(const std::string& path,
                                LoadPolicy policy = LoadPolicy::FrozenOnly,
                                std::string* err = nullptr);

class O1SearchSession;

class Network final : public INetwork {
public:
    // Historical/control path: cache is always OFF.
    Network(std::unique_ptr<INetwork> base, Model model)
        : base_(std::move(base)), model_(std::move(model)) {}

    int evaluate(const Position& pos) const noexcept override;
    int evaluate_from_base(const Position& pos, int base_score) const noexcept;
    double residual_parent(const Position& pos) const noexcept;
    const INetwork* base_network() const noexcept { return base_.get(); }
    const Model& model() const noexcept { return model_; }

    bool cache_enabled() const noexcept { return cache_enabled_; }
    bool thread_contract_ok(int threads) const noexcept {
        return !cache_enabled_ || threads == 1;
    }
    CacheStats cache_stats() const noexcept { return cache_stats_; }
    void clear_cache() const noexcept;
    static std::uint16_t cache_index(const Position& pos) noexcept;

private:
    friend class O1SearchSession;
    struct CacheActivation {};

    Network(std::unique_ptr<INetwork> base, Model model, CacheActivation)
        : base_(std::move(base)), model_(std::move(model)),
          cache_enabled_(true), cache_(CACHE_CAPACITY) {}

    // Private by design: no production/HUB caller can obtain a cache-enabled
    // Network and then pass it to Lazy SMP. O1SearchSession is the sole legal
    // owner and re-validates the actual SearchLimits::threads immediately
    // before every search call.
    static std::unique_ptr<Network> make_o1_cached(
        std::unique_ptr<INetwork> base, Model model, int threads,
        std::string* err = nullptr);

    struct CacheKey {
        std::uint64_t white_men{0};
        std::uint64_t white_kings{0};
        std::uint64_t black_men{0};
        std::uint64_t black_kings{0};
        std::uint8_t side_to_move{0};

        friend bool operator==(const CacheKey& a, const CacheKey& b) noexcept {
            return a.white_men == b.white_men
                && a.white_kings == b.white_kings
                && a.black_men == b.black_men
                && a.black_kings == b.black_kings
                && a.side_to_move == b.side_to_move;
        }
    };

    struct CacheEntry {
        CacheKey key{};
        double residual{0.0};
        bool valid{false};
    };

    static CacheKey cache_key(const Position& pos) noexcept;
    static std::uint16_t cache_index(const CacheKey& key) noexcept;

    std::unique_ptr<INetwork> base_;
    Model model_;
    bool cache_enabled_{false};
    mutable std::vector<CacheEntry> cache_;
    mutable CacheStats cache_stats_{};
};

// The only public O1 activation surface. It owns the cached Network privately,
// so callers cannot hand the mutable cache to the generic search/HUB API. Both
// construction and the actual search boundary fail closed unless threads==1.
// A session can perform at most one search, and that search is rejected unless
// the cache is still cold. Thus every Gate-C/D root×budget unit necessarily
// starts from a fresh Network/cache and cannot inherit prior root/search state.
// The two-argument jass::search overload creates a fresh TT for the accepted
// search call as required by the preregistered lifecycle.
class O1SearchSession final {
public:
    static std::unique_ptr<O1SearchSession> create(
        std::unique_ptr<INetwork> base, Model model, int threads,
        std::string* err = nullptr) {
        auto network = Network::make_o1_cached(
            std::move(base), std::move(model), threads, err);
        if (!network) return nullptr;
        return std::unique_ptr<O1SearchSession>(
            new O1SearchSession(std::move(network)));
    }

    std::optional<SearchResult> run_search(
        const Position& pos, SearchLimits limits,
        std::string* err = nullptr) const {
        if (limits.threads != 1) {
            if (err) *err = "T3/F6 O1 cache requires SearchLimits::threads == 1";
            return std::nullopt;
        }
        if (limits.nnue != nullptr) {
            if (err) *err = "T3/F6 O1 session owns SearchLimits::nnue";
            return std::nullopt;
        }
        if (search_consumed_) {
            if (err) *err = "T3/F6 O1 search session is one-shot";
            return std::nullopt;
        }
        const CacheStats before = network_->cache_stats();
        if (before.lookups != 0 || before.hits != 0 || before.misses != 0
            || before.replacements != 0 || before.extract_f6_executions != 0) {
            if (err) *err = "T3/F6 O1 search requires a cold cache";
            return std::nullopt;
        }
        search_consumed_ = true;
        limits.nnue = network_.get();
        return jass::search(pos, limits);
    }

    int evaluate(const Position& pos) const noexcept {
        return network_->evaluate(pos);
    }
    int evaluate_from_base(const Position& pos, int base_score) const noexcept {
        return network_->evaluate_from_base(pos, base_score);
    }
    double residual_parent(const Position& pos) const noexcept {
        return network_->residual_parent(pos);
    }
    CacheStats cache_stats() const noexcept { return network_->cache_stats(); }
    void clear_cache() const noexcept { network_->clear_cache(); }

private:
    explicit O1SearchSession(std::unique_ptr<Network> network)
        : network_(std::move(network)) {}

    std::unique_ptr<Network> network_;
    mutable bool search_consumed_{false};
};

// Production T3 loader remains the exact pre-O1 behavior: absent model env is
// a no-op; present model env authenticates the frozen model and CURRICULUM and
// returns a cache-OFF Network. O1 cache activation is deliberately impossible
// through environment variables and is restricted to O1SearchSession.
std::unique_ptr<INetwork> maybe_wrap_from_env(
    std::unique_ptr<INetwork> base,
    const std::string& base_path,
    std::string* err = nullptr);

}  // namespace jass::t3_f6
