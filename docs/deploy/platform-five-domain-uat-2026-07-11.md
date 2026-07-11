# 五域优化 UAT 部署报告

- 部署日期：2026-07-11（Asia/Shanghai）
- 部署提交：`c343f367`（已推送到 `main`）
- Compose project：`suying-main-uat`
- 栈性质：独立 main UAT，未复用旧 `suying-uat` 或功能分支验证栈
- 端口段：`9632/9737/9800-9810/9901/9980`（标准 +900 端口被既有栈占用，改用同等隔离的空闲端口）

## 部署门

- [x] main 干净 detached worktree，部署提交为 `c343f367`
- [x] Docker Compose 可用并使用 `--build`
- [x] `.env.uat` 仅从本地注入，未入库
- [x] 独立项目名、独立网络和独立数据库卷
- [x] backend 容器内 Alembic 已到 `031`

## 真实冒烟证据

- Frontend：`http://127.0.0.1:9980` 返回 HTTP 200。
- Backend：`/api/health` 返回 `{"status":"healthy"}`，HTTP 200。
- Gateway：`/health` 返回 healthy，HTTP 200。
- Screener：`/api/v1/screener/modes` 返回真实 freshness；从旧 UAT 迁入的真实行情覆盖到 `2026-07-03`。
- 页面 API smoke：41/41 checks 通过，未执行 action。
- `bi_trend_launch` 在该 UAT 目标日返回 `success_no_matches`，是实际数据结果；普通 smoke 按合同安全跳过诊断、策略、回测和下单，不伪造候选。
- 正式模型 manifest 已在同一 clean main 提交生成：`RUN-20260711_153321`，`official=true`、strict timeline、snapshot `c8a3676d1785460a8c5c8f3408dba3a7`、成本 14 bps。

## 回滚演练

1. 首次使用旧 `suying-uat-*` 镜像回滚时，backend 与旧数据库 schema 不兼容，出现连接重置；该结果判定失败，不计为通过。
2. 使用上一版功能分支验证镜像（`suying-branch-validation-*`）重新回滚，预测服务完成模型预热后，页面 API smoke 41/41 通过。
3. 随后恢复 `c343f367` main 镜像，backend `/api/health` 再次 HTTP 200；数据库卷和 Alembic 版本未回滚。

**回滚结论：通过（使用兼容的上一版应用镜像）；旧 UAT 镜像不兼容，已明确记录并未继续使用。**

## UAT 结论

部署、迁移、只读页面 API 和兼容上一版镜像回滚均通过。正式业务全链路在真实数据 PostgreSQL 上已有三次 paper-only 通过证据；本 UAT 目标日的真实市场结果为无候选，按 no-pick 合同安全跳过依赖候选的步骤。
