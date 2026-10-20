#!/usr/bin/env bash
#
# Rollback manual ke rilis sebelum deploy terakhir:
#   ssh deploy@vps 'bash -s' < deploy/rollback.sh
#
# Memulihkan backend (.deploy/snap/api-prev.tgz) dan frontend
# (.deploy/web.prev) lalu restart. CATATAN: migrasi database TIDAK ikut
# dibalik; DB bisa dipulihkan dari .deploy/backups/db-*.sql.gz.
set -euo pipefail

DEP=/opt/duitakuh/.deploy
rm -f "$DEP/result"
echo rollback > "$DEP/trigger"

for _ in $(seq 1 60); do
    [ -f "$DEP/result" ] && break
    sleep 2
done
cat "$DEP/last.log" 2>/dev/null || true
result="$(cut -d' ' -f1 "$DEP/result" 2>/dev/null || echo timeout)"
echo "HASIL: $result"
[ "$result" = ok-rollback ]
