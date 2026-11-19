# Employee action: trust ONLY the supplied office CA for this workbench.
$ErrorActionPreference='Stop'
$certificate=Join-Path $PSScriptRoot 'data\junfei-office-ca.cer'
if (-not (Test-Path -LiteralPath $certificate)) { throw 'Office certificate not found.' }
Import-Certificate -FilePath $certificate -CertStoreLocation 'Cert:\CurrentUser\Root' | Select-Object Subject,Thumbprint
