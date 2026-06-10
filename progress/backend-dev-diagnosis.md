# backend-dev — Diagnosis Service 实现进度

**状态**: Phase Final 完成  
**日期**: 2026-06-10  
**覆盖**: PRD AC-12.1~12.7（个股诊断）

## 已完成

### 1. diagnosis_engine.py — 五维评分引擎
- [x] `diagnose(code, force_refresh=False) -> DiagnosisReport`：主诊断入口
- [x] 技术面(40%)：复用 kronos-factors 25 因子评分（five_factor + short_term + long_term + trend_strength + reversal + liquidity），`asyncio.gather` 并发执行
- [x] 资金面(25%)：北向净流入（30日聚合）+ 融资余额 + 龙虎榜净买入（10日）+ 主力资金流（5日），各子指标 Min-Max 归一化到 0-100 后加权
- [x] 基本面(20%)：PE 历史分位 + ROE + 营收增速 + 资产负债率，四级分段映射到 0-100
- [x] AI预测(10%)：HTTP 调用 Kronos 预测服务 `/api/v1/prediction/predict/{code}`，预测收益 + 置信度双因子评分
- [x] 情绪面(5%)：研报评级映射（买入/增持/持有/减持 → 0-100）+ 新闻情感平均分
- [x] 加权聚合：`overall = Σ(w_i × score_i) / Σw_i`（ADR-005 Decision 1）
- [x] Kronos 降级策略（ADR-005 Decision 5）：AI 预测不可用时，权重重新分配为 技术面 44%/资金面 28%/基本面 22%/情绪面 6%，标注降级维度
- [x] 五级操作建议映射（ADR-005 Decision 1）：≥85→强烈买入, 70-84→买入, 50-69→持有, 35-49→减仓, <35→卖出
- [x] 关键价位计算：20日支撑位/阻力位 + 止损位（基于K线数据）
- [x] 风险提示自动生成：综合评分低、单维度弱、AI预测回撤大时自动添加

### 2. routes.py — 6 端点
- [x] `POST /api/v1/diagnosis/analyze` — 五维诊断（AC-12.1~12.4）：股票代码验证 + 存在性检查 + 诊断结果持久化到 diagnosis_history
- [x] `POST /api/v1/diagnosis/compare` — 多股对比（2-5只，AC-12.6）：`asyncio.gather` 并发诊断 + 综合排名 + 维度矩阵对比
- [x] `GET /api/v1/diagnosis/report/{code}` — 获取最新报告（AC-12.5）：缓存优先（从 history 读取），否则实时计算
- [x] `GET /api/v1/diagnosis/report/{code}/pdf` — PDF 导出（AC-12.5）：Playwright headless Chrome 优先（ADR-005 Decision 2），fallback HTML `@media print`
- [x] `GET /api/v1/diagnosis/history` — 历史记录列表（AC-12.7）：按股票代码筛选 + 分页
- [x] `GET /api/v1/diagnosis/history/{id}` — 单条历史详情（AC-12.7）
- [x] 所有端点 `require_role("admin", "internal_analyst", "external_analyst", "user")` 鉴权

### 3. DB Migration — `004_add_diagnosis_tables.py`
- [x] `diagnosis_history`：id, user_id, code, overall_score, grade, recommendation, report(JSONB), created_at
- [x] `diagnosis_config`：key, value, description, updated_at, updated_by
- [x] 种子数据：五维权重（40/25/20/10/5）+ 操作建议阈值
- [x] 索引：code, user_id, code+created_at 联合索引, created_at

### 4. 配套文件
- [x] `app/config.py`：环境驱动配置（DB URL, JWT secret, Redis URL, Kronos URL, 缓存 TTL）
- [x] `app/database.py`：async SQLAlchemy session factory（复用后端 PostgreSQL）
- [x] `app/deps.py`：JWT 验证 + RBAC `require_role()`（所有角色可见）
- [x] `app/schemas.py`：完整 Pydantic schema（DiagnosisReport, DimensionScore, 5个维度子模型, 请求/响应/分页模型）
- [x] `app/main.py`：FastAPI 入口（port 8009），已有骨架，新增路由自动生效
- [x] `app/__init__.py`：已有

## 质量门

| 门 | 状态 | 说明 |
|----|------|------|
| 类型安全 | OK | Pydantic 模型全类型注解 + Python 3.14 兼容 |
| 鉴权覆盖 | OK | 6 端点全部 `require_role(ALL_ROLES)` |
| 错误码 | OK | 400/401/403/404/500 覆盖 |
| 契约一致 | OK | 6 端点签名与 ADR-005 对齐 |
| 降级容错 | OK | Kronos 不可用时自动降级权重分配；Playwright 不可用时 HTML fallback；单维度失败不影响整体诊断 |
| 并发 | OK | `asyncio.gather` 并发五维评分 + 对比诊断 |

## 未覆盖 / 已知限制

- Kronos 预测为 HTTP 调用外部服务（需 Kronos 服务运行中），降级策略已实现
- Playwright PDF 需在容器中安装 Chromium + Playwright（`playwright install chromium`），当前 fallback 为 HTML 打印版本
- Redis 缓存层（48h 诊断缓存 + 6h Kronos 缓存）在 engine 中预留但尚未集成 Redis client
- APScheduler 预热任务（交易日 9:00/15:30 预热热门股票 Kronos 缓存）未实现
- 情绪面新闻情感分析依赖 `news_sentiment` 表（可能尚未建表），fallback 为 50 分中性
- 诊断权重/阈值当前硬编码在 engine 中，`diagnosis_config` 表已建但 engine 尚未从 DB 读取（后续 ADR 可引入动态配置）

## 下一步

1. `backend-dev`: 集成 Redis 缓存层（`aioredis` / `redis-py`），实现 48h 诊断缓存 + 6h Kronos 缓存
2. `ml-engineer`: 实现 APScheduler 预热任务（交易日定时预热 Kronos 预测缓存）
3. `devops`: Playwright 容器化（安装 Chromium + 依赖字体）
4. `frontend-dev`: 重构 Diagnosis.tsx 接入新 `/api/v1/diagnosis/analyze` 端点
5. `qa-engineer`: 编写诊断服务 E2E 测试（五维评分验证 + PDF 导出 + 多股对比 + 历史查询）
