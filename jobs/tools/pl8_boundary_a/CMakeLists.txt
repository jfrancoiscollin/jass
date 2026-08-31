cmake_minimum_required(VERSION 3.16)
project(jass_pl8_boundary_a LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

get_filename_component(JASS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

# Boundary A is defined only for the frozen 8cf/120-extra/tempo production
# architecture. Force those already-existing engine switches before importing
# the project. No search/movegen/qsearch/TT parameter is changed here.
set(JASS_ENDGAME_FEATURES ON CACHE BOOL "" FORCE)
set(JASS_KING_MOBILITY ON CACHE BOOL "" FORCE)
set(JASS_SCAN_PARITY ON CACHE BOOL "" FORCE)
set(JASS_TEMPO_STAGE ON CACHE BOOL "" FORCE)
set(JASS_KING_PATTERNS OFF CACHE BOOL "" FORCE)
set(JASS_DRAWISH_SCALING OFF CACHE BOOL "" FORCE)
set(JASS_NATIVE ON CACHE BOOL "" FORCE)
set(JASS_ENABLE_SIMD ON CACHE BOOL "" FORCE)

# Root CMake resolves embedded NNUE support through CMAKE_SOURCE_DIR. As with
# the E2 isolated harness, materialize byte-identical configure-time copies in
# this top-level source and delete them immediately after add_subdirectory().
set(PL8_COMPAT_NNUE "${CMAKE_CURRENT_LIST_DIR}/nnue.bin")
set(PL8_COMPAT_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}/cmake")
set(PL8_COMPAT_NNUE_TEMPLATE "${PL8_COMPAT_CMAKE_DIR}/nnue_default_data.cpp.in")
file(MAKE_DIRECTORY "${PL8_COMPAT_CMAKE_DIR}")
configure_file("${JASS_ROOT}/nnue.bin" "${PL8_COMPAT_NNUE}" COPYONLY)
configure_file("${JASS_ROOT}/cmake/nnue_default_data.cpp.in"
               "${PL8_COMPAT_NNUE_TEMPLATE}" COPYONLY)
add_subdirectory("${JASS_ROOT}" "${CMAKE_BINARY_DIR}/jass-root" EXCLUDE_FROM_ALL)
file(REMOVE "${PL8_COMPAT_NNUE}" "${PL8_COMPAT_NNUE_TEMPLATE}")
file(REMOVE_RECURSE "${PL8_COMPAT_CMAKE_DIR}")

add_library(pl8_runtime STATIC "${JASS_ROOT}/src/pl8.cpp")
target_include_directories(pl8_runtime PUBLIC "${JASS_ROOT}/src")
target_link_libraries(pl8_runtime PRIVATE jass_lib jass_warnings)

function(pl8_tool name source)
    add_executable(${name} "${CMAKE_CURRENT_LIST_DIR}/${source}")
    target_include_directories(${name} PRIVATE "${JASS_ROOT}/src")
    target_link_libraries(${name} PRIVATE pl8_runtime jass_lib jass_warnings)
    # Engine -march=native is directory-scoped under add_subdirectory(); mirror
    # the same already-selected native contract onto harness translation units.
    if(JASS_NATIVE AND NOT EMSCRIPTEN AND NOT MSVC)
        target_compile_options(${name} PRIVATE -march=native)
    endif()
endfunction()

pl8_tool(pl8_contract_test pl8_contract_test.cpp)
pl8_tool(pl8_feature_export pl8_feature_export.cpp)
pl8_tool(pl8_runtime_probe pl8_runtime_probe.cpp)

enable_testing()
add_test(NAME pl8_contract_test COMMAND pl8_contract_test)
