# PRD — 大葱产业链解构选股模型重构

- **Date**: 2026-06-24
- **Owner**: product-lead
- **Status**: Draft
- **Estimated effort tier**: Large

## 1. Background

### 现状问题
当前大葱产业解构选股模型（supply_chain_bom）仅覆盖**机器人/具身智能**单一产业的4个BOM节点（减速器/电机/轴承/控制器），存在以下痛点：

1. **产业覆盖窄**：无法扩展到14个政策产业（8战新+6未来）
2. **政策解读人工依赖**：产业重点方向的识别靠人工维护，无法动态响应新政策
3. **产业链拆解维度单一**：只有BOM节点拆解，缺少上下游/价值链/竞争格局三维度分析
4. **上市公司映射静态**：公司-节点映射固定在PG表，无法随产业演进动态更新
5. **商业化进程信号缺失**：现有评分体系缺少"产业周期+政策强度+业绩兑现"三因子共振判断

### 用户痛点
证券分析师/量化交易员需要：
- **快速解读新政策** → 识别产业机会窗口
- **深度解构产业链** → 找到价值链高利润环节
- **筛选卡脖子标的** → 找到国产替代突破口
- **判断启动时机** → 商业化进程三因子共振 = 爆发起点

### 业务驱动
- 提升选股模型的产业覆盖广度（从1个产业 → 14个产业）
- 提升政策响应速度（人工解读 → LLM自动解读）
- 提升选股精准度（单维度BOM → 三维度拆解 + 三因子共振）

---

## 2. Goal & Non-Goals

### 目标
**一句话目标**：构建LLM驱动的全产业链解构选股系统，实现"政策解读 → 产业链拆解 → 标的筛选 → 启动判断"全链路自动化。

### KPI
| 指标 | 基线 | 目标 |
|------|------|------|
| 产业覆盖数 | 1（机器人） | ≥8（覆盖战新产业） |
| 政策解读耗时 | 人工2-3天 | LLM <30秒 |
| 产业链节点数 | 4个BOM节点 | ≥100个拆解节点 |
| 样本外IC（test_h20） | +0.08~0.09 | ≥+0.10（全市场验证后） |

### Non-Goals
1. ❌ 不做实盘交易信号——本系统输出"研究信号"，不替代交易决策
2. ❌ 不做财务数据实时采集——沿用现有PG stocks/fina_indicator表
3. ❌ 不做多语言国际化——仅支持中文界面
4. ❌ 不做移动端适配——仅桌面端Web应用
5. ❌ 不做量化因子训练——本版本聚焦产业链解构，因子训练是后续迭代

---

## 3. User Stories

| ID | As a | I want to | So that |
|---|---|---|---|
| US-1 | 证券分析师 | 输入政策文章/地址，系统自动解读出产业重点方向 | 快速响应新政策，不遗漏投资机会 |
| US-2 | 证券分析师 | 查看产业链上下游拆解树，找到原材料/零部件/制造环节 | 定位价值链高利润环节 |
| US-3 | 证券分析师 | 查看价值链拆解，看到每个环节的利润率/定价权 | 判断环节议价能力和投资价值 |
| US-4 | 证券分析师 | 查看竞争格局拆解，看到集中度/龙头份额/壁垒 | 判断环节护城河和龙头优势 |
| US-5 | 证券分析师 | 下钻拆解树到末端，看到映射的上市公司清单 | 定位可投资标的 |
| US-6 | 量化交易员 | 系统自动筛选高增长+高利润+高壁垒企业 | 快速获得候选池 |
| US-7 | 量化交易员 | 系统识别卡脖子级别企业，标注国产替代机会 | 找到政策支持+技术突破的突破点 |
| US-8 | 量化交易员 | 查看企业商业化进程（产业周期+政策强度+业绩兑现） | 判断爆发启动时机 |
| US-9 | 量化交易员 | 三因子共振时系统发出"强启动"信号 | 捕捉量产元年爆发点 |

---

## 4. Acceptance Criteria

### 板块1: 政策解读和产业链行业梳理

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-1.1 | P0 | 用户输入政策文章文本（≥500字）→ POST `/api/v1/policy/interpret` 返回200 + `{"themes": [{"theme_id": "...", "theme_name": "...", "key_directions": [...]}]}` | curl + 验响应体 |
| AC-1.2 | P0 | 用户输入政策文章URL → POST `/api/v1/policy/interpret-url` 返回200 + 自动抓取+解读结果 | curl + 验响应体 |
| AC-1.3 | P1 | 解读结果包含：产业主题、重点方向、关键词、政策强度评级（1-5星） | curl + 验响应体 |
| AC-1.4 | P2 | 解读结果自动关联`stocks.industry`行业清单，输出行业映射表 | curl + 验响应体 |
| AC-1.5 | P1 | 系统预置14个产业的重点方向-行业清单（参考《产业-重点方向-Tushare映射.md》）| PG表 `industry_theme_mapping` 初始化验证 |

### 板块2: 产业链解构

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-2.1 | P0 | 用户选择产业+重点方向 → GET `/api/v1/chain/deconstruct?theme_id=...` 返回上下游拆解树 | curl + 验响应体树结构 |
| AC-2.2 | P0 | 上下游拆解树包含5层：原材料 → 核心零部件 → 制造 → 渠道 → 终端应用 | 验JSON树节点层级 |
| AC-2.3 | P0 | 每个节点包含：节点ID、节点名称、上游节点列表、下游节点列表 | 验节点字段完整性 |
| AC-2.4 | P1 | 用户切换"价值链"视图 → 返回每个环节的附加值、利润率、定价权评分 | curl + 验value_chain字段 |
| AC-2.5 | P1 | 用户切换"竞争格局"视图 → 返回集中度、龙头份额、进入壁垒、替代威胁评分 | curl + 验competition字段 |
| AC-2.6 | P0 | 用户下钻到末端节点 → GET `/api/v1/chain/node/{node_id}/companies` 返回映射的上市公司清单 | curl + 验公司列表 |
| AC-2.7 | P0 | 公司映射包含：code、name、主营占比、政策匹配度、证据来源 | 验公司字段完整性 |
| AC-2.8 | P0 | 前端ECharts树图支持点击节点展开下钻，显示映射公司卡片 | E2E click → 验UI显示 |
| AC-2.9 | P1 | ECharts支持三种视图切换：上下游树、价值链桑基图、竞争格局气泡图 | E2E 视图切换 → 验图表渲染 |

### 板块3: 候选上市公司多维度分析

| ID | Priority | AC | Verification method |
|---|---|---|---|
| AC-3.1 | P0 | GET `/api/v1/chain/candidates?theme_id=...&filter=high_growth` 返回高增长企业（营收yoy≥30%或净利yoy≥50%）| curl + 验筛选条件 |
| AC-3.2 | P0 | GET `/api/v1/chain/candidates?theme_id=...&filter=chokepoint` 返回卡脖子级别企业（chokepoint_score≥15）| curl + 验筛选条件 |
| AC-3.3 | P0 | 每个候选企业包含：商业化进程三因子评分（产业周期、政策强度、业绩兑现）| 验three_factors字段 |
| AC-3.4 | P0 | 三因子评分算法：产业周期（概念/中试/量产/放量）× 政策强度（星级）× 业绩兑现（财务/预告）| 验评分逻辑单元测试 |
| AC-3.5 | P0 | 三因子全部达标 → `trade_signal = "强启动"`，输出爆发信号 | 验signal生成逻辑 |
| AC-3.6 | P1 | 前端候选列表支持按：总评分、chokepoint、商业化进程排序 | E2E 排序 → 验列表变化 |
| AC-3.7 | P1 | 前端候选卡片显示三因子雷达图 + 证据摘要 | E2E → 雷达图渲染验证 |
| AC-3.8 | P2 | 用户点击候选卡片 → 跳转个股诊断页（复用现有diagnosis-service）| E2E click → 验路由跳转 |

---

## 5. Design

### UI原型
- **位置**: `docs/design/supply-chain-reconstruct/`
- **主页面**: 产业链解构工作台（三视图Tab + 下钻树 + 候选列表）
- **关键组件**:
  1. 政策解读输入框（文本/URL两种输入）
  2. 产业选择下拉框（14产业）
  3. 三视图Tab：上下游树 / 价值链桑基图 / 竞争格局气泡图
  4. ECharts树图（点击节点下钻）
  5. 候选公司卡片列表（排序+筛选）
  6. 三因子雷达图

### API契约

#### 板块1: 政策解读
```
POST /api/v1/policy/interpret
Request: { "text": "政策文章全文", "context": "可选上下文" }
Response: {
  "themes": [{
    "theme_id": "semiconductor",
    "theme_name": "集成电路",
    "key_directions": ["先进封装", "存储芯片", "光刻胶"],
    "keywords": ["国产替代", "自主可控", "卡脖子"],
    "policy_intensity": 4,
    "related_industries": ["半导体", "元器件", "IT设备"]
  }],
  "model_used": "deepseek-chat",
  "tokens_used": 1500
}

POST /api/v1/policy/interpret-url
Request: { "url": "https://...", "extract_mode": "auto" }
Response: 同上 + { "source_title": "...", "source_domain": "..." }
```

#### 板块2: 产业链解构
```
GET /api/v1/chain/deconstruct?theme_id=semiconductor&view=upstream_downstream
Response: {
  "theme": { "id": "semiconductor", "name": "集成电路" },
  "view": "upstream_downstream",
  "tree": {
    "node_id": "root",
    "name": "集成电路",
    "children": [
      { "node_id": "raw_material", "name": "原材料", "layer": 1,
        "children": [{ "node_id": "silicon", "name": "硅片", ... }] },
      { "node_id": "component", "name": "核心零部件", "layer": 2, ... },
      { "node_id": "manufacture", "name": "制造", "layer": 3, ... },
      { "node_id": "channel", "name": "渠道", "layer": 4, ... },
      { "node_id": "terminal", "name": "终端应用", "layer": 5, ... }
    ]
  },
  "value_chain": {
    "raw_material": { "margin": 15, "pricing_power": 2, "value_added": 10 },
    "component": { "margin": 35, "pricing_power": 4, "value_added": 30 },
    ...
  },
  "competition": {
    "raw_material": { "concentration": 0.8, "leader_share": 0.6, "barrier": 5, "threat": 2 },
    ...
  }
}

GET /api/v1/chain/node/{node_id}/companies
Response: {
  "node_id": "silicon",
  "node_name": "硅片",
  "companies": [{
    "code": "600XXX",
    "name": "XX硅业",
    "main_pct": 45.5,
    "policy_match": 0.9,
    "chokepoint_score": 18,
    "evidence": ["互动问答提及国产替代", "研报标注首家量产"]
  }]
}
```

#### 板块3: 候选分析
```
GET /api/v1/chain/candidates?theme_id=semiconductor&filter=chokepoint
Response: {
  "theme": "集成电路",
  "filter": "chokepoint",
  "candidates": [{
    "code": "600XXX",
    "name": "XX公司",
    "total_score": 85,
    "chokepoint_score": 18,
    "three_factors": {
      "industry_cycle": { "stage": "量产", "score": 9 },
      "policy_intensity": { "stars": 4, "score": 12 },
      "performance_proof": { "status": "业绩兑现", "score": 10 }
    },
    "trade_signal": "强启动",
    "commercialization_note": "量产+政策4星+预增80%"
  }]
}
```

### 数据模型

#### 新增表
```sql
-- 产业主题表
CREATE TABLE industry_themes (
  theme_id VARCHAR(50) PRIMARY KEY,
  theme_name VARCHAR(100) NOT NULL,
  category VARCHAR(20), -- '战新' / '未来'
  key_directions JSONB,
  policy_intensity_stars INT DEFAULT 3,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- 产业链节点树
CREATE TABLE chain_nodes (
  node_id VARCHAR(100) PRIMARY KEY,
  theme_id VARCHAR(50) REFERENCES industry_themes(theme_id),
  node_name VARCHAR(100) NOT NULL,
  layer INT NOT NULL, -- 1-5层
  parent_node_id VARCHAR(100) REFERENCES chain_nodes(node_id),
  upstream_nodes JSONB,
  downstream_nodes JSONB,
  value_chain JSONB, -- {margin, pricing_power, value_added}
  competition JSONB, -- {concentration, leader_share, barrier, threat}
  created_at TIMESTAMP DEFAULT NOW()
);

-- 公司-节点映射
CREATE TABLE company_chain_mapping (
  id SERIAL PRIMARY KEY,
  code VARCHAR(10) NOT NULL REFERENCES stocks(code),
  node_id VARCHAR(100) REFERENCES chain_nodes(node_id),
  main_pct DECIMAL(5,2),
  policy_match_score DECIMAL(3,2),
  chokepoint_score INT,
  evidence JSONB,
  three_factors JSONB, -- {industry_cycle, policy_intensity, performance_proof}
  trade_signal VARCHAR(20),
  valid_from DATE,
  valid_to DATE,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_company_chain_node ON company_chain_mapping(node_id);
CREATE INDEX idx_company_chain_code ON company_chain_mapping(code);

-- 政策解读记录
CREATE TABLE policy_interpretations (
  id SERIAL PRIMARY KEY,
  source_type VARCHAR(20), -- 'text' / 'url'
  source_content TEXT,
  source_url VARCHAR(500),
  interpreted_themes JSONB,
  model_used VARCHAR(50),
  tokens_used INT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 6. Technical Constraints

### 必须遵守
- `.claude/standards/coding.md`: TypeScript strict mode / Python type hints
- `.claude/standards/security.md`: LLM API key 不落地，环境变量注入
- `.claude/standards/observability.md`: API调用日志 + LLM token计数

### LLM集成
- 使用 skill `agf-wiring-multi-llm-sdk` 集成 DeepSeek SDK
- 政策解读 prompt 模板化，输出JSON schema校验
- fallback链：DeepSeek → Doubao → Qwen（按cost-budget）

### 性能预算
- API P95 ≤ 500ms（不含LLM调用）
- LLM P95 ≤ 5s（政策解读）
- ECharts渲染 ≤ 2s（树节点≤500）

### 依赖约束
- 前端：ECharts 5.5（已有）
- 后端：复用现有screener-service框架
- 不引入新数据库依赖

---

## 7. Cost Estimate

### LLM Token预估
| 场景 | 单次token | 月调用量 | 月token |
|------|-----------|----------|---------|
| 政策解读 | ~2000 | 100次 | 200K |
| 产业链节点推理 | ~3000 | 50次 | 150K |
| **合计** | | | **350K tokens/月** |

### Agent Team开发token
- 预估：Large档（≥500K）
- 按cost-budget.md，触发**Large档**审批流程

---

## 8. Out of Scope / Future Work

### 不在本版本范围
1. 实盘交易信号集成（trade-service）
2. 多产业选股信号融合（跨产业相关性）
3. 量化因子训练（LightGBM/CatBoost）
4. 移动端适配
5. 多语言国际化

### 后续迭代方向
1. 全市场OOS验证（all_a cache跑通）
2. V5评分权重调优（IC分解）
3. IC衰减监测自动化
4. 实时政策监控（RSS订阅）

---

## 9. Open Questions

| ID | 问题 | Owner | Due | 备注 |
|---|---|---|---|---|
| Q-1 | LLM政策解读的prompt模板如何设计？需要输出哪些字段？ | ai-agent-dev | 2026-06-26 | 参考《产业-重点方向-Tushare映射.md》字段定义 |
| Q-2 | 产业链节点树的初始化数据从哪里来？人工维护 vs LLM自动生成？ | product-lead | 2026-06-25 | 建议先人工维护14产业基础树，后续LLM扩展 |
| Q-3 | 公司-节点映射的主营占比来源：fina_mainbz实时计算 vs 预计算缓存？ | backend-dev | 2026-06-26 | 需平衡性能和时效性 |
| Q-4 | 三因子评分的具体阈值如何定义？产业周期阶段如何量化？ | product-lead | 2026-06-25 | 需结合历史验证调参 |
| Q-5 | 现有V5评分体系如何与三因子融合？完全替换 vs 并行输出？ | tech-lead | 2026-06-26 | 架构决策，需ADR |
| Q-6 | ECharts下钻树的节点数量上限？性能如何优化？ | frontend-dev | 2026-06-26 | 建议≤500节点，懒加载 |

---

## 10. Sign-offs

- [ ] product-lead: 初稿
- [ ] tech-lead: 技术可行性 review（涉及LLM集成 + 新数据模型）
- [ ] frontend-dev: 前端可行性确认（ECharts树图 + 三视图）
- [ ] backend-dev: 后端可行性确认（新API + PG表设计）
- [ ] ai-agent-dev: LLM集成可行性确认（prompt + schema）
- [ ] uiux-designer: UI设计契合PRD
- [ ] qa-engineer: AC可测性确认

---

## Changelog

- 2026-06-24: 初稿，三大板块需求结构化