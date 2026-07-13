#!/usr/bin/env bash
# id: cpx62-0702-scratch-t3-held-verdict
# description: CONCLURE 0675 — rendre le VERDICT COMPOSE que le gate n=0 (bug openings) avait avale.
# 0675 a DEJA paye+committe le gen (256k WDL adjud-tenu 4/24) ET le FIT (logloss 0.406817->0.399780,
# ancre T2 --anchor 0.05) : la sortie du fit = cand-diag.pjtw.gz (committe, 203KB). SEUL le compose-gate
# est mort (openings generees de positions >=38p degenerees => n=0). Ce job NE regenere RIEN, NE refit RIEN :
# il consomme cand-diag.pjtw.gz TEL QUEL et le gate vs T2 (=champion-current), d9 qs6, openings = head-300
# data/dilf_combinations.fen (source connue-bonne + disjointe, celle qui a donne n>0 sur 0689/0691).
# LECTURES PRE-ENGAGEES (memo JFC) : COMPOSE (lo>0.5) => c'etait le FADE ADJUD (b) => corriger E1 avant de grimper.
#                                    REGRESS (hi<0.5) => d10 vraiment EPUISE (a) => R2 d12.
#                                    in-IC => ambigu, refaire haut-N. n<NMIN => ABORT/INCONCLUANT (jamais "neutre").
# UN seul tour, pas de boucle. Gardes complets. AUCUN NNUE. Code src pull develop + arch_assert avant cmake.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0702.lock
if ! flock -n 9; then echo "ABORT 0702 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0702-scratch-t3-held-verdict/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0702-scratch-t3-held-verdict/artefacts"
W=/root/cw-0702; GEOM=/root/jass-geom32-0702
# --- hygiene disque : auto-clean cw-* stale (>3h, jamais le sien) + garde df ---
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # RES hors arbre git (rule 8ter)
PROG="$W/PROGRESS.txt"; : > "$PROG"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
CHAMP_GZ=jobs/results/cpx62-0674-scratch-chain/artefacts/champion-current.pjtw.gz          # = T2 (meilleur d10)
CAND_GZ=jobs/results/cpx62-0675-scratch-diag-adjud/artefacts/cand-diag.pjtw.gz             # = fit adjud-tenu 4/24 ancre T2 (0675, deja paye)
QS="qs_forcing_depth=6,qs_promo_depth=6"
NOPEN=300; PAIRS=2; NMIN=800; DEPTH=9; MAXPLIES=160; SHTIMEOUT=7200                          # 300op x2 x2col = ~1200 games -> IC ~+-20 elo
NSH=$((NCPU/2)); [ "$NSH" -lt 1 ] && NSH=1                                                   # NCPU/2 shards = zero oversub (patron 0689)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

START=$(date +%s)
monitor_loop(){ while [ ! -f "$W/.stopmon" ]; do sleep 600; [ -f "$W/.stopmon" ] && break
  local a=0 d=0 b=0 x y z
  for f in "$W"/pf.*; do [ -f "$f" ] || continue; read -r _ x y z < <(tail -1 "$f" 2>/dev/null); a=$((a+${x:-0})); d=$((d+${y:-0})); b=$((b+${z:-0})); done
  printf '[+%dmin] gate cand(adjud-tenu) vs T2 : W=%d D=%d L=%d n=%d\n' "$(( ($(date +%s)-START)/60 ))" "$a" "$d" "$b" "$((a+d+b))" >> "$PROG"
  commit_to_main "$PROG" "$ARTREL/PROGRESS.txt" "0702 gate n=$((a+d+b))" >/dev/null 2>&1||true; done; }

DFAVAIL=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== 0702 CONCLURE 0675 : gate cand(adjud-tenu 4/24, fit deja paye) vs T2 | d$DEPTH qs6 — nproc=$NCPU NSH=$NSH df=${DFAVAIL}Mo ==="
[ "${DFAVAIL:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

# ---- src perf-critique : pull develp (ref connue) + arch_assert AVANT cmake (garde-fou archi) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp \
         tools/jass_vs_jass_arch.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp tools/jass_vs_jass_arch.py 2>/dev/null||true; }
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS opts NPS (g_emasks)"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  say "  garde-fou archi ✓ : scan_eval=g_emasks + has_any_capture (search+movegen) = NPS-opt"; }
arch_assert

cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0702 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP (attendu 32, meme geom que 0674/0675)"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

# ---- inputs : T2 + candidat 0675 (deja committes, aucune regen/refit) ----
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champion-current (T2) introuvable"; restore_src; exit 4; }
git show "origin/main:$CAND_GZ"  | gunzip > "$W/cand.pjtw"  || { say "ABORT cand-diag (fit 0675) introuvable"; restore_src; exit 4; }
CE=$("$J" --eval-position "$W/champ.pjtw" "W:W31-50:B1-20" 2>&1|head -1)
AE=$("$J" --eval-position "$W/cand.pjtw"  "W:W31-50:B1-20" 2>&1|head -1)
say "  ✓ build+geom(NP=$NP v4) ; T2=champion-current (eval start=$CE) ; cand=fit-0675-adjud-tenu (eval start=$AE)"

# ---- openings : head-$NOPEN de dilf_combinations.fen (source CONNUE-BONNE + disjointe ; c'est le FIX du n=0 de 0675) ----
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
NO=$(grep -c . "$W/open.fen")
[ "$NO" -ge 50 ] || { say "ABORT openings=$NO (<50) : dilf_combinations.fen absent/vide"; restore_src; exit 8; }
say "  ✓ openings=$NO (dilf_combinations — la source n>0 de 0689/0691, FIX du n=0 de 0675) ; plan=$NO x$PAIRS x2col ~$((NO*PAIRS*2)) games"

# ---- GATE cand(adjud-tenu) vs T2, d$DEPTH qs6, wait-PIDS (jamais wait nu : monitor en fond) ----
say ""; say "=== GATE cand(adjud-tenu 4/24) vs T2 (champion-current) | d$DEPTH qs6 | ${NO}op x${PAIRS} x2 sur $NSH shards ==="
rm -f "$W/.stopmon"; monitor_loop & MON=$!; PIDS=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHTIMEOUT" python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
    --search-params-a "$QS" --search-params-b "$QS" --depth "$DEPTH" --pairs "$PAIRS" --max-plies "$MAXPLIES" \
    --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" --progress-file "$W/pf.$s" \
    >"$W/g.$s" 2>&1 &
  PIDS+=($!)
done
wait "${PIDS[@]}"                       # attend SEULEMENT les shards (pas le monitor) -> pas de deadlock 0665
touch "$W/.stopmon"; wait "$MON" 2>/dev/null || true

# ---- verdict (lectures pre-engagees) ----
python3 - "$W/.gate" "$NMIN" "$W"/g.* <<'PY'
import sys,math
outp=sys.argv[1]; nmin=int(sys.argv[2]); a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"):
                p=l.split()
                if len(p)>=4: a+=int(p[1]); d+=int(p[2]); b+=int(p[3])
    except Exception: pass
g=a+d+b
if g < nmin:
    open(outp,'w').write(f"  [GATE] n={g} < {nmin} => ABORT/INCONCLUANT (jamais 'neutre' : le gate n'a pas produit assez de games)\n  => RELANCER (diagnostiquer pourquoi n bas) — verdict NON rendu.\n")
else:
    r=(a+0.5*d)/g; se=0.5/(g**0.5); lo,hi=r-1.96*se,r+1.96*se
    elo=-400*math.log10(1/r-1) if 0<r<1 else 999
    if lo>0.5:
        vd=("COMPOSE (lo>0.5) => c'etait le FADE ADJUD (b) : 0674 a STOP a d10 parce que l'adjud avait fade "
            "TROP TOT, pas parce que d10 etait epuise. ACTION : corriger E1 (tenir adjud 4/24 + garde conversion-self) "
            "AVANT de grimper le profondeur.")
    elif hi<0.5:
        vd=("REGRESS (hi<0.5) => d10 vraiment EPUISE (a) : meme en tenant l'adjud, re-jouer d10 depuis T2 ne rend rien. "
            "ACTION : monter la profondeur R2 (d12, memo v2).")
    else:
        vd="in-IC (ambigu) : IC chevauche 0.5 => refaire en haut-N (plus d'openings/pairs) pour trancher (a) vs (b)."
    open(outp,'w').write(
        f"  [cand(adjud-tenu 4/24) vs T2 | d9] W={a} L={b} D={d} n={g} "
        f"rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}]\n  => {vd}\n")
PY
say ""; say "=== VERDICT 0675 (rendu via 0702) ==="
cat "$W/.gate" | tee -a "$RES"
echo "$(cat "$W/.gate" | tr '\n' ' ')" > "$W/.verdict"

restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0702 FIN — verdict 0675 rendu : $(head -1 "$W/.gate" | tr -s ' ' | cut -c1-90)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
gzip -c "$W/cand.pjtw" > "$ART/cand-adjud-tenu.pjtw.gz" 2>/dev/null && \
  commit_to_main "$ART/cand-adjud-tenu.pjtw.gz" "$ARTREL/cand-adjud-tenu.pjtw.gz" "0702 candidat adjud-tenu (copie 0675, gate rendu)" >/dev/null 2>&1 || true
say "=== fin 0702 ==="
rm -rf "$W" "$GEOM"
