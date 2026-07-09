#!/usr/bin/env python3
"""Materialize the storage-chip complex chain template and listed-company mappings.

This seed is intentionally conservative: it maps listed companies to the
storage-chain layer they can plausibly support, but keeps mappings in
``pending_review`` until original filings / IR / research evidence is attached.
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

THEME_ID = "future_industry_storage_chips"
CHAIN_ID = "storage_chips"
THEME_NAME = "存储芯片复杂产业链"


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


def metric_groups(commercialization: list[str], expectation_gap: list[str], trigger_signals: list[str]) -> dict[str, list[str]]:
    return {
        "commercialization": commercialization,
        "expectation_gap": expectation_gap,
        "trigger_signals": trigger_signals,
    }


def physical_metric(metric_id: str, name: str, layer_id: str, segment: str, usage: list[str]) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "name": name,
        "mapped_layer_id": layer_id,
        "mapped_segment": segment,
        "metric_usage": usage,
        "data_type": "timeseries",
        "source_type": "industry_physical_research",
        "source_name": "verified_memory_price_or_industry_source_required",
        "source_url": "",
        "evidence_level": "unknown",
        "collection_method": "manual_or_pipeline_required",
        "as_of_date": "unknown",
        "impact_direction": "unknown",
        "confidence": "unknown",
    }


def capex_evidence(evidence_id: str, company: str, layer_id: str, directions: list[str], segments: list[str]) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "company": company,
        "region": "global",
        "fiscal_period": "unknown",
        "capex_amount": None,
        "currency": "unknown",
        "capex_direction": directions,
        "mapped_layer_id": layer_id,
        "mapped_segments": segments,
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


STORAGE_TEMPLATE: dict[str, Any] = {
    "template_id": CHAIN_ID,
    "name": "存储芯片复杂产业链路模板",
    "description": "面向 DRAM、NAND、HBM、DDR5、LPDDR、SSD、UFS/eMMC 等存储方向，沿用复杂科技 8 层拆解逻辑，突出价格周期、国产替代、扩产 CAPEX、封测材料和商业变现证据。",
    "example_theme": "存储芯片",
    "macro_context": macro_context(),
    "layers": [
        {
            "layer_id": "demand",
            "order": 1,
            "name": "需求层",
            "definition": "识别 AI服务器、云厂商、终端、汽车电子等真实存储需求来源，区分价格周期、库存补库和终端出货拉动。",
            "key_questions": ["需求来自 AI 服务器、手机 PC 复苏还是汽车电子？", "下游是在真实补库还是价格投机？", "云厂商 CAPEX 是否传导到存储采购？"],
            "segments": ["AI服务器", "云厂商CAPEX", "智能手机", "PC/AI PC", "汽车电子", "工业控制"],
            "evidence": ["AI服务器、云厂商、手机/PC、汽车电子出货是需求层核心证据。", "价格上涨必须和库存、出货或订单结合判断，不能单看概念热度。"],
            "companies": ["浪潮信息", "中科曙光", "工业富联", "紫光股份"],
            "tracking_metrics": ["AI服务器出货", "云厂商CAPEX", "手机/PC出货", "汽车电子存储用量", "库存周转天数"],
            "metrics": metric_groups(["终端补库", "AI服务器放量", "云厂商采购", "汽车电子渗透"], ["出货量高于预期", "库存去化快于预期", "云CAPEX上修"], ["云厂商CAPEX上修", "AI服务器订单放量", "终端补库启动"]),
            "capex_evidence": [capex_evidence("storage_demand_cloud_ai_server_capex", "cloud_and_ai_server_customers", "demand", ["AI服务器采购", "数据中心CAPEX"], ["AI服务器", "云厂商CAPEX"])],
            "physical_metrics": [physical_metric("storage_ai_server_shipments", "AI服务器出货量", "demand", "AI服务器", ["commercialization", "expectation_gap"])],
        },
        {
            "layer_id": "task",
            "order": 2,
            "name": "任务层",
            "definition": "把存储需求拆成容量、带宽、功耗、可靠性和接口任务，判断哪类产品正在形成结构性增量。",
            "key_questions": ["任务需要高带宽、低功耗、低延迟还是车规可靠性？", "HBM、DDR5、LPDDR、SSD 哪个品类最紧？", "接口芯片和模组是否成为瓶颈？"],
            "segments": ["训练存储", "推理缓存", "端侧内存", "车规存储", "SSD容量", "内存接口"],
            "evidence": ["任务层要看 DDR5、HBM、LPDDR、SSD 等不同产品的需求结构。", "同样叫存储，服务器、终端和车规对应的价格弹性不同。"],
            "companies": ["澜起科技", "聚辰股份", "兆易创新", "北京君正"],
            "tracking_metrics": ["DDR5渗透率", "HBM需求", "LPDDR需求", "SSD容量", "车规认证进度", "内存接口出货"],
            "metrics": metric_groups(["样品验证", "客户认证", "批量导入", "平台绑定"], ["高端存储渗透率高于预期", "接口芯片导入快于预期", "车规认证进度提前"], ["DDR5/HBM需求上修", "车规客户认证", "服务器平台切换"]),
            "capex_evidence": [],
            "physical_metrics": [physical_metric("storage_ddr5_hbm_penetration", "DDR5/HBM渗透率", "task", "高带宽任务", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "core_product",
            "order": 3,
            "name": "核心产品层",
            "definition": "识别直接承载存储价值的芯片、颗粒、模组和接口产品，包括 DRAM、NAND、HBM、SSD、UFS/eMMC、NOR 和接口芯片。",
            "key_questions": ["产品是颗粒、主控、模组还是接口？", "涨价是否能进入收入和毛利？", "国产替代在 DRAM、NAND、NOR、接口芯片哪个品类突破？"],
            "segments": ["DRAM", "NAND Flash", "HBM", "DDR5/LPDDR", "SSD/UFS/eMMC", "NOR Flash", "内存接口芯片"],
            "evidence": ["核心产品层要看合约价、现货价、出货量、客户导入和毛利率。", "模组厂库存收益和芯片厂真实涨价弹性需要分开。"],
            "companies": ["兆易创新", "北京君正", "普冉股份", "东芯股份", "恒烁股份", "佰维存储", "江波龙", "德明利", "澜起科技", "聚辰股份"],
            "tracking_metrics": ["DRAM价格", "NAND价格", "HBM供需", "NOR价格", "模组出货", "毛利率"],
            "metrics": metric_groups(["价格触底", "涨价传导", "客户导入", "收入毛利兑现"], ["价格涨幅高于预期", "毛利改善快于预期", "客户导入快于预期"], ["合约价连续上涨", "业绩预增", "客户订单披露"]),
            "capex_evidence": [capex_evidence("storage_core_product_capacity_capex", "memory_idm_and_module_companies", "core_product", ["DRAM扩产", "NAND扩产", "HBM产线", "模组产线"], ["DRAM", "NAND Flash", "HBM", "SSD/UFS/eMMC"])],
            "physical_metrics": [physical_metric("storage_dram_nand_contract_price", "DRAM/NAND合约价", "core_product", "存储价格", ["commercialization", "expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "foundation",
            "order": 4,
            "name": "底层支撑层",
            "definition": "拆解决定存储扩产、良率和国产替代的设备、材料、硅片、气体、光刻胶、CMP、靶材和测试能力。",
            "key_questions": ["长鑫/长江存储扩产首先卡在哪些设备和材料？", "国产设备材料是否通过认证？", "扩产 CAPEX 是否能传导到订单？"],
            "segments": ["刻蚀/薄膜/清洗设备", "涂胶显影/检测测试", "CMP设备和材料", "硅片", "电子特气", "光刻胶", "靶材", "湿电子化学品"],
            "evidence": ["底层支撑层要用扩产订单、客户认证、产线导入和良率改善验证。", "设备材料公司不能只因半导体概念入选，必须能对应存储扩产或先进制程。"],
            "companies": ["北方华创", "中微公司", "拓荆科技", "芯源微", "华海清科", "盛美上海", "长川科技", "雅克科技", "安集科技", "沪硅产业", "江丰电子", "中船特气"],
            "tracking_metrics": ["设备订单", "材料认证", "产线导入", "国产化率", "良率", "客户集中度"],
            "metrics": metric_groups(["送样认证", "客户导入", "批量订单", "国产替代放量"], ["订单高于预期", "认证快于预期", "国产化率提升快于预期"], ["长鑫/长江存储扩产订单", "设备中标", "材料认证通过"]),
            "capex_evidence": [capex_evidence("storage_foundation_equipment_material_capex", "equipment_and_material_suppliers", "foundation", ["半导体设备", "材料认证", "存储扩产配套"], ["刻蚀/薄膜/清洗设备", "CMP设备和材料", "电子特气", "光刻胶"])],
            "physical_metrics": [physical_metric("storage_equipment_order_backlog", "存储扩产设备订单", "foundation", "设备订单", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "integration",
            "order": 5,
            "name": "集成层",
            "definition": "跟踪晶圆制造、封装测试、模组制造和系统集成，把存储颗粒转化为客户可用产品。",
            "key_questions": ["封测是否受益于 DDR5/HBM/NAND 封装升级？", "模组厂是否能把涨价转化为利润？", "系统集成是否接近终端客户？"],
            "segments": ["晶圆制造", "存储封测", "先进封装", "模组制造", "SSD整机", "测试分选"],
            "evidence": ["集成层看封测产能、模组出货、客户订单和收入毛利改善。", "封测和模组的商业模式不同，库存收益不能等同长期盈利能力。"],
            "companies": ["长电科技", "通富微电", "华天科技", "甬矽电子", "颀中科技", "深科技", "太极实业"],
            "tracking_metrics": ["封测订单", "封测产能利用率", "模组出货", "SSD出货", "客户导入", "良率"],
            "metrics": metric_groups(["封测导入", "模组出货", "客户批量采购", "毛利兑现"], ["封测订单高于预期", "模组出货高于预期", "良率提升"], ["封测扩产", "大客户订单", "业绩预增"]),
            "capex_evidence": [capex_evidence("storage_integration_packaging_testing_capex", "packaging_testing_and_module_companies", "integration", ["存储封测", "先进封装", "模组产线"], ["存储封测", "先进封装", "模组制造"])],
            "physical_metrics": [physical_metric("storage_packaging_testing_utilization", "存储封测产能利用率", "integration", "存储封测", ["commercialization", "expectation_gap"])],
        },
        {
            "layer_id": "supporting",
            "order": 6,
            "name": "配套层",
            "definition": "识别测试设备、PCB/IC载板、洁净室、真空/管路、厂务工程和供应链服务等扩产配套。",
            "key_questions": ["扩产配套是否形成真实订单？", "IC载板、PCB、测试设备是否成为瓶颈？", "洁净室和厂务是否先于产线投产？"],
            "segments": ["测试设备", "IC载板", "高速PCB", "洁净室", "厂务工程", "高纯工艺系统"],
            "evidence": ["配套层要用招标、中标、订单、产能建设和客户认证验证。", "PCB/载板和洁净室受益于扩产，但必须区分存储链相关收入占比。"],
            "companies": ["长川科技", "华峰测控", "精测电子", "兴森科技", "深南电路", "沪电股份", "胜宏科技", "生益科技", "至纯科技", "亚翔集成", "柏诚股份", "新莱应材"],
            "tracking_metrics": ["测试机订单", "IC载板订单", "PCB出货", "洁净室订单", "厂务订单", "高纯系统订单"],
            "metrics": metric_groups(["配套认证", "订单获取", "交付验收", "收入确认"], ["订单超预期", "交付快于预期", "收入占比提升"], ["中标公告", "扩产配套订单", "客户导入"]),
            "capex_evidence": [capex_evidence("storage_supporting_facility_pcb_test_capex", "supporting_suppliers", "supporting", ["测试设备", "PCB/IC载板", "洁净室厂务"], ["测试设备", "IC载板", "高速PCB", "洁净室"])],
            "physical_metrics": [physical_metric("storage_supporting_order_amount", "存储扩产配套订单金额", "supporting", "配套订单", ["commercialization", "trigger_signal"])],
        },
        {
            "layer_id": "infrastructure",
            "order": 7,
            "name": "基础设施层",
            "definition": "跟踪存储晶圆厂、HBM/先进封装产线、洁净厂房和国产化基础设施建设。",
            "key_questions": ["CAPEX 投向 DRAM、NAND、HBM 还是封测？", "新厂房、产线和设备进场节奏如何？", "扩产是否对应真实订单周期？"],
            "segments": ["DRAM晶圆厂", "NAND晶圆厂", "HBM封装线", "先进封装产线", "洁净厂房", "国产设备材料生态"],
            "evidence": ["基础设施层以 CAPEX、设备进场、厂房建设、投产节点为核心证据。", "未上市的长鑫/长江存储本体不映射股票，只作为证据源和需求源。"],
            "companies": ["北方华创", "中微公司", "拓荆科技", "华海清科", "芯源微", "至纯科技", "亚翔集成", "柏诚股份"],
            "tracking_metrics": ["CAPEX金额", "设备进场", "厂房建设", "产线投产", "产能爬坡", "国产化率"],
            "metrics": metric_groups(["项目备案", "设备采购", "产线投产", "产能爬坡"], ["CAPEX高于预期", "投产提前", "国产设备占比提升"], ["招标公告", "设备进场", "投产公告"]),
            "capex_evidence": [capex_evidence("storage_infrastructure_memory_fab_capex", "memory_fabs_and_infrastructure_suppliers", "infrastructure", ["DRAM晶圆厂", "NAND晶圆厂", "HBM封装线", "洁净厂房"], ["DRAM晶圆厂", "NAND晶圆厂", "HBM封装线", "洁净厂房"])],
            "physical_metrics": [physical_metric("storage_fab_capacity_wpm", "存储晶圆月产能", "infrastructure", "晶圆厂产能", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "commercialization",
            "order": 8,
            "name": "商业变现层",
            "definition": "把存储价格周期、库存收益、客户订单和成本改善落到收入、毛利和现金流。",
            "key_questions": ["涨价是否传导到收入和毛利？", "库存收益能否持续？", "客户订单和现金流是否同步改善？"],
            "segments": ["价格周期", "库存周期", "模组销售", "芯片销售", "封测服务", "设备材料订单"],
            "evidence": ["商业变现层看业绩预告、毛利率、库存周转、合约价和订单兑现。", "短期涨价不等于长期盈利，要确认库存和客户订单结构。"],
            "companies": ["佰维存储", "江波龙", "德明利", "同有科技", "朗科科技", "兆易创新", "北京君正", "澜起科技", "聚辰股份"],
            "tracking_metrics": ["业绩预告", "毛利率", "库存周转", "合约价", "现货价", "现金流"],
            "metrics": metric_groups(["价格触底", "涨价兑现", "毛利改善", "现金流改善"], ["业绩预增超预期", "毛利率改善快于预期", "库存周转改善"], ["业绩预增", "价格连续上涨", "大客户订单"]),
            "capex_evidence": [],
            "physical_metrics": [physical_metric("storage_company_gross_margin", "存储链公司毛利率", "commercialization", "商业变现", ["commercialization", "expectation_gap"])],
        },
    ],
}


LAYER_SEGMENTS = {
    "demand": ["AI服务器", "云厂商CAPEX", "智能手机", "PC/AI PC", "汽车电子", "工业控制"],
    "task": ["训练存储", "推理缓存", "端侧内存", "车规存储", "SSD容量", "内存接口"],
    "core_product": ["DRAM", "NAND Flash", "HBM", "DDR5/LPDDR", "SSD/UFS/eMMC", "NOR Flash", "内存接口芯片"],
    "foundation": ["刻蚀/薄膜/清洗设备", "涂胶显影/检测测试", "CMP设备和材料", "硅片", "电子特气", "光刻胶", "靶材", "湿电子化学品"],
    "integration": ["晶圆制造", "存储封测", "先进封装", "模组制造", "SSD整机", "测试分选"],
    "supporting": ["测试设备", "IC载板", "高速PCB", "洁净室", "厂务工程", "高纯工艺系统"],
    "infrastructure": ["DRAM晶圆厂", "NAND晶圆厂", "HBM封装线", "先进封装产线", "洁净厂房", "国产设备材料生态"],
    "commercialization": ["价格周期", "库存周期", "模组销售", "芯片销售", "封测服务", "设备材料订单"],
}


LISTED_COMPANY_MAPPINGS: list[dict[str, Any]] = [
    {"code": "000977", "name": "浪潮信息", "layer": "demand", "product": "AI服务器/存储需求"},
    {"code": "603019", "name": "中科曙光", "layer": "demand", "product": "AI服务器/智算中心存储需求"},
    {"code": "601138", "name": "工业富联", "layer": "demand", "product": "AI服务器制造/云端存储需求"},
    {"code": "000938", "name": "紫光股份", "layer": "demand", "product": "ICT基础设施/服务器存储需求"},
    {"code": "688008", "name": "澜起科技", "layer": "task", "product": "内存接口芯片/服务器内存配套"},
    {"code": "688123", "name": "聚辰股份", "layer": "task", "product": "EEPROM/存储配套芯片"},
    {"code": "603986", "name": "兆易创新", "layer": "task", "product": "NOR/DRAM关联任务"},
    {"code": "300223", "name": "北京君正", "layer": "task", "product": "车规/嵌入式存储任务"},
    {"code": "603986", "name": "兆易创新", "layer": "core_product", "product": "DRAM/NOR Flash"},
    {"code": "300223", "name": "北京君正", "layer": "core_product", "product": "车规存储/DRAM/SRAM"},
    {"code": "688766", "name": "普冉股份", "layer": "core_product", "product": "NOR Flash/EEPROM"},
    {"code": "688110", "name": "东芯股份", "layer": "core_product", "product": "NAND/NOR/DRAM小容量存储"},
    {"code": "688416", "name": "恒烁股份", "layer": "core_product", "product": "NOR Flash/MCU存储"},
    {"code": "688525", "name": "佰维存储", "layer": "core_product", "product": "存储模组/SSD"},
    {"code": "301308", "name": "江波龙", "layer": "core_product", "product": "存储模组/SSD/UFS"},
    {"code": "001309", "name": "德明利", "layer": "core_product", "product": "存储模组/SSD"},
    {"code": "000021", "name": "深科技", "layer": "core_product", "product": "存储封测/模组制造"},
    {"code": "688008", "name": "澜起科技", "layer": "core_product", "product": "DDR内存接口芯片"},
    {"code": "688123", "name": "聚辰股份", "layer": "core_product", "product": "EEPROM/汽车级存储"},
    {"code": "301666", "name": "大普微", "layer": "core_product", "product": "企业级SSD/存储控制"},
    {"code": "002371", "name": "北方华创", "layer": "foundation", "product": "半导体设备/刻蚀薄膜清洗"},
    {"code": "688012", "name": "中微公司", "layer": "foundation", "product": "刻蚀/MOCVD设备"},
    {"code": "688072", "name": "拓荆科技", "layer": "foundation", "product": "薄膜沉积设备"},
    {"code": "688037", "name": "芯源微", "layer": "foundation", "product": "涂胶显影/清洗设备"},
    {"code": "688120", "name": "华海清科", "layer": "foundation", "product": "CMP设备"},
    {"code": "688082", "name": "盛美上海", "layer": "foundation", "product": "清洗/电镀设备"},
    {"code": "300604", "name": "长川科技", "layer": "foundation", "product": "半导体测试设备"},
    {"code": "688200", "name": "华峰测控", "layer": "foundation", "product": "半导体测试设备"},
    {"code": "002409", "name": "雅克科技", "layer": "foundation", "product": "电子材料/前驱体"},
    {"code": "688019", "name": "安集科技", "layer": "foundation", "product": "CMP抛光液/材料"},
    {"code": "688126", "name": "沪硅产业", "layer": "foundation", "product": "半导体硅片"},
    {"code": "300666", "name": "江丰电子", "layer": "foundation", "product": "半导体靶材"},
    {"code": "688146", "name": "中船特气", "layer": "foundation", "product": "电子特气"},
    {"code": "300655", "name": "晶瑞电材", "layer": "foundation", "product": "光刻胶/湿电子化学品"},
    {"code": "300576", "name": "容大感光", "layer": "foundation", "product": "光刻胶/电子材料"},
    {"code": "603078", "name": "江化微", "layer": "foundation", "product": "湿电子化学品"},
    {"code": "688268", "name": "华特气体", "layer": "foundation", "product": "电子特气"},
    {"code": "688106", "name": "金宏气体", "layer": "foundation", "product": "电子大宗气体/特气"},
    {"code": "688596", "name": "正帆科技", "layer": "foundation", "product": "工艺介质供应系统"},
    {"code": "300054", "name": "鼎龙股份", "layer": "foundation", "product": "CMP抛光垫/材料"},
    {"code": "603650", "name": "彤程新材", "layer": "foundation", "product": "光刻胶/电子材料"},
    {"code": "300236", "name": "上海新阳", "layer": "foundation", "product": "电镀液/清洗液/半导体材料"},
    {"code": "300346", "name": "南大光电", "layer": "foundation", "product": "电子特气/光刻胶材料"},
    {"code": "600584", "name": "长电科技", "layer": "integration", "product": "存储封测/先进封装"},
    {"code": "002156", "name": "通富微电", "layer": "integration", "product": "集成电路封测"},
    {"code": "002185", "name": "华天科技", "layer": "integration", "product": "存储封测/先进封装"},
    {"code": "688362", "name": "甬矽电子", "layer": "integration", "product": "封装测试"},
    {"code": "688352", "name": "颀中科技", "layer": "integration", "product": "封装测试"},
    {"code": "000021", "name": "深科技", "layer": "integration", "product": "存储封测/模组制造"},
    {"code": "600667", "name": "太极实业", "layer": "integration", "product": "半导体工程/封测相关"},
    {"code": "300604", "name": "长川科技", "layer": "supporting", "product": "测试设备"},
    {"code": "688200", "name": "华峰测控", "layer": "supporting", "product": "测试设备"},
    {"code": "300567", "name": "精测电子", "layer": "supporting", "product": "半导体检测设备"},
    {"code": "002436", "name": "兴森科技", "layer": "supporting", "product": "IC载板/PCB"},
    {"code": "002916", "name": "深南电路", "layer": "supporting", "product": "IC载板/高速PCB"},
    {"code": "002463", "name": "沪电股份", "layer": "supporting", "product": "高速PCB"},
    {"code": "300476", "name": "胜宏科技", "layer": "supporting", "product": "高速PCB/AI服务器PCB"},
    {"code": "600183", "name": "生益科技", "layer": "supporting", "product": "覆铜板/电子材料"},
    {"code": "603690", "name": "至纯科技", "layer": "supporting", "product": "高纯工艺系统/洁净厂务"},
    {"code": "603929", "name": "亚翔集成", "layer": "supporting", "product": "洁净室工程"},
    {"code": "601133", "name": "柏诚股份", "layer": "supporting", "product": "洁净室/厂务工程"},
    {"code": "300260", "name": "新莱应材", "layer": "supporting", "product": "高洁净应用材料/管路"},
    {"code": "002371", "name": "北方华创", "layer": "infrastructure", "product": "存储晶圆厂扩产设备"},
    {"code": "688012", "name": "中微公司", "layer": "infrastructure", "product": "存储晶圆厂扩产设备"},
    {"code": "688072", "name": "拓荆科技", "layer": "infrastructure", "product": "存储晶圆厂薄膜设备"},
    {"code": "688120", "name": "华海清科", "layer": "infrastructure", "product": "存储晶圆厂CMP设备"},
    {"code": "688037", "name": "芯源微", "layer": "infrastructure", "product": "存储晶圆厂涂胶显影/清洗"},
    {"code": "603690", "name": "至纯科技", "layer": "infrastructure", "product": "高纯工艺系统/厂务"},
    {"code": "603929", "name": "亚翔集成", "layer": "infrastructure", "product": "洁净室工程"},
    {"code": "601133", "name": "柏诚股份", "layer": "infrastructure", "product": "洁净室/厂务工程"},
    {"code": "688596", "name": "正帆科技", "layer": "infrastructure", "product": "工艺介质供应系统"},
    {"code": "688525", "name": "佰维存储", "layer": "commercialization", "product": "存储产品销售/价格周期"},
    {"code": "301308", "name": "江波龙", "layer": "commercialization", "product": "存储产品销售/价格周期"},
    {"code": "001309", "name": "德明利", "layer": "commercialization", "product": "存储模组/SSD销售"},
    {"code": "300302", "name": "同有科技", "layer": "commercialization", "product": "存储系统"},
    {"code": "300042", "name": "朗科科技", "layer": "commercialization", "product": "存储产品"},
    {"code": "603986", "name": "兆易创新", "layer": "commercialization", "product": "存储芯片收入/价格周期"},
    {"code": "300223", "name": "北京君正", "layer": "commercialization", "product": "存储芯片收入/车规周期"},
    {"code": "688008", "name": "澜起科技", "layer": "commercialization", "product": "内存接口芯片收入"},
    {"code": "688123", "name": "聚辰股份", "layer": "commercialization", "product": "存储配套芯片收入"},
    {"code": "301666", "name": "大普微", "layer": "commercialization", "product": "企业级SSD/存储控制销售"},
]


def layer_node_id(layer_id: str) -> str:
    return f"{CHAIN_ID}_{layer_id}"


def build_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for layer in STORAGE_TEMPLATE["layers"]:
        nodes.append({
            "node_id": layer_node_id(layer["layer_id"]),
            "theme_id": THEME_ID,
            "chain_id": CHAIN_ID,
            "parent_node_id": None if layer["order"] == 1 else layer_node_id(LAYER_IDS[layer["order"] - 2]),
            "level": f"L{layer['order']}",
            "name": layer["name"],
            "node_type": "complex_chain_layer",
            "keywords": layer["segments"],
            "policy_weight": 3,
        })
    return nodes


def mapping_id(code: str, layer_id: str, product: str) -> str:
    token = "".join(ch for ch in product.upper() if ch.isalnum())[:20] or layer_id.upper()
    return f"STOR-{code}-{layer_id.upper()}-{token}"


def mapping_path(layer_id: str, product: str) -> list[dict[str, str]]:
    layer = next(item for item in STORAGE_TEMPLATE["layers"] if item["layer_id"] == layer_id)
    return [
        {"level": "L1", "name": "未来产业主攻方向"},
        {"level": "L2", "name": "存储芯片"},
        {"level": "L3", "name": "存储芯片复杂产业链"},
        {"level": f"L{layer['order']}", "id": layer_node_id(layer_id), "name": layer["name"]},
        {"level": "segment", "name": ";".join(LAYER_SEGMENTS[layer_id])},
        {"level": "product", "name": product},
    ]


def update_template_file() -> bool:
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    templates = [item for item in data.get("templates", []) if item.get("template_id") != CHAIN_ID]
    templates.append(STORAGE_TEMPLATE)
    data["templates"] = templates
    before = TEMPLATE_PATH.read_text(encoding="utf-8")
    after = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if before == after:
        return False
    TEMPLATE_PATH.write_text(after, encoding="utf-8")
    return True


def persist(pg_url: str) -> dict[str, int]:
    nodes = build_nodes()
    counts = {
        "industry_themes": 0,
        "supply_chain_bom_nodes": 0,
        "chain_nodes": 0,
        "supply_chain_bom_edges": 0,
        "company_business_segments": 0,
        "business_tag_mapping": 0,
    }
    with psycopg2.connect(pg_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
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
                (THEME_ID, THEME_NAME, "复杂产业链", Json(["存储芯片", "DRAM", "NAND", "HBM", "先进封装"]), 4),
            )
            counts["industry_themes"] += 1

            for node in nodes:
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
                        node["node_id"],
                        node["theme_id"],
                        node["chain_id"],
                        node["parent_node_id"],
                        node["level"],
                        node["name"],
                        node["node_type"],
                        Json(node["keywords"]),
                        node["policy_weight"],
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
                        node["node_id"],
                        node["theme_id"],
                        node["name"],
                        int(node["level"][1:]),
                        node["parent_node_id"],
                        Json([]),
                        Json([]),
                        Json({"note": "存储芯片复杂产业链8层节点", "chain_id": CHAIN_ID, "segments": node["keywords"]}),
                        Json({"status": "pending_evidence_review", "note": "竞争格局需公告/研报补证"}),
                    ),
                )
                counts["chain_nodes"] += 1

            for idx in range(len(nodes) - 1):
                edge_id = f"{nodes[idx]['node_id']}->{nodes[idx + 1]['node_id']}"
                cur.execute(
                    """
                    INSERT INTO supply_chain_bom_edges (edge_id, from_node_id, to_node_id, relation)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (edge_id) DO UPDATE SET
                        from_node_id = EXCLUDED.from_node_id,
                        to_node_id = EXCLUDED.to_node_id,
                        relation = EXCLUDED.relation
                    """,
                    (edge_id, nodes[idx]["node_id"], nodes[idx + 1]["node_id"], "8层复杂产业链顺序链路"),
                )
                counts["supply_chain_bom_edges"] += 1

            for item in LISTED_COMPANY_MAPPINGS:
                layer_id = item["layer"]
                product = item["product"]
                segment_id = f"{CHAIN_ID}_{layer_id}_{item['code']}"
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
                        "manual_storage_chain_seed",
                        mapping_id(item["code"], layer_id, product),
                        "pending_review",
                        Json({
                            "chain_id": CHAIN_ID,
                            "layer_id": layer_id,
                            "company_name": item["name"],
                            "requires_original_evidence": True,
                        }),
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (mapping_id) DO UPDATE SET
                        code = EXCLUDED.code,
                        business_segment_id = EXCLUDED.business_segment_id,
                        node_id = EXCLUDED.node_id,
                        theme_id = EXCLUDED.theme_id,
                        chain_id = EXCLUDED.chain_id,
                        tag_name = EXCLUDED.tag_name,
                        l1_l8_path = EXCLUDED.l1_l8_path,
                        revenue_ratio = EXCLUDED.revenue_ratio,
                        gross_profit_ratio = EXCLUDED.gross_profit_ratio,
                        confidence = EXCLUDED.confidence,
                        status = EXCLUDED.status,
                        evidence_ids = EXCLUDED.evidence_ids,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        mapping_id(item["code"], layer_id, product),
                        item["code"],
                        segment_id,
                        layer_node_id(layer_id),
                        THEME_ID,
                        CHAIN_ID,
                        STORAGE_TEMPLATE["layers"][LAYER_IDS.index(layer_id)]["name"],
                        json.dumps(mapping_path(layer_id, product), ensure_ascii=False),
                        None,
                        None,
                        item.get("confidence", 0.72),
                        item.get("status", "pending_review"),
                        json.dumps(["manual_storage_chain_seed_requires_original_evidence"], ensure_ascii=False),
                    ),
                )
                counts["business_tag_mapping"] += 1
        conn.commit()
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--skip-db", action="store_true")
    parser.add_argument("--skip-template", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {"template_updated": False, "persist_counts": {}}
    if not args.skip_template:
        result["template_updated"] = update_template_file()
    if not args.skip_db:
        result["persist_counts"] = persist(args.pg_url)
    result["unique_companies"] = len({item["code"] for item in LISTED_COMPANY_MAPPINGS})
    result["mapping_rows"] = len(LISTED_COMPANY_MAPPINGS)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
