#!/usr/bin/env bash
# id: cpx62-0722-recette-corrigee
# description: RECETTE CORRIGÉE L3 (suite F1/0721, défauts méthodo corrigés) — combine les 2 leviers confirmés :
# (ii) ADJUD-labels d14+egdb (stoppe la régression généraliste) + (iii) GYMNASE up-weighté (0718, 52k tip, labels
# d14+egdb) qui doit fournir le GAIN-conversion. 3 CELLULES sur positions APPARIÉES (fix 0721) : on-policy / adjud-W0 /
# adjud-W(élevé) → effet-LABEL propre (on-policy vs adjud-W0, MÊMES positions) + effet-GYMNASE (W0 vs W-élevé).
# CORRECTIFS 0721 : (1) tools tirés de DEVELOP pinné (fin hybride multi-branches), SHA au manifeste ; (2) CORPUS APPARIÉ
# — on ne garde que les shards relabel RÉUSSIS et le contrôle on-policy est bâti sur EXACTEMENT ces positions (les fits
# ne diffèrent QUE par le label) ; (3) diff labels PAR-SHARD (aligné, % valide) ; (4) log succès par-shard.
# Corpus committé (sous-échantillon relabélisé, PAS de gen self-play). Build egdb. AUCUN NNUE. AUCUN bake.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0722.lock
if ! flock -n 9; then echo "ABORT 0722 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0722-recette-corrigee/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0722-recette-corrigee/artefacts"
W=/root/cw-0722; GEOM=/root/jass-geom32-0722
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
EVALSTRAT=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen
GYMPOOL=jobs/results/ccx33-0718-mine-tip/artefacts/conversion_pool_train_v2.fen
MAXIT=60; CHUNK=1000000; CONV_DEPTH=10; ANCHOR=0.05; ARB_DEPTH=14
N_TARGET=120000; GYM_W=4
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
conv_self(){ local pids=()  # $1=lab $2=pattern -> "conv n"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/conv_self.py --jass "$J" --pattern "$2" --defender-pattern "$W/gen2.pjtw" \
      --pool-file "$W/conv_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
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
gate_vs_boot(){ local pids=()  # $1=lab $2=pattern -> "rate n elo"
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
fit_a(){ # $1=lab $2=data -> $W/cand_$1.pjtw
  "$J" --dump-eval-features "$2" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || { say "  [$1] DUMP FAIL"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$2" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  return 0
}

say "=== RECETTE CORRIGÉE L3 (adjud-full + gymnase, positions APPARIÉES) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
DEVSHA=$(git rev-parse origin/develop)
# ⭐ FIX repro : TOUS les outils tirés de DEVELOP pinné (fin hybride multi-branches)
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
for f in pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py \
         tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py tools/promotion_gate.py; do
  git show "origin/develop:$f" > "$f" || { echo "ABORT: $f absent de develop"; exit 5; }
done
restore_src(){ git checkout -- src pattern_jass/src pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py tools/promotion_gate.py 2>/dev/null||true; }
say "  develop pinné SHA=$DEVSHA (tools L3 consolidés)"
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py tools/promotion_gate.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0722 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0722 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }
git show "origin/main:$EVALSTRAT" | grep -vE '^\s*#' | awk 'NR%4==1' > "$W/conv_pool.fen"
git show "origin/main:$GYMPOOL" | grep -vE '^\s*#' | sed 's/#.*//' | awk 'NF' > "$W/gym.fen"
NCP=$(grep -cvE '^\s*#' "$W/conv_pool.fen"); NGF=$(wc -l < "$W/gym.fen")
say "  ✓ build egdb + bootstrap + corpus T1 + jauge conv ($NCP) + gymnase FEN ($NGF)"

# --- sous-échantillon corpus → shards (stride déterministe) ---
say ""; say "=== sous-échantillon $N_TARGET + relabel d$ARB_DEPTH+egdb ($NSH shards) — CORPUS APPARIÉ ==="
python3 - "$W/full.jnnw" "$W/sh" "$NSH" "$N_TARGET" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3]); k=int(sys.argv[4])
st=max(1,n//k); sel=list(range(0,n,st))[:k]                 # sous-échantillon déterministe
for s in range(nsh):
    idx=sel[s::nsh]                                          # shard s = 1 pos sur nsh du sous-échantillon
    out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out)
print("sous-échantillon:",len(sel))
PY
TOSH=3000
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$TOSH" "$J" --deep-relabel "$W/sh.$s.jnnw" "$W/sh_rel.$s.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
# --- APPARIEMENT : ne garder que les shards RÉUSSIS (count identique) ; construire onp_matched + adj_matched ---
python3 - "$W/sh" "$W/sh_rel" "$NSH" "$W/onp_matched.jnnw" "$W/adj_matched.jnnw" <<'PY' | tee -a "$RES"
import struct,sys,os
pref,prefr,nsh=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
def load(p):
    if not os.path.exists(p): return None
    b=open(p,'rb').read()
    if b[:4]!=b'JNNW': return None
    n=struct.unpack('<I',b[4:8])[0]; return b[8:8+n*REC], n
onp=bytearray(); adj=bytearray(); good=[]; changed=0; total=0
for s in range(nsh):
    o=load(f"{pref}.{s}.jnnw"); a=load(f"{prefr}.{s}.jnnw")
    if o is None or a is None or o[1]!=a[1]:
        print(f"  shard {s}: ÉCHEC (relabel manquant/incomplet) → EXCLU des 2 fits"); continue
    ob,ab_,n=o[0],a[0],o[1]; good.append(s)
    onp+=ob; adj+=ab_                                        # MÊMES positions, seul le label diffère
    for i in range(n):                                       # diff PAR-SHARD (aligné = % valide)
        if ob[i*REC+37]!=ab_[i*REC+37]: changed+=1
    total+=n
open(sys.argv[4],'wb').write(b'JNNW'+struct.pack('<I',total)+bytes(onp))
open(sys.argv[5],'wb').write(b'JNNW'+struct.pack('<I',total)+bytes(adj))
print(f"  shards réussis : {len(good)}/{nsh} | positions APPARIÉES = {total}")
print(f"  labels changés par l'adjud (PAR-SHARD, aligné) : {changed}/{total} = {100.0*changed/max(1,total):.1f}%")
PY
NMATCH=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/onp_matched.jnnw','rb').read(8)[4:8])[0])")
[ "${NMATCH:-0}" -ge 40000 ] || { say "ABORT: positions appariées n=$NMATCH < 40000 (trop de shards morts)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0722 ABORT appariement n=$NMATCH"; exit 9; }

# --- gymnase JNNW : FEN → pack → deep-relabel d14+egdb (labels conversion VRAIS) ---
say ""; say "=== gymnase JNNW ($NGF FEN → pack → relabel d$ARB_DEPTH+egdb) ==="
python3 - "$W/gym.fen" "$W/gym_raw.jnnw" <<'PY'
import struct,sys
def pack(fen):
    stm_c,wp,bp=fen.split(':'); stm=1 if stm_c.strip()[0]=='B' else 0
    def bits(part):
        men=king=0
        for t in part[1:].split(','):
            t=t.strip()
            if not t: continue
            if t[0]=='K': king|=1<<(int(t[1:])-1)
            else: men|=1<<(int(t)-1)
        return men,king
    wm,wk=bits(wp); bm,bk=bits(bp)
    return struct.pack('<QQQQ',wm,wk,bm,bk)+bytes([stm])+b'\x00'*5   # 32+1+5=38, wdl@37=0
out=bytearray(); n=0
for ln in open(sys.argv[1]):
    f=ln.strip()
    if not f: continue
    try: out+=pack(f); n+=1
    except Exception: pass
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(out)); print("gym packé:",n)
PY
pids=()
python3 - "$W/gym_raw.jnnw" "$W/gs" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3])
for s in range(nsh):
    idx=list(range(n))[s::nsh]; out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out)
PY
for s in $(seq 0 $((NSH-1))); do
  timeout 2000 "$J" --deep-relabel "$W/gs.$s.jnnw" "$W/gs_rel.$s.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/grel.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
python3 - "$W/gym.jnnw" "$W/gs_rel" <<'PY' | tee -a "$RES"
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; keep=bytearray(); dec=0; tot=0
for f in sorted(glob.glob(pref+".*.jnnw")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
    for i in range(n):
        tot+=1
        if body[i*REC+37]!=0: keep+=body[i*REC:(i+1)*REC]; dec+=1   # garde décisifs (WDL != 0)
open(outp,'wb').write(b'JNNW'+struct.pack('<I',dec)+bytes(keep)); print(f"  gymnase certifié décisif : {dec}/{tot}")
PY
NGYM=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/gym.jnnw','rb').read(8)[4:8])[0])")

# --- mix adjud + gymnase×W ---
python3 - "$W/adj_matched.jnnw" "$W/gym.jnnw" "$GYM_W" "$W/adj_gymW.jnnw" <<'PY'
import struct,sys
def rd(p): b=open(p,'rb').read(); return b[8:], struct.unpack('<I',b[4:8])[0]
ab,na=rd(sys.argv[1]); gb,ng=rd(sys.argv[2]); Wt=int(sys.argv[3])
body=bytearray(ab)+bytearray(gb)*Wt; tot=na+ng*Wt
open(sys.argv[4],'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print("mix:",tot)
PY

# --- 3 cellules (positions appariées) ---
say ""; say "--- cellules @$ANCHOR : on-policy / adjud-W0 / adjud-W$GYM_W (gymnase $NGYM ×$GYM_W) ---"
for spec in "onpolicy:$W/onp_matched.jnnw" "adjudW0:$W/adj_matched.jnnw" "adjudWhi:$W/adj_gymW.jnnw"; do
  lab="${spec%%:*}"; data="${spec#*:}"
  say ""; say "  · fit $lab (N=$(python3 -c "import struct;print(struct.unpack('<I',open('$data','rb').read(8)[4:8])[0])"))"
  if fit_a "$lab" "$data"; then
    read CS NP1 < <(conv_self "$lab" "$W/cand_$lab.pjtw"); read GR GN GE < <(gate_vs_boot "$lab" "$W/cand_$lab.pjtw")
    say "  [$lab] conv_self=$CS (n=$NP1) | gate vs bootstrap : rate=$GR n=$GN elo=$GE"
  fi
done

say ""; say "=== VERDICT RECETTE CORRIGÉE ==="
python3 - "$RES" "$NMATCH" "$NGYM" "$GYM_W" "$DEVSHA" "$ART/manifest.json" <<'PY' | tee -a "$RES"
import re,sys,json
RESF,NMATCH,NGYM,GYMW,DEVSHA,MANIF=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),sys.argv[5],sys.argv[6]
txt=open(RESF).read()
def grab(tag):
    m=re.search(rf"\[{tag}\] conv_self=([\d.]+) \(n=(\d+)\) \| gate vs bootstrap : rate=([\d.]+) n=(\d+) elo=([+-]?\d+)",txt)
    return dict(conv=float(m.group(1)),cn=int(m.group(2)),rate=float(m.group(3)),gn=int(m.group(4)),elo=int(m.group(5))) if m else None
mc=re.search(r"labels changés par l'adjud \(PAR-SHARD, aligné\) : \d+/\d+ = ([\d.]+)%",txt); chg=float(mc.group(1)) if mc else None
g={t:grab(t) for t in ("onpolicy","adjudW0","adjudWhi")}
man={"dev_sha":DEVSHA,"n_matched":NMATCH,"n_gym":NGYM,"gym_w":GYMW,"labels_changed_pct":chg,"cells":g}
open(MANIF,'w').write(json.dumps(man,indent=2,ensure_ascii=False))
print(f"  labels changés par adjud (valide) = {chg}%")
for t in ("onpolicy","adjudW0","adjudWhi"):
    if g[t]: print(f"  {t:9s} : conv_self={g[t]['conv']:.4f}  gate_elo={g[t]['elo']:+d} (rate {g[t]['rate']:.3f})")
op,a0,ah=g["onpolicy"],g["adjudW0"],g["adjudWhi"]
if op and a0: print(f"  → effet-LABEL (adjud-W0 vs on-policy, MÊMES positions) : conv {a0['conv']-op['conv']:+.3f}  elo {a0['elo']-op['elo']:+d}")
if a0 and ah: print(f"  → effet-GYMNASE (W{GYMW} vs W0) : conv {ah['conv']-a0['conv']:+.3f}  elo {ah['elo']-a0['elo']:+d}")
if a0 and ah:
    dconv=ah['conv']-a0['conv']
    if ah['elo']>=-5 and dconv>=0.03:
        print(f"  => ✓✓ RECETTE L3 TROUVÉE : gymnase up-weight MONTE conv (+{dconv:.3f}) ET gate tient (elo {ah['elo']:+d} ≥ bootstrap). Lancer la CAMPAGNE multi-tours (F2 gate).")
    elif dconv>=0.03:
        print(f"  => ~ conv monte (+{dconv:.3f}) mais gate régresse (elo {ah['elo']:+d}) : gymnase trop lourd (midgame sacrifié) → baisser W / sweep.")
    else:
        print(f"  => ✗ gymnase up-weight ne monte pas conv (+{dconv:.3f}) même à W{GYMW} ⟹ bootstrap-fort = plafond à 1 tour → pivot CAMPAGNE multi-tours / repenser le départ.")
PY
commit_to_main "$ART/manifest.json" "$ARTREL/manifest.json" "0722 manifest (dev_sha, cells, labels%)" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0722 FIN recette corrigée : on-policy/adjudW0/adjudW$GYM_W appariés (N=$NMATCH gym=$NGYM) dev=$DEVSHA" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0722 FINI ==="
rm -rf "$W" "$GEOM"
