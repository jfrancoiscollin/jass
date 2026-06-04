// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "weights.hpp"

#include <fstream>

namespace othello {

namespace {

std::uint32_t read_u32_le(const unsigned char* p) noexcept {
    return  static_cast<std::uint32_t>(p[0])
         | (static_cast<std::uint32_t>(p[1]) <<  8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

}  // namespace

std::optional<Weights> load_weights(const std::string& path, std::string* err) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { if (err) *err = "cannot open " + path; return std::nullopt; }
    f.seekg(0, std::ios::end);
    const std::streamoff size = f.tellg();
    f.seekg(0, std::ios::beg);
    if (size < static_cast<std::streamoff>(WEIGHTS_HEADER_SIZE)) {
        if (err) *err = "file too short";
        return std::nullopt;
    }

    std::vector<unsigned char> raw(static_cast<std::size_t>(size));
    f.read(reinterpret_cast<char*>(raw.data()), size);
    if (!f) { if (err) *err = "read failure"; return std::nullopt; }

    const std::uint32_t magic   = read_u32_le(raw.data() +  0);
    const std::uint32_t version = read_u32_le(raw.data() +  4);
    const std::uint32_t count   = read_u32_le(raw.data() +  8);
    const std::uint32_t scale   = read_u32_le(raw.data() + 12);

    if (magic != WEIGHTS_MAGIC) {
        if (err) *err = "bad magic";
        return std::nullopt;
    }
    if (version != WEIGHTS_VERSION) {
        if (err) *err = "unsupported version " + std::to_string(version);
        return std::nullopt;
    }
    if (count != total_pattern_buckets()) {
        if (err) *err = "count " + std::to_string(count)
                      + " != expected " + std::to_string(total_pattern_buckets());
        return std::nullopt;
    }
    const std::size_t expected = WEIGHTS_HEADER_SIZE + count * sizeof(std::int32_t);
    if (raw.size() != expected) {
        if (err) *err = "size " + std::to_string(raw.size())
                      + " != expected " + std::to_string(expected);
        return std::nullopt;
    }

    Weights out;
    out.scale = scale;
    out.w.resize(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        const unsigned char* p = raw.data() + WEIGHTS_HEADER_SIZE + i * 4;
        const std::uint32_t u = read_u32_le(p);
        out.w[i] = static_cast<std::int32_t>(u);
    }
    return out;
}

}  // namespace othello
