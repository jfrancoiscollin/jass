#include "mini_jass/l2_solver.hpp"

#include <algorithm>
#include <array>
#include <functional>
#include <limits>
#include <map>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace mini_jass::l2 {
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
    std::uint64_t transition_count{};
    std::uint64_t graph_hash{};
};
struct NodeSolution {
    ExactValue value{ExactValue::Draw};
    bool resolved{};
    std::optional<std::uint16_t> dtw;
    std::vector<std::uint8_t> optimal_actions;
};
struct NormalizedState { State state; bool transformed{}; };

void hash_byte(std::uint64_t& hash, const std::uint8_t value) noexcept {
    hash ^= value;
    hash *= 1099511628211ULL;
}
void hash_u64(std::uint64_t& hash, const std::uint64_t value) noexcept {
    for (unsigned shift = 0; shift < 64; shift += 8)
        hash_byte(hash, static_cast<std::uint8_t>((value >> shift) & 0xffU));
}
void hash_text(std::uint64_t& hash, const std::string_view text) noexcept {
    for (const char value : text) hash_byte(hash, static_cast<std::uint8_t>(value));
}
[[nodiscard]] std::uint64_t fnv1a(const std::string_view text) noexcept {
    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, text);
    return hash;
}
[[nodiscard]] NormalizedState normalize_state(const State& state, const bool canonical) noexcept {
    if (!canonical) return {state, false};
    const State transformed = rotate180_and_swap_colours(state);
    return state_key(transformed) < state_key(state)
        ? NormalizedState{transformed, true} : NormalizedState{state, false};
}

[[nodiscard]] Graph build_graph(const bool canonical) {
    Graph graph;
    graph.nodes.reserve(60000);
    const State root = normalize_state(initial_state(), canonical).state;
    graph.nodes.push_back({root, TerminalStatus::Ongoing, {}});
    graph.ids.emplace(state_key(root), 0);

    for (std::size_t state_id = 0; state_id < graph.nodes.size(); ++state_id) {
        const State state = graph.nodes[state_id].state;
        if (generate_board_moves(state) != generate_reference_board_moves(state))
            throw std::logic_error{"L2 production and reference move generators differ"};
        const TerminalStatus terminal = terminal_status(state);
        graph.nodes[state_id].terminal = terminal;
        if (terminal != TerminalStatus::Ongoing) continue;
        const std::vector<Move> moves = legal_moves(state);
        std::vector<OracleTransition> transitions;
        transitions.reserve(moves.size());
        for (const Move& move : moves) {
            const auto action = action_id(move);
            if (!action.has_value())
                throw std::logic_error{"legal L2 move is absent from its action vocabulary"};
            const State child = normalize_state(apply_move(state, move), canonical).state;
            const std::uint64_t key = state_key(child);
            const auto [found, inserted] = graph.ids.emplace(key, static_cast<StateId>(graph.nodes.size()));
            if (inserted) {
                if (graph.nodes.size() >= std::numeric_limits<StateId>::max())
                    throw std::overflow_error{"L2 graph exceeds 32-bit state IDs"};
                graph.nodes.push_back({child, TerminalStatus::Ongoing, {}});
            }
            transitions.push_back({*action, found->second});
            ++graph.transition_count;
        }
        graph.nodes[state_id].transitions = std::move(transitions);
    }

    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, canonical ? "mini_jass.l2.canonical_graph.v1" : "mini_jass.l2.graph.v1");
    for (const GraphNode& node : graph.nodes) {
        hash_u64(hash, state_key(node.state));
        hash_byte(hash, static_cast<std::uint8_t>(node.terminal));
        hash_u64(hash, node.transitions.size());
        for (const OracleTransition& edge : node.transitions) {
            hash_byte(hash, edge.action);
            hash_u64(hash, state_key(graph.nodes[edge.child_id].state));
        }
    }
    hash_u64(hash, graph.nodes.size());
    hash_u64(hash, graph.transition_count);
    graph.graph_hash = hash;
    return graph;
}

[[nodiscard]] std::uint16_t plus_one(const std::uint16_t value) {
    if (value == std::numeric_limits<std::uint16_t>::max())
        throw std::overflow_error{"L2 DTW exceeds 16 bits"};
    return static_cast<std::uint16_t>(value + 1);
}

[[nodiscard]] std::vector<NodeSolution> solve_graph(const Graph& graph) {
    const std::size_t count = graph.nodes.size();
    std::vector<NodeSolution> result(count);
    std::vector<std::vector<StateId>> predecessors(count);
    std::vector<std::uint32_t> remaining(count);
    std::vector<std::uint16_t> maximum_child_dtw(count);
    for (StateId parent = 0; parent < count; ++parent) {
        remaining[parent] = static_cast<std::uint32_t>(graph.nodes[parent].transitions.size());
        for (const OracleTransition& edge : graph.nodes[parent].transitions)
            predecessors[edge.child_id].push_back(parent);
    }
    using Entry = std::pair<std::uint16_t, StateId>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<>> queue;
    for (StateId state_id = 0; state_id < count; ++state_id) {
        const TerminalStatus terminal = graph.nodes[state_id].terminal;
        if (terminal == TerminalStatus::SideToMoveLoss) {
            result[state_id] = {ExactValue::Loss, true, 0, {}};
            queue.emplace(0, state_id);
        } else if (terminal == TerminalStatus::Draw) {
            result[state_id] = {ExactValue::Draw, true, std::nullopt, {}};
        }
    }
    while (!queue.empty()) {
        const auto [distance, child] = queue.top();
        queue.pop();
        for (const StateId parent : predecessors[child]) {
            NodeSolution& solution = result[parent];
            if (solution.resolved) continue;
            if (result[child].value == ExactValue::Loss) {
                solution = {ExactValue::Win, true, plus_one(distance), {}};
                queue.emplace(*solution.dtw, parent);
            } else if (result[child].value == ExactValue::Win && remaining[parent] != 0) {
                --remaining[parent];
                maximum_child_dtw[parent] = std::max(maximum_child_dtw[parent], distance);
                if (remaining[parent] == 0) {
                    solution = {ExactValue::Loss, true, plus_one(maximum_child_dtw[parent]), {}};
                    queue.emplace(*solution.dtw, parent);
                }
            }
        }
    }
    for (std::size_t state_id = 0; state_id < count; ++state_id) {
        NodeSolution& solution = result[state_id];
        if (!solution.resolved) { solution.value = ExactValue::Draw; solution.resolved = true; }
        if (graph.nodes[state_id].terminal != TerminalStatus::Ongoing) continue;
        int best = -2;
        for (const OracleTransition& edge : graph.nodes[state_id].transitions) {
            const int score = -static_cast<int>(result[edge.child_id].value);
            if (score > best) { best = score; solution.optimal_actions.clear(); }
            if (score == best) solution.optimal_actions.push_back(edge.action);
        }
        if (best != static_cast<int>(solution.value) || solution.optimal_actions.empty())
            throw std::logic_error{"L2 solution violates negamax recurrence"};
    }
    return result;
}

[[nodiscard]] std::array<std::uint8_t, kActionCount> transformed_actions() {
    std::array<std::uint8_t, kActionCount> result{};
    const auto& vocabulary = action_vocabulary();
    for (std::size_t i = 0; i < vocabulary.size(); ++i) {
        const auto transformed = action_id(rotate180_move(vocabulary[i]));
        if (!transformed.has_value()) throw std::logic_error{"rotated L2 action is absent"};
        result[i] = *transformed;
    }
    for (std::size_t i = 0; i < result.size(); ++i)
        if (result[result[i]] != i) throw std::logic_error{"L2 action rotation is not involutive"};
    return result;
}

[[nodiscard]] std::uint64_t hash_solver(
    const Graph& raw, const std::vector<NodeSolution>& solutions,
    const std::vector<StateId>& canonical_ids, const std::vector<bool>& transforms,
    const std::uint64_t canonical_graph_hash) {
    std::uint64_t hash = 14695981039346656037ULL;
    hash_text(hash, "mini_jass.l2.solver.v1");
    hash_u64(hash, action_vocabulary_hash());
    hash_u64(hash, raw.graph_hash);
    hash_u64(hash, canonical_graph_hash);
    for (std::size_t i = 0; i < raw.nodes.size(); ++i) {
        hash_u64(hash, state_key(raw.nodes[i].state));
        hash_byte(hash, static_cast<std::uint8_t>(raw.nodes[i].terminal));
        hash_byte(hash, static_cast<std::uint8_t>(static_cast<int>(solutions[i].value) + 1));
        hash_u64(hash, solutions[i].dtw.has_value() ? *solutions[i].dtw
                                                    : std::numeric_limits<std::uint64_t>::max());
        hash_u64(hash, canonical_ids[i]);
        hash_byte(hash, transforms[i] ? 1 : 0);
        for (const OracleTransition& edge : raw.nodes[i].transitions) {
            hash_byte(hash, edge.action);
            hash_u64(hash, state_key(raw.nodes[edge.child_id].state));
        }
        for (const std::uint8_t action : solutions[i].optimal_actions) hash_byte(hash, action);
    }
    return hash;
}

[[nodiscard]] std::string manifest_payload(const SolverManifest& manifest) {
    std::ostringstream out;
    out << "mini_jass.l2.solver_manifest.v1\n"
        << "rules=mini_jass.rules.l2.selected_2v1.v1\n"
        << "board_size=6\nplayable_squares=18\naction_count=122\n"
        << "initial_state_key=" << state_key(initial_state()) << '\n'
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
    if (manifest.initial_dtw.has_value()) out << *manifest.initial_dtw; else out << "null";
    out << '\n' << "action_vocabulary_hash=" << manifest.action_vocabulary_hash << '\n'
        << "raw_graph_hash=" << manifest.raw_graph_hash << '\n'
        << "canonical_graph_hash=" << manifest.canonical_graph_hash << '\n'
        << "solver_hash=" << manifest.solver_hash << '\n';
    return out.str();
}

}  // namespace

ExactOracle solve_exact_oracle() {
    const Graph raw = build_graph(false);
    const std::vector<NodeSolution> raw_solutions = solve_graph(raw);
    const Graph canonical = build_graph(true);
    const std::vector<NodeSolution> canonical_solutions = solve_graph(canonical);
    const auto rotated = transformed_actions();
    std::vector<StateId> canonical_ids(raw.nodes.size());
    std::vector<bool> transforms(raw.nodes.size());

    for (std::size_t i = 0; i < raw.nodes.size(); ++i) {
        const NormalizedState normalized = normalize_state(raw.nodes[i].state, true);
        const auto found = canonical.ids.find(state_key(normalized.state));
        if (found == canonical.ids.end()) throw std::logic_error{"raw L2 state absent from canonical graph"};
        canonical_ids[i] = found->second;
        transforms[i] = normalized.transformed;
        const NodeSolution& expected = canonical_solutions[found->second];
        if (raw_solutions[i].value != expected.value || raw_solutions[i].dtw != expected.dtw ||
            raw.nodes[i].terminal != canonical.nodes[found->second].terminal)
            throw std::logic_error{"raw and canonical L2 solutions differ"};
        std::vector<std::uint8_t> optimal = raw_solutions[i].optimal_actions;
        if (normalized.transformed) {
            for (std::uint8_t& action : optimal) action = rotated[action];
            std::sort(optimal.begin(), optimal.end());
        }
        if (optimal != expected.optimal_actions)
            throw std::logic_error{"raw and canonical L2 optimal actions differ"};
    }

    ExactOracle oracle;
    oracle.states.reserve(raw.nodes.size());
    for (std::size_t i = 0; i < raw.nodes.size(); ++i) {
        oracle.states.push_back({raw.nodes[i].state, raw.nodes[i].terminal,
            raw_solutions[i].value, raw_solutions[i].dtw, raw.nodes[i].transitions,
            raw_solutions[i].optimal_actions, canonical_ids[i], transforms[i]});
    }
    SolverManifest& manifest = oracle.manifest;
    manifest.raw_state_count = raw.nodes.size();
    manifest.raw_transition_count = raw.transition_count;
    manifest.canonical_state_count = canonical.nodes.size();
    manifest.canonical_transition_count = canonical.transition_count;
    manifest.action_vocabulary_hash = action_vocabulary_hash();
    manifest.raw_graph_hash = raw.graph_hash;
    manifest.canonical_graph_hash = canonical.graph_hash;
    manifest.initial_value = raw_solutions.front().value;
    manifest.initial_dtw = raw_solutions.front().dtw;
    for (const NodeSolution& solution : raw_solutions) {
        if (solution.value == ExactValue::Win) ++manifest.win_count;
        else if (solution.value == ExactValue::Draw) ++manifest.draw_count;
        else ++manifest.loss_count;
        if (solution.dtw.has_value()) manifest.maximum_dtw = std::max(manifest.maximum_dtw, *solution.dtw);
    }
    manifest.solver_hash = hash_solver(raw, raw_solutions, canonical_ids, transforms,
                                       canonical.graph_hash);
    manifest.manifest_hash = fnv1a(manifest_payload(manifest));
    return oracle;
}

std::string solver_manifest_json(const SolverManifest& manifest) {
    std::ostringstream out;
    out << "{\n  \"schema\": \"mini_jass.l2.solver_manifest.v1\",\n"
        << "  \"rules\": {\n"
        << "    \"schema\": \"mini_jass.rules.l2.selected_2v1.v1\",\n"
        << "    \"board_size\": 6,\n    \"playable_squares\": 18,\n"
        << "    \"feature_count\": 74,\n    \"initial_state_key\": " << state_key(initial_state()) << ",\n"
        << "    \"initial_material\": \"2v2_forced_capture_to_2v1\",\n"
        << "    \"exact_material_scope\": \"reachable_selected_2v1_closure\",\n"
        << "    \"maximum_pieces_per_side\": 2,\n    \"reversible_ply_limit\": 20,\n"
        << "    \"men_capture_directions\": \"forward_and_backward\",\n"
        << "    \"king_type\": \"short\",\n    \"mandatory_capture\": true,\n"
        << "    \"capture_priority\": \"all_complete_continuations\",\n"
        << "    \"promotion_timing\": \"after_complete_move\",\n"
        << "    \"canonical_symmetry\": \"rotate180_swap_colours_and_turn\"\n  },\n"
        << "  \"action_schema\": \"mini_jass.actions.l2.v1\",\n  \"action_count\": 122,\n"
        << "  \"action_vocabulary_hash\": " << manifest.action_vocabulary_hash << ",\n"
        << "  \"raw_state_count\": " << manifest.raw_state_count << ",\n"
        << "  \"raw_transition_count\": " << manifest.raw_transition_count << ",\n"
        << "  \"canonical_state_count\": " << manifest.canonical_state_count << ",\n"
        << "  \"canonical_transition_count\": " << manifest.canonical_transition_count << ",\n"
        << "  \"win_count\": " << manifest.win_count << ",\n"
        << "  \"draw_count\": " << manifest.draw_count << ",\n"
        << "  \"loss_count\": " << manifest.loss_count << ",\n"
        << "  \"maximum_dtw\": " << manifest.maximum_dtw << ",\n"
        << "  \"initial_value\": " << static_cast<int>(manifest.initial_value) << ",\n"
        << "  \"initial_dtw\": ";
    if (manifest.initial_dtw.has_value()) out << *manifest.initial_dtw; else out << "null";
    out << ",\n  \"raw_graph_hash\": " << manifest.raw_graph_hash << ",\n"
        << "  \"canonical_graph_hash\": " << manifest.canonical_graph_hash << ",\n"
        << "  \"solver_hash\": " << manifest.solver_hash << ",\n"
        << "  \"manifest_hash\": " << manifest.manifest_hash << "\n}\n";
    return out.str();
}

std::string_view to_string(const ExactValue value) noexcept {
    switch (value) {
        case ExactValue::Loss: return "loss";
        case ExactValue::Draw: return "draw";
        case ExactValue::Win: return "win";
    }
    return "unknown";
}

}  // namespace mini_jass::l2
