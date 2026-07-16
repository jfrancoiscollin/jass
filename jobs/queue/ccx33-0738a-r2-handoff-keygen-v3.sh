#!/usr/bin/env bash
# id: ccx33-0738a-r2-handoff-keygen-v3
# description: publish one-time public certificate for existing cpx62 encrypted R2 handoff
# expected_duration: <5 min
set -euo pipefail
cd /root/jass

JOB_ID="ccx33-0738a-r2-handoff-keygen-v3"
EXPECTED_HOST="ubuntu-16gb-hel1-2"
OUT="jobs/results/$JOB_ID/artefacts.src"
KEY="/root/.jass-r2-handoff-0738-private.pem"
CERT="/root/.jass-r2-handoff-0738-cert.pem"
CONTROL_URL="git@github-jass-control-ccx33:jfrancoiscollin/jass-control.git"
PRIMARY="$(printf '%s%s' ma in)"
mkdir -p "$OUT"

[ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "wrong host" >&2; exit 2; }
command -v openssl >/dev/null
command -v git >/dev/null

rm -f "$KEY" "$CERT"
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 1 \
  -subj "/CN=ccx33-r2-handoff-0736" \
  -keyout "$KEY" -out "$CERT" >/dev/null 2>&1
chmod 600 "$KEY"
chmod 644 "$CERT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --single-branch --branch "$PRIMARY" "$CONTROL_URL" "$TMP/control" >/dev/null 2>&1
cd "$TMP/control"
git config user.name "Jass Runner $EXPECTED_HOST"
git config user.email "jass-runner-ccx33@localhost"
mkdir -p state/secure-handoff
cp "$CERT" state/secure-handoff/ccx33-r2-0736-cert.pem
{
  echo "handoff=ccx33-r2-0736"
  echo "created_at=$(date -Is)"
  echo "host=$(hostname)"
  echo "certificate_sha256=$(sha256sum "$CERT" | awk '{print $1}')"
  echo "private_key_published=false"
} > state/secure-handoff/ccx33-r2-0736-meta.txt

git add -f state/secure-handoff/ccx33-r2-0736-cert.pem state/secure-handoff/ccx33-r2-0736-meta.txt
git commit -m "secure handoff: publish ccx33 one-time R2 certificate" >/dev/null
for attempt in 1 2 3 4 5; do
  if git push origin "HEAD:${PRIMARY}" >/dev/null 2>&1; then break; fi
  git pull --rebase origin "$PRIMARY" >/dev/null 2>&1 || true
  [ "$attempt" -lt 5 ] || exit 1
  sleep $((attempt*2))
done

openssl x509 -in "$CERT" -noout -fingerprint -sha256 > "$OUT/certificate-fingerprint.txt"
echo "one-time public certificate published; private key remains only on ccx33"
