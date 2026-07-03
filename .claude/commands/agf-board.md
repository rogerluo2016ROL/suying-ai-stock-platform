---
description: 生成/实时刷新 AGF 开发看板（task 卡片三列 kanban + 成员栏 + 阶段门 chips 的自包含 HTML，浏览器 open 即用）。数据全来自现成落盘态（~/.claude/tasks + ~/.claude/teams config + docs 报告 frontmatter），零新状态。
argument-hint: "[team] [--feature <slug>] [--watch]"
---

# 任务

把当前开发进度渲染成看板 HTML 给用户看。执行：

1. 解析参数 `$ARGUMENTS`：可选 team 名（缺省 = 最近活跃）、`--feature <slug>`（启用阶段门 chips）、`--watch`（实时模式）。
2. 跑 `bash .claude/scripts/agf-board.sh $ARGUMENTS`：
   - **一次性**（无 --watch）：生成后告诉用户 `open progress/board.html`。
   - **实时**（--watch）：脚本会循环重生成（默认 3s）+ 页面自刷新。用 `run_in_background: true` 跑，告诉用户「看板已开:open progress/board.html，task 状态变化 ≈3s 内上板」；用户说停就 kill 该后台任务。
3. 看板含义一句话给用户：三列 = Pending / In Progress / Completed；卡片左边条色 = 角色（task `owner` 字段直读，含 pool 实例名；缺 owner 旧卡才从 description 兜底匹配 19 角色），`· N 分钟前` = 该卡最后一次状态更新；⛓ = blocked by；成员栏 = 全队名单（◆ lead / ● 工作中→按 owner 精确关联卡号，无卡片时内联 `spawn:` 初始任务摘要【可能已改派，hover 看全文】/ ○ 空闲；`· 通信 X 前` = 该成员 inbox mtime，僵尸 ● 自我揭穿；来自 team config，solo session 自动隐藏）；顶部 chips = 阶段门（实现 → Code Review → UAT 部署 → E2E → UAT）。team 缺省选择带项目亲和（优先成员 cwd 命中本仓库的 team），跨项目 fallback 时 header 以 `⚠ 非本项目 team` 揭示。

# 注意

- `progress/board.html` 是运行时产物，已 gitignore，不要 commit。
- 阶段门 chips 只在给了 `--feature` 时按 `docs/reviews|deploy|qa/<feature>-*` frontmatter 解析；缺文件显示 `—`，属正常（该阶段还没到）。
- 数据只读，本命令零写盘风险（除 board.html 本身）。
