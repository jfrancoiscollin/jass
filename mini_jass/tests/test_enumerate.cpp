#include "mini_jass/enumerate.hpp"

#include <iostream>

namespace {

int failures = 0;

void expect(const bool condition, const char* const message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

}  // namespace

int main() {
    const mini_jass::EnumerationSummary first = mini_jass::enumerate_reachable_states();
    const mini_jass::EnumerationSummary second = mini_jass::enumerate_reachable_states();

    expect(first == second, "two enumerations produce the same summary and graph hash");
    expect(first == mini_jass::kReachableGraphV1,
           "reachable graph matches the frozen v1 summary and hash");

    std::cout << "states=" << first.state_count << '\n'
              << "transitions=" << first.transition_count << '\n'
              << "loss_terminals=" << first.loss_terminal_count << '\n'
              << "draw_terminals=" << first.draw_terminal_count << '\n'
              << "graph_hash=" << first.graph_hash << '\n';

    if (failures != 0) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    return 0;
}
