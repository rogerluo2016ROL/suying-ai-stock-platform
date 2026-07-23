#!/usr/bin/env python3
"""Materialize the near-memory-computing complex chain template and listed-company mappings.

This seed is intentionally conservative: it maps listed companies to the
near-memory-computing chain layer they can plausibly support, but keeps
mappings in ``pending_review`` until original filings / IR / research
evidence is attached.
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

THEME_ID = "future_industry_near_memory_computing"
CHAIN_ID = "near_memory_computing"
THEME_NAME = "近存计算复杂产业链"


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


NEAR_MEMORY_TEMPLATE: dict[str, Any] = {
    "template_id": CHAIN_ID,
    "name": "近存计算复杂产业链路模板",
    "description": "面向存算一体(CIM)、HBM-PIM/AiM、CXL内存池化、近数据处理(NDP)等近存计算方向，沿用复杂科技 8 层拆解逻辑，突出存储墙瓶颈、国产 HBM 突破、先进封装集成和商业变现证据。",
    "example_theme": "近存计算",
    "macro_context": macro_context(),
    "layers": [
        {
            "layer_id": "demand",
            "order": 1,
            "name": "需求层",
            "definition": "识别 AI 大模型推理带宽瓶颈(存储墙)、云厂商 CAPEX、端侧 AI、车载计算和数据库加速等真实近存计算需求来源。",
            "key_questions": ["需求来自 AI 推理存储墙、端侧 AI 还是车载计算？", "云厂商 CAPEX 是否传导到 HBM/存算采购？", "数据库加速是否形成真实采购订单？"],
            "segments": ["AI推理带宽", "云厂商CAPEX", "端侧AI", "车载计算", "数据库加速", "智算中心"],
            "evidence": ["AI 大模型推理的存储墙(带宽/功耗)是近存计算需求层核心证据。", "需求必须由推理服务器出货、云 CAPEX 或端侧 SoC 出货验证，不能单看概念热度。"],
            "companies": ["浪潮信息", "中科曙光", "工业富联"],
            "tracking_metrics": ["AI推理服务器出货", "云厂商CAPEX", "端侧AI SoC出货", "车载智驾渗透率", "数据库加速采购"],
            "metrics": metric_groups(["推理算力采购", "端侧AI放量", "车载定点", "数据库加速采购"], ["推理带宽需求高于预期", "云CAPEX上修", "端侧AI出货超预期"], ["云厂商CAPEX上修", "AI推理订单放量", "端侧AI SoC放量"]),
            "capex_evidence": [capex_evidence("nmc_demand_cloud_inference_capex", "cloud_and_ai_inference_customers", "demand", ["AI推理服务器采购", "数据中心CAPEX"], ["AI推理带宽", "云厂商CAPEX"])],
            "physical_metrics": [physical_metric("nmc_ai_inference_server_shipments", "AI推理服务器出货量", "demand", "AI推理带宽", ["commercialization", "expectation_gap"])],
        },
        {
            "layer_id": "task",
            "order": 2,
            "name": "任务层",
            "definition": "把近存计算需求拆成打破存储墙(带宽/功耗)、绕开先进制程限制、国产 HBM 突破和 CXL 生态标准化等任务。",
            "key_questions": ["任务需要高带宽、低功耗还是低延迟？", "存算一体能否绕开先进制程限制？", "国产 HBM 和 CXL 标准化进度如何？"],
            "segments": ["带宽提升", "功耗降低", "国产HBM突破", "CXL生态标准化", "先进制程替代", "近数据处理"],
            "evidence": ["任务层要看存算一体算力密度、能效比(TOPS/W)、国产 HBM 进度和 CXL 标准落地。", "同样叫近存计算，数据中心推理、端侧和车载对应的技术路线不同。"],
            "companies": ["澜起科技", "恒烁股份", "芯原股份", "兆易创新"],
            "tracking_metrics": ["存算一体算力密度", "能效比TOPS/W", "国产HBM进度", "CXL标准版本", "HBM-PIM送样"],
            "metrics": metric_groups(["样品验证", "客户认证", "批量导入", "平台绑定"], ["算力密度高于预期", "国产HBM进度提前", "CXL生态落地快于预期"], ["国产HBM突破", "CXL标准落地", "存算芯片客户认证"]),
            "capex_evidence": [],
            "physical_metrics": [physical_metric("nmc_cim_tops_per_watt", "存算一体能效比", "task", "功耗降低", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "core_product",
            "order": 3,
            "name": "核心产品层",
            "definition": "识别直接承载近存计算价值的核心产品：存算一体芯片(CIM)、HBM-PIM/AiM、CXL 内存控制器和计算存储(NDP SSD)。",
            "key_questions": ["产品是存算芯片、PIM 内存、CXL 控制器还是 NDP SSD？", "流片和定点能否进入收入？", "国产存算路线在 ReRAM/SRAM/DRAM 哪条介质突破？"],
            "segments": ["存算一体芯片(CIM)", "HBM-PIM/AiM", "CXL内存控制器", "计算存储(NDP SSD)", "ReRAM/MRAM存算芯片", "端侧存算SoC"],
            "evidence": ["核心产品层要看流片、送样、定点、出货和毛利率。", "未上市一级公司知存科技、后摩智能、亿铸科技、苹芯科技是存算一体芯片的重要主体，只作为证据源和竞争格局参照，不映射股票。"],
            "companies": ["澜起科技", "恒烁股份", "兆易创新", "佰维存储", "江波龙"],
            "tracking_metrics": ["存算芯片流片", "HBM-PIM送样", "CXL MXC出货", "NDP SSD定点", "存算芯片定点"],
            "metrics": metric_groups(["流片成功", "客户送样", "定点获取", "批量出货"], ["流片进度快于预期", "定点数量超预期", "CXL MXC出货超预期"], ["存算芯片流片", "车载/端侧定点", "CXL MXC批量出货"]),
            "capex_evidence": [capex_evidence("nmc_core_product_cim_capex", "cim_and_pim_chip_companies", "core_product", ["存算一体芯片研发", "HBM-PIM产线", "CXL控制器研发"], ["存算一体芯片(CIM)", "HBM-PIM/AiM", "CXL内存控制器"])],
            "physical_metrics": [physical_metric("nmc_cim_tapeout_count", "存算一体芯片流片数", "core_product", "存算一体芯片(CIM)", ["commercialization", "trigger_signal"])],
        },
        {
            "layer_id": "foundation",
            "order": 4,
            "name": "底层支撑层",
            "definition": "拆解决定近存计算落地的存储颗粒、ReRAM/MRAM 新型存储介质和国产 HBM 突破能力。",
            "key_questions": ["长鑫/长江存储的颗粒能否支撑国产 HBM？", "ReRAM/MRAM 介质良率和产能如何？", "介质突破能否传导到存算芯片量产？"],
            "segments": ["DRAM存储颗粒", "NAND存储颗粒", "HBM颗粒", "ReRAM介质", "MRAM介质", "新型存储材料"],
            "evidence": ["底层支撑层要用颗粒产能、介质良率、产线导入和国产化率验证。", "未上市的长鑫/长江存储本体不映射股票，只作为证据源和需求源。"],
            "companies": ["恒烁股份", "兆易创新", "雅克科技"],
            "tracking_metrics": ["DRAM颗粒产能", "NAND颗粒产能", "国产HBM进展", "ReRAM良率", "MRAM产线导入"],
            "metrics": metric_groups(["介质送样", "产线导入", "良率爬坡", "国产替代放量"], ["国产HBM进展快于预期", "ReRAM良率超预期", "介质产能超预期"], ["国产HBM量产", "介质产线投产", "颗粒扩产订单"]),
            "capex_evidence": [capex_evidence("nmc_foundation_memory_media_capex", "memory_media_and_idm_companies", "foundation", ["存储颗粒扩产", "ReRAM/MRAM产线", "国产HBM产线"], ["DRAM存储颗粒", "HBM颗粒", "ReRAM介质"])],
            "physical_metrics": [physical_metric("nmc_domestic_hbm_progress", "国产HBM量产进度", "foundation", "HBM颗粒", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "integration",
            "order": 5,
            "name": "集成层",
            "definition": "跟踪 2.5D/3D 先进封装、混合键合集成、UCIe/Chiplet IP 和 3D IC EDA，把存储介质与计算 die 集成为可用产品。",
            "key_questions": ["混合键合是否支撑存算/HBM 堆叠量产？", "UCIe/Chiplet IP 是否形成授权收入？", "3D IC EDA 工具链是否完备？"],
            "segments": ["2.5D封装", "3D封装", "混合键合集成", "UCIe/Chiplet IP", "3D IC EDA", "TSV集成"],
            "evidence": ["集成层看先进封装订单、混合键合产线导入、IP 授权和 EDA 工具落地。", "封测厂必须区分近存计算相关收入占比，不能只因先进封装概念入选。"],
            "companies": ["长电科技", "通富微电", "华天科技", "甬矽电子", "芯原股份", "华大九天", "概伦电子"],
            "tracking_metrics": ["先进封装订单", "混合键合产线导入", "Chiplet IP授权", "3D IC EDA客户数", "封装良率"],
            "metrics": metric_groups(["封装导入", "IP授权", "EDA客户落地", "收入毛利兑现"], ["混合键合订单超预期", "IP授权快于预期", "良率提升"], ["混合键合产线导入", "大客户封装订单", "3D IC EDA签约"]),
            "capex_evidence": [capex_evidence("nmc_integration_advanced_packaging_capex", "advanced_packaging_and_ip_companies", "integration", ["2.5D/3D封装扩产", "混合键合产线", "Chiplet集成"], ["2.5D封装", "3D封装", "混合键合集成"])],
            "physical_metrics": [physical_metric("nmc_hybrid_bonding_line_adoption", "混合键合产线导入数", "integration", "混合键合集成", ["commercialization", "trigger_signal"])],
        },
        {
            "layer_id": "supporting",
            "order": 6,
            "name": "配套层",
            "definition": "识别混合键合设备、TSV 刻蚀沉积、CMP、电镀清洗、HBM 前驱体、封装填料、载板和玻璃基板等扩产配套。",
            "key_questions": ["混合键合/TSV/CMP 设备是否形成真实订单？", "HBM 前驱体和封装填料是否通过认证？", "载板和玻璃基板是否成为瓶颈？"],
            "segments": ["混合键合设备", "TSV刻蚀沉积设备", "CMP设备", "电镀清洗设备", "HBM前驱体", "封装填料", "IC载板", "玻璃基板/TGV"],
            "evidence": ["配套层要用招标、中标、订单、材料认证和产线导入验证。", "设备材料公司必须能对应 HBM/先进封装/存算扩产，不能只因半导体概念入选。"],
            "companies": ["拓荆科技", "北方华创", "中微公司", "华海清科", "盛美上海", "雅克科技", "联瑞新材", "壹石通", "兴森科技", "深南电路", "沃格光电"],
            "tracking_metrics": ["混合键合设备订单", "TSV设备订单", "CMP设备订单", "前驱体认证", "载板订单", "玻璃基板送样"],
            "metrics": metric_groups(["送样认证", "客户导入", "批量订单", "国产替代放量"], ["订单高于预期", "认证快于预期", "国产化率提升快于预期"], ["混合键合设备订单", "材料认证通过", "载板/玻璃基板定点"]),
            "capex_evidence": [capex_evidence("nmc_supporting_equipment_material_capex", "equipment_and_material_suppliers", "supporting", ["键合/刻蚀/CMP设备", "HBM材料", "载板玻璃基板"], ["混合键合设备", "CMP设备", "HBM前驱体", "IC载板"])],
            "physical_metrics": [physical_metric("nmc_hybrid_bonding_equipment_orders", "混合键合设备订单", "supporting", "混合键合设备", ["expectation_gap", "trigger_signal"])],
        },
        {
            "layer_id": "infrastructure",
            "order": 7,
            "name": "基础设施层",
            "definition": "跟踪数据中心/智算中心建设、CXL 交换机与内存池化基础设施和内存接口芯片配套。",
            "key_questions": ["智算中心 CAPEX 是否传导到内存池化采购？", "CXL 交换机和内存池化是否规模部署？", "内存接口芯片(RCD/MRCD/CKD/MXC)出货节奏如何？"],
            "segments": ["数据中心/智算中心", "CXL交换机", "内存池化", "内存接口芯片", "先进封装产线"],
            "evidence": ["基础设施层以智算中心 CAPEX、CXL 部署、接口芯片出货为核心证据。", "澜起科技的 RCD/MRCD/CKD/MXC 出货是 CXL 生态落地的关键跟踪信号。"],
            "companies": ["澜起科技", "浪潮信息", "中科曙光"],
            "tracking_metrics": ["智算中心CAPEX", "CXL交换机部署", "内存池化规模", "RCD/MRCD/CKD出货", "MXC出货"],
            "metrics": metric_groups(["项目备案", "设备采购", "CXL部署", "接口芯片放量"], ["CAPEX高于预期", "CXL部署快于预期", "MXC出货超预期"], ["智算中心招标", "CXL内存池化部署", "MXC批量出货"]),
            "capex_evidence": [capex_evidence("nmc_infrastructure_datacenter_capex", "datacenter_and_cxl_infrastructure", "infrastructure", ["智算中心建设", "CXL内存池化", "先进封装产线"], ["数据中心/智算中心", "内存池化", "先进封装产线"])],
            "physical_metrics": [physical_metric("nmc_cxl_mxc_shipments", "CXL MXC芯片出货量", "infrastructure", "内存接口芯片", ["commercialization", "trigger_signal"])],
        },
        {
            "layer_id": "commercialization",
            "order": 8,
            "name": "商业变现层",
            "definition": "把端侧 AI 量产、数据中心推理采购、车载定点和模组出货落到收入、毛利和现金流。",
            "key_questions": ["端侧 AI(TWS/视觉)存算芯片是否量产出货？", "数据中心推理采购是否兑现为订单？", "车载定点和模组出货是否同步改善毛利？"],
            "segments": ["端侧AI量产", "数据中心推理采购", "车载定点", "存储模组出货", "IP授权", "EDA授权"],
            "evidence": ["商业变现层看业绩预告、出货量、定点公告、模组出货和现金流。", "跟踪信号：国产 HBM 量产时间表、混合键合设备订单、CXL MXC 出货、存算芯片流片/定点。"],
            "companies": ["兆易创新", "江波龙", "佰维存储", "澜起科技", "芯原股份"],
            "tracking_metrics": ["业绩预告", "存算芯片出货", "模组出货", "定点公告", "毛利率", "现金流"],
            "metrics": metric_groups(["端侧量产出货", "推理采购兑现", "定点转量产", "毛利改善"], ["业绩预增超预期", "出货高于预期", "定点数量超预期"], ["国产HBM量产时间表", "混合键合设备订单", "CXL MXC出货", "存算芯片流片/定点"]),
            "capex_evidence": [],
            "physical_metrics": [physical_metric("nmc_company_gross_margin", "近存计算链公司毛利率", "commercialization", "商业变现", ["commercialization", "expectation_gap"])],
        },
    ],
}


LAYER_SEGMENTS = {
    "demand": ["AI推理带宽", "云厂商CAPEX", "端侧AI", "车载计算", "数据库加速", "智算中心"],
    "task": ["带宽提升", "功耗降低", "国产HBM突破", "CXL生态标准化", "先进制程替代", "近数据处理"],
    "core_product": ["存算一体芯片(CIM)", "HBM-PIM/AiM", "CXL内存控制器", "计算存储(NDP SSD)", "ReRAM/MRAM存算芯片", "端侧存算SoC"],
    "foundation": ["DRAM存储颗粒", "NAND存储颗粒", "HBM颗粒", "ReRAM介质", "MRAM介质", "新型存储材料"],
    "integration": ["2.5D封装", "3D封装", "混合键合集成", "UCIe/Chiplet IP", "3D IC EDA", "TSV集成"],
    "supporting": ["混合键合设备", "TSV刻蚀沉积设备", "CMP设备", "电镀清洗设备", "HBM前驱体", "封装填料", "IC载板", "玻璃基板/TGV"],
    "infrastructure": ["数据中心/智算中心", "CXL交换机", "内存池化", "内存接口芯片", "先进封装产线"],
    "commercialization": ["端侧AI量产", "数据中心推理采购", "车载定点", "存储模组出货", "IP授权", "EDA授权"],
}


LISTED_COMPANY_MAPPINGS: list[dict[str, Any]] = [
    {"code": "000977", "name": "浪潮信息", "layer": "demand", "product": "AI推理服务器/智算中心需求"},
    {"code": "603019", "name": "中科曙光", "layer": "demand", "product": "AI服务器/智算中心需求"},
    {"code": "601138", "name": "工业富联", "layer": "demand", "product": "AI服务器制造/云端推理需求"},
    {"code": "688008", "name": "澜起科技", "layer": "task", "product": "CXL生态/内存接口任务"},
    {"code": "688416", "name": "恒烁股份", "layer": "task", "product": "存算一体/NOR存内计算任务"},
    {"code": "688008", "name": "澜起科技", "layer": "core_product", "product": "CXL内存控制器/MXC"},
    {"code": "688416", "name": "恒烁股份", "layer": "core_product", "product": "存算一体芯片/NOR存内计算"},
    {"code": "603986", "name": "兆易创新", "layer": "core_product", "product": "存储芯片/存算相关"},
    {"code": "688525", "name": "佰维存储", "layer": "core_product", "product": "存储模组/先进封测"},
    {"code": "301308", "name": "江波龙", "layer": "core_product", "product": "存储模组/企业级存储"},
    {"code": "688416", "name": "恒烁股份", "layer": "foundation", "product": "ReRAM/MRAM介质/NOR"},
    {"code": "603986", "name": "兆易创新", "layer": "foundation", "product": "DRAM/NOR存储颗粒"},
    {"code": "002409", "name": "雅克科技", "layer": "foundation", "product": "HBM前驱体/电子材料"},
    {"code": "600584", "name": "长电科技", "layer": "integration", "product": "先进封装/2.5D/3D"},
    {"code": "002156", "name": "通富微电", "layer": "integration", "product": "先进封装/Chiplet封测"},
    {"code": "002185", "name": "华天科技", "layer": "integration", "product": "先进封装/3D封装"},
    {"code": "688362", "name": "甬矽电子", "layer": "integration", "product": "先进封装/封装测试"},
    {"code": "688521", "name": "芯原股份", "layer": "integration", "product": "UCIe/Chiplet IP"},
    {"code": "301269", "name": "华大九天", "layer": "integration", "product": "3D IC EDA"},
    {"code": "688206", "name": "概伦电子", "layer": "integration", "product": "EDA/3D IC仿真"},
    {"code": "688072", "name": "拓荆科技", "layer": "supporting", "product": "混合键合设备/薄膜沉积"},
    {"code": "002371", "name": "北方华创", "layer": "supporting", "product": "TSV刻蚀/沉积设备"},
    {"code": "688012", "name": "中微公司", "layer": "supporting", "product": "TSV刻蚀设备"},
    {"code": "688120", "name": "华海清科", "layer": "supporting", "product": "CMP设备"},
    {"code": "688082", "name": "盛美上海", "layer": "supporting", "product": "电镀/清洗设备"},
    {"code": "002409", "name": "雅克科技", "layer": "supporting", "product": "HBM前驱体"},
    {"code": "688300", "name": "联瑞新材", "layer": "supporting", "product": "封装填料/硅微粉"},
    {"code": "688733", "name": "壹石通", "layer": "supporting", "product": "封装填料/Low-α材料"},
    {"code": "002436", "name": "兴森科技", "layer": "supporting", "product": "IC载板"},
    {"code": "002916", "name": "深南电路", "layer": "supporting", "product": "IC载板/高速PCB"},
    {"code": "603773", "name": "沃格光电", "layer": "supporting", "product": "玻璃基板/TGV"},
    {"code": "688008", "name": "澜起科技", "layer": "infrastructure", "product": "内存接口芯片RCD/MRCD/CKD/MXC"},
    {"code": "000977", "name": "浪潮信息", "layer": "infrastructure", "product": "智算中心基础设施"},
    {"code": "603019", "name": "中科曙光", "layer": "infrastructure", "product": "智算中心基础设施"},
    {"code": "603986", "name": "兆易创新", "layer": "commercialization", "product": "存储芯片收入/模组出货"},
    {"code": "301308", "name": "江波龙", "layer": "commercialization", "product": "存储模组出货"},
    {"code": "688525", "name": "佰维存储", "layer": "commercialization", "product": "存储模组出货"},
    {"code": "688008", "name": "澜起科技", "layer": "commercialization", "product": "内存接口芯片收入"},
    {"code": "688521", "name": "芯原股份", "layer": "commercialization", "product": "IP授权收入"},
]


OBSOLETE_MAPPING_KEYS: list[tuple[str, str, str]] = []


def layer_node_id(layer_id: str) -> str:
    return f"{CHAIN_ID}_{layer_id}"


def build_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for layer in NEAR_MEMORY_TEMPLATE["layers"]:
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
    return f"NMC-{code}-{layer_id.upper()}-{token}"


def mapping_path(layer_id: str, product: str) -> list[dict[str, str]]:
    layer = next(item for item in NEAR_MEMORY_TEMPLATE["layers"] if item["layer_id"] == layer_id)
    return [
        {"level": "L1", "name": "未来产业主攻方向"},
        {"level": "L2", "name": "近存计算"},
        {"level": "L3", "name": "近存计算复杂产业链"},
        {"level": f"L{layer['order']}", "id": layer_node_id(layer_id), "name": layer["name"]},
        {"level": "segment", "name": ";".join(LAYER_SEGMENTS[layer_id])},
        {"level": "product", "name": product},
    ]


def update_template_file() -> bool:
    """Register NEAR_MEMORY_TEMPLATE into industry_chain_templates.json.

    Idempotent: if the template already exists and is unchanged, the file is
    left untouched. When inserting a new template, the JSON block is spliced
    in textually so the rest of the file keeps its original formatting.
    """
    before = TEMPLATE_PATH.read_text(encoding="utf-8")
    data = json.loads(before)
    existing = [item for item in data.get("templates", []) if item.get("template_id") == CHAIN_ID]
    if existing and existing[0] == NEAR_MEMORY_TEMPLATE:
        return False
    if existing:
        templates = [item for item in data.get("templates", []) if item.get("template_id") != CHAIN_ID]
        templates.append(NEAR_MEMORY_TEMPLATE)
        data["templates"] = templates
        after = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if before == after:
            return False
        TEMPLATE_PATH.write_text(after, encoding="utf-8")
        return True
    block = json.dumps(NEAR_MEMORY_TEMPLATE, ensure_ascii=False, indent=2)
    block = "\n".join("    " + line for line in block.splitlines())
    anchor = "\n  ]\n}"
    idx = before.rfind(anchor)
    if idx == -1:
        raise RuntimeError("cannot locate templates array terminator in industry_chain_templates.json")
    after = before[:idx] + ",\n" + block + before[idx:]
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
                (THEME_ID, THEME_NAME, "复杂产业链", Json(["近存计算", "存算一体", "HBM-PIM", "CXL", "先进封装"]), 4),
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
                        Json({"note": "近存计算复杂产业链8层节点", "chain_id": CHAIN_ID, "segments": node["keywords"]}),
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

            for code, layer_id, product in OBSOLETE_MAPPING_KEYS:
                cur.execute(
                    "DELETE FROM business_tag_mapping WHERE mapping_id = %s",
                    (mapping_id(code, layer_id, product),),
                )

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
                        "manual_near_memory_chain_seed",
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
                        NEAR_MEMORY_TEMPLATE["layers"][LAYER_IDS.index(layer_id)]["name"],
                        json.dumps(mapping_path(layer_id, product), ensure_ascii=False),
                        None,
                        None,
                        item.get("confidence", 0.72),
                        item.get("status", "pending_review"),
                        json.dumps(["manual_near_memory_chain_seed_requires_original_evidence"], ensure_ascii=False),
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
