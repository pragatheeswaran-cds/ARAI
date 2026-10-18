#!/bin/bash
# Turn the imported development realm (deploy/keycloak/arai-realm.json) into the demonstration realm. Idempotent.
# Called by bringup.sh with APP_DIR, APP_HOST, VERCEL_HOST, OIDC_CLIENT_SECRET, KEYCLOAK_ADMIN_PASSWORD and USERS set.
# USERS: records separated by "|", fields by ",": username,email,First name,Last name,group[;group]
#   e.g. "asha,asha@example.org,Asha,Rao,arai-reviewers;arai-approvers|admin,you@example.org,Your,Name,arai-admins"
# New people get a temporary password, written once to /opt/arai/users-initial-passwords.txt (root only); Keycloak asks
# them to change it at first sign-in.
set -euo pipefail
cd "$APP_DIR"
KC="docker compose -f docker-compose.yml -f deploy/aws/compose.vm.yml --profile sso exec -T keycloak /opt/keycloak/bin/kcadm.sh"

for i in $(seq 1 60); do
  $KC config credentials --server http://localhost:8081 --realm master --user kcadmin --password "$KEYCLOAK_ADMIN_PASSWORD" 2>/dev/null && break
  sleep 5
done

# The client: real secret, the two callbacks (one per API process), the two browser origins.
CID=$($KC get clients -r arai -q clientId=arai --fields id --format csv --noquotes | tail -1)
$KC update "clients/$CID" -r arai \
  -s "secret=$OIDC_CLIENT_SECRET" \
  -s "rootUrl=https://$APP_HOST" -s "baseUrl=https://$APP_HOST" \
  -s "redirectUris=[\"https://$APP_HOST/api/v1/auth/callback\",\"https://$VERCEL_HOST/api/v1/auth/callback\"]" \
  -s "webOrigins=[\"https://$APP_HOST\",\"https://$VERCEL_HOST\"]"
$KC update realms/arai -s sslRequired=external -s bruteForceProtected=true

# The development users leave.
for u in asha ravi meera arjun priya admin; do
  id=$($KC get users -r arai -q username="$u" -q exact=true --fields id,username --format csv --noquotes | awk -F, -v u="$u" '$2==u{print $1}')
  if [ -n "$id" ] && ! echo "|$USERS|" | grep -q "|$u,"; then $KC delete "users/$id" -r arai; echo "removed development user $u"; fi
done

# The real people.
[ -n "${USERS:-}" ] || { echo "no USERS parameter: realm has no people yet"; exit 0; }
touch /opt/arai/users-initial-passwords.txt; chmod 600 /opt/arai/users-initial-passwords.txt
IFS='|' read -ra records <<< "$USERS"
for rec in "${records[@]}"; do
  IFS=',' read -r username email first last groups <<< "$rec"
  [ -n "$username" ] || continue
  id=$($KC get users -r arai -q username="$username" -q exact=true --fields id,username --format csv --noquotes | awk -F, -v u="$username" '$2==u{print $1}')
  if [ -z "$id" ]; then
    $KC create users -r arai -s username="$username" -s email="$email" -s firstName="$first" -s lastName="$last" \
        -s enabled=true -s emailVerified=true
    id=$($KC get users -r arai -q username="$username" -q exact=true --fields id,username --format csv --noquotes | awk -F, -v u="$username" '$2==u{print $1}')
    pw="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 14)"
    $KC set-password -r arai --username "$username" --new-password "$pw" --temporary
    echo "$(date -Is) $username $email temporary-password $pw" >> /opt/arai/users-initial-passwords.txt
    echo "created $username"
  fi
  IFS=';' read -ra wanted <<< "$groups"
  for g in "${wanted[@]}"; do
    gid=$($KC get groups -r arai -q search="$g" --fields id,name --format csv --noquotes | awk -F, -v g="$g" '$2==g{print $1}')
    [ -n "$gid" ] || { echo "unknown group $g for $username"; continue; }
    $KC update "users/$id/groups/$gid" -r arai -s realm=arai -s userId="$id" -s groupId="$gid" -n
  done
done
echo "keycloak realm arai: $($KC get users -r arai --fields username --format csv --noquotes | tr '\n' ' ')"
