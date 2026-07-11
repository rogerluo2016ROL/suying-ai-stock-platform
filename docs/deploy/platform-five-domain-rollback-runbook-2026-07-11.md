# 五域优化回滚演练运行手册

## 目的

仅回滚应用镜像，不回滚本次新增的 nullable 元数据表；所有验证保持 paper/read-only，不连接 live broker。

## 正式执行前置门

- 部署源必须是已合并到 `main` 的干净提交。
- 必须同时记录当前发布镜像 digest 和上一版本镜像 digest。
- `.env.uat`、数据库备份和隔离 UAT 栈必须可复现。

当前分支只有 `feature/suying-ai-stock-platform`，远端没有 `main`，所以本文件截至 2026-07-11 只作为可执行 runbook，未把分支验证冒充正式回滚签字。[KNOWN]

## 执行步骤

```bash
# 1. 记录发布前镜像与数据库版本
docker compose --env-file docker/.env.uat -p suying-uat images
psql "$KRONOS_PG_URL" -Atc "select version_num from alembic_version"

# 2. 将应用服务切换到上一版本 digest（不要执行 down -v）
docker compose --env-file docker/.env.uat -p suying-uat up -d \
  api-gateway backend frontend screener-service data-service prediction-service \
  strategy-service signal-service alert-service trade-service backtest-service \
  training-service diagnosis-service

# 3. 只读验证；交易仍只能 paper
python3 tools/page_api_smoke.py --timeout 30
python3 tools/full_stack_smoke.py --trade-mode paper --require-pick
```

## 判定

回滚通过的必要条件：服务健康、页面 API 无 mock、readiness/schema/ownership 不回退、旧应用能读取新增 nullable 元数据、没有创建 live order。任何一项失败都停止，不回滚数据库。
