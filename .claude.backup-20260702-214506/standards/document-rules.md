# Document Output and Single Source Rules

## Document Outputs

关键决策与设计必须持久化为文件：

| 角色 | 文档类型 | 路径规范 | 触发时机 |
|---|---|---|---|
| `product-lead` | PRD | `docs/prd/[feature]-[YYYY-MM-DD].md` | 分配任务前（必须） |
| `tech-lead` | ADR（架构决策记录） | `docs/adr/[NNN]-[title].md` | 每次技术选型或架构决策 |
| `uiux-designer` | 设计规范 + 静态原型 | `docs/design/[feature]/spec.md` + `docs/design/[feature]/index.html` | 移交 frontend-dev 前（必须） |
| `code-reviewer` | 审查报告 | `docs/reviews/[feature]-[YYYY-MM-DD].md`（单实例）/ `docs/reviews/[feature]-r<N>-[YYYY-MM-DD].md`（pool 实例 N，详 [ADR-001](../../docs/adr/001-multi-instance-worker-pool.md)）| 每次完成代码审查（必须）；YAML frontmatter 必填 |
| `qa-engineer` | 测试报告（E2E / UAT） | `docs/qa/[feature]-[e2e|uat]-[YYYY-MM-DD].md`（单实例）/ `docs/qa/[feature]-[e2e|uat]-q<N>-[YYYY-MM-DD].md`（pool 实例 N）| 每次完成 E2E / UAT（必须）；YAML frontmatter 必填；集成层证据由 dev 写入 `progress/<role>{-<N>}.md` |

### 单一来源原则（Single Source of Truth）

**每项内容只在一个文档中完整描述，其他文档只能引用，不得重复。**

团队所有 agent 必须遵循此原则（见各 agent "行事原则" 第 1 条）。下表为权威来源映射：

| 内容类型 | 权威来源 | 其他文档的处理方式 |
|---|---|---|
| 技术栈选型 | `docs/adr/000-system-architecture.md`（决策 + 备选 + 理由）+ `CLAUDE.md ## Tech Stack`（版本号摘要 + ADR 链接） | 引用 ADR 编号，不重复决策理由 |
| 架构决策背景与理由 | `docs/adr/[NNN]-[title].md` | 引用 ADR 编号和路径 |
| 功能需求与验收标准 | `docs/prd/[feature]-[YYYY-MM-DD].md` | 任务分配时摘录相关 AC 条目（唯一允许的必要复制，便于 agent 执行） |
| 界面设计规范 | `docs/design/[feature]/spec.md`（同目录附 `index.html` 静态原型） | 引用设计目录路径 |
| 代码审查结论 | `docs/reviews/[feature]-[YYYY-MM-DD].md` | 引用报告路径 |
| 测试结果与判定 | E2E / UAT: `docs/qa/[feature]-[e2e|uat]-[YYYY-MM-DD].md`；集成层证据: `progress/<role>.md` 的 `**SIT 证据**` 段（feature 结束归档至 `docs/qa/<feature>-process-log.md`） | 引用报告路径 |

**违反示例**：ADR 中已记录"选择 PostgreSQL 的理由（备选 MySQL 因 X 排除）"，CLAUDE.md `## Tech Stack` 不得再写理由或备选方案，只能写"数据库: PostgreSQL 16.x（见 ADR-000）"。
