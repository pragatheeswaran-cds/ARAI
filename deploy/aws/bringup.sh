#!/bin/bash
# Bring up (or re-run on) the ARAI demonstration VM. Idempotent; run as root through SSM Session Manager or Run Command:
#   sudo bash /opt/arai/bringup.sh
# Reads everything from Parameter Store under /arai (RUNBOOK 8.2 lists the parameters), fetches the release from the
# bucket, keeps DuckDNS current, renders nginx, obtains the certificate, writes .env and starts the Compose stack.
set -euo pipefail
exec > >(tee -a /var/log/arai-bringup.log) 2>&1
echo "== bringup $(date -Is)"

APP_DIR=/opt/arai/app
COMPOSE="docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml --profile sso"
TOKEN=$(curl -sS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
REGION=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="arai-${ACCOUNT}-${REGION}"
export AWS_DEFAULT_REGION="$REGION"

# 1. Parameters: /arai/config/<NAME> (plain) and /arai/secret/<NAME> (SecureString) become shell variables NAME.
while IFS=$'\t' read -r name value; do
  declare -g "${name##*/}=$value"
done < <(aws ssm get-parameters-by-path --path /arai --recursive --with-decryption \
          --query "Parameters[].[Name,Value]" --output text)
for required in APP_HOST API_HOST AUTH_HOST VERCEL_HOST LE_EMAIL DUCKDNS_DOMAINS POSTGRES_PASSWORD BASIC_AUTH_USER \
                BASIC_AUTH_PASSWORD OIDC_CLIENT_SECRET KEYCLOAK_ADMIN_PASSWORD DUCKDNS_TOKEN BOOTSTRAP_ADMINS; do
  [ -n "${!required:-}" ] || { echo "missing parameter /arai/.../$required"; exit 2; }
done
ALLOWLIST="${ALLOWLIST:-}"; ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"; USERS="${USERS:-}"

# 2. The release: a git archive of the repository, uploaded by RUNBOOK 8.3.
mkdir -p /opt/arai /var/www/certbot
aws s3 cp "s3://${BUCKET}/release/arai.tar.gz" /opt/arai/arai.tar.gz
rm -rf "${APP_DIR}.new" && mkdir -p "${APP_DIR}.new"
tar -xzf /opt/arai/arai.tar.gz -C "${APP_DIR}.new"
rm -rf "${APP_DIR}.old"; [ -d "$APP_DIR" ] && mv "$APP_DIR" "${APP_DIR}.old"; mv "${APP_DIR}.new" "$APP_DIR"
install -m 755 "$APP_DIR/deploy/aws/duckdns.sh" /opt/arai/duckdns.sh
install -m 755 "$APP_DIR/deploy/aws/backup.sh" /opt/arai/backup.sh
install -m 755 "$APP_DIR/deploy/aws/keycloak-setup.sh" /opt/arai/keycloak-setup.sh
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

# 4. The allowlist for the UI hostname (D-044): one "allow <address>;" per entry; an empty list denies everyone.
: > /opt/arai/allowlist.conf
IFS=',' read -ra entries <<< "$ALLOWLIST"
for ip in "${entries[@]}"; do ip=$(echo "$ip" | tr -d ' '); [ -n "$ip" ] && echo "allow $ip;" >> /opt/arai/allowlist.conf; done
[ -s /opt/arai/allowlist.conf ] || echo "WARNING: /arai/config/ALLOWLIST is empty; the UI hostname answers 403 to everyone"

# 5. nginx
sed -e "s/__APP_HOST__/$APP_HOST/g" -e "s/__API_HOST__/$API_HOST/g" -e "s/__AUTH_HOST__/$AUTH_HOST/g" \
    "$APP_DIR/deploy/aws/nginx.vm.conf.template" > /opt/arai/nginx.conf

# 6. One certificate for the three names. First issue stands alone on port 80; renewals use the webroot nginx serves.
if [ ! -f "/etc/letsencrypt/live/${APP_HOST}/fullchain.pem" ]; then
  echo "waiting for DNS: ${APP_HOST} -> this instance"
  MYIP=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
  for i in $(seq 1 36); do [ "$(dig +short "$APP_HOST" @1.1.1.1 | tail -1)" = "$MYIP" ] && break; sleep 5; done
  (cd "$APP_DIR" && $COMPOSE stop web 2>/dev/null || true)
  certbot certonly --standalone --non-interactive --agree-tos --no-eff-email -m "$LE_EMAIL" \
          -d "$APP_HOST" -d "$API_HOST" -d "$AUTH_HOST"
fi
cat > /etc/cron.d/arai-certbot <<EOF
17 3 * * * root certbot renew --quiet --webroot -w /var/www/certbot --deploy-hook "cd $APP_DIR && $COMPOSE exec -T web nginx -s reload"
EOF

# 7. .env for Compose (RUNBOOK 3 and .env.example): the vm profile, single sign-on, the secrets.
umask 077
cat > /opt/arai/.env <<EOF
# written by bringup.sh $(date -Is); edit Parameter Store, not this file
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
APP_PROFILE=vm
ARAI_ARTIFACTS=/data/artifacts
UI_ORIGINS=https://${APP_HOST}
BASIC_AUTH_USER=${BASIC_AUTH_USER}
BASIC_AUTH_PASSWORD=${BASIC_AUTH_PASSWORD}
AUTH_MODE=oidc
OIDC_ISSUER=https://${AUTH_HOST}/realms/arai
OIDC_CLIENT_ID=arai
OIDC_CLIENT_SECRET=${OIDC_CLIENT_SECRET}
OIDC_REDIRECT_URI=https://${APP_HOST}/api/v1/auth/callback
AUTH_ROLE_MAP=arai-viewers=viewer,arai-reviewers=reviewer,arai-approvers=approver,arai-admins=admin
ARAI_BOOTSTRAP_ADMINS=${BOOTSTRAP_ADMINS}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
KEYCLOAK_ADMIN_USER=kcadmin
KEYCLOAK_ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD}
APP_HOST=${APP_HOST}
API_HOST=${API_HOST}
AUTH_HOST=${AUTH_HOST}
VERCEL_HOST=${VERCEL_HOST}
EOF
umask 022
cp /opt/arai/.env "$APP_DIR/.env"

# 8. The stack
cd "$APP_DIR"
$COMPOSE up -d --build --remove-orphans
for i in $(seq 1 60); do
  curl -fsS -o /dev/null --resolve "${API_HOST}:443:127.0.0.1" -u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD}" \
       "https://${API_HOST}/api/v1/health" && break
  sleep 5
done
curl -sS --resolve "${API_HOST}:443:127.0.0.1" -u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD}" "https://${API_HOST}/api/v1/health"; echo

# 9. Keycloak: the real client secret and callbacks, the real people, no development users.
APP_DIR="$APP_DIR" APP_HOST="$APP_HOST" VERCEL_HOST="$VERCEL_HOST" OIDC_CLIENT_SECRET="$OIDC_CLIENT_SECRET" \
KEYCLOAK_ADMIN_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" USERS="$USERS" /opt/arai/keycloak-setup.sh

# 10. Nightly backup of the databases and the artifact root to the bucket.
echo "30 2 * * * root BUCKET=$BUCKET APP_DIR=$APP_DIR /opt/arai/backup.sh >> /var/log/arai-backup.log 2>&1" > /etc/cron.d/arai-backup
echo "== bringup done $(date -Is)"
