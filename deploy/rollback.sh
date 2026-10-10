#!/usr/bin/env bash
#
# Rollback manual ke rilis sebelumnya:
#   ssh duitakuh 'bash -s' -- web < deploy/rollback.sh
#   ssh duitakuh 'bash -s' -- api < deploy/rollback.sh
#
# Atau ke tarball tertentu:
#   ssh duitakuh 'bash -s' -- api api-<sha>.tar.gz < deploy/rollback.sh
#
# `app.old` adalah rilis yang digantikan oleh deploy terakhir, jadi tanpa
# argumen kedua ini menukar keduanya kembali — instan, tanpa unpack.
#
# CATATAN: migrasi database TIDAK ikut dibalik. Alembic downgrade harus
# dijalankan sendiri, dan untuk ledger biasanya justru tidak diinginkan.
set -euo pipefail

WHICH="${1:?pilih: web | api}"
TARBALL="${2:-}"

case "$WHICH" in
    web)
        BASE=/home/rswicent/finance.agann.my.id
        HOST=finance.rswicentral.my.id
        INTERP=nodejs
        APPREL=finance.agann.my.id/app
        MARKER='/_next/'
        PROBE='/'
        ;;
    api)
        BASE=/home/rswicent/api-finance.agann.my.id
        HOST=api-finance.rswicentral.my.id
        INTERP=python
        APPREL=api-finance.agann.my.id/app
        MARKER='"status":"ok"'
        PROBE='/health'
        ;;
    *) echo "argumen harus 'web' atau 'api'" >&2; exit 1 ;;
esac

APPROOT="$BASE/app"
log() { printf '\n==> %s\n' "$*"; }

if [ -n "$TARBALL" ]; then
    SRC="$BASE/releases/$TARBALL"
    [ -f "$SRC" ] || { echo "tarball tidak ada: $SRC" >&2; ls -1t "$BASE/releases" >&2; exit 1; }
    log "Unpack $TARBALL"
    rm -rf "$BASE/app.new"
    mkdir -p "$BASE/app.new"
    tar -xzf "$SRC" -C "$BASE/app.new"
    mkdir -p "$BASE/app.new/public" "$BASE/app.new/tmp"
    cp -p "$BASE/shared/htaccess" "$BASE/app.new/public/.htaccess"
    [ "$WHICH" = api ] && ln -sfn ../shared/.env "$BASE/app.new/.env"
    [ "$WHICH" = web ] && rm -f "$BASE/app.new/public/index.html"
    rm -rf "$BASE/app.old"
    mv "$APPROOT" "$BASE/app.old"
    mv "$BASE/app.new" "$APPROOT"
else
    [ -d "$BASE/app.old" ] || {
        echo "tidak ada app.old untuk dibalik. Pilih tarball:" >&2
        ls -1t "$BASE/releases" >&2
        exit 1
    }
    log "Tukar app <-> app.old"
    mv "$APPROOT" "$BASE/app.tmp"
    mv "$BASE/app.old" "$APPROOT"
    mv "$BASE/app.tmp" "$BASE/app.old"
fi

log "Restart Passenger"
mkdir -p "$APPROOT/tmp"
touch "$APPROOT/tmp/restart.txt"
cloudlinux-selector restart --json --interpreter "$INTERP" --app-root "$APPREL" >/dev/null 2>&1 || true

log "Health: https://$HOST$PROBE"
for _ in 1 2 3 4 5 6; do
    BODY="$(curl -k -sS -m 45 --resolve "$HOST:443:127.0.0.1" "https://$HOST$PROBE" 2>/dev/null || true)"
    case "$BODY" in *"$MARKER"*) echo "OK"; exit 0 ;; esac
    sleep 5
done

echo "ROLLBACK SELESAI TAPI HEALTH GAGAL — periksa manual" >&2
exit 1
