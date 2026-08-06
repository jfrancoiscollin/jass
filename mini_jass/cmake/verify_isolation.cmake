cmake_minimum_required(VERSION 3.24)

if(NOT DEFINED MINI_JASS_SOURCE_DIR)
    message(FATAL_ERROR "MINI_JASS_SOURCE_DIR is required")
endif()

get_filename_component(MINI_JASS_SOURCE_DIR "${MINI_JASS_SOURCE_DIR}" ABSOLUTE)
get_filename_component(REPOSITORY_ROOT "${MINI_JASS_SOURCE_DIR}/.." ABSOLUTE)

set(repository_root_for_git "${REPOSITORY_ROOT}")
set(worktree_git_file "${REPOSITORY_ROOT}/.git")
set(use_windows_git_from_wsl FALSE)

if(NOT WIN32 AND EXISTS "${worktree_git_file}" AND NOT IS_DIRECTORY "${worktree_git_file}")
    file(READ "${worktree_git_file}" worktree_git_contents)
    if(worktree_git_contents MATCHES "gitdir: [A-Za-z]:[/\\\\]")
        set(use_windows_git_from_wsl TRUE)
    endif()
endif()

if(use_windows_git_from_wsl)
    find_program(MINI_JASS_GIT_EXECUTABLE
        NAMES git.exe
        HINTS "/mnt/c/Program Files/Git/cmd"
        REQUIRED
    )
    find_program(MINI_JASS_WSLPATH_EXECUTABLE wslpath REQUIRED)
    execute_process(
        COMMAND "${MINI_JASS_WSLPATH_EXECUTABLE}" -w "${REPOSITORY_ROOT}"
        RESULT_VARIABLE wslpath_result
        OUTPUT_VARIABLE repository_root_for_git
        ERROR_VARIABLE wslpath_error
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT wslpath_result EQUAL 0)
        message(FATAL_ERROR "Unable to translate repository path for git.exe: ${wslpath_error}")
    endif()
else()
    find_program(MINI_JASS_GIT_EXECUTABLE git REQUIRED)
endif()

execute_process(
    COMMAND "${MINI_JASS_GIT_EXECUTABLE}" -C "${repository_root_for_git}"
            status --porcelain=v1 --untracked-files=all
    RESULT_VARIABLE status_result
    OUTPUT_VARIABLE status_output
    ERROR_VARIABLE status_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(NOT status_result EQUAL 0)
    message(FATAL_ERROR "Unable to inspect repository scope: ${status_error}")
endif()

string(REPLACE "\r\n" "\n" status_output "${status_output}")
string(REPLACE "\n" ";" status_lines "${status_output}")

foreach(status_line IN LISTS status_lines)
    if(status_line STREQUAL "")
        continue()
    endif()

    string(LENGTH "${status_line}" status_line_length)
    if(status_line_length LESS 4)
        message(FATAL_ERROR "Unexpected git status line: ${status_line}")
    endif()

    string(SUBSTRING "${status_line}" 3 -1 changed_path)
    if(changed_path MATCHES " -> ")
        string(REGEX REPLACE "^.* -> " "" changed_path "${changed_path}")
    endif()
    string(REPLACE "\\" "/" changed_path "${changed_path}")

    if(NOT changed_path MATCHES "^mini_jass/")
        message(FATAL_ERROR
            "Mini-Jass isolation violation: changed path outside mini_jass/: ${changed_path}")
    endif()
endforeach()

file(READ "${REPOSITORY_ROOT}/CMakeLists.txt" root_cmake)
string(TOLOWER "${root_cmake}" root_cmake_lower)
if(root_cmake_lower MATCHES "add_subdirectory[ \t\r\n]*\\([ \t\r\n]*mini_jass")
    message(FATAL_ERROR
        "Mini-Jass isolation violation: root CMakeLists.txt must not add mini_jass")
endif()

message(STATUS "Mini-Jass isolation verified")
