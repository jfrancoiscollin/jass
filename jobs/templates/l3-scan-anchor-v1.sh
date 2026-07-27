#!/usr/bin/env bash
# L3 — reproduction de l'ancre historique contre Scan, puis mesure de TURNOVER.
#
# home-0997/0998 ont sorti TURNOVER à 0,050 contre Scan, soit ~-512 Elo, alors
# que l'historique du projet donne -128 à -155 Elo au movetime pour gen2-mmto
# et que la lignée a gagné ~60-70 Elo depuis. Un des deux chiffres est faux et
# aucune matrice de calibration ne vaut tant qu'on ne sait pas lequel.
#
# Le job ne mesure donc pas d'abord TURNOVER : il rejoue d'abord l'ancre. GEN2
# (gen2-mmto) est le modèle EXACT dont le -155 mt0.3 / -276 d9 a été publié
# (`0637`, protocole `0571`). S'il se reproduit ici, le harnais est sain et le
# 0,050 de TURNOVER est un vrai résultat à expliquer ; s'il s'effondre lui
# aussi, c'est le harnais ou le runtime Scan qui a bougé et toute mesure
# vs Scan postérieure à `0637` est nulle. Les deux bras jouent le même pool,
# le même binaire Scan, la même cadence.
#
# Déviations assumées par rapport à `0571`, identiques sur les deux bras :
#   - EGDB OFF (l'historique n'en avait pas, et Scan tourne bb-size=0 : lui
#     donner une base de fin de partie parfaite fausserait la symétrie) ;
#   - chaque bras joue sa configuration canonique de recherche — GEN2 les
#     constantes compilées (comme en `0571`/`0637`), TURNOVER son Q00. La
#     comparaison qui compte est bras-à-bras dans le temps, pas bras-à-bras
#     dans ce job.
#
# Aucun verdict de promotion. Aucune continuation automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${SCAN_BIN:?}"; : "${EXPECTED_SCAN_SHA256:?}"
: "${CHAMPION_TRAIN_PREFIX:?}"; : "${EXPECTED_CHAMPION_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/cells"
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
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'stage=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
        for f in "$W"/cell-*.log; do
          [ -e "$f" ] || continue
          n=$(grep -cE '^  game +[0-9]+:' "$f" 2>/dev/null || echo 0)
          printf 'games_%s=%s\n' "$(basename "$f" .log | sed 's/^cell-//')" "$n"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"
      cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32" "$IN" "$GEOM" 2>/dev/null || true
  rm -f "$W"/*.pjtw 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

NOPEN=20
PAIRS=1
GAMES_PER_CELL=$((NOPEN * 2 * PAIRS))
MIN_GAMES=30
CELL_TIMEOUT=3000
MAX_PLIES=200
MOVETIME=0.3
FIXED_DEPTH=9
# Pool historique : les 20 premières positions de combinaison DILF, filtrées
# exactement comme `0571` (`grep -vE '^\s*(#|$)' | head -N`).
DILF="data/dilf_combinations.fen"
DILF_SHA="f0f1ff5e60d0b44d23a1190843cb72d5385eaf87d5757e2f24166d484cb90849"
POOL_SHA="764cef5c414d93d94e012d40e9d0c6086c9bd805d1da0315c7e44fd2f4b7e1d1"
TURNOVER_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
# PLANCHERS pour le bras GEN2, fixés AVANT le run — et volontairement
# UNILATÉRAUX. Les ancres publiées (mt0.3 = -155 Elo, score ~0,290 ; d9 = -276,
# score ~0,170) ont été mesurées sur un moteur qui rendait un coup nul sur toute
# racine nulle et perdait donc la partie : ce sont des PLANCHERS, pas des
# valeurs. Un moteur réparé doit faire mieux, et le dépassement ne contredit
# rien. Seul l'effondrement sous le plancher signe un harnais encore cassé.
# n=40 par cellule => erreur-type 7,9 pp ; plancher = ancre - 1,5 erreur-type.
GEN2_MT_FLOOR=0.17
GEN2_D9_FLOOR=0.05
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 5000 ] ||
  die "need 5 GiB free"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
monitor

stage verify-pinned-scan-runtime
[ -x "$SCAN_BIN" ] || die "Scan binary missing at $SCAN_BIN"
[ "$(sha256sum "$SCAN_BIN" | awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary SHA mismatch — runtime is not the pinned one"
say "  runtime Scan ✓ figé : $EXPECTED_SCAN_SHA256"

stage fetch-both-models
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=TURNOVER.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-champion-train.json" \
  > "$W/fetch-turnover.log" 2>&1
python3 - "$ART/verified-champion-train.json" "$EXPECTED_CHAMPION_TRAIN_JOB" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
if report.get("job_id") != sys.argv[2] or report.get("result_state") != "completed":
    raise SystemExit(f"{sys.argv[1]}: source identity/state mismatch")
PY
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-gen2.json" > "$W/fetch-gen2.log" 2>&1
gunzip -c "$IN/TURNOVER.pjtw.gz" > "$W/TURNOVER.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] ||
  die "TURNOVER model hash drift"
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
  die "Gen2 model hash drift"
say "  modèles ✓ : TURNOVER (8cf) + GEN2 (32cf), hachés à l'identique des portes"

stage build-engines
# EGDB volontairement absent : cf en-tête. Le reste des options reproduit la
# ligne de build de `0571`.
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns8.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j8 --target jass jass_tests > "$W/build8.log" 2>&1
ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns32.py"
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j8 --target jass > "$W/build32.log" 2>&1
J32="$W/build32/jass"
for jass in "$J8" "$J32"; do
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "king-capture witness failed for $jass"
done
# `pattern_jass::load_weights` refuse un fichier dont le nombre de buckets ne
# correspond pas à la géométrie compilée, et `--pattern` sort en code 2 dans ce
# cas : un modèle chargé dans la mauvaise géométrie ne peut donc PAS produire
# une évaluation silencieusement absurde. On le vérifie ici plutôt que de le
# supposer, dans les deux sens, parce que c'est l'hypothèse la plus naturelle
# pour expliquer le 0,050 et qu'il faut pouvoir l'écarter par une trace.
loads(){ "$1" --eval-position "$2" 'W:W31,32,33:B18,19,20' >/dev/null 2>&1; }
if ! loads "$J8"  "$W/TURNOVER.pjtw"; then die "8cf engine cannot load TURNOVER"; fi
if ! loads "$J32" "$W/GEN2.pjtw";     then die "32cf engine cannot load GEN2"; fi
if loads "$J8"  "$W/GEN2.pjtw";     then die "8cf engine accepted the 32cf model"; fi
if loads "$J32" "$W/TURNOVER.pjtw"; then die "32cf engine accepted the 8cf model"; fi
say "  moteurs ✓ : 8cf et 32cf construits, chacun rejette la géométrie de l'autre"

stage build-historical-pool
grep -vE '^\s*(#|$)' "$DILF" | head -"$NOPEN" > "$W/open.fen"
[ "$(sha256sum "$DILF" | awk '{print $1}')" = "$DILF_SHA" ] || die "DILF drift"
[ "$(sha256sum "$W/open.fen" | awk '{print $1}')" = "$POOL_SHA" ] ||
  die "historical pool drift"
NPOS=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' \
  "$W/open.fen")
[ "$NPOS" -eq "$NOPEN" ] || die "pool count drift: $NPOS != $NOPEN"
say "  pool historique ✓ : $NPOS positions DILF, $GAMES_PER_CELL parties/cellule"

# Une cellule joue ses parties séquentiellement (l'outil est séquentiel) ; les
# quatre cellules tournent en parallèle, soit 8 processus moteur sur 16 CPU.
run_cell(){
  local name="$1" engine="$2" model="$3" params="$4"; shift 4
  local start end rc extra=()
  [ -n "$params" ] && extra=(--jass-search-params "$params")
  start=$(date +%s)
  timeout "$CELL_TIMEOUT" python3 jobs/tools/calibrate_vs_scan.py \
    --jass "$engine" --scan "$SCAN_BIN" --jass-pattern "$model" \
    "${extra[@]}" --jass-threads 1 --scan-book off --scan-bb-size 0 \
    --openings-file "$W/open.fen" --pairs "$PAIRS" \
    --dump-games-dir "$W/games-$name" \
    --max-plies "$MAX_PLIES" "$@" > "$W/cell-$name.log" 2>&1
  rc=$?
  end=$(date +%s)
  printf '%s %s %s\n' "$name" "$rc" "$((end - start))" > "$W/cell-$name.timing"
}

stage play-anchor-and-champion
pids=()
run_cell gen2-mt030     "$J32" "$W/GEN2.pjtw"     ""      --movetime "$MOVETIME" & pids+=("$!")
run_cell gen2-d9        "$J32" "$W/GEN2.pjtw"     ""      --depth "$FIXED_DEPTH" & pids+=("$!")
run_cell turnover-mt030 "$J8"  "$W/TURNOVER.pjtw" "$Q00"  --movetime "$MOVETIME" & pids+=("$!")
run_cell turnover-d9    "$J8"  "$W/TURNOVER.pjtw" "$Q00"  --depth "$FIXED_DEPTH" & pids+=("$!")
for pid in "${pids[@]}"; do wait "$pid" || true; done
say "  quatre cellules jouées"

stage publish-anchor-verdict
python3 - "$W" "$ART" "$EXPECTED_CODE_SHA" "$GAMES_PER_CELL" "$MIN_GAMES" \
  "$GEN2_MT_FLOOR" "$GEN2_D9_FLOOR" "$POOL_SHA" <<'PY'
import json
import math
import pathlib
import re
import sys

w, art = map(pathlib.Path, sys.argv[1:3])
code_sha = sys.argv[3]
games_per_cell, min_games = int(sys.argv[4]), int(sys.argv[5])
mt_floor, d9_floor = float(sys.argv[6]), float(sys.argv[7])
pool_sha = sys.argv[8]

# Ancres publiées dans PROJECT_RESULTS §3.4 pour gen2-mmto contre Scan. Elles
# ont été mesurées sur un moteur qui perdait toute partie atteignant une racine
# nulle : ce sont des planchers, pas des valeurs cibles.
ANCHORS = {"gen2-mt030": -155.0, "gen2-d9": -276.0}
FLOORS = {"gen2-mt030": mt_floor, "gen2-d9": d9_floor}
REGIMES = {"mt030": ("gen2-mt030", "turnover-mt030"),
           "d9": ("gen2-d9", "turnover-d9")}


def elo(rate):
    if rate is None or rate <= 0.0 or rate >= 1.0:
        return None
    return -400.0 * math.log10(1.0 / rate - 1.0)


cells = {}
for timing in sorted(w.glob("cell-*.timing")):
    name, rc, seconds = timing.read_text().split()
    rc, seconds = int(rc), int(seconds)
    log = (w / f"cell-{name}.log").read_text(errors="replace")
    tally = re.search(r"Jass=(\d+)\s+Scan=(\d+)\s+Draws=(\d+)", log)
    rate_m = re.search(r"Jass score rate:\s*([0-9.]+)", log)
    played = re.findall(r"^\s*game\s+(\d+):", log, re.M)
    wins, losses, draws = (
        tuple(int(g) for g in tally.groups()) if tally else (0, 0, 0))
    games = wins + losses + draws
    rate = float(rate_m.group(1)) if rate_m else None
    # Le motif qui a trahi le bug du coup nul : une cellule où presque chaque
    # partie finit par « no legal move from Jass-player » n'est pas une série
    # de défaites, c'est un moteur qui abandonne. On le compte pour qu'il ne
    # puisse plus passer inaperçu.
    forfeits = len(re.findall(r"no legal move from Jass", log))
    usable = rc == 0 and games >= min_games and rate is not None
    cells[name] = {
        "return_code": rc,
        "timed_out": rc == 124,
        "elapsed_s": seconds,
        "games_started": int(played[-1]) if played else 0,
        "games_scored": games,
        "wins": wins, "draws": draws, "losses": losses,
        "jass_forfeits": forfeits,
        "forfeit_share": round(forfeits / games, 3) if games else None,
        "score_rate": rate,
        "elo": round(elo(rate), 1) if elo(rate) is not None else None,
        "elo_ci95": round(800.0 / math.sqrt(games), 1) if games else None,
        "usable": usable,
    }

anchor_checks = {}
for name, floor in FLOORS.items():
    c = cells.get(name)
    if not c or not c["usable"]:
        anchor_checks[name] = {"at_or_above_floor": None,
                               "reason": "cell unusable"}
        continue
    anchor_checks[name] = {
        "at_or_above_floor": c["score_rate"] >= floor,
        "floor": floor,
        "observed_rate": c["score_rate"],
        "historical_elo_floor": ANCHORS[name],
        "observed_elo": c["elo"],
    }

# Le contraste intra-job ne dépend d'aucune ancre : même binaire, même pool,
# même Scan, même cadence. C'est lui qui dit si le 0,050 était propre à
# TURNOVER ou commun aux deux modèles.
contrast = {}
for regime, (a, b) in REGIMES.items():
    ca, cb = cells.get(a), cells.get(b)
    if not (ca and cb and ca["usable"] and cb["usable"]):
        contrast[regime] = None
        continue
    contrast[regime] = {
        "gen2_rate": ca["score_rate"],
        "turnover_rate": cb["score_rate"],
        "turnover_minus_gen2_pp": round(
            100.0 * (cb["score_rate"] - ca["score_rate"]), 2),
    }

decided = [v["at_or_above_floor"] for v in anchor_checks.values()]
if any(v is None for v in decided):
    verdict = "SCAN_ANCHOR_INCONCLUSIVE_CELL_FAILED"
elif all(decided):
    verdict = "SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR"
elif not any(decided):
    verdict = "SCAN_HARNESS_STILL_BROKEN_ANCHOR_BELOW_FLOOR"
else:
    verdict = "SCAN_ANCHOR_PARTIAL_HUMAN_REVIEW"

payload = {
    "schema": 2,
    "verdict": verdict,
    "code_sha": code_sha,
    "protocol": {
        "reproduces": "cpx62-0571 / 0637 (gen2-mmto vs Scan)",
        "openings": "DILF combinations, first 20, sha256=" + pool_sha,
        "games_per_cell": games_per_cell,
        "min_games_per_cell": min_games,
        "egdb": False,
        "scan_book": "off",
        "scan_bb_size": 0,
        "jass_book": "built-in (unchanged from the historical runs)",
        "anchors_are_floors_not_targets": True,
    },
    "cells": cells,
    "anchor_checks": anchor_checks,
    "within_job_contrast": contrast,
    "reading": {
        "SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR":
            "the null-move fix holds; read within_job_contrast for TURNOVER",
        "SCAN_HARNESS_STILL_BROKEN_ANCHOR_BELOW_FLOOR":
            "a second defect remains; no vs-Scan number is usable yet",
    },
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "scan-anchor.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / f"VERDICT__{verdict}").write_text(verdict + "\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")

print("  cellule           n     W-D-L        score    Elo     forfaits  etat")
for name, c in sorted(cells.items()):
    if c["usable"]:
        state = "ok"
    elif c["timed_out"]:
        state = "TIMEOUT"
    elif c["return_code"]:
        state = f"ECHEC rc={c['return_code']}"
    else:
        state = f"n<{min_games}"
    print(f"  {name:16s} {c['games_scored']:>3}  "
          f"{c['wins']:>3}-{c['draws']:>3}-{c['losses']:>3}  "
          f"{str(c['score_rate']):>6}  {str(c['elo']):>7}  "
          f"{str(c['forfeit_share']):>8}  {state}")
print()
for name, chk in sorted(anchor_checks.items()):
    if chk["at_or_above_floor"] is None:
        print(f"  plancher {name}: INDECIDABLE ({chk['reason']})")
    else:
        print(f"  plancher {name}: historique {chk['historical_elo_floor']:+.0f} Elo "
              f"(score >= {chk['floor']}), observe {chk['observed_elo']:+.1f} Elo "
              f"({'tenu' if chk['at_or_above_floor'] else 'ENFONCE'})")
print()
for regime, c in sorted(contrast.items()):
    if c is None:
        print(f"  contraste {regime}: indisponible")
    else:
        print(f"  contraste {regime}: gen2 {c['gen2_rate']:.3f} vs "
              f"turnover {c['turnover_rate']:.3f} "
              f"({c['turnover_minus_gen2_pp']:+.2f} pp)")
print()
print(f"  verdict={verdict}")
PY
cp "$W"/cell-*.timing "$ART/cells/" 2>/dev/null || true
# Les dumps sont la seule facon d'autopsier une partie apres coup, et deux
# runs ont deja ete perdus faute de les avoir. 160 parties tiennent largement
# dans une archive.
(cd "$W" && tar czf "$ART/games.tar.gz" games-* 2>/dev/null) || true
VERDICT=$(ls "$ART" | sed -n 's/^VERDICT__//p' | head -1)
stage complete
say "$VERDICT promotion=false automatic_next_job=null"
