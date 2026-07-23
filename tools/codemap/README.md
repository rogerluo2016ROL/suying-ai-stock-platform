# codemap — Deeply Understand

Python-native code understanding engine for AGF（[ADR-021](../../docs/adr/021-code-understanding-engine.md)，设计 [docs/design/deeply-understand/](../../docs/design/deeply-understand/)）。

## 开发

```bash
cd tools/codemap
uv sync                 # 装依赖（含 dev）
uv run pytest           # 跑测试
uv run codemap --help   # CLI（M1 后可用）
```

## 状态

- **已交付**：多语言 adapter（Python/TS/Java/SQL/YAML/JSON/SFC）+ SQLite 图谱 + 影响分析 + orphans + dashboard，120 单测全绿；设计档见 `docs/design/deeply-understand/`（实施 plan 已归档 untrack）
