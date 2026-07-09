# Industry Chain Evidence Schema

## Layer Metrics

`metrics` 是每层内部指标分组。

```json
{
  "commercialization": ["订单", "出货", "收入确认"],
  "expectation_gap": ["订单超预期", "价格上行", "客户认证提前"],
  "trigger_signals": ["大客户公告", "财报指引上修", "招标启动"]
}
```

## Layer CAPEX Evidence

CAPEX 证据必须挂到具体层级。

```json
{
  "evidence_id": "msft_ai_datacenter_capex",
  "company": "Microsoft",
  "region": "US",
  "fiscal_period": "unknown",
  "capex_amount": null,
  "currency": "USD",
  "capex_direction": ["AI data center"],
  "mapped_layer_id": "infrastructure",
  "mapped_segments": ["IDC", "液冷", "AI服务器"],
  "metric_usage": ["commercialization", "expectation_gap"],
  "source_type": "earnings_call",
  "source_name": "Investor relations / earnings call",
  "source_url": "",
  "quote": "",
  "as_of_date": "2026-07-08",
  "evidence_level": "manual_judgement",
  "collection_method": "manual_first"
}
```

## Layer Physical Metric

产业物理指标必须挂到具体层级和环节。

```json
{
  "metric_id": "foundation_hbm_supply_gap",
  "name": "HBM 供需缺口",
  "mapped_layer_id": "foundation",
  "mapped_segment": "HBM",
  "metric_usage": ["commercialization", "expectation_gap", "trigger_signals"],
  "data_type": "number_or_event",
  "value": null,
  "unit": "",
  "period": "unknown",
  "direction": "higher_means_tighter_supply",
  "source_type": "industry_research",
  "source_name": "研报/公司公告/产业新闻",
  "source_url": "",
  "evidence_level": "manual_judgement",
  "collection_method": "manual_first",
  "as_of_date": "2026-07-08"
}
```

## Evidence Chain

`evidence_chain` 是层级内统一证据视图，由 CAPEX 证据和产业物理指标转换得到。

```json
{
  "evidence_id": "msft_ai_datacenter_capex",
  "evidence_type": "capex",
  "mapped_layer_id": "infrastructure",
  "mapped_segment": "IDC",
  "source_type": "earnings_call",
  "source_name": "Investor relations / earnings call",
  "evidence_level": "manual_judgement",
  "as_of_date": "2026-07-08",
  "metric_usage": ["commercialization", "expectation_gap"],
  "impact_direction": "positive",
  "confidence": "medium"
}
```

## Expectation Gap

第一版不重算现有公式，只保留结构和证据追溯。

```json
{
  "expected": {"value": null, "source": "unknown"},
  "actual": {"value": null, "source": "unknown"},
  "gap_direction": "unknown",
  "gap_strength": "unknown",
  "calculation_method": "existing_business_tag_formula_unavailable",
  "evidence_ids": []
}
```

## Trigger Signal

启动信号必须能追溯到 evidence ids。

```json
{
  "signal_type": "unknown",
  "signal_strength": "unknown",
  "triggered_by_evidence_ids": [],
  "mapped_layer_id": "infrastructure",
  "mapped_segments": []
}
```

## Macro Context

宏观环境只放顶层，不直接进入层级预期差。

```json
{
  "region": "US",
  "policy_stance": "unknown",
  "inflation_state": "unknown",
  "rate_trend": "unknown",
  "liquidity_signal": "unknown",
  "source_type": "official_pending",
  "source_name": "Fed / BLS / BEA",
  "source_url": "",
  "as_of_date": "2026-07-08",
  "evidence_level": "unknown"
}
```
