#!/usr/bin/env bash
# =============================================================================
# BAA 私有部署一键脚本（Linux / macOS / WSL2）
# 用法：
#   ./deploy/private/deploy.sh init      # 生成密钥 + .env
#   ./deploy/private/deploy.sh up        # 启动服务
#   ./deploy/private/deploy.sh down      # 停止服务
#   ./deploy/private/deploy.sh logs      # 查看实时日志
#   ./deploy/private/deploy.sh status    # 查看运行状态
#   ./deploy/private/deploy.sh reset     # ⚠️ 停止并删除数据卷（清空所有数据）
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_PROD_EXAMPLE="$PROJECT_ROOT/.env.production.example"

cd "$PROJECT_ROOT"

# ── 工具函数 ──────────────────────────────────────────────

gen_key() {
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

check_prereqs() {
    command -v docker >/dev/null 2>&1 || { echo "ERROR: docker 未安装"; exit 1; }
    command -v docker compose >/dev/null 2>&1 || {
        docker-compose --version >/dev/null 2>&1 || { echo "ERROR: docker compose 未安装"; exit 1; }
    }
}

ensure_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "❌ 未找到 .env 文件"
        echo "   请先运行: ./deploy/private/deploy.sh init"
        exit 1
    fi
}

# ── 命令实现 ──────────────────────────────────────────────

cmd_init() {
    check_prereqs
    if [[ -f "$ENV_FILE" ]]; then
        echo "⚠️  .env 已存在，跳过初始化（如需重新生成请手动删除）"
        exit 0
    fi
    echo "🔧 生成 BAA 安全配置..."
    cp "$ENV_PROD_EXAMPLE" "$ENV_FILE"
    sed -i "s/CHANGE_ME_TO_STRONG_RANDOM/$(gen_key)/g" "$ENV_FILE"
    echo "✅ 已生成 $ENV_FILE"
    echo ""
    echo "📋 关键配置："
    grep -E "^BAA_API_KEY|^POSTGRES_PASSWORD" "$ENV_FILE" | sed 's/=.*/=***REDACTED***/'
    echo ""
    echo "🚀 启动: ./deploy/private/deploy.sh up"
}

cmd_up() {
    check_prereqs
    ensure_env
    echo "🚀 启动 BAA 服务..."
    docker compose up -d --build
    echo ""
    echo "⏳ 等待服务就绪（最多 90s）..."
    for i in $(seq 1 18); do
        if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "✅ BAA 已就绪！"
            echo "   Health:   http://localhost:8000/health"
            echo "   Metrics:  http://localhost:8000/metrics"
            echo "   API:      http://localhost:8000/api/v1/functions"
            echo ""
            echo "📋 验证安全门禁（应返回 401）:"
            curl -s http://localhost:8000/api/v1/functions | python3 -m json.tool 2>/dev/null || true
            exit 0
        fi
        sleep 5
    done
    echo "⚠️  服务未就绪，查看日志排查："
    docker compose logs --tail=50 baa
    exit 1
}

cmd_down() {
    check_prereqs
    docker compose down
    echo "✅ 服务已停止"
}

cmd_status() {
    check_prereqs
    docker compose ps
    echo ""
    curl -sf http://127.0.0.1:8000/health 2>/dev/null && echo "" || echo "⚠️  /health 不可达（服务可能未启动）"
}

cmd_logs() {
    check_prereqs
    docker compose logs -f "$@"
}

cmd_reset() {
    echo "⚠️  警告：此操作将停止服务并删除所有数据卷！"
    read -rp "确认删除？输入 yes: " answer
    if [[ "$answer" != "yes" ]]; then
        echo "❌ 已取消"
        exit 0
    fi
    check_prereqs
    docker compose down -v
    echo "✅ 数据卷已删除，运行 ./deploy/private/deploy.sh init 重新开始"
}

# ── 入口 ──────────────────────────────────────────────────

case "${1:-help}" in
    init)     cmd_init ;;
    up)       cmd_up ;;
    down)     cmd_down ;;
    status)   cmd_status ;;
    logs)     shift; cmd_logs "$@" ;;
    reset)    cmd_reset ;;
    help|*)
        echo "BAA 私有部署工具"
        echo ""
        echo "用法: ./deploy/private/deploy.sh <命令>"
        echo ""
        echo "命令:"
        echo "  init     生成 .env（首次部署）"
        echo "  up       启动服务（自动构建镜像）"
        echo "  down     停止服务"
        echo "  status   查看运行状态"
        echo "  logs     查看实时日志（可跟服务名）"
        echo "  reset    ⚠️  停止并删除所有数据"
        ;;
esac
