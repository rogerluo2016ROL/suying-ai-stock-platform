---
description: 安装 AGF 后由 Claude Code 接管项目初始化（替代手敲 setup/init-team.sh + 手工合并 CLAUDE.md / 重写 ADR-000 / 建 gh label / preset 裁剪）。在刚用 setup/agf-install.sh 装好 AGF 的目标项目里运行。
argument-hint: 无需参数（自动探测安装产物）
---

# 任务

你是刚被装入本项目的 AGF 模板的**初始化编排者**。用户用 `/agf-init` 把 Day-1 初始化交给你做——**不要让用户手敲 shell 步骤**，你来跑命令、读输出、做判断、在关键决策点才问用户。逐步执行下列流程，每步先说要做什么，破坏性/改用户文件的动作先展示再落。

# 前置自检（不通过就停）

1. 确认这是「刚装好 AGF 的目标项目」：检测以下任一存在 —— `AGF_INSTALL_NEXT_STEPS.md`、`*.agf-template`（CLAUDE.md / docs/adr/000 / settings.json 等的 `.agf-template` 后缀）、`.claude.backup-*`。
   - 全都没有 → 这可能是 AGF 模板仓自身或已初始化过的项目；告诉用户"未发现安装产物，`/agf-init` 只在 setup/agf-install.sh 装后首次运行"，停止。
2. `git rev-parse --git-dir` 确认在 git 仓内（AGF 依赖 git）。

# 执行流程（按依赖顺序，逐步）

## 1. 环境校验（替代手跑 setup/init-team.sh）

跑 `bash setup/init-team.sh`，读输出判断：
- 全绿 → 继续。
- 有失败 → 逐项诊断修复：`.git/hooks/pre-commit` 缺失/非 symlink → `ln -sf ../../.claude/hooks/scan-commit.sh .git/hooks/pre-commit`；hook 不可执行 → `chmod +x`；JSON 语法错 → 定位修。修完重跑直到绿，或如实告诉用户哪项无法自动修。

## 2. 合并 CLAUDE.md（改用户文件——先展示再落）

若存在 `CLAUDE.md.agf-template`：读它与现 `CLAUDE.md`，把**团队基础设施段**（`Project-Specific Rules` / `Tool Boundaries` / `Team Runtime Contract` / `Verified Facts`）合并进项目 CLAUDE.md，**保留**项目原有的 `Project Overview` / `Tech Stack` / 自定义段。
- 合并前用一句话列出"将追加哪几段"，有内容冲突的段落停下问用户取舍。
- 落盘后**暂不删** `.agf-template` / `.backup-*`（留到第 7 步统一清理，便于用户回看）。
- 若项目原本无 CLAUDE.md（现 CLAUDE.md 即模板版）→ 跳过合并，仅在第 3 步把 Tech Stack 摘要改成项目实际栈。

## 3. 技术栈基线 ADR-000（核心 AI 价值 · 幻觉重灾区）

> ⚠️ **本步最易瞎编技术栈**。三道硬约束**不可省、不可走捷径**——宁可慢，不可猜：
> 1. **brownfield 必须先 `/agf-understand` 扫描出理解地图后才动 ADR-000**——禁止凭目录名 / 文件后缀 / 印象直接断言技术栈；没有理解地图就没有 ADR-000。
> 2. **verify before assert**（[`coding.md`](../standards/coding.md) 同名纪律）：写进 ADR-000 / CLAUDE.md 的**每一条**技术栈结论（语言 / 框架 / 版本 / DB / 外部服务）必须先 `grep` 或读实际文件（`package.json` / `pyproject.toml` / `requirements.txt` / `go.mod` / lockfile / 实际 import）**逐条核实**，不接受"看起来像 / 通常是 / 默认应该"；核实不到的标 `待确认`，不臆断填值。
> 3. **ADR-000 一律派 `tech-lead` 写，不由主 session 顺手写**——tech-lead 带版本查证 + ADR 撰写的专门约束，降低"边 init 边随手编"的风险。

`docs/adr/000-system-architecture.md.agf-template` 是模板默认栈（React + FastAPI + Postgres），**大概率不是本项目**。分两种情况：
- **已有代码（brownfield）**：① 先跑 `/agf-understand 整个仓库` 出理解地图（`docs/reviews/<slug>-understand-<date>.md`）；② 派 `tech-lead` 据**理解地图 + 逐条 grep 核实**重写 `docs/adr/000-system-architecture.md` + 同步 CLAUDE.md `## Tech Stack` 摘要。派单示例：`Agent({subagent_type: "tech-lead", description: "落地 ADR-000", prompt: "据理解地图 docs/reviews/<slug>-understand-<date>.md 重写 docs/adr/000-system-architecture.md 为本项目真实技术栈；每条结论先 grep 实际 manifest/lockfile/import 核实（verify before assert），核实不到的标『待确认』不臆断；同步 CLAUDE.md Tech Stack 摘要"})`。
- **空项目（greenfield，无可扫描代码）**：跳过 /agf-understand（无代码可扫），用 AskUserQuestion 让用户确认技术选型（默认模板栈 React+Vite / FastAPI+Postgres，或用户指定），据**用户明确答案**落 ADR-000——greenfield 的栈来自用户决策，不是 LLM 猜。
- ADR-000 写好后才删其 `.agf-template`（第 7 步）；写完向用户一句话说明"栈据什么定的（扫了哪几个 manifest / 你的选型）"，便于你复核有没有编。

## 4. settings.json / .mcp.json 合并（安全防御不能缺）

若存在 `.claude/settings.json.agf-template`（说明项目原有 settings 被保留）：把模板的 **`permissions.deny`**（敏感路径保护）、**`hooks` 注册块**（四层防御触发点）、**`env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`**（启用 Agent Teams）合并进项目 `.claude/settings.json`——这三样缺了防御/团队功能不生效。合并后校验 JSON 可解析。`.mcp.json.agf-template` 同理（按需合并 chrome-devtools server）。

## 5. gh label 初始化（GitHub 仓适用）

检测 `gh auth status` 可用且 remote 是 GitHub：建 AGF 锁定 label 核心子集（type:feat/bug/chore/adr、area:frontend/backend/ai/infra、priority:P0-P2、severity:P0-P1、phase:design/dev/review/sit/e2e/uat、status:blocked/needs-info/wontfix），命令模式见 skill `agf-writing-github-issue` 的「本仓锁定 label 集合」。已存在的 label `gh label create` 会报错跳过即可。非 GitHub 仓或无 gh → 跳过并提示。

## 6. preset 裁剪确认

用 AskUserQuestion 问项目类型：纯 Web / 纯小程序 / 全栈（含小程序）。若纯 Web 且小程序三角色仍在 → 建议跑 `bash setup/customize.sh --preset minimal --yes`（去 `miniapp-*`）；纯小程序 → `--preset miniapp-only`。安装时已裁剪过则跳过。

## 7. 收尾清理（先列清单再删）

列出残留的 `*.agf-template` / `*.backup-*` / `AGF_INSTALL_NEXT_STEPS.md`，确认前几步已落地无误后，问用户是否清理 → 删除。报告初始化完成 + 下一步建议：`/agf-team-start <feature>`（起团队交付）或 `/agf-understand <主题>`（继续摸代码）。

# 原则

- **破坏性动作先展示**：改 CLAUDE.md / settings.json 先说改哪几段；删文件先列清单 + 确认。
- **关键决策才问**：技术栈、preset、CLAUDE.md 段冲突用 AskUserQuestion；其余（跑校验、装 hook、建 label）直接做。
- **不起 Team**：初始化是单 session 编排，重写 ADR-000 按需派 `tech-lead` subagent 或跑 `/agf-understand`，不 `/agf-team-start`。
- **回滚兜底仍是 shell**：若初始化中途出错且无法继续，指向 `AGF_INSTALL_NEXT_STEPS.md` 末尾「回滚」节（含本次 backup stamp 的完整命令）——它在你清理前一直可用。

# 任务规模过小怎么办

- 安装产物齐全即正常初始化，不存在"过小"。
- 已无任何 `.agf-template`/`.backup-*`/NEXT_STEPS → 项目已初始化过，告诉用户无需再跑，直接 `/agf-team-start`。
