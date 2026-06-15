#!/usr/bin/env bash
# id: ccx33-0271-movegen-profile
# description: SOUS-PROFILAGE MOVEGEN (terrain pour l'optim). movegen = 31 % du temps/nœud (0095)
# mais on ne sait pas la répartition INTERNE. L'instrumentation existe déjà (-DJASS_TIME_BREAKDOWN :
# movegen_capture_ms / movegen_quiet_ms, BD_TIME aux lignes movegen.cpp:161/209). On build avec le
# flag, on pilote des positions STRATIFIÉES par phase (ouverture / milieu / finale-à-rois) via HUB,
# et on agrège le split CAPTURE-DFS vs QUIET par phase. → on saura quel levier de l'audit attaquer
# en premier (la DFS de captures est suspectée n°1 ; en finale, le movegen rois doit dominer).
# NB : l'instrumentation ajoute des timers (temps absolus gonflés) ; seul le SPLIT relatif compte.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0271-movegen-profile/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }

echo "=== build avec -DJASS_TIME_BREAKDOWN (king-aware pour gérer les finales à rois) ==="
rm -rf build-bd
cmake -S . -B build-bd -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_TIME_BREAKDOWN=ON \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" >"$ART/cmake.log" 2>&1
cmake --build build-bd -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-bd/jass
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy
EVAL=""
for c in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
         /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$c" ] && { EVAL="$c"; break; }
done

# --- échantillonne des positions STRATIFIÉES par phase + tag phase, en FEN HUB ---
python3 - "$MASTER" "$ART" <<'PY'
import sys, struct, random
import numpy as np
master, art = sys.argv[1], sys.argv[2]
raw = open(master,'rb').read(); n = struct.unpack_from('<I', raw, 4)[0]; REC=38
def pc(bb): return bin(bb).count('1')
def fen(wm,wk,bm,bk,stm):
    sq=lambda bb:[i+1 for i in range(50) if (bb>>i)&1]
    w=','.join([str(s) for s in sq(wm)]+[f'K{s}' for s in sq(wk)])
    b=','.join([str(s) for s in sq(bm)]+[f'K{s}' for s in sq(bk)])
    return f"{'W' if stm==0 else 'B'}:W{w}:B{b}"
rng=random.Random(7)
# buckets : opening>=30, midgame 15-29, endgame<=14 (préférer avec rois)
buckets={'opening':[], 'midgame':[], 'endgame':[]}
order=list(range(n)); rng.shuffle(order)
for i in order:
    off=8+i*REC; wm,wk,bm,bk=struct.unpack_from('<QQQQ',raw,off); stm=raw[off+32]
    tot=pc(wm)+pc(wk)+pc(bm)+pc(bk); kings=(wk|bk)!=0
    ph='opening' if tot>=30 else ('midgame' if tot>=15 else 'endgame')
    if ph=='endgame' and not kings and len(buckets['endgame'])>=2: continue  # privilégie finales à rois
    if len(buckets[ph])<6: buckets[ph].append(fen(wm,wk,bm,bk,stm))
    if all(len(v)>=6 for v in buckets.values()): break
with open(f"{art}/positions.tsv","w") as f:
    for ph,lst in buckets.items():
        for p in lst: f.write(f"{ph}\t{p}\n")
print("positions:", {k:len(v) for k,v in buckets.items()})
PY

# --- pilote HUB : 1 BREAKDOWN par position (mt 3s), tag phase via l'ordre ---
: > "$ART/tagged.tsv"
while IFS=$'\t' read -r ph pos; do
  IN="$ART/hub.txt"; { echo hello; echo "position fen $pos"; echo "go movetime 3000"; echo quit; } > "$IN"
  ${EVAL:+true} >/dev/null
  if [ -n "$EVAL" ]; then "$JASS" --nnue "$EVAL" < "$IN" >/dev/null 2>"$ART/err.log"; else "$JASS" < "$IN" >/dev/null 2>"$ART/err.log"; fi
  bd=$(grep '^BREAKDOWN' "$ART/err.log" | tail -1)
  [ -n "$bd" ] && echo -e "$ph\t$bd" >> "$ART/tagged.tsv"
done < "$ART/positions.tsv"

echo; echo "=========================================================="
echo "   ccx33-0271 — SOUS-PROFIL MOVEGEN (split capture/quiet par phase)"
echo "----------------------------------------------------------"
python3 - "$ART/tagged.tsv" <<'PY'
import sys, re
from collections import defaultdict
rows=defaultdict(lambda: defaultdict(float)); cnt=defaultdict(int)
keys=['eval_pct','movegen_pct','movegen_capture_pct','movegen_quiet_pct','apply_pct']
for line in open(sys.argv[1]):
    parts=line.rstrip('\n').split('\t'); ph=parts[0]; bd=parts[-1]
    d={k:float(v) for k,v in re.findall(r'(\w+)=([0-9.]+)',bd)}
    if 'movegen_pct' not in d: continue
    cnt[ph]+=1
    for k in keys: rows[ph][k]+=d.get(k,0.0)
hdr=f"  {'phase':9s} {'eval%':>6s} {'movegen%':>9s} {'  ↳capt%':>8s} {'↳quiet%':>8s} {'apply%':>7s}  (n)"
print(hdr); print("  "+"-"*58)
for ph in ['opening','midgame','endgame']:
    c=cnt.get(ph,0)
    if not c: continue
    a={k:rows[ph][k]/c for k in keys}
    print(f"  {ph:9s} {a['eval_pct']:6.1f} {a['movegen_pct']:9.1f} {a['movegen_capture_pct']:8.1f} {a['movegen_quiet_pct']:8.1f} {a['apply_pct']:7.1f}  ({c})")
PY
echo "----------------------------------------------------------"
echo "  Lecture : si movegen_capture% >> quiet% → attaquer la DFS captures (audit #1/#2)."
echo "  Si quiet% domine en finale → movegen rois (audit #5) ; sinon priorité = captures partout."
echo "  Cf docs/MOVEGEN_OPTIM.md pour le plan priorisé + garde-fou perft."
echo "=========================================================="
