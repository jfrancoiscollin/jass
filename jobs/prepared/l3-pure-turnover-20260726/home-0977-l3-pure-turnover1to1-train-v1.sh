#!/usr/bin/env bash
# id: home-0977-l3-pure-turnover1to1-train-v1
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged SHA}"
export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-0977-l3-pure-turnover1to1-train-v1"
export M1_PREFIX="r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/20260724T052619Z-faddc80a"
export EXPECTED_M1_JOB="home-0944-l3-pure-m1-train-resume-v3"
export CHAMPION_PREFIX="r2:jass-data/runs/home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1/20260725T154956Z-0c1e04a9"
export EXPECTED_CHAMPION_JOB="home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1"
export EXPECTED_PARENT_MODEL_SHA256="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
export EXPECTED_F2M_CORPUS_SHA256="15261c89bd6520e17c03bcf2843b226600ff334130656aab7b1a1f2d1ca03248"
export EXPECTED_F2M_META_SHA256="6b12a940128033652afe578c61e48c8570ba4db14cb4cde363d56d4bdcdf2d7f"
export M2_D8_PREFIX="r2:jass-data/runs/home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1/20260725T164714Z-012b9c71"
export EXPECTED_M2_D8_JOB="home-0966bis-l3-pure-m2-f2m-fresh2m-train-v1"
export EXPECTED_M2_D8_CODE_SHA="012b9c716dadf2c3df668c23a7dd9d5ece423b8c"
export EXPECTED_M2_D8_MODEL_SHA256="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
export EXPECTED_M2_D8_CORPUS_SHA256="ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8"
export EXPECTED_M2_D8_META_SHA256="42b184456375bb581192651262f3981879bd04e5ee3162a6186883c2f8f66729"
export M2_EVAL_PREFIX="r2:jass-data/runs/home-0970bis-l3-pure-m2-independent-eval-v3/20260725T214024Z-f9ee6be0"
export EXPECTED_M2_EVAL_JOB="home-0970bis-l3-pure-m2-independent-eval-v3"
export D12_EVAL_PREFIX="r2:jass-data/runs/home-0974bis-l3-pure-d12-causal-independent-eval-v1/20260726T054944Z-4d10d40d"
export EXPECTED_D12_EVAL_JOB="home-0974bis-l3-pure-d12-causal-independent-eval-v1"
export EXPECTED_TURNOVER_CORPUS_SHA256="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
export EXPECTED_TURNOVER_META_SHA256="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
export EXPERIMENT_VARIANT="TURNOVER_1_1"
export PLAY_DEPTH_OVERRIDE=8
export TURNOVER_APPROVED=1
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1
exec timeout -k 120s 14400s bash jobs/templates/l3-pure-m2-train-v1.sh
