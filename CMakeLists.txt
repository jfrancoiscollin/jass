cmake_minimum_required(VERSION 3.16)

project(jass
    VERSION   0.0.1
    LANGUAGES CXX
    DESCRIPTION "Just Another Scan System — international draughts engine"
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# Compile-database for tooling.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# -----------------------------------------------------------------------------
# Warnings
# -----------------------------------------------------------------------------
add_library(jass_warnings INTERFACE)
if(MSVC)
    target_compile_options(jass_warnings INTERFACE /W4 /permissive-)
else()
    target_compile_options(jass_warnings INTERFACE
        -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Wsign-conversion
        -Wnon-virtual-dtor -Wold-style-cast -Wcast-align -Wunused
        -Woverloaded-virtual -Wnull-dereference -Wdouble-promotion
        -Wformat=2)
endif()

# -----------------------------------------------------------------------------
# SIMD opt-in (AVX2 on native, WASM SIMD128 on Emscripten)
# -----------------------------------------------------------------------------
# Two architecture-specific code paths live in `MLPNetworkQ::evaluate`:
#   * `__AVX2__`           — Intel / AMD desktops since ~2013.
#   * `__wasm_simd128__`   — browsers since Chrome 91 / Firefox 89 / Safari 16.4.
# When neither macro is defined the scalar fallback runs (matches what
# CI would produce on a non-AVX2 host or a stock Emscripten build).
#
# Turn the whole thing off with `-DJASS_ENABLE_SIMD=OFF` to ship a
# portable binary that doesn't require any specific ISA feature.
option(JASS_ENABLE_SIMD "Enable architecture-specific SIMD intrinsics for the int8 NNUE forward pass" ON)
add_library(jass_simd INTERFACE)
if(JASS_ENABLE_SIMD)
    if(EMSCRIPTEN)
        target_compile_options(jass_simd INTERFACE -msimd128)
        message(STATUS "Jass: WASM SIMD128 enabled (-msimd128)")
    elseif(MSVC)
        target_compile_options(jass_simd INTERFACE /arch:AVX2)
        message(STATUS "Jass: AVX2 enabled (/arch:AVX2)")
    else()
        include(CheckCXXCompilerFlag)
        check_cxx_compiler_flag(-mavx2 JASS_COMPILER_SUPPORTS_AVX2)
        if(JASS_COMPILER_SUPPORTS_AVX2)
            target_compile_options(jass_simd INTERFACE -mavx2)
            message(STATUS "Jass: AVX2 enabled (-mavx2)")
        else()
            message(STATUS "Jass: compiler does not support -mavx2; scalar fallback only")
        endif()
    endif()
endif()

# -----------------------------------------------------------------------------
# Native-arch + LTO (engine speed). Standard engine build optimisations the
# project previously skipped. -march=native enables the host's full ISA (BMI2
# pext, etc.) — non-portable, so it is an option (turn OFF for distribution
# builds). LTO (link-time / interprocedural optimisation) is portable. PGO
# (profile-guided) is a separate two-pass job. Placed before the targets so the
# compile options apply to jass_lib / jass / jass_tests.
# -----------------------------------------------------------------------------
option(JASS_NATIVE "Build for the host CPU (-march=native: BMI2 etc.)" ON)
if(JASS_NATIVE AND NOT EMSCRIPTEN AND NOT MSVC)
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag(-march=native JASS_SUPPORTS_MARCH_NATIVE)
    if(JASS_SUPPORTS_MARCH_NATIVE)
        add_compile_options(-march=native)
        message(STATUS "Jass: -march=native enabled")
    endif()
endif()
if(NOT EMSCRIPTEN)
    include(CheckIPOSupported)
    check_ipo_supported(RESULT JASS_IPO_OK OUTPUT JASS_IPO_MSG)
    if(JASS_IPO_OK)
        set(CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE ON)
        message(STATUS "Jass: LTO enabled for Release")
    else()
        message(STATUS "Jass: LTO not supported (${JASS_IPO_MSG})")
    endif()
endif()

# -----------------------------------------------------------------------------
# Optional time-breakdown instrumentation
# -----------------------------------------------------------------------------
# When ON, wraps eval / movegen / pos.after calls with chrono samplers and
# emits a "BREAKDOWN ..." stderr line after every HUB bestmove. ~5-10%
# overhead. Off by default — used only for profiling jobs (e.g. 0093).
option(JASS_TIME_BREAKDOWN "Instrument the search with per-bucket chrono timers" OFF)
if(JASS_TIME_BREAKDOWN)
    add_compile_definitions(JASS_TIME_BREAKDOWN=1)
    message(STATUS "Jass: time-breakdown instrumentation ENABLED")
endif()

# King-aware patterns : a king counts as a "piece" on its square (base-3
# men|kings, Scan-style) instead of men-only. MUST be paired with a king-aware
# eval (train.py --king-patterns). See src/scan_eval.hpp.
option(JASS_KING_PATTERNS "Include kings in the pattern occupancy (men|kings, Scan-style)" OFF)
if(JASS_KING_PATTERNS)
    add_compile_definitions(JASS_KING_PATTERNS=1)
    message(STATUS "Jass: KING-AWARE patterns ENABLED (occupancy = men|kings)")
endif()

# DEFAULT ON since job 0311 (endgame king-interaction extras = best Elo arm,
# +87 vs base on hc; king-features help, per SCAN_EVAL_DIFF). NUM_EXTRAS 106->110.
# A pjtw must match the binary's NUM_EXTRAS (loader rejects a mismatch loudly) —
# retrain evals with this default. Flip OFF to reproduce the legacy 106-extras eval.
option(JASS_ENDGAME_FEATURES "Add endgame king-interaction extras (NUM_EXTRAS 106->110)" ON)
if(JASS_ENDGAME_FEATURES)
    add_compile_definitions(JASS_ENDGAME_FEATURES=1)
    message(STATUS "Jass: ENDGAME FEATURES ENABLED (NUM_EXTRAS=110)")
endif()

# King-mobility / confinement extras (Scan's king_mob) : separate king-slide
# mobility per side + trapped-king count = the structural conversion gradient.
# See src/scan_eval.hpp + docs/archives/SCAN_EVAL_DIFF.md (LEAD 1).
option(JASS_KING_MOBILITY "Add king-mobility/confinement extras (Scan king_mob, +4 extras)" OFF)
if(JASS_KING_MOBILITY)
    add_compile_definitions(JASS_KING_MOBILITY=1)
    message(STATUS "Jass: KING-MOBILITY extras ENABLED (+4 extras)")
endif()

# Scan-parity structural extras : absolute men-skew + king material split (+6 extras).
option(JASS_SCAN_PARITY "Add Scan-parity extras (abs skew + king material), +6 extras" OFF)
if(JASS_SCAN_PARITY)
    add_compile_definitions(JASS_SCAN_PARITY=1)
    message(STATUS "Jass: SCAN-PARITY extras ENABLED (+6 extras)")
endif()

# Tempo-based game stage (Scan's phase driver = men advancement, not piece count).
option(JASS_TEMPO_STAGE "Use Scan's tempo (men-advancement) phase blend instead of piece-count" OFF)
if(JASS_TEMPO_STAGE)
    add_compile_definitions(JASS_TEMPO_STAGE=1)
    message(STATUS "Jass: TEMPO-STAGE phase blend ENABLED (men advancement / 300)")
endif()

# Drawish-material draw-scaling (Scan's one non-linear eval term) : shrink the
# score toward a draw in unwinnable K-vs-few / near-equal endgames. Play-time
# only (not trained). See src/scan_eval.cpp + docs/archives/SCAN_EVAL_DIFF.md.
option(JASS_DRAWISH_SCALING "Scale eval toward draw in drawish material endgames (Scan)" OFF)
if(JASS_DRAWISH_SCALING)
    add_compile_definitions(JASS_DRAWISH_SCALING=1)
    message(STATUS "Jass: DRAWISH SCALING ENABLED")
endif()

# Diagnostic-only parity mode for loading an exact port of Scan's raw
# `data/eval` weights.  This does not change the learned PJTW format; it only
# makes the two remaining runtime details match Scan exactly:
#   * king safe/denied mobility is summed per king (overlaps count twice);
#   * score rounding and drawish scaling follow Scan's integer order.
# Pair with KING_MOBILITY, SCAN_PARITY, TEMPO_STAGE and DRAWISH_SCALING.
option(JASS_SCAN_EXACT_EVAL "Match Scan 3.1 runtime details for exact-eval diagnostics" OFF)
if(JASS_SCAN_EXACT_EVAL)
    add_compile_definitions(JASS_SCAN_EXACT_EVAL=1)
    message(STATUS "Jass: SCAN EXACT-EVAL diagnostic runtime ENABLED")
endif()

# Phase ramp endpoints (pieces) for the mg/eg blend. Empty = default 0/40 (=
# legacy pieces/40). A sharper ramp (e.g. 10/24) specialises the endgame bank
# (cf 0310 phase conflict). MUST match train.py --phase-lo/--phase-hi.
set(JASS_PHASE_LO "" CACHE STRING "phase ramp low (pieces); empty=default 0")
set(JASS_PHASE_HI "" CACHE STRING "phase ramp high (pieces); empty=default 40")
if(JASS_PHASE_LO)
    add_compile_definitions(JASS_PHASE_LO=${JASS_PHASE_LO})
    message(STATUS "Jass: phase ramp LO=${JASS_PHASE_LO}")
endif()
if(JASS_PHASE_HI)
    add_compile_definitions(JASS_PHASE_HI=${JASS_PHASE_HI})
    message(STATUS "Jass: phase ramp HI=${JASS_PHASE_HI}")
endif()

# External endgame database (Kingsrow egdb_intl). OFF → src/egdb_bridge.cpp
# compiles to no-op stubs and the engine has ZERO external dependency. ON →
# adapt Ed Gilbert's egdb_intl driver (https://github.com/eygilbert/egdb_intl)
# for full men+kings WLD lookups. Point CMake at a checkout of egdb_intl with
# -DJASS_EGDB_SRC_DIR=/path/to/egdb_intl and it is compiled from source into a
# static `egdb_intl` lib (no prebuilt lib needed; the build job clones the repo
# the same way the Scan jobs do). A prebuilt lib is still accepted via
# -DJASS_EGDB_LIB + -DJASS_EGDB_INCLUDE_DIR. The DB *data* files are downloaded
# separately on the host (edgilbert.org). See docs/archives/BITBASE_INTEGRATION.md.
option(JASS_EGDB "Link Kingsrow egdb_intl for full endgame WLD lookups" OFF)
if(JASS_EGDB)
    add_compile_definitions(JASS_EGDB=1)
    message(STATUS "Jass: EXTERNAL EGDB ENABLED (egdb_intl)")
    set(JASS_EGDB_SRC_DIR     "" CACHE PATH     "Path to an egdb_intl source checkout (built from source)")
    set(JASS_EGDB_INCLUDE_DIR "" CACHE PATH     "Path to egdb_intl headers (dir containing egdb/egdb_intl.h)")
    set(JASS_EGDB_LIB         "" CACHE FILEPATH "Path to a prebuilt egdb_intl library to link")
    if(JASS_EGDB_SRC_DIR)
        # Compile the driver's three source dirs into one static lib. Includes
        # are root-relative ("egdb/...", "engine/...") so the checkout root is
        # the include dir. USE_MULTI_THREADING makes egdb_lookup thread-safe for
        # the lazy-SMP search. Built without jass_warnings (3rd-party code).
        file(GLOB JASS_EGDB_SOURCES
            "${JASS_EGDB_SRC_DIR}/egdb/*.cpp"
            "${JASS_EGDB_SRC_DIR}/engine/*.cpp"
            "${JASS_EGDB_SRC_DIR}/builddb/*.cpp"
            "${JASS_EGDB_SRC_DIR}/Huffman/*.cpp"
            "${JASS_EGDB_SRC_DIR}/Re-pair/*.cpp")
        add_library(egdb_intl STATIC ${JASS_EGDB_SOURCES})
        target_include_directories(egdb_intl PUBLIC "${JASS_EGDB_SRC_DIR}")
        target_compile_definitions(egdb_intl PUBLIC USE_MULTI_THREADING)
        find_package(Threads REQUIRED)
        target_link_libraries(egdb_intl PUBLIC Threads::Threads)
    endif()
endif()

# -----------------------------------------------------------------------------
# Embedded NNUE weights
# -----------------------------------------------------------------------------
# `nnue.bin` at the repo root is the default LinearNetwork shipped with
# the engine (raw little-endian int32 layout). At configure time we read
# the file, format it as a comma-separated `0xHH` byte sequence and
# expand it into the auto-generated source `nnue_default_data.cpp`.
# That file defines `jass::NNUE_DEFAULT_BYTES[]` and `NNUE_DEFAULT_LEN`,
# which `default_nnue()` consumes via `LinearNetwork::load_from_bytes`.
set(NNUE_BIN_PATH "${CMAKE_SOURCE_DIR}/nnue.bin")
if(NOT EXISTS "${NNUE_BIN_PATH}")
    message(FATAL_ERROR
        "default NNUE weights not found at ${NNUE_BIN_PATH} — "
        "expected the raw 800-byte LinearNetwork file at the repo root")
endif()
file(READ "${NNUE_BIN_PATH}" NNUE_HEX HEX)
string(LENGTH "${NNUE_HEX}" NNUE_HEX_LEN)
math(EXPR NNUE_BYTE_COUNT "${NNUE_HEX_LEN} / 2")
string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," NNUE_BYTES "${NNUE_HEX}")
string(REGEX REPLACE ",$" "" NNUE_BYTES "${NNUE_BYTES}")

set(NNUE_DEFAULT_DATA_CPP "${CMAKE_BINARY_DIR}/generated/nnue_default_data.cpp")
configure_file(
    "${CMAKE_SOURCE_DIR}/cmake/nnue_default_data.cpp.in"
    "${NNUE_DEFAULT_DATA_CPP}"
    @ONLY
)

# -----------------------------------------------------------------------------
# Engine library
# -----------------------------------------------------------------------------
add_library(jass_lib STATIC
    src/board.cpp
    src/position.cpp
    src/movegen.cpp
    src/eval.cpp
    src/nnue.cpp
    src/nnue_accumulator.cpp
    src/nnue_server_client.cpp
    src/pattern_network.cpp
    src/pattern_jass_bridge.cpp
    src/scan_eval.cpp
    src/conversion_head.cpp
    src/scan_sacs.cpp
    pattern_jass/src/pattern.cpp
    pattern_jass/src/weights.cpp
    "${NNUE_DEFAULT_DATA_CPP}"
    src/search.cpp
    src/zobrist.cpp
    src/tt.cpp
    src/engine.cpp
    src/endgame.cpp
    src/bitbase.cpp
    src/egdb_bridge.cpp
    src/book.cpp
    src/scan_book.cpp
    src/timemgr.cpp
    src/tournament.cpp
    src/hub.cpp
)
# Keep the historical loader implementation but rename only that translation
# unit's public token. src/conversion_head.cpp exposes the wrapper symbol.
set_source_files_properties(src/scan_eval.cpp PROPERTIES
    COMPILE_DEFINITIONS "load_eval_network=load_eval_network_base")
target_include_directories(jass_lib PUBLIC src)
target_link_libraries(jass_lib PRIVATE jass_warnings jass_simd)

# Frozen T3/F6 runtime objects stay outside jass_lib.  The historical
# residual-feature contract deliberately compiles residual_features.cpp next
# to jass_lib; keeping these objects on the executable side preserves that
# independent reference build while making the production engine whole.
add_library(jass_t3_f6_runtime OBJECT
    src/residual_features.cpp
    src/t3_f6.cpp
)
target_include_directories(jass_t3_f6_runtime PUBLIC src)
target_link_libraries(jass_t3_f6_runtime PRIVATE jass_warnings)

# When the external endgame DB is enabled, wire its headers + library into the
# engine library that owns src/egdb_bridge.cpp.
if(JASS_EGDB)
    if(JASS_EGDB_SRC_DIR)
        # From-source path: jass_lib gets the egdb headers + the lib we built.
        target_include_directories(jass_lib PRIVATE "${JASS_EGDB_SRC_DIR}")
        target_link_libraries(jass_lib PRIVATE egdb_intl)
    elseif(JASS_EGDB_LIB)
        # Prebuilt-lib path.
        if(JASS_EGDB_INCLUDE_DIR)
            target_include_directories(jass_lib PRIVATE "${JASS_EGDB_INCLUDE_DIR}")
        endif()
        target_link_libraries(jass_lib PRIVATE "${JASS_EGDB_LIB}")
    else()
        message(WARNING "JASS_EGDB=ON but neither JASS_EGDB_SRC_DIR nor "
                        "JASS_EGDB_LIB is set — egdb_bridge will fail to link")
    endif()
endif()

# -----------------------------------------------------------------------------
# Front-end executable
# -----------------------------------------------------------------------------
# Native build: a smoke-test/CLI binary using src/main.cpp.
# Emscripten build: an ES-module exposing the engine to JavaScript via Embind
# (src/wasm_api.cpp). The two entry points are mutually exclusive.
if(EMSCRIPTEN)
    add_executable(jass src/wasm_api.cpp $<TARGET_OBJECTS:jass_t3_f6_runtime>)
else()
    add_executable(jass src/main.cpp $<TARGET_OBJECTS:jass_t3_f6_runtime>)
endif()
target_link_libraries(jass PRIVATE jass_lib jass_warnings)

# Native benchmark-only tools for the preregistered L3 Scan ceiling campaign.
# They share the production engine library but expose no fit, tuning, game,
# bake, or promotion path and are not part of the browser/WASM artefact.
if(NOT EMSCRIPTEN)
    add_executable(jass_scan_ceiling_parent_filter
        src/deep_sibling_parent_filter.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(jass_scan_ceiling_parent_filter PRIVATE jass_lib jass_warnings)

    add_executable(jass_scan_ceiling_source_generator
        src/scan_ceiling_source_generator.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(jass_scan_ceiling_source_generator PRIVATE jass_lib jass_warnings)

    add_executable(jass_scan_ceiling_sibling_export
        src/scan_ceiling_sibling_export.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(jass_scan_ceiling_sibling_export PRIVATE jass_lib jass_warnings)

    add_executable(jass_scan_ceiling_jass_ladder
        src/scan_ceiling_jass_ladder.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(jass_scan_ceiling_jass_ladder PRIVATE jass_lib jass_warnings)

    # HOME-only Attribution V1 scorer. It links the frozen attribution search
    # under isolated symbols while production jass_lib continues to own the
    # current develop/V4 search unchanged.
    add_executable(jass_search_semantics_attribution
        src/search_semantics_attribution_entry.cpp
        src/search_semantics_alt.cpp
        $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(jass_search_semantics_attribution PRIVATE jass_lib jass_warnings)
endif()

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
enable_testing()
add_executable(jass_tests
    $<TARGET_OBJECTS:jass_t3_f6_runtime>
    tests/test_main.cpp
    tests/test_position.cpp
    tests/test_movegen.cpp
    tests/test_search.cpp
    tests/test_tt.cpp
    tests/test_engine.cpp
    tests/test_draws.cpp
    tests/test_endgame.cpp
    tests/test_book.cpp
    tests/test_scan_book.cpp
    tests/test_tournament.cpp
    tests/test_nnue.cpp
    tests/test_hub.cpp
    tests/test_scan_eval.cpp
    tests/test_conversion_head.cpp
    tests/test_t3_f6.cpp
)
target_link_libraries(jass_tests PRIVATE jass_lib jass_warnings)
target_include_directories(jass_tests PRIVATE tests)
add_test(NAME jass_tests COMMAND jass_tests)
add_test(
    NAME node_budget_selfplay_smoke
    COMMAND ${CMAKE_COMMAND}
        -DJASS_EXE=$<TARGET_FILE:jass>
        -DSMOKE_DIR=${CMAKE_CURRENT_BINARY_DIR}/node-budget-smoke
        -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/node_budget_selfplay_smoke.cmake
)

if(NOT EMSCRIPTEN)
    add_executable(t3_f6_runtime_probe jobs/tools/t3_f6_runtime_probe.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_runtime_probe PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_invariance_probe jobs/tools/t3_f6_invariance_probe.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_invariance_probe PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_relative_probe jobs/tools/t3_f6_relative_probe.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_relative_probe PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_negamax_autopsy jobs/tools/t3_f6_negamax_autopsy.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_negamax_autopsy PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_leaf_contract_v3 jobs/tools/t3_f6_leaf_contract_v3.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_leaf_contract_v3 PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_runtime_contract_v4 jobs/tools/t3_f6_runtime_contract_v4.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_runtime_contract_v4 PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_exact_cache_o1_contract jobs/tools/t3_f6_exact_cache_o1_contract.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_exact_cache_o1_contract PRIVATE jass_lib jass_warnings)
    add_executable(t3_f6_exact_cache_o1_profile jobs/tools/t3_f6_exact_cache_o1_profile.cpp
                   $<TARGET_OBJECTS:jass_t3_f6_runtime>)
    target_link_libraries(t3_f6_exact_cache_o1_profile PRIVATE jass_lib jass_warnings)
    add_test(NAME t3_f6_transposition_selftest
             COMMAND t3_f6_invariance_probe --transposition-selftest)
    add_test(NAME t3_f6_relative_transposition_selftest
             COMMAND t3_f6_relative_probe --transposition-selftest)
    add_test(NAME t3_f6_negamax_autopsy_selftest
             COMMAND t3_f6_negamax_autopsy --selftest)
    add_test(NAME t3_f6_leaf_contract_v3_selftest
             COMMAND t3_f6_leaf_contract_v3 --selftest)
    add_test(NAME t3_f6_runtime_contract_v4_selftest
             COMMAND t3_f6_runtime_contract_v4 --selftest)
    add_test(NAME t3_f6_exact_cache_o1_contract_selftest
             COMMAND t3_f6_exact_cache_o1_contract --selftest)
    add_test(NAME t3_f6_exact_cache_o1_profile_selftest
             COMMAND t3_f6_exact_cache_o1_profile --selftest)
endif()

# -----------------------------------------------------------------------------
# Emscripten / WASM specifics
# -----------------------------------------------------------------------------
if(EMSCRIPTEN)
    # Produce jass.js + jass.wasm as an ES6 module.
    set_target_properties(jass PROPERTIES
        OUTPUT_NAME "jass"
        SUFFIX      ".js"
    )
    target_compile_options(jass PRIVATE -O3)
    target_link_options(jass PRIVATE
        "-O3"
        "-lembind"
        "-sMODULARIZE=1"
        "-sEXPORT_ES6=1"
        "-sENVIRONMENT=web,worker"
        "-sALLOW_MEMORY_GROWTH=1"
        "-sEXPORT_NAME=createJass"
        "-sFILESYSTEM=0"
        "-sASSERTIONS=0"
    )
endif()
