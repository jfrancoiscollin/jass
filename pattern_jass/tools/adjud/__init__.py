"""Adjudication predicates (MEMO PREDICATS D'ADJUDICATION).

Deterministic structural predicates composed from dilf's ``pedagogy.features``
primitives, scored against the tablebase (TB) by the §2 harness. Only predicates
whose measured TB-precision is >= 99.9% are admitted as fine steps ("crans") of
the material-adjudication escalier. See docs/MEMO_ADJUD_PREDICATS.md.

Predicates NEVER adjudicate on an eval SCORE (circularity). They read only the
board (geometry/structure) and the move generator (mobility), the latter backed
by jass ``--dump-legal`` via :class:`~adjud.engine.DumpEngine`.
"""
