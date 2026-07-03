# Spec: example-capability

<!--
活规格模板。新建能力：cp 本文件到 docs/specs/<capability>/spec.md（capability 用 kebab-case），
删除本注释与示例，按该能力**当前**行为填写。格式纪律见 docs/specs/README.md。
本模板本身是合法规格（1 Requirement + 1 Scenario），可直接 agf-spec-validate.sh 自校 PASS。
-->

## Purpose

一句话说明这个能力是什么、解决什么用户/系统需求。

## Requirements

### Requirement: 示例行为名（用名词短语）

The system MUST <规范性行为契约——用 MUST / SHALL 描述系统必须保证的行为，不写实现细节>.

#### Scenario: 示例场景名

- WHEN <触发条件：用户做了什么 / 系统进入什么状态>
- THEN <可观察结果：返回什么 / 显示什么 / 跳转到哪>
- AND <附加结果（可选，可多条）>
