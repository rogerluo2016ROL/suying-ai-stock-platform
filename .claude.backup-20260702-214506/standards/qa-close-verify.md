# P0/P1 Issue Close Verify SOP

> **触发教训**: Issue #37 Premature Close — `dc512fa` 修复代码 commit 后立即 close，但容器未重建，fix 未上线；实际由 #39 hot-fix fe9ab58 + 容器重建 + `curl 实证（cost ¥301.76 → HTTP 422 + 中文 detail）`才完成验收。
> **合规样本**: 合规 close comment 含完整 curl 命令 + response body（样本源自 RolexOps 实战，不随模板分发；§3 模板据此提炼）。

---

## 适用范围

> **与 SIT Audit 的分工**（防同一证据被验两遍）：SIT Audit（code review 阶段，见 [`workflow.md`](workflow.md)）审**开发阶段集成验证**证据，不要求容器重建；本 SOP 只管 **P0/P1 issue close 前的部署后端到端实证**（容器重建 + 真实 curl）。dev 不需要在 progress SIT 证据段重复提交 close-verify 级证据，反之亦然。

| 严重度 | Close 前必须本 SOP | 备注 |
|---|---|---|
| **P0** | ✅ 必须 | 所有步骤 |
| **P1** | ✅ 必须 | 所有步骤 |
| P2 | ⚠️ 建议 | 至少完成 §2 Evidence 要求 |
| P3 / chore | — | 不适用 |

---

## §1 Close 前 Checklist（Close-Gate）

关闭 P0/P1 issue 前**发起方必须逐条打勾**；code-reviewer review 时可拦截任一未勾项。

### 1.1 修复验证

- [ ] **代码路径确认**：定位引发 bug 的具体文件 + 行号，确认 fix 已覆盖该路径
- [ ] **AC 边界触发**：用 **真实 curl / pytest / Playwright** 命令**实际触发**原 bug 的 AC 边界条件（不接受"读代码逻辑判断已修复"）
- [ ] **Response body 可见**：命令输出含完整 HTTP 状态码 + response body（或 DB row / log line），敏感字段可打码但结构必须完整

### 1.2 容器化部署专项（使用 docker compose 时必做）

> **教训 #37**：代码 commit 后未重建容器，旧镜像仍在运行，close 时 fix 实际未上线。

- [ ] **容器重建**：fix commit 后执行 `docker compose up --build -d <service>` 或等价命令（不接受仅 `docker compose restart`，重启不重建镜像）
- [ ] **重建后 curl 实证**：**重建完成后**再次执行边界验证命令，output 中时间戳或 response 差异可证明是新镜像响应
- [ ] **旧容器无遗留**：`docker compose ps` 确认相关 service `Up` 而非 `Restarting` 或 `Exit`

### 1.3 回归验证

- [ ] **同模块邻近 AC 未退化**：至少跑一条同文件 / 同模块的 SIT case，确认 fix 无 side effect
- [ ] **关联 issue 无连带**：检查关联 issue（issue body 里的 Related / Blocked by），确认不受本次 fix 影响

### 1.4 文档同步

- [ ] **Close comment 含 Evidence**：按 §3 模板写 close comment，不允许只写"已修复，见 commit XXXXXX"
- [ ] **PR / commit 引用**：close comment 须含修复 commit hash（完整 7 位或以上）

---

## §2 Evidence 质量要求

### 2.1 必须包含的产物（至少一项；P0 建议多项）

| 场景 | 合规 Evidence | 不合规（拒绝 close） |
|---|---|---|
| API Bug | `curl -i` 完整响应头 + body | 仅 diff + "逻辑分析表明已修复" |
| DB Bug | `SELECT` 前后对比（row 级别） | 仅截图 / 仅 ORM 代码 |
| Frontend Bug | Playwright 截图 + console log clean | 仅 "界面看起来正常" |
| LLM Output Bug | 3 次真实 LLM 调用输出（结构符合预期） | 仅 prompt 代码修改 diff |
| 容器化 fix | 重建后 curl（有新镜像时间戳或 diff 证明） | 重建前 curl 截图 |

### 2.2 禁止使用的 Evidence 形式

```
❌ 代码 diff + 注释"此处逻辑已修复"
❌ 截图无时间戳（无法区分修复前/后）
❌ 纯文字描述"测试通过，无问题"
❌ curl mock（铁律：**issue close 边界验证证据中禁 mock，必须真实接入**；SIT / 单元测试内 mock 外部 API、miniapp E2E 用 `mockWxMethod` 仍允许，本铁律仅约束 close-verify evidence）
❌ 仅 log 无对应请求记录（无法溯源）
```

### 2.3 Evidence 格式模板（curl 示例）

```bash
# ✅ 合规 Evidence 示例（#39 合规样本风格）

# 修复后容器重建
$ docker compose up --build -d backend
[+] Building 12.3s (10/10) FINISHED
...

# 容器重建后边界验证
$ curl -i -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"cost": 301.76, "persona_id": 1}'

HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{"detail": "cost 超出预算上限，请调整参数"}

# 回归验证（正常路径不退化）
$ curl -i -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"cost": 0.5, "persona_id": 1}'

HTTP/1.1 200 OK
{"task_id": "abc123", "status": "queued"}
```

---

## §3 gh Issue Close Comment 模板

关闭 P0/P1 issue 时**必须**用下列模板写 close comment（`gh issue comment` 或 GitHub UI）：

```markdown
## Close Verify Report — Issue #[N]

**修复 Commit**: [hash 7位+] — [commit message 简写]
**验证时间**: YYYY-MM-DD HH:MM CST
**验证者**: [role]

### 修复定位
- **文件**: `path/to/file.py:L行号`
- **根因**: [1行说明根因]
- **Fix 方案**: [1行说明修复方式]

### AC 边界验证

**边界触发命令**:
```bash
[实际使用的 curl / pytest / playwright 命令]
```

**命令输出（重建后）**:
```
[完整 response body / test output，敏感字段打码]
```

**结论**: ✅ 边界条件符合 PRD AC / ❌ 偏差（见下方 Notes）

### 容器重建验证（若使用 docker compose）
- [ ] `docker compose up --build -d [service]` 已执行
- [ ] 重建后 curl 输出已含在上方（时间戳 / diff 可证明新镜像）
- [ ] `docker compose ps` 确认服务 `Up`

### 回归验证
- **同模块用例**: [执行命令] → ✅ Pass / ❌ Fail
- **关联 issue 影响**: ✅ 无连带 / ⚠️ 见 [issue #N]

### Notes（可选）
[已知 P2 后续 / 边缘 case / 下一步行动]
```

---

## §4 Code-Reviewer Close-Gate 职责

code-reviewer 在 review PR / 接到 close 通知时**有权拦截**以下情形，要求补 evidence：

| 拦截条件 | 要求补充 |
|---|---|
| Close comment 无 curl / test 输出 | 补 §3 模板中的 Evidence 段 |
| 容器化 fix 无重建证明 | 补 `docker compose up --build` + 重建后 curl |
| Evidence 时间戳早于 fix commit | 重跑并附新截图 |
| 仅 diff + 逻辑分析 | 补真实命令输出 |
| `curl mock` 输出（铁律禁止） | 必须真实接入后重验 |

**拦截方式**：在 PR comment / issue comment 写明缺失项，**不 approve close**，直到补齐。

---

## §5 快速自检（Close 前 30 秒）

```
□ 有真实 curl / pytest / playwright 输出？
□ 容器化场景：输出来自重建后的容器？
□ Response body 完整可见（非"200 OK"一行了事）？
□ Close comment 按 §3 模板写了？
□ code-reviewer 已 review 或本 SOP 已自检完毕？
```

**任一未勾 → 不 close**。

---

## 附录：反面教材 vs 合规样本

| | #37 Premature Close ❌ | #39 Hot-fix Close ✅ |
|---|---|---|
| Evidence | commit dc512fa diff + 逻辑说明 | `curl -i` 完整 422 response body |
| 容器重建 | ❌ 未重建，旧镜像在跑 | ✅ fe9ab58 hot-fix 含重建后验证 |
| 时效性 | Close 时 fix 未上线 | Close 时已在线可验 |
| 可重现性 | ❌ 他人无法独立复现 | ✅ curl 命令可直接复制执行 |
| 结果 | 需要 #39 重开修复 | Issue 真正关闭 |
