cmake_minimum_required(VERSION 3.16)
project(jass_search_semantics_technical_preflight LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build the pinned repository as a subproject, then add one HOME-only technical
# executable without modifying the production root target graph.
get_filename_component(JASS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
add_subdirectory("${JASS_ROOT}" "${CMAKE_BINARY_DIR}/jass-subbuild")

add_executable(jass_search_semantics_preflight
    "${JASS_ROOT}/src/search_semantics_preflight.cpp"
    "${JASS_ROOT}/src/search_semantics_alt.cpp"
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_link_libraries(jass_search_semantics_preflight PRIVATE jass_lib jass_warnings)
