cmake_minimum_required(VERSION 3.16)
project(jass_t3_f6_e2_match LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

get_filename_component(JASS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
# The engine root still resolves its embedded NNUE input/template through
# CMAKE_SOURCE_DIR.  CMake restores that special variable when entering an
# add_subdirectory(), so shadowing it in this top-level harness does not reach
# the engine subdirectory.  Materialize byte-identical compatibility copies at
# the isolated harness top source only for the duration of configure instead.
# They are removed immediately after the engine CMakeLists has consumed them;
# normal top-level Jass builds and all scientific/runtime parameters are
# unchanged.
set(E2_COMPAT_NNUE "${CMAKE_CURRENT_LIST_DIR}/nnue.bin")
set(E2_COMPAT_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}/cmake")
set(E2_COMPAT_NNUE_TEMPLATE "${E2_COMPAT_CMAKE_DIR}/nnue_default_data.cpp.in")
file(MAKE_DIRECTORY "${E2_COMPAT_CMAKE_DIR}")
configure_file("${JASS_ROOT}/nnue.bin" "${E2_COMPAT_NNUE}" COPYONLY)
configure_file("${JASS_ROOT}/cmake/nnue_default_data.cpp.in"
               "${E2_COMPAT_NNUE_TEMPLATE}" COPYONLY)
add_subdirectory("${JASS_ROOT}" "${CMAKE_BINARY_DIR}/jass-root" EXCLUDE_FROM_ALL)
file(REMOVE "${E2_COMPAT_NNUE}" "${E2_COMPAT_NNUE_TEMPLATE}")
file(REMOVE_RECURSE "${E2_COMPAT_CMAKE_DIR}")

add_executable(t3_f6_e2_match
    "${CMAKE_CURRENT_LIST_DIR}/t3_f6_e2_match.cpp"
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_include_directories(t3_f6_e2_match PRIVATE
    "${JASS_ROOT}/src"
    "${JASS_ROOT}/jobs/tools")
target_link_libraries(t3_f6_e2_match PRIVATE jass_lib jass_warnings)

# The engine's -march=native is a directory-scoped compile option inside the
# add_subdirectory() tree, so CMake does not propagate it back up to this
# top-level harness target.  Mirror the already-selected production-native flag
# on the harness translation unit only.  This changes no E2 cell, seed, pool,
# budget, search semantics, model, F6 feature, or O1 behavior; it merely makes
# the isolated executable obey the same CPX62 native-ISA build contract that
# the preregistered preflight audits in compile_commands.json.
if(JASS_NATIVE AND NOT EMSCRIPTEN AND NOT MSVC)
    target_compile_options(t3_f6_e2_match PRIVATE -march=native)
endif()
