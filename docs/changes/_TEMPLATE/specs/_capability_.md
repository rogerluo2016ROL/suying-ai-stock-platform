# Delta: example-capability

<!--
delta 模板。文件名改成实际 capability（kebab-case，如 user-auth.md），与 docs/specs/<cap>/spec.md 对应。
**只保留你这次用到的段，删掉其余**（空段会被 validate flag）。
应用顺序（archive 时）：RENAMED → REMOVED → MODIFIED → ADDED。
本模板四段都填了合法示例，可直接 agf-spec-validate.sh 自校 PASS。
-->

## ADDED Requirements

### Requirement: 新增行为名

The system MUST <新增的规范性行为契约>.

#### Scenario: 新增场景名

- WHEN <触发条件>
- THEN <可观察结果>

## MODIFIED Requirements

<!-- 整块复制活规格里的 requirement（从 ### 到所有 scenario）再改；header 文本须与活规格精确匹配 -->

### Requirement: 既有行为名

The system MUST <改后的完整行为契约>.

#### Scenario: 既有场景名

- WHEN <触发条件>
- THEN <改后的可观察结果>

## REMOVED Requirements

### Requirement: 被删行为名

**Reason**: <为什么删>
**Migration**: <现有用户/调用方怎么迁移>

## RENAMED Requirements

- FROM: `### Requirement: 旧行为名`
- TO: `### Requirement: 新行为名`
