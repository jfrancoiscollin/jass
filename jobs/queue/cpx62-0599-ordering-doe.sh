#!/usr/bin/env bash
# id: cpx62-0599-ordering-doe
# description: DOE ordering history-prob (port Scan, develop 2edfbe84) — gate 0597 vert (jass survie<Scan), 0598 code sain
# (legacy byte-identical). Ici on tranche par les VRAIS gates du briefing. Preambule : jass_tests sur BASE => prouve que
# les 10 echecs de 0598 sont pre-existants (book-I/O, hors ordering). Puis 3 configs vs baseline(legacy) :
#   P1   = prob pur + E3   : hist_mode=1,hist_pure=1,hist_order_captures=1
#   P1nc = prob pur, NO E3 : hist_mode=1,hist_pure=1                       (isole E3 dans prob)
#   P2   = prob + machinerie jass + E3 : hist_mode=1,hist_order_captures=1
# METRIQUES : (A) first-move-cutoff LITTERAL (cut1/cutoffs via --search-profile) doit MONTER ; (B) node-EBF paired
# (nodes @ d9/d12) doit BAISSER (ordering => coupes plus tot, GRATUIT) ; (C) Elo movetime jass-vs-jass A/B vs legacy
# (mt0.1+0.3, dilf). GATE : cut1-rate ↑ ET nodes ↓ ET Elo ≥0.5 => candidat bake (puis controle generaliste avant bake reel).
# Un seul binaire PROB : baseline = PROB a params defaut (== BASE, byte-identical prouve). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0599-ordering-doe/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0599-ordering-doe/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-orddoe; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
PAIRS=2; NOPEN=60

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== DOE ordering history-prob — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true

# ---- BASE (main) + preuve que les echecs jass_tests sont pre-existants ----
git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null || true
cmake -S . -B "$W/base" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmb.log" 2>&1
cmake --build "$W/base" -j"$NCPU" --target jass jass_tests >"$W/bb.log" 2>&1 || { say "BASE BUILD FAIL"; tail -12 "$W/bb.log"|sed 's/^/  /'; exit 6; }
"$W/base/jass_tests" >"$W/base_tests.log" 2>&1 || true
BF=$(grep -oE '[0-9]+ / [0-9]+ assertions FAILED' "$W/base_tests.log" | head -1)
BOOK=$(grep -c 'test_scan_book.cpp' "$W/base_tests.log")
say "  [preambule] jass_tests BASE : $BF ; dont test_scan_book=$BOOK => $([ "$BOOK" -gt 0 ] && echo 'echecs book-I/O PRE-EXISTANTS (hors ordering) confirmes' || echo 'BASE clean ?!')"

# ---- PROB (overlay develop search files) ----
git show origin/develop:src/search.cpp > src/search.cpp
git show origin/develop:src/search_params.hpp > src/search_params.hpp
cmake -S . -B "$W/prob" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmp.log" 2>&1
cmake --build "$W/prob" -j"$NCPU" --target jass >"$W/bp.log" 2>&1 || { say "PROB BUILD FAIL"; tail -12 "$W/bp.log"|sed 's/^/  /'; git checkout -- src/search.cpp src/search_params.hpp; exit 6; }
J="$W/prob/jass"; git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null || true
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -40 "$DILF" | sed 's/#.*//' | tr -d ' ' | grep -E ':' > "$W/fp.txt"
head -n "$NOPEN" "$DILF" > "$W/open.fen"
say "  PROB build OK ; profil FEN=$(wc -l <"$W/fp.txt") ; Elo openings=$NOPEN pairs=$PAIRS"

# configs : tag|spec
CFGS=( "baseline|" "P1|hist_mode=1,hist_pure=1,hist_order_captures=1" "P1nc|hist_mode=1,hist_pure=1" "P2|hist_mode=1,hist_order_captures=1" )

# ---- (A)+(B) search-profile : first-move-cutoff rate + node-EBF ----
say ""; say "=== (A) first-move-cutoff (cut1/cutoffs) + (B) node-EBF (nodes) — search-profile @ d9 & d12 ==="
for e in "${CFGS[@]}"; do IFS='|' read -r tag spec <<<"$e"
  : > "$W/prof_$tag.txt"
  while IFS= read -r fen; do [ -z "$fen" ] && continue
    for d in 9 12; do
      "$J" --search-profile "$fen" "$d" 0 "$W/gen1.pjtw" ${spec:+"$spec"} 2>/dev/null \
        | grep -oE "nodes=[0-9]+ .*cut1=[0-9]+" | sed "s/^/$d /" >> "$W/prof_$tag.txt"
    done
  done < "$W/fp.txt"
done
python3 - "$W" "${CFGS[@]}" <<'PY' 2>&1 | tee -a "$RES"
import sys,re,statistics
W=sys.argv[1]; cfgs=[c.split("|")[0] for c in sys.argv[2:]]
def load(tag):
    rows={9:[],12:[]}
    for ln in open(f"{W}/prof_{tag}.txt"):
        m=re.search(r'^(\d+) nodes=(\d+).*cutoffs=(\d+) cut1=(\d+)',ln)
        if m: rows[int(m.group(1))].append((int(m.group(2)),int(m.group(3)),int(m.group(4))))
    return rows
base=load("baseline")
def med(xs): return statistics.median(xs) if xs else 0
print(f"  {'config':8s} | {'d9 nodes(ratio)':18s} {'d12 nodes(ratio)':18s} | {'d9 fmc':7s} {'d12 fmc':7s}")
for tag in cfgs:
    r=load(tag); line=f"  {tag:8s} |"
    for d in (9,12):
        nodes=[x[0] for x in r[d]]; bn=[x[0] for x in base[d]]
        mn=med(nodes); rb=med(bn); rat=(mn/rb) if rb else 0
        line+=f" {int(mn):8d}({rat:.3f})   "
    line+="|"
    for d in (9,12):
        co=sum(x[1] for x in r[d]); c1=sum(x[2] for x in r[d]); fmc=(c1/co) if co else 0
        line+=f" {fmc:.3f} "
    print(line)
print("  (node-EBF ratio<1 = arbre plus PETIT = meilleur ordering GRATUIT ; fmc plus haut = 1er coup coupe plus souvent)")
PY

# ---- (C) Elo movetime jass-vs-jass A/B vs baseline(legacy) ----
elo_ab(){ local tag="$1" spec="$2" mt="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen1.pjtw" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$mt" --search-params-a "$spec" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/open.fen" >"$W/e_${tag}_${mt}.$s" 2>&1 & done; wait
  python3 - "$tag" "$mt" "$W"/e_${tag}_${mt}.* <<'PY' 2>&1 | tee -a "$RES"
import sys,math; tag,mt=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
print(f"  [{tag} mt{mt}] A={a} B(legacy)={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} => {vd}")
PY
  rm -f "$W"/e_${tag}_${mt}.* ; }
say ""; say "=== (C) Elo movetime A/B (side A=config vs side B=legacy, dilf) ==="
for e in "${CFGS[@]}"; do IFS='|' read -r tag spec <<<"$e"; [ "$tag" = baseline ] && continue
  for mt in 0.1 0.3; do elo_ab "$tag" "$spec" "$mt"; done
done
say ""
say "  GATE : un config avec fmc↑ ET node-EBF ratio<1 ET Elo≥0.5 (hors-IC) => candidat => controle generaliste puis BAKE."
say "  fmc↑ + nodes↓ mais Elo≈ => l'ordering se resserre sans payer en jeu (le goulot n'etait pas la) => consigner, front clos."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0599 DOE ordering hist-prob : fmc littoral + node-EBF + Elo movetime (P1/P1nc/P2 vs legacy)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin DOE ordering ==="
