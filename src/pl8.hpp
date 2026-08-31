// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "nnue.hpp"
#include "position.hpp"
#include "scan_eval.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>

namespace jass::pl8 {

inline constexpr std::size_t PATTERN_INPUTS = 16;
inline constexpr std::size_t EXTRA_INPUTS = 120;
inline constexpr std::size_t INPUT_WIDTH = 138;
inline constexpr std::size_t LATENT_WIDTH = 8;
inline constexpr std::size_t LEARNED_PARAMS = 1121;
inline constexpr double TEMPERATURE_CP = 100.0;
inline constexpr std::uint64_t FIT_SEED = 2026103101ULL;
inline constexpr std::uint64_t ANCHOR_SEED = 2026103102ULL;
inline constexpr std::uint64_t FRESH_SELECT_SEED = 2026103120ULL;
inline constexpr std::uint64_t FRESH_BOOTSTRAP_SEED = 2026103121ULL;
inline constexpr const char* CURRICULUM_SHA256 =
    "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1";

struct Model {
    std::array<double, INPUT_WIDTH> mu{};
    std::array<double, INPUT_WIDTH> sigma{};
    std::array<double, LATENT_WIDTH * INPUT_WIDTH> w1{};  // row-major [8,138]
    std::array<double, LATENT_WIDTH> b1{};
    std::array<double, LATENT_WIDTH> w2{};
    double b2{0.0};
    double shrink{1.0};
    std::string curriculum_sha256{CURRICULUM_SHA256};
};

// Project-standard rotate180 + colour-swap canonicalization. The result is
// always side-to-move Black. Black-to-move input is returned unchanged.
Position canonical_stm_black(const Position& pos) noexcept;

// Exact production tempo-stage scalar used by the frozen 120-extra CURRICULUM.
double tempo_wmg_exact(const Position& pos) noexcept;

class FeatureExtractor {
public:
    explicit FeatureExtractor(scan_eval::ScanWeights weights);

    // 138 frozen PL8 scalars:
    // 16 active pattern mg/eg contributions, 120 raw compute_extras values,
    // exact production phase_wmg, exact byte-identical CURRICULUM T0 score.
    std::array<double, INPUT_WIDTH> extract(const Position& pos) const noexcept;
    int base_score(const Position& pos) const noexcept;

private:
    scan_eval::PatPair pair_at(std::size_t global_col) const noexcept;

    scan_eval::ScanWeights weights_;
    std::unique_ptr<scan_eval::ScanEvalNetwork> base_;
};

class Network final : public INetwork {
public:
    Network(scan_eval::ScanWeights curriculum, Model model);
    int evaluate(const Position& pos) const noexcept override;
    const Model& model() const noexcept { return model_; }
    std::array<double, INPUT_WIDTH> input(const Position& pos) const noexcept {
        return extractor_.extract(pos);
    }

private:
    FeatureExtractor extractor_;
    Model model_;
};

// Binary PL8P v1 serializer/loader. The artifact stores no CURRICULUM table;
// the exact baseline remains an external byte-identical PJTW authenticated by
// its frozen SHA-256 identity.
bool save_model(const std::string& path, const Model& model,
                std::string* error = nullptr);
std::optional<Model> load_model(const std::string& path,
                                std::string* error = nullptr);
std::unique_ptr<Network> load_network(const std::string& curriculum_path,
                                      const std::string& model_path,
                                      std::string* error = nullptr);

}  // namespace jass::pl8
