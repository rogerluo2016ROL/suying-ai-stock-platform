# Diagnosis Backend Code Review — 2026-06-10

Reviewer: code-reviewer
Scope: `services/diagnosis-service/app/{diagnosis_engine.py, routes.py, deps.py, schemas.py, config.py}`
Reference: `docs/adr/005-stock-diagnosis.md`
Focus: 五维评分正确性 / Kronos 降级 / PDF 生成 / RBAC / 前后端契约一致性

---

## Verdict: **BLOCKED — 3 Critical**

The engine logic is architecturally sound and faithfully implements ADR-005 weights/thresholds, but the service cannot ship because: (1) the Kronos cache layer that ADR-005 mandates is absent, (2) the PDF generation route does not render charts as the ADR requires, and (3) the frontend-backend contract is fundamentally broken (query-param vs request body, type shape mismatch).

---

## Findings

### C1 — Kronos 缓存未实现（违反 ADR-005 Decision 5）

**File**: `diagnosis_engine.py:545-606`
**ADR reference**: Decision 5 — "缓存优先 + TTL 驱动刷新"

`_score_ai_predict()` 每次诊断都直接通过 `aiohttp` 调用 Kronos HTTP API，完全不检查 Redis 缓存。`config.py` 中定义了 `KRONOS_CACHE_TTL` (6h) 和 `KRONOS_CACHE_TTL_WEEKEND` (24h)，但在诊断引擎代码中**零引用**。

ADR-005 明确写了"同一股票代码的预测结果缓存 6 小时（交易日期间），非交易日缓存 24 小时"，且估算"按缓存命中率 90% 估算，日均诊断 500 次 → 实际调用 50 次/天"。如果不实现缓存，Kronos GPU 推理成本将是预期的 **10 倍**（500/day vs 50/day），且每次诊断延迟额外增加 3-8 秒。

**Fix**:
```
# Before Kronos HTTP call, check Redis:
cache_key = f"kronos_pred:{code}"
cached = await redis.get(cache_key)
if cached and not force_refresh:
    return _build_ai_dimension(json.loads(cached))
```

---

### C2 — PDF 报告不含图表（违反 ADR-005 Decision 2 选型意图）

**File**: `routes.py:355-496`
**ADR reference**: Decision 2 — "HTML 模板（前端渲染）+ Playwright headless 转 PDF"；否决 WeasyPrint 的理由是"不支持 JavaScript 图表渲染"

`_generate_pdf_playwright()` 构建了一个纯服务端 HTML（`_build_report_html()`），然后让 Playwright 渲染它。这个 HTML：
- 没有 `<script>` 标签，没有 ECharts
- K 线图和五维雷达图完全缺失
- 只是一个带内联 CSS 的静态表格 + 文字卡片

这与 ADR-005 否决 WeasyPrint 的理由直接矛盾 —— ADR 选 Playwright 就是为了能渲染 JavaScript 图表（ECharts K 线图 + 雷达图），但当前实现实际上就是 Service-side static HTML，跟 WeasyPrint 方案无本质区别。

ADR-005 原文："诊断报告包含 K 线图（ECharts/Lightweight Charts）、五维雷达图、评分仪表盘等复杂可视化，HTML + 前端图表库渲染效果远优于后端 PDF 库手绘图形。"

ADR 意图是 Playwright 打开**前端诊断报告页面**（Diagnosis.tsx 的 URL），然后 `page.pdf()` 截取。当前实现是服务端自建 HTML，完全绕过了前端图表。

**Fix**:
```
# Navigate to the actual frontend report page
frontend_url = f"{FRONTEND_BASE_URL}/diagnosis?code={code}"
await page.goto(frontend_url, wait_until="networkidle")
await page.wait_for_selector(".diagnosis-report-loaded")  # wait for charts to render
pdf_bytes = await page.pdf(...)
```

---

### C3 — Kronos 调用缺少认证头

**File**: `diagnosis_engine.py:559-560`
**ADR reference**: Decision 5 — "HTTP REST POST /api/v1/prediction/predict/{code} + 带 Bearer Token 认证"

`_score_ai_predict()` 创建 `aiohttp.ClientSession()` 后直接 `session.get(kr_url)`，没有添加 `Authorization: Bearer <token>` 头。如果 Kronos 服务启用了 JWT 校验（与后端共享同一 secret），此调用将返回 401。

另外，ADR 写的是 `POST`，但代码用的是 `session.get()`。

**Fix**: 从 `app.config` 读取 `KRONOS_AUTH_TOKEN` 或复用 `JWT_SECRET_KEY` 签发内部服务 token，在 headers 中传递。

---

### H1 — 资金面归一化魔法数字缺乏依据

**File**: `diagnosis_engine.py:345-351`

```python
nb_score = _clamp(50 + northbound_net / 50000 * 50)
lb_score = _clamp(50 + leaderboard_net / 20000 * 50)
mf_score = _clamp(50 + main_force_flow / 100000 * 50)
```

这些除数（50000 / 20000 / 100000）是硬编码的魔法数字。不同市值规模的股票，其北向资金 / 龙虎榜 / 主力资金净额的绝对值差距可达数倍。例如贵州茅台日成交额数百亿、北向净额可超 10 亿，而小盘股日成交仅几千万。相同的除数会导致大盘股资金面评分几乎恒定为 100，小盘股恒定为 50，失去区分度。

建议：按个股近 N 日平均成交额做标准化（例如 `net_flow / avg_turnover * 100`），或至少使用分位数归一化。

---

### H2 — `get_current_user` 异常处理不完整

**File**: `deps.py:70`

```python
{"uid": int(user_id)},
```

如果 JWT payload 的 `sub` 字段不是可转换整数（例如被篡改为字符串 "abc"），`int(user_id)` 会抛出 `ValueError`，导致 500 Internal Server Error 而非 401 Unauthorized。应捕获 `ValueError` 并返回 401。

```python
try:
    uid = int(user_id)
except (ValueError, TypeError):
    raise HTTPException(status_code=401, detail="Invalid token payload")
```

---

### M1 — 技术面因子评分器异常吞噬过度

**File**: `diagnosis_engine.py:163-195`

每个因子 runner 的异常被静默吞噬并返回默认值 `{"score": 5.0}`。当 Kronos factors 包更新后某个 scorer 签名变化导致 `TypeError`，诊断不会报错而是静默给出中性评分，掩盖了集成破损。

建议：对 `ImportError`（包未安装）静默降级，对其他异常至少 `logger.warning` 并记录异常类型。

---

### M2 — `math` import 位置不当

**File**: `routes.py:574`

```python
import math  # line 574 — at the bottom of the file
```

`math` 是标准库，应在文件顶部导入。`history` 端点（line 563）使用了 `math.ceil` 但 `math` 在 line 574 才导入。运行时会因为 Python 的 import 机制在函数调用前已解析全部顶层 import 而不会报错，但不符合 PEP 8。

---

### M3 — `_score_to_grade` 与 `_score_to_recommendation` 阈值不对齐

**File**: `diagnosis_engine.py:87-112`

| 分数 | Letter Grade | Recommendation |
|------|-------------|----------------|
| 82 | A | 买入 |
| 76 | B+ | 买入 |
| 66 | B | 持有 |
| 56 | C+ | 持有 |
| 46 | C | 持有 |
| 36 | D | 减仓 |

字母等级的内部阈值与操作建议阈值不一致。这不是功能 bug（二者的语义不同），但用户在 UI 上看到"A 级评分"对应"买入"（而非"强烈买入"）可能感到困惑。建议统一或至少在 PRD/ADR 中定义字母等级映射。

---

### M4 — `analysis_history` 写入失败被静默忽略

**File**: `routes.py:111-131`

```python
try:
    await db.execute(...)
    await db.commit()
except Exception as e:
    logger.warning("Failed to persist diagnosis history: %s", e)
    await db.rollback()
```

诊断成功但历史记录写入失败时客户端收不到任何提示。应在 `DiagnosisReport` 中添加一个 `history_saved: bool` 字段，或至少在 response header 中标记。

---

### M5 — 基本面 fallback 查询被注释掉

**File**: `diagnosis_engine.py:417-425`

`daily_basic` 表 fallback 查询实际上被执行了，但逻辑正确。然而 fallback 分支使用了硬编码默认值（`pe_percentile = 50.0`、`roe = 10.0` 等），这些值没有标注来源且可能与实际偏差较大。建议至少从 `daily_basic` 中提取 `pe_ttm` 并做粗略映射。

---

### L1 — routes.py `GET /report/{code}` 返回类型不精确

**File**: `routes.py:281-282`

```python
report_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
return report_data  # returns dict, but response_model says DiagnosisReport
```

FastAPI 会自动将 dict 转换为 `DiagnosisReport`，但 JSON 反序列化后的 datetime 字符串不会自动转为 `datetime` 对象，`created_at` 字段可能返回字符串而非 ISO 格式。建议显式构造 `DiagnosisReport(**report_data)`。

---

### L2 — 缺少 `main.py` / Dockerfile 的代码未纳入本次审查范围

根据 ADR-005 后续工作清单，还缺少：
- Redis 客户端封装（`dependencies/redis.py`）
- APScheduler 预热任务
- `diagnosis_history` + `diagnosis_config` 表的 DDL 迁移脚本
- Playwright 容器配置

这些在 `services/diagnosis-service/` 中均未找到，属于尚未实现的依赖项。

---

## Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| Critical | 3 | C1 (Kronos cache absent), C2 (PDF no charts), C3 (Kronos auth missing) |
| High | 2 | H1 (magic number normalization), H2 (int(user_id) exception) |
| Medium | 4 | M1-M4 |
| Low | 2 | L1-L2 |

**Blockers for ship**: C1, C2 (if PDF is required), C3.
**Recommended before UAT**: H1 (score quality), M3 (grade alignment).
