#!/bin/bash
# Run after extracting the deployment archive into /opt/junfei/workbench.
set -euo pipefail
APP=/opt/junfei/workbench
id junfei >/dev/null 2>&1 || useradd --system --home /opt/junfei --shell /usr/sbin/nologin junfei
install -d -m 750 -o root -g junfei /etc/junfei
python3 -m venv /opt/junfei/venv
/opt/junfei/venv/bin/pip install -r "$APP/cloud_requirements.txt"
if [ ! -f /etc/junfei/master.key ]; then
  /opt/junfei/venv/bin/python -c "from cryptography.fernet import Fernet; from pathlib import Path; Path('/etc/junfei/master.key').write_bytes(Fernet.generate_key())"
fi
chown root:junfei /etc/junfei/master.key
chmod 640 /etc/junfei/master.key
printf '%s\n' 'JUNFEI_MASTER_KEY_FILE=/etc/junfei/master.key' 'JUNFEI_TRUST_PROXY=1' 'PYTHONUNBUFFERED=1' > /etc/junfei/server.env
chmod 640 /etc/junfei/server.env
chown root:junfei /etc/junfei/server.env
chown -R root:root "$APP"
chown -R junfei:junfei "$APP/data"
chmod 700 "$APP/data"
cat > /etc/systemd/system/junfei.service <<'UNIT'
[Unit]
Description=Junfei Listing Workbench
After=network-online.target
Wants=network-online.target
[Service]
User=junfei
Group=junfei
WorkingDirectory=/opt/junfei/workbench
EnvironmentFile=/etc/junfei/server.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/junfei/venv/bin/python server.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/junfei/workbench/data
[Install]
WantedBy=multi-user.target
UNIT
install -d -m 755 /var/www/html/.well-known/acme-challenge
cat > /etc/nginx/sites-available/junfei <<'NGINX'
server {
    listen 80 default_server;
    server_name 101.32.128.180;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 503; }
}
NGINX
ln -sfn /etc/nginx/sites-available/junfei /etc/nginx/sites-enabled/junfei
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --now junfei
systemctl reload nginx
echo APP_INSTALLED
