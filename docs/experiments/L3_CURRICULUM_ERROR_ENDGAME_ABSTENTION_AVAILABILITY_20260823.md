# CURRICULUM error learning: endgame-abstention availability

This screen is the first confirmatory step after the post-hoc 1519/1519a
discovery. It does not reuse any 1517 state as validation evidence and it does
not compute an exact action target.

## Frozen contract

- Candidate: the immutable 1508 residual (`alpha=300`, `cap=100`,
  `strict_both_change`, threshold 10 cp).
- Decision rule: return the byte-identical CURRICULUM anchor whenever the
  production phase classifier returns `endgame`; use the frozen residual
  byte-identically in every other phase.
- Two new pools of 3,840 openings, seeds `2026082301` and `2026082302`.
- Split seed `2026082303`; target-free candidate-order seed `2026082304`.
- 15,360 CURRICULUM-vs-CURRICULUM trajectory games. Both sides use the same
  champion bytes and search parameters.
- Openings are mutually disjoint and exclude the static source plus both pools
  from 1492, 1504 and 1515.

## Availability gates

Before any exact action value is reconstructed, the screen requires:

- at least 3,600 eligible target-free states from at least 1,800 games and
  1,800 openings;
- a matching capacity of at least 1,800 pairs globally and 720 in each pool;
- canonical state uniqueness, at most two states per source game, distinct
  games and openings within every candidate edge;
- a projected cost for the frozen 600-pair reconstruction of at most 360
  minutes;
- zero exact action target, fit, holdout read, strength game, frozen read or
  promotion.

A PASS authorizes only the exact 600-pair confirmatory job. It does not
authorize a production refit or a strength gate.
