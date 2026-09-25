# Bay Log — operations runbook

Native LXC service. No Docker: a Python venv, a systemd unit, and nginx
in front. Everything below assumes the CT created by
`scripts/provision-ct.sh`.

## Layout on the container

| Path | What it is | Backed up? |
|---|---|---|
| `/opt/blendzone` | Application code (root-owned, read-only to the service) | No — it's in git |
| `/var/lib/blendzone/baylog.db` | SQLite database — **the actual records** | Yes |
| `/var/lib/blendzone/uploads/` | Photos and files, one folder per ticket | Yes |
| `/etc/blendzone.env` | Environment: DB path, secret key, auth flags | Yes |
| `/opt/blendzone/config/keys/` | LTI signing keypair | Yes |
| `/etc/systemd/system/blendzone.service` | Service unit | No — it's in git |
| `/etc/nginx/sites-available/blendzone` | Reverse proxy config | No — it's in git |

The three things that are genuinely irreplaceable: the database, the
uploads, and the LTI keypair. Everything else is reproducible from the
repo in one bootstrap run.

## The deployed instance

| | |
|---|---|
| Node | `pve1` (cluster `lab-cluster`, PVE 8.4.19) |
| Container | CTID **301**, hostname `baylog`, unprivileged, `onboot=1` |
| Address | `http://192.0.2.10/` (DHCP on `vmbr0` — see the note below) |
| Template | `debian-12-standard_12.12-1_amd64.tar.zst` |
| Resources | 2 cores, 1 GB RAM, 512 MB swap, 8 GB on `local-lvm` |
| Repo | `git@github.com:<you>/<your-fork>.git` (private, branch `main`) |
| Deploy key | read-only, at `/root/.ssh/baylog_deploy_key` in the CT and `/root/baylog_deploy_key` on the host |

The address came from DHCP, so it can move after a reboot. Either reserve
it on the DHCP server or convert the container to a static address:

```bash
pct set 301 -net0 name=eth0,bridge=vmbr0,ip=192.0.2.10/24,gw=<gateway>
pct reboot 301
```

## Host prerequisites

Two things bit us on first run and will bite again on a fresh node:

- **`git` must be installed on the Proxmox host** to clone this repo there
  in the first place. `apt-get install -y git`.
- If that install fails with *"dpkg was interrupted"*, run
  `dpkg --configure -a` first, then retry. A half-finished earlier
  install (in our case `cloudflared`) leaves apt wedged.

The container itself needs neither — the bootstrap installs its own
packages.

## Provisioning a fresh container

Run on the Proxmox host shell (`pve1` node), not inside a container:

```bash
git clone <repo-url> /root/blendzone && cd /root/blendzone/scripts
REPO_URL=<repo-url> DEPLOY_KEY_FILE=/root/baylog_deploy_key ./provision-ct.sh
```

Drop `DEPLOY_KEY_FILE` if the repo is public. With a private repo over
SSH it's required, and the script pushes the key into the container so
the container can clone and later pull.

Override anything via environment variables — no file edits needed:

```bash
CTID=305 \
HOSTNAME_CT=baylog \
CT_STORAGE=local-lvm \
CT_MEMORY_MB=1024 \
CT_IP=192.168.1.50/24 CT_GW=192.168.1.1 \
REPO_URL=<repo-url> \
./provision-ct.sh
```

Defaults: CTID 301, hostname `baylog`, Debian 12, 2 cores, 1 GB RAM,
8 GB on `local-lvm`, DHCP on `vmbr0`, unprivileged, `onboot=1`.

**Template selection is automatic.** The script prefers a Debian 12
template already on the storage, otherwise it picks the newest one the
repo still offers. Don't pin a point release: Proxmox retires them, so a
hardcoded `12.7-1` starts failing with *"template: no such template"*
once `12.12-1` supersedes it. That is exactly what happened on the first
provisioning run here. Override with `TEMPLATE_NAME=` for an exact build
or `TEMPLATE_MAJOR=13` for a different Debian generation.

## Day-to-day commands

```bash
pct enter 301                          # shell into the container

systemctl status blendzone             # is it running
systemctl restart blendzone            # after changing /etc/blendzone.env
journalctl -u blendzone -f             # live logs
journalctl -u blendzone -n 100         # last 100 lines

curl -s localhost/api/health           # {"status":"ok",...}
curl -s localhost/lti/health           # {"status":"ok","jwk_count":1}
nginx -t && systemctl reload nginx     # after proxy config changes
```

## Deploying a code change

```bash
pct exec 301 -- env REPO_URL=git@github.com:<you>/<your-fork>.git \
  bash /root/bootstrap.sh
```

The deploy key already inside the container is picked up automatically,
so no credentials go on the command line.

Re-running the bootstrap is the deploy path. It pulls the branch,
rebuilds the venv, reinstalls the unit and proxy config, and restarts —
and it deliberately does not touch the database, the uploads, the env
file, or the LTI keys.

## Backups

The whole service state is three paths. From the Proxmox host:

```bash
pct exec 301 -- sqlite3 /var/lib/blendzone/baylog.db ".backup /tmp/baylog-backup.db"
pct pull 301 /tmp/baylog-backup.db ./baylog-$(date +%F).db
pct exec 301 -- tar czf /tmp/uploads.tgz -C /var/lib/blendzone uploads
pct pull 301 /tmp/uploads.tgz ./baylog-uploads-$(date +%F).tgz
```

Use `.backup` rather than copying the file directly — the database runs
in WAL mode, so a raw `cp` of a live DB can capture a torn state.

For the container as a whole, a scheduled Proxmox vzdump of CT 301
covers everything, including the keys and env file.

## Restoring

```bash
systemctl stop blendzone
# put the .db back at /var/lib/blendzone/baylog.db, untar uploads alongside
chown -R blendzone:blendzone /var/lib/blendzone
systemctl start blendzone
```

## Configuration flags

In `/etc/blendzone.env`, then `systemctl restart blendzone`:

| Variable | Default | Meaning |
|---|---|---|
| `BZ_REQUIRE_AUTH` | `0` | `1` = every request needs a session from a Canvas launch |
| `BZ_DEV_AUTH` | `1` | `1` = allows `?as=instructor` role override. **Set to 0 in production** |
| `BZ_SESSION_TTL_HOURS` | `12` | How long a launch session lasts |
| `BZ_MAX_UPLOAD_BYTES` | `15728640` | Per-file upload cap (nginx also caps at 20 MB) |
| `BZ_DB_PATH` | `/var/lib/blendzone/baylog.db` | Database location |
| `BZ_CF_TEAM_DOMAIN` | *(empty)* | Zero Trust team domain, e.g. `yourteam.cloudflareaccess.com` |
| `BZ_CF_ACCESS_AUD` | *(empty)* | Access application AUD tag. Both this and the team domain must be set for Access identity to work |
| `BZ_STAFF_EMAILS` | *(empty)* | Comma-separated addresses granted the `instructor` role |
| `BZ_STAFF_DOMAIN` | *(empty)* | Email suffix granted the `instructor` role, e.g. `@example.edu` |
| `BZ_STUDENT_DOMAIN` | *(empty)* | Email suffix granted the `student` role, e.g. `@student.example.edu` |
| `BZ_ANON_ROLE` | `viewer` | Role for a request with no session and no Access assertion |

While `BZ_DEV_AUTH=1` and `BZ_REQUIRE_AUTH=0`, anyone who can reach the
container can act as any role. That is fine on an isolated lab network
for a walkthrough and not fine otherwise.

## Identity through Cloudflare Access

When the service is published through a Cloudflare tunnel with an Access
application in front of it, Cloudflare authenticates the person before
the request ever reaches uvicorn and forwards a signed assertion in the
`Cf-Access-Jwt-Assertion` header. `app/cf_access.py` verifies that
assertion against the team JWKS, pinned to the application's AUD tag,
and derives the role from the verified email address:

- an address in `BZ_STAFF_EMAILS` → `instructor`
- an address ending in `BZ_STAFF_DOMAIN` → `instructor`
- an address ending in `BZ_STUDENT_DOMAIN` → `student`
- anything else → **403**, even though Cloudflare let them in

The leading `@` on both domain settings is load-bearing. With
`BZ_STAFF_DOMAIN=@example.edu`, an address like `jdoe@student.example.edu` does
not match, because it ends in `.example.edu` rather than `@example.edu`. Drop the
`@` and every student silently becomes an instructor with sign-off
authority.

Granting a whole domain the `instructor` role grants sign-off on
estimates and QC to everyone with an address at that domain — typically
every employee of the institution. Prefer listing named approvers in
`BZ_STAFF_EMAILS` until you actually need the breadth.

Cloudflare's "Emails ending in" rule is looser than this check: the
dashboard stores and displays the value without the `@`, so a lookalike
domain such as `evil-example.edu` can satisfy the Access policy. It will
still be refused here with a 403. Treat this function, not the Access
policy, as the authorization boundary.

The plain `Cf-Access-Authenticated-User-Email` header is deliberately
ignored. It is trustworthy only if the origin is genuinely unreachable
except through the tunnel, and that is a property that quietly breaks.

Get the AUD tag from Zero Trust → Access → Applications → your app →
Overview. It is not a secret, but a token minted for a *different*
application on the same account will be rejected because of it, which is
the point.

### The anonymous bay terminal

`BZ_ANON_ROLE` covers the shop-floor terminal that nobody signs in to.
It used to be hardcoded to `staff`, which meant that anyone who could
reach the service — including, once the tunnel was published, the open
internet — could approve an estimate or sign off a QC inspection. The
default is now `viewer`, which is not in `signoff_roles` and therefore
cannot sign anything off.

If you want an unauthenticated kiosk to retain sign-off, set
`BZ_ANON_ROLE=staff` explicitly, and only where the network makes that
safe.

## Getting to HTTPS

The container ships HTTP only. Canvas will not launch an LTI tool over
plain HTTP, so pick one before wiring Canvas:

1. **certbot in the container** — needs the container reachable from the
   internet on 80/443 with a public DNS name:
   ```bash
   apt-get install -y certbot python3-certbot-nginx
   certbot --nginx -d baylog.<your-domain>
   ```
2. **Terminate upstream** — pfSense/HAProxy or a Cloudflare Tunnel
   fronting the container. This suits the existing setup better since
   pfSense (VM 110) is already the edge. The unit already passes
   `--proxy-headers` and trusts `X-Forwarded-Proto` from 127.0.0.1;
   if TLS terminates on another host, add that host's IP to
   `--forwarded-allow-ips` in the systemd unit.

Then update the `X-Frame-Options` header in the nginx config — see the
comment at the bottom of `deploy/nginx-blendzone.conf`. Canvas renders
the tool in an iframe, and `SAMEORIGIN` blocks that. Replace it with:

```nginx
add_header Content-Security-Policy
    "frame-ancestors https://<your-institution>.instructure.com" always;
```

## Wiring the Canvas Developer Key

1. Generate keys if the bootstrap hasn't: `.venv/bin/python scripts/generate_keys.py`
2. In Canvas: **Admin → Developer Keys → + LTI Key**, manual entry, with:
   - OpenID Connect Initiation URL: `https://<host>/lti/login`
   - Target Link URI: `https://<host>/lti/launch`
   - Public JWK URL: `https://<host>/lti/jwks`
3. Save, then flip the key **ON** and copy the **Client ID**.
4. Add the app to a course: **Settings → Apps → + App → By Client ID**,
   paste the Client ID. Copy the **Deployment ID** from the app's detail.
5. Put both into `config/lti_config.json`, confirm the issuer key matches
   what Canvas reports, then `systemctl restart blendzone`.
6. Verify: `curl -s https://<host>/lti/health` → `jwk_count: 1`, then
   launch the tool from the course.
7. Once launches work, set `BZ_REQUIRE_AUTH=1` and `BZ_DEV_AUTH=0`.

Do not add comment keys to `lti_config.json` — pylti1p3 treats every
top-level key as an issuer and rejects non-list/dict values with
"Invalid tool conf format." Notes belong in `config/README.md`.

## Troubleshooting

| Symptom | Where to look |
|---|---|
| 502 from nginx | `systemctl status blendzone`; the app isn't listening on 8080 |
| "Could not reach the service" in the UI | `journalctl -u blendzone -n 50` |
| `/lti/health` returns `no-keys` | keypair missing — run `scripts/generate_keys.py` |
| `/lti/health` → "Invalid tool conf format" | a stray comment/string key in `lti_config.json` |
| `/lti/health` → "No such file ... private.pem" | key paths must be `keys/private.pem`, relative to `config/` |
| Canvas: "Invalid Client ID" | `client_id` in `lti_config.json` doesn't match, or the key isn't ON |
| Canvas launch loops back | issuer key mismatch, or the launch isn't over HTTPS |
| Tool loads blank inside Canvas | `X-Frame-Options: SAMEORIGIN` still set — switch to CSP `frame-ancestors` |
| Uploads fail at ~15 MB | `BZ_MAX_UPLOAD_BYTES` (app) and `client_max_body_size` (nginx) |
| `database is locked` | two service instances on one DB; check for a stray uvicorn |

## Health checks worth monitoring

- `GET /api/health` → `{"status":"ok","database":"ok"}` — app + DB
- `GET /lti/health` → `{"status":"ok","jwk_count":1}` — Canvas readiness

Both are unauthenticated and cheap. `/api/health` is excluded from the
nginx access log so polling it doesn't bury real traffic.
