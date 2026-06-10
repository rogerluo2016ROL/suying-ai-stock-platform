# Auth + RBAC 前端方案设计

> **版本**: v1.0  
> **日期**: 2026-06-10  
> **状态**: Draft — 待 tech-lead / product-lead 确认  
> **关联文档**: [投资管理平台_PRD_产品需求文档.md](../../Kronos/docs/投资管理平台_PRD_产品需求文档.md) §2.2 角色权限矩阵

---

## 1. 概述

为速赢AI 投资管理平台添加用户认证 + RBAC 权限系统。当前前端有 8 个业务页面，无任何登录/权限控制。Phase 1 仅上线 **管理员** 和 **普通用户** 两个角色（内部分析师 / 外部分析师在 Phase 4 上线），但状态管理方案需预留四角色扩展能力。

---

## 2. 技术基线

| 项 | 当前选型 | 说明 |
|---|---|---|
| 框架 | React 18.3 + TypeScript 5.6 | 已有 |
| 构建 | Vite 6.0 | 已有 |
| UI 库 | Ant Design 5.22 + @ant-design/icons 5.5 | 已有 |
| 路由 | react-router-dom 6.28 | 已有 |
| HTTP 客户端 | axios 1.7 | 已有，当前无拦截器 |
| 状态管理 | React Context（不新增 Zustand/Redux） | 项目无全局状态库，Auth 场景用 Context 足够 |

---

## 3. 页面设计

### 3.1 LoginPage — 登录页

**路由**: `/login`

**布局**: 全屏居中卡片式，暗色背景（`#141414` 或 `#1f1f1f`），与现有 QuantDinger 风格统一的科技感暗色主题。

```
┌──────────────────────────────────────────────────┐
│                    (暗色背景)                       │
│                                                    │
│           ┌──────────────────────┐                 │
│           │   🏦 速赢AI           │                 │
│           │                      │                 │
│           │  [邮箱输入框]         │                 │
│           │  [密码输入框]         │                 │
│           │  [□ 记住我]          │                 │
│           │  [  登  录  ]        │                 │
│           │                      │                 │
│           │  还没有账号？去注册 →  │                 │
│           └──────────────────────┘                 │
│                                                    │
└──────────────────────────────────────────────────┘
```

**字段与校验**:
| 字段 | 类型 | 校验规则 | 错误提示 |
|---|---|---|---|
| email | string (email) | 必填，合法邮箱格式 | "请输入有效的邮箱地址" |
| password | string | 必填，≥6 字符 | "密码至少 6 位" |
| remember | boolean | 可选 | — |

**交互流程**:
1. 用户填写邮箱 + 密码 → 点击"登录"
2. 调用 `POST /api/v1/auth/login`，按钮进入 loading 态
3. 成功 → 存储 token → 跳转到 `/`（或登录前目标页）
4. 失败 → 表单顶部显示错误提示（"邮箱或密码错误" / "账号已被禁用" 等服务端返回的 message）
5. 已登录用户访问 `/login` → 自动跳转 `/`

**文案**: 登录、邮箱、密码、记住我、还没有账号？去注册

### 3.2 RegisterPage — 注册页

**路由**: `/register`

**布局**: 与 LoginPage 对称布局，标题改为"创建账号"。

**字段与校验**:
| 字段 | 类型 | 校验规则 | 错误提示 |
|---|---|---|---|
| username | string | 必填，2-20 字符，字母/数字/下划线/中文 | "用户名为 2-20 个字符" |
| email | string (email) | 必填，合法邮箱格式 | "请输入有效的邮箱地址" |
| password | string | 必填，≥6 字符 | "密码至少 6 位" |
| confirmPassword | string | 必填，与 password 一致 | "两次密码输入不一致" |

**交互流程**:
1. 用户填写表单 → 实时前端校验
2. 点击"注册" → 调用 `POST /api/v1/auth/register`
3. 成功 → 自动登录（后端直接返回 token）→ 跳转 `/`
4. 失败 → 表单顶部错误提示（"邮箱已被注册" 等）
5. 已登录用户访问 `/register` → 自动跳转 `/`

**文案**: 注册、用户名、邮箱、密码、确认密码、已有账号？去登录

### 3.3 403 Forbidden 页

**路由**: 无独立路由，由 ProtectedRoute 组件在当前路由下渲染。

**布局**: 居中结果页（Ant Design `Result` 组件），status="403"，subTitle="您没有权限访问此页面"，extra 按钮"返回首页"。

---

## 4. 状态管理：AuthContext

### 4.1 数据结构

```typescript
// 角色枚举（与后端对齐）
type Role = 'admin' | 'internal_analyst' | 'external_analyst' | 'user';

interface User {
  id: number;
  username: string;
  email: string;
  role: Role;
  avatar?: string;          // 头像 URL，可选
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;  // 派生自 !!user && !!accessToken
  isLoading: boolean;        // 初始化时检查 token 有效性
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
  refreshAuth: () => Promise<void>;  // 手动刷新 token
}
```

### 4.2 Context 设计要点

- **AuthProvider** 包裹在 `<BrowserRouter>` 内层，位于 `<App>` 之上
- **初始化流程**：
  1. 组件挂载时检查 `localStorage` 中是否有 `refreshToken`
  2. 有 → 调用 `POST /api/v1/auth/refresh` 尝试获取新 accessToken
  3. 刷新成功 → 设置 user + token，`isLoading=false`
  4. 刷新失败 → 清除本地存储，`isLoading=false`（视为未登录）
  5. 无 → `isLoading=false`（未登录）
- **`hasRole`**: 接受变长角色参数，检查 `user.role` 是否在允许列表中
- **`login`/`register`**: async 函数，调用 API → 成功后存储 token + user 到 state + localStorage
- **`logout`**: 清除 state + localStorage → 跳转到 `/login`（可选调用后端 revoke 接口）

### 4.3 主入口注入点

`main.tsx` 调整（伪代码结构）：

```
<ConfigProvider>
  <BrowserRouter>
    <AuthProvider>       ← 新增
      <App />
    </AuthProvider>
  </BrowserRouter>
</ConfigProvider>
```

---

## 5. Token 存储与自动刷新

### 5.1 存储方案

| Token | 存储位置 | 理由 |
|---|---|---|
| `accessToken` | 内存（AuthContext state）+ `localStorage` | 页面刷新后仍需保留，避免每次刷新都要重新登录 |
| `refreshToken` | `localStorage` | 长期有效，用于获取新 accessToken |
| `user` | 内存 + `localStorage` | 导航栏展示用户名/头像 |

> **安全权衡**: 纯前端 SPA 无法使用 httpOnly cookie，localStorage 存在 XSS 风险。Phase 1 接受此权衡；若后续安全要求提升，改为 BFF 层代理 + httpOnly cookie。

### 5.2 自动刷新策略

- **触发时机**: 任何 API 调用返回 `401` 状态码
- **刷新流程**:
  1. axios 响应拦截器捕获 `401`
  2. 检查是否有 `refreshToken`，无则直接跳转 `/login`
  3. 调用 `POST /api/v1/auth/refresh`（带 `refreshToken`）
  4. 成功 → 更新内存 + localStorage 中的 token → 重放原始请求
  5. 失败 → 清除本地状态 → 跳转 `/login`
- **并发保护**: 多个请求同时遇到 401 时，只发一次 refresh 请求（用 Promise 锁），其余请求等待同一 refresh 结果

### 5.3 Token 过期时间假设

| Token | 有效期 | 说明 |
|---|---|---|
| accessToken | 15 min | 短有效期，减少泄露风险 |
| refreshToken | 7 days | 长有效期；后端可配置 |

> 实际过期时间以后端返回的 JWT `exp` 为准，前端不做时间判断，只靠 401 驱动刷新。

---

## 6. API 拦截器

### 6.1 改造 `api/client.ts`

在现有 axios 实例上挂载：

**请求拦截器**（request interceptor）:
- 从 AuthContext 的 `accessToken` 读取 token（通过外部注入或模块级变量）
- 附加 `Authorization: Bearer <accessToken>` header
- 已有 `Content-Type: application/json` 保持不变

**响应拦截器**（response interceptor）:
- `2xx` → 直接返回 `response`
- `401` → 触发 token 刷新流程（见 §5.2）
- `403` → 可选：全局 toast 提示"权限不足"
- 其他错误 → 保持现有行为（调用方自行 catch）

### 6.2 拦截器注入方式

由于 axios 实例是模块顶层创建的，拦截器需要访问 AuthContext 的 token 和 refresh 函数。两种方案：

**方案 A — 模块级闭包**（推荐）:
```typescript
// client.ts
let getAccessToken: (() => string | null) | null = null;
let onRefreshToken: (() => Promise<string | null>) | null = null;

export function injectAuth(
  getToken: () => string | null,
  refreshToken: () => Promise<string | null>,
  onForceLogout: () => void,
) {
  getAccessToken = getToken;
  onRefreshToken = refreshToken;
  // ... 注册拦截器
}
```
AuthProvider 在挂载时调用 `injectAuth(...)`，传入 context 中的 getter 函数。

**方案 B — 事件驱动**:
- 将 token 存储在 `window.__AUTH__` 或自定义 EventTarget 上
- 拦截器从中读取

**选择方案 A**：类型安全，不污染全局命名空间。

---

## 7. 路由守卫

### 7.1 ProtectedRoute 组件

```typescript
interface ProtectedRouteProps {
  children: React.ReactNode;
  roles?: Role[];  // 允许访问的角色列表；不传则只要求已登录
}
```

**行为逻辑**:

```
ProtectedRoute
 ├── AuthContext.isLoading === true
 │   └── 渲染全局 Spin（全屏加载中）
 ├── AuthContext.isAuthenticated === false
 │   └── <Navigate to="/login" state={{ from: location }} replace />
 ├── roles 未传 → 渲染 children
 ├── hasRole(...roles) === false
 │   └── 渲染 403 Forbidden 页面（Result 组件）
 └── 渲染 children
```

**`state.from`**: 登录成功后跳回原目标页（LoginPage 读取 `location.state?.from`）。

### 7.2 现有路由改造

在 `App.tsx` 中将现有 8 个 `<Route>` 包裹在 `<ProtectedRoute>` 中：

```tsx
<Routes>
  {/* 公开路由 */}
  <Route path="/login" element={<LoginPage />} />
  <Route path="/register" element={<RegisterPage />} />

  {/* 受保护路由 */}
  <Route path="/" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Dashboard /></ProtectedRoute>} />
  <Route path="/screener" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Screener /></ProtectedRoute>} />
  <Route path="/predictions" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Predictions /></ProtectedRoute>} />
  <Route path="/strategy" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Strategy /></ProtectedRoute>} />
  <Route path="/signals" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Signals /></ProtectedRoute>} />
  <Route path="/trade" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'user']}><Trade /></ProtectedRoute>} />
  <Route path="/backtest" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst']}><Backtest /></ProtectedRoute>} />
  <Route path="/diagnosis" element={<ProtectedRoute roles={['admin', 'internal_analyst', 'external_analyst', 'user']}><Diagnosis /></ProtectedRoute>} />

  {/* 404 兜底 */}
  <Route path="*" element={<Navigate to="/" replace />} />
</Routes>
```

### 7.3 权限映射表

源自 PRD §2.2 角色权限矩阵：

| 页面 | 路由 | 管理员 | 内部分析师 | 外部分析师 | 普通用户 | 备注 |
|---|---|---|---|---|---|---|
| AI 智能看板 | `/` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| 智能选股 | `/screener` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| K线预测 | `/predictions` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| 方案管理 | `/strategy` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| 交易信号 | `/signals` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| 交易中心 | `/trade` | ✅ | ✅ | ❌ | ✅ | 外部分析师不可交易 |
| 回测分析 | `/backtest` | ✅ | ✅ | ✅ | ❌ | 普通用户不可回测 |
| 个股诊断 | `/diagnosis` | ✅ | ✅ | ✅ | ✅ | Phase 1 全部可用 |
| 系统设置 | `/settings` | ✅ | ❌ | ❌ | ❌ | 仅管理员 |

### 7.4 菜单可见性控制

侧边栏菜单需要根据角色动态过滤：不具备某页面权限的角色，对应菜单项不渲染。

`menuItems` 本身变为函数（接收 `role` 参数），或使用 `useAuth()` hook 在组件内过滤。**建议**: 在 `App.tsx` 中用 `useAuth()` 获取 `user.role`，对 `menuItems` 数组 `filter`。

---

## 8. UI 设计要点

### 8.1 登录/注册页视觉

- **背景**: 深色渐变 (`#0d1117` → `#161b22`)，可选添加 K 线暗纹或网格线装饰
- **卡片**: 深色卡片 (`#1f1f1f` 或 `rgba(255,255,255,0.06)`)，`borderRadius: 8`，`boxShadow: 0 4px 24px rgba(0,0,0,0.4)`
- **品牌**: 卡片顶部显示 `StockOutlined` 图标 + "速赢AI" 文字（与侧边栏 Logo 一致）
- **按钮**: `type="primary"` 蓝色 `#1677ff`，全宽
- **输入框**: Ant Design `Input` + `Input.Password`，暗色主题适配（设置 `ConfigProvider` 局部暗色 theme）
- **链接**: "去注册" / "去登录" 使用 Ant Design `Link` 或 `Button type="link"`

### 8.2 导航栏用户区改造

替换现有 `App.tsx` 中硬编码的 `Avatar` + "Admin" 文字为动态内容：

```tsx
// 现有代码（Line 134-143）:
<Dropdown menu={{ items: [
  { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
  { key: 'logout', icon: <UserOutlined />, label: '退出登录' },
]}}>
  <Space>
    <Avatar icon={<UserOutlined />} />
    <span>Admin</span>
  </Space>
</Dropdown>

// 改造后:
<Dropdown menu={{ items: [
  { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
]}}>
  <Space>
    <Avatar src={user?.avatar} icon={<UserOutlined />} />
    <span>{user?.username || '未登录'}</span>
  </Space>
</Dropdown>
```

**下拉菜单项**:
| key | 图标 | 文案 | 行为 |
|---|---|---|---|
| `profile` | `UserOutlined` | 个人中心 | 跳转 `/profile`（或暂为 `void`） |
| `logout` | `LogoutOutlined` | 退出登录 | 调用 `logout()` |

> Phase 1 无"切换角色"功能（单用户单角色），菜单预留该 key。Phase 4 上线多角色后再加入。

### 8.3 全局 Loading 态

在 AuthProvider 初始化期间（检查 refresh token），整个应用渲染全局 Spin：

```tsx
// AuthProvider 内
if (isLoading) {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#f5f5f5' }}>
      <Spin size="large" tip="加载中..." />
    </div>
  );
}
```

---

## 9. 组件树与文件结构

### 9.1 新增文件

```
frontend/src/
├── api/
│   └── client.ts              # [修改] 新增拦截器注入
├── contexts/
│   └── AuthContext.tsx         # [新增] AuthProvider + useAuth hook
├── components/
│   └── auth/
│       ├── ProtectedRoute.tsx  # [新增] 路由守卫
│       ├── LoginPage.tsx       # [新增] 登录页面
│       └── RegisterPage.tsx    # [新增] 注册页面
├── App.tsx                     # [修改] 包裹 ProtectedRoute + 动态菜单 + 动态头像
├── main.tsx                    # [修改] 注入 AuthProvider
```

> 注：页面组件放在 `components/auth/` 而非 `pages/`，因为它们属于 auth 功能模块，不是独立业务页面。若团队偏好统一放在 `pages/`，也可调整为 `pages/auth/LoginPage.tsx` + `pages/auth/RegisterPage.tsx`。

### 9.2 组件关系图

```
<ConfigProvider>
  <BrowserRouter>
    <AuthProvider>                    ← contexts/AuthContext.tsx
      <App>                          ← src/App.tsx (修改)
        <Layout>
          <Sider> (动态菜单)           ← 根据 role filter menuItems
          <Layout>
            <Header> (动态头像+下拉)    ← useAuth().user
            <Content>
              <Routes>
                <Route /login → LoginPage>         ← components/auth/LoginPage.tsx
                <Route /register → RegisterPage>    ← components/auth/RegisterPage.tsx
                <Route /* → ProtectedRoute>         ← components/auth/ProtectedRoute.tsx
                  <PageComponent />
                </Route>
              </Routes>
            </Content>
          </Layout>
        </Layout>
      </App>
    </AuthProvider>
  </BrowserRouter>
</ConfigProvider>
```

---

## 10. 实现步骤建议

| 步骤 | 内容 | 依赖 | 预计改动文件数 |
|---|---|---|---|
| 1 | 与 backend-dev 对齐 API 契约（详见 §12） | — | 0 |
| 2 | 创建 `AuthContext.tsx`（Provider + hook + 类型定义） | §12 契约 | 1 |
| 3 | 改造 `api/client.ts`（拦截器注入） | AuthContext | 1 |
| 4 | 创建 `ProtectedRoute.tsx` | AuthContext | 1 |
| 5 | 创建 `LoginPage.tsx` + `RegisterPage.tsx` | api/client | 2 |
| 6 | 改造 `App.tsx`（路由守卫 + 动态菜单 + 动态头像） | ProtectedRoute + AuthContext | 1 |
| 7 | 改造 `main.tsx`（注入 AuthProvider） | AuthContext | 1 |
| 8 | 编写 Unit 测试 + SIT 测试 | 全部完成 | 3 |

---

## 11. Phase 1 简化说明

Phase 1 仅上线 **admin** 和 **user** 两个角色，但：

- Role 枚举保留四角色定义（TypeScript 字面量联合类型）
- `ProtectedRoute` 的 `roles` 参数按四角色完整配置
- 侧边栏菜单过滤逻辑按四角色完整实现
- 后端用户表/注册接口也预留四角色字段（由 backend-dev 保障）

这样 Phase 4 上线内/外部分析师时，**前端只需后端配置新用户角色，无需改任何前端代码**。

---

## 12. 附录：API 契约草案（待 backend-dev 确认）

### POST /api/v1/auth/login

```
Request:
{
  "email": "string",
  "password": "string"
}

Response 200:
{
  "access_token": "string (JWT)",
  "refresh_token": "string",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "roger",
    "email": "roger@example.com",
    "role": "admin",
    "avatar": "https://..." | null
  }
}

Response 401:
{
  "detail": "邮箱或密码错误"
}
```

### POST /api/v1/auth/register

```
Request:
{
  "username": "string (2-20 chars)",
  "email": "string (valid email)",
  "password": "string (≥6 chars)"
}

Response 201:
{
  "access_token": "string (JWT)",
  "refresh_token": "string",
  "token_type": "bearer",
  "user": { ... }  // 同 login
}

Response 409:
{
  "detail": "邮箱已被注册"
}
```

### POST /api/v1/auth/refresh

```
Request:
{
  "refresh_token": "string"
}

Response 200:
{
  "access_token": "string (JWT)",
  "refresh_token": "string",  // 轮转：旧 refreshToken 失效，发新的
  "token_type": "bearer"
}

Response 401:
{
  "detail": "Token 已过期或无效"
}
```

### GET /api/v1/auth/me（可选，Phase 1 可不实现）

```
Headers: Authorization: Bearer <access_token>

Response 200:
{
  "id": 1,
  "username": "roger",
  "email": "roger@example.com",
  "role": "admin",
  "avatar": null
}
```

---

> **下一步**: product-lead 确认本方案后，frontend-dev 与 backend-dev 对齐 API 契约（SendMessage），然后进入实现阶段。
