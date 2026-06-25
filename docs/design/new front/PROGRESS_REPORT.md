# 阶段2进度更新

> 时间: 2026-06-25
> 状态: 部分完成

## ✅ 已完成修复

| 页面 | 错误数（原） | 错误数（现） | 修复内容 |
|------|-------------|-------------|---------|
| **Screener.tsx** | ~10 | 0 | 应用A股涨跌色、等宽数字、aria属性，替换`any`类型 |
| **Diagnosis.tsx** | 4+ | 0 | 修复类型定义冲突，保留页面本地类型 |

## ⚠️ 待修复（剩余41个错误）

| 页面 | 错误数 | 主要问题 | 优先级 |
|------|--------|---------|--------|
| **Backtest.tsx** | 5 | `FactorItem.id`缺失，`BacktestRunResponse`字段不匹配 | P1 |
| **Dashboard.tsx** | 1 | `DashboardSummaryResponse`字段不匹配 | P1 |
| **Predictions.tsx** | 3 | 缺少`pred_return_pct`属性 | P1 |
| **SupplyChainBom.tsx** | 8+ | `ChainCandidate`类型导出问题 | P1 |
| **Signals.tsx** | 1 | `levels`类型错误 | P2 |
| **Trade.tsx** | 1 | `AccountResponse`类型不匹配 | P2 |
| **测试文件** | 12+ | 类型导出问题 | P3 |

## 下一步建议

**建议**：由于类型错误较多且涉及多个页面，可以采用两种策略：

### 策略A：逐页面修复（推荐）
按优先级逐页面修复类型并应用设计系统：
1. Backtest.tsx → Dashboard.tsx → Predictions.tsx → SupplyChainBom.tsx

### 狼略B：批量类型修复
先集中修复api/types.ts中的类型定义，补充缺失字段：
- `FactorItem.id`
- `DashboardSummaryResponse.alert_signals`等
- `PredictionResponse.pred_return_pct`

## 设计系统已应用验证

**Screener.tsx已成功应用**：
```tsx
// A股涨跌色
color: v >= 16 ? 'var(--up)' : v >= 12 ? 'var(--warn)' : 'var(--accent)'

// 等宽数字
<span className="mono">{v?.toFixed(2)}</span>

// aria属性
aria-pressed={expandedRow === record.code}
aria-label="选择策略模式"
```

**建议**：继续执行策略A，逐页面修复剩余41个错误。预计需2-3轮迭代。