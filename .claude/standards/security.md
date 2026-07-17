# Security Baseline

## Security

团队安全基线（基于 OWASP Top 10），开发者实现时必须遵守，code-reviewer 审查时逐条核对：

- [ ] 所有查询使用参数化，禁止字符串拼接 SQL（SQL 注入）
- [ ] 输出编码、配置 CSP headers（XSS）
- [ ] shell 命令中无未清理的输入（命令注入）
- [ ] 认证和授权在每个受保护端点正确执行
- [ ] 不硬编码密钥、凭证或 API key
- [ ] 敏感数据不入日志，错误信息不暴露堆栈或内部细节
- [ ] 输入验证在系统边界做（用户输入、外部 API 响应）
- [ ] 公共端点配置限流
- [ ] CORS 配置正确（白名单源，不用 `*` 配 `credentials: true`）
- [ ] 依赖无已知关键 CVE（定期 `npm audit` / `pip-audit` 等扫描）

## Tool-level Hard Constraints

本节是**项目级实现回链**——本 standards 文件保留团队通用安全基线，具体 hook 拦截清单作为项目级实现位于 `CLAUDE.md` "Tool Boundaries" 节。

### 四层 Hook 防御（注册位置：`.claude/settings.json` + `.git/hooks/pre-commit`）

> 前 3 层运行时（agent 工具调用时拦截）+ 第 4 层 commit 时（防 Edit/Write 绕过 prompt 扫描）。

| 层 | 时机 | 文件 | 行为 | 防御目标 |
|---|---|---|---|---|
| 1. Bash 拦截 | `PreToolUse` (matcher: `Bash`) | `.claude/hooks/block-dangerous-bash.sh` | exit 2 硬阻断 | 防 agent 跑出毁灭性命令（`rm -rf`、`DROP TABLE/DATABASE/SCHEMA`、`git push --force`、`git reset --hard`、`curl\|sh` 下载即执行）+ **`git commit --no-verify`/`-n`/`core.hooksPath` 绕过 pre-commit**（rule #6，堵 scan-commit 旁路，ADR-017）|
| 1b. 配置保护 | `PreToolUse` (matcher: `Edit\|Write`) | `.claude/hooks/block-config-edit.sh` | exit 2（已存在配置）/ 放行（首次创建）| 防 agent 改 lint/format 配置弱化规则（`.eslintrc`/`.prettierrc`/`ruff.toml`/`.shellcheckrc`/`.swiftformat` 等），steer 修代码而非弱化门（ADR-017）|
| 1c. 角色边界 | `PreToolUse` (matcher: `Edit\|Write`) | `.claude/hooks/enforce-write-scope.sh` | exit 2（越界）/ 放行（在 write_scope 下）| 按 `roles.yaml` `boundary.write_scope` 拦角色越界写（code-reviewer 只 `docs/reviews/`、qa 只 `docs/qa/`、deploy 只 `docs/deploy/`）；主线程 + 无 boundary 角色（dev 等）放行；ADR-018|
| 2. Secret 扫描 | `UserPromptSubmit` | `.claude/hooks/scan-secrets.sh` | exit 2 硬阻断 | 防用户把 API key / Token / PEM 私钥粘进对话；模式覆盖 AWS / GitHub / OpenAI / Anthropic / Google / Slack / DeepSeek / Doubao / Qwen / MiniMax / Apple 签名材料（ASC API key / match 密码 / fastlane session 的 inline `KEY=value` 形式 + `.p8` 的 PEM 内容经第 7 行 PEM 规则，见 ADR-009）。**注**：`.p12` / `.mobileprovision` 是二进制（PKCS#12 / plist），文本正则**无法**匹配 → 不在本层扫描覆盖内，改由 `.claude/settings.json` 的 `permissions.deny` 按扩展名**拦读**（`Read(./**/*.p12)` / `*.mobileprovision` / `*.p8`），别误以为粘贴二进制签名文件会被本层挡 |
| 3. 工具输出净化 | `PostToolUse` (matcher: `WebFetch\|WebSearch\|Read\|Bash\|mcp__.*`) | `.claude/hooks/sanitize-tool-output.sh` | exit 0 + stderr WARNING（软告警，不阻断） | 防外部内容夹带的 prompt injection 指令被 agent 当成系统提示执行（含所有 MCP 工具输出） |

**回归测试**（统一在 `.claude/hooks/tests/`，由 `lint-all.sh` 跑全部 `test-*.sh`）：
- `.claude/hooks/tests/test-block-dangerous-bash.sh`（覆盖 rm -rf / DROP / git push --force / git reset --hard 各形态 + edge case 的回归测试套）
- `.claude/hooks/tests/test-scan-secrets.sh`（覆盖 scan-secrets + sanitize-tool-output + BIP39 + SSH/PuTTY 场景的回归测试套）
- `.claude/hooks/tests/test-secret-pattern-parity.sh`（守 scan-secrets ↔ scan-commit 厂商覆盖面一致）

**Hook 形态**：当前所有 hook 均为 `type: "command"`（shell 脚本）。Claude Code 另支持 `type: "mcp_tool"`，hook 可直接调 MCP 工具而无需 shell 中转——未来如需让 hook 调 chrome-devtools-mcp（截图取证）或 MiniMax（内容审核）时再切换；当前用例不涉及，保持 shell 路径以便 git 评审与离线测试。

### 第 4 层：Git Pre-commit 扫描（防止 Edit/Write 绕过 prompt-time 扫描）

`.claude/hooks/scan-commit.sh` 复用 `scan-secrets.sh` 同一套正则，对 `git diff --staged` 的新增行扫描。**这是必须的补防线**——`UserPromptSubmit` 只看 prompt，agent 用 `Edit`/`Write` 直接落盘的内容不经 prompt，会绕过第 2 层。

**安装**：`setup/init-team.sh` 已自动检测并安装此 symlink（缺失即建链、已存在但非 scan-commit 即告警，见其 §3b），**跑过 `init-team.sh` / `install-to-existing.sh` 的项目无需手动**。下面命令仅为手动补装 / 排障备用（每个 clone 一次）：

```bash
ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit
```

或：

```bash
git config core.hooksPath .claude/hooks/git-hooks  # 进阶：把 git-hooks/ 单独建目录
```

**额外覆盖**（scan-secrets.sh 没有的）：
- BIP39 助记词（mnemonic + 12+ lowercase short words 双因子匹配）
- OpenSSH/PuTTY 私钥块
- 通用 `*_TOKEN/_SECRET/_KEY=` 高熵值（兜底覆盖未枚举厂商）

**紧急绕过**：`git commit --no-verify`。**任何 `--no-verify` 都必须在 `docs/reviews/` 下记录原因**（test fixture / 已知白名单等），由 code-reviewer 复核。

### 第 5 层（推荐叠加）：`security-guidance` plugin — 代码级危险模式（Anthropic 原生 · 免费）

上面四层是 AGF 自有 hook，覆盖**毁灭性命令 / 密钥 / 注入文本 / commit 落盘**；但**代码级危险模式**——`eval` / `new Function`、XSS（`dangerouslySetInnerHTML` / `innerHTML`）、Python `pickle` 反序列化、`os.system` / `child_process.exec`、GitHub Actions 命令注入——AGF 的 bash/secret hook **不覆盖**。Anthropic 官方 `security-guidance` plugin 正好补这一层：它注册 `PostToolUse`（`Edit` / `Write` / `NotebookEdit`），**编辑落地后**即时按模式扫描并把告警**追加进 Claude 的下一步上下文**（**不阻断写入 / 提交**——官方明示「None of the layers block writes or commits」，见 security-guidance），给修复建议；价值是**减少流向下游 review 的危险代码量**而非硬门，与 AGF 的 hook 防御**同机制、零冲突**。

**安装（强烈推荐，每个 clone 一次）**：

```
/plugin install security-guidance@claude-plugins-official
```

**定位**：defense-in-depth 第 5 层（代码模式），与 code-reviewer 手工 OWASP **互补不替代**——它自动挡常见模式，reviewer 聚焦逻辑 / 架构 / 业务越权。**优雅降级**：未装时 AGF 四层 hook + 手工 OWASP 仍成立，只少一道自动网（故标"推荐"而非"硬依赖"）。

### Hook 运行时 profile（ADR-014）

四层防御 + `block-config-edit` + `enforce-write-scope` + `validate-verdict` 是**安全 SSOT，永不响应 profile**；6 个团队协调类 workflow hook 可运行时降级：

| 类别 | hook | profile 行为 |
|---|---|---|
| **永不响应**（安全） | `block-dangerous-bash` / `block-config-edit` / `enforce-write-scope` / `scan-secrets` / `sanitize-tool-output` / `scan-commit` / `validate-verdict` | 任何 profile 下全开 |
| **可降级**（协调） | `teammate-keepalive` / `check-progress-file` / `session-start-context` / `validate-task-schema` / `gate-deploy-release-auth` / `gate-redo-fuse` | `AGF_HOOK_PROFILE=minimal` 关，`standard`（默认）开 |

- `AGF_HOOK_PROFILE=minimal|standard`（默认 `standard`，未设=零回归）+ `AGF_DISABLED_HOOKS=id1,id2`（精确关单个非安全 hook；对安全 hook 无效——边界硬约束）
- fast lane（ADR-011）= `minimal`，**机械实现"只减不跳"**
- env 须 `export`（shell 变量不传 hook 子进程）

~~opt-in 治理事件留痕~~（`AGF_GOVERNANCE_LOG`）：已按 ADR-026 D6 退役（v6.26.0，默认全关且字段路径从未被真实验证）；如需运行时观测走 observability.md 的 OTEL 路径。

### Permission Deny 清单（settings.json）

`.claude/settings.json` 的 `permissions.deny` 已禁读以下敏感路径：`./.env*`、`./secrets/**`、`~/.ssh/**`、`~/.aws/**`、`~/.gnupg/**`、`~/.kube/config`、`~/.config/gcloud/**`、`~/.docker/config.json`、`~/.netrc`、`~/.pgpass` + Apple 签名材料二进制 `./**/*.p12`、`./**/*.mobileprovision`、`./**/*.p8`（PKCS#12 / plist / PEM key 文件，文本扫描抓不到 → 按扩展名拦读，见 §2 注）；并禁 `eval` 等远程执行链路。新增敏感路径时同步该清单。

> **`curl|sh`「下载即执行」改由第 1 层 hook 拦，不再放 deny 清单**：官方明示 `Bash(curl *|*sh*)` 这类**约束命令参数**的权限 glob **脆弱**——可被变量（`URL=x && curl $URL|sh`）/ 协议 / 无空格 / 多管道变体绕过，且 `|` 在单条规则里非「逻辑或」语义（见 permissions "Bash permission patterns that try to constrain command arguments are fragile"）。故已从 `permissions.deny` 移除这 4 条 glob，下沉到 `block-dangerous-bash.sh` 的 **anchored + quote-strip** 规则（rule #5，可靠匹配 `curl…|…sh` shape、不误伤健康检查 / `curl|jq` / 引号内文档，回归用例 AC-2e/AC-6f）。
>
> **残留边界（需知会）**：该 hook 仍只挡**命令行** `curl…|…sh` shape；「下载到文件再单独执行」（`curl x -o f && sh f`）属 **data-flow 边界**、不拦（见下「Hook Coverage Boundary」），靠 No Equivalent Bypass 纪律兜底。`Read(./.env*)` 等 deny 也**不拦子进程间接读**（`python -c "open('.env')"`）、不覆盖父目录——需 **OS 级硬隔离**时叠加官方 `/sandbox`（filesystem / network 边界），deny 清单不等于 OS 边界。

**细粒度 spawn 护栏（可选，v2.1.178+）**：Claude Code 支持 `Tool(param:value)` 权限语法（按工具入参匹配、含 `*` 通配），如 `Agent(model:opus)` 拦截 spawn opus 类 subagent/teammate、`Agent(name:foo)` 限定可 spawn 的命名 teammate。**AGF 模板默认不加此类 deny**——盲加 `Agent(model:opus)` 会误伤合法 opus 角色（`product-lead` / `tech-lead` / `ai-agent-dev`）；per-role 模型/工具管控已由 `roles.yaml` 的 `tools` 白名单 + `cost-budget.md` model 路由覆盖。maintainer 如需临时封锁特定 spawn（成本应急 / 调试），可针对性加 `Agent(...)` 规则，属一次性运维动作、非模板基线。

> 模板复用提示：若把 `standards/` 抽出作跨项目模板，本节应留下，但 hook 文件本身、settings.json 的 hook 注册块、CLAUDE.md 的 "Tool Boundaries" 节会随项目走，需新项目重新建立。

### 诚实层 gates（ADR-023 / ADR-024）

对标 claude-code-harness，把"声称 ↔ 现实"与"安全配置非回归"机械化。均由 `lint-all.sh` / pre-commit 链调：

- **deny 非回归门 `agf-deny-baseline.sh`**（hard-block）：`permissions.deny` 受 baseline `.claude/security/deny-baseline.json`（排序 entries + sha256）守护——deny 条目被悄悄删（安全边界弱化）或 baseline 被篡改 → exit 2；新增 deny 放行；有意变更后 `--update` 重签 + PR 说明。补 `block-config-edit`（护 lint 配置）不覆盖的 deny-列表-收缩攻击面（对标 selfaudit DenyBaseline）。
- **claims-audit `agf-claims-audit.sh`**（hard-block A/B + advisory C）：校验 CLAUDE.md 治理声称 ↔ 现实——已注册 hook 必有磁盘脚本（A）、CLAUDE.md 点名的 AGF 脚本必存在（B，防幽灵声称 / 改名漂移）、已注册 hook 应有文档（C，advisory）。消灭 AGF 自身 `written≠working`。
- **诚实 SSOT `docs/known-limitations.md`**：模板本体能力的强制强度（hard-block/advisory/model-dependent/process-dependent）+ 证据三态（executed/not-observed/absent）声称审计表——**各 hook / gate 的真实强度以该表为准**（部分软控制在 prose 里措辞偏硬，该表做诚实校准）。
- ~~模块级可达性 advisory `agf-wiring-check.sh`~~：已按 ADR-026 D2 退役（v6.26.0）；codemap `orphans` 子命令保留，需要时手动 `/agf-code-map`。

### No Equivalent Bypass（hook 等价绕过禁令）

hook 的设计意图是"决策权升级"，不是"等 agent 找到等价方式继续"。任何 agent 撞到 hook 阻断时：

1. **必须立即停下**，不许寻找功能等价的替代命令绕过 hook
2. **必须 SendMessage 给 product-lead**，附完整命令 + exit code + 执行意图
3. **必须等待书面授权**：product-lead 评估后，要么让用户手动执行，要么显式书面授权使用替代方式
4. **拿到授权后**才可继续

**明确禁止的等价绕过示例**（非穷举）：

| 被 hook 阻断的命令 | 禁止的"等价"替代 |
|---|---|
| `rm -rf <path>` | `python -c "import shutil; shutil.rmtree(...)"` / `find <path> -delete` / `mv <path> /tmp && rm -rf /tmp/...` |
| `git reset --hard` | `git checkout -- .` + `git clean -fd` 组合 / `git update-ref` 直接改引用 |
| `git push --force` | `git push --force-with-lease`（除非 product-lead 明确授权该弱化形式） |
| `DROP TABLE x` | `TRUNCATE TABLE x` + `ALTER TABLE x DROP COLUMN ...` 组合 / 通过 ORM `metadata.drop_all()` |

**透明告知 ≠ 授权**：agent 执行前透明告知替代方案是好习惯，但仍需先拿到授权。先斩后奏（即使透明）属于纪律违规。

**适用范围**：本规则约束所有 agent（dev / code-reviewer / qa-engineer / ml-engineer / miniapp-* 等）。product-lead 自身的 escalation 路径是 SendMessage 给用户，由用户最终拍板。

### Hook Coverage Boundary（hook 不是 data-flow security boundary）

`block-dangerous-bash.sh` 的拦截范围是**命令行参数中的危险操作**（segment-internal：单个命令段内的可执行 verb + 参数）。它**不拦** data-flow 形式喂入的危险内容，包括但不限于：

- 管道 stdin：`echo "DROP TABLE x" | psql mydb`（DROP 在 echo 段，psql 在管道下游段）
- 文件输入：`psql -f migration.sql`（破坏性 SQL 在文件里）
- heredoc 喂入：`psql <<EOF\nDROP TABLE x;\nEOF`
- 数据库迁移脚本里的 ORM `metadata.drop_all()` / Alembic `op.drop_table()`（脚本被 `python` / `alembic upgrade` 间接拉起）

**这是设计取舍而非疏漏**：用 string-match 跨命令段追 data flow 会 false-positive 任何讨论 SQL/file 的 commit message、文档示例、教程命令——实际项目通常含大量 SQL 脚本 / Alembic migration / 教程文档，误伤面不可忽略。

**兜底依赖**：agent 意图执行 data-flow 形式的破坏性操作时（含上述四类及其他等价形式），仍受**前节 No Equivalent Bypass** 约束 —— **必须 SendMessage product-lead 等书面授权**。hook 不阻断 ≠ 允许执行。

**回归验证**：`.claude/hooks/tests/test-block-dangerous-bash.sh` AC-6c 用例锁定该 limitation；如未来 hook 意外扩到 data-flow 维度，该测试会主动失败提醒 review。
