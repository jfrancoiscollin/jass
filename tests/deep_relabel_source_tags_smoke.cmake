if(NOT DEFINED JASS_EXE OR NOT DEFINED SMOKE_DIR OR NOT DEFINED TESTS_DIR)
    message(FATAL_ERROR "JASS_EXE, SMOKE_DIR and TESTS_DIR are required")
endif()
if(NOT DEFINED PYTHON_EXE)
    set(PYTHON_EXE "python3")
endif()

file(MAKE_DIRECTORY "${SMOKE_DIR}")

function(run_cmd result_var stdout_var stderr_var)
    execute_process(
        COMMAND ${ARGN}
        RESULT_VARIABLE result
        OUTPUT_VARIABLE stdout
        ERROR_VARIABLE stderr
    )
    set(${result_var} "${result}" PARENT_SCOPE)
    set(${stdout_var} "${stdout}" PARENT_SCOPE)
    set(${stderr_var} "${stderr}" PARENT_SCOPE)
endfunction()

set(base_jnnw "${SMOKE_DIR}/base.jnnw")
set(in_jnnw   "${SMOKE_DIR}/in.jnnw")

# 64 tiny, fast, deterministic records (fixed seed, low depths).
run_cmd(gen_rc gen_out gen_err
    "${JASS_EXE}" --gen-data-wdl 64 "${base_jnnw}" 4 2 40 4242
    --wdl-zero-score --sample-initial --random-open-plies 2
)
if(NOT gen_rc EQUAL 0)
    message(FATAL_ERROR "gen-data-wdl smoke input failed: ${gen_err}")
endif()

# Append one hand-built TERMINAL record (no legal move for STM).
run_cmd(app_rc app_out app_err
    "${PYTHON_EXE}" "${TESTS_DIR}/deep_relabel_append_terminal.py"
    "${base_jnnw}" "${in_jnnw}"
)
if(NOT app_rc EQUAL 0)
    message(FATAL_ERROR "append_terminal failed: ${app_err}")
endif()

# --- Run WITHOUT the two new flags twice: legacy path must be deterministic
#     and must not produce a tags file. -------------------------------------
set(legacy_a "${SMOKE_DIR}/legacy-a.jnnw")
set(legacy_b "${SMOKE_DIR}/legacy-b.jnnw")
run_cmd(leg_a_rc leg_a_out leg_a_err
    "${JASS_EXE}" --deep-relabel "${in_jnnw}" "${legacy_a}" 6
)
if(NOT leg_a_rc EQUAL 0)
    message(FATAL_ERROR "legacy deep-relabel run a failed: ${leg_a_err}")
endif()
run_cmd(leg_b_rc leg_b_out leg_b_err
    "${JASS_EXE}" --deep-relabel "${in_jnnw}" "${legacy_b}" 6
)
if(NOT leg_b_rc EQUAL 0)
    message(FATAL_ERROR "legacy deep-relabel run b failed: ${leg_b_err}")
endif()
file(SHA256 "${legacy_a}" legacy_a_sha)
file(SHA256 "${legacy_b}" legacy_b_sha)
if(NOT legacy_a_sha STREQUAL legacy_b_sha)
    message(FATAL_ERROR "legacy deep-relabel path is not deterministic")
endif()
if(EXISTS "${SMOKE_DIR}/legacy.tags")
    message(FATAL_ERROR "legacy run unexpectedly produced a tags file")
endif()

# --- Run WITH --clear-tt --source-tags-out, twice, for determinism. --------
set(out_a  "${SMOKE_DIR}/out-a.jnnw")
set(out_b  "${SMOKE_DIR}/out-b.jnnw")
set(tags_a "${SMOKE_DIR}/tags-a.bin")
set(tags_b "${SMOKE_DIR}/tags-b.bin")

run_cmd(tag_a_rc tag_a_out tag_a_err
    "${JASS_EXE}" --deep-relabel "${in_jnnw}" "${out_a}" 6
    --clear-tt --source-tags-out "${tags_a}"
)
if(NOT tag_a_rc EQUAL 0)
    message(FATAL_ERROR "tagged deep-relabel run a failed: ${tag_a_err}")
endif()
if(NOT tag_a_out MATCHES "deep-relabel summary: records=65 search=64 tb=0 terminal=1")
    message(FATAL_ERROR "unexpected summary line: ${tag_a_out}")
endif()
if(NOT tag_a_out MATCHES "clear_tt=1")
    message(FATAL_ERROR "summary line does not report clear_tt=1: ${tag_a_out}")
endif()

run_cmd(tag_b_rc tag_b_out tag_b_err
    "${JASS_EXE}" --deep-relabel "${in_jnnw}" "${out_b}" 6
    --clear-tt --source-tags-out "${tags_b}"
)
if(NOT tag_b_rc EQUAL 0)
    message(FATAL_ERROR "tagged deep-relabel run b failed: ${tag_b_err}")
endif()

file(SHA256 "${out_a}" out_a_sha)
file(SHA256 "${out_b}" out_b_sha)
if(NOT out_a_sha STREQUAL out_b_sha)
    message(FATAL_ERROR "tagged deep-relabel output is not deterministic")
endif()
file(SHA256 "${tags_a}" tags_a_sha)
file(SHA256 "${tags_b}" tags_b_sha)
if(NOT tags_a_sha STREQUAL tags_b_sha)
    message(FATAL_ERROR "tags file is not deterministic")
endif()

# --- Structural / value checks via the python verifier. --------------------
run_cmd(verify_rc verify_out verify_err
    "${PYTHON_EXE}" "${TESTS_DIR}/deep_relabel_source_tags_verify.py"
    "${in_jnnw}" "${out_a}" "${tags_a}"
)
if(NOT verify_rc EQUAL 0)
    message(FATAL_ERROR "verifier failed: ${verify_out} ${verify_err}")
endif()

message(STATUS "deep-relabel source-tags smoke passed: ${verify_out}")
