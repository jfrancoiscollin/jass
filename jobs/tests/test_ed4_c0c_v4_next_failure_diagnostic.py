from jobs.tools import ed4_c0c_v4_next_failure_diagnostic_stage as diag

JOB="cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1"
ATTEMPT="20260905T145718Z-d3657332"
PREFIX="b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/"
SHAPE={
    "state":"invalid",
    "reason":"jnnw_trailing_bytes",
    "declared_count":0,
    "declared_body_bytes":0,
    "consumed_body_bytes":0,
}


def _desc(name,size=114914):
    return {"kind":"jnnw","path":PREFIX+name,"size_bytes":size}


def test_v4_class_matches_real_sp1_instances_from_envelope_only():
    for name in ("sp1-1.jnnw","sp1-2.jnnw","sp1-3.jnnw"):
        assert diag.is_v4_class(JOB,ATTEMPT,_desc(name),SHAPE)


def test_v4_class_requires_exact_scope_and_interrupted_tail():
    desc=_desc("sp1-9.jnnw")
    assert not diag.is_v4_class("other",ATTEMPT,desc,SHAPE)
    assert not diag.is_v4_class(JOB,"other",desc,SHAPE)
    assert not diag.is_v4_class(JOB,ATTEMPT,{**desc,"kind":"jnnw_gzip"},SHAPE)
    assert not diag.is_v4_class(JOB,ATTEMPT,{**desc,"path":"elsewhere/sp1-9.jnnw"},SHAPE)
    assert not diag.is_v4_class(JOB,ATTEMPT,desc,{**SHAPE,"reason":"jnnw_truncated"})
    assert not diag.is_v4_class(JOB,ATTEMPT,desc,{**SHAPE,"declared_count":1})
    # 3023 complete records and no tail is not an interrupted-tail instance.
    assert not diag.is_v4_class(JOB,ATTEMPT,_desc("aligned.jnnw",8+3023*38),SHAPE)
    # Header plus only a partial first record is not recoverable under V4.
    assert not diag.is_v4_class(JOB,ATTEMPT,_desc("too-short.jnnw",8+17),SHAPE)
