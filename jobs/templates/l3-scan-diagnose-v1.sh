#!/usr/bin/env bash
# L3 — diagnostic du harnais Jass-contre-Scan.
#
# home-0997ter a mesuré 5 % contre Scan, identique en d12/d12 et d10/d6, avec
# 40 parties en 18 s à profondeur 10 — physiquement impossible. 38 parties sur
# 40 se terminent par « no legal move from Jass-player ».
#
# calibrate_vs_scan.go() renvoie None quand le moteur répond « error », et
# l'arbitre traduit None en « pas de coup légal », donc en DÉFAITE. Une erreur
# moteur est ainsi indiscernable d'une position terminale légitime.
#
# Ce job ne mesure aucune force. Il établit la cause en trois temps :
#   1. dialogue HUB brut avec le moteur, sans harnais, stderr capturée ;
#   2. trois variantes d'argv pour isoler --search-params et --pattern ;
#   3. mini-cellules de 4 parties par variante, avec dump des parties.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"
: "${CHAMPION_TRAIN_PREFIX:?}"; : "${EXPECTED_CHAMPION_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/hub" "$ART/cells"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/stage.txt"
: > "$RES"
echo preflight > "$STAGE"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  ( while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 30
    done ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f \( -name '*.log' -o -name '*.err' \) -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=2
OPENING_SEED=1414214
CACHE_MB=128
CHAMPION_MODEL_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
PROBE_POS='W:W34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50:B1,2,3,4,5,6,7,8,9,10,11,12,14,15,19,20,23,27,28'
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
monitor

stage verify-scan-and-fetch-model
[ -x "$SCAN_BIN" ] || die "Scan binary missing at $SCAN_BIN"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary SHA mismatch"
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=CHAMPION.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-champion-train.json" \
  > "$W/fetch-champion.log" 2>&1
gunzip -c "$IN/CHAMPION.pjtw.gz" > "$W/CHAMPION.pjtw"
[ "$(sha256sum "$W/CHAMPION.pjtw" | awk '{print $1}')" = "$CHAMPION_MODEL_SHA" ] ||
  die "champion model hash drift"

stage build-8cf-engine
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass > "$W/build8.log" 2>&1
J8="$W/build8/jass"

# --- 1. dialogue HUB brut, sans harnais ---------------------------------------
stage hub-dialogue-raw
python3 - "$J8" "$W/CHAMPION.pjtw" "$Q00" "$PROBE_POS" "$ART/hub" <<'PY'
import json
import pathlib
import subprocess
import sys
import time

jass, pattern, q00, pos, outdir = sys.argv[1:6]
outdir = pathlib.Path(outdir)

VARIANTS = {
    "A_pattern_and_params": [jass, "--pattern", pattern, "--search-params", q00],
    "B_pattern_only":       [jass, "--pattern", pattern],
    "C_no_pattern":         [jass],
}

report = {}
for name, argv in VARIANTS.items():
    entry = {"argv": argv[1:]}
    try:
        p = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
    except Exception as exc:                      # noqa: BLE001
        report[name] = {**entry, "spawn_error": repr(exc)}
        continue
    lines, t0 = [], time.time()
    try:
        for cmd in ("hub", "init", f"pos pos={pos}", "go depth 10"):
            p.stdin.write(cmd + "\n")
            p.stdin.flush()
            deadline = time.time() + 60
            while time.time() < deadline:
                line = p.stdout.readline()
                if not line:
                    break
                lines.append(line.rstrip())
                head = line.split(None, 1)[0] if line.strip() else ""
                if head in ("ready", "done", "bestmove", "error"):
                    break
                if cmd == "hub" and head == "id":
                    continue
    except Exception as exc:                      # noqa: BLE001
        lines.append(f"<<exception {exc!r}>>")
    elapsed = round(time.time() - t0, 3)
    try:
        p.stdin.write("quit\n")
        p.stdin.flush()
        p.wait(timeout=10)
    except Exception:                             # noqa: BLE001
        p.kill()
    err = ""
    try:
        err = p.stderr.read()[-4000:]
    except Exception:                             # noqa: BLE001
        pass
    entry.update({
        "elapsed_s": elapsed,
        "returncode": p.returncode,
        "stdout_lines": lines[-40:],
        "stderr_tail": err,
        "produced_bestmove": any(l.startswith("bestmove") for l in lines),
        "produced_error": any(l.startswith("error") for l in lines),
    })
    report[name] = entry
    (outdir / f"{name}.txt").write_text(
        "\n".join(lines) + "\n\n--- stderr ---\n" + err, encoding="utf-8"
    )

(outdir / "hub-dialogue.json").write_text(
    json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
)
for name, e in sorted(report.items()):
    print(
        f"  {name:22s} bestmove={e.get('produced_bestmove')} "
        f"error={e.get('produced_error')} rc={e.get('returncode')} "
        f"{e.get('elapsed_s')}s"
    )
PY

# --- 2. mini-cellules par variante --------------------------------------------
stage mini-cells-per-variant
"$J8" --gen-opening-pool "$NOPEN" "$W/open-diag.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-diag.log" 2>&1

run_variant(){
  local name="$1"; shift
  mkdir -p "$W/games-$name"
  timeout 600 python3 jobs/tools/calibrate_vs_scan.py \
    --jass "$J8" --scan "$SCAN_BIN" --jass-threads 1 \
    --scan-book off --scan-bb-size 0 \
    --openings-file "$W/open-diag.fen" --pairs 1 --max-plies 260 \
    --jass-depth 10 --scan-depth 6 --dump-games-dir "$W/games-$name" \
    "$@" > "$W/cell-$name.log" 2>"$W/cell-$name.err" || true
}
run_variant A_pattern_and_params --jass-pattern "$W/CHAMPION.pjtw" \
  --jass-search-params "$Q00"
run_variant B_pattern_only --jass-pattern "$W/CHAMPION.pjtw"
run_variant C_no_pattern

stage publish-diagnosis
python3 - "$W" "$ART" <<'PY'
import json
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
cells = {}
for log in sorted(w.glob("cell-*.log")):
    name = log.stem[len("cell-"):]
    txt = log.read_text(errors="replace")
    m = re.search(r"Jass score rate:\s*([0-9.]+)", txt)
    nolegal = len(re.findall(r"no legal move from Jass-player", txt))
    games = re.findall(r"^\s*game\s+(\d+):", txt, re.M)
    err = (w / f"cell-{name}.err").read_text(errors="replace")[-2000:]
    cells[name] = {
        "score_rate": float(m.group(1)) if m else None,
        "games_logged": int(games[-1]) if games else 0,
        "jass_no_legal_move_losses": nolegal,
        "stderr_tail": err,
    }

hub = json.loads((art / "hub" / "hub-dialogue.json").read_text())
culprit = None
if hub.get("A_pattern_and_params", {}).get("produced_error"):
    culprit = "search_params_rejected_by_engine"
elif not hub.get("A_pattern_and_params", {}).get("produced_bestmove"):
    culprit = "engine_never_answers_go_depth"
elif all(c["jass_no_legal_move_losses"] for c in cells.values()):
    culprit = "harness_or_protocol_bridge"
else:
    culprit = "variant_dependent_see_cells"

payload = {
    "schema": 1,
    "verdict": "SCAN_HARNESS_DIAGNOSIS_READY",
    "suspected_cause": culprit,
    "hub_dialogue": hub,
    "cells": cells,
    "known_harness_weakness": (
        "calibrate_vs_scan.go() renvoie None sur une réponse 'error' du moteur, "
        "et l'arbitre traduit None en 'no legal move' donc en défaite. Une "
        "erreur moteur est indiscernable d'une position terminale."
    ),
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "scan-diagnosis.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__SCAN_HARNESS_DIAGNOSIS_READY").write_text(
    "SCAN_HARNESS_DIAGNOSIS_READY\n"
)
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
print(f"  cause suspectée : {culprit}")
for name, c in sorted(cells.items()):
    print(
        f"  {name:22s} score={c['score_rate']} "
        f"parties={c['games_logged']} pertes_no_legal={c['jass_no_legal_move_losses']}"
    )
PY
cp -r "$W"/games-* "$ART/cells/" 2>/dev/null || true
stage complete
say "SCAN_HARNESS_DIAGNOSIS_READY promotion=false automatic_next_job=null"
