from jobs.tools import ed4_c0c_v4_next_failure_diagnostic_stage as diag


def test_v4_class_requires_exact_scope_and_shape():
    shape={"magic":"JNNW","declared_count":0,"complete_records":3023,"partial_tail_bytes":32}
    desc={"kind":"jnnw","path":"b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-9.jnnw"}
    assert diag.is_v4_class("cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1","20260905T145718Z-d3657332",desc,shape)
    assert not diag.is_v4_class("other","20260905T145718Z-d3657332",desc,shape)
    bad=dict(shape); bad["partial_tail_bytes"]=0
    assert not diag.is_v4_class("cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1","20260905T145718Z-d3657332",desc,bad)
