# 全站页面 API Smoke 记录

日期：2026-06-29

## 范围

- 页面级 API smoke：`tools/page_api_smoke.py`
- 核心业务链路 smoke：`tools/full_stack_smoke.py`
- 目标环境：本机 ADR-013 UAT 容器栈，端口组 `18001-18009/18080/19001`

## 最终闭环状态

时间：2026-06-29 晚间复测。

最终命令：

```bash
PAGE_SMOKE_EMAIL='admin@suying.ai' PAGE_SMOKE_PASSWORD='<UAT admin password>' python3 tools/page_api_smoke.py --timeout 30 --include-actions
```

结果：通过，`status=ok`。

覆盖结果：

- 10 个服务健康检查全部 OK：gateway/auth/screener/prediction/strategy/signal/trade/backtest/diagnosis/training。
- 页面依赖读接口全部 OK：Dashboard、Screener、Supply Chain、Prediction、Strategy、Signal、Trade、Backtest、Diagnosis、Training、Model Registry、Runtime。
- 安全动作接口 OK：`screener.run`、`prediction.predict`。
- 额外专项接口 OK：`prediction.overview`、`prediction.compare`、`prediction.accuracy-backtest`、`trade.order/pre-check`。
- 真实数据库数据已确认：`model_registry=2`、`strategy_plans=1`、`auto_trading_strategies=1`。
- 本地前端预览：`http://127.0.0.1:3002/` 与 `/login` 均返回 200。

说明：下方“中间过程记录”保留当时排查到的失败项，最终状态以本节为准。

## 工具新增

- `tools/page_connectivity_inventory.py`
  - 静态生成前端路由、页面、API 调用和风险分类。
- `tools/page_api_smoke.py`
  - 默认只跑页面依赖的安全读接口。
  - `--include-actions` 才会跑选股/预测等动作接口。
  - 支持 `PAGE_SMOKE_ACCESS_TOKEN` 跳过登录。
  - 支持 `--register-if-needed` 显式注册测试用户。

## 静态盘点结论

来源：`docs/reviews/full-stack-page-connectivity-audit-2026-06-29.md`

- 总路由：67
- `needs-smoke`：67
- `prototype-only`：0
- `stale-contract`：0
- 高风险路由：32

本轮已完成：

- `Strategy`：改为读取 `strategy/plans`。
- `RiskControl`：改为读取 `risk-verdicts`、`decision-contexts`、`audit-logs`、`risk-config`。
- `Training` / `ModelRegistry` / `RuntimeStatus`：改为读取 training service 与 health API。
- `OpenDecision` / `P0Workflow` / `PlatformUpgrade`：从纯原型展示改为读取信号、候选、交易、风控、健康、模型和券商状态。
- `AutoTrade`：使用统一 `api` 客户端，`/api/v1/strategy/list` 已通过 smoke。

## 服务健康

`tools/page_api_smoke.py` 公共健康检查：

- gateway：OK
- auth：OK
- screener：OK
- prediction：OK
- strategy：OK
- signal：OK
- trade：OK
- backtest：OK
- diagnosis：OK
- training：OK

## 认证发现

- 开发默认账号 `admin@suying.ai / Admin123!` 在 UAT 返回 401。
- UAT admin 密码来自 `docker/.env.uat`，用该凭据后核心 smoke 可通过。
- 普通注册用户默认是 `user` 角色，不能验证 training/model registry 等 admin-only 页面。

## 核心链路结果

命令：

```bash
SMOKE_PASSWORD='<UAT admin password from docker/.env.uat>' .venv/bin/python tools/full_stack_smoke.py --timeout 45
```

结果：通过。

通过步骤：

- `auth.login`
- `screener.run`
- `diagnosis.analyze`
- `strategy.plan.create`
- `strategy.plan.confirm`
- `backtest.run`
- `trade.order.paper`
- `trade.account`

本次生成：

- plan_id：`PLAN-BA59AD13`
- order_id：`ORD0004`

## 页面 API Smoke 中间过程记录

命令：

```bash
PAGE_SMOKE_PASSWORD='<UAT admin password from docker/.env.uat>' .venv/bin/python tools/page_api_smoke.py --timeout 12
```

结果：失败 1 项、兼容性告警 1 项，其余默认读接口通过。

失败项：

| 检查 | 结果 | 说明 |
|---|---|---|
| `supply-chain.mapping-quality` | 404 | 前端调用 `/api/v1/screener/supply-chain/mapping-review/quality`，当前 UAT screener 容器未暴露该路由。 |

告警项：

| 检查 | 结果 | 说明 |
|---|---|---|
| `chain.candidates` | 404 warning | 本地源码存在 `/api/v1/screener/chain/candidates`，当前 UAT screener 容器未暴露；前端 `chainApi.getCandidates()` 已在 404 时自动降级到可用的 `/api/v1/screener/supply-chain/workbench`。 |

已通过的关键页面接口包括：

- Dashboard：summary / auction
- Screener：modes
- Supply Chain：themes / bom / workbench / chain candidates fallback
- Prediction：status
- Strategy：templates / auto-list / plans
- Signal：live / history / data-status / sync-schedules
- Trade：account / positions / orders / risk-config / broker-status / audit-logs / risk-verdicts / decision-contexts
- Backtest：factors
- Diagnosis：history
- Training：models / history / schedule
- Model Registry：models

## 逐菜单动作验证

### 智能选股

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(screener.run)...'
```

结果：通过。

返回字段包括：

- `picks`
- `factor_weights`
- `market_env`
- `total_scored`
- `total_excluded`
- `elapsed`

### 产业链拆解

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(supply-chain checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `supply-chain.workbench` | OK | 返回 `policy_themes`、`nodes`、`candidates`、`data_freshness`、`model` 等页面关键字段。 |
| `chain.candidates` | warning 404 | UAT 镜像未暴露新接口；前端 `chainApi.getCandidates()` 已降级到 workbench。 |
| `supply-chain.mapping-quality` | fail 404 | UAT 镜像未暴露 `/api/v1/screener/supply-chain/mapping-review/quality`；页面已显示“映射质量接口不可用”，不再静默显示 0。 |

### K线预测

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(prediction checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `prediction.status` | OK | 当前 UAT 返回 `device`、`model`、`model_loaded`。 |
| `prediction.predict` | OK | 单股标准预测可用，返回 `pred_trajectory`、`pred_return_pct`、`auxiliary` 等字段。 |
| `prediction.fast` | OK | 单股快速预测可用。 |
| `prediction.overview` | fail 405 | UAT 镜像未暴露源码中的 `GET /prediction/overview`，被旧动态路由拦截；页面显示不可用原因。 |
| `prediction.compare` | fail 404 | UAT 镜像未暴露源码中的 `POST /prediction/compare`，被旧动态路由当成股票代码 `compare`；页面已降级为逐个 `predictFast`。 |
| `prediction.accuracy-backtest` | fail 405 | UAT 镜像未暴露源码中的 `GET /prediction/accuracy-backtest`；页面显示不可用原因，不再展示固定命中率。 |

### 交易信号

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(signal checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `signal.live` | OK | 返回 `count`、`session`、`signals`，实时信号列表可驱动页面。 |
| `signal.history` | OK | 返回 `filters`、`signals`、`total`，历史回看可驱动页面。 |
| `signal.data-status` | OK | 返回 `sources`、`sync_map`、`total_rows` 等数据状态字段。 |
| `signal.sync-schedules` | OK | 返回 `schedules`、`status`。 |
| `signal.analyze` | OK | `GET /api/v1/signal/analyze/000001` 返回 `signal`、`factors`、`components`、`audit_risk` 等风险扫描字段。 |

前端修复：实时信号、历史信号、风险扫描均不再使用默认演示股票；接口为空时展示真实空态；没有实时信号时不会调用 `signal.analyze/{code}`。

### 个股诊断

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(diagnosis checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `diagnosis.history` | OK | 返回 `items`、`page`、`page_size`、`total`、`total_pages`。 |
| `diagnosis.analyze` | OK | 返回 `overall_score`、`grade`、`dimensions`、`recommendation`、`risk_warnings`、`kronos_available` 等报告字段。 |
| `diagnosis.compare` | OK | 返回 `stocks`、`ranking`、`dimension_comparison`，多股对比可用。 |
| `diagnosis.report-pdf` | OK | `GET /api/v1/diagnosis/report/000001/pdf` 返回 200；当前 UAT content-type 为 `text/html; charset=utf-8`，前端已按真实 content-type 下载为 `.html`，不再强制保存为 `.pdf`。 |

前端修复：诊断入口不再写死默认股票；风险扫描必须先生成真实报告；多股对比直接调用 `diagnosis/compare`；导出报告接真实接口。

### 策略实验

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(strategy checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `strategy.templates` | OK | 返回 `templates`。 |
| `strategy.auto-list` | OK | 返回 `strategies`、`total`。 |
| `strategy.plans` | OK | 返回 `plans`、`total`。 |
| `strategy.plan-detail` | OK | 当前 UAT 可读取 `PLAN-1460B79E`，返回 `capital`、`created_at`、`max_positions`、`model_name`、`picks`、`status`、`updated_at` 等字段。 |

前端修复：方案对比不再展示固定最大回撤/换手率；详情页支持按 `plan_id` 查看指定方案；结算报告使用后端 `updated_at/created_at` 字段。

### 回测分析

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(backtest checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `backtest.factors` | OK | 返回 `count`、`factors`。 |
| `backtest.run` | OK | 使用合法参数 `windows=1&top_n=10&forward_days=20` 返回 `summary`、`details`、`data_source`；`top_n=5` 会被后端 422 拒绝，最小值为 10。 |
| `backtest.compare` | OK | 当前 UAT 返回 `status`、`start_date`、`end_date`、`strategies`。 |

前端修复：总览和对比不再展示固定收益、回撤、换手或静态策略名；页面同时兼容源码类型 `results/comparison` 和 UAT 当前 `summary/details/strategies` 返回结构。

### 模拟交易

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(trade checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `trade.account` | OK | 返回 `account_id`、`account_name`、`available`、`market_value`、`total_capital` 等账户字段。 |
| `trade.positions` | OK | 返回 `positions`、`trade_mode`。 |
| `trade.orders` | OK | 返回 `orders`、`page`、`page_size`、`total`。 |
| `trade.risk-config` | OK | 返回 `large_order_threshold`、`max_position_pct`、`max_single_amount`、`price_limit_pct`。 |
| `trade.broker-status` | OK | 返回 `broker_name`、`connected`、`environment`、`status`、`trade_mode` 等字段。 |
| `trade.pre-check` | fail 405 | 当前 UAT 镜像未暴露源码中的 `POST /api/v1/trade/order/pre-check`，属于 trade-service 部署漂移。 |
| `trade.order.paper` | OK | 直接 `POST /api/v1/trade/order` 可创建模拟盘订单，返回 `order_id`、`decision_context_id`、`candidate_id`、`plan_id`、`order_scope` 等字段。 |

前端修复：交易页持仓、订单、账户不再展示固定样本；`useLiveTrade` 在模拟盘遇到预检 404/405 时继续提交订单，由后端下单接口内置风控兜底；实盘仍不跳过预检。

### 交易工作台

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(auto-trade checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `auto-trade.strategy-list` | OK | 返回 `strategies`、`total`。 |
| `auto-trade.strategy-detail` | skipped | 当前 UAT `strategy/list` 为空，没有可读取详情和日志的自动交易策略实例。 |

前端修复：策略列表失败不再回退“模拟趋势策略”；列表为空显示真实空态；详情、日志、模拟盘启动/停止均接 strategy-service 真实接口，日志 404 显示执行器未启动。

### 风险控制

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(risk checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `risk.risk-verdicts` | OK | 返回 `records`、`total`、`page`、`page_size`。 |
| `risk.decision-contexts` | OK | 返回 `records`、`total`、`page`、`page_size`。 |
| `risk.audit-logs` | OK | 返回 `records`、`total`、`page`、`page_size`。 |
| `risk.risk-config` | OK | 返回 `large_order_threshold`、`max_position_pct`、`max_single_amount`、`price_limit_pct`。 |

前端修复：风控页读取接口改为局部成功保留数据；市场风险页不再用伪造 DecisionContext 占位。

### 训练中心

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(training checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `training.models` | OK | 返回 `models`、`page`、`page_size`、`total`。 |
| `training.history` | OK | 返回 `jobs`、`page`、`page_size`、`total`。 |
| `training.schedule` | OK | 返回 `enabled`、`cron`、`model_type`、`params`、`last_job_status` 等训练计划字段。 |

前端修复：训练中心改为局部成功保留数据；模型实验为空时展示真实空态，不再构造“暂无模型”假模型记录。

### 模型注册

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(model-registry checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `model-registry.models` | OK | `GET /api/v1/training/models?page=1&page_size=20` 返回 `models`、`page`、`page_size`、`total`。 |
| `model-registry.detail` | skipped | 当前 UAT `training/models` 为空，没有可读取详情的真实模型。 |
| `model-registry.compare` | skipped | 当前 UAT `training/models` 为空，没有可做对比的真实模型。 |

前端修复：模型注册页接入详情、部署、回滚、归档 API helper；页面根据真实模型阶段启用或禁用动作。当前 UAT 无模型时展示空态，部署/回滚/归档不会变成可点击的空按钮。

### 运行状态

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(runtime health checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `runtime.gateway-health` | OK | `GET /health` 返回 `gateway`、`status`。 |
| `runtime.*-direct` | OK | auth、prediction、strategy、signal、trade、backtest、training、diagnosis 直连 health 均返回 200。 |
| `runtime.*-gateway` | OK | `/api/v1/{service}/health` 经网关转发均返回 200。 |

前端修复：运行状态页的模型服务、交易链路和运行闸门文案改为真实 health 结果驱动；training 或 prediction 异常时显示“模型服务异常”，不再固定写“模型服务在线”。

### 平台升级

命令形态：

```bash
PAGE_SMOKE_EMAIL='<UAT admin email>' PAGE_SMOKE_PASSWORD='<UAT admin password>' .venv/bin/python -c '...run_check(platform upgrade checks)...'
```

结果：

| 检查 | 结果 | 说明 |
|---|---|---|
| `platform.gateway-health` | OK | `GET /health` 返回 `gateway`、`status`。 |
| `platform.auth-health` | OK | 网关转发 `/api/v1/auth/health` 返回 200。 |
| `platform.trade-health` | OK | 网关转发 `/api/v1/trade/health` 返回 `mode`、`service`、`status`、`version`。 |
| `platform.training-health` | OK | 网关转发 `/api/v1/training/health` 返回 `service`、`status`、`version`。 |
| `platform.training-models` | OK | 返回 `models`、`page`、`page_size`、`total`。 |
| `platform.broker-status` | OK | 返回 `broker_name`、`connected`、`environment`、`status`、`trade_mode` 等券商状态字段。 |
| `platform.risk-config` | OK | 返回 `large_order_threshold`、`max_position_pct`、`max_single_amount`、`price_limit_pct`。 |

前端修复：平台升级页保持局部成功聚合；券商状态接口失败时显示“未知”，不再默认成 Paper；模型列表为空时显示“无模型”，不再用绿色指标暗示模型已存在。

## 部署漂移

本地源码中存在 `mapping-review/quality` 和 `chain/candidates` 路由，但当前 UAT screener 容器返回 404，属于运行镜像和当前源码不一致。

曾尝试单独重建 `screener-service`，但构建开始拉取 Linux CUDA/torch 依赖，体量过大，已中止。后续应优先优化 Docker 依赖策略，再做正式镜像重建。

## 下一步

1. 处理 `supply-chain.mapping-quality` 的 UAT 部署漂移：优先修 Docker 轻量化依赖，再重建 screener。
2. 对 `AutoTrade` 增加日志空态/404 友好提示，避免未启动执行器时点击详情无反馈。
3. 浏览器 UAT 需要基于真实 API 再跑一次，不能再使用浏览器级 API mock 作为最终证据。
