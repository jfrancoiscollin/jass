// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "nnue.hpp"
#include "position.hpp"

#include <cstddef>
#include <memory>

namespace jass::chinook_hybrid {

bool gate_components(int total_pieces, std::size_t legal_moves,
                     int stm_material_margin) noexcept;
bool gate(const Position& pos) noexcept;

class Network final : public INetwork {
public:
    Network(std::unique_ptr<INetwork> curriculum,
            std::unique_ptr<INetwork> hier)
        : curriculum_(std::move(curriculum)), hier_(std::move(hier)) {}

    int evaluate(const Position& pos) const noexcept override;

private:
    std::unique_ptr<INetwork> curriculum_;
    std::unique_ptr<INetwork> hier_;
};

}  // namespace jass::chinook_hybrid
