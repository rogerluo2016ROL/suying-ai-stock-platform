# 大葱产业链 BOM 解构选股模型：A/B/C 三阶段专家工作台重构设计

## 1. 设计结论

当前“产业链拆解”页面不应继续以“主题表 + 图谱 + 候选公司表”的方式修补。这个模型的产品目标不是展示产业目录，而是提供一套可审计的产业链投研推理系统：

```text
国家政策与战略任务
→ 未来产业方向
→ BOM 级产业链拆解
→ 高增长 / 高利润 / 高围墙 / 卡脖子环节
→ 上市公司产品与材料映射
→ 商业化阶段与证据
→ 政策、量产、订单、业绩、市场共振
→ 候选公司评分、评级、排序、交易研究信号
```

因此，A/B/C 三个方案应合并为三阶段递进式架构：

| 阶段 | 目标 | 交付物 |
|---|---|---|
| A | 把现有页面救成可用专家工作台 | 节点联动公司池、研究卡、评分拆解、商业阶段、共振展示 |
| B | 重构后端领域模型与 API | 统一 BOM 图谱、公司映射、证据、评分、共振快照 |
| C | 升级为知识图谱 + LLM 自动投研系统 | 自动阅读政策/公告/研报/专利/招投标/产能信息，并进入人工审核流 |

核心原则：A 阶段可以复用现有数据，但页面必须按 B 阶段目标设计；B 阶段必须为 C 阶段预留证据、置信度、审核和版本化；C 阶段不得绕过人工审核直接改写正式图谱。

## 2. 业务专家视角

A 股产业链主题投资的关键不是“某家公司属于某行业”，而是它是否处于国家战略支持、产业升级、国产替代、商业化放量与资本市场确认的交汇点。

本模型的选股理念应明确为：

1. A 股牛市常承接政策任务与产业升级任务，政策不是装饰字段，而是一级约束。
2. 产业方向来自十五五、未来产业、新质生产力、科技自立自强、现代化产业体系。
3. 选股不能停留在行业关键词，必须用 BOM 方法拆到产品、材料、设备、工艺和供应关系。
4. 候选公司不是“属于某行业”，而是“卡在某个 BOM 节点，并有证据证明产品、订单、产能、客户或财务兑现”。
5. 商业化阶段决定投资节奏。预研、中试、小批量、量产爬坡、规模推广、业绩兑现对应不同信号。
6. 启动窗口来自政策、商业化、业绩、市场四类共振，而不是单一分数。

## 3. 领域模型

### 3.1 核心实体

| 实体 | 含义 | 关键字段 |
|---|---|---|
| `PolicyTheme` | 政策主题 | `theme_id`, `name`, `source_level`, `policy_weight`, `keywords`, `source_refs` |
| `IndustryDirection` | 产业方向 | `direction_id`, `theme_id`, `name`, `strategic_priority`, `expected_window` |
| `BomNode` | BOM 节点 | `node_id`, `direction_id`, `parent_node_id`, `level`, `node_type`, `name`, `bom_path`, `criticality` |
| `CompanyBomMapping` | 公司到 BOM 节点映射 | `mapping_id`, `code`, `node_id`, `product_name`, `material_name`, `equipment_name`, `process_name`, `confidence`, `status` |
| `Evidence` | 证据 | `evidence_id`, `source_type`, `source_id`, `code`, `node_id`, `summary`, `excerpt`, `published_at`, `confidence`, `status` |
| `CommercializationEvent` | 商业化事件 | `event_id`, `code`, `node_id`, `stage`, `event_type`, `event_date`, `evidence_id` |
| `ScoreSnapshot` | 评分快照 | `score_id`, `trade_date`, `code`, `node_id`, `total_score`, `dimension_scores`, `rating`, `rank` |
| `ResonanceSnapshot` | 共振快照 | `resonance_id`, `trade_date`, `code`, `node_id`, `policy`, `commercialization`, `performance`, `market`, `summary` |
| `ResearchSignal` | 研究信号 | `signal_id`, `trade_date`, `code`, `node_id`, `signal`, `reason`, `risk_flags` |
| `ManualOverride` | 人工覆盖 | `override_id`, `target_type`, `target_id`, `before`, `after`, `operator`, `created_at` |

### 3.2 关系

```text
PolicyTheme
  → IndustryDirection
    → BomNode
      → CompanyBomMapping
        → Evidence
        → CommercializationEvent
        → ScoreSnapshot
        → ResonanceSnapshot
        → ResearchSignal
```

业务解释：

- `PolicyTheme` 回答“国家鼓励什么”。
- `BomNode` 回答“产业链怎么拆，哪个环节关键”。
- `CompanyBomMapping` 回答“哪家公司卡在哪个产品/材料/设备/工艺节点”。
- `Evidence` 回答“凭什么这么说”。
- `CommercializationEvent` 回答“产品处于什么阶段”。
- `ScoreSnapshot` 和 `ResonanceSnapshot` 回答“是否值得进入候选池以及是否临近启动”。

## 4. BOM 拆解模型

BOM 不能只到“AI 算力、机器人、创新药”这种链级口径，必须至少支持 6 层：

```text
政策主题
  产业方向
    上游 / 中游 / 下游
      环节
        产品 / 材料 / 设备 / 工艺
          上市公司
```

示例：具身智能

```text
未来产业主攻方向
  具身智能
    上游
      稀土永磁材料
      高精密轴承材料
      高性能传感材料
    中游
      减速器
        谐波减速器
        RV减速器
      伺服系统
        伺服电机
        伺服驱动器
      控制器
        运动控制器
        主控芯片
      传感器
        力矩传感器
        视觉传感器
    下游
      工业机器人
      人形机器人
      医疗康复机器人
      特种机器人
```

每个 BOM 节点必须包含：

| 字段 | 说明 |
|---|---|
| `criticality` | 节点关键度，表示是否决定产业链性能或成本 |
| `chokepoint_level` | 卡脖子强度，表示进口替代和自主可控紧迫性 |
| `profit_pool` | 利润池吸引力 |
| `growth_elasticity` | 产业增长弹性 |
| `moat_requirement` | 护城河要求，如专利、客户认证、工艺壁垒 |
| `commercialization_stage` | 节点整体商业化阶段 |
| `candidate_count` | 映射上市公司数量 |

## 5. 阶段 A：现有页面专家化

### 5.1 目标

在不推倒现有数据库的前提下，把当前前端从“数据表页面”改成“节点驱动的专家投研工作台”。A 阶段解决用户最直观的不满：公司在哪里，为什么入选，怎么评分，处于什么商业阶段，是否共振。

### 5.2 后端最小改造

新增或增强一个工作台聚合接口：

```text
GET /api/v1/screener/supply-chain/workbench?theme_id=&node_id=&top_n=30
```

`theme_id` 和 `node_id` 为可选参数。传入 `node_id` 时，返回值中的 `selected_node_thesis` 和 `node_candidate_companies` 必须只对应该节点。

返回：

```json
{
  "model": {
    "name": "大葱产业链解构选股模型 V4",
    "philosophy": "政策主题定方向，BOM 拆解定环节，证据链定公司，商业化和共振定启动窗口",
    "score_dimensions": [
      {"key": "policy", "name": "政策力度", "weight": 15},
      {"key": "bom", "name": "BOM关键度", "weight": 15},
      {"key": "commercialization", "name": "商业化阶段", "weight": 15}
    ]
  },
  "policy_themes": [
    {"theme_id": "future_industry_core", "name": "未来产业主攻方向", "policy_weight": 1.5}
  ],
  "bom_tree": [
    {
      "key": "future_industry_core",
      "title": "未来产业主攻方向",
      "children": [
        {"key": "embodied_ai_reducer", "title": "具身智能 / 中游 / 减速器"}
      ]
    }
  ],
  "graph_nodes": [
    {"node_id": "embodied_ai_reducer", "name": "减速器", "candidate_count": 4, "commercialization_stage": "量产爬坡"}
  ],
  "graph_edges": [
    {"from_node_id": "embodied_ai_core", "to_node_id": "embodied_ai_reducer", "relation": "中游核心零部件"}
  ],
  "selected_node_thesis": {
    "node_id": "embodied_ai_reducer",
    "thesis": "减速器决定机器人运动精度、寿命和成本，是具身智能核心零部件。"
  },
  "node_candidate_companies": [
    {
      "code": "688017",
      "name": "绿的谐波",
      "product_name": "谐波减速器",
      "commercialization_stage": "量产爬坡",
      "score": 78.5
    }
  ],
  "evidence_summary": {
    "approved": 12,
    "pending_review": 5,
    "low_confidence": 2
  },
  "resonance_model": {
    "dimensions": ["policy", "commercialization", "order_capacity", "performance", "market"]
  }
}
```

A 阶段允许从现有 `supply_chain` picks 兜底，但必须在服务层完成“候选股 → BOM 节点”的投影，前端不负责猜。

### 5.3 前端信息架构

页面布局：

```text
顶部：研究结论总览
  政策主题、模型版本、候选公司数、强共振公司数、风险公司数

左侧：BOM 树
  政策主题 → 产业方向 → 上中下游 → 环节 → 产品/材料/设备/工艺

中间：产业链图谱
  节点大小 = 候选公司数
  节点颜色 = 商业化阶段
  节点边框 = 卡脖子强度

右侧：节点研究卡
  节点为什么重要
  政策依据
  关键产品/材料/设备
  爆发触发条件
  主要风险

下方：当前节点候选公司池
  只显示当前节点相关公司

公司详情：研究报告式详情
  BOM路径、产品映射、入选理由、评分拆解、商业阶段时间线、证据、风险
```

### 5.4 A 阶段验收

- 打开页面第一屏能看到 BOM 树、产业链图谱、节点研究卡、候选公司池。
- 点击任意 BOM 节点，下方公司池随节点过滤。
- 公司池每行必须展示：公司、产品/材料、商业阶段、周期位置、评分、评级、交易研究信号、入选理由。
- 点击公司后必须看到：BOM 路径、产品/材料映射、财务指标、评分拆解、护城河证据、共振判断、风险。
- 当节点无公司映射时，页面必须明确显示“该节点缺少公司映射证据”，不能把全局公司池混进来。

## 6. 阶段 B：后端领域模型重构

### 6.1 目标

B 阶段解决架构问题：让 BOM、公司映射、证据、评分、商业阶段、共振和研究信号来自同一套领域模型，而不是多个接口拼接。

### 6.2 服务分层

| 层 | 模块 | 责任 |
|---|---|---|
| Repository | `supply_chain_repository.py` | 读取主题、节点、映射、证据、评分、共振 |
| Domain Service | `supply_chain_workbench_service.py` | 组装节点 thesis、候选池、研究卡 |
| Scoring Service | `supply_chain_scoring_service.py` | 计算评分、评级、排名 |
| Resonance Service | `supply_chain_resonance_service.py` | 计算政策、商业化、业绩、市场共振 |
| Evidence Service | `supply_chain_evidence_service.py` | 聚合公告、研报、互动问答、财报、外部证据 |
| API Router | `supply_chain_router.py` | 输出稳定 API 契约 |

现有 `services/screener-service/app/routers/screener.py` 已经过大，B 阶段应拆出独立 router 和 service，避免继续在一个文件里堆业务逻辑。

### 6.3 API 契约

```text
GET /api/v1/screener/supply-chain/workbench
GET /api/v1/screener/supply-chain/tree
GET /api/v1/screener/supply-chain/graph
GET /api/v1/screener/supply-chain/node/{node_id}/thesis
GET /api/v1/screener/supply-chain/node/{node_id}/companies
GET /api/v1/screener/supply-chain/company/{code}/research-card
GET /api/v1/screener/supply-chain/scoring-model
GET /api/v1/screener/supply-chain/resonance-model
POST /api/v1/screener/supply-chain/manual-overrides
```

### 6.4 `node/{node_id}/thesis`

返回节点研究逻辑：

```json
{
  "node_id": "embodied_ai_reducer",
  "name": "减速器",
  "bom_path": ["未来产业主攻方向", "具身智能", "中游", "核心零部件", "减速器"],
  "thesis": "减速器决定机器人运动精度、寿命和成本，是具身智能核心零部件。",
  "policy_basis": ["未来产业主攻方向", "新质生产力", "首台套推广应用"],
  "criticality": 92,
  "chokepoint_level": "高",
  "profit_pool": "中高",
  "growth_elasticity": "高",
  "commercialization_stage": "量产爬坡",
  "trigger_conditions": ["人形机器人订单放量", "国产减速器客户认证突破", "毛利率稳定"],
  "risk_factors": ["客户验证周期长", "价格竞争", "良率波动"]
}
```

### 6.5 `node/{node_id}/companies`

返回当前节点候选公司，不返回全局公司池：

```json
{
  "node_id": "embodied_ai_reducer",
  "companies": [
    {
      "code": "688017",
      "name": "绿的谐波",
      "product_name": "谐波减速器",
      "material_name": "高精密齿轮材料",
      "commercialization_stage": "量产爬坡",
      "commercialization_evidence": "公告披露已进入客户小批量供货",
      "selection_reason": "公司映射到具身智能减速器节点，具备客户验证和量产推进证据。",
      "score": 78.5,
      "rating": "A",
      "trade_signal": "关注",
      "resonance": {
        "policy": "强",
        "commercialization": "量产放量",
        "performance": "待兑现",
        "market": "观察跟踪",
        "summary": "政策与商业化共振，等待业绩确认"
      }
    }
  ]
}
```

### 6.6 `company/{code}/research-card`

返回公司研究卡：

```json
{
  "code": "300308",
  "name": "中际旭创",
  "research_title": "AI 算力高速光模块核心供应商",
  "bom_paths": [
    ["新质生产力", "AI算力", "中游", "硬件", "高速光模块"]
  ],
  "product_mappings": [
    {
      "node_id": "ai_compute_optical_module",
      "product_name": "高速光模块",
      "confidence": 0.86,
      "evidence_ids": ["ev_001"]
    }
  ],
  "selection_reason": "公司处于 AI 算力高速光模块关键节点，商业化阶段为规模推广，收入利润高增长。",
  "commercialization_timeline": [
    {"stage": "小批量验证", "date": "2023-01-01", "evidence_id": "ev_001"},
    {"stage": "规模推广", "date": "2025-01-01", "evidence_id": "ev_002"}
  ],
  "financial_indicators": {
    "revenue_growth": 192.1,
    "profit_growth": 571.8,
    "roe": 17.5,
    "gross_margin": 46.1
  },
  "score": {
    "total": 82.5,
    "dimension_scores": {
      "policy": 12.0,
      "bom": 14.0,
      "chokepoint": 12.0,
      "commercialization": 14.0,
      "growth": 15.0,
      "profit": 8.0,
      "moat": 5.0,
      "market": 2.5
    }
  },
  "resonance": {
    "policy": "强",
    "commercialization": "规模推广",
    "order_capacity": "客户验证",
    "performance": "高增长",
    "market": "观察跟踪",
    "summary": "政策、商业化、订单、业绩四维共振，等待市场确认"
  },
  "moat_evidence": [
    {"evidence_id": "ev_003", "summary": "券商研报认定其为高速光模块核心供应商", "confidence": 0.82}
  ],
  "risk_flags": [
    {"risk_type": "customer_concentration", "summary": "海外云厂商需求波动会影响订单节奏"}
  ]
}
```

## 7. 阶段 C：知识图谱 + LLM 自动投研

### 7.1 目标

C 阶段让系统从“人工维护产业链图谱”升级为“LLM 自动抽取 + 人工审核 + 图谱增量更新”。LLM 不直接给投资结论，只生成结构化候选事实。

### 7.2 数据源

| 数据源 | 作用 | 优先级 |
|---|---|---|
| 政策文本 | 政策主题、产业方向、政策强度 | P0 |
| Tushare `anns_d` | 公告、订单、产能、客户、产品进展 | P0 |
| Tushare `research_report` | 券商覆盖、护城河、行业观点 | P0 |
| Tushare `irm_qa_sh/sz` | 互动问答中的产品、产能、客户 | P1 |
| Tushare 财务接口 | 收入、利润、毛利率、ROE、现金流 | P0 |
| 专利数据 | 技术壁垒、专利数量、核心专利 | P1 |
| 招投标数据 | 订单落地、客户验证 | P1 |
| 产能投产公告 | 量产阶段、产能释放 | P0 |

### 7.3 LLM 抽取流程

```text
文本源入库
→ 规则过滤：政策/公告/研报是否命中产业关键词
→ LLM 抽取：主题、节点、公司、产品、材料、商业阶段、证据
→ 结构化校验：字段、股票代码、节点候选、置信度
→ 写入 pending_review
→ 人工审核
→ approved 后进入正式图谱和评分
```

### 7.4 审核工作台

审核台必须支持：

- 查看 LLM 抽取的公司-BOM 映射。
- 查看证据原文片段、来源、日期、置信度。
- 修改节点、产品、材料、商业阶段。
- 批准、驳回、合并重复证据。
- 记录操作者和时间。

### 7.5 C 阶段验收

- 粘贴一篇公司公告，系统能抽取公司、产品、BOM 节点、商业阶段和证据摘要。
- 抽取结果默认进入待审核状态。
- 审核批准后，节点公司池出现对应公司。
- 公司研究卡出现该证据，并影响商业阶段或评分。
- 无 LLM key 或外部数据失败时，主模型正常运行，页面显示数据源降级状态。

## 8. 评分模型

### 8.1 总分

| 维度 | 权重 | 说明 |
|---|---:|---|
| 政策力度 | 15 | 政策层级、政策频次、是否命中十五五/未来产业/新质生产力 |
| BOM 关键度 | 15 | 是否决定性能、成本、供应安全或标准 |
| 卡脖子/国产替代 | 15 | 进口依赖、国产替代空间、供应稀缺度 |
| 商业化阶段 | 15 | 预研、中试、小批量、量产爬坡、规模推广、业绩兑现 |
| 业绩成长 | 15 | 营收、利润、业绩预告、主营构成 |
| 盈利质量 | 10 | 毛利率、ROE、现金流、费用率 |
| 护城河证据 | 10 | 专利、客户认证、产能、工艺、券商覆盖 |
| 市场共振 | 5 | 板块强度、趋势、资金、龙虎榜、北向 |
| 风险扣分 | -20 | 监管、伦理、减持、质押、业绩恶化、证据不足 |

### 8.2 评级

| 评级 | 分数 | 含义 |
|---|---:|---|
| S | >= 85 | 政策、节点、商业化、业绩、市场多维共振 |
| A | 75-84 | 产业地位明确，商业化或业绩进入强验证 |
| B | 65-74 | 候选观察，等待更强证据 |
| C | 50-64 | 相关但证据不足 |
| D | < 50 | 剔除或风险回避 |

### 8.3 交易研究信号

| 信号 | 条件 |
|---|---|
| 观察 | B 级以上，但商业化或市场确认不足 |
| 关注 | A 级以上，政策、BOM、商业化至少两项强 |
| 启动 | A 级以上，商业化和业绩出现确认，市场开始转强 |
| 强启动 | S 级，政策、商业化、业绩、市场四维共振 |
| 风险回避 | 风险扣分高、证据置信度低、财务恶化或事件风险 |

交易信号只用于研究排序，不触发自动下单。

## 9. 商业阶段模型

| 阶段 | 定义 | 典型证据 | 投资意义 |
|---|---|---|---|
| 预研验证 | 技术方向明确，但未形成稳定样品 | 政策、立项、研发投入、专利 | 主题观察 |
| 中试 | 样品或试验线验证 | 中试线、样品送样、客户验证 | 早期布局 |
| 小批量验证 | 小批量交付或客户试用 | 小批量订单、试生产、客户导入 | 重点跟踪 |
| 量产爬坡 | 产线投产，产能释放 | 产能公告、订单放量、良率提升 | 启动窗口 |
| 规模推广 | 多客户、多场景规模化应用 | 收入增长、客户扩张、产能扩建 | 主升观察 |
| 业绩兑现 | 利润确认，主营占比提升 | 利润增长、毛利稳定、主营构成提升 | 强趋势与风险并存 |
| 成熟 | 增速放缓，竞争稳定 | 增长回落、价格竞争 | 估值修复或退出 |

商业阶段必须由证据支持。没有证据时只能标记为“待验证”，不能凭行业印象升级。

## 10. 共振模型

共振不是一句文案，而是 5 个独立维度：

| 维度 | 判断 |
|---|---|
| 政策共振 | 近期政策主题强化，且政策层级足够高 |
| 商业化共振 | 从预研/中试进入小批量、量产或规模推广 |
| 订单产能共振 | 招投标、订单、客户、产能投产出现证据 |
| 业绩共振 | 收入、利润、毛利率、ROE 或主营占比改善 |
| 市场共振 | 板块强度、趋势、资金、量价结构确认 |

输出：

```json
{
  "policy": "强",
  "commercialization": "量产放量",
  "order_capacity": "订单验证",
  "performance": "高增长",
  "market": "观察跟踪",
  "summary": "政策、商业化、订单、业绩四维共振，等待市场确认"
}
```

## 11. 前端设计规范

### 11.1 页面目标

页面必须让研究员在 30 秒内回答：

1. 国家政策鼓励哪个方向？
2. 产业链如何层层拆解？
3. 哪些节点高增长、高利润、高围墙、卡脖子？
4. 哪些上市公司卡在节点上？
5. 公司为什么入选？
6. 公司处于什么商业阶段？
7. 政策、商业化、订单、业绩、市场是否共振？

### 11.2 视觉结构

```text
┌──────────────────────────────────────────────────────┐
│ 顶部研究条：政策主题 / 当前节点 / 候选数 / 强共振数       │
├──────────────┬─────────────────────┬─────────────────┤
│ BOM 树        │ 产业链结构图          │ 节点研究卡        │
│ 政策→产品→公司│ 节点关键度/阶段/公司数 │ thesis/触发/风险   │
├──────────────┴─────────────────────┴─────────────────┤
│ 当前节点候选公司池                                      │
│ 公司 / 产品 / 阶段 / 评分 / 共振 / 入选理由 / 证据数量    │
├──────────────────────────────────────────────────────┤
│ 公司研究卡 / 证据时间线 / 评分拆解 / 风险扣分             │
└──────────────────────────────────────────────────────┘
```

### 11.3 交互规则

- 点击政策主题：刷新 BOM 树、图谱和节点矩阵。
- 点击 BOM 节点：右侧显示节点 thesis，下方公司池只显示该节点公司。
- 点击公司：打开研究卡，不是普通字段抽屉。
- 点击证据：显示来源、时间、摘要、原文片段、置信度。
- 切换商业阶段筛选：公司池按预研、中试、小批量、量产爬坡、规模推广、业绩兑现过滤。
- 切换共振筛选：公司池按政策、商业化、订单产能、业绩、市场共振过滤。

### 11.4 前端组件拆分

| 组件 | 责任 |
|---|---|
| `SupplyChainWorkbench` | 页面容器、数据加载、布局 |
| `BomTreePanel` | BOM 层级树与节点选择 |
| `IndustryGraphPanel` | 产业链图谱 |
| `NodeThesisPanel` | 当前节点研究卡 |
| `CandidateCompanyTable` | 当前节点候选公司池 |
| `CompanyResearchCard` | 公司研究报告式详情 |
| `EvidenceTimeline` | 证据时间线 |
| `ScoringBreakdown` | 多维评分拆解 |
| `ResonanceBadgeGroup` | 共振状态展示 |
| `EvidenceReviewPanel` | C 阶段审核台 |

## 12. 数据质量与降级

| 情况 | 降级方式 |
|---|---|
| 节点无公司映射 | 显示“缺少公司映射证据”，不混入全局公司池 |
| 公司无商业阶段证据 | 标记“待验证”，商业化分不得高于基础分 |
| 公司无财务数据 | 财务维度显示缺失，评分置信度下降 |
| LLM 不可用 | 抽取功能禁用，主模型继续运行 |
| 外部专利/招投标不可用 | 对应证据源显示缺失，不阻断主链路 |
| 证据置信度低 | 进入 pending_review，不作为强证据 |

## 13. UAT 验收标准

### 13.1 A 阶段验收

- 页面第一屏包含 BOM 树、产业链图谱、节点研究卡、当前节点公司池。
- 点击“具身智能 → 减速器”后，公司池只显示减速器相关公司。
- 公司行展示产品/材料、商业阶段、周期位置、评分、评级、信号、入选理由。
- 公司研究卡展示财务指标、评分拆解、护城河证据、共振判断、风险。
- 节点没有公司映射时，页面显示明确空态。

### 13.2 B 阶段验收

- `node/{node_id}/companies` 返回的公司都带证据来源或映射置信度。
- `company/{code}/research-card` 能反查 BOM 路径、产品映射、商业阶段事件、评分和共振。
- 评分结果能解释每个维度来源。
- 商业阶段不得在没有证据时升级。
- 历史回测按 `trade_date` 截止，不能读取未来公告、研报、财务或交易数据。

### 13.3 C 阶段验收

- 粘贴政策或公告文本后，LLM 能抽取主题、节点、公司、产品、材料、商业阶段、证据摘要。
- 抽取结果默认进入待审核。
- 审核通过后，公司出现在对应 BOM 节点公司池。
- 审核驳回后，不影响正式图谱和评分。
- LLM 或外部数据源失败时，页面显示降级状态，主模型正常运行。

## 14. 实施顺序

### Phase A：专家工作台可用化

1. 扩展 `/workbench`，支持 `theme_id`、`node_id`、`top_n`。
2. 增加 `selected_node_thesis` 和 `node_candidate_companies`。
3. 前端拆出 `BomTreePanel`、`NodeThesisPanel`、`CandidateCompanyTable`、`CompanyResearchCard`。
4. 让公司池随节点联动，不再展示全局混合池。
5. 补浏览器 UAT 截图和组件测试。

### Phase B：领域模型重构

1. 拆分 screener router 中 supply-chain 逻辑。
2. 建立 repository/service/router 三层。
3. 扩展数据表或物化视图支持 company-node-evidence-score-resonance 统一查询。
4. 建立 `research-card` 与 `node thesis` API。
5. 建立评分和共振快照。

### Phase C：自动投研图谱

1. 建立文本源入库与去重。
2. 接入 LLM 抽取 pipeline。
3. 建立证据审核台。
4. 接入专利、招投标、产能投产外部适配器。
5. 审核通过后增量更新图谱、商业阶段和评分。

## 15. 不做什么

- 不把交易研究信号接入自动下单。
- 不让 LLM 直接给最终评分或最终投资结论。
- 不在缺证据时强行给公司高商业化阶段。
- 不继续把所有 supply-chain 逻辑堆在一个 router 文件里。
- 不把全局候选池伪装成某个 BOM 节点候选池。

## 16. 成功判定

这个重构成功的标准不是“页面有多少字段”，而是用户能沿着一条清晰证据链完成判断：

```text
我为什么看这个产业？
这个产业哪个节点关键？
这个节点有哪些产品/材料/设备？
哪些上市公司真实卡位？
证据是什么？
商业化到了哪一步？
政策、订单、业绩、市场是否共振？
为什么给这个评分、评级和研究信号？
```

只有当这条链条在前端可见、在后端可追溯、在测试里可验证，才算达到专家级产业链解构选股模型。
