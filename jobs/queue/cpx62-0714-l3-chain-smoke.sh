#!/usr/bin/env bash
# id: cpx62-0714-l3-chain-smoke
# description: SMOKE-TEST CHAÎNE L3 (T0→T1) — assemble les 4 bloquants en UN tour et valide la machinerie de bout en
# bout AVANT campagne. champion(0)=BOOTSTRAP (B4, matériel-conscient → remplace l'adjud dès T0). Gen tour-1 =
# scan_selfplay_gen piloté bootstrap + GYMNASE (B2 : --seed-pool conversion_pool --seed-frac 0.18, pairing) + ARBITRE-AU-
# CAP (B1 : --cap-arbiter d14 --egdb-dir, nulles d'épuisement adjugées). conv_self (B3, défenseur-fixe) mesuré comme
# JAUGE de conversion (bootstrap puis cand). Fit WDL ancré bootstrap → cand(T1). GATE compose cand vs bootstrap d9.
# MANIFEST tous compteurs. SMOKE PASS = compose (rate hors-IC) + compteurs d'oracle (positions, pool, gate n) > 0.
# Build egdb. AUCUN NNUE. Pas de bake (smoke). Note : escalier-adjud multi-tours = raffinement campagne, hors smoke.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0714.lock
if ! flock -n 9; then echo "ABORT 0714 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0714-l3-chain-smoke/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0714-l3-chain-smoke/artefacts"
W=/root/cw-0714; GEOM=/root/jass-geom32-0714
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
PROG="$W/PROGRESS.txt"; : > "$PROG"
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
GAMES=2500; PLAYD=10; MAXPLIES=200; MINPC=36; SEEDFRAC=0.18; ARB_DEPTH=14
CONV_POOL_GAMES=200; CONV_DEPTH=10; SHARD_TIMEOUT=7000
ANCHOR=0.05; MAXIT=60; CHUNK=1000000
NOPEN=300; PAIRS=2; DEPTH=9; NMIN=800; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+"*")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}
conv_self(){ # $1=label $2=champ_pattern -> imprime "conv_self n_pos"
  local pids=()
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/conv_self.py --jass "$J" --pattern "$2" --defender-pattern "$W/gen2.pjtw" \
      --pool-file "$W/conversion_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
      --shard "$s" --nshards "$NSH" --out "$W/cs_$1.$s.json" >"$W/cs_$1.$s.log" 2>&1 & pids+=($!)
  done
  wait "${pids[@]}"
  python3 - "$W"/cs_$1.*.json <<'PY'
import json,sys
P=Wn=0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); P+=j["n_pos"]; Wn+=j["n_win"]
    except Exception: pass
print(f"{(Wn/P if P else 0):.4f} {P}")
PY
}

say "=== SMOKE CHAÎNE L3 (T0=bootstrap → T1) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
# outils L3 (branche corpus, dont scan_selfplay_gen MODIFIÉ B1+B2)
for f in tools/scan_selfplay_gen.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do
  git show "origin/$SRC_BRANCH:$f" > "$f" 2>/dev/null || true
done
git show "origin/$SRC_BRANCH:data/conversion_pool.fen" > "$W/conversion_pool.fen" 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py tools/scan_selfplay_gen.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
for f in tools/scan_selfplay_gen.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do [ -s "$f" ] || { say "ABORT: $f absent de $SRC_BRANCH"; restore_src; exit 5; }; done
[ -s "$W/conversion_pool.fen" ] || { say "ABORT: conversion_pool.fen absent"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp && grep -q "has_any_capture" src/search.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/scan_selfplay_gen.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0714 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb (v4) ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0714 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
# champion(0) = BOOTSTRAP (B4), dims build-matched
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" | tee -a "$RES"
say "  ✓ build egdb ; champion(0)=bootstrap ; pool=$(grep -c . "$W/conversion_pool.fen") ; egdb=$EGDIR"

# --- JAUGE conversion AVANT (conv_self bootstrap) ---
say ""; say "=== conv_self(bootstrap) — jauge de conversion T0 (défenseur-fixe gen2) ==="
read CSB0 NB0 < <(conv_self boot "$W/bootstrap.pjtw"); say "  conv_self(bootstrap) = $CSB0 (n=$NB0)"

# --- GEN tour-1 : bootstrap self-play + gymnase(B2) + cap-arbiter(B1) ---
say ""; say "=== gen tour-1 : bootstrap + gymnase(seed-frac $SEEDFRAC) + cap-arbiter d$ARB_DEPTH — ${GAMES}×${NSH} ==="
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/bootstrap.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$s" --games "$GAMES" --max-plies "$MAXPLIES" --min-pieces "$MINPC" \
    --sample-every 1 --depth "$PLAYD" --seed 71400 --nshards "$NSH" --shard "$s" \
    --seed-pool "$W/conversion_pool.fen" --seed-frac "$SEEDFRAC" --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \
    >"$W/sp-$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
NPOS=$(merge_jnnw "$W/wdl.jnnw" "$W/sp.")
CAPFIRES=$(grep -h 'cap-arbiter d' "$W"/sp-*.log 2>/dev/null | grep -oE '[0-9]+ nulles' | grep -oE '[0-9]+' | awk '{s+=$1} END{print s+0}')
POOLGAMES=$(grep -h 'seed-pool (B2)' "$W"/sp-*.log 2>/dev/null | grep -oE '[0-9]+ parties gymnase' | grep -oE '[0-9]+' | awk '{s+=$1} END{print s+0}')
say "  positions générées : $NPOS ; parties gymnase (pool) : $POOLGAMES ; cap-arbiter fires : $CAPFIRES"
python3 - "$W/wdl.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]
d=sum(1 for i in range(n) if struct.unpack_from('<b',b,8+i*38+37)[0]==0)
print(f"  WDL {100*d//max(n,1)}% nulles (post cap-arbiter)")
PY

# --- FIT WDL ancré bootstrap → cand(T1) ---
say ""; say "=== fit WDL ancré bootstrap (wdl_finetune --anchor $ANCHOR) → cand(T1) ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; restore_src; exit 9; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$W/wdl.jnnw" --feat "$W/feat" --out "$W/cand.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
    --verify-jass "$J" --verify-n 60 >"$W/ft.log" 2>&1 || { say "FIT ABORT : $(tail -1 "$W/ft.log")"; restore_src; exit 9; }
grep -iE 'logloss|delta|wrote' "$W/ft.log"|tail -2|sed 's/^/  /'|tee -a "$RES"

# --- JAUGE conversion APRÈS (conv_self cand) ---
say ""; say "=== conv_self(cand T1) — la conversion a-t-elle monté ? ==="
read CSC1 NC1 < <(conv_self cand "$W/cand.pjtw"); say "  conv_self(cand) = $CSC1 (n=$NC1)  [bootstrap était $CSB0]"

# --- GATE compose : cand(T1) vs bootstrap(T0) d9 ---
say ""; say "=== GATE compose : cand(T1) vs bootstrap(T0) | d$DEPTH qs6 | ${NOPEN}op x$PAIRS ==="
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout 5000 python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/cand.pjtw" --jass-b "$J" --pattern-b "$W/bootstrap.pjtw" \
    --search-params-a "$QS" --search-params-b "$QS" --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" >"$W/g.$s" 2>&1 & pids+=($!)
done
wait "${pids[@]}"

# --- MANIFEST + SMOKE VERDICT ---
python3 - "$W/.man" "$NPOS" "$POOLGAMES" "$CAPFIRES" "$CSB0" "$CSC1" "$NMIN" "$W"/g.* <<'PY' | tee -a "$RES"
import sys,math,json
man=sys.argv[1]; npos=int(sys.argv[2]); pool=int(sys.argv[3]); cap=int(sys.argv[4])
csb=float(sys.argv[5]); csc=float(sys.argv[6]); nmin=int(sys.argv[7]); a=d=b=0
for f in sys.argv[8:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else float('nan')
se=0.5/(g**0.5) if g else 0; lo,hi=(r-1.96*se,r+1.96*se) if g else (0,0)
elo=-400*math.log10(1/r-1) if 0<r<1 else 0
manifest={"positions":npos,"pool_games":pool,"cap_arbiter_fires":cap,
          "conv_self_bootstrap":csb,"conv_self_cand":csc,"conv_self_delta":round(csc-csb,4),
          "gate_n":g,"gate_rate":round(r,4) if g else None,"gate_elo":round(elo),"gate_ic":[round(lo,3),round(hi,3)]}
json.dump(manifest,open(man,'w'),indent=2,ensure_ascii=False)
print("  === MANIFEST L3 (T0→T1) ===")
for k,v in manifest.items(): print(f"    {k} = {v}")
# SMOKE PASS = machinerie OK : compteurs oracle > 0 + gate produit n>=nmin + compose (lo>0.5)
counters_ok = npos>0 and pool>0 and g>=nmin
compose = g>=nmin and lo>0.5
print("  === SMOKE VERDICT ===")
print(f"    compteurs (positions>0, pool>0, gate n≥{nmin}) : {counters_ok}")
print(f"    conv_self : bootstrap {csb} → cand {csc} (Δ{csc-csb:+.4f})")
print(f"    gate compose cand vs bootstrap : rate={r:.4f} IC=[{lo:.3f},{hi:.3f}] elo~{elo:+.0f}")
if counters_ok and compose:
    print("    => SMOKE PASS ✓ : machinerie L3 de bout en bout OK + cand COMPOSE sur bootstrap → prête pour campagne")
elif counters_ok:
    print(f"    => MACHINERIE OK mais cand NE COMPOSE PAS hors-IC (rate {r:.3f}) : gen/fit à ajuster (volume smoke faible OK)")
else:
    print("    => SMOKE FAIL : un compteur d'oracle = 0 (positions/pool/gate) — corriger la machinerie")
PY
cp "$W/.man" "$ART/manifest_T1.json" 2>/dev/null || true
gzip -c "$W/cand.pjtw" > "$ART/cand-T1.pjtw.gz" 2>/dev/null || true
commit_to_main "$ART/manifest_T1.json" "$ARTREL/manifest_T1.json" "0714 manifest L3 T1" >/dev/null 2>&1||true
commit_to_main "$ART/cand-T1.pjtw.gz" "$ARTREL/cand-T1.pjtw.gz" "0714 cand T1 (smoke)" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0714 FIN smoke chaîne L3 : positions=$NPOS pool=$POOLGAMES cap=$CAPFIRES conv $CSB0->$CSC1" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0714 FINI ==="
rm -rf "$W" "$GEOM"
