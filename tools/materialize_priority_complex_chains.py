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
    "lithography_equipment_chain": {
        "theme_id": "future_industry_lithography_equipment_chain",
        "theme_name": "光刻机/光刻工艺复杂产业链",
        "name": "光刻机/光刻工艺复杂产业链路模板",
        "description": "围绕光刻整机、光源光学、掩膜版、光刻胶、涂胶显影、检测量测、洁净厂务和晶圆厂验证，拆解国产替代和商业化证据。",
        "example_theme": "光刻机/光刻工艺",
        "layers": {
            "demand": ["晶圆厂扩产", "国产替代", "先进制程", "成熟制程", "存储扩产"],
            "task": ["线宽控制", "套刻精度", "吞吐量", "良率提升", "客户验证"],
            "core_product": ["ArF浸没光刻机", "ArF干式光刻机", "KrF光刻机", "i-line光刻机", "涂胶显影设备"],
            "foundation": ["光学元件", "光学晶体", "掩膜版", "光刻胶", "湿电子化学品"],
            "integration": ["光机电集成", "涂胶显影", "曝光工艺验证", "检测量测", "套刻控制"],
            "supporting": ["洁净室", "高纯工艺系统", "电子特气", "真空温控", "减振平台"],
            "infrastructure": ["晶圆厂光刻产线", "国产设备验证线", "掩膜版产线", "光刻胶认证平台", "中试线"],
            "commercialization": ["客户认证", "设备订单", "材料放量", "掩膜版订单", "收入毛利兑现"],
        },
    },
    "data_ai_application_commercialization": {
        "theme_id": "future_industry_data_ai_app_commercialization",
        "theme_name": "数据要素/AI应用商业化复杂产业链",
        "name": "数据要素/AI应用商业化复杂产业链路模板",
        "description": "围绕数据确权、数据资源入表、行业数据运营、AI办公、AI金融、AI政企和模型应用付费，拆解从数据供给到商业化收入兑现的链路。",
        "example_theme": "数据要素/AI应用商业化",
        "layers": {
            "demand": ["政企数字化", "数据资产入表", "内容生成AIGC", "办公与生产力", "软件开发提效", "企业服务智能化", "垂直行业应用", "端侧AI硬件", "AI for Science"],
            "task": ["数据治理", "数据确权", "模型调用", "应用集成", "付费转化"],
            "core_product": ["行业大模型", "AI办公软件", "AIGC内容生成工具", "代码生成/开发工具", "智能客服/企业SaaS", "垂直行业AI产品", "端侧AI终端", "数据交易平台", "智能投研/金融IT", "知识管理"],
            "foundation": ["算力资源", "数据资源", "向量数据库", "安全可信", "云原生中间件"],
            "integration": ["政企系统集成", "行业SaaS", "金融IT交付", "数据运营", "AI Agent工作流"],
            "supporting": ["数据安全", "身份认证", "隐私计算", "运维服务", "咨询实施"],
            "infrastructure": ["数据交易所", "政务云", "企业数据湖", "智算中心", "行业知识库"],
            "commercialization": ["订阅收入", "API调用收入", "项目订单", "数据运营分成", "续费率", "内容/流量变现"],
        },
    },
    "defense_informatization_unmanned": {
        "theme_id": "future_industry_defense_informatization_unmanned",
        "theme_name": "军工信息化/无人作战复杂产业链",
        "name": "军工信息化/无人作战复杂产业链路模板",
        "description": "围绕军工信息化、无人机、精确制导、雷达通信、红外探测、北斗导航和新材料，拆解无人作战体系的装备、感知、通信和交付兑现。",
        "example_theme": "军工信息化/无人作战",
        "layers": {
            "demand": ["国防装备升级", "无人化作战", "低空安全", "远程精确打击", "体系化联合作战"],
            "task": ["侦察感知", "导航制导", "指挥通信", "自主控制", "打击评估"],
            "core_product": ["无人机", "雷达系统", "红外探测", "北斗导航", "航空航天电子"],
            "foundation": ["碳纤维复材", "高温合金", "石英材料", "连接器", "微波射频"],
            "integration": ["装备总装", "任务载荷集成", "航电系统", "地面站系统", "仿真测试"],
            "supporting": ["军工电子元件", "惯导/传感", "卫星遥感", "电源模块", "可靠性测试"],
            "infrastructure": ["军工产线", "试验验证场", "卫星导航系统", "指挥信息网络", "低空监管平台"],
            "commercialization": ["军品订单", "型号定型", "批产交付", "外贸订单", "收入确认"],
        },
    },
    "intelligent_driving_v2x": {
        "theme_id": "future_industry_intelligent_driving_v2x",
        "theme_name": "智能驾驶/车路云复杂产业链",
        "name": "智能驾驶/车路云复杂产业链路模板",
        "description": "围绕城市NOA、车路云一体化、智能座舱、传感器、线控底盘、路侧感知和云控平台，拆解智能驾驶从单车智能到基础设施协同的链路。",
        "example_theme": "智能驾驶/车路云",
        "layers": {
            "demand": ["城市NOA渗透", "车路云试点", "新能源车智能化", "交通治理", "Robotaxi示范"],
            "task": ["环境感知", "决策规划", "车辆控制", "高精定位", "路云协同"],
            "core_product": ["智能驾驶域控", "车载操作系统", "高精地图", "激光雷达/毫米波雷达", "线控底盘"],
            "foundation": ["车规芯片", "传感器", "摄像头模组", "通信模组", "算法软件"],
            "integration": ["整车集成", "座舱集成", "车路协同系统", "云控平台", "智能交通集成"],
            "supporting": ["测试验证", "数据闭环", "道路感知设备", "车载连接器", "车规制造"],
            "infrastructure": ["路侧单元", "智慧道路", "交通云平台", "充电补能网络", "示范运营区"],
            "commercialization": ["定点订单", "车型放量", "路侧项目中标", "软件订阅", "运营收入"],
        },
    },
    "controlled_fusion_materials": {
        "theme_id": "future_industry_controlled_fusion_materials",
        "theme_name": "可控核聚变材料复杂产业链",
        "name": "可控核聚变材料复杂产业链路模板",
        "description": "围绕超导磁体、第一壁材料、钨钼钽锆等难熔金属、真空低温、电源控制和实验装置建设，拆解可控核聚变材料与装备国产化链路。",
        "example_theme": "可控核聚变材料",
        "layers": {
            "demand": ["聚变实验装置", "能源安全", "强磁场应用", "科研装置投资", "新材料国产化"],
            "task": ["等离子体约束", "耐高温辐照", "低温超导", "真空维持", "脉冲电源控制"],
            "core_product": ["超导磁体", "第一壁材料", "偏滤器材料", "真空室部件", "高功率电源"],
            "foundation": ["钨钼材料", "钽铌锆材料", "钛合金", "碳纤维复材", "高温合金"],
            "integration": ["装置总装", "磁体系统集成", "真空低温系统", "电源控制系统", "材料验证"],
            "supporting": ["精密加工", "增材制造", "检测服务", "电力电子", "工程建设"],
            "infrastructure": ["聚变实验堆", "大科学装置", "材料中试线", "超导产业基地", "能源示范项目"],
            "commercialization": ["科研订单", "装置部件交付", "材料认证", "示范项目投资", "收入确认"],
        },
    },
    "industrial_machine_tools_cnc": {
        "theme_id": "future_industry_industrial_machine_tools_cnc",
        "theme_name": "工业母机/高端数控复杂产业链",
        "name": "工业母机/高端数控复杂产业链路模板",
        "description": "围绕高端五轴机床、数控系统、核心功能部件、机器人自动化、精密加工和航空航天/新能源客户验证，拆解工业母机国产替代链路。",
        "example_theme": "工业母机/高端数控",
        "layers": {
            "demand": ["制造业升级", "航空航天加工", "新能源汽车", "机器人量产", "进口替代"],
            "task": ["高精加工", "五轴联动", "复合加工", "自动化上下料", "精度保持"],
            "core_product": ["五轴数控机床", "数控系统", "加工中心", "成形装备", "激光加工设备"],
            "foundation": ["伺服系统", "滚珠丝杠", "减速器", "刀具夹具", "铸件床身"],
            "integration": ["产线集成", "柔性制造单元", "机器人上下料", "工艺软件", "客户验证"],
            "supporting": ["检测量具", "工业软件", "液压系统", "精密铸造", "售后服务"],
            "infrastructure": ["智能工厂", "高端装备基地", "航空制造产线", "汽车零部件产线", "职业培训体系"],
            "commercialization": ["设备订单", "进口替代份额", "产能利用率", "客户复购", "毛利率"],
        },
    },
    "innovative_drug_cxo_adc_glp1": {
        "theme_id": "future_industry_innovative_drug_cxo_adc_glp1",
        "theme_name": "创新药/CXO/ADC/减重药复杂产业链",
        "name": "创新药/CXO/ADC/减重药复杂产业链路模板",
        "description": "围绕创新药研发、CXO服务、ADC、GLP-1减重药、临床试验、原料药和商业化销售，拆解医药创新从研发到兑现的证据链。",
        "example_theme": "创新药/CXO/ADC/减重药",
        "layers": {
            "demand": ["肿瘤治疗", "慢病减重", "出海授权", "医保支付", "临床未满足需求"],
            "task": ["靶点发现", "临床推进", "药物偶联", "规模化生产", "商业销售"],
            "core_product": ["ADC药物", "GLP-1药物", "小分子创新药", "生物药", "疫苗/免疫治疗"],
            "foundation": ["原料药", "多肽合成", "抗体平台", "Linker/Payload", "临床数据"],
            "integration": ["CRO", "CDMO", "临床试验", "注册申报", "MAH生产"],
            "supporting": ["药物发现服务", "安全评价", "药品包装", "冷链物流", "医学推广"],
            "infrastructure": ["GMP产线", "临床中心", "研发平台", "商业渠道", "国际注册体系"],
            "commercialization": ["BD授权", "销售放量", "里程碑付款", "订单收入", "研发管线兑现"],
        },
    },
    "flexible_dc_offshore_wind_grid": {
        "theme_id": "future_industry_flexible_dc_offshore_wind_grid",
        "theme_name": "海上风电/柔直输电复杂产业链",
        "name": "海上风电/柔直输电复杂产业链路模板",
        "description": "围绕海上风电基地、深远海送出、柔性直流换流、海缆、风机、塔筒桩基和电网并网，拆解海风与柔直输电的项目链路。",
        "example_theme": "海上风电/柔直输电",
        "layers": {
            "demand": ["海风装机", "深远海送出", "新能源消纳", "电网投资", "沿海能源基地"],
            "task": ["海上发电", "海缆集电", "柔直换流", "远距离送出", "并网调度"],
            "core_product": ["海上风机", "海底电缆", "柔直换流阀", "换流变压器", "塔筒桩基"],
            "foundation": ["导体材料", "绝缘材料", "电力电子器件", "海工钢结构", "高压开关"],
            "integration": ["海风EPC", "海缆敷设", "柔直系统集成", "升压站建设", "并网调试"],
            "supporting": ["施工船队", "运维检测", "电力通信", "海工吊装", "监测系统"],
            "infrastructure": ["海上风电场", "海底输电通道", "柔直换流站", "沿海电网", "能源基地"],
            "commercialization": ["风机订单", "海缆订单", "柔直中标", "项目并网", "收入确认"],
        },
    },
    "rare_earth_minor_metals_security": {
        "theme_id": "future_industry_rare_earth_minor_metals_security",
        "theme_name": "稀土永磁/小金属资源安全复杂产业链",
        "name": "稀土永磁/小金属资源安全复杂产业链路模板",
        "description": "围绕稀土、永磁材料、锂钴钨锡锗镁等关键小金属和资源安全，拆解从资源开采、冶炼分离到高端应用的价格与供应链链路。",
        "example_theme": "稀土永磁/小金属资源安全",
        "layers": {
            "demand": ["新能源车", "机器人", "风电", "军工电子", "资源安全"],
            "task": ["资源保障", "冶炼分离", "磁材制造", "价格传导", "出口管制应对"],
            "core_product": ["稀土氧化物", "钕铁硼磁材", "锂钴资源", "钨锡锗资源", "镁合金"],
            "foundation": ["矿山资源", "分离冶炼", "金属回收", "粉体制备", "合金材料"],
            "integration": ["磁材加工", "电机配套", "电池材料配套", "军工材料配套", "贸易库存管理"],
            "supporting": ["检测认证", "环保处理", "物流仓储", "期现管理", "设备维护"],
            "infrastructure": ["资源基地", "冶炼分离产线", "永磁材料基地", "回收体系", "战略储备"],
            "commercialization": ["金属价格", "磁材订单", "资源产量", "出口份额", "毛利弹性"],
        },
    },
    "display_oled_microled": {
        "theme_id": "future_industry_display_oled_microled",
        "theme_name": "OLED/Micro LED/半导体显示复杂产业链",
        "name": "OLED/Micro LED/半导体显示复杂产业链路模板",
        "description": "围绕OLED、Micro LED、Mini LED、显示面板、驱动背板、发光材料、检测设备和终端应用，拆解半导体显示升级链路。",
        "example_theme": "OLED/Micro LED/半导体显示",
        "layers": {
            "demand": ["手机显示升级", "车载显示", "AR/VR", "大尺寸显示", "高端电视"],
            "task": ["发光效率提升", "良率提升", "高刷新显示", "柔性封装", "巨量转移"],
            "core_product": ["OLED面板", "Micro LED显示", "Mini LED背光", "显示模组", "驱动芯片/控制"],
            "foundation": ["发光材料", "光学膜", "玻璃基板", "驱动背板", "光刻/显影材料"],
            "integration": ["面板制造", "模组贴合", "检测修复", "终端集成", "客户认证"],
            "supporting": ["显示设备", "激光设备", "检测量测", "封装材料", "洁净厂务"],
            "infrastructure": ["面板产线", "Micro LED中试线", "模组产线", "材料认证平台", "终端供应链"],
            "commercialization": ["面板出货", "模组订单", "设备中标", "材料导入", "价格/毛利"],
        },
    },
    "domestic_os_database_industrial_software": {
        "theme_id": "future_industry_domestic_base_software",
        "theme_name": "国产操作系统/数据库/工业软件复杂产业链",
        "name": "国产操作系统/数据库/工业软件复杂产业链路模板",
        "description": "围绕信创替代、国产操作系统、数据库、中间件、办公软件、工业软件和行业应用迁移，拆解国产基础软件商业化链路。",
        "example_theme": "国产操作系统/数据库/工业软件",
        "layers": {
            "demand": ["信创替代", "央国企国产化", "工业数字化", "数据安全", "云原生改造"],
            "task": ["系统迁移", "数据库替换", "应用适配", "工艺建模", "安全运维"],
            "core_product": ["国产操作系统", "国产数据库", "中间件", "办公软件", "CAD/CAE/工业软件"],
            "foundation": ["CPU适配", "安全可信", "编译工具链", "数据治理", "工业知识模型"],
            "integration": ["信创集成", "行业应用迁移", "工业现场部署", "云平台适配", "运维服务"],
            "supporting": ["网络安全", "身份认证", "测试认证", "培训服务", "生态兼容"],
            "infrastructure": ["信创云", "政企数据中心", "工业互联网平台", "国产软件生态", "行业标准体系"],
            "commercialization": ["软件授权", "订阅续费", "集成项目", "生态适配收入", "客户留存"],
        },
    },
    "huawei_ascend_ai_ecosystem": {
        "theme_id": "future_industry_huawei_ascend_ai",
        "theme_name": "昇腾AI算力生态复杂产业链",
        "name": "昇腾AI算力生态复杂产业链路模板",
        "description": "围绕华为昇腾AI处理器、Atlas硬件、CANN/MindSpore软件栈、鲲鹏/昇腾服务器、智算中心、政企行业适配和AI应用商业化，拆解国产AI算力生态链路。",
        "example_theme": "昇腾AI算力生态",
        "layers": {
            "demand": ["国产AI算力", "政企智算中心", "大模型训练推理", "信创替代", "行业AI应用"],
            "task": ["模型适配迁移", "集群训练", "推理部署", "软硬件调优", "行业场景交付"],
            "core_product": ["昇腾AI处理器", "Atlas服务器", "AI训练推理一体机", "CANN异构计算架构", "MindSpore框架"],
            "foundation": ["鲲鹏CPU生态", "高速互联", "高速PCB", "光模块", "电源散热"],
            "integration": ["昇腾服务器整机", "智算集群交付", "云平台适配", "行业解决方案", "国产基础软件适配"],
            "supporting": ["液冷温控", "网络安全", "数据治理", "数据库/中间件", "运维服务"],
            "infrastructure": ["政企智算中心", "运营商算力节点", "行业云平台", "IDC机房", "算力调度平台"],
            "commercialization": ["服务器订单", "智算中心中标", "软件适配收入", "AI应用订阅", "项目验收收入"],
        },
    },
    "physical_ai": {
        "theme_id": "future_industry_physical_ai",
        "theme_name": "物理AI复杂产业链",
        "name": "物理AI复杂产业链路模板",
        "description": "围绕世界模型、物理仿真、合成数据、机器人基础模型、自动驾驶和数字孪生，拆解AI从数字世界走向物理世界的模型-仿真-数据-本体链路。",
        "example_theme": "物理AI",
        "layers": {
            "demand": ["无人工厂/智能制造", "自动驾驶", "仓储物流", "城市数字孪生", "特种作业"],
            "task": ["物理规律理解", "世界模型预测", "Sim2Real迁移", "合成数据生成", "空间感知"],
            "core_product": ["世界模型", "物理仿真引擎", "机器人基础模型/VLA", "自动驾驶方案", "数字孪生平台"],
            "foundation": ["训练算力", "物理求解器", "深度视觉传感器", "实时渲染", "边缘计算模组"],
            "integration": ["本体/整车集成", "仿真真实联合标定", "数据采集系统", "场景库构建", "车路协同集成"],
            "supporting": ["合成数据服务", "数据标注", "仿真资产/内容", "安全验证", "标准评测"],
            "infrastructure": ["智算中心", "仿真云/渲染农场", "数据闭环平台", "车路协同设施", "测试场"],
            "commercialization": ["本体销售/RaaS", "仿真软件订阅", "数据服务", "算力租赁", "方案授权"],
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
        {"code": "600667", "name": "太极实业", "layer": "infrastructure", "product": "数据中心工程技术服务/EPC"},
        {"code": "688111", "name": "金山办公", "layer": "commercialization", "product": "AI应用商业化"},
    ],
    "advanced_packaging_chiplet": [
        {"code": "600584", "name": "长电科技", "layer": "integration", "product": "先进封装/封测"},
        {"code": "002156", "name": "通富微电", "layer": "integration", "product": "先进封装/封测"},
        {"code": "002185", "name": "华天科技", "layer": "integration", "product": "封装测试"},
        {"code": "688362", "name": "甬矽电子", "layer": "integration", "product": "封装测试"},
        {"code": "688352", "name": "颀中科技", "layer": "integration", "product": "封装测试"},
        {"code": "603005", "name": "晶方科技", "layer": "integration", "product": "晶圆级封装"},
        {"code": "600667", "name": "太极实业", "layer": "integration", "product": "高阶混合封装/FCBGA/存储封测"},
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
        {"code": "600667", "name": "太极实业", "layer": "supporting", "product": "电子高科技工程设计/EPC"},
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
        {"code": "600667", "name": "太极实业", "layer": "infrastructure", "product": "半导体厂房/洁净厂务/电子高科技工程"},
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
    "lithography_equipment_chain": [
        {"code": "688037", "name": "芯源微", "layer": "core_product", "product": "涂胶显影/清洗设备"},
        {"code": "688138", "name": "清溢光电", "layer": "foundation", "product": "掩膜版/光罩"},
        {"code": "688401", "name": "路维光电", "layer": "foundation", "product": "掩膜版/光罩"},
        {"code": "300655", "name": "晶瑞电材", "layer": "foundation", "product": "光刻胶/湿电子化学品"},
        {"code": "300576", "name": "容大感光", "layer": "foundation", "product": "光刻胶/电子材料"},
        {"code": "603650", "name": "彤程新材", "layer": "foundation", "product": "光刻胶/电子材料"},
        {"code": "300346", "name": "南大光电", "layer": "foundation", "product": "光刻胶/电子特气材料"},
        {"code": "300236", "name": "上海新阳", "layer": "foundation", "product": "电镀液/清洗液/半导体材料"},
        {"code": "603078", "name": "江化微", "layer": "foundation", "product": "湿电子化学品"},
        {"code": "688502", "name": "茂莱光学", "layer": "foundation", "product": "精密光学元件"},
        {"code": "002222", "name": "福晶科技", "layer": "foundation", "product": "光学晶体/精密光学元件"},
        {"code": "688195", "name": "腾景科技", "layer": "foundation", "product": "精密光学元组件"},
        {"code": "301421", "name": "波长光电", "layer": "foundation", "product": "工业光学镜头/光学元件"},
        {"code": "603297", "name": "永新光学", "layer": "foundation", "product": "精密光学组件"},
        {"code": "300395", "name": "菲利华", "layer": "foundation", "product": "石英材料/光学材料"},
        {"code": "300567", "name": "精测电子", "layer": "integration", "product": "半导体检测量测"},
        {"code": "688200", "name": "华峰测控", "layer": "integration", "product": "半导体测试设备"},
        {"code": "300604", "name": "长川科技", "layer": "integration", "product": "半导体测试设备"},
        {"code": "603690", "name": "至纯科技", "layer": "supporting", "product": "高纯工艺系统/洁净厂务"},
        {"code": "688596", "name": "正帆科技", "layer": "supporting", "product": "工艺介质供应系统"},
        {"code": "603929", "name": "亚翔集成", "layer": "supporting", "product": "洁净室工程"},
        {"code": "601133", "name": "柏诚股份", "layer": "supporting", "product": "洁净室/厂务工程"},
        {"code": "300260", "name": "新莱应材", "layer": "supporting", "product": "高洁净应用材料/管路"},
        {"code": "688268", "name": "华特气体", "layer": "supporting", "product": "电子特气"},
        {"code": "688106", "name": "金宏气体", "layer": "supporting", "product": "电子大宗气体/特气"},
    ],
    "data_ai_application_commercialization": [
        {"code": "600941", "name": "中国移动", "layer": "demand", "product": "政企数字化/云网需求"},
        {"code": "601728", "name": "中国电信", "layer": "demand", "product": "政企云/数字化采购需求"},
        {"code": "600050", "name": "中国联通", "layer": "demand", "product": "政企数字化需求"},
        {"code": "600588", "name": "用友网络", "layer": "demand", "product": "企业数字化/AI办公需求承载"},
        {"code": "603000", "name": "人民网", "layer": "task", "product": "数据确权/数据要素运营"},
        {"code": "300766", "name": "每日互动", "layer": "task", "product": "数据治理/数据要素服务"},
        {"code": "600602", "name": "云赛智联", "layer": "task", "product": "政企数据治理/城市数据运营"},
        {"code": "688787", "name": "海天瑞声", "layer": "task", "product": "训练数据服务/数据治理"},
        {"code": "688111", "name": "金山办公", "layer": "core_product", "product": "AI办公软件/WPS AI"},
        {"code": "002230", "name": "科大讯飞", "layer": "core_product", "product": "大模型/AI教育办公应用"},
        {"code": "300624", "name": "万兴科技", "layer": "core_product", "product": "AI创意软件"},
        {"code": "300229", "name": "拓尔思", "layer": "core_product", "product": "NLP/行业知识智能"},
        {"code": "300033", "name": "同花顺", "layer": "commercialization", "product": "AI金融信息服务"},
        {"code": "688318", "name": "财富趋势", "layer": "commercialization", "product": "证券行情交易软件"},
        {"code": "600570", "name": "恒生电子", "layer": "integration", "product": "金融IT/AI金融应用"},
        {"code": "300170", "name": "汉得信息", "layer": "integration", "product": "企业数字化/AI应用集成"},
        {"code": "000938", "name": "紫光股份", "layer": "integration", "product": "ICT基础设施/云与数据中心"},
        {"code": "000977", "name": "浪潮信息", "layer": "foundation", "product": "AI服务器/算力底座"},
        {"code": "603019", "name": "中科曙光", "layer": "foundation", "product": "算力基础设施"},
        {"code": "688256", "name": "寒武纪", "layer": "foundation", "product": "AI芯片/推理训练算力"},
        {"code": "300308", "name": "中际旭创", "layer": "foundation", "product": "高速光模块"},
        {"code": "300454", "name": "深信服", "layer": "supporting", "product": "云安全/企业云平台"},
        {"code": "300369", "name": "绿盟科技", "layer": "supporting", "product": "数据安全/网络安全"},
        {"code": "300579", "name": "数字认证", "layer": "supporting", "product": "电子认证/可信身份"},
        {"code": "300188", "name": "国投智能", "layer": "supporting", "product": "数据治理/智能分析"},
        {"code": "300166", "name": "东方国信", "layer": "infrastructure", "product": "企业数据平台/大数据"},
        {"code": "688031", "name": "星环科技", "layer": "foundation", "product": "大数据基础软件"},
        {"code": "688327", "name": "云从科技", "layer": "core_product", "product": "AI视觉/行业智能应用"},
        {"code": "688228", "name": "开普云", "layer": "integration", "product": "政务数据运营/数字内容"},
        {"code": "601360", "name": "三六零", "layer": "core_product", "product": "大模型/AI应用"},
        {"code": "300418", "name": "昆仑万维", "layer": "core_product", "product": "大模型/AI应用出海"},
        {"code": "688095", "name": "福昕软件", "layer": "core_product", "product": "AI办公/PDF软件"},
        {"code": "002362", "name": "汉王科技", "layer": "core_product", "product": "OCR/AI识别应用"},
        {"code": "300634", "name": "彩讯股份", "layer": "core_product", "product": "AI办公/智能邮箱"},
        {"code": "688041", "name": "海光信息", "layer": "foundation", "product": "DCU/AI算力芯片"},
        {"code": "688058", "name": "宝兰德", "layer": "foundation", "product": "云原生中间件"},
        {"code": "688118", "name": "普元信息", "layer": "foundation", "product": "中间件/数据平台"},
        {"code": "300846", "name": "首都在线", "layer": "foundation", "product": "云计算/推理算力"},
        {"code": "002368", "name": "太极股份", "layer": "integration", "product": "政企系统集成"},
        {"code": "002065", "name": "东华软件", "layer": "integration", "product": "行业系统集成"},
        {"code": "000034", "name": "神州数码", "layer": "integration", "product": "云与数字化集成"},
        {"code": "300674", "name": "宇信科技", "layer": "integration", "product": "金融IT交付"},
        {"code": "688232", "name": "新点软件", "layer": "integration", "product": "政务集成/智慧政务"},
        {"code": "688023", "name": "安恒信息", "layer": "supporting", "product": "数据安全"},
        {"code": "688561", "name": "奇安信", "layer": "supporting", "product": "网络安全"},
        {"code": "603232", "name": "格尔软件", "layer": "supporting", "product": "身份认证/商用密码"},
        {"code": "300659", "name": "中孚信息", "layer": "supporting", "product": "数据安全/保密"},
        {"code": "300442", "name": "润泽科技", "layer": "infrastructure", "product": "智算中心"},
        {"code": "603881", "name": "数据港", "layer": "infrastructure", "product": "IDC/数据中心"},
        {"code": "300738", "name": "奥飞数据", "layer": "infrastructure", "product": "IDC/算力服务"},
        {"code": "600845", "name": "宝信软件", "layer": "infrastructure", "product": "IDC/工业互联网"},
        {"code": "000032", "name": "深桑达A", "layer": "infrastructure", "product": "政务云/数据要素"},
        {"code": "300803", "name": "指南针", "layer": "commercialization", "product": "金融信息服务订阅"},
        {"code": "601519", "name": "大智慧", "layer": "commercialization", "product": "金融信息服务"},
        {"code": "603171", "name": "税友股份", "layer": "commercialization", "product": "财税SaaS订阅"},
        {"code": "002410", "name": "广联达", "layer": "commercialization", "product": "建筑SaaS订阅/AI"},
        {"code": "300058", "name": "蓝色光标", "layer": "core_product", "product": "AIGC营销文案/内容生成"},
        {"code": "300364", "name": "中文在线", "layer": "core_product", "product": "AIGC文本/IP内容"},
        {"code": "000681", "name": "视觉中国", "layer": "core_product", "product": "AIGC图像/版权内容"},
        {"code": "688039", "name": "当虹科技", "layer": "core_product", "product": "视频生成/智能剪辑"},
        {"code": "603039", "name": "泛微网络", "layer": "core_product", "product": "智能助手/OA协同"},
        {"code": "300496", "name": "中科创达", "layer": "core_product", "product": "端侧AI软件/开发工具"},
        {"code": "301236", "name": "软通动力", "layer": "core_product", "product": "软件开发服务/代码生成"},
        {"code": "300339", "name": "润和软件", "layer": "core_product", "product": "软件开发/AI服务"},
        {"code": "300002", "name": "神州泰岳", "layer": "core_product", "product": "智能客服/NLP"},
        {"code": "688365", "name": "光云科技", "layer": "core_product", "product": "电商SaaS/智能客服"},
        {"code": "300253", "name": "卫宁健康", "layer": "core_product", "product": "医疗AI/影像辅助"},
        {"code": "300559", "name": "佳发教育", "layer": "core_product", "product": "教育AI/个性化学习"},
        {"code": "301378", "name": "通达海", "layer": "core_product", "product": "法律AI/合同审查"},
        {"code": "688083", "name": "中望软件", "layer": "core_product", "product": "制造/工业设计AI"},
        {"code": "002315", "name": "焦点科技", "layer": "core_product", "product": "零售电商AI/数字人"},
        {"code": "301556", "name": "托普云农", "layer": "core_product", "product": "农业AI/病虫害识别"},
        {"code": "600446", "name": "金证股份", "layer": "core_product", "product": "金融AI/量化风控"},
        {"code": "688036", "name": "传音控股", "layer": "core_product", "product": "端侧AI手机"},
        {"code": "002241", "name": "歌尔股份", "layer": "core_product", "product": "AI眼镜/智能终端"},
        {"code": "688475", "name": "萤石网络", "layer": "core_product", "product": "智能家居/端侧AI"},
        {"code": "688222", "name": "成都先导", "layer": "core_product", "product": "AI药物研发/AI4S"},
        {"code": "300785", "name": "值得买", "layer": "commercialization", "product": "内容/导购变现"},
        {"code": "688568", "name": "中科星图", "layer": "infrastructure", "product": "行业知识库/遥感气象AI"},
    ],
    "embodied_intelligence": [
        {"code": "300024", "name": "机器人", "layer": "demand", "product": "机器人整机/零部件需求拉动"},
        {"code": "603486", "name": "科沃斯", "layer": "demand", "product": "家庭服务机器人需求"},
        {"code": "688169", "name": "石头科技", "layer": "demand", "product": "家庭服务机器人需求"},
        {"code": "688585", "name": "上纬新材", "layer": "demand", "product": "智元机器人入主/本体平台"},
        {"code": "603893", "name": "瑞芯微", "layer": "task", "product": "端侧推理SoC"},
        {"code": "688099", "name": "晶晨股份", "layer": "task", "product": "端侧AI芯片"},
        {"code": "300458", "name": "全志科技", "layer": "task", "product": "端侧SoC/智能硬件"},
        {"code": "688165", "name": "埃夫特", "layer": "core_product", "product": "工业机器人整机"},
        {"code": "002527", "name": "新时达", "layer": "core_product", "product": "机器人整机/控制器"},
        {"code": "689009", "name": "九号公司", "layer": "core_product", "product": "服务/配送机器人"},
        {"code": "603666", "name": "亿嘉和", "layer": "core_product", "product": "特种作业机器人"},
        {"code": "688017", "name": "绿的谐波", "layer": "foundation", "product": "谐波减速器"},
        {"code": "002472", "name": "双环传动", "layer": "foundation", "product": "精密减速器/齿轮"},
        {"code": "603728", "name": "鸣志电器", "layer": "foundation", "product": "空心杯/步进电机"},
        {"code": "603662", "name": "柯力传感", "layer": "foundation", "product": "力矩/六维力传感器"},
        {"code": "300007", "name": "汉威科技", "layer": "foundation", "product": "柔性/触觉传感器"},
        {"code": "300124", "name": "汇川技术", "layer": "foundation", "product": "伺服系统/工控"},
        {"code": "003021", "name": "兆威机电", "layer": "foundation", "product": "微型传动/灵巧手模组"},
        {"code": "300503", "name": "昊志机电", "layer": "foundation", "product": "谐波减速器/电主轴"},
        {"code": "601689", "name": "拓普集团", "layer": "integration", "product": "执行器/关节模组"},
        {"code": "002050", "name": "三花智控", "layer": "integration", "product": "机电执行器"},
        {"code": "300660", "name": "江苏雷利", "layer": "integration", "product": "微特电机/执行器"},
        {"code": "002747", "name": "埃斯顿", "layer": "integration", "product": "运动控制/整机集成"},
        {"code": "002979", "name": "雷赛智能", "layer": "integration", "product": "运动控制/伺服"},
        {"code": "688787", "name": "海天瑞声", "layer": "supporting", "product": "训练数据服务"},
        {"code": "688507", "name": "索辰科技", "layer": "supporting", "product": "仿真平台/CAE"},
        {"code": "601965", "name": "中国汽研", "layer": "supporting", "product": "检测认证/测试评价"},
        {"code": "300353", "name": "东土科技", "layer": "infrastructure", "product": "工业网络/工业互联网"},
        {"code": "603236", "name": "移远通信", "layer": "infrastructure", "product": "边缘通信模组"},
        {"code": "002698", "name": "博实股份", "layer": "commercialization", "product": "成套装备/运维服务"},
        {"code": "300853", "name": "申昊科技", "layer": "commercialization", "product": "巡检机器人运营"},
    ],
    "physical_ai": [
        {"code": "002594", "name": "比亚迪", "layer": "demand", "product": "自动驾驶/智能制造需求"},
        {"code": "601127", "name": "赛力斯", "layer": "demand", "product": "智能驾驶需求"},
        {"code": "601138", "name": "工业富联", "layer": "demand", "product": "无人工厂/智能制造需求"},
        {"code": "688787", "name": "海天瑞声", "layer": "task", "product": "合成/训练数据"},
        {"code": "301221", "name": "光庭信息", "layer": "task", "product": "智驾仿真/数据服务"},
        {"code": "688322", "name": "奥比中光", "layer": "task", "product": "空间感知/深度视觉"},
        {"code": "688507", "name": "索辰科技", "layer": "core_product", "product": "物理仿真CAE"},
        {"code": "688083", "name": "中望软件", "layer": "core_product", "product": "工业软件/数字孪生"},
        {"code": "300036", "name": "超图软件", "layer": "core_product", "product": "GIS/数字孪生平台"},
        {"code": "002920", "name": "德赛西威", "layer": "core_product", "product": "智驾方案/域控制器"},
        {"code": "688326", "name": "经纬恒润", "layer": "core_product", "product": "智驾电子/仿真测试"},
        {"code": "002405", "name": "四维图新", "layer": "core_product", "product": "高精地图/数字孪生"},
        {"code": "688256", "name": "寒武纪", "layer": "foundation", "product": "训练算力芯片"},
        {"code": "688041", "name": "海光信息", "layer": "foundation", "product": "DCU/训练算力"},
        {"code": "300496", "name": "中科创达", "layer": "foundation", "product": "边缘计算/操作系统"},
        {"code": "600728", "name": "佳都科技", "layer": "integration", "product": "城市数字孪生集成"},
        {"code": "002373", "name": "千方科技", "layer": "integration", "product": "车路协同集成"},
        {"code": "601965", "name": "中国汽研", "layer": "supporting", "product": "测试验证/试验场"},
        {"code": "300012", "name": "华测检测", "layer": "supporting", "product": "检测认证"},
        {"code": "600845", "name": "宝信软件", "layer": "infrastructure", "product": "智算中心/IDC"},
        {"code": "300442", "name": "润泽科技", "layer": "infrastructure", "product": "智算中心"},
        {"code": "300846", "name": "首都在线", "layer": "infrastructure", "product": "云渲染/算力服务"},
        {"code": "688088", "name": "虹软科技", "layer": "commercialization", "product": "视觉算法授权"},
        {"code": "688158", "name": "优刻得", "layer": "commercialization", "product": "云订阅/算力租赁"},
    ],
    "defense_informatization_unmanned": [
        {"code": "600760", "name": "中航沈飞", "layer": "integration", "product": "航空装备总装"},
        {"code": "000768", "name": "中航西飞", "layer": "integration", "product": "航空装备总装"},
        {"code": "600893", "name": "航发动力", "layer": "foundation", "product": "航空发动机"},
        {"code": "600879", "name": "航天电子", "layer": "core_product", "product": "航天电子/无人装备配套"},
        {"code": "600038", "name": "中直股份", "layer": "core_product", "product": "直升机/低空装备"},
        {"code": "688297", "name": "中无人机", "layer": "core_product", "product": "大型无人机系统"},
        {"code": "600562", "name": "国睿科技", "layer": "core_product", "product": "雷达系统"},
        {"code": "002414", "name": "高德红外", "layer": "core_product", "product": "红外探测/制导配套"},
        {"code": "002151", "name": "北斗星通", "layer": "core_product", "product": "北斗导航定位"},
        {"code": "300101", "name": "振芯科技", "layer": "core_product", "product": "北斗导航/集成电路"},
        {"code": "002179", "name": "中航光电", "layer": "foundation", "product": "军用连接器"},
        {"code": "002025", "name": "航天电器", "layer": "foundation", "product": "连接器/继电器"},
        {"code": "300395", "name": "菲利华", "layer": "foundation", "product": "石英材料/军工材料"},
        {"code": "300699", "name": "光威复材", "layer": "foundation", "product": "碳纤维复合材料"},
        {"code": "300456", "name": "赛微电子", "layer": "supporting", "product": "MEMS/惯性传感器"},
        {"code": "688011", "name": "新光光电", "layer": "supporting", "product": "光电系统"},
        {"code": "688682", "name": "霍莱沃", "layer": "supporting", "product": "雷达仿真测试"},
        {"code": "600150", "name": "中国船舶", "layer": "integration", "product": "海军装备/船舶总装"},
    ],
    "intelligent_driving_v2x": [
        {"code": "002594", "name": "比亚迪", "layer": "demand", "product": "智能电动车整车需求"},
        {"code": "601127", "name": "赛力斯", "layer": "demand", "product": "智能电动车整车需求"},
        {"code": "601633", "name": "长城汽车", "layer": "demand", "product": "智能汽车整车需求"},
        {"code": "002920", "name": "德赛西威", "layer": "core_product", "product": "智能座舱/智能驾驶域控"},
        {"code": "002405", "name": "四维图新", "layer": "core_product", "product": "高精地图/智驾软件"},
        {"code": "300496", "name": "中科创达", "layer": "core_product", "product": "智能驾驶操作系统/软件"},
        {"code": "688326", "name": "经纬恒润", "layer": "core_product", "product": "智能驾驶电子系统"},
        {"code": "300458", "name": "全志科技", "layer": "foundation", "product": "车规芯片/座舱芯片"},
        {"code": "603197", "name": "保隆科技", "layer": "foundation", "product": "车载传感器"},
        {"code": "600699", "name": "均胜电子", "layer": "integration", "product": "汽车电子/安全系统"},
        {"code": "002906", "name": "华阳集团", "layer": "integration", "product": "智能座舱/车载电子"},
        {"code": "603596", "name": "伯特利", "layer": "core_product", "product": "线控制动"},
        {"code": "002284", "name": "亚太股份", "layer": "core_product", "product": "汽车制动系统"},
        {"code": "002373", "name": "千方科技", "layer": "infrastructure", "product": "智慧交通/车路协同"},
        {"code": "300552", "name": "万集科技", "layer": "infrastructure", "product": "路侧感知/ETC/V2X"},
        {"code": "002331", "name": "皖通科技", "layer": "infrastructure", "product": "智慧交通系统"},
        {"code": "300098", "name": "高新兴", "layer": "infrastructure", "product": "车联网/智慧交通"},
        {"code": "600105", "name": "永鼎股份", "layer": "supporting", "product": "车载线束/通信线缆"},
        {"code": "600660", "name": "福耀玻璃", "layer": "supporting", "product": "汽车玻璃/HUD配套"},
        {"code": "600741", "name": "华域汽车", "layer": "integration", "product": "汽车零部件系统集成"},
    ],
    "controlled_fusion_materials": [
        {"code": "002130", "name": "沃尔核材", "layer": "core_product", "product": "核电/高分子功能材料"},
        {"code": "603969", "name": "银龙股份", "layer": "core_product", "product": "超导线材/预应力材料"},
        {"code": "688122", "name": "西部超导", "layer": "core_product", "product": "超导材料/钛合金"},
        {"code": "002149", "name": "西部材料", "layer": "foundation", "product": "稀有金属复合材料"},
        {"code": "600456", "name": "宝钛股份", "layer": "foundation", "product": "钛材/钛合金"},
        {"code": "000962", "name": "东方钽业", "layer": "foundation", "product": "钽铌材料"},
        {"code": "002167", "name": "东方锆业", "layer": "foundation", "product": "锆材料"},
        {"code": "300034", "name": "钢研高纳", "layer": "foundation", "product": "高温合金"},
        {"code": "300855", "name": "图南股份", "layer": "foundation", "product": "高温合金"},
        {"code": "300699", "name": "光威复材", "layer": "foundation", "product": "碳纤维复合材料"},
        {"code": "300777", "name": "中简科技", "layer": "foundation", "product": "碳纤维"},
        {"code": "688333", "name": "铂力特", "layer": "supporting", "product": "金属增材制造"},
        {"code": "688239", "name": "航宇科技", "layer": "supporting", "product": "环锻件/高端金属加工"},
        {"code": "688248", "name": "南网科技", "layer": "supporting", "product": "电力电子/试验检测"},
        {"code": "300489", "name": "光智科技", "layer": "supporting", "product": "红外光学/高纯材料加工"},
    ],
    "industrial_machine_tools_cnc": [
        {"code": "000837", "name": "秦川机床", "layer": "core_product", "product": "数控机床/齿轮磨床"},
        {"code": "000410", "name": "沈阳机床", "layer": "core_product", "product": "数控机床"},
        {"code": "002520", "name": "日发精机", "layer": "core_product", "product": "数控机床/航空装备"},
        {"code": "300161", "name": "华中数控", "layer": "core_product", "product": "数控系统"},
        {"code": "688558", "name": "国盛智科", "layer": "core_product", "product": "高端数控机床"},
        {"code": "688697", "name": "纽威数控", "layer": "core_product", "product": "数控机床"},
        {"code": "688305", "name": "科德数控", "layer": "core_product", "product": "五轴联动数控机床"},
        {"code": "300083", "name": "创世纪", "layer": "core_product", "product": "钻攻机/数控机床"},
        {"code": "002559", "name": "亚威股份", "layer": "core_product", "product": "金属成形机床"},
        {"code": "002008", "name": "大族激光", "layer": "core_product", "product": "激光加工设备"},
        {"code": "603011", "name": "合锻智能", "layer": "integration", "product": "成形装备/智能产线"},
        {"code": "603283", "name": "赛腾股份", "layer": "integration", "product": "自动化设备"},
        {"code": "002031", "name": "巨轮智能", "layer": "supporting", "product": "机器人/智能装备"},
        {"code": "688017", "name": "绿的谐波", "layer": "foundation", "product": "精密减速器"},
        {"code": "002472", "name": "双环传动", "layer": "foundation", "product": "齿轮传动/减速器"},
        {"code": "603308", "name": "应流股份", "layer": "foundation", "product": "高端铸件/装备部件"},
    ],
    "innovative_drug_cxo_adc_glp1": [
        {"code": "603259", "name": "药明康德", "layer": "integration", "product": "CRO/CDMO一体化服务"},
        {"code": "603127", "name": "昭衍新药", "layer": "supporting", "product": "药物安全评价"},
        {"code": "300347", "name": "泰格医药", "layer": "integration", "product": "临床CRO"},
        {"code": "300759", "name": "康龙化成", "layer": "integration", "product": "CRO/CDMO服务"},
        {"code": "688202", "name": "美迪西", "layer": "supporting", "product": "药物发现/临床前CRO"},
        {"code": "300725", "name": "药石科技", "layer": "foundation", "product": "药物分子砌块"},
        {"code": "300363", "name": "博腾股份", "layer": "integration", "product": "CDMO服务"},
        {"code": "002821", "name": "凯莱英", "layer": "integration", "product": "小分子CDMO"},
        {"code": "603456", "name": "九洲药业", "layer": "integration", "product": "CDMO/API"},
        {"code": "688331", "name": "荣昌生物", "layer": "core_product", "product": "ADC/创新生物药"},
        {"code": "688235", "name": "百济神州", "layer": "core_product", "product": "创新药管线"},
        {"code": "600196", "name": "复星医药", "layer": "core_product", "product": "创新药/商业化平台"},
        {"code": "300558", "name": "贝达药业", "layer": "core_product", "product": "小分子创新药"},
        {"code": "688506", "name": "百利天恒", "layer": "core_product", "product": "ADC创新药"},
        {"code": "000513", "name": "丽珠集团", "layer": "core_product", "product": "GLP-1/生物药"},
        {"code": "300199", "name": "翰宇药业", "layer": "foundation", "product": "多肽原料药/多肽药物"},
        {"code": "688278", "name": "特宝生物", "layer": "core_product", "product": "生物药"},
        {"code": "688578", "name": "艾力斯", "layer": "core_product", "product": "肺癌靶向创新药"},
        {"code": "300122", "name": "智飞生物", "layer": "commercialization", "product": "疫苗商业化渠道"},
        {"code": "300601", "name": "康泰生物", "layer": "core_product", "product": "疫苗/生物制品"},
    ],
    "flexible_dc_offshore_wind_grid": [
        {"code": "601615", "name": "明阳智能", "layer": "core_product", "product": "海上风电整机"},
        {"code": "002202", "name": "金风科技", "layer": "core_product", "product": "风电整机"},
        {"code": "600875", "name": "东方电气", "layer": "core_product", "product": "海上风电整机/电力装备"},
        {"code": "600522", "name": "中天科技", "layer": "core_product", "product": "海底电缆/柔性直流电缆"},
        {"code": "603606", "name": "东方电缆", "layer": "core_product", "product": "海底电缆"},
        {"code": "600487", "name": "亨通光电", "layer": "core_product", "product": "海缆/电力光缆"},
        {"code": "000400", "name": "许继电气", "layer": "core_product", "product": "柔直换流/智能变配电"},
        {"code": "600406", "name": "国电南瑞", "layer": "core_product", "product": "柔直控制保护/电网自动化"},
        {"code": "002028", "name": "思源电气", "layer": "core_product", "product": "输变电设备"},
        {"code": "601179", "name": "中国西电", "layer": "core_product", "product": "输变电设备"},
        {"code": "600312", "name": "平高电气", "layer": "core_product", "product": "高压开关"},
        {"code": "600089", "name": "特变电工", "layer": "core_product", "product": "变压器/输变电系统"},
        {"code": "600973", "name": "宝胜股份", "layer": "foundation", "product": "电线电缆/导体材料"},
        {"code": "301155", "name": "海力风电", "layer": "foundation", "product": "海上风电塔筒/桩基"},
        {"code": "002531", "name": "天顺风能", "layer": "foundation", "product": "风塔/海工装备"},
        {"code": "002487", "name": "大金重工", "layer": "foundation", "product": "海风塔筒/单桩"},
        {"code": "600522", "name": "中天科技", "layer": "commercialization", "product": "海缆订单/柔直电缆交付"},
    ],
    "rare_earth_minor_metals_security": [
        {"code": "600111", "name": "北方稀土", "layer": "core_product", "product": "稀土资源/稀土氧化物"},
        {"code": "000831", "name": "中国稀土", "layer": "core_product", "product": "稀土氧化物/冶炼分离"},
        {"code": "600392", "name": "盛和资源", "layer": "core_product", "product": "稀土资源/冶炼分离"},
        {"code": "300748", "name": "金力永磁", "layer": "core_product", "product": "高性能钕铁硼磁材"},
        {"code": "000970", "name": "中科三环", "layer": "core_product", "product": "钕铁硼永磁材料"},
        {"code": "000795", "name": "英洛华", "layer": "core_product", "product": "钕铁硼磁材/电机"},
        {"code": "600366", "name": "宁波韵升", "layer": "core_product", "product": "稀土永磁材料"},
        {"code": "002056", "name": "横店东磁", "layer": "integration", "product": "磁性材料/电机磁材"},
        {"code": "002466", "name": "天齐锂业", "layer": "core_product", "product": "锂资源"},
        {"code": "002460", "name": "赣锋锂业", "layer": "core_product", "product": "锂资源/锂盐"},
        {"code": "603799", "name": "华友钴业", "layer": "core_product", "product": "钴镍资源/电池材料"},
        {"code": "300618", "name": "寒锐钴业", "layer": "core_product", "product": "钴资源"},
        {"code": "000960", "name": "锡业股份", "layer": "core_product", "product": "锡资源"},
        {"code": "002182", "name": "宝武镁业", "layer": "core_product", "product": "镁合金"},
        {"code": "002428", "name": "云南锗业", "layer": "core_product", "product": "锗资源"},
        {"code": "002378", "name": "章源钨业", "layer": "core_product", "product": "钨资源"},
        {"code": "603993", "name": "洛阳钼业", "layer": "core_product", "product": "钼钴铜资源"},
        {"code": "600549", "name": "厦门钨业", "layer": "integration", "product": "钨钼材料/稀土材料"},
        {"code": "002600", "name": "领益智造", "layer": "commercialization", "product": "消费电子磁材应用"},
    ],
    "display_oled_microled": [
        {"code": "000725", "name": "京东方A", "layer": "core_product", "product": "OLED/LCD显示面板"},
        {"code": "000100", "name": "TCL科技", "layer": "core_product", "product": "半导体显示面板"},
        {"code": "002387", "name": "维信诺", "layer": "core_product", "product": "OLED显示面板"},
        {"code": "688538", "name": "和辉光电", "layer": "core_product", "product": "AMOLED显示面板"},
        {"code": "300296", "name": "利亚德", "layer": "core_product", "product": "Micro LED显示"},
        {"code": "300232", "name": "洲明科技", "layer": "core_product", "product": "LED显示屏/Mini LED"},
        {"code": "002449", "name": "国星光电", "layer": "foundation", "product": "LED封装/Mini LED"},
        {"code": "300241", "name": "瑞丰光电", "layer": "foundation", "product": "Mini LED/显示封装"},
        {"code": "600703", "name": "三安光电", "layer": "foundation", "product": "LED芯片/Micro LED"},
        {"code": "300566", "name": "激智科技", "layer": "foundation", "product": "光学膜"},
        {"code": "300545", "name": "联得装备", "layer": "supporting", "product": "显示模组设备"},
        {"code": "300567", "name": "精测电子", "layer": "supporting", "product": "面板检测设备"},
        {"code": "688025", "name": "杰普特", "layer": "supporting", "product": "激光设备"},
        {"code": "300346", "name": "南大光电", "layer": "foundation", "product": "OLED材料/电子特气"},
        {"code": "603650", "name": "彤程新材", "layer": "foundation", "product": "光刻胶/电子材料"},
        {"code": "300655", "name": "晶瑞电材", "layer": "foundation", "product": "显示用湿电子化学品"},
        {"code": "688502", "name": "茂莱光学", "layer": "supporting", "product": "精密光学元件"},
        {"code": "688195", "name": "腾景科技", "layer": "supporting", "product": "精密光学组件"},
        {"code": "002841", "name": "视源股份", "layer": "commercialization", "product": "交互显示终端"},
    ],
    "domestic_os_database_industrial_software": [
        {"code": "600536", "name": "中国软件", "layer": "core_product", "product": "国产操作系统/基础软件"},
        {"code": "688111", "name": "金山办公", "layer": "core_product", "product": "国产办公软件"},
        {"code": "688031", "name": "星环科技", "layer": "core_product", "product": "大数据基础软件/数据库"},
        {"code": "688058", "name": "宝兰德", "layer": "core_product", "product": "中间件"},
        {"code": "300525", "name": "博思软件", "layer": "integration", "product": "财政政务软件"},
        {"code": "600588", "name": "用友网络", "layer": "integration", "product": "企业管理软件/ERP"},
        {"code": "600570", "name": "恒生电子", "layer": "integration", "product": "金融行业软件"},
        {"code": "300170", "name": "汉得信息", "layer": "integration", "product": "ERP实施/企业数字化"},
        {"code": "688777", "name": "中控技术", "layer": "core_product", "product": "工业控制软件/流程工业自动化"},
        {"code": "688188", "name": "柏楚电子", "layer": "core_product", "product": "激光切割控制系统"},
        {"code": "688083", "name": "中望软件", "layer": "core_product", "product": "国产CAD/CAE软件"},
        {"code": "300378", "name": "鼎捷数智", "layer": "integration", "product": "制造业ERP/MES"},
        {"code": "002063", "name": "远光软件", "layer": "integration", "product": "电力行业软件"},
        {"code": "300830", "name": "金现代", "layer": "integration", "product": "电力/政企软件"},
        {"code": "300454", "name": "深信服", "layer": "supporting", "product": "云平台/安全软件"},
        {"code": "688168", "name": "安博通", "layer": "supporting", "product": "网络安全软件"},
        {"code": "300166", "name": "东方国信", "layer": "infrastructure", "product": "工业互联网/大数据平台"},
    ],
    "huawei_ascend_ai_ecosystem": [
        {"code": "000977", "name": "浪潮信息", "layer": "integration", "product": "AI服务器整机/智算集群交付"},
        {"code": "603019", "name": "中科曙光", "layer": "integration", "product": "AI服务器/智算中心"},
        {"code": "000938", "name": "紫光股份", "layer": "integration", "product": "ICT基础设施/服务器网络"},
        {"code": "000034", "name": "神州数码", "layer": "integration", "product": "鲲鹏/昇腾生态集成与分销"},
        {"code": "002261", "name": "拓维信息", "layer": "integration", "product": "昇腾/鲲鹏服务器与行业解决方案"},
        {"code": "301236", "name": "软通动力", "layer": "integration", "product": "华为生态软件开发/行业适配"},
        {"code": "300339", "name": "润和软件", "layer": "integration", "product": "开源鸿蒙/欧拉/昇腾生态适配"},
        {"code": "300598", "name": "诚迈科技", "layer": "integration", "product": "操作系统与终端软件适配"},
        {"code": "300170", "name": "汉得信息", "layer": "integration", "product": "企业数字化/AI应用集成"},
        {"code": "600588", "name": "用友网络", "layer": "commercialization", "product": "企业AI应用/ERP商业化"},
        {"code": "688111", "name": "金山办公", "layer": "commercialization", "product": "AI办公软件商业化"},
        {"code": "600570", "name": "恒生电子", "layer": "commercialization", "product": "金融IT/AI金融应用"},
        {"code": "300166", "name": "东方国信", "layer": "supporting", "product": "数据治理/行业大数据平台"},
        {"code": "688031", "name": "星环科技", "layer": "supporting", "product": "大数据基础软件/数据库"},
        {"code": "688777", "name": "中控技术", "layer": "commercialization", "product": "工业AI/流程工业智能化"},
        {"code": "688083", "name": "中望软件", "layer": "commercialization", "product": "工业软件/国产CAD"},
        {"code": "688188", "name": "柏楚电子", "layer": "commercialization", "product": "工业控制软件"},
        {"code": "300454", "name": "深信服", "layer": "supporting", "product": "云安全/企业云平台"},
        {"code": "300369", "name": "绿盟科技", "layer": "supporting", "product": "网络安全/数据安全"},
        {"code": "300579", "name": "数字认证", "layer": "supporting", "product": "可信身份/电子认证"},
        {"code": "300308", "name": "中际旭创", "layer": "foundation", "product": "高速光模块"},
        {"code": "300502", "name": "新易盛", "layer": "foundation", "product": "高速光模块"},
        {"code": "300394", "name": "天孚通信", "layer": "foundation", "product": "光器件"},
        {"code": "002281", "name": "光迅科技", "layer": "foundation", "product": "光模块/光器件"},
        {"code": "688498", "name": "源杰科技", "layer": "foundation", "product": "光芯片"},
        {"code": "688313", "name": "仕佳光子", "layer": "foundation", "product": "光芯片/PLC"},
        {"code": "002463", "name": "沪电股份", "layer": "foundation", "product": "AI服务器高速PCB"},
        {"code": "002916", "name": "深南电路", "layer": "foundation", "product": "高速PCB/IC载板"},
        {"code": "300476", "name": "胜宏科技", "layer": "foundation", "product": "AI服务器PCB"},
        {"code": "600183", "name": "生益科技", "layer": "foundation", "product": "覆铜板/高速材料"},
        {"code": "002837", "name": "英维克", "layer": "supporting", "product": "数据中心液冷/温控"},
        {"code": "002335", "name": "科华数据", "layer": "infrastructure", "product": "数据中心/UPS电源"},
        {"code": "300442", "name": "润泽科技", "layer": "infrastructure", "product": "IDC/算力基础设施"},
        {"code": "300738", "name": "奥飞数据", "layer": "infrastructure", "product": "IDC"},
        {"code": "603881", "name": "数据港", "layer": "infrastructure", "product": "IDC"},
        {"code": "600845", "name": "宝信软件", "layer": "infrastructure", "product": "IDC/工业云"},
        {"code": "600522", "name": "中天科技", "layer": "infrastructure", "product": "算力中心电力配套/机电总包"},
        {"code": "600667", "name": "太极实业", "layer": "infrastructure", "product": "数据中心工程技术服务/EPC"},
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
        "company_chain_mapping": 0,
    }
    with psycopg2.connect(pg_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            validation = validate_codes(cur)
            if validation["missing_codes"]:
                raise RuntimeError(f"stocks table missing codes: {validation['missing_codes']}")
            for chain_id, config in CHAIN_CONFIGS.items():
                _persist_chain_nodes(cur, chain_id, config, counts)
                _persist_chain_mappings(cur, chain_id, config, counts)

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
                # EXISTING_TEMPLATE 链 (如具身智能) 也可带 MAPPINGS 种子, 与 CHAIN_CONFIGS 链同路径落映射
                if MAPPINGS.get(chain_id):
                    _persist_chain_mappings(cur, chain_id, config, counts)
        conn.commit()
    unique_companies = {item["code"] for items in MAPPINGS.values() for item in items}
    return {"counts": counts, "unique_companies": len(unique_companies), "mapping_rows": sum(len(items) for items in MAPPINGS.values())}


def _persist_chain_mappings(cur, chain_id: str, config: dict[str, Any], counts: dict[str, int]) -> None:
    # company_chain_mapping 无唯一键, 先按本链节点+种子代码清理再生行, 保证幂等
    chain_node_ids = [layer_node_id(chain_id, lid) for lid in LAYER_IDS]
    chain_codes = [item["code"] for item in MAPPINGS[chain_id]]
    cur.execute(
        "DELETE FROM company_chain_mapping WHERE node_id = ANY(%s) AND code = ANY(%s)",
        (chain_node_ids, chain_codes),
    )
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
        cur.execute(
            """
            INSERT INTO company_chain_mapping (
                code, node_id, main_pct, policy_match_score, chokepoint_score,
                evidence, three_factors, trade_signal
            )
            VALUES (%s, %s, NULL, NULL, 0, %s, %s, %s)
            """,
            (
                item["code"],
                layer_node_id(chain_id, layer_id),
                Json({
                    "source": "manual_priority_complex_chain_seed",
                    "chain_id": chain_id,
                    "layer_id": layer_id,
                    "product": product,
                    "company_name": item["name"],
                    "requires_original_evidence": True,
                }),
                Json({}),
                "观察",
            ),
        )
        counts["company_chain_mapping"] += 1


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
