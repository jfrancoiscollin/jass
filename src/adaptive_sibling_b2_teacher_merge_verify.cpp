// SPDX-License-Identifier: AGPL-3.0-or-later
// Native-only structural verifier for the prospective PR771 B2 teacher merge.

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "t3_f6.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <sys/stat.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif

namespace {

using namespace jass;

constexpr std::size_t JNNW_RECORD_SIZE = 38;
constexpr std::uint32_t PARENT_COUNT = 4'000;
constexpr std::uint32_t SHARD_COUNT = 16;
constexpr std::uint32_t MIN_ACTIONS = 8'000;
constexpr std::uint32_t MAX_ACTIONS = 64'000;
constexpr std::string_view ROW_SCHEMA = "jass.adaptive_sibling_b2_semantic_action.v1";
constexpr std::string_view RECEIPT_SCHEMA =
    "jass.adaptive_sibling_b2_teacher_merge_native_verification.v1";

struct DiskRow {
    std::uint64_t wm{0};
    std::uint64_t wk{0};
    std::uint64_t bm{0};
    std::uint64_t bk{0};
    std::uint8_t stm{0};
    bool target_zero{false};
};

struct JnnwFile {
    std::filesystem::path path;
    std::string sha256;
    std::uintmax_t size_bytes{0};
    std::vector<DiskRow> rows;
    std::uint32_t nonzero_targets{0};
};

struct SemanticRow {
    std::uint32_t captured_kings{0};
    std::uint64_t captured{0};
    std::string child_fingerprint;
    std::uint32_t child_pieces{0};
    std::uint32_t from{0};
    std::uint32_t global_row_index{0};
    std::uint32_t local_row_index{0};
    std::int32_t material_count_delta_parent{0};
    std::uint32_t num_captures{0};
    std::string parent_fingerprint;
    std::uint32_t parent_id{0};
    std::uint32_t parent_legal_moves{0};
    std::uint32_t parent_pieces{0};
    bool promotes{false};
    std::uint32_t source_shard{0};
    std::uint32_t to{0};
};

struct SemanticFile {
    std::filesystem::path path;
    std::string sha256;
    std::uintmax_t size_bytes{0};
    std::vector<SemanticRow> rows;
};

struct BuildProvenance {
    std::string build_type;
    std::string cmake_cache_sha256;
    std::string code_sha;
    std::string compiler_id;
    std::string compiler_version;
    std::string verifier_source_sha256;
};

struct FileIdentity {
    std::filesystem::path path;
    std::string sha256;
    std::uintmax_t size_bytes{0};
};

class ExitError final : public std::runtime_error {
public:
    ExitError(int code, const std::string& message) : std::runtime_error(message), code_(code) {}
    int code() const noexcept { return code_; }
private:
    int code_;
};

template <typename T>
T load_le(const char* data) noexcept {
    using U = std::make_unsigned_t<T>;
    U value = 0;
    for (std::size_t i = 0; i < sizeof(T); ++i) {
        value |= static_cast<U>(static_cast<unsigned char>(data[i])) << (8U * i);
    }
    return static_cast<T>(value);
}

std::string read_binary(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input: " + path.string());
    std::ostringstream out;
    out << input.rdbuf();
    if (!input.good() && !input.eof())
        throw std::runtime_error("cannot read input: " + path.string());
    return out.str();
}

std::string checked_sha256(const std::filesystem::path& path) {
    std::string error;
    const std::string digest = t3_f6::sha256_file(path.string(), &error);
    if (digest.size() != 64U)
        throw std::runtime_error("cannot hash " + path.string() + ": " + error);
    return digest;
}

bool lowercase_hex(std::string_view value, std::size_t width) noexcept {
    return value.size() == width
        && std::all_of(value.begin(), value.end(), [](unsigned char c) {
            return (c >= static_cast<unsigned char>('0')
                    && c <= static_cast<unsigned char>('9'))
                || (c >= static_cast<unsigned char>('a')
                    && c <= static_cast<unsigned char>('f'));
        });
}

bool printable_ascii(std::string_view value) noexcept {
    return !value.empty() && value.size() <= 512U
        && std::all_of(value.begin(), value.end(), [](unsigned char c) {
            return c >= 0x20U && c <= 0x7eU;
        });
}

std::string json_string(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (const char raw : value) {
        const auto c = static_cast<unsigned char>(raw);
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20U || c > 0x7eU) {
                    constexpr char HEX[] = "0123456789abcdef";
                    out << "\\u00" << HEX[c >> 4U] << HEX[c & 0x0fU];
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    out << '"';
    return out.str();
}

std::filesystem::path canonical_existing(const std::filesystem::path& path) {
    std::error_code error;
    const auto result = std::filesystem::canonical(path, error);
    if (error || !std::filesystem::is_regular_file(result, error) || error)
        throw std::runtime_error("path is not an existing regular file: " + path.string());
    return result;
}

std::string path_key(const std::filesystem::path& path) {
    std::error_code error;
    auto normalized = std::filesystem::weakly_canonical(path, error);
    if (error) normalized = std::filesystem::absolute(path, error).lexically_normal();
    std::string key = normalized.generic_string();
    std::transform(key.begin(), key.end(), key.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return key;
}

std::string checked_local_name(const std::filesystem::path& path) {
    const std::string name = path.filename().string();
    if (!printable_ascii(name) || name == "." || name == ".."
            || name.find('/') != std::string::npos || name.find('\\') != std::string::npos)
        throw std::runtime_error("artifact basename is not safe printable ASCII");
    return name;
}

bool valid_disk_row(const DiskRow& row) noexcept {
    if (row.stm > 1) return false;
    const Bitboard occupied = row.wm | row.wk | row.bm | row.bk;
    if ((occupied & ~PLAYABLE_BB) != 0) return false;
    return ((row.wm & row.wk) | (row.wm & row.bm) | (row.wm & row.bk)
          | (row.wk & row.bm) | (row.wk & row.bk) | (row.bm & row.bk)) == 0;
}

Position position_from_row(const DiskRow& row) {
    Position position;
    position.clear();
    const auto add_all = [&](Bitboard bits, Piece piece) {
        while (bits != 0) {
            const Square square = pop_lsb(bits);
            position.add_piece(square, piece);
        }
    };
    add_all(row.wm, Piece::WhiteMan);
    add_all(row.wk, Piece::WhiteKing);
    add_all(row.bm, Piece::BlackMan);
    add_all(row.bk, Piece::BlackKing);
    position.set_side_to_move(row.stm == 0 ? Color::White : Color::Black);
    position.set_halfmove_clock(0);
    return position;
}

DiskRow row_from_position(const Position& position) noexcept {
    return DiskRow{
        position.white_men(), position.white_kings(), position.black_men(),
        position.black_kings(),
        static_cast<std::uint8_t>(position.side_to_move() == Color::White ? 0 : 1),
        true,
    };
}

int piece_count(const DiskRow& row) noexcept {
    return popcount(row.wm | row.wk | row.bm | row.bk);
}

std::string fingerprint(const DiskRow& row) {
    std::ostringstream out;
    out << std::hex << std::setfill('0')
        << std::setw(13) << row.wm << ':'
        << std::setw(13) << row.wk << ':'
        << std::setw(13) << row.bm << ':'
        << std::setw(13) << row.bk << ':'
        << std::dec << static_cast<int>(row.stm);
    return out.str();
}

JnnwFile load_jnnw(const std::filesystem::path& path,
                   const std::string& expected_sha256,
                   std::uint32_t minimum_records,
                   std::uint32_t maximum_records) {
    JnnwFile file;
    file.path = canonical_existing(path);
    file.size_bytes = std::filesystem::file_size(file.path);
    const std::uintmax_t minimum_size = 8U
        + static_cast<std::uintmax_t>(minimum_records) * JNNW_RECORD_SIZE;
    const std::uintmax_t maximum_size = 8U
        + static_cast<std::uintmax_t>(maximum_records) * JNNW_RECORD_SIZE;
    if (file.size_bytes < minimum_size || file.size_bytes > maximum_size)
        throw std::runtime_error("JNNW file size outside cardinality bound");
    file.sha256 = checked_sha256(file.path);
    if (file.sha256 != expected_sha256) throw std::runtime_error("JNNW SHA256 mismatch");
    const std::string raw = read_binary(file.path);
    if (raw.size() != file.size_bytes) throw std::runtime_error("JNNW changed while reading");
    if (checked_sha256(file.path) != file.sha256)
        throw std::runtime_error("JNNW changed while reading");
    if (raw.size() < 8U || raw.compare(0, 4, "JNNW") != 0)
        throw std::runtime_error("input is not counted JNNW");
    const std::uint32_t count = load_le<std::uint32_t>(raw.data() + 4);
    if (count < minimum_records || count > maximum_records)
        throw std::runtime_error("JNNW record count outside contract");
    if (raw.size() != 8U + static_cast<std::uint64_t>(count) * JNNW_RECORD_SIZE)
        throw std::runtime_error("JNNW size/trailing-byte mismatch");
    file.rows.reserve(count);
    for (std::uint32_t index = 0; index < count; ++index) {
        const char* data = raw.data() + 8U + static_cast<std::size_t>(index) * JNNW_RECORD_SIZE;
        DiskRow row;
        row.wm = load_le<std::uint64_t>(data);
        row.wk = load_le<std::uint64_t>(data + 8);
        row.bm = load_le<std::uint64_t>(data + 16);
        row.bk = load_le<std::uint64_t>(data + 24);
        row.stm = static_cast<std::uint8_t>(data[32]);
        row.target_zero = std::all_of(data + 33, data + 38,
            [](char c) { return c == 0; });
        if (!row.target_zero) ++file.nonzero_targets;
        if (!valid_disk_row(row))
            throw std::runtime_error("invalid JNNW board at row " + std::to_string(index));
        file.rows.push_back(row);
    }
    return file;
}

class CanonicalRowParser {
public:
    explicit CanonicalRowParser(std::string_view input) : input_(input) {}

    SemanticRow parse() {
        SemanticRow row;
        expect("{\"captured_kings\":");
        row.captured_kings = narrow_u32(parse_u64(), "captured_kings");
        expect(",\"captured_square_bitboard\":");
        row.captured = parse_u64();
        expect(",\"child_fingerprint\":");
        row.child_fingerprint = parse_string();
        expect(",\"child_pieces\":");
        row.child_pieces = narrow_u32(parse_u64(), "child_pieces");
        expect(",\"from\":");
        row.from = narrow_u32(parse_u64(), "from");
        expect(",\"global_row_index\":");
        row.global_row_index = narrow_u32(parse_u64(), "global_row_index");
        expect(",\"local_row_index\":");
        row.local_row_index = narrow_u32(parse_u64(), "local_row_index");
        expect(",\"material_count_delta_parent\":");
        row.material_count_delta_parent = narrow_i32(parse_i64(), "material_count_delta_parent");
        expect(",\"num_captures\":");
        row.num_captures = narrow_u32(parse_u64(), "num_captures");
        expect(",\"parent_fingerprint\":");
        row.parent_fingerprint = parse_string();
        expect(",\"parent_id\":");
        row.parent_id = narrow_u32(parse_u64(), "parent_id");
        expect(",\"parent_legal_moves\":");
        row.parent_legal_moves = narrow_u32(parse_u64(), "parent_legal_moves");
        expect(",\"parent_pieces\":");
        row.parent_pieces = narrow_u32(parse_u64(), "parent_pieces");
        expect(",\"promotes\":");
        row.promotes = parse_bool();
        expect(",\"schema\":");
        if (parse_string() != ROW_SCHEMA) throw std::runtime_error("semantic row schema mismatch");
        expect(",\"source_shard\":");
        row.source_shard = narrow_u32(parse_u64(), "source_shard");
        expect(",\"to\":");
        row.to = narrow_u32(parse_u64(), "to");
        expect("}");
        if (cursor_ != input_.size()) throw std::runtime_error("trailing semantic JSON bytes");
        return row;
    }

private:
    void expect(std::string_view token) {
        if (input_.substr(cursor_, token.size()) != token)
            throw std::runtime_error("semantic JSON is not canonical or has schema drift");
        cursor_ += token.size();
    }

    std::uint64_t parse_u64() {
        const std::size_t begin = cursor_;
        if (cursor_ >= input_.size() || input_[cursor_] < '0' || input_[cursor_] > '9')
            throw std::runtime_error("semantic unsigned integer is invalid");
        if (input_[cursor_] == '0' && cursor_ + 1U < input_.size()
                && input_[cursor_ + 1U] >= '0' && input_[cursor_ + 1U] <= '9')
            throw std::runtime_error("semantic unsigned integer has a leading zero");
        std::uint64_t value = 0;
        while (cursor_ < input_.size() && input_[cursor_] >= '0' && input_[cursor_] <= '9') {
            const unsigned digit = static_cast<unsigned>(input_[cursor_] - '0');
            if (value > (std::numeric_limits<std::uint64_t>::max() - digit) / 10U)
                throw std::runtime_error("semantic unsigned integer overflows uint64");
            value = value * 10U + digit;
            ++cursor_;
        }
        if (cursor_ == begin) throw std::runtime_error("semantic unsigned integer is empty");
        return value;
    }

    std::int64_t parse_i64() {
        bool negative = false;
        if (cursor_ < input_.size() && input_[cursor_] == '-') {
            negative = true;
            ++cursor_;
            if (cursor_ >= input_.size() || input_[cursor_] == '0')
                throw std::runtime_error("semantic signed integer has invalid negative form");
        }
        const std::uint64_t magnitude = parse_u64();
        constexpr std::uint64_t ABS_MIN = std::uint64_t{1} << 63U;
        if ((!negative && magnitude > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
                || (negative && magnitude > ABS_MIN))
            throw std::runtime_error("semantic signed integer overflows int64");
        if (negative && magnitude == ABS_MIN) return std::numeric_limits<std::int64_t>::min();
        return negative ? -static_cast<std::int64_t>(magnitude)
                        : static_cast<std::int64_t>(magnitude);
    }

    std::string parse_string() {
        if (cursor_ >= input_.size() || input_[cursor_] != '"')
            throw std::runtime_error("semantic string is invalid");
        ++cursor_;
        const std::size_t begin = cursor_;
        while (cursor_ < input_.size() && input_[cursor_] != '"') {
            const unsigned char c = static_cast<unsigned char>(input_[cursor_]);
            if (c < 0x20U || c > 0x7eU || c == '\\')
                throw std::runtime_error("semantic string must be unescaped printable ASCII");
            ++cursor_;
        }
        if (cursor_ >= input_.size()) throw std::runtime_error("unterminated semantic string");
        std::string result(input_.substr(begin, cursor_ - begin));
        ++cursor_;
        return result;
    }

    bool parse_bool() {
        if (input_.substr(cursor_, 4) == "true") { cursor_ += 4; return true; }
        if (input_.substr(cursor_, 5) == "false") { cursor_ += 5; return false; }
        throw std::runtime_error("semantic bool is invalid");
    }

    static std::uint32_t narrow_u32(std::uint64_t value, const char* field) {
        if (value > std::numeric_limits<std::uint32_t>::max())
            throw std::runtime_error(std::string(field) + " exceeds uint32");
        return static_cast<std::uint32_t>(value);
    }

    static std::int32_t narrow_i32(std::int64_t value, const char* field) {
        if (value < std::numeric_limits<std::int32_t>::min()
                || value > std::numeric_limits<std::int32_t>::max())
            throw std::runtime_error(std::string(field) + " exceeds int32");
        return static_cast<std::int32_t>(value);
    }

    std::string_view input_;
    std::size_t cursor_{0};
};

SemanticFile load_semantic(const std::filesystem::path& path,
                           const std::string& expected_sha256) {
    SemanticFile file;
    file.path = canonical_existing(path);
    file.size_bytes = std::filesystem::file_size(file.path);
    if (file.size_bytes == 0U
            || file.size_bytes > static_cast<std::uintmax_t>(MAX_ACTIONS) * 1024U)
        throw std::runtime_error("semantic JSONL size outside bounded contract");
    file.sha256 = checked_sha256(file.path);
    if (file.sha256 != expected_sha256) throw std::runtime_error("semantic JSONL SHA256 mismatch");
    const std::string raw = read_binary(file.path);
    if (raw.size() != file.size_bytes) throw std::runtime_error("semantic JSONL changed while reading");
    if (checked_sha256(file.path) != file.sha256)
        throw std::runtime_error("semantic JSONL changed while reading");
    if (raw.empty() || raw.back() != '\n' || raw.find('\r') != std::string::npos)
        throw std::runtime_error("semantic JSONL must be nonempty LF-only and LF-terminated");
    std::size_t begin = 0;
    while (begin < raw.size()) {
        const std::size_t end = raw.find('\n', begin);
        if (end == std::string::npos || end == begin)
            throw std::runtime_error("semantic JSONL contains an empty or unterminated line");
        file.rows.push_back(CanonicalRowParser(
            std::string_view(raw).substr(begin, end - begin)).parse());
        if (file.rows.size() > MAX_ACTIONS)
            throw std::runtime_error("semantic JSONL exceeds maximum action rows");
        begin = end + 1U;
    }
    return file;
}

bool semantic_less(const Move& left, const Move& right) noexcept {
    return std::tuple{static_cast<int>(left.from), static_cast<int>(left.to),
                      static_cast<std::uint64_t>(left.captured), left.promotes}
         < std::tuple{static_cast<int>(right.from), static_cast<int>(right.to),
                      static_cast<std::uint64_t>(right.captured), right.promotes};
}

std::vector<Move> semantic_catalogue(const Position& parent) {
    MoveList generated;
    generate_legal_moves(parent, generated);
    std::vector<Move> unique;
    unique.reserve(generated.size());
    for (const Move& move : generated) {
        if (std::find(unique.begin(), unique.end(), move) == unique.end()) unique.push_back(move);
    }
    std::sort(unique.begin(), unique.end(), semantic_less);
    if (std::adjacent_find(unique.begin(), unique.end()) != unique.end())
        throw std::runtime_error("movegen catalogue contains a semantic duplicate");
    return unique;
}

int material_count_delta_parent(const Position& parent, const Position& child) noexcept {
    const bool white = parent.side_to_move() == Color::White;
    const int own_before = popcount(white ? parent.whites() : parent.blacks());
    const int opp_before = popcount(white ? parent.blacks() : parent.whites());
    const int own_after = popcount(white ? child.whites() : child.blacks());
    const int opp_after = popcount(white ? child.blacks() : child.whites());
    return (own_after - opp_after) - (own_before - opp_before);
}

void validate_row_shape(const SemanticRow& row, std::uint32_t total_actions) {
    if (row.global_row_index >= total_actions || row.local_row_index >= total_actions)
        throw std::runtime_error("semantic row index outside action cardinality");
    if (row.parent_id >= PARENT_COUNT || row.source_shard >= SHARD_COUNT
            || row.source_shard != row.parent_id % SHARD_COUNT)
        throw std::runtime_error("semantic parent/shard identity mismatch");
    if (row.from < 1 || row.from > 50 || row.to < 1 || row.to > 50)
        throw std::runtime_error("semantic move square outside 1..50");
    if (row.parent_legal_moves < 2 || row.parent_legal_moves > 16)
        throw std::runtime_error("semantic parent legal count outside 2..16");
    if (row.parent_pieces < 9 || row.parent_pieces > 40
            || row.child_pieces < 1 || row.child_pieces > 40)
        throw std::runtime_error("semantic piece count outside contract");
    if (row.num_captures > 20 || row.captured_kings > row.num_captures
            || (row.captured & ~PLAYABLE_BB) != 0
            || popcount(row.captured) != static_cast<int>(row.num_captures))
        throw std::runtime_error("semantic capture fields are inconsistent");
    if ((row.num_captures == 0) != (row.captured == 0))
        throw std::runtime_error("quiet/capture identity mismatch");
    if (row.material_count_delta_parent < -40 || row.material_count_delta_parent > 40)
        throw std::runtime_error("material delta outside board range");
}

void verify_payloads(const JnnwFile& parents,
                     const JnnwFile& children,
                     const SemanticFile& semantic) {
    if (parents.rows.size() != PARENT_COUNT || parents.nonzero_targets != 0)
        throw std::runtime_error("parents JNNW must contain 4000 zero-target records");
    if (children.rows.size() < MIN_ACTIONS || children.rows.size() > MAX_ACTIONS
            || children.rows.size() != semantic.rows.size())
        throw std::runtime_error("child/semantic action cardinality mismatch");
    if (children.nonzero_targets != 0)
        throw std::runtime_error("children JNNW contains nonzero targets");
    const std::uint32_t action_count = static_cast<std::uint32_t>(semantic.rows.size());
    std::array<std::uint32_t, SHARD_COUNT> next_local_index{};
    std::size_t cursor = 0;
    for (std::uint32_t parent_id = 0; parent_id < PARENT_COUNT; ++parent_id) {
        const DiskRow& parent_row = parents.rows[parent_id];
        const int actual_parent_pieces = piece_count(parent_row);
        if (actual_parent_pieces < 9 || actual_parent_pieces > 40)
            throw std::runtime_error("parent JNNW piece count outside 9..40");
        const Position parent = position_from_row(parent_row);
        const std::vector<Move> catalogue = semantic_catalogue(parent);
        if (catalogue.size() < 2U || catalogue.size() > 16U)
            throw std::runtime_error("native legal catalogue outside 2..16");
        if (cursor + catalogue.size() > semantic.rows.size())
            throw std::runtime_error("semantic ledger ends within a parent catalogue");

        const std::string parent_fp = fingerprint(parent_row);
        for (std::size_t action = 0; action < catalogue.size(); ++action, ++cursor) {
            const SemanticRow& row = semantic.rows[cursor];
            validate_row_shape(row, action_count);
            if (row.global_row_index != cursor || row.parent_id != parent_id
                    || row.parent_legal_moves != catalogue.size()
                    || row.parent_pieces != static_cast<std::uint32_t>(actual_parent_pieces)
                    || row.parent_fingerprint != parent_fp)
                throw std::runtime_error("semantic parent block/order metadata mismatch");
            if (row.local_row_index != next_local_index[row.source_shard]++)
                throw std::runtime_error("shard local_row_index order is not 0..n-1");

            const Move& move = catalogue[action];
            if (row.from != move.from || row.to != move.to
                    || row.num_captures != move.num_captures
                    || row.promotes != move.promotes || row.captured != move.captured)
                throw std::runtime_error("semantic action differs from native legal catalogue");
            const auto opponent = opposite(parent.side_to_move());
            if (row.captured_kings != static_cast<std::uint32_t>(
                    popcount(move.captured & parent.kings_of(opponent))))
                throw std::runtime_error("captured-kings count mismatch");

            const Position expected_child = parent.after(move);
            const DiskRow expected_row = row_from_position(expected_child);
            const DiskRow& actual_child_row = children.rows[cursor];
            const Position actual_child = position_from_row(actual_child_row);
            if (!(expected_child == actual_child))
                throw std::runtime_error("published child differs from Position::after");
            if (row.child_fingerprint != fingerprint(expected_row)
                    || row.child_pieces != static_cast<std::uint32_t>(piece_count(expected_row))
                    || row.material_count_delta_parent
                        != material_count_delta_parent(parent, expected_child))
                throw std::runtime_error("semantic child structural fields mismatch");
        }
    }
    if (cursor != semantic.rows.size())
        throw std::runtime_error("semantic ledger has rows after parent 3999");
    if (std::any_of(next_local_index.begin(), next_local_index.end(),
                    [](std::uint32_t count) { return count < 500U || count > 4'000U; }))
        throw std::runtime_error("shard action cardinality outside 500..4000");
}

std::string descriptor_json(const JnnwFile& file) {
    return "{\"local_name\":" + json_string(checked_local_name(file.path))
        + ",\"record_size_bytes\":38,\"records\":" + std::to_string(file.rows.size())
        + ",\"sha256\":" + json_string(file.sha256)
        + ",\"size_bytes\":" + std::to_string(file.size_bytes) + "}";
}

std::string semantic_descriptor_json(const SemanticFile& file) {
    return "{\"local_name\":" + json_string(checked_local_name(file.path))
        + ",\"row_schema\":" + json_string(ROW_SCHEMA)
        + ",\"rows\":" + std::to_string(file.rows.size())
        + ",\"sha256\":" + json_string(file.sha256)
        + ",\"size_bytes\":" + std::to_string(file.size_bytes) + "}";
}

std::string executable_descriptor_json(const FileIdentity& file) {
    return "{\"local_name\":" + json_string(checked_local_name(file.path))
        + ",\"sha256\":" + json_string(file.sha256)
        + ",\"size_bytes\":" + std::to_string(file.size_bytes) + "}";
}

std::string receipt_json(const JnnwFile& parents,
                         const JnnwFile& children,
                         const SemanticFile& semantic,
                         const FileIdentity& executable,
                         const BuildProvenance& build) {
    const std::string actions = std::to_string(semantic.rows.size());
    std::ostringstream out;
    out << "{\"actions_verified\":" << actions
        << ",\"build_provenance_declared\":{\"build_type\":" << json_string(build.build_type)
        << ",\"cmake_cache_sha256\":" << json_string(build.cmake_cache_sha256)
        << ",\"code_sha\":" << json_string(build.code_sha)
        << ",\"compiler_id\":" << json_string(build.compiler_id)
        << ",\"compiler_version\":" << json_string(build.compiler_version)
        << ",\"verifier_source_sha256\":" << json_string(build.verifier_source_sha256)
        << "},\"catalogue_actions_generated\":" << actions
        << ",\"catalogues_verified\":4000"
        << ",\"children\":" << descriptor_json(children)
        << ",\"duplicate_semantic_actions\":0"
        << ",\"executable\":" << executable_descriptor_json(executable)
        << ",\"extra_actions\":0,\"forbidden_reordering\":0"
        << ",\"identity_order\":[\"from\",\"to\",\"captured_square_bitboard_uint64\",\"promotes\"]"
        << ",\"identity_tuple\":[\"from\",\"to\",\"num_captures\",\"promotes\",\"captured_square_bitboard\"]"
        << ",\"missing_actions\":0,\"nonzero_child_targets\":0,\"nonzero_parent_targets\":0"
        << ",\"parent_after_matches\":" << actions
        << ",\"parent_count_matches\":4000"
        << ",\"parents\":" << descriptor_json(parents)
        << ",\"parents_verified\":4000"
        << ",\"schema\":" << json_string(RECEIPT_SCHEMA)
        << ",\"semantic_actions\":" << semantic_descriptor_json(semantic)
        << ",\"semantic_rows_verified\":" << actions
        << ",\"verification_complete\":true}\n";
    return out.str();
}

bool path_is_absent(const std::filesystem::path& path) {
    std::error_code error;
    const auto status = std::filesystem::symlink_status(path, error);
    if (status.type() == std::filesystem::file_type::not_found
            && (!error || error == std::errc::no_such_file_or_directory))
        return true;
    if (error) throw std::runtime_error("cannot inspect output path: " + path.string());
    return false;
}

void write_exclusive(const std::filesystem::path& path, std::string_view bytes) {
#ifdef _WIN32
    const int descriptor = _open(path.string().c_str(),
        _O_WRONLY | _O_CREAT | _O_EXCL | _O_BINARY, _S_IREAD | _S_IWRITE);
#else
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
#endif
    if (descriptor < 0)
        throw std::runtime_error("cannot exclusively create receipt temporary");
    std::size_t offset = 0;
    bool descriptor_open = true;
    try {
        while (offset < bytes.size()) {
            const std::size_t remaining = bytes.size() - offset;
#ifdef _WIN32
            const unsigned chunk = static_cast<unsigned>(std::min<std::size_t>(
                remaining, std::numeric_limits<unsigned>::max()));
            const int written = _write(descriptor, bytes.data() + offset, chunk);
#else
            const ssize_t written = ::write(descriptor, bytes.data() + offset, remaining);
#endif
            if (written <= 0) throw std::runtime_error("cannot write receipt temporary");
            offset += static_cast<std::size_t>(written);
        }
#ifdef _WIN32
        const int close_result = _close(descriptor);
#else
        const int close_result = ::close(descriptor);
#endif
        descriptor_open = false;
        if (close_result != 0) throw std::runtime_error("cannot close receipt temporary");
    } catch (...) {
        if (descriptor_open) {
#ifdef _WIN32
            (void)_close(descriptor);
#else
            (void)::close(descriptor);
#endif
        }
        std::error_code ignored;
        std::filesystem::remove(path, ignored);
        throw;
    }
}

void publish_receipt(const std::filesystem::path& receipt,
                     const std::string& bytes,
                     const std::vector<std::filesystem::path>& protected_inputs) {
    const std::filesystem::path temporary = receipt.string() + ".tmp";
    std::vector<std::filesystem::path> paths = protected_inputs;
    paths.push_back(receipt);
    paths.push_back(temporary);
    std::unordered_set<std::string> keys;
    for (const auto& path : paths) {
        if (!keys.insert(path_key(path)).second)
            throw std::runtime_error("input/output/temporary path alias");
    }
    if (!path_is_absent(receipt) || !path_is_absent(temporary))
        throw std::runtime_error("refusing existing receipt or temporary");
    if (!receipt.parent_path().empty() && !std::filesystem::is_directory(receipt.parent_path()))
        throw std::runtime_error("receipt parent directory does not exist");
    bool temporary_owned = false;
    bool receipt_owned = false;
    try {
        write_exclusive(temporary, bytes);
        temporary_owned = true;
        if (read_binary(temporary) != bytes)
            throw std::runtime_error("receipt temporary round-trip mismatch");
        // create_hard_link is an atomic no-replace publication: it fails if a
        // file or even a dangling symlink appeared at the final path.
        std::filesystem::create_hard_link(temporary, receipt);
        receipt_owned = true;
        std::filesystem::remove(temporary);
        temporary_owned = false;
        if (read_binary(receipt) != bytes)
            throw std::runtime_error("published receipt round-trip mismatch");
    } catch (...) {
        std::error_code ignored;
        if (temporary_owned) std::filesystem::remove(temporary, ignored);
        if (receipt_owned) std::filesystem::remove(receipt, ignored);
        throw;
    }
}

struct Args {
    std::filesystem::path parents;
    std::filesystem::path children;
    std::filesystem::path semantic;
    std::filesystem::path executable;
    std::filesystem::path receipt;
    std::string expected_parents_sha;
    std::string expected_children_sha;
    std::string expected_semantic_sha;
    std::string expected_executable_sha;
    BuildProvenance build;
};

Args parse_args(int argc, char** argv) {
    if (argc < 2 || std::string_view(argv[1]) != "verify" || (argc - 2) % 2 != 0)
        throw std::invalid_argument("expected verify followed by flag/value pairs");
    std::vector<std::pair<std::string, std::string>> values;
    for (int index = 2; index < argc; index += 2) {
        const std::string flag = argv[index];
        if (!flag.starts_with("--") || flag.size() <= 2U)
            throw std::invalid_argument("invalid CLI flag");
        if (std::any_of(values.begin(), values.end(), [&](const auto& item) {
                return item.first == flag;
            })) throw std::invalid_argument("duplicate CLI flag: " + flag);
        values.emplace_back(flag, argv[index + 1]);
    }
    const auto take = [&](std::string_view flag) -> std::string {
        const auto found = std::find_if(values.begin(), values.end(), [&](const auto& item) {
            return item.first == flag;
        });
        if (found == values.end()) throw std::invalid_argument("missing CLI flag: " + std::string(flag));
        return found->second;
    };
    Args args;
    args.parents = take("--parents-jnnw");
    args.children = take("--children-jnnw");
    args.semantic = take("--semantic-actions");
    args.executable = take("--verifier-executable");
    args.expected_parents_sha = take("--expected-parents-sha256");
    args.expected_children_sha = take("--expected-children-sha256");
    args.expected_semantic_sha = take("--expected-semantic-actions-sha256");
    args.expected_executable_sha = take("--expected-verifier-executable-sha256");
    args.build.code_sha = take("--code-sha");
    args.build.verifier_source_sha256 = take("--verifier-source-sha256");
    args.build.cmake_cache_sha256 = take("--cmake-cache-sha256");
    args.build.build_type = take("--build-type");
    args.build.compiler_id = take("--compiler-id");
    args.build.compiler_version = take("--compiler-version");
    args.receipt = take("--receipt");
    if (values.size() != 15U) throw std::invalid_argument("unknown CLI flag");
    for (const auto* digest : {&args.expected_parents_sha, &args.expected_children_sha,
                               &args.expected_semantic_sha, &args.expected_executable_sha,
                               &args.build.verifier_source_sha256,
                               &args.build.cmake_cache_sha256}) {
        if (!lowercase_hex(*digest, 64)) throw std::invalid_argument("invalid lowercase SHA256");
    }
    if (!lowercase_hex(args.build.code_sha, 40)) throw std::invalid_argument("invalid code SHA");
    if (args.build.build_type != "Release" || !printable_ascii(args.build.compiler_id)
            || !printable_ascii(args.build.compiler_version))
        throw std::invalid_argument("invalid declared build provenance");
    return args;
}

FileIdentity verify_executable(const std::filesystem::path& argv0,
                               const std::filesystem::path& declared,
                               const std::string& expected_sha) {
    const auto actual = canonical_existing(argv0);
    const auto stated = canonical_existing(declared);
    std::error_code error;
    if (!std::filesystem::equivalent(actual, stated, error) || error)
        throw std::runtime_error("declared verifier executable differs from argv[0]");
    const std::string digest = checked_sha256(actual);
    if (digest != expected_sha) throw std::runtime_error("verifier executable SHA256 mismatch");
    return FileIdentity{actual, digest, std::filesystem::file_size(actual)};
}

std::string semantic_line(const SemanticRow& row) {
    std::ostringstream out;
    out << "{\"captured_kings\":" << row.captured_kings
        << ",\"captured_square_bitboard\":" << row.captured
        << ",\"child_fingerprint\":" << json_string(row.child_fingerprint)
        << ",\"child_pieces\":" << row.child_pieces
        << ",\"from\":" << row.from
        << ",\"global_row_index\":" << row.global_row_index
        << ",\"local_row_index\":" << row.local_row_index
        << ",\"material_count_delta_parent\":" << row.material_count_delta_parent
        << ",\"num_captures\":" << row.num_captures
        << ",\"parent_fingerprint\":" << json_string(row.parent_fingerprint)
        << ",\"parent_id\":" << row.parent_id
        << ",\"parent_legal_moves\":" << row.parent_legal_moves
        << ",\"parent_pieces\":" << row.parent_pieces
        << ",\"promotes\":" << (row.promotes ? "true" : "false")
        << ",\"schema\":" << json_string(ROW_SCHEMA)
        << ",\"source_shard\":" << row.source_shard
        << ",\"to\":" << row.to << '}';
    return out.str();
}

void require_selftest(bool condition, std::string_view message) {
    if (!condition) throw std::runtime_error("selftest: " + std::string(message));
}

int selftest() {
    const auto multi = Position::from_fen("W:W40,43,K2:B8,18,29,30");
    require_selftest(multi.has_value(), "multi-path FEN parse");
    const auto catalogue = semantic_catalogue(*multi);
    require_selftest(catalogue.size() == 9U, "multi-path catalogue size");
    const Bitboard expected_captured = square_bb(8) | square_bb(30);
    require_selftest(std::count_if(catalogue.begin(), catalogue.end(), [&](const Move& move) {
        return move.from == 2 && move.to == 35 && move.captured == expected_captured;
    }) == 1, "multi-path capture must have unit semantic weight");

    const auto same_endpoints = Position::from_fen("W:WK34:B11,17,29,38");
    require_selftest(same_endpoints.has_value(), "same-endpoint FEN parse");
    const auto second = semantic_catalogue(*same_endpoints);
    std::vector<Bitboard> endpoint_sets;
    for (const Move& move : second) {
        if (move.from == 34 && move.to == 43 && move.num_captures == 3)
            endpoint_sets.push_back(move.captured);
    }
    std::sort(endpoint_sets.begin(), endpoint_sets.end());
    endpoint_sets.erase(std::unique(endpoint_sets.begin(), endpoint_sets.end()), endpoint_sets.end());
    require_selftest(endpoint_sets.size() == 2U, "captured set distinguishes same endpoints");
    require_selftest(std::find(endpoint_sets.begin(), endpoint_sets.end(),
        square_bb(29) | square_bb(17) | square_bb(38)) != endpoint_sets.end(),
        "first captured set missing");
    require_selftest(std::find(endpoint_sets.begin(), endpoint_sets.end(),
        square_bb(29) | square_bb(11) | square_bb(38)) != endpoint_sets.end(),
        "second captured set missing");

    const Move& move = catalogue.front();
    const DiskRow parent = row_from_position(*multi);
    const DiskRow child = row_from_position(multi->after(move));
    SemanticRow row;
    row.captured = move.captured;
    row.captured_kings = static_cast<std::uint32_t>(
        popcount(move.captured & multi->kings_of(opposite(multi->side_to_move()))));
    row.child_fingerprint = fingerprint(child);
    row.child_pieces = static_cast<std::uint32_t>(piece_count(child));
    row.from = move.from;
    row.global_row_index = 0;
    row.local_row_index = 0;
    row.material_count_delta_parent = material_count_delta_parent(*multi, multi->after(move));
    row.num_captures = move.num_captures;
    row.parent_fingerprint = fingerprint(parent);
    row.parent_id = 0;
    row.parent_legal_moves = static_cast<std::uint32_t>(catalogue.size());
    row.parent_pieces = static_cast<std::uint32_t>(piece_count(parent));
    row.promotes = move.promotes;
    row.source_shard = 0;
    row.to = move.to;
    require_selftest(semantic_line(CanonicalRowParser(semantic_line(row)).parse())
                         == semantic_line(row),
                     "canonical semantic row round-trip");
    std::string reordered = semantic_line(row);
    reordered.insert(1, " ");
    bool rejected = false;
    try { (void)CanonicalRowParser(reordered).parse(); }
    catch (const std::exception&) { rejected = true; }
    require_selftest(rejected, "noncanonical JSON rejection");

    std::cout << "adaptive_sibling_b2_teacher_merge_verify selftest PASS\n";
    return 0;
}

int run_verify(int argc, char** argv) {
    const Args args = parse_args(argc, argv);
    FileIdentity executable;
    JnnwFile parents;
    JnnwFile children;
    SemanticFile semantic;
    try {
        executable = verify_executable(argv[0], args.executable, args.expected_executable_sha);
        parents = load_jnnw(args.parents, args.expected_parents_sha,
                            PARENT_COUNT, PARENT_COUNT);
        children = load_jnnw(args.children, args.expected_children_sha,
                             MIN_ACTIONS, MAX_ACTIONS);
        semantic = load_semantic(args.semantic, args.expected_semantic_sha);
        (void)checked_local_name(executable.path);
        (void)checked_local_name(parents.path);
        (void)checked_local_name(children.path);
        (void)checked_local_name(semantic.path);
    } catch (const std::exception& error) {
        throw ExitError(3, error.what());
    }
    try {
        verify_payloads(parents, children, semantic);
    } catch (const std::exception& error) {
        throw ExitError(4, error.what());
    }
    const std::string receipt = receipt_json(parents, children, semantic, executable, args.build);
    try {
        publish_receipt(args.receipt, receipt,
            {parents.path, children.path, semantic.path, executable.path});
    } catch (const std::exception& error) {
        throw ExitError(5, error.what());
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest") return selftest();
        return run_verify(argc, argv);
    } catch (const ExitError& error) {
        std::cerr << "error: " << error.what() << '\n';
        return error.code();
    } catch (const std::invalid_argument& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    } catch (const std::filesystem::filesystem_error& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 5;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 4;
    }
}
