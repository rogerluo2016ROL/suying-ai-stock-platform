# 大葱产业链解构模型数据底座优化设计

日期: 2026-06-25
状态: 待用户复核
范围: 大葱产业链解构选股模型的数据底座，不包含实盘交易、不包含前端大改版、不做量化训练。

## 背景

当前大葱产业链解构模型已经具备可运行主干：

- 后端模型 `SupplyChainEngine` 可返回 Top30 选股结果。
- `supply_chain` 模式已注册到 screener-service。
- 前端已有 `/supply-chain-bom` 工作台入口。
- 研报、财务、券商覆盖、股票画像等基础表可用。

主要问题在数据底座：

- `company_chain_mapping` 为空，缺少公司到产业链节点的正式映射。
- `supply_chain_bom_edges` 为空，图谱节点没有上下游边。
- `supply_chain_bom_nodes` 只有 5 个节点，主要覆盖具身智能/机器人，不能支撑“全部产业链”。
- `supply_chain_scores` 只有 19 条，偏小样本。
- 引擎 metadata 仍标记 `bom_model_version=4.0`，而工作台展示偏 V5，版本口径不一致。

## 目标

把模型从“可运行的主题粗筛”升级为“全产业链可解释数据底座”：

1. 覆盖现有配置中的 10 条产业链。
2. 为每条产业链生成可视化可下钻的 BOM 节点和边。
3. 建立公司到 BOM 节点、公司到产业链节点的映射。
4. 为每条映射保留置信度、状态和证据缺口。
5. 让模型优先使用真实映射，缺失时再回退到行业关键词粗筛。
6. 输出数据完整度报告，方便后续持续补齐。

## 第一版覆盖范围

以 `packages/kronos-factors/configs/supply_chains.json` 为单一配置来源，首批覆盖：

| 产业链 | 首批节点方向 |
|---|---|
| 半导体 | 材料、设备、制造、封测、设计 |
| 新能源 | 材料、光伏、电池、设备 |
| AI算力 | 硬件、软件、应用 |
| 机器人 | 核心部件、整机、集成 |
| 创新药 | CXO、原料药、创新药 |
| 新能源车 | 材料、电池、零部件、整车 |
| 消费升级 | 品牌、渠道 |
| 国防军工 | 主机厂、分系统、元器件、材料 |
| 高端制造 | 核心部件、整机、集成 |
| 周期资源 | 资源、冶炼、加工 |

具身智能已有的 5 个 BOM 节点继续保留，并纳入机器人链条下的细分节点。

## 数据模型

### BOM 节点

写入 `supply_chain_bom_nodes`：

- `node_id`: 稳定 ID，例如 `semiconductor_materials`
- `theme_id`: 默认 `future_industry_core`，后续可扩展为政策主题
- `chain_id`: 产业链英文或拼音稳定标识
- `parent_node_id`: 上级链条节点
- `level`: `chain`、`layer`、`component`
- `name`: 中文节点名
- `node_type`: `industry`、`layer`、`component`
- `keywords`: 用于候选公司匹配
- `policy_weight`: 默认继承政策主题权重

### 边关系

写入 `supply_chain_bom_edges`：

- 链条根节点指向层级节点。
- 上游节点指向中游节点，中游节点指向下游节点。
- 机器人/具身智能等已有细分 BOM 节点挂在对应层级下。

边关系只表达产业逻辑，不表达投资建议。

### 公司映射

写入 `company_bom_mapping` 和 `company_chain_mapping`：

- `company_bom_mapping` 表示公司与具体 BOM/层级节点的产品关系。
- `company_chain_mapping` 表示公司在产业链中的投资映射关系。
- 映射来源优先级：
  1. `stock_profiles.main_business`
  2. `stock_profiles.introduction`
  3. `research_reports_tushare.title`
  4. `stocks.industry`
  5. 现有 `company_bom_mapping`

置信度分层：

| 置信度 | 条件 |
|---:|---|
| 0.85-1.00 | 主营或简介命中强关键词，且行业匹配 |
| 0.65-0.84 | 主营/简介命中关键词，但行业较宽 |
| 0.45-0.64 | 研报标题命中，主营未明确 |
| 0.30-0.44 | 仅行业粗匹配 |

状态规则：

| 状态 | 含义 |
|---|---|
| `verified` | 主营/简介强证据，且节点明确 |
| `pending_review` | 有关键词证据但仍需人工复核 |
| `weak_evidence` | 只有行业或弱文本证据 |

### 证据缺口

每条低置信度映射生成 `evidence_gaps`，常见缺口包括：

- 是否有明确客户或供应链认证。
- 是否有量产、扩产、订单或定点公告。
- 该产品收入占比是否足够高。
- 是否存在国产替代或卡脖子稀缺性证据。
- 是否只是概念相关，还是已经商业化兑现。

## 模型联动

`SupplyChainEngine` 的候选池生成逻辑调整为三段：

1. 优先读取 `company_chain_mapping` 和 `company_bom_mapping`。
2. 映射不足时使用 `supply_chains.json` 的行业和关键词生成候选。
3. 对回退生成的候选打上 `mapping_source=fallback_keyword`，避免和强证据候选混在一起。

排序仍保留原有五维：

- moat
- growth
- profit
- rating
- consensus

新增展示/解释字段：

- `chain_id`
- `node_id`
- `node_name`
- `mapping_confidence`
- `mapping_status`
- `evidence_gaps`
- `mapping_source`

## 产出

新增一个数据补齐工具：

`tools/build_supply_chain_foundation.py`

建议参数：

- `--dry-run`: 只输出报告，不写库。
- `--persist`: 写入 PG。
- `--chains`: 指定链条，默认全部。
- `--min-confidence`: 写入阈值，默认 0.30。
- `--report-path`: 输出完整度报告。

输出报告：

`outputs/supply_chain_foundation_report.json`

报告字段：

- 每条链节点数。
- 每条链边数。
- 每条链候选公司数。
- verified / pending_review / weak_evidence 数量。
- 映射 Top 公司样例。
- 无候选节点清单。
- 数据缺口摘要。

## 验收标准

| 指标 | 目标 |
|---|---:|
| 覆盖产业链 | 10 条 |
| BOM 节点 | >= 35 |
| BOM 边关系 | >= 30 |
| 公司 BOM 映射 | >= 150 |
| 公司产业链映射 | >= 150 |
| 每条链候选公司 | >= 10 |
| 数据完整度报告 | 必须生成 |
| 模型 Top30 | 必须包含节点、置信度、证据状态 |
| 回归测试 | supply-chain 相关后端测试通过 |

## 测试方案

1. 单元测试：
   - 节点生成稳定。
   - 边关系无孤儿节点。
   - 公司映射置信度规则正确。
   - dry-run 不写库。

2. 数据集成测试：
   - `--persist` 后关键表数量增加。
   - `company_chain_mapping` 不再为空。
   - `supply_chain_bom_edges` 不再为空。
   - 工作台接口能读到节点、边、候选。

3. 模型回归：
   - `SupplyChainEngine.run(top_n=30)` 正常返回。
   - Top30 中每个结果至少带链条和映射状态。
   - 没有映射的数据仍可通过 fallback 生成，但必须显式标记。

## 风险和边界

- 关键词映射会产生误判，第一版必须保留 `pending_review` 和 `weak_evidence`。
- 不在本阶段引入 LLM 自动抽取，避免依赖外部 key 和不可控输出。
- 不把所有低置信度映射视为卡脖子供应商。
- 不改实盘交易、不改自动交易策略、不触碰资金相关逻辑。
- 不一次性追求“全网事实完备”，先把本地可持续更新的骨架搭起来。

## 推荐实施顺序

1. 做 dry-run 工具，生成全链节点、边和映射报告。
2. 人工检查报告中的 Top 样例和明显误判。
3. 加 persist 写库能力。
4. 调整 `SupplyChainEngine` 优先使用映射表。
5. 补接口和前端展示字段。
6. 跑测试和模型输出验证。

## 自检结果

- 无待定字段。
- 范围聚焦在数据底座，不包含 UI 大改和实盘逻辑。
- 第一版验收指标可度量。
- 低置信度映射有状态隔离，避免把弱证据当作强结论。
