#!/usr/bin/env bash
# Immutable identity-only exclusions shared by R0, Pool1 and Pool2.

T3_F6_IDENTITY_EXCLUDE_SPECS="train-a|r2:jass-data/runs/cpx62-1570-l3-deep-sibling-selection-v2/20260826T104456Z-1493d426|artefacts/selected-parents.tsv.gz
train-b|r2:jass-data/runs/cpx62-1578-l3-deep-sibling-phase-b-fresh-v2/20260826T203927Z-87475360|artefacts/fresh-selected-parents.tsv.gz
train-c|r2:jass-data/runs/cpx62-1587-l3-rich-d-r1-phase-c-select-v2/20260827T074201Z-fff1f716|artefacts/phase-c-selected-parents.tsv.gz
m2|r2:jass-data/runs/cpx62-1593-l3-micro-search-m2-fresh-select-v3/20260827T134028Z-f6f96f42|artefacts/m2-selected-parents.tsv.gz
m3|r2:jass-data/runs/cpx62-1599-l3-micro-search-m3-scale-select-v1/20260827T164326Z-430ff2d1|artefacts/m3-selected-parents.tsv.gz
m5|r2:jass-data/runs/cpx62-1609-l3-micro-search-m5-fresh-select-v1/20260828T054803Z-f6f96f42|artefacts/m5-selected-parents.tsv.gz
q1|r2:jass-data/runs/cpx62-1617-l3-joint-td-q1-select-v7/20260828T114236Z-2034c5c9|artefacts/q1-selected-parents.tsv.gz
t2|r2:jass-data/runs/cpx62-1628c-l3-t2-phase-specialist-fresh-select-v3/20260828T182726Z-a3ba045f|artefacts/t2-selected-parents.tsv.gz
rf1|r2:jass-data/runs/cpx62-1633-l3-residual-feature-fresh-select-v1/20260829T032756Z-e5c4a0d6|artefacts/rf1-selected-parents.tsv.gz
t3|r2:jass-data/runs/cpx62-1638-l3-t3-rf1-joint-ab-fresh-select-v1/20260829T084038Z-bbb2bfe4|artefacts/t3-selected-parents.tsv.gz"

T3_F6_FORCE_EXCLUDE_SPECS="context30-p1|r2:jass-data/runs/cpx62-1360-l3-context30-causal-pool1-v1/20260816T075225Z-196d5e1d|artefacts/context30-causal-pool1-openings.fen
context30-p2|r2:jass-data/runs/cpx62-1361-l3-context30-causal-pool2-v1/20260816T080325Z-196d5e1d|artefacts/context30-causal-pool2-openings.fen
d-champion-p1|r2:jass-data/runs/cpx62-1348-jass-d-champion-fresh3000-pool-v1/20260815T065455Z-18c38a33|artefacts/d-champion-fresh3000-openings.fen
d-champion-p2|r2:jass-data/runs/cpx62-1351-jass-d-champion-replication3000-pool-v1/20260815T083517Z-18c38a33|artefacts/d-champion-replication3000-openings.fen
reverse-seed|r2:jass-data/runs/home-1108-l3-pure-reverse-seed-scale4m-independent-readout-v1/20260731T034759Z-3351b160|artefacts/reverse-seed-scale4m-readout-openings.fen
turnover|r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe|artefacts/turnover-l2-eval-openings.fen
big-a|r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa|artefacts/big3000-openings.fen
big-b|r2:jass-data/runs/cpx62-1183-l3-second-big-opening-pool/20260805T155017Z-cd9064f9|artefacts/big3000b-openings.fen
volume8m|r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1|artefacts/vol8m-eval-openings.fen
succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen
context2-p1|r2:jass-data/runs/cpx62-1375-l3-context2-primary-pool1-v1/20260817T025306Z-3393763d|artefacts/context2-primary-pool1-openings.fen
context2-p2|r2:jass-data/runs/cpx62-1377-l3-context2-primary-pool2-v1/20260817T030349Z-3393763d|artefacts/context2-primary-pool2-openings.fen
context3-1419-p1|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool1-openings.fen
context3-1419-p2|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool2-openings.fen
context3-1428-p1|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool1-openings.fen
context3-1428-p2|r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/20260820T005123Z-17517b38|artefacts/ctx3-force-pool2-openings.fen
replay-doe-p1|r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool1-openings.fen
replay-doe-p2|r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool2-openings.fen
replay-promotion-p1|r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool1-openings.fen
replay-promotion-p2|r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool2-openings.fen
rgsc-p1|r2:jass-data/runs/cpx62-1562-l3-rgsc-force-pool1-v1/20260825T053822Z-dd293864|artefacts/force-pool1.fen
tb-policy-p1|r2:jass-data/runs/cpx62-1568-l3-tb-policy-move-ordering-force-pool1-v1/20260825T234756Z-146f3464|artefacts/force-pool1.fen
tb-policy-p2|r2:jass-data/runs/cpx62-1569-l3-tb-policy-move-ordering-force-pool2-v1/20260826T061618Z-146f3464|artefacts/force-pool2.fen
dssd-policy-p1|r2:jass-data/runs/cpx62-1584-l3-dssd-move-ordering-force-pool1-v1/20260826T232038Z-9cc1788b|artefacts/force-pool1.fen"
