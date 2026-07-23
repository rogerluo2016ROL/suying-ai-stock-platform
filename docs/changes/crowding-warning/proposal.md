# Proposal: 拥挤度→回撤预警模型

- **Date**: 2026-07-20
- **Owner**: product-lead
- **Status**: In Progress（v1 代码完成, 待样本外验证 + 归档）
- **Estimated effort tier**: Medium
- **交付 lane**: fast（因子/预警层, 不涉交易资金风险）

## Why（背景 + 痛点）

项目现有"拥挤"逻辑分散在 4 处、口径不一:`leader_afternoon`(涨停拥挤-8/放量拥挤-4)、`leader_closing`(板块过热 peer_n≥30→-18)、`leader_intraday`(回撤保护仅 `print` 不报警)、`screening_scorers`(20日涨>50%超买-2)。无统一拥挤度因子, 也无"拥挤→回撤"的预警闭环。

需要: ① 统一拥挤度因子; ② 选股结果直接标注拥挤度; ③ 盘后扫描高拥挤并推飞书; ④ 样本外验证"预警后是否真回撤"。

## What（范围）

**做**: 统一拥挤度因子(6 成分时序滚动分位) + 选股 `/run` 响应标注 `crowding_level` + `alert-service /crowding-scan` 批量扫描推送 + 回测脚本(预警后回撤命中率, 对齐 walk_forward M01 时序纪律)。

**Non-Goals**: 不做指数级拥挤(科创50 指数历史/ETF 数据缺失); 不做北向个股维度(2024-08 交易所停止披露); 不做权重 IC 最优化(v2 按 OOS 校准); 不做实盘交易联动。

## 影响的能力

| Capability | 活规格 | 本次 delta |
|---|---|---|
| screening | `docs/specs/screening/spec.md` | `specs/screening.md` |

## Open Questions

| ID | 问题 | Owner | Due |
|---|---|---|---|
| Q-1 | 拥挤度权重需按 walk_forward OOS (IC + 分组方向) 校准, v1 等权 | ml-engineer | 2026-08 |
| Q-2 | 数据管道: PG 数据到 2026-07-16, 需确认是否持续更新（SQLite 停在 06-24） | data-eng | 2026-07-30 |
| Q-3 | 实盘启用前需 commit 策略文件跑 OOS（M01-C dirty 拦截已验证生效） | tech-lead | 2026-08 |
| Q-4 | 是否为新信号范式(时序滚动分位 + 回撤事件评估) 新开 ADR | tech-lead | 2026-08 |
