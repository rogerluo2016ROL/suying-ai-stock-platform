# Frontend Dev - 个股诊断

> 角色: frontend-dev | 日期: 2026-06-10 | 功能: AC-12.1~12.7 个股诊断前端

---

## 状态: DONE

---

## Skills

- React 18 + TypeScript + Vite
- Ant Design 5.x (Card, Table, Tabs, Collapse, Modal, Select, Descriptions, Statistic, Tag, Progress, Input.Search, Badge, Empty, Spin)
- ECharts 5.5 + echarts-for-react (雷达图、K线预测图、对比雷达图)
- API client (diagnosisApi.analyze / diagnosisApi.compare)

---

## SIT 证据

### AC-12.1 搜索诊断
- [x] Diagnosis.tsx: Input.Search 输入股票代码 + "开始诊断"按钮
- [x] POST `/api/v1/diagnosis/analyze` 调用 (diagnosisApi.analyze)
- [x] 加载状态 + 错误处理 + 成功消息
- [x] 快速示例标签 (000001/600519/300750)

### AC-12.2 综合评分与等级
- [x] 大数字评分显示 (56px, 动态颜色)
- [x] 等级标签: 强烈买入/买入/持有/减仓/卖出 (GRADE_CONFIG)
- [x] 股票名称/代码/当前价格/涨跌幅展示

### AC-12.3 五维雷达图
- [x] ECharts 雷达图 (技术面/资金面/基本面/AI预测/情绪面)
- [x] buildRadarOption 函数 (暗色/亮色自适应)
- [x] 结果卡片右上角雷达图 + 各维度进度条

### AC-12.4 各维度详情展开
- [x] Collapse 展开面板 (技术面/资金面/基本面/AI预测/情绪面)
- [x] 技术面: 因子得分明细 Table (名称/得分/权重/方向/说明)
- [x] 资金面: 北向资金/融资融券/龙虎榜 统计卡片
- [x] 基本面: PE/PB/ROE/营收增速/利润增速/负债率/市值 Descriptions
- [x] AI预测: Kronos 30日K线图 (历史收盘实线 + AI预测虚线 + 置信区间)
- [x] 情绪面: 新闻情感分/研报评级/社交情绪 统计卡片

### AC-12.5 操作建议卡片
- [x] 建议买入价 (绿色卡片)
- [x] 止损价 (橙色卡片)
- [x] 止盈目标 (红色卡片)
- [x] 建议操作 + 置信度 + 推理说明

### AC-12.6 导出 PDF + 多股对比
- [x] "导出 PDF 报告" 按钮 → `GET /api/v1/report/{code}/pdf` (window.open)
- [x] "多股对比" 按钮 → Modal (2-5只股票)
- [x] 对比 Modal: 股票代码添加/删除 + 雷达图叠加 + 对比数据表
- [x] 对比雷达图 buildCompareRadarOption (5色系列)

### AC-12.7 历史记录
- [x] Tabs: 智能诊断 | 历史记录
- [x] Table: 股票代码/名称/评分/等级/时间
- [x] 点击行展开详情: 五维雷达图 + 基本面快照
- [x] 重新诊断按钮
- [x] 排序 (评分/时间) + 分页

---

## 质量门

- [x] TypeScript 零错误 (tsc --noEmit 通过)
- [x] Vite build 绿 (2.6MB bundle, 3.07s)
- [x] Ant Design 组件规范 (Card/Tabs/Collapse/Table/Modal)
- [x] ECharts 正确集成 (echarts-for-react + svg renderer)
- [x] API fallback mock 数据 (API 不可用时自动降级)
- [x] 空状态 / 加载态 / 错误态 全覆盖

---

## 下一步

- 后端实现 `POST /api/v1/diagnosis/analyze` 和 `POST /api/v1/diagnosis/compare` 端点后，移除 mock fallback
- 实现 `GET /api/v1/report/{code}/pdf` PDF 生成端点
- 暗色主题切换 (App.tsx 中 Radio.Group 联动 ConfigProvider)
