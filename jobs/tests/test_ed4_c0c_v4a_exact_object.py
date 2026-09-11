from pathlib import Path

from jobs.tools import ed4_c0c_exclusion_union_v4 as v4


def _desc(path, sha, size):
    return {'kind':'jnnw','path':path,'sha256':sha,'size_bytes':size}


def test_v4a_exact_sp0_1_is_scoped_only_with_exact_identity():
    path='b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0297-saturate-loop/artefacts/sp0-1.jnnw'
    sha='bb556ce4b75a16e2123c2413346bb2abe34375c46d53531079d9ca324cc9aeea'
    good=_desc(path,sha,98498)
    assert v4._is_scoped_object(good,v4.SALVAGE_JOB,v4.SALVAGE_ATTEMPT)
    assert not v4._is_scoped_object(_desc(path,'0'*64,98498),v4.SALVAGE_JOB,v4.SALVAGE_ATTEMPT)
    assert not v4._is_scoped_object(_desc(path,sha,98499),v4.SALVAGE_JOB,v4.SALVAGE_ATTEMPT)
    assert not v4._is_scoped_object(good,'other-job',v4.SALVAGE_ATTEMPT)
    assert not v4._is_scoped_object(good,v4.SALVAGE_JOB,'other-attempt')


def test_v4a_does_not_admit_sibling_in_same_directory():
    sibling=_desc(
        'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0297-saturate-loop/artefacts/sp0-2.jnnw',
        'bb556ce4b75a16e2123c2413346bb2abe34375c46d53531079d9ca324cc9aeea',
        98498,
    )
    assert not v4._is_scoped_object(sibling,v4.SALVAGE_JOB,v4.SALVAGE_ATTEMPT)


def test_v4a_exact_shape_is_2591_complete_records_plus_32_tail():
    assert divmod(98498-8,38)==(2591,32)
