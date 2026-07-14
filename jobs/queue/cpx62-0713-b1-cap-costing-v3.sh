#!/usr/bin/env bash
# id: cpx62-0713-b1-cap-costing-v2
# description: CHIFFRAGE B1 v3 (épuisement = ply-cap + 25-move) — v1 (0710) INCONCLUANT : 0 caps car ouvertures=dilf_combinations (tactiques, résolvent
# en 0.19s). v2 corrige : (1) ouvertures = seeds MILIEU corpus-mix2M ≥36 pièces (comme la vraie gen) ; (2) pilote =
# BOOTSTRAP (éval jeune = PIRE cas, plus de caps ; c'est tôt dans la lignée que les caps abondent) ; (3) coût_d14
# DÉCOUPLÉ (mesuré sur échantillon ≤12 pièces = ce que sont les caps, toujours mesurable). Surcoût = plycap × coût_d14
# ÷ coût/partie vs +25%. Build egdb. AUCUNE intégration (chiffrage seul). AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0713.lock
if ! flock -n 9; then echo "ABORT 0713 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0713-b1-cap-costing-v2/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0713-b1-cap-costing-v2/artefacts"
W=/root/cw-0713
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
GAMES=1200; DEPTH=10; MAXPLIES=200; ARB_DEPTH=14; NSH="$NCPU"; SHARD_TIMEOUT=6000; THRESHOLD_PCT=25
OPEN_MINPC=36; D14SAMPLE=200; D14_MAXPC=12

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== CHIFFRAGE B1 v2 (seeds milieu + pilote bootstrap) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show "origin/$SRC_BRANCH:tools/cap_costing.py" > tools/cap_costing.py 2>/dev/null || true
git show "origin/$SRC_BRANCH:pattern_jass/tools/make_bootstrap_eval.py" > pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py tools/scan_selfplay_gen.py 2>/dev/null||true; rm -f tools/cap_costing.py pattern_jass/tools/make_bootstrap_eval.py; }
[ -s tools/cap_costing.py ] && [ -s pattern_jass/tools/make_bootstrap_eval.py ] || { say "ABORT: outils absents"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/cap_costing.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0713 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0713 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }

# --- ouvertures = seeds MILIEU (>=OPEN_MINPC pièces) + échantillon FINALES (<=D14_MAXPC) pour coût_d14 ---
python3 - "$W/seeds.jnnw" "$W/open.fen" "$W/d14sample.jnnw" "$GAMES" "$OPEN_MINPC" "$D14SAMPLE" "$D14_MAXPC" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38
openp,d14p=sys.argv[2],sys.argv[3]; ng=int(sys.argv[4]); minpc=int(sys.argv[5]); nd14=int(sys.argv[6]); maxpc=int(sys.argv[7])
def sqs(v): return [s for s in range(1,51) if (v>>(s-1))&1]
def pc(v):
    c=0
    while v: v&=v-1; c+=1
    return c
opens=[]; d14recs=[]
st1=max(1,n//(ng*4)); st2=max(1,n//(nd14*40))
for i in range(0,n,1):
    off=8+i*REC; wm,wk,bm,bk,stm=struct.unpack_from('<QQQQB',b,off); tp=pc(wm)+pc(wk)+pc(bm)+pc(bk)
    if len(opens)<ng and i%st1==0 and tp>=minpc:
        Wl=[f"K{s}" for s in sqs(wk)]+[str(s) for s in sqs(wm)]; Bl=[f"K{s}" for s in sqs(bm)]+[str(s) for s in sqs(bk)]
        opens.append(f"{'B' if stm else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}")
    if len(d14recs)<nd14 and i%st2==0 and 2<=tp<=maxpc:
        d14recs.append(b[off:off+REC])
    if len(opens)>=ng and len(d14recs)>=nd14: break
open(openp,'w').write("\n".join(opens)+"\n")
open(d14p,'wb').write(b'JNNW'+struct.pack('<I',len(d14recs))+b''.join(d14recs))
print(f"  ouvertures milieu (>= {minpc}pc) : {len(opens)} ; échantillon finales (<= {maxpc}pc) coût_d14 : {len(d14recs)}")
PY
NOPEN=$(grep -c . "$W/open.fen"); ND14=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/d14sample.jnnw','rb').read(8)[4:8])[0])")
say "  ✓ build egdb + gen2 + bootstrap ; pilote=BOOTSTRAP ; ouvertures=$NOPEN ; egdb=$EGDIR"

# --- (1) témoin gen (pilote bootstrap, seeds milieu) -> plycap_rate + coût/partie ---
say ""; say "=== témoin self-play BOOTSTRAP ($NOPEN ouvertures milieu, $NSH shards, d$DEPTH cap$MAXPLIES) ==="
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/cap_costing.py --jass "$J" --pattern "$W/bootstrap.pjtw" \
    --openings-file "$W/open.fen" --games "$NOPEN" --depth "$DEPTH" --max-plies "$MAXPLIES" \
    --shard "$s" --nshards "$NSH" --caps-out "$W/caps.$s.jnnw" --out "$W/cost.$s.json" \
    >"$W/cost.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
read NG NCAP PLYCAP SPG < <(python3 - "$W"/cost.*.json <<'PY'
import json,sys
ng=nc=0; sec=0.0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); ng+=j["n_games"]; nc+=j["n_cap"]; sec+=j["play_sec"]
    except Exception: pass
print(ng, nc, f"{(nc/ng if ng else 0):.4f}", f"{(sec/ng if ng else 0):.4f}")
PY
)
say "  parties=$NG  épuisement(ply-cap+25-move)=$NCAP  taux=$PLYCAP  coût/partie=${SPG}s"
python3 - "$W"/cost.*.json <<'PY' | tee -a "$RES"
import json,sys,collections
c=collections.Counter()
for f in sys.argv[1:]:
    try: c.update(json.load(open(f)).get("reasons",{}))
    except Exception: pass
print(f"  raisons de fin de partie (agrégées) : {dict(c)}")
PY

# --- (2) coût_d14 DÉCOUPLÉ : deep-relabel d14+egdb sur l'échantillon finales ---
say ""; say "=== coût_d14 (deep-relabel d$ARB_DEPTH+egdb sur $ND14 finales ≤${D14_MAXPC}pc) ==="
T0=$(date +%s.%N)
"$J" --deep-relabel "$W/d14sample.jnnw" "$W/d14sample_rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.log" 2>&1 || say "  (deep-relabel warn: $(tail -1 "$W/rel.log"))"
T1=$(date +%s.%N)
COSTD14=$(python3 -c "print(f'{($T1-$T0)/max($ND14,1):.4f}')")
say "  coût_d14/pos = ${COSTD14}s (sur $ND14 positions ≤${D14_MAXPC}pc)"

# --- (3) surcoût + VERDICT ---
say ""; say "=== VERDICT CHIFFRAGE B1 v2 (surcoût ≤ +${THRESHOLD_PCT}% ?) ==="
python3 - "$PLYCAP" "$SPG" "$COSTD14" "$THRESHOLD_PCT" "$NCAP" <<'PY' | tee -a "$RES"
import sys
plycap=float(sys.argv[1]); spg=float(sys.argv[2]); costd14=float(sys.argv[3]); thr=float(sys.argv[4]); ncap=int(sys.argv[5])
if spg<=0:
    print("  INCONCLUANT : coût/partie non mesuré"); sys.exit(0)
overhead = plycap * costd14 / spg; pct=100*overhead
print(f"  plycap_rate={plycap:.4f} ({ncap} caps)  coût/partie={spg:.3f}s  coût_d14/pos={costd14:.3f}s")
print(f"  SURCOÛT/tour = {plycap:.4f}×{costd14:.3f}/{spg:.3f} = {pct:.1f}%")
ok = pct <= thr
if plycap < 0.02:
    print(f"  ⚠ plycap bas ({plycap:.3f}) même pilote bootstrap+seeds milieu → l'arbitre coûte peu MAIS le mensonge ply-cap est aussi plus rare qu'estimé (~19% était young-eval fade-adjud). Surcoût={pct:.1f}%.")
print(f"  => {'ADMIS ('+f'{pct:.1f}% ≤ {thr:.0f}%'+') : INTÉGRER --cap-arbiter d14' if ok else f'DÉPASSE ({pct:.1f}% > {thr:.0f}%) : fallback d12 / arbitre ciblé |matériel| ambigu'}")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0713 FIN chiffrage B1 v2 : plycap=$PLYCAP coutd14=$COSTD14 spg=$SPG" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0713 FINI ==="
rm -rf "$W"
