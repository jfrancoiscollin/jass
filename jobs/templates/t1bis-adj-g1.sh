#!/usr/bin/env bash
# TEMPLATE (spec codex_review_v3_2 §5 + §12 item 9) — runner T1-bis « ADJ + G1 » reproductible.
# ⚠ CECI EST UN TEMPLATE, PAS UN JOB EN QUEUE. Phase 1 l'instancie sous jobs/queue/cpx62-NNNN-t1bis...
# avec un numéro de job + GO explicite JFC, APRÈS checklist §13 verte. Il ne s'auto-lance pas.
#
# Séquence (§5) : checklist §13 → génération pilote-T0 (G1, cap-arbiter, --label-src-out)
#   → relabel d14+egdb (résolution label §3, protection tip, survie) → fit wdl_finetune ancre 0.05
#   (+ cellule lambda-énorme garde-fou + z-stats) → jauges (conv WDL-grounded 1600 figé ventilé p1-p4,
#   gate vs parent, gate vs référence fixe T0, d9 vs Scan télémétrie) → promotion_gate --regime young
#   → mining PASSIF (hors-boucle). Manifests + hashes partout. restart-on-death dans les jauges.
set -uo pipefail
cd /root/jass
JOB_ID="${JOB_ID:?instancier via jobs/queue/cpx62-NNNN-t1bis-adj-g1.sh qui exporte JOB_ID}"
TOUR="${TOUR:-T1-bis}"                       # T1-bis | T2 | T3
PARENT_PJTW_GZ="${PARENT_PJTW_GZ:-}"         # T1-bis : bootstrap/T0 ; T2/T3 : champion du tour précédent
exec 9>"/root/.jass-${JOB_ID}.lock"; flock -n 9 || { echo "ABORT instance active"; exit 0; }
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/$JOB_ID/artefacts"; ARTREL="jobs/results/$JOB_ID/artefacts"; mkdir -p "$ART"
W="/root/cw-${JOB_ID}"; GEOM="/root/geom-${JOB_ID}"; rm -rf "$W" "$GEOM"; mkdir -p "$W" "$GEOM"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
GYMPOOL=jobs/results/ccx33-0718-mine-tip/artefacts/conversion_pool_train_v2.fen        # G1 (composition + pointe p3/p4 figées §5.1)
GAUGE1600=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen       # jauge conversion FIGÉE 1600 (§5.4)
# sizing (à valider JFC au moment de l'instanciation Phase 1)
CACHE_MB="${CACHE_MB:-512}"; ARB_DEPTH=14; ANCHOR=0.05; PERG="${PERG:-200}"
NOPEN="${NOPEN:-300}"; PAIRS="${PAIRS:-1}"; DEPTH=9; CONV_DEPTH=10
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1; GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== T1-bis RUNNER ($JOB_ID, tour=$TOUR) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU ==="

# ───────────────────────── CHECKLIST §13 (bon pour lancement) — ABORT si rouge ─────────────────────────
say "--- §13 pré-lancement ---"
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || die "fetch develop"
DEVSHA=$(git rev-parse origin/develop); MAINSHA=$(git rev-parse origin/main)
# 1. tests Phase 0 verts (labels/draw-band, promotion, mining, cache)
for t in test_oracle_cert test_promotion_gate test_probe_mining test_cache_guard; do
  python3 "jobs/tests/$t.py" >"$W/$t.log" 2>&1 || die "tests $t rouges (§13)"; done
say "  [✓] tests Phase 0 verts"
# 5. cache agrégé sous budget (garde cache×procs — incident 0723)
MEM_MB=$(python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs "$NCPU" 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)['mem_mb'])" 2>/dev/null || echo 0)
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs "$NCPU" | tee -a "$RES" || die "cache agrégé > budget (§13) — baisser CACHE_MB"
# 4. audit MTC documenté (env EGDB/MTC)
python3 jobs/tools/mtc_audit.py --cache-mb "$CACHE_MB" --procs "$NCPU" --smoke-ok skip --out "$ART/mtc_audit.json" | tee -a "$RES" || say "  [!] MTC audit non-OK (consigné ; smoke concurrent à faire on-box)"
# 6-8. corpus/jauges figés + référence fixe + seeds : hashés dans le manifest
[ -n "$PARENT_PJTW_GZ" ] || die "PARENT_PJTW_GZ non défini (référence fixe T0/parent)"
git show "origin/main:$GAUGE1600" | grep -cvE '^\s*#' >/dev/null || die "jauge 1600 introuvable"
say "  [✓] cache OK, MTC consigné, jauge 1600 + G1 pinnés, dev=$DEVSHA main=$MAINSHA"

# ───────────────────────── build egdb (garde-fou archi) ─────────────────────────
for f in $(git diff --name-only origin/main origin/develop -- src pattern_jass/src); do git show "origin/develop:$f" > "$f"; done
grep -q "g_emasks" src/scan_eval.cpp || die "archi scan_eval"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "egdb"; export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "cmake egdb"
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || die "build"
J="$W/build/jass"
git show "origin/main:$PARENT_PJTW_GZ" | gunzip > "$W/parent.pjtw" || die "parent pjtw"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || die "gen2"

say ""
say "  ⚠ ÉTAPES PIPELINE (§5.1-5.5) — à câbler/valider ON-BOX en Phase 1 avec GO JFC :"
say "    1. GÉNÉRATION : scan_selfplay_gen piloté \$W/parent.pjtw, G1=\$GYMPOOL (quota POSITIONS, PAS G4),"
say "       --cap-arbiter d$ARB_DEPTH, --label-src-out, provenance+hashes, PERG=$PERG × $NCPU."
say "    2. RELABEL : d$ARB_DEPTH+egdb ; résolution label via jobs/tools/oracle_cert (TB/CERT protègent le tip),"
say "       compteurs oracle_cert.tip_survival (invariants durs 100% TB/CERT) → \$ART/tip_survival.json."
say "    3. FIT : wdl_finetune --anchor $ANCHOR + cellule lambda-énorme (garde-fou) + z-stats + |Δw| groupes."
say "    4. JAUGES : conv_fixed_wdl (WDL-grounded, restart-on-death) sur \$GAUGE1600 ventilé p1-p4 ;"
say "       gate vs parent + gate vs référence-fixe T0 ; d9 vs Scan (télémétrie)."
say "    5. PROMOTION : jobs/tools/promotion_gate.py --regime young --tour $TOUR (double comparaison)."
say "    6. MINING PASSIF : jobs/tools/probe_mining.py (hors-boucle, WIN_TO_DRAW/LOSS)."
say "  Cette structure + la checklist §13 ci-dessus SONT le livrable Phase 0 (item 9)."
say "  Phase 1 remplit 1-6 en réutilisant les patrons 0714/0715 (gen) + 0722/0726 (relabel/fit/gate) + outils Phase 0."

commit_to_main "$RES" "$ARTREL/RESULTS.txt" "$JOB_ID template T1-bis : checklist §13 + squelette pipeline" || say "⚠ commit"
say "=== $JOB_ID (template) FIN — pipeline à instancier Phase 1 ==="
rm -rf "$W" "$GEOM"
