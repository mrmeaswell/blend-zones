#!/usr/bin/env bash
# ============================================================
# Bay Log — Proxmox LXC provisioning
#
# Run this ON THE PROXMOX HOST (node shell), not inside a container.
# It creates an unprivileged Debian CT, pushes the bootstrap script in,
# and runs it. Idempotent-ish: it refuses to clobber an existing CTID.
#
#   ./provision-ct.sh                      # uses defaults below
#   CTID=305 CT_IP=dhcp ./provision-ct.sh  # override anything via env
#
# Every setting is an env-var override so this can be re-run for a
# second blend-zone tool without editing the file.
# ============================================================

set -euo pipefail

CTID="${CTID:-301}"
HOSTNAME_CT="${HOSTNAME_CT:-baylog}"
CT_STORAGE="${CT_STORAGE:-local-lvm}"
CT_DISK_GB="${CT_DISK_GB:-8}"
CT_CORES="${CT_CORES:-2}"
CT_MEMORY_MB="${CT_MEMORY_MB:-1024}"
CT_SWAP_MB="${CT_SWAP_MB:-512}"
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"
# CT_IP: either "dhcp" or a CIDR like 192.168.1.50/24 (then set CT_GW)
CT_IP="${CT_IP:-dhcp}"
CT_GW="${CT_GW:-}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
# Leave TEMPLATE_NAME unset to auto-pick the newest Debian 12 template.
# Pinning a version here is a trap: Proxmox retires point releases from the
# repo, so a hardcoded 12.7-1 stops resolving once 12.12-1 supersedes it.
TEMPLATE_NAME="${TEMPLATE_NAME:-}"
TEMPLATE_MAJOR="${TEMPLATE_MAJOR:-12}"
REPO_URL="${REPO_URL:-}"
# Path on THIS host to a read-only SSH deploy key, if the repo is private.
# It gets pushed into the container so the container can clone.
DEPLOY_KEY_FILE="${DEPLOY_KEY_FILE:-}"
START_AFTER="${START_AFTER:-1}"
CT_DEPLOY_KEY="/root/.ssh/baylog_deploy_key"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- preflight ----------
command -v pct >/dev/null 2>&1 || die "pct not found — run this on the Proxmox host."
[[ $EUID -eq 0 ]] || die "Run as root."

if pct status "$CTID" >/dev/null 2>&1; then
  die "CTID $CTID already exists. Pick a free ID with: CTID=<id> $0"
fi

if [[ "$CT_IP" != "dhcp" && -z "$CT_GW" ]]; then
  die "Static CT_IP given without CT_GW. Set CT_GW=<gateway-ip>."
fi

if [[ -n "$DEPLOY_KEY_FILE" && ! -f "$DEPLOY_KEY_FILE" ]]; then
  die "DEPLOY_KEY_FILE=$DEPLOY_KEY_FILE does not exist."
fi

if [[ "$REPO_URL" == git@* || "$REPO_URL" == ssh://* ]] && [[ -z "$DEPLOY_KEY_FILE" ]]; then
  die "REPO_URL is an SSH URL, so a deploy key is required.
     Set DEPLOY_KEY_FILE=<path to the private key on this host>."
fi

# ---------- template ----------
# Resolution order: an already-downloaded template on this storage, then the
# newest matching one still offered by the repo.
if [[ -z "$TEMPLATE_NAME" ]]; then
  TEMPLATE_NAME="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null \
    | awk '{print $1}' | sed 's|.*/||' \
    | grep -E "^debian-${TEMPLATE_MAJOR}-standard_.*amd64\.tar\.(zst|gz|xz)$" \
    | sort -V | tail -1 || true)"

  if [[ -n "$TEMPLATE_NAME" ]]; then
    log "Using template already on $TEMPLATE_STORAGE: $TEMPLATE_NAME"
  else
    log "No local Debian $TEMPLATE_MAJOR template — checking the repo."
    pveam update >/dev/null 2>&1 || warn "pveam update failed; continuing."
    TEMPLATE_NAME="$(pveam available --section system 2>/dev/null \
      | awk '{print $2}' \
      | grep -E "^debian-${TEMPLATE_MAJOR}-standard_.*amd64\.tar\.(zst|gz|xz)$" \
      | sort -V | tail -1 || true)"
    [[ -n "$TEMPLATE_NAME" ]] || die "No Debian $TEMPLATE_MAJOR template available.
     Pick one from 'pveam available --section system' and pass
     TEMPLATE_NAME=<name>, or set TEMPLATE_MAJOR=<13|11>."
    log "Selected newest available: $TEMPLATE_NAME"
  fi
fi

TEMPLATE_REF="${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE_NAME}"
if ! pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep -q "$TEMPLATE_NAME"; then
  log "Downloading $TEMPLATE_NAME"
  pveam update >/dev/null 2>&1 || warn "pveam update failed; trying download anyway."
  if ! pveam download "$TEMPLATE_STORAGE" "$TEMPLATE_NAME"; then
    echo
    warn "Could not download $TEMPLATE_NAME. Available Debian templates:"
    pveam available --section system | grep -i debian || true
    die "Set TEMPLATE_NAME=<one of the above> and re-run."
  fi
fi

# ---------- root password ----------
if [[ -z "${CT_ROOT_PASSWORD:-}" ]]; then
  CT_ROOT_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)"
  GENERATED_PW=1
fi

# ---------- create ----------
if [[ "$CT_IP" == "dhcp" ]]; then
  NET="name=eth0,bridge=${CT_BRIDGE},ip=dhcp"
else
  NET="name=eth0,bridge=${CT_BRIDGE},ip=${CT_IP},gw=${CT_GW}"
fi

log "Creating CT $CTID ($HOSTNAME_CT) on $CT_STORAGE"
pct create "$CTID" "$TEMPLATE_REF" \
  --hostname "$HOSTNAME_CT" \
  --cores "$CT_CORES" \
  --memory "$CT_MEMORY_MB" \
  --swap "$CT_SWAP_MB" \
  --rootfs "${CT_STORAGE}:${CT_DISK_GB}" \
  --net0 "$NET" \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --password "$CT_ROOT_PASSWORD" \
  --description "Bay Log — blend-zone tool service (Automotive x IT). Provisioned by provision-ct.sh."

log "Starting CT $CTID"
pct start "$CTID"

# Wait for the container to actually have working DNS/network before apt runs.
log "Waiting for network inside the container"
for i in $(seq 1 30); do
  if pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1; then
    break
  fi
  sleep 2
  [[ $i -eq 30 ]] && die "Container has no working DNS after 60s. Check bridge $CT_BRIDGE / gateway."
done

# ---------- bootstrap ----------
log "Pushing bootstrap script into CT $CTID"
pct push "$CTID" "${SCRIPT_DIR}/bootstrap.sh" /root/bootstrap.sh --perms 0755

if [[ -n "$DEPLOY_KEY_FILE" ]]; then
  log "Pushing deploy key into CT $CTID"
  pct exec "$CTID" -- mkdir -p /root/.ssh
  pct exec "$CTID" -- chmod 700 /root/.ssh
  pct push "$CTID" "$DEPLOY_KEY_FILE" "$CT_DEPLOY_KEY" --perms 0600
fi

log "Running bootstrap inside CT $CTID"
if [[ -n "$REPO_URL" ]]; then
  pct exec "$CTID" -- env REPO_URL="$REPO_URL" bash /root/bootstrap.sh
else
  warn "No REPO_URL set — bootstrap will install prerequisites and wait for code."
  pct exec "$CTID" -- bash /root/bootstrap.sh
fi

# ---------- report ----------
CT_ADDR="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"

echo
log "Done."
echo "  CTID:       $CTID ($HOSTNAME_CT)"
echo "  IP address: ${CT_ADDR:-unknown — check 'pct exec $CTID -- ip a'}"
echo "  Tool URL:   http://${CT_ADDR:-<ct-ip>}/"
echo "  Health:     http://${CT_ADDR:-<ct-ip>}/api/health"
echo "  API docs:   http://${CT_ADDR:-<ct-ip>}/docs"
if [[ "${GENERATED_PW:-0}" == "1" ]]; then
  echo
  echo "  CT root password (generated, save it now): $CT_ROOT_PASSWORD"
fi
echo
echo "Next: see docs/runbook.md for TLS and the Canvas Developer Key wiring."
