#!/usr/bin/env bash
#
# Dijalankan DI VPS (user `deploy`), di-pipe dari runner CI:
#   ssh deploy@vps 'bash -s' -- <api.tar.gz> <web.tar.gz> < deploy/activate.sh
#
# Script ini sengaja tipis: ia hanya mem-backup DB, menaruh tarball di
# .deploy/incoming lalu "menyentuh" .deploy/trigger. Pekerjaan sebenarnya
# (ekstrak, pip, migrasi, restart, health check, auto-rollback) dilakukan
# oleh /usr/local/sbin/duitakuh-post-deploy yang dipicu systemd
# (duitakuh-deploy.path) dan berjalan sebagai root dengan isi tetap, jadi
# user `deploy` tidak perlu sudo. Lihat deploy/server/.
set -euo pipefail

API_TGZ="${1:?butuh path api tarball}"
WEB_TGZ="${2:?butuh path web tarball}"
DEP=/opt/duitakuh/.deploy
KEEP_BACKUPS=7

log() { printf '\n==> %s\n' "$*"; }

log "Backup database (pg_dump)"
mkdir -p "$DEP/backups"
f="$DEP/backups/db-$(date +%Y%m%d-%H%M%S).sql.gz"
docker exec duit-akuh-db pg_dump -U duitakuh duitakuh | gzip > "$f.tmp"
mv "$f.tmp" "$f"
ls -1t "$DEP"/backups/db-*.sql.gz | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
ls -lh "$f" | awk '{print $5, $9}'

log "Taruh artifact di incoming"
mv -f "$API_TGZ" "$DEP/incoming/api.tgz"
mv -f "$WEB_TGZ" "$DEP/incoming/web.tgz"

log "Picu post-deploy"
rm -f "$DEP/result"
date +%s > "$DEP/trigger"

for _ in $(seq 1 90); do
    [ -f "$DEP/result" ] && break
    sleep 2
done

echo; echo "---- log post-deploy ----"
cat "$DEP/last.log" 2>/dev/null || true
echo "-------------------------"

result="$(cut -d' ' -f1 "$DEP/result" 2>/dev/null || echo timeout)"
echo "HASIL: $result"
[ "$result" = ok ]
