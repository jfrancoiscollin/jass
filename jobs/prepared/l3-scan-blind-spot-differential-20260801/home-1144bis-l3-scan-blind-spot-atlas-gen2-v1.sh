#!/usr/bin/env bash
# id: home-1144bis-l3-scan-blind-spot-atlas-gen2-v1
# Retry of the Gen2 pass after home-1144 exposed a transport-only startup
# failure: five of sixteen 32cf referees timed out before their first position.
#
# The Python shim changes no collection setting.  It only spaces the sixteen
# full-run process starts by ten seconds so the 32cf models do not all fault in
# at once.  The collector's 1500-second scientific clock starts after the
# delay; the existing 600-second per-shard timeout margin covers the maximum
# 150-second stagger.
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set the SAME reviewed develop SHA as the EXACT arm}"
: "${JASS_RESULT_DIR:?}"

export JASS_OBJSTORE_REMOTE="${JASS_OBJSTORE_REMOTE:-r2:jass-data}"
export EXPECTED_JOB_ID="home-1144bis-l3-scan-blind-spot-atlas-gen2-v1"
export SCAN_BIN="/root/jass-scan/scan_linux"
export EXPECTED_SCAN_SHA256="a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864"
export EXPECTED_SCAN_EVAL_SHA256="0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"
export BUDGET_S=1500 PLAY_DEPTH=8 JUDGE_DEPTH=10 MAX_PLIES=160
export GAMES_CAP=100000 MIN_POSITIONS=200 SHARDS=16
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 NO_AUTOMATIC_CONTINUATION=1

STAGGER_DIR="$(mktemp -d "$JASS_RESULT_DIR/python-stagger.XXXXXX")"
export ATLAS_REAL_PYTHON3="$(command -v python3)"
export ATLAS_STARTUP_STAGGER_S=10
cat > "$STAGGER_DIR/python3" <<'SHIM'
#!/usr/bin/env bash
set -Eeuo pipefail

if [ "${1:-}" = "jobs/tools/scan_blind_spot_collector.py" ]; then
  seed=""
  previous=""
  for argument in "$@"; do
    if [ "$previous" = "--seed" ]; then
      seed="$argument"
      break
    fi
    previous="$argument"
  done
  case "$seed" in
    1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16)
      delay=$(( (seed - 1) * ATLAS_STARTUP_STAGGER_S ))
      printf '[atlas-startup] seed=%s delay_s=%s\n' "$seed" "$delay" >&2
      sleep "$delay"
      ;;
  esac
fi

exec "$ATLAS_REAL_PYTHON3" "$@"
SHIM
chmod +x "$STAGGER_DIR/python3"
export PATH="$STAGGER_DIR:$PATH"

exec timeout -k 120s 3600s \
  bash jobs/templates/l3-scan-blind-spot-atlas-v1.sh --variant gen2
