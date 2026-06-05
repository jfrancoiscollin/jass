# Standalone build for the pattern_jass Phase Pattern-2 POC.
# Deliberately NOT linked to the jass core build (cf README §Structure).

cmake_minimum_required(VERSION 3.16)
project(pattern_jass LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_library(pattern_jass_core STATIC
    src/pattern.cpp
    src/weights.cpp
)
target_include_directories(pattern_jass_core PUBLIC src)
target_compile_options(pattern_jass_core PRIVATE -Wall -Wextra -Wpedantic)

enable_testing()
add_executable(pattern_jass_tests tests/run_tests.cpp)
target_link_libraries(pattern_jass_tests PRIVATE pattern_jass_core)
add_test(NAME pattern_jass_tests COMMAND pattern_jass_tests)
