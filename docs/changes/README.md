# docs/changes/ —— 变更文件夹（需求入口）

> 取代 PRD 作为新需求入口（OpenSpec 风格）。决策见 [ADR-012](../adr/012-spec-driven-change-folders.md)。
> `docs/prd/` 自 v6.9.0 起 **deprecated**（仍可用作 fallback），v7.0.0 删除。新需求一律走这里。

## 一个 change 的结构

```
docs/changes/<change-kebab-case>/
├── proposal.md          # why + what + scope（意图）
├── specs/<cap>.md       # delta：对 docs/specs/<cap>/spec.md 的 ADDED/MODIFIED/REMOVED/RENAMED
├── design.md            # 单 change 技术「怎么做」（薄，可省；高风险 change 引用新 ADR）
└── tasks.md             # 实现 checklist + AC-N ↔ scenario 映射表
```

`specs/` 是**唯一会 merge 进活规格**的部分。一个 change 可含多个能力的 delta（多个 `specs/<cap>.md`）。

## 生命周期（入口层 = OpenSpec 形态；apply 之后 = AGF 验证脊柱不变）

```
explore（可选, /agf-code-map understand）
  → propose:  PL 用 skill agf-writing-change 建 docs/changes/<change>/ 四件套
  → 【对齐门: 用户批准 proposal + delta】          ← 复用现有审批位
  → validate: bash .claude/scripts/agf-spec-validate.sh docs/changes/<change>/specs/<cap>.md
  → 派工:     PL 据 tasks.md 建 Agent Teams task（6 段 schema 不变）
  ──────────────── 以下为 AGF 验证脊柱，全不变 ────────────────
  → apply → code review(+SIT Audit) → 部署门 → E2E → UAT pass² → PL 业务签字
  → archive:  PL 跑 agf-spec-archive.py <change> <YYYY-MM-DD>
              （delta merge 进 docs/specs/，change 移 archive/<date>-<change>/）
```

## 新建一个 change

```bash
cp -r docs/changes/_TEMPLATE docs/changes/<change-kebab-case>
# 删模板注释，填 proposal / delta / design(可省) / tasks
bash .claude/scripts/agf-spec-validate.sh docs/changes/<change>/specs/*.md
```

细则见 skill `.claude/skills/agf-writing-change/`。
