#!/usr/bin/env bash
# id: cpx62-0574-doe-featuregroup-v4
# description: DOE FEATURE-GROUP v4 PROPRE (JFC) — sous le recadrage ENCODAGE (geometrie superset Scan => pas la capacite ;
# quel groupe de features AIDE/NUIT au FIT ?). 4 facteurs compile-time ENDGAME x KING_MOB x SCAN_PARITY x TEMPO, 2^(4-1)
# Res IV (D=ABC). FIX des 3 echecs precedents : (1) mkdir build dir avant redirect [0569], (2) --prune-min-visits 1 [0572],
# (3) REPONSE = vs gen1 au lieu de vs Scan [0573 : fit-from-scratch reduit perd tout vs Scan => 0.000 = effet PLANCHER,
# aucune discrimination]. Chaque config a son PROPRE binaire (features reduites) => on juge eval_config (binaire_config)
# vs gen1 (binaire all-ON) avec jass_vs_jass_arch --jass-a/--jass-b separes (pas de chargement cross-arch). Reponse =
# rate vs gen1 a d9. Capture BLINDEE : fichiers de travail hors $ART, VERDICT ecrit+committe job-side en fin uniquement.
# Effet principal (ON-OFF) par facteur => quel groupe pruner (net-negatif = explique mix2M -18). AUCUN NNUE. ~1-1.5h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0574-doe-featuregroup-v4/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0574-doe-featuregroup-v4/artefacts"
W=/root/cw-doev4; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-doev4
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
REGEN_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen; NOPEN=60
SUBSAMPLE=600000; L2=3e-5; MAXIT=25; CHUNK=1000000; JUDGE_DEPTH=9; JUDGE_PAIRS=1
RANK="$W/rank.tsv"; : > "$RANK"; LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

note "=== DOE feature-group v4 — reponse vs gen1 @ d${JUDGE_DEPTH} — HEAD $(git log --oneline -1|cat) ==="
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
# reference : build all-ON + gen1
REFB="$W/b_ref"; mkdir -p "$REFB"
cmake -S . -B "$REFB" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$REFB/cmake.log" 2>&1
cmake --build "$REFB" -j"$NCPU" --target jass >"$REFB/build.log" 2>&1 || { note "BUILD REF FAIL"; tail -8 "$REFB/build.log"; exit 6; }
REFBIN="$REFB/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { note "ABORT gen1"; exit 4; }
git show "origin/main:$REGEN_GZ" | gunzip > "$W/full.jnnw" || { note "ABORT corpus"; exit 4; }
python3 - "$W/full.jnnw" "$W/sub.jnnw" "$SUBSAMPLE" <<'PY'
import sys,struct
inp,out,K=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
with open(inp,'rb') as f:
    f.read(4); cnt=struct.unpack('<I',f.read(4))[0]; data=f.read()
tot=len(data)//REC; step=max(1,tot//K); idx=list(range(0,tot,step))[:K]
with open(out,'wb') as g:
    g.write(b'JNNW'); g.write(struct.pack('<I',len(idx)))
    for i in idx: g.write(data[i*REC:(i+1)*REC])
PY
grep -vE '^\s*(#|$)' "$DILF" | head -"$NOPEN" > "$W/open.fen"
note "  ref=all-ON+gen1 ; subsample fit=$SUBSAMPLE ; openings=$(wc -l <"$W/open.fen") ; ~$(( $(wc -l <"$W/open.fen") *2 )) games/config"

onoff(){ [ "$1" = 1 ] && echo ON || echo OFF; }
# design 2^(4-1) : A B C D(=ABC)
DESIGN=( "0 0 0 0" "1 0 0 1" "0 1 0 1" "1 1 0 0" "0 0 1 1" "1 0 1 0" "0 1 1 0" "1 1 1 1" )
run_cfg(){ local A="$1" B="$2" C="$3" D="$4"; local tag="A${A}B${B}C${C}D${D}"; local bd="$W/b_$tag"
  note ""; note "--- $tag : ENDGAME=$(onoff $A) KING_MOB=$(onoff $B) SCAN_PARITY=$(onoff $C) TEMPO=$(onoff $D) ---"
  mkdir -p "$bd"
  if ! cmake -S . -B "$bd" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=$(onoff $A) \
       -DJASS_KING_MOBILITY=$(onoff $B) -DJASS_SCAN_PARITY=$(onoff $C) -DJASS_TEMPO_STAGE=$(onoff $D) >"$bd/cmake.log" 2>&1; then
    note "  CMAKE FAIL : $(tail -2 "$bd/cmake.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\tcmakefail" >>"$RANK"; return; fi
  if ! cmake --build "$bd" -j"$NCPU" --target jass >"$bd/build.log" 2>&1; then
    note "  BUILD FAIL : $(tail -2 "$bd/build.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\tbuildfail" >>"$RANK"; return; fi
  if ! "$bd/jass" --dump-eval-features "$W/sub.jnnw" "$bd/feat" >"$bd/feat.log" 2>&1; then
    note "  DUMP FAIL : $(tail -2 "$bd/feat.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\tdumpfail" >>"$RANK"; return; fi
  local tempoflag=""; [ "$D" = 1 ] && tempoflag="--tempo-stage"
  if ! env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/sub.jnnw" --feat "$bd/feat" \
       --color-fold $tempoflag --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --prune-min-visits 1 \
       --out "$bd/cand.pjtw" >"$bd/train.log" 2>&1; then
    note "  TRAIN FAIL : $(tail -2 "$bd/train.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\ttrainfail" >>"$RANK"; return; fi
  # JUGE eval_config (binaire_config) vs gen1 (binaire ref all-ON) — binaires separes => pas de cross-arch
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$bd/jass" --pattern-a "$bd/cand.pjtw" \
      --jass-b "$REFBIN" --pattern-b "$W/gen1.pjtw" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/open.fen" >"$bd/j.$s" 2>&1 & done; wait
  local rate; rate=$(python3 - "$bd"/j.* <<'PY'
import sys,math; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}" if g else "NA")
PY
)
  note "  => rate vs gen1 (d${JUDGE_DEPTH}) = ${rate}"
  echo -e "$A\t$B\t$C\t$D\t$rate\tok" >>"$RANK"
  rm -rf "$bd" 2>/dev/null || true
}
for row in "${DESIGN[@]}"; do run_cfg $row; done

# ---- ANALYSE + VERDICT (ecrit dans $ART SEULEMENT ici, en fin => pas de snapshot stale) ----
VERD="$ART/VERDICT.txt"
python3 - "$RANK" > "$VERD" <<'PY'
import sys
rows=[l.strip().split('\t') for l in open(sys.argv[1]) if l.strip()]
data=[]; fails=[]
for r in rows:
    if len(r)<6: continue
    A,B,C,D,rate,stat=r
    if stat=='ok' and rate!='NA':
        try: data.append((int(A),int(B),int(C),int(D),float(rate)))
        except: pass
    else: fails.append((f"A{A}B{B}C{C}D{D}",stat))
names={0:'ENDGAME',1:'KING_MOB',2:'SCAN_PARITY',3:'TEMPO'}
print("=== VERDICT DOE feature-group v4 — reponse rate vs gen1 @ d9 ===")
print(f"configs valides : {len(data)}/8" + (f" ; echecs : {fails}" if fails else ""))
if len(data)<4: print("DOE non concluant (trop peu de configs valides)"); raise SystemExit
print(f"  {'config':>10} {'rate_vs_gen1':>13}")
for A,B,C,D,r in sorted(data,key=lambda x:-x[4]):
    print(f"  A{A}B{B}C{C}D{D} {r:>13.4f}")
print("")
print("EFFET PRINCIPAL (moyenne rate ON - OFF ; >0 => le groupe AIDE le fit, <0 => NUIT) :")
for f in range(4):
    on=[r for r in data if r[f]==1]; off=[r for r in data if r[f]==0]
    if on and off:
        eon=sum(x[4] for x in on)/len(on); eoff=sum(x[4] for x in off)/len(off); eff=eon-eoff
        tag='AIDE' if eff>0.01 else ('NUIT (a pruner ?)' if eff<-0.01 else 'neutre')
        print(f"  {names[f]:>12} : ON {eon:.4f} vs OFF {eoff:.4f}  effet {eff:+.4f}  [{tag}]")
print("")
print("Res IV : effets principaux propres, interactions 2-fact. confondues par paires.")
print("Un facteur NUIT (effet<0) = feature qui degrade l'encodage => candidat a retirer (explique mix2M -18 ?).")
PY
cat "$VERD" | tee -a "$LOG"
cp "$RANK" "$ART/RANKING.tsv"
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0574 DOE v4 : VERDICT job-side (effets features vs gen1)" \
  && note "  VERDICT committe job-side ✓" || note "  ⚠ commit VERDICT echoue"
commit_to_main "$ART/RANKING.tsv" "$ARTREL/RANKING.tsv" "0574 DOE v4 : RANKING job-side" || true
note "=== fin DOE v4 ==="
