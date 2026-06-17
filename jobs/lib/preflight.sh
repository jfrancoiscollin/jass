# shellcheck shell=bash
# jobs/lib/preflight.sh — SYSTEMATIC compute pre-flight for GitOps jobs.
# ----------------------------------------------------------------------------
# Lesson from 0307 (an 8h+ overrun on a measurement job that should have taken
# ~3h): a job that under-estimates its own cost wastes a whole box-day and
# blocks the queue. Source this at the top of a job, DECLARE the planned work,
# and the helper prints a wall-clock estimate and ABORTS before launching if it
# exceeds the cap — so a runaway is caught in seconds, not hours.
#
# Usage (from a job, cwd = /root/jass):
#   source jobs/lib/preflight.sh
#   preflight_build 4                      # 4 cmake builds
#   preflight_train 3700000 4              # 4 evals on 3.7M rows
#   preflight_match $((12*2*3)) 1.0 140    # 72 games, 1.0s/move, ~140 plies
#   preflight_check                        # prints TOTAL, aborts if > cap
#
# Override the cap (minutes) or force past it:
#   PREFLIGHT_CAP_MIN=300 ...   |   PREFLIGHT_FORCE=1 ...
#
# Calibration constants are deliberately conservative (rather over- than
# under-estimate); tune from observed durations as the fleet changes.

PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"   # hard cap: abort beyond, unless PREFLIGHT_FORCE=1
PREFLIGHT_MIN_PER_MROW="${PREFLIGHT_MIN_PER_MROW:-4}"   # min per 1M rows per logistic train (lowmem)
PREFLIGHT_MIN_PER_BUILD="${PREFLIGHT_MIN_PER_BUILD:-4}" # min per cmake Release build of `jass`
_PF_TOTAL=0

_pf_add(){ _PF_TOTAL=$(python3 -c "print(round($_PF_TOTAL + ($1), 1))"); }

# preflight_match <n_games> <movetime_s> [avg_plies=140]
# A game ≈ movetime × plies seconds (only the side to move thinks each ply, but
# both sides do over the game, so ≈ one movetime per ply). avg_plies defaults
# high (140) because draws drift toward the ply cap — the 0307 trap.
preflight_match(){
  local g="${1:?n_games}" mt="${2:?movetime_s}" ap="${3:-140}"
  local mins; mins=$(python3 -c "print(round($g*$mt*$ap/60.0,1))")
  echo "  [preflight] matches: $g parties × ${mt}s × ~${ap} plies ≈ ${mins} min"
  _pf_add "$mins"
}

# preflight_train <rows> <n_models> [min_per_million]
preflight_train(){
  local rows="${1:?rows}" nm="${2:-1}" rate="${3:-$PREFLIGHT_MIN_PER_MROW}"
  local mins; mins=$(python3 -c "print(round($rows/1e6*$nm*$rate,1))")
  echo "  [preflight] train: $nm × $(printf '%d' "$rows") lignes @ ${rate}min/M ≈ ${mins} min"
  _pf_add "$mins"
}

# preflight_build [n_builds]
preflight_build(){
  local n="${1:-1}" mins
  mins=$(python3 -c "print(round($n*$PREFLIGHT_MIN_PER_BUILD,1))")
  echo "  [preflight] build ×$n ≈ ${mins} min"
  _pf_add "$mins"
}

# preflight_note <label> <minutes> — anything else (data gen, coverage, autopsy…)
preflight_note(){ echo "  [preflight] ${1}: ≈ ${2} min"; _pf_add "$2"; }

# preflight_check — print the total and abort (exit 9) if over the cap.
preflight_check(){
  echo "  [preflight] TOTAL estimé ≈ ${_PF_TOTAL} min  (cap ${PREFLIGHT_CAP_MIN} min)"
  local over; over=$(python3 -c "print(1 if $_PF_TOTAL > $PREFLIGHT_CAP_MIN else 0)")
  if [ "$over" = "1" ] && [ "${PREFLIGHT_FORCE:-0}" != "1" ]; then
    echo "  [preflight] ABORT — estimé > cap. Réduis pairs/conditions/max-plies/n_models,"
    echo "  [preflight]   ou relance avec PREFLIGHT_FORCE=1 (ou PREFLIGHT_CAP_MIN plus haut) si c'est voulu."
    exit 9
  fi
  echo "  [preflight] OK — sous le cap, lancement."
}

# mem_safe_jobs — parallel build width capped by RAM. Heavy C++ TUs (bitbase.cpp,
# scan_eval.cpp) peak ~1.5-2 GB per g++; on a low-RAM box -j$(nproc) OOMs and the
# assembler temp gets killed ("can't open /tmp/ccXXXX.s"). Cap at ~RAM/2 cores.
# Use: cmake --build B -j"$(mem_safe_jobs)".
mem_safe_jobs(){
  local n m j; n=$(nproc)
  m=$(awk '/MemTotal/{printf "%d",$2/1024/1024}' /proc/meminfo 2>/dev/null); [ -z "$m" ] && m=$n
  j=$(( m / 2 )); [ "$j" -lt 1 ] && j=1; [ "$j" -gt "$n" ] && j="$n"
  echo "$j"
}
