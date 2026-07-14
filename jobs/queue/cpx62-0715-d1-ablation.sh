#!/usr/bin/env bash
# id: cpx62-0715-d1-ablation
# description: PHASE D1 (mémo diag smoke 0714) — FIT-ABLATION, le test décisif de H1 (« les labels on-policy d'un pilote
# jeune SANS adjud sont du bruit qui remplit les patterns »). NB : le corpus 0714 n'a pas été committé (scratch effacé)
# ET n'avait pas de label_src → REGEN forcé, instrumenté (--label-src-out ONP/GYM/CAP) et COMMITTÉ (plus de perte).
# Puis 3 fits depuis le MÊME corpus (anchor 0.05) : (a) COMPLET (contrôle ~−45) ; (b) GYM+CAP seuls (oracle-truthful) ;
# (c) ONP seul (on-policy sans oracle). Chaque variante : conv_self + mini-A/B généraliste vs bootstrap (~600 games).
# LECTURES : (b) neutre ET (c)≤−45 => H1 CONFIRMÉE (bruit on-policy) => F1 adjud-escalier. (b) régresse => fit lui-même
# (D3). (c) neutre => H1 réfutée. Build egdb. AUCUN NNUE. Pas de bake.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0715.lock
if ! flock -n 9; then echo "ABORT 0715 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0715-d1-ablation/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0715-d1-ablation/artefacts"
W=/root/cw-0715; GEOM=/root/jass-geom32-0715
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
GAMES=2500; PLAYD=10; MAXPLIES=200; MINPC=36; SEEDFRAC=0.18; ARB_DEPTH=14
ANCHOR=0.05; MAXIT=60; CHUNK=1000000; CONV_DEPTH=10
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"; SHARD_TIMEOUT=7000

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
merge_labels(){ python3 - "$1" "$2" <<'PY'
import glob,sys
outp,pref=sys.argv[1],sys.argv[2]; body=bytearray()
for f in sorted(glob.glob(pref+"*")): body+=open(f,'rb').read()
open(outp,'wb').write(bytes(body)); print(len(body))
PY
}
conv_self(){ local pids=()  # $1=lab $2=pattern -> "conv_self n"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/conv_self.py --jass "$J" --pattern "$2" --defender-pattern "$W/gen2.pjtw" \
      --pool-file "$W/conversion_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
      --shard "$s" --nshards "$NSH" --out "$W/cs_$1.$s.json" >"$W/cs_$1.$s.log" 2>&1 & pids+=($!); done
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
gate_vs_boot(){ local pids=()  # $1=lab $2=cand_pattern -> "rate n elo"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$2" --jass-b "$J" --pattern-b "$W/bootstrap.pjtw" \
      --search-params-a "$QS" --search-params-b "$QS" --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" >"$W/g_$1.$s" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$W"/g_$1.* <<'PY'
import sys,math
a=d=b=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"{r:.4f} {g} {elo:+.0f}")
PY
}
fit_variant(){ # $1=lab $2=data_jnnw -> cand pattern à $W/cand_$1.pjtw
  "$J" --dump-eval-features "$2" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || { say "  [$1] DUMP FAIL"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$2" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  return 0
}

say "=== D1 FIT-ABLATION (test H1) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
for f in tools/scan_selfplay_gen.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do
  git show "origin/$SRC_BRANCH:$f" > "$f" 2>/dev/null || true; done
git show "origin/$SRC_BRANCH:data/conversion_pool.fen" > "$W/conversion_pool.fen" 2>/dev/null || true
restore_src(){ git checkout -- src pattern_jass/src tools/calibrate_vs_scan.py pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py tools/scan_selfplay_gen.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
grep -q label-src-out tools/scan_selfplay_gen.py || { say "ABORT: scan_selfplay_gen SANS --label-src-out (mauvaise branche)"; restore_src; exit 5; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/scan_selfplay_gen.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0715 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb (v4) ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0715 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
say "  ✓ build egdb + bootstrap + pool=$(grep -c . "$W/conversion_pool.fen") ; egdb=$EGDIR"

# --- REGEN labellisé (mêmes seeds/volume que 0714) + COMMIT (survie) ---
say ""; say "=== regen T1 labellisé (bootstrap + gymnase + cap-arbiter + --label-src-out) — ${GAMES}×${NSH} ==="
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/bootstrap.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$s" --games "$GAMES" --max-plies "$MAXPLIES" --min-pieces "$MINPC" \
    --sample-every 1 --depth "$PLAYD" --seed 71400 --nshards "$NSH" --shard "$s" \
    --seed-pool "$W/conversion_pool.fen" --seed-frac "$SEEDFRAC" --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \
    --label-src-out "$W/lab.$s" >"$W/sp-$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
NPOS=$(merge_jnnw "$W/wdl.jnnw" "$W/sp."); NLAB=$(merge_labels "$W/lab.jnnw.labels" "$W/lab.")
[ "$NPOS" = "$NLAB" ] || { say "ABORT: désalignement corpus/labels ($NPOS != $NLAB)"; restore_src; exit 8; }
# split en 3 sous-corpus par label
python3 - "$W/wdl.jnnw" "$W/lab.jnnw.labels" "$W/full.jnnw" "$W/oracle.jnnw" "$W/onp.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
corp,lab,full,oracle,onp=sys.argv[1:6]; REC=38
b=open(corp,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; L=open(lab,'rb').read()
body=b[8:]; orc=bytearray(); onpb=bytearray(); no=nn=0
for i in range(n):
    rec=body[i*REC:(i+1)*REC]; t=L[i]
    if t in (1,2): orc+=rec; no+=1
    else: onpb+=rec; nn+=1
open(full,'wb').write(b); # full = tel quel
open(oracle,'wb').write(b'JNNW'+struct.pack('<I',no)+bytes(orc))
open(onp,'wb').write(b'JNNW'+struct.pack('<I',nn)+bytes(onpb))
import collections; dist=dict(collections.Counter(L))
print(f"  corpus={n} ; ONP={dist.get(0,0)} GYM={dist.get(1,0)} CAP={dist.get(2,0)} ; oracle(GYM+CAP)={no} on-policy={nn}")
PY
# commit corpus + labels (survie future)
gzip -c "$W/wdl.jnnw" > "$ART/corpus_T1.jnnw.gz"; gzip -c "$W/lab.jnnw.labels" > "$ART/corpus_T1.labels.gz"
commit_to_main "$ART/corpus_T1.jnnw.gz" "$ARTREL/corpus_T1.jnnw.gz" "0715 corpus T1 labellisé (survie)" >/dev/null 2>&1||true
commit_to_main "$ART/corpus_T1.labels.gz" "$ARTREL/corpus_T1.labels.gz" "0715 labels T1" >/dev/null 2>&1||true

# --- 3 fits + gates (a=full, b=oracle, c=onp) ---
say ""; say "=== ablation : 3 fits (anchor $ANCHOR) + conv_self + généraliste vs bootstrap ==="
for V in full oracle onp; do
  say ""; say "--- variante $V ---"
  if fit_variant "$V" "$W/$V.jnnw"; then
    read CS NP1 < <(conv_self "$V" "$W/cand_$V.pjtw")
    read GR GN GE < <(gate_vs_boot "$V" "$W/cand_$V.pjtw")
    say "  [$V] conv_self=$CS (n=$NP1) | généraliste vs bootstrap : rate=$GR n=$GN elo=$GE"
    # D3 sanity : |Δw| EXTRA vs patterns
    python3 - "$W/bootstrap.pjtw" "$W/cand_$V.pjtw" "$V" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys,numpy as np
b0=open(sys.argv[1],'rb').read(); b1=open(sys.argv[2],'rb').read()
_,_,sc,npat,next_=struct.unpack_from('<IIIII',b0,0)
a0=np.frombuffer(b0,dtype='<i4',offset=20).astype(np.float64)/sc
a1=np.frombuffer(b1,dtype='<i4',offset=20).astype(np.float64)/sc
patm=slice(0,npat); extm=slice(2*npat,2*npat+next_)
dp=np.abs(a1[patm]-a0[patm]); de=np.abs(a1[extm]-a0[extm])
print(f"  [{sys.argv[3]}] |Δw| patterns: mean={dp.mean():.5f} nz_moved={(dp>1e-9).sum()} | EXTRA: mean={de.mean():.4f} max={de.max():.4f}")
PY
  fi
done

# --- VERDICT H1 ---
say ""; say "=== VERDICT D1 (H1 : on-policy jeune sans adjud = bruit) ==="
python3 - "$RES" <<'PY' | tee -a "$RES"
import re,sys
txt=open(sys.argv[1]).read()
g={}
for V in ("full","oracle","onp"):
    m=re.search(rf"\[{V}\] conv_self=([\d.]+).*?rate=([\d.]+).*?elo=([+-]?\d+)",txt,re.S)
    if m: g[V]=(float(m.group(1)),float(m.group(2)),int(m.group(3)))
if len(g)<3:
    print("  INCONCLUANT : une variante a échoué au fit/gate — relire les logs"); sys.exit(0)
print(f"  full   : conv_self={g['full'][0]} elo={g['full'][2]:+d}")
print(f"  oracle : conv_self={g['oracle'][0]} elo={g['oracle'][2]:+d}  (GYM+CAP seuls)")
print(f"  onp    : conv_self={g['onp'][0]} elo={g['onp'][2]:+d}  (on-policy seul)")
oe=g['oracle'][2]; ce=g['onp'][2]
if oe>=-15 and ce<=-30:
    v="H1 CONFIRMÉE : oracle ~neutre, on-policy régresse => le bruit vient du segment on-policy sans oracle => FIX F1 (adjud-escalier au régime jeune)"
elif oe< -30:
    v="H1 INSUFFISANTE : oracle régresse AUSSI => problème dans le FIT lui-même (anchor/échelle/POV) => D3, suspendre"
elif ce>=-15:
    v="H1 RÉFUTÉE : on-policy ~neutre => chercher ailleurs (D2 ventilation par phase)"
else:
    v=f"AMBIGU (oracle {oe:+d}, onp {ce:+d}) => trancher à JFC (regarder D3 |Δw| + ventilation)"
print(f"  => {v}")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0715 FIN D1 ablation : verdict H1 (voir RESULTS)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0715 FINI ==="
rm -rf "$W" "$GEOM"
