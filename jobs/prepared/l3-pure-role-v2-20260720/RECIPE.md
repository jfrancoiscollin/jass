# L3-PURE role-aware V2 — paired tests

This directory prepares two independent paired A/B tests for the original balanced-start L3 lineage.

## ccx33 primary pair

- control: `ccx33-l3-pure-q00-control.sh`;
- treatment: `ccx33-l3-pure-q00-role-v2.sh`;
- common seed: `271828`.

## cpx62 replication pair

- control: `cpx62-l3-pure-q00-control.sh`;
- treatment: `cpx62-l3-pure-q00-role-v2.sh`;
- common seed: `161803`.

Within each pair, the initial model, search parameters, seeds, generation count and source-volume contract are identical. Only the post-split training corpus differs:

- control trains on the unweighted `fit.jnnw`;
- treatment reweights only positions with exactly two men of difference and equal king counts;
- treatment matrix, side-to-move POV: `+2 = 1/2/4`, `-2 = 4/2/1`;
- positions outside the exact domain remain weight `1`;
- the final holdout remains untouched.

G1 self-play is directly matched because both arms start from the same material seed. From G2 onward, trajectories may diverge because G1 students differ; that divergence is part of the treatment effect, not a configuration mismatch.

Both tests use Q00_CAPTURE, two generations, 150,000 source records per generation, eight shards and no moving frontier. They are not promotion jobs and must not be queued without explicit approval.
