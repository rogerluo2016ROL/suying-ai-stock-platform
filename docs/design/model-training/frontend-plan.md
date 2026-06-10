# 模型训练管线 -- 前端方案文档

> 基于 PRD AC-6.1~6.9。日期：2026-06-10。

---

## 1. 页面架构

模型训练功能拆分为两个页面，均仅 `admin` 角色可访问（AC-6.9）：

| 页面 | 路由 | 文件 | 职责 |
|------|------|------|------|
| 训练中心 (Training) | `/training` | `frontend/src/pages/Training.tsx` | 触发训练 + 任务列表 + 实时指标(ECharts) + 调度配置 |
| 模型注册 (ModelRegistry) | `/model-registry` | `frontend/src/pages/ModelRegistry.tsx` | 模型列表 + A/B对比 + 上线/回滚 + 因子分析 |

### 1.1 路由注册 (App.tsx)

```tsx
// 侧边栏菜单项
{ key: '/training',        icon: <ExperimentOutlined />, label: '训练中心',     roles: ['admin'] },
{ key: '/model-registry',  icon: <ApiOutlined />,        label: '模型注册',     roles: ['admin'] },

// 路由映射
{ path: '/training',       element: <Training />,       roles: ['admin'] },
{ path: '/model-registry', element: <ModelRegistry />,  roles: ['admin'] },
```

- 两个页面均通过 `ProtectedRoute` 包裹，非 `admin` 角色访问即重定向到 `/`。
- 侧边栏菜单在 `filterMenu()` 中按角色过滤，普通用户不可见这两个入口。
- 训练完成后可从 Training 页面跳转至 ModelRegistry 查看评估结果（`navigate('/model-registry')`）。

### 1.2 布局框架

沿用 `App.tsx` 的 Ant Design Layout 套件：
- 固定左侧 Sider（256px / 收起 80px），带 `StockOutlined` Logo + "速赢AI" 品牌名。
- 右侧 `Layout` 包含 sticky Header（48px）+ Content（margin: 16px）+ Footer。
- 页面内容区使用 `margin: 16px` 外边距。

---

## 2. 组件树

### 2.1 Training 页面组件树

```
Training
├── PageHeader
│   ├── Title "训练中心" (ExperimentOutlined 图标)
│   └── Button "手动触发训练" (PlusOutlined, primary)
│
├── Tabs
│   ├── Tab "训练任务"
│   │   └── Card (任务列表)
│   │       └── Table (pageSize=10)
│   │           ├── 任务ID (code 样式, 前12位)
│   │           ├── 模型类型 (Tag: blue=LightGBM, green=CatBoost, purple=Kronos)
│   │           ├── 数据范围 (起止日期)
│   │           ├── 状态 (Tag: processing=blue, completed=green, failed=red, queued=default)
│   │           ├── 开始时间
│   │           ├── 耗时
│   │           ├── 关键指标 (best_loss / best_val_loss)
│   │           └── 操作
│   │               ├── 查看详情 → 展开下方 Charts + Logs
│   │               ├── 取消 (processing/queued 状态, Popconfirm)
│   │               └── 删除 (completed/failed 状态, Popconfirm)
│   │
│   ├── Tab "训练监控" (仅在 processing 任务时激活)
│   │   └── Row (2 列)
│   │       ├── Col "实时指标" (Col span=12)
│   │       │   ├── Card "Loss 曲线"
│   │       │   │   └── ECharts (ReactECharts, 折线图: train_loss + val_loss)
│   │       │   ├── Card "学习率"
│   │       │   │   └── ECharts (折线图: learning_rate)
│   │       │   └── Card "当前 Round"
│   │       │       └── Statistic (当前轮次 / 总轮次, 进度条)
│   │       └── Col "训练日志" (Col span=12)
│   │           └── Card
│   │               └── Timeline (实时滚动, 每 5s 轮询)
│   │                   ├── info: 训练开始 / 数据加载
│   │                   ├── success: Round 完成
│   │                   ├── warning: 早停触发
│   │                   └── error: 训练异常
│   │
│   └── Tab "调度配置" (ScheduleConfig)
│       ├── Card "定时训练"
│       │   └── Form (vertical layout)
│       │       ├── Switch "启用自动训练" (AC-6.2)
│       │       ├── Select "模型类型" (多选: LightGBM, CatBoost, Kronos)
│       │       ├── Input "Cron 表达式" (如 "0 2 * * 6" = 每周六凌晨 2:00)
│       │       ├── Typography.Text (人类可读: "下次执行: 2026-06-13 周六 02:00")
│       │       ├── InputNumber "数据回溯天数" (default 365)
│       │       ├── InputNumber "最大训练轮次" (default 1000)
│       │       ├── Switch "启用早停" (default true)
│       │       ├── InputNumber "早停轮次" (default 50)
│       │       └── Button "保存配置"
│       └── Card "调度历史"
│           └── Table
│               ├── 执行时间
│               ├── 模型类型
│               ├── 结果 (Tag: success=green, failed=red)
│               └── 关联任务ID (可点击跳转)
│
└── Modal "触发训练" (AC-6.1)
    └── Form (vertical layout, size=small)
        ├── Divider "训练配置"
        ├── Select "模型类型" (LightGBM | CatBoost | Kronos Fine-tune)
        ├── DatePicker.RangePicker "数据时间范围" (required)
        ├── InputNumber "最大轮次" (default 1000)
        ├── Select "目标列" (next_day_return | next_week_return | ...)
        ├── Switch "启用早停" (default true)
        ├── InputNumber "早停轮次" (default 50)
        ├── Select "因子集合" (多选预定义因子组)
        ├── Divider "Kronos 专属 (仅 Kronos Fine-tune 时显示)"
        ├── InputNumber "Fine-tune Epochs" (default 10)
        ├── InputNumber "Learning Rate" (default 1e-4)
        └── Button "提交训练" (loading)
```

### 2.2 ModelRegistry 页面组件树

```
ModelRegistry
├── PageHeader
│   ├── Title "模型注册" (ApiOutlined 图标)
│   └── Button "刷新" (ReloadOutlined)
│
├── Card (模型列表, AC-6.8)
│   └── Table (pageSize=10)
│       ├── 模型名称 (可点击展开详情)
│       ├── 版本号 (Badge)
│       ├── 模型类型 (Tag: blue=LightGBM, green=CatBoost, purple=Kronos)
│       ├── 状态 (Tag: online=green, staging=yellow, archived=default, failed=red)
│       ├── 上线时间
│       ├── 评估指标 (AUC / Sharpe / 年化收益 / 最大回撤, 紧凑显示)
│       └── 操作 (AC-6.5, AC-6.6)
│           ├── 上线 (staging 状态, Popconfirm: "确认上线此模型？")
│           ├── 回滚 (online 状态, Popconfirm: "确认回滚到上一版本？")
│           ├── 对比 → 打开 A/B 对比 Modal
│           └── 详情 → Drawer
│
├── Drawer "模型详情" (640px 宽)
│   ├── Descriptions "基本信息"
│   │   ├── 模型名称 / 版本 / 类型
│   │   ├── 训练数据范围
│   │   ├── 训练耗时 / 完成时间
│   │   └── 超参数 (JSON 格式化)
│   ├── Card "评估指标" (AC-6.4)
│   │   ├── Row (4 列 KPI 卡片)
│   │   │   ├── Statistic "AUC"
│   │   │   ├── Statistic "夏普比率"
│   │   │   ├── Statistic "年化收益"
│   │   │   └── Statistic "最大回撤"
│   │   └── Table "逐项指标" (precision, recall, f1, ic_mean, icir, rank_ic)
│   ├── Card "特征重要性" (AC-6.3)
│   │   └── ECharts (横向柱状图: 特征名 → 重要性得分, Top 20)
│   ├── Card "训练曲线"
│   │   └── ECharts (双 Y 轴: train_loss + val_loss)
│   ├── Card "因子权重" (AC-6.7)
│   │   └── Table (因子名 / 当前权重 / IC / ICIR / 更新时间)
│   └── Card "训练日志 → 跳转 Training 页面任务详情"
│
├── Modal "A/B 对比" (1000px 宽, AC-6.4, AC-6.5, AC-6.6)
│   ├── Row (2 列)
│   │   ├── Col "模型 A (旧/当前线上)" (span=12)
│   │   │   ├── Descriptions (基本信息)
│   │   │   ├── Statistic (核心指标)
│   │   │   └── ECharts (回测收益曲线, 小图)
│   │   └── Col "模型 B (新/待评估)" (span=12)
│   │       ├── Descriptions (基本信息)
│   │       ├── Statistic (核心指标)
│   │       └── ECharts (回测收益曲线, 小图)
│   ├── Divider
│   ├── Table "指标对比"
│   │   ├── 指标名
│   │   ├── 模型 A 值
│   │   ├── 模型 B 值
│   │   └── 变化 (↑绿色=改善, ↓红色=退化)
│   └── Alert (结论: "模型 B 在 AUC/夏普/最大回撤 上均优于模型 A, 建议上线")
│       ├── Button "一键上线" (primary, AC-6.5)
│       └── Button "保留旧模型" (AC-6.6: 弹 TextArea 填写失败原因, 提交后归档新模型)
│
└── Card "因子分析" (FactorAnalysis, AC-6.7)
    ├── Row (2 列)
    │   ├── Col span=12
    │   │   └── Card "IC 滚动折线图"
    │   │       └── ECharts (多因子 IC 折线图, 时间轴 X, IC 值 Y, 含零线)
    │   └── Col span=12
    │       └── Card "IC 衰减热力图"
    │           └── ECharts (Heatmap: 因子 × 未来周期 → IC 值)
    └── Card "因子排名表" (AC-6.7)
        └── Table
            ├── 排名
            ├── 因子名称
            ├── IC 均值
            ├── ICIR
            ├── Rank IC
            ├── 当前权重
            ├── 建议权重
            └── 权重趋势 (Sparkline: 最近 4 周权重变化)
```

---

## 3. 状态管理

两个页面均使用 React 本地 `useState` + `useEffect` + `useCallback`，无第三方状态库。数据流为单向：**API → setState → 组件重渲染**。

### 3.1 Training 状态变量

```tsx
const [tasks, setTasks] = useState<TrainingTask[]>([])
const [tasksLoading, setTasksLoading] = useState(false)
const [activeTask, setActiveTask] = useState<TrainingTask | null>(null)
const [metrics, setMetrics] = useState<TrainingMetrics | null>(null)     // 实时指标
const [taskLogs, setTaskLogs] = useState<TaskLog[]>([])
const [triggerOpen, setTriggerOpen] = useState(false)
const [schedule, setSchedule] = useState<ScheduleConfig | null>(null)
const [scheduleHistory, setScheduleHistory] = useState<ScheduleRun[]>([])
const [liveTaskId, setLiveTaskId] = useState<string | null>(null)        // 当前正在监控的任务ID
const [form] = Form.useForm()                                            // 触发训练表单
const [scheduleForm] = Form.useForm()                                    // 调度配置表单
const [activeTab, setActiveTab] = useState('tasks')                      // 当前 Tab
```

**实时监控轮询机制**：当存在 `liveTaskId`（processing 状态的任务）时，`useEffect` 启动 `setInterval` 每 5 秒轮询 `GET /api/v1/training/tasks/{id}/metrics` 和 `GET /api/v1/training/tasks/{id}/logs?after={lastId}`，增量更新 `metrics` 和 `taskLogs`。任务完成后自动停止轮询。

**Cron 人类可读**：前端使用 `cronstrue` 库将 Cron 表达式转为中文描述，同时在调度配置卡片中计算并展示"下次执行时间"。

### 3.2 ModelRegistry 状态变量

```tsx
const [models, setModels] = useState<ModelInfo[]>([])
const [modelsLoading, setModelsLoading] = useState(false)
const [detailModel, setDetailModel] = useState<ModelInfo | null>(null)
const [compareOpen, setCompareOpen] = useState(false)
const [modelA, setModelA] = useState<ModelInfo | null>(null)   // 对比: 旧模型
const [modelB, setModelB] = useState<ModelInfo | null>(null)   // 对比: 新模型
const [factors, setFactors] = useState<FactorInfo[]>([])
const [factorIcHistory, setFactorIcHistory] = useState<IcPoint[]>([])
const [rollbackReason, setRollbackReason] = useState('')
```

### 3.3 加载时机

| 页面 | 触发时机 | 方法 |
|------|---------|------|
| Training | `useEffect([], [])` 首次挂载 | `loadTasks()` + `loadSchedule()` |
| Training | 切换到"调度配置" Tab | `loadScheduleHistory()` |
| Training | 手动触发训练成功后 | `loadTasks()` |
| Training | 点击任务"查看详情" | `loadMetrics(id)` + `loadLogs(id)` |
| Training | 任务变为 processing | 启动 `liveTaskId` 轮询 |
| Training | 任务完成 | 停止轮询, `loadTasks()` 刷新列表 |
| ModelRegistry | `useEffect([], [])` 首次挂载 | `loadModels()` + `loadFactors()` |
| ModelRegistry | 上线/回滚/删除成功后 | `loadModels()` |
| ModelRegistry | 点击"对比"按钮 | `setModelA(currentOnline)`, `setModelB(selected)`, `setCompareOpen(true)` |

---

## 4. 用户交互流程

```
┌─────────────────────────┐
│ 回测分析页面              │  AC-5.7: "回测不理想 → 一键训练"
│ /backtest               │  点击 "优化训练" 按钮 → navigate('/training')
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 训练中心 /training       │
│                         │
│  [Tab: 训练任务]         │
│  ├── 查看历史任务列表      │
│  ├── 点击 "手动触发训练"   │
│  │   └── Modal 表单       │  AC-6.1: 选择模型类型 + 数据范围 + 参数
│  │       └── 提交训练      │  POST /api/v1/training/tasks
│  │           └── 自动切到 "训练监控" Tab
│  │
│  ├── 查看任务详情          │
│  │   └── 展开 Loss 曲线   │  AC-6.3: 训练/验证 Loss 曲线
│  │   └── 特征重要性排名    │  AC-6.3: 特征重要性排名
│  │   └── 实时日志 Timeline │
│  │
│  [Tab: 训练监控]          │
│  ├── 实时 Loss 曲线       │  每 5s 轮询更新
│  ├── 当前轮次 / 总轮次     │
│  └── 实时日志流           │
│       └── 训练完成 → 自动停止轮询
│
│  [Tab: 调度配置]          │  AC-6.2
│  ├── 启用/禁用自动训练     │
│  ├── 设置 Cron 表达式     │  "0 2 * * 6" = 每周六凌晨 2:00
│  ├── 配置训练参数          │
│  └── 查看调度历史          │
│
└───────────┬─────────────┘
            │ 训练完成后 → 跳转查看
            ▼
┌─────────────────────────┐
│ 模型注册 /model-registry │
│                         │
│  ├── 查看模型列表          │  AC-6.8: 训练历史可追溯
│  │   ├── 版本 / 状态 / 指标 │
│  │   └── 操作: 上线/回滚/对比/详情
│  │
│  ├── 查看模型详情          │
│  │   ├── 超参数 / 评估指标  │
│  │   ├── 特征重要性图表     │
│  │   ├── 训练曲线          │
│  │   └── 因子权重          │
│  │
│  ├── A/B 对比             │  AC-6.4, AC-6.5, AC-6.6
│  │   ├── 新模型 vs 旧模型  │
│  │   ├── 指标逐项对比      │
│  │   ├── 新模型更好        │
│  │   │   └── "一键上线"    │  PUT /api/v1/models/{id}/promote
│  │   │       └── 状态: staging → online
│  │   └── 新模型不如旧模型   │
│  │       └── "保留旧模型"   │  PUT /api/v1/models/{id}/archive
│  │           └── 填写失败原因 (AC-6.6)
│  │
│  ├── 回滚                  │  AC-6.5
│  │   └── online → 选择上一版本 → 回滚
│  │       PUT /api/v1/models/{id}/rollback
│  │
│  └── 因子分析              │  AC-6.7
│      ├── IC 滚动折线图     │
│      ├── IC 衰减热力图     │
│      └── 因子排名表         │  IC均值 / ICIR / 权重建议
│          └── 每周自动校准   │  基于最新 IC/ICIR 数据
└─────────────────────────┘
```

### 4.1 模型状态转换图

```
                        POST /api/v1/training/tasks
                              │
                              ▼
                       ┌──────────┐
                       │ queued   │
                       └────┬─────┘
                            │ worker picks up
                            ▼
                       ┌──────────┐
                 ┌─────│processing│─────┐
                 │     └────┬─────┘     │
                 │          │           │
            cancel     success      failure
                 │          │           │
                 ▼          ▼           ▼
            ┌──────┐  ┌──────────┐  ┌──────┐
            │cancelled│ │completed │  │failed│
            └──────┘  └────┬─────┘  └──────┘
                           │
                     auto-evaluate
                           │
                           ▼
                     ┌──────────┐
                     │ staging  │ ← 新模型等待评审
                     └────┬─────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
           promote     archive      (对比结果: 更好/更差)
              │           │
              ▼           ▼
         ┌────────┐  ┌──────────┐
         │ online │  │ archived │
         └───┬────┘  └──────────┘
             │
          rollback
             │
             ▼
         ┌──────────┐
         │ archived │ (上一版本变回 online)
         └──────────┘
```

- `queued` 可取消 (`cancel`)
- `processing` 可取消 (`cancel`)
- `completed` 自动进入 `staging` 等待管理员评审
- `staging` 可上线 (`promote`) 或归档 (`archive`)
- `online` 可回滚 (`rollback`)，上一版本自动变回 `online`
- 取消、删除操作均需 `Popconfirm` 二次确认

---

## 5. 暗色主题一致性 (QuantDinger)

沿用现有 App.tsx 的暗色主题预留框架。激活后需与 QuantDinger 品牌视觉保持一致：

| 维度 | 规格 | 备注 |
|------|------|------|
| 主色调 | `#1677ff` (Ant Design 默认蓝) | ExperimentOutlined、ApiOutlined 使用此色 |
| 盈亏/涨跌颜色 | 涨 `#52c41a` (绿) / 跌 `#ff4d4f` (红) | 指标对比 ↑绿色改善, ↓红色退化 |
| 模型类型标签 | LightGBM=blue, CatBoost=green, Kronos=purple | 全局统一 |
| 状态标签 | online=green, staging=yellow, archived=default, failed=red | statusConfig 对象统一管理 |
| ECharts 暗色 | `backgroundColor: 'transparent'`, `textStyle.color: 暗色主题变量` | 图表跟随主题切换 |
| 卡片圆角 | `borderRadius: 8` | 所有 Card 统一 |
| 对比列背景 | A 列 `#fafafa` (浅色) / 暗色模式 `#1f1f1f` | A/B 对比 Modal 左右分栏 |
| 侧边栏 | 跟随全局 Layout 暗色变量 | -- |
| 字体 | Ant Design 默认字体栈 | 12px (辅助) / 13px (正文) / 14px (标签) / 16px (标题) |
| 间距 | 16px 页面外边距，8px/12px 组件内间距 | 统一 8 的倍数 |

图表配色（ECharts）：
- Loss 曲线: `train=#1677ff` (蓝), `val=#52c41a` (绿)
- IC 折线: 多因子用 10 色调色板 `['#5470C6','#91CC75','#FAC858','#EE6666','#73C0DE','#3BA272','#FC8452','#9A60B4','#EA7CCC','#5470C6']`
- IC 热力图: `visualMap` 蓝-白-红渐变 (负→零→正)
- 特征重要性: 横向柱状图, `#1677ff` 渐变

---

## 6. API 调用清单

### 6.1 Training 页面

| 方法 | 端点 | 何时调用 | 请求体 / 参数 |
|------|------|---------|-------------|
| `GET` | `/api/v1/training/tasks` | 页面挂载、刷新、训练提交后 | -- |
| `GET` | `/api/v1/training/tasks/{id}` | 点击"查看详情" | -- |
| `GET` | `/api/v1/training/tasks/{id}/metrics` | 查看详情 + 监控轮询 (5s) | -- |
| `GET` | `/api/v1/training/tasks/{id}/logs?after={logId}` | 查看详情 + 监控轮询 (5s) | 增量拉取 |
| `POST` | `/api/v1/training/tasks` | 提交"触发训练"表单 | `{ model_type, data_start, data_end, max_rounds, target_column, early_stopping, early_stopping_rounds, factor_groups, kronos_epochs?, kronos_lr? }` |
| `POST` | `/api/v1/training/tasks/{id}/cancel` | 取消训练 (Popconfirm) | -- |
| `DELETE` | `/api/v1/training/tasks/{id}` | 删除任务 (Popconfirm) | -- |
| `GET` | `/api/v1/training/schedule` | 页面挂载 | -- |
| `PUT` | `/api/v1/training/schedule` | 保存调度配置 | `{ enabled, model_types[], cron, data_lookback_days, max_rounds, early_stopping, early_stopping_rounds }` |
| `GET` | `/api/v1/training/schedule/history` | 切换"调度配置" Tab | -- |

**请求体结构 (POST /api/v1/training/tasks)**：
```json
{
  "model_type": "lightgbm | catboost | kronos",
  "data_start": "2025-06-01",
  "data_end": "2026-06-01",
  "max_rounds": 1000,
  "target_column": "next_day_return",
  "early_stopping": true,
  "early_stopping_rounds": 50,
  "factor_groups": ["technical", "fundamental", "sentiment"],
  "kronos_epochs": 10,
  "kronos_lr": 0.0001
}
```

**响应结构 (GET /api/v1/training/tasks 列表)**：
```json
{
  "tasks": [
    {
      "id": "t_abc123def456",
      "model_type": "lightgbm",
      "data_start": "2025-06-01",
      "data_end": "2026-06-01",
      "status": "completed",
      "started_at": "2026-06-10T02:00:00Z",
      "duration_seconds": 845,
      "best_loss": 0.234,
      "best_val_loss": 0.256,
      "best_round": 487,
      "hyperparams": { "learning_rate": 0.05, "num_leaves": 31 },
      "created_at": "2026-06-10T01:55:00Z"
    }
  ]
}
```

**响应结构 (GET /api/v1/training/tasks/{id}/metrics)**：
```json
{
  "task_id": "t_abc123def456",
  "rounds": [0, 1, 2, 3, ...],
  "train_loss": [0.8, 0.6, 0.45, 0.38, ...],
  "val_loss": [0.82, 0.63, 0.48, 0.41, ...],
  "learning_rate": [0.1, 0.095, 0.09, 0.085, ...]
}
```

**响应结构 (GET /api/v1/training/tasks/{id}/logs)**：
```json
{
  "logs": [
    { "id": "log_001", "time": "2026-06-10T02:00:01Z", "level": "info",    "message": "数据加载完成: 24500 条样本, 86 个特征" },
    { "id": "log_002", "time": "2026-06-10T02:00:05Z", "level": "info",    "message": "开始训练 LightGBM, max_rounds=1000" },
    { "id": "log_003", "time": "2026-06-10T02:00:12Z", "level": "success", "message": "Round 100: train_loss=0.412, val_loss=0.435" },
    { "id": "log_004", "time": "2026-06-10T02:05:30Z", "level": "warning", "message": "早停触发: val_loss 连续 50 轮未改善" }
  ]
}
```

### 6.2 ModelRegistry 页面

| 方法 | 端点 | 何时调用 | 说明 |
|------|------|---------|------|
| `GET` | `/api/v1/models` | 页面挂载、刷新、上线/回滚后 | 模型列表 |
| `GET` | `/api/v1/models/{id}` | 点击"详情" | 模型详情 |
| `PUT` | `/api/v1/models/{id}/promote` | A/B 对比后"一键上线" (AC-6.5) | staging → online |
| `PUT` | `/api/v1/models/{id}/archive` | "保留旧模型" (AC-6.6) | staging → archived + 失败原因 |
| `PUT` | `/api/v1/models/{id}/rollback` | "回滚" (AC-6.5) | online → archived, prev → online |
| `GET` | `/api/v1/factors` | 页面挂载 | 因子列表 + 权重 |
| `GET` | `/api/v1/factors/ic-history?factor_names={}&window_days=120` | 页面挂载 | IC 滚动历史 |
| `POST` | `/api/v1/factors/calibrate` | 手动触发权重校准 (AC-6.7) | 基于最新 IC/ICIR 更新权重 |

**响应结构 (GET /api/v1/models 列表)**：
```json
{
  "models": [
    {
      "id": "m_xyz789abc012",
      "name": "LightGBM-2026Q2",
      "version": "v3.2.0",
      "model_type": "lightgbm",
      "status": "online",
      "promoted_at": "2026-06-10T08:00:00Z",
      "training_task_id": "t_abc123def456",
      "data_start": "2025-06-01",
      "data_end": "2026-06-01",
      "metrics": {
        "auc": 0.723,
        "sharpe": 1.85,
        "annual_return": 0.32,
        "max_drawdown": 0.18,
        "precision": 0.68,
        "recall": 0.71,
        "f1": 0.695,
        "ic_mean": 0.045,
        "icir": 0.82,
        "rank_ic": 0.052
      },
      "feature_importance": { "momentum_20d": 0.15, "volume_ratio": 0.12, ... },
      "hyperparams": { "learning_rate": 0.05, "num_leaves": 31, ... },
      "created_at": "2026-06-10T02:15:00Z"
    }
  ]
}
```

**响应结构 (GET /api/v1/factors)**：
```json
{
  "factors": [
    {
      "name": "momentum_20d",
      "current_weight": 0.15,
      "suggested_weight": 0.12,
      "ic_mean": 0.038,
      "icir": 0.65,
      "rank_ic": 0.044,
      "last_calibrated_at": "2026-06-07T02:00:00Z",
      "weight_trend": [0.18, 0.16, 0.15, 0.15]
    }
  ]
}
```

**请求体结构 (PUT /api/v1/models/{id}/archive)**：
```json
{
  "reason": "新版模型在回测集上 AUC 下降 0.03, 最大回撤增加 5%, 暂不上线。"
}
```

### 6.3 错误处理模式

统一沿用项目现有错误处理模式：

```tsx
// fetch + then/catch + message.error
fetch('/api/v1/training/tasks', { method: 'POST', body: JSON.stringify(values) })
  .then(r => {
    if (r.ok) { message.success('训练任务已提交'); loadTasks(); setActiveTab('monitor'); }
    else { r.json().then(err => message.error(err.detail || '操作失败')); }
  })
  .catch(() => message.error('服务未连接'));

// async/await + try/catch
try {
  const r = await fetch(`/api/v1/models/${id}/promote`, { method: 'PUT' });
  if (r.ok) { message.success('模型已上线'); loadModels(); }
  else { message.error((await r.json().catch(() => ({ detail: '操作失败' }))).detail); }
} catch { message.error('服务未连接'); }
```

---

## 7. 类型定义

### 7.1 Training 核心类型

```tsx
type ModelType = 'lightgbm' | 'catboost' | 'kronos'
type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
type LogLevel = 'info' | 'success' | 'warning' | 'error'

interface TrainingTask {
  id: string
  model_type: ModelType
  data_start: string
  data_end: string
  status: TaskStatus
  started_at?: string
  duration_seconds?: number
  best_loss?: number
  best_val_loss?: number
  best_round?: number
  hyperparams: Record<string, number>
  created_at: string
}

interface TrainingMetrics {
  task_id: string
  rounds: number[]
  train_loss: number[]
  val_loss: number[]
  learning_rate: number[]
}

interface TaskLog {
  id: string
  time: string
  level: LogLevel
  message: string
}

interface ScheduleConfig {
  enabled: boolean
  model_types: ModelType[]
  cron: string
  data_lookback_days: number
  max_rounds: number
  early_stopping: boolean
  early_stopping_rounds: number
}

interface ScheduleRun {
  id: string
  executed_at: string
  model_type: ModelType
  result: 'success' | 'failed'
  task_id: string
}

interface TriggerTrainingForm {
  model_type: ModelType
  data_start: string
  data_end: string
  max_rounds: number
  target_column: string
  early_stopping: boolean
  early_stopping_rounds: number
  factor_groups: string[]
  kronos_epochs?: number
  kronos_lr?: number
}
```

### 7.2 ModelRegistry 核心类型

```tsx
type ModelStatus = 'online' | 'staging' | 'archived' | 'failed'

interface ModelMetrics {
  auc: number
  sharpe: number
  annual_return: number
  max_drawdown: number
  precision: number
  recall: number
  f1: number
  ic_mean: number
  icir: number
  rank_ic: number
}

interface ModelInfo {
  id: string
  name: string
  version: string
  model_type: ModelType
  status: ModelStatus
  promoted_at?: string
  training_task_id: string
  data_start: string
  data_end: string
  metrics: ModelMetrics
  feature_importance: Record<string, number>
  hyperparams: Record<string, number>
  created_at: string
}

interface FactorInfo {
  name: string
  current_weight: number
  suggested_weight: number
  ic_mean: number
  icir: number
  rank_ic: number
  last_calibrated_at: string
  weight_trend: number[]
}

interface IcPoint {
  date: string
  factor_name: string
  ic_value: number
}
```

### 7.3 常量定义

| 常量 | 值 | 用途 |
|------|---|------|
| `modelTypeConfig` | `{ lightgbm: blue/LightGBM, catboost: green/CatBoost, kronos: purple/Kronos }` | 模型类型标签 |
| `taskStatusConfig` | `{ queued: default/排队中, processing: blue/训练中, completed: green/已完成, failed: red/失败, cancelled: default/已取消 }` | 任务状态标签 |
| `modelStatusConfig` | `{ online: green/线上, staging: yellow/待评审, archived: default/已归档, failed: red/失败 }` | 模型状态标签 |
| `logLevelConfig` | `{ info: blue/信息, success: green/成功, warning: gold/警告, error: red/错误 }` | 日志级别 |
| `targetColumns` | `['next_day_return', 'next_week_return', 'next_month_return']` | 目标列下拉 |
| `factorGroupOptions` | `['technical', 'fundamental', 'sentiment', 'macro', 'flow']` | 因子集合多选 |
| `defaultCron` | `"0 2 * * 6"` | 默认: 每周六凌晨 2:00 |
| `icColorPalette` | `['#5470C6','#91CC75','#FAC858','#EE6666','#73C0DE','#3BA272','#FC8452','#9A60B4','#EA7CCC']` | IC 折线图 10 色 |

---

## 8. 关键实现细节

### 8.1 ECharts 集成

```tsx
import ReactECharts from 'echarts-for-react'

// Loss 曲线
const lossOption = {
  tooltip: { trigger: 'axis' },
  legend: { data: ['Train Loss', 'Val Loss'] },
  xAxis: { type: 'category', name: 'Round', data: metrics?.rounds },
  yAxis: { type: 'value', name: 'Loss' },
  series: [
    { name: 'Train Loss', type: 'line', data: metrics?.train_loss, smooth: true,
      itemStyle: { color: '#1677ff' } },
    { name: 'Val Loss',   type: 'line', data: metrics?.val_loss, smooth: true,
      itemStyle: { color: '#52c41a' } },
  ],
}

// 特征重要性 (横向柱状图)
const featureImportanceOption = {
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'value', name: 'Importance' },
  yAxis: { type: 'category', data: sortedFeatureNames, inverse: true },
  series: [{ type: 'bar', data: sortedFeatureValues,
    itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
      { offset: 0, color: '#83bff6' }, { offset: 1, color: '#1677ff' }
    ]) }
  }],
  grid: { left: '20%' },  // 留空间给长特征名
}

// IC 折线图
const icLineOption = {
  tooltip: { trigger: 'axis' },
  legend: { data: factorNames, type: 'scroll' },
  xAxis: { type: 'time' },
  yAxis: { type: 'value', name: 'IC',
    splitLine: { lineStyle: { type: 'dashed' } } },
  series: factorNames.map((name, i) => ({
    name, type: 'line', data: icDataForFactor(name),
    smooth: true, symbol: 'none',
    itemStyle: { color: icColorPalette[i % icColorPalette.length] },
  })),
  markLine: { data: [{ yAxis: 0, lineStyle: { color: '#999', type: 'dashed' } }] },
}

// IC 衰减热力图
const icHeatmapOption = {
  tooltip: { position: 'top' },
  xAxis: { type: 'category', data: horizons, name: '预测周期 (天)' },
  yAxis: { type: 'category', data: factorNames, inverse: true },
  visualMap: { min: -0.1, max: 0.1, calculable: true,
    inRange: { color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8',
                       '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026'] },
    orient: 'horizontal', left: 'center', bottom: 0 },
  series: [{ type: 'heatmap', data: heatmapData }],
  grid: { left: '20%', bottom: '15%' },
}
```

### 8.2 实时监控轮询

```tsx
useEffect(() => {
  if (!liveTaskId) return

  let lastLogId = ''
  const timer = setInterval(async () => {
    try {
      // 拉取最新指标
      const mRes = await fetch(`/api/v1/training/tasks/${liveTaskId}/metrics`)
      if (mRes.ok) setMetrics(await mRes.json())

      // 增量拉取日志
      const lRes = await fetch(`/api/v1/training/tasks/${liveTaskId}/logs?after=${lastLogId}`)
      if (lRes.ok) {
        const data = await lRes.json()
        if (data.logs.length > 0) {
          setTaskLogs(prev => [...prev, ...data.logs])
          lastLogId = data.logs[data.logs.length - 1].id
        }
      }

      // 检查任务是否完成
      const tRes = await fetch(`/api/v1/training/tasks/${liveTaskId}`)
      if (tRes.ok) {
        const task = await tRes.json()
        if (task.status !== 'processing') {
          setLiveTaskId(null)  // 停止轮询
          loadTasks()
          message.success('训练完成')
        }
      }
    } catch { /* 轮询静默失败 */ }
  }, 5000)

  return () => clearInterval(timer)
}, [liveTaskId])
```

### 8.3 Cron 人类可读

```tsx
import cronstrue from 'cronstrue'
import 'cronstrue/locales/zh_CN'

// 在调度配置中显示
{cronstrue.toString(schedule.cron, { locale: 'zh_CN' })}
// "0 2 * * 6" → "每周六 02:00"
```

### 8.4 A/B 对比逻辑

```tsx
interface CompareResult {
  metric: string
  valueA: number
  valueB: number
  change: number       // (valueB - valueA) / |valueA| * 100, 正=改善
  isHigherBetter: boolean
  winner: 'A' | 'B' | 'tie'
}

function computeCompare(modelA: ModelInfo, modelB: ModelInfo): CompareResult[] {
  const metrics = [
    { key: 'auc',           label: 'AUC',           higherBetter: true },
    { key: 'sharpe',        label: '夏普比率',       higherBetter: true },
    { key: 'annual_return', label: '年化收益',       higherBetter: true },
    { key: 'max_drawdown',  label: '最大回撤',       higherBetter: false },
    { key: 'ic_mean',       label: 'IC 均值',       higherBetter: true },
  ]
  return metrics.map(m => {
    const a = modelA.metrics[m.key], b = modelB.metrics[m.key]
    const change = ((b - a) / Math.abs(a)) * 100
    const winner = m.higherBetter
      ? (b > a ? 'B' : a > b ? 'A' : 'tie')
      : (b < a ? 'B' : a < b ? 'A' : 'tie')
    return { metric: m.label, valueA: a, valueB: b, change, isHigherBetter: m.higherBetter, winner }
  })
}
```

### 8.5 一键上线 / 保留旧模型

```tsx
// 一键上线 (AC-6.5)
const handlePromote = async (modelId: string) => {
  try {
    const r = await fetch(`/api/v1/models/${modelId}/promote`, { method: 'PUT' })
    if (r.ok) { message.success('模型已上线'); loadModels(); setCompareOpen(false) }
    else { message.error((await r.json()).detail) }
  } catch { message.error('服务未连接') }
}

// 保留旧模型 (AC-6.6)
const handleArchive = async (modelId: string, reason: string) => {
  if (!reason.trim()) { message.warning('请填写失败原因'); return }
  try {
    const r = await fetch(`/api/v1/models/${modelId}/archive`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    if (r.ok) { message.success('已归档并保留旧模型'); loadModels(); setCompareOpen(false) }
    else { message.error((await r.json()).detail) }
  } catch { message.error('服务未连接') }
}
```

### 8.6 空状态处理

- Table 空数据：`locale={{ emptyText: '暂无训练任务，点击"手动触发训练"创建。' }}`
- 监控无活跃任务：`<Empty description="当前无训练中的任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />`
- 模型列表空：`locale={{ emptyText: '暂无已注册模型。训练完成后模型将自动注册到此列表。' }}`
- 因子数据空：`<Empty description="暂无因子数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />`
- A/B 对比无旧模型：`<Empty description="当前无线上模型可作为对比基线" />`

---

## 9. 文件清单

| 文件 | 预估行数 | 职责 |
|------|---------|------|
| `frontend/src/App.tsx` | +30 | 新增菜单项 `/training`、`/model-registry` + 路由注册 (roles: ['admin']) |
| `frontend/src/pages/Training.tsx` | ~600 | 训练中心: 任务列表/触发训练 Modal/实时监控/调度配置 |
| `frontend/src/pages/ModelRegistry.tsx` | ~550 | 模型注册: 模型列表/A/B对比/上线回滚/因子分析 |

---

## 10. AC 覆盖矩阵

| AC | 描述 | 前端覆盖点 |
|----|------|----------|
| AC-6.1 | 手动触发训练 | Training 页面 "手动触发训练" Modal, 选择模型类型/数据/参数 |
| AC-6.2 | 自动训练调度 | Training 页面 "调度配置" Tab, Cron 表达式 + 启停开关 |
| AC-6.3 | 训练过程可视化 | Training 页面 ECharts Loss 曲线 + 特征重要性; ModelRegistry 特征重要性柱状图 |
| AC-6.4 | 训练完成自动评估 vs 旧模型 | ModelRegistry A/B 对比 Modal, 指标逐项对比 + 回测曲线 |
| AC-6.5 | 新模型优于旧模型 → 一键上线 | ModelRegistry 对比结论 "一键上线" 按钮 (promote API) |
| AC-6.6 | 新模型不如旧模型 → 保留旧模型 | ModelRegistry "保留旧模型" 按钮, TextArea 填写失败原因 (archive API) |
| AC-6.7 | 因子权重自动校准 | ModelRegistry 因子分析区: IC 折线图 + 排名表 + 权重建议 + 手动校准按钮 |
| AC-6.8 | 训练历史可追溯 | ModelRegistry 模型列表 + 详情 Drawer: 时间/数据/参数/效果 完整记录 |
| AC-6.9 | 仅管理员可访问 | 路由 `roles: ['admin']`, 侧边栏按角色过滤, ProtectedRoute 拦截 |
