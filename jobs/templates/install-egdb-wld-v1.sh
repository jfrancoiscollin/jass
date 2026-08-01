#!/usr/bin/env bash
# Installe la bitbase WLD 2-7 (egdb_intl) sur la box courante.
#
# Portage runner-v3 de `home-0004-egdb-install`, qui l'avait posée sur HOME. La
# sonde `cpx62-1125` a établi que cpx62 n'en a AUCUNE trace : ni base, ni
# bibliothèque, ni répertoire. Les portes de succession en ont besoin — sans elle
# leur Elo n'est pas comparable à celui des promotions antérieures.
#
# Chaîne : megatools → mega.nz (~3,5 Go) → innoextract sur l'installeur Inno
# (~4,8 Go extraits) → build `JASS_EGDB=ON` → self-test natif.
#
# ⚠️ Ce job SORT DE LA BOX : il télécharge depuis mega.nz et github. C'est le
# seul de la campagne dans ce cas, et il est lancé sur demande explicite de JFC.
#
# Idempotent : si la base est déjà extraite, il saute directement au self-test.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_HOST:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

DBDIR=/root/egdb_db
EXDIR=/root/egdb_extracted
APP="$EXDIR/app"
WLD27="${WLD27_URL:-https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA}"
INNO_URL="https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz"
NEED_GB="${NEED_GB:-12}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm /root | awk 'NR==2{print $4}')"
        printf 'dbdir_mb=%s\n' "$(du -sm "$DBDIR" 2>/dev/null | cut -f1 || echo 0)"
        # `2>/dev/null` masque le message, pas le code de retour : tant que $APP
        # n'existe pas, `find` rend 1, `pipefail` propage, et le trap ERR écrit
        # dans RESULTS. C'est ce qui a sali le rapport de cpx62-1128.
        printf 'app_files=%s\n' "$(find "$APP" -maxdepth 1 -type f 2>/dev/null | wc -l || true)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done ) &
  MON="$!"
}
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build-egdb" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
HOST="$(hostname)"
[ "$HOST" = "$EXPECTED_HOST" ] || die "box inattendue : $HOST (attendu $EXPECTED_HOST)"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "authorization missing"
monitor

stage disk-guard
AVAIL_MB=$(df -Pm /root | awk 'NR==2{print $4}')
say "  /root libre = ${AVAIL_MB} Mo (besoin ~${NEED_GB} Go)"
if [ "$(find "$APP" -maxdepth 1 -name 'db2.idx1' 2>/dev/null | wc -l || true)" -eq 0 ]; then
  [ "${AVAIL_MB:-0}" -ge $((NEED_GB * 1024)) ] ||
    die "moins de ${NEED_GB} Go libres — le téléchargement + extraction en demande autant"
fi

stage megatools
# ⚠️ `set +e` NE SUFFIT PAS : en bash le trap ERR se déclenche indépendamment de
# `errexit`, et le nôtre finit par `exit`. Un `command -v` qui ne trouve rien
# rend 1, déclenche le trap, et tue le job — c'est exactement ce qui a fait
# échouer cpx62-1126 en trente secondes. Toute la découverte d'outils doit donc
# ABSORBER l'échec (`|| true`), pas seulement désactiver errexit.
MT="$(command -v megatools || true)"
if [ -z "$MT" ]; then
  say "  megatools absent — installation via apt"
  apt-get update -qq  > "$W/apt.log" 2>&1 || say "  (apt-get update non concluant, on continue)"
  apt-get install -y -qq megatools >> "$W/apt.log" 2>&1 || say "  (apt-get install KO)"
  MT="$(command -v megatools || true)"
fi
if [ -z "$MT" ]; then
  say "  repli : apt-get download + dpkg-deb"
  rm -rf "$W/mt"; mkdir -p "$W/mt"
  ( cd "$W/mt" && apt-get download megatools >> "$W/apt.log" 2>&1 || true
    D=$(ls megatools_*.deb 2>/dev/null | head -1 || true)
    [ -n "$D" ] && dpkg-deb -x "$D" "$W/mt/x" || true ) || true
  MT="$(find "$W/mt" -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1 || true)"
fi
[ -n "$MT" ] || die "megatools introuvable après apt et repli dpkg — voir apt.log ; la box a-t-elle accès au réseau ?"
chmod +x "$MT" 2>/dev/null || true
"$MT" dl --help > /dev/null 2>&1 || die "megatools présent mais inutilisable ($MT)"
say "  megatools ✓ ($MT)"

stage download-wld
if find "$APP" -maxdepth 1 -name 'db2.idx1' 2>/dev/null | grep -q . ; then
  say "  base déjà extraite — téléchargement sauté"
elif find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | grep -q .; then
  say "  installeur déjà présent — téléchargement sauté"
else
  mkdir -p "$DBDIR"
  say "  téléchargement mega.nz (~3,5 Go, peut prendre 30-60 min)"
  timeout 7200 "$MT" dl --no-progress --path "$DBDIR" "$WLD27" > "$W/dl.log" 2>&1 ||
    die "téléchargement en échec (rc=$?) — voir dl.log ; la box a-t-elle accès à mega.nz ?"
  say "  téléchargé, $(du -sh "$DBDIR" 2>/dev/null | cut -f1)"
fi

stage extract
if ! find "$APP" -maxdepth 1 -name 'db2.idx1' 2>/dev/null | grep -q .; then
  SETUP="$(find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | head -1 || true)"
  [ -n "$SETUP" ] || die "aucun installeur trouvé — le téléchargement a échoué silencieusement"
  rm -rf "$W/ie"; mkdir -p "$W/ie"
  curl -sL --max-time 180 "$INNO_URL" -o "$W/ie/ie.tar.xz" || die "innoextract : téléchargement KO"
  ( cd "$W/ie" && tar xJf ie.tar.xz )
  IE="$(find "$W/ie" -path '*/bin/amd64/innoextract' -type f 2>/dev/null | head -1 || true)"
  [ -n "$IE" ] || die "innoextract introuvable dans l'archive"
  chmod +x "$IE"
  rm -rf "$EXDIR"; mkdir -p "$EXDIR"
  ( cd "$DBDIR" && "$IE" --extract --output-dir "$EXDIR" "$SETUP" ) > "$W/inno.log" 2>&1 ||
    die "innoextract en échec — voir inno.log"
  # L'installeur ne sert plus une fois la base extraite : ~3,5 Go rendus au disque.
  if find "$APP" -maxdepth 1 -name 'db2.idx1' | grep -q .; then
    rm -rf "$DBDIR"; say "  installeur supprimé, ~3,5 Go rendus au disque"
  fi
fi
NFILES="$(find "$APP" -maxdepth 1 -type f 2>/dev/null | wc -l || echo 0)"
find "$APP" -maxdepth 1 -name 'db2.idx1' | grep -q . || die "base incomplète : db2.idx1 manquant"
find "$APP" -maxdepth 1 -name 'db5.idx1' | grep -q . || die "base incomplète : db5.idx1 manquant"
say "  base ✓ $NFILES fichiers, $(du -sh "$APP" 2>/dev/null | cut -f1)"

stage build-and-selfcheck
[ -d /root/egdb_intl ] ||
  git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1 ||
  die "clone egdb_intl en échec"
cmake -S . -B "$W/build-egdb" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl > "$W/cmake.log" 2>&1 || die "cmake KO — voir cmake.log"
cmake --build "$W/build-egdb" -j"$(nproc)" --target jass egdb_intl > "$W/build.log" 2>&1 ||
  die "build KO — voir build.log"
# Le contrôle qui compte : le moteur lit-il vraiment la base ? Des hashes ne
# diraient rien d'un jeu de fichiers présent mais illisible par la bibliothèque.
"$W/build-egdb/jass" --egdb-selfcheck "$APP" 2000 > "$W/selfcheck.log" 2>&1 ||
  die "self-check EGDB en échec — voir selfcheck.log"
cp "$W/selfcheck.log" "$ART/egdb-selfcheck.log"
say "  self-check : $(tail -1 "$W/selfcheck.log")"

stage report
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$HOST" "$APP" "$NFILES" "$DFA" <<'PY'
import json, sys
out, host, app, nfiles, free = sys.argv[1:6]
json.dump({"schema": 1, "verdict": f"EGDB_INSTALLED_{host}", "host": host,
           "egdb_path": app, "files": int(nfiles), "disk_free_mb": int(free),
           "diagnostic_only": True, "promotion_authorized": False,
           "automatic_next_job": None},
          open(out, "w"), indent=2, sort_keys=True)
open(out, "a").write("\n")
PY
VERDICT="EGDB_INSTALLED_${HOST}"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT chemin=$APP fichiers=$NFILES libre=${DFA}Mo promotion=false"
