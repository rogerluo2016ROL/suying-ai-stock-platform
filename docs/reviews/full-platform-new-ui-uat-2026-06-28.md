# 全站新 UI 浏览器 UAT 记录

日期：2026-06-28  
范围：新 UI 全站路由矩阵、交易门禁、数据更新降级渲染  
执行方式：Vite dev server + Chromium/Chrome + Playwright browser-level API mock

## 结论

通过。全站 67 条前端路由完成浏览器烟测，未发现空白页、路由 404、React runtime error 或 app shell 缺失。

## 环境

- 前端地址：`http://127.0.0.1:3002`
- 浏览器：Playwright Chromium，使用本机 Chrome channel
- 鉴权：浏览器层 mock `/api/v1/auth/refresh` 与 `/api/v1/auth/me`，身份为 `admin`
- API：浏览器层 mock 基础服务响应，用于验证真实 React 页面在空/降级数据下不崩溃
- 截图目录：`output/playwright/full-platform-uat-2026-06-28/`
- 结果文件：`output/playwright/full-platform-uat-2026-06-28/route-smoke-results.json`

## 覆盖

- 智能看板、开盘决策、智能选股、产业链拆解、K 线预测、交易信号
- 交易中心、量化交易、方案管理、风控中心、回测分析、P0 主链路
- 个股诊断、模型训练、模型注册、数据更新、运行状态、平台升级
- 交易审计、风控判定、决策上下文

## 结果

- 路由数量：67
- 截图数量：67
- 失败数量：0
- app shell 检查：67/67 通过
- 主体内容非空检查：67/67 通过
- 页面运行时错误：0

## 过程中发现并修复

- 数据更新页在 API 返回 `{}` 时会覆盖 fallback 状态，导致 `undefined.toLocaleString()`。
- 已修复：`frontend/src/pages/DataUpdate.tsx` 增加 `normalizeDataStatus` 与安全数字格式化。
- 已补测试：`frontend/src/__tests__/DataUpdate.test.tsx` 覆盖 partial response fallback。

## 交易链路补充验证

- live 未连接时，后端拒绝 `trade_mode=live` 下单和预检，不再静默回退模拟盘。
- paper/live 下单前共用 `/api/v1/trade/order/pre-check` 风控预检。
- 风控通过、拒绝、人工复核、下单、撤单、券商未连接均有审计事件。
- 全站 header 增加券商连接状态，避免“实盘模式”和“券商已连接”混淆。

## 剩余边界

本次浏览器 UAT 验证的是新 UI 路由和降级渲染稳定性。真实 PostgreSQL 数据、真实模型服务、真实 QMT/券商连接需要在 API smoke 与部署环境中继续验证。
