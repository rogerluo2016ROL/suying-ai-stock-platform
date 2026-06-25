# 前端优化待办事项

> 日期: 2026-06-25
> 下次继续优化

---

## ✅ 已完成

1. **后端修复**
   - 安装 `psycopg2-binary` 解决数据库连接问题
   - Screener服务API现在能正确返回数据

2. **前端修复**
   - 修复 Screener模式选择：`m.id` 替代 `m.mode`
   - 修复 API调用：POST请求格式

3. **设计系统**
   - 复制 `suying-app.css` 设计系统CSS
   - 创建布局组件（Navigation、WorkflowNav、TradingContextBar）

---

## 🔴 待优化问题

### 问题1：界面显示混乱

**现状**：界面与HTML设计稿不一致，样式混乱

**原因**：
- Ant Design框架与纯HTML设计稿CSS冲突
- 新创建的 `ScreenerV2.tsx` 完全脱离Ant Design，导致布局问题

**建议方案**：
1. 方案A：在现有Ant Design基础上，逐步替换样式token
2. 方案B：完全按照HTML设计稿重写，移除Ant Design依赖

### 问题2：设计系统CSS未生效

**现状**：`suying-app.css` 已复制但未正确应用

**原因**：
- Ant Design样式覆盖了自定义CSS
- 需要调整CSS导入顺序或增加优先级

**建议方案**：
- 在 `index.css` 中增加Ant Design覆盖样式
- 或使用CSS-in-JS方案（如styled-components）

### 问题3：数据加载问题

**现状**：部分页面数据加载不正确

**待检查**：
- Dashboard页面数据加载
- Predictions页面数据加载
- SupplyChain页面数据加载

---

## 📋 下次工作建议

### 优先级P0：界面修复

1. **确定方案**：选择方案A或方案B
2. **实现界面**：按照HTML设计稿实现一致的界面

### 优先级P1：数据加载

1. 检查各页面API调用
2. 确保数据正确显示

### 优先级P2：布局组件集成

1. 将 `Navigation.tsx` 集成到 `App.tsx`
2. 替换现有Ant Design Layout

---

## 📁 相关文件

### 设计稿位置
```
docs/design/new front/
├── screener.html        # 智能选股页面设计稿
├── index.html           # Dashboard设计稿
├── predictions.html     # K线预测设计稿
├── assets/app.css       # 设计系统CSS
└── design-spec.md       # 设计规范文档
```

### 新增组件
```
frontend/src/components/layout/
├── Navigation.tsx       # 三组左侧导航
├── WorkflowNav.tsx      # 顶部工作流导航
├── TradingContextBar.tsx # 交易上下文条
└── index.ts             # 导出汇总

frontend/src/styles/
├── suying-app.css       # 设计系统CSS（已复制）
└── design-tokens.css    # 原设计token

frontend/src/pages/
├── Screener.tsx         # 原页面（已修复模式选择）
├── ScreenerV2.tsx       # 新页面（完全按HTML设计稿）
└── Dashboard.tsx        # 已应用部分设计token
```

---

## 🔧 开发环境

- **前端开发服务器**: http://localhost:3000
- **后端API**: http://localhost:18001 (screener-service)
- **Docker容器**: `uat-adr013-screener-service-1`

---

## 📝 备注

用户建议直接按照HTML设计稿实现，而非在Ant Design基础上修改。下次应优先考虑此方案。

界面效果需用户在浏览器中验证：http://localhost:3000/screener