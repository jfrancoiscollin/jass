#!/usr/bin/env bash
# id: cpx62-0327-scan-selfplay-distill
# description: COVARIATE-SHIFT A/B — la DISTRIBUTION des positions de distillation est-elle le verrou ?
# Hypothèse (JFC) : même si Scan labelise parfaitement, des positions PEU INSTRUCTIVES (self-play faible
# + coverage ≤7p aléatoire = le dataset 0314) ne peuvent rien apprendre, quelle que soit la depth/mt. On
# isole la SEULE variable « source des positions » : ARM-OLD = distribution 0314 (enriched-cumulative),
# ARM-NEW = positions issues du JEU PROPRE de Scan (Scan joue les deux côtés, on dumpe tout son chemin).
# Tout le reste identique : MÊME archi FULL Scan-alignée, MÊME relabel Scan (depth 9), MÊME train, MÊME
# taille (sous-échantillonnées au min commun), MÊME juge vs Scan mt1.5. new > old → la distribution EST
# le verrou (le covariate-shift). ≈ égal → la distribution n'est pas le lever ; le plafond est ailleurs.
# expected_duration: ~11-13 h (2× relabel Scan d9 + génération self-play, 16 cœurs)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-900}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

ENR=/root/jass/jobs/results/cpx62-0314-endgame-data-aug/artefacts.src/enriched-cumulative.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
SCAN_DEPTH=9          # relabel Scan (cible de distillation)
GEN_DEPTH=8           # Scan self-play (génération de la distribution forte)
GAMES=7000            # parties self-play Scan (réparties sur les shards)
MAXPLIES=160
MINPIECES=40          # seeds = positions d'ouverture (≥40 pièces) échantillonnées de 0314
NPOS=280000           # cible par bras (les deux sous-échantillonnés au min commun)

[ -f "$ENR" ] || { echo "ABORT: dataset enrichi 0314 absent ($ENR)"; exit 4; }

preflight_build 1
preflight_note "Scan self-play ${GAMES} parties @ d${GEN_DEPTH} (×$NCPU)" 120
preflight_note "relabel Scan 2×${NPOS} @ d${SCAN_DEPTH} (×$NCPU)" 260
preflight_train "$NPOS" 2
preflight_match $((2*9*2)) 1.5 160; preflight_match $((2*9*2)) 1.5 160
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

# --- build FULL Scan-alignée (referee + éval) : endg + king_mob + scan-parity + tempo-stage, drawish OFF ---
echo "=== build jass FULL Scan-alignée (egdb) ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

cnt(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }
subsample(){ # <in> <out> <n>
  python3 - "$1" "$2" "$3" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
n=min(n,tot); stride=max(1,tot//n); recs=bytearray(); k=0
for i in range(0,tot,stride):
    recs+=body[i*REC:(i+1)*REC]; k+=1
    if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(recs)); print(f'  subsample {k}/{tot} -> {out}')
PY
}

# --- ARM-NEW : génération de la DISTRIBUTION FORTE (Scan joue les deux côtés, shardée ×NCPU) ---
echo "=== ARM-NEW : Scan self-play (depth ${GEN_DEPTH}, ${GAMES} parties, ×${NCPU} shards) ==="
PERG=$(( (GAMES + NCPU - 1) / NCPU ))
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$JASS" \
    --seeds "$ENR" --out "$ART/.sp-$s.jnnw" --games "$PERG" --depth "$GEN_DEPTH" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 2 --seed $((1000 + s)) \
    >"$ART/.sp-$s.log" 2>&1 &
done
wait
python3 - "$ART/new-raw.jnnw" "$ART" "$NCPU" <<'PY'
import sys,struct,os,glob
out,d,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
o=open(out,'wb'); tot=0; o.write(b'JNNW'+struct.pack('<I',0))
for s in range(nc):
    f=os.path.join(d,f'.sp-{s}.jnnw')
    if not os.path.exists(f):
        print('  [selfplay] shard',s,'manquant (voir .sp-%d.log)'%s); continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; o.write(b[8:8+n*REC]); tot+=n
o.seek(4); o.write(struct.pack('<I',tot)); o.close()
print(f'  [selfplay] mergé {tot} positions Scan-self-play -> {out}')
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$ART/.sp-$s.jnnw"; done
[ -f "$ART/new-raw.jnnw" ] || { echo "ABORT: génération self-play vide"; tail -20 "$ART"/.sp-0.log 2>/dev/null; exit 7; }
NEWTOT=$(cnt "$ART/new-raw.jnnw")
echo "  Scan self-play : $NEWTOT positions"
[ "$NEWTOT" -gt 50000 ] || { echo "ABORT: self-play trop maigre ($NEWTOT) — voir .sp-*.log"; tail -20 "$ART"/.sp-0.log 2>/dev/null; exit 7; }

# --- taille commune = min(NPOS, NEWTOT) → A/B équitable (seule la SOURCE diffère) ---
N=$(( NEWTOT < NPOS ? NEWTOT : NPOS ))
echo "=== taille A/B commune : N=$N ==="
subsample "$ART/new-raw.jnnw" "$ART/new.jnnw" "$N"
subsample "$ENR"             "$ART/old.jnnw" "$N"

# --- relabel Scan (depth 9), IDENTIQUE pour les deux bras (distillation = cible Scan-score) ---
echo "=== relabel Scan depth ${SCAN_DEPTH} (×$NCPU) — ARM-OLD ==="
relabel_scan_sharded "$ART/old.jnnw" "$ART/old-scan.jnnw" "$SCAN_BIN" "$SCAN_DEPTH" "$NCPU"
echo "=== relabel Scan depth ${SCAN_DEPTH} (×$NCPU) — ARM-NEW ==="
relabel_scan_sharded "$ART/new.jnnw" "$ART/new-scan.jnnw" "$SCAN_BIN" "$SCAN_DEPTH" "$NCPU"
[ -f "$ART/old-scan.jnnw" ] && [ -f "$ART/new-scan.jnnw" ] || { echo "RELABEL FAIL"; exit 8; }

elo(){ local lg="$1-elo.log"; "$2" --benchmark-scan-eval "$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2); local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

declare -A ELOHC SCAN
arm(){ # <name> <scan-relabeled-data>
  local name="$1" data="$2"
  "$JASS" --dump-eval-features "$data" "$ART/$name.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$ART/$name.feat" \
    --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
    --prune --lowmem --full-fold --out "$ART/$name.pjtw" >"$ART/$name-train.log" 2>&1
  [ -f "$ART/$name.pjtw" ] || { echo "$name TRAIN FAIL"; tail -8 "$ART/$name-train.log"; return 1; }
  manifest_write "$ART/$name.pjtw" "DISTILL=Scan-d${SCAN_DEPTH} FULL-aligned SRC=$name" "$data" >/dev/null
  ELOHC[$name]=$(elo "$ART/$name" "$JASS")
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/$name.pjtw" \
      --scan-bb-size 0 --movetime 1.5 --pairs 2 --max-plies 160 --allow-long-movetime >"$ART/$name-scan.log" 2>&1 || true
  SCAN[$name]=$(grep -E 'score rate' "$ART/$name-scan.log" | grep -oE '[0-9.]+ \([0-9./]+\)' | head -1)
  echo "  $name : Elo_hc=${ELOHC[$name]:-NA}  vs_Scan_mt1.5=${SCAN[$name]:-NA}"
}

echo "=== ARM-OLD (distribution 0314) ==="
arm old "$ART/old-scan.jnnw"
echo "=== ARM-NEW (distribution Scan self-play) ==="
arm new "$ART/new-scan.jnnw"

echo; echo "=========================================================="
echo "   cpx62-0327 — COVARIATE-SHIFT A/B (la DISTRIBUTION est-elle le verrou ?)"
echo "----------------------------------------------------------"
echo "   N=$N positions/bras · relabel Scan d${SCAN_DEPTH} · archi FULL Scan-alignée · juge Scan mt1.5"
printf "  %-4s Elo_hc=%-9s vs_Scan_mt1.5=%s\n" old "${ELOHC[old]:-NA}" "${SCAN[old]:-NA}"
printf "  %-4s Elo_hc=%-9s vs_Scan_mt1.5=%s\n" new "${ELOHC[new]:-NA}" "${SCAN[new]:-NA}"
echo "----------------------------------------------------------"
echo "  new vs_Scan > old → la DISTRIBUTION est le verrou (covariate-shift confirmé)."
echo "  ≈ égal → la distribution n'est pas le lever ; le plafond de distillation est ailleurs."
echo "=========================================================="
