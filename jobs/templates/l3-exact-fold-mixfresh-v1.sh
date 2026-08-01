#!/usr/bin/env bash
# L3 — on-policy DANS la recette turnover : un seul facteur bouge.
#
# `cpx62-1119` avait remplacé le corpus par 100 % de self-play frais du modèle
# exact, et perdu 9,15 Elo. Question de JFC : un meilleur générateur ne devrait
# pas faire régresser. En vérifiant, le protocole était fautif — le corpus de
# TURNOVER n'est PAS du frais, c'est un **mélange 1:1 mémoire/frais** (c'est le
# sens même de « turnover »), et la passe était passée à 100/0. Deux facteurs
# avaient bougé : le générateur ET la composition. C'est exactement l'écart
# « frais/mémoire » que le registre reproche déjà à VOL8M.
#
# Ce job garde la recette : moitié mémoire F2M inchangée et vérifiée par hash,
# mélange 1:1, même graine, même volume. **Seule la moitié fraîche change** —
# engendrée par le modèle exact au lieu de m2-d8. Comparé à EXACT, un seul
# facteur sépare les deux.
#
# Aucune promotion, aucune chaîne automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${REFIT_PREFIX:?}"; : "${EXPECTED_REFIT_JOB:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

# Paramètres de génération de `l3-pure-m2-train-v1`, à l'identique : ce job
# change la POLITIQUE qui engendre, pas la recette d'engendrement.
TOTAL_RECORDS="${TOTAL_RECORDS:-2000000}"
FRESH_RECORDS="${FRESH_RECORDS:-1000000}"   # moitié fraîche ; le mélange 1:1 fait le reste
MIX_SEED=141421                              # graine de home-0977, à l'identique
EXPECTED_F2M_CORPUS_SHA256="15261c89bd6520e17c03bcf2843b226600ff334130656aab7b1a1f2d1ca03248"
EXPECTED_F2M_META_SHA256="6b12a940128033652afe578c61e48c8570ba4db14cb4cde363d56d4bdcdf2d7f"
PRODUCERS="${PRODUCERS:-12}"
LABEL_DEPTH=4; PLAY_DEPTH=8; MAXPLIES=260; BASE_SEED=1618033
HOLDOUT_MOD=10; SPLIT_SEED=577215
L2=3e-5; MAXIT=1000; LBFGS_MAXCOR=20; LBFGS_GTOL=1e-3; CHUNK=20000
GEN_TIMEOUT="${GEN_TIMEOUT:-5400}"; FIT_TIMEOUT="${FIT_TIMEOUT:-3600}"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        # `gen-data-wdl` imprime « X / Y positions » : on somme les shards et on
        # extrapole le restant sur le rythme observé.
        awk -v el="$(( ($(date +%s) - t0) / 60 ))" '
          /positions$/ { d[FILENAME]=$4; t[FILENAME]=$6 }
          END { for (k in d) { s+=d[k]; u+=t[k] }
                if (u>0) { printf "gen_positions=%d/%d (%.1f%%)\n", s, u, 100*s/u
                           if (s>0 && el>0) printf "gen_eta_remaining_min=%d\n", el*(u-s)/s } }' \
          "$W"/gen-s*.log 2>/dev/null || true
        [ -f "$W/fit.log" ] && printf 'fit_lines=%s\n' "$(wc -l < "$W/fit.log")"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10000 ] || die "moins de 10 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo producteurs=$PRODUCERS"
monitor

stage fetch-exact-parent
python3 jobs/tools/fetch_result_files.py --prefix "$REFIT_PREFIX" \
  --file artefacts/exact.pjtw.gz=exact.pjtw.gz \
  --file artefacts/symmetry-report.json=symmetry.json \
  --out-dir "$IN" --report "$ART/verified-refit.json" \
  --expected-state completed > "$W/fetch.log" 2>&1 || die "fetch du parent en échec"
python3 - "$ART/verified-refit.json" "$EXPECTED_REFIT_JOB" "$IN/symmetry.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("refit source identity/state mismatch")
s = json.load(open(sys.argv[3]))
if s["exact"]["violation_rot180_cs_EXACT"] > 1e-9:
    raise SystemExit("le parent annoncé exact ne l'est pas — on-policy sans objet")
PY
gunzip -c "$IN/exact.pjtw.gz" > "$W/PARENT.pjtw"
say "  parent EXACT ✓ (antisymétrie vérifiée à la source)"

stage fetch-memory-half
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file source/f2m-common.jnnw.gz=f2m-common.jnnw.gz \
  --file source/f2m-common.jsm.gz=f2m-common.jsm.gz \
  --file source/f2m-extra.jnnw.gz=f2m-extra.jnnw.gz \
  --file source/f2m-extra.jsm.gz=f2m-extra.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover-train.json" \
  --expected-state completed > "$W/fetch-f2m.log" 2>&1 || die "fetch de la moitié mémoire en échec"
python3 - "$ART/verified-turnover-train.json" "$EXPECTED_TURNOVER_TRAIN_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("source identity/state mismatch")
PY
for f in f2m-common f2m-extra; do
  gunzip -c "$IN/$f.jnnw.gz" > "$W/$f.jnnw"
  gunzip -c "$IN/$f.jsm.gz"  > "$W/$f.jsm"
done
# Reconstruction à l'identique de home-0977, hash épinglé : si la moitié mémoire
# n'est pas bit-pour-bit celle de TURNOVER, la comparaison ne tient plus.
python3 tools/selfplay_frontier.py merge \
  --pair "$W/f2m-common.jnnw" "$W/f2m-common.jsm" \
  --pair "$W/f2m-extra.jnnw" "$W/f2m-extra.jsm" \
  --renamespace-nested \
  --out-data "$W/f2m.raw.jnnw" --out-meta "$W/f2m.raw.jsm" \
  --manifest "$ART/f2m-reconstruction.json" > "$W/f2m-reconstruction.log" 2>&1 ||
  die "reconstruction F2M en échec"
[ "$(sha256sum "$W/f2m.raw.jnnw" | awk '{print $1}')" = "$EXPECTED_F2M_CORPUS_SHA256" ] ||
  die "moitié mémoire : hash du corpus différent de celui de TURNOVER"
[ "$(sha256sum "$W/f2m.raw.jsm" | awk '{print $1}')" = "$EXPECTED_F2M_META_SHA256" ] ||
  die "moitié mémoire : hash des métadonnées différent"
say "  moitié mémoire F2M ✓ reconstruite, hashes conformes à TURNOVER"

stage build
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
grep -q "warm_kings_endgame_bitbases" src/hub.cpp ||
  { restore_src; die "engine predates the movetime endgame bake"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/PARENT.pjtw" > "$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "le binaire ne charge pas le parent exact"
say "  build ✓, parent chargeable"

stage generate-fresh-half
base=$((FRESH_RECORDS / PRODUCERS)); rem=$((FRESH_RECORDS % PRODUCERS))
pairs=(); pids=()
for shard in $(seq 0 $((PRODUCERS-1))); do
  count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
  data="$W/gen-s$shard.jnnw"; meta="$W/gen-s$shard.jsm"
  ( timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" "$data" \
      "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((BASE_SEED+shard)) \
      --nnue "$W/PARENT.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
      --pair-openings --drop-plycap --sample-meta-out "$meta" \
      > "$W/gen-s$shard.log" 2>&1 < /dev/null
    echo "$?" > "$W/done-s$shard" ) &
  pids+=("$!"); pairs+=(--pair "$data" "$meta")
done
# ⚠️ JAMAIS `wait` nu quand un monitor tourne : il attendrait aussi le monitor,
# qui boucle jusqu'au finalize → interblocage circulaire (bug 0665/0666/0668).
wait "${pids[@]}"
bad=0
for shard in $(seq 0 $((PRODUCERS-1))); do
  [ "$(cat "$W/done-s$shard" 2>/dev/null || echo 1)" = 0 ] || bad=$((bad+1))
done
[ "$bad" -eq 0 ] || die "$bad producteur(s) en échec sur $PRODUCERS"
for log in "$W"/gen-s*.log; do
  grep -q 'label_score_searches=0' "$log" || die "recherche d'étiquette par score dans $log"
done
say "  moitié fraîche ✓ $FRESH_RECORDS positions par $PRODUCERS producteurs, étiquettes WDL pures"

stage merge-split-and-features
python3 tools/selfplay_frontier.py merge "${pairs[@]}" \
  --out-data "$W/fresh.jnnw" --out-meta "$W/fresh.jsm" \
  --manifest "$ART/merge.json" > "$W/merge.log" 2>&1 || die "merge des shards en échec"
# LE point du job : mélange 1:1, mêmes paramètres que home-0977 (graine 141421,
# namespace des ouvertures). Seule la source FRESH a changé de générateur.
python3 tools/selfplay_frontier.py mix \
  --source PARENT "$W/f2m.raw.jnnw" "$W/f2m.raw.jsm" 1 \
  --source FRESH  "$W/fresh.jnnw"   "$W/fresh.jsm"   1 \
  --target-records "$TOTAL_RECORDS" --seed "$MIX_SEED" --namespace-openings \
  --out-data "$W/raw.jnnw" --out-meta "$W/raw.jsm" \
  --manifest "$ART/mix.json" > "$W/mix.log" 2>&1 || die "mélange 1:1 en échec"
python3 - "$ART/mix.json" <<'PY' | tee -a "$RES"
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  mélange ✓ {m['records']} records (cible {m['target_records']}, graine {m['seed']})")
for src in m["sources"]:
    print(f"    {src['label']:<7} poids={src['weight']}  retenus={src['selected_records']:,}"
          f"  sur {src['input_records']:,}  ({100*src['selected_fraction']:.1f} %)"
          f"  ouvertures={src['selected_openings']}")
sel = {s["label"]: s["selected_records"] for s in m["sources"]}
if len(sel) == 2:
    a, b = sel.values()
    # Le ratio EST l'objet du job : s'il n'est pas 1:1 la comparaison avec
    # TURNOVER ne tient plus, et mieux vaut le savoir ici qu'après la porte.
    if abs(a - b) > 0.02 * max(a, b):
        raise SystemExit(f"mélange déséquilibré {a} vs {b} — ce n'est pas du 1:1")
    print(f"  ratio 1:1 vérifié ({a:,} / {b:,})")
PY
python3 tools/selfplay_frontier.py split \
  --data "$W/raw.jnnw" --meta "$W/raw.jsm" \
  --out-data "$W/fit.jnnw" --out-meta "$W/fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" > "$W/split.log" 2>&1 || die "split en échec"
HOLDOUT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split.json")
[ "$HOLDOUT" -gt 0 ] || die "holdout vide"
"$J" --dump-eval-features "$W/fit.jnnw" "$W/corpus.feat" > "$W/features.log" 2>&1 ||
  die "dump-eval-features en échec"
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/corpus.feat")
[ "$K" = 120 ] || die "extras K=$K attendu 120"
say "  corpus on-policy ✓ holdout=$HOLDOUT extras=$K"

stage python-runtime
python3 -m venv "$W/venv"
if "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
     numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then PINSTACK=historical
else
  "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >> "$W/pip.log" 2>&1 || die "pip en échec"
  PINSTACK=current
fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
say "  pile numérique : $PINSTACK (numpy/scipy $NPV)"
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" \
  pattern_jass/tools/test_exact_fold.py -v > "$W/selftest.log" 2>&1 ||
  die "auto-tests du fold exact en échec"

stage fit-mixfresh-exact
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/fit.jnnw" --feat "$W/corpus.feat" --out "$W/mixfresh.pjtw" \
    --target wdl --loss logistic --exact-fold --tempo-stage \
    --warm-start "$W/PARENT.pjtw" --holdout-count "$HOLDOUT" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" --prune \
    --optimizer-report "$ART/mixfresh-optimizer.json" \
    > "$W/fit.log" 2> "$W/fit-time.log"
fit_rc=$?
set -e
[ "$fit_rc" -eq 0 ] || die "fit rc=$fit_rc — voir fit.log"
[ -s "$W/mixfresh.pjtw" ] || die "fit sans modèle"
python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("success") else 1)' \
  "$ART/mixfresh-optimizer.json" || die "le fit n'a pas convergé"
gzip -n -c "$W/mixfresh.pjtw" > "$ART/mixfresh.pjtw.gz"
IT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["iterations"])' "$ART/mixfresh-optimizer.json")
LL=$(grep -o 'HOLDOUT_LOGLOSS[= ][0-9.]*' "$W/fit.log" | tail -1)
say "  fit ✓ $IT itérations, ${LL:-holdout n/a}"

stage verify-symmetry
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" - \
  "$W/mixfresh.pjtw" "$ART/symmetry-report.json" <<'PY' | tee -a "$RES"
import json, struct, sys
import numpy as np
import patterns as P, symmetry as S
NB, NP = P.BUCKETS_PER_PATTERN, P.NUM_PATTERNS
cs = S.colorswap_map(); rp, rotperm = S.rot_structure()
raw = open(sys.argv[1], "rb").read()
_, _, _, n_pat, _ = struct.unpack("<5I", raw[:20])
pat = np.frombuffer(raw[20:], dtype="<i4")[:n_pat].reshape(NP, NB)
def viol(sig):
    ok = bad = 0.0
    for p in range(NP):
        q, s = sig(p)
        a = pat[p].astype(np.float64); b = -pat[q][s].astype(np.float64)
        ok += np.sum((0.5*(a+b))**2); bad += np.sum((0.5*(a-b))**2)
    return float(bad/(ok+bad)) if ok+bad else 0.0
e = viol(lambda p: (rp[p], cs[S._reorder_all(rotperm[p])]))
c = viol(lambda p: (p, cs))
print(f"  mixfresh rot180∘cs (EXACTE) = {100*e:7.4f} %   cs seule (approx) = {100*c:7.4f} %")
json.dump({"mixfresh": {"violation_rot180_cs_EXACT": round(e, 8),
                        "violation_colourswap_approx": round(c, 8)}},
          open(sys.argv[2], "w"), indent=2, sort_keys=True)
if e > 1e-9:
    raise SystemExit("le modèle mixfresh n'est pas antisymétrique")
PY

stage report
cp "$ART/symmetry-report.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=L3_EXACT_FOLD_MIXFRESH_READY
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
