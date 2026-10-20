# Konfigurasi VPS (referensi)

Salinan file yang hidup di server, supaya bisa dipasang ulang. CI **tidak**
menyentuh file-file ini; hanya `deploy/activate.sh` yang dijalankan tiap deploy.

| File di sini | Lokasi di server |
| --- | --- |
| `duitakuh-post-deploy` | `/usr/local/sbin/duitakuh-post-deploy` (root, 755) |
| `duitakuh-deploy.service`, `duitakuh-deploy.path` | `/etc/systemd/system/` |
| `duitakuh-api.service`, `duitakuh-web.service` | `/etc/systemd/system/` |
| `nginx-lega.conf` | `/etc/nginx/sites-available/lega.rswicentral.my.id` |

Alur deploy: CI build -> scp tarball ke `~deploy/deploy/` -> `activate.sh`
(backup DB, taruh di `.deploy/incoming`, sentuh `.deploy/trigger`) ->
systemd menjalankan `duitakuh-post-deploy` (root) yang mengekstrak sebagai
`ubuntu`, `pip install`, `alembic upgrade head`, restart, health check, dan
auto-rollback bila gagal. Hasil ada di `.deploy/result` dan `.deploy/last.log`.

Layout: backend dari `/opt/duitakuh/backend` (venv `.venv`), frontend standalone
di `/opt/duitakuh/.deploy/web`, database Postgres 17 di Docker
(`backend/docker-compose.yml`, loopback `127.0.0.1:5433`).
