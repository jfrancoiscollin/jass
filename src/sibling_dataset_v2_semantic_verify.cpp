// SPDX-License-Identifier: AGPL-3.0-or-later
// Native structural verifier/exporter for C SiblingDataset v2.
// Uses production Position/Move/movegen only. No search, model load, EGDB, fit,
// game, promotion, or bake is reachable from this tool.

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

using namespace jass;

constexpr std::size_t RECORD_SIZE = 38;
constexpr std::uint32_t PARENTS = 4000;
constexpr std::uint32_t EXPECTED_ROWS = 38053;
constexpr std::string_view SEMANTIC_SCHEMA = "jass.sibling_dataset_v2.semantic_action.v1";
constexpr std::string_view RECEIPT_SCHEMA = "jass.sibling_dataset_v2.native_semantic_verification.v1";

struct DiskRow {
    std::uint64_t wm{0};
    std::uint64_t wk{0};
    std::uint64_t bm{0};
    std::uint64_t bk{0};
    std::uint8_t stm{0};
};

struct LedgerRow {
    std::uint32_t row_index{0};
    std::uint32_t parent_id{0};
    std::string parent_fingerprint;
    std::uint32_t parent_stm{0};
    std::uint32_t parent_pieces{0};
    std::uint32_t from{0};
    std::uint32_t to{0};
    std::uint32_t num_captures{0};
    bool promotes{false};
    bool moving_king{false};
    std::uint32_t captured_kings{0};
    int material_delta{0};
    std::uint32_t child_pieces{0};
    std::uint32_t child_legal_moves{0};
    bool child_forced_capture{false};
};

template <typename T>
T load_le(const char* p) noexcept {
    T value{};
    std::memcpy(&value, p, sizeof(T));
    return value;
}

std::vector<std::string> split_tsv(const std::string& line) {
    std::vector<std::string> values;
    std::size_t begin = 0;
    while (true) {
        const std::size_t tab = line.find('\t', begin);
        if (tab == std::string::npos) {
            values.emplace_back(line.substr(begin));
            break;
        }
        values.emplace_back(line.substr(begin, tab - begin));
        begin = tab + 1;
    }
    return values;
}

std::uint64_t strict_uint(const std::string& text, std::uint64_t lo, std::uint64_t hi,
                          const char* label) {
    if (text.empty() || (text.size() > 1 && text.front() == '0'))
        throw std::runtime_error(std::string(label) + " is not canonical uint");
    std::uint64_t value = 0;
    for (char c : text) {
        if (c < '0' || c > '9')
            throw std::runtime_error(std::string(label) + " is not canonical uint");
        const std::uint64_t digit = static_cast<std::uint64_t>(c - '0');
        if (value > (hi - digit) / 10)
            throw std::runtime_error(std::string(label) + " overflows");
        value = value * 10 + digit;
    }
    if (value < lo || value > hi)
        throw std::runtime_error(std::string(label) + " outside bounds");
    return value;
}

int strict_int(const std::string& text, int lo, int hi, const char* label) {
    if (text.empty()) throw std::runtime_error(std::string(label) + " empty");
    bool neg = text.front() == '-';
    std::string digits = neg ? text.substr(1) : text;
    if (digits.empty() || (digits.size() > 1 && digits.front() == '0'))
        throw std::runtime_error(std::string(label) + " is not canonical int");
    const auto magnitude = strict_uint(digits, 0, static_cast<std::uint64_t>(hi > -lo ? hi : -lo), label);
    const long long value = neg ? -static_cast<long long>(magnitude) : static_cast<long long>(magnitude);
    if (value < lo || value > hi)
        throw std::runtime_error(std::string(label) + " outside bounds");
    return static_cast<int>(value);
}

bool strict_bool01(const std::string& text, const char* label) {
    if (text == "0") return false;
    if (text == "1") return true;
    throw std::runtime_error(std::string(label) + " is not 0/1");
}

std::string json_string(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : value) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20U || c > 0x7eU)
                    throw std::runtime_error("non-ASCII identity in native verifier");
                out << static_cast<char>(c);
        }
    }
    out << '"';
    return out.str();
}

std::vector<DiskRow> load_parents(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open parents JNNW");
    std::string raw((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    if (raw.size() != 8U + static_cast<std::size_t>(PARENTS) * RECORD_SIZE
            || raw.compare(0, 4, "JNNW") != 0
            || load_le<std::uint32_t>(raw.data() + 4) != PARENTS)
        throw std::runtime_error("parents JNNW header/count/size mismatch");
    std::vector<DiskRow> rows;
    rows.reserve(PARENTS);
    for (std::uint32_t i = 0; i < PARENTS; ++i) {
        const char* p = raw.data() + 8U + static_cast<std::size_t>(i) * RECORD_SIZE;
        if (!std::all_of(p + 33, p + 38, [](char c) { return c == 0; }))
            throw std::runtime_error("parent target bytes must be zero");
        DiskRow row;
        row.wm = load_le<std::uint64_t>(p + 0);
        row.wk = load_le<std::uint64_t>(p + 8);
        row.bm = load_le<std::uint64_t>(p + 16);
        row.bk = load_le<std::uint64_t>(p + 24);
        row.stm = static_cast<std::uint8_t>(p[32]);
        const Bitboard all = row.wm | row.wk | row.bm | row.bk;
        if (row.stm > 1 || (all & ~PLAYABLE_BB) != 0
                || ((row.wm & row.wk) | (row.wm & row.bm) | (row.wm & row.bk)
                    | (row.wk & row.bm) | (row.wk & row.bk) | (row.bm & row.bk)) != 0)
            throw std::runtime_error("invalid parent board row");
        rows.push_back(row);
    }
    return rows;
}

Position position_from_row(const DiskRow& row) {
    Position pos;
    pos.clear();
    auto add_all = [&](Bitboard bits, Piece piece) {
        while (bits) pos.add_piece(pop_lsb(bits), piece);
    };
    add_all(row.wm, Piece::WhiteMan);
    add_all(row.wk, Piece::WhiteKing);
    add_all(row.bm, Piece::BlackMan);
    add_all(row.bk, Piece::BlackKing);
    pos.set_side_to_move(row.stm == 0 ? Color::White : Color::Black);
    pos.set_halfmove_clock(0);
    return pos;
}

std::string fingerprint(const Position& pos) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << pos.white_men() << ':'
        << std::setw(13) << pos.white_kings() << ':'
        << std::setw(13) << pos.black_men() << ':'
        << std::setw(13) << pos.black_kings() << ':'
        << std::dec << (pos.side_to_move() == Color::White ? 0 : 1);
    return out.str();
}

bool same_semantic_move(const Move& a, const Move& b) noexcept {
    return a.from == b.from && a.to == b.to && a.captured == b.captured
        && a.promotes == b.promotes;
}

bool semantic_less(const Move& a, const Move& b) noexcept {
    return std::tuple{static_cast<int>(a.from), static_cast<int>(a.to),
                      static_cast<std::uint64_t>(a.captured), a.promotes}
         < std::tuple{static_cast<int>(b.from), static_cast<int>(b.to),
                      static_cast<std::uint64_t>(b.captured), b.promotes};
}

int material_count_delta_parent(const Position& parent, const Position& child) noexcept {
    const bool white = parent.side_to_move() == Color::White;
    const int own_before = popcount(white ? parent.whites() : parent.blacks());
    const int opp_before = popcount(white ? parent.blacks() : parent.whites());
    const int own_after = popcount(white ? child.whites() : child.blacks());
    const int opp_after = popcount(white ? child.blacks() : child.whites());
    return (own_after - opp_after) - (own_before - opp_before);
}

std::vector<std::vector<LedgerRow>> load_groups(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open adaptive groups TSV");
    std::string header_line;
    if (!std::getline(in, header_line) || header_line.find('\r') != std::string::npos)
        throw std::runtime_error("missing/invalid adaptive groups header");
    const auto header = split_tsv(header_line);
    std::unordered_map<std::string, std::size_t> index;
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (!index.emplace(header[i], i).second)
            throw std::runtime_error("duplicate adaptive groups header field");
    }
    const std::array<const char*, 15> required = {
        "row_index", "parent_id", "parent_fingerprint", "parent_stm", "parent_pieces",
        "from", "to", "num_captures", "promotes", "moving_king", "captured_kings",
        "material_count_delta_parent", "child_pieces", "child_legal_moves",
        "child_forced_capture"
    };
    for (const char* name : required)
        if (!index.count(name)) throw std::runtime_error(std::string("missing groups field ") + name);

    std::vector<std::vector<LedgerRow>> by_parent(PARENTS);
    std::string line;
    std::uint32_t expected_row = 0;
    while (std::getline(in, line)) {
        if (line.find('\r') != std::string::npos)
            throw std::runtime_error("CR in adaptive groups TSV");
        const auto values = split_tsv(line);
        if (values.size() != header.size())
            throw std::runtime_error("adaptive groups TSV width mismatch");
        const auto get = [&](const char* name) -> const std::string& { return values[index.at(name)]; };
        LedgerRow row;
        row.row_index = static_cast<std::uint32_t>(strict_uint(get("row_index"), 0, EXPECTED_ROWS - 1, "row_index"));
        if (row.row_index != expected_row++) throw std::runtime_error("row_index is not contiguous");
        row.parent_id = static_cast<std::uint32_t>(strict_uint(get("parent_id"), 0, PARENTS - 1, "parent_id"));
        row.parent_fingerprint = get("parent_fingerprint");
        row.parent_stm = static_cast<std::uint32_t>(strict_uint(get("parent_stm"), 0, 1, "parent_stm"));
        row.parent_pieces = static_cast<std::uint32_t>(strict_uint(get("parent_pieces"), 1, 40, "parent_pieces"));
        row.from = static_cast<std::uint32_t>(strict_uint(get("from"), 1, 50, "from"));
        row.to = static_cast<std::uint32_t>(strict_uint(get("to"), 1, 50, "to"));
        row.num_captures = static_cast<std::uint32_t>(strict_uint(get("num_captures"), 0, 20, "num_captures"));
        row.promotes = strict_bool01(get("promotes"), "promotes");
        row.moving_king = strict_bool01(get("moving_king"), "moving_king");
        row.captured_kings = static_cast<std::uint32_t>(strict_uint(get("captured_kings"), 0, 20, "captured_kings"));
        row.material_delta = strict_int(get("material_count_delta_parent"), -20, 20, "material_count_delta_parent");
        row.child_pieces = static_cast<std::uint32_t>(strict_uint(get("child_pieces"), 0, 40, "child_pieces"));
        row.child_legal_moves = static_cast<std::uint32_t>(strict_uint(get("child_legal_moves"), 0, 64, "child_legal_moves"));
        row.child_forced_capture = strict_bool01(get("child_forced_capture"), "child_forced_capture");
        by_parent[row.parent_id].push_back(std::move(row));
    }
    if (expected_row != EXPECTED_ROWS) throw std::runtime_error("adaptive row count is not 38053");
    return by_parent;
}

int run_verify(const std::string& parents_path, const std::string& groups_path,
               const std::string& semantic_path, const std::string& receipt_path) {
    const auto parents = load_parents(parents_path);
    const auto groups = load_groups(groups_path);
    std::ofstream semantic(semantic_path, std::ios::binary | std::ios::trunc);
    if (!semantic) throw std::runtime_error("cannot create semantic JSONL");

    std::uint64_t rows_verified = 0;
    std::uint64_t duplicates_elided = 0;
    for (std::uint32_t parent_id = 0; parent_id < PARENTS; ++parent_id) {
        const Position parent = position_from_row(parents[parent_id]);
        const std::string parent_fp = fingerprint(parent);
        MoveList legal;
        generate_legal_moves(parent, legal);
        std::vector<Move> unique;
        for (const Move& move : legal) {
            const auto it = std::find_if(unique.begin(), unique.end(), [&](const Move& old) {
                return same_semantic_move(old, move);
            });
            if (it == unique.end()) unique.push_back(move); else ++duplicates_elided;
        }
        std::sort(unique.begin(), unique.end(), semantic_less);
        if (unique.size() < 2 || unique.size() > 16)
            throw std::runtime_error("parent legal semantic support outside 2..16");
        const auto& ledger = groups[parent_id];
        if (ledger.size() != unique.size())
            throw std::runtime_error("native legal action count differs from adaptive ledger");
        for (std::size_t local = 0; local < unique.size(); ++local) {
            const Move& move = unique[local];
            const LedgerRow& row = ledger[local];
            const Position child = parent.after(move);
            MoveList child_legal;
            generate_legal_moves(child, child_legal);
            const bool child_forced = !child_legal.empty() && child_legal[0].is_capture();
            const bool moving_king = test(parent.kings_of(parent.side_to_move()), move.from);
            const std::uint32_t captured_kings = static_cast<std::uint32_t>(popcount(
                move.captured & parent.kings_of(opposite(parent.side_to_move()))));
            const int material_delta = material_count_delta_parent(parent, child);
            const std::uint32_t child_pieces = static_cast<std::uint32_t>(popcount(child.occupied()));
            const std::string child_fp = fingerprint(child);
            if (row.parent_fingerprint != parent_fp
                    || row.parent_stm != (parent.side_to_move() == Color::White ? 0U : 1U)
                    || row.parent_pieces != static_cast<std::uint32_t>(popcount(parent.occupied()))
                    || row.from != static_cast<std::uint32_t>(move.from)
                    || row.to != static_cast<std::uint32_t>(move.to)
                    || row.num_captures != static_cast<std::uint32_t>(move.num_captures)
                    || row.promotes != move.promotes
                    || row.moving_king != moving_king
                    || row.captured_kings != captured_kings
                    || row.material_delta != material_delta
                    || row.child_pieces != child_pieces
                    || row.child_legal_moves != static_cast<std::uint32_t>(child_legal.size())
                    || row.child_forced_capture != child_forced)
                throw std::runtime_error("adaptive ledger structural action differs from production movegen");

            semantic << "{\"captured_kings\":" << captured_kings
                     << ",\"captured_square_bitboard\":" << static_cast<std::uint64_t>(move.captured)
                     << ",\"child_fingerprint\":" << json_string(child_fp)
                     << ",\"child_forced_capture\":" << (child_forced ? "true" : "false")
                     << ",\"child_legal_moves\":" << child_legal.size()
                     << ",\"child_pieces\":" << child_pieces
                     << ",\"from\":" << static_cast<int>(move.from)
                     << ",\"local_action_index\":" << local
                     << ",\"material_count_delta_parent\":" << material_delta
                     << ",\"moving_king\":" << (moving_king ? "true" : "false")
                     << ",\"num_captures\":" << static_cast<int>(move.num_captures)
                     << ",\"parent_fingerprint\":" << json_string(parent_fp)
                     << ",\"parent_id\":" << parent_id
                     << ",\"promotes\":" << (move.promotes ? "true" : "false")
                     << ",\"schema\":" << json_string(SEMANTIC_SCHEMA)
                     << ",\"to\":" << static_cast<int>(move.to) << "}\n";
            ++rows_verified;
        }
    }
    semantic.flush();
    if (!semantic || rows_verified != EXPECTED_ROWS)
        throw std::runtime_error("semantic output row count/write mismatch");

    std::ofstream receipt(receipt_path, std::ios::binary | std::ios::trunc);
    if (!receipt) throw std::runtime_error("cannot create native receipt");
    receipt << "{\"duplicate_move_paths_elided\":" << duplicates_elided
            << ",\"fits\":0,\"full_ladder_reference_reads\":0,\"parents_verified\":" << PARENTS
            << ",\"production_movegen\":true,\"promotions\":0,\"rows_verified\":" << rows_verified
            << ",\"schema\":" << json_string(RECEIPT_SCHEMA)
            << ",\"searches\":0,\"strength_games\":0}\n";
    return 0;
}

int selftest() {
    if (strict_uint("0", 0, 10, "x") != 0 || strict_uint("10", 0, 10, "x") != 10)
        return 1;
    bool rejected = false;
    try { (void) strict_uint("01", 0, 10, "x"); } catch (...) { rejected = true; }
    if (!rejected || json_string("a\\b") != "\"a\\\\b\"") return 1;
    std::cout << "sibling_dataset_v2_semantic_verify selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "SiblingDataset v2 verifier requires little-endian host");
    try {
        if (argc == 2 && std::string_view(argv[1]) == "selftest") return selftest();
        if (argc != 5) {
            std::cerr << "usage: sibling_dataset_v2_semantic_verify "
                         "<parents.jnnw> <adaptive-groups.tsv> <semantic.jsonl> <receipt.json>\n";
            return 2;
        }
        return run_verify(argv[1], argv[2], argv[3], argv[4]);
    } catch (const std::exception& exc) {
        std::cerr << "sibling_dataset_v2_semantic_verify: " << exc.what() << '\n';
        return 3;
    }
}
