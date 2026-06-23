# Kronos 孤儿 gitlink 结构治理 — tech-lead 评估

- 评估日期: 2026-06-22
- 评估人: tech-lead
- 触发: ml-engineer-2 执行 M11 gitlink 提升时发现 `git add Kronos` 无法记录嵌套仓库 commit，flag 为结构性问题
- 关联: `docs/reviews/m01-techlead-assessment-2026-06-22.md`（M11 是 ML-P1 AC-5）、`docs/reviews/audit-model-2026-06-22.md` M05（Kronos 自研 checkpoint 生产不存在）
- **状态更新（2026-06-22）**: P1 止血已由 ml-engineer-2 执行完毕，tech-lead 独立核实通过：
  - 嵌套仓库 commit `c2bc93d`（dataset.py M11）+ `git push my master` 成功，`git ls-remote my master` 确认 remote 可达（不悬空）。
  - 顶层 `git update-index --cacheinfo 160000,c2bc93d,Kronos` → commit `597ede8` `chore: 更新 Kronos submodule (M11 dataset.py 时间一致性校验)`，`git show --stat` 确认只改 Kronos gitlink 一行（1 file/1 ins/1 del，无夹带顶层 modified 文件）。
  - backup tag `pre-m11-gitlink-bump → e15f24d` 已打（update-index 前），回退点就位。
  - 顶层 HEAD 链：`e15f24d`（嵌套 commit done）→ `597ede8`（gitlink 提升）→ `51b73fb`（progress 收口）。
  - M11 全收口，ML-P1 (task #8) completed。
  - 结构性 follow-up 已开 GitHub issue #2（label 待补标 `type:tech-debt`/`area:infra`/`epic:bi-trend-rebuild`，团队既定 label 未建、skill 禁自创，body 注明待建立后补标）：https://github.com/rogerluo2016ROL/suying-ai-stock-platform/issues/2
  - 结构根治（P2/P3）仍按本文 §4.3 推迟，触发条件 = bi_trend 重设专项启动。

---

## 1. 问题复述

ML-P1 的 M11（dataset.py 时间一致性校验）代码已 commit 在嵌套仓库 `Kronos/Kronos-uat-bak`（c2bc93d），但顶层 `git add Kronos` 无法把 gitlink 提升到 c2bc93d。这是 Kronos 目录的**结构性损坏**，不是 M11 的实现问题。

---

## 2. tech-lead 核实的事实（实测，非推理）

### 2.1 目录真实结构

```
Kronos/                        # 普通目录，无 .git
├── data/                      # 空
├── Kronos-uat-bak/            # 嵌套 git 仓库（.git 存在，branch master）
│   └── src/kronos/finetune/dataset.py   # M11 改动在此
└── outputs/
```

### 2.2 顶层 git 对 Kronos 的追踪

- `git ls-files --stage Kronos` = `160000 1472f20... Kronos`（mode 160000 = gitlink）
- `git ls-files Kronos | wc -l` = 1（顶层只追踪 gitlink 本身，**不**追踪 Kronos 下任何文件）
- `.gitmodules` 不存在 → `git submodule status` 报 `fatal: no submodule mapping found in .gitmodules for path 'Kronos'` = **孤儿 gitlink**

### 2.3 路径错位（核心病灶）

- gitlink mode 160000 期望 `Kronos/.git` 是个 git 仓库根。
- 实际 `Kronos/.git` **不存在**，真实仓库根在 `Kronos/Kronos-uat-bak/.git`（深一层）。
- git 找 gitlink 仓库时不递归子目录 → 顶层看不见 `Kronos-uat-bak` 的新 commit。

### 2.4 实测验证（决定性）

| 操作 | 结果 |
|---|---|
| 嵌套仓库 HEAD | `c2bc93d`（M11，已 commit，在 1472f20 之上）|
| c2bc93d 是否在 my remote | **否**（`git branch -r --contains c2bc93d` 空，未 push）|
| 顶层 `git add Kronos` | exit 0，但 gitlink SHA **不变**（仍 1472f20）—— 探测失败 |
| 顶层 `git update-index --cacheinfo 160000,c2bc93d,Kronos` | exit 0，gitlink 正确变为 c2bc93d，`git diff --cached` 显示 1472f20→c2bc93d —— **可行** |

### 2.5 历史 gitlink 更新为什么能用（推断）

历史 `chore: 更新 Kronos submodule` commit（fb734f5 等）确实改了 gitlink SHA（b456b65→1472f20）。但当前 `git add Kronos` 复现不出来。唯一解释：那些历史更新发生在 `Kronos/.git` 临时存在或目录结构不同的时刻，当前的路径错位 + 孤儿状态是**后来某个操作（很可能 `Kronos-uat-bak` 目录改名/迁移）留下的冻结态**。机制已失效，不可考复现。

---

## 3. 候选路径

### P1 — 止血：update-index 强制提升 gitlink

- 动作：嵌套仓库 `git push my master`（c2bc93d 上 remote）+ 顶层 `git update-index --cacheinfo 160000,c2bc93d,Kronos` + `git commit`。
- 彻底性：M11 落地，gitlink 指向 remote 可达 commit。**不**修结构，下次改 Kronos 还要同样手法。
- 成本：低（2 行命令）。
- 风险：低。`update-index --cacheinfo` 是 git 底层命令但语义明确（直接写 index 条目），不碰工作区。前提是 c2bc93d 必须 push 到 my，否则 gitlink 悬空。

### P2 — 规范化：补 .gitmodules 转 proper submodule

- 动作：要么 (a) 把 `Kronos-uat-bak/` 内容移到 `Kronos/` 根（让 gitlink 路径与仓库根对齐），要么 (b) 把 gitlink 重定向到 `Kronos/Kronos-uat-bak`（但 git submodule 路径不支持子目录嵌套）+ 写 `.gitmodules`。
- 彻底性：根治孤儿 gitlink，团队未来用标准 `git submodule` 工作流。
- 成本：**高**。(a) 涉及移动整个 Kronos-uat-bak 内容 + 调整所有 import 路径（`from kronos.finetune.dataset` 等）+ 重新验证 prediction-service / training-service 的加载链路。(b) 技术上 git submodule 不支持仓库根在主仓子目录深处的布局，不可行。
- 风险：高。Kronos-uat-bak 是 2158 行 bi_trend + Kronos Transformer 的载体，移动会触发 audit M05（自研 checkpoint 路径）+ memory bi_trend 重设的连锁影响。

### P3 — 根治：评估 Kronos 该不该是 submodule

- 动作：评估 Kronos 本质（自研模型代码 vs 外部依赖）。鉴于 audit M05（自研 checkpoint 生产不存在，prediction-service 实际跑公开 HF base）+ memory（bi_trend 需根本重设、不接 Kronos/LLM），Kronos 在生产路径上**基本不活跃**。可考虑把 finetune/dataset.py 这类生产需要的少量代码外提为顶层普通目录，Kronos-uat-bak 整体降级为纯研究产物（不进版本库或转 git-lfs）。
- 彻底性：彻底消除 gitlink 问题。
- 成本：**极高**，且依赖 bi_trend 重设专项的产出（要先知道重设后哪些 Kronos 代码还要用）。
- 风险：高，时机不对（bi_trend 重设未启动，现在做 P3 是为未定型的未来重构）。

---

## 4. 推荐：P1 止血 + P3 列结构性 follow-up

### 4.1 理由

1. **memory 定性决定 P2/P3 现在不做**。memory `phase1-sample-out-conclusion` 已定性 bi_trend 需根本重设、不接 Kronos/LLM；audit M05 坐实 Kronos 自研 checkpoint 生产不存在。在"Kronos 在生产路径基本不活跃 + bi_trend 待重设"的状态下，投入 P2（移动目录 + 调 import）或 P3（重新规划 Kronos 定位）都是**为未定型的未来做高代价重构**，违反"简单优于巧妙"。

2. **P1 的成本/风险最低且 M11 能立即落地**。update-index 是 2 行命令，实测可行，不碰工作区。M11 是 ML-P1 的最后一个 AC，不该被结构债无限期阻塞。

3. **P1 的"下次还要踩坑"问题**承认但不解决——列为 follow-up，触发条件绑定到 bi_trend 重设专项：**重设专项启动时，一并做 P3（Kronos 定位评估）**，届时知道哪些 Kronos 代码要保留，P2/P3 才有准星。在重设前，Kronos 代码变动频率低（memory 已禁再调参），update-index 手法的重复成本可接受。

### 4.2 给 ml-engineer 的执行步骤（P1）

```
# 1. 嵌套仓库 push（c2bc93d 必须 remote 可达，否则 gitlink 悬空）
cd Kronos/Kronos-uat-bak
git push my master
git log --oneline -1 my/master   # 确认 my/master = c2bc93d

# 2. 顶层强制提升 gitlink
cd <repo root>
git update-index --cacheinfo 160000,c2bc93d13b663c277630da8885c3dced93277e96,Kronos
git diff --cached -- Kronos      # 确认显示 1472f20 → c2bc93d
git commit -m "chore: 更新 Kronos submodule (M11 dataset.py 时间一致性校验)"
```

**约束**：
- 步骤 1 必须先于步骤 2（gitlink 指向的 commit 必须 remote 可达）。
- commit message 用团队既定中文句式（对齐 fb734f5/79c9900 历史）。
- **禁止** `git add -A`（顶层有大量 ML-P0/P1 + 其他模块的 modified/untracked 文件，会混入）——只 commit Kronos gitlink 这一个变化（update-index 已精确写到 index，commit 前用 `git diff --cached` 核对只有 Kronos 一行）。

### 4.3 结构性 follow-up（列 ML-P2 / 基础设施 ticket）

- **FU-Kronos-gitlink-1**（P1 落地后立即记）：Kronos 孤儿 gitlink + 路径错位（仓库根在 Kronos-uat-bak 深一层）+ `git add Kronos` 失效。临时手法：update-index。触发根治的条件：bi_trend 重设专项启动。
- **FU-Kronos-gitlink-2**（绑 bi_trend 重设专项）：重设启动时评估 Kronos 定位（P3）——保留哪些代码外提顶层、Kronos-uat-bak 是否降级为研究产物。届时一并修 gitlink 结构（P2 或 P3）。
- **不在本次做**：补 .gitmodules（P2）——当前路径错位下补 .gitmodules 也无法让 `git submodule` 正常工作（git submodule 不支持仓库根在子目录深处），属无效修复。

---

## 5. 对上一轮 tech-lead 判断的纠正

我在 `docs/reviews/m01-techlead-assessment-2026-06-22.md` 同期的 M11 决策消息中曾说"嵌套仓库 HEAD 1472f20 正好等于顶层 gitlink 指向的 commit → gitlink 指向嵌套仓库"。这是**推理错误**——1472f20 的对齐是历史冻结态的巧合，不代表 gitlink 机制能复现。实测证明 `git add Kronos` 探测不到嵌套仓库。ml-engineer-2 的诊断正确，本评估据此纠正。

教训：gitlink/submodule 结构问题必须实测（`git add` + `git diff --cached` 看探测结果），不能凭 HEAD SHA 对齐就推断机制可用。

---

## 6. 不写 ADR 的说明

本评估不开 ADR。理由：

- P1 是止血操作（update-index 提升一个 gitlink SHA），不是架构决策。
- 真正的结构决策（P2/P3）**推迟到 bi_trend 重设专项**，届时若决定 Kronos 定位重构，才开 ADR 记录"Kronos 模块版本化策略"。
- 当前阶段只记录"现状 + 止血手法 + follow-up 触发条件"，属 review 文档范畴。

---

## 7. 结论

| 路径 | 取舍 | 时机 |
|---|---|---|
| P1（update-index 止血） | **立即执行** | M11 收尾，本轮 |
| P2（补 .gitmodules 规范化） | **不做**（路径错位下无效） | — |
| P3（Kronos 定位重构） | **列 follow-up** | 绑 bi_trend 重设专项 |

ml-engineer-2 按 §4.2 两步执行 M11 gitlink 提升。结构性 follow-up FU-Kronos-gitlink-1/2 记入 ML-P2。

---

*评估结束。只做评估与实测，未改任何源码；M11 gitlink 提升由 ml-engineer-2 按 §4.2 执行。*
