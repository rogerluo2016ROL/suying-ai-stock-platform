# 速赢AI 模型 + 量化策略审计报告

- 审计日期: 2026-06-21
- 审计人: AI 模型 + 量化策略审计专家（只读分析，未修改任何代码 / 未重训 checkpoint）
- 审计范围: `Kronos/`、`packages/kronos-core`、`packages/kronos-factors`、bi_trend 策略、`services/{prediction,backtest,training}-service`、`outputs/backtest_bi_trend_*.json`
- 数据基准: PG daily_kline 全市场 + bi_trend V12→V13 P0-P2 迭代（commit b0d0189 / 545a4ab 等，6 月期间密集调参）

---

## 1. 总体结论

| 维度 | 评分 (1-5) | 说明 |
|---|---|---|
| **Kronos 模型可用性** | 3 | 服务能起来、能推理，但加载的是 HuggingFace 公开 `NeoQuasar/Kronos-mini`，不是自研 checkpoint；自研微调权重只有一个 demo 预测器（16MB）且 tokenizer 微调权重目录为空。 |
| **Kronos 模型有效性** | 2 | 推理路径真实，但 **Kronos 与 bi_trend 选股/回测完全解耦** —— bi_trend 不读 Kronos 预测，模型产出的 30 日 K 线未进入选股或回测任何环节。 |
| **bi_trend 策略可用性** | 4 | 代码结构完整、PG 取数与多档仓位/熔断/降权链路齐备，能跑出选股与回测。 |
| **bi_trend 策略有效性** | 2 | 六个月 V13 回测均值 +0.173%/trade、Sharpe-like ≈ 0.041、3/4/5 月为负；6 月 +1.60% 异常高，疑似样本内调参；无滑点/手续费/印花税；stop_loss=-12% 在 32 只触发 1 只，与"已教过的股"高度相关。 |
| **回测可信度** | 1.5 | 见 §4。**无交易成本 + 调参期样本 + 未加权累计口径 + 无幸存者偏差隔离**，指标无法对外承诺。 |

**一句话结论：当前这套"模型 + 策略"在现有回测口径下不足以产生可信 alpha —— Kronos 与选股解耦（零贡献），bi_trend 回测在去掉交易成本与样本内调参偏差后，6 个月聚合收益大概率归零甚至为负。**

**最薄弱环节**（优先级降序）：
1. 回测口径缺失交易成本 + 调参期样本内回测（系统性高估收益）。
2. Kronos 与 bi_trend 解耦，自研模型未落地到任何生产路径。
3. 训练管线默认走 synthetic 数据 + mock MLflow，无真实训练产物流。

---

## 2. Kronos 模型状态（事实核查）

### 2.1 Checkpoint 真实情况

| 路径 | 状态 | 证据 |
|---|---|---|
| `Kronos/outputs/models/finetune_tokenizer_demo/checkpoints/best_model/` | **目录为空**（仅 1 个 pytorch_model.bin 16MB 子文件缺失） | `ls -la` 确认 tokenizer demo 下无 checkpoint 文件 |
| `Kronos/outputs/models/finetune_predictor_demo/checkpoints/best_model/pytorch_model.bin` | 存在，16.46 MB | 仅 16MB，与公开 Kronos-mini 规模不符，疑似 demo 级玩具权重 |
| `Kronos/outputs/models/{catboost_ranker, lgbm_ranker, lgbm_ranker_v2, vq_fusion}` | 存在（LightGBM/CatBoost 排序器 + VQ 码本） | 这些是 kronos-factors 的因子排序器，**非 Kronos Transformer 自身** |

> **事实**：仓库内**没有可用的、自研的 Kronos Transformer checkpoint**。所谓"自研 Kronos K线预测 Transformer"在生产路径上跑的是第三方公开模型 `NeoQuasar/Kronos-mini`（HuggingFace）。

### 2.2 prediction-service (8002) 加载逻辑

`services/prediction-service/app/main.py:42-96` lifespan：

1. `KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")` —— 从 HF 拉公开 tokenizer（line 56）。
2. `Kronos.from_pretrained("NeoQuasar/Kronos-mini")` —— 从 HF 拉公开 base 模型（line 58）。
3. 尝试 overlay 自研权重：`ft_tok` / `ft_pred`（line 61-80）。
   - **tokenizer demo 目录为空** → `ft_tok` 分支永远走 else（用公开 tokenizer）。
   - **predictor demo 16MB 文件存在** → `ft_pred` 会 load 进去，但 16MB 相对 Kronos-mini（公开版通常数百 MB）可疑；不验证 shape 是否匹配，`load_state_dict` 无 `strict=False`，shape 不匹配会抛异常被外层 `except Exception` 吞掉（line 94-95），退化到纯公开模型。
4. `_model_loaded = True`（line 84）后调用 `_predictor.warmup`（line 92）。
5. 任何异常（含网络/shape/load 失败）→ `logger.warning` 后**继续启动**（line 95-96），`_model_loaded` 保持 `False`，路由返回 503。

**健壮性评估**：
- 降级行为合理（503 显式告警）。
- **缺陷**：load 失败被 `except Exception` 笼统吞掉，生产环境难以区分"无 checkpoint"vs"网络失败"vs"shape 不匹配"——观察性弱（违反 `.claude/standards/observability.md` 结构化日志要求）。
- **缺陷**：模型参数量、实际加载的 checkpoint 路径、fine-tuned 标志只在日志输出，无 metric 上报。

### 2.3 推理是否真实

`services/prediction-service/app/routes.py:206-269`（`/{code}/fast`）：

- 从 SQLite (`stock_screening.db`) 取 `daily_kline` → 喂入 `_m._predictor.predict_fast(...)` → 返回 `pred_trajectory`。
- 推理路径真实（调用 `_predictor.predict_fast`），不是模板/随机。
- **P3 后处理 hack**（line 240-251）：`adjusted_return_pct = pred_return + (auxiliary_score - 5) * 0.4`，把规则引擎（资金流/技术指标）的 ±2% 偏置加到 Kronos 输出上。Kronos 与"选股/回测"在这里没有任何交集 —— bi_trend 不调用 prediction-service，prediction-service 的 aux 评分也不被 bi_trend 使用。

### 2.4 数据源就绪性

- prediction-service 走 **SQLite** `Kronos/webui/stock_screening.db`（`_resolve_db_path` line 16-38），而 bi_trend 走 **PostgreSQL**。
- 两套数据源，列名/数据完整性可能不一致（CLAUDE.md 已记录 `pct_chg` vs `change_pct` 差异由 pg_adapter 转换，但 prediction-service 直接读 SQLite 不经 pg_adapter）。
- **风险**：prediction-service 与 bi_trend 看到的"同一只股票同一日"可能不一致，融合难。

---

## 3. bi_trend 策略分析（逻辑梳理 + 参数合理性）

### 3.1 战法核心理念（来源：`bi_trend_launch.py:1-21`）

"上升趋势中的洗盘回踩 → 高胜率买点"，由 4 个技术信号叠加触发：
1. **OBV > OBV_MA10 持续 N 天**（资金持续流入，趋势确认）
2. **WR 3 日内急跌**（价格快速回踩，洗盘而非反转）
3. **回踩缩量**（主力未出货）
4. 三者叠加 = 买点

### 3.2 评分维度（`_score_bi_trend_arrays`，launch 版 line 1035+）

| 因子 | 满分 | 实现位置 |
|---|---|---|
| OBV 趋势 | 32（含倒置：刚突破 +32，趋势尾部 +3） | line 1150-1178 |
| WR 三日轨迹 | 32（9 种模式：强势反转🔥🔥 到 假突破暴跌☠️） | line 1217-1239 |
| 缩量 | 8 | line 1294-1303 |
| 均线趋势 | 10 | line 1322-1338 |
| ADX 强度 | 8 | line 1348-1362 |
| 板块动量 | 7 | line 1364-1374 |
| 追高/派发/MA20 距离惩罚 | -6/-5/-4 | line 1273-1291, 1311-1320, 1340-1346 |
| 周线空头惩罚 | -6 | line 1376-1386 |
| 硬科技赛道加分 | +3 | line 1496 |
| 卡脖子稀缺 | +0/+1/+2 | line 939-948 |
| 点火/蓄力/压缩反转 | +4/+3/+8 | line 1409-1480 |
| 5 点 checklist | +3/+5 | line 1482-1493 |

**参数密度**：`bi_trend_launch.py` 单文件 ~1545 行（已截断，完整 2159 行），常量定义 100+ 个，权重 15+ 项。这是**强过拟合信号**——每个常量后面跟注释 "Vx: a→b (xx 教训)"，说明参数是**逐只股票 case-by-case 调出来的**。

### 3.3 V13 P0-P2 关键改动

| 改动 | 证据 | 合理性评估 |
|---|---|---|
| **P0: OBV=0 + 极端波动 → 直接淘汰**（新易盛教训） | launch.py:1117-1137 | 单点案例驱动，泛化性存疑；极端波动阈值 EXTREME_VOL_ANNUAL=100% 是硬切，相邻样本（99% vs 101%）命运迥异 |
| **P0: 弱市前 5 日单日跌 >8% → 跳过** | launch.py:910-921 | 合理（防接飞刀），但仅在 `breadth < 40` 生效，参数耦合 |
| **P1: S 级仓位降权 0.6x** | launch.py:1009-1010 | 自圆其说：H1 数据 S 胜率 47.4% < A 胜率 50.7%。**但回测脚本未将 weight 应用到 next_day_return**（见 §4.4） |
| **P1: 盘中止损模拟** | `tools/backtest_bi_trend.py:79-94` | 实现合理（跳空低开→开盘价止损；盘中触及→止损价） |
| **P2: 熔断后冷静期降仓** | launch.py:810-814, 851-854 | 合理，但 post_meltdown 判定依赖 `breadth_5d_list[1] < 18`，链式依赖脆弱 |
| **P2: 最低分散 5 只** | launch.py:849-850 | 合理（防单票暴雷） |
| **V12.2: TP 15%→20%/25%** | launch.py:1017-1023 | "网格搜索 216 种参数 → 最优解"——**这是典型样本内过拟合**（在 6 月数据上网格搜索出来的 TP 上 6 月回测表现最优，几乎必然） |
| **V12.2: 移除 -5%/-8% 误杀止损** | launch.py:144（DAY3_CHECK_LOSS_THRESHOLD -5→-10） | 同上，"全是误杀"是在 6 月样本上的结论 |

### 3.4 全市场版（`bi_trend_full_market.py`）与 launch 版差异

- 全市场：不限制硬科技，加 VR≥85 资金流向过滤，Top10 板块动量过滤。
- **代码重复严重**：launch 与 full_market 是两份 ~2100 行的近重复代码，参数漂移风险高（已观察到 `obv_score` 评分表两版不一致：launch 用倒置 32/26/20/16/12，full_market 在另一段用 35/32/28/22/15）。**单一可信源违反**（`.claude/standards/document-rules.md` SSOT）。

### 3.5 过拟合征兆汇总

1. 6 月一个月内有 **15 次 bi_trend commit**（commit 历史已调取），每次都以"教训股"命名（新易盛、中富通、川金诺、工业富联、华润微、强一、光迅科技、鼎通、立昂微、大唐、领先股份...）。
2. 回测脚本 `analyze_results` 把所有"教训股"作为 **top winners / top losers 展示**（line 226-237），形成调参反馈环。
3. 参数注释普遍写 "(xx 教训)" 或 "(回测: xx%)" —— **参数直接拟合历史样本**。

---

## 4. 回测有效性专项（**重点**）

### 4.1 回测口径

`tools/backtest_bi_trend.py:53-94` `get_next_day_return`：

- **入场**: T 日 `daily_kline.close`（收盘价）买入。
- **退出**: T+1 日 `daily_kline.close` 卖出（line 76）。
- **持仓周期**: 固定 1 个交易日（T→T+1）。
- **止损**: 仅当 `stop_loss_pct < 0` 时模拟盘中止损（line 79-91）。

> **核心问题**：策略代码（`bi_trend_launch.py:1000-1023`）声称 `hold_days` 为 3/5/7/10 天，TP 为 20%/25%，但**回测脚本完全不实现这些持有期与止盈逻辑**——只算 T+1 单日收益。`hold_days / take_profit / trailing_stop` 字段被写入 JSON（line 137-141）但从未参与收益计算。

### 4.2 前视偏差（look-ahead bias）核查

| 检查项 | 结论 | 证据 |
|---|---|---|
| 选股信号是否用 T 日及之前数据 | **无前视** | `_prefetch_kline_batch` 取 `trade_date <= trade_date` 的 K 线，`closes[-1]` 是 T 日收盘 |
| 入场价是否用 T 日收盘 | **无前视** | `entry_price = close[T]`（line 65） |
| 退出价是否用 T+1 收盘 | **无前视** | `next_row = SELECT ... WHERE trade_date > T ORDER BY trade_date ASC LIMIT 1`（line 68-72） |
| **同日信号+交易** | **潜在偏差** | 选股用 T 日收盘特征，**T 日收盘买入** = 用同一根 K 线收盘价同时决策与成交，现实中收盘瞬间无法成交（实际应在 T+1 开盘买入） |
| 涨跌比/熔断是否前视 | **潜在偏差** | line 666-678 的 breadth 用 T 日 vs T-1 日 close 比，但 breadth 是 T 日**盘后**才能算出的，T 日收盘买入时用 T 日 breadth 决策 = **决策时刻数据未就绪** |

### 4.3 数据泄露 / 幸存者偏差核查

| 检查项 | 结论 | 证据 |
|---|---|---|
| 股票池过滤 | `is_st=0 AND name NOT LIKE '%ST%'`（launch.py:866-870）—— **只看当前是否 ST**，不看历史是否曾被 ST 或已退市 → **存在幸存者偏差** | 2026 年 1 月回测时，用 2026-06 的 ST 状态过滤 2026-01 的股票池 |
| 退市股处理 | 未发现任何退市/暂停上市过滤逻辑 | grep `delist|退市|suspended|停牌` 在 bi_trend 源码 0 命中 |
| 停牌处理 | 未发现——`next_row` 取 `trade_date > T` 的下一条，若停牌可能跳到复牌后第一天（实际收益 ≠ 模拟） | line 68-72 |
| 复权处理 | 未在回测脚本核查到复权标志，`close` 是原始价还是前复权未注释 | 需 PG schema 确认 |

### 4.4 交易成本核查

```
grep -niE "commission|slippage|stamp_duty|手续费|印花税|滑点|过户费" \
  tools/backtest_bi_trend.py \
  packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py \
  packages/kronos-factors/kronos_factors/engine/bi_trend_full_market.py \
  services/backtest-service/app/*.py
→ 0 命中
```

**结论**：回测完全未模拟交易成本。A 股单边交易成本典型：
- 印花税 0.05%（卖出单边）
- 券商佣金 0.025%-0.03%（双边，含规费）
- 过户费 0.001%（双边，沪市）

**往返成本约 0.13%-0.16%**。V13 六个月聚合均值 +0.173%/trade，**扣除成本后 ≈ +0.04%/trade，已接近噪声水平**；3/4/5 月本身为负，扣成本后更负。

### 4.5 加权 vs 未加权口径不一致

`analyze_results`（line 207-224）的"每日加权均值"用 `np.average(dr, weights=weights)`，S 级 weight=0.6 已应用——**但这是打印日志的口径**。

导出到 JSON 的 `next_day_return`（line 290-291）是**未加权原始值**，`summary.valid` 也是未加权计数。下游聚合（本报告 §1 用的脚本）拿 JSON 算的是**未加权 sum/mean**，与策略声称的"S 级降权"逻辑**实际脱钩**——降权只在 stdout 显示，不进产物。

**实证**：Jun v13_final 未加权 mean = +1.604%，加权 mean 也 = +1.604%（weight 全为 1.0 或 0.6 计算结果相近，本批 S 级少）。

### 4.6 样本期与样本充分性

| 月份 | n_trades | win% | mean/trade | sum |
|---|---|---|---|---|
| 2026-01 | 199 | 48.7% | +0.324% | +64.38% |
| 2026-02 | 121 | 50.4% | +0.488% | +59.02% |
| 2026-03 | 119 | 38.7% | **-0.343%** | **-40.79%** |
| 2026-04 | 160 | 48.8% | **-0.043%** | **-6.90%** |
| 2026-05 | 133 | 45.9% | **-0.164%** | **-21.75%** |
| 2026-06 | 51 | 62.7% | **+1.604%** | +81.79% |
| **聚合** | **783** | **47.9%** | **+0.173%** | — |

- **6 月 n=51 异常少**（其他月 120-200），且 +1.60%/trade 是其他月份的 3-10 倍。
- **6 月正是 V12/V13 P0-P2 密集调参期**（commit 历史 15 次 bi_trend 改动集中在 6 月）→ **样本内回测**（in-sample），+1.60% 是调参目标函数的直接产物，**不能外推**。
- Sharpe-like（mean/std）= **0.041**，作为单 trade 风险调整后收益极低（典型有效策略 ≥ 0.5）。
- 月度方差极大（+0.49% 到 -0.34%，跨度 0.83pp），**无月份一致性**。

### 4.7 stop_loss 实际触发率

Jun v13_final: `stop_loss` 分布 `{None: 25, -12: 32}`，**32 只 -12% 止损中只有 1 只触发**（1/32 = 3%）。

- 说明 -12% 阈值对单日 T+1 收益几乎不生效（T+1 跌 12% 的股票极少）。
- 策略声称的"5 维卖出决策树 / 移动止盈 / 时间止损"在回测中**完全没有实现**（只实现了单日止损）。

### 4.8 回测有效性小结

| 偏差类型 | 是否存在 | 严重度 |
|---|---|---|
| 前视偏差（显式） | 否 | — |
| 前视偏差（隐式：同日信号+收盘成交；T 日 breadth 当日决策） | **是** | 中 |
| 数据泄露 | 未发现显式 | — |
| 幸存者偏差（用当前 ST 状态过滤历史） | **是** | 高 |
| 交易成本缺失 | **是** | **高**（吃掉全部 alpha） |
| 样本内调参（6 月密集调参 + 6 月回测） | **是** | **极高** |
| 持有期/止盈逻辑未实现 | **是** | 高（回测不代表策略声明） |
| 加权逻辑不进产物 | **是** | 中 |

---

## 5. 训练与因子管线状态

### 5.1 training-service (8008)

`services/training-service/app/training_engine.py:919-992`：

- 训练数据加载路径在 `_load_training_data`（未直接读到，从 line 919 推断），任何 ImportError / Exception → **fallback 到 `_generate_synthetic_data`**（line 920, 941, 948-952）。
- `_generate_synthetic_data`（line 955-992）：`np.random.seed(42)`，2000 条正态分布随机特征 + 线性合成 ret_5d/10d/20d/30d。
- **结论**：训练管线默认跑在合成数据上，产出的 ranker 模型学到的是"随机数据上的线性关系"，**无任何真实信号**。

### 5.2 MLflow / A/B 上线

`services/training-service/app/config.py:30-34`：
- `MLFLOW_TRACKING_URI` 默认 `http://localhost:5010`。
- `MLFLOW_MODE` 默认 **`"mock"`**（in-memory dict 存储，非真实 MLflow server）。

`mlflow_client.py:1-50`：`MockMlflowClient` 用 JSON 文件持久化 runs/models，**A/B 上线（`_evaluate_vs_production`，line 999-1056）的"production model"对比是在 mock 字典里比，不是真实流量对照**。

ADR-004 声称的 "A/B 上线" 在当前默认配置下是**纸面能力**。

### 5.3 因子 IC/ICIR 计算

`services/training-service/app/factor_calibration.py:60-163`：

- `compute_ic_from_db` 先尝试调 Kronos `tools/calibrate_weights.py` 的 `run_calibration`（line 80-105），对 500 只随机股票、3 个窗口（2/4/6 月）算 Rank IC。
- 失败则 fallback 到 `_compute_ic_fallback`（line 163+，numpy 实现）。
- **IC 计算逻辑真实存在**，但：
  - 样本仅 500 只随机股（非全市场）。
  - 窗口仅 3 个（统计意义弱，ICIR = ic_mean/ic_std 在 n=3 时极不稳定）。
  - **未观察到 IC 结果被 bi_trend 评分实际消费** —— bi_trend 的 100+ 常量是手调的，不来自 IC 加权。

### 5.4 因子定义位置

`packages/kronos-factors/kronos_factors/scorer/`:
- `advanced_factors.py`、`five_factor.py`、`screening_scorers.py`、`market_regime.py`、`kronos_prediction.py`、`adj_factor.py`。
- bi_trend 用的是 OBV/WR/ADX/MA 这些**经典技术指标**（`bi_trend_launch.py:258-321` 自实现），**不是 kronos-factors 包定义的因子**——两套因子体系并行，未统一。

---

## 6. 发现的问题（P0/P1/P2 分级）

### P0-1 回测未模拟交易成本，alpha 被成本吃光
- **证据**: `tools/backtest_bi_trend.py:53-94` `get_next_day_return` 无任何 commission/slippage 字段；全仓库 grep 0 命中。
- **影响**: V13 六个月聚合均值 +0.173%/trade，扣往返 0.13-0.16% 成本后 ≈ 0；3/4/5 月扣成本后亏损加深。**所有"回测盈利"的对外承诺都不可信**。
- **建议**: 在 `get_next_day_return` 出口加 `ret -= 0.13`（或可配置 `--cost-bps`），重跑全部历史回测。工作量 **S**。

### P0-2 6 月回测为样本内调参，+1.60%/trade 不可外推
- **证据**: commit 历史 6 月 15 次 bi_trend 改动（b0d0189, 545a4ab, 838c988, d3cfd83, 09a436c, f2427f4, a0f4d1e, 9e4e176, 225a305, eeb0c99, ...），每次以"教训股"驱动调参；6 月回测 +1.60% 是其他月 3-10 倍；Jun v13_final n=51（其他月 120-200）。
- **影响**: 调参目标函数 = 6 月回测收益，回测指标必然偏好。**真实样本外表现未知**。
- **建议**: 用 **walk-forward / rolling window** 替代整月回测：T-3 月调参 → T 月验证，滚动推进；冻结参数后跑 2025 年或更早未参与调参的样本。工作量 **M**。

### P0-3 Kronos 与选股/回测完全解耦，"AI 模型"零贡献
- **证据**: bi_trend 全部源码 grep `kronos|prediction|KronosPredictor` 0 命中；prediction-service 推理结果不被 bi_trend 消费；strategy-service 不调用 prediction-service。
- **影响**: 平台宣称的"AI 驱动量化"在选股链路上**名不副实**——bi_trend 是纯规则策略（OBV+WR+ADX），Kronos 只在前端"30 日 K 线预测"展示页用，与决策无关。
- **建议**: 要么 (a) 明确产品定位为"规则量化 + K 线可视化"，撤下"AI 选股"宣传；要么 (b) 把 Kronos 30 日预测作为 bi_trend 的一个评分维度（如 predicted_return > X 加分），并 A/B 验证增量。工作量 **L**。

### P1-1 回测未实现策略声明的持有期/止盈/移动止损
- **证据**: `bi_trend_launch.py:1000-1023` 声明 `hold_days=3/5/7/10`、`take_profit=20/25%`、`trailing_stop`，但 `tools/backtest_bi_trend.py:53-94` 只算 T+1 单日收益；`stop_loss=-12` 在 32 只中仅触发 1 只。
- **影响**: 回测指标 ≠ 策略实际行为；"5 维卖出决策树"在生产/回测两套口径。
- **建议**: 实现多日持有回测引擎，逐日检查止损/止盈/移动止盈触发。工作量 **M**。

### P1-2 幸存者偏差：用当前 ST 状态过滤历史股票池
- **证据**: `bi_trend_launch.py:867-870` `"WHERE is_st=0 AND name NOT LIKE '%ST%'"`——无时间戳过滤。
- **影响**: 2026-01 回测时，已戴帽股在 2026-01 仍被排除（实际 2026-01 可能未戴帽），样本被"未来信息"污染。
- **建议**: 在 `stocks` 表加 `st_history` 或按 `trade_date` 关联 ST 标记表（Tushare 有 `namechange`）。工作量 **M**。

### P1-3 训练管线默认走合成数据 + mock MLflow
- **证据**: `training_engine.py:919-992` 任何异常 fallback 到 `_generate_synthetic_data`（np.random.seed(42)）；`config.py:34` `MLFLOW_MODE="mock"` 默认。
- **影响**: 训练服务产出的 ranker 模型学的是随机噪声，A/B 上线对比在 mock 字典里跑——**整个训练子系统是 demo 态**。
- **建议**: (a) 缺真实数据时直接报错而非静默 fallback；(b) 部署真实 MLflow server，切 `MLFLOW_MODE=live`；(c) 至少加一条 e2e 测试断言"训练后 IC > 0"。工作量 **L**。

### P1-4 加权逻辑未进回测产物
- **证据**: `tools/backtest_bi_trend.py:290-291` 导出未加权 `next_day_return`；`analyze_results:220` 的 `np.average(dr, weights=weights)` 只进 stdout。
- **影响**: 下游聚合/报告无法复现"S 级降权"效果，策略声称的仓位管理与实际统计脱钩。
- **建议**: JSON 增加 `weighted_return` 字段，summary 用加权 sum。工作量 **S**。

### P2-1 launch / full_market 两份 2100 行重复代码，参数漂移
- **证据**: `bi_trend_launch.py` 与 `bi_trend_full_market.py` 结构近重复；`obv_score` 评分表两版不一致（launch: 32/26/20/16/12 倒置；旧段: 35/32/28/22/15）。
- **影响**: 维护成本翻倍，调一处漏一处；违反 SSOT。
- **建议**: 抽公共 `_bi_trend_core.py`，差异通过 config 注入。工作量 **M**。

### P2-2 prediction-service 与 bi_trend 数据源不一致（SQLite vs PG）
- **证据**: `routes.py:16-38` 读 SQLite `stock_screening.db`；bi_trend 读 PG。
- **影响**: 融合困难，列名/复权/完整性差异不可控。
- **建议**: prediction-service 改走 pg_adapter，与 bi_trend 同源。工作量 **S**。

### P2-3 Kronos 加载失败被笼统 except 吞掉
- **证据**: `main.py:94-95` `except Exception as e: logger.warning(...)` 不区分失败类型。
- **影响**: 生产排障困难，违反 observability.md 结构化日志要求。
- **建议**: 分类捕获（网络/shape/OOM），emit 结构化 metric。工作量 **S**。

### P2-4 参数密度过高，强过拟合信号
- **证据**: `bi_trend_launch.py` 100+ 常量，每个带 "(xx 教训)" 注释；6 月 15 次调参 commit。
- **影响**: 泛化性差，样本外大概率衰减。
- **建议**: 做参数敏感性分析（每个参数 ±20% 看收益变化），删除高敏感且无理论支撑的项。工作量 **M**。

---

## 7. 优化建议（优先级清单）

### 可信度提升（必须先做，否则任何性能优化都建立在沙地上）

| # | 建议 | 优先级 | 工作量 | 预期效果 |
|---|---|---|---|---|
| 1 | 回测加交易成本（P0-1） | **P0** | S | 暴露真实盈亏，大概率翻转结论 |
| 2 | Walk-forward 替代整月回测（P0-2） | **P0** | M | 得到样本外可信指标 |
| 3 | 实现多日持有 + 止盈/移动止损回测（P1-1） | P1 | M | 回测对齐策略声明 |
| 4 | 修复幸存者偏差（P1-2） | P1 | M | 避免系统性高估 |
| 5 | 加权逻辑进产物（P1-4） | P1 | S | 口径一致 |
| 6 | 冻结参数跑 2024-2025 样本外 | P1 | S | 验证泛化 |

### 性能提升（在可信度建立之后才有意义）

| # | 建议 | 优先级 | 工作量 | 预期效果 |
|---|---|---|---|---|
| 7 | Kronos 预测接入 bi_trend 评分（P0-3） | P1 | L | 真正实现"AI 驱动" |
| 8 | 训练管线接真实数据 + 真实 MLflow（P1-3） | P1 | L | ranker 模型可用 |
| 9 | launch/full_market 合并（P2-1） | P2 | M | 降维护成本 |
| 10 | 参数敏感性分析瘦身（P2-4） | P2 | M | 提升泛化 |

---

## 8. 未验证项

1. **PG daily_kline 是否前复权**——未确认 `close` 列语义，影响绝对收益与回测真实性。
2. **Kronos-mini 公开模型在 A 股的预测精度**——未跑预测精度评估（MAE/方向准确率），无法判断 P3 后处理 ±2% 偏置是否合理。
3. **strategy-service / trade-service 是否实际调用 bi_trend**——本次审计聚焦模型与策略本身，未追踪实盘执行链路；若 bi_trend 仅在 `tools/` 离线回测用，则影响范围限于决策支持，不涉真实资金。
4. **`_prefetch_kline_batch` 的具体 SQL 与 live_mode 分支**——未读到完整实现，无法 100% 排除 K 线取数层面的隐式前视（如取了 T 日盘中未来时段）。
5. **回测脚本 `analyze_results` line 444 `obv_score -= 5`**：`obv_score` 在该行尚未定义（line 446 才赋值），疑似 dead code 或 NameError 被 `except Exception: continue`（line 959-960）吞掉——若真触发异常，会**静默跳过本该入选的股票**，引入选择性偏差。需单测确认。
6. **训练服务的 `_load_training_data` 真实分支**——本次只确认了 fallback 到 synthetic，未验证真实分支在 PG 数据就绪时是否真的能跑出非平凡 IC。
7. **6 月 V13_final 与 v13 的差异**（+1.60% vs 未单独算 v13）——两份文件都存在但本次只深入 final，差异源未定位。

---

**报告结束。**
