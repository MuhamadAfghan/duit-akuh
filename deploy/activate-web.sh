#!/usr/bin/env bash
#
# Activates a frontend release. Runs ON the cPanel server, piped from the
# runner:
#   ssh host 'bash -s' -- <tarball> [smoke-host] < deploy/activate-web.sh
#
# The tarball is a Next.js `output: 'standalone'` bundle: server.js, a
# pruned node_modules, .next/ and public/. Nothing is installed or built
# here — the host has no build toolchain and Node caps at 20.20.2.
#
# See deploy/activate-api.sh for the host quirks that shape this script
# (no rsync, fixed Passenger app root, WAF-aware smoke test).
set -euo pipefail

BASE=/home/rswicent/finance.agann.my.id
APPROOT="$BASE/app"
INCOMING="${1:?butuh path tarball}"
SMOKE_HOST="${2:-finance.rswicentral.my.id}"
KEEP=3

log() { printf '\n==> %s\n' "$*"; }

smoke() {
    curl -k -sS -m 45 --resolve "$SMOKE_HOST:443:127.0.0.1" \
        "https://$SMOKE_HOST/" 2>/dev/null || true
}

restore() {
    log "ROLLBACK ke rilis sebelumnya"
    rm -rf "$APPROOT"
    mv "$BASE/app.old" "$APPROOT"
    mkdir -p "$APPROOT/tmp" && touch "$APPROOT/tmp/restart.txt"
}

log "Unpack $(basename "$INCOMING")"
rm -rf "$BASE/app.new"
mkdir -p "$BASE/app.new"
tar -xzf "$INCOMING" -C "$BASE/app.new"

[ -f "$BASE/app.new/server.js" ] || {
    echo "tarball tidak berisi server.js — bukan bundle standalone" >&2
    exit 1
}

log "Scaffolding Passenger"
mkdir -p "$BASE/app.new/public" "$BASE/app.new/tmp"
# Next's own public/ ships here too; the Passenger block has to be added
# because .htaccess is not part of the build.
cp -p "$BASE/shared/htaccess" "$BASE/app.new/public/.htaccess"
# An index.html in the docroot would shadow the app: Passenger serves
# static files from public/ before handing the request to Node.
rm -f "$BASE/app.new/public/index.html"

log "Swap rilis"
rm -rf "$BASE/app.old"
mv "$APPROOT" "$BASE/app.old"
mv "$BASE/app.new" "$APPROOT"

log "Restart Passenger"
touch "$APPROOT/tmp/restart.txt"
cloudlinux-selector restart --json --interpreter nodejs \
    --app-root finance.agann.my.id/app >/dev/null 2>&1 || true

log "Smoke test: https://$SMOKE_HOST/"
BODY=""
for attempt in 1 2 3 4 5 6 7 8; do
    BODY="$(smoke)"
    case "$BODY" in
        *'/_next/'*) break ;;
    esac
    sleep 5
done
printf 'panjang body: %s bytes\n' "${#BODY}"

case "$BODY" in
    *'/_next/'*) ;;
    *)
        restore
        echo "DEPLOY GAGAL: halaman tidak memuat asset /_next/ (app tidak jalan)" >&2
        exit 1
        ;;
esac

log "Prune tarball lama (sisakan $KEEP)"
cd "$BASE/releases"
ls -1t ./*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
ls -1t ./*.tar.gz 2>/dev/null || true

log "SUKSES: frontend aktif"
