cmake_minimum_required(VERSION 3.16)
project(jass_pl8_boundary_a LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

get_filename_component(JASS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

set(JASS_ENDGAME_FEATURES ON CACHE BOOL "" FORCE)
set(JASS_KING_MOBILITY ON CACHE BOOL "" FORCE)
set(JASS_SCAN_PARITY ON CACHE BOOL "" FORCE)
set(JASS_TEMPO_STAGE ON CACHE BOOL "" FORCE)
set(JASS_KING_PATTERNS OFF CACHE BOOL "" FORCE)
set(JASS_DRAWISH_SCALING OFF CACHE BOOL "" FORCE)
set(JASS_NATIVE ON CACHE BOOL "" FORCE)
set(JASS_ENABLE_SIMD ON CACHE BOOL "" FORCE)

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

add_library(pl8_exact_arch INTERFACE)
target_compile_definitions(pl8_exact_arch INTERFACE
    JASS_ENDGAME_FEATURES=1
    JASS_KING_MOBILITY=1
    JASS_SCAN_PARITY=1
    JASS_TEMPO_STAGE=1)

add_library(pl8_runtime STATIC
    "${JASS_ROOT}/src/pl8.cpp"
    "${JASS_ROOT}/src/pl8_sha256.cpp")
target_include_directories(pl8_runtime PUBLIC "${JASS_ROOT}/src")
target_link_libraries(pl8_runtime PRIVATE jass_lib jass_warnings pl8_exact_arch)
if(JASS_NATIVE AND NOT EMSCRIPTEN AND NOT MSVC)
    target_compile_options(pl8_runtime PRIVATE -march=native)
endif()

function(pl8_tool name source)
    add_executable(${name} "${CMAKE_CURRENT_LIST_DIR}/${source}")
    target_include_directories(${name} PRIVATE "${JASS_ROOT}/src" "${CMAKE_CURRENT_LIST_DIR}")
    target_link_libraries(${name} PRIVATE pl8_runtime jass_lib jass_warnings pl8_exact_arch)
    if(JASS_NATIVE AND NOT EMSCRIPTEN AND NOT MSVC)
        target_compile_options(${name} PRIVATE -march=native)
    endif()
endfunction()

pl8_tool(pl8_contract_test pl8_contract_test.cpp)
pl8_tool(pl8_feature_export pl8_feature_export.cpp)
pl8_tool(pl8_runtime_probe pl8_runtime_probe.cpp)
pl8_tool(pl8_anchor pl8_anchor.cpp)
pl8_tool(pl8_scalar_score pl8_scalar_score.cpp)
# src/search.cpp has compile-time references to the repository's already-existing
# T3/F6 runtime class even when the active INetwork is PL8. Production jass and
# jass_tests satisfy those references with this same object target. Link those
# dormant support objects into the technical search probe only; PL8 itself has
# no dependency on or activation path to F6/D/D1/Rich-D/micro-search.
target_sources(pl8_runtime_probe PRIVATE $<TARGET_OBJECTS:jass_t3_f6_runtime>)

enable_testing()
add_test(NAME pl8_contract_test COMMAND pl8_contract_test)
