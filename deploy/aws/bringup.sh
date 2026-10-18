#!/bin/bash
# Bring up (or re-run on) the ARAI demonstration VM. Idempotent; run as root through SSM Session Manager or Run Command:
#   sudo bash /opt/arai/bringup.sh
# Reads everything from Parameter Store under /arai (RUNBOOK 8.2 lists the parameters), fetches the release from the
# bucket, keeps DuckDNS current, renders nginx, obtains the certificate, writes .env and starts the Compose stack.
set -euo pipefail
exec > >(tee -a /var/log/arai-bringup.log) 2>&1
echo "== bringup $(date -Is)"

APP_DIR=/opt/arai/app
COMPOSE="docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml"
TOKEN=$(curl -sS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
REGION=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="arai-${ACCOUNT}-${REGION}"
export AWS_DEFAULT_REGION="$REGION"

# 1. Parameters: /arai/config/<NAME> (plain) and /arai/secret/<NAME> (SecureString) become shell variables NAME.
while IFS=$'\t' read -r name value; do
  [ "$value" = "-" ] && value=""                      # Parameter Store refuses empty values; "-" means empty
  declare -g "${name##*/}=$value"
done < <(aws ssm get-parameters-by-path --path /arai --recursive --with-decryption \
          --query "Parameters[].[Name,Value]" --output text)
for required in APP_HOST LE_EMAIL DUCKDNS_DOMAINS POSTGRES_PASSWORD BASIC_AUTH_USER BASIC_AUTH_PASSWORD DUCKDNS_TOKEN; do
  [ -n "${!required:-}" ] || { echo "missing parameter /arai/.../$required"; exit 2; }
done
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"; AUTH_DEV_USERS="${AUTH_DEV_USERS:-}"

# 2. The release: a git archive of the repository, uploaded by RUNBOOK 8.3.
mkdir -p /opt/arai /var/www/certbot
aws s3 cp "s3://${BUCKET}/release/arai.tar.gz" /opt/arai/arai.tar.gz
rm -rf "${APP_DIR}.new" && mkdir -p "${APP_DIR}.new"
tar -xzf /opt/arai/arai.tar.gz -C "${APP_DIR}.new"
rm -rf "${APP_DIR}.old"; [ -d "$APP_DIR" ] && mv "$APP_DIR" "${APP_DIR}.old"; mv "${APP_DIR}.new" "$APP_DIR"
install -m 755 "$APP_DIR/deploy/aws/duckdns.sh" /opt/arai/duckdns.sh
install -m 755 "$APP_DIR/deploy/aws/backup.sh" /opt/arai/backup.sh
install -m 755 "$APP_DIR/deploy/aws/bringup.sh" /opt/arai/bringup.sh

# 3. DuckDNS: now, at every boot and every five minutes (the public address changes at each stop/start).
printf 'DOMAINS=%s\nTOKEN=%s\n' "$DUCKDNS_DOMAINS" "$DUCKDNS_TOKEN" > /etc/arai-duckdns.env; chmod 600 /etc/arai-duckdns.env
cat > /etc/systemd/system/arai-duckdns.service <<'EOF'
[Unit]
Description=ARAI: update DuckDNS with this instance's public address
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/opt/arai/duckdns.sh
EOF
cat > /etc/systemd/system/arai-duckdns.timer <<'EOF'
[Unit]
Description=ARAI: DuckDNS every five minutes
[Timer]
OnBootSec=30s
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload && systemctl enable --now arai-duckdns.timer && systemctl start arai-duckdns.service

# 4. (no IP allowlist since 18 Oct 2026: the UI is public, D-044 as amended in AM-73; see nginx.vm.conf.template)

# 5. nginx
sed -e "s/__APP_HOST__/$APP_HOST/g" \
    "$APP_DIR/deploy/aws/nginx.vm.conf.template" > /opt/arai/nginx.conf

# 6. The certificate. First issue stands alone on port 80; renewals use the webroot nginx serves.
if [ ! -f "/etc/letsencrypt/live/${APP_HOST}/fullchain.pem" ]; then
  echo "waiting for DNS: ${APP_HOST} -> this instance"
  MYIP=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
  for i in $(seq 1 36); do [ "$(dig +short "$APP_HOST" @1.1.1.1 | tail -1)" = "$MYIP" ] && break; sleep 5; done
  (cd "$APP_DIR" && $COMPOSE stop web 2>/dev/null || true)
  certbot certonly --standalone --non-interactive --agree-tos --no-eff-email -m "$LE_EMAIL" \
          -d "$APP_HOST"
fi
cat > /etc/cron.d/arai-certbot <<EOF
17 3 * * * root certbot renew --quiet --webroot -w /var/www/certbot --deploy-hook "cd $APP_DIR && $COMPOSE exec -T web nginx -s reload"
EOF

# 7. .env for Compose (RUNBOOK 3 and .env.example): the vm profile, the development login (AM-74), the secrets.
umask 077
cat > /opt/arai/.env <<EOF
# written by bringup.sh $(date -Is); edit Parameter Store, not this file
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
APP_PROFILE=vm
ARAI_ARTIFACTS=/data/artifacts
UI_ORIGINS=https://${APP_HOST}
BASIC_AUTH_USER=${BASIC_AUTH_USER}
BASIC_AUTH_PASSWORD=${BASIC_AUTH_PASSWORD}
AUTH_MODE=dev
AUTH_DEV_ON_VM=1
AUTH_DEV_USERS=${AUTH_DEV_USERS}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
APP_HOST=${APP_HOST}
EOF
umask 022
cp /opt/arai/.env "$APP_DIR/.env"

# 8. The stack
cd "$APP_DIR"
$COMPOSE up -d --build --remove-orphans
for i in $(seq 1 60); do
  curl -fsS -o /dev/null --resolve "${APP_HOST}:443:127.0.0.1" -u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD}" \
       "https://${APP_HOST}/api/v1/health" && break
  sleep 5
done
curl -sS --resolve "${APP_HOST}:443:127.0.0.1" -u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD}" "https://${APP_HOST}/api/v1/health"; echo

# 9. Nightly backup of the database and the artifact root to the bucket.
echo "30 2 * * * root BUCKET=$BUCKET APP_DIR=$APP_DIR /opt/arai/backup.sh >> /var/log/arai-backup.log 2>&1" > /etc/cron.d/arai-backup
echo "== bringup done $(date -Is)"
