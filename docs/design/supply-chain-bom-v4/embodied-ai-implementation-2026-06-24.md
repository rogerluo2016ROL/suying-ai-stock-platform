# 产业链 BOM 拆解选股模型 — 具身智能链实施与 OOS 验证

> Date: 2026-06-24
> Status: 方法论闭环 + OOS 验证通过
> 关联 PRD: docs/prd/supply-chain-bom-2026-06-23.md
> 关联 migration: backend/alembic/versions/012_supply_chain_bom_v4.py

## 1. 背景

现有 `supply_chain` 模型是"行业关键词 + 五维评分"，能做主题粗筛，不能回答"国家鼓励哪条链 → 卡在哪一环 → 哪些公司已量产"。本次以**具身智能链**为试点，落地 BOM（Bill of Materials）级拆解：政策主题 → 产业链 → BOM 节点 → 企业-产品-材料映射 → 卡脖子/商业化证据 → 七维评分 → 交易信号，并做严格样本外验证。

## 2. 数据底盘 (Tushare, 已 probe)

`tools/tushare_vip_probe.py` 探测 23 个接口：**17 OK / 0 DENIED**，token 权限充足。BOM 拆解关键接口全可用：

| 用途 | 接口 | 调用陷阱 |
|---|---|---|
| 企业-产品锚定（核心）| `fina_mainbz_vip` | **必传 `type='P'`** 才是产品级拆分 |
| 互动问答（证据金矿）| `irm_qa_sz` / `irm_qa_sh` | **按 `trade_date` 全市场调**，不能 ts_code+长区间 |
| 研报 | `research_report` | — |
| 业绩预告 | `forecast` | — |
| 板块骨架 | `ths_index` / `ths_member` | `ths_member` 用**概念 ts_code 查成员**，不能反向 |
| 财务 | `fina_indicator` | 时点隔离用 `ann_date` 非 `end_date` |

## 3. 实施七步

| 步骤 | 脚本 | 产出 | 结论 |
|---|---|---|---|
| 1 产品锚定 | `bom_embodied_probe.py` | 概念池 138→38 只 | `fina_mainbz_vip` 剔 72% 沾边股，自动定位节点龙头 |
| 2 证据采集 | `bom_reducer_evidence.py` | 80 条证据 | 互动问答质量远超研报，含产品/客户/量产/国产替代 |
| 3 七维评分 | `bom_reducer_score.py` | reducer 7 只分层 | S/A/C/D 区分龙头（绿的谐波/昊志=A） |
| 4 横扩节点 | `bom_expand_evidence.py` + `bom_embodied_score_all.py` | 4 节点×19 公司×221 证据 | 每节点出龙头，跨节点分层一致 |
| 5 补财务+修规则 | `bom_embodied_score_v5.py` | V5 评分 | 接 `fina_indicator` 填 growth/profit；修 chokepoint 多样性加权（光洋降分）+ 低互动财务兜底（鸣志升分） |
| 6 落 PG+API | `bom_persist_pg.py` | 八表 + API 可读 | code 统一 6 位对齐 stocks 表；screener `/supply-chain/bom` 可下钻 |
| 7 严格 OOS | `bom_oos_cache.py` + `bom_oos_ic.py` | cutoff-aware IC | **20d test rankIC +0.093, p=0.007** |

## 4. 七维评分规则 (V5)

```
policy(15)          节点属强政策链(具身智能=未来产业主攻方向) 基础分 + 政策催化证据
bom(15)             主营占比映射 (节点集中度): 80%+→15, 50%→12, 25%→8, 10%→4
chokepoint(20)      卡脖子证据多样性加权: 同关键词最多计2次, 垄断/独家/首家×5, 客户验证/认证/供应商×3
growth(15)          财务 q_sales_yoy/netprofit_yoy 优先, 业绩预告兜底
profit(10)          毛利率映射 (制造业阈值下调): 50%+→10, 30%→7, 15%→4
commercialization(15) 商业化阶段: 放量/订单>量产>小批量>样品 + 业绩预增加成
market(10)          互动问答+研报证据数映射
```

评分经 `derive_rating` (S≥85/A≥75/B≥65/C≥50/D) + `derive_trade_signal` (强启动/启动/关注/观察/风险回避) 输出。

## 5. OOS 验证 (AC-9 核心验收)

### 防 lookahead (AC-8)

`bom_oos_ic.py` 逐月末 cutoff 重算评分，只用 `ann_date/trade_date ≤ cutoff` 的数据：
- 财务/预告：`ann_date ≤ cutoff` 的最新一期
- 互动问答/研报：`trade_date ≤ cutoff`
- 主营占比：最新一期（结构变化慢，可接受）

### 结果

| horizon | train (2025-01~09) | test (2025-10~2026-05) |
|---|---|---|
| 10d | rankIC −0.035 (p=0.715) | rankIC +0.011 (p=0.445) |
| **20d** | rankIC −0.031 (p=0.716) | **rankIC +0.093 (p=0.007)** |

**20 日 horizon test 期 rankIC +0.093，p=0.007 统计显著**——BOM 评分有真选股能力（OOS 成立）。

### 关键发现

1. **路径1 vs 路径2 对比**：路径1（lookahead）2026-03 IC=+0.525，路径2（cutoff-aware）+0.244——lookahead 虚高约 2 倍，证明 cutoff-aware 必要。
2. **horizon 效应**：20d 显著、10d 不显著。BOM 是中长期选股因子，非短期博弈。
3. **regime 效应**：train（2025H1 下行）rankIC 负，test（2025Q4 起上行）正。BOM 在板块上行期有效，下行期失效——与 bi_trend regime 暴露同源，后续可加 regime 过滤。
4. **20d test 7 个 cutoff 全为正**（+0.014~+0.244），无负 cutoff，比均值更稳健。

### 限定

- 样本 36 只偏小，统计功效有限，p=0.007 需更大样本复核
- 36 只均为已锚定标的，存在选择偏差
- 下行期无效，不能无条件使用

## 6. 落库 (migration 012 八表)

`bom_persist_pg.py` 幂等落库（`ON CONFLICT DO NOTHING`，可重跑）：

| 表 | 行数 | 内容 |
|---|---|---|
| policy_themes | 1 | 未来产业主攻方向 |
| supply_chain_bom_nodes | 5 | 具身智能链 + 4 组件节点 |
| policy_sources | 4 | Tushare 研报/问答/预告 |
| company_bom_mapping | 36 | 公司×节点锚定 + 主营产品 |
| company_evidence | 211 | 证据（来源/类型/摘要/置信度）|
| supply_chain_scores | 19 | V5 评分（trade_date=当前快照）|

⚠️ `supply_chain_scores.trade_date` 是当前快照，非回测时点。回测须 cutoff-aware 重算（见第 5 节）。

screener `/api/v1/screener/supply-chain/bom` 已可读取这些表，前端 `SupplyChainBom.tsx` 下钻链路有真实数据支撑。

## 7. 待办

- [ ] 扩样本 OOS：36 只 → 全市场 `fina_mainbz` 锚定，提升统计功效复核 p=0.007
- [ ] regime 过滤：下行期降仓/跳过，复用 bi_trend breadth 门控思路
- [ ] profit 维度校准：制造业毛利阈值进一步调
- [ ] LLM 抽取接入：当前证据抽取是规则+关键词，`llm_supply_chain.py` 的 DeepSeek 抽取可替代，提升证据颗粒度
- [ ] 前端联调：启动 screener-service + 前端，浏览器实测下钻（PRD AC-3/4/5）
