#!/bin/bash
# ADR-013 UAT 栈部署脚本
# 用法: cd /Users/rogerluo/程序目录/K线大模型/docker && bash uat-adr013-deploy.sh
set -euo pipefail

echo "=== ADR-013 UAT 栈部署 ==="
echo "Commit: 0ba2a3e"
echo "Project: uat-adr013"
echo "端口偏移: +10000 (PG 16432 / Redis 17379 / API 18080 / backend 19001 / 18001-18009)"

# Step 1: Retag 旧镜像
echo ""
echo "--- Step 1: Retag suying-uat images → uat-adr013 ---"
for s in alert-service api-gateway backend backtest-service diagnosis-service prediction-service screener-service signal-service strategy-service trade-service; do
  if docker image inspect suying-uat-${s}:latest >/dev/null 2>&1; then
    docker tag suying-uat-${s}:latest uat-adr013-${s}:latest && echo "  OK: $s"
  else
    echo "  WARN: suying-uat-${s}:latest not found"
  fi
done
echo "Retag 完成: $(docker images | grep uat-adr013 | wc -l) images"

# Step 2: Bring up full stack
echo ""
echo "--- Step 2: docker compose up -d ---"
docker compose -p uat-adr013 --env-file .env.uat up -d

echo ""
echo "--- Step 3: 检查容器状态 ---"
docker compose -p uat-adr013 ps

echo ""
echo "--- Step 4: 健康检查 ---"
echo "Postgres:"
docker exec uat-adr013-postgres-1 pg_isready -U kronos

echo ""
echo "Redis:"
docker exec uat-adr013-redis-1 redis-cli ping

echo ""
echo "API Gateway (18080):"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:18080/health 2>&1 || echo "  not ready yet"

echo ""
echo "Backend (19001):"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:19001/health 2>&1 || echo "  not ready yet"

echo ""
echo "Alembic version:"
docker exec uat-adr013-postgres-1 psql -U kronos -d kronos -c "SELECT version_num FROM alembic_version;"

echo ""
echo "ths_daily schema (17 columns):"
docker exec uat-adr013-postgres-1 psql -U kronos -d kronos -c "SELECT count(*) AS col_count FROM information_schema.columns WHERE table_name='ths_daily';"

echo ""
echo "=== 部署脚本完成 ==="
echo "下一步:"
echo "  1. 冒烟其他服务: for p in 18001 18002 18003 18004 18005 18006 18007 18009; do curl -sS -w 'port \$p: %{http_code}\n' http://localhost:\$p/health; done"
echo "  2. 启动 data-service: KRONOS_PG_URL=postgresql://kronos:kronos@localhost:16432/kronos TUSHARE_TOKEN_FILE=/path/to/tushare_token python -m uvicorn app.main:app --port 18010"
echo "  3. cb_sync 实跑: 手动触发 sync_ths_daily(days_back=2)"
