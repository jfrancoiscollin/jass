// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tiny self-contained test scaffolding shared by the per-topic test files.
// Globals are defined once in `test_main.cpp`.

#pragma once

#include <cstdio>

extern int g_failures;
extern int g_assertions;

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
