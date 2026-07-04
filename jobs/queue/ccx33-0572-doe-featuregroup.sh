#!/usr/bin/env bash
# id: ccx33-0572-doe-featuregroup
# description: DOE FEATURE-GROUP (JFC "pour voir") — fourche CAPACITE de l'eval, en parallele du fit 0568. 4 facteurs
# COMPILE-TIME : ENDGAME_FEATURES x KING_MOBILITY x SCAN_PARITY x TEMPO_STAGE, design 2^(4-1) Res IV (D=ABC, 8 runs,
# le defaut all-ON est un run). Par config : build (flags) -> fit-from-scratch (plain L2, PAS de prior : archi differente
# => extras differents => prior gen1 incompatible) sur un sous-echantillon de corpus-regen-mix2M -> MATCH vs Scan a
# PROFONDEUR EGALE d9 (= QUALITE d'eval pure, arch-agnostique, contourne le chargement cross-arch ; movetime serait
# injuste car notre eval est plus lente). Reponse = score-rate vs Scan. Analyse : effets principaux (chaque facteur ON vs
# OFF) => quel groupe de features PAIE / est net-negatif (explique la regression mix2M ?). VERDICT job-side. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0572-doe-featuregroup/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0572-doe-featuregroup/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-doefeat; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-doefeat
SCAN_BIN=/root/jass-scan/scan_linux
REGEN_GZ=jobs/results/cpx62-0566-regen-mix-oncoin/artefacts/corpus-regen-mix2M.jnnw.gz
SUBSAMPLE=600000; L2=3e-5; MAXIT=25; CHUNK=1000000; MATCH_DEPTH=9; MATCH_PAIRS=16
RANK="$ART/RANKING.tsv"; : > "$RANK"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

# --- Scan pret ---
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 5; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# --- corpus subsample (fixe pour tous les runs) ---
git show "origin/main:$REGEN_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus-regen absent"; exit 4; }
python3 - "$W/full.jnnw" "$W/sub.jnnw" "$SUBSAMPLE" <<'PY' 2>&1 | tee -a "$RES"
import sys,struct
inp,out,K=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
with open(inp,'rb') as f:
    f.read(4); cnt=struct.unpack('<I',f.read(4))[0]; data=f.read()
tot=len(data)//REC; step=max(1,tot//K); idx=list(range(0,tot,step))[:K]
with open(out,'wb') as g:
    g.write(b'JNNW'); g.write(struct.pack('<I',len(idx)))
    for i in idx: g.write(data[i*REC:(i+1)*REC])
print(f"  subsample fit : {len(idx)} pos (corpus {tot}, step {step})")
PY

say "=== DOE FEATURE-GROUP 2^(4-1) Res IV — reponse = score-rate vs Scan @ d${MATCH_DEPTH} (qualite eval) ==="
say "  facteurs : A=ENDGAME B=KING_MOB C=SCAN_PARITY D=TEMPO (D=ABC)"
# design 8 runs : A B C D(=ABC)  (0=OFF 1=ON)
DESIGN=(
  "0 0 0 0" "1 0 0 1" "0 1 0 1" "1 1 0 0"
  "0 0 1 1" "1 0 1 0" "0 1 1 0" "1 1 1 1"
)
onoff(){ [ "$1" = 1 ] && echo ON || echo OFF; }
run_cfg(){ local A="$1" B="$2" C="$3" D="$4"; local tag="A${A}B${B}C${C}D${D}"; local bd="$W/b_$tag"
  say ""; say "--- config $tag : ENDGAME=$(onoff $A) KING_MOB=$(onoff $B) SCAN_PARITY=$(onoff $C) TEMPO=$(onoff $D) ---"
  mkdir -p "$bd"    # FIX : creer le build dir AVANT de rediriger cmake.log dedans (sinon la redirection shell echoue)
  if ! cmake -S . -B "$bd" -DCMAKE_BUILD_TYPE=Release \
     -DJASS_ENDGAME_FEATURES=$(onoff $A) -DJASS_KING_MOBILITY=$(onoff $B) \
     -DJASS_SCAN_PARITY=$(onoff $C) -DJASS_TEMPO_STAGE=$(onoff $D) >"$bd/cmake.log" 2>&1; then
    say "  CMAKE CONFIGURE FAIL : $(tail -3 "$bd/cmake.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\tcmakefail" >>"$RANK"; return; fi
  if ! cmake --build "$bd" -j"$NCPU" --target jass >"$bd/build.log" 2>&1; then
    say "  BUILD FAIL : $(tail -3 "$bd/build.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\tbuildfail" >>"$RANK"; return; fi
  local J="$bd/jass"
  # fit-from-scratch (pas de prior : archi propre a cette config)
  "$J" --dump-eval-features "$W/sub.jnnw" "$bd/feat" >"$bd/feat.log" 2>&1 || { say "  dump feat FAIL"; echo -e "$A\t$B\t$C\t$D\tNA\tdumpfail" >>"$RANK"; return; }
  local tempoflag=""; [ "$D" = 1 ] && tempoflag="--tempo-stage"
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/sub.jnnw" --feat "$bd/feat" \
     --color-fold $tempoflag --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --prune 1 \
     --out "$bd/cand.pjtw" >"$bd/train.log" 2>&1 || { say "  TRAIN FAIL : $(tail -2 "$bd/train.log"|tr '\n' ' ')"; echo -e "$A\t$B\t$C\t$D\tNA\ttrainfail" >>"$RANK"; return; }
  # match vs Scan a profondeur egale (qualite eval)
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$bd/cand.pjtw" \
     --scan-bb-size 0 --depth "$MATCH_DEPTH" --pairs "$MATCH_PAIRS" >"$bd/match.log" 2>&1 || true
  local rate; rate=$(grep -iE 'Jass score rate' "$bd/match.log" | grep -oE '[0-9]*\.[0-9]+' | head -1)
  [ -z "$rate" ] && rate="NA"
  say "  => score-rate vs Scan (d${MATCH_DEPTH}) = ${rate}"
  echo -e "$A\t$B\t$C\t$D\t$rate\tok" >>"$RANK"
  rm -f "$bd/feat"; rm -rf "$bd" 2>/dev/null || true    # cleanup disque (build dir entier, apres le match)
}
for row in "${DESIGN[@]}"; do run_cfg $row; done

say ""; say "=== ANALYSE DOE (effets principaux sur score-rate vs Scan) ==="
python3 - "$RANK" <<'PY' 2>&1 | tee -a "$RES"
import sys
rows=[l.strip().split('\t') for l in open(sys.argv[1]) if l.strip()]
data=[]
for r in rows:
    A,B,C,D,rate,stat=r[0],r[1],r[2],r[3],r[4],r[5]
    if stat=='ok' and rate!='NA':
        try: data.append((int(A),int(B),int(C),int(D),float(rate)))
        except: pass
if len(data)<4:
    print(f"  trop peu de configs valides ({len(data)}/8) — DOE non concluant"); raise SystemExit
names={0:'ENDGAME',1:'KING_MOB',2:'SCAN_PARITY',3:'TEMPO'}
print(f"  {len(data)}/8 configs valides")
print(f"  {'config':>10} {'rate_vs_scan':>13}")
for A,B,C,D,r in sorted(data,key=lambda x:-x[4]):
    print(f"  A{A}B{B}C{C}D{D:>1} {r:>13.4f}")
print("")
print("  EFFET PRINCIPAL (moyenne rate ON - moyenne rate OFF) :")
for f in range(4):
    on=[r for r in data if r[f]==1]; off=[r for r in data if r[f]==0]
    if on and off:
        eon=sum(x[4] for x in on)/len(on); eoff=sum(x[4] for x in off)/len(off)
        eff=eon-eoff
        tag='PAIE' if eff>0.01 else ('NUIT' if eff<-0.01 else 'neutre')
        print(f"    {names[f]:>12} : ON {eon:.4f} vs OFF {eoff:.4f}  effet {eff:+.4f}  [{tag}]")
print("")
print("  (Res IV : effets principaux propres, interactions 2-facteurs confondues par paires.)")
print("  Lecture : un facteur a effet negatif net = candidat a RETIRER de l'archi (expliquerait mix2M -18).")
print("  Ecart absolu a Scan bas (rate<<0.5) = normal : fit-from-scratch sur 600k sans prior, comparaison RELATIVE.")
PY
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0569 DOE feature-group : RESULTS job-side (effets principaux vs Scan d9)" \
  && say "  RESULTS committe job-side ✓" || say "  ⚠ commit RESULTS echoue"
commit_to_main "$RANK" "$ARTREL/RANKING.tsv" "0569 DOE feature-group : RANKING job-side" || true
say "=== fin DOE feature-group ==="
