// SPDX-License-Identifier: AGPL-3.0-or-later
#include "test_framework.hpp"

#include "chinook_hybrid.hpp"
#include "position.hpp"

#include <memory>

using namespace jass;

namespace {

class ConstantNetwork final : public INetwork {
public:
    explicit ConstantNetwork(int value) : value_(value) {}
    int evaluate(const Position&) const noexcept override { return value_; }
private:
    int value_;
};

void test_gate_components() {
    using chinook_hybrid::gate_components;
    JASS_CHECK(gate_components(12, 5, -1));
    JASS_CHECK(gate_components(19, 8, -4));
    JASS_CHECK(!gate_components(20, 5, -1));
    JASS_CHECK(!gate_components(8, 5, -1));
    JASS_CHECK(!gate_components(12, 4, -1));
    JASS_CHECK(!gate_components(12, 9, -1));
    JASS_CHECK(!gate_components(12, 5, 0));
    JASS_CHECK(!gate_components(12, 5, 2));
}

void test_network_off_gate_uses_curriculum() {
    auto parsed = Position::from_fen("W:W31-50:B1-20");
    JASS_CHECK(parsed.has_value());
    const Position pos = *parsed;
    chinook_hybrid::Network net(
        std::make_unique<ConstantNetwork>(11),
        std::make_unique<ConstantNetwork>(99));
    JASS_CHECK_EQ(net.evaluate(pos), 11);
}

}  // namespace

void run_chinook_hybrid_tests() {
    test_gate_components();
    test_network_off_gate_uses_curriculum();
}
