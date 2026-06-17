// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tiny self-contained test scaffolding shared by the per-topic test files.
// Globals are defined once in `test_main.cpp`.

#pragma once

#include <cstdio>
#include <cstdlib>
#include <string>
#include <unistd.h>

extern int g_failures;
extern int g_assertions;

// Build an mkstemp template under $TMPDIR (falling back to /tmp). The CI
// runner has a tiny /tmp — jobs export TMPDIR to a roomy disk path, so any
// test that writes temp files MUST honour it or mkstemp fails (and a cascade
// of file-backed tests segfault). `name` is a short, descriptive stem.
//
// If TMPDIR is set but the directory is not writable (e.g. a job forgot to
// `mkdir -p` it), fall back to /tmp rather than handing back a template
// mkstemp can't create — a missing temp dir shouldn't crash the suite.
inline std::string jass_tmp_template(const char* name) {
    const char* td = std::getenv("TMPDIR");
    std::string dir = (td != nullptr && td[0] != '\0') ? std::string(td)
                                                        : std::string("/tmp");
    if (!dir.empty() && dir.back() == '/') dir.pop_back();
    if (::access(dir.c_str(), W_OK) != 0) dir = "/tmp";
    return dir + "/" + name + "_XXXXXX";
}

#define JASS_CHECK(cond)                                                       \
    do {                                                                       \
        ++g_assertions;                                                        \
        if (!(cond)) {                                                         \
            ++g_failures;                                                      \
            std::fprintf(stderr, "[FAIL] %s:%d: %s\n",                         \
                         __FILE__, __LINE__, #cond);                           \
        }                                                                      \
    } while (0)

#define JASS_CHECK_EQ(a, b)                                                    \
    do {                                                                       \
        ++g_assertions;                                                        \
        const auto _va = (a);                                                  \
        const auto _vb = (b);                                                  \
        if (!(_va == _vb)) {                                                   \
            ++g_failures;                                                      \
            std::fprintf(stderr,                                               \
                         "[FAIL] %s:%d: expected %s == %s\n",                  \
                         __FILE__, __LINE__, #a, #b);                          \
        }                                                                      \
    } while (0)

void run_position_tests();
void run_movegen_tests();
void run_search_tests();
void run_tt_tests();
void run_engine_tests();
void run_draw_tests();
void run_endgame_tests();
void run_book_tests();
void run_scan_book_tests();
void run_tournament_tests();
void run_nnue_tests();
void run_hub_tests();
void run_scan_eval_tests();
