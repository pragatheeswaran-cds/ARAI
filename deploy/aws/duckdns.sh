#!/bin/bash
# Point the DuckDNS names at this instance's current public address (no Elastic IP by design, section 2.9).
# /etc/arai-duckdns.env holds DOMAINS (comma separated subdomains, without .duckdns.org) and TOKEN.
set -euo pipefail
. /etc/arai-duckdns.env
# an empty ip= makes DuckDNS use the caller's address, which is this instance's public IPv4
answer=$(curl -fsS "https://www.duckdns.org/update?domains=${DOMAINS}&token=${TOKEN}&ip=")
echo "$(date -Is) duckdns ${DOMAINS}: ${answer}"
[ "$answer" = "OK" ]
