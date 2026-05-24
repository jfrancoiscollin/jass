// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Network-backed `INetwork`: forwards each `evaluate(pos)` call to a
// Unix-domain socket server (typically `tools/nnue_eval_server.py`).
// Used to evaluate jass's leaves on a remote GPU (Phase 1) — Phase 0
// uses a stub server to measure pure IPC overhead.
//
// Wire format (little-endian):
//   request:  4 × uint64 bitboards (white_men, white_kings, black_men,
//             black_kings) + 1 byte STM (0 = white, 1 = black).
//   response: int32 score (centipawn, STM POV).

#pragma once

#include "nnue.hpp"
#include "position.hpp"

#include <string>
#include <string_view>

namespace jass {

class NetworkServerClient : public INetwork {
public:
    NetworkServerClient();
    ~NetworkServerClient() override;

    // Connect to the Unix socket at `path`. Returns true on success.
    // On failure the client falls into a "disabled" state in which
    // `evaluate()` returns 0 — callers should check the return value.
    bool connect(std::string_view path);

    // Read-modify-write a request/response with the server. NOT
    // thread-safe — caller must serialize access (the search uses one
    // Searcher per thread, each with its own NNUE pointer so this is
    // fine in practice).
    int evaluate(const Position& pos) const noexcept override;

    bool is_connected() const noexcept { return fd_ >= 0; }

private:
    // mutable because evaluate() is const but we touch the fd cache.
    mutable int         fd_{-1};
    std::string         path_;
};

}  // namespace jass
