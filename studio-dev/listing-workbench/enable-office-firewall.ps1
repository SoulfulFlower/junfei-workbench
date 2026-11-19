# Run as administrator once. Only permits the local office subnet on this address/port.
$ErrorActionPreference='Stop'
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'data\deployment.json') -Raw | ConvertFrom-Json
$ruleName='JunfeiListingOfficeHTTPS'
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName 'Junfei Listing Office HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $config.address -LocalPort $config.port -RemoteAddress LocalSubnet -Profile Any | Out-Null
}
Write-Host ('Office HTTPS enabled: ' + $config.url)
