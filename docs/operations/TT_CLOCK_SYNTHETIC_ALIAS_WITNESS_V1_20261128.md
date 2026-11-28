# Synthetic halfmove-clock alias witness V1

Status: **FIXTURE SPECIFIED; EXECUTION PENDING**.

This fixture asks whether two explicitly composed, legal move sequences can
reach the same board, side to move and position hash with distinct halfmove
clocks. The starting position is composed; its reachability from the standard
initial position is not asserted.

Start both sequences from `W:W42,K50:B9,K1` with the parser's initial clock of
zero. For each move, select exactly one matching from/to move from the legal
generator and require a quiet, non-promoting move before applying it.

| Sequence | Moves | Expected final clock |
| --- | --- | ---: |
| A | `42-37 9-13 50-45 1-6` | 2 |
| B | `50-45 1-6 42-37 9-13` | 0 |

Both sequences must end at `W:W37,K45:B13,K6`, with equal position hashes.
The clocks are derived exclusively through `Position::after`, never injected.
Failure of any assertion rejects this witness; it does not authorize choosing
another sequence from observed results under this fixture.

This test does not invoke search or a transposition table. A successful fixture
would demonstrate an alias of the position hash with respect to the clock; it
would not establish an incorrect reused score, practical decision improvement,
calibration, or a candidate. Such questions require separate evidence and
prospective protocols, including independent fresh groups and an adjudicator
that accounts for the clock and history. No data, model, real position, database,
R2, cohort, scientific job or alpha is used by this fixture.
