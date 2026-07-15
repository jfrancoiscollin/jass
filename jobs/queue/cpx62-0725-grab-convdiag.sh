#!/usr/bin/env bash
# id: cpx62-0725-grab-convdiag
# description: DIAG-EXPRESS — récupère les messages d'erreur conv_fixed_wdl du scratch cw-0724 (run échoué, die() ne rm pas
# → encore présent <180min) pour voir l'exception EXACTE (EOFError moteur-mort / ValueError parse / TimeoutError) sans rebuild.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0725-grab-convdiag/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0725-grab-convdiag/artefacts"
OUT=/root/grab-0725.txt; : > "$OUT"
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

echo "=== cw-0724 présent ? ===" >> "$OUT"
if [ -d /root/cw-0724 ]; then
  echo "OUI. contenu conv_* :" >> "$OUT"; ls -la /root/cw-0724/conv_onp_g1.*.json 2>/dev/null | head >> "$OUT"
  echo "" >> "$OUT"; echo "=== errors[:8] par shard (onp_g1) ===" >> "$OUT"
  for f in /root/cw-0724/conv_onp_g1.*.json; do
    [ -e "$f" ] || continue
    echo "--- $(basename "$f") ---" >> "$OUT"
    python3 - "$f" >> "$OUT" 2>&1 <<'PY'
import json,sys
try:
    j=json.load(open(sys.argv[1]))
    print("  n_pos=%s n_win=%s n_loss=%s n_draw=%s n_errors=%s"%(j.get("n_pos"),j.get("n_win"),j.get("n_loss"),j.get("n_draw"),j.get("n_errors")))
    for e in (j.get("errors") or [])[:8]: print("   ERR:",e)
except Exception as ex: print("  unreadable:",ex)
PY
  done
  echo "" >> "$OUT"; echo "=== tail d'un log conv shard (si présent) ===" >> "$OUT"
  for g in /root/cw-0724/conv_onp_g1.0.log /root/cw-0724/conv_onp_g1.1.log; do
    [ -e "$g" ] && { echo "--- $(basename "$g") ---" >> "$OUT"; tail -15 "$g" >> "$OUT" 2>&1; }
  done
else
  echo "NON — cw-0724 déjà nettoyé. Il faudra un diag qui rebuild." >> "$OUT"
fi
commit_to_main "$OUT" "$ARTREL/convdiag.txt" "0725 grab conv errors depuis cw-0724" && echo "committé"
