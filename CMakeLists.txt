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
# Engine library
# -----------------------------------------------------------------------------
add_library(jass_lib STATIC
    src/board.cpp
    src/position.cpp
    src/movegen.cpp
    src/eval.cpp
    src/search.cpp
    src/zobrist.cpp
    src/tt.cpp
    src/engine.cpp
    src/endgame.cpp
    src/bitbase.cpp
    src/book.cpp
    src/timemgr.cpp
    src/hub.cpp
)
target_include_directories(jass_lib PUBLIC src)
target_link_libraries(jass_lib PRIVATE jass_warnings)

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
    tests/test_hub.cpp
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
