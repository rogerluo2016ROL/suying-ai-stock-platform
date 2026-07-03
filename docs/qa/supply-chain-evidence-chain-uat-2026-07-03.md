# 产业链证据链补全 UAT 记录

**日期:** 2026-07-03  
**范围:** PRD `supply-chain-evidence-chain-tracking-prd-2026-07-03.md` 的 P0 数据底座、结构化事实、阶段跟踪、证据新鲜度、预期差和前端公司抽屉接数。

## 1. 迁移结果

| 项目 | 结果 |
|---|---:|
| Alembic version | `023` |
| 新增证据链表 | 6 张 |
| 迁移状态 | 通过 |

验证命令：

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -At -c "SELECT version_num FROM alembic_version;"
```

## 2. 真实数据落库结果

| 指标 | 数量 |
|---|---:|
| 数据源目录 | 13 |
| 原始证据文档 | 2056 |
| 结构化事实 | 2056 |
| 证据新鲜度记录 | 2199 |
| 阶段变化候选 | 30 |
| 预期差跟踪项 | 159 |

证据新鲜度分布：

| 状态 | 数量 |
|---|---:|
| fresh | 101 |
| unknown | 2098 |

结构化事实分布：

| 来源强度 | 校验状态 | 数量 |
|---|---|---:|
| strong | confirmed | 60 |
| mid | pending | 1996 |

## 3. 接口抽样

抽样对象：

| 字段 | 值 |
|---|---|
| mapping_id | `18C-MAP-ai_compute-300308SZ` |
| 公司 | 中际旭创 |
| 标签 | 高速光模块 |

接口：

```text
GET /api/v1/screener/supply-chain/business-tag/18C-MAP-ai_compute-300308SZ/evidence-chain
```

返回结果：

| 项目 | 结果 |
|---|---:|
| HTTP 状态 | 200 |
| version | `supply-chain-evidence-chain-v1` |
| source_status | `ready` |
| documents | 31 |
| facts | 31 |
| stage_transitions | 0 |
| expectations | 2 |

## 4. 前端验收

| 项目 | 结果 |
|---|---|
| API client 类型 | 已新增 `EvidenceChainResponse`、`EvidenceReviewQueueResponse` |
| 工作台候选池 | 模型候选为空时，已从 `business_tag_mapping` 返回真实映射候选 |
| 公司抽屉 | 已接真实 `mapping_id` 证据链接口 |
| 证据链面板 | 已展示结构化事实、来源文档、限制信息 |
| 阶段跟踪面板 | 已展示 R/C 阶段变化、预期差、新鲜度 |
| 字段对齐 | 使用 `validation_status`、`original_quote`、`research_stage_signal`、`commercial_stage_signal`、单对象 `freshness` |
| 缺少 `mapping_id` | 只显示空态，不展示静态伪数据 |
| TypeScript | 通过 |

工作台抽样：

| 项目 | 结果 |
|---|---|
| 接口 | `GET /api/v1/screener/supply-chain/workbench?top_n=5` |
| HTTP 状态 | 200 |
| candidate_count | 5 |
| candidate_pool 状态 | `mapping_fallback` |
| 首条候选 | 中际旭创 / `18C-MAP-ai_compute-300308SZ` |

验证命令：

```bash
bash tools/codex-lowio.sh fe-typecheck
```

## 5. 自动化测试

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py services/screener-service/tests/test_chain_api.py tools/tests/test_supply_chain_evidence_pipeline.py -q
```

结果：`65 passed`。  
已知提示：FastAPI TestClient 触发 `StarletteDeprecationWarning`，不影响本次功能验收。

## 6. P1 增量验收

| 项目 | 结果 |
|---|---|
| 检索词 dry-run | `generate-search-terms --limit 1` 返回 `mapping_count=1` |
| L1-L8 路径清洗 | 已将对象数组解析为名称，未再出现 `{'name': ...}` |
| 新证据同步旧事件表 | `ingest-text` 返回 `legacy_events=1` |
| 新鲜度刷新 | `freshness_rows=2199` |
| 样例旧事件 | `EV-ffe7631856d35d9481aff91f / commercial_stage / approved` |

P1 增量后真实库状态：

| 指标 | 数量 |
|---|---:|
| 原始证据文档 | 2057 |
| 结构化事实 | 2057 |
| 旧证据事件 | 31888 |
| 证据新鲜度记录 | 2199 |

P1 增量测试：

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_pipeline.py -q
```

结果：`12 passed`。

## 7. 已知限制

- 当前事实表的校验字段为 `validation_status`，接口层对前端展示需要继续保持字段映射，避免误用不存在的 `review_status` 原表字段。
- `unknown` 新鲜度数量较高，说明大量业务标签还没有最新结构化证据，这是后续采集补全的重点，不应在前端用公司整体数据替代。
- 新闻、研报等 mid 来源默认进入待复核；weak 来源不能改变研发或商用阶段。
- 本轮完成的是证据链底座和前端公司抽屉接数，待复核中心独立页面和预期差看板仍属于后续增强。

## 8. 最终全量试跑验收

验收时间：2026-07-03

验收报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/eighteen_chains_incremental_refresh_20260703/18chains-incremental-20260703-130007_acceptance_report.json
```

执行命令：

```bash
python3 tools/run_18chains_incremental_refresh.py --pg-url postgresql://kronos:kronos@localhost:6432/kronos --days 30 --skip-source-sync
```

说明：同一轮任务中已先完成外部增量源刷新；最终验收命令从本地 PostgreSQL 真实库继续执行 18 链拆解、证据结构化、阶段刷新和预期差刷新，避免重复请求外部源。

### 8.1 外部/本地增量源状态

| 数据表 | 最新日期/期间 | 行数 |
|---|---:|---:|
| daily_kline | 2026-07-02 | 8604835 |
| daily_basic | 2026-07-01 | 10744455 |
| moneyflow | 2026-07-02 | 14294615 |
| financial_income | 2026-03-31 | 17595 |
| financial_indicator | 2026-03-31 | 33524 |
| forecast_data | 2027-12-31 | 27251 |
| fina_mainbz | 2026-03-31 | 379 |
| announcements | 2026-07-02 | 33924 |
| interact_qa | 2026-07-02 | 137322 |
| research_reports_tushare | 2026-06-24 | 116300 |
| broker_recommend | 202606 | 17347 |

财报类数据当前验收到 2026Q1。按 75 天披露滞后窗口，2026-07-03 的可验收财务期为 2026-03-31。

### 8.2 全量拆解落库结果

| 指标 | 数量 |
|---|---:|
| 产业链数量 | 18 |
| 标签映射 | 2199 |
| 覆盖公司 | 1162 |
| 批量生成证据事件 | 23920 |
| 原始证据文档 | 32114 |
| 结构化事实 | 32114 |
| 旧证据事件 | 32112 |
| 证据新鲜度记录 | 2199 |
| L8 证据状态 | 16366 |
| 阶段跟踪记录 | 2339 |
| 三高评分 | 2199 |
| 预期差评分 | 2199 |

18 条产业链映射分布：

| chain_id | 映射数 |
|---|---:|
| ai_compute | 2066 |
| bio_manufacturing | 6 |
| brain_computer_interface | 6 |
| embodied_intelligence | 36 |
| future_display | 6 |
| future_energy | 6 |
| future_health | 6 |
| future_materials | 6 |
| future_space | 6 |
| hydrogen_energy | 6 |
| industrial_mother_machine | 6 |
| industrial_software | 6 |
| intelligent_manufacturing | 6 |
| low_altitude_economy | 6 |
| nuclear_fusion | 6 |
| quantum_technology | 5 |
| semiconductor_equipment_materials | 8 |
| sixth_generation_6g | 6 |

新鲜度分布：

| 状态 | 数量 |
|---|---:|
| fresh | 2180 |
| stale | 6 |
| expired | 5 |
| unknown | 8 |

### 8.3 最终验证命令

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py services/screener-service/tests/test_chain_api.py tools/tests/test_supply_chain_evidence_pipeline.py tools/tests/test_18chains_incremental_refresh.py -q
```

结果：`71 passed`。

```bash
bash tools/codex-lowio.sh fe-typecheck
```

结果：通过。

## 11. 候选公司总榜验收

验收时间：2026-07-03

执行命令：

```bash
python3 tools/build_supply_chain_candidate_ranking.py \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --top-n 120
```

输出报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.json
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.csv
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.md
```

总览：

| 指标 | 数量 |
|---|---:|
| 标签映射评分行 | 2255 |
| 公司-产业链组合 | 1219 |
| 产业链数量 | 18 |
| 重点候选 | 1 |
| 观察 | 92 |
| 暂缓 | 1126 |

全局 Top 10：

| 排名 | chain_id | 代码 | 名称 | 分数 | 信号 | 最强标签 |
|---:|---|---|---|---:|---|---|
| 1 | ai_compute | 688498 | 源杰科技 | 80.97 | 重点候选 | 公司业务标签：AI芯片/芯片业务 |
| 2 | ai_compute | 688008 | 澜起科技 | 74.39 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 3 | ai_compute | 300502 | 新易盛 | 73.11 | 观察 | 公司业务标签：光模块业务 |
| 4 | ai_compute | 301308 | 江波龙 | 72.75 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 5 | ai_compute | 688110 | 东芯股份 | 72.39 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 6 | ai_compute | 603893 | 瑞芯微 | 71.79 | 观察 | 公司业务标签：AI算法业务 |
| 7 | ai_compute | 300308 | 中际旭创 | 71.04 | 观察 | 公司业务标签：光模块业务 |
| 8 | ai_compute | 688620 | 安凯微 | 70.43 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 9 | ai_compute | 603459 | 红板科技 | 70.17 | 观察 | 公司业务标签：PCB与连接材料业务 |
| 10 | ai_compute | 603160 | 汇顶科技 | 70.12 | 观察 | 公司业务标签：AI芯片/芯片业务 |

验收说明：

```text
全局 Top 主要来自 AI 算力链，因为该链数据密度和证据覆盖最高。
报告同时输出每条产业链 Top 5，避免只看全局榜造成大链偏置。
短期行情仅占 2% 权重，不能覆盖产业链证据。
重点候选不是买入建议，只是后续研究优先级。
```

验证命令：

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_candidate_ranking.py -q
```

结果：`3 passed`。

## 12. 候选总榜 API 和前端页签验收

验收时间：2026-07-03

后端真实接口：

```text
GET /api/v1/screener/supply-chain/candidate-ranking?top_n=5
```

真实库返回：

| 指标 | 值 |
|---|---|
| HTTP 状态 | 200 |
| version | `supply-chain-candidate-ranking-v1` |
| source_status | `ready` |
| mapping_rows | 2255 |
| company_chain_rows | 1219 |
| chain_count | 18 |
| 重点候选 | 1 |
| 观察 | 92 |
| 暂缓 | 1126 |

接口 Top 3：

| 排名 | chain_id | 代码 | 名称 | 分数 | 信号 | mapping_id |
|---:|---|---|---|---:|---|---|
| 1 | ai_compute | 688498 | 源杰科技 | 80.97 | 重点候选 | auto_688498_ai_compute_hardware |
| 2 | ai_compute | 688008 | 澜起科技 | 74.39 | 观察 | auto_688008_ai_compute_hardware |
| 3 | ai_compute | 300502 | 新易盛 | 73.11 | 观察 | auto_300502_ai_compute_hardware |

前端验收：

| 项目 | 结果 |
|---|---|
| 新增路由 | `/supply-chain-bom/ranking` |
| 新增页签 | 候选总榜 |
| 数据来源 | `/api/v1/screener/supply-chain/candidate-ranking` |
| 查看证据 | 使用 `best_mapping_id` 打开公司研究抽屉 |
| 静态候选 | 未使用 |

验证命令：

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestSupplyChainCandidateRanking -q
bash tools/codex-lowio.sh fe-test src/__tests__/SupplyChainCandidateRankingPanel.test.tsx
bash tools/codex-lowio.sh fe-test src/__tests__/PrototypeRoutes.test.tsx
bash tools/codex-lowio.sh fe-typecheck
```

结果：

```text
后端接口测试通过。
候选总榜组件测试通过。
路由覆盖测试通过，73 passed。
前端类型检查通过。
```

### 8.4 验收结论

通过。

原因：

```text
18 条产业链全部有映射记录。
映射、证据事件、原始文档、结构化事实、L8 状态、研发/商用阶段、三高评分、预期差评分均已落库。
前端类型检查通过，后端合同测试和管道测试通过。
未用静态假数据替代缺失证据；财报类数据按披露窗口判断，不强拉不存在的新报告期。
```

## 9. 数据质量体检验收

验收时间：2026-07-03

执行命令：

```bash
python3 tools/audit_supply_chain_data_quality.py --pg-url postgresql://kronos:kronos@localhost:6432/kronos
```

输出报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703/chain_quality_audit_20260703-131200.json
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703/chain_quality_audit_20260703-131200.md
```

总体结果：

| 指标 | 数值 |
|---|---:|
| 产业链数量 | 18 |
| 高风险链 | 3 |
| 中风险链 | 4 |
| 低风险链 | 11 |
| 平均质量分 | 78.88 |

补数优先级 Top 10：

| 优先级 | chain_id | 风险 | 质量分 | 映射 | 公司 | 事实/映射 | L8/映射 | 新鲜度 | 建议动作 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | future_materials | high | 74.41 | 6 | 6 | 15.33 | 14.0 | 66.7% | 补公司/标签映射；刷新过期/未知证据 |
| 2 | industrial_software | high | 74.41 | 6 | 6 | 13.33 | 14.0 | 66.7% | 补公司/标签映射；刷新过期/未知证据 |
| 3 | embodied_intelligence | high | 97.72 | 36 | 36 | 19.22 | 14.0 | 69.4% | 刷新过期/未知证据 |
| 4 | quantum_technology | medium | 74.72 | 5 | 5 | 14.6 | 14.0 | 80.0% | 补公司/标签映射；刷新过期/未知证据 |
| 5 | brain_computer_interface | medium | 76.26 | 6 | 6 | 18.17 | 14.0 | 83.3% | 补公司/标签映射；刷新过期/未知证据 |
| 6 | future_display | medium | 76.26 | 6 | 6 | 20.0 | 14.0 | 83.3% | 补公司/标签映射；刷新过期/未知证据 |
| 7 | intelligent_manufacturing | medium | 76.26 | 6 | 6 | 20.17 | 14.0 | 83.3% | 补公司/标签映射；刷新过期/未知证据 |
| 8 | bio_manufacturing | low | 77.0 | 6 | 6 | 10.67 | 14.0 | 100.0% | 补公司/标签映射 |
| 9 | future_energy | low | 77.0 | 6 | 6 | 23.17 | 14.0 | 100.0% | 补公司/标签映射 |
| 10 | future_health | low | 77.0 | 6 | 6 | 10.83 | 14.0 | 100.0% | 补公司/标签映射 |

说明：

```text
高风险不等于产业链没有价值，也不等于公司不好。
高风险表示当前数据底座不够稳，或者近期证据不够新，不能直接用于强推荐。
具身智能质量分高但风险高，原因是证据和 L8 覆盖充足，但新鲜度只有 69.4%，下一步应优先刷新近期证据。
未来材料、工业软件、量子、脑机等链主要问题是公司/标签映射太薄，需要扩候选池。
```

验证命令：

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_quality_audit.py -q
```

结果：`3 passed`。

## 10. 优先链候选池修复验收

验收时间：2026-07-03

执行命令：

```bash
python3 tools/repair_priority_supply_chains.py \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --since 2026-01-01 \
  --limit-per-chain 20 \
  --execute
```

输出报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/priority_chain_repair_20260703/priority_chain_repair_20260703-133930.json
/Users/rogerluo/程序目录/K线大模型/outputs/priority_chain_repair_20260703/priority_chain_repair_20260703-133930.md
```

修复对象：

| chain_id | 来源命中公司 | 选中候选 | 新增映射 | 刷新已有映射 | 证据事件 |
|---|---:|---:|---:|---:|---:|
| future_materials | 484 | 20 | 18 | 2 | 120 |
| industrial_software | 342 | 20 | 20 | 0 | 120 |
| embodied_intelligence | 354 | 20 | 18 | 2 | 120 |

落库结果：

| 项目 | 数量 |
|---|---:|
| 新增候选映射 | 56 |
| 修复证据事件 | 359 |

三条链映射扩容：

| chain_id | 修复后映射 | 修复后公司 |
|---|---:|---:|
| future_materials | 24 | 24 |
| industrial_software | 26 | 26 |
| embodied_intelligence | 54 | 54 |

后续重算命令：

```bash
python3 tools/backfill_ai_compute_all_mapped.py --chain-id future_materials
python3 tools/backfill_ai_compute_all_mapped.py --chain-id industrial_software
python3 tools/backfill_ai_compute_all_mapped.py --chain-id embodied_intelligence
python3 tools/supply_chain_evidence_pipeline.py backfill-existing-events --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
python3 tools/supply_chain_evidence_pipeline.py refresh-stage-transitions --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
python3 tools/supply_chain_evidence_pipeline.py refresh-expectation-monitor --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
```

重算结果：

| 指标 | 数量 |
|---|---:|
| 证据事件 | 32917 |
| 原始证据文档 | 32919 |
| 结构化事实 | 32919 |
| L8 证据状态 | 16758 |
| 三高评分 | 32919 |
| 预期差评分 | 32919 |
| 阶段迁移候选 | 4738 |
| 预期差监控 | 927 |

复测报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703_after_repair/chain_quality_audit_20260703-134337.json
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703_after_repair/chain_quality_audit_20260703-134337.md
```

复测总览：

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| 高风险链 | 3 | 0 |
| 中风险链 | 4 | 5 |
| 低风险链 | 11 | 13 |
| 平均质量分 | 78.88 | 81.42 |

重点链变化：

| chain_id | 修复前 | 修复后 | 结论 |
|---|---|---|---|
| future_materials | high / 6 映射 | low / 24 映射 | 候选池已补齐，进入日更跟踪 |
| industrial_software | high / 6 映射 | low / 26 映射 | 候选池已补齐，进入日更跟踪 |
| embodied_intelligence | high / 36 映射 | medium / 54 映射 | 风险下降，但新鲜度仍需继续补近期硬证据 |

本轮发现并修复的后端问题：

```text
backfill_ai_compute_all_mapped.py 删除旧 batch 事件时，会触发 evidence_extracted_facts 外键约束。
已改为只删除未被结构化事实引用的 batch 事件，已引用事件保留并通过 upsert 更新。
```

验证命令：

```bash
bash tools/codex-lowio.sh py tools/tests/test_repair_priority_supply_chains.py tools/tests/test_backfill_ai_compute_all_mapped.py -q
```

结果：通过。
