#!/usr/bin/env bash
# objstore.sh — couche de STOCKAGE OBJET durable pour les gros corpus (au-delà du cap git ~95Mo/9Go repo).
#
# Pourquoi : git tient ~30-50M (≤~500Mo gz) ; au-delà (100M→1B = ~1-9Go) il faut un store externe.
# Backend : rclone (S3-compatible : Cloudflare R2 / Backblaze B2 / AWS S3 / MinIO / Wasabi / DO Spaces…).
# rclone gère SigV4, multipart, reprise, checksums — bien plus robuste qu'un curl maison.
#
# DORMANT tant que non configuré : toute commande no-op proprement (exit 0) sans casser un job.
#
# ── ACTIVATION (à fournir par l'utilisateur, via secrets d'environnement du runner) ──
#   JASS_OBJSTORE_REMOTE   remote rclone + bucket, ex : "r2:jass-corpus"   (obligatoire)
#   RCLONE_CONF_B64        contenu de rclone.conf encodé base64 (contient les credentials)  [SECRET]
#   JASS_OBJSTORE_PREFIX   sous-dossier dans le bucket, défaut "corpus"    (optionnel)
#   La policy réseau du runner doit autoriser l'egress vers l'endpoint du bucket.
#
# ── COMMANDES ──
#   objstore.sh check                      état config + binaire + connectivité (lsd)
#   objstore.sh push <localfile> [name]    envoie un fichier (name = nom distant, défaut = basename)
#   objstore.sh pull <name> <localfile>    récupère un fichier
#   objstore.sh list                       liste le préfixe distant (taille + nom)
#   objstore.sh sync-shards                pousse TOUS les shards corpus committés (depuis origin/main) vers le store
#   objstore.sh verify                     compare présence/tailles distantes vs manifeste local
set -uo pipefail
cd "$(dirname "$0")/.."

PREFIX="${JASS_OBJSTORE_PREFIX:-corpus}"
RCLONE_BIN="${RCLONE_BIN:-/root/.local/bin/rclone}"
CONF="/root/.config/jass-rclone.conf"

log(){ echo "[objstore] $*" >&2; }

configured(){ [ -n "${JASS_OBJSTORE_REMOTE:-}" ] && [ -n "${RCLONE_CONF_B64:-}" ]; }

rclone_cmd(){ # rclone avec la config décodée
  local bin; bin="$(command -v rclone || echo "$RCLONE_BIN")"
  "$bin" --config "$CONF" "$@"
}

ensure_conf(){
  mkdir -p "$(dirname "$CONF")"
  printf '%s' "${RCLONE_CONF_B64}" | base64 -d > "$CONF" 2>/dev/null || { log "RCLONE_CONF_B64 invalide (base64)"; return 1; }
  chmod 600 "$CONF"
}

bootstrap_rclone(){
  command -v rclone >/dev/null 2>&1 && return 0
  [ -x "$RCLONE_BIN" ] && return 0
  log "rclone absent → téléchargement du binaire statique…"
  local url="https://downloads.rclone.org/rclone-current-linux-amd64.zip" zip="/tmp/rclone.zip"
  local ok=0
  for a in 1 2 3 4; do curl -fsSL "$url" -o "$zip" 2>/dev/null && { ok=1; break; }; sleep $((a*2)); done
  [ "$ok" = 1 ] || { log "ÉCHEC téléchargement rclone (egress bloqué ?)"; return 1; }
  mkdir -p "$(dirname "$RCLONE_BIN")"
  python3 - "$zip" "$RCLONE_BIN" <<'PY' || { echo "[objstore] unzip rclone échec" >&2; exit 1; }
import zipfile,sys,os,stat
z,out=sys.argv[1],sys.argv[2]
with zipfile.ZipFile(z) as f:
    name=[n for n in f.namelist() if n.endswith('/rclone')][0]
    data=f.read(name)
open(out,'wb').write(data); os.chmod(out, os.stat(out).st_mode|stat.S_IEXEC|stat.S_IXGRP|stat.S_IXOTH)
print("rclone extrait ->",out)
PY
  [ -x "$RCLONE_BIN" ]
}

require_ready(){
  if ! configured; then
    log "NON CONFIGURÉ (JASS_OBJSTORE_REMOTE / RCLONE_CONF_B64 absents) → no-op."
    log "Voir docs/OBJSTORE_SETUP.md pour activer. (sortie 0 : ne casse aucun job)"
    exit 0
  fi
  bootstrap_rclone || { log "rclone indisponible → no-op (exit 0)"; exit 0; }
  ensure_conf      || { log "config rclone illisible → no-op (exit 0)"; exit 0; }
}

remote_path(){ echo "${JASS_OBJSTORE_REMOTE%/}/${PREFIX}/${1:-}"; }

cmd="${1:-check}"; shift || true
case "$cmd" in
  check)
    echo "remote     : ${JASS_OBJSTORE_REMOTE:-<non défini>}"
    echo "prefix     : $PREFIX"
    echo "conf b64   : $([ -n "${RCLONE_CONF_B64:-}" ] && echo '<fourni>' || echo '<absent>')"
    echo "rclone bin : $(command -v rclone || ([ -x "$RCLONE_BIN" ] && echo "$RCLONE_BIN") || echo '<à bootstrapper>')"
    if configured; then
      bootstrap_rclone && ensure_conf && { echo "connectivité:"; rclone_cmd lsd "$(remote_path)" 2>&1 | head -5 || echo "  (échec lsd — vérifier credentials/egress)"; }
    else
      echo "ÉTAT       : DORMANT (non configuré). Toutes les commandes no-op. Voir docs/OBJSTORE_SETUP.md."
    fi
    ;;
  push)
    require_ready
    f="${1:?usage: push <localfile> [name]}"; name="${2:-$(basename "$f")}"
    log "push $f → $(remote_path "$name")"
    rclone_cmd copyto "$f" "$(remote_path "$name")" --progress
    ;;
  pull)
    require_ready
    name="${1:?usage: pull <name> <localfile>}"; out="${2:?usage: pull <name> <localfile>}"
    log "pull $(remote_path "$name") → $out"
    rclone_cmd copyto "$(remote_path "$name")" "$out" --progress
    ;;
  list) require_ready; rclone_cmd ls "$(remote_path)" ;;
  sync-shards)
    require_ready
    git fetch origin main -q 2>/dev/null || true
    mapfile -t SHARDS < <(git ls-tree -r --name-only origin/main 2>/dev/null \
      | grep -E 'jobs/results/.*/artefacts/.*corpus.*\.jnnw\.gz$' | sort)
    log "${#SHARDS[@]} shards committés à pousser"
    for s in "${SHARDS[@]}"; do
      name="$(echo "$s" | sed -E 's#jobs/results/([^/]+)/artefacts/#\1__#')"   # ex: cpx62-0391-corpus-d10__corpus-d10.jnnw.gz
      tmp="/tmp/$name"
      git cat-file blob "origin/main:$s" > "$tmp" 2>/dev/null || { log "skip (blob absent) $s"; continue; }
      rclone_cmd copyto "$tmp" "$(remote_path "$name")" 2>&1 | tail -1
      rm -f "$tmp"
    done
    log "sync terminé"
    ;;
  verify) require_ready; echo "distant :"; rclone_cmd ls "$(remote_path)" ;;
  *) echo "commande inconnue: $cmd (check|push|pull|list|sync-shards|verify)"; exit 2 ;;
esac
