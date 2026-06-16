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

option(JASS_ENDGAME_FEATURES "Add endgame king-interaction extras (NUM_EXTRAS 106->110)" OFF)
if(JASS_ENDGAME_FEATURES)
    add_compile_definitions(JASS_ENDGAME_FEATURES=1)
    message(STATUS "Jass: ENDGAME FEATURES ENABLED (NUM_EXTRAS=110)")
endif()

# External endgame database (Kingsrow egdb_intl). OFF → src/egdb_bridge.cpp
# compiles to no-op stubs and the engine has ZERO external dependency. ON →
# adapt Ed Gilbert's egdb_intl driver (https://github.com/eygilbert/egdb_intl)
# for full men+kings WLD lookups. Point CMake at a checkout of egdb_intl with
# -DJASS_EGDB_SRC_DIR=/path/to/egdb_intl and it is compiled from source into a
# static `egdb_intl` lib (no prebuilt lib needed; the build job clones the repo
# the same way the Scan jobs do). A prebuilt lib is still accepted via
# -DJASS_EGDB_LIB + -DJASS_EGDB_INCLUDE_DIR. The DB *data* files are downloaded
# separately on the host (edgilbert.org). See docs/BITBASE_INTEGRATION.md.
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
    src/timemgr.cpp
    src/tournament.cpp
    src/hub.cpp
)
target_include_directories(jass_lib PUBLIC src)
target_link_libraries(jass_lib PRIVATE jass_warnings jass_simd)

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
    add_executable(jass src/wasm_api.cpp)
else()
    add_executable(jass src/main.cpp)
endif()
target_link_libraries(jass PRIVATE jass_lib jass_warnings)

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
enable_testing()
add_executable(jass_tests
    tests/test_main.cpp
    tests/test_position.cpp
    tests/test_movegen.cpp
    tests/test_search.cpp
    tests/test_tt.cpp
    tests/test_engine.cpp
    tests/test_draws.cpp
    tests/test_endgame.cpp
    tests/test_book.cpp
    tests/test_tournament.cpp
    tests/test_nnue.cpp
    tests/test_hub.cpp
    tests/test_scan_eval.cpp
)
target_link_libraries(jass_tests PRIVATE jass_lib jass_warnings)
target_include_directories(jass_tests PRIVATE tests)
add_test(NAME jass_tests COMMAND jass_tests)

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
