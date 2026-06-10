---
description: 触发 product-lead 在 MAJOR / MINOR release 推完后做复盘；PATCH 自动 abort。沿用 skill agf-running-release-retro。
argument-hint: <vX.Y.Z>（必须已经 git tag + gh release create 成功）
---

# 任务

对 release `$ARGUMENTS` 启动 release 复盘流程（仅 MAJOR / MINOR）。

# 执行步骤

1. **解析版本号**：把 `$ARGUMENTS` 拆成 `vX.Y.Z`：
   - `Y=0 ∧ Z=0` → MAJOR，继续
   - `Y>0 ∧ Z=0` → MINOR，继续
   - `Z>0` → PATCH，**显式 abort**：告诉用户 "PATCH release（$ARGUMENTS）按 versioning.md 不需要复盘，退出。"
   - 解析失败 → 告诉用户用法 `/agf-release-retro v1.4.0`

2. **检查先决条件**（任一失败立刻 abort 并提示）：
   - `git tag -l $ARGUMENTS` 必须返回该 tag
   - CHANGELOG.md 必须含 `## [$ARGUMENTS]` 节
   - `gh release view $ARGUMENTS` 必须成功

3. **复制模板** 到 `docs/reviews/retro-$ARGUMENTS-$(date +%Y-%m-%d).md`，并 pre-fill header（版本号、release 日期、CHANGELOG 锚点）

4. **调用 skill** `agf-running-release-retro` 接力执行剩余 7 步

5. **不要自己跑复盘** — 你（主 Claude）只负责前置检查 + 文件 scaffold + 调用 skill；复盘的整合 / 派 self-report / 验收由 skill 主持（实际执行者是 product-lead）

# 任务规模过小怎么办

如果 $ARGUMENTS 不是合法 SemVer（缺 v 前缀 / 缺段）→ 告诉用户用法范例并退出。
如果 $ARGUMENTS 是 PATCH → 不该到这里就要 abort（见步骤 1）。
