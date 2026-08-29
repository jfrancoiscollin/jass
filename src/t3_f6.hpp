// SPDX-License-Identifier: AGPL-3.0-or-later
// Frozen T3-A/F6 residual leaf evaluator. Dormant unless explicitly enabled.
#pragma once

#include "nnue.hpp"
#include "residual_features.hpp"

#include <array>
#include <cstddef>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace jass::t3_f6 {

inline constexpr std::size_t INPUT_WIDTH = residual_features::ALL_NEW_WIDTH;
inline constexpr std::size_t H0 = 256;
inline constexpr std::size_t H1 = 128;
inline constexpr std::size_t H2 = 64;

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

std::string sha256_file(const std::string& path, std::string* err = nullptr);
std::optional<Model> load_model(const std::string& path,
                                LoadPolicy policy = LoadPolicy::FrozenOnly,
                                std::string* err = nullptr);

class Network final : public INetwork {
public:
    Network(std::unique_ptr<INetwork> base, Model model)
        : base_(std::move(base)), model_(std::move(model)) {}

    int evaluate(const Position& pos) const noexcept override;
    int evaluate_from_base(const Position& pos, int base_score) const noexcept;
    double residual_parent(const Position& pos) const noexcept;
    const INetwork* base_network() const noexcept { return base_.get(); }
    const Model& model() const noexcept { return model_; }

private:
    std::unique_ptr<INetwork> base_;
    Model model_;
};

// Absent env: exact no-op. Present env: authenticate model and CURRICULUM,
// validate the full contract and fail closed on any discrepancy.
std::unique_ptr<INetwork> maybe_wrap_from_env(
    std::unique_ptr<INetwork> base,
    const std::string& base_path,
    std::string* err = nullptr);

}  // namespace jass::t3_f6
