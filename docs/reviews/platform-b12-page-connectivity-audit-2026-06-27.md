# 平台化主链路 B12 页面级联通盘点

日期：2026-06-27

## 结论

前端业务 API 已基本收口到统一网关：

```text
baseURL=/api/v1
api-gateway 按服务前缀代理
平台上下文头自动注入
服务健康兼容 status=healthy / online
```

## 已收口

```text
screenerApi      -> /api/v1/screener
predictionApi    -> /api/v1/prediction
strategyApi      -> /api/v1/strategy
signalApi        -> /api/v1/signal
alertApi         -> /api/v1/alert
tradeApi         -> /api/v1/trade
backtestApi      -> /api/v1/backtest
diagnosisApi     -> /api/v1/diagnosis
chainApi         -> /api/v1/screener/chain / policy
liveTradeApi     -> /api/v1/trade
```

## 允许的例外

```text
AuthContext 使用 fetch('/api/v1/auth/*')
```

原因：认证初始化需要在 axios token interceptor 注入前运行，且路径仍经过网关。

```text
Training 页面 EventSource('/api/v1/training/status/:id')
```

原因：SSE 连接不是 axios 请求，但仍走网关路径。

```text
Dashboard window.open('/api/v1/dashboard/run-pipeline')
```

原因：人为触发 pipeline 的浏览器打开动作，仍走网关路径。

## 本阶段修复

```text
healthApi.gateway() 改为 GET /health，避免误拼 /api/v1/health
healthApi.checkOnline() 同时接受 healthy / online
api-gateway 新增 /api/v1/<service>/health -> /api/v1/health 重写
api-gateway 增加核心服务路由矩阵测试
frontend api client 增加服务路径矩阵测试
```

## 下一步

进入页面真实数据联调，建议顺序：

```text
B13 智能看板真实数据和健康态
B14 智能选股 / 产业链
B15 K线预测 / 交易信号
B16 个股诊断 / 回测
B17 模型训练 / 数据更新 / 管理端
```
