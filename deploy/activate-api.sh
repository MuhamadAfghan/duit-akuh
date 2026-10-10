#!/usr/bin/env bash
#
# Activates a backend release. Runs ON the cPanel server, piped from the
# runner:
#   ssh host 'bash -s' -- <tarball> <app-dir> < deploy/activate-api.sh
#
# <app-dir> is the directory under $HOME that holds the deployment, and is
# named after the domain it serves (e.g. api-finance.rswicentral.my.id),
# which is also what the smoke test probes.
#
# Host notes (verified on heroic.jagoanhosting.id, re-check before changing):
#   - rsync is NOT installed      -> transfer is tar + scp
#   - no PostgreSQL on the server -> DATABASE_URL points at the local MariaDB
#   - Passenger's app root is FIXED at <base>/app. The CloudLinux selector
#     resolves symlinks when it writes .htaccess, so a `current -> releases/rX`
#     symlink would bake the release name into the config and into the
#     virtualenv path. Releases are therefore swapped by moving directories.
#   - Restart is `touch tmp/restart.txt`; the selector CLI is a fallback.
#   - Smoke tests go over loopback TLS with --resolve, because the public
#     edge answers non-browser clients with an Imunify360 interstitial that
#     is itself HTTP 200. Checking the status code alone would pass while
#     the app was down, so the body is matched too.
set -euo pipefail

INCOMING="${1:?butuh path tarball}"
APP_DIR="${2:?butuh nama folder app, mis. api-finance.rswicentral.my.id}"

BASE="$HOME/$APP_DIR"
APPROOT="$BASE/app"
VENV="$HOME/virtualenv/$APP_DIR/app/3.11"
SMOKE_HOST="$APP_DIR"
KEEP=3

log() { printf '\n==> %s\n' "$*"; }

restore() {
    log "ROLLBACK ke rilis sebelumnya"
    rm -rf "$APPROOT"
    mv "$BASE/app.old" "$APPROOT"
    mkdir -p "$APPROOT/tmp" && touch "$APPROOT/tmp/restart.txt"
}

[ -d "$VENV" ] || { echo "virtualenv hilang: $VENV" >&2; exit 1; }

log "Unpack $(basename "$INCOMING")"
rm -rf "$BASE/app.new"
mkdir -p "$BASE/app.new"
tar -xzf "$INCOMING" -C "$BASE/app.new"

log "Scaffolding Passenger + shared state"
mkdir -p "$BASE/app.new/public" "$BASE/app.new/tmp"
# .htaccess carries the Passenger block and is not part of the build.
cp -p "$BASE/shared/htaccess" "$BASE/app.new/public/.htaccess"
ln -sfn ../shared/.env "$BASE/app.new/.env"

log "Dependencies"
"$VENV/bin/pip" install --disable-pip-version-check --no-input -q \
    -r "$BASE/app.new/requirements-prod.txt"

log "Migrasi database"
(
    set -a
    # shellcheck disable=SC1091
    . "$BASE/shared/.env"
    set +a
    cd "$BASE/app.new"
    "$VENV/bin/alembic" upgrade head
)

log "Swap rilis"
rm -rf "$BASE/app.old"
mv "$APPROOT" "$BASE/app.old"
mv "$BASE/app.new" "$APPROOT"

log "Restart Passenger"
touch "$APPROOT/tmp/restart.txt"
cloudlinux-selector restart --json --interpreter python \
    --app-root "$APP_DIR/app" >/dev/null 2>&1 || true

log "Smoke test: https://$SMOKE_HOST/health"
BODY=""
for _ in 1 2 3 4 5 6; do
    BODY="$(curl -k -sS -m 45 --resolve "$SMOKE_HOST:443:127.0.0.1" \
        "https://$SMOKE_HOST/health" 2>/dev/null || true)"
    case "$BODY" in *'"status":"ok"'*) break ;; esac
    sleep 5
done
printf '%s\n' "${BODY:0:300}"

case "$BODY" in
    *'"status":"ok"'*) ;;
    *)
        restore
        echo "DEPLOY GAGAL: /health tidak mengembalikan status ok" >&2
        exit 1
        ;;
esac

log "Prune tarball lama (sisakan $KEEP)"
cd "$BASE/releases"
ls -1t ./*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
ls -1t ./*.tar.gz 2>/dev/null || true

log "SUKSES: backend aktif"
