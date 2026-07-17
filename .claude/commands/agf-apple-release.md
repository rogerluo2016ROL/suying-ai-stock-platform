---
description: 触发 product-lead 派 apple-release-engineer 把合并后的 main 代码构建成签名分发包（TestFlight / 公证 DMG / 内部包）并冒烟自检；通过后交接 apple-qa-engineer 跑 E2E/UAT
argument-hint: <feature-slug>（必须已通过 apple code review（含 SIT Audit）且已合并到 main；PRD 已声明分发渠道）
---

# 任务

对 feature `$ARGUMENTS` 启动 **Apple 发布门**：把合并后的 main 代码构建成签名分发包，冒烟自检通过后交接 apple-qa-engineer。

这是 Apple 轨交付链路里 code review 与 E2E 之间的发布门（对应 Web 轨的 UAT 部署门），二元 gate（`✅ 构建成功（冒烟通过）` / `❌ 构建失败`），不是测试阶段。

# 执行步骤

1. **检查先决条件**：
   - `docs/reviews/$ARGUMENTS-apple-*.md` 存在（含 pool 实例 `-r<N>-`）；**所有** match 文件 frontmatter `code_verdict` ≠ `block` 且 `sit_audit_verdict` ∈ {`Pass`, `Pass with concerns`}；用 `bash .claude/scripts/agf-matrix.sh --type=review --feature=$ARGUMENTS` 一眼看全部
   - 对应代码**已合并到 main**（`git log main --oneline` 可见合并提交）；记录构建 commit SHA
   - 目标为 **Apple 原生链路**（`apple/` 工程）；若是 Web feature → **拒绝**：走 `/agf-deploy-uat`；小程序 → 归 miniapp 轨
   - PRD 已声明分发渠道（TestFlight / App Store / macOS 直发 DMG / 企业内部），映射 lane 见 `deployment.md` §7.2
   - 任一不满足 → **拒绝启动**，告诉用户缺什么
2. **派单**（派 `apple-release-engineer`；**Pool 上限 = 1，禁 fan-out**——唯一签名身份 + App Store Connect，并发构建必撞 build number / match 仓）：
   - **用户授权归因（A-F4 / ADR-019，hook `gate-deploy-release-auth` 强制）**：本 slash 命令由用户显式触发 = 用户授权。派单 task 描述**必须含**一行 `用户授权: /agf-apple-release $ARGUMENTS 已触发（用户显式调用）`，否则 TaskCreated 被 hook exit 2 阻断。
   - `apple-release-engineer` — initial task: 按 skill `agf-releasing-apple` 从合并后 main 构建：match 同步签名材料 → 按渠道跑对应 lane（`beta` / `release_appstore` / `release_dmg` / `release_internal`）→ 公证 / TestFlight 处理**等到完成状态** → 冒烟自检（真实输出：`spctl -a -vv` / "Ready to Test" 状态 / 实际装包启动），落发布报告到 `docs/deploy/$ARGUMENTS-apple-[YYYY-MM-DD].md`，SendMessage product-lead 附分发包定位
3. **发布门约束**：
   - 构建源必须是**合并后的 main**，不是任何未合并分支
   - 签名材料（`.p8` / `.p12` / match 密码）走环境变量 / Keychain，**不入库**（scan-secrets / pre-commit 兜底）
   - 冒烟必须真实输出，禁 "构建 exit 0 就算成功"
   - **apple-release-engineer 不修业务源码**：冒烟暴露代码问题 → 退回 product-lead → apple-dev；签名/公证/打包配置问题 → 自己重跑（`apple/fastlane/` 是其可写域）
4. **完成后**：
   - ✅ 构建成功（冒烟通过）→ product-lead 据发布报告里的分发包定位触发 apple-qa-engineer 跑 E2E（XCUITest 对分发包），随后 `/agf-uat $ARGUMENTS`
   - ❌ 构建失败 → product-lead 决策：配置问题让 apple-release-engineer 重跑；代码问题回 apple-dev 修复，重走后续阶段门

# 任务规模过小怎么办

- 发布门规模固定（出一个签名分发包 + 冒烟），不存在"过小"。
- 若签名材料缺失（无 Apple Developer 会籍 / API key 未配 / match 仓不可达）→ 不硬启动，告诉用户先补齐前置（ADR-009「后续工作」列了清单），再重跑本命令。
- 若代码尚未合并到 main → 不启动，告诉用户："Apple 发布门要求代码先合并到 main；当前请先完成 code review（含 SIT Audit）并合并。"
