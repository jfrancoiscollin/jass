#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One-shot installer for a fresh Hetzner Cloud / dedicated Ubuntu 24.04
# server that will act as a Jass GitOps runner. Run once as root:
#
#     curl -sSL https://raw.githubusercontent.com/jfrancoiscollin/jass/main/infra/bootstrap.sh | bash
#
# What it does:
#   1. Installs build deps + python3 (no torch by default — we mostly
#      do data-gen here; training is opt-in via INSTALL_TORCH=1)
#   2. Clones /root/jass at main
#   3. Builds the jass binary (Release)
#   4. Generates a dedicated SSH key so the runner can `git push`
#      without bundling a PAT. Prints the public key + the URL to
#      paste it into.
#   5. Installs and enables the runner systemd timer (ticks every 5
#      minutes; idempotent — second tick is a no-op if no job is
#      queued and no job is in flight).
#
# After the script finishes you MUST:
#   - Open the printed GitHub deploy-key URL and paste the SSH key,
#     ticking "Allow write access".
#
# That's the only manual GitHub step. Once it's done you can `exit`
# and never SSH back: jobs are scheduled by committing
# `jobs/queue/<id>.sh` files from anywhere.
set -euo pipefail

REPO_URL_SSH="git@github.com:jfrancoiscollin/jass.git"
REPO_URL_HTTPS="https://github.com/jfrancoiscollin/jass.git"
REPO_DIR="/root/jass"
RUNNER_KEY="/root/.ssh/jass_runner"
INSTALL_TORCH="${INSTALL_TORCH:-0}"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "must run as root" >&2; exit 1
fi

log "1/6 apt update + install base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    build-essential cmake git curl wget unzip jq tmux htop \
    python3 python3-pip python3-venv \
    ca-certificates openssh-client

log "2/6 cloning $REPO_URL_HTTPS"
if [[ ! -d "$REPO_DIR/.git" ]]; then
    git clone --depth=1 "$REPO_URL_HTTPS" "$REPO_DIR"
else
    git -C "$REPO_DIR" fetch --depth=1 origin main
    git -C "$REPO_DIR" reset --hard origin/main
fi

log "3/6 building jass (Release)"
cmake -S "$REPO_DIR" -B "$REPO_DIR/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$REPO_DIR/build" -j
"$REPO_DIR/build/jass" --version 2>/dev/null || true
echo "position fen W:W31-50:B1-15" | "$REPO_DIR/build/jass" | head -1

log "4/6 generating dedicated SSH key for git push"
mkdir -p /root/.ssh
chmod 700 /root/.ssh
if [[ ! -f "$RUNNER_KEY" ]]; then
    ssh-keygen -t ed25519 -C "jass-runner@$(hostname)" -f "$RUNNER_KEY" -N ""
fi
# Make git/ssh use this key for github.com automatically.
cat > /root/.ssh/config <<EOF
Host github.com
    HostName github.com
    User git
    IdentityFile $RUNNER_KEY
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
EOF
chmod 600 /root/.ssh/config

# Switch the local clone to the SSH URL so push goes via this key.
git -C "$REPO_DIR" remote set-url origin "$REPO_URL_SSH"

# Configure committer identity for runner commits.
git -C "$REPO_DIR" config user.name  "Jass Runner"
git -C "$REPO_DIR" config user.email "jass-runner@$(hostname)"

log "5/6 installing systemd unit + timer"
install -m 0644 "$REPO_DIR/infra/jass-runner.service" /etc/systemd/system/jass-runner.service
install -m 0644 "$REPO_DIR/infra/jass-runner.timer"   /etc/systemd/system/jass-runner.timer
systemctl daemon-reload
systemctl enable --now jass-runner.timer

if [[ "$INSTALL_TORCH" == "1" ]]; then
    log "6/6 installing torch + numpy (CPU-only, large download)"
    pip3 install --break-system-packages --quiet \
        numpy torch --index-url https://download.pytorch.org/whl/cpu
else
    log "6/6 skipping torch (set INSTALL_TORCH=1 to enable)"
fi

echo
echo "================================================================"
echo "  Bootstrap done. ONE manual step remains:"
echo
echo "  Open this URL in a browser:"
echo "      https://github.com/jfrancoiscollin/jass/settings/keys/new"
echo
echo "  Title:  jass-runner@$(hostname)"
echo "  Key:    (paste the line below)"
echo "  ✅ Allow write access"
echo
echo "----------------------- public key -----------------------"
cat "$RUNNER_KEY.pub"
echo "-----------------------------------------------------------"
echo
echo "  Then verify the runner can talk to GitHub:"
echo "      sudo -u root ssh -T git@github.com"
echo "  (expect: 'Hi jfrancoiscollin/jass! You've successfully...')"
echo
echo "  Timer status:    systemctl status jass-runner.timer"
echo "  Next tick:       systemctl list-timers jass-runner.timer"
echo "  Live logs:       journalctl -fu jass-runner.service"
echo "================================================================"
