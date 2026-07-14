#!/usr/bin/env bash
# id: ccx33-0718-mine-tip
# description: G4-TIP (mémo « compute → pointe de la pyramide ») — GROSSIR le tip p3/p4 du gymnase, PAS la base.
# Découverte : le corpus T1 (3,4M pos) contient DÉJÀ 27 533 candidats tip uniques ON-DISTRIBUTION (marge-VALEUR 0/1 :
# p4_egal 15192, p3_mince 12341) → ×6,5 le tip actuel (~4,2k). AUCUNE perturbation synthétique. Certif d14+egdb rapide
# près de la frontière TB (0717 : 48k en ~7 min → ~0,04 s/pos). Pipeline : extract --val-margin-max 1 (balaye TOUT le
# corpus) → certif d14+egdb shardé → filter --value-adv (garde marge0 en enseignant le GAGNANT — les gains valeur-égale
# purs, le + dur, que l'ancien filtre-pièces droppait) → FUSION avec le pool existant (dédup canon) → RE-CARVE stratifié
# 400/palier (gel UNIQUE de la jauge conv_self AVANT le 1er tour nourri : rien mesuré dessus = gratuit) → commits.
# Livrables main : conversion_pool_tip.fen + conversion_pool_train_v2.fen + conv_self_eval_strat_v2.fen + manifests.
# Eval stratifié = disjoint dur du training + ∩thermo=∅. Build egdb. AUCUN NNUE. OFFLINE (ne touche pas la boucle).
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0718.lock
if ! flock -n 9; then echo "ABORT 0718 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0718-mine-tip/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0718-mine-tip/artefacts"
W=/root/cw-0718
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
POOL_TRAIN=jobs/results/ccx33-0717-mine-pool/artefacts/conversion_pool_train.fen
EVAL_STRAT=jobs/results/ccx33-0717-mine-pool/artefacts/conv_self_eval_strat.fen
EVAL_FLAT=jobs/results/ccx33-0717-mine-pool/artefacts/conv_self_eval_set.fen
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
NCAND=30000; MAX_OVER=3; VMAX=1; ARB_DEPTH=14; PER_PAL=400; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== G4-TIP MINAGE p3/p4 ON-DISTRIBUTION — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show "origin/$SRC_BRANCH:tools/mine_conversion_pool.py" > tools/mine_conversion_pool.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src 2>/dev/null||true; rm -f tools/mine_conversion_pool.py; }
[ -s tools/mine_conversion_pool.py ] || { say "ABORT: mine_conversion_pool.py absent"; restore_src; exit 5; }
grep -q "val_margin_max" tools/mine_conversion_pool.py || { say "ABORT: outil sans --val-margin-max (corpus branch pas à jour)"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/mine_conversion_pool.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0718 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0718 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }

# --- extract TIP : marge-VALEUR ≤ VMAX (0/1), balaye TOUT le corpus (on-distribution) ---
say ""; say "=== extract TIP (marge-VALEUR ≤$VMAX = p4_egal/p3_mince, HORS-TB 8..10, balaye 3,4M pos) ==="
python3 tools/mine_conversion_pool.py extract --corpus "$W/corpus.jnnw" --out "$W/tip.jnnw" \
  --n-cand "$NCAND" --max-over "$MAX_OVER" --min-adv 0 --val-margin-max "$VMAX" | tee -a "$RES"
NCA=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/tip.jnnw','rb').read(8)[4:8])[0])")

# --- certif d14+egdb, shardé (timeout par shard, wait sur PIDs collectés) ---
say ""; say "=== certif d$ARB_DEPTH+egdb sur $NCA candidats tip ($NSH shards) ==="
python3 - "$W/tip.jnnw" "$W/cc" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3])
for s in range(nsh):
    idx=[i for i in range(n) if i%nsh==s]
    out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out)
PY
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout 3000 "$J" --deep-relabel "$W/cc.$s.jnnw" "$W/cc_rel.$s.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
python3 - "$W/certified.jnnw" "$W/cc_rel" <<'PY'
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*.jnnw")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print("certified:",tot)
PY

# --- filter --value-adv : garde marge0 (enseigne le gagnant) ; eval-n 0 = tout au pool tip brut ---
say ""; say "=== filter --value-adv (WIN camp valeur-avantagé + marge0→gagnant) ==="
git show "origin/main:$EVAL_STRAT" > "$W/estrat.fen" 2>/dev/null || : > "$W/estrat.fen"
git show "origin/main:$EVAL_FLAT"  > "$W/eflat.fen"  2>/dev/null || : > "$W/eflat.fen"
cat "$W/estrat.fen" "$W/eflat.fen" > "$W/frozen_eval.fen"   # dédup vs jauges déjà figées
python3 tools/mine_conversion_pool.py filter --certified "$W/certified.jnnw" --thermo data/pcblues_thermometre.fen \
  --eval-set-in "$W/frozen_eval.fen" --value-adv --min-adv 0 --eval-n 0 \
  --out-pool "$ART/conversion_pool_tip.fen" --out-eval "$W/unused_eval.fen" --manifest "$ART/tip_manifest.json" 2>&1 | tee -a "$RES" \
  || { say "ABORT filter"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0718 ABORT filter"; exit 8; }
NTIP=$(grep -cvE '^\s*#' "$ART/conversion_pool_tip.fen" 2>/dev/null||echo 0)
[ "${NTIP:-0}" -ge 200 ] || { say "ABORT: tip certifié n=$NTIP < 200 (échec, pas neutre)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0718 ABORT tip n=$NTIP"; exit 9; }
say "  tip certifié (WIN camp-avantagé) = $NTIP positions"

# --- FUSION (pool existant + tip) dédupliqué canon → RE-CARVE stratifié 400/palier ---
say ""; say "=== fusion (train+evals+tip) dédup canon → re-carve stratifié $PER_PAL/palier ==="
git show "origin/main:$POOL_TRAIN" > "$W/train.fen"
python3 - "$W/train.fen" "$W/estrat.fen" "$W/eflat.fen" "$ART/conversion_pool_tip.fen" "$W/merged.fen" <<'PY'
import sys; sys.path.insert(0,'tools'); import mine_conversion_pool as M
seen=set(); out=[]
for p in sys.argv[1:-1]:
    for ln in open(p):
        if ln.startswith('#'): continue
        fen=ln.split('#',1)[0].strip()
        if not fen: continue
        c=M.canon(fen)
        if c in seen: continue
        seen.add(c); out.append(fen)
open(sys.argv[-1],'w').write('\n'.join(out)+'\n'); print("fusion dédup:",len(out))
PY
python3 tools/mine_conversion_pool.py carve --pool "$W/merged.fen" --per-palier "$PER_PAL" \
  --out-eval "$ART/conv_self_eval_strat_v2.fen" --out-train "$ART/conversion_pool_train_v2.fen" \
  --manifest "$ART/carve_v2_manifest.json" 2>&1 | tee -a "$RES"
# assertion disjonction dure (n=0 = échec)
python3 - "$ART/conv_self_eval_strat_v2.fen" "$ART/conversion_pool_train_v2.fen" <<'PY' | tee -a "$RES"
import sys; sys.path.insert(0,'tools'); import mine_conversion_pool as M
def load(p): return set(M.canon(l.split('#')[0].strip()) for l in open(p) if not l.startswith('#') and l.strip())
ev,tr=load(sys.argv[1]),load(sys.argv[2])
assert len(ev)>0 and len(tr)>0, "ABORT: eval ou train vide"
assert not (ev&tr), f"ABORT: eval ∩ train = {len(ev&tr)}"
print(f"  ✓ DISJONCTION eval({len(ev)}) ∩ train({len(tr)}) = 0")
PY
NEV=$(grep -cvE '^\s*#' "$ART/conv_self_eval_strat_v2.fen" 2>/dev/null||echo 0)
NTR=$(grep -cvE '^\s*#' "$ART/conversion_pool_train_v2.fen" 2>/dev/null||echo 0)

commit_to_main "$ART/conversion_pool_tip.fen"        "$ARTREL/conversion_pool_tip.fen"        "0718 tip p3/p4 certifié on-distribution (n=$NTIP, marge-VALEUR≤$VMAX)" >/dev/null 2>&1||true
commit_to_main "$ART/tip_manifest.json"              "$ARTREL/tip_manifest.json"              "0718 tip manifest" >/dev/null 2>&1||true
commit_to_main "$ART/conversion_pool_train_v2.fen"   "$ARTREL/conversion_pool_train_v2.fen"   "0718 pool training v2 fusionné (tip grossi) = $NTR" >/dev/null 2>&1||true
commit_to_main "$ART/conv_self_eval_strat_v2.fen"    "$ARTREL/conv_self_eval_strat_v2.fen"    "0718 eval conv_self stratifié v2 FIGÉ $PER_PAL/palier (jauge du 1er tour nourri) = $NEV" >/dev/null 2>&1||true
commit_to_main "$ART/carve_v2_manifest.json"         "$ARTREL/carve_v2_manifest.json"         "0718 carve v2 manifest" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0718 FIN tip=$NTIP train_v2=$NTR eval_v2=$NEV (cand=$NCA)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0718 FINI ==="
rm -rf "$W"
