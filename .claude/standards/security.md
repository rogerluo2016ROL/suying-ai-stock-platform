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
| 1. Bash 拦截 | `PreToolUse` (matcher: `Bash`) | `.claude/hooks/block-dangerous-bash.sh` | exit 2 硬阻断 | 防 agent 跑出毁灭性命令（`rm -rf`、`DROP TABLE/DATABASE/SCHEMA`、`git push --force`、`git reset --hard`） |
| 2. Secret 扫描 | `UserPromptSubmit` | `.claude/hooks/scan-secrets.sh` | exit 2 硬阻断 | 防用户把 API key / Token / PEM 私钥粘进对话；模式覆盖 AWS / GitHub / OpenAI / Anthropic / Google / Slack / DeepSeek / Doubao / Qwen / MiniMax / Apple 签名材料（App Store Connect API key `.p8`、`.mobileprovision`、`.p12`，见 ADR-009 安全约束） |
| 3. 工具输出净化 | `PostToolUse` (matcher: `WebFetch\|WebSearch\|Read\|Bash\|mcp__.*`) | `.claude/hooks/sanitize-tool-output.sh` | exit 0 + stderr WARNING（软告警，不阻断） | 防外部内容夹带的 prompt injection 指令被 agent 当成系统提示执行（含所有 MCP 工具输出） |

**回归测试**（统一在 `.claude/hooks/tests/`，由 `lint-all.sh` 跑全部 `test-*.sh`）：
- `.claude/hooks/tests/test-block-dangerous-bash.sh`（覆盖 rm -rf / DROP / git push --force / git reset --hard 各形态 + edge case 的回归测试套）
- `.claude/hooks/tests/test-scan-secrets.sh`（覆盖 scan-secrets + sanitize-tool-output + BIP39 + SSH/PuTTY 场景的回归测试套）
- `.claude/hooks/tests/test-secret-pattern-parity.sh`（守 scan-secrets ↔ scan-commit 厂商覆盖面一致）

**Hook 形态**：当前所有 hook 均为 `type: "command"`（shell 脚本）。Claude Code 另支持 `type: "mcp_tool"`，hook 可直接调 MCP 工具而无需 shell 中转——未来如需让 hook 调 chrome-devtools-mcp（截图取证）或 MiniMax（内容审核）时再切换；当前用例不涉及，保持 shell 路径以便 git 评审与离线测试。

### 第 4 层：Git Pre-commit 扫描（防止 Edit/Write 绕过 prompt-time 扫描）

`.claude/hooks/scan-commit.sh` 复用 `scan-secrets.sh` 同一套正则，对 `git diff --staged` 的新增行扫描。**这是必须的补防线**——`UserPromptSubmit` 只看 prompt，agent 用 `Edit`/`Write` 直接落盘的内容不经 prompt，会绕过第 2 层。

**安装（每个 clone 跑一次）**：

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

上面四层是 AGF 自有 hook，覆盖**毁灭性命令 / 密钥 / 注入文本 / commit 落盘**；但**代码级危险模式**——`eval` / `new Function`、XSS（`dangerouslySetInnerHTML` / `innerHTML`）、Python `pickle` 反序列化、`os.system` / `child_process.exec`、GitHub Actions 命令注入——AGF 的 bash/secret hook **不覆盖**。Anthropic 官方 `security-guidance` plugin 正好补这一层：它是 `PreToolUse` hook，拦 Write/Edit/MultiEdit，**应用前**扫这些模式 + 给修复建议（编辑时 / AI 改完 / commit 时多层），与 AGF 的 hook 防御**同一套机制、零冲突**。

**安装（强烈推荐，每个 clone 一次）**：

```
/plugin install security-guidance@claude-plugins-official
```

**定位**：defense-in-depth 第 5 层（代码模式），与 code-reviewer 手工 OWASP **互补不替代**——它自动挡常见模式，reviewer 聚焦逻辑 / 架构 / 业务越权。**优雅降级**：未装时 AGF 四层 hook + 手工 OWASP 仍成立，只少一道自动网（故标"推荐"而非"硬依赖"）。

### Permission Deny 清单（settings.json）

`.claude/settings.json` 的 `permissions.deny` 已禁读以下敏感路径：`./.env*`、`./secrets/**`、`~/.ssh/**`、`~/.aws/**`、`~/.gnupg/**`、`~/.kube/config`、`~/.config/gcloud/**`、`~/.docker/config.json`、`~/.netrc`、`~/.pgpass`；并禁 `curl|sh` / `wget|sh` / `eval` 等远程执行链路。新增敏感路径时同步该清单。

> 模板复用提示：若把 `standards/` 抽出作跨项目模板，本节应留下，但 hook 文件本身、settings.json 的 hook 注册块、CLAUDE.md 的 "Tool Boundaries" 节会随项目走，需新项目重新建立。

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
