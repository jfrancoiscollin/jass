#!/usr/bin/env bash
# id: ccx33-0434-match-vs-scan-fair
# description: MATCH vs Scan CORRIGE (defauts du 0433 resolus). (1) jass AVEC egdb = sa VRAIE config (son eval fut
# entrainee avec finales adjugees egdb ; sans, il s'effondrait -> "no legal move") + Scan avec bitbases si presentes.
# (2) --pairs 2 seulement : a depth fixe les 2 moteurs sont DETERMINISTES => 9 ouvertures x 2 couleurs = 18 parties
# DISTINCTES (repeter = identique, inutile). Depth 11 partage. Probe Scan/egdb/bitbases et RAPPORTE la config exacte
# (si Scan n'a pas ses bitbases, l'egdb favorise jass -> dit clairement le biais). ⚠️ 18 parties + hors-plateau =
# ORDRE DE GRANDEUR (pas un verdict fin ; robustesse stat = randomiser les ouvertures = modif outil, plus tard).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0434-match-vs-scan-fair/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-vs-scan2; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
DEPTH=11; PAIRS=2
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz

# ---------- probes ----------
say "=== probes (Scan / egdb jass / bitbases Scan) ==="
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable a $SCAN_BIN"; ls -la /root/jass-scan/ 2>&1 | head | sed 's/^/  /' | tee -a "$RES"; exit 4; }
SCAN_BB=0
if ls /root/jass-scan/data/*bb* >/dev/null 2>&1 || ls /root/jass-scan/bb*/ >/dev/null 2>&1 || ls /root/jass-scan/data/ >/dev/null 2>&1; then
  SCAN_BB=6; say "  Scan bitbases : repertoire data/ present -> --scan-bb-size 6 (Scan AVEC finale)"
else say "  Scan bitbases : ABSENTES -> --scan-bb-size 0 (Scan SANS DB finale ; si jass a egdb, biais EN FAVEUR de jass)"; fi
EGDB_NOTE="OFF"
if [ -d /root/egdb_extracted ]; then export JASS_EGDB_PATH=/root/egdb_extracted; EGDB_NOTE="ON (/root/egdb_extracted)"; say "  jass egdb : present -> ON"; else say "  jass egdb : ABSENT -> jass SANS finale (il s'effondrera comme au 0433)"; fi

# ---------- build jass AVEC egdb (memes extras que le champion) ----------
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass (egdb ON, extras du champion) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log" | sed 's/^/  /'; exit 6; }
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || say "  WARN: 'EXTERNAL EGDB ENABLED' absent du cmake (egdb peut ne pas etre compile)"
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log" | sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion 3e-5 absent"; exit 4; }
say "# champion = w32 fit L2=3e-5 @35M"

# ---------- match ----------
say "=== MATCH FAIR : depth ${DEPTH} (partage) | ${PAIRS} paires = 18 parties distinctes | jass egdb=${EGDB_NOTE} | scan-bb=${SCAN_BB} ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
    --scan-bb-size "$SCAN_BB" --depth "$DEPTH" --pairs "$PAIRS" 2>&1 | tee "$W/match.log" | tail -28 | sed 's/^/  /' | tee -a "$RES"

# ---------- resume + comparaison au 0433 (no-DB both) ----------
say "=== RESUME ==="
python3 - "$W/match.log" <<'PY' 2>/dev/null | tee -a "$RES" || say "(voir match.log)"
import re,sys,math
t=open(sys.argv[1]).read()
s=re.findall(r'score[^0-9]*([01]?\.\d+)', t, re.I)
if s:
    sc=float(s[-1]); elo=-400*math.log10(1/sc-1) if 0<sc<1 else float('nan')
    print(f"  score champion vs Scan = {sc:.3f}  (~{elo:+.0f} Elo)  [18 parties, ordre de grandeur]")
else: print("  (score non parse — lire ci-dessus)")
PY
say "# RAPPEL 0433 (no-DB des 2 cotes, jass handicape finale) = 0.056. Ce match-ci (jass egdb) = la vraie config jass."
say "# Lecture : l'ecart 0433->0434 = l'effet egdb ; le score 0434 = ou en est jass *en vrai* vs Scan (a +-0.12 pres)."
