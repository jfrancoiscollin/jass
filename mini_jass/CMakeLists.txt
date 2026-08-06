cmake_minimum_required(VERSION 3.24)

project(mini_jass VERSION 0.1.0 LANGUAGES CXX)

option(MINI_JASS_BUILD_TESTS "Build the standalone Mini-Jass tests" ON)

add_library(mini_jass_core STATIC
    src/enumerate.cpp
    src/game.cpp
    src/move.cpp
    src/movegen.cpp
    src/reference_movegen.cpp
    src/rules.cpp
)

target_include_directories(mini_jass_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(mini_jass_core PUBLIC cxx_std_20)

add_executable(mini_jass_cli
    src/main.cpp
)

target_link_libraries(mini_jass_cli PRIVATE mini_jass_core)

if(MSVC)
    target_compile_options(mini_jass_core PRIVATE /W4 /permissive-)
    target_compile_options(mini_jass_cli PRIVATE /W4 /permissive-)
else()
    target_compile_options(mini_jass_core PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(mini_jass_cli PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(MINI_JASS_BUILD_TESTS)
    enable_testing()

    add_executable(mini_jass_rules_tests
        tests/test_rules.cpp
    )
    target_link_libraries(mini_jass_rules_tests PRIVATE mini_jass_core)

    add_executable(mini_jass_movegen_tests
        tests/test_movegen.cpp
    )
    target_link_libraries(mini_jass_movegen_tests PRIVATE mini_jass_core)

    add_executable(mini_jass_enumerate_tests
        tests/test_enumerate.cpp
    )
    target_link_libraries(mini_jass_enumerate_tests PRIVATE mini_jass_core)

    if(MSVC)
        target_compile_options(mini_jass_rules_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_movegen_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_enumerate_tests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(mini_jass_rules_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_movegen_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_enumerate_tests PRIVATE -Wall -Wextra -Wpedantic)
    endif()

    add_test(NAME mini_jass_rules COMMAND mini_jass_rules_tests)
    add_test(NAME mini_jass_movegen COMMAND mini_jass_movegen_tests)
    add_test(NAME mini_jass_enumerate COMMAND mini_jass_enumerate_tests)
    add_test(
        NAME mini_jass_isolation
        COMMAND ${CMAKE_COMMAND}
            -DMINI_JASS_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}
            -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/verify_isolation.cmake
    )
endif()
