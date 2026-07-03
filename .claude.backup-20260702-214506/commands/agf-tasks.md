---
description: 查阅 Claude Code Agent Teams 原生 task list（人类可读视图，把 ~/.claude/tasks/ 里的 JSON 美化成表格）
argument-hint: [team-name] [task-id | -s <status>]
---

# 任务

执行 `bash .claude/scripts/agf-tasks.sh $ARGUMENTS` 并把输出原样呈现给用户。调用模式（无参概览 / `<team>` / `<team> -s <status>` / `<team> <id>`）以脚本 `--help` 为准，本文件不复述。

## 行为

1. 直接 Bash 跑 `bash .claude/scripts/agf-tasks.sh $ARGUMENTS`
2. 把 stdout 完整输出给用户（含 emoji + 颜色码——Claude Code UI 一般会渲染颜色；不渲染时以纯文本看也清晰）
3. 用户问"这个 team 都谁在干什么"/"现在卡在哪"时，**优先用本命令**，不要让 lead 调 TaskList（省 token；本命令直接读文件系统）

## 约束

- **只读**：本命令仅读 `~/.claude/tasks/` 与 `~/.claude/teams/`，绝不写
- **不依赖活跃 team**：即使当前没有运行中的 agent team 也能用——读历史团队的 task 状态做复盘
- **依赖 jq**：脚本会自检；macOS 一般自带 `/usr/bin/jq`

## 失败回退

- 脚本报"team 不存在" → 把脚本输出的"可用 teams"原样转给用户
- 脚本报"需要 jq" → 提示用户跑 `brew install jq`
- `~/.claude/teams/` 完全为空 → 脚本会输出"还没建过 agent team"，照样转给用户
