# Communication Style

> 团队所有 agent 面向人的回复保持精简。本规范由项目使用反馈固化（用户反映对话区反馈过多）。

## 适用范围

- 所有 agent（product-lead / executor / reviewer / qa / tech-lead / designer …）回对话区的文本。
- 跨 agent `SendMessage` 的 `summary` 字段，及 `message` 字段的非数据部分。

**不适用于**：写入 `docs/` 的产出物（PRD / ADR / design spec / E2E 报告 / UAT 报告 / code review 报告 / retro）及 `progress/<role>.md` 的 5 段格式条目，这些保持完整。

## 规则

1. **默认 1 句话收尾**：陈述结果 + 下一步（如有）。最多 3 句。
2. **不复述 diff / 工具输出**：用户已看到，勿再贴改动摘要。
3. **不预告动作**：连续工具调用前不写"我现在去做 X"；一句"开做"足够。
4. **不主动列 Next Steps / 风险清单**：除非用户问"还差什么"或当前阶段强制要求（如 E2E / UAT 报告 verdict 段 或 code-reviewer 的 SIT Audit verdict）。
5. **SendMessage**：`summary` ≤ 10 字（pool 模式 ≤ 15 字可含实例后缀如 `完成: T-101 (be-1)`）；`message` 只放对方下一步必需的决策、未通过 AC、阻塞点；不复述已写入 progress/docs 的内容，只给指针。**Pool 模式按实例名寻址**（规则见 [`workflow.md`](workflow.md) §Multi-instance Worker Pool / [ADR-001](../../docs/adr/001-multi-instance-worker-pool.md)）。
6. **列表 / 标题**：≥3 个真正并列的项才用 bullet；≤2 个用逗号串联。聊天回复禁用 H1/H2 标题。
7. **结尾不加客套**：不写"如需调整请告诉我"等。

## 例外

- 用户显式要求"详细解释 / 展开 / 给完整方案" → 扩展回复。
- 验收 / verdict / 阻塞升级 → 可超过 3 句，但仍不写无信息量的客套。
- 第一次提出关键架构决策或风险 → 一段陈述 + 一个明确问题，等用户裁决。

## 反例

> ❌ "我已经完成了 X 文件的修改，添加了 Y 函数。这个函数会处理 Z 场景。下一步我建议你 review 一下，如果没问题我们可以继续。如有调整请告诉我。"
>
> ✅ "X.py 加了 Y(),处理 Z 场景。要继续 SIT 吗？"
