#!/usr/bin/env bash
# id: cpx62-0485-forcing-ext-depthsweep
# description: LE TEST DU MIRAGE D11 (suite de 0483). 0483 a montre ext_forcing 0.302->0.603 sur 0440 a d11 (enorme,
# hors IC). MAIS le diagnostic 0451 avertit : a movetime jass atteint deja d14-16 et trouve les combos sans aide (la
# profondeur SUBSTITUE) => un gain a d11 peut etre un MIRAGE redondant en jeu reel. Test propre, SANS confond vitesse
# (depth-fixe, eval-pur, PAS movetime) : on rejoue la jauge 0440 (dilf, vs Scan, champion egdbmix, SANS re-entrainement)
# aux PROFONDEURS QUE LE JEU REEL ATTEINT (d13, d15), baseline vs ext_forcing. 4 cellules + IC95 bootstrap.
#
# LECTURE (le decideur du « bake or not ») :
#   d15-baseline ~0.52 ET d15-ext ~ d15-baseline => la profondeur seule trouve deja les combos => ext_forcing REDONDANT
#       en jeu reel (mirage d11 confirme, coherent 0451) => garder ext_forcing OFF par defaut.
#   d15-ext >> d15-baseline (ex. 0.7 vs 0.52, hors IC) => ext_forcing est un VRAI levier AU-DELA de la profondeur =>
#       le baker au jeu, et l'ecart 0440 etait bien de la RECHERCHE (re-cadre toute la strategie : gate NNUE non pertinente).
# 100% recherche, AUCUN re-entrainement, AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0485-forcing-ext-depthsweep/artefacts"; mkdir -p "$ART"
W=/root/cw-extdepth; mkdir -p "$W"
RES="$ART/RESULTS.txt"; SUM="$ART/SUMMARY.txt"; say(){ echo "$@" | tee -a "$RES"; }
[ -f "$RES" ] || : > "$RES"; [ -f "$SUM" ] || : > "$SUM"
DILF=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan absent"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT: egdbmix absent"; exit 4; }

conv_ci(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=[]
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw.append(0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0))
n=len(aw)
if not n: print("NA NA NA 0"); sys.exit(0)
m=sum(aw)/n; seed=12345; boots=[]
for _ in range(2000):
    acc=0
    for _ in range(n):
        seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
    boots.append(acc/n)
boots.sort(); print(f"{m:.3f} {boots[50]:.3f} {boots[1949]:.3f} {n}")
PY
}

say "=== 0440 forcing-ext depth-sweep (champion egdbmix, eval-pur no-DB, vs Scan) ==="
for D in 13 15; do
  for entry in "base:" "ext:ext_forcing=1"; do
    name="d${D}_${entry%%:*}"; spec="${entry#*:}"
    DGD="$ART/conv-$name"
    if ls "$DGD"/game-*.json >/dev/null 2>&1; then
      say "  (reprise) $name deja joue"
    else
      mkdir -p "$DGD"; SP=(); [ -n "$spec" ] && SP=(--jass-search-params "$spec")
      ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" \
          --jass-pattern "$W/egdbmix.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 \
          --openings-file "$DILF" --dump-games-dir "$DGD" "${SP[@]}" >"$W/cv-$name.log" 2>&1 ) \
        || say "  ($name : calibrate erreur, on juge le dump)"
    fi
    read M LO HI N < <(conv_ci "$DGD")
    line="$name  0440=$M  IC95=[$LO,$HI]  (n=$N)"; say "$line"; echo "$line" >> "$SUM"
  done
done

say ""; say "=== LECTURE (vs 0483 d11 : base 0.302 / ext 0.603 ; baseline movetime 0451 ~0.519) ==="
cat "$SUM" | sed 's/^/  /' | tee -a "$RES"
say "  d15_ext >> d15_base (hors IC) => VRAI levier au-dela de la profondeur => baker ext_forcing au jeu."
say "  d15_ext ~ d15_base (~0.52) => la profondeur substitue => mirage d11 => garder OFF (coherent 0451)."
