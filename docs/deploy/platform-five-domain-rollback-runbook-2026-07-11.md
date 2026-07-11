# 五域优化回滚演练运行手册

## 目的

仅回滚应用镜像，不回滚本次新增的 nullable 元数据表；所有验证保持 paper/read-only，不连接 live broker。

## 正式执行前置门

- 部署源必须是已合并到 `main` 的干净提交。
- 必须同时记录当前发布镜像 digest 和上一版本镜像 digest。
- `.env.uat`、数据库备份和隔离 UAT 栈必须可复现。

当前已建立 `main` 基线；正式 UAT 使用 `c343f367`，兼容上一版回滚镜像来自 `suying-branch-validation-*`。旧 `suying-uat-*` 镜像已验证与当前 schema 不兼容，不得作为回滚候选。[KNOWN]

## 执行步骤

```bash
# 1. 记录发布前镜像与数据库版本
docker compose --env-file docker/.env.uat -p suying-uat images
psql "$KRONOS_PG_URL" -Atc "select version_num from alembic_version"

# 2. 只允许切换到已通过兼容性 smoke 的上一版本 digest（不要执行 down -v）
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

已验证的镜像样例：

- 当前 main backend：`sha256:c7c4cc32af35b3b8f34dc5b4a4d083d5a7baf3b061b6ad98e017c9b4f6e2b9b4`
- 兼容上一版 backend：`sha256:89d9b4f86c671c19164f8c7c77b4ff9186a05a212950dad51101e83413619088`
- 当前 main screener：`sha256:b5a3071d9239e51a7ec13edc09e9540eb495f28c7cfaa7c1b643bce5f45edef5`
- 兼容上一版 screener：`sha256:d1639d93430f18d9bd2cb874fcd6c5e44264b481b3e6f75a55bf3ffe9a428abb`
