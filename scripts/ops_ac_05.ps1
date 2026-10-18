<#
OPS-AC-05 smoke checks against the AWS demonstration VM (final-spec component 15; docs/design/aws-deployment.md 3.6).
Run from an allowlisted machine:
  .\scripts\ops_ac_05.ps1 -AppHost arai-demo.duckdns.org -ApiHost arai-api.duckdns.org -AuthHost arai-auth.duckdns.org `
                          -BasicUser <shared login user> -BasicPassword <shared login password>
Writes reports\ops-ac-05\<date>\result.json. Three checks need a person and are listed as MANUAL in the result:
the request from a non-allowlisted address (run `curl -I https://<AppHost>/` from a phone hotspot: expect 403),
a Keycloak sign-in followed by a role refusal (403 on a reviewer action as a viewer) and the idle session expiry.
#>
param(
  [Parameter(Mandatory)] [string] $AppHost,
  [Parameter(Mandatory)] [string] $ApiHost,
  [Parameter(Mandatory)] [string] $AuthHost,
  [Parameter(Mandatory)] [string] $BasicUser,
  [Parameter(Mandatory)] [string] $BasicPassword
)
$ErrorActionPreference = "Stop"
$day = Get-Date -Format "yyyy-MM-dd"
$out = Join-Path $PSScriptRoot "..\reports\ops-ac-05\$day"
New-Item -ItemType Directory -Force $out | Out-Null
$checks = @()

function Head($url, $headers = @{}) {
  try { $r = Invoke-WebRequest -Uri $url -Method Get -MaximumRedirection 0 -Headers $headers -UseBasicParsing; return @{ status = [int]$r.StatusCode; headers = $r.Headers } }
  catch { $resp = $_.Exception.Response; if ($null -eq $resp) { throw }; return @{ status = [int]$resp.StatusCode; headers = @{ Location = $resp.Headers["Location"] } } }
}

# 1. HTTP redirects to HTTPS
$r = Head "http://$AppHost/"
$checks += @{ id = "https-redirect"; pass = ($r.status -eq 301 -and "$($r.headers.Location)".StartsWith("https://$AppHost")); observed = "$($r.status) $($r.headers.Location)" }

# 2. No shared login: 401 at the UI host and at the API host
foreach ($h in @($AppHost, $ApiHost)) {
  $r = Head "https://$h/api/v1/health"
  $checks += @{ id = "shared-login-401 $h"; pass = ($r.status -eq 401); observed = "$($r.status)" }
}

# 3. With the shared login but no ARAI session: health answers, a protected route is 401 from ARAI itself
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${BasicUser}:${BasicPassword}"))
$auth = @{ Authorization = "Basic $basic" }
$r = Head "https://$AppHost/api/v1/health" $auth
$checks += @{ id = "health-behind-shared-login"; pass = ($r.status -eq 200); observed = "$($r.status)" }
$r = Head "https://$AppHost/api/v1/me" $auth
$checks += @{ id = "no-session-401"; pass = ($r.status -eq 401); observed = "$($r.status)" }

# 4. Sign-in goes to Keycloak over https, and the realm publishes an https issuer
$r = Head "https://$AppHost/api/v1/auth/login" $auth
$checks += @{ id = "sso-redirect"; pass = ($r.status -eq 302 -and "$($r.headers.Location)".StartsWith("https://$AuthHost/realms/arai/")); observed = "$($r.status) $($r.headers.Location)" }
$disc = Invoke-RestMethod "https://$AuthHost/realms/arai/.well-known/openid-configuration"
$checks += @{ id = "issuer-https"; pass = ($disc.issuer -eq "https://$AuthHost/realms/arai"); observed = $disc.issuer }

# 5. The database port is not public
$ip = [System.Net.Dns]::GetHostAddresses($AppHost)[0].IPAddressToString
$tcp = Test-NetConnection -ComputerName $ip -Port 5432 -WarningAction SilentlyContinue
$checks += @{ id = "db-port-closed"; pass = (-not $tcp.TcpTestSucceeded); observed = "tcp 5432 open=$($tcp.TcpTestSucceeded) at $ip" }

# 6. The Vercel upstream has no UI
$r = Head "https://$ApiHost/"
$checks += @{ id = "api-host-no-ui"; pass = ($r.status -eq 404); observed = "$($r.status)" }

$manual = @(
  @{ id = "ip-block"; pass = $null; observed = "MANUAL: from a non-allowlisted address, curl -I https://$AppHost/ must answer 403; paste the output into $out\ip-block.txt" },
  @{ id = "sso-sign-in-and-role-refusal"; pass = $null; observed = "MANUAL: sign in as a viewer, open a case, attempt a review: 403; screenshot to $out" },
  @{ id = "session-expiry"; pass = $null; observed = "MANUAL: leave the UI idle past SESSION_IDLE_MINUTES (60); the next request signs out; screenshot to $out" }
)
$result = @{ executed_at = (Get-Date -Format "o"); app_host = $AppHost; api_host = $ApiHost; auth_host = $AuthHost; checks = $checks + $manual }
$result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $out "result.json") -Encoding utf8
$checks | ForEach-Object { "{0,-34} {1,-5} {2}" -f $_.id, ($(if ($_.pass) { "PASS" } else { "FAIL" })), $_.observed }
$manual | ForEach-Object { "{0,-34} {1,-5} {2}" -f $_.id, "TODO", $_.observed }
"written $out\result.json"
