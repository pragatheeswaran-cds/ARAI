<#
OPS-AC-05 smoke checks against the AWS demonstration VM (final-spec component 15; docs/design/aws-deployment.md 3.6).
Run from any machine (the UI is public since D-044 was amended, AM-73; the development login replaces Keycloak, AM-74):
  .\scripts\ops_ac_05.ps1 -AppHost arai-demo.duckdns.org -BasicUser <shared login user> -BasicPassword <shared login password>
Writes reports\ops-ac-05\<date>\result.json. Two checks need a person and are listed as MANUAL in the result:
a sign-in as the viewer persona followed by a role refusal (403 on a review) and the idle session expiry.
#>
param(
  [Parameter(Mandatory)] [string] $AppHost,
  [Parameter(Mandatory)] [string] $BasicUser,
  [Parameter(Mandatory)] [string] $BasicPassword
)
$ErrorActionPreference = "Stop"
$day = Get-Date -Format "yyyy-MM-dd"
$out = Join-Path $PSScriptRoot "..\reports\ops-ac-05\$day"
New-Item -ItemType Directory -Force $out | Out-Null
$checks = @()

function Head($url, $headers = @{}) {
  try { $r = Invoke-WebRequest -Uri $url -Method Get -MaximumRedirection 0 -Headers $headers -UseBasicParsing; return @{ status = [int]$r.StatusCode; headers = $r.Headers; body = $r.Content } }
  catch { $resp = $_.Exception.Response; if ($null -eq $resp) { throw }; return @{ status = [int]$resp.StatusCode; headers = @{ Location = $resp.Headers["Location"] }; body = "" } }
}

# 1. HTTP redirects to HTTPS
$r = Head "http://$AppHost/"
$checks += @{ id = "https-redirect"; pass = ($r.status -eq 301 -and "$($r.headers.Location)".StartsWith("https://$AppHost")); observed = "$($r.status) $($r.headers.Location)" }

# 2. No shared login: 401
$r = Head "https://$AppHost/api/v1/health"
$checks += @{ id = "shared-login-401"; pass = ($r.status -eq 401); observed = "$($r.status)" }

# 3. With the shared login but no ARAI session: health answers, a protected route is 401 from ARAI itself
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${BasicUser}:${BasicPassword}"))
$auth = @{ Authorization = "Basic $basic" }
$r = Head "https://$AppHost/api/v1/health" $auth
$checks += @{ id = "health-behind-shared-login"; pass = ($r.status -eq 200); observed = "$($r.status)" }
$r = Head "https://$AppHost/api/v1/me" $auth
$checks += @{ id = "no-session-401"; pass = ($r.status -eq 401); observed = "$($r.status)" }

# 4. The development login is on, with the personas and their roles (AM-74)
$r = Head "https://$AppHost/api/v1/auth/dev-users" $auth
$checks += @{ id = "dev-login-personas"; pass = ($r.status -eq 200 -and $r.body -match '"Admin"' -and $r.body -match '"viewer"'); observed = "$($r.status) $($r.body.Substring(0, [Math]::Min(80, $r.body.Length)))" }

# 5. The database port is not public
$ip = [System.Net.Dns]::GetHostAddresses($AppHost)[0].IPAddressToString
$tcp = Test-NetConnection -ComputerName $ip -Port 5432 -WarningAction SilentlyContinue
$checks += @{ id = "db-port-closed"; pass = (-not $tcp.TcpTestSucceeded); observed = "tcp 5432 open=$($tcp.TcpTestSucceeded) at $ip" }

# 6. Sign-in requests are rate limited (the 11th request within a minute answers 429)
$statuses = @(); 1..12 | ForEach-Object { $statuses += (Head "https://$AppHost/api/v1/auth/dev-users" $auth).status }
$checks += @{ id = "auth-rate-limit"; pass = ($statuses -contains 429); observed = ($statuses -join ",") }

$manual = @(
  @{ id = "viewer-role-refusal"; pass = $null; observed = "MANUAL: sign in as Priya (viewer), open a case, attempt a review: 403; screenshot to $out" },
  @{ id = "session-expiry"; pass = $null; observed = "MANUAL: leave the UI idle past SESSION_IDLE_MINUTES (60); the next request signs out; screenshot to $out" }
)
$result = @{ executed_at = (Get-Date -Format "o"); app_host = $AppHost; checks = $checks + $manual }
$result | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $out "result.json") -Encoding utf8
$checks | ForEach-Object { "{0,-34} {1,-5} {2}" -f $_.id, ($(if ($_.pass) { "PASS" } else { "FAIL" })), $_.observed }
$manual | ForEach-Object { "{0,-34} {1,-5} {2}" -f $_.id, "TODO", $_.observed }
"written $out\result.json"
