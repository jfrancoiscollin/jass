// SPDX-License-Identifier: AGPL-3.0-or-later
// Test-only native fixture generator for the prospective PR771 B2 merge tests.

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
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

constexpr std::size_t RECORD_SIZE = 38;
constexpr std::uint32_t SELECTED_PARENTS = 4'000;
constexpr std::uint32_t SHARDS = 16;
constexpr std::uint32_t MAX_POOL_ROWS = 1'000'000;
constexpr std::string_view CATALOG_HEADER =
    "pool_row_index\tparent_fingerprint\tparent_stm\tpieces\tlegal_semantic_moves\n";
constexpr std::string_view ACTION_HEADER =
    "local_row_index\tparent_id\tparent_fingerprint\tparent_stm\tparent_pieces\t"
    "from\tto\tnum_captures\tpromotes\tmoving_king\tcaptured_kings\t"
    "captured_square_bitboard\tmaterial_count_delta_parent\tchild_fingerprint\tchild_pieces\n";

struct DiskRow {
    std::uint64_t wm{0};
    std::uint64_t wk{0};
    std::uint64_t bm{0};
    std::uint64_t bk{0};
    std::uint8_t stm{0};
};

struct Output {
    std::filesystem::path final_path;
    std::filesystem::path temporary_path;
    std::string bytes;
    bool temporary_owned{false};
    bool final_owned{false};
};

template <typename T>
T load_le(const char* data) noexcept {
    T value = 0;
    for (std::size_t index = 0; index < sizeof(T); ++index) {
        value |= static_cast<T>(static_cast<unsigned char>(data[index])) << (8U * index);
    }
    return value;
}

template <typename T>
void append_le(std::string& bytes, T value) {
    static_assert(std::is_unsigned_v<T>);
    for (std::size_t index = 0; index < sizeof(T); ++index) {
        bytes.push_back(static_cast<char>((value >> (8U * index)) & static_cast<T>(0xffU)));
    }
}

std::string read_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input: " + path.string());
    std::ostringstream out;
    out << input.rdbuf();
    if (!input.good() && !input.eof())
        throw std::runtime_error("cannot read input: " + path.string());
    return out.str();
}

bool path_absent(const std::filesystem::path& path) {
    std::error_code error;
    const auto status = std::filesystem::symlink_status(path, error);
    if (status.type() == std::filesystem::file_type::not_found
            && (!error || error == std::errc::no_such_file_or_directory)) return true;
    if (error) throw std::runtime_error("cannot inspect output path: " + path.string());
    return false;
}

std::string path_key(const std::filesystem::path& path) {
    std::error_code error;
    auto normalized = std::filesystem::weakly_canonical(path, error);
    if (error) normalized = std::filesystem::absolute(path, error).lexically_normal();
    std::string key = normalized.generic_string();
    std::transform(key.begin(), key.end(), key.begin(), [](unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return key;
}

void write_exclusive(const std::filesystem::path& path, std::string_view bytes) {
#ifdef _WIN32
    const int descriptor = _open(path.string().c_str(),
        _O_WRONLY | _O_CREAT | _O_EXCL | _O_BINARY, _S_IREAD | _S_IWRITE);
#else
    const int descriptor = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
#endif
    if (descriptor < 0) throw std::runtime_error("cannot exclusively create temporary output");
    bool open = true;
    try {
        std::size_t offset = 0;
        while (offset < bytes.size()) {
#ifdef _WIN32
            const unsigned chunk = static_cast<unsigned>(std::min<std::size_t>(
                bytes.size() - offset, std::numeric_limits<unsigned>::max()));
            const int written = _write(descriptor, bytes.data() + offset, chunk);
#else
            const ssize_t written = ::write(descriptor, bytes.data() + offset, bytes.size() - offset);
#endif
            if (written <= 0) throw std::runtime_error("cannot write temporary output");
            offset += static_cast<std::size_t>(written);
        }
#ifdef _WIN32
        const int result = _close(descriptor);
#else
        const int result = ::close(descriptor);
#endif
        open = false;
        if (result != 0) throw std::runtime_error("cannot close temporary output");
    } catch (...) {
        if (open) {
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

void publish_outputs(std::vector<Output>& outputs,
                     const std::vector<std::filesystem::path>& protected_inputs) {
    std::unordered_set<std::string> keys;
    for (const auto& input : protected_inputs) {
        if (!keys.insert(path_key(input)).second)
            throw std::runtime_error("duplicate protected input path");
    }
    for (const auto& output : outputs) {
        if (!keys.insert(path_key(output.final_path)).second
                || !keys.insert(path_key(output.temporary_path)).second)
            throw std::runtime_error("input/output/temporary path alias");
        if (!path_absent(output.final_path) || !path_absent(output.temporary_path))
            throw std::runtime_error("refusing existing output or temporary");
        const auto parent = output.final_path.parent_path().empty()
            ? std::filesystem::path(".") : output.final_path.parent_path();
        if (!std::filesystem::is_directory(parent))
            throw std::runtime_error("output parent directory does not exist");
    }
    try {
        for (auto& output : outputs) {
            write_exclusive(output.temporary_path, output.bytes);
            output.temporary_owned = true;
            if (read_file(output.temporary_path) != output.bytes)
                throw std::runtime_error("temporary output roundtrip mismatch");
        }
        for (auto& output : outputs) {
            std::filesystem::create_hard_link(output.temporary_path, output.final_path);
            output.final_owned = true;
            if (!std::filesystem::remove(output.temporary_path))
                throw std::runtime_error("cannot remove linked temporary output");
            output.temporary_owned = false;
            if (read_file(output.final_path) != output.bytes)
                throw std::runtime_error("published output roundtrip mismatch");
        }
    } catch (...) {
        for (auto& output : outputs) {
            std::error_code ignored;
            if (output.temporary_owned) std::filesystem::remove(output.temporary_path, ignored);
            if (output.final_owned) std::filesystem::remove(output.final_path, ignored);
        }
        throw;
    }
}

bool valid_row(const DiskRow& row) noexcept {
    if (row.stm > 1U) return false;
    const Bitboard occupied = row.wm | row.wk | row.bm | row.bk;
    if ((occupied & ~PLAYABLE_BB) != 0) return false;
    return ((row.wm & row.wk) | (row.wm & row.bm) | (row.wm & row.bk)
          | (row.wk & row.bm) | (row.wk & row.bk) | (row.bm & row.bk)) == 0;
}

std::vector<DiskRow> load_jnnw(const std::filesystem::path& requested,
                               std::uint32_t minimum_rows,
                               std::uint32_t maximum_rows) {
    std::error_code error;
    const auto path = std::filesystem::canonical(requested, error);
    if (error || !std::filesystem::is_regular_file(path, error) || error)
        throw std::runtime_error("JNNW input is not an existing regular file");
    const auto size = std::filesystem::file_size(path);
    if (size < 8U || size > 8ULL + static_cast<std::uint64_t>(maximum_rows) * RECORD_SIZE)
        throw std::runtime_error("JNNW size outside fixture bound");
    const std::string raw = read_file(path);
    if (raw.size() != size || raw.compare(0, 4, "JNNW") != 0)
        throw std::runtime_error("invalid JNNW fixture header");
    const std::uint32_t count = load_le<std::uint32_t>(raw.data() + 4);
    if (count < minimum_rows || count > maximum_rows
            || raw.size() != 8ULL + static_cast<std::uint64_t>(count) * RECORD_SIZE)
        throw std::runtime_error("JNNW fixture count/size mismatch");
    std::vector<DiskRow> rows;
    rows.reserve(count);
    for (std::uint32_t index = 0; index < count; ++index) {
        const char* bytes = raw.data() + 8U + static_cast<std::size_t>(index) * RECORD_SIZE;
        DiskRow row{
            load_le<std::uint64_t>(bytes), load_le<std::uint64_t>(bytes + 8),
            load_le<std::uint64_t>(bytes + 16), load_le<std::uint64_t>(bytes + 24),
            static_cast<std::uint8_t>(bytes[32]),
        };
        if (!valid_row(row))
            throw std::runtime_error("invalid fixture board at row " + std::to_string(index));
        if (!std::all_of(bytes + 33, bytes + 38, [](char value) { return value == 0; }))
            throw std::runtime_error("fixture JNNW target bytes must be zero");
        rows.push_back(row);
    }
    return rows;
}

Position position_from_row(const DiskRow& row) {
    Position position;
    position.clear();
    const auto add = [&](Bitboard bits, Piece piece) {
        while (bits != 0) position.add_piece(pop_lsb(bits), piece);
    };
    add(row.wm, Piece::WhiteMan);
    add(row.wk, Piece::WhiteKing);
    add(row.bm, Piece::BlackMan);
    add(row.bk, Piece::BlackKing);
    position.set_side_to_move(row.stm == 0U ? Color::White : Color::Black);
    position.set_halfmove_clock(0);
    return position;
}

DiskRow row_from_position(const Position& position) noexcept {
    return DiskRow{position.white_men(), position.white_kings(),
                   position.black_men(), position.black_kings(),
                   static_cast<std::uint8_t>(position.side_to_move() == Color::White ? 0 : 1)};
}

std::uint32_t pieces(const DiskRow& row) noexcept {
    return static_cast<std::uint32_t>(popcount(row.wm | row.wk | row.bm | row.bk));
}

std::string fingerprint(const DiskRow& row) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::hex << std::setfill('0')
        << std::setw(13) << row.wm << ':' << std::setw(13) << row.wk << ':'
        << std::setw(13) << row.bm << ':' << std::setw(13) << row.bk << ':'
        << std::dec << static_cast<unsigned>(row.stm);
    return out.str();
}

std::vector<Move> semantic_catalogue(const Position& parent, bool sort_moves) {
    MoveList generated;
    generate_legal_moves(parent, generated);
    std::vector<Move> unique;
    unique.reserve(generated.size());
    for (const Move& move : generated) {
        if (std::find(unique.begin(), unique.end(), move) == unique.end()) unique.push_back(move);
    }
    if (sort_moves) {
        std::sort(unique.begin(), unique.end(), [](const Move& left, const Move& right) {
            return std::tuple{static_cast<int>(left.from), static_cast<int>(left.to),
                              static_cast<std::uint64_t>(left.captured), left.promotes}
                 < std::tuple{static_cast<int>(right.from), static_cast<int>(right.to),
                              static_cast<std::uint64_t>(right.captured), right.promotes};
        });
    }
    if (std::adjacent_find(unique.begin(), unique.end()) != unique.end())
        throw std::runtime_error("semantic catalogue contains a duplicate");
    for (const Move& move : unique) {
        if (move.from < 1 || move.from > 50 || move.to < 1 || move.to > 50
                || (move.captured & ~PLAYABLE_BB) != 0
                || move.num_captures != popcount(move.captured))
            throw std::runtime_error("native movegen emitted an invalid semantic move");
    }
    return unique;
}

int material_count_delta_parent(const Position& parent, const Position& child) noexcept {
    const bool white = parent.side_to_move() == Color::White;
    const int own_before = popcount(white ? parent.whites() : parent.blacks());
    const int opponent_before = popcount(white ? parent.blacks() : parent.whites());
    const int own_after = popcount(white ? child.whites() : child.blacks());
    const int opponent_after = popcount(white ? child.blacks() : child.whites());
    return (own_after - opponent_after) - (own_before - opponent_before);
}

std::string jnnw_bytes(const std::vector<DiskRow>& rows) {
    if (rows.size() > std::numeric_limits<std::uint32_t>::max())
        throw std::runtime_error("too many fixture child rows");
    std::string bytes("JNNW", 4);
    append_le(bytes, static_cast<std::uint32_t>(rows.size()));
    for (const DiskRow& row : rows) {
        append_le(bytes, row.wm);
        append_le(bytes, row.wk);
        append_le(bytes, row.bm);
        append_le(bytes, row.bk);
        bytes.push_back(static_cast<char>(row.stm));
        bytes.append(5, '\0');
    }
    return bytes;
}

int run_catalog(const std::filesystem::path& input, const std::filesystem::path& output) {
    const auto parents = load_jnnw(input, 1, MAX_POOL_ROWS);
    std::ostringstream tsv;
    tsv.imbue(std::locale::classic());
    tsv << CATALOG_HEADER;
    for (std::uint32_t index = 0; index < parents.size(); ++index) {
        const DiskRow& row = parents[index];
        const std::uint32_t count = pieces(row);
        if (count < 9U || count > 40U) continue;
        const auto moves = semantic_catalogue(position_from_row(row), false);
        if (moves.size() < 2U || moves.size() > 16U) continue;
        tsv << index << '\t' << fingerprint(row) << '\t' << static_cast<unsigned>(row.stm)
            << '\t' << count << '\t' << moves.size() << '\n';
    }
    std::vector<Output> outputs{{output, output.string() + ".tmp", tsv.str()}};
    publish_outputs(outputs, {input});
    return 0;
}

int run_export(const std::filesystem::path& input,
               const std::filesystem::path& requested_directory) {
    const auto parents = load_jnnw(input, SELECTED_PARENTS, SELECTED_PARENTS);
    std::error_code error;
    const auto directory = std::filesystem::canonical(requested_directory, error);
    if (error || !std::filesystem::is_directory(directory, error) || error)
        throw std::runtime_error("export output directory must already exist");
    std::array<std::vector<DiskRow>, SHARDS> children;
    std::array<std::ostringstream, SHARDS> actions;
    for (auto& stream : actions) {
        stream.imbue(std::locale::classic());
        stream << ACTION_HEADER;
    }
    for (std::uint32_t parent_id = 0; parent_id < SELECTED_PARENTS; ++parent_id) {
        const DiskRow& parent_row = parents[parent_id];
        const std::uint32_t parent_pieces = pieces(parent_row);
        if (parent_pieces < 9U || parent_pieces > 40U)
            throw std::runtime_error("selected fixture parent outside 9..40 pieces");
        const Position parent = position_from_row(parent_row);
        const auto moves = semantic_catalogue(parent, true);
        if (moves.size() < 2U || moves.size() > 16U)
            throw std::runtime_error("selected fixture parent outside 2..16 semantic moves");
        const std::uint32_t shard = parent_id % SHARDS;
        const std::string parent_fp = fingerprint(parent_row);
        for (const Move& move : moves) {
            const std::uint32_t local = static_cast<std::uint32_t>(children[shard].size());
            const bool moving_king = test(parent.kings_of(parent.side_to_move()), move.from);
            const auto opponent = opposite(parent.side_to_move());
            const std::uint32_t captured_kings = static_cast<std::uint32_t>(
                popcount(move.captured & parent.kings_of(opponent)));
            const Position child = parent.after(move);
            const DiskRow child_row = row_from_position(child);
            children[shard].push_back(child_row);
            actions[shard]
                << local << '\t' << parent_id << '\t' << parent_fp << '\t'
                << static_cast<unsigned>(parent_row.stm) << '\t' << parent_pieces << '\t'
                << static_cast<int>(move.from) << '\t' << static_cast<int>(move.to) << '\t'
                << static_cast<unsigned>(move.num_captures) << '\t' << (move.promotes ? 1 : 0)
                << '\t' << (moving_king ? 1 : 0) << '\t' << captured_kings << '\t'
                << static_cast<std::uint64_t>(move.captured) << '\t'
                << material_count_delta_parent(parent, child) << '\t' << fingerprint(child_row)
                << '\t' << pieces(child_row) << '\n';
        }
    }
    std::vector<Output> outputs;
    outputs.reserve(SHARDS * 2U);
    for (std::uint32_t shard = 0; shard < SHARDS; ++shard) {
        std::ostringstream number;
        number << std::setfill('0') << std::setw(2) << shard;
        const std::string prefix = "shard-" + number.str();
        const auto child_path = directory / (prefix + ".children.jnnw");
        const auto action_path = directory / (prefix + ".actions.tsv");
        outputs.push_back(Output{child_path, child_path.string() + ".tmp", jnnw_bytes(children[shard])});
        outputs.push_back(Output{action_path, action_path.string() + ".tmp", actions[shard].str()});
    }
    publish_outputs(outputs, {input});
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 4 && std::string_view(argv[1]) == "catalog")
            return run_catalog(argv[2], argv[3]);
        if (argc == 4 && std::string_view(argv[1]) == "export")
            return run_export(argv[2], argv[3]);
        throw std::invalid_argument(
            "usage: adaptive_sibling_b2_native_fixture catalog POOL_JNNW OUT_TSV\n"
            "   or: adaptive_sibling_b2_native_fixture export SELECTED_JNNW OUT_DIR");
    } catch (const std::invalid_argument& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 3;
    }
}
