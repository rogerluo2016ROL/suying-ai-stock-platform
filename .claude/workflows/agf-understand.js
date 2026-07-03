// AGF Understand — 代码库/领域理解地图 workflow（ADR-005 阶段嵌入：需求澄清 / 架构基线前）
//
// 用途：在 PL 写 PRD、tech-lead 写 ADR **之前**，对仓库（或指定子域）做一次只读并行扫读，
//       产出一份结构化「理解地图」（子系统边界 / 关键文件 / 对外接口 / 风险 / 未决问题），
//       作为 PRD「现状」节与 ADR「上下文」节的喂料。**不替代** tech-lead 的架构判断。
// 触发：首个 feature 启动前（backend/ frontend/ 尚不存在时输出的是模板本体地图）、
//       接手陌生模块、PRD 涉及 ≥2 个既有子系统时。成本走 cost-budget.md Workflow 门
//       （本 workflow ≤8 agent，正常落 Small 档），PL 批。
// 调用：/agf-understand <主题或范围>（如 "backend 鉴权链路" / "整个仓库"；缺省 = 整个仓库）。
//       未被识别为 slash 命令时：Workflow({scriptPath: ".claude/workflows/agf-understand.js", args: "<范围>"})。
// 产物：docs/reviews/<slug>-understand-<YYYY-MM-DD>.md（与 source-audit 同归档区）。
// 安全：全程 read-only（仅最终合成 agent 写产物文件）；PreToolUse 防御层覆盖
//       workflow subagent（ADR-002 探针 agf-hook-probe）。

export const meta = {
  name: 'agf-understand',
  description: '只读并行扫读仓库/子域，产出结构化理解地图（子系统/接口/风险/未决问题），给 PRD 与 ADR 喂料；不替代 tech-lead 判断',
  whenToUse: '写 PRD / ADR 前、接手陌生模块、需求涉及 ≥2 个既有子系统时；成本 Small 档，PL 批',
  phases: [
    { title: 'Scout', detail: '切分扫读区域（≤6 块）' },
    { title: 'Read', detail: '每区域一个只读 reader，结构化输出' },
    { title: 'Synthesize', detail: '合成理解地图 → docs/reviews/' },
  ],
}

// --- 范围（args 可为 string 或 {topic} 对象）---
const TOPIC =
  (typeof args === 'string' && args.trim()) ? args.trim()
  : (args && typeof args === 'object' && args.topic) ? String(args.topic)
  : '整个仓库'

const AREAS_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    areas: {
      type: 'array', maxItems: 6,
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          key: { type: 'string' },        // 短 slug，如 "auth" / "hooks"
          paths: { type: 'array', items: { type: 'string' } },
          question: { type: 'string' },   // 这个区域要回答的核心问题
        },
        required: ['key', 'paths', 'question'],
      },
    },
    slug: { type: 'string' },             // 产物文件名用的主题 slug（kebab-case）
  },
  required: ['areas', 'slug'],
}

const AREA_REPORT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    key: { type: 'string' },
    summary: { type: 'string' },                                   // ≤10 行
    key_files: { type: 'array', items: { type: 'string' } },       // file:line 可点引用
    interfaces: { type: 'array', items: { type: 'string' } },      // 对外契约/入口
    risks: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },  // 留给 PRD/ADR 决策的问题
  },
  required: ['key', 'summary', 'key_files', 'interfaces', 'risks', 'open_questions'],
}

// --- Phase 1：侦察切分（只读）---
phase('Scout')
const plan = await agent(
  `范围主题：${TOPIC}\n` +
  '你在 AGF 仓库根目录。用 ls/Glob 摸清目录结构后，把本主题切成 ≤6 个互不重叠的扫读区域，' +
  '每个区域给 key（短 slug）、paths（目录/文件前缀）、question（该区域要回答的核心问题）。' +
  '同时给产物文件名用的主题 slug（kebab-case，≤4 词）。只侦察，不深读。',
  { label: 'scout', phase: 'Scout', schema: AREAS_SCHEMA, model: 'sonnet' }
)

// --- Phase 2：并行扫读（pipeline，无 barrier）---
const reports = await parallel(
  plan.areas.map((a) => () =>
    agent(
      `范围主题：${TOPIC}\n你负责区域 "${a.key}"（paths: ${a.paths.join(', ')}）。\n` +
      `核心问题：${a.question}\n` +
      '只读扫读（Read/Grep/Glob，禁止写文件），回答核心问题并按 schema 输出。' +
      'key_files 用 file:line 形式；open_questions 留给 PRD/ADR 决策的问题，不自己拍板。',
      { label: `read:${a.key}`, phase: 'Read', schema: AREA_REPORT_SCHEMA, model: 'sonnet', agentType: 'Explore' }
    ).catch(() => null)
  )
)
const ok = reports.filter(Boolean)
log(`扫读完成 ${ok.length}/${plan.areas.length} 区域`)

// --- Phase 3：合成理解地图 ---
phase('Synthesize')
const out = await agent(
  `主题：${TOPIC}（slug: ${plan.slug}）\n` +
  '把以下各区域结构化报告合成一份「理解地图」，写入 docs/reviews/<slug>-understand-<YYYY-MM-DD>.md' +
  '（日期用 Bash `date +%F` 取）。文档结构：① 一页总览（子系统关系，可用 mermaid）；' +
  '② 各区域小节（summary / key_files / interfaces / risks）；③ 汇总「未决问题」清单（给 PRD/ADR 的输入，逐条标注来源区域）；' +
  '④ 末尾标注生成方式（agf-understand workflow + 区域数）。写完返回：文件路径 + ≤10 行要点。\n\n' +
  '各区域报告：\n' + JSON.stringify(ok, null, 2),
  { label: 'synthesize', phase: 'Synthesize' }
)

return { file_hint: out, areas: ok.length, slug: plan.slug }
