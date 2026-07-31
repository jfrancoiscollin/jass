#!/usr/bin/env bash
# L3 — sonde de protocole Scan : capturer le format réel des scores.
#
# L'atlas de points aveugles jugé par Scan a besoin du SCORE de Scan sur une
# position. Scan ne le met pas sur `done` (qui ne porte que `move=`) mais sur
# les lignes émises pendant la réflexion, et ce format n'a jamais été capturé
# ici : `calibrate_vs_scan` ne lit que le coup et jette le reste.
#
# Ce job ouvre Scan, lui donne quatre positions, et écrit VERBATIM tout ce qu'il
# répond. Puis il teste le motif d'extraction de `scan_blind_spot_atlas.py`
# contre ces lignes.
#
# Un motif qui rate n'est PAS un échec de ce job : c'est son résultat, et la
# transcription est là pour qu'on écrive le bon. Le verdict porte l'information.
#
# Aucune partie jouée, aucun modèle, aucun fit, aucune promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_EVAL_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$ART"
RES="$W/RESULTS.txt"
: > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  cp "$RES" "$ART/RESULTS.txt"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"

say "phase=verify-pinned-scan-runtime"
[ -x "$SCAN_BIN" ] || die "binaire Scan absent ou non exécutable : $SCAN_BIN"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "hash du binaire Scan différent de l'épinglage"
SCAN_DIR="$(dirname "$(readlink -f "$SCAN_BIN")")"
[ "$(sha256sum "$SCAN_DIR/data/eval" | awk '{print $1}')" = "$EXPECTED_SCAN_EVAL_SHA256" ] ||
  die "hash de data/eval différent de l'épinglage"
say "  runtime Scan ✓ : binaire et data/eval conformes à l'épinglage"

say "phase=self-test-of-the-probe"
# La sonde est testée contre un faux Scan AVANT de toucher au vrai : si la
# plomberie est cassée, autant le savoir sans consommer le runtime épinglé.
python3 -m pytest jobs/tests/test_scan_protocol_probe.py \
                  jobs/tests/test_scan_blind_spot_atlas.py -q \
  > "$W/selftest.log" 2>&1 || die "auto-test de la sonde en échec — voir selftest.log"
say "  auto-test ✓"

say "phase=probe-real-scan"
python3 jobs/tools/scan_protocol_probe.py \
  --scan "$SCAN_BIN" --depth "${PROBE_DEPTH:-10}" \
  --transcript "$ART/scan-transcript.txt" \
  --out "$ART/scan-protocol-probe.json" \
  > "$W/probe.log" 2>&1 || die "sonde en échec — voir probe.log"

cp "$ART/scan-protocol-probe.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' \
  "$ART/scan-protocol-probe.json")"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"

python3 - "$ART/scan-protocol-probe.json" <<'PY' | tee -a "$RES"
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  motif testé : {d['pattern_under_test']}")
print(f"  positions sondées : {d['positions_probed']}, "
      f"scores extraits : {d['positions_with_score_extracted']}")
for f in d["findings"]:
    print(f"    {f['position']:14s} lignes={f['lines_received']:3d} "
          f"done={f['reached_done']} score={f['score_extracted']}")
    for line in f["last_three_lines"]:
        print(f"        | {line[:110]}")
PY
say "$VERDICT promotion=false automatic_next_job=null"
