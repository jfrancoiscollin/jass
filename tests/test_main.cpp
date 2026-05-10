// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "test_framework.hpp"

#include <cstdio>

int g_failures   = 0;
int g_assertions = 0;

int main() {
    run_position_tests();
    run_movegen_tests();
    run_search_tests();
    run_tt_tests();

    if (g_failures == 0) {
        std::printf("All %d assertions passed.\n", g_assertions);
        return 0;
    }
    std::fprintf(stderr, "%d / %d assertions FAILED.\n",
                 g_failures, g_assertions);
    return 1;
}
