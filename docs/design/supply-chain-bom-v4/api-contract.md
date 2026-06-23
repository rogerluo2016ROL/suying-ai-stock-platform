# 大葱产业链 BOM V4 API Contract

本文档固定“产业链拆解”前端工作台使用的只读接口结构。交易信号仅用于研究排序，不触发自动交易。

## GET /api/v1/screener/supply-chain/themes

返回国家政策主题和板块矩阵摘要。

```json
{
  "version": "4.0",
  "source": "《求是》2026年第11期《前瞻布局和发展未来产业》...",
  "themes": [
    {
      "theme_id": "future_industry_core",
      "name": "未来产业主攻方向",
      "policy_weight": 1.5,
      "keywords": ["量子科技", "生物制造", "氢能", "核聚变能", "脑机接口", "具身智能", "第六代移动通信"],
      "node_count": 6,
      "matrix": {
        "policy_weight": 1.5,
        "high_growth": null,
        "high_profit": null,
        "high_moat": null
      }
    }
  ]
}
```

## GET /api/v1/screener/supply-chain/bom

返回可视化图谱所需的主题、节点、边。

```json
{
  "version": "4.0",
  "themes": [
    {
      "theme_id": "future_industry_core",
      "name": "未来产业主攻方向",
      "policy_weight": 1.5
    }
  ],
  "nodes": [
    {
      "node_id": "embodied_ai_core",
      "theme_id": "future_industry_core",
      "chain_id": "embodied_ai",
      "level": "chain",
      "name": "具身智能",
      "node_type": "industry",
      "policy_theme": "未来产业主攻方向",
      "bom_path": ["未来产业主攻方向", "具身智能"],
      "keywords": ["具身智能", "机器人", "伺服", "减速器", "控制器"],
      "companies": []
    }
  ],
  "edges": []
}
```

## GET /api/v1/screener/supply-chain/node/{node_id}

返回单个 BOM 节点的企业、产品和证据列表。数据库证据未同步时，数组为空。

```json
{
  "node_id": "embodied_ai_core",
  "policy_theme": "未来产业主攻方向",
  "bom_path": ["未来产业主攻方向", "具身智能"],
  "node": {
    "node_id": "embodied_ai_core",
    "name": "具身智能",
    "level": "chain",
    "node_type": "industry"
  },
  "companies": [
    {
      "code": "688001",
      "name": "测试科技",
      "rank": 1,
      "rating": "A",
      "trade_signal": "启动",
      "product_name": "关节模组",
      "material_name": "高精密减速器"
    }
  ],
  "evidence": []
}
```

## GET /api/v1/screener/supply-chain/company/{code}

返回上市公司级下钻信息，用于“公司-产品/材料-财务指标-护城河证据”面板。

```json
{
  "code": "688001",
  "rank": 1,
  "rating": "A",
  "trade_signal": "启动",
  "policy_theme": "未来产业主攻方向",
  "bom_path": ["未来产业主攻方向", "具身智能", "核心部件"],
  "products": ["关节模组"],
  "materials": ["高精密减速器"],
  "financial_indicators": {
    "revenue_growth": 28.5,
    "profit_growth": 31.2,
    "roe": 15.6,
    "gross_margin": 42.1
  },
  "moat_evidence": [
    {
      "evidence_type": "patent",
      "summary": "核心专利覆盖关键工艺",
      "confidence": 0.86,
      "source": "company_announcement"
    }
  ],
  "evidence": []
}
```

## POST /api/v1/screener/supply-chain/extract

对政策、公告、研报文本做结构化抽取。无 `DEEPSEEK_API_KEY` 时返回禁用状态，不写图谱。

Request:

```json
{
  "text": "公司公告：具身智能关节模组已小批量交付",
  "persist": false,
  "source": {
    "source_type": "manual_paste",
    "title": "测试公告",
    "published_at": "2026-06-23"
  }
}
```

Response:

```json
{
  "status": "ok",
  "policy_theme": "未来产业主攻方向",
  "bom_nodes": ["具身智能", "核心部件"],
  "companies": [{"code": "688001", "name": "测试科技"}],
  "products": ["关节模组"],
  "materials": ["高精密减速器"],
  "commercialization_stage": "小批量",
  "evidence": [
    {
      "summary": "产品已小批量交付",
      "excerpt": "关节模组已小批量交付",
      "confidence": 0.82,
      "evidence_date": "2026-06-23",
      "source_type": "announcement"
    }
  ],
  "usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 260,
    "total_tokens": 1460
  },
  "persisted": false,
  "records": {
    "source": {
      "source_id": "src_xxx",
      "source_type": "manual_paste",
      "title": "测试公告"
    },
    "mappings": [
      {
        "mapping_id": "map_xxx",
        "code": "688001",
        "node_id": "embodied_ai_core",
        "product_name": "关节模组",
        "material_name": "高精密减速器",
        "status": "pending_review"
      }
    ],
    "evidence": [
      {
        "evidence_id": "ev_xxx",
        "code": "688001",
        "node_id": "embodied_ai_core",
        "summary": "产品已小批量交付",
        "confidence": 0.82,
        "status": "pending_review"
      }
    ]
  }
}
```

Disabled response:

```json
{
  "status": "disabled",
  "reason": "DEEPSEEK_API_KEY missing"
}
```
