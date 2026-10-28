# =============================================================================
# BAA 私有部署一键脚本（Windows / WSL2 / Git Bash）
# 用法:
#   .\deploy\private\deploy.ps1 init
#   .\deploy\private\deploy.ps1 up
#   .\deploy\private\deploy.ps1 down
#   .\deploy\private\deploy.ps1 status
#   .\deploy\private\deploy.ps1 logs
#   .\deploy\private\deploy.ps1 reset
# =============================================================================
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet("init","up","down","status","logs","reset","help")]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$envFile = Join-Path $projectRoot ".env"
$envProdExample = Join-Path $projectRoot ".env.production.example"

Set-Location $projectRoot

# ── 工具函数 ──────────────────────────────────────────────

function ConvertFrom-SecureStringToHex {
    param($password)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($password)
    ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

function New-RandomKey {
    $bytes = New-Object byte[] 36
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::Create()
    $rng.GetBytes($bytes)
    $base64 = [Convert]::ToBase64String($bytes)
    return $base64 -replace '[+/=]', 'x'  # URL-safe base64
}

function Test-Prereqs {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: docker 未安装" -ForegroundColor Red
        exit 1
    }
    docker compose version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        docker-compose --version > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: docker compose 未安装" -ForegroundColor Red
            exit 1
        }
    }
}

function Ensure-Env {
    if (-not (Test-Path $envFile)) {
        Write-Host "❌ 未找到 .env 文件" -ForegroundColor Red
        Write-Host "   请先运行: .\deploy\private\deploy.ps1 init" -ForegroundColor Yellow
        exit 1
    }
}

# ── 命令实现 ──────────────────────────────────────────────

function Cmd-Init {
    Test-Prereqs
    if (Test-Path $envFile) {
        Write-Host "⚠️  .env 已存在，跳过初始化" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "🔧 生成 BAA 安全配置..." -ForegroundColor Cyan
    Copy-Item $envProdExample $envFile
    $secret = New-RandomKey
    (Get-Content $envFile) -replace 'CHANGE_ME_TO_STRONG_RANDOM', $secret | Set-Content $envFile
    Write-Host "✅ 已生成 $envFile" -ForegroundColor Green
    Write-Host ""
    Write-Host "📋 关键配置:" -ForegroundColor White
    Get-Content $envFile | Where-Object { $_ -match '^BAA_API_KEY=' -or $_ -match '^POSTGRES_PASSWORD=' } | ForEach-Object {
        $_ -replace '=.+$', '=***REDACTED***'
    }
    Write-Host ""
    Write-Host "🚀 启动: .\deploy\private\deploy.ps1 up" -ForegroundColor Green
}

function Cmd-Up {
    Test-Prereqs
    Ensure-Env
    Write-Host "🚀 启动 BAA 服务..." -ForegroundColor Cyan
    docker compose up -d --build
    Write-Host ""
    Write-Host "⏳ 等待服务就绪（最多 90s）..." -ForegroundColor Yellow
    for ($i = 1; $i -le 18; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                Write-Host "✅ BAA 已就绪！" -ForegroundColor Green
                Write-Host "   Health:   http://localhost:8000/health"
                Write-Host "   Metrics:  http://localhost:8000/metrics"
                Write-Host "   API:      http://localhost:8000/api/v1/functions"
                Write-Host ""
                Write-Host "📋 验证安全门禁（应返回 401）:"
                try {
                    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/functions" -UseBasicParsing -TimeoutSec 3
                    Write-Host "   Status: $($r.StatusCode)"
                } catch {
                    Write-Host "   响应: $($_.Exception.Response.StatusCode.value__)"
                }
                return
            }
        } catch { Start-Sleep -Seconds 5 }
    }
    Write-Host "⚠️  服务未就绪，查看日志排查:" -ForegroundColor Red
    docker compose logs --tail 50 baa
    exit 1
}

function Cmd-Down {
    Test-Prereqs
    docker compose down
    Write-Host "✅ 服务已停止" -ForegroundColor Green
}

function Cmd-Status {
    Test-Prereqs
    docker compose ps
    Write-Host ""
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3
        Write-Host "✅ /health 响应: $($r.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  /health 不可达（服务可能未启动）" -ForegroundColor Yellow
    }
}

function Cmd-Logs {
    Test-Prereqs
    docker compose logs -f @args
}

function Cmd-Reset {
    Write-Host "⚠️  警告：此操作将停止服务并删除所有数据卷！" -ForegroundColor Red
    $answer = Read-Host "确认删除？输入 yes"
    if ($answer -ne "yes") {
        Write-Host "❌ 已取消" -ForegroundColor Yellow
        return
    }
    Test-Prereqs
    docker compose down -v
    Write-Host "✅ 数据卷已删除，运行 .\deploy\private\deploy.ps1 init 重新开始" -ForegroundColor Green
}

# ── 入口 ──────────────────────────────────────────────────

switch ($Command) {
    "init"     { Cmd-Init }
    "up"       { Cmd-Up }
    "down"     { Cmd-Down }
    "status"   { Cmd-Status }
    "logs"     { Cmd-Logs }
    "reset"    { Cmd-Reset }
    default    {
        Write-Host "BAA 私有部署工具" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "用法: .\deploy\private\deploy.ps1 <命令>"
        Write-Host ""
        Write-Host "命令:"
        Write-Host "  init     生成 .env（首次部署）"
        Write-Host "  up       启动服务（自动构建镜像）"
        Write-Host "  down     停止服务"
        Write-Host "  status   查看运行状态"
        Write-Host "  logs     查看实时日志"
        Write-Host "  reset    ⚠️  停止并删除所有数据"
    }
}
