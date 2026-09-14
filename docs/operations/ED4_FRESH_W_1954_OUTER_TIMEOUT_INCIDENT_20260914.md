# ED4-FRESH W production 1954 — outer-timeout admission incident

Date: 2026-09-14.

Job `cpx62-1954-l3-ed4-fresh-w-source-production-v1`, attempt `20260914T061056Z-80167252`, failed before stage execution with launch classification `TECHNICAL` / `OUTER_TIMEOUT_CONTRACT`.

The scientific stage specification itself remained the frozen W-production contract: Jass `80167252aa59c26ca36bafa86c1dbcdeb8569fff`, raw record budget `40960`, W seed `202609120402`, authenticated rehearsal 1953, score-free source generation and zero confirmation-target reads. The spec had `stage_seconds=2700`.

The control queue wrapper incorrectly set `EXPECTED_LAUNCH_TIMEOUT_SECONDS=3000`. Launch Gate V2 requires the outer runner timeout to equal `stage_seconds + 600`, therefore the required value was `3300`. The gate rejected the job immediately before the W stage executed, so no W production cohort or confirmation target was consumed.

The technical retry is `cpx62-1956-l3-ed4-fresh-w-source-production-v2`. It keeps the stage spec/science byte-identical and changes only the job/admission identity plus the outer timeout to `3300`. The retry remains subject to the same authenticated 1953 rehearsal receipt and all frozen ED4-FRESH barriers.
