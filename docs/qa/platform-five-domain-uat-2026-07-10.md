# 五域优化 UAT 验证报告

- 验证日期：2026-07-11
- 最新验证提交：`d9f462d9`
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

**尚未签字**。项目 UAT 规范要求部署源必须是已合并到 `main` 的干净代码。当前验证源仍是功能分支，且工作区保留用户无关改动，因此本报告只证明最新分支 SIT，不把它伪称为正式 UAT。

## 回滚

正式镜像回滚演练尚未执行：必须在合并后的 main UAT 栈上保留前一应用镜像、仅回滚应用镜像而不回滚新增表，再跑同一套 read-only smoke。当前不覆盖已有旧 `suying-uat` 栈。

## Verdict

**SIT 与可执行 E2E 通过；正式 UAT / 回滚签字待 main 发布基线。**
