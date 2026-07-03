# Apple Native Standards（macOS / iOS 原生专项规范）

> 适用对象：`uiux-designer`（在 Apple Mode 下）/ `apple-dev` / `apple-code-reviewer` / `apple-qa-engineer` / `apple-release-engineer`。
> 与 `coding.md` / `security.md` / `testing.md` 并列；通用规则仍在原文件，不重复。
> 技术选型**决策与理由**唯一来源是 [ADR-007](../../docs/adr/007-apple-native-stack.md)（栈）/ [ADR-008](../../docs/adr/008-apple-backend-contract-sync.md)（契约）/ [ADR-009](../../docs/adr/009-apple-release-pipeline.md)（发布）；本文件只放执行细则。

## 1. 目录结构约定（按 ADR-007）

```
apple/
  App.xcodeproj          # 单一多平台工程（macOS + iOS 两个 destination）
  App/                   # app target：入口、平台 view、asset catalog、entitlements
  AppCore/               # 本地 SPM package：业务逻辑 / 数据层 / 生成的 API client
    Sources/AppCore/
    Tests/AppCoreTests/  # swift test 可在 CLI 直跑，不依赖模拟器
    openapi.json         # 后端导出的契约（进库，generator 输入，见 ADR-008）
  AppUITests/            # XCUITest E2E（apple-dev 写脚本，apple-qa-engineer 执行）
  fastlane/              # Fastfile / Matchfile / Appfile（ADR-009，首个交付 feature 创建）
```

## 2. 平台 target 声明（apple 轨核心约定）

**平台是 task 的属性，不是角色的属性。** product-lead 派 apple 轨任务时必须在 task description 声明 target：

- `target: macos` / `target: ios` / `target: universal`（两端都要）
- PRD 的 AC 凡涉及平台差异行为，按平台分别写条目（如 `AC-3(macos)` / `AC-3(ios)`）
- 未声明 target 的 apple 任务 → apple-dev 退回 product-lead 补，不自行猜测

## 3. Swift 6 并发纪律（执行细则，决策见 ADR-007）

- strict concurrency 全开（`SWIFT_STRICT_CONCURRENCY = complete`），新代码零 warning
- UI 入口类型 `@MainActor`；跨隔离域类型显式 `Sendable`
- 禁裸 GCD（`DispatchQueue`）写新代码；既有桥接场景须注释理由
- 共享可变状态一律 actor 化，禁锁 + 类的手工同步

## 4. UI 框架纪律

- SwiftUI-first；AppKit / UIKit 仅经 `NSViewRepresentable` / `UIViewRepresentable` 局部下沉
- **每个下沉点必须在 PR 描述声明理由**（SwiftUI 缺什么能力），apple-code-reviewer 核对
- 状态管理用 Observation（`@Observable`），禁混用旧 `ObservableObject` 范式写新代码
- API 可用性：跨版本 API 一律 `@available` / `if #available` gating，禁 runtime 崩溃式调用

## 5. 平台差异：macOS 章节

- **窗口形态**：支持多窗口 / 可调尺寸；最小窗口尺寸必须显式设定
- **菜单栏**：标准菜单（App/File/Edit/Window/Help）必须完整；核心操作给快捷键（⌘ 系）
- **交互**：hover 态、右键 contextMenu、键盘导航（Tab/方向键）必须覆盖
- **沙盒与 entitlements**：App Store 渠道强制 App Sandbox；Developer ID 直发渠道也默认开启，例外须 ADR
- **分发特有**：Developer ID 签名 + 公证（notarization）是直发硬前提（ADR-009）

## 6. 平台差异：iOS 章节

- **安全区**：刘海 / 灵动岛 / Home indicator 一律用 safe area API，禁硬编码 inset
- **尺寸适配**：支持 Dynamic Type（正文字号跟随系统）；iPhone 竖屏为基线，iPad/横屏按 PRD 声明
- **生命周期**：进后台即保存状态；冷启动恢复到上次上下文
- **权限**：相机 / 麦克风 / 相册等权限请求必须延迟到用户触发动作时，`Info.plist` 用途文案具体到场景（审核红线）
- **分发特有**：TestFlight 是 UAT 真机通道（ADR-009）

## 7. App Store 审核红线（两平台共用）

- **必备**：隐私清单（PrivacyInfo.xcprivacy，含第三方 SDK 的 required reason API 声明）、隐私政策 URL、权限用途文案
- **禁止**：私有 API、热更新执行外部代码、未声明的数据收集、诱导好评
- **LLM 功能特有**：AI 生成内容须有举报 / 过滤机制（App Review 4.0 系）；用户输入发往后端须在隐私政策声明
- macOS 直发渠道不过 App Review，但公证（恶意软件扫描）仍是硬门槛

## 8. 性能预算

- 冷启动 ≤ 2s（中端设备）；主线程无 >100ms 卡顿（Instruments hang 检测）
- 内存：常驻 ≤ 200MB（工具类基线，媒体类 PRD 另定）；Instruments Leaks 零泄漏过门
- 包体积：iOS 下载体积 ≤ 50MB 基线（超出须 PRD 声明理由）

## 9. 测试矩阵

| 阶段 | 工具 | 通过门槛 | 责任角色 |
|---|---|---|---|
| **Unit** | Swift Testing（`swift test`，AppCore 在 CLI 直跑） | 全过 | `apple-dev` |
| **SIT** | `xcodebuild test` + 模拟器（按 target 选 destination）走 AC 集成路径 | 全部 AC 通过率 100% | **apple-dev 自跑**，证据进 `progress/apple-dev.md` 的 `**SIT 证据**` 段，由 `apple-code-reviewer` 在 code review 时 audit（流程按 skill `agf-running-apple-sit`） |
| **E2E** | XCUITest 对**签名分发包**（TestFlight build / 公证 DMG）跑控件遍历 | 声明的 target 全平台通过 | `apple-qa-engineer` |
| **UAT** | TestFlight（iOS）/ 公证 DMG（macOS）+ 用例文档 | 业务 AC 逐条签字（P0 pass^2） | `apple-qa-engineer` 执行 + `product-lead` 业务签字 |

### 自动化命令速查

```bash
# Unit（AppCore，无模拟器依赖）
cd apple/AppCore && swift test

# SIT / E2E（按 target 选 destination）
xcodebuild test -project apple/App.xcodeproj -scheme App \
  -destination 'platform=iOS Simulator,name=iPhone 16' \        # ios
  -destination 'platform=macOS' \                               # macos
  -resultBundlePath TestResults.xcresult

# 结果提取（SIT 证据用）
xcrun xcresulttool get --path TestResults.xcresult --format json
```

> **结构化替代**：`apple-dev` / `apple-qa-engineer` 白名单已放行 **XcodeBuildMCP**（`mcp__xcodebuild__*`，`.mcp.json` 声明）——build / 模拟器 boot·install·launch·截图·日志 / 真机 devicectl / 跑测试均有结构化工具，**优先于上述裸 Bash 长命令**；本节命令保留作为 MCP 不可用时的 fallback 与证据格式参照。

- E2E 脚本（`AppUITests/*.swift`）由 `apple-dev` 开发自验时一并提交，`apple-qa-engineer` 执行判定——分工同 miniapp 轨
- mock：SIT 层后端 mock 一律实现生成的 `APIProtocol`（ADR-008），禁手写 JSON fixture

## 10. SendMessage 协作模板

- `uiux-designer（Apple Mode）→ apple-dev`：交付设计稿 + HIG 标注（含 target 声明）
- `apple-dev → backend-dev`：契约变更走 openapi.json 重导出（ADR-008），不走自然语言对齐
- `apple-dev → apple-code-reviewer`：完成自验后请求审查
- `apple-code-reviewer → product-lead`：审查通过 → PL 合并 → 派 `apple-release-engineer` 构建分发包
- `apple-release-engineer → apple-qa-engineer`：交接 `docs/deploy/` 报告（分发包路径 / TestFlight build 号）
- 任何阶段失败 → 回到 `product-lead` 重派（代码层退 apple-dev；签名/构建层退 apple-release-engineer）

## 11. 与 Web / MiniApp 团队的边界

- `backend-dev`、`ai-agent-dev`、`ml-engineer` 共用，不按端区分；API 按业务域划分
- 同一份 OpenAPI 契约服务三端（Web orval / Apple swift-openapi-generator / 小程序），后端导出动作只有一个
- UI 层各自维护；Apple 轨与 Web 不共享 UI 代码

## 12. Apple Mode 行为（uiux-designer 在 Apple 场景的 overlay）

> `product-lead` 任务明确为 Apple 原生（提到 "macOS" / "iOS" / "apple" / "原生 app"）时，`uiux-designer` 应用以下附加规则。

- **产出路径**：`docs/design/[feature]-apple/spec.md` + `index.html`（与 Web 设计区分；HTML 原型标注"仅示意布局，最终以 SwiftUI 实现为准"）
- **设计规范**：遵循 Apple HIG——SF Symbols 图标、系统语义色（支持深色模式）、系统字体（SF Pro / 苹方），禁自带图标库与硬编码色值
- **平台差异前置**：spec 必须按 target 分节——macOS 标注菜单栏 / 快捷键 / hover / 窗口尺寸；iOS 标注安全区 / Dynamic Type / 手势
- **审核红线前置**：设计阶段标注第 7 节约束——权限请求触发时机、隐私声明入口位置
- **视口**：iOS 设计 393×852（iPhone 基线）；macOS 设计 1280×800 起的可缩放布局
- **交付对象**：通过 SendMessage 交付给 `apple-dev`（非 `frontend-dev`），路径替换为 `[feature]-apple/`

> 设计意图：本节集中 Designer 在 Apple 模式下的所有附加规则；preset 裁剪时可连同本文件整体移除——单一来源 + 干净裁剪。
