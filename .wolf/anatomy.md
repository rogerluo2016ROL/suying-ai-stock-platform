# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-06-30T02:29:33.642Z
> Files: 520 tracked | Anatomy hits: 0 | Misses: 0

## ../../../../tmp/

- `analyze_main_force_300539.py` — 分析 横河精密(300539) 主力出货迹象. (~2618 tok)
- `analyze_main_force_600268.py` — 分析 国电南自(600268) 主力出货迹象. (~3079 tok)

## ./

- `.dockerignore` — Docker ignore rules (~87 tok)
- `.DS_Store` (~1640 tok)
- `.gitignore` — Git ignore rules (~491 tok)
- `.mcp.json` (~38 tok)
- `.mcp.json.agf-template` (~75 tok)
- `AGENTS.md` — 速赢AI — 证券投资管理平台 (~2829 tok)
- `agf-team-start.sh` — agf-team-start.sh — interactive Agent Team launcher (~3341 tok)
- `calibrated_weights.json` (~501 tok)
- `CLAUDE.md` — OpenWolf (~2931 tok)
- `init-team.sh` — init-team.sh — verify and prepare AppGenesisForge AI team scaffold (~1846 tok)
- `package-lock.json` — npm lock file (~36508 tok)
- `package.json` — Node.js package manifest (~139 tok)
- `pyproject.toml` — Python project configuration (~96 tok)

## .agents/skills/agf-deploying-uat/

- `SKILL.md` — Deploying to the isolated UAT stack (~1567 tok)

## .agents/skills/agf-releasing-apple/

- `SKILL.md` — Releasing the Apple distributable (sign → notarize → package → smoke) (~1372 tok)

## .agents/skills/agf-running-apple-sit/

- `SKILL.md` — Running Apple SIT (xcodebuild + simulator) (~984 tok)

## .agents/skills/agf-running-release-retro/

- `SKILL.md` — Running Release Retrospective (~1524 tok)

## .agents/skills/agf-running-sit-tests/

- `SKILL.md` — Running System Integration Tests (SIT) (~1322 tok)

## .agents/skills/agf-wiring-apple-llm/

- `SKILL.md` — Wiring LLM into the Apple client (gateway streaming / on-device) (~911 tok)

## .agents/skills/agf-wiring-multi-llm-sdk/

- `SKILL.md` — Wiring Multi-LLM SDK (DeepSeek / Doubao / Qwen / MiniMax) (~1499 tok)

## .agents/skills/agf-writing-adr/

- `SKILL.md` — Writing an ADR (Architecture Decision Record) (~952 tok)

## .agents/skills/agf-writing-docx-reports/

- `SKILL.md` — 写 docx 报告 — 高密度实战手册 (~1121 tok)
- `template.js` — 4A 评审决议书 docx 生成器 — 阅读友好版 v2 (~9372 tok)

## .agents/skills/agf-writing-docx-reports/references/

- `design-tokens-and-helpers.md` — 设计 token + spacing + 9 个 helper + 文档外壳（docx-js 全套） (~2235 tok)

## .agents/skills/agf-writing-github-issue/

- `SKILL.md` — Writing a GitHub Issue (~1368 tok)

## .agents/skills/agf-writing-github-issue/references/

- `templates-and-examples.md` — Body 模板 + gh CLI heredoc 模板 + 完整例子 (~858 tok)

## .agents/skills/agf-writing-pptx-reports/

- `diagram-generation-guide.md` — 图层生成实战手册 — draw.io / Mermaid / matplotlib 选型 (~2475 tok)
- `SKILL.md` — 写 pptx 报告 — 高密度实战手册 (~1630 tok)
- `template-team-guide.md` — Template.pptx（iSlide 商务团队主题）使用指南 (~2637 tok)
- `template.py` — set_font, clear_template_slides, dump_template_structure, rect + 3 more (~6184 tok)

## .agents/skills/agf-writing-pptx-reports/references/

- `design-tokens-and-techniques.md` — 设计 token + 12 个关键技巧 + 品牌色获取流程 (~1893 tok)
- `rendering-and-embedding.md` — 图嵌入 / PNG→PDF 输出 + 资源链接 + 沉淀来源 (~535 tok)
- `template-based-generation.md` — 基于已有 .pptx 模板生成（推荐路径详解） (~1086 tok)

## .agents/skills/agf-writing-prd/

- `SKILL.md` — Writing a PRD (Product Requirements Document) (~1208 tok)

## .agents/skills/agf-writing-qa-report/

- `SKILL.md` — Writing a QA Report (E2E / UAT) (~1481 tok)

## .agents/skills/docx/

- `LICENSE.txt` (~367 tok)
- `SKILL.md` — DOCX creation, editing, and analysis (~5012 tok)

## .agents/skills/docx/scripts/

- `__init__.py` (~1 tok)
- `accept_changes.py` — Accept all tracked changes in a DOCX file using LibreOffice. (~1158 tok)
- `comment.py` — Add comments to DOCX documents. (~3056 tok)

## .agents/skills/docx/scripts/office/

- `pack.py` — Pack a directory into a DOCX, PPTX, or XLSX file. (~1426 tok)
- `soffice.py` — get_soffice_env, run_soffice (~1513 tok)
- `unpack.py` — Unpack Office files (DOCX, PPTX, XLSX) for editing. (~1158 tok)
- `validate.py` — main (~1048 tok)

## .agents/skills/docx/scripts/office/helpers/

- `__init__.py` (~0 tok)
- `merge_runs.py` — Merge adjacent runs with identical formatting in DOCX. (~1591 tok)
- `simplify_redlines.py` — Simplify tracked changes by merging adjacent w:ins or w:del elements. (~1644 tok)

## .agents/skills/docx/scripts/office/schemas/ISO-IEC29500-4_2016/

- `dml-chart.xsd` (~19996 tok)
- `dml-chartDrawing.xsd` (~1855 tok)
- `dml-diagram.xsd` (~13681 tok)
- `dml-lockedCanvas.xsd` (~167 tok)
- `dml-main.xsd` (~40544 tok)
- `dml-picture.xsd` (~329 tok)
- `dml-spreadsheetDrawing.xsd` (~2364 tok)
- `dml-wordprocessingDrawing.xsd` (~3946 tok)
- `pml.xsd` (~22297 tok)
- `shared-additionalCharacteristics.xsd` (~339 tok)
- `shared-bibliography.xsd` (~1955 tok)
- `shared-commonSimpleTypes.xsd` (~1702 tok)
- `shared-customXmlDataProperties.xsd` (~333 tok)
- `shared-customXmlSchemaProperties.xsd` (~235 tok)
- `shared-documentPropertiesCustom.xsd` (~696 tok)
- `shared-documentPropertiesExtended.xsd` (~936 tok)
- `shared-documentPropertiesVariantTypes.xsd` (~2002 tok)
- `shared-math.xsd` (~6217 tok)
- `shared-relationshipReference.xsd` (~365 tok)
- `sml.xsd` (~64608 tok)
- `vml-main.xsd` (~6973 tok)
- `vml-officeDrawing.xsd` (~6742 tok)
- `vml-presentationDrawing.xsd` (~143 tok)
- `vml-spreadsheetDrawing.xsd` (~1524 tok)
- `vml-wordprocessingDrawing.xsd` (~1070 tok)
- `wml.xsd` (~45698 tok)
- `xml.xsd` — Declares which (~1239 tok)

## .agents/skills/docx/scripts/office/schemas/ecma/fouth-edition/

- `opc-contentTypes.xsd` (~523 tok)
- `opc-coreProperties.xsd` (~671 tok)
- `opc-digSig.xsd` (~762 tok)
- `opc-relationships.xsd` (~358 tok)

## .agents/skills/docx/scripts/office/schemas/mce/

- `mc.xsd` (~834 tok)

## .agents/skills/docx/scripts/office/schemas/microsoft/

- `wml-2010.xsd` (~7080 tok)
- `wml-2012.xsd` (~999 tok)
- `wml-2018.xsd` (~241 tok)
- `wml-cex-2018.xsd` (~475 tok)
- `wml-cid-2016.xsd` (~268 tok)
- `wml-sdtdatahash-2020.xsd` (~160 tok)
- `wml-symex-2015.xsd` (~199 tok)

## .agents/skills/docx/scripts/office/validators/

- `__init__.py` (~96 tok)
- `base.py` — URL patterns: 1 routes (~9329 tok)
- `docx.py` — URL patterns: 6 routes (~4678 tok)
- `pptx.py` — PPTXSchemaValidator: validate, validate_uuid_ids, validate_slide_layout_ids, validate_no_duplicate_slide_layouts + 1 more (~2807 tok)
- `redlining.py` — RedliningValidator: repair, validate (~2548 tok)

## .agents/skills/docx/scripts/templates/

- `comments.xml` (~744 tok)
- `commentsExtended.xml` (~746 tok)
- `commentsExtensible.xml` (~774 tok)
- `commentsIds.xml` (~749 tok)
- `people.xml` (~33 tok)

## .agents/skills/pptx/

- `editing.md` — Editing Presentations (~1711 tok)
- `LICENSE.txt` (~367 tok)
- `pptxgenjs.md` — PptxGenJS Tutorial (~3194 tok)
- `SKILL.md` — PPTX Skill (~2282 tok)

## .agents/skills/pptx/scripts/

- `__init__.py` (~0 tok)
- `add_slide.py` — Add a new slide to an unpacked PPTX directory. (~1964 tok)
- `clean.py` — Remove unreferenced files from an unpacked PPTX directory. (~2738 tok)
- `thumbnail.py` — Create thumbnail grids from PowerPoint presentation slides. (~2510 tok)

## .agents/skills/pptx/scripts/office/

- `pack.py` — Pack a directory into a DOCX, PPTX, or XLSX file. (~1426 tok)
- `soffice.py` — get_soffice_env, run_soffice (~1513 tok)
- `unpack.py` — Unpack Office files (DOCX, PPTX, XLSX) for editing. (~1158 tok)
- `validate.py` — main (~1048 tok)

## .agents/skills/pptx/scripts/office/helpers/

- `__init__.py` (~0 tok)
- `merge_runs.py` — Merge adjacent runs with identical formatting in DOCX. (~1591 tok)
- `simplify_redlines.py` — Simplify tracked changes by merging adjacent w:ins or w:del elements. (~1644 tok)

## .agents/skills/pptx/scripts/office/schemas/ISO-IEC29500-4_2016/

- `dml-chart.xsd` (~19996 tok)
- `dml-chartDrawing.xsd` (~1855 tok)
- `dml-diagram.xsd` (~13681 tok)
- `dml-lockedCanvas.xsd` (~167 tok)
- `dml-main.xsd` (~40544 tok)
- `dml-picture.xsd` (~329 tok)
- `dml-spreadsheetDrawing.xsd` (~2364 tok)
- `dml-wordprocessingDrawing.xsd` (~3946 tok)
- `pml.xsd` (~22297 tok)
- `shared-additionalCharacteristics.xsd` (~339 tok)
- `shared-bibliography.xsd` (~1955 tok)
- `shared-commonSimpleTypes.xsd` (~1702 tok)
- `shared-customXmlDataProperties.xsd` (~333 tok)
- `shared-customXmlSchemaProperties.xsd` (~235 tok)
- `shared-documentPropertiesCustom.xsd` (~696 tok)
- `shared-documentPropertiesExtended.xsd` (~936 tok)
- `shared-documentPropertiesVariantTypes.xsd` (~2002 tok)
- `shared-math.xsd` (~6217 tok)
- `shared-relationshipReference.xsd` (~365 tok)
- `sml.xsd` (~64608 tok)
- `vml-main.xsd` (~6973 tok)
- `vml-officeDrawing.xsd` (~6742 tok)
- `vml-presentationDrawing.xsd` (~143 tok)
- `vml-spreadsheetDrawing.xsd` (~1524 tok)
- `vml-wordprocessingDrawing.xsd` (~1070 tok)
- `wml.xsd` (~45698 tok)
- `xml.xsd` — Declares which (~1239 tok)

## .agents/skills/pptx/scripts/office/schemas/ecma/fouth-edition/

- `opc-contentTypes.xsd` (~523 tok)
- `opc-coreProperties.xsd` (~671 tok)
- `opc-digSig.xsd` (~762 tok)
- `opc-relationships.xsd` (~358 tok)

## .agents/skills/pptx/scripts/office/schemas/mce/

- `mc.xsd` (~834 tok)

## .agents/skills/pptx/scripts/office/schemas/microsoft/

- `wml-2010.xsd` (~7080 tok)
- `wml-2012.xsd` (~999 tok)
- `wml-2018.xsd` (~241 tok)
- `wml-cex-2018.xsd` (~475 tok)
- `wml-cid-2016.xsd` (~268 tok)
- `wml-sdtdatahash-2020.xsd` (~160 tok)
- `wml-symex-2015.xsd` (~199 tok)

## .agents/skills/pptx/scripts/office/validators/

- `__init__.py` (~96 tok)
- `base.py` — URL patterns: 1 routes (~9329 tok)
- `docx.py` — URL patterns: 6 routes (~4678 tok)
- `pptx.py` — PPTXSchemaValidator: validate, validate_uuid_ids, validate_slide_layout_ids, validate_no_duplicate_slide_layouts + 1 more (~2807 tok)
- `redlining.py` — RedliningValidator: repair, validate (~2548 tok)

## .agents/skills/source-command-agf-init/

- `SKILL.md` — source-command-agf-init (~1150 tok)

## .agents/skills/source-command-agf-team-stop/

- `SKILL.md` — source-command-agf-team-stop (~691 tok)

## .claude/

- `settings.json` (~1608 tok)
- `settings.local.json` (~680 tok)

## .claude/agent-memory/product-lead/

- `kv-cache-tech-assessment.md` (~168 tok)
- `MEMORY.md` (~23 tok)

## .claude/agent-memory/tech-lead/

- `auth-decisions-2026-06-10.md` (~159 tok)
- `d3-shadcn-deferred.md` (~123 tok)
- `data-pipeline-dual-track-deployment.md` — data-pipeline 双轨部署：fresh DB / UAT 新栈启动顺序 (~436 tok)
- `data-pipeline-no-subprocess-bridge.md` (~133 tok)
- `data-pipeline-pg-first.md` (~142 tok)
- `data-pipeline-stocks-sync.md` (~162 tok)
- `dual-db-phase-a.md` (~143 tok)
- `MEMORY.md` (~186 tok)

## .claude/agents/

- `ai-agent-dev.md` — 团队协作 (~1518 tok)
- `apple-code-reviewer.md` — 团队协作 (~1600 tok)
- `apple-dev.md` — 团队协作 (~1369 tok)
- `apple-qa-engineer.md` — 团队协作 (~1217 tok)
- `apple-release-engineer.md` — 铁律 (~1260 tok)
- `backend-dev.md` — 铁律 (~1600 tok)
- `code-reviewer.md` — 铁律 (~1952 tok)
- `content-writer.md` — 铁律 (~1120 tok)
- `deploy-engineer.md` — 铁律 (~1291 tok)
- `frontend-dev.md` — 团队协作 (~1508 tok)
- `growth-analyst.md` — 铁律 (~1076 tok)
- `miniapp-code-reviewer.md` — 团队协作 (~1755 tok)
- `miniapp-dev.md` — 团队协作 (~1623 tok)
- `miniapp-qa-engineer.md` — 团队协作 (~1040 tok)
- `ml-engineer.md` — 团队协作 (~1151 tok)
- `product-lead.md` — 铁律 (~3811 tok)
- `qa-engineer.md` — 铁律 (~2313 tok)
- `tech-lead.md` — 铁律 (~1350 tok)
- `uiux-designer.md` — 团队协作 (~1142 tok)

## .claude/commands/

- `agf-apple-release.md` — 任务 (~567 tok)
- `agf-board.md` — 任务 (~271 tok)
- `agf-deploy-uat.md` — 任务 (~515 tok)
- `agf-init.md` — 任务 (~1119 tok)
- `agf-release-retro.md` — 任务 (~251 tok)
- `agf-tasks.md` — 任务 (~213 tok)
- `agf-team-start.md` — 任务 (~1776 tok)
- `agf-team-stop.md` — 任务 (~658 tok)
- `agf-uat.md` — 任务 (~456 tok)

## .claude/hooks/

- `block-dangerous-bash.sh` — PreToolUse hook: block destructive Bash commands. (~2414 tok)
- `check-progress-file.sh` — .claude/hooks/check-progress-file.sh (~1809 tok)
- `sanitize-tool-output.sh` — PostToolUse hook: warn (not block) when external content shows prompt-injection (~1526 tok)
- `scan-commit.sh` — Git pre-commit hook: scan staged diff for secrets that the UserPromptSubmit (~1599 tok)
- `scan-secrets.sh` — UserPromptSubmit hook: block prompts containing secret/credential patterns. (~2140 tok)
- `session-start-context.sh` — session-start-context.sh (~1074 tok)
- `skill-rules.json` (~1545 tok)
- `skill-suggester.sh` — UserPromptSubmit hook: suggest relevant skills/commands based on prompt keywords + paths. (~952 tok)
- `teammate-keepalive.sh` — .claude/hooks/teammate-keepalive.sh (~364 tok)
- `test-block-dangerous-bash.sh` — Tests for .claude/hooks/block-dangerous-bash.sh (~3320 tok)
- `test-scan-secrets.sh` — Test harness for scan-secrets.sh + sanitize-tool-output.sh. (~1796 tok)
- `test-validate-task-schema.sh` — test-validate-task-schema.sh — 回归测试 validate-task-schema.sh (~534 tok)
- `validate-review-verdict.sh` — validate-review-verdict.sh (~1261 tok)
- `validate-task-schema.sh` — validate-task-schema.sh (~844 tok)

## .claude/hooks/tests/

- `test-block-dangerous-bash.sh` — Tests for .claude/hooks/block-dangerous-bash.sh (~3321 tok)
- `test-scan-secrets.sh` — Test harness for scan-secrets.sh + sanitize-tool-output.sh. (~1797 tok)
- `test-secret-pattern-parity.sh` — test-secret-pattern-parity.sh — 断言 scan-secrets.sh 与 scan-commit.sh 覆盖同一组厂商密钥。 (~494 tok)
- `test-validate-review-verdict.sh` — test-validate-review-verdict.sh — validate-review-verdict.sh 单元测试 (~982 tok)
- `test-validate-task-schema.sh` — test-validate-task-schema.sh — 回归测试 validate-task-schema.sh (~653 tok)

## .claude/progress/

- `frontend-dev.md` — frontend-dev Progress Log (~421 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)
- `repo-layout.md` — Repository Layout (~1808 tok)
- `team-mode.md` — Team Mode 协议（多角色任务必须以 Agent Team 启动） (~819 tok)

## .claude/scripts/

- `agf-board.sh` — agf-board.sh — AGF 实时开发看板（task 卡片 → 自包含 HTML，浏览器 open 即用） (~3915 tok)
- `agf-check-ownership.sh` — agf-check-ownership.sh — Pool 并行派发时校验实例只改了自己名下的文件 (~486 tok)
- `agf-matrix.sh` — agf-matrix.sh — PL 在 Multi-instance Worker Pool 模式下聚合 N 份报告为 1 张表 (~2091 tok)
- `agf-next-instance.sh` — agf-next-instance.sh — Multi-instance Worker Pool 的「N 分配算法」可执行版 (~562 tok)
- `agf-tasks.sh` — agf-tasks.sh — 查阅 Claude Code Agent Teams 原生 task list（人类可读视图） (~1931 tok)
- `agf-tui.sh` — agf-tui.sh — 纯 bash 零依赖 TUI 原语库（被 source，不是入口） (~4833 tok)
- `archive-progress.sh` — archive-progress.sh — UAT 签字后归档 progress/ 到 docs/qa/<feature>-process-log.md (~824 tok)
- `lint-all.sh` — lint-all.sh — 项目级一键 lint 入口 (~1173 tok)
- `test-install.sh` — test-install.sh — 安装链路 E2E 自检（install-to-existing.sh） (~2361 tok)

## .claude/skills/agf-deploying-uat/

- `SKILL.md` — Deploying to the isolated UAT stack (~1567 tok)

## .claude/skills/agf-releasing-apple/

- `SKILL.md` — Releasing the Apple distributable (sign → notarize → package → smoke) (~1372 tok)

## .claude/skills/agf-running-apple-sit/

- `SKILL.md` — Running Apple SIT (xcodebuild + simulator) (~984 tok)

## .claude/skills/agf-running-release-retro/

- `SKILL.md` — Running Release Retrospective (~1526 tok)

## .claude/skills/agf-running-sit-tests/

- `SKILL.md` — Running System Integration Tests (SIT) (~1322 tok)

## .claude/skills/agf-wiring-apple-llm/

- `SKILL.md` — Wiring LLM into the Apple client (gateway streaming / on-device) (~911 tok)

## .claude/skills/agf-wiring-multi-llm-sdk/

- `SKILL.md` — Wiring Multi-LLM SDK (DeepSeek / Doubao / Qwen / MiniMax) (~1499 tok)

## .claude/skills/agf-writing-adr/

- `SKILL.md` — Writing an ADR (Architecture Decision Record) (~952 tok)

## .claude/skills/agf-writing-docx-reports/

- `SKILL.md` — 写 docx 报告 — 高密度实战手册 (~1121 tok)
- `template.js` — 4A 评审决议书 docx 生成器 — 阅读友好版 v2 (~9372 tok)

## .claude/skills/agf-writing-docx-reports/references/

- `design-tokens-and-helpers.md` — 设计 token + spacing + 9 个 helper + 文档外壳（docx-js 全套） (~2235 tok)

## .claude/skills/agf-writing-github-issue/

- `SKILL.md` — Writing a GitHub Issue (~1368 tok)

## .claude/skills/agf-writing-github-issue/references/

- `templates-and-examples.md` — Body 模板 + gh CLI heredoc 模板 + 完整例子 (~858 tok)

## .claude/skills/agf-writing-pptx-reports/

- `diagram-generation-guide.md` — 图层生成实战手册 — draw.io / Mermaid / matplotlib 选型 (~2475 tok)
- `SKILL.md` — 写 pptx 报告 — 高密度实战手册 (~1630 tok)
- `template-team-guide.md` — Template.pptx（iSlide 商务团队主题）使用指南 (~2637 tok)
- `template.py` — set_font, clear_template_slides, dump_template_structure, rect + 3 more (~6184 tok)

## .claude/skills/agf-writing-pptx-reports/references/

- `design-tokens-and-techniques.md` — 设计 token + 12 个关键技巧 + 品牌色获取流程 (~1893 tok)
- `rendering-and-embedding.md` — 图嵌入 / PNG→PDF 输出 + 资源链接 + 沉淀来源 (~535 tok)
- `template-based-generation.md` — 基于已有 .pptx 模板生成（推荐路径详解） (~1086 tok)

## .claude/skills/agf-writing-prd/

- `SKILL.md` — Writing a PRD (Product Requirements Document) (~1208 tok)

## .claude/skills/agf-writing-qa-report/

- `SKILL.md` — Writing a QA Report (E2E / UAT) (~1481 tok)

## .claude/skills/docx/

- `LICENSE.txt` (~367 tok)
- `SKILL.md` — DOCX creation, editing, and analysis (~5014 tok)

## .claude/skills/docx/scripts/

- `__init__.py` (~1 tok)
- `accept_changes.py` — Accept all tracked changes in a DOCX file using LibreOffice. (~1158 tok)
- `comment.py` — Add comments to DOCX documents. (~3056 tok)

## .claude/skills/docx/scripts/office/

- `pack.py` — Pack a directory into a DOCX, PPTX, or XLSX file. (~1426 tok)
- `soffice.py` — get_soffice_env, run_soffice (~1513 tok)
- `unpack.py` — Unpack Office files (DOCX, PPTX, XLSX) for editing. (~1158 tok)
- `validate.py` — main (~1048 tok)

## .claude/skills/docx/scripts/office/helpers/

- `__init__.py` (~0 tok)
- `merge_runs.py` — Merge adjacent runs with identical formatting in DOCX. (~1591 tok)
- `simplify_redlines.py` — Simplify tracked changes by merging adjacent w:ins or w:del elements. (~1644 tok)

## .claude/skills/docx/scripts/office/schemas/ISO-IEC29500-4_2016/

- `dml-chart.xsd` (~19996 tok)
- `dml-chartDrawing.xsd` (~1855 tok)
- `dml-diagram.xsd` (~13681 tok)
- `dml-lockedCanvas.xsd` (~167 tok)
- `dml-main.xsd` (~40544 tok)
- `dml-picture.xsd` (~329 tok)
- `dml-spreadsheetDrawing.xsd` (~2364 tok)
- `dml-wordprocessingDrawing.xsd` (~3946 tok)
- `pml.xsd` (~22297 tok)
- `shared-additionalCharacteristics.xsd` (~339 tok)
- `shared-bibliography.xsd` (~1955 tok)
- `shared-commonSimpleTypes.xsd` (~1702 tok)
- `shared-customXmlDataProperties.xsd` (~333 tok)
- `shared-customXmlSchemaProperties.xsd` (~235 tok)
- `shared-documentPropertiesCustom.xsd` (~696 tok)
- `shared-documentPropertiesExtended.xsd` (~936 tok)
- `shared-documentPropertiesVariantTypes.xsd` (~2002 tok)
- `shared-math.xsd` (~6217 tok)
- `shared-relationshipReference.xsd` (~365 tok)
- `sml.xsd` (~64608 tok)
- `vml-main.xsd` (~6973 tok)
- `vml-officeDrawing.xsd` (~6742 tok)
- `vml-presentationDrawing.xsd` (~143 tok)
- `vml-spreadsheetDrawing.xsd` (~1524 tok)
- `vml-wordprocessingDrawing.xsd` (~1070 tok)
- `wml.xsd` (~45698 tok)
- `xml.xsd` — Declares which (~1239 tok)

## .claude/skills/docx/scripts/office/schemas/ecma/fouth-edition/

- `opc-contentTypes.xsd` (~523 tok)
- `opc-coreProperties.xsd` (~671 tok)
- `opc-digSig.xsd` (~762 tok)
- `opc-relationships.xsd` (~358 tok)

## .claude/skills/docx/scripts/office/schemas/mce/

- `mc.xsd` (~834 tok)

## .claude/skills/docx/scripts/office/schemas/microsoft/

- `wml-2010.xsd` (~7080 tok)
- `wml-2012.xsd` (~999 tok)
- `wml-2018.xsd` (~241 tok)
- `wml-cex-2018.xsd` (~475 tok)
- `wml-cid-2016.xsd` (~268 tok)
- `wml-sdtdatahash-2020.xsd` (~160 tok)
- `wml-symex-2015.xsd` (~199 tok)

## .claude/skills/docx/scripts/office/validators/

- `__init__.py` (~96 tok)
- `base.py` — URL patterns: 1 routes (~9329 tok)
- `docx.py` — URL patterns: 6 routes (~4678 tok)
- `pptx.py` — PPTXSchemaValidator: validate, validate_uuid_ids, validate_slide_layout_ids, validate_no_duplicate_slide_layouts + 1 more (~2807 tok)
- `redlining.py` — RedliningValidator: repair, validate (~2548 tok)

## .claude/skills/docx/scripts/templates/

- `comments.xml` (~744 tok)
- `commentsExtended.xml` (~746 tok)
- `commentsExtensible.xml` (~774 tok)
- `commentsIds.xml` (~749 tok)
- `people.xml` (~33 tok)

## .claude/skills/pptx/

- `editing.md` — Editing Presentations (~1711 tok)
- `LICENSE.txt` (~367 tok)
- `pptxgenjs.md` — PptxGenJS Tutorial (~3194 tok)
- `SKILL.md` — PPTX Skill (~2282 tok)

## .claude/skills/pptx/scripts/

- `__init__.py` (~0 tok)
- `add_slide.py` — Add a new slide to an unpacked PPTX directory. (~1964 tok)
- `clean.py` — Remove unreferenced files from an unpacked PPTX directory. (~2738 tok)
- `thumbnail.py` — Create thumbnail grids from PowerPoint presentation slides. (~2510 tok)

## .claude/skills/pptx/scripts/office/

- `pack.py` — Pack a directory into a DOCX, PPTX, or XLSX file. (~1426 tok)
- `soffice.py` — get_soffice_env, run_soffice (~1513 tok)
- `unpack.py` — Unpack Office files (DOCX, PPTX, XLSX) for editing. (~1158 tok)
- `validate.py` — main (~1048 tok)

## .claude/skills/pptx/scripts/office/helpers/

- `__init__.py` (~0 tok)
- `merge_runs.py` — Merge adjacent runs with identical formatting in DOCX. (~1591 tok)
- `simplify_redlines.py` — Simplify tracked changes by merging adjacent w:ins or w:del elements. (~1644 tok)

## .claude/skills/pptx/scripts/office/schemas/ISO-IEC29500-4_2016/

- `dml-chart.xsd` (~19996 tok)
- `dml-chartDrawing.xsd` (~1855 tok)
- `dml-diagram.xsd` (~13681 tok)
- `dml-lockedCanvas.xsd` (~167 tok)
- `dml-main.xsd` (~40544 tok)
- `dml-picture.xsd` (~329 tok)
- `dml-spreadsheetDrawing.xsd` (~2364 tok)
- `dml-wordprocessingDrawing.xsd` (~3946 tok)
- `pml.xsd` (~22297 tok)
- `shared-additionalCharacteristics.xsd` (~339 tok)
- `shared-bibliography.xsd` (~1955 tok)
- `shared-commonSimpleTypes.xsd` (~1702 tok)
- `shared-customXmlDataProperties.xsd` (~333 tok)
- `shared-customXmlSchemaProperties.xsd` (~235 tok)
- `shared-documentPropertiesCustom.xsd` (~696 tok)
- `shared-documentPropertiesExtended.xsd` (~936 tok)
- `shared-documentPropertiesVariantTypes.xsd` (~2002 tok)
- `shared-math.xsd` (~6217 tok)
- `shared-relationshipReference.xsd` (~365 tok)
- `sml.xsd` (~64608 tok)
- `vml-main.xsd` (~6973 tok)
- `vml-officeDrawing.xsd` (~6742 tok)
- `vml-presentationDrawing.xsd` (~143 tok)
- `vml-spreadsheetDrawing.xsd` (~1524 tok)
- `vml-wordprocessingDrawing.xsd` (~1070 tok)
- `wml.xsd` (~45698 tok)
- `xml.xsd` — Declares which (~1239 tok)

## .claude/skills/pptx/scripts/office/schemas/ecma/fouth-edition/

- `opc-contentTypes.xsd` (~523 tok)
- `opc-coreProperties.xsd` (~671 tok)
- `opc-digSig.xsd` (~762 tok)
- `opc-relationships.xsd` (~358 tok)

## .claude/skills/pptx/scripts/office/schemas/mce/

- `mc.xsd` (~834 tok)

## .claude/skills/pptx/scripts/office/schemas/microsoft/

- `wml-2010.xsd` (~7080 tok)
- `wml-2012.xsd` (~999 tok)
- `wml-2018.xsd` (~241 tok)
- `wml-cex-2018.xsd` (~475 tok)
- `wml-cid-2016.xsd` (~268 tok)
- `wml-sdtdatahash-2020.xsd` (~160 tok)
- `wml-symex-2015.xsd` (~199 tok)

## .claude/skills/pptx/scripts/office/validators/

- `__init__.py` (~96 tok)
- `base.py` — URL patterns: 1 routes (~9329 tok)
- `docx.py` — URL patterns: 6 routes (~4678 tok)
- `pptx.py` — PPTXSchemaValidator: validate, validate_uuid_ids, validate_slide_layout_ids, validate_no_duplicate_slide_layouts + 1 more (~2807 tok)
- `redlining.py` — RedliningValidator: repair, validate (~2548 tok)

## .claude/standards/

- `ac-lifecycle.md` — AC Lifecycle and Delivery Definition (~1630 tok)
- `apple-native.md` — Apple Native Standards（macOS / iOS 原生专项规范） (~1427 tok)
- `coding.md` — Coding and AI Development Standards (~1073 tok)
- `communication.md` — Communication Style (~311 tok)
- `cost-budget.md` — Cost & Token Budget Baseline (~1665 tok)
- `deployment.md` — Deployment Standards (~1863 tok)
- `document-rules.md` — Document Output and Single Source Rules (~442 tok)
- `miniapp.md` — MiniApp Standards（微信小程序专项规范） (~1321 tok)
- `observability.md` — Observability Baseline (~683 tok)
- `plans-format.md` — Plans 轻量化格式规范 (~397 tok)
- `qa-close-verify.md` — P0/P1 Issue Close Verify SOP (~1217 tok)
- `review-checklist.md` — Code Review Checklist (~1211 tok)
- `security.md` — Security Baseline (~1457 tok)
- `superpowers.md` — Superpowers Skills Policy (~966 tok)
- `team-roles.md` — Team Roles and Capability Baseline (~3084 tok)
- `testing.md` — Testing Standards (~2308 tok)
- `versioning.md` — Versioning Standard (~1223 tok)
- `workflow.md` — Team Workflow (~4894 tok)

## .clawhub/

- `lock.json` (~37 tok)

## .codegraph/

- `.gitignore` — Git ignore rules (~61 tok)
- `daemon.log` (~4538 tok)

## .codex/

- `config.toml` (~200 tok)
- `hooks.json` (~392 tok)

## .codex/agents/

- `ai-agent-dev.toml` — ` | free | 工具有 schema；命中"Plan Mode 强制"表格的高风险变更须有 PL 授权 | (~1622 tok)
- `apple-code-reviewer.toml` (~1772 tok)
- `apple-dev.toml` — `、`apple/AppCore/Sources/**` | free（ADR-007 工程结构） | strict concurrency 零 warning；按 target 过模拟器目测 | (~1460 tok)
- `apple-qa-engineer.toml` (~1324 tok)
- `apple-release-engineer.toml` (~1381 tok)
- `backend-dev.toml` — ` 或本任务声明的归属目录 | free | 每条 AC 配 curl 自验输出；端点有请求/响应 schema | (~1714 tok)
- `code-reviewer.toml` — Declares XxxResponse (~2173 tok)
- `content-writer.toml` (~1236 tok)
- `deploy-engineer.toml` (~1416 tok)
- `frontend-dev.toml` — `、`frontend/src/pages/**`、`frontend/src/features/**` 或本任务声明的归属目录 | free | 启动 dev server 目测验证；遵循 AGENTS.md ## Tech Stack | (~1614 tok)
- `growth-analyst.toml` (~1177 tok)
- `miniapp-code-reviewer.toml` (~1943 tok)
- `miniapp-dev.toml` — `、`miniapp/native/components/**` | free（WXML/WXSS/JS 微信官方目录结构） | DevTools 模拟器目测通过；setData payload ≤ 256KB | (~1760 tok)
- `miniapp-qa-engineer.toml` (~1130 tok)
- `ml-engineer.toml` — `（异步任务 / 轮询 / webhook 回调） | free | 真实 API 调用验证 + 异常处理（超时 / 限流 / 无效输入） | (~1213 tok)
- `product-lead.toml` (~4244 tok)
- `qa-engineer.toml` (~2556 tok)
- `tech-lead.toml` (~1426 tok)
- `uiux-designer.toml` (~1261 tok)

## .codex/hooks/

- `block-dangerous-bash.sh` — PreToolUse hook: block destructive Bash commands. (~2414 tok)
- `check-progress-file.sh` — .claude/hooks/check-progress-file.sh (~1809 tok)
- `sanitize-tool-output.sh` — PostToolUse hook: warn (not block) when external content shows prompt-injection (~1526 tok)
- `scan-commit.sh` — Git pre-commit hook: scan staged diff for secrets that the UserPromptSubmit (~1599 tok)
- `scan-secrets.sh` — UserPromptSubmit hook: block prompts containing secret/credential patterns. (~2140 tok)
- `session-start-context.sh` — session-start-context.sh (~1074 tok)
- `skill-rules.json` (~1545 tok)
- `skill-suggester.sh` — UserPromptSubmit hook: suggest relevant skills/commands based on prompt keywords + paths. (~952 tok)
- `teammate-keepalive.sh` — .claude/hooks/teammate-keepalive.sh (~364 tok)
- `test-block-dangerous-bash.sh` — Tests for .claude/hooks/block-dangerous-bash.sh (~3320 tok)
- `test-scan-secrets.sh` — Test harness for scan-secrets.sh + sanitize-tool-output.sh. (~1796 tok)
- `test-validate-task-schema.sh` — test-validate-task-schema.sh — 回归测试 validate-task-schema.sh (~534 tok)
- `validate-review-verdict.sh` — validate-review-verdict.sh (~1261 tok)
- `validate-task-schema.sh` — validate-task-schema.sh (~844 tok)

## .codex/hooks/tests/

- `test-block-dangerous-bash.sh` — Tests for .claude/hooks/block-dangerous-bash.sh (~3321 tok)
- `test-scan-secrets.sh` — Test harness for scan-secrets.sh + sanitize-tool-output.sh. (~1797 tok)
- `test-secret-pattern-parity.sh` — test-secret-pattern-parity.sh — 断言 scan-secrets.sh 与 scan-commit.sh 覆盖同一组厂商密钥。 (~494 tok)
- `test-validate-review-verdict.sh` — test-validate-review-verdict.sh — validate-review-verdict.sh 单元测试 (~982 tok)
- `test-validate-task-schema.sh` — test-validate-task-schema.sh — 回归测试 validate-task-schema.sh (~653 tok)

## .github/workflows/

- `ci.yml` — ", "速赢AI**"] (~678 tok)

## .playwright-cli/

- `console-2026-06-23T16-18-28-205Z.log` (~930 tok)
- `console-2026-06-24T10-43-27-363Z.log` — Declares can (~358 tok)
- `console-2026-06-24T11-09-39-445Z.log` (~377 tok)
- `console-2026-06-24T11-14-11-905Z.log` — Declares can (~581 tok)
- `console-2026-06-25T16-19-24-256Z.log` (~387 tok)
- `page-2026-06-23T16-18-28-687Z.yml` (~190 tok)
- `page-2026-06-23T16-21-38-764Z.yml` (~2493 tok)
- `page-2026-06-23T16-22-21-468Z.yml` (~2892 tok)
- `page-2026-06-23T16-22-38-603Z.yml` (~2496 tok)
- `page-2026-06-23T16-22-40-713Z.yml` (~2511 tok)
- `page-2026-06-23T16-22-49-969Z.yml` (~2628 tok)
- `page-2026-06-24T10-43-27-629Z.yml` (~8 tok)
- `page-2026-06-24T10-43-37-462Z.yml` (~2072 tok)
- `page-2026-06-24T10-45-04-127Z.yml` (~6536 tok)
- `page-2026-06-24T10-45-20-819Z.yml` (~3845 tok)
- `page-2026-06-24T11-09-40-025Z.yml` (~8 tok)
- `page-2026-06-24T11-10-00-862Z.yml` (~262 tok)
- `page-2026-06-24T11-14-12-390Z.yml` (~8 tok)
- `page-2026-06-24T11-14-25-550Z.yml` (~2362 tok)
- `page-2026-06-24T11-14-39-096Z.yml` (~1890 tok)
- `page-2026-06-24T11-14-46-976Z.yml` (~4437 tok)
- `page-2026-06-24T11-14-55-805Z.yml` (~4864 tok)
- `page-2026-06-25T16-19-24-502Z.yml` (~190 tok)
- `page-2026-06-25T16-19-40-364Z.yml` (~5461 tok)
- `page-2026-06-25T16-41-08-917Z.yml` (~190 tok)
- `page-2026-06-25T16-42-05-328Z.yml` (~4308 tok)
- `page-2026-06-25T16-42-15-407Z.yml` (~4282 tok)
- `page-2026-06-25T16-42-26-570Z.yml` (~4310 tok)
- `page-2026-06-25T16-43-43-572Z.yml` (~8 tok)
- `page-2026-06-25T16-44-11-363Z.yml` (~4300 tok)
- `page-2026-06-25T16-44-20-247Z.yml` (~5109 tok)
- `page-2026-06-25T16-45-15-056Z.yml` (~8 tok)
- `page-2026-06-25T16-45-33-559Z.yml` (~5109 tok)

## .playwright-mcp/

- `console-2026-06-08T07-21-31-196Z.log` (~138 tok)
- `console-2026-06-08T07-44-03-653Z.log` (~61 tok)
- `console-2026-06-08T07-45-21-973Z.log` (~267 tok)
- `console-2026-06-08T07-54-53-778Z.log` (~527 tok)
- `console-2026-06-08T07-59-02-306Z.log` (~61 tok)
- `console-2026-06-08T08-00-27-827Z.log` (~1374 tok)
- `console-2026-06-09T14-49-57-946Z.log` (~950 tok)
- `console-2026-06-10T04-34-40-332Z.log` (~796 tok)
- `console-2026-06-10T04-36-33-046Z.log` (~2486 tok)
- `console-2026-06-10T09-16-54-819Z.log` (~298 tok)
- `console-2026-06-10T09-18-32-184Z.log` (~470 tok)
- `console-2026-06-10T09-19-32-883Z.log` (~261 tok)
- `console-2026-06-10T09-20-54-376Z.log` — Declares can (~368 tok)
- `console-2026-06-10T09-24-16-695Z.log` — Declares can (~321 tok)
- `console-2026-06-10T09-34-45-878Z.log` (~261 tok)
- `console-2026-06-10T09-34-56-943Z.log` (~261 tok)
- `console-2026-06-10T09-34-57-333Z.log` (~261 tok)
- `console-2026-06-10T09-34-57-774Z.log` (~261 tok)
- `console-2026-06-10T09-35-02-514Z.log` (~261 tok)
- `console-2026-06-10T09-35-02-947Z.log` (~343 tok)
- `console-2026-06-10T09-35-03-373Z.log` (~261 tok)
- `console-2026-06-10T09-35-03-699Z.log` (~261 tok)
- `console-2026-06-10T09-35-10-855Z.log` (~261 tok)
- `console-2026-06-10T09-35-32-907Z.log` — Declares can (~321 tok)
- `console-2026-06-10T10-13-14-467Z.log` (~2033 tok)
- `console-2026-06-10T10-24-28-768Z.log` — Declares can (~321 tok)
- `console-2026-06-10T10-37-30-012Z.log` (~261 tok)
- `console-2026-06-10T10-39-55-216Z.log` (~261 tok)
- `console-2026-06-10T10-41-44-661Z.log` — Declares can (~321 tok)
- `console-2026-06-10T10-42-38-841Z.log` — Declares can (~321 tok)
- `console-2026-06-10T10-45-19-402Z.log` (~261 tok)
- `console-2026-06-10T10-47-54-050Z.log` — Declares can (~321 tok)
- `console-2026-06-10T10-55-22-818Z.log` — Declares can (~367 tok)
- `console-2026-06-10T14-01-16-349Z.log` (~111 tok)
- `console-2026-06-10T16-02-49-967Z.log` (~685 tok)
- `console-2026-06-10T16-12-01-089Z.log` (~6678 tok)
- `console-2026-06-11T03-50-12-316Z.log` (~1596 tok)
- `console-2026-06-11T03-59-33-566Z.log` (~261 tok)
- `console-2026-06-11T04-04-37-748Z.log` (~261 tok)
- `console-2026-06-11T04-05-14-307Z.log` (~261 tok)
- `console-2026-06-11T04-05-33-747Z.log` (~311 tok)
- `console-2026-06-11T04-06-36-422Z.log` (~2617 tok)

## docs/screener/

- `screener-optimization-design.md` — 速赢AI 选股模型优化 — 设计文档 (~5563 tok)
- `Suying-AI-Screener-Optimization-2026-06-30.md` — 速赢AI 选股模型优化报告 (~6105 tok)

## packages/kronos-factors/config/

- `mode_profiles.json` (~1942 tok)

## packages/kronos-factors/kronos_factors/engine/

- `multi_index.py` — MultiIndexEngine — 宽基指数成分股超额收益挖掘. (~1881 tok)
- `risk_parity.py` — RiskParityAllocator — 风险平价仓位分配器. (~1729 tok)
- `sector_heatmap.py` — SectorHeatmapEngine — 板块实时热度引擎. (~2922 tok)
- `weighted_fusion.py` — WeightedFusionEngine — V5.0 加权融合引擎. (~3616 tok)

## packages/kronos-factors/kronos_factors/engine/llm_intelligence/

- `__init__.py` — LLMIntelligenceEngine — 实时情绪情报引擎. (~3539 tok)

## packages/kronos-factors/tests/

- `test_v5_engines.py` — Unit tests for V5.0 new screening engines. (~5536 tok)

## services/screener-service/app/

- `orchestrator.py` — Mode Orchestrator — V5.0 multi-strategy fusion + Kronos prediction + pipeline. (~5576 tok)
