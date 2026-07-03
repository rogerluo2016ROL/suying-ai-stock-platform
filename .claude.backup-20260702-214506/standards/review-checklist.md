# Code Review Checklist

> **权威来源**：本文件是 `code-reviewer` 审查时必须逐条核对的操作性 checklist，与 `.claude/agents/code-reviewer.md` 的铁律和 `.claude/standards/security.md` OWASP 基线共同构成完整审查框架。三者不重复——本文件只覆盖项目特有的结构性检查项。
>
> **触发时机**：product-lead 派单触发 code review 时，code-reviewer 读 diff 前先过本 checklist 确定审查焦点；写报告时按 checklist 项逐条标注结果。

---

## 1. DB Model 字段变更覆盖检查（#13 教训 — 必查项）

> **根因**：Issue #13 (avatar_path) 审计发现，新增字段测试仅覆盖 CRUD endpoint，漏掉 `list_all_with_stats()` 聚合路径，导致列表页字段静默为 `null`，close 后 49h 才追补修复。

### 核心原则

> **endpoint-level SIT pass ≠ view-integration layer pass**
>
> CRUD endpoint 与聚合查询（`list_all_with_stats()` / `list_with_counts()` / 其他 JOIN 查询方法）走不同代码路径。CRUD endpoint IT 通过，不能推断列表 endpoint 的 Pydantic 构造器已正确传入该字段。

### 触发条件

PR 满足以下任一即触发本节全部检查：

- 新增 DB ORM 模型字段（`Column` / `mapped_column`）
- 修改已有字段名、类型或默认值
- 新增 Pydantic schema 字段（`BaseModel` / `SQLModel`）
- 修改聚合 service 方法（`list_*` / `get_all_*` / `*_with_stats` / `*_with_counts`）

### 检查项（逐条，缺一不可）

#### CHK-F1: Detail endpoint 覆盖（基础项）
- [ ] 存在至少 1 个 IT 调用 detail endpoint（`GET /api/{resource}/{id}`）并断言新字段值正确（非 `null` / 非默认值）
- **Severity**：Critical（缺失）

#### CHK-F2: List endpoint 覆盖（重点项 — #13 教训核心）
- [ ] 存在至少 1 个 IT 调用 list endpoint（`GET /api/{resource}` 或等价批量端点）并断言对应 item 的新字段值正确（非 `null` / 非默认值）
- [ ] 该 IT 不能与 CHK-F1 合并——list 与 detail endpoint 走不同代码路径，必须独立 IT
- **Severity**：**Critical**（缺失，列表页字段静默丢失是 P1 级 UI 断层）

#### CHK-F3: 聚合服务方法构造器核查
- [ ] 找到 list service 方法中对应的 Pydantic 模型构造器（通常是 `PersonaInfo(...)` / `MaterialOut(...)` 等）
- [ ] 确认构造器显式传入了新字段（`new_field=p.new_field`），而非依赖 `**kwargs` 或 ORM lazy 映射
- [ ] 若聚合方法有多处构造器调用（如 list + export + search），逐一检查
- **Severity**：Critical（漏传 → list endpoint 静默返回 `null` / 默认值）

#### CHK-F4: SIT Audit 关联（与 SIT Audit 协议衔接）

做 SIT Audit（`progress/<role>.md` 证据审计）时，发现以下情况则对应 AC 覆盖项判定为 **❌**（触发 `Redo SIT`）：
- SIT 证据仅含 detail endpoint / POST / PATCH 的 IT，无 list endpoint 的字段断言
- SIT 证据无 `GET /api/{resource}` list 路径的 curl / pytest 输出

> **直接对应条目**：SIT Audit 检查项 2「AC 覆盖」——"聚合查询路径需独立覆盖，不能依赖 CRUD 测试隐含"

### 报告写法（review 报告内）

```markdown
## DB 字段覆盖检查（#13 checklist）

| 检查项 | 状态 | 备注 |
|---|---|---|
| CHK-F1 detail endpoint IT | ✅ / ❌ | [IT 文件:行号 或 缺失说明] |
| CHK-F2 list endpoint IT | ✅ / ❌ | [IT 文件:行号 或 缺失说明] |
| CHK-F3 聚合构造器核查 | ✅ / ❌ | [service.py:行号 或 缺失字段] |
```

若 CHK-F2 / CHK-F3 任一为 ❌，在 Critical 节写入：
```
- [ ] service.py:NNN — list endpoint 漏传字段 `xxx`，聚合构造器缺 `xxx=p.xxx`
    复现：① POST /api/personas/{id}/avatar 上传成功，② GET /api/personas 列表响应中 avatar_path=null
    修复：在 list_all_with_stats() PersonaInfo 构造器加 `xxx=p.xxx`
```

---

## 2. Cron-Driven Feature 覆盖检查（#16 教训）

> **权威来源**：`.claude/standards/testing.md` §"Cron-Driven Feature E2E（强制覆盖项）"
>
> 本节是 code-reviewer 做 SIT Audit 时的快速对照入口——若 dev SIT 证据只覆盖 BE schema + cron 注册而未覆盖 cron 实际 tick + 消费链路，直接判 `❌ Redo SIT`。

### 触发条件

PR 涉及以下任一：
- taskiq / Redis 周期 task 注册（`@scheduler.task` / `broker.kick`）
- `_TASK_TYPE_MAP` 新增 task 类型
- 消费 worker 函数签名变更（参数增减）

### 检查项（SIT Audit 关联）

| 检查项 | 若缺失 | SIT Audit 判定 |
|---|---|---|
| cron 实际 tick 验证（手动触发 or broker.kick） | SIT 只验注册，不验执行 | `❌ Redo SIT` |
| worker 消费链路断言（logs / DB / task_status） | 消费链路未覆盖 | `❌ Redo SIT` |
| Worker 函数签名一致性（call site vs 定义） | 运行时 TypeError | **Critical** |

---

## 3. 前端接入完整性检查（#16 教训）

### 触发条件

PR labels 含 `area:frontend` 或 PR 描述声明"前端接入"。

### 检查项

- [ ] TS 类型（`types.gen.ts` / `*.ts` API 类型）含新字段
- [ ] 相关页面 / 组件实际使用新字段（非零引用）
- [ ] 若 PR 是后端字段扩展，检查前端 API client 是否同步更新
- **Severity**：Critical（字段存在于 BE 但 FE TS 类型零引用 → 用户无 UI 入口）

---

## 4. 铁律合规检查

| 规则 | 检查项 | Severity |
|---|---|---|
| 禁 mock（**production code only**；test fixtures / `mockWxMethod` / SIT 外部 API mock 例外）| PR diff 在生产代码路径无 `setTimeout`（业务逻辑）/ `_mock` / `VITE_MOCK_*`；issue close evidence 中禁 mock 见 `qa-close-verify.md` §2.2 | Critical（生产路径）/ Warning（其他） |
| 新代码优先 | 无 backward-compat 兼容层 / 无 `if old_version` 双分支并存 | Warning |
| 模型禁 hardcode | `models.toml` 是 LLM model ID 唯一来源，业务代码无 hardcode model string | Critical |
| import-linter | 跨模块 import 未违反 `backend/app/modules/*` 隔离规则 | Warning |

---

## 5. 安全快速核对（详细清单见 `.claude/standards/security.md`）

| OWASP 项 | 快速检查点 |
|---|---|
| A01 Broken Access Control | 每个受保护 endpoint 有 `require_owner_or_assistant` / `get_current_user` 依赖 |
| A03 SQL Injection | 查询全部参数化（SQLAlchemy ORM / `text()` + bindparams），无字符串拼接 |
| A05 Security Misconfiguration | CORS 无 `allow_origins=["*"]` + `credentials=True` 同时出现 |
| A07 Auth Failures | 新 endpoint 无遗漏认证 |
| 硬编码凭证 | 无 API key / secret / password literal |

> **辅助工具**：核对本表前，可先用内置 `/security-review` 对当前 diff 跑一遍自动安全扫描（OWASP 维度），把发现作为逐项核对的输入——不替代人工核对，只缩小搜索面。CI / 非交互场景的整体 review 走 `claude ultrareview`（详 [`workflow.md`](workflow.md) §Fan-out 硬约束）。

---

## Checklist 维护记录

| 日期 | 变更 | 触发 issue | 作者 |
|---|---|---|---|
| 2026-05-17 | 初始建立 — CHK-F1/F2/F3/F4 双 endpoint 覆盖检查；Cron-Driven / FE 接入 / 铁律合规检查 / OWASP 快查 | #47（#13 教训落地） | code-reviewer |
