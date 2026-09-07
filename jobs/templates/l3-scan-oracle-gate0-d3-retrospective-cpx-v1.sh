#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
cd "$JASS_CODE_DIR"

SRC="jobs/templates/l3-scan-oracle-gate0-d3-retrospective-v1.sh"
TMP="$JASS_RESULT_DIR/scan-oracle-gate0-d3-retrospective-cpx-stage.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]); out=Path(sys.argv[2])
text=src.read_text(encoding='utf-8')
repls=[
    ('[ "$(hostname)" = User ] || die "Gate0 retrospective must run on HOME/User"',
     '[ "$(hostname)" = cpx62 ] || die "Gate0 retrospective must run on cpx62"'),
    ('''phase locate-runtime
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB data unavailable"
[ -d /root/egdb_intl ] || die "HOME egdb_intl source checkout unavailable"
''', '''phase locate-runtime
say "external_egdb=OFF mirror_d3_equal_node_runtime=1"
'''),
    ('    -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \\\n', ''),
    ('"$W/WDL_CONTROL.pjtw" "$EGDIR" 20000 CONTROL', '"$W/WDL_CONTROL.pjtw" - 20000 CONTROL'),
    ('"$W/WDL_CONTROL.pjtw" "$EGDIR" 20000 D3', '"$W/WDL_CONTROL.pjtw" - 20000 D3'),
]
for old,new in repls:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'Gate0 CPX preexecution patch drift count={count} old={old[:80]!r}')
    text=text.replace(old,new)
if 'EGDIR' in text or 'JASS_EGDB_SRC_DIR' in text or '-DJASS_EGDB=ON' in text:
    raise SystemExit('external EGDB residue after CPX patch')
out.write_text(text,encoding='utf-8')
PY
exec /usr/bin/bash "$TMP"
