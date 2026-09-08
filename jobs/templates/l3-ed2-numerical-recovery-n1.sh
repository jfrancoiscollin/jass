#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"
legacy="$JASS_CODE_DIR/jobs/templates/l3-ed2-paired-value-fit-v1.sh"
[ "$(git hash-object "$legacy")" = 7c4b077e53fbc8c035b96e47116bc055973d2431 ]
[ "$(grep -Fc 'jobs/tools/ed2_value_entrypoint.py' "$legacy")" -eq 1 ]
rendered="$JASS_RESULT_DIR/ed2-n1-launcher.sh"
[ ! -e "$rendered" ]
sed 's@jobs/tools/ed2_value_entrypoint.py@jobs/tools/ed2_value_recovery.py@' "$legacy" >"$rendered"
bash -n "$rendered"
exec /usr/bin/bash "$rendered"
