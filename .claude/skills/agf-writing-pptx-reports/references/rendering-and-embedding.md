# 图嵌入 / PNG→PDF 输出 + 资源链接 + 沉淀来源

> 从 `SKILL.md` 下沉的完整参考。需要 mermaid 出图嵌 PPT、多 PNG 合并 PDF 对外提报、或查外部资源链接时读本文。

## 一键 SVG/PNG/PDF 输出 + mermaid 嵌入

```bash
# 在 build-ppt.py 之前先跑：
mmdc -i diagram.mmd -o diagram.svg
mmdc -i diagram.mmd -o diagram.png -w 2400 -H 1800 -b transparent
```

```python
# build-ppt.py 直接引用 .png：
slide.shapes.add_picture("diagram.png", Inches(0.55), Inches(1.9), height=Inches(5.0))
```

合并多 PNG 为单 PDF（视觉对外提报）：

```python
import subprocess, tempfile
with tempfile.TemporaryDirectory() as tmp:
    for i, png in enumerate(png_paths):
        subprocess.run(["sips", "-s", "format", "pdf", png,
                        "--out", f"{tmp}/p{i}.pdf"], check=True)
    subprocess.run(["pdfunite"] +
                   [f"{tmp}/p{i}.pdf" for i in range(len(png_paths))] +
                   ["out.pdf"], check=True)
```

## 资源链接

**本仓库内**（优先看）：
- `template/Template.pptx` — 1 个 coral 团队风 .pptx 模板（39 slides / 6 layouts / 1 MB；详 `template-team-guide.md` 内 6 layouts + 6 类版面拆解）
- `template-team-guide.md` — Template.pptx 完整使用指南（39 slides / 6 layouts / 6 类版面 / 6 个踩坑）
- `template.py` — 本 skill 自带的 helper 集合（含 `_fix_ph_font` / `clear_template_slides` / `card` / `bullets` / `table_modern` 等）
- `.claude/skills/pptx/SKILL.md` — Anthropic 提供的低层 .pptx 读写 skill（unpack / thumbnail / clean / pack 脚本）

**外部资源**：
- python-pptx 官方文档
- python-pptx Issue #503 — .potx 模板讨论
- pptx-ea-font — 手写 EA 字段的封装库（不装也行，本 skill 已展示手写法）
- SlidesCarnival — 严肃极简风免费模板（视觉参考）
- BrandColorCode — 企业品牌色查询
- Mermaid Live Editor — 在线调试 mermaid 图

## 本 skill 的沉淀来源

2026-05《AI 4A 架构评审管理办法（试行）》v1.0 PPT 实战：
- 23 页，GAC 广汽红主调，党政严肃风
- 嵌入 mermaid flowchart + sequence 双视图 + isolation matrix
- 约 4 小时（含 3 轮迭代：纯代码版 / 装饰修复版 / GAC 红主题版）

> 历史产物（完整 1500 行生成器、文档源、最终 .pptx）在 TopConsultant 仓库，迁入 AppGenesisForge 时已剥离项目耦合，仅保留通用方法论。
