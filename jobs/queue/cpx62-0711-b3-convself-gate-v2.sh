#!/usr/bin/env bash
# id: cpx62-0711-b3-convself-gate-v2
# description: GATE B3 v2 (défenseur-fixe) — re-valide conv_self après le confound self-play de 0708 (aveugle 0.88 >
# gen2 0.75, anti-corrélé). v2 : le champion testé joue le camp AVANTAGÉ d'une position gagnée du pool vs un DÉFENSEUR
# FIXE fort (gen2-mmto). GATE = MONOTONIE conv_self(zero) < conv_self(gen2) (un champion fort convertit PLUS des mêmes
# positions vs le même défenseur). Pool = corpus-mix2M filtré |Δ pièces| ≥ 3, échantillon. Sharded. PUR offline.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0711.lock
if ! flock -n 9; then echo "ABORT 0711 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0711-b3-convself-gate-v2/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0711-b3-convself-gate-v2/artefacts"
W=/root/cw-0711
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
POOL=300; LEAD=3; DEPTH=10; MAXPLIES=260; NSH="$NCPU"; SHARD_TIMEOUT=4000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== GATE B3 v2 conv_self défenseur-fixe — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show "origin/$SRC_BRANCH:tools/conv_self.py" > tools/conv_self.py 2>/dev/null || true
git show "origin/$SRC_BRANCH:pattern_jass/tools/make_bootstrap_eval.py" > pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
[ -s tools/conv_self.py ] && [ -s pattern_jass/tools/make_bootstrap_eval.py ] || { say "ABORT: outils absents"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }

say "=== build jass (v4) ==="
cmake -S . -B "$W/build" $FLAGS >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0711 BUILD FAIL"; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/zero.pjtw" --like "$W/gen2.pjtw" --men 0 --king 0 --king-center 0 --mobility 0 >/dev/null
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }

# --- pool : positions gagnées (|Δ pièces| >= LEAD) échantillonnées de corpus-mix2M ---
python3 - "$W/seeds.jnnw" "$W/pool.fen" "$POOL" "$LEAD" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38
outp=sys.argv[2]; want=int(sys.argv[3]); lead=int(sys.argv[4])
def sqs(v): return [s for s in range(1,51) if (v>>(s-1))&1]
def pc(v):
    c=0
    while v: v&=v-1; c+=1
    return c
step=max(1,n//(want*8)); out=[]
for i in range(0,n,step):
    off=8+i*REC
    wm,wk,bm,bk,stm=struct.unpack_from('<QQQQB',b,off)
    wp=pc(wm)+pc(wk); bp=pc(bm)+pc(bk)
    if abs(wp-bp)<lead: continue
    Wl=[f"K{s}" for s in sqs(wk)]+[str(s) for s in sqs(wm)]
    Bl=[f"K{s}" for s in sqs(bm)]+[str(s) for s in sqs(bk)]
    out.append(f"{'B' if stm else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}")
    if len(out)>=want: break
open(outp,'w').write("\n".join(out)+"\n")
print(f"  pool positions gagnées (|Δ|>={lead}) : {len(out)}")
PY
NPOOL=$(grep -c . "$W/pool.fen"); say "  ✓ build ; pool=$NPOOL ; défenseur FIXE=gen2-mmto ; depth=$DEPTH"

run_champ(){ # $1=label $2=champ_pattern
  local lab="$1" pat="$2"; local pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout "$SHARD_TIMEOUT" python3 tools/conv_self.py --jass "$J" --pattern "$pat" \
      --defender-pattern "$W/gen2.pjtw" --pool-file "$W/pool.fen" --depth "$DEPTH" --lead "$LEAD" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NSH" --out "$W/cs_${lab}.$s.json" \
      >"$W/cs_${lab}.$s.log" 2>&1 & pids+=($!)
  done
  wait "${pids[@]}"
  python3 - "$W"/cs_${lab}.*.json <<'PY'
import json,sys
P=Wn=D=L=0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); P+=j["n_pos"]; Wn+=j["n_win"]; D+=j["n_draw"]; L+=j["n_loss"]
    except Exception: pass
cs=Wn/P if P else float('nan')
print(f"{P} {Wn} {D} {L} {cs:.4f}")
PY
}
say ""; say "=== conv_self (champion convertit vs défenseur FIXE gen2) : zero vs gen2 ==="
read ZP ZW ZD ZL ZCS < <(run_champ zero "$W/zero.pjtw" | tail -1); say "  champion=zero : pos=$ZP win=$ZW draw=$ZD loss=$ZL conv_self=$ZCS"
read GP GW GD GL GCS < <(run_champ gen2 "$W/gen2.pjtw" | tail -1); say "  champion=gen2 : pos=$GP win=$GW draw=$GD loss=$GL conv_self=$GCS"

say ""; say "=== VERDICT GATE B3 v2 (monotonie conv_self, défenseur fixe) ==="
python3 - "$ZCS" "$ZP" "$GCS" "$GP" <<'PY' | tee -a "$RES"
import sys
zcs=float(sys.argv[1]); zp=int(sys.argv[2]); gcs=float(sys.argv[3]); gp=int(sys.argv[4])
if zp<30 or gp<30:
    print(f"  INCONCLUANT : n_pos bas (zero={zp}, gen2={gp}) — élargir pool"); sys.exit(0)
mono = gcs > zcs
print(f"  conv_self : zero={zcs:.4f} (n={zp})  <  gen2={gcs:.4f} (n={gp}) ? => {'OUI ✓' if mono else 'NON ✗'}")
print(f"  => {'ADMIS — conv_self monotone (défenseur-fixe corrige le confound self-play) : instrument valide, pilote l escalier' if mono else 'ÉCHEC — encore non monotone : re-diagnostiquer'}")
PY
cp "$W/pool.fen" "$ART/won_pool.fen" 2>/dev/null || true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0711 FIN gate B3 v2 défenseur-fixe : zero=$ZCS gen2=$GCS (monotone attendu)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0711 FINI ==="
rm -rf "$W"
