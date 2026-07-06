"""Industry chain deconstruct module for multi-method chain analysis.

This module implements four deconstruct methods for industry chain analysis:
1. bom: L1-L8 BOM-oriented layered tree and node paths
2. upstream_downstream: 5-layer tree (raw_material → component → manufacture → channel → terminal)
3. value_chain: margin/pricing_power/value_added per node
4. competition: concentration/leader_share/barrier/threat per node

PRD: docs/prd/supply-chain-reconstruct-2026-06-24.md §4.2
Migration: backend/alembic/versions/013_industry_chain_deconstruct.py
"""

from __future__ import annotations

from typing import Any


# Layer definitions for upstream_downstream view
LAYER_NAMES = {
    1: "原材料",
    2: "核心零部件",
    3: "制造",
    4: "渠道",
    5: "终端应用",
}

BOM_LAYER_NAMES = {
    "L1": "政策主题",
    "L2": "产业方向",
    "L3": "产业链",
    "L4": "环节",
    "L5": "BOM节点",
    "L6": "产品/技术路线",
    "L7": "公司业务分部",
    "L8": "证据事件",
}

DEFAULT_EVIDENCE_EVENTS = [
    "研发进展",
    "样机或小批量交付",
    "客户验证",
    "订单或中标",
    "产线建设或量产",
    "收入和毛利改善",
    "专利与标准",
]

BOM_COMPLETION_PROFILES: dict[str, dict[str, list[str] | str]] = {
    "量子科技": {
        "chain": "量子科技产业链",
        "segments": ["量子计算", "量子通信", "量子测量", "低温与控制系统"],
        "bom_nodes": ["量子芯片", "单光子探测器", "低温制冷设备", "测控系统", "量子随机数/密钥设备"],
        "technologies": ["超导量子", "光量子", "离子阱", "量子密钥分发", "量子精密测量"],
        "business_segments": ["量子计算设备业务", "量子通信设备业务", "量子测量仪器业务", "低温测控系统业务"],
    },
    "生物制造": {
        "chain": "生物制造产业链",
        "segments": ["底盘细胞/菌种", "酶制剂与发酵", "分离纯化", "生物基材料应用"],
        "bom_nodes": ["菌种库", "酶制剂", "发酵罐", "分离纯化设备", "生物基单体/材料"],
        "technologies": ["合成生物", "酶工程", "发酵工程", "代谢工程", "生物基材料"],
        "business_segments": ["合成生物平台业务", "酶制剂业务", "发酵工程业务", "生物基材料业务"],
    },
    "氢能和核聚变能": {
        "chain": "氢能和核聚变能产业链",
        "segments": ["制氢", "储运", "燃料电池", "聚变关键部件"],
        "bom_nodes": ["电解槽", "膜电极", "储氢瓶/储氢材料", "燃料电池系统", "超导磁体", "真空室/偏滤器"],
        "technologies": ["PEM/AEM电解槽", "液氢/固态储氢", "燃料电池", "高温超导", "托卡马克"],
        "business_segments": ["制氢装备业务", "储氢材料业务", "燃料电池系统业务", "聚变部件业务"],
    },
    "脑机接口": {
        "chain": "脑机接口产业链",
        "segments": ["信号采集", "植入/非植入设备", "算法解码", "医疗与康复应用"],
        "bom_nodes": ["神经电极", "脑电采集芯片", "植入式器械", "神经调控设备", "脑电算法平台"],
        "technologies": ["脑电EEG", "植入式电极", "神经调控", "脑信号解码", "康复外骨骼"],
        "business_segments": ["神经电极业务", "脑电采集设备业务", "神经调控设备业务", "康复应用业务"],
    },
    "具身智能": {
        "chain": "具身智能产业链",
        "segments": ["核心零部件", "运动控制", "整机制造", "场景集成"],
        "bom_nodes": ["减速器", "电机", "轴承", "控制器", "传感器", "执行器"],
        "technologies": ["谐波/RV减速", "空心杯/伺服电机", "力矩传感器", "运动控制", "人形机器人"],
        "business_segments": ["减速器业务", "电机业务", "控制器业务", "机器人整机业务"],
    },
    "第六代移动通信": {
        "chain": "第六代移动通信产业链",
        "segments": ["无线接入", "承载传输", "卫星互联网", "测试验证"],
        "bom_nodes": ["太赫兹器件", "毫米波射频", "基站天线", "高速光模块", "卫星载荷", "通信测试仪器"],
        "technologies": ["6G", "空天地一体", "通感一体", "太赫兹", "CPO/LPO光通信"],
        "business_segments": ["射频器件业务", "光通信模块业务", "卫星通信载荷业务", "通信测试设备业务"],
    },
    "AI算力": {
        "chain": "AI算力产业链",
        "segments": ["算力硬件", "基础软件", "网络互联", "行业应用"],
        "bom_nodes": ["AI芯片/GPU", "服务器", "高速交换机", "光模块", "液冷系统", "调度平台"],
        "technologies": ["GPU/ASIC", "HBM", "高速互联", "CPO/LPO", "液冷", "云边端推理"],
        "business_segments": ["AI芯片业务", "服务器与交换机业务", "光模块业务", "算力调度软件业务"],
    },
    "半导体": {
        "chain": "半导体产业链",
        "segments": ["材料", "设备", "制造", "封测", "设计"],
        "bom_nodes": ["硅片", "光刻胶", "刻蚀设备", "薄膜沉积设备", "封测设备", "EDA/IP"],
        "technologies": ["先进制程", "刻蚀/薄膜沉积", "先进封装", "Chiplet", "EDA"],
        "business_segments": ["半导体材料业务", "半导体设备业务", "晶圆制造业务", "封测/EDA业务"],
    },
    "华为韬定律": {
        "chain": "华为韬定律先进封装产业链",
        "segments": ["先进封测", "封测设备", "EDA工具", "封测材料", "光互连与PCB"],
        "bom_nodes": ["混合键合设备", "ALD/PECVD", "临时键合/解键合", "CMP设备", "3D IC EDA", "键合胶/抛光液", "玻璃基板/TGV", "800G/1.6T光模块", "高速PCB/IC载板"],
        "technologies": ["逻辑折叠(Logic Folding)", "Hybrid Bonding", "3D堆叠/Chiplet", "TSV/硅通孔", "CoWoS/XDFOI", "CPO/硅光集成", "mSAP/VPD高端PCB", "时间缩微(τ-缩微)"],
        "business_segments": ["先进封装业务", "半导体设备业务", "EDA软件业务", "半导体材料业务", "光模块业务", "高速PCB业务"],
    },
    "光通信": {
        "chain": "光通信产业链",
        "segments": ["光芯片", "光器件", "光模块", "CPO/硅光集成"],
        "bom_nodes": ["EML/DFB激光器", "探测器/PD", "高速光器件", "800G/1.6T光模块", "ELS/光源", "CPO引擎", "硅光集成芯片"],
        "technologies": ["800G/1.6T", "CPO/LPO", "硅光集成", "相干光通信", "波分复用", "高速DSP"],
        "business_segments": ["光芯片业务", "光器件业务", "光模块业务", "CPO/硅光业务"],
    },
    "存储芯片": {
        "chain": "存储芯片产业链",
        "segments": ["DRAM", "NAND Flash", "HBM", "存储封测"],
        "bom_nodes": ["DRAM颗粒", "NAND颗粒", "HBM堆叠", "存储主控芯片", "SSD模组", "内存模组"],
        "technologies": ["DDR5/LPDDR5", "3D NAND(200L+)", "HBM3/HBM4", "CXL内存", "存算一体"],
        "business_segments": ["DRAM业务", "NAND/SSD业务", "HBM业务", "存储封测业务"],
    },
    "华为终端": {
        "chain": "华为终端产业链",
        "segments": ["麒麟芯片", "终端组装", "核心零部件", "鸿蒙生态"],
        "bom_nodes": ["麒麟2026 SoC", "折叠屏/铰链", "射频前端模组", "摄像头模组", "电池/电源管理", "鸿蒙系统"],
        "technologies": ["逻辑折叠芯片", "折叠屏UTG", "卫星通信", "星闪NearLink", "鸿蒙原生应用"],
        "business_segments": ["麒麟芯片业务", "终端组装业务", "核心零部件业务", "鸿蒙生态业务"],
    },
    "EDA工业软件": {
        "chain": "EDA工业软件产业链",
        "segments": ["全流程EDA", "点工具EDA", "仿真验证", "IP核"],
        "bom_nodes": ["全流程EDA平台", "版图设计工具", "电路仿真工具", "3D IC仿真", "接口IP核", "DFM/OPC工具"],
        "technologies": ["全流程EDA", "3D IC设计", "多物理场仿真", "AI驱动EDA", "国产IP核"],
        "business_segments": ["全流程EDA业务", "点工具EDA业务", "仿真验证业务", "IP授权业务"],
    },

    "半导体设备材料": {
        "chain": "半导体设备材料产业链",
        "segments": ["核心材料", "关键设备", "基础软件", "国产替代验证"],
        "bom_nodes": ["光刻胶", "靶材", "硅片", "刻蚀设备", "薄膜沉积设备", "EDA"],
        "technologies": ["ArF/KrF光刻胶", "PVD/CVD/ALD", "刻蚀", "CMP", "EDA工具链"],
        "business_segments": ["光刻胶业务", "半导体设备业务", "靶材/硅片业务", "EDA软件业务"],
    },
    "工业软件": {
        "chain": "工业软件产业链",
        "segments": ["研发设计", "生产制造", "运维管理", "基础软件"],
        "bom_nodes": ["CAD", "CAE", "MES", "PLM", "工业操作系统", "工业数据平台"],
        "technologies": ["CAD/CAE", "MES/PLM", "工业互联网", "数字孪生", "国产基础软件"],
        "business_segments": ["研发设计软件业务", "生产制造软件业务", "工业数据平台业务", "基础软件业务"],
    },
    "新能源": {
        "chain": "新能源产业链",
        "segments": ["材料", "光伏", "电池", "设备"],
        "bom_nodes": ["硅料/硅片", "电池片/组件", "逆变器", "储能电芯", "锂电材料", "电池设备"],
        "technologies": ["TOPCon/HJT", "钙钛矿", "大储/工商业储能", "固态电池", "快充"],
        "business_segments": ["光伏材料业务", "光伏组件业务", "储能电池业务", "新能源设备业务"],
    },
    "新能源车": {
        "chain": "新能源车产业链",
        "segments": ["材料", "动力电池", "核心零部件", "整车平台"],
        "bom_nodes": ["动力电池", "电驱/电控", "热管理", "智能座舱", "线控底盘", "整车平台"],
        "technologies": ["高压快充", "固态电池", "智能驾驶", "一体化压铸", "线控底盘"],
        "business_segments": ["动力电池业务", "电驱电控业务", "智能座舱业务", "整车平台业务"],
    },
    "机器人": {
        "chain": "机器人产业链",
        "segments": ["核心零部件", "运动控制", "整机", "系统集成"],
        "bom_nodes": ["减速器", "伺服电机", "控制器", "传感器", "执行器", "整机"],
        "technologies": ["谐波/RV减速", "空心杯", "力矩传感器", "运动控制", "人形机器人"],
        "business_segments": ["机器人减速器业务", "伺服电机业务", "控制器业务", "机器人整机业务"],
    },
    "高端制造": {
        "chain": "高端制造产业链",
        "segments": ["核心部件", "整机装备", "系统集成", "高端工艺"],
        "bom_nodes": ["数控系统", "伺服系统", "高端机床", "工业母机", "自动化产线"],
        "technologies": ["精密加工", "智能制造", "工业母机", "柔性产线", "数字化工厂"],
        "business_segments": ["核心部件业务", "高端装备业务", "系统集成业务", "智能制造业务"],
    },
    "国防军工": {
        "chain": "国防军工产业链",
        "segments": ["主机厂", "分系统", "元器件", "材料"],
        "bom_nodes": ["航空发动机", "雷达/电子对抗", "惯导", "军用连接器", "高温合金/复材"],
        "technologies": ["型号批产", "军贸", "高可靠元器件", "隐身材料", "导航制导"],
        "business_segments": ["主机配套业务", "军工电子业务", "高可靠元器件业务", "军工材料业务"],
    },
    "创新药": {
        "chain": "创新药产业链",
        "segments": ["靶点发现", "CXO", "原料药", "临床与商业化"],
        "bom_nodes": ["靶点平台", "临床前服务", "CRO/CDMO", "特色原料药", "创新药管线"],
        "technologies": ["IND", "临床I/II/III期", "NDA", "License-out", "商业化放量"],
        "business_segments": ["创新药管线业务", "CXO业务", "原料药业务", "商业化销售业务"],
    },
    "消费升级": {
        "chain": "消费升级产业链",
        "segments": ["品牌", "渠道", "供应链", "会员运营"],
        "bom_nodes": ["智能终端", "健康消费", "国潮品牌", "新零售渠道", "供应链数字化"],
        "technologies": ["DTC", "会员运营", "渠道数字化", "柔性供应链"],
        "business_segments": ["品牌业务", "渠道运营业务", "供应链服务业务", "会员运营业务"],
    },
    "周期资源": {
        "chain": "周期资源产业链",
        "segments": ["资源", "冶炼", "加工", "回收"],
        "bom_nodes": ["锂/铜/铝/稀土资源", "冶炼产能", "高纯金属", "高端合金", "材料回收"],
        "technologies": ["资源勘探", "选矿冶炼", "高纯制备", "高端加工", "循环回收"],
        "business_segments": ["资源开采业务", "冶炼业务", "深加工材料业务", "回收业务"],
    },
}


def _to_float(value: Any, default: float | None = None) -> float | None:
    """Convert value to float with fallback."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_tree_node(
    node: dict[str, Any],
    all_nodes: list[dict[str, Any]],
    include_children: bool = True,
) -> dict[str, Any]:
    """Build a tree node with recursive children."""
    result = {
        "node_id": node.get("node_id"),
        "name": node.get("node_name"),
        "layer": node.get("layer"),
    }

    if include_children:
        children = [
            n for n in all_nodes
            if n.get("parent_node_id") == node.get("node_id")
        ]
        if children:
            result["children"] = [
                _build_tree_node(child, all_nodes, include_children=True)
                for child in sorted(children, key=lambda x: x.get("layer", 0))
            ]

    return result


def build_upstream_downstream_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build 5-layer upstream_downstream tree structure.

    Args:
        nodes: List of chain_nodes records with node_id, node_name, layer, parent_node_id,
               upstream_nodes, downstream_nodes

    Returns:
        Tree structure with root and 5-layer children:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [
                {"node_id": "...", "name": "原材料", "layer": 1, "children": [...]},
                {"node_id": "...", "name": "核心零部件", "layer": 2, "children": [...]},
                ...
            ]
        }
    """
    if not nodes:
        return {"node_id": "root", "name": "空产业链", "children": []}

    # 去重: 同一 node_id 只保留第一次出现
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for n in nodes:
        nid = str(n.get("node_id") or "")
        if nid and nid not in seen:
            seen.add(nid)
            deduped.append(n)

    # 推断 parent_node_id: 如果子节点的 node_id = "{chain_slug}_{layer_slug}"，
    # 且存在 node_id = "chain_{chain_slug}" 的节点，则自动建立父子关系
    for n in deduped:
        nid = str(n.get("node_id") or "")
        if n.get("parent_node_id") or nid.startswith("chain_"):
            continue
        # 尝试找父链节点: 从 node_id 中提取 chain_slug
        parts = nid.split("_", 1)
        if len(parts) >= 2:
            chain_nid = "chain_" + parts[0]
            # 检查是否存在这个父节点
            if any(d["node_id"] == chain_nid for d in deduped):
                n["parent_node_id"] = chain_nid

    # Find root nodes (no parent_node_id)
    root_nodes = [n for n in deduped if not n.get("parent_node_id")]

    if not root_nodes:
        min_layer = min(n.get("layer", 1) for n in deduped)
        root_nodes = [n for n in deduped if n.get("layer") == min_layer]

    # Build tree from root nodes
    children = [
        _build_tree_node(root, nodes, include_children=True)
        for root in sorted(root_nodes, key=lambda x: x.get("layer", 0))
    ]

    # Group by layer for clearer structure
    theme_name = nodes[0].get("theme_id", "产业链") if nodes else "产业链"

    return {
        "node_id": "root",
        "name": theme_name,
        "children": children,
    }


def _bom_layer_key(layer: Any) -> str:
    """Map source layer values into the V2 L1-L8 display buckets."""
    try:
        layer_num = int(layer)
    except (TypeError, ValueError):
        layer_num = 8
    layer_num = min(8, max(1, layer_num))
    return f"L{layer_num}"


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None and str(item)]
    return [str(value)]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _node_name(node: dict[str, Any]) -> str:
    return str(node.get("node_name") or node.get("name") or node.get("node_id") or "")


def _profile_for_node(node: dict[str, Any]) -> dict[str, list[str] | str]:
    name = _node_name(node)
    lookup_keys = [
        str(node.get("node_id") or ""),
        str(node.get("chain_id") or ""),
        name,
    ]
    for key in lookup_keys:
        if key in BOM_COMPLETION_PROFILES:
            return BOM_COMPLETION_PROFILES[key]
    for profile_key, profile in BOM_COMPLETION_PROFILES.items():
        if profile_key and (profile_key in name or name in profile_key):
            return profile
    return {}


def _generic_segments(name: str) -> list[str]:
    return [f"{name}核心材料", f"{name}关键设备", f"{name}系统集成", f"{name}应用场景"]


def _generic_bom_nodes(name: str, children: list[dict[str, Any]], keywords: list[str]) -> list[str]:
    child_names = [_node_name(child) for child in children]
    if child_names:
        return _unique(child_names)
    if keywords:
        return _unique(keywords[:6])
    return [f"{name}核心部件", f"{name}专用设备", f"{name}关键材料"]


def _make_layer_item(
    *,
    layer: str,
    name: str,
    node_id: str,
    parent_node_id: str | None = None,
    source_node_id: str | None = None,
    keywords: list[str] | None = None,
    source_status: str = "derived",
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "name": name,
        "layer": layer,
        "layer_name": BOM_LAYER_NAMES[layer],
        "parent_node_id": parent_node_id,
        "source_node_id": source_node_id,
        "source_status": source_status,
        "keywords": keywords or [],
    }


def _add_layer_items(
    bom_layers: dict[str, list[dict[str, Any]]],
    layer: str,
    names: list[str],
    *,
    parent_node_id: str | None,
    source_node_id: str,
    source_status: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, name in enumerate(_unique(names), start=1):
        item = _make_layer_item(
            layer=layer,
            name=name,
            node_id=f"{source_node_id}:{layer}:{index}",
            parent_node_id=parent_node_id,
            source_node_id=source_node_id,
            keywords=[name],
            source_status=source_status,
        )
        bom_layers[layer].append(item)
        items.append(item)
    return items


def _semantic_bom_layers(
    nodes: list[dict[str, Any]],
    tree: dict[str, Any],
    theme_name: str | None = None,
    theme_id: str | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]], dict[str, str]]:
    layer_keys = [f"L{i}" for i in range(1, 9)]
    bom_layers: dict[str, list[dict[str, Any]]] = {key: [] for key in layer_keys}
    bom_table: list[dict[str, str]] = []
    layer_definitions = {key: BOM_LAYER_NAMES[key] for key in layer_keys}

    if not nodes:
        return bom_layers, bom_table, layer_definitions

    theme_label = theme_name or str(tree.get("name") or nodes[0].get("theme_id") or "产业主题")
    theme_source_id = theme_id or str(nodes[0].get("theme_id") or "policy_theme")
    policy_item = _make_layer_item(
        layer="L1",
        name=theme_label,
        node_id=f"policy:{theme_source_id}",
        source_node_id=theme_source_id,
        keywords=[theme_label],
        source_status="policy_theme",
    )
    bom_layers["L1"].append(policy_item)

    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        parent_id = node.get("parent_node_id")
        if parent_id:
            children_by_parent.setdefault(str(parent_id), []).append(node)
    root_nodes = [node for node in nodes if not node.get("parent_node_id")]
    if not root_nodes:
        min_layer = min(node.get("layer", 1) for node in nodes)
        root_nodes = [node for node in nodes if node.get("layer") == min_layer]

    for root in sorted(root_nodes, key=lambda item: (item.get("layer", 0), _node_name(item))):
        source_node_id = str(root.get("node_id") or _node_name(root))
        direction_name = _node_name(root)
        children = children_by_parent.get(source_node_id, [])
        keywords = _unique(_as_list(root.get("keywords")))
        profile = _profile_for_node(root)

        chain_name = str(profile.get("chain") or f"{direction_name}产业链")
        segment_names = _unique(_as_list(profile.get("segments")) or [_node_name(child) for child in children] or _generic_segments(direction_name))
        bom_node_names = _unique(_as_list(profile.get("bom_nodes")) or _generic_bom_nodes(direction_name, children, keywords))
        technology_names = _unique([*_as_list(profile.get("technologies")), *keywords] or bom_node_names)
        business_segments = _unique(
            _as_list(profile.get("business_segments"))
            or [f"{name}业务" for name in bom_node_names[:4]]
            or [f"{direction_name}业务"]
        )
        evidence_events = _unique(_as_list(profile.get("evidence_events")) or DEFAULT_EVIDENCE_EVENTS)

        direction_item = _make_layer_item(
            layer="L2",
            name=direction_name,
            node_id=f"{source_node_id}:L2",
            parent_node_id=policy_item["node_id"],
            source_node_id=source_node_id,
            keywords=keywords,
            source_status="source_node",
        )
        bom_layers["L2"].append(direction_item)

        chain_item = _make_layer_item(
            layer="L3",
            name=chain_name,
            node_id=f"{source_node_id}:L3",
            parent_node_id=direction_item["node_id"],
            source_node_id=source_node_id,
            keywords=[chain_name],
            source_status="derived_chain",
        )
        bom_layers["L3"].append(chain_item)

        segment_items = _add_layer_items(
            bom_layers,
            "L4",
            segment_names,
            parent_node_id=chain_item["node_id"],
            source_node_id=source_node_id,
            source_status="derived_segment",
        )
        bom_node_items = _add_layer_items(
            bom_layers,
            "L5",
            bom_node_names,
            parent_node_id=segment_items[0]["node_id"] if segment_items else chain_item["node_id"],
            source_node_id=source_node_id,
            source_status="derived_bom_node",
        )
        technology_items = _add_layer_items(
            bom_layers,
            "L6",
            technology_names,
            parent_node_id=bom_node_items[0]["node_id"] if bom_node_items else chain_item["node_id"],
            source_node_id=source_node_id,
            source_status="derived_technology",
        )
        business_items = _add_layer_items(
            bom_layers,
            "L7",
            business_segments,
            parent_node_id=technology_items[0]["node_id"] if technology_items else chain_item["node_id"],
            source_node_id=source_node_id,
            source_status="business_segment_template",
        )
        _add_layer_items(
            bom_layers,
            "L8",
            evidence_events,
            parent_node_id=business_items[0]["node_id"] if business_items else chain_item["node_id"],
            source_node_id=source_node_id,
            source_status="evidence_event_type",
        )

        bom_table.append({
            "L1": theme_label,
            "L2": direction_name,
            "L3": chain_name,
            "L4": "、".join(segment_names),
            "L5": "、".join(bom_node_names),
            "L6": "、".join(technology_names),
            "L7": "、".join(business_segments),
            "L8": "、".join(evidence_events),
        })

    return bom_layers, bom_table, layer_definitions


def _collect_bom_paths(node: dict[str, Any], path: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    current = {
        "node_id": node.get("node_id"),
        "name": node.get("name"),
        "layer": node.get("layer"),
    }
    next_path = [*path, current]
    children = node.get("children") or []
    if not children:
        return [next_path]
    paths: list[list[dict[str, Any]]] = []
    for child in children:
        paths.extend(_collect_bom_paths(child, next_path))
    return paths


def build_bom_tree(
    nodes: list[dict[str, Any]],
    theme_name: str | None = None,
    theme_id: str | None = None,
) -> dict[str, Any]:
    """Build V2 BOM view with L1-L8 layer buckets and leaf paths."""
    layer_keys = [f"L{i}" for i in range(1, 9)]
    bom_layers: dict[str, list[dict[str, Any]]] = {key: [] for key in layer_keys}
    if not nodes:
        return {
            "node_id": "root",
            "name": "空产业链",
            "children": [],
            "bom_layers": bom_layers,
            "bom_paths": [],
            "bom_table": [],
            "layer_definitions": {key: BOM_LAYER_NAMES[key] for key in layer_keys},
        }

    tree = build_upstream_downstream_tree(nodes)
    bom_layers, bom_table, layer_definitions = _semantic_bom_layers(nodes, tree, theme_name, theme_id)

    bom_paths: list[list[dict[str, Any]]] = []
    for child in tree.get("children", []):
        bom_paths.extend(_collect_bom_paths(child, []))

    tree["bom_layers"] = bom_layers
    tree["bom_paths"] = bom_paths
    tree["bom_table"] = bom_table
    tree["layer_definitions"] = layer_definitions
    return tree


def build_value_chain_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build value chain tree with margin/pricing_power/value_added per node.

    Args:
        nodes: List of chain_nodes records with value_chain JSONB field

    Returns:
        Tree structure with value_chain metrics:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [...],
            "value_chain": {
                "<node_id>": {
                    "margin": 15.0,
                    "pricing_power": 2.0,
                    "value_added": 10.0,
                    "note": "毛利率15%, 定价权弱"
                }
            }
        }
    """
    if not nodes:
        return {
            "node_id": "root",
            "name": "空产业链",
            "children": [],
            "value_chain": {},
        }

    # Build base tree structure
    tree = build_upstream_downstream_tree(nodes)

    # Extract value_chain data from each node
    value_chain_data: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_id = node.get("node_id")
        vc_raw = node.get("value_chain") or {}

        # Parse value_chain JSONB
        margin = _to_float(vc_raw.get("margin"))
        pricing_power = _to_float(vc_raw.get("pricing_power"))
        value_added = _to_float(vc_raw.get("value_added"))

        # Build note from available data
        note_parts = []
        if margin is not None:
            note_parts.append(f"毛利率{margin:.0f}%")
        if pricing_power is not None:
            pp_label = "强" if pricing_power >= 4 else ("中" if pricing_power >= 2 else "弱")
            note_parts.append(f"定价权{pp_label}")
        if value_added is not None:
            note_parts.append(f"附加值{value_added:.0f}%")

        value_chain_data[node_id] = {
            "margin": margin,
            "pricing_power": pricing_power,
            "value_added": value_added,
            "note": ", ".join(note_parts) if note_parts else "无数据",
        }

    tree["value_chain"] = value_chain_data
    return tree


def build_competition_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build competition tree with concentration/leader_share/barrier/threat per node.

    Args:
        nodes: List of chain_nodes records with competition JSONB field

    Returns:
        Tree structure with competition metrics:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [...],
            "competition": {
                "<node_id>": {
                    "concentration": 0.8,
                    "leader_share": 0.6,
                    "barrier": 5,
                    "threat": 2,
                    "note": "高集中度, 龙头份额60%, 高壁垒, 低威胁"
                }
            }
        }
    """
    if not nodes:
        return {
            "node_id": "root",
            "name": "空产业链",
            "children": [],
            "competition": {},
        }

    # Build base tree structure
    tree = build_upstream_downstream_tree(nodes)

    # Extract competition data from each node
    competition_data: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_id = node.get("node_id")
        comp_raw = node.get("competition") or {}

        # Parse competition JSONB
        concentration = _to_float(comp_raw.get("concentration"))
        leader_share = _to_float(comp_raw.get("leader_share"))
        barrier = _to_float(comp_raw.get("barrier"))
        threat = _to_float(comp_raw.get("threat"))

        # Build note from available data
        note_parts = []
        if concentration is not None:
            cc_label = "高" if concentration >= 0.7 else ("中" if concentration >= 0.4 else "低")
            note_parts.append(f"{cc_label}集中度")
        if leader_share is not None:
            note_parts.append(f"龙头份额{leader_share:.0f}%")
        if barrier is not None:
            bar_label = "高" if barrier >= 4 else ("中" if barrier >= 2 else "低")
            note_parts.append(f"{bar_label}壁垒")
        if threat is not None:
            th_label = "高" if threat >= 4 else ("中" if threat >= 2 else "低")
            note_parts.append(f"{th_label}威胁")

        competition_data[node_id] = {
            "concentration": concentration,
            "leader_share": leader_share,
            "barrier": barrier,
            "threat": threat,
            "note": ", ".join(note_parts) if note_parts else "无数据",
        }

    tree["competition"] = competition_data
    return tree


def deconstruct_chain(
    theme_id: str,
    method: str,
    nodes: list[dict[str, Any]] | None = None,
    theme_name: str | None = None,
) -> dict[str, Any]:
    """Deconstruct industry chain using specified method.

    Args:
        theme_id: Industry theme identifier (e.g., "semiconductor", "robot")
        method: Deconstruct method - one of:
            - "bom": L1-L8 BOM layer buckets and paths
            - "upstream_downstream": 5-layer tree structure
            - "value_chain": tree + margin/pricing_power/value_added
            - "competition": tree + concentration/leader_share/barrier/threat
        nodes: List of chain_nodes records (optional, for testing)
        theme_name: Human-readable theme name (optional)

    Returns:
        Deconstruct result with theme info and tree structure:
        {
            "theme": {"id": "...", "name": "..."},
            "view": "<method>",
            "tree": {...},
            "bom_layers": {...} | None,
            "bom_paths": [...] | None,
            "value_chain": {...} | None,
            "competition": {...} | None
        }
    """
    valid_methods = ("bom", "upstream_downstream", "value_chain", "competition")
    if method not in valid_methods:
        raise ValueError(f"Invalid method '{method}', must be one of {valid_methods}")

    # Use provided nodes or return empty structure
    if nodes is None:
        nodes = []

    # Add theme_name to nodes if provided (for root node name)
    if theme_name and nodes:
        for node in nodes:
            if not node.get("parent_node_id"):
                node["theme_id"] = theme_name

    # Build tree based on method
    if method == "bom":
        tree = build_bom_tree(nodes, theme_name=theme_name, theme_id=theme_id)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "bom_layers": tree.get("bom_layers", {f"L{i}": [] for i in range(1, 9)}),
            "bom_paths": tree.get("bom_paths", []),
            "bom_table": tree.get("bom_table", []),
            "layer_definitions": tree.get("layer_definitions", {}),
        }
    elif method == "upstream_downstream":
        tree = build_upstream_downstream_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
        }
    elif method == "value_chain":
        tree = build_value_chain_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "value_chain": tree.get("value_chain", {}),
        }
    elif method == "competition":
        tree = build_competition_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "competition": tree.get("competition", {}),
        }

    return result
