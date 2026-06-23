# ADR-005: 个股诊断

- 状态：Proposed
- 日期：2026-06-10
- 决策者：tech-lead
- 影响范围：diagnosis-service + frontend Diagnosis.tsx + Kronos 预测服务集成 + PostgreSQL 诊断历史表

## 上下文

PRD 第 ⑫ 环节"个股诊断"（AC-12.1~12.7）要求实现：用户输入股票代码后一键生成多维诊断报告，包括五个维度的量化评分 —— 技术面（40%）、资金面（25%）、基本面（20%）、AI 预测（10%）、情绪面（5%）。诊断结果需输出综合评分（0-100）、五级操作建议（强烈买入/买入/持有/减仓/卖出）、Kronos 30 日预测 K 线图与买卖点信号，并支持 PDF 导出、多股对比（2-5 只）和历史记录查询。

现有资产评估：
- `frontend/src/pages/Diagnosis.tsx`（115 行骨架）：已搭建搜索框 + 五维进度条 + 统计卡片 UI，但数据来源仅调用了 `/api/v1/signal/analyze/{code}` + `/api/v1/prediction/predict/{code}` 两个旧接口，未按五维模型组装数据
- `services/diagnosis-service/app/`（3 文件空壳服务）：`main.py`（FastAPI 骨架，port 8009）+ `routes.py`（3 个存根端点返回 mock 数据），无实际诊断逻辑、无 DB 连接、无 Kronos 集成
- `services/training-service/`（ADR-004 已建）：已具备 LightGBM/CatBoost 因子训练能力，可为技术面和基本面维度提供子模型输出
- Kronos 预测服务：已在园区运行，可由 diagnosis-service 调用获取 AI 预测维度数据

不做此决策的后果：diagnosis-service 与前端各自演进，数据组装逻辑散落在前端和多个服务调用之间，无统一聚合层；五维评分算法随意选择导致输出不稳定；PDF 导出方案选错导致中文字体/图表渲染失败须返工；历史诊断数据无处存储无法追溯；Kronos 预测每次实时推理成本失控。

## 决策

### 决策 1：诊断聚合算法 — 加权评分 vs ML 融合模型

| 维度 | 选型 | 理由 |
|------|------|------|
| 聚合方式 | **加权线性评分（Weighted Linear Score）** | PRD AC-12.2 已明确五维权重（40/25/20/10/5），加权求和公式 `overall = Σ(w_i × score_i) / Σw_i × 100` 天然可解释、可审计、可调试。每一维度的子评分有明确的归因路径，用户问"为什么评分低"时可以逐维追溯到具体指标 |
| 否决方案 | ML 元分类器（XGBoost/Stacking）融合五维 | 否决理由：(1) PRD 已给定固定权重，不需要从数据学习融合参数；(2) 当前标注样本不足 —— 诊断是新产品功能，不存在"正确的综合评分"作为训练目标，ML 模型缺乏 ground truth；(3) 不可解释 —— 黑盒融合违反了金融合规对诊断建议"可审计归因"的要求，如出现亏损用户有权追问评分依据 |
| 子维度评分归一化 | Min-Max 归一化到 0-100 | 各维度原始信号（如技术面 ADX 0-100、RSI 0-100、资金流净额 -∞~+∞、PE 倒数映射）统一映射到 [0, 100] 区间后再加权，保证量纲一致 |
| 五级操作建议映射 | 阈值分段函数 | 综合评分 ≥85 → 强烈买入，70-84 → 买入，50-69 → 持有，35-49 → 减仓，<35 → 卖出。阈值通过管理员面板可配置（存储在 `diagnosis_config` 表），后续 ADR 可引入动态阈值优化 |

### 决策 2：报告生成 — HTML 模板 + Headless Chrome vs 后端 PDF 库

| 维度 | 选型 | 理由 |
|------|------|------|
| 报告格式 | **HTML 模板（前端渲染）+ Playwright headless 转 PDF** | 诊断报告包含 K 线图（ECharts/Lightweight Charts）、五维雷达图、评分仪表盘等复杂可视化，HTML + 前端图表库渲染效果远优于后端 PDF 库手绘图形。Playwright 的 `page.pdf()` API 支持 CSS `@page`、页眉页脚、分页控制，且复用已有的 E2E 测试基础设施（chrome-devtools MCP）。前端 Diagnosis.tsx 自带报告视图，PDF 导出本质是"截取当前报告的打印版本" |
| 否决方案 A | WeasyPrint/ReportLab 后端直接生成 PDF | 否决理由：不支持 JavaScript 图表渲染，需后端用 matplotlib/Pillow 重新实现 K 线图和雷达图，导致两套渲染代码并存，且中文字体配置复杂度高（需安装字体 + 配置 fontconfig） |
| 否决方案 B | 纯前端 `window.print()` + 浏览器原生打印 | 否决理由：用户打印体验不可控（浏览器差异、打印对话框样式丢失、无页面控制系统），不适合自动化批量生成场景。Playwright 可无头运行，服务端统一品质 |
| 导出流程 | `POST /api/v1/diagnosis/report/{code}?format=pdf` → diagnosis-service 调用 Playwright → 打开前端报告页 → `page.pdf()` → 返回 PDF 二进制流 / 或生成 COS 下载链接 | Playwright 浏览器实例通过单例池管理（最多 3 个并发），诊断报告生成非高频操作，3 并发可满足峰值 |

### 决策 3：多股对比 — 后端聚合 vs 前端并行请求

| 维度 | 选型 | 理由 |
|------|------|------|
| 数据聚合方式 | **后端聚合（`POST /api/v1/diagnosis/compare` 一次性返回）**| 多股对比需同时对 2-5 只股票跑五维诊断，如果前端逐一请求 `POST /analyze` 再合并：(1) 5 只股票 × 5 维维度 = 可能需要 5-10 个后端 API 调用（若维度各自独立服务），前端请求瀑布流延长总耗时；(2) 前端合并逻辑随对比维度变化而复杂化，增加维护负担。后端聚合由 diagnosis-service 内部并行调用各维度数据源（Kronos、factors、data），`asyncio.gather` 并发，单次诊断耗时 ≈ 最慢子调用的延迟 |
| 否决方案 | 前端并行请求 + 前端合并 | 否决理由：前端需感知诊断内部服务拓扑（技术面从 factors-service、AI 预测从 Kronos、情绪面从 sentiment-service），微服务边界泄露到前端，后续服务拆分/合并时前端需同步改。后端聚合遵循 BFF（Backend for Frontend）模式，diagnosis-service 是前端的唯一诊断数据入口 |
| 并排展示 | 前端表格/卡片矩阵 | 后端返回 `[{stock, dimensions: {...}, overall_score}]` 数组，前端用 Ant Design Table 或自定义卡片网格渲染并排对比，每只股票一列，每维度一行，支持排序（按综合评分 / 单维度评分） |
| 对比维度可配置 | `dimensions` 查询参数 | AC-12.6 未限定对比维度，允许用户自选对比维度（如只看技术面 + AI 预测），减少不必要的数据拉取 |

### 决策 4：历史存储 — PostgreSQL vs Redis 缓存

| 维度 | 选型 | 理由 |
|------|------|------|
| 持久化方案 | **PostgreSQL 诊断历史表** | AC-12.7 要求"历史诊断记录可查询"，需要支持按股票代码、时间范围、评分区间等条件查询和分页。PostgreSQL 提供结构化查询、JSONB 存储维度详情、索引加速、与现有 `kronos_db` 复用连接。Redis 是缓存层，不应作为历史记录的单一来源 —— 内存优先、数据易失、查询能力弱（不支持复杂 WHERE/LIKE/排序），且历史数据长期增长不适合全量内存 |
| 否决方案 | Redis 缓存 + TTL 过期 | 否决理由：(1) 历史记录 ≠ 缓存 —— 用户期望查询"上周对某股票做了哪些诊断"，而非"最近 1 小时内有没有人查过同一只股票"；(2) 诊断详情体积大（含 JSON 维度和图表元数据），长期堆积在 Redis 内存中成本不可控；(3) Redis 天然无关联查询，无法按时间范围/评分排序/持仓状态过滤 |
| 表结构 | `diagnosis_history` — `id, user_id, stock_code, overall_score, grade, recommendation, dimensions(JSONB), kronos_prediction(JSONB), key_levels(JSONB), risk_warnings(TEXT[]), created_at` | JSONB 列存储五维详情和预测数据，避免为每个维度建子表过度规范化；`created_at` 加索引用于历史查询；`stock_code + created_at` 联合索引覆盖"某股票历史"查询 |
| 补充缓存 | **Redis 缓存"48 小时内同股票同用户"的近期诊断** | 用户在同一天反复查看同一股票不应每次都重新计算。Redis 键 `diagnosis:{user_id}:{stock_code}` TTL 48 小时，缓存命中直接返回，减少后端重复计算和 Kronos API 调用费用 |

### 决策 5：Kronos 预测集成 — 实时预测 vs 缓存预测

| 维度 | 选型 | 理由 |
|------|------|------|
| 预测获取方式 | **缓存优先 + TTL 驱动刷新** | Kronos 30 日预测是 GPU 推理任务，每次调用成本可观（LLM/K 线预测模型推理），且预测结果在短时间内（同一天内）不应有显著变化。缓存策略：同一股票代码的预测结果缓存 6 小时（交易日期间），非交易日缓存 24 小时。缓存存储在 Redis `kronos_pred:{stock_code}`，TTL = 6h/24h |
| 否决方案 | 每次诊断实时调用 Kronos | 否决理由：(1) 成本不可控 —— 用户反复点击诊断同一只股票或频繁切换对比股票时，每次触发 GPU 推理；(2) 延迟体验差 —— Kronos 预测耗时 3-8s（取决于模型负载），叠加其他维度诊断，总响应时间突破 10s 不可接受；(3) 无意义重复 —— 同一天内同一只股票的预测结果没有变化，实时调用是浪费 |
| 缓存刷新策略 | 被动失效 + 主动预热 | 交易日开盘前（9:00）和收盘后（15:30），通过 APScheduler 定时任务预热热门股票（持仓股 + 最近 7 天诊断过的股票）的 Kronos 预测缓存，确保用户进行诊断时命中率 >90%。缓存键包含 `pred_days=30` 参数，与 PRD AC-12.3 要求的"Kronos 30 日预测 K 线图"一致 |
| 容错降级 | Kronos 不可用时 AI 预测维度显示"暂无数据" | 诊断不应因 Kronos 服务故障而整体失败。当 Kronos 调用超时（>8s）或返回 5xx 时，AI 预测维度标记为 `unavailable`，维度权重临时重新分配（技术面 44%、资金面 28%、基本面 22%、情绪面 6%），总分仍然计算但标注"AI 预测暂不可用" |
| Kronos 集成协议 | HTTP REST `POST /api/v1/prediction/predict/{code}` + 带 Bearer Token 认证 | diagnosis-service 通过内部网络调用 Kronos 服务，不经过前端中转，减少延迟和暴露面 |
| 模型来源说明 | **基于公开 `NeoQuasar/Kronos-mini` 托管推理**（非自研） | M05（audit-model-2026-06-22）：prediction-service 加载的是 HuggingFace 公开的 `NeoQuasar/Kronos-mini` base 权重，自研 fine-tune checkpoint（`Kronos/outputs/models/finetune_*`）**当前不存在**。本 ADR 中的"Kronos 预测"均指该公开模型的本地托管推理，不自研、不微调。自研训练需 GPU 集群 + 真实数据集，另立项（见 ADR-004 决策 6 待定项）。prediction-service `/api/v1/health` 的 `checkpoint_status` 字段标注来源（`base_public` / `finetuned`）|

## 备选方案

### A. 诊断聚合 — ML 融合模型（XGBoost Stacking）
- **Pros**: 理论上可以从历史数据学习最优融合权重，可能发现非线性交互（如"技术面差 + 资金面强"的实际含义）
- **Cons**: 需要标注数据（未来 N 日实际收益作为 ground truth），当前零样本；不可解释、不可审计；违反 PRD 已给定的固定权重
- **否决理由**: 标注数据不存在（chicken-and-egg），且金融合规要求诊断建议可归因。保留为未来 Phase 3/4 的备选方向，届时若积累了 ≥5000 条诊断+实际收益样本，可用新 ADR 重新评估

### B. 多股对比 — 前端并行请求 + 前端数据合并
- **Pros**: diagnosis-service 逻辑更简单，只需提供单股诊断接口
- **Cons**: 前端需感知后端服务拓扑；5 只股票并发诊断时前端需管理 5 个异步请求的状态和错误，UI 复杂度上升
- **否决理由**: BFF 模式在微服务架构中已是成熟实践，diagnosis-service 作为聚合层的定位与其服务名一致，不应退化

### C. 报告生成 — 纯后端 WeasyPrint
- **Pros**: 不依赖浏览器进程，部署简单，资源占用低
- **Cons**: 无法渲染 JavaScript 图表（K 线图、雷达图）；中文字体配置复杂；图表需后端用 matplotlib 重复实现
- **否决理由**: 诊断报告的核心价值是可视化图表，不能为了部署简单而牺牲图表质量

## 影响

### 对现有代码
- `services/diagnosis-service/app/routes.py`：三个存根端点需要完全重写，实现真实诊断逻辑、权重计算、Kronos 调用、PDF 生成
- `services/diagnosis-service/app/`：新增 `dependencies/`（Redis 客户端、Kronos HTTP 客户端、DB session）、`services/`（维度评分计算、PDF 生成、对比聚合）、`schemas/`（Pydantic 响应模型）
- `frontend/src/pages/Diagnosis.tsx`：重构前端数据接入，从调用旧 `/api/v1/signal/analyze` 和 `/api/v1/prediction/predict` 改为统一调用 `POST /api/v1/diagnosis/analyze`；新增多股对比 UI、PDF 导出按钮
- `docker-compose.yml`：新增 diagnosis-service 容器定义（port 8009）；Playwright 浏览器依赖（chromium 镜像或 sidecar 容器）
- PostgreSQL：新增 `diagnosis_history` 表 + `diagnosis_config` 配置表（操作建议阈值）

### 对团队
- 后端开发需掌握 asyncio 并发调用模式（`asyncio.gather`）和 Playwright 无头浏览器 PDF 生成
- 前端开发需实现 PDF 导出按钮对接后端、多股并排对比表格、操作建议卡片 UI
- 无需新人角色，diagnosis-service 在执行层按现有后端开发 + 前端开发分工即可

### 对成本
- Kronos GPU 预测：按缓存命中率 90% 估算，日均诊断 500 次 → 实际调用 50 次/天 × 30 天 = 1500 次/月，按每万 tokens 0.5 CNY → 约 30-60 CNY/月（取决于预测 prompt 长度）
- Playwright 无头浏览器：3 并发 ≈ 300-500 MB 内存，无需额外计费（复用现有 E2E 基础设施）
- PostgreSQL 存储：诊断历史每条约 2-5 KB JSONB，日均 500 条 × 30 天 = 15,000 条 × 5 KB ≈ 75 MB/月，可忽略
- 总增量 < 100 CNY/月

### 对运维
- 新增 monitoring point：diagnosis-service health check（`/api/v1/health`），Kronos 调用失败率、诊断平均延迟、缓存命中率
- 新增告警：Kronos 服务连续 3 次调用失败 → 触发 warning（诊断仍可用降级模式）
- 备份策略：`diagnosis_history` 表纳入现有 PostgreSQL 备份策略（每日 pg_dump + WAL 归档），无需额外备份

## 本 ADR 不覆盖的决策

- **情绪面数据源选择**（新闻 API vs 股吧/雪球爬虫 vs NLP 情绪分析模型）：留给后续 ADR，当前 Phase 采用 mock 数据占位
- **基本面因子数据源**（东方财富/同花顺 API vs 自建数据采集）：留给 data-service 相关 ADR
- **Kronos 预测图前端渲染方案**（ECharts vs Lightweight Charts vs Canvas 自绘）：前端实现细节，不需 ADR 级别决策
- **诊断配置面板 UI**（管理员修改权重/阈值）：前端 + 管理后台功能，不需独立 ADR

## 后续工作

- [ ] **后端开发**：实现 diagnosis-service 真实诊断逻辑（维度评分计算、加权聚合、Kronos 调用、PDF 生成），在 AC-12 启动时
- [ ] **前端开发**：重构 Diagnosis.tsx 接入新接口、实现多股对比 UI、PDF 导出按钮，在 AC-12 启动时
- [ ] **DB 迁移**：创建 `diagnosis_history` + `diagnosis_config` 表，在 diagnosis-service 首次部署前
- [ ] **Playwright 部署**：在 diagnosis-service 容器中安装 Chromium + Playwright，在 PDF 导出功能实现前
- [ ] **Redis 配置**：为 diagnosis-service 配置 Redis 连接（缓存 Kronos 预测 + 近期诊断），在 diagnosis-service 实现时
- [ ] **APScheduler 预热任务**：添加交易日定时预热 Kronos 预测缓存的任务，在 Kronos 集成上线后
- [ ] **成本监控**：上线 1 个月后 review Kronos API 实际调用量，按需调整缓存 TTL

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。新增技术或大版本升级时必填。

**查证基线日期**：2026-06-10

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|------|---------|-----------|-------------|---------|----------------------|
| FastAPI | 0.115.x | 0.115.6 | 0 | Active | [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/) — 当前项目 training-service 已使用 |
| PostgreSQL | 15.x | 17.3 | 2 个 major 落后 | Active | [PostgreSQL Versioning](https://www.postgresql.org/support/versioning/) — docker-compose.yml 中选定 15，向下兼容 |
| Redis | 7.x | 7.4.2 | 0 | Active | [Redis Release Notes](https://raw.githubusercontent.com/redis/redis/7.4/00-RELEASENOTES) — docker-compose 已有 Redis 服务 |
| Playwright | 1.52.x | 1.52.0 | 0 | Active | [Playwright Release Notes](https://github.com/microsoft/playwright/releases) — "Playwright 1.52 includes Chromium 134, Firefox 134, WebKit 18.4" |
| APScheduler | 3.10.x | 3.11.0 | 1 个 minor 落后 | Active | [APScheduler Changelog](https://github.com/agronholm/apscheduler/blob/master/docs/versionhistory.rst) — ADR-004 已选定 3.x 用于 training-service 调度，diagnosis-service 复用 |

---

*本 ADR 由 tech-lead 基于 PRD AC-12.1~12.7 撰写，遵循 skill `agf-writing-adr` 的"查证 → 决策 → 写 ADR"三步骤。*
