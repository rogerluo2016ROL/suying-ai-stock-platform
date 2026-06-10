# Frontend Dev - 模型训练管线

> 角色: frontend-dev | 日期: 2026-06-10 | 功能: AC-6.1~6.9 模型训练管线前端

---

## 状态: DONE

---

## Skills

- React 18 + TypeScript + Vite
- Ant Design 5.x (Table, Modal, Drawer, Form, Tabs, Card, Popconfirm, Badge, Tag, Timeline, Statistic)
- ECharts 5.5 + echarts-for-react (Loss 曲线、特征重要性、雷达图、IC 折线图)
- SSE (EventSource) 实时训练指标推送
- 路由 ProtetedRoute role-based access (admin only)

---

## SIT 证据

### AC-6.1 手动触发训练
- [x] Training.tsx: TriggerTrainingModal - 下拉选择模型类型 (LightGBM/CatBoost/Kronos) + 超参配置 + RangePicker + "提交训练"按钮
- [x] POST `/api/v1/training/run` + loading + 202 响应处理
- [x] 训练提交后自动刷新任务列表

### AC-6.2 自动训练调度
- [x] Training.tsx > ScheduleConfigForm: Cron 表达式 Input + Switch 启停 + 模型类型选择
- [x] 显示 next_run / last_run 时间
- [x] 调度历史 Table (执行时间/模型类型/结果/关联任务)
- [x] POST `/api/v1/training/schedule` 保存配置

### AC-6.3 训练过程可视化
- [x] Training.tsx > 监控 Tab: ECharts Loss 曲线 (train_loss + val_loss 双线)
- [x] ECharts 特征重要性横向柱状图 (Top 15)
- [x] 学习率曲线 (ECharts 折线图)
- [x] 当前 Trial / 进度条 (Ant Design Statistic + Progress)
- [x] 训练日志 Timeline (信息/成功/警告/错误 四级)
- [x] SSE EventSource 实时接收 metric/complete/error/trial_complete/evaluating 事件

### AC-6.4 训练完成自动评估 vs 旧模型
- [x] ModelRegistry.tsx: A/B 对比 Modal (1000px 宽)
- [x] ECharts 雷达图: 旧模型 vs 新模型多指标对比
- [x] Table: 指标名 / A值 / B值 / 变化 (绿色改善/红色退化) / 结论
- [x] Alert: 综合判定 + 操作建议
- [x] GET `/api/v1/training/models/{id}/compare` (含回退本地对比逻辑)

### AC-6.5 新模型优于旧模型 → 一键上线
- [x] ModelRegistry.tsx: A/B 对比 Modal 底部 "一键上线新模型" 按钮 (RocketOutlined)
- [x] POST `/api/v1/training/models/{id}/deploy` → message.success + 刷新列表
- [x] 模型列表 staging 行 "上线" Popconfirm

### AC-6.6 新模型不如旧模型 → 保留旧模型
- [x] ModelRegistry.tsx: "保留旧模型" 按钮 → Modal 填写失败原因 → 归档新模型
- [x] 模型列表 production 行 "回滚" 按钮 → Modal 填写回滚原因
- [x] POST `/api/v1/training/models/{id}/rollback` + archive

### AC-6.7 因子权重自动校准
- [x] ModelRegistry.tsx: 因子分析区 IC 滚动折线图 (多因子, ECharts 时间轴, 10 色调色板)
- [x] 因子排名 Table: 排名/因子名/IC均值/ICIR/排名IC/权重/方向/显著性
- [x] "权重校准" 按钮 POST `/api/v1/training/calibrate`
- [x] 因子排序功能 (IC/ICIR 列 sortable)

### AC-6.8 训练历史可追溯
- [x] Training.tsx: 任务列表 Table (JobID/模型类型/状态/数据范围/时间/耗时/Loss/操作)
- [x] GET `/api/v1/training/history` + 分页加载
- [x] ModelRegistry.tsx: 模型列表 (名称+版本/类型/状态/AUC/夏普/年化/回撤/IC/上线时间)
- [x] ModelRegistry.tsx: Detail Drawer (Descriptions 基本信息 + 指标 Statistic + 超参数 JSON + 备注)
- [x] GET `/api/v1/training/models/{id}` 模型详情

### AC-6.9 仅管理员可访问
- [x] App.tsx: allMenuItems 仅 `roles: ['admin']` 可看到 "模型训练" 和 "模型注册" 菜单项
- [x] App.tsx: protectedRoutes 路由 `roles: ['admin']` 
- [x] ProtectedRoute 组件: 非 admin 返回 403
- [x] filterMenu() 按角色过滤: 普通用户侧边栏不显示这两个入口

### 增量功能
- [x] ExperimentOutlined 图标显示在 "模型训练" 菜单项
- [x] ApiOutlined 图标显示在 "模型注册" 菜单项
- [x] 模型类型 Tag: LightGBM=blue, CatBoost=green, Kronos=purple (全局统一)
- [x] 状态 Tag: pending/default, running/processing, completed/green, failed/red
- [x] 模型状态: staging/gold, production/green, archived/default
- [x] 空状态 Empty 组件覆盖全部场景 (无任务/无模型/无监控/无因子/无对比基线)
- [x] Popconfirm 二次确认 (取消训练、上线模型)
- [x] DatePicker.RangePicker 数据范围选择
- [x] 表格分页 10/页

---

## 质量门

- [x] tsc -b: 0 errors
- [x] vite build: green (3.24s)
- [x] 零 TS errors
- [x] 所有 imports 正确解析
- [x] ECharts 类型正确使用
- [x] SSE EventSource 事件类型正确 (MessageEvent cast)

---

## 文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `frontend/src/pages/Training.tsx` | ~510 | 训练中心: 触发训练 Modal + 任务列表 + 实时监控(ECharts+SSE) + 调度配置 |
| `frontend/src/pages/ModelRegistry.tsx` | ~430 | 模型注册: 模型列表 + Detail Drawer + A/B对比 Modal + 上线/回滚/归档 + 因子分析 |
| `frontend/src/App.tsx` | +6 | 新增菜单项 + 路由注册 (admin only) |

## 下一步

- `backend-dev` 实现 `/api/v1/training/*` 端点 (protocol/docs/design/model-training/api-contract.md)
- UAT 验证后上线
