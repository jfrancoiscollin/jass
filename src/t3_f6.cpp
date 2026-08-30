// SPDX-License-Identifier: AGPL-3.0-or-later
#include "t3_f6.hpp"

#include "scan_eval.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <variant>

namespace jass::t3_f6 {
namespace {

struct Json {
    using Array = std::vector<Json>;
    using Object = std::map<std::string, Json, std::less<>>;
    std::variant<std::nullptr_t, bool, double, std::string, Array, Object> value;
};

class JsonParser {
public:
    explicit JsonParser(std::string_view text) : text_(text) {}
    Json parse() {
        Json out = parse_value();
        whitespace();
        if (pos_ != text_.size()) fail("trailing JSON bytes");
        return out;
    }

private:
    [[noreturn]] void fail(const char* what) const {
        throw std::runtime_error(std::string(what) + " at byte " + std::to_string(pos_));
    }
    void whitespace() noexcept {
        while (pos_ < text_.size()) {
            const char c = text_[pos_];
            if (c != ' ' && c != '\n' && c != '\r' && c != '\t') break;
            ++pos_;
        }
    }
    bool take(char c) noexcept {
        whitespace();
        if (pos_ < text_.size() && text_[pos_] == c) { ++pos_; return true; }
        return false;
    }
    void literal(std::string_view token) {
        if (text_.substr(pos_, token.size()) != token) fail("bad JSON literal");
        pos_ += token.size();
    }
    Json parse_value() {
        whitespace();
        if (pos_ >= text_.size()) fail("unexpected JSON EOF");
        switch (text_[pos_]) {
            case '{': return parse_object();
            case '[': return parse_array();
            case '"': return Json{parse_string()};
            case 't': literal("true"); return Json{true};
            case 'f': literal("false"); return Json{false};
            case 'n': literal("null"); return Json{nullptr};
            default: return Json{parse_number()};
        }
    }
    Json parse_object() {
        if (!take('{')) fail("expected object");
        Json::Object out;
        if (take('}')) return Json{std::move(out)};
        for (;;) {
            whitespace();
            if (pos_ >= text_.size() || text_[pos_] != '"') fail("expected object key");
            std::string key = parse_string();
            if (!take(':')) fail("expected colon");
            if (!out.emplace(std::move(key), parse_value()).second) fail("duplicate object key");
            if (take('}')) break;
            if (!take(',')) fail("expected object comma");
        }
        return Json{std::move(out)};
    }
    Json parse_array() {
        if (!take('[')) fail("expected array");
        Json::Array out;
        if (take(']')) return Json{std::move(out)};
        for (;;) {
            out.push_back(parse_value());
            if (take(']')) break;
            if (!take(',')) fail("expected array comma");
        }
        return Json{std::move(out)};
    }
    std::string parse_string() {
        if (!take('"')) fail("expected string");
        std::string out;
        while (pos_ < text_.size()) {
            const unsigned char c = static_cast<unsigned char>(text_[pos_++]);
            if (c == '"') return out;
            if (c < 0x20U) fail("control byte in string");
            if (c != '\\') { out.push_back(static_cast<char>(c)); continue; }
            if (pos_ >= text_.size()) fail("truncated string escape");
            const char e = text_[pos_++];
            switch (e) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u': {
                    if (pos_ + 4U > text_.size()) fail("truncated unicode escape");
                    unsigned code = 0;
                    for (int i = 0; i < 4; ++i) {
                        const char h = text_[pos_++];
                        code <<= 4U;
                        if (h >= '0' && h <= '9') code += static_cast<unsigned>(h - '0');
                        else if (h >= 'a' && h <= 'f') code += static_cast<unsigned>(h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') code += static_cast<unsigned>(h - 'A' + 10);
                        else fail("bad unicode escape");
                    }
                    if (code > 0x7fU) fail("non-ASCII unicode escape");
                    out.push_back(static_cast<char>(code));
                    break;
                }
                default: fail("bad string escape");
            }
        }
        fail("unterminated string");
    }
    double parse_number() {
        whitespace();
        const std::size_t begin = pos_;
        if (pos_ < text_.size() && text_[pos_] == '-') ++pos_;
        if (pos_ >= text_.size()) fail("truncated number");
        if (text_[pos_] == '0') ++pos_;
        else {
            if (text_[pos_] < '1' || text_[pos_] > '9') fail("bad number");
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
        }
        if (pos_ < text_.size() && text_[pos_] == '.') {
            ++pos_; const std::size_t digits = pos_;
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
            if (digits == pos_) fail("bad fraction");
        }
        if (pos_ < text_.size() && (text_[pos_] == 'e' || text_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < text_.size() && (text_[pos_] == '+' || text_[pos_] == '-')) ++pos_;
            const std::size_t digits = pos_;
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
            if (digits == pos_) fail("bad exponent");
        }
        const std::string token{text_.substr(begin, pos_ - begin)};
        std::size_t used = 0;
        const double out = std::stod(token, &used);
        if (used != token.size() || !std::isfinite(out)) fail("non-finite number");
        return out;
    }
    std::string_view text_;
    std::size_t pos_{0};
};

const Json::Object& object(const Json& j, const char* where) {
    const auto* p = std::get_if<Json::Object>(&j.value);
    if (!p) throw std::runtime_error(std::string(where) + " is not an object");
    return *p;
}
const Json::Array& array(const Json& j, const char* where) {
    const auto* p = std::get_if<Json::Array>(&j.value);
    if (!p) throw std::runtime_error(std::string(where) + " is not an array");
    return *p;
}
const std::string& string(const Json& j, const char* where) {
    const auto* p = std::get_if<std::string>(&j.value);
    if (!p) throw std::runtime_error(std::string(where) + " is not a string");
    return *p;
}
double number(const Json& j, const char* where) {
    const auto* p = std::get_if<double>(&j.value);
    if (!p || !std::isfinite(*p)) throw std::runtime_error(std::string(where) + " is not numeric");
    return *p;
}
bool boolean(const Json& j, const char* where) {
    const auto* p = std::get_if<bool>(&j.value);
    if (!p) throw std::runtime_error(std::string(where) + " is not boolean");
    return *p;
}
const Json& member(const Json::Object& o, std::string_view key, const char* where) {
    const auto it = o.find(key);
    if (it == o.end()) throw std::runtime_error(std::string("missing ") + where + "." + std::string(key));
    return it->second;
}
void require_string(const Json::Object& o, std::string_view key,
                    std::string_view expected, const char* where) {
    if (string(member(o, key, where), where) != expected)
        throw std::runtime_error(std::string(where) + "." + std::string(key) + " contract drift");
}
void require_integer(const Json::Object& o, std::string_view key,
                     std::size_t expected, const char* where) {
    if (number(member(o, key, where), where) != static_cast<double>(expected))
        throw std::runtime_error(std::string(where) + "." + std::string(key) + " contract drift");
}
template <std::size_t N>
std::array<double, N> fixed_vector(const Json& j, const char* where) {
    const auto& a = array(j, where);
    if (a.size() != N) throw std::runtime_error(std::string(where) + " shape drift");
    std::array<double, N> out{};
    for (std::size_t i = 0; i < N; ++i) out[i] = number(a[i], where);
    return out;
}
std::vector<double> matrix(const Json& j, std::size_t rows, std::size_t cols,
                           const char* where) {
    const auto& outer = array(j, where);
    if (outer.size() != rows) throw std::runtime_error(std::string(where) + " row shape drift");
    std::vector<double> out;
    out.reserve(rows * cols);
    for (const Json& row : outer) {
        const auto& inner = array(row, where);
        if (inner.size() != cols) throw std::runtime_error(std::string(where) + " column shape drift");
        for (const Json& v : inner) out.push_back(number(v, where));
    }
    return out;
}
std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open artifact " + path);
    f.seekg(0, std::ios::end);
    const std::streamoff end = f.tellg();
    if (end <= 0) throw std::runtime_error("empty artifact " + path);
    f.seekg(0, std::ios::beg);
    std::string raw(static_cast<std::size_t>(end), '\0');
    f.read(raw.data(), static_cast<std::streamsize>(raw.size()));
    if (!f) throw std::runtime_error("cannot read artifact " + path);
    return raw;
}

constexpr std::array<std::uint32_t, 64> SHA_K = {
    0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
    0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
    0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
    0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
    0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
    0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
    0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
    0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U,
};

std::string sha256(std::string_view data) {
    std::array<std::uint32_t, 8> h = {0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
                                      0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    const std::uint64_t bit_len = static_cast<std::uint64_t>(data.size()) * 8U;
    std::vector<unsigned char> bytes(data.begin(), data.end());
    bytes.push_back(0x80U);
    while ((bytes.size() % 64U) != 56U) bytes.push_back(0U);
    for (int shift = 56; shift >= 0; shift -= 8)
        bytes.push_back(static_cast<unsigned char>((bit_len >> shift) & 0xffU));
    for (std::size_t off = 0; off < bytes.size(); off += 64U) {
        std::array<std::uint32_t, 64> w{};
        for (std::size_t i = 0; i < 16U; ++i) {
            const std::size_t p = off + 4U * i;
            w[i] = (static_cast<std::uint32_t>(bytes[p]) << 24U)
                 | (static_cast<std::uint32_t>(bytes[p+1U]) << 16U)
                 | (static_cast<std::uint32_t>(bytes[p+2U]) << 8U)
                 | static_cast<std::uint32_t>(bytes[p+3U]);
        }
        for (std::size_t i = 16U; i < 64U; ++i) {
            const std::uint32_t x=w[i-15U], y=w[i-2U];
            const std::uint32_t s0=std::rotr(x,7)^std::rotr(x,18)^(x>>3U);
            const std::uint32_t s1=std::rotr(y,17)^std::rotr(y,19)^(y>>10U);
            w[i]=w[i-16U]+s0+w[i-7U]+s1;
        }
        std::uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for (std::size_t i=0;i<64U;++i) {
            const std::uint32_t s1=std::rotr(e,6)^std::rotr(e,11)^std::rotr(e,25);
            const std::uint32_t ch=(e&f)^((~e)&g);
            const std::uint32_t t1=hh+s1+ch+SHA_K[i]+w[i];
            const std::uint32_t s0=std::rotr(a,2)^std::rotr(a,13)^std::rotr(a,22);
            const std::uint32_t t2=s0+((a&b)^(a&c)^(b&c));
            hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
    }
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (std::uint32_t v : h) out << std::setw(8) << v;
    return out.str();
}

int round_score(double score) noexcept {
    if (!std::isfinite(score)) std::terminate();
    return static_cast<int>(std::clamp(std::llround(score), -20000LL, 20000LL));
}

}  // namespace

double Model::residual_parent(const std::array<float, INPUT_WIDTH>& features) const noexcept {
    std::array<double, H0> a0{};
    std::array<double, H1> a1{};
    std::array<double, H2> a2{};
    for (std::size_t j=0;j<H0;++j) {
        double sum=b0[j];
        for (std::size_t i=0;i<INPUT_WIDTH;++i) {
            const double x=(static_cast<double>(features[i])-mean[i])/stddev[i];
            sum += x*w0[i*H0+j];
        }
        a0[j]=std::max(0.0,sum);
    }
    for (std::size_t j=0;j<H1;++j) {
        double sum=b1[j];
        for (std::size_t i=0;i<H0;++i) sum += a0[i]*w1[i*H1+j];
        a1[j]=std::max(0.0,sum);
    }
    for (std::size_t j=0;j<H2;++j) {
        double sum=b2[j];
        for (std::size_t i=0;i<H1;++i) sum += a1[i]*w2[i*H2+j];
        a2[j]=std::max(0.0,sum);
    }
    double out=b3;
    for (std::size_t i=0;i<H2;++i) out += a2[i]*w3[i];
    return out;
}

std::string sha256_file(const std::string& path, std::string* err) {
    try { return sha256(read_file(path)); }
    catch (const std::exception& e) { if (err) *err=e.what(); return {}; }
}

std::optional<Model> load_model(const std::string& path, LoadPolicy policy,
                                std::string* err) {
    try {
        const std::string raw=read_file(path);
        const std::string artifact_sha=sha256(raw);
        if (policy==LoadPolicy::FrozenOnly && artifact_sha!=FROZEN_MODEL_SHA256)
            throw std::runtime_error("T3/F6 artifact SHA256 mismatch");
        if (policy==LoadPolicy::ZeroProbeOnly && artifact_sha!=V4_ZERO_PROBE_SHA256)
            throw std::runtime_error("T3/F6 ZERO probe artifact SHA256 mismatch");
        const Json root=JsonParser(raw).parse();
        const auto& o=object(root,"root");
        require_string(o,"schema","jass.t3_rf1_joint_ab.v1","root");
        require_string(o,"arm","T3_F6_ONLY","root");
        require_string(o,"score_convention","higher_is_better_for_parent","root");
        require_string(o,"base","byte-identical T0 parent score, coefficient 1","root");
        require_string(o,"input_semantics","exact frozen F6_ALL_NEW packed order","root");
        require_integer(o,"input_width",INPUT_WIDTH,"root");
        const auto& names=array(member(o,"input_names","root"),"input_names");
        if (names.size()!=INPUT_WIDTH) throw std::runtime_error("input_names shape drift");
        for (std::size_t i=0;i<INPUT_WIDTH;++i) {
            std::ostringstream expected;
            expected << "F6_ALL_NEW_" << std::setw(2) << std::setfill('0') << i;
            if (string(names[i],"input_names")!=expected.str()) throw std::runtime_error("F6 input order drift");
        }
        const auto& arch=object(member(o,"architecture","root"),"architecture");
        const auto& hidden=array(member(arch,"hidden","architecture"),"hidden");
        if (hidden.size()!=3U || number(hidden[0],"hidden")!=256.0
            || number(hidden[1],"hidden")!=128.0 || number(hidden[2],"hidden")!=64.0
            || !boolean(member(arch,"relu_hidden","architecture"),"relu_hidden")
            || !boolean(member(arch,"linear_output","architecture"),"linear_output"))
            throw std::runtime_error("T3/F6 architecture drift");
        const auto& provenance=object(member(o,"provenance","root"),"provenance");
        require_string(provenance,"t0_sha256",FROZEN_CURRICULUM_SHA256,"provenance");
        require_string(provenance,"rf1_sha256",FROZEN_RF1_SHA256,"provenance");
        require_string(provenance,"d1_sha256",FROZEN_D1_SHA256,"provenance");
        const auto& norm=object(member(o,"normalization","root"),"normalization");
        Model model;
        model.mean=fixed_vector<INPUT_WIDTH>(member(norm,"mean","normalization"),"mean");
        model.stddev=fixed_vector<INPUT_WIDTH>(member(norm,"std","normalization"),"std");
        for (double v:model.stddev) if (!(v>0.0)) throw std::runtime_error("invalid normalization std");
        const auto& params=object(member(o,"params","root"),"params");
        model.w0=matrix(member(params,"W0","params"),INPUT_WIDTH,H0,"W0");
        model.b0=fixed_vector<H0>(member(params,"b0","params"),"b0");
        model.w1=matrix(member(params,"W1","params"),H0,H1,"W1");
        model.b1=fixed_vector<H1>(member(params,"b1","params"),"b1");
        model.w2=matrix(member(params,"W2","params"),H1,H2,"W2");
        model.b2=fixed_vector<H2>(member(params,"b2","params"),"b2");
        const auto w3=matrix(member(params,"W3","params"),H2,1U,"W3");
        std::copy(w3.begin(),w3.end(),model.w3.begin());
        model.b3=fixed_vector<1>(member(params,"b3","params"),"b3")[0];
        return model;
    } catch (const std::exception& e) {
        if (err) *err=e.what();
        return std::nullopt;
    }
}

Network::CacheKey Network::cache_key(const Position& pos) noexcept {
    return CacheKey{
        static_cast<std::uint64_t>(pos.white_men()),
        static_cast<std::uint64_t>(pos.white_kings()),
        static_cast<std::uint64_t>(pos.black_men()),
        static_cast<std::uint64_t>(pos.black_kings()),
        static_cast<std::uint8_t>(pos.side_to_move() == Color::White ? 0U : 1U),
    };
}

std::uint16_t Network::cache_index(const CacheKey& key) noexcept {
    std::uint64_t h = 14695981039346656037ULL;
    const auto mix_byte = [&h](std::uint8_t byte) noexcept {
        h ^= static_cast<std::uint64_t>(byte);
        h *= 1099511628211ULL;
    };
    const auto mix_u64_le = [&mix_byte](std::uint64_t value) noexcept {
        for (unsigned shift = 0; shift < 64U; shift += 8U) {
            mix_byte(static_cast<std::uint8_t>((value >> shift) & 0xffULL));
        }
    };
    mix_u64_le(key.white_men);
    mix_u64_le(key.white_kings);
    mix_u64_le(key.black_men);
    mix_u64_le(key.black_kings);
    mix_byte(key.side_to_move);
    return static_cast<std::uint16_t>(h & 0xffffULL);
}

std::uint16_t Network::cache_index(const Position& pos) noexcept {
    return cache_index(cache_key(pos));
}

void Network::clear_cache() const noexcept {
    if (!cache_enabled_) return;
    for (CacheEntry& entry : cache_) entry.valid = false;
    cache_stats_ = CacheStats{};
}

double Network::residual_parent(const Position& pos) const noexcept {
    try {
        if (!cache_enabled_) {
            return model_.residual_parent(residual_features::extract_f6(pos).all_new());
        }
        const CacheKey key = cache_key(pos);
        CacheEntry& entry = cache_[cache_index(key)];
        ++cache_stats_.lookups;
        if (entry.valid && entry.key == key) {
            ++cache_stats_.hits;
            return entry.residual;
        }
        ++cache_stats_.misses;
        if (entry.valid) ++cache_stats_.replacements;
        const double residual = model_.residual_parent(
            residual_features::extract_f6(pos).all_new());
        ++cache_stats_.extract_f6_executions;
        entry.valid = false;
        entry.key = key;
        entry.residual = residual;
        entry.valid = true;
        return residual;
    } catch (...) { std::terminate(); }
}
int Network::evaluate_from_base(const Position& pos, int base_score) const noexcept {
    return round_score(static_cast<double>(base_score)-residual_parent(pos));
}
int Network::evaluate(const Position& pos) const noexcept {
    if (!base_) std::terminate();
    return evaluate_from_base(pos,base_->evaluate(pos));
}

std::unique_ptr<INetwork> maybe_wrap_from_env(std::unique_ptr<INetwork> base,
                                             const std::string& base_path,
                                             std::string* err) {
    if (!base) return nullptr;
    bool cache_enabled = false;
    if (const char* cache_env = std::getenv("JASS_T3_F6_CACHE")) {
        const std::string_view value(cache_env);
        if (value == "1") cache_enabled = true;
        else if (value == "0") cache_enabled = false;
        else {
            if (err) *err = "JASS_T3_F6_CACHE must be exactly 0 or 1";
            return nullptr;
        }
    }
    const char* env=std::getenv("JASS_T3_F6_MODEL");
    if (env==nullptr) {
        if (cache_enabled) {
            if (err) *err="JASS_T3_F6_CACHE=1 requires JASS_T3_F6_MODEL";
            return nullptr;
        }
        return base;
    }
    if (*env=='\0') { if (err) *err="JASS_T3_F6_MODEL is present but empty"; return nullptr; }
    std::string hash_error;
    const std::string base_sha=sha256_file(base_path,&hash_error);
    if (base_sha.empty()) { if (err) *err=hash_error; return nullptr; }
    if (base_sha!=FROZEN_CURRICULUM_SHA256) {
        if (err) *err="CURRICULUM SHA256 mismatch in T3/F6 ON arm";
        return nullptr;
    }
    if (dynamic_cast<const scan_eval::ScanEvalNetwork*>(base.get())==nullptr) {
        if (err) *err="T3/F6 frozen base is not a ScanEvalNetwork";
        return nullptr;
    }
    auto model=load_model(env,LoadPolicy::FrozenOnly,err);
    if (!model) return nullptr;
    return std::make_unique<Network>(std::move(base),std::move(*model),cache_enabled);
}

}  // namespace jass::t3_f6
