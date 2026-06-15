# pgvector + 因子快照自学习系统 — 架构设计

> 版本: V1.0 | 日期: 2026-06-15 | 适用范围: 全部选股模型

---

## 1. 设计目标

为全部选股模型（秋神系列 5 个 + 匪爷系列 3 个 + 未来新增模型）建立统一的因子快照自学习系统：

1. **因子快照**: 每次选股时，自动记录所有因子的原始值 + 模型输出
2. **相似检索**: 基于 pgvector，在新选股时检索历史上最相似的 K 个案例
3. **结果反馈**: 次日收盘后自动回写实际收益，构建标注数据集
4. **自动训练**: 样本积累到阈值后，自动触发 LightGBM/XGBoost 重训练
5. **多模型共享**: 因子定义由各模型自行注册，系统不绑定因子 schema

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        选股模型层                               │
│  秋神竞价 │ 秋神盘后 │ 秋神盘中 │ 秋神尾盘 │ 秋神选债 │ 匪爷系列 │
└──────────┴─────────┴─────────┴─────────┴─────────┴──────────┘
                              │
                    ┌─────────▼─────────┐
                    │  FactorRecorder   │  ← 自动记录因子快照
                    │  (每次选股后调用)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   PostgreSQL      │
                    │   + pgvector      │
                    │                   │
                    │  factor_snapshots  │  ← 因子向量 + 元数据
                    │  model_registry   │  ← 模型注册
                    │  daily_outcomes   │  ← 次日收益反馈
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
     │ Similarity    │ │ AutoTrain   │ │ Dashboard   │
     │ 相似案例检索   │ │ 自动重训练   │ │ 模型监控     │
     └───────────────┘ └─────────────┘ └─────────────┘
```

---

## 3. 数据库设计

### 3.1 启用 pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3.2 model_registry（模型注册表）

```sql
CREATE TABLE model_registry (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL UNIQUE,   -- 'leader_intraday_v7'
    display_name    VARCHAR(128),                   -- '秋神龙头战法-盘中 V7.0'
    category        VARCHAR(32),                    -- '秋神' / '匪爷' / '大葱'
    factor_keys     TEXT[] NOT NULL,               -- ['gain_14','sector_leader_score',...]
    factor_dim      INTEGER NOT NULL,              -- 向量维度
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);
```

### 3.3 factor_snapshots（因子快照表）

```sql
CREATE TABLE factor_snapshots (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,           -- 关联 model_registry
    trade_date      DATE NOT NULL,                  -- 选股日期
    stock_code      VARCHAR(10) NOT NULL,           -- 股票代码
    time_slot       VARCHAR(5),                     -- 选股时点 '14:40'
    
    -- 因子原始值 (JSONB, 灵活 schema)
    factors         JSONB NOT NULL,                 -- {"gain_14":10.5, "leader":24, ...}
    factor_vector   vector(32),                    -- pgvector 向量 (维度=model_registry.factor_dim)
    
    -- 模型输出
    total_score     DOUBLE PRECISION,              -- 模型总分
    grade           VARCHAR(2),                     -- S/A/B/C
    rank_in_day     INTEGER,                        -- 当日排名
    
    -- 结果反馈 (T+1 回写)
    next_day_return DOUBLE PRECISION,              -- 次日实际收益
    is_win          BOOLEAN,                        -- 是否盈利
    outcome_at      TIMESTAMP,                      -- 结果回写时间
    
    created_at      TIMESTAMP DEFAULT NOW(),
    
    -- 索引
    CONSTRAINT fk_model FOREIGN KEY (model_name) REFERENCES model_registry(model_name)
);

CREATE INDEX idx_snapshots_model_date ON factor_snapshots(model_name, trade_date);
CREATE INDEX idx_snapshots_stock ON factor_snapshots(stock_code, trade_date);
CREATE INDEX idx_snapshots_outcome ON factor_snapshots(model_name) WHERE next_day_return IS NOT NULL;
```

### 3.4 daily_outcomes（每日结果汇总）

```sql
CREATE TABLE daily_outcomes (
    id              SERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    model_name      VARCHAR(64) NOT NULL,
    total_picks     INTEGER,                       -- 当日选股数
    win_count       INTEGER,                       -- 盈利数
    avg_return      DOUBLE PRECISION,             -- 平均收益
    cum_return      DOUBLE PRECISION,             -- 累计收益
    market_breadth  DOUBLE PRECISION,             -- 市场涨跌比
    sh_index_change DOUBLE PRECISION,             -- 上证涨跌
    
    UNIQUE(model_name, trade_date)
);
```

### 3.5 model_versions（模型版本演进）

```sql
CREATE TABLE model_versions (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(64) NOT NULL,
    version_tag     VARCHAR(32) NOT NULL,          -- 'V7.0' / 'V8.0'
    snapshot_count  INTEGER,                       -- 该版本的快照数
    win_rate        DOUBLE PRECISION,             -- 胜率
    mean_return     DOUBLE PRECISION,             -- 均值
    cum_return      DOUBLE PRECISION,             -- 累计
    is_current      BOOLEAN DEFAULT FALSE,
    deployed_at     TIMESTAMP DEFAULT NOW()
);
```

---

## 4. 核心服务

### 4.1 FactorRecorder（因子快照记录器）

```python
# packages/kronos-factors/kronos_factors/recorder.py

class FactorRecorder:
    """选股后自动记录因子快照。"""
    
    def record_picks(model_name: str, trade_date: str, time_slot: str, picks: list[dict]):
        """记录一批选股结果的因子快照。
        
        Args:
            model_name: 'leader_intraday_v7'
            trade_date: '2026-06-15'
            time_slot: '14:40'
            picks: [{code, total_score, grade, gain_14, sector_leader_score, ...}, ...]
        """
        # 1. 查询或注册模型
        # 2. 构建 factor_vector (标准化 + pgvector)
        # 3. 批量 INSERT INTO factor_snapshots
        pass
    
    def backfill_outcomes():
        """回写最近 N 天快照的次日收益。每日收盘后自动调用。"""
        pass
    
    def find_similar(model_name: str, factors: dict, k: int = 10) -> list[dict]:
        """检索历史上因子最相似的 K 个案例及其收益。
        
        Returns: [{stock_code, trade_date, similarity, next_day_return, is_win}, ...]
        """
        # SELECT *, 1 - (factor_vector <=> $1) AS similarity
        # FROM factor_snapshots
        # WHERE model_name = $2 AND next_day_return IS NOT NULL
        # ORDER BY factor_vector <=> $1 LIMIT $3
        pass
```

### 4.2 AutoTrainer（自动训练器）

```python
# packages/kronos-factors/kronos_factors/autotrain.py

class AutoTrainer:
    """当标注样本积累到阈值时，自动训练 LightGBM 排序模型。"""
    
    SAMPLE_THRESHOLD = 500  # 最小训练样本数
    
    def check_and_train(model_name: str):
        """检查是否需要重新训练。"""
        # 1. SELECT COUNT(*) FROM factor_snapshots 
        #    WHERE model_name = $1 AND next_day_return IS NOT NULL
        # 2. 如果 >= 500，提取 factor_vector → X, next_day_return → y
        # 3. 训练 LightGBM ranker
        # 4. 保存模型到 outputs/ml/{model_name}_{version}.pkl
        # 5. 更新 model_versions
        pass
    
    def predict_win_prob(model_name: str, factors: dict) -> float:
        """预测次日盈利概率 (0-1)。"""
        pass
```

### 4.3 与选股模型的集成点

每个模型的 `run_*_screening()` 函数末尾增加：

```python
# 记录因子快照 (非侵入式, 失败不影响选股)
try:
    from kronos_factors.recorder import FactorRecorder
    FactorRecorder.record_picks(
        model_name='leader_intraday_v7',
        trade_date=trade_date,
        time_slot=time_slot,
        picks=top_picks
    )
except Exception:
    pass  # 记录失败不影响选股主流程
```

每天收盘后（L4 scheduler 凌晨 04:00）自动运行：

```python
# 回写结果 + 检查重训练
FactorRecorder.backfill_outcomes()
AutoTrainer.check_and_train('leader_intraday_v7')
```

---

## 5. 实施计划

### Phase 1：基础设施（1-2 天）

| 步骤 | 内容 |
|:--:|------|
| 1.1 | PostgreSQL 安装 pgvector 插件 |
| 1.2 | 创建 4 张表（model_registry, factor_snapshots, daily_outcomes, model_versions） |
| 1.3 | 实现 `FactorRecorder` 基础功能（record_picks + backfill_outcomes） |

### Phase 2：接入现有模型（1 天）

| 步骤 | 内容 |
|:--:|------|
| 2.1 | 秋神盘中 V7.0 接入 FactorRecorder |
| 2.2 | 秋神尾盘 V3.0 接入 |
| 2.3 | 秋神盘后接入 |
| 2.4 | 秋神竞价接入 |
| 2.5 | 回填历史 71 天数据（291 笔因子快照） |

### Phase 3：相似检索 + 预测（2 天）

| 步骤 | 内容 |
|:--:|------|
| 3.1 | 实现 `find_similar()` — 基于 pgvector 余弦相似度 |
| 3.2 | 在盘中模型预测时，检索 Top 10 相似案例 |
| 3.3 | 基于相似案例胜率，调整当前评分（置信度加权） |

### Phase 4：自动训练（1-2 天）

| 步骤 | 内容 |
|:--:|------|
| 4.1 | 实现 LightGBM Ranker 训练 |
| 4.2 | 设置 500 样本自动触发阈值 |
| 4.3 | 模型版本管理 + A/B 对比 |

### Phase 5：匪爷模型接入（1 天）

| 步骤 | 内容 |
|:--:|------|
| 5.1 | cb_floor / cb_intraday 接入 |
| 5.2 | short / long / chokepoint 接入 |

---

## 6. 因子向量构建规范

### 标准化方法

每个因子在写入向量前进行 Z-score 标准化（按模型、按日期）：

```python
# 当日所有 picks 的因子值
values = [pick['gain_14'] for pick in day_picks]
mean = np.mean(values)
std = np.std(values)
normalized = [(v - mean) / std for v in values]
```

### 向量维度

| 模型 | 因子数 | 向量维度 |
|------|:--:|:--:|
| leader_intraday | 15 | 32 (填充到 2^n) |
| leader_scalp | 9 | 16 |
| leader_auction | 5 | 8 |
| leader_closing | 15 | 32 |
| cb_floor | 6 | 8 |
| cb_intraday | 6 | 8 |

维度不足 2^n 的用 0 填充，确保 pgvector 索引效率。

---

## 7. 预期收益

| 时间 | 样本量 | 能力 |
|------|:--:|------|
| 立即 | 291 笔 | 历史回填，启用相似检索 |
| +2 月 | ~500 笔 | 首次 LightGBM 自动训练（预测胜率 AUC 预计 0.55-0.60） |
| +6 月 | ~1000 笔 | 模型显著优于规则引擎，AUC 预计 0.60+ |
