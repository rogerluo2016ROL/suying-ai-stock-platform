# Packages — Phase 0 代码提取

> 从 Kronos 旧项目中提取的纯逻辑代码，独立为可测试、可复用的 pip 包。

## 已提取

```
packages/
├── kronos-factors/           # 选股因子 + 策略引擎 + 回测
│   └── kronos_factors/
│       ├── scorer/            # 25 个因子评分函数
│       │   ├── five_factor.py      # M/V/T/Q/R 五因子 (from screener_service.py)
│       │   ├── advanced_factors.py # 7 个高级因子 (from advanced_models.py)
│       │   │   ├── score_money_flow()
│       │   │   ├── score_mean_reversion()
│       │   │   ├── score_trend_strength()
│       │   │   ├── score_reversal()
│       │   │   ├── score_liquidity()
│       │   │   ├── score_hard_tech()
│       │   │   ├── get_tushare_scores()
│       │   │   └── run_multi_model()
│       │   └── screening_scorers.py # 短线/长线/成长/辨识度/融资动量 (from screening_top50.py)
│       ├── engine/            # 6 套策略引擎
│       │   ├── leader_scalp.py      # 龙头战法 (收盘后, 1934行)
│       │   └── leader_intraday.py   # 龙头战法 (盘中, 685行)
│       ├── backtest/          # 回测引擎
│       │   ├── engine.py            # IC/ICIR/Hit Rate (from backtest_engine.py)
│       │   ├── calibration.py       # 因子权重校准 (from calibrate_weights.py)
│       │   └── forward.py           # 前向回测 (from forward_backtest.py)
│       └── tests/
│
├── kronos-core/              # Kronos K线基础模型
│   └── kronos/
│       ├── model/
│       │   ├── kronos.py           # Kronos + Tokenizer + Predictor (758行)
│       │   ├── module.py           # TransformerBlock 等底层模块 (634行)
│       │   └── __init__.py         # model_dict, get_model_class
│       └── __init__.py             # v0.2.0, AAAI 2026
│
└── kronos-data/              # 数据管道
    └── kronos_data/
        ├── etl.py                  # Tushare 同步管线 (1329行)
        ├── models.py               # SQLite 数据库模型 48张表 (888行)
        ├── market_data.py          # 行情数据服务 + mootdx/akshare (717行)
        └── adapters/
```

## 提取状态

| 源文件 | 目标文件 | 状态 |
|--------|---------|:--:|
| webui/services/screener_service.py | scorer/five_factor.py | ✅ |
| webui/services/advanced_models.py | scorer/advanced_factors.py | ✅ |
| tools/screening_top50.py | scorer/screening_scorers.py | ✅ |
| tools/leader_scalp.py | engine/leader_scalp.py | ✅ |
| tools/leader_scalp_intraday.py | engine/leader_intraday.py | ✅ |
| webui/services/backtest_engine.py | backtest/engine.py | ✅ |
| tools/calibrate_weights.py | backtest/calibration.py | ✅ |
| tools/forward_backtest.py | backtest/forward.py | ✅ |
| src/kronos/** | kronos-core/kronos/** | ✅ |
| tools/tushare_sync.py | kronos-data/etl.py | ✅ |
| webui/services/database.py | kronos-data/models.py | ✅ |
| webui/services/market_data_service.py | kronos-data/market_data.py | ✅ |

## 下一步 (Phase 1)

- 提取后清理：移除死代码、统一接口、写单元测试
- 创建 engine base class (StrategyEngine ABC)
- 创建 engine/short_mode.py, long_mode.py, all_mode.py (from screening_top50.py mode 分支)
- 创建顶层 pyproject.toml (monorepo workspace)
- 在每个包上运行 `pytest`
- 旧项目中的原文件不受影响，继续正常运行
