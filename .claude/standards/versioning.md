# Versioning Standard

## SemVer 应用细则

按 [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html)。本仓库是 AI 团队模板（产物 ≠ 传统代码 API），下表把 "public API change" 具象化为模板特定触发器。

### MAJOR — `vX.0.0`（标题必加 `(BREAKING)`）

**以下任一**视为 MAJOR：

- 删除或重命名：`.claude/agents/*.md` / `.claude/skills/*/` / `.claude/commands/*.md` / `.claude/hooks/*.sh` / `.claude/standards/*.md`
- 文档路径约定改名（如 `docs/prd/` → 其他）
- 任一 agent 的 frontmatter 必填字段变更（`name` / `description` / `tools`）
- 任一 agent 的 Definition of Done 变严（既有产物不再合规）
- hook 范围扩大到既有合法操作被阻断
- PRD / ADR / SIT 等模板新增必填字段（旧产物不再合规）

### MINOR — `vX.Y.0`（向后兼容增量）

- 新增 agent / skill / slash command / hook / standards 文件
- 既有 agent 增加职责但不改既有行为
- 新增 frontmatter 可选字段（限官方支持的字段，如 `effort:` / `maxTurns:` / `isolation:`）
- 新增 CLAUDE.md / standards / agent 中的可选段落
- hook 放宽（既有阻断变软告警）
- 新增 PRD / ADR 等模板可选字段
- 新增 examples / persona / 经典示例

### PATCH — `vX.Y.Z`（向后兼容修复）

- typo / wording / formatting
- 不改接口的 hook bug 修复
- README / 内部文档调整
- eval JSONL 内容增减
- CHANGELOG 自身修订

## Release 流程

| 步骤 | 谁做 | 产物 |
|---|---|---|
| 1. 合并到 main 前判定版本号 | `product-lead` | PR 描述里写 `Bump: MAJOR / MINOR / PATCH + 理由` |
| 2. 更新 `CHANGELOG.md` | `product-lead` | 顶部追加 `## [vX.Y.Z] — YYYY-MM-DD — 一句话标题`，下分 Added / Changed / Deprecated / Removed / Fixed / Security 节。**MAJOR / MINOR 节必须含一行「token 实数（input / output / cache_read / cache_create，用户跑 `/usage` 提供）或 cost 档位（Small / Medium / Large）」——release DoD 的一部分，缺则不得进 step 4 打 tag** |
| 3. Commit changelog | 任意 dev | commit msg: `docs(changelog): vX.Y.Z` |
| 3b. 安装链路自检（仅 MINOR+） | 任意 dev | MINOR / MAJOR release 前跑 `bash .claude/scripts/test-install.sh` 须全绿（known-gap warn 可接受）；PATCH 跳过 |
| 4. 创建 git tag | `product-lead` | `git tag -a vX.Y.Z -m "..."`（annotation body 必须列出本 tag 实际覆盖但未在 CHANGELOG vX.Y.Z 节描述的 "out-of-scope but tagged-along" commits，避免 tag 覆盖范围与 CHANGELOG 描述范围漂移） |
| 5. 推送 commit + tag | `product-lead` | `git push && git push --tags` |
| 6. 创建 GitHub release | `product-lead` | `gh release create vX.Y.Z --latest --notes-file <path>`（MAJOR/MINOR 必须 `--latest`；PATCH 同会话内自动跟随时也加 `--latest`，单独打 hotfix PATCH 不覆盖最新 MAJOR/MINOR 时用 `--latest=false`）|
| 7. （建议）release 复盘提醒（MAJOR / MINOR） | `product-lead` | release 完成后**提醒用户**可跑 `/agf-release-retro vX.Y.Z` 做复盘（skill `agf-running-release-retro` 产出 `docs/reviews/retro-vX.Y.Z-YYYY-MM-DD.md`）；**非强制 gate**——有 team 交付周期数据时价值高，maintainer-direct session 可跳过；PATCH 不提醒 |

## CHANGELOG 格式

遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)：

- 顶部 `# Changelog` + 一句格式说明
- 每个版本一节：`## [vX.Y.Z] — YYYY-MM-DD — 一句话标题`
- BREAKING 在标题后加 `(BREAKING)`
- 节内固定子标题（按需出现，不必全有）：`Why` / `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security` / `Migration steps` / `Verification` / `Tag-along commits`
- AGF 在 Keep a Changelog 6 节基础上扩展 4 节：`Why`（决策动机）/ `Migration steps`（fork 用户同步建议）/ `Verification`（hook test / lint 通过证明）/ `Tag-along commits`（按主题分组列本 release 包含但不在主标题描述范围的 commits，避免与 tag annotation 漂移）

## Tag 命名

- 正式版：`vX.Y.Z`（如 `v2.0.0`）
- 预发布：`vX.Y.Z-rc.N` / `vX.Y.Z-beta.N`（仅 MAJOR 或大型 MINOR 用；PATCH 不开 RC）
- 不允许 `latest` / `stable` 等 alias tag——用 GitHub release 的 "Latest" 标记替代

## Deprecation 策略

删除（MAJOR）前**至少经过 1 个 MINOR 版本**的 deprecation 期：

1. MINOR 版本：目标对象顶部加注释 `> ⚠️ Deprecated since vX.Y.0, will be removed in vX+1.0.0. Migrate to: ...`
2. MAJOR 版本：实际删除

**例外**：从未真正发布过的实验性产物（如实验分支上从未 tag 发布过的命令 / 脚本）可在 MAJOR 直接删，不需 deprecation 期。

## 谁动什么

- **`product-lead`** — Release 唯一发起者；所有版本号判定经 PL 签字
- **`tech-lead`** — 仅在 BREAKING 涉及架构基线（ADR-000 调整）时出意见
- **执行层** — PR 描述里建议版本类型；最终判定权在 PL

## 反模式（拒绝）

- ❌ MAJOR 没有 CHANGELOG `Migration steps` 节
- ❌ 删除 agent / skill 但版本号只跳 MINOR
- ❌ 跳过 tag 直接 push（GitHub release 必须有 tag 锚点）
- ❌ Force-push 已发布的 tag（破坏下游缓存）
- ❌ 同一版本号已发布后还改 release notes 实质内容（小改 typo 可，改清单不可——开 PATCH 重发）
- ❌ **做了 retro 但**其 §5 Action Items 缺 owner / 缺 due / 缺继承次数（retro 本身是建议项、非强制；但一旦做，每条 Action Item 必填这三项否则不算闭环；继承次数 ≥2 必须落地为硬手段或 dropped，禁止第三次继承）
- ❌ MAJOR / MINOR 的 CHANGELOG 节缺「token 实数（或 cost 档位）」行（release DoD）
- ❌ CHANGELOG `## [vX.Y.Z]` 节 commit 落 main 后未在同次会话内 `git tag -a vX.Y.Z` + 推送——形成 tag-orphan（back-fill tag 是有条件 acceptable 的修复手段，但首次出现 orphan 本身视为反模式，PL 当次会话内必须补打或解释延期）

## Retro 历史登记（强制时期遗留，机制已退役）

> retro 现为**建议项 / 提醒**（见 Release 流程 step 7），**非强制 gate**——缺 retro 不再是反模式，"补录豁免"机制随之退役。下表是 retro **曾作为强制 DoD 时期**（≤ v6.0.0）已登记的豁免记录，保留备查；此后 release 缺 retro 无需登记、无需豁免。

- retro 价值与 team 交付周期数据强相关：有完整 team cycle 时做（趋势 / Action Items 有据），maintainer-direct session（无 team 数据）默认跳过。
- 仍**鼓励**在有复盘价值时主动跑 `/agf-release-retro`——它不是负担，是工具。

### 已豁免登记

| 版本 | 类型 | 豁免日期 | 理由 |
|---|---|---|---|
| v5.0.0 | MAJOR | 2026-06-10 | 删 plugin 分发形态的大版本，发布时漏做 retro；maintainer-direct session 无 team 复盘数据，时隔已久补做价值低；核心决策已在 CHANGELOG v5.0.0 节 + ADR-002 / security.md 第 5 层充分沉淀。 |
| v5.3.0 | MINOR | 2026-06-10 | 与 v5.2.0 同日连续 maintainer session，cycle-time 数据与 v5.2.0 / v5.4.0 不可比；Workflow 阶段嵌入 / agent 去重 / TUI 美化等改进已在 CHANGELOG v5.3.0 节 + ADR-005 详记。 |
