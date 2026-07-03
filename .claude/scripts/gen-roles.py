#!/usr/bin/env python3
"""gen-roles.py — Agent 能力单一来源（roles.yaml）生成器。

SSOT 设计：docs/superpowers/specs/2026-06-15-agent-capability-yaml-ssot-design.md

把 19 个团队角色的能力数据收敛到 `.claude/agents/roles.yaml`，反向产出：
  1. 每个 `.claude/agents/<name>.md` 的 frontmatter（两个 `---` 围栏间，逐字节零 diff）
  2. `.claude/standards/team-roles.md` 的 Team Roles 表 + Agent Tools 表（marker 包裹）

三模式（spec §5.1）：
  gen-roles.py            默认 = write：渲染并写入三类产物的 owned region
  gen-roles.py --check    渲染到内存，与磁盘逐字节比对；有差异打 unified diff 并 exit 1
  gen-roles.py --extract  一次性迁移：从现有 19 个 .md + team-roles 两表反抽出 roles.yaml

退出码：0 = 一致 / 成功；1 = drift / schema 非法 / marker 缺失 / 其他错误。

依赖：Python 3 + PyYAML（lint-all.sh 已用），不引新依赖。
frontmatter **不**用裸 yaml.dump（会改引号/折行/顺序），见 §5.4 自定义确定性输出器。
"""

import argparse
import difflib
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - 环境缺 pyyaml
    sys.stderr.write("✗ 需要 PyYAML（python3 -c 'import yaml'）\n")
    sys.exit(1)

# ── 路径常量（相对仓库根；脚本位于 .claude/scripts/）──────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
AGENTS_DIR = os.path.join(REPO_ROOT, ".claude", "agents")
ROLES_YAML = os.path.join(AGENTS_DIR, "roles.yaml")
TEAM_ROLES_MD = os.path.join(REPO_ROOT, ".claude", "standards", "team-roles.md")

# ── 枚举（spec §4 / §5.3）─────────────────────────────────────────────────
# 取值源自官方 sub-agent frontmatter（https://code.claude.com/docs/en/sub-agents
# #supported-frontmatter-fields，核验日 2026-06-23）；官方扩充取值时同步此处，勿漂移。
MODEL_ENUM = {"opus", "sonnet", "haiku", "fable"}
PERMISSION_ENUM = {"acceptEdits", "auto", "default", "dontAsk", "plan", "bypassPermissions"}
COLOR_ENUM = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
BOUNDARY_KINDS = {"review-only", "test-only", "deploy-only"}
# `extra` 通道只承载官方支持、位于 frontmatter `color` 与 `tools` 之间的 passthrough 标量，
# 防 AGF 私有 / 拼错字段污染进生成的 frontmatter（Claude Code 忽略未知字段 → 静默失效）。
EXTRA_ALLOWED = {"permissionMode", "memory", "maxTurns", "background", "effort", "isolation"}

# 通用工具底座（spec §4 base_tools；与 team-roles.md「通用工具底座」一致）
DEFAULT_BASE_TOOLS = [
    "Glob", "Grep", "Read", "Write", "Edit", "Bash",
    "SendMessage", "TaskGet", "TaskUpdate", "TaskList", "Skill",
]

# frontmatter 字段输出顺序（spec §4 零 diff 契约）：
#   name → description → model → color → [extra...] → tools → [mcpServers] → skills
# `extra` 是对 spec §4 的忠实扩展：承载 spec 未枚举但现状存在的 passthrough 标量字段
# （当前仅 product-lead 的 permissionMode / memory，位于 color 与 tools 之间），保零 diff。

# Agent Tools 表里「工具调整」delta 渲染时，mcp 通配也算 added（既不在 base_tools）。


# ════════════════════════════════════════════════════════════════════════
#  frontmatter 解析（--extract 用）
# ════════════════════════════════════════════════════════════════════════
def split_frontmatter(text):
    """把 .md 文本拆成 (frontmatter_lines, body_text)。

    frontmatter = 文件开头两个 `---` 行之间的内容（不含围栏行本身）。
    body_text   = 第二个 `---` 行（含）之后的所有原文（用于 write 时回拼）。
    """
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise ValueError("frontmatter 必须以 '---' 开头")
    end = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end = i
            break
    if end is None:
        raise ValueError("frontmatter 缺少第二个 '---' 围栏")
    fm_lines = lines[1:end]
    # body 含第二个围栏行起的全部内容
    body = "\n".join(lines[end:])
    return fm_lines, body


def parse_frontmatter_fields(fm_lines):
    """把 frontmatter 行解析为有序字段 dict（保留出现顺序）。

    只识别两种形态（现状全覆盖）：
      key: scalar              （单行标量，含 description 的长中文）
      key:\n  - item\n  - item （块列表，仅 skills / tools 不走这条——tools 是 inline）
    skills 块列表项可能是 `  - name` 或 `  - { name: x, note: "y" }`。
    返回 list[(key, value)] 保序；value 对块列表是 list。
    """
    fields = []
    i = 0
    n = len(fm_lines)
    while i < n:
        ln = fm_lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith(" "):
            raise ValueError(f"意外的缩进行（无对应 key）：{ln!r}")
        if ":" not in ln:
            raise ValueError(f"无法解析 frontmatter 行：{ln!r}")
        key, rest = ln.split(":", 1)
        key = key.strip()
        rest = rest.rstrip("\n")
        # 块列表？下一行以 '  - ' 开头且本行冒号后为空
        if rest.strip() == "" and (i + 1 < n) and fm_lines[i + 1].lstrip().startswith("- "):
            items = []
            i += 1
            while i < n and fm_lines[i].lstrip().startswith("- "):
                item_raw = fm_lines[i].lstrip()[2:]  # 去掉 '- '
                items.append(item_raw)
                i += 1
            fields.append((key, ("list", items)))
            continue
        # 单行标量（去前导空格，保留原文其余）
        fields.append((key, ("scalar", rest.lstrip())))
        i += 1
    return fields


def _parse_skill_item(raw):
    """把 frontmatter skills 块列表的一项解析为 str 或 {name, note}。

    frontmatter 现状里 skills 项只有裸 name（无 note），故这里恒返回 str。
    （note 是 team-roles 表侧数据，--extract 时从那边补，不在 frontmatter。）
    """
    raw = raw.strip()
    if raw.startswith("{"):
        # 容错：万一未来 frontmatter 出现 inline map
        parsed = yaml.safe_load(raw)
        if isinstance(parsed, dict) and "name" in parsed:
            return parsed
    return raw


def extract_agent_from_md(path):
    """从单个 .md 反抽出 roles.yaml 形态的 agent dict（frontmatter 维度）。

    team-roles 表侧字段（role_title / pool / permission / focus / tools_note /
    skills note / boundary）不在 frontmatter，--extract 由调用方从 team-roles 表补。
    """
    text = open(path, encoding="utf-8").read()
    fm_lines, _ = split_frontmatter(text)
    fields = parse_frontmatter_fields(fm_lines)
    agent = {}
    extra = []  # 保序 passthrough（color 与 tools 之间的非标准字段）
    known_scalar = {"name", "description", "model", "color", "mcpServers"}
    seen_tools = False
    for key, (kind, val) in fields:
        if key == "tools" and kind == "scalar":
            agent["tools"] = [t.strip() for t in val.split(",") if t.strip()]
            seen_tools = True
        elif key == "skills" and kind == "list":
            agent["skills"] = [_parse_skill_item(x) for x in val]
        elif key in known_scalar and kind == "scalar":
            agent[key] = val
        else:
            # 未知 passthrough 标量（如 permissionMode / memory）。
            # 位置：在 tools 之前 → 进 extra；理论上不会在 tools 之后出现。
            if kind != "scalar":
                raise ValueError(f"未知块字段 {key!r}（暂不支持）")
            if not seen_tools:
                extra.append((key, val))
            else:
                raise ValueError(f"tools 之后出现未知字段 {key!r}，超出输出器契约")
    if extra:
        agent["extra"] = extra
    return agent


# ════════════════════════════════════════════════════════════════════════
#  frontmatter 渲染（spec §5.4 零 diff 输出器）— 最大风险点
# ════════════════════════════════════════════════════════════════════════
def _skill_name(item):
    """skills 项 → name（item 可为 str 或 {name, note}）。"""
    if isinstance(item, dict):
        return item["name"]
    return item


def render_frontmatter(agent):
    """渲染单个 agent 的 frontmatter 块（含两个 `---` 围栏 + 末尾换行）。

    字段顺序（spec §4）：name → description → model → color → [extra] → tools
      → [mcpServers] → skills。
    - description：不加引号的单行 scalar（原样）。
    - tools：inline 逗号列表 `Glob, Grep, ...`（保零 diff，逐字原样列表）。
    - mcpServers：仅非空才输出该行。
    - skills：`  - name` 块列表（仅 name，frontmatter 不带 note）。
    返回字符串以 `---\n` 起、`---\n` 收尾（不含围栏后正文）。
    """
    out = []
    out.append("---")
    out.append(f"name: {agent['name']}")
    out.append(f"description: {agent['description']}")
    out.append(f"model: {agent['model']}")
    out.append(f"color: {agent['color']}")
    for key, val in agent.get("extra", []):
        out.append(f"{key}: {val}")
    out.append("tools: " + ", ".join(agent["tools"]))
    mcp = agent.get("mcpServers")
    if mcp:
        out.append(f"mcpServers: {mcp}")
    out.append("skills:")
    for item in agent["skills"]:
        out.append(f"  - {_skill_name(item)}")
    out.append("---")
    return "\n".join(out) + "\n"


def render_agent_md(agent, body):
    """frontmatter 渲染 + 原正文回拼。body 是 split_frontmatter 的第二段
    （从第二个 `---` 行起）。渲染 frontmatter 以闭合围栏 `---\n` 收尾，正文也以
    `---` 开头，故拼接时去掉渲染端的闭合围栏行，避免双围栏 / 多空行。"""
    fm = render_frontmatter(agent)  # 形如 "...skills...\n---\n"
    # 去掉末尾的闭合围栏行 "\n---\n"，留 "...skills...\n"；body 自带开头 "---"。
    fm_no_close = fm.rsplit("\n---\n", 1)[0] + "\n"
    return fm_no_close + body


# ════════════════════════════════════════════════════════════════════════
#  roles.yaml 加载 + schema 校验（spec §5.3）
# ════════════════════════════════════════════════════════════════════════
class SchemaError(Exception):
    pass


def load_roles_yaml(path=ROLES_YAML):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SchemaError("roles.yaml 顶层必须是 mapping")
    return data


def _is_valid_tool(t):
    """工具名格式合法？已知非空 token，或 mcp__*__* 通配。"""
    if not isinstance(t, str) or not t.strip():
        return False
    if t.startswith("mcp__"):
        return t.count("__") >= 2  # mcp__server__tool 或 mcp__server__*
    return True


def validate_schema(data, agents_dir=AGENTS_DIR, check_file_set=True):
    """校验 roles.yaml，任一失败 raise SchemaError（spec §5.3 五条）。"""
    base_tools = data.get("base_tools")
    if not isinstance(base_tools, list) or not base_tools:
        raise SchemaError("base_tools 必须是非空列表")
    agents = data.get("agents")
    if not isinstance(agents, list) or not agents:
        raise SchemaError("agents 必须是非空列表")

    required = ["name", "role_title", "model", "color", "description",
                "tools", "skills", "pool", "permission", "focus"]
    names = []
    for idx, a in enumerate(agents):
        if not isinstance(a, dict):
            raise SchemaError(f"agents[{idx}] 必须是 mapping")
        nm = a.get("name", f"<idx {idx}>")
        # 1. 必填字段齐全
        for r in required:
            if r not in a or a[r] in (None, ""):
                raise SchemaError(f"agent {nm!r} 缺必填字段 {r!r}")
        # model 枚举
        if a["model"] not in MODEL_ENUM:
            raise SchemaError(f"agent {nm!r} 非法 model {a['model']!r}（须 ∈ {sorted(MODEL_ENUM)}）")
        # permission 枚举
        if a["permission"] not in PERMISSION_ENUM:
            raise SchemaError(
                f"agent {nm!r} 非法 permission {a['permission']!r}（须 ∈ {sorted(PERMISSION_ENUM)}）")
        # color 枚举（官方仅 8 值；越界时 Claude Code 回退默认色，属 schema 违规）
        if a["color"] not in COLOR_ENUM:
            raise SchemaError(
                f"agent {nm!r} 非法 color {a['color']!r}（官方仅支持 {sorted(COLOR_ENUM)}）")
        # extra passthrough 白名单（只许官方 frontmatter 字段进生成物，防私有字段污染）
        for ek, _ev in (a.get("extra") or []):
            if ek not in EXTRA_ALLOWED:
                raise SchemaError(
                    f"agent {nm!r} extra 含非官方 frontmatter 字段 {ek!r}"
                    f"（只许 {sorted(EXTRA_ALLOWED)} 进 frontmatter）")
        # pool.limit ≥ 1
        pool = a["pool"]
        if not isinstance(pool, dict) or "limit" not in pool:
            raise SchemaError(f"agent {nm!r} pool 须含 limit")
        if not isinstance(pool["limit"], int) or pool["limit"] < 1:
            raise SchemaError(f"agent {nm!r} pool.limit 须为 ≥1 的整数")
        # 2. tools 每项格式合法
        if not isinstance(a["tools"], list) or not a["tools"]:
            raise SchemaError(f"agent {nm!r} tools 须为非空列表")
        for t in a["tools"]:
            if not _is_valid_tool(t):
                raise SchemaError(f"agent {nm!r} 非法工具名 {t!r}")
        # 3. skills 每项 name 非空
        if not isinstance(a["skills"], list):
            raise SchemaError(f"agent {nm!r} skills 须为列表")
        for s in a["skills"]:
            nm_s = _skill_name(s) if isinstance(s, (str, dict)) else None
            if not nm_s or not isinstance(nm_s, str):
                raise SchemaError(f"agent {nm!r} skills 项 name 非法：{s!r}")
        # 4. boundary↔tools 一致：review-only ⟹ Edit ∉ tools
        boundary = a.get("boundary")
        if boundary is not None:
            if not isinstance(boundary, dict) or "kind" not in boundary:
                raise SchemaError(f"agent {nm!r} boundary 须含 kind")
            if boundary["kind"] not in BOUNDARY_KINDS:
                raise SchemaError(
                    f"agent {nm!r} 非法 boundary.kind {boundary['kind']!r}")
            if boundary["kind"] == "review-only" and "Edit" in a["tools"]:
                raise SchemaError(
                    f"agent {nm!r} 声明 review-only 却带 Edit（boundary↔tools 冲突）")
        names.append(a["name"])
    # 5. name 唯一
    if len(names) != len(set(names)):
        dups = sorted({x for x in names if names.count(x) > 1})
        raise SchemaError(f"name 重复：{dups}")
    # 5. agent 数与 .claude/agents/*.md 文件集合一致
    if check_file_set:
        md_names = {
            os.path.splitext(f)[0]
            for f in os.listdir(agents_dir)
            if f.endswith(".md")
        }
        yaml_names = set(names)
        missing = md_names - yaml_names
        extra = yaml_names - md_names
        if missing or extra:
            raise SchemaError(
                f"roles.yaml 与 agents/*.md 文件集合不一致："
                f"漏角色={sorted(missing)} 多余条目={sorted(extra)}")


# ════════════════════════════════════════════════════════════════════════
#  team-roles 两表渲染（spec §5.2 / §6）
# ════════════════════════════════════════════════════════════════════════
def render_team_roles_table(data):
    """Team Roles 表：Role | Agent Name | Model | Color | Permission | Pool 上限 | Focus。"""
    rows = [
        "| Role | Agent Name | Model | Color | Permission | Pool 上限 | Focus |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in data["agents"]:
        pool = a["pool"]
        pool_cell = f"**{pool['limit']}**"
        note = pool.get("note")
        if note:
            pool_cell += f"（{note}）"
        rows.append(
            f"| {a['role_title']} | `{a['name']}` | {a['model']} | {a['color']} "
            f"| {a['permission']} | {pool_cell} | {a['focus']} |"
        )
    return "\n".join(rows)


def _tools_delta_cell(agent, base_tools):
    """Agent Tools 表「工具调整」单元格（spec §5.2）。"""
    tools = agent["tools"]
    removed = [t for t in base_tools if t not in tools]
    added = [t for t in tools if t not in base_tools]
    parts = []
    for t in removed:
        parts.append(f"− `{t}`")
    for t in added:
        parts.append(f"+ `{t}`")
    delta = ", ".join(parts) if parts else "（仅通用底座）"
    note = agent.get("tools_note")
    if note:
        # tools_note 紧跟 delta 追加（note 自身含措辞/分隔，保留迁移原文）。
        # 无 delta 时（如 qa-engineer 白名单全靠 note 表达）单元格 = note。
        return (delta + note) if parts else note
    return delta


def _skill_cell(item):
    """Agent Tools 表 Plugin Skills 项：`name`（+「（note）」若有），name 用反引号。"""
    if isinstance(item, dict):
        name = item["name"]
        note = item.get("note")
        if note:
            return f"`{name}`（{note}）"
        return f"`{name}`"
    return f"`{item}`"


def render_agent_tools_table(data):
    """Agent Tools 表：Agent | 工具调整 | Plugin Skills（启动时预加载）。"""
    base_tools = data["base_tools"]
    rows = [
        "| Agent | 工具调整 | Plugin Skills（启动时预加载） |",
        "|---|---|---|",
    ]
    for a in data["agents"]:
        delta = _tools_delta_cell(a, base_tools)
        skills_cell = ", ".join(_skill_cell(s) for s in a["skills"])
        rows.append(f"| `{a['name']}` | {delta} | {skills_cell} |")
    return "\n".join(rows)


# ════════════════════════════════════════════════════════════════════════
#  marker 注入（spec §6）
# ════════════════════════════════════════════════════════════════════════
def marker_pair(name):
    return (
        f"<!-- BEGIN GENERATED:{name} -->",
        f"<!-- END GENERATED:{name} -->",
    )


def replace_marker_region(text, marker_name, new_content):
    """替换 `<!-- BEGIN GENERATED:name -->` … `<!-- END GENERATED:name -->`
    之间的内容为 new_content（marker 行保留，content 前后各一空行）。
    marker 对缺失 → raise ValueError（spec §6 防静默漏写）。"""
    begin, end = marker_pair(marker_name)
    bi = text.find(begin)
    ei = text.find(end)
    if bi == -1 or ei == -1:
        raise ValueError(f"marker 缺失：{marker_name}（找不到 BEGIN/END 对）")
    if ei < bi:
        raise ValueError(f"marker 顺序错误：{marker_name} 的 END 在 BEGIN 之前")
    # 保留 BEGIN 行本身：找 BEGIN 行末
    begin_line_end = text.find("\n", bi)
    if begin_line_end == -1:
        raise ValueError(f"marker {marker_name} BEGIN 行不完整")
    head = text[: begin_line_end + 1]      # 含 BEGIN 行及其换行
    tail = text[ei:]                        # 从 END 行起
    return f"{head}\n{new_content}\n\n{tail}"


# ════════════════════════════════════════════════════════════════════════
#  write / --check 公共：渲染所有产物到 {path: 新内容}
# ════════════════════════════════════════════════════════════════════════
def render_all(data, agents_dir=AGENTS_DIR, team_roles_md=TEAM_ROLES_MD):
    """返回 {abs_path: new_text}。对 .md 保留原正文，仅替换 frontmatter；
    对 team-roles.md 替换两表 marker 区。"""
    out = {}
    by_name = {a["name"]: a for a in data["agents"]}
    for name, agent in by_name.items():
        md_path = os.path.join(agents_dir, f"{name}.md")
        original = open(md_path, encoding="utf-8").read()
        _, body = split_frontmatter(original)
        out[md_path] = render_agent_md(agent, body)
    # team-roles.md 两表
    tr_text = open(team_roles_md, encoding="utf-8").read()
    tr_text = replace_marker_region(tr_text, "team-roles-table",
                                    render_team_roles_table(data))
    tr_text = replace_marker_region(tr_text, "agent-tools-table",
                                    render_agent_tools_table(data))
    out[team_roles_md] = tr_text
    return out


# ════════════════════════════════════════════════════════════════════════
#  模式实现
# ════════════════════════════════════════════════════════════════════════
def mode_write(data):
    validate_schema(data)
    rendered = render_all(data)
    for path, text in rendered.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"✓ 已写入 {len(rendered)} 个产物")
    return 0


def mode_check(data):
    validate_schema(data)
    rendered = render_all(data)
    drift = False
    for path, new_text in sorted(rendered.items()):
        try:
            cur = open(path, encoding="utf-8").read()
        except FileNotFoundError:
            cur = ""
        if cur != new_text:
            drift = True
            rel = os.path.relpath(path, REPO_ROOT)
            sys.stderr.write(f"✗ roles drift: {rel} 与 roles.yaml 不一致\n")
            diff = difflib.unified_diff(
                cur.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{rel} (disk)",
                tofile=f"{rel} (from roles.yaml)",
            )
            sys.stderr.writelines(diff)
            sys.stderr.write("\n")
    if drift:
        sys.stderr.write(
            "  跑 `python3 .claude/scripts/gen-roles.py` 同步后再 commit\n")
        return 1
    print("✓ roles 一致（无 drift）")
    return 0


def mode_extract(agents_dir=AGENTS_DIR, team_roles_md=TEAM_ROLES_MD):
    """从 19 个 .md frontmatter + team-roles 两表反抽出 roles.yaml（spec §7）。

    frontmatter 提供：name / description / model / color / tools / mcpServers /
      skills（仅 name）/ extra。
    team-roles 两表提供：role_title / permission / pool / focus / tools_note /
      skills note。
    本函数尽量自动抽取；team-roles 单元格散文（note）由 PL 在迁移 PR 人工 review。
    输出 YAML 文本到 stdout（Task 2 据此落盘 roles.yaml）。
    """
    md_files = sorted(
        f for f in os.listdir(agents_dir) if f.endswith(".md") and f != "roles.yaml"
    )
    table = _parse_team_roles_tables(team_roles_md)
    agents = []
    for f in md_files:
        name = os.path.splitext(f)[0]
        agent = extract_agent_from_md(os.path.join(agents_dir, f))
        meta = table.get(name, {})
        merged = {
            "name": agent["name"],
            "role_title": meta.get("role_title", ""),
            "model": agent["model"],
            "color": agent["color"],
            "description": agent["description"],
            "tools": agent["tools"],
        }
        if meta.get("tools_note"):
            merged["tools_note"] = meta["tools_note"]
        if agent.get("mcpServers"):
            merged["mcpServers"] = agent["mcpServers"]
        if agent.get("extra"):
            merged["extra"] = agent["extra"]
        # skills：合并 frontmatter name 顺序 + team-roles note
        merged["skills"] = _merge_skills(agent["skills"], meta.get("skill_notes", {}))
        merged["pool"] = meta.get("pool", {"limit": 1, "note": ""})
        merged["permission"] = meta.get("permission", "acceptEdits")
        merged["focus"] = meta.get("focus", "")
        if meta.get("boundary"):
            merged["boundary"] = meta["boundary"]
        agents.append(merged)
    doc = {"base_tools": list(DEFAULT_BASE_TOOLS), "agents": agents}

    # extract 自检（spec §10 / 评审 #2）：team-roles 两表若缺 marker 或解析失败，
    # role_title / focus / pool / permission 等团队侧必填字段会带空兜底值，
    # 静默写出会在 Task 2 跑 --check 时炸出难懂的 diff。先在这里把它转成清晰的
    # extract-time 报错（列出每个角色哪些必填 cell 为空），不让人到下游才发现。
    empties = []
    for a in agents:
        missing = [
            k for k in ("role_title", "focus", "permission")
            if not a.get(k)
        ]
        pool = a.get("pool") or {}
        if not pool.get("note"):
            missing.append("pool.note")
        if missing:
            empties.append(f"{a['name']}: {', '.join(missing)}")
    if empties:
        detail = "\n  ".join(empties)
        raise SchemaError(
            "extract 抽出的 roles.yaml 有空的团队侧必填字段（多半是 team-roles 两表"
            "缺 marker 或未解析到）——补全后再落盘：\n  " + detail
        )
    # 结构性校验（不查文件集合：extract 阶段 roles.yaml 尚未落盘）
    validate_schema(doc, check_file_set=False)

    # 用 yaml.dump 仅用于 roles.yaml 本身（非 frontmatter；roles.yaml 不要求零 diff）
    sys.stdout.write(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=10**9)
    )
    return 0


def _merge_skills(fm_skills, skill_notes):
    """frontmatter skills（仅 name，定序）+ team-roles note → 双形态列表。"""
    out = []
    for s in fm_skills:
        nm = _skill_name(s)
        note = skill_notes.get(nm)
        if note:
            out.append({"name": nm, "note": note})
        else:
            out.append(nm)
    return out


def _parse_team_roles_tables(team_roles_md):
    """从 team-roles.md 解析两表 → {name: {role_title, model, color, permission,
    pool, focus, tools_note, skill_notes, boundary}}。

    迁移阶段：若两表尚未加 marker（Task 2 才插），本函数容错——找不到表就返回
    能解析到的部分，缺字段由 mode_extract 兜底默认值，PL 人工补。
    """
    result = {}
    try:
        text = open(team_roles_md, encoding="utf-8").read()
    except FileNotFoundError:
        return result
    lines = text.split("\n")
    # Team Roles 表：表头含 "Agent Name" 且含 "Pool 上限"
    for i, ln in enumerate(lines):
        if "Agent Name" in ln and "Pool 上限" in ln and ln.strip().startswith("|"):
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                cells = _split_md_row(row)
                if len(cells) < 7:
                    continue
                name = cells[1].strip().strip("`")
                limit, note = _parse_pool_cell(cells[5])
                result.setdefault(name, {})
                result[name].update({
                    "role_title": cells[0].strip(),
                    "model": cells[2].strip(),
                    "color": cells[3].strip(),
                    "permission": cells[4].strip(),
                    "pool": {"limit": limit, "note": note},
                    "focus": cells[6].strip(),
                })
            break
    # Agent Tools 表：表头含 "工具调整" 且含 "Plugin Skills"
    for i, ln in enumerate(lines):
        if "工具调整" in ln and "Plugin Skills" in ln and ln.strip().startswith("|"):
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                cells = _split_md_row(row)
                if len(cells) < 3:
                    continue
                name = cells[0].strip().strip("`")
                result.setdefault(name, {})
                # tools_note 故意不自动抽取——迁移时人工手填 roles.yaml（spec §7/§11）
                result[name]["tools_note"] = _tools_note_placeholder(cells[1])
                result[name]["skill_notes"] = _extract_skill_notes(cells[2])
            break
    return result


def _split_md_row(row):
    """拆 markdown 表行为单元格列表（去首尾空管道）。"""
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return s.split("|")


def _parse_pool_cell(cell):
    """`**5**（Small=3 / Med=5 / Large=7）` → (5, 'Small=3 / Med=5 / Large=7')。"""
    cell = cell.strip()
    num = ""
    rest = cell
    if "**" in cell:
        try:
            inner = cell.split("**")[1]
            num = "".join(ch for ch in inner if ch.isdigit())
            rest = cell.split("**", 2)[2] if cell.count("**") >= 2 else ""
        except IndexError:
            pass
    note = rest.strip()
    if note.startswith("（") and note.endswith("）"):
        note = note[1:-1]
    elif note.startswith("（"):
        note = note[1:].rstrip("）")
    limit = int(num) if num else 1
    return limit, note


def _tools_note_placeholder(_cell):
    """tools_note 占位符——**故意不自动抽取**（spec §7/§11）。

    工具调整单元格的散文尾巴（如 qa-engineer 的长白名单注解）由人工在迁移 PR
    手填进 roles.yaml：自动从 delta（+/−）里切散文易误伤，留空更安全。恒返回 ""，
    渲染端（_tools_delta_cell）在 roles.yaml 有 tools_note 时才追加。"""
    return ""


def _extract_skill_notes(cell):
    """从 Plugin Skills 单元格抽 {name: note}（`name`（note） 形态）。"""
    notes = {}
    # 拆分顶层逗号较脆（note 里可能含逗号/括号）；用简单状态机按 ` 包裹的 name 切。
    # 现状 note 不含反引号，故以 '`' 配对找 name，其后若紧跟「（…）」记为 note。
    i = 0
    s = cell
    while True:
        a = s.find("`", i)
        if a == -1:
            break
        b = s.find("`", a + 1)
        if b == -1:
            break
        name = s[a + 1:b]
        j = b + 1
        note = None
        # 跳过空白后若是中文左括号，截到匹配右括号
        while j < len(s) and s[j] == " ":
            j += 1
        if j < len(s) and s[j] == "（":
            depth = 0
            k = j
            while k < len(s):
                if s[k] == "（":
                    depth += 1
                elif s[k] == "）":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            note = s[j + 1:k]
            j = k + 1
        if note:
            notes[name] = note
        i = j
    return notes


# ════════════════════════════════════════════════════════════════════════
def main(argv=None):
    parser = argparse.ArgumentParser(description="roles.yaml 能力 SSOT 生成器")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true",
                   help="渲染到内存与磁盘逐字节比对；drift 则 exit 1")
    g.add_argument("--extract", action="store_true",
                   help="从现有 .md + team-roles 两表反抽 roles.yaml 到 stdout")
    args = parser.parse_args(argv)

    try:
        if args.extract:
            return mode_extract()
        data = load_roles_yaml()
        if args.check:
            return mode_check(data)
        return mode_write(data)
    except (SchemaError, ValueError) as e:
        sys.stderr.write(f"✗ {e}\n")
        return 1
    except FileNotFoundError as e:
        sys.stderr.write(f"✗ 文件缺失：{e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
