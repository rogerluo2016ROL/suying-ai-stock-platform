#!/usr/bin/env python3
"""Materialize priority complex-chain templates and seed listed-company mappings.

The mappings are seed candidates. They stay in pending_review until original
filings, IR records, announcements, or exchange documents are attached.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "packages/kronos-factors/configs/industry_chain_templates.json"
DEFAULT_DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

LAYER_IDS = [
    "demand",
    "task",
    "core_product",
    "foundation",
    "integration",
    "supporting",
    "infrastructure",
    "commercialization",
]

LAYER_NAMES = {
    "demand": "需求层",
    "task": "任务层",
    "core_product": "核心产品层",
    "foundation": "底层支撑层",
    "integration": "集成层",
    "supporting": "配套层",
    "infrastructure": "基础设施层",
    "commercialization": "商业变现层",
}


def metric_groups(seed: str) -> dict[str, list[str]]:
    return {
        "commercialization": [f"{seed}订单", f"{seed}收入", f"{seed}毛利率"],
        "expectation_gap": [f"{seed}订单高于预期", f"{seed}导入快于预期", f"{seed}价格/份额改善"],
        "trigger_signals": [f"{seed}中标/定点", f"{seed}CAPEX上修", f"{seed}业绩预增"],
    }


def physical_metric(chain_id: str, layer_id: str, segment: str) -> dict[str, Any]:
    return {
        "metric_id": f"{chain_id}_{layer_id}_physical_metric",
        "name": f"{segment}物理指标",
        "mapped_layer_id": layer_id,
        "mapped_segment": segment,
        "metric_usage": ["commercialization", "expectation_gap", "trigger_signal"],
        "data_type": "timeseries",
        "source_type": "industry_physical_research",
        "source_name": "verified_industry_source_required",
        "source_url": "",
        "evidence_level": "unknown",
        "collection_method": "manual_or_pipeline_required",
        "as_of_date": "unknown",
        "impact_direction": "unknown",
        "confidence": "unknown",
    }


def capex_evidence(chain_id: str, layer_id: str, segment: str) -> dict[str, Any]:
    return {
        "evidence_id": f"{chain_id}_{layer_id}_capex_evidence",
        "company": "sector_participants",
        "region": "global",
        "fiscal_period": "unknown",
        "capex_amount": None,
        "currency": "unknown",
        "capex_direction": [segment],
        "mapped_layer_id": layer_id,
        "mapped_segments": [segment],
        "metric_usage": ["commercialization", "expectation_gap", "trigger_signal"],
        "source_type": "company_filings_or_ir_required",
        "source_name": "official_company_filing_required",
        "source_url": "",
        "quote": "待采集：只允许使用公告、财报、招股书、投资者关系材料、交易所问询回复等可追溯证据。",
        "as_of_date": "unknown",
        "evidence_level": "unknown",
        "collection_method": "manual_review_required",
        "impact_direction": "unknown",
        "confidence": "unknown",
    }


def macro_context() -> list[dict[str, str]]:
    return [
        {
            "region": region,
            "policy_stance": "unknown",
            "inflation_state": "unknown",
            "rate_trend": "unknown",
            "liquidity_signal": "unknown",
            "source_type": "official_macro_policy",
            "source_name": "macro_policy_snapshot_required",
            "source_url": "",
            "as_of_date": "unknown",
            "evidence_level": "unknown",
        }
        for region in ["US", "CN", "JP", "KR", "EU"]
    ]


CHAIN_CONFIGS: dict[str, dict[str, Any]] = {
    "ai_compute_infrastructure": {
        "theme_id": "future_industry_ai_compute_infrastructure",
        "theme_name": "AI算力基础设施复杂产业链",
        "name": "AI算力基础设施复杂产业链路模板",
        "description": "围绕AI训练和推理需求，拆解芯片、服务器、光通信、PCB、电源散热、IDC、云厂商CAPEX和商业化变现。",
        "example_theme": "AI算力基础设施",
        "layers": {
            "demand": ["云厂商CAPEX", "AI训练", "AI推理", "智算中心", "政企算力"],
            "task": ["模型训练", "推理部署", "集群互联", "高带宽存储", "散热供电"],
            "core_product": ["AI芯片/GPU/ASIC", "AI服务器", "高速光模块", "交换机", "加速卡"],
            "foundation": ["HBM", "先进制程", "高速PCB", "电源芯片", "EDA/IP"],
            "integration": ["服务器整机", "集群交付", "云平台", "算力调度", "系统集成"],
            "supporting": ["液冷", "UPS电源", "高速铜缆", "连接器", "数据中心运维"],
            "infrastructure": ["智算中心", "IDC机房", "电力配套", "网络骨干", "云基础设施"],
            "commercialization": ["云算力租赁", "推理API", "服务器订单", "IDC出租率", "毛利率"],
        },
    },
    "advanced_packaging_chiplet": {
        "theme_id": "future_industry_advanced_packaging_chiplet",
        "theme_name": "先进封装/Chiplet复杂产业链",
        "name": "先进封装/Chiplet复杂产业链路模板",
        "description": "围绕2.5D/3D、CoWoS、TSV、RDL、倒装、先进封测、ABF/载板、封装材料和测试验证拆解。",
        "example_theme": "先进封装/Chiplet",
        "layers": {
            "demand": ["AI芯片封装", "HBM集成", "高性能计算", "国产替代", "服务器升级"],
            "task": ["高带宽互联", "异构集成", "散热管理", "良率提升", "测试验证"],
            "core_product": ["2.5D/3D封装", "Chiplet", "CoWoS类封装", "SiP", "先进测试"],
            "foundation": ["ABF/IC载板", "TSV/RDL", "键合材料", "封装基板", "环氧塑封料"],
            "integration": ["封装测试", "晶圆级封装", "系统级封装", "模组集成", "客户验证"],
            "supporting": ["测试设备", "切磨抛设备", "贴装键合设备", "洁净厂务", "高纯材料"],
            "infrastructure": ["先进封装产线", "封测基地", "HBM配套产能", "测试产能", "研发中试线"],
            "commercialization": ["封测订单", "产能利用率", "客户导入", "单价提升", "毛利改善"],
        },
    },
    "semiconductor_equipment_materials": {
        "theme_id": "future_industry_semiconductor_equipment_materials",
        "theme_name": "半导体设备材料复杂产业链",
        "name": "半导体设备材料复杂产业链路模板",
        "description": "围绕国产半导体扩产和先进制程，拆解设备、材料、零部件、厂务、客户认证、订单和国产替代进度。",
        "example_theme": "半导体设备材料",
        "layers": {
            "demand": ["晶圆厂扩产", "存储扩产", "先进封装扩产", "国产替代", "设备更新"],
            "task": ["制程突破", "良率提升", "成本下降", "供应安全", "客户认证"],
            "core_product": ["刻蚀设备", "薄膜设备", "清洗设备", "CMP设备", "测试设备"],
            "foundation": ["硅片", "光刻胶", "电子特气", "CMP材料", "靶材", "湿电子化学品"],
            "integration": ["设备交付", "材料导入", "产线验证", "良率爬坡", "客户量产"],
            "supporting": ["零部件", "真空系统", "高纯工艺系统", "洁净室", "检测量测"],
            "infrastructure": ["晶圆厂产线", "设备国产化平台", "材料认证平台", "厂务工程", "供应链安全"],
            "commercialization": ["订单 backlog", "收入确认", "国产化率", "客户扩散", "毛利率"],
        },
    },
    "offshore_wind_subsea_cable": {
        "theme_id": "future_industry_offshore_wind_subsea_cable",
        "theme_name": "海风海缆/海洋能源装备复杂产业链",
        "name": "海风海缆/海洋能源装备复杂产业链路模板",
        "description": "围绕海上风电、海底光电复合缆、海工施工、海洋能源互联和深远海运维，拆解订单、交付、技术门槛和商业变现。",
        "example_theme": "海风海缆/海洋能源装备",
        "layers": {
            "demand": ["海上风电装机", "海洋能源互联", "深远海开发", "海洋油气", "跨国电力互联"],
            "task": ["大容量输电", "深远海敷设", "动态海缆连接", "海上施工运维", "项目交付"],
            "core_product": ["海底电缆", "海底光电复合缆", "动态海缆", "海工装备", "风机整机"],
            "foundation": ["高压绝缘材料", "导体材料", "海缆附件", "塔筒桩基", "海工船舶"],
            "integration": ["海缆制造", "海缆敷设", "海风EPC", "风电场并网", "运维服务"],
            "supporting": ["施工船队", "检测监测", "海工吊装", "电力设备", "项目管理"],
            "infrastructure": ["海上风电基地", "海底输电通道", "柔直送出", "海洋牧场能源系统", "跨海联网"],
            "commercialization": ["海缆订单", "海工收入", "在手订单", "交付验收", "海洋板块收入"],
        },
    },
    "new_power_system_grid": {
        "theme_id": "future_industry_new_power_system_grid",
        "theme_name": "新型电力系统/智能电网复杂产业链",
        "name": "新型电力系统/智能电网复杂产业链路模板",
        "description": "围绕新能源并网、特高压、柔直、电网智能化、配网升级、储能和用电侧管理，拆解电网投资、设备订单和商业化兑现。",
        "example_theme": "新型电力系统/智能电网",
        "layers": {
            "demand": ["新能源并网", "电网投资", "特高压建设", "配网升级", "AI算力用电"],
            "task": ["远距离输电", "柔性直流", "电网调度", "配电自动化", "负荷管理"],
            "core_product": ["特高压设备", "柔直设备", "电力电缆", "变压器", "智能电表"],
            "foundation": ["电力电子器件", "绝缘材料", "导线金具", "通信光缆", "传感计量"],
            "integration": ["输变电系统", "配网系统", "调度自动化", "储能接入", "电力工程"],
            "supporting": ["电力通信", "二次设备", "电力软件", "运维检测", "充电配套"],
            "infrastructure": ["特高压通道", "主干电网", "配电网", "虚拟电厂", "源网荷储系统"],
            "commercialization": ["电网订单", "设备中标", "收入确认", "在手订单", "毛利率"],
        },
    },
}

EXISTING_TEMPLATE_NODE_CONFIGS = {
    "embodied_intelligence": {
        "theme_id": "future_industry_embodied_intelligence",
        "theme_name": "具身智能复杂产业链",
    },
}


MAPPINGS: dict[str, list[dict[str, str]]] = {
    "ai_compute_infrastructure": [
        {"code": "688256", "name": "寒武纪", "layer": "core_product", "product": "AI芯片/加速卡"},
        {"code": "688041", "name": "海光信息", "layer": "core_product", "product": "AI/HPC处理器"},
        {"code": "300474", "name": "景嘉微", "layer": "core_product", "product": "GPU/图形处理芯片"},
        {"code": "000977", "name": "浪潮信息", "layer": "integration", "product": "AI服务器整机"},
        {"code": "603019", "name": "中科曙光", "layer": "integration", "product": "AI服务器/智算中心"},
        {"code": "601138", "name": "工业富联", "layer": "integration", "product": "AI服务器制造"},
        {"code": "000938", "name": "紫光股份", "layer": "integration", "product": "ICT基础设施/交换机"},
        {"code": "300308", "name": "中际旭创", "layer": "core_product", "product": "高速光模块"},
        {"code": "300502", "name": "新易盛", "layer": "core_product", "product": "高速光模块"},
        {"code": "300394", "name": "天孚通信", "layer": "foundation", "product": "光器件"},
        {"code": "002281", "name": "光迅科技", "layer": "foundation", "product": "光模块/光器件"},
        {"code": "688498", "name": "源杰科技", "layer": "foundation", "product": "光芯片"},
        {"code": "688313", "name": "仕佳光子", "layer": "foundation", "product": "光芯片/PLC"},
        {"code": "002463", "name": "沪电股份", "layer": "foundation", "product": "AI服务器高速PCB"},
        {"code": "002916", "name": "深南电路", "layer": "foundation", "product": "高速PCB/IC载板"},
        {"code": "300476", "name": "胜宏科技", "layer": "foundation", "product": "AI服务器PCB"},
        {"code": "600183", "name": "生益科技", "layer": "foundation", "product": "覆铜板"},
        {"code": "002837", "name": "英维克", "layer": "supporting", "product": "数据中心液冷/温控"},
        {"code": "600522", "name": "中天科技", "layer": "supporting", "product": "高速铜缆/数据中心线缆/连接器"},
        {"code": "002335", "name": "科华数据", "layer": "infrastructure", "product": "数据中心/电源"},
        {"code": "300442", "name": "润泽科技", "layer": "infrastructure", "product": "IDC/算力基础设施"},
        {"code": "600845", "name": "宝信软件", "layer": "infrastructure", "product": "IDC/工业云"},
        {"code": "300738", "name": "奥飞数据", "layer": "infrastructure", "product": "IDC"},
        {"code": "603881", "name": "数据港", "layer": "infrastructure", "product": "IDC"},
        {"code": "600522", "name": "中天科技", "layer": "infrastructure", "product": "算力中心电力配套/机电总包"},
        {"code": "688111", "name": "金山办公", "layer": "commercialization", "product": "AI应用商业化"},
    ],
    "advanced_packaging_chiplet": [
        {"code": "600584", "name": "长电科技", "layer": "integration", "product": "先进封装/封测"},
        {"code": "002156", "name": "通富微电", "layer": "integration", "product": "先进封装/封测"},
        {"code": "002185", "name": "华天科技", "layer": "integration", "product": "封装测试"},
        {"code": "688362", "name": "甬矽电子", "layer": "integration", "product": "封装测试"},
        {"code": "688352", "name": "颀中科技", "layer": "integration", "product": "封装测试"},
        {"code": "603005", "name": "晶方科技", "layer": "integration", "product": "晶圆级封装"},
        {"code": "688135", "name": "利扬芯片", "layer": "supporting", "product": "芯片测试"},
        {"code": "300604", "name": "长川科技", "layer": "supporting", "product": "测试设备"},
        {"code": "688200", "name": "华峰测控", "layer": "supporting", "product": "测试设备"},
        {"code": "002436", "name": "兴森科技", "layer": "foundation", "product": "IC载板/封装基板"},
        {"code": "002916", "name": "深南电路", "layer": "foundation", "product": "IC载板/PCB"},
        {"code": "002463", "name": "沪电股份", "layer": "foundation", "product": "高速PCB"},
        {"code": "600183", "name": "生益科技", "layer": "foundation", "product": "覆铜板/封装材料"},
        {"code": "688535", "name": "华海诚科", "layer": "foundation", "product": "环氧塑封料"},
        {"code": "688300", "name": "联瑞新材", "layer": "foundation", "product": "硅微粉/封装填料"},
        {"code": "688630", "name": "芯碁微装", "layer": "supporting", "product": "直写光刻设备"},
        {"code": "601133", "name": "柏诚股份", "layer": "infrastructure", "product": "洁净室/厂务工程"},
        {"code": "603690", "name": "至纯科技", "layer": "infrastructure", "product": "高纯工艺系统"},
    ],
    "semiconductor_equipment_materials": [
        {"code": "002371", "name": "北方华创", "layer": "core_product", "product": "刻蚀/薄膜/清洗设备"},
        {"code": "688012", "name": "中微公司", "layer": "core_product", "product": "刻蚀/MOCVD设备"},
        {"code": "688072", "name": "拓荆科技", "layer": "core_product", "product": "薄膜沉积设备"},
        {"code": "688037", "name": "芯源微", "layer": "core_product", "product": "涂胶显影/清洗设备"},
        {"code": "688120", "name": "华海清科", "layer": "core_product", "product": "CMP设备"},
        {"code": "688082", "name": "盛美上海", "layer": "core_product", "product": "清洗/电镀设备"},
        {"code": "300604", "name": "长川科技", "layer": "core_product", "product": "测试设备"},
        {"code": "688200", "name": "华峰测控", "layer": "core_product", "product": "测试设备"},
        {"code": "300567", "name": "精测电子", "layer": "supporting", "product": "检测量测设备"},
        {"code": "688126", "name": "沪硅产业", "layer": "foundation", "product": "半导体硅片"},
        {"code": "002409", "name": "雅克科技", "layer": "foundation", "product": "前驱体/电子材料"},
        {"code": "688019", "name": "安集科技", "layer": "foundation", "product": "CMP抛光液"},
        {"code": "300666", "name": "江丰电子", "layer": "foundation", "product": "半导体靶材"},
        {"code": "688146", "name": "中船特气", "layer": "foundation", "product": "电子特气"},
        {"code": "688268", "name": "华特气体", "layer": "foundation", "product": "电子特气"},
        {"code": "688106", "name": "金宏气体", "layer": "foundation", "product": "电子大宗气体/特气"},
        {"code": "688548", "name": "广钢气体", "layer": "foundation", "product": "电子大宗气体"},
        {"code": "688596", "name": "正帆科技", "layer": "supporting", "product": "工艺介质供应系统"},
        {"code": "300655", "name": "晶瑞电材", "layer": "foundation", "product": "光刻胶/湿电子化学品"},
        {"code": "300576", "name": "容大感光", "layer": "foundation", "product": "光刻胶/电子材料"},
        {"code": "603078", "name": "江化微", "layer": "foundation", "product": "湿电子化学品"},
        {"code": "300054", "name": "鼎龙股份", "layer": "foundation", "product": "CMP抛光垫/材料"},
        {"code": "603650", "name": "彤程新材", "layer": "foundation", "product": "光刻胶/电子材料"},
        {"code": "300236", "name": "上海新阳", "layer": "foundation", "product": "电镀液/清洗液"},
        {"code": "300346", "name": "南大光电", "layer": "foundation", "product": "电子特气/光刻胶材料"},
        {"code": "603690", "name": "至纯科技", "layer": "infrastructure", "product": "高纯工艺系统/厂务"},
        {"code": "603929", "name": "亚翔集成", "layer": "infrastructure", "product": "洁净室工程"},
        {"code": "601133", "name": "柏诚股份", "layer": "infrastructure", "product": "洁净室/厂务工程"},
    ],
    "offshore_wind_subsea_cable": [
        {"code": "600522", "name": "中天科技", "layer": "core_product", "product": "海底光电复合缆/动态海缆"},
        {"code": "603606", "name": "东方电缆", "layer": "core_product", "product": "海底电缆/海底光电复合缆"},
        {"code": "600487", "name": "亨通光电", "layer": "core_product", "product": "海缆/海底通信光缆"},
        {"code": "600973", "name": "宝胜股份", "layer": "foundation", "product": "电线电缆/导体材料"},
        {"code": "301155", "name": "海力风电", "layer": "foundation", "product": "海上风电塔筒/桩基"},
        {"code": "002487", "name": "大金重工", "layer": "foundation", "product": "海风塔筒/单桩"},
        {"code": "300129", "name": "泰胜风能", "layer": "foundation", "product": "风电塔筒"},
        {"code": "002531", "name": "天顺风能", "layer": "foundation", "product": "风塔/海工装备"},
        {"code": "600875", "name": "东方电气", "layer": "core_product", "product": "海上风电整机"},
        {"code": "601615", "name": "明阳智能", "layer": "core_product", "product": "海上风电整机"},
        {"code": "300772", "name": "运达股份", "layer": "core_product", "product": "风电整机"},
        {"code": "002202", "name": "金风科技", "layer": "core_product", "product": "风电整机"},
        {"code": "600522", "name": "中天科技", "layer": "integration", "product": "海缆制造/敷设/运维一体化"},
        {"code": "603606", "name": "东方电缆", "layer": "integration", "product": "海缆系统交付"},
        {"code": "600487", "name": "亨通光电", "layer": "integration", "product": "海洋通信与能源互联"},
        {"code": "600905", "name": "三峡能源", "layer": "demand", "product": "海上风电运营/装机需求"},
        {"code": "600522", "name": "中天科技", "layer": "commercialization", "product": "海洋板块收入/海缆订单"},
    ],
    "new_power_system_grid": [
        {"code": "600406", "name": "国电南瑞", "layer": "core_product", "product": "电网自动化/继电保护"},
        {"code": "000400", "name": "许继电气", "layer": "core_product", "product": "特高压/柔直/智能变配电"},
        {"code": "600312", "name": "平高电气", "layer": "core_product", "product": "高压开关/特高压设备"},
        {"code": "601179", "name": "中国西电", "layer": "core_product", "product": "输变电设备"},
        {"code": "002028", "name": "思源电气", "layer": "core_product", "product": "输变电设备/无功补偿"},
        {"code": "600089", "name": "特变电工", "layer": "core_product", "product": "变压器/输变电系统"},
        {"code": "688676", "name": "金盘科技", "layer": "core_product", "product": "干式变压器/新能源电力设备"},
        {"code": "600522", "name": "中天科技", "layer": "core_product", "product": "电力电缆/OPGW/柔性直流电缆"},
        {"code": "600487", "name": "亨通光电", "layer": "core_product", "product": "电力光缆/海缆/智能电网"},
        {"code": "600973", "name": "宝胜股份", "layer": "core_product", "product": "电线电缆"},
        {"code": "000682", "name": "东方电子", "layer": "integration", "product": "电力调度/配电自动化"},
        {"code": "600131", "name": "国网信通", "layer": "supporting", "product": "电力通信/能源数字化"},
        {"code": "300360", "name": "炬华科技", "layer": "core_product", "product": "智能电表/计量"},
        {"code": "300286", "name": "安科瑞", "layer": "supporting", "product": "用户侧电力监控/能效管理"},
        {"code": "300001", "name": "特锐德", "layer": "infrastructure", "product": "箱变/充电网/配电设备"},
        {"code": "002452", "name": "长高电气", "layer": "core_product", "product": "高压隔离开关/组合电器"},
        {"code": "300820", "name": "英杰电气", "layer": "foundation", "product": "工业电源/电力电子"},
        {"code": "600522", "name": "中天科技", "layer": "commercialization", "product": "电网业务收入/在手订单"},
    ],
}


def make_template(chain_id: str, config: dict[str, Any]) -> dict[str, Any]:
    layers = []
    for order, layer_id in enumerate(LAYER_IDS, start=1):
        segments = config["layers"][layer_id]
        seed = segments[0]
        layers.append({
            "layer_id": layer_id,
            "order": order,
            "name": LAYER_NAMES[layer_id],
            "definition": f"围绕{config['example_theme']}的{LAYER_NAMES[layer_id]}，跟踪{';'.join(segments)}。",
            "key_questions": [
                f"{seed}是否形成真实订单或验证进展？",
                "是否能传导到收入、毛利或CAPEX？",
                "是否有公告、财报、IR或产业物理指标支撑？",
            ],
            "segments": segments,
            "evidence": [
                "所有现实判断必须回到公告、财报、招股书、IR、交易所文件或可复核产业数据。",
                "概念相关只能作为候选映射，不能直接视为强证据。",
            ],
            "companies": sorted({m["name"] for m in MAPPINGS.get(chain_id, []) if m["layer"] == layer_id}),
            "tracking_metrics": [f"{seed}订单", f"{seed}价格/渗透率", f"{seed}客户导入", f"{seed}CAPEX", f"{seed}毛利率"],
            "metrics": metric_groups(seed),
            "capex_evidence": [capex_evidence(chain_id, layer_id, seed)],
            "physical_metrics": [physical_metric(chain_id, layer_id, seed)],
        })
    return {
        "template_id": chain_id,
        "name": config["name"],
        "description": config["description"],
        "example_theme": config["example_theme"],
        "macro_context": macro_context(),
        "layers": layers,
    }


def layer_node_id(chain_id: str, layer_id: str) -> str:
    return f"{chain_id}_{layer_id}"


def mapping_id(chain_id: str, code: str, layer_id: str, product: str) -> str:
    token = "".join(ch for ch in product.upper() if ch.isalnum())[:20] or layer_id.upper()
    return f"{chain_id[:6].upper()}-{code}-{layer_id.upper()}-{token}"


def mapping_path(chain_id: str, config: dict[str, Any], layer_id: str, product: str) -> list[dict[str, str]]:
    layer = LAYER_IDS.index(layer_id) + 1
    return [
        {"level": "L1", "name": "未来产业主攻方向"},
        {"level": "L2", "name": config["example_theme"]},
        {"level": "L3", "name": config["theme_name"]},
        {"level": f"L{layer}", "id": layer_node_id(chain_id, layer_id), "name": LAYER_NAMES[layer_id]},
        {"level": "segment", "name": ";".join(config["layers"][layer_id])},
        {"level": "product", "name": product},
    ]


def update_template_file() -> list[str]:
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    current = {item.get("template_id"): item for item in data.get("templates", [])}
    updated: list[str] = []
    for chain_id, config in CHAIN_CONFIGS.items():
        template = make_template(chain_id, config)
        if current.get(chain_id) != template:
            current[chain_id] = template
            updated.append(chain_id)
    ordered = [item for item in data.get("templates", []) if item.get("template_id") not in CHAIN_CONFIGS]
    ordered.extend(current[chain_id] for chain_id in CHAIN_CONFIGS)
    data["templates"] = ordered
    TEMPLATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated


def validate_codes(cur) -> dict[str, list[str]]:
    all_codes = sorted({item["code"] for items in MAPPINGS.values() for item in items})
    cur.execute("SELECT code FROM stocks WHERE code = ANY(%s)", (all_codes,))
    found = {row[0] for row in cur.fetchall()}
    return {"missing_codes": sorted(set(all_codes) - found)}


def persist(pg_url: str) -> dict[str, Any]:
    counts: dict[str, int] = {
        "industry_themes": 0,
        "supply_chain_bom_nodes": 0,
        "chain_nodes": 0,
        "supply_chain_bom_edges": 0,
        "company_business_segments": 0,
        "business_tag_mapping": 0,
    }
    with psycopg2.connect(pg_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            validation = validate_codes(cur)
            if validation["missing_codes"]:
                raise RuntimeError(f"stocks table missing codes: {validation['missing_codes']}")
            for chain_id, config in CHAIN_CONFIGS.items():
                _persist_chain_nodes(cur, chain_id, config, counts)
                for item in MAPPINGS[chain_id]:
                    layer_id = item["layer"]
                    product = item["product"]
                    segment_id = f"{chain_id}_{layer_id}_{item['code']}"
                    mid = mapping_id(chain_id, item["code"], layer_id, product)
                    cur.execute(
                        """
                        INSERT INTO company_business_segments (
                            segment_id, code, segment_name, report_period, revenue, revenue_ratio,
                            gross_profit, gross_margin, source_table, source_row_id,
                            evidence_status, metadata
                        )
                        VALUES (%s, %s, %s, NULL, NULL, NULL, NULL, NULL, %s, %s, %s, %s)
                        ON CONFLICT (segment_id) DO UPDATE SET
                            code = EXCLUDED.code,
                            segment_name = EXCLUDED.segment_name,
                            source_table = EXCLUDED.source_table,
                            source_row_id = EXCLUDED.source_row_id,
                            evidence_status = EXCLUDED.evidence_status,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            segment_id,
                            item["code"],
                            product,
                            "manual_priority_complex_chain_seed",
                            mid,
                            "pending_review",
                            Json({"chain_id": chain_id, "layer_id": layer_id, "company_name": item["name"], "requires_original_evidence": True}),
                        ),
                    )
                    counts["company_business_segments"] += 1
                    cur.execute(
                        """
                        INSERT INTO business_tag_mapping (
                            mapping_id, code, business_segment_id, node_id, theme_id, chain_id,
                            tag_name, l1_l8_path, revenue_ratio, gross_profit_ratio,
                            confidence, status, evidence_ids
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NULL, NULL, %s, %s, %s::jsonb)
                        ON CONFLICT (mapping_id) DO UPDATE SET
                            code = EXCLUDED.code,
                            business_segment_id = EXCLUDED.business_segment_id,
                            node_id = EXCLUDED.node_id,
                            theme_id = EXCLUDED.theme_id,
                            chain_id = EXCLUDED.chain_id,
                            tag_name = EXCLUDED.tag_name,
                            l1_l8_path = EXCLUDED.l1_l8_path,
                            confidence = EXCLUDED.confidence,
                            status = EXCLUDED.status,
                            evidence_ids = EXCLUDED.evidence_ids,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            mid,
                            item["code"],
                            segment_id,
                            layer_node_id(chain_id, layer_id),
                            config["theme_id"],
                            chain_id,
                            LAYER_NAMES[layer_id],
                            json.dumps(mapping_path(chain_id, config, layer_id, product), ensure_ascii=False),
                            0.72,
                            "pending_review",
                            json.dumps(["manual_priority_complex_chain_seed_requires_original_evidence"], ensure_ascii=False),
                        ),
                    )
                    counts["business_tag_mapping"] += 1

            existing_templates = {
                item.get("template_id"): item
                for item in json.loads(TEMPLATE_PATH.read_text(encoding="utf-8")).get("templates", [])
            }
            for chain_id, node_config in EXISTING_TEMPLATE_NODE_CONFIGS.items():
                template = existing_templates.get(chain_id)
                if not template:
                    raise RuntimeError(f"missing template for {chain_id}")
                config = {
                    "theme_id": node_config["theme_id"],
                    "theme_name": node_config["theme_name"],
                    "example_theme": template.get("example_theme", node_config["theme_name"]),
                    "layers": {
                        layer["layer_id"]: layer.get("segments", [])
                        for layer in sorted(template.get("layers", []), key=lambda item: item.get("order", 0))
                    },
                }
                _persist_chain_nodes(cur, chain_id, config, counts)
        conn.commit()
    unique_companies = {item["code"] for items in MAPPINGS.values() for item in items}
    return {"counts": counts, "unique_companies": len(unique_companies), "mapping_rows": sum(len(items) for items in MAPPINGS.values())}


def _persist_chain_nodes(cur, chain_id: str, config: dict[str, Any], counts: dict[str, int]) -> None:
    cur.execute(
        """
        INSERT INTO industry_themes
            (theme_id, theme_name, category, key_directions, policy_intensity_stars)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (theme_id) DO UPDATE SET
            theme_name = EXCLUDED.theme_name,
            category = EXCLUDED.category,
            key_directions = EXCLUDED.key_directions,
            policy_intensity_stars = EXCLUDED.policy_intensity_stars,
            updated_at = NOW()
        """,
        (
            config["theme_id"],
            config["theme_name"],
            "复杂产业链",
            Json(config["layers"]["core_product"] + config["layers"]["foundation"]),
            4,
        ),
    )
    counts["industry_themes"] += 1
    for order, layer_id in enumerate(LAYER_IDS, start=1):
        node_id = layer_node_id(chain_id, layer_id)
        parent_node_id = None if order == 1 else layer_node_id(chain_id, LAYER_IDS[order - 2])
        segments = config["layers"][layer_id]
        cur.execute(
            """
            INSERT INTO supply_chain_bom_nodes
                (node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id = EXCLUDED.theme_id,
                chain_id = EXCLUDED.chain_id,
                parent_node_id = EXCLUDED.parent_node_id,
                level = EXCLUDED.level,
                name = EXCLUDED.name,
                node_type = EXCLUDED.node_type,
                keywords = EXCLUDED.keywords,
                policy_weight = EXCLUDED.policy_weight
            """,
            (
                node_id,
                config["theme_id"],
                chain_id,
                parent_node_id,
                f"L{order}",
                LAYER_NAMES[layer_id],
                "complex_chain_layer",
                Json(segments),
                3,
            ),
        )
        counts["supply_chain_bom_nodes"] += 1
        cur.execute(
            """
            INSERT INTO chain_nodes
                (node_id, theme_id, node_name, layer, parent_node_id, upstream_nodes, downstream_nodes, value_chain, competition)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id = EXCLUDED.theme_id,
                node_name = EXCLUDED.node_name,
                layer = EXCLUDED.layer,
                parent_node_id = EXCLUDED.parent_node_id,
                upstream_nodes = EXCLUDED.upstream_nodes,
                downstream_nodes = EXCLUDED.downstream_nodes,
                value_chain = EXCLUDED.value_chain,
                competition = EXCLUDED.competition
            """,
            (
                node_id,
                config["theme_id"],
                LAYER_NAMES[layer_id],
                order,
                parent_node_id,
                Json([]),
                Json([]),
                Json({"note": f"{config['example_theme']}复杂产业链8层节点", "chain_id": chain_id, "segments": segments}),
                Json({"status": "pending_evidence_review", "note": "竞争格局需公告/研报补证"}),
            ),
        )
        counts["chain_nodes"] += 1
    for idx in range(len(LAYER_IDS) - 1):
        from_id = layer_node_id(chain_id, LAYER_IDS[idx])
        to_id = layer_node_id(chain_id, LAYER_IDS[idx + 1])
        edge_id = f"{from_id}->{to_id}"
        cur.execute(
            """
            INSERT INTO supply_chain_bom_edges (edge_id, from_node_id, to_node_id, relation)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (edge_id) DO UPDATE SET
                from_node_id = EXCLUDED.from_node_id,
                to_node_id = EXCLUDED.to_node_id,
                relation = EXCLUDED.relation
            """,
            (edge_id, from_id, to_id, "8层复杂产业链顺序链路"),
        )
        counts["supply_chain_bom_edges"] += 1

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--skip-db", action="store_true")
    parser.add_argument("--skip-template", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {"templates_updated": [], "persist": {}}
    if not args.skip_template:
        result["templates_updated"] = update_template_file()
    if not args.skip_db:
        result["persist"] = persist(args.pg_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
