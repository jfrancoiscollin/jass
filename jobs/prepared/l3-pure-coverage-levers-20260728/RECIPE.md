# L3-PURE coverage levers — prepared HOME jobs

Status: prepared only. None of these files is in `jobs/queue`, and no job is
authorized or scheduled by this directory.

## Dependency

Every training A/B requires the completed, authenticated result of
`home-1017-l3-pure-topk-causal-ab-v2` with verdict
`L3_PURE_TOPK_CAUSAL_AB_ARMS_READY`. This dependency proves that the current
experiment is closed; it does not select either 1017 arm as a new parent.
TURNOVER remains the pinned parent for all five comparisons.

It also requires the completed independent TOPK3-vs-UNIFORM readout following
1017, with at least 5,400 valid summed games across Q00/native. This prevents a
new causal axis from starting before the current one has a force verdict.

Before launch, fill:

- a unique, non-duplicated `EXPECTED_JOB_ID`;
- the reviewed merged `EXPECTED_CODE_SHA`;
- the exact completed `PREREQUISITE_PREFIX`;
- `TOPK_READOUT_PREFIX` and its exact `EXPECTED_TOPK_READOUT_JOB`;
- `FULL_RUN_APPROVED=1` and `SCIENTIFIC_GO=1`.
- the SHA256 of `artefacts/uniform.jnnw.gz` and
  `artefacts/uniform.jsm.gz` from 1017.

Every arm is trained on exactly 2M records: 1M fresh records plus the same
deterministically selected 1M records from that authenticated, post-root-fix
UNIFORM corpus. This fixed 50/50 rolling replay is part of the causal contract,
not a tuned hyperparameter.

## Order

Run one training A/B at a time:

1. `phase-sampling-ab.sh`
   - control: historical `1/4` sampling in every phase;
   - treatment: denominators `8,4,3,2,1`;
   - fixed output volume: 2M records per arm.
2. `topk-softmax-ab.sh`
   - both arms: TOPK3, margin 50;
   - control: uniform choice inside the eligible set;
   - treatment: score-softmax at 50 cp.
3. `regret-restart-ab.sh`
   - control: no restart;
   - treatment: 20% restart from a 4,000-position parent-regret archive.
4. `opening-pool-ab.sh`
   - control: historical random-8 opening diversification;
   - treatment: 50% random-8 and 50% uniformly sampled quiet master positions;
   - durable source: Git blob `4ec127ffc32e2eee9e4a36f656ce4d97fac8d04e`
     containing 1,458,341 positions from 13,266 Lidraughts master games;
   - preferred source when still present on HOME: run
     `master-corpus-preflight.sh` first, then pin its path and SHA256 with
     `MASTER_CORPUS_MODE=local`, `MASTER_CORPUS_LOCAL_PATH` and
     `MASTER_CORPUS_LOCAL_SHA256`. The historical fetch documented 43,996
     games; the preflight proves how many complete boundaries actually remain;
   - master labels and played moves are not used as learning targets: each
     selected position receives a fresh self-play continuation and WDL.
5. `replay-ratio-ab.sh`
   - control: 2M fresh records;
   - treatment: a deterministic 1M sample of the same byte-identical 2M fresh
     input plus 1M records from the authenticated post-fix 1017 UNIFORM corpus;
   - constant 2M fit volume; the only factor is replacement of half the fresh
     corpus by rolling replay.

The ordering is operational, not inferential. Do not launch the next A/B while
another HOME job is pending or running.

After an A/B reaches `L3_PURE_COVERAGE_LEVER_ARMS_READY`, run `readout.sh` with
its exact prefix and lever. The readout uses 1,500 newly generated openings,
both colours, Q00 and native 0.1 s, for 6,000 games summed before Elo/CI95.

Every job writes:

```text
promotion_authorized=false
automatic_next_job=null
```

No oracle, teacher, reweight V2, removed box or L3-IMBALANCE2 input is used.
