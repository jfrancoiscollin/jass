cmake_minimum_required(VERSION 3.16)
project(jass_t3_f6_e2_match LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

get_filename_component(JASS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
# The engine's root CMakeLists predates subproject use and resolves its embedded
# NNUE input/template through CMAKE_SOURCE_DIR.  When this isolated harness is
# the top-level project, that variable would otherwise point here and configure
# would fail before any E2 code is built.  Scope the compatibility override to
# the add_subdirectory call; normal top-level Jass builds are unchanged.
set(E2_TOP_SOURCE_DIR "${CMAKE_SOURCE_DIR}")
set(CMAKE_SOURCE_DIR "${JASS_ROOT}")
add_subdirectory("${JASS_ROOT}" "${CMAKE_BINARY_DIR}/jass-root" EXCLUDE_FROM_ALL)
set(CMAKE_SOURCE_DIR "${E2_TOP_SOURCE_DIR}")

add_executable(t3_f6_e2_match
    "${CMAKE_CURRENT_LIST_DIR}/t3_f6_e2_match.cpp"
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_include_directories(t3_f6_e2_match PRIVATE
    "${JASS_ROOT}/src"
    "${JASS_ROOT}/jobs/tools")
target_link_libraries(t3_f6_e2_match PRIVATE jass_lib jass_warnings)
