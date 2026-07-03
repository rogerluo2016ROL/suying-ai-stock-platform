// AGF Review Sweep — 高风险大 PR 深审 workflow（ADR-002 pilot）
//
// 用途：在 AGF 常规 code-review 之上**加深一遍**——按维度并行扇出 code-reviewer，
//       再对每条 finding 做 3-lens 对抗性验证（独立 skeptic 默认 refute，≥2 判真才保留），
//       合成报告到 docs/reviews/。**不替代**常规 code-review。
// 触发：大 PR / 高风险变更（Auth / schema 迁移 / LLM 切换 / cross-cutting）；需 PL 批准（成本，见 cost-budget.md）。
// 调用：/agf-review-sweep <PR# 或 路径 或 一句话范围>（缺省 = 当前 working-tree diff）。
//       未被识别为 slash 命令时，可用 Workflow({scriptPath: ".claude/workflows/agf-review-sweep.js", args: "<范围>"})。
// 安全：workflow subagent 已实测被 AGF PreToolUse hook 覆盖（ADR-002 探针 agf-hook-probe）；review agent read-only，只写 docs/reviews/。

export const meta = {
  name: 'agf-review-sweep',
  description: '高风险大 PR 深审：扇出 code-reviewer × 维度 + 对抗性验证每条 finding，产出带 verdict 的报告（常规 review 之上加深一遍，不替代）',
  whenToUse: '大 PR / 高风险变更（Auth / DB schema 迁移 / LLM 切换 / cross-cutting）；需 product-lead 按 cost-budget 批准',
  phases: [
    { title: 'Review', detail: '按维度并行扇出 code-reviewer' },
    { title: 'Verify', detail: '对每条 finding 跑 3-lens 对抗验证（≥2 判真才留）' },
    { title: 'Report', detail: '合成存活 finding → docs/reviews/' },
  ],
}

// --- 审查范围（args 可为 string 或 {target} 对象）---
const TARGET =
  (typeof args === 'string' && args.trim()) ? args.trim()
  : (args && typeof args === 'object' && args.target) ? String(args.target)
  : 'the current working-tree diff (run: git diff)'

// --- 审查维度（对照 AGF standards / review-checklist）---
const DIMENSIONS = [
  { key: 'security',        prompt: 'OWASP / 鉴权遗漏 / 注入 / 密钥泄漏 / CORS（对照 skill agf:security 与 agf:review-checklist §5；可辅以内置 /security-review）' },
  { key: 'correctness',     prompt: '逻辑正确性 / 边界条件 / 错误处理 / 并发与竞态' },
  { key: 'coverage-13',     prompt: 'DB 字段与聚合查询覆盖（agf:review-checklist §1 #13 教训：list endpoint 与聚合构造器是否各自独立覆盖、是否漏传字段）' },
  { key: 'tests',           prompt: 'Unit/SIT 是否真验行为（非 mock 生产路径）、AC 是否逐条覆盖' },
  { key: 'maintainability', prompt: '命名 / 重复代码 / 跨模块隔离（import-linter）/ 新代码优先无兼容层' },
]

const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          title: { type: 'string' },
          file: { type: 'string' },
          severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
          detail: { type: 'string' },
          repro: { type: 'string' },
        },
        required: ['title', 'file', 'severity', 'detail'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { isReal: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['isReal', 'reason'],
}

// --- Phase 1 + 2：每维度 review 完，立刻对其 findings 做对抗验证（pipeline，无 barrier）---
const perDimension = await pipeline(
  DIMENSIONS,
  // stage 1：按维度 review（用 AGF 自己的 code-reviewer 角色）
  (d) => agent(
    `You are doing a focused code review of: ${TARGET}\n` +
    `ONLY through this lens: ${d.prompt}\n` +
    `Read the diff/code (read-only; do NOT modify anything). Report concrete findings, each with file, severity (Critical/Important/Minor), a short detail and a repro/fix hint. If you find nothing real, return an empty findings array — do not invent issues.`,
    { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS_SCHEMA, agentType: 'code-reviewer' }
  ),
  // stage 2：对该维度每条 finding 做 3-lens 对抗验证
  (review, d) => parallel(
    ((review && review.findings) || []).map((fn) => () =>
      parallel(
        ['correctness', 'does-it-reproduce', 'severity-justified'].map((lens) => () =>
          agent(
            `Adversarially REFUTE this code-review finding via the "${lens}" lens. ` +
            `Default to isReal=false unless the evidence clearly holds after you read the actual code. ` +
            `Finding: ${JSON.stringify(fn)}\nDimension: ${d.key}\nTarget: ${TARGET}`,
            { label: `verify:${d.key}:${(fn.file || '?').slice(-24)}`, phase: 'Verify', schema: VERDICT_SCHEMA, agentType: 'code-reviewer' }
          ).then((v) => v).catch(() => null)
        )
      ).then((votes) => {
        const real = votes.filter(Boolean).filter((v) => v.isReal).length
        return { ...fn, dimension: d.key, survivedVotes: real, survived: real >= 2 }
      })
    )
  )
)

// --- 汇总：过了 ≥2/3 对抗验证的 finding ---
const allVerified = perDimension.flat().filter(Boolean)
const confirmed = allVerified.filter((f) => f.survived)
const dropped = allVerified.length - confirmed.length
log(`finding 总数 ${allVerified.length} → 存活 ${confirmed.length}（对抗验证淘汰 ${dropped} 条疑似误报）`)

// --- Phase 3：合成报告 → docs/reviews/ ---
phase('Report')
const report = await agent(
  [
    `Write an AGF "review sweep" report for target: ${TARGET}`,
    ``,
    `These findings each survived adversarial verification (≥2 of 3 independent skeptics confirmed real):`,
    JSON.stringify(confirmed, null, 2),
    ``,
    `Write the report to docs/reviews/<feature-slug>-sweep-<YYYY-MM-DD>.md . Requirements:`,
    `- Group findings by severity (Critical / Important / Minor), each with file:line and a fix hint.`,
    `- State up front: this is a DEEP pass ON TOP of normal AGF code-review, not a replacement.`,
    `- Note that ${dropped} candidate finding(s) were dropped by adversarial verification (reduce false positives).`,
    `- End with an overall verdict using EXACTLY one of AGF's code-review verdict words: "approve" / "approve with changes" / "block".`,
    `Reply with the path you wrote and the one-line verdict.`,
  ].join('\n'),
  { label: 'synthesize-report', phase: 'Report', agentType: 'code-reviewer' }
)

return { target: TARGET, findingsConfirmed: confirmed.length, findingsDropped: dropped, report }
