# ChatBI 工具调用契约

- **日期**: 2026-07-03
- **阶段**: Design Gate D
- **调用方向**: Java ChatBI 后端 -> K线大模型 FastAPI 工具服务
- **原则**: 工具白名单、结构化输入输出、必须带数据日期和来源字段

## 1. 通用请求

```json
{
  "request_id": "req_001",
  "tool_id": "supply_chain_candidate_ranking",
  "user_id": "u_001",
  "agent_id": "supply_chain_research",
  "params": {},
  "limits": {
    "max_rows": 200,
    "timeout_ms": 10000
  }
}
```

## 2. 通用响应

```json
{
  "tool_id": "supply_chain_candidate_ranking",
  "status": "ok",
  "data_date": "2026-07-03",
  "source": "kline_model_db",
  "summary": "返回候选公司排名",
  "artifacts": [],
  "empty_reason": null,
  "elapsed_ms": 812
}
```

空状态必须返回：

```json
{
  "status": "empty",
  "empty_reason": "no_candidate",
  "next_action": "检查当日模型是否已运行"
}
```

## 3. 工具清单

### 3.1 `supply_chain_candidate_ranking`

用途：产业链候选公司排序。

Input:

```json
{
  "chain_name": "AI算力",
  "tag_level": "L5",
  "trade_date": "2026-07-03",
  "top_n": 20,
  "filters": {
    "three_high_required": true,
    "stage": ["商用放量", "验证放量"]
  }
}
```

Output:

```json
{
  "columns": ["code", "name", "chain_path", "score", "stage", "high_tech", "high_growth", "high_profit", "price", "change_pct"],
  "rows": [],
  "data_date": "2026-07-03",
  "source_fields": ["supply_chain_company_mapping", "market_snapshot", "evidence_chain"]
}
```

### 3.2 `company_evidence_chain`

用途：公司标签级证据链。

Input:

```json
{
  "code": "300308",
  "company_name": "中际旭创",
  "chain_name": "AI算力",
  "tag_level": "L8",
  "include": ["business_stage", "three_high", "revenue_mapping", "expectation_gap"]
}
```

Output:

```json
{
  "company": {"code": "300308", "name": "中际旭创"},
  "mappings": [
    {
      "mapping_id": "map_001",
      "chain_path": "AI算力 > 网络互联 > 光模块 > 800G",
      "business_stage": "商用放量",
      "three_high": {
        "high_tech": 91,
        "high_growth": 94,
        "high_profit": 86
      },
      "evidence": [
        {
          "evidence_id": "ev_001",
          "source_type": "公告",
          "source_date": "2026-04-28",
          "quote": "高速光模块产品批量交付...",
          "url": null,
          "confidence": 0.92
        }
      ]
    }
  ],
  "data_date": "2026-07-03"
}
```

### 3.3 `stock_model_run`

用途：选股模型结果汇总。

Input:

```json
{
  "model_id": "leader_afternoon",
  "trade_date": "2026-07-03",
  "include_failed_gates": true
}
```

Output:

```json
{
  "model_id": "leader_afternoon",
  "trade_date": "2026-07-03",
  "status": "done",
  "picks": [],
  "failed_gates": [],
  "data_cutoff": "2026-07-03T14:50:00+08:00"
}
```

### 3.4 `bond_model_run`

用途：选债模型结果汇总。

Input:

```json
{
  "model_id": "cb_auction",
  "trade_date": "2026-07-03",
  "run_time": "09:26",
  "include_failed_gates": true
}
```

Output:

```json
{
  "model_id": "cb_auction",
  "trade_date": "2026-07-03",
  "status": "done",
  "picks": [],
  "failed_gates": [
    {
      "gate": "竞价强度",
      "input_count": 128,
      "pass_count": 24,
      "reason": "动能不足"
    }
  ]
}
```

### 3.5 `model_no_pick_diagnosis`

用途：解释模型为什么没有票。

Input:

```json
{
  "model_id": "cb_auction",
  "trade_date": "2026-07-03",
  "asset_type": "convertible_bond"
}
```

Output:

```json
{
  "model_id": "cb_auction",
  "trade_date": "2026-07-03",
  "final_pick_count": 0,
  "gates": [
    {
      "gate_order": 1,
      "gate_name": "基础流动性",
      "input_count": 536,
      "pass_count": 128,
      "fail_reason_top": "成交额不足"
    }
  ],
  "diagnosis_available": true
}
```

### 3.6 `model_resonance`

用途：多模型、产业链、市场共振。

Input:

```json
{
  "trade_date": "2026-07-03",
  "scope": "all",
  "group_by": "company"
}
```

Output:

```json
{
  "trade_date": "2026-07-03",
  "items": [
    {
      "code": "300308",
      "name": "中际旭创",
      "hit_models": ["supply_chain", "market_momentum"],
      "hit_tags": ["AI算力", "光模块"],
      "resonance_score": 91.2
    }
  ]
}
```

### 3.7 `market_snapshot`

用途：行情快照。

Input:

```json
{
  "codes": ["300308"],
  "trade_date": "2026-07-03",
  "fields": ["price", "change_pct", "turnover", "volume"]
}
```

Output:

```json
{
  "trade_date": "2026-07-03",
  "items": [
    {
      "code": "300308",
      "price": 188.42,
      "change_pct": 4.82,
      "turnover": 1234567890
    }
  ],
  "data_cutoff": "2026-07-03T15:00:00+08:00"
}
```

### 3.8 `report_export`

用途：报告导出。

Input:

```json
{
  "message_id": "m_001",
  "template_version_id": "company_deep_report:v1",
  "format": "docx",
  "data_refs": ["company_evidence_chain:300308"]
}
```

Output:

```json
{
  "export_id": "r_001",
  "status": "running",
  "download_url": null
}
```

## 4. 工具调用限制

| 限制 | 默认值 |
|---|---:|
| 单次工具超时 | 10 秒 |
| 单次返回行数 | 200 |
| 并发工具数 | 3 |
| 导出最大行数 | 5000 |

## 5. 快速回答模板映射

| 模板 | 匹配问题 | 工具 |
|---|---|---|
| `candidate_ranking` | 候选公司、Top、排序 | `supply_chain_candidate_ranking` |
| `company_evidence` | 公司证据链、L8、三高 | `company_evidence_chain` |
| `stock_model_summary` | 选股模型结果 | `stock_model_run` |
| `bond_model_summary` | 选债模型结果 | `bond_model_run` |
| `no_pick_reason` | 为什么没票、无票原因 | `model_no_pick_diagnosis` |

快速回答如果未命中模板，返回 `CHATBI_TEMPLATE_NOT_FOUND`，前端提示用户切换“深度思考”。

