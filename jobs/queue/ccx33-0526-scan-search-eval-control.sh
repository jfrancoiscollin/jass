#!/usr/bin/env bash
# id: ccx33-0526-scan-search-eval-control
# description: BRAS CONTRÔLE du localiseur éval-vs-recherche (jumeau de cpx62-0525 ; relance de 0524 mort rc=7 = --threads
# inexistant). MÊME corpus, MÊME pipeline, MÊME jauge 0440 — seule variable : relabel au SCORE DE RECHERCHE de Scan (depth 12)
# au lieu de son éval quasi-statique (depth 1). Reproduit proprement 0147 (Scan-d10) sur le corpus/pipeline courant pour un
# static-vs-search apples-to-apples. LECTURE (croisée avec 0525) : static ~ search => la profondeur du label n'est pas le
# levier ; static >> search => la contamination-recherche plombait le fit historique. AUCUN NNUE. expected_duration: ~1.5-3.5 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0526-scan-search-eval-control/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-scan-search; rm -rf "$W"; mkdir -p "$W"

SCAN_BIN=/root/jass-scan/scan_linux
CORPUS=jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
FENS=data/dilf_combinations.fen
RELABEL_DEPTH=12       # 12 = score de RECHERCHE de Scan (contrôle contaminé)
MAXREC=400000
PLAY_DEPTH=11

say "=== CONTRÔLE éval-vs-recherche — bras RECHERCHE (Scan depth ${RELABEL_DEPTH}) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 5; }
[ -f "$CORPUS" ] || { say "ABORT: corpus absent $CORPUS"; exit 4; }
[ -f "$FENS" ]   || { say "ABORT: dilf FENS absentes $FENS"; exit 4; }

say "=== build jass (mêmes flags que 0525) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 \
    || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 \
    || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say "=== Phase 1 : relabel corpus PARALLÈLE (Scan depth ${RELABEL_DEPTH}, ${MAXREC} pos) ==="
say "    (depth 12 => ~23 ms/pos ; parallélisé pour tenir en ~15-30 min)"
NSHARD=$(( NCPU > 8 ? 8 : NCPU )); [ "$NSHARD" -lt 1 ] && NSHARD=1
SHARD_N=$(( (MAXREC + NSHARD - 1) / NSHARD ))
say "  ${NSHARD} shards //, ${SHARD_N} pos/shard"
pids=(); rc_shards=0
for i in $(seq 0 $((NSHARD-1))); do
    START=$(( i * SHARD_N ))
    python3 tools/relabel_with_scan.py --in "$CORPUS" --out "$W/shard_$i.jnnw" \
        --scan "$SCAN_BIN" --depth "$RELABEL_DEPTH" --start "$START" --max-records "$SHARD_N" \
        --progress-every 5000 >"$W/relabel_$i.log" 2>&1 &
    pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || rc_shards=1; done
[ "$rc_shards" -eq 0 ] || { say "ABORT relabel (un shard a échoué)"; tail -6 "$W"/relabel_*.log | sed 's/^/  /'; exit 7; }
LAB="$W/search-labelled.jnnw"
python3 - "$LAB" "$W"/shard_*.jnnw <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
out=sys.argv[1]; shards=sys.argv[2:]
total=0; magic=None; bodies=[]
for s in sorted(shards):
    b=open(s,'rb').read()
    if len(b)<8: continue
    if magic is None: magic=b[0:4]
    n=struct.unpack_from("<I",b,4)[0]; bodies.append(b[8:8+n*38]); total+=n
open(out,'wb').write(magic+struct.pack("<I",total)+b"".join(bodies))
print(f"  merged {total} records depuis {len(shards)} shards")
PY
[ -f "$LAB" ] || { say "ABORT merge"; exit 7; }
python3 - "$LAB" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys,statistics as st
b=open(sys.argv[1],'rb').read(); n=struct.unpack_from("<I",b,4)[0]; body=memoryview(b)[8:8+n*38]
sc=[struct.unpack_from("<i",body,i*38+33)[0] for i in range(n)]
nz=sum(1 for s in sc if s!=0)
print(f"  garde-fou : {n} pos ; non-nuls {nz}/{n} ({100*nz/max(n,1):.1f}%) ; min {min(sc)} max {max(sc)} med {int(st.median(sc))}")
PY

say "=== Phase 2 : dump-eval-features ==="
FEAT="$W/search.feat"
"$JASS" --dump-eval-features "$LAB" "$FEAT" >"$W/dump.log" 2>&1 || { say "ABORT dump-eval-features"; tail -6 "$W/dump.log"|sed 's/^/  /'; exit 8; }
[ -f "$FEAT" ] || { say "ABORT: feat absent"; exit 8; }

say "=== Phase 3 : fit éval Scan-portée v3 sur le SCORE DE RECHERCHE ==="
V3="$ART/scan_search_eval_v3.pjtw"
python3 pattern_jass/tools/train.py --data "$LAB" --scan-eval \
    --eval-features-file "$FEAT" --target score --score-clip 5000 \
    --l2 1e-5 --max-iter 200 --scale 1000 --out "$V3" >"$W/train.log" 2>&1 \
    || { say "ABORT train"; tail -12 "$W/train.log"|sed 's/^/  /'; exit 9; }
[ -f "$V3" ] || { say "ABORT: v3 non produit"; exit 9; }
say "  QUALITÉ DU FIT (résidu sur le score de RECHERCHE) :"
grep -iE "loss|iter|final|converg|r2|corr|rmse" "$W/train.log" | tail -6 | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== Phase 4 : JOUE jass-search + Scan-SEARCH-eval vs Scan sur 0440 (depth ${PLAY_DEPTH}, no-DB) ==="
timeout 18000 python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$V3" \
    --scan-bb-size 0 --depth "$PLAY_DEPTH" --pairs 1 --openings-file "$FENS" \
    --dump-games-dir "$ART/games" >"$W/match.log" 2>&1 || say "  (match interrompu/timeout — on analyse les parties dumpées)"
tail -6 "$W/match.log" | sed 's/^/    /' | tee -a "$RES"

say ""
say "=== ANALYSE : conversion du camp AU TRAIT (identique à 0440) ==="
python3 - "$ART/games" "$FENS" <<'PY' | tee -a "$RES"
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm[b]=b.split(':',1)[0].strip()
ja_w=ja_n=0; sc_w=sc_n=0; tot=0; nolegal=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except Exception: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    tot+=1
    jw=g.get("jass_is_white"); out=g.get("outcome")
    if g.get("reason","")=="no-legal-move" and g.get("plies",1)<=1: nolegal+=1
    jass_is_attacker = (jw and s=="W") or ((not jw) and s=="B")
    if out=="D": att_win=0.5
    elif (out=="W" and s=="W") or (out=="L" and s=="B"): att_win=1.0
    else: att_win=0.0
    if jass_is_attacker: ja_w+=att_win; ja_n+=1
    else:                sc_w+=att_win; sc_n+=1
def pct(w,n): return f"{w/n:.3f} ({w:.1f}/{n})" if n else "n/a"
print(f"  parties analysees      : {tot}  (sans coup legal au depart : {nolegal})")
print(f"  JASS(+Scan-search-eval) au trait : {pct(ja_w,ja_n)}")
print(f"  SCAN au trait                    : {pct(sc_w,sc_n)}")
if ja_n and sc_n: print(f"  ECART jass - scan : {ja_w/ja_n - sc_w/sc_n:+.3f}")
PY

say ""
say "  LECTURE : à croiser avec cpx62-0525 (bras statique). Voir son bloc LECTURE."
