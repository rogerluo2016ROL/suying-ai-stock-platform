---
description: Deeply Understand (codemap) 入口 — 代码图谱 / 变更影响分析 / 理解地图（ADR-021，替换 agf-understand）。在 tools/codemap/ 跑 codemap CLI
argument-hint: <build|update|diff|explain|onboard|understand|context|search|dashboard> [args...]
---

# /agf-code-map

Deeply Understand / codemap（ADR-021）入口。在 `tools/codemap/` 跑对应子命令：

```bash
cd tools/codemap && uv run codemap $ARGUMENTS
```

## 子命令速查

- `build [path]` 全量建图 → `.agf/code-map.db`
- `update` 增量（git diff）
- `diff [--base main] [--out <path>]` 变更影响（→ code review 清单；--out 落 JSON 报告）
- `explain <file|node>` 深度解释
- `onboard [--out <path>]` 新人/接手指南
- `understand [topic] [--out <path>]` 理解地图（PRD/ADR 前现状，接管 agf-understand）
- `context "<query>"` 相关子图（给 agent 注入）
- `search "<query>"` 检索（FTS5；跑过 `embed` 后自动启用 semantic 余弦，三态降级）
- `embed` 生成 embedding（需 `uv sync --extra semantic`，jina-code-v2 ~90MB；未装则 search 降级 FTS）
- `dashboard` 静态 HTML 图（`open .agf/dashboard.html`）

## 边界

- 产物 `.agf/*` gitignored；消费层报告 `understand/onboard/diff --out docs/reviews/<slug>-{onboard,understand,diff}-<date>.md`（不加 `--out` 走 stdout；understand/onboard 落 markdown，diff 落结构化 JSON）
- 事实层，不碰 specs/adr/design SSOT；不投票 verdict（详见 skill）
