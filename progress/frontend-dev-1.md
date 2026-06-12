## T-204: auto-trading frontend 修复 - 2026-06-12 16:30
**状态**: 已完成
**Skills**: agf-running-sit-tests

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:
- [x] AC-204.1 ✅ API path: 全部 `/api/v1/strategy/*`，vite.config.ts proxy 已覆盖 strategy→8003
- [x] AC-204.2 ✅ request body 字段对齐: Condition(field/operator/threshold/description)，position_rules 嵌套，risk_rules 嵌套对象
- [x] AC-204.3 ✅ status enum: running→active, terminated→stopped, completed→archived, 追加 draft/archived
- [x] AC-204.4 ✅ form 补充: trade_mode(paper/live), check_interval_sec, capital, picks + Form.List
- [x] AC-204.5 ✅ log 字段: action→message, detail→details, time→timestamp
- [x] AC-204.6 ✅ npx tsc -b --noEmit: 0 errors
- [x] AC-204.7 ✅ npm run build: success (3681 modules, 3.28s)

**质量门**: lint ✅ / typecheck ✅ / build ✅ / SIT ✅（all AC pass）

**下一步**: 等待 product-lead review / 无阻塞
