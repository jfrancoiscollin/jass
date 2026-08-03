if(NOT DEFINED JASS_EXE OR NOT DEFINED SMOKE_DIR)
    message(FATAL_ERROR "JASS_EXE and SMOKE_DIR are required")
endif()

file(MAKE_DIRECTORY "${SMOKE_DIR}")

function(run_jass result_var stdout_var stderr_var)
    execute_process(
        COMMAND "${JASS_EXE}" ${ARGN}
        RESULT_VARIABLE result
        OUTPUT_VARIABLE stdout
        ERROR_VARIABLE stderr
    )
    set(${result_var} "${result}" PARENT_SCOPE)
    set(${stdout_var} "${stdout}" PARENT_SCOPE)
    set(${stderr_var} "${stderr}" PARENT_SCOPE)
endfunction()

# Historical CLI: no new field means depth mode and no node-budget telemetry.
run_jass(depth_rc depth_out depth_err
    --gen-data-wdl 1 "${SMOKE_DIR}/depth.jnnw" 1 1 8 4242
    --wdl-zero-score --sample-initial --random-open-plies 0
)
if(NOT depth_rc EQUAL 0)
    message(FATAL_ERROR "historical depth smoke failed: ${depth_err}")
endif()
if(depth_out MATCHES "node_budget|search_limit=nodes")
    message(FATAL_ERROR "historical depth smoke emitted node-budget telemetry")
endif()

# Partial configuration must fail closed before generation.
run_jass(invalid_rc invalid_out invalid_err
    --gen-data-wdl 1 "${SMOKE_DIR}/invalid.jnnw" 1 1 8 4242
    --wdl-zero-score --node-budget-fixed 1000
)
if(invalid_rc EQUAL 0 OR NOT invalid_err MATCHES "require --search-limit nodes")
    message(FATAL_ERROR "partial node-budget configuration was not rejected")
endif()

# Fixed policy: one complete mini-game and exact node caps.
run_jass(fixed_rc fixed_out fixed_err
    --gen-data-wdl 1 "${SMOKE_DIR}/fixed.jnnw" 1 1 8 4242
    --wdl-zero-score --sample-initial --random-open-plies 0
    --search-limit nodes --node-budget-fixed 1000
    --node-budget-sample-per move
    --node-budget-log "${SMOKE_DIR}/fixed.jsonl"
)
if(NOT fixed_rc EQUAL 0)
    message(FATAL_ERROR "fixed node-budget smoke failed: ${fixed_err}")
endif()
file(READ "${SMOKE_DIR}/fixed.jsonl" fixed_log)
if(NOT fixed_log MATCHES "\"event\":\"node_budget_manifest\"")
    message(FATAL_ERROR "fixed log has no manifest")
endif()
if(NOT fixed_log MATCHES "\"nodes_budget\":1000,\"nodes_used\":1000")
    message(FATAL_ERROR "fixed log does not contain an exact 1000-node search")
endif()
if(NOT fixed_log MATCHES "\"event\":\"node_budget_summary\"")
    message(FATAL_ERROR "fixed log has no summary")
endif()

# Weighted policy: two identical runs must reproduce all deterministic search
# and game fields. Wall-clock telemetry is intentionally stripped.
foreach(suffix IN ITEMS a b)
    run_jass(weighted_rc weighted_out weighted_err
        --gen-data-wdl 1 "${SMOKE_DIR}/weighted-${suffix}.jnnw" 1 1 8 4242
        --wdl-zero-score --sample-initial --random-open-plies 0
        --search-limit nodes --node-budget-weighted 1000:1,2000:2,5000:1
        --node-budget-sample-per move
        --node-budget-log "${SMOKE_DIR}/weighted-${suffix}.jsonl"
    )
    if(NOT weighted_rc EQUAL 0)
        message(FATAL_ERROR "weighted node-budget smoke ${suffix} failed: ${weighted_err}")
    endif()
endforeach()

file(STRINGS "${SMOKE_DIR}/weighted-a.jsonl" stable_a
     REGEX "\"event\":\"selfplay_(search|game)\"")
file(STRINGS "${SMOKE_DIR}/weighted-b.jsonl" stable_b
     REGEX "\"event\":\"selfplay_(search|game)\"")
string(REGEX REPLACE
       ",\"search_time_ms\":[0-9.]+,\"nps\":[0-9.]+" ""
       stable_a "${stable_a}")
string(REGEX REPLACE
       ",\"search_time_ms\":[0-9.]+,\"nps\":[0-9.]+" ""
       stable_b "${stable_b}")
if(NOT stable_a STREQUAL stable_b)
    message(FATAL_ERROR "weighted deterministic telemetry differs between runs")
endif()

file(SHA256 "${SMOKE_DIR}/weighted-a.jnnw" corpus_a_sha)
file(SHA256 "${SMOKE_DIR}/weighted-b.jnnw" corpus_b_sha)
if(NOT corpus_a_sha STREQUAL corpus_b_sha)
    message(FATAL_ERROR "weighted self-play corpora differ at identical seed")
endif()

message(STATUS "node-budget self-play smoke passed")
