# 速赢AI 模型 + 量化策略审计报告（2026-06-22 复审）

- 审计日期: 2026-06-22
- 审计人: AI 模型 + 量化策略审计专家（只读分析，未修改任何代码 / 未重训 checkpoint / 未重跑 SIT）
- 审计范围: `packages/kronos-{core,factors,data}`、`Kronos/`（含 `Kronos-uat-bak/` 训练备份）、`services/{prediction,training,backtest}-service`、`tools/backtest_bi_trend.py` + `tools/walk_forward.py`、bi_trend 策略引擎
- 关联前置: 本报告在 `docs/reviews/audit-model-2026-06-21.md`（昨日审计）之上做代码层根因深挖，重点回答 memory 记录的「bi_trend 样本外 -1.157%/月、Sharpe -3.178」的代码层根因
- 安全/铁律自检: 本次仅 Read 源码 + grep + ls，未 Edit 任何源码；未触发 trade-service / BrokerInterface；未运行任何训练 / 回测

---

## §1 概览

| 维度 | 问题数 | 说明 |
|---|---|---|
| **P0（数据泄露 / 模型实现错 / 导致亏损根因 / 回测前视）** | **6** | 见 §2 表格；其中 3 条直接坐实 bi_trend 样本外亏损根因 |
| **P1（训练管线缺陷 / 因子错 / 预测不一致）** | **6** | MLflow 默认 mock、Kronos 训练 placeholder、合成数据 fallback、横截面泄露等 |
| **P2（代码质量 / 可维护性）** | **4** | 死代码、观察性差、注释调参残留 |

**总评**：模型 + 量化策略层在「可信回测 → 可信样本外 → 可用模型」三个台阶上都站不住。bi_trend 的样本外亏损有**三层叠加根因**（详见 §3），Kronos 自研模型在生产路径上**根本不存在**（跑的是 HF 公开 base 模型），训练管线的 Kronos 分支是 placeholder + 合成数据。这套"模型 + 策略"链路在当前形态下**不具备产生 alpha 的工程基础**，与昨日审计结论一致并进一步坐实。

### 1.1 bi_trend 样本外亏损根因（独立结论）

memory 记录「bi_trend 样本外确定性亏 -1.157%/月、Sharpe -3.178」的**代码层根因有三层叠加**：

1. **参数从未来泄漏到过去（P0-M01，最致命）**：`walk_forward.py` 表面是"3+1 rolling 样本外"，实际循环里 `run_month(db, oos_month, ...)` 调用的是 **HEAD 版本** 的 `bi_trend_launch.py`——该版本是 2026-06 用 216 种网格搜索调参后才冻结的 V13 P2。也就是说"2024-01~2025-12 样本外回测"用的是 2026-06 的"最优"参数去回测**调参前**的时间段，等同于用未来信息决定过去交易。过拟合参数在样本外必亏——这是 -1.157%/月的**直接代码层根因**。
2. **成交假设前视（P1-M04）**：`get_next_day_return` 用 T 日 close 当作买入价（line 307），但 T 日 close 在物理上不可成交（信号需 T 日全市场 close 算完才能生成）。新版 `simulate_pick` 改 T+1 open 入场是对的方向，但单日口径仍存留作对比，导致两套口径混用。
3. **样本内调参污染（P0-M02，定性根因）**：`bi_trend_launch.py` line 1000-1023 大量 `V12.2: 网格搜索216种参数 → 最优解` / `V13 P1: H1数据 S胜率47.4%` / `V9.4: 立昂微06-02` 等注释，证实策略参数是用样本内（6 月 / H1）数据反复调出来的；用调参前的 V5.9（`--frozen`）跑同样 2024-2025 样本外仍是 -1.263%/月，说明参数本身就缺乏泛化能力。

**与昨日审计差异**：昨日结论是「无交易成本 + 调参期样本 + 未加权累计口径」系统性高估收益；本次进一步定位到 `walk_forward` 的"样本外"定义本身**有参数时序泄露**（用未来参数测过去）——这是比"样本内调参"更深一层的 bug。

---

## §2 问题清单

| 编号 | 标题 | 位置（file:line） | 严重度 | 描述 | 修复建议 |
|---|---|---|---|---|---|
| M01 | **walk_forward 样本外回测参数时序泄露** | `tools/walk_forward.py:173-182` | **P0** | 循环里 `run_month` 调 HEAD 版本 `bi_trend_launch.py`（V13 P2 调参后），等于用 2026-06 的参数测 2024-2025，参数从未来泄漏到过去。 | walk_forward 的 `run_month` 必须对每个 `oos_month` **checkout oos_month 时点的 `bi_trend_launch.py`** （`git show <commit-at-oos-month>:...`），而非用 HEAD。或显式记录每次样本外跑用的是哪个 commit 的策略模块，避免「样本外」定义被污染。 |
| M02 | **bi_trend 策略参数样本内调参残留** | `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:1000-1023` + 全文 `V12.2 网格搜索216种参数` / `V13 P1 H1数据` 等注释 | **P0** | 216 种参数组合在 1 个样本（6 月）上挑"最优"无任何统计显著性，必然样本外过拟合。memory 已定性决策"禁止再基于6月数据调参"，但代码里这套参数仍在生产路径上使用。 | (1) 把"个性化持有建议"hard-code 推回 V5.9 调参前参数（hold=5/tp=15/stop=-10）；(2) 删除所有"V12.2 网格搜索"注释；(3) 策略迭代流程改为**先 walk-forward 样本外验证再合入主干**（而非先合入再事后验证）。 |
| M03 | **backtest engine 时间泄漏（未来 K 线算历史因子）** | `packages/kronos-factors/kronos_factors/backtest/engine.py:501` + `packages/kronos-factors/kronos_factors/pg_adapter.py:138-160` | **P0** | `run_historical_backtest` 在每个月末 `batch_date` 调 `_get_market_data().get_kline_df(code, lookback=400)`，而 `pg_adapter.get_kline` 的 SQL 是 `ORDER BY trade_date DESC LIMIT lookback`——**没有 end_date 过滤**，永远取"当下"最近 400 天。2008 年的 batch_date 用的是 2024 年的 K 线数据算因子，IC 完全不可信。 | `get_kline` 必须接受 `end_date` 参数并 `WHERE trade_date <= end_date`；`run_historical_backtest` 传 `batch_date` 作为 end_date。此修复后所有历史 IC 数字会大幅变化，需重跑。 |
| M04 | **训练管线默认走 mock + synthetic 数据** | `services/training-service/app/training_engine.py:663-699`（Kronos placeholder）+ `:908-993`（fallback 合成数据）+ `services/training-service/app/mlflow_client.py:370-382`（mock 默认） | **P0** | `_train_kronos_sync` 是 `time.sleep(0.5)` + 假 loss 数列的 placeholder；`_prepare_training_data` 找不到 `train_data.pkl` 就 `_generate_synthetic_data`（np.random 造数 + label 公式与特征完全相关，IC 必接近 1.0）；`get_mlflow_client` 默认 mock 且 live 失败静默回退 mock。**Auto-deploy（line 842-848）会在合成数据上盲目上线模型**。 | (1) Kronos 训练分支要么实现要么在 UI/API 上明确标记 "未实现，禁用"；(2) `_prepare_training_data` 找不到真实数据应**抛异常**而非 fallback 合成；(3) MLflow mode 必须显式配置，live 失败应 fail-fast 而非静默 mock。 |
| M05 | **prediction-service 自研 checkpoint 永远加载不上** | `services/prediction-service/app/main.py:61-95` + `Kronos/outputs/models/`（目录不存在） | **P0** | `ft_tok` / `ft_pred` 路径指向 `Kronos/outputs/models/finetune_{tokenizer,predictor}_demo/checkpoints/best_model/pytorch_model.bin`，但 `Kronos/outputs/models/` **整个目录不存在**（`ls` exit 1）。生产 prediction-service 永远走 `else: logger.info("Using pre-trained ...")` 分支，加载的是 HF 公开 `NeoQuasar/Kronos-mini`。**"自研 Kronos K线预测 Transformer" 在生产路径上根本不存在**。 | 要么 (a) 真训一个自研 checkpoint 并落盘到正确路径 + 在 lifespan 里校验文件存在并上报 metric；要么 (b) 在 README / ADR-005 里把"自研 Kronos"措辞改为"基于公开 Kronos-mini 的托管推理服务"，停止宣称自研。当前形态对用户 / 投资决策构成信息误导。 |
| M06 | **训练集样本高度相关 + 横截面信息泄露** | `services/training-service/app/training_engine.py:223-337`（LightGBM）+ `Kronos/Kronos-uat-bak/src/kronos/finetune/dataset.py:50-75` | **P0** | (a) `_build_features_from_kline` 对单只股票的连续时间序列做 sliding window（相邻样本重叠 89/90），train IC 严重高估；(b) LightGBM 训练 `split_date = dates[int(len(dates) * (1-test_size))]` 按 date 切，但同一天不同股票的样本可能横跨 train/val——同日市场环境相同，val 标签与 train 高度相关，**横截面泄露**。 | (a) 引入样本间隔（如 sliding window step ≥ lookback/2）或按"股票 × 时间"双维度 group split；(b) val 必须是 train 之后**连续日期段**的所有样本（purge + embargo），不允许同日跨集。 |
| M07 | **prediction load_state_dict 无 strict=False + 异常被吞** | `services/prediction-service/app/main.py:70,77,94-95` | **P1** | `tokenizer.load_state_dict(torch.load(ft_tok))` 用默认 `strict=True`，shape 不匹配会抛异常，被外层 `except Exception` 一把吞掉，静默回退公开模型。生产无法区分"加载成功"vs"shape 不匹配静默回退"vs"网络失败"。 | (1) `load_state_dict(..., strict=False)` + 检查 missing/unexpected keys 并 log；(2) `except Exception` 拆分为 `(FileNotFoundError, RuntimeError, shape-mismatch)` 不同分支，各自 log 不同 metric；(3) 上报 `model_loaded_finetuned=true/false` Prometheus 指标。 |
| M08 | **bi_trend 单日回测口径成交价前视** | `tools/backtest_bi_trend.py:281-347`（`get_next_day_return` line 307 `entry_price = entry["close"]`） | **P1** | 信号需 T 日全市场 close 算完才能生成，物理上不可能以 T close 成交。新版 `simulate_pick` 已改 T+1 open 入场（正确），但 `get_next_day_return` 单日口径仍保留并与新口径混用（`analyze_results` 用 `ret_key` 区分），回测结果两套口径并存易混淆。 | 单日口径仅作向后兼容对比用，应在 `analyze_results` 输出 + JSON 导出里**显著标注 "单日口径含成交假设前视，仅对比用，禁止对外披露"**；生产口径只保留 `simulate_pick` 多日模式。 |
| M09 | **bi_trend 信号评分硬编码"川金诺/新易盛/立昂微"等个股教训** | `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:86, 410, 565, 575, 911, 166, 811`（多处） | **P1** | 参数注释带具体股票名 + 具体日期（`06-02`, `06-09`, `05-28`），说明这些阈值（`OBV_NEGATIVE_SKIP`, `MARKET_BREADTH_WEAK 35→25`, `max_drop_5d < -8` 等）是用**单只股票单日事件**反推出来的——单点过拟合，泛化性极差。 | 把所有"教训驱动"的阈值标记为 `# DEPRECATED: in-sample anecdote`，回到学术定义默认值；策略改进走 walk-forward 而非"教训打补丁"。 |
| M10 | **ONNX 导出 / 优化器全是 placeholder 死代码** | `services/prediction-service/app/onnx_optimizer.py:21-50`（全文件）+ grep 结果显示无任何调用方 | **P1** | `export_to_onnx` / `optimize_for_inference` / `quantize_int8` 函数体只有 `logger.info` + `raise RuntimeError("Placeholder")`，且 main.py / routes.py 从未 import 此模块。ADR-004 宣称 ONNX Runtime 加速，实际未实现。 | 要么实现并在 routes.py 接入，要么删除文件 + 从 ADR-004 删除 ONNX 相关 Decision。死代码误导"已优化"的印象。 |
| M11 | **Kronos 训练 train/val 划分依赖外部 pickle，无时间一致性保证** | `Kronos/Kronos-uat-bak/src/kronos/finetune/dataset.py:34-42` + `Kronos/Kronos-uat-bak/tools/prepare_finetune_data.py`（未审，但 dataset 直接读 train_data.pkl / val_data.pkl） | **P1** | `QlibDataset` 按 `data_type` 读不同的 pkl，**train/val 边界完全由 prepare 阶段决定**，dataset.py 不校验。若 prepare 把同一只股票的相邻时间窗口分别写 train / val pkl（极可能，因为 sliding window 跨边界），则相邻窗口重叠 89/90 导致 val loss 严重低估。 | prepare_finetune_data.py 必须按**时间切**（如 2020-2023 train / 2024 val），同一只股票的窗口不能跨 train/val；dataset.py 加载时校验"train 最大时间 < val 最小时间"。 |
| M12 | **`_evaluate_vs_production` 在 mock 模式下对比无意义** | `services/training-service/app/training_engine.py:996-1047` | **P1** | `verdict = "new_better" if ic_delta_pct >= 2 and icir_delta_pct > 0` —— 在 mock MLflow + 合成数据下 IC 必接近 1.0，`ic_delta_pct` 容易触发 ≥2% 阈值，导致 auto_deploy 在合成数据上盲目上线模型。 | (1) `_evaluate_vs_production` 加 `if MLFLOW_MODE != "live": skip auto_deploy`；(2) 阈值从 2% 改为**统计显著性检验**（Diebold-Mariano 或 bootstrap IC 置信区间）。 |
| M13 | **`calc_obv` / `calc_wr` O(N²) 实现且无边界保护** | `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:258-281`（calc_obv 用 Python for 循环）+ `:271-281`（calc_wr 内层 `np.max(highs[i-period+1:i+1])` 每次切片） | **P2** | 全市场 5000+ 只股票 × 每只 400 天循环，单次选股 O(stocks × days × period)；虽不致错，但每只股票算 WR 14 期在 Python 层有 N×period 次切片。 | 用 `pd.Series.rolling` 或 numpy 向量化重写；或在 `_prefetch_kline_batch` 后批量算。当前性能开销使回测一轮要数小时，阻碍 walk-forward 多次验证。 |
| M14 | **`_build_features_from_kline` 用 `score_fundamental("000001")` 硬编码大盘代码** | `services/training-service/app/training_engine.py:248` | **P2** | 对每只股票算特征时，`fund = score_fundamental("000001")` 永远传深发展代码，不是当前股票。fund_score 特征对全部样本是常数，对模型无信息量。 | 改为 `score_fundamental(sym)` 或删除 fund_score 特征。 |
| M15 | **bi_trend_launch.py 2158 行单文件，违反单一职责** | `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`（全文） | **P2** | 因子计算 + 评分 + 选股 + 市场环境 + 仓位管理 + 持有建议 + 个性化参数全堆在一个文件。任何一处改参数都需 grep 全文确认无副作用，是 M02/M09 过拟合难以治理的结构性原因。 | 拆为 `factors.py`（OBV/WR/ADX 纯函数）+ `scoring.py`（权重表）+ `screening.py`（选股 pipeline）+ `params.py`（所有可调参数集中，标注来源）；参数变更走 PR + walk-forward 验证。 |
| M16 | **`run_historical_backtest` 随机抽样 `random.seed(42)` 写死** | `packages/kronos-factors/kronos_factors/backtest/engine.py:459` | **P2** | 固定 seed 使每次跑都抽同一批股票，若这批股票恰好有利/不利，IC 数字会被这批样本绑架。 | 改为多 seed 平均（如 5 个 seed 各跑一遍取 IC 均值 ± std），或全市场计算（若性能允许）。 |

---

## §3 bi_trend 根因专项

### 3.1 三层叠加根因（按致命度降序）

#### 根因 A（P0，最致命）：walk_forward 参数时序泄露

**证据链**：

1. `tools/walk_forward.py:40-42` import：
   ```python
   from backtest_bi_trend import (  # noqa: E402
       setup_db, get_trading_days, run_backtest_day, simulate_pick,
   )
   ```
2. `run_backtest_day`（`tools/backtest_bi_trend.py:367-389`）里：
   ```python
   from kronos_factors.engine.bi_trend_launch import run_bi_screening
   top, all_scores, market_info = run_bi_screening(db, trade_date, top_n=top_n)
   ```
3. `run_bi_screening` 的实现在 `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:632`——**HEAD 版本**。
4. HEAD 版本的 `bi_trend_launch.py` 包含 V13 P2（line 810 `# V13 P2: 熔断后冷静期 — 昨日熔断→今日降仓防追反弹`）、V13 P1（line 1009 `# V13 P1: S级仓位降权 0.6x (H1数据: S胜率47.4% < A胜率50.7%)`）、V12.2（line 1000 `# V12.2: 个性化持有建议 (网格搜索216种参数 → 最优解)`）等调参后产物。
5. walk_forward 的循环 `for mi, oos_month in enumerate(sample_months)` 跑 2024-01~2025-12，但用的策略参数来自 2026-06 的 HEAD。

**推理链**：用 2026-06 调参后的参数回测 2024-2025 = 用未来信息决定过去交易。过拟合参数在样本外（其实不是真样本外，是被未来污染的"伪样本外"）必亏。

**为什么 `--frozen` 也亏（-1.263%/月）**：`--frozen` 用 V5.9 调参前参数，但 V5.9 本身也是用 2026-06 之前的数据调出来的（只是没做 216 网格搜索），参数缺乏泛化性，所以换个时间段（2024-2025）仍亏。这印证 memory 的"参数本身就不好"判断。

#### 根因 B（P0，定性）：策略参数样本内调参污染

**证据**：`bi_trend_launch.py` 全文 grep `网格搜索` / `H1数据` / `教训` / `V12.2` / `V13 P`，命中 30+ 处。典型：

- line 144: `DAY3_CHECK_LOSS_THRESHOLD = -10  # V12.2: -5→-10 (网格搜索: <-10%才需干预, 否则全是误杀)`
- line 166: `MARKET_BREADTH_WEAK = 25             # V9.4: 35→25, 减少误杀 (立昂微06-02:涨跌比27%)`
- line 211: `SELL_TIME_STOP_THRESHOLD = -5     # V12.2: -3→-5 (网格搜索: -3%太紧, 日内波动就触发)`
- line 1000-1023: `V12.2: 个性化持有建议 (网格搜索216种参数 → 最优解)`

**推理链**：每个参数都对应一次"在样本内（6月 / H1）发现某只股票亏损 → 调阈值消除这笔亏损"的微调。216 个参数在 1 个样本上挑"最优"无统计显著性（自由度 ≈ 样本数 - 参数数 ≈ 负数），必然过拟合。

#### 根因 C（P1）：单日回测口径成交假设前视

**证据**：`tools/backtest_bi_trend.py:281-347` `get_next_day_return`：
```python
entry_price = entry["close"]   # line 307 — T 日收盘价当买入价
...
exit_price = next_row["close"]  # line 329 — T+1 收盘价当卖出价
ret = (exit_price / entry_price - 1) * 100
```

**推理链**：T 日 close 是全市场收盘价，策略要在 T 日 15:00 收盘瞬间算完 OBV/WR/breadth（需扫全市场 5000 只股票 daily_kline JOIN）才能生成信号——**物理上不可能以 T close 成交**。这个口径会**系统性高估收益**（因为总是"事后知道 close"）。新版 `simulate_pick`（line 147-222）改 T+1 open 入场是正确方向，但单日口径仍保留对比，混用导致结果难解读。

### 3.2 为什么样本外确定性亏

把 A+B+C 叠加：

- A 让"样本外"名不副实（参数从未来泄漏到过去），所以"样本外"回测本质上是"用调参后参数测调参前数据"——过拟合参数在新数据上必亏。
- B 是 A 的根因——参数本身样本内过拟合。
- C 在单日口径下额外高估收益，掩盖了 B 的亏损；切到多日 T+1 open 口径（`simulate_pick`）后，前视红利消失，真实亏损暴露。

**结论**：bi_trend 在可信口径（扣 14bp + 后复权 + 多日持有 + T+1 open 入场）下 2024-2025 全样本外 24 月确定性亏 -1.157%/月、Sharpe -3.178，**代码层根因是参数样本内过拟合 + walk_forward 参数时序泄露**，不是模型或数据管道 bug。memory 的"阶段1优先于阶段2 / 不接 Kronos / 需根本重设"决策在代码层完全坐实。

---

## §4 修复优先级建议

### 必修（P0，阻断任何后续策略 / 模型迭代）

1. **M01 walk_forward 参数时序泄露** —— walk_forward 的 `run_month` 对每个 oos_month checkout 对应时点的 `bi_trend_launch.py`，否则"样本外"三个字就是假的。
2. **M03 backtest engine 时间泄漏** —— `get_kline` 加 `end_date` 参数；修完后所有历史 IC 数字重跑。这是 `kronos-factors/backtest/engine.py` 的根本性 bug，影响所有因子有效性判断。
3. **M04 训练管线 mock + synthetic 默认** —— 在 live MLflow + 真实数据就绪前，禁用 auto_deploy；`_prepare_training_data` 找不到数据抛异常而非 fallback 合成。
4. **M05 prediction-service 自研 checkpoint 不存在** —— 要么真训自研 checkpoint，要么把"自研 Kronos"措辞从所有文档删除。当前形态对投资决策构成信息误导。
5. **M06 训练样本相关性 + 横截面泄露** —— LightGBM/CatBoost 训练的 IC 数字在修复前全部不可信。
6. **M02 bi_trend 参数样本内调参残留** —— 推回 V5.9 调参前参数 + 删除"网格搜索"注释 + 策略迭代改 walk-forward 先行。

### 建议修（P1）

7. M07 prediction load_state_dict strict + 异常分类。
8. M08 单日回测口径标注"含前视，仅对比用"。
9. M09 bi_trend 删除"个股教训驱动"的阈值。
10. M10 ONNX 死代码清理或实现。
11. M11 Kronos 训练 prepare 阶段时间切校验。
12. M12 auto-deploy 阈值改统计显著性检验。

### 可缓（P2）

13. M13 calc_obv / calc_wr 向量化（性能）。
14. M14 `score_fundamental("000001")` 硬编码修正。
15. M15 bi_trend_launch.py 拆分（结构性）。
16. M16 run_historical_backtest 多 seed 平均。

---

## §5 链路完整性自检

- [x] bi_trend 信号生成无 look-ahead（`_prefetch_kline_batch` 用 `trade_date <= trade_date`，不含 T+1）—— 信号生成层无泄露。
- [x] Kronos Transformer 实现正确（causal mask + RoPE + KV-cache 增量推理均正确，复刻公开论文）—— 模型结构无 bug。
- [x] Kronos 训练侧 per-sample 标准化无未来泄露（`dataset.py:109-113` mean/std 只从 lookback 窗口算）—— 训练预处理无泄露。
- [x] `simulate_pick` 多日回测引擎逻辑正确（T+1 open 入场 + stop > TP > trailing 优先级保守 + 跳空按 open）—— 多日回测层无 bug。
- [ ] **bi_trend 策略参数无样本内过拟合** —— **不通过**，见 M02。
- [ ] **walk_forward 样本外定义无时序泄露** —— **不通过**，见 M01。
- [ ] **backtest engine 历史因子用历史 K 线** —— **不通过**，见 M03。
- [ ] **训练管线在真实数据 + live MLflow 上运行** —— **不通过**，见 M04。
- [ ] **生产 prediction-service 加载自研 checkpoint** —— **不通过**，见 M05。

5 项关键链路自检 4 项不通过，模型 + 量化策略层**不具备产生可信 alpha 的工程基础**。

---

## §6 与昨日审计（2026-06-21）的差异

| 维度 | 昨日（2026-06-21） | 今日（2026-06-22） |
|---|---|---|
| Kronos 模型可用性 | 跑 HF 公开 base + 16MB demo predictor | **确认 `Kronos/outputs/models/` 整个目录不存在**，prediction-service 永远走 `else` 分支，自研模型零落地（M05 升级证据） |
| Kronos 模型有效性 | 与 bi_trend 解耦 | 同；额外确认 ONNX 优化器全 placeholder + 死代码（M10） |
| bi_trend 策略有效性 | 6 月 +1.60% 疑似样本内调参 | **定位到 walk_forward 参数时序泄露代码证据（M01）** + 策略参数样本内调参注释铁证（M02），坐实 -1.157%/月根因 |
| 回测可信度 | 无交易成本 + 调参期样本 + 未加权累计 | **额外发现 backtest engine 时间泄漏（M03）** —— `get_kline` 无 end_date 过滤，历史 IC 全部不可信 |
| 训练管线 | 默认 synthetic + mock MLflow | 同；额外发现 `_build_features_from_kline` 用 `score_fundamental("000001")` 硬编码（M14）+ 横截面泄露（M06） |

昨日审计的结论（"这套模型+策略不足以产生可信 alpha"）在今日代码层根因深挖后**完全坐实并进一步恶化**。

---

*报告结束。本报告仅做代码层只读审计，所有修复建议待 product-lead 重派给执行层（backend-dev / ai-agent-dev / ml-engineer）实施。*
