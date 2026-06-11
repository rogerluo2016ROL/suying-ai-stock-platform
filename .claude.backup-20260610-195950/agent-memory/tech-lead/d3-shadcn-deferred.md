---
name: d3-shadcn-deferred
description: shadcn/ui v4 暂缓至 Phase B，目前沿用自建组件库
metadata:
  type: project
---

shadcn/ui v4 技术方向受认同，但 product-lead 于 2026-06-08 review ADR-005 时决定暂缓至 Phase B。

**Why:** T-001（Design Token）+ T-002（13 组件 + 68 tests）已完成，T-005（布局重构）已在进行中。此时 pivot 到 shadcn/ui 会废弃 T-002 全部产出 + T-005 返工。

**How to apply:** Phase A 前端交付沿用现有自建组件栈。Phase A 交付后做 A/B 评估（自建组件 vs shadcn/ui v4 Accessibility/Keyboard Navigation），若 shadcn/ui 显著优于自建组件，Phase B 切换。

See also: [[dual-db-phase-a]]
