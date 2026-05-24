#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Minimal NNUE-eval-server STUB (Phase 0 — measures IPC overhead only,
NOT a real forward pass).

Architecture:
  * Unix socket bound to `--socket PATH`.
  * Each request: 33 bytes (32-byte bitboard quadruple + 1-byte STM).
  * Each response: 4 bytes (int32 score, little-endian).

This stub returns a deterministic constant (the side-to-move byte cast
to int32). The point is to measure round-trip latency and throughput
from the C++ client. If raw IPC is fast enough (~40K evals/sec needed
per CPU worker to saturate a depth-20 search), we can layer a real
PyTorch forward pass on top in Phase 1. If IPC is the bottleneck, we
need to swap the socket for shared memory.
"""
from __future__ import annotations

import argparse
import os
import socket
import struct
import sys


REQ_SIZE = 33
RESP_SIZE = 4


def serve(sock_path: str) -> None:
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(8)
    print(f"nnue_eval_server: listening on {sock_path}", flush=True)

    while True:
        conn, _ = srv.accept()
        # One client per connection. Loop reading requests and
        # responding until the client closes.
        try:
            buf = b""
            with conn:
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while len(buf) >= REQ_SIZE:
                        req = buf[:REQ_SIZE]
                        buf = buf[REQ_SIZE:]
                        stm = req[32]
                        # Stub: return stm as int32 score so we can
                        # sanity-check the C++ client parses correctly.
                        resp = struct.pack("<i", int(stm))
                        conn.sendall(resp)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True,
                   help="Path to the Unix socket")
    args = p.parse_args()
    serve(args.socket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
