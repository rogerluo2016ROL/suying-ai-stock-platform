# Design: <change 名>

<!--
单 change 的技术「怎么做」。**薄、可省**——简单 change 可删本文件。
分层边界：design.md 管这一个 change 的技术方案；耐久的跨 feature 架构决策走 ADR。
高风险 change（auth / schema migration / LLM 切换 / cross-cutting）：本文件**引用一个新 ADR**
（由 tech-lead 写），不在这里自拍架构。
-->

## 技术方案

- 实现路径：1–3 段说明怎么实现（组件、数据流、关键取舍）。
- API 契约（如涉及前后端）：列新增/变更接口签名（path / request / response / error code）；契约 SSOT 仍是 OpenAPI（[ADR-006](../../adr/006-frontend-backend-contract-sync.md)）。
- 数据模型（如涉及）：列新增/变更表结构（字段、类型、索引、迁移）。

## 关联 ADR（高风险时必填）

- ADR-NNN: <若本 change 含架构风险，此处引用 tech-lead 新起的 ADR>
