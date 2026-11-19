param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$port = 18775
$url = "http://127.0.0.1:$port"
$dataRoot = Join-Path $appRoot 'data'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'

function Test-Workbench {
    try {
        $request = [System.Net.HttpWebRequest]::Create("$url/api/desktop-health")
        $request.Proxy = $null
        $request.Timeout = 2000
        $response = $request.GetResponse()
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try { return ($reader.ReadToEnd() | ConvertFrom-Json).app -eq 'amazon-listing-workbench' }
        finally { $reader.Dispose(); $response.Close() }
    } catch { return $false }
}

if (-not (Test-Workbench)) {
    $launcherIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($launcherIdentity -match '(^|\\)CodexSandbox[^\\]*$') {
        throw '检测到 CodexSandbox 隔离账号，已停止启动。请在本机终端或 FullAccess 环境运行工作台启动入口。'
    }
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "端口 $port 已被其他服务占用。"
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw '找不到工作台 Python 3.12 运行时。' }
    if (-not (Test-Path -LiteralPath (Join-Path $dataRoot 'accounts.sqlite3') -PathType Leaf)) {
        throw '找不到当前工作台账号库，已停止启动以免创建另一套数据。'
    }
    $env:JUNFEI_ACCOUNT_DATA = $dataRoot
    $env:JUNFEI_PROJECT_ROOT = Split-Path -Parent $appRoot
    $env:JUNFEI_PORT = "$port"
    $env:JUNFEI_OPEN_BROWSER = '0'
    Start-Process -FilePath $pythonPath -ArgumentList '-B','-X','utf8','desktop_launcher.py' `
        -WorkingDirectory $appRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $dataRoot 'current-server.stdout.log') `
        -RedirectStandardError (Join-Path $dataRoot 'current-server.stderr.log')
    for ($i=0; $i -lt 40 -and -not (Test-Workbench); $i++) { Start-Sleep -Milliseconds 250 }
    if (-not (Test-Workbench)) { throw '当前工作台启动超时，请检查 data/current-server.stderr.log。' }
}
if (-not $NoBrowser) { Start-Process $url }
Write-Output "Workbench ready: $url"
