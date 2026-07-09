# PRD — 复杂科技产业链证据模型

- **Date**: 2026-07-08
- **Owner**: product-lead
- **Status**: In Progress
- **Estimated effort tier**: Medium

## 1. Background

AI 算力产业链已经接入 `complex_tech` 8 层拆解模板。当前模板能展示层级、环节、公司和普通跟踪指标，但还不能把海外大厂 CAPEX、产业物理指标、宏观环境和现有证据链/预期差计算统一起来。

本功能把模板升级为“产业链层级 + 指标体系 + 证据链 + 预期差/启动信号”的结构。CAPEX 和产业物理指标必须挂到具体产业链层级，宏观环境只作为顶层外部环境，不直接生成买卖建议。

## 2. Goal & Non-Goals

**目标**:
- 每个 `complex_tech` 层级都有商业化阶段、预期差、启动信号三类指标。
- 海外大厂 CAPEX 和产业物理指标进入层级级别的 `evidence_chain`。
- 每层保留可追溯的 `expectation_gap.evidence_ids` 和 `trigger_signal.triggered_by_evidence_ids`。
- 顶层返回美国、中国、日本、韩国、欧洲宏观政策和通胀/通缩环境占位字段，缺数据时使用 `unknown`。

**Non-Goals**:
- 不做自动交易信号。
- 不接入新的实时海外数据源。
- 不自动判断通胀/通缩。
- 不改现有 business-tag 预期差计算公式。
- 不做数据库迁移。

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 产品经理 | 在每层看到 CAPEX 和产业物理证据 | 判断钱流向哪一层、哪一环节正在放量 |
| US-2 | 研究员 | 通过统一 evidence_chain 追溯证据 | 避免 CAPEX、物理指标和旧证据链割裂 |
| US-3 | 投研用户 | 看到预期差和启动信号的证据来源 | 判断结论是否有依据 |
| US-4 | QA | 看到 unknown 占位 | 确认系统没有编造宏观状态 |

## 4. Acceptance Criteria

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | 每个 `complex_tech` 层级返回 `metrics.commercialization`、`metrics.expectation_gap`、`metrics.trigger_signals` | 后端测试 |
| AC-2 | P0 | 每条 CAPEX 证据必须有 `mapped_layer_id`、`metric_usage`、`source_type`、`as_of_date` | 后端测试 |
| AC-3 | P0 | 每条产业物理指标必须有 `mapped_layer_id`、`mapped_segment`、`metric_usage`、`source_type` | 后端测试 |
| AC-4 | P0 | CAPEX 和产业物理指标进入层级 `evidence_chain` | 后端测试 |
| AC-5 | P0 | 每条 evidence 有 `evidence_type`、`impact_direction`、`confidence` | 后端测试 |
| AC-6 | P0 | 每层返回 `expectation_gap`，并通过 `evidence_ids` 关联证据 | 后端测试 |
| AC-7 | P0 | 每层返回 `trigger_signal`，并通过 `triggered_by_evidence_ids` 关联证据 | 后端测试 |
| AC-8 | P0 | 顶层 `macro_context` 覆盖 US、CN、JP、KR、EU，缺数据状态为 `unknown` | 后端测试 |
| AC-9 | P1 | 前端复杂科技卡片展示三类指标、CAPEX 证据、产业物理指标、证据链摘要 | 前端 typecheck + 手动查看 |
| AC-10 | P1 | 旧字段 `tracking_metrics` 继续返回 | 后端测试 |

## 5. Design

API 不新增路径，继续使用：

```text
GET /api/v1/screener/chain/deconstruct?theme_id=ai_compute&method=upstream_downstream&template=complex_tech
```

层级节点新增字段：

```json
{
  "metrics": {
    "commercialization": [],
    "expectation_gap": [],
    "trigger_signals": []
  },
  "capex_evidence": [],
  "physical_metrics": [],
  "evidence_chain": [],
  "expectation_gap": {
    "gap_direction": "unknown",
    "gap_strength": "unknown",
    "calculation_method": "existing_business_tag_formula_unavailable",
    "evidence_ids": []
  },
  "trigger_signal": {
    "signal_strength": "unknown",
    "triggered_by_evidence_ids": []
  }
}
```

顶层新增：

```json
{
  "macro_context": []
}
```

## 6. Technical Constraints

- 不新增依赖。
- 不做数据库迁移。
- 缺数据时使用 `unknown`，不能硬编码成事实判断。
- 保留 `tracking_metrics`，避免旧前端和旧测试破坏。
- 复用现有预期差口径：`actual_progress - market_expectation + evidence_delta*0.35 - risk_penalty*0.45`。

## 7. Cost Estimate

- LLM token / 月：0，本次不接 LLM。
- Agent Team 开发 token：Medium。
- 数据维护成本：第一版人工结构化维护。

## 8. Out of Scope / Future Work

- 自动采集 SEC/IR/央行数据。
- 自动计算真实 CAPEX 预期差。
- 接入行情触发提醒。
- 将指标纳入个股买卖建议。

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | CAPEX 第一版覆盖哪些海外大厂 | product-lead | 2026-07-09 | 建议先覆盖 Microsoft、Google、Meta、Amazon、NVIDIA、TSMC、Samsung、SK Hynix、ASML |
| Q-2 | 产业物理指标是否允许人工录入 null 值 | product-lead | 2026-07-09 | 建议允许，用 `unknown` 和来源字段约束 |

## 10. Sign-offs

- [ ] product-lead: 初稿
- [ ] backend-dev: 接口可行性确认
- [ ] frontend-dev: 展示可行性确认
- [ ] qa-engineer: AC 可测性确认

## Changelog

- 2026-07-08: 初稿并进入实施。
