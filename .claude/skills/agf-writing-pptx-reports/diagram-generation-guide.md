# 图层生成实战手册 — draw.io / Mermaid / matplotlib 选型

> 沉淀自 AGF 内部培训 deck v2.2 实战：**41 张架构图**（A 流程 17 / B 概念 6 / C 矩阵 5 / D 关系 4 / F 数据 3 / G 卡片墙 6），约 10h 工时
> 全部踩过 + 验证过的坑与方法。不含理论水文。
>
> **谁会读这份**：用 `agf-writing-pptx-reports` 时发现 deck 缺图（架构 / 流程 / 矩阵 / 决策树），必须先把图生出来再嵌 PPT。

## 何时用本 guide

| 信号 | 用本 guide |
|---|:--:|
| deck 里需要 5 张以上"非简单 mermaid 流程图"的图 | ✅ |
| 用户抱怨"图太少 / 架构看不懂 / 没有可视化" | ✅ |
| 矩阵图（≥ 3 列）/ 角色边界圈 / 决策树 | ✅ |
| 多张图需要"视觉一致性"（同配色 / 同字体 / 同字号体系）| ✅ |
| 单张简单线性流程（≤ 6 节点）| ❌ Mermaid 即可，不必动 draw.io |
| 数据可视化（柱 / 雷达 / 仪表盘）数据驱动 | ❌ matplotlib，本 guide §6 |

## 1. 工具选型决策（41 张图实证）

| 图类型 | 首选 | 替代 | 选型理由 |
|---|---|---|---|
| **简单线性流程**（≤ 8 节点 / 单层） | Mermaid | draw.io | Mermaid 文本 DSL 快 5×，单图 5min |
| **多层架构图**（嵌套 subgraph / 跨边界箭头） | draw.io | — | Mermaid subgraph 配色易翻车（默认棕色） |
| **类比 / 概念图**（足球队 / 时光机文件夹） | draw.io（普通模式） | Excalidraw | 普通 draw.io 风格统一 |
| **矩阵 / 表格图**（4 厂商 × 3 类型 双矩阵） | draw.io | python-pptx add_shape | draw.io 网格控制比 PPT 灵活 |
| **角色 / 边界图**（不重叠椭圆 / 决策象限） | draw.io | — | 椭圆 + 矩阵都靠精确坐标 |
| **决策树**（rhombus 判断节点） | draw.io | — | mermaid flowchart 菱形 hover 时尺寸不稳 |
| **数据可视化**（柱 / 雷达 / 仪表盘） | matplotlib | draw.io 静态 | 数据驱动用 mpl；演示静态用 draw.io |
| **卡片墙**（≥ 4 张卡片 grid） | draw.io | python-pptx 直接画 | 提前生成 PNG 比 slide 内画稳定 |

**经验规则**：deck 总图数 ≤ 10 → 全 Mermaid；> 10 张或要"视觉一致" → 全 draw.io 沉本到底；混搭只会增加视觉割裂。

## 2. draw.io 工作流（重点）

### 2.1 安装

```bash
brew install --cask drawio   # macOS，约 150 MB
# 安装后：/Applications/draw.io.app + /opt/homebrew/bin/drawio 软链接
```

### 2.2 headless CLI 渲染

```bash
/Applications/draw.io.app/Contents/MacOS/drawio \
  --export --format png --width 3200 \
  --output out.png in.drawio
```

| 参数 | 说明 |
|---|---|
| `--format png` | PNG（PPT 嵌入用）。也支持 svg / pdf / jpg |
| `--width 3200` | **必设**。默认输出 800px 太糊，3200px 适配 16:9 PPT（13.333" × 200 DPI ≈ 2666px，留余量到 3200）|
| `-t / --transparent` | PNG 透明背景（嵌 PPT 时通常用白底，不必）|
| `-s 2 / --scale 2` | 矢量缩放（与 --width 二选一）|

**渲染速度**：单图约 1-3s（Electron 启动慢，但 draw.io 内部有进程复用）；41 张图 ~3min 跑完。

### 2.3 mxGraph XML 最小模板

```xml
<mxfile host="app.diagrams.net" version="30.0.1">
  <diagram name="my-diagram" id="D1">
    <mxGraphModel dx="1600" dy="900" page="1" pageWidth="1600" pageHeight="900">
      <root>
        <mxCell id="0" /><mxCell id="1" parent="0" />

        <!-- 节点 -->
        <mxCell id="n1" value="深色节点" vertex="1" parent="1"
                style="rounded=1;fillColor=#0E3569;strokeColor=#0E3569;fontColor=#FFFFFF;fontSize=20;fontFamily=PingFang SC;fontStyle=1;strokeWidth=2;arcSize=10;">
          <mxGeometry x="100" y="100" width="240" height="80" as="geometry" />
        </mxCell>

        <!-- 边（必须 source/target 引用 id） -->
        <mxCell id="e1" edge="1" parent="1" source="n1" target="n2"
                style="endArrow=classic;endFill=1;endSize=14;strokeColor=#0E3569;strokeWidth=2.5;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### 2.4 Cell 类型清单（按用途）

| 用途 | shape= / style= 关键字段 | 何时用 |
|---|---|---|
| **圆角矩形** | `rounded=1;arcSize=10` | 90% 节点用这个 |
| **椭圆** | `ellipse` | 角色 / 决策象限 / 雷达顶点 |
| **三角形** | `shape=triangle;direction=north` | 雷达图 / 视觉装饰 |
| **菱形（判断）** | `rhombus` | 决策树 / 流程分支 |
| **文本（无框）** | `text;html=1;strokeColor=none;fillColor=none` | 标签 / 说明 / 标题 |
| **直边** | `endArrow=classic;endFill=1` | 流程顺序箭头 |
| **正交折边** | `edgeStyle=orthogonalEdgeStyle;rounded=1` | 90° 折线（最常用）|
| **虚线边** | `dashed=1;dashPattern=8 4` | 失败回路 / 可选路径 |
| **曲线** | `curved=1` | 循环箭头（TDD red→green→refactor）|

### 2.5 mxGeometry 中点坐标

边 cell 默认走最短路径。要绕路 / 加拐点 → 在 mxGeometry 里加 `<Array as="points"><mxPoint x=".." y=".." /></Array>`：

```xml
<mxCell id="back" edge="1" parent="1" source="s4" target="s3"
        style="endArrow=classic;dashed=1;curved=1;...">
  <mxGeometry relative="1" as="geometry">
    <Array as="points">
      <mxPoint x="900" y="550" />
      <mxPoint x="650" y="550" />
    </Array>
  </mxGeometry>
</mxCell>
```

## 3. 设计 token（与 AGF PPT 对齐）

### 颜色（直接拷贝）

```
navy    #0E3569   主色 / 深色 box / 标题
coral   #F06966   accent / 警示 / 高亮
gold    #FFBF00   第三色 / 输入 / 装饰
green   #2E8B57   pass / 成功（如 TDD 绿、UAT 签字）
浅蓝    #EEF3F9   subgraph 浅底
浅红    #FFE5E5   失败 / 反例浅底
浅绿    #E5F5E5   成功浅底
灰色文 #999999   次要文本 / 占位 dash
```

7-8 色覆盖 90% 场景。**别超过 12 色**（与 PPT skill 同规则）。

### 字体 — 一律 PingFang SC

```
fontFamily=PingFang SC
```

⚠️ Heiti SC 视觉"老派"，全局用 PingFang SC。**与 PPT 嵌入字体一致**，确保跨页面无字体跳变。

draw.io 通过 SVG `<foreignObject>` 写入 font-family，渲染时调 Chromium 找系统字体 → macOS 找到 PingFang SC 即生效。

### 字号体系（基准画布 1600×900）

| 用途 | 字号 | bold |
|---|---|---|
| **标题**（最上方） | 28pt | ✓ |
| **章节 / subgraph 标题** | 22-24pt | ✓ |
| **节点（深色背景）** | 20-22pt | ✓ |
| **节点（浅色 / 描述）** | 18-20pt | — |
| **输入 / 输出强调框** | 24-26pt | ✓ |
| **注解 / 底部结论** | 16-18pt | 视情况 |
| **小标签 / 角标** | 14-15pt | — |

**字号对应实际渲染尺寸**：3200px 输出，每 pt 约 4-5px 高 → 28pt = ~140px，在 PPT 内缩到 13.333" slide 后 = ~28px，PPT 32pt 视感等价。

### 画布尺寸

**统一 1600×900**（16:9，与 PPT slide 比例一致）。所有图保持等比，嵌 PPT 时 `add_picture(height=Inches(N))` 缩放不变形。

## 4. 8 大致丑坑（必须主动避开）

| # | 坑 | 后果 | 修法 |
|:-:|---|---|---|
| 1 | `fontFamily=Heiti SC` | 中文字感老派"显得奇怪" | 全部替换 PingFang SC（`sed -i '' 's/Heiti SC/PingFang SC/g' *.drawio`）|
| 2 | 大背景 box 加 `sketch=1` + fillColor | 背景变 hatch 斜线纹理，盖前景文字 | 大背景去掉 sketch；小元素可保留手画感 |
| 3 | 长英文串（如 `Doubao-Seed-2.0-Pro`）在 240px box 内换行 | PingFang 字距比 Heiti 宽 ~5%，原宽度不够 | box width 加 30px（240→270）+ spacingLeft/Right 留内边距 |
| 4 | 渲染不带 `--width 3200` | 默认 800px 输出糊 | 必须显式 `--width 3200` |
| 5 | `value="..."` 里裸 `\n` | XML 不识别 | 用 `&#xa;`（line feed XML entity）|
| 6 | `value` 里裸 `&` / `<` / `>` | XML parser 报错 | `&amp;` / `&lt;` / `&gt;` |
| 7 | edge 用纯 mxPoint 坐标定起止 | 节点移动后边不跟 | 用 `source="id1" target="id2"`，坐标只用于拐点 |
| 8 | 节点 emoji（如 💡 ⚽ 📷） | LibreOffice 转 PDF 时可能丢失 | macOS 直接 PNG 嵌 PPT OK；如果走 PDF 出版本，慎用 emoji |

## 5. Mermaid 工作流（≤ 10 张简单图时）

### 5.1 安装 + CLI

```bash
brew install mermaid-cli   # mmdc
mmdc -i diagram.mmd -o diagram.png -w 1600 -H 900 -s 2 -b white -p puppeteer-config.json
```

`puppeteer-config.json`：
```json
{
  "args": ["--no-sandbox", "--font-render-hinting=medium"]
}
```

### 5.2 主题变量配齐（避免棕色翻车）

```mermaid
---
config:
  theme: base
  themeVariables:
    primaryColor: '#0E3569'
    primaryTextColor: '#ffffff'
    primaryBorderColor: '#0E3569'
    lineColor: '#0E3569'
    secondaryColor: '#EEF3F9'
    clusterBkg: '#EEF3F9'       # subgraph 背景（不设默认棕色 ⚠️）
    clusterBorder: '#0E3569'
    fontFamily: 'PingFang SC, Heiti SC, Arial, sans-serif'
    fontSize: '15px'
---
flowchart LR
  ...
```

### 5.3 Mermaid 局限（实测）

- subgraph 嵌套 ≥ 2 层时布局不稳
- 节点形状有限（无 rhombus 决策 / 无 triangle）
- 多色高亮要 classDef，写起来不如 draw.io 直观
- 长字符串自动 wrap，但折点位置不可控

**结论**：超过 10 个节点 / 需要精确视觉控制 → 转 draw.io。

## 6. matplotlib 工作流（数据驱动图）

仅当**数据从 CSV / 实验结果**动态生成图时用 matplotlib。本 guide 来源的 41 张图里 F 类 3 张（雷达 / 柱状 / 仪表盘）都是**演示数据静态画**——用 draw.io 反而省一次工具切换。

确实需要 mpl 时：
```bash
pip3 install --user --break-system-packages matplotlib
```
中文字体：
```python
import matplotlib
matplotlib.rcParams['font.family'] = ['PingFang SC', 'Heiti SC']
matplotlib.rcParams['axes.unicode_minus'] = False
```

## 7. 批量工作流（41 张图实证）

```bash
# 目录结构
docs/training/diagrams/
├── src/   *.drawio  (XML 源)
└── png/   *.png     (3200px 渲染产物)
```

### 7.1 批量渲染

```bash
cd docs/training/diagrams/src
for f in *.drawio; do
  /Applications/draw.io.app/Contents/MacOS/drawio \
    --export --format png --width 3200 \
    --output "../png/${f%.drawio}.png" "$f" 2>&1 | tail -1
done
```

### 7.2 全局字体替换

```bash
# 改 Heiti SC → PingFang SC（实测可用）
for f in *.drawio; do
  sed -i '' 's/fontFamily=Heiti SC/fontFamily=PingFang SC/g' "$f"
done
# 然后重跑 7.1 批量渲染
```

### 7.3 工时估算（实测）

| 阶段 | 工时 |
|---|---|
| 单图首次（构思 + 写 XML + 验证渲染）| 5-10 min |
| 单图修订（改字段 / 重渲染）| 1-2 min |
| 字体 / 配色全局调整（41 张）| 5 min（sed + 重渲染）|
| 41 张全部首次完成 | ~6-8 h |

## 8. 嵌入 PPT 路径

PNG 嵌 slide：

```python
from pptx.util import Inches
slide.shapes.add_picture(
    "docs/training/diagrams/png/A1-agf-three-layer.png",
    left=Inches(0.55), top=Inches(1.6),
    height=Inches(5.0)   # 等比缩放
)
```

**3200px 宽 PNG → 缩到 5" 高 slide**：分辨率充裕（5" × 200 DPI = 1000px），不会糊。

一页放 2 张图（左右并列）：每张 `height=Inches(4.5)`，左 `left=Inches(0.55)`，右 `left=Inches(7.0)`。

## 9. draw.io vs Mermaid vs matplotlib 选型对照（一图速查）

| 维度 | draw.io | Mermaid | matplotlib |
|---|---|---|---|
| 学习曲线 | 中（mxGraph XML） | 低（DSL） | 中（Python API） |
| 单图源长度 | 长 5-10× | 短 | 中 |
| 坐标控制 | 精确手工 | 自动布局 | 精确（pyplot）|
| 中文字体可控性 | ✅ 强 | ⚠️ 中（看 puppeteer + 系统）| ⚠️ 弱（需配 rcParams + fontconfig）|
| 视觉一致性（多图）| ✅ 强 | ⚠️ 中 | ⚠️ 中 |
| 数据驱动 | ❌ 弱（手工坐标）| ⚠️ 中 | ✅ 强 |
| 安装代价 | brew cask 150MB | mmdc npm | pip install |
| 渲染速度 | 慢（Electron）| 快 | 快 |
| **最佳场景** | **复杂架构 / 多图项目** | 简单流程图 | 数据可视化 |

## 10. Anti-prompt — 让 Claude 不要做的事

把下面这段拷给 Claude 避免走弯路：

```
- 不要把 Heiti SC 作为默认字体 — macOS 10.11+ 用 PingFang SC（更现代）
- 不要给大背景 box 加 sketch=1 — 会变 hatch 纹理盖前景
- 不要用默认 --width 渲染 PNG（800px 太糊）— 必须 --width 3200
- 不要在 mxCell value 里用裸 \n — 用 XML entity &#xa;
- 不要 ≤ 10 张图选 draw.io — 用 Mermaid 5min/张更快
- 不要 > 30 张图选 Mermaid — subgraph 配色控制弱、节点形状少
- 不要"先写文字 deck 再补图" — 图先行（图是骨架，文字嵌图周围）
- 不要 41 张图都 mermaid 但每张配色都靠 themeVariable — 必失败，直接 draw.io
- 不要边 edge 用纯坐标定起止 — 用 source/target ID 引用节点，节点移动边跟随
- 不要让 PingFang 长英文串撑爆 240px box — 240→270 加宽 + 留 spacing
```

## 11. 沉淀来源

2026-05-16 AGF 内部培训 deck v2.2 实战（commit `0bd917a`）：

| 类型 | 数量 | 工具 |
|---|---|---|
| A 流程 / 架构 | 17 | draw.io |
| B 概念 / 类比 | 6 | draw.io |
| C 矩阵 / 对照 | 5 | draw.io |
| D 关系 / 决策 | 4 | draw.io |
| F 数据可视化 | 3 | draw.io（静态）|
| G 卡片墙 | 6 | draw.io |
| **合计** | **41** | + 1 Mermaid 对比版 |

迭代记录：
1. 首张 A3 出 Mermaid + draw.io 双版本对比 → 用户选 draw.io
2. 11 张 ⭐⭐⭐ 单 task 完成 → 字号体系收敛（input 26pt / 节点 22pt / 描述 20pt）
3. 30 张 ⭐⭐ + 数据图 + 卡片墙批量产出
4. 字体 Heiti SC → PingFang SC 全局替换（用户反馈"字感奇怪"）
5. A3 长英文串换行修（240→270 box 宽）+ git commit

**产物**：`docs/training/diagrams/src/*.drawio` (41) + `docs/training/diagrams/png/*.png` (42, 含 1 mermaid 对比)
