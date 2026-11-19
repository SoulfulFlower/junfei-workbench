#!/bin/bash
set -euo pipefail
test -f /etc/letsencrypt/live/junfei-ip/fullchain.pem
cat > /etc/nginx/sites-available/junfei <<'NGINX'
server {
    listen 80 default_server;
    server_name 101.32.128.180;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://101.32.128.180$request_uri; }
}
server {
    listen 443 ssl default_server;
    server_name 101.32.128.180;
    ssl_certificate /etc/letsencrypt/live/junfei-ip/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/junfei-ip/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    client_max_body_size 16m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    location / {
        proxy_pass http://127.0.0.1:18765;
        proxy_http_version 1.1;
        proxy_set_header Host 101.32.128.180;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
        proxy_buffering off;
    }
}
NGINX
nginx -t
systemctl reload nginx
install -d /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/nginx
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/nginx
cat > /etc/systemd/system/junfei-certificate.service <<'UNIT'
[Unit]
Description=Renew Junfei IP certificate
[Service]
Type=oneshot
ExecStart=/home/ubuntu/certbot-venv/bin/certbot renew --quiet
UNIT
cat > /etc/systemd/system/junfei-certificate.timer <<'UNIT'
[Unit]
Description=Check short-lived IP certificate twice daily
[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=1800
Persistent=true
[Install]
WantedBy=timers.target
UNIT
cat > /etc/systemd/system/junfei-backup.service <<'UNIT'
[Unit]
Description=Backup Junfei data and encryption key
[Service]
Type=oneshot
UMask=0077
ExecStart=/opt/junfei/venv/bin/python /opt/junfei/workbench/cloud/backup.py
UNIT
cat > /etc/systemd/system/junfei-backup.timer <<'UNIT'
[Unit]
Description=Daily Junfei backup
[Timer]
OnCalendar=*-*-* 19:30:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now junfei-certificate.timer junfei-backup.timer
systemctl start junfei-backup.service
echo HTTPS_ENABLED
