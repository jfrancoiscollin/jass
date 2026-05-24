// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "nnue_server_client.hpp"

#include <cerrno>
#include <cstring>
#include <iostream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace jass {

NetworkServerClient::NetworkServerClient() = default;

NetworkServerClient::~NetworkServerClient() {
    if (fd_ >= 0) ::close(fd_);
}

bool NetworkServerClient::connect(std::string_view path) {
    path_.assign(path);

    fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd_ < 0) {
        std::cerr << "NetworkServerClient: socket() failed: "
                  << std::strerror(errno) << "\n";
        return false;
    }
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    if (path.size() >= sizeof(addr.sun_path)) {
        std::cerr << "NetworkServerClient: socket path too long\n";
        ::close(fd_);
        fd_ = -1;
        return false;
    }
    std::memcpy(addr.sun_path, path.data(), path.size());
    if (::connect(fd_, reinterpret_cast<sockaddr*>(&addr),
                  static_cast<socklen_t>(sizeof(addr))) < 0) {
        std::cerr << "NetworkServerClient: connect(" << path_ << ") failed: "
                  << std::strerror(errno) << "\n";
        ::close(fd_);
        fd_ = -1;
        return false;
    }
    return true;
}

int NetworkServerClient::evaluate(const Position& pos) const noexcept {
    if (fd_ < 0) return 0;

    // Pack request: 4 × uint64 bitboards + 1 byte STM = 33 bytes.
    unsigned char req[33];
    const std::uint64_t bbs[4] = {
        pos.white_men(), pos.white_kings(),
        pos.black_men(), pos.black_kings(),
    };
    std::memcpy(req, bbs, 32);
    req[32] = (pos.side_to_move() == Color::White) ? 0 : 1;

    // Send. Handle partial writes (TCP semantics — single byte at most
    // unlikely on a local Unix socket, but the kernel doesn't guarantee
    // atomic full writes).
    std::size_t sent = 0;
    while (sent < sizeof(req)) {
        const ssize_t n = ::send(fd_, req + sent, sizeof(req) - sent, 0);
        if (n <= 0) return 0;
        sent += static_cast<std::size_t>(n);
    }

    // Receive 4 bytes (int32 score).
    unsigned char resp[4];
    std::size_t got = 0;
    while (got < sizeof(resp)) {
        const ssize_t n = ::recv(fd_, resp + got, sizeof(resp) - got, 0);
        if (n <= 0) return 0;
        got += static_cast<std::size_t>(n);
    }
    std::int32_t score;
    std::memcpy(&score, resp, sizeof(score));
    return static_cast<int>(score);
}

}  // namespace jass
