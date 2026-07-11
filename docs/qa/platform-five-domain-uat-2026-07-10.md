# 五域优化 UAT 验证报告

- 验证日期：2026-07-11
- 最新验证提交：`62a372dc`
- 验证栈：`suying-branch-validation`
- 栈性质：功能分支隔离 SIT，不冒充正式 main UAT
- Frontend：`http://127.0.0.1:28981`
- Gateway：`http://127.0.0.1:28080`
- PostgreSQL：本地隔离端口 26432

## 环境结论

- 15 个容器均稳定运行；PostgreSQL、Redis healthy。
- 全新数据库 Alembic 已升级到 `031`。
- 修复了 migration 030 对 identity 列设置 default 导致的新库启动失败。
- 修复了 screener 在 Python 3.11 下缺少 `Optional` 导入导致的重启。
- Docker 构建上下文由约 640MB 降到约 41MB。
- 预测镜像使用 `torch-2.13.0+cpu`，不再下载 CUDA 运行库。
- 页面 API 41/41 通过；浏览器测试 1/1 通过。
- trade health 明确为 paper；未连接 live broker，未执行实盘交易。
- 真实历史因子横截面补采后，回测达到 32 个交易期/2586 条观测；三次 paper-only full-stack smoke 均通过。

## 正式 UAT 门

已建立 `main` 基线 `c343f367`，并从干净 detached worktree 部署独立 `suying-main-uat` 栈；部署、迁移和 41 项只读页面 API 检查通过。部署细节见 `docs/deploy/platform-five-domain-uat-2026-07-11.md`。

## 回滚

已在 main UAT 栈执行应用镜像回滚：旧 `suying-uat-*` 镜像因 schema 不兼容失败，随后使用兼容的上一版 `suying-branch-validation-*` 镜像回滚，41/41 read-only smoke 通过；恢复 main 镜像后 backend health 仍为 HTTP 200，数据库未回滚。

## Verdict

**正式 UAT 部署与兼容上一版镜像回滚通过；目标日无候选按真实 no-pick 合同记录。**
