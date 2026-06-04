# Standalone build for the Othello Phase Pattern-1 POC.
# Deliberately NOT linked to the jass core build : isolation matters
# (cf. othello/README.md §5).

cmake_minimum_required(VERSION 3.16)
project(othello LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_library(othello_core STATIC
    src/board.cpp
    src/movegen.cpp
    src/pattern.cpp
    src/eval.cpp
    src/search.cpp
)
target_include_directories(othello_core PUBLIC src)
target_compile_options(othello_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(othello_cli src/main.cpp)
target_link_libraries(othello_cli PRIVATE othello_core)

add_executable(othello_bench_random src/bench_random.cpp)
target_link_libraries(othello_bench_random PRIVATE othello_core)

add_executable(othello_gen_data src/gen_data.cpp)
target_link_libraries(othello_gen_data PRIVATE othello_core)

enable_testing()
add_executable(othello_tests tests/run_tests.cpp)
target_link_libraries(othello_tests PRIVATE othello_core)
add_test(NAME othello_tests COMMAND othello_tests)
