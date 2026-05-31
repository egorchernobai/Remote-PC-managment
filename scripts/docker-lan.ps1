param(
    [int]$Port = 8443,
    [switch]$Build,
    [switch]$RenewCert
)

$ErrorActionPreference = "Stop"

$preferredIp = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -like "192.168.1.*" -and
        $_.PrefixOrigin -ne "WellKnown" -and
        $_.SuffixOrigin -ne "WellKnown"
    } |
    Select-Object -First 1 -ExpandProperty IPAddress

if (-not $preferredIp) {
    $preferredIp = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            ($_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -match "^172\.(1[6-9]|2[0-9]|3[0-1])\.") -and
            $_.PrefixOrigin -ne "WellKnown" -and
            $_.SuffixOrigin -ne "WellKnown"
        } |
        Select-Object -First 1 -ExpandProperty IPAddress
}

if (-not $preferredIp) {
    throw "No LAN IPv4 address found. Set SERVER_PUBLIC_HOSTS and AGENT_SERVER_HOST manually."
}

$env:PORT = "$Port"
$env:SERVER_PUBLIC_HOSTS = $preferredIp
$env:AGENT_SERVER_HOST = "${preferredIp}:${Port}"
if ($RenewCert) {
    $env:CERT_FORCE_RENEW = "true"
}

Write-Host "LAN address: https://${preferredIp}:${Port}"
Write-Host "SERVER_PUBLIC_HOSTS=$env:SERVER_PUBLIC_HOSTS"
Write-Host "AGENT_SERVER_HOST=$env:AGENT_SERVER_HOST"

if ($Build) {
    docker compose up --build
} else {
    docker compose up
}
