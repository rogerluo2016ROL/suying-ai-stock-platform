---
tester: Codex
stage: UAT
report_verdict: Conditional
uat_signoff_verdict: Pending
p0_pass2_total: 6
p0_pass2_ok: 6
critical_defect_count: 0
warning_count: 2
---

# QA Report — 产业链研究与选股模型 V2 — UAT

- **Date**: 2026-07-11
- **Stage**: UAT（本地真实数据库技术验收，不等同于投资有效性验收）
- **Tester**: Codex
- **Branch**: `codex/supply-chain-selection-v2`
- **Code baseline**: `2377dc35f1d481c33f09afc45829abd16077b77c`
- **Environment**: 本地 PostgreSQL `localhost:6432/kronos`
- **Database migration**: `031 -> 032 (head)`
- **Evidence/score date**: `2026-07-09`
- **Evidence cutoff**: `2026-07-09 23:59:59.999999 Asia/Shanghai`
- **Design**: `docs/superpowers/specs/2026-07-11-industry-chain-research-selection-v2-design.md`
- **Approved implementation plan**: `docs/superpowers/plans/2026-07-11-industry-chain-research-selection-v2.md`
- **Separate code-review report**: 未生成；本报告不据此宣称可合并或可升生产
- **UI rendering check**: N/A；本次没有新增前端页面，只验收数据库、脚本和 API

## Summary

- Total AC: 9
- Passed: 8
- Failed: 0
- Blocked: 1（样本外投资有效性）
- Focused tests: 174 passed，0 failed
- Open Critical/High defects: 0
- **Verdict**: **CONDITIONAL PASS**

[COMPUTED] 数据结构、物化、评分、四池门禁、API、模型注册、幂等性和无前视回测降级均按设计工作。模型有效性没有通过：当前只有一个评分日，全部候选都处于 `E1 / D / watch`，A/B/C 正式快照为 0，且评分日之后尚无 T+1 行情。因此模型必须保持 `staging`，不得升级为 `production`，也不能宣称已经找到有效股票。

## Pre-conditions Checked

- [x] 174 项聚焦单元/契约/回归测试通过。
- [x] 设计文档与实施计划可访问，且用户已在当前任务中明确确认并授权实施。
- [x] PostgreSQL 可用；迁移已从 `031` 应用到 `032`。
- [x] 精确交易日已固定为 `2026-07-09`，未使用模糊的“今天”。
- [x] V2 写入前全局旧快照重复组为 695，V2 重复组为 0；迁移未清理其他模型数据。
- [!] 没有独立 `uat-cases` 文档；本次以用户确认的实施计划 Task 9 作为用例 SSOT。这是流程偏差，所以报告不作正式发布签字。
- [!] 没有独立 code-review/SIT Audit 报告；需在合并或发布前补做。

## AC Results

### AC-1 (P0): 迁移只新增 V2 结构，不破坏既有快照

- **Setup**: 数据库 `alembic_version=031`；全局历史快照重复组 695；V2 重复组 0。
- **Action**: 执行 `alembic upgrade head`，再查 `alembic current`、10 张 V2 表和部分唯一索引。
- **Expected**: 单一 head `032`；10 张表存在；仅 V2 使用专属唯一索引；其他模型历史重复不被修改。
- **Actual (run 1)**: `[COMPUTED] Running upgrade 031 -> 032` 成功。
- **Actual (run 2)**: `[COMPUTED] 032 (head)`；10/10 表存在；`uq_screening_snapshots_supply_chain_v2=1`；V2 重复组仍为 0。
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: ✅ Pass

### AC-2 (P0): 灵巧手按八层 × 八横向维度物化

- **Setup**: 模板 `dexterous_hand`，日期 `2026-07-09`。
- **Action**: dry-run 后真实运行物化脚本，并幂等重跑。
- **Expected**: 8 个层级节点、64 条节点维度、6 条技术路线、4 条传导边、8 条节点分数；未知值保持 `NULL/unknown`。
- **Actual (run 1)**: `[COMPUTED] nodes=8, dimensions=64, routes=6, edges=4, node_scores=8`。
- **Actual (run 2)**: `[COMPUTED] 重跑后数量不增长；同日仍为 8/64/6/4/8`。
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: ✅ Pass

### AC-3 (P0): 候选映射、证据门禁和四池不越级

- **Setup**: 物化生成 6 个业务映射，对应 5 只归一化股票。
- **Action**: 先 dry-run，再真实评分并幂等重跑；查询证据等级、资格和分池。
- **Expected**: 弱证据不能进入 A/B/C；缺失分数保持 `NULL`；重复运行不重复记录池迁移。
- **Actual (run 1)**: `[COMPUTED] 6 个映射全部为 E1 / D / watch；5 只股票；可计算 opportunity_score=0；首次 transitions=6`。
- **Actual (run 2)**: `[COMPUTED] 仍为 D=6，written=6，transitions=0`。
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: ✅ Pass

### AC-4 (P1): 轴向磁通电机按 AF0-AF6 反例门禁，不因概念表述晋级

- **Setup**: 模板定义 AF0-AF6：AF0 不入池，AF1 最高 D，AF2-AF3 最高 C，AF4 最高 B，AF5-AF6 才可能进入 A。
- **Action**: 查询 `dexterous_axial_flux_motor` 物化记录及验证字段。
- **Expected**: 无机器人规格产品、装机、温升和转矩强证据时保持概念/待复核，不晋级。
- **Actual (run 1)**: `[COMPUTED] maturity_stage=concept，review_status=pending_review，evidence_ids=[]，last_strong_evidence_date=NULL`；持续/峰值转矩、温升、直径、厚度均为 `NULL`，installed_prototype=false，installation_position=unknown。
- **Framework interpretation**: `[FRAME]` 按本模型 AF 阶梯，该记录对应 AF0；这是模型内部状态，不是对现实技术成熟度的事实判断。
- **Reliability**: `pass^1 = 1/1`
- **Verdict**: ✅ Pass

### AC-5 (P1): API 返回主映射、完整解释且批量接口默认只试算

- **Setup**: V2 分数已落库。
- **Action**: 用真实数据库调用 candidates、`stocks/603662` 和 batch-score。
- **Expected**: 按股票去重；保留多业务映射；batch 默认 `dry_run=true`。
- **Actual (run 1)**: `[COMPUTED] 三个接口均 HTTP 200；候选为 5 只且全部 D；603662 返回 2 个 mapping 和 2 条迁移记录；5 个未知 stock_score 均为 NULL；batch dry_run=true、mapping_count=6`。
- **Reliability**: `pass^1 = 1/1`
- **Verdict**: ✅ Pass

### AC-6 (P0): V2 以 staging 注册，快照幂等且 V1 不受影响

- **Setup**: 注册前 V1 注册记录 1、V1 快照 6；V2 注册 0、快照 0。
- **Action**: dry-run、真实注册、再次真实注册；查询三张注册表和快照重复。
- **Expected**: `model_type=screener`、`stage=staging`；只写 A/B/C；胜率和收益为空；V1 不变。
- **Actual (run 1)**: `[COMPUTED] V2 registry=1，stage=staging，snapshot_count=0，win_rate=NULL，mean_return=NULL`。
- **Actual (run 2)**: `[COMPUTED] 再次注册仍为 1 条版本记录、0 条快照、0 组 V2 重复；V1 仍为 1 条注册、6 条快照`。
- **Reliability**: `pass^2 = 2/2`
- **Verdict**: ✅ Pass

### AC-7 (P0): 回测严格使用 T+1、复权和真实不足语义

- **Setup**: 回测口径为 `T+1 open to future adjusted close, 14.0 bps cost`；缺任一端复权因子必须排除。
- **Action**: 执行 T+3/T+5/T+10/T+20；每个周期运行 7 个完整候选集消融并写 `factor_evaluations`。
- **Expected**: 不用信号日收盘成交；不以 `adj_factor=1` 填空；有样本时计算沪深300同期基准与超额收益；样本不足时不生成胜率、Sharpe、收益和上线建议。
- **Actual (run 1-4)**: `[COMPUTED] 四个周期 snapshot_rows=0、return_rows=0，均为 INSUFFICIENT_EVIDENCE`。
- **Actual (ablation)**: `[COMPUTED] 7 个变体 × 4 个周期=28 条独立评估；状态全部为 INSUFFICIENT_EVIDENCE；V1 因缺完整冻结历史候选分数明确拒绝推断`。
- **Reliability**: `pass^4 = 4/4`
- **Verdict**: ✅ Pass（回测机制与诚实降级通过，不代表模型收益有效）

### AC-8 (P1): 旧接口、V1 和训练服务契约保持兼容

- **Setup**: 在修复混合代码格式后，以独立 pytest 进程运行各服务测试。
- **Action**: 运行迁移、评分、模板、工具、API、回测、训练契约和旧产业链接口回归。
- **Expected**: 全部通过；训练服务可解析 `screener`，但不能把它创建为可训练模型；缺真实指标时不得补固定数值。
- **Actual (run 1)**: `[COMPUTED] 174 passed，0 failed`；仅有 TestClient 弃用和本地开发密钥回退警告。
- **Reliability**: `pass^1 = 1/1`
- **Verdict**: ✅ Pass

### AC-9 (P1): 新模型投资有效性达到可发布证据门槛

- **Setup**: 最低门槛为 20 个评分日、100 条真实复权收益观测，并需要 A/B/C 正式候选。
- **Action**: 检查注册快照、四周期回测和七项消融。
- **Expected**: 有足够样本时才能计算并比较收益、胜率、回撤和超额收益。
- **Actual**: `[COMPUTED] 评分日 1 个；A/B/C 快照 0；可用收益观测 0；所有回测和消融均为 INSUFFICIENT_EVIDENCE`。
- **Reliability**: N/A（尚未达到可测条件）
- **Verdict**: ⚠️ Blocked；不得升级 production，不得形成正式买入池

## Database Evidence

### V2 表行数

| 表 | 行数 |
|---|---:|
| `supply_chain_node_dimensions` | 64 |
| `supply_chain_transmission_edges` | 4 |
| `supply_chain_technology_routes` | 6 |
| `supply_chain_node_scores` | 8 |
| `business_tag_authenticity_scores` | 6 |
| `business_tag_operating_quality_scores` | 6 |
| `business_tag_benefit_scores` | 6 |
| `business_tag_selection_scores` | 6 |
| `business_tag_pool_state` | 6 |
| `business_tag_pool_transition_log` | 6 |

### 分池与快照

| 指标 | 结果 |
|---|---:|
| 灵巧手业务映射 | 6 |
| 归一化股票 | 5 |
| A 池 | 0 |
| B 池 | 0 |
| C 池 | 0 |
| D 池 | 6 mappings / 5 stocks |
| 排除 | 0 |
| V2 正式快照 | 0 |
| V2 快照重复组 | 0 |
| V2 消融评估 | 28 |
| V2 production 记录 | 0 |

## Defects Found

| ID | Severity | Status | Title | Repro steps | Suspected file |
|---|---|---|---|---|---|
| DEF-1 | High | Resolved in `a6e3afcd` | `603662` 与 `603662.SH` 被派生为两个股票代码 | 1. 真实物化；2. 查询 `business_tag_mapping WHERE chain_id='dexterous_hand'`；3. 观察同一股票混合格式 | `tools/materialize_supply_chain_research_v2.py` |
| DEF-2 | Medium | Resolved in `6a03cf20` | 未知 benefit 被聚合成 `stock_score=0` | 1. 查询 D 池 API；2. 观察 benefit_score=NULL；3. 旧聚合结果 stock_score=0 | `packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py` |
| DEF-3 | Medium | Resolved in `2377dc35` | 未知候选总分写快照时被兜底成 0 | 1. 构造 C 池 score=NULL；2. 调用快照写入；3. 检查 total_score | `tools/register_supply_chain_research_selection_v2.py` |
| DEF-4 | High | Resolved in `2377dc35` | 负数最大回撤的优劣方向相反 | 1. 比较 -0.10 与 -0.20；2. 旧逻辑把 -0.10 判为不更好 | `services/training-service/app/routes.py` |
| DEF-5 | Medium | Resolved in `2377dc35` | benchmark/excess 字段永久返回不足 | 1. 提供有效股票收益和同期指数价格；2. 旧报告仍无基准收益 | `services/backtest-service/app/adapters/supply_chain_selection_v2.py` |

修复后数据库为 5 只股票、6 个业务映射；`603662` 的两个业务标签由 API 聚合到同一只股票；未知股票总分保持 `NULL`。代码格式修复只更新 `status=candidate` 的派生行，不覆盖 verified/approved 映射或人工证据。

## Known Limitations

1. 当前没有 A/B/C 正式候选，四个股票池只是机制已建立，尚无可执行选股清单。
2. 当前只有 `2026-07-09` 一个评分截面，且这是行情最新日，没有 T+1 后续价格。
3. AF0-AF6 阶梯定义保存在模板配置中；数据库路线表保存当前成熟阶段、验证字段和证据，不逐行复制七级定义。
4. 派生候选只保留来源映射 ID，不复制原证据；当前 E1 代表只有业务存在映射，不能当作订单、收入或客户验证。
5. 全局旧快照仍有 695 组重复；本任务只加 V2 部分唯一索引，未改写其他模型历史。
6. pytest 必须按服务隔离运行；把多个顶层 `app/tests` 包放进同一 pytest 进程会发生收集冲突。
7. TestClient 有 Starlette 弃用警告；本地训练服务有开发密钥回退警告，均未影响本次断言，但发布前应清理。

## Cross-stage Notes

- 下一阶段先积累至少 20 个独立评分日和 100 条 T+1 可执行复权收益观测。
- 只有经人工审核的强证据才能把映射从 D 推进到 C/B/A。
- 满足样本门槛后重跑 T+3/T+5/T+10/T+20 和七项消融，再决定 V2 是否优于 V1。
- 在 code review、SIT Audit 和正式 UAT case 签字补齐前，不建议合并到生产发布链。

## Cost (this QA session)

- Tokens consumed: UNKNOWN（当前运行环境未暴露会话 token 计数，未伪造）
- Estimated cost: UNKNOWN（缺少 token/计价证据）
- 同 feature 累计: UNKNOWN

## Hand-off

**CONDITIONAL PASS**：允许把 V2 作为 `staging` 研究模型继续积累证据；不允许转 `production`，不允许输出正式买入建议。

Product Lead sign-off：Pending。
