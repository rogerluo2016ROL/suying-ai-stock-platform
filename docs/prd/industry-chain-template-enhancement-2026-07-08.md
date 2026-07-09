# PRD - 大葱产业链解构模型：行业链路模板增强

- **Date**: 2026-07-08
- **Owner**: product-lead
- **Status**: In Progress
- **Estimated effort tier**: Medium

## 1. Background

现有“大葱产业链解构模型”已经有通用 L1-L8 框架和供应链 BOM 工作台，但复杂科技产业不能只用普通上中下游解释。AI 算力报告给出的链路是从大模型需求传导到芯片、封装、HBM、服务器、网络、液冷、IDC 和商业变现，适合作为复杂科技产业的链路模板。

本次增强保留原 L1-L8 总框架，不替换现有 BOM 语义，只新增“行业链路模板”能力。首个模板为 `complex_tech`。

## 2. Goal & Non-Goals

**目标**:
- 在原大葱模型中新增“行业链路模板”能力。
- 首个模板为 `complex_tech`：需求层 -> 任务层 -> 核心产品层 -> 底层支撑层 -> 集成层 -> 配套层 -> 基础设施层 -> 商业变现层。
- 输出必须支持产业链层级、技术路线、价值量/瓶颈线索、客户订单线索、股票映射、验证指标。

**Non-Goals**:
- 不替换原 L1-L8 架构。
- 不重做供应链 BOM V4。
- 不自动生成买卖建议。
- 不把券商报告观点当成实时市场事实。
- 不新增 LLM 自动抽取能力。

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 产品经理 | 选择产业类型模板 | 不同产业能用不同拆解逻辑 |
| US-2 | 研究用户 | 用 AI 算力模板拆产业链 | 看到从需求到 IDC/应用的传导路径 |
| US-3 | 研究用户 | 每层看到公司、证据和跟踪指标 | 判断哪个环节值得继续跟踪 |
| US-4 | 研究用户 | 看到模板与原 L1-L8 的边界 | 避免把通用框架和行业模板混在一起 |

## 4. Acceptance Criteria

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1 | P0 | `/screener/chain/deconstruct` 支持 `template=complex_tech` 参数，返回 8 层链路树 | API test |
| AC-2 | P0 | 原 `method=upstream_downstream` 结果不变 | regression test |
| AC-3 | P0 | `complex_tech` 返回需求、任务、核心产品、底层支撑、集成、配套、基础设施、商业变现 8 层 | unit test |
| AC-4 | P0 | 每层支持 `definition`、`key_questions`、`segments`、`evidence`、`companies`、`tracking_metrics` 字段 | response assertion |
| AC-5 | P1 | 前端工作台可切换“通用层级/复杂科技链路” | frontend manual smoke |
| AC-6 | P1 | AI 算力模板展示来源性质，不把报告样例伪装成实时事实 | copy review |
| AC-7 | P1 | 候选股映射继续使用现有候选池和证据链，不新建重复表 | code review |
| AC-8 | P2 | 后续可扩展 `resource_cycle`、`platform_ecosystem`、`traditional_manufacturing` 模板 | config design review |

## 5. Design

新增配置文件：

```text
packages/kronos-factors/configs/industry_chain_templates.json
```

新增 API 参数：

```text
GET /api/v1/screener/chain/deconstruct?theme_id=future_industry_core&method=upstream_downstream&template=complex_tech
```

响应新增：

```json
{
  "view": "complex_tech",
  "template": {
    "template_id": "complex_tech",
    "name": "复杂科技产业链路模板"
  },
  "tree": {
    "node_id": "template:complex_tech",
    "children": []
  }
}
```

前端在现有产业链工作台新增模板切换控件：

```text
通用层级 / 复杂科技
```

## 6. Technical Constraints

- 保持 `/supply-chain/layers`、`/supply-chain/bom`、`/chain/deconstruct` 旧参数兼容。
- 模板使用本地 JSON 配置，不引入数据库迁移。
- 不新增 LLM 依赖。
- 使用现有 Ant Design 工作台，不新建独立大页面。
- 验证优先使用 `tools/codex-lowio.sh`。

## 7. Cost Estimate

- LLM token/月：0，首版不接 LLM 自动抽取。
- Agent 开发 token：Medium。
- 主要成本：后端配置/类型/API、前端模板切换、测试。

## 8. Out of Scope / Future Work

- 自动从任意 PDF 抽取产业链模板。
- 模板后台管理。
- 多模板智能选择。
- 实时估值或买卖建议。

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | 后续是否增加资源周期、平台生态、传统制造模板 | product-lead | 2026-07-15 | 首版仅 complex_tech |
| Q-2 | 是否把 PDF 报告全文导入来源库 | product-lead | 2026-07-15 | 首版只沉淀模板，不导入全文 |

## 10. Sign-offs

- [x] product-lead: 方向确认
- [ ] tech-lead: 技术方案确认
- [ ] backend-dev: API/配置可行性确认
- [ ] frontend-dev: 工作台改造确认
- [ ] qa-engineer: AC 可测性确认

## Changelog

- 2026-07-08: 初稿，按用户确认方向开始实施。
