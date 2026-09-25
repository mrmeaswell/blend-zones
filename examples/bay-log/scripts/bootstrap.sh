#!/usr/bin/env bash
# ============================================================
# Bay Log — in-container setup
#
# Runs INSIDE a fresh Debian LXC. Installs the service natively
# (no Docker): a venv under /opt/blendzone, a dedicated system user,
# a systemd unit, and nginx in front on port 80.
#
# Safe to re-run: it updates code and restarts rather than starting over,
# and it never overwrites the database, the uploads, or the LTI keypair.
#
#   REPO_URL=https://github.com/you/blendzone.git bash bootstrap.sh
# ============================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/blendzone}"
APP_USER="${APP_USER:-blendzone}"
APP_PORT="${APP_PORT:-8080}"
DATA_DIR="${DATA_DIR:-/var/lib/blendzone}"
REPO_URL="${REPO_URL:-}"
REPO_BRANCH="${REPO_BRANCH:-main}"
# Read-only SSH deploy key, for cloning a private repo. Optional: leave
# unset for a public repo over HTTPS.
DEPLOY_KEY="${DEPLOY_KEY:-/root/.ssh/baylog_deploy_key}"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root inside the container."

# ---------- packages ----------
log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  python3 python3-venv python3-pip \
  nginx sqlite3 git ca-certificates curl tzdata >/dev/null

timedatectl set-timezone America/Los_Angeles 2>/dev/null || true

# ---------- user + dirs ----------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Creating system user $APP_USER"
  useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR" "$DATA_DIR/uploads" "$DATA_DIR/lti_cache"

# ---------- git auth ----------
# If a deploy key is present, use it for every git call below. accept-new
# trusts GitHub's host key on first contact but still pins it afterwards,
# so a later key change fails loudly instead of being accepted silently.
if [[ -f "$DEPLOY_KEY" ]]; then
  log "Using deploy key $DEPLOY_KEY for git"
  chmod 600 "$DEPLOY_KEY"
  export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.ssh/known_hosts"
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
elif [[ "$REPO_URL" == git@* || "$REPO_URL" == ssh://* ]]; then
  die "REPO_URL is an SSH URL but no deploy key at $DEPLOY_KEY.
     Push one in from the Proxmox host:
       pct push <ctid> <keyfile> /root/.ssh/baylog_deploy_key --perms 0600
     or set DEPLOY_KEY=<path>."
fi

# ---------- code ----------
if [[ -n "$REPO_URL" ]]; then
  if [[ -d "$APP_DIR/.git" ]]; then
    log "Updating code from $REPO_URL"
    git -C "$APP_DIR" remote set-url origin "$REPO_URL"
    git -C "$APP_DIR" fetch --depth 1 origin "$REPO_BRANCH"
    git -C "$APP_DIR" reset --hard "origin/$REPO_BRANCH"
  else
    log "Cloning $REPO_URL"
    rm -rf "${APP_DIR:?}"/* 2>/dev/null || true
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
  fi
elif [[ ! -f "$APP_DIR/app/main.py" ]]; then
  warn "No REPO_URL and no code at $APP_DIR."
  warn "Copy the project in (from the Proxmox host:"
  warn "  pct push <ctid> blendzone.tar.gz /root/blendzone.tar.gz"
  warn "  pct exec <ctid> -- tar xzf /root/blendzone.tar.gz -C $APP_DIR --strip-components=1)"
  warn "then re-run this script. Prerequisites are installed and waiting."
  exit 0
else
  log "Using code already present at $APP_DIR"
fi

# ---------- python env ----------
log "Building virtualenv"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---------- secrets + LTI keys ----------
ENV_FILE="/etc/blendzone.env"
if [[ ! -f "$ENV_FILE" ]]; then
  log "Writing $ENV_FILE"
  SECRET="$(head -c 32 /dev/urandom | base64 | tr -d '\n/+=')"
  cat > "$ENV_FILE" <<EOF
# Bay Log service environment. Edit, then: systemctl restart blendzone
BZ_DB_PATH=$DATA_DIR/baylog.db
BZ_UPLOAD_DIR=$DATA_DIR/uploads
BZ_SECRET_KEY=$SECRET

# Set to 1 once the Canvas Developer Key is wired up, to require an LTI
# launch for every request. Leave 0 while testing on the lab network.
BZ_REQUIRE_AUTH=0

# Set to 0 in production to remove the ?as=<role> role override.
BZ_DEV_AUTH=1
EOF
  chmod 640 "$ENV_FILE"
  chown root:"$APP_USER" "$ENV_FILE"
else
  log "Keeping existing $ENV_FILE"
fi

if [[ ! -f "$APP_DIR/config/keys/private.pem" ]]; then
  log "Generating LTI signing keypair"
  "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/generate_keys.py"
else
  log "LTI keypair already present — leaving it alone (replacing it would"
  log "    invalidate the Canvas Developer Key)."
fi

# ---------- ownership ----------
# Code stays root-owned and read-only to the service; only data and the
# LTI cache/keys the app must read are opened up.
chown -R root:root "$APP_DIR"
chown -R "$APP_USER":"$APP_USER" "$DATA_DIR"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR/config/keys"
chmod 750 "$APP_DIR/config/keys"

# ---------- systemd ----------
log "Installing systemd unit"
install -m 0644 "$APP_DIR/deploy/blendzone.service" /etc/systemd/system/blendzone.service
sed -i "s|__APP_DIR__|$APP_DIR|g; s|__APP_USER__|$APP_USER|g; s|__APP_PORT__|$APP_PORT|g" \
  /etc/systemd/system/blendzone.service
systemctl daemon-reload
systemctl enable blendzone >/dev/null 2>&1
systemctl restart blendzone

# ---------- nginx ----------
log "Configuring nginx"
install -m 0644 "$APP_DIR/deploy/nginx-blendzone.conf" /etc/nginx/sites-available/blendzone
sed -i "s|__APP_PORT__|$APP_PORT|g" /etc/nginx/sites-available/blendzone
ln -sf /etc/nginx/sites-available/blendzone /etc/nginx/sites-enabled/blendzone
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# ---------- verify ----------
log "Waiting for the service to answer"
OK=0
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then OK=1; break; fi
  sleep 1
done

echo
if [[ $OK -eq 1 ]]; then
  log "Service healthy."
  echo "  direct:  $(curl -fsS http://127.0.0.1:${APP_PORT}/api/health)"
  echo "  nginx:   $(curl -fsS http://127.0.0.1/api/health || echo 'nginx check failed')"
  echo "  lti:     $(curl -fsS http://127.0.0.1/lti/health || echo 'n/a')"
  echo "  address: http://$(hostname -I | awk '{print $1}')/"
else
  warn "Service did not come up. Recent logs:"
  journalctl -u blendzone -n 40 --no-pager || true
  exit 1
fi
