#include "mini_jass/enumerate.hpp"

#include "mini_jass/game.hpp"

#include <cstddef>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace mini_jass {
namespace {

void hash_byte(std::uint64_t& hash, const std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}

void hash_u64(std::uint64_t& hash, const std::uint64_t value) noexcept {
    for (unsigned shift = 0; shift < 64; shift += 8) {
        hash_byte(hash, static_cast<std::uint8_t>((value >> shift) & 0xffU));
    }
}

}  // namespace

EnumerationSummary enumerate_reachable_states() {
    std::vector<State> states;
    states.reserve(4096);
    std::map<std::uint64_t, std::uint64_t> state_ids;

    const State initial = initial_state();
    states.push_back(initial);
    state_ids.emplace(state_key(initial), 0);

    EnumerationSummary summary;
    std::uint64_t hash = 14695981039346656037ULL;
    for (const char byte : std::string_view{"mini_jass.graph.v1"}) {
        hash_byte(hash, static_cast<std::uint8_t>(byte));
    }

    for (std::size_t state_id = 0; state_id < states.size(); ++state_id) {
        const State state = states[state_id];
        const std::uint64_t key = state_key(state);
        const TerminalStatus status = terminal_status(state);

        hash_u64(hash, key);
        hash_byte(hash, static_cast<std::uint8_t>(status));

        if (status == TerminalStatus::SideToMoveLoss) {
            ++summary.loss_terminal_count;
            continue;
        }
        if (status == TerminalStatus::Draw) {
            ++summary.draw_terminal_count;
            continue;
        }

        const std::vector<Move> moves = legal_moves(state);
        hash_u64(hash, moves.size());
        for (const Move& move : moves) {
            const auto id = action_id(move);
            if (!id.has_value()) {
                throw std::logic_error{"legal move missing from action vocabulary"};
            }

            const State child = apply_move(state, move);
            const std::uint64_t child_key = state_key(child);
            const auto [iterator, inserted] = state_ids.emplace(child_key, states.size());
            if (inserted) {
                states.push_back(child);
            }

            hash_byte(hash, *id);
            hash_u64(hash, child_key);
            ++summary.transition_count;
            static_cast<void>(iterator);
        }
    }

    summary.state_count = states.size();
    hash_u64(hash, summary.state_count);
    hash_u64(hash, summary.transition_count);
    hash_u64(hash, summary.loss_terminal_count);
    hash_u64(hash, summary.draw_terminal_count);
    summary.graph_hash = hash;
    return summary;
}

}  // namespace mini_jass
