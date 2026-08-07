cmake_minimum_required(VERSION 3.24)

project(mini_jass VERSION 0.1.0 LANGUAGES CXX)

option(MINI_JASS_BUILD_TESTS "Build the standalone Mini-Jass tests" ON)
set(MINI_JASS_PYTHON_EXECUTABLE "" CACHE FILEPATH
    "Optional Python with Mini-Jass M3 dependencies for pytest")

add_library(mini_jass_core STATIC
    src/enumerate.cpp
    src/game.cpp
    src/l2_game.cpp
    src/l2_move.cpp
    src/l2_movegen.cpp
    src/l2_reference_movegen.cpp
    src/l2_rules.cpp
    src/l2_solver.cpp
    src/move.cpp
    src/movegen.cpp
    src/reference_movegen.cpp
    src/rules.cpp
    src/solver.cpp
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

    add_executable(mini_jass_solver_tests
        tests/test_solver.cpp
    )
    target_link_libraries(mini_jass_solver_tests PRIVATE mini_jass_core)

    add_executable(mini_jass_l2_tests
        tests/test_l2.cpp
    )
    target_link_libraries(mini_jass_l2_tests PRIVATE mini_jass_core)

    if(MSVC)
        target_compile_options(mini_jass_rules_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_movegen_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_enumerate_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_solver_tests PRIVATE /W4 /permissive-)
        target_compile_options(mini_jass_l2_tests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(mini_jass_rules_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_movegen_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_enumerate_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_solver_tests PRIVATE -Wall -Wextra -Wpedantic)
        target_compile_options(mini_jass_l2_tests PRIVATE -Wall -Wextra -Wpedantic)
    endif()

    add_test(NAME mini_jass_rules COMMAND mini_jass_rules_tests)
    add_test(NAME mini_jass_movegen COMMAND mini_jass_movegen_tests)
    add_test(NAME mini_jass_enumerate COMMAND mini_jass_enumerate_tests)
    add_test(
        NAME mini_jass_solver
        COMMAND mini_jass_solver_tests
            ${CMAKE_CURRENT_SOURCE_DIR}/artefacts/solver_manifest.v1.json
    )
    add_test(NAME mini_jass_l2 COMMAND mini_jass_l2_tests)
    add_test(
        NAME mini_jass_isolation
        COMMAND ${CMAKE_COMMAND}
            -DMINI_JASS_SOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}
            -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/verify_isolation.cmake
    )
    if(MINI_JASS_PYTHON_EXECUTABLE)
        add_test(
            NAME mini_jass_python
            COMMAND ${MINI_JASS_PYTHON_EXECUTABLE} -m pytest
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/python
        )
        set_tests_properties(mini_jass_python PROPERTIES
            ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/python"
        )
    endif()
endif()
