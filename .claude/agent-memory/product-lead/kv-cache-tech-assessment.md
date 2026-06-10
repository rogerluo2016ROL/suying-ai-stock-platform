---
name: kv-cache-tech-assessment
description: tech-lead 对 P0-2 KV-cache 的技术评估（2026-06-01），含风险矩阵和实现建议
metadata:
  type: project
---

tech-lead P0-2 KV-cache 技术评估摘要（2026-06-01，SendMessage）。

**Why:** KV-cache 是本项目最大性能杠杆（理论 20-40x 推理加速），但实现复杂度高，需谨慎推进。

**How to apply:**
- T-006 启动时，将本评估的 5 处修改点 + 风险矩阵 + "先简单版后完整版"策略随 SendMessage 传递给 backend-dev
- 关键风险：滑动窗口 roll 使 KV-cache 失效是 HIGH 风险（最大实现复杂度来源）
- 建议策略：先做无滑动窗口的简单版（max_context >= pred_len），验证正确性后再加 cache trimming
- 5 处修改点: MultiHeadAttentionWithRoPE.forward → TransformerBlock.forward → Kronos.decode_s1/decode_s2 → auto_regressive_inference
- 与 BSQuantizer 无冲突；sample_count 广播使 KV-cache per-sequence 内存 × sample_count
