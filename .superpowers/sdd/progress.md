# 五域优化实施台账

- 依据 PRD：`docs/prd/platform-five-domain-optimization-2026-07-10.md`
- 依据设计：`docs/superpowers/specs/2026-07-10-platform-five-domain-optimization-design.md`
- 依据计划：`docs/superpowers/plans/2026-07-10-platform-five-domain-optimization.md`
- 实施分支：`codex/platform-five-domain-optimization`
- 起始提交：`c9791e04f24c021d631e6e97f8cd04f6adf46682`
- 工作约束：每项任务均采用测试先行、独立任务审查、聚焦验证；交易能力默认仅纸面模式，未通过准入不得实盘。

## 基线

- 前端类型检查：基线命令无报错输出。
- 前端聚焦测试：26 通过、1 失败；失败为 `SupplyChainBom.test.tsx` 文案期望与现有页面不一致，纳入任务 1 修复。
- API 网关与数据服务聚焦测试：22 通过，1 条依赖弃用警告。

## 任务状态

| 任务 | 状态 | 开发提交 | 审查 | 验证 |
|---|---|---|---|---|
| 1. 恢复前端基线并移除 DataUpdate 固定演示回退 | 已完成 | `4f3bbd5f`, `03d8f1a2` | CLEAN | 24/24；typecheck 0 |
| 2. 移除 Screener 伪造 IC/相关性/分位收益 | 已完成 | `b9bf60a9`, `4ffccb7d`, `9c8aadfc` | CLEAN | 36/36；typecheck 0 |
| 3. 移除网关预览固定数字与伪 lineage | 已完成 | `f2c5d843`, `a9e527d6` | CLEAN（主控复核；代理快照不同步） | 9/9；preview scan clean |
| 4. 清除训练随机校准、默认指标与回测代理 | 已完成 | `cfe80532`, `9ebc074b`, `b5ebd74c`, `75d8ee74`, `498c2957` | CLEAN（审查问题已修复；独立服务审查） | training 2/2；backtest 2/2；py_compile；全量 training 36/1/1（既有缺文件） |
| 5. 移除固定 Kronos 50 并阻断 xtquant 实盘桩 | 已完成 | `d9bd3722`, `77e770fa`, `d6026c9d`, `f74ffba3` | CLEAN | trade 3/3；signal 14/15（既有日期断言）；py_compile |
| 6. 建立隔离服务测试运行器与 CI | 已完成 | `a190e4db`, `501fb1c`, `746711d4`, `360978e7` | CLEAN | runner 3/3；CI 依赖/矩阵审查通过 |
| 7. 修复数据路由与服务责任边界 | 已完成 | `f04fde4f`, `54690474`, `b290ae7d`, `430c1abd`, `ed8c0e57`, `74d07927` | 主控复核；待代理最终确认 | gateway 10/10；FE API 7/7；compose config；signal header |
| 8. 统一 liveness/readiness 和运行状态 | 已完成 | `6343391f`, `5e83e22d`, `5ac73901`, `be606630`, `f3cc7d39`, `92650fae`, `36c1e162` | CLEAN（最终审查） | contracts/gateway 4 passed；FE 11/11；typecheck；py_compile |
| 9. 拆分 data inventory/jobs/schedules/readiness 语义 | 已完成 | `71c0a954`, `97f17945` | 基本 CLEAN（低风险：schedules 为 jobs 投影） | data 2 passed；FE typecheck；py_compile |
| 10. 建立 profile 驱动的数据 readiness 快照 | 已完成 | `c139c056`, `b7a32859`, `1afc84c2` | 主控复核（data 2/2；gate 已接入） | data readiness 2/2；py_compile |
| 11. 建立数据库就绪性与数据新鲜度门禁 | 已完成 | `9d6525a4` | 主控复核 | ownership 2/2；CLI clean；CI gate |
| 12. 建立不可变模型运行 manifest 和正式时间线 | 已完成 | `257946ac`, `6de4d35` | 主控复核 | manifest 2/2；config/lint |
| 13. 建立可执行模型清单与版本清单 | 已完成 | `85847384` | 主控复核 | factor IC 2/2；py/lint |
| 14. 建立统一回测适配器与可复现证据 | 已完成 | `85847384` | 主控复核 | rank IC 2/2；adapter registry |
| 15. 建立模型准入和发布门禁 | 已完成 | `dc8961b7` | 主控复核 | admission 6/6；production manual gate |
| 16. 拆分 screener router 并把流水线改成受控 job | 已完成 | `1f5eb6b0` | 主控复核 | pipeline idempotency 1/1；py_compile |
| 17. 真实 API SIT、浏览器 UAT 和回滚演练 | 已完成 | `d4949112`, `f12b8109` | 主控复核 | smoke tests 15/15；paper-only/no-pick gate；UAT docs |

## Final Verification

- Frontend typecheck: pass.
- Frontend full Vitest suite: pass (existing jsdom pseudo-element warnings only).
- Frontend production build: pass; Vite emitted only chunk-size warnings for ECharts/AntD.
- Gateway tests: 12 passed.
- Model/ownership/smoke contract tests: 19 passed with `PYTHONPATH=packages/kronos-contracts`.
- Ownership CLI: clean.
- Paper-only policy remains enforced; live broker operations remain blocked.
- Known baseline failures: signal freshness test expects fixed 2026-06-21 and training suite references missing `Kronos/Kronos-uat-bak/src/kronos/finetune/dataset.py`; neither was masked or rewritten.

## 次要问题

- Starlette 仍有 1 条弃用警告，若未在对应服务任务中自然消除，则在最终收口阶段处理。
