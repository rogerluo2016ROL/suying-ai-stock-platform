# ADR-004: 模型训练管线

- 状态：Proposed
- 日期：2026-06-10
- 决策者：tech-lead
- 影响范围：新增 training-service + 现有 Kronos `tools/` 工具升级为服务化 + MLflow 基础设施

## 上下文

速赢 AI 证券投资管理平台的选股/排序/回测能力依赖 3 个模型：12 因子等权投票筛选（`screening_top50.py`）、LightGBM LambdaRank 排序（`train_lgbm_ranker.py`）、CatBoost 回归（`train_catboost.py`）。因子权重校准依赖 `calibrate_weights.py` 的 IC/ICIR 分析。目前所有训练和校准均为手动执行 CLI 脚本，模型文件散落在 `outputs/models/` 目录，无版本管理、无 A/B 切换、无自动调度。

PRD AC-6.1~6.9 要求实现：管理员手动/自动触发训练（LightGBM / CatBoost / Kronos Fine-tune）、训练过程可视化、新老模型自动评估对比、管理员一键 A/B 上线、失败保留旧模型并记录原因、因子权重每周自动校准、训练历史全链路追溯、仅管理员可访问。

现有资产评估：
- `tools/train_lgbm_ranker.py`：LightGBM binary classification，13 特征，200 boost rounds，特征工程内嵌，输出到 `outputs/models/lgbm_ranker/`
- `tools/train_catboost.py`：CatBoost 回归，19 特征（含 P0 优化），300 trees，样本权重策略，输出到 `outputs/models/catboost_ranker/`
- `tools/calibrate_weights.py`：14 因子 IC/ICIR 滚动窗口（3 窗口 × 500 样本），输出权重建议到 JSON
- `services/training-service/`：空壳目录，尚未创建任何代码

不做此决策的后果：模型退化无法感知（市场风格切换后旧模型失效）；因子权重偏离市场迟迟不更新；训练脚本散落、无统一入口、无法追溯；新模型上线全靠人工对比和手工替换文件，易出错且不可回滚。

## 决策

### 决策 1：训练调度 — APScheduler vs Celery Beat

| 维度 | 选型 | 理由 |
|------|------|------|
| 调度框架 | **APScheduler 3.x（AsyncIOScheduler）** | 轻量进程内调度，无需额外 Broker/Worker 进程。PRD AC-6.2 要求"每周六凌晨自动训练"，任务量低（每周 1-3 次训练 + 1 次校准），不需要 Celery 的分布式能力。与 FastAPI training-service 原生集成（`asyncio` 事件循环复用）。否决 Celery Beat：需引入 RabbitMQ/Redis Broker + Celery Worker 进程 + Celery Beat 调度器，基础设施复杂度增长 3 倍，而当前训练任务量远未达到需要分布式队列的门槛 |
| 任务持久化 | **PostgreSQL job_store** | 利用现有 docker-compose 中的 PostgreSQL 15，训练任务状态可查询、重启不丢失。备选 SQLite job_store：单机够用但无法复用现有数据库连接池，增加 State 碎片 |
| 触发方式 | **Cron（APScheduler）+ API 手动触发** | 覆盖 AC-6.1（手动）和 AC-6.2（定时）。APScheduler 的 `CronTrigger` 天然支持 `day_of_week='sat' hour=2`，API 触发通过 `POST /api/v1/training/trigger` |

### 决策 2：超参搜索 — Optuna vs 网格搜索

| 维度 | 选型 | 理由 |
|------|------|------|
| 搜索策略 | **Optuna 3.x（TPE sampler）** | Tree-structured Parzen Estimator (TPE) 贝叶斯优化，搜索效率远高于网格搜索。LightGBM 超参空间（`num_leaves`, `learning_rate`, `feature_fraction`, `bagging_fraction`, `min_data_in_leaf`）和 CatBoost 超参空间（`iterations`, `depth`, `learning_rate`, `l2_leaf_reg`）均为连续 + 离散混合，网格搜索在 5+ 维空间组合爆炸。PRD 明确写"Optuna 超参搜索"（Phase 3 功能清单）。否决网格搜索：5 参数 × 5 取值 = 3125 次训练，单次 LightGBM 训练 ~60s，总耗时 52 小时不可接受。Optuna 通常 50-100 trials 即可收敛 |
| 目标函数 | **验证集 Rank IC** | Rank IC（Spearman 相关系数）直接衡量排序质量，与业务目标（Top 30 超额收益）一致。备选：验证集 AUC——但分类精度不等于排序质量 |
| 剪枝 | **MedianPruner** | 训练过程中 trial 的中间结果低于已有 trials 中位数 → 提前终止，节省 30-50% 搜索时间 |

### 决策 3：模型注册 — MLflow vs 自建

| 维度 | 选型 | 理由 |
|------|------|------|
| 注册中心 | **MLflow Tracking + Model Registry** | 覆盖 AC-6.4（自动评估对比）、AC-6.5（A/B 切换）、AC-6.8（训练历史可追溯）。MLflow 提供：实验跟踪（参数/指标/产物自动记录）、模型版本管理（Stage: Staging → Production → Archived）、模型签名（输入/输出 schema）、REST API 查询。PRD 明确写"MLflow 集成"。否决自建：自建需实现实验存储、指标对比 UI、版本切换、模型服务等，工作量 >2 人月，且 MLflow 已是 Python ML 生态的事实标准 |
| 部署方式 | **MLflow Tracking Server（本地） + PostgreSQL backend store + 本地文件系统 artifact store** | 与现有基础设施一致（复用 docker-compose Postgres），无需引入 S3/MinIO。artifact 存于 `outputs/mlflow-artifacts/`，Kronos 和 training-service 共享同文件系统 |
| 模型格式 | **LightGBM `.txt` + CatBoost `.cbm` + MLflow pyfunc wrapper** | 原生格式保留框架特定优化；pyfunc wrapper 提供统一 `predict()` 接口，解耦推理代码与模型实现 |

### 决策 4：A/B 上线 — 手动切换 vs 蓝绿部署

| 维度 | 选型 | 理由 |
|------|------|------|
| 切换机制 | **MLflow Model Registry Stage 切换 + 手动管理员确认** | AC-6.5 明确要求"管理员一键上线"——这是人审批 + 系统执行的混合模式，不是全自动。流程：训练完成 → 自动评估（新模型 vs 生产模型在回测集上的 Rank IC 对比）→ 生成评估报告 → 管理员审查 → 调用 `transition_model_version_stage(name, version, "Production")` → 推理服务自动加载新 Production 模型。否决蓝绿部署：蓝绿部署（两套完整推理服务同时运行 → 流量切换）适用于在线推理的零停机切换，但本系统选股/排序是批量离线推理，无需流量切换，MLflow Stage 切换即可满足 |
| 回滚 | **MLflow Stage 回退到上一 Production 版本** | AC-6.6："新模型不如旧模型 → 保留旧模型，记录失败原因"。MLflow 保留所有历史版本，`transition` 到 `Archived` 并恢复旧版本 `Production` 标签。操作记录写入 MLflow 的 model version description |
| 评估标准 | **Rank IC 提升 ≥ 2% 且 Top30 超额收益未恶化** | 量化门禁，避免主观判断。连续 2 周回测集上均满足 → 推荐上线 |

### 决策 5：校准策略 — 事件驱动 vs 定时

| 维度 | 选型 | 理由 |
|------|------|------|
| 触发方式 | **定时（每周五收盘后 Cron）** | AC-6.7："基于最新 IC/ICIR 数据，每周自动更新"。因子 IC 变化是缓慢漂移（周级别），不需要事件驱动（如新数据到达立即重算）的实时性。每周五 15:30（收盘后 30 分钟）触发校准，计算结果写入 `factor_weights` 表，`screening_top50.py` 下次运行时自动读取最新权重。否决事件驱动：需要监听数据更新事件、维护事件总线、处理乱序和幂等，复杂度远超收益 |
| 权重生效 | **数据库驱动，推理时自动读取最新生效权重** | `factor_weights` 表记录 `(factor_name, weight, calibrated_at, effective_from)`，选股服务读取 `effective_from <= NOW()` 的最新记录。避免修改 Python 源代码文件的脆弱模式 |
| 人工兜底 | **管理员可通过 API 手动覆盖单因子权重** | 防止极端行情下 IC 失真导致自动校准偏离，保留人工干预通道 |

### 决策 6：训练硬件 — CPU vs GPU

| 维度 | 选型 | 理由 |
|------|------|------|
| 硬件 | **CPU（多核）** | LightGBM 和 CatBoost 均为 CPU 优化的梯度提升树模型（基于直方图算法），GPU 加速收益有限（LightGBM GPU 版仅对超大数据集 >1M 行有明显优势）。当前训练数据规模：200-3000 只股票 × ~500 窗口 × 13-19 特征 = 10 万-150 万行，CPU 训练时间 60-200s。GPU 需额外硬件成本（云 GPU ~3-5 元/小时 vs CPU 0.3 元/小时），且当前训练频率低（每周 1-3 次），ROI 不值得。否决 GPU：额外成本 + 部署复杂度（CUDA 依赖、GPU 驱动、容器 GPU passthrough），无显著加速收益 |
| 并行策略 | **LightGBM `num_threads=4` + CatBoost `thread_count=4`，单机多核** | 利用现有服务器 4-8 核 CPU，训练服务配置 `OMP_NUM_THREADS=4` 避免过度竞争。未来如需扩大数据量，优先扩展到 16 核 CPU 而非上 GPU |
| 例外 | **Kronos Fine-tune（Transformer）预留 GPU** | PRD AC-6.1 提到"Kronos Fine-tune"（基于 Transformer 的时间序列预测模型），Transformer 训练确实收益于 GPU。此部分不在本次 ADR 覆盖范围，待 Kronos Fine-tune 可行性验证后由独立 ADR 决策 |

## 备选方案

- **A. Celery Beat + Redis 调度** — 分布式能力强，适合高频/多任务场景。否决理由：当前训练任务量低（每周 3-4 次），引入 Redis + Celery Worker + Celery Beat 三组件运维成本与收益不匹配；未来任务量增长时可迁移，APScheduler → Celery 迁移成本低（均为 Python 生态）
- **B. 网格搜索超参** — 简单、确定性强。否决理由：5 维参数空间组合爆炸，单次完整搜索需数十小时，不可行
- **C. 自建模型注册** — 完全掌控、无外部依赖。否决理由：重复造轮子，实验对比 UI、版本管理、API 均为通用需求，MLflow 已成熟且 PRD 明确提到
- **D. GPU 训练** — 训练速度快。否决理由：LightGBM/CatBoost 为 CPU 优化模型，GPU 加速有限；增量成本不划算

## 影响

- **对现有代码**：
  - `tools/train_lgbm_ranker.py`、`tools/train_catboost.py`、`tools/calibrate_weights.py`：核心训练/校准逻辑保留并抽取为 `training-service` 内的 Python 模块，CLI 入口改为 API 触发
  - `outputs/models/`：现有模型文件迁移到 MLflow artifact store，目录废弃
  - 选股服务（`screening_top50.py`）：因子权重从硬编码改为读取 `factor_weights` 表
  - 排序/预测服务：模型加载从本地文件改为 MLflow `pyfunc.load_model()`
  - 前端：新增管理端"训练管理"页面（AC-6.3 训练可视化、AC-6.5 A/B 切换按钮）

- **对团队**：
  - 需学习 MLflow 基本操作（实验创建、模型注册、Stage 切换）
  - 需学习 Optuna 基本概念（Study、Trial、Sampler）

- **对成本**：
  - MLflow Tracking Server：1 个额外容器（~256MB 内存），无额外许可费用
  - CPU 训练：无额外硬件成本（复用现有服务器）
  - 预估月增量：0 CNY（全部开源 + 现有硬件）

- **对运维**：
  - 新增监控：MLflow Tracking Server 健康检查、训练任务失败告警（APScheduler job 执行失败 → 日志 + 企微通知）
  - 新增备份：MLflow 后端 PostgreSQL 数据库随现有 PostgreSQL 备份策略一起备份
  - APScheduler job store 表自动随 training-service 启动创建

## 本 ADR 不覆盖的决策

- **Kronos Fine-tune（Transformer）的训练管线**：PRD AC-6.1 提到但当前无可用模型代码，待可行性验证后由独立 ADR 决策（预计涉及 GPU 硬件、HuggingFace Trainer vs 自建训练循环、LoRA 微调策略）
- **模型推理服务的部署拓扑**：当前选股/排序为批量离线推理（请求-响应模式），不涉及在线模型服务（如 Triton Inference Server / BentoML）。如果未来需要实时推理，另开 ADR
- **训练数据版本管理**（DVC / Delta Lake）：当前数据量级（SQLite → pickle → DataFrame）足够，数据版本与模型版本通过 MLflow run 的 `data_path` tag 关联即可
- **多市场扩展（港股/美股）的模型训练**：PRD Phase 4，当前仅覆盖 A 股

## 后续工作

- [ ] ml-engineer / 第 17 周前：搭建 MLflow Tracking Server（docker-compose 新增 mlflow 容器）
- [ ] ml-engineer / 第 17-18 周：将 `train_lgbm_ranker.py` 核心逻辑重构到 `training-service/app/trainers/lgbm_trainer.py`，接入 MLflow 和 Optuna
- [ ] ml-engineer / 第 18-19 周：将 `train_catboost.py` 核心逻辑重构到 `training-service/app/trainers/catboost_trainer.py`，接入 MLflow 和 Optuna
- [ ] ml-engineer / 第 19 周：将 `calibrate_weights.py` 逻辑重构到 `training-service/app/calibrator.py`，结果写入 `factor_weights` 表
- [ ] ml-engineer / 第 19-20 周：实现 APScheduler 训练调度（周六 02:00 训练 + 周五 15:30 校准）
- [ ] ml-engineer / 第 20 周：实现 A/B 评估对比逻辑 + MLflow Stage 切换 API
- [ ] backend-dev / 第 20-21 周：改造选股/排序/预测服务，从 MLflow 加载模型 + 从 DB 读取因子权重
- [ ] frontend-dev / 第 21-22 周：管理端训练管理页面（训练触发、可视化、A/B 切换按钮、训练历史列表）
- [ ] tech-lead / Kronos Fine-tune 可行性验证后：开独立 ADR 决策 Transformer 训练管线

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。

**查证基线日期**：2026-06-10

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|------|---------|-----------|-------------|---------|----------------------|
| MLflow | 3.7.1 | 3.7.1 | 当前最新 | Active | [MLflow Release Notes](https://github.com/mlflow/mlflow/releases) |
| Optuna | 4.3.0 | 4.3.0 | 当前最新 | Active | [Optuna Changelog](https://github.com/optuna/optuna/releases) — "v4.3.0 is the latest stable release" |
| APScheduler | 3.11.0 | 3.11.0 | 当前最新 | Active (维护模式) | [APScheduler GitHub](https://github.com/agronholm/apscheduler) — 稳定维护，主要在修 bug |
| LightGBM | 4.6.0 | 4.6.0 | 当前最新 | Active | [LightGBM Releases](https://github.com/microsoft/LightGBM/releases) |
| CatBoost | 2.0.2 | 2.0.2 | 当前最新 | Active | [CatBoost Releases](https://github.com/catboost/catboost/releases) |

**回填规则**：执行层在落地时（写入 `requirements.txt` / `pyproject.toml`）回填本表对应行，commit message 加 `docs(adr): backfill ADR-004 verification for [pkg]`。
