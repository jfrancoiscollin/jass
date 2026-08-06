#include "mini_jass/solver.hpp"

#include "mini_jass/enumerate.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace mini_jass {
namespace {

using StateId = std::uint32_t;

struct GraphNode {
    State state;
    TerminalStatus terminal{TerminalStatus::Ongoing};
    std::vector<OracleTransition> transitions;
};

struct Graph {
    std::vector<GraphNode> nodes;
    std::map<std::uint64_t, StateId> ids;
    EnumerationSummary summary;
};

struct NodeSolution {
    ExactValue value{ExactValue::Draw};
    bool resolved{};
    std::optional<std::uint16_t> dtw;
    std::vector<std::uint8_t> optimal_actions;
};

struct NormalizedState {
    State state;
    bool transformed{};
};

void hash_byte(std::uint64_t& hash, const std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}

void hash_u64(std::uint64_t& hash, const std::uint64_t value) noexcept {
    for (unsigned shift = 0; shift < 64; shift += 8) {
        hash_byte(hash, static_cast<std::uint8_t>((value >> shift) & 0xffU));
    }
}

void hash_text(std::uint64_t& hash, const std::string_view text) noexcept {
    for (const char byte : text) {
        hash_byte(hash, static_cast<std::uint8_t>(byte));
    }
}

[[nodiscard]] std::uint64_t fnv1a(const std::string_view text) noexcept {
    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, text);
    return hash;
}

[[nodiscard]] NormalizedState normalize_state(
    const State& state,
    const bool canonical) noexcept {
    if (!canonical) {
        return {state, false};
    }
    const State transformed = rotate180_and_swap_colours(state);
    if (state_key(transformed) < state_key(state)) {
        return {transformed, true};
    }
    return {state, false};
}

[[nodiscard]] EnumerationSummary hash_graph(
    const Graph& graph,
    const std::string_view schema) {
    EnumerationSummary summary;
    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, schema);

    for (const GraphNode& node : graph.nodes) {
        hash_u64(hash, state_key(node.state));
        hash_byte(hash, static_cast<std::uint8_t>(node.terminal));

        if (node.terminal == TerminalStatus::SideToMoveLoss) {
            ++summary.loss_terminal_count;
            continue;
        }
        if (node.terminal == TerminalStatus::Draw) {
            ++summary.draw_terminal_count;
            continue;
        }

        hash_u64(hash, node.transitions.size());
        for (const OracleTransition& transition : node.transitions) {
            hash_byte(hash, transition.action);
            hash_u64(hash, state_key(graph.nodes[transition.child_id].state));
            ++summary.transition_count;
        }
    }

    summary.state_count = graph.nodes.size();
    hash_u64(hash, summary.state_count);
    hash_u64(hash, summary.transition_count);
    hash_u64(hash, summary.loss_terminal_count);
    hash_u64(hash, summary.draw_terminal_count);
    summary.graph_hash = hash;
    return summary;
}

[[nodiscard]] Graph build_graph(const bool canonical) {
    Graph graph;
    graph.nodes.reserve(kReachableGraphV1.state_count);

    const State root = normalize_state(initial_state(), canonical).state;
    graph.nodes.push_back(GraphNode{root, TerminalStatus::Ongoing, {}});
    graph.ids.emplace(state_key(root), 0);

    for (std::size_t state_id = 0; state_id < graph.nodes.size(); ++state_id) {
        const State state = graph.nodes[state_id].state;
        const TerminalStatus terminal = terminal_status(state);
        graph.nodes[state_id].terminal = terminal;
        if (terminal != TerminalStatus::Ongoing) {
            continue;
        }

        const std::vector<Move> moves = legal_moves(state);
        std::vector<OracleTransition> transitions;
        transitions.reserve(moves.size());
        for (const Move& move : moves) {
            const auto action = action_id(move);
            if (!action.has_value()) {
                throw std::logic_error{"legal move missing from action vocabulary"};
            }

            const State raw_child = apply_move(state, move);
            const State child = normalize_state(raw_child, canonical).state;
            const std::uint64_t child_key = state_key(child);
            const auto [iterator, inserted] = graph.ids.emplace(
                child_key, static_cast<StateId>(graph.nodes.size()));
            if (inserted) {
                if (graph.nodes.size() >= std::numeric_limits<StateId>::max()) {
                    throw std::overflow_error{"Mini-Jass graph exceeds 32-bit state IDs"};
                }
                graph.nodes.push_back(GraphNode{child, TerminalStatus::Ongoing, {}});
            }
            transitions.push_back(OracleTransition{*action, iterator->second});
        }
        graph.nodes[state_id].transitions = std::move(transitions);
    }

    graph.summary = hash_graph(
        graph, canonical ? "mini_jass.canonical_graph.v1" : "mini_jass.graph.v1");
    if (!canonical && graph.summary != kReachableGraphV1) {
        throw std::logic_error{"raw solver graph differs from the frozen M1 graph"};
    }
    return graph;
}

[[nodiscard]] std::uint16_t plus_one(const std::uint16_t value) {
    if (value == std::numeric_limits<std::uint16_t>::max()) {
        throw std::overflow_error{"Mini-Jass DTW exceeds 16 bits"};
    }
    return static_cast<std::uint16_t>(value + 1);
}

[[nodiscard]] std::vector<NodeSolution> solve_graph(const Graph& graph) {
    const std::size_t state_count = graph.nodes.size();
    std::vector<NodeSolution> solutions(state_count);
    std::vector<std::vector<StateId>> predecessors(state_count);
    std::vector<std::uint32_t> remaining(state_count);
    std::vector<std::uint16_t> maximum_child_dtw(state_count);

    for (StateId parent = 0; parent < state_count; ++parent) {
        const GraphNode& node = graph.nodes[parent];
        remaining[parent] = static_cast<std::uint32_t>(node.transitions.size());
        for (const OracleTransition& transition : node.transitions) {
            predecessors[transition.child_id].push_back(parent);
        }
    }

    using QueueEntry = std::pair<std::uint16_t, StateId>;
    std::priority_queue<QueueEntry, std::vector<QueueEntry>, std::greater<>> queue;
    for (StateId state_id = 0; state_id < state_count; ++state_id) {
        const TerminalStatus terminal = graph.nodes[state_id].terminal;
        if (terminal == TerminalStatus::SideToMoveLoss) {
            solutions[state_id].value = ExactValue::Loss;
            solutions[state_id].resolved = true;
            solutions[state_id].dtw = 0;
            queue.emplace(0, state_id);
        } else if (terminal == TerminalStatus::Draw) {
            solutions[state_id].value = ExactValue::Draw;
            solutions[state_id].resolved = true;
        }
    }

    while (!queue.empty()) {
        const auto [distance, child] = queue.top();
        queue.pop();
        const ExactValue child_value = solutions[child].value;

        for (const StateId parent : predecessors[child]) {
            NodeSolution& parent_solution = solutions[parent];
            if (parent_solution.resolved) {
                continue;
            }

            if (child_value == ExactValue::Loss) {
                parent_solution.value = ExactValue::Win;
                parent_solution.resolved = true;
                parent_solution.dtw = plus_one(distance);
                queue.emplace(*parent_solution.dtw, parent);
                continue;
            }

            if (child_value != ExactValue::Win || remaining[parent] == 0) {
                continue;
            }
            --remaining[parent];
            maximum_child_dtw[parent] = std::max(maximum_child_dtw[parent], distance);
            if (remaining[parent] == 0) {
                parent_solution.value = ExactValue::Loss;
                parent_solution.resolved = true;
                parent_solution.dtw = plus_one(maximum_child_dtw[parent]);
                queue.emplace(*parent_solution.dtw, parent);
            }
        }
    }

    for (std::size_t state_id = 0; state_id < state_count; ++state_id) {
        NodeSolution& solution = solutions[state_id];
        if (!solution.resolved) {
            solution.value = ExactValue::Draw;
            solution.resolved = true;
        }

        const GraphNode& node = graph.nodes[state_id];
        if (node.terminal != TerminalStatus::Ongoing) {
            continue;
        }

        int best = -2;
        for (const OracleTransition& transition : node.transitions) {
            const int score = -static_cast<int>(solutions[transition.child_id].value);
            if (score > best) {
                best = score;
                solution.optimal_actions.clear();
            }
            if (score == best) {
                solution.optimal_actions.push_back(transition.action);
            }
        }
        if (best != static_cast<int>(solution.value) || solution.optimal_actions.empty()) {
            throw std::logic_error{"retrograde value violates the negamax recurrence"};
        }
    }
    return solutions;
}

[[nodiscard]] std::array<std::uint8_t, kActionCount> transformed_action_ids() {
    std::array<std::uint8_t, kActionCount> result{};
    const auto& vocabulary = action_vocabulary();
    for (std::size_t action = 0; action < vocabulary.size(); ++action) {
        const auto transformed = action_id(rotate180_move(vocabulary[action]));
        if (!transformed.has_value()) {
            throw std::logic_error{"rotated move missing from action vocabulary"};
        }
        result[action] = *transformed;
    }
    for (std::size_t action = 0; action < result.size(); ++action) {
        if (result[result[action]] != action) {
            throw std::logic_error{"action rotation is not an involution"};
        }
    }
    return result;
}

[[nodiscard]] std::uint64_t hash_solver(
    const Graph& raw,
    const std::vector<NodeSolution>& solutions,
    const std::vector<StateId>& canonical_ids,
    const std::vector<bool>& canonical_transforms,
    const std::uint64_t canonical_graph_hash) {
    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, "mini_jass.solver.v1");
    hash_u64(hash, action_vocabulary_hash());
    hash_u64(hash, raw.summary.graph_hash);
    hash_u64(hash, canonical_graph_hash);

    for (std::size_t state_id = 0; state_id < raw.nodes.size(); ++state_id) {
        const GraphNode& node = raw.nodes[state_id];
        const NodeSolution& solution = solutions[state_id];
        hash_u64(hash, state_key(node.state));
        hash_byte(hash, static_cast<std::uint8_t>(node.terminal));
        hash_byte(hash, static_cast<std::uint8_t>(static_cast<int>(solution.value) + 1));
        hash_u64(hash, solution.dtw.has_value()
                           ? *solution.dtw
                           : std::numeric_limits<std::uint64_t>::max());
        hash_u64(hash, canonical_ids[state_id]);
        hash_byte(hash, canonical_transforms[state_id] ? 1 : 0);
        hash_u64(hash, node.transitions.size());
        for (const OracleTransition& transition : node.transitions) {
            hash_byte(hash, transition.action);
            hash_u64(hash, state_key(raw.nodes[transition.child_id].state));
        }
        hash_u64(hash, solution.optimal_actions.size());
        for (const std::uint8_t action : solution.optimal_actions) {
            hash_byte(hash, action);
        }
    }
    return hash;
}

[[nodiscard]] std::string manifest_hash_payload(const SolverManifest& manifest) {
    std::ostringstream output;
    output << "mini_jass.solver_manifest.v1\n"
           << "rule_schema=mini_jass.rules.l1.v1\n"
           << "board_size=5\n"
           << "playable_squares=13\n"
           << "square_coordinates=0:0,0:2,0:4,1:1,1:3,2:0,2:2,2:4,3:1,3:3,4:0,4:2,4:4\n"
           << "initial_state_key=46080\n"
           << "maximum_pieces_per_side=2\n"
           << "reversible_ply_limit=20\n"
           << "men_capture_directions=forward_and_backward\n"
           << "king_type=short\n"
           << "mandatory_capture=true\n"
           << "capture_priority=all_complete_continuations\n"
           << "promotion_timing=after_complete_move\n"
           << "terminal_precedence=no_piece_or_legal_move,reversible_ply_limit\n"
           << "square_permutation=12,11,10,9,8,7,6,5,4,3,2,1,0\n"
           << "action_schema=mini_jass.actions.v1\n"
           << "raw_state_count=" << manifest.raw_state_count << '\n'
           << "raw_transition_count=" << manifest.raw_transition_count << '\n'
           << "canonical_state_count=" << manifest.canonical_state_count << '\n'
           << "canonical_transition_count=" << manifest.canonical_transition_count << '\n'
           << "win_count=" << manifest.win_count << '\n'
           << "draw_count=" << manifest.draw_count << '\n'
           << "loss_count=" << manifest.loss_count << '\n'
           << "maximum_dtw=" << manifest.maximum_dtw << '\n'
           << "initial_value=" << static_cast<int>(manifest.initial_value) << '\n'
           << "initial_dtw=";
    if (manifest.initial_dtw.has_value()) {
        output << *manifest.initial_dtw;
    } else {
        output << "null";
    }
    output << '\n'
           << "action_vocabulary_hash=" << manifest.action_vocabulary_hash << '\n'
           << "raw_graph_hash=" << manifest.raw_graph_hash << '\n'
           << "canonical_graph_hash=" << manifest.canonical_graph_hash << '\n'
           << "solver_hash=" << manifest.solver_hash << '\n';
    return output.str();
}

}  // namespace

ExactOracle solve_exact_oracle() {
    const Graph raw = build_graph(false);
    const std::vector<NodeSolution> raw_solutions = solve_graph(raw);
    const Graph canonical = build_graph(true);
    const std::vector<NodeSolution> canonical_solutions = solve_graph(canonical);
    const auto rotated_actions = transformed_action_ids();

    std::vector<StateId> canonical_ids(raw.nodes.size());
    std::vector<bool> canonical_transforms(raw.nodes.size());

    for (std::size_t state_id = 0; state_id < raw.nodes.size(); ++state_id) {
        const NormalizedState normalized = normalize_state(raw.nodes[state_id].state, true);
        const auto canonical_iterator = canonical.ids.find(state_key(normalized.state));
        if (canonical_iterator == canonical.ids.end()) {
            throw std::logic_error{"raw state is missing from the canonical graph"};
        }
        const StateId canonical_id = canonical_iterator->second;
        canonical_ids[state_id] = canonical_id;
        canonical_transforms[state_id] = normalized.transformed;

        if (raw_solutions[state_id].value != canonical_solutions[canonical_id].value ||
            raw_solutions[state_id].dtw != canonical_solutions[canonical_id].dtw ||
            raw.nodes[state_id].terminal != canonical.nodes[canonical_id].terminal) {
            throw std::logic_error{"raw and canonical state values differ"};
        }

        std::vector<std::uint8_t> mapped_optimal = raw_solutions[state_id].optimal_actions;
        if (normalized.transformed) {
            for (std::uint8_t& action : mapped_optimal) {
                action = rotated_actions[action];
            }
            std::sort(mapped_optimal.begin(), mapped_optimal.end());
        }
        if (mapped_optimal != canonical_solutions[canonical_id].optimal_actions) {
            throw std::logic_error{"raw and canonical optimal move sets differ"};
        }

        std::vector<OracleTransition> mapped_transitions;
        mapped_transitions.reserve(raw.nodes[state_id].transitions.size());
        for (const OracleTransition& transition : raw.nodes[state_id].transitions) {
            const NormalizedState normalized_child = normalize_state(
                raw.nodes[transition.child_id].state, true);
            const auto child_iterator = canonical.ids.find(state_key(normalized_child.state));
            if (child_iterator == canonical.ids.end()) {
                throw std::logic_error{"raw child is missing from the canonical graph"};
            }
            mapped_transitions.push_back(OracleTransition{
                normalized.transformed ? rotated_actions[transition.action]
                                       : transition.action,
                child_iterator->second,
            });
        }
        std::sort(
            mapped_transitions.begin(),
            mapped_transitions.end(),
            [](const OracleTransition& lhs, const OracleTransition& rhs) {
                return std::pair{lhs.action, lhs.child_id} <
                       std::pair{rhs.action, rhs.child_id};
            });
        std::vector<OracleTransition> canonical_transitions =
            canonical.nodes[canonical_id].transitions;
        std::sort(
            canonical_transitions.begin(),
            canonical_transitions.end(),
            [](const OracleTransition& lhs, const OracleTransition& rhs) {
                return std::pair{lhs.action, lhs.child_id} <
                       std::pair{rhs.action, rhs.child_id};
            });
        if (mapped_transitions != canonical_transitions) {
            throw std::logic_error{"raw and canonical transitions differ"};
        }
    }

    ExactOracle oracle;
    oracle.states.reserve(raw.nodes.size());
    for (std::size_t state_id = 0; state_id < raw.nodes.size(); ++state_id) {
        const NodeSolution& solution = raw_solutions[state_id];
        oracle.states.push_back(OracleState{
            raw.nodes[state_id].state,
            raw.nodes[state_id].terminal,
            solution.value,
            solution.dtw,
            raw.nodes[state_id].transitions,
            solution.optimal_actions,
            canonical_ids[state_id],
            canonical_transforms[state_id],
        });
    }

    SolverManifest& manifest = oracle.manifest;
    manifest.raw_state_count = raw.summary.state_count;
    manifest.raw_transition_count = raw.summary.transition_count;
    manifest.canonical_state_count = canonical.summary.state_count;
    manifest.canonical_transition_count = canonical.summary.transition_count;
    manifest.action_vocabulary_hash = action_vocabulary_hash();
    manifest.raw_graph_hash = raw.summary.graph_hash;
    manifest.canonical_graph_hash = canonical.summary.graph_hash;
    manifest.initial_value = raw_solutions.front().value;
    manifest.initial_dtw = raw_solutions.front().dtw;

    for (const NodeSolution& solution : raw_solutions) {
        switch (solution.value) {
            case ExactValue::Win:
                ++manifest.win_count;
                break;
            case ExactValue::Draw:
                ++manifest.draw_count;
                break;
            case ExactValue::Loss:
                ++manifest.loss_count;
                break;
        }
        if (solution.dtw.has_value()) {
            manifest.maximum_dtw = std::max(manifest.maximum_dtw, *solution.dtw);
        }
    }

    manifest.solver_hash = hash_solver(
        raw,
        raw_solutions,
        canonical_ids,
        canonical_transforms,
        canonical.summary.graph_hash);
    manifest.manifest_hash = fnv1a(manifest_hash_payload(manifest));
    return oracle;
}

std::string solver_manifest_json(const SolverManifest& manifest) {
    std::ostringstream output;
    output << "{\n"
           << "  \"schema\": \"mini_jass.solver_manifest.v1\",\n"
           << "  \"rules\": {\n"
           << "    \"schema\": \"mini_jass.rules.l1.v1\",\n"
           << "    \"board_size\": 5,\n"
           << "    \"playable_squares\": 13,\n"
           << "    \"square_coordinates\": [[0, 0], [0, 2], [0, 4], [1, 1], [1, 3], [2, 0], [2, 2], [2, 4], [3, 1], [3, 3], [4, 0], [4, 2], [4, 4]],\n"
           << "    \"initial_state_key\": 46080,\n"
           << "    \"maximum_pieces_per_side\": 2,\n"
           << "    \"reversible_ply_limit\": 20,\n"
           << "    \"men_capture_directions\": \"forward_and_backward\",\n"
           << "    \"king_type\": \"short\",\n"
           << "    \"mandatory_capture\": true,\n"
           << "    \"capture_priority\": \"all_complete_continuations\",\n"
           << "    \"promotion_timing\": \"after_complete_move\",\n"
           << "    \"terminal_precedence\": [\"no_piece_or_legal_move\", \"reversible_ply_limit\"],\n"
           << "    \"canonical_symmetry\": \"rotate180_swap_colours_and_turn\",\n"
           << "    \"square_permutation\": [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]\n"
           << "  },\n"
           << "  \"action_schema\": \"mini_jass.actions.v1\",\n"
           << "  \"action_count\": 72,\n"
           << "  \"action_vocabulary_hash\": " << manifest.action_vocabulary_hash << ",\n"
           << "  \"raw_state_count\": " << manifest.raw_state_count << ",\n"
           << "  \"raw_transition_count\": " << manifest.raw_transition_count << ",\n"
           << "  \"canonical_state_count\": " << manifest.canonical_state_count << ",\n"
           << "  \"canonical_transition_count\": "
           << manifest.canonical_transition_count << ",\n"
           << "  \"win_count\": " << manifest.win_count << ",\n"
           << "  \"draw_count\": " << manifest.draw_count << ",\n"
           << "  \"loss_count\": " << manifest.loss_count << ",\n"
           << "  \"maximum_dtw\": " << manifest.maximum_dtw << ",\n"
           << "  \"initial_value\": " << static_cast<int>(manifest.initial_value) << ",\n"
           << "  \"initial_dtw\": ";
    if (manifest.initial_dtw.has_value()) {
        output << *manifest.initial_dtw;
    } else {
        output << "null";
    }
    output << ",\n"
           << "  \"raw_graph_hash\": " << manifest.raw_graph_hash << ",\n"
           << "  \"canonical_graph_hash\": " << manifest.canonical_graph_hash << ",\n"
           << "  \"solver_hash\": " << manifest.solver_hash << ",\n"
           << "  \"manifest_hash\": " << manifest.manifest_hash << "\n"
           << "}\n";
    return output.str();
}

std::string_view to_string(const ExactValue value) noexcept {
    switch (value) {
        case ExactValue::Loss:
            return "loss";
        case ExactValue::Draw:
            return "draw";
        case ExactValue::Win:
            return "win";
    }
    return "unknown";
}

}  // namespace mini_jass
