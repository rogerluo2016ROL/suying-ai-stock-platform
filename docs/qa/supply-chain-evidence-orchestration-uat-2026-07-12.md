# 灵巧手产业链证据编排 UAT QA

- 状态：PASS_WITH_LIMITATIONS
- 数据库 revision：033
- 历史截止日：2026-07-09 (Asia/Shanghai)
- synthetic reviewed_at：2026-07-12T04:47:25.425985+00:00
- synthetic 上海 review date：2026-07-12
- UAT 没有批准五家真实公司事实。
- 模型仍为 staging；本 UAT 不能证明投资有效性，不构成自动买入信号。

## 来源、计数与四池

```json
{
  "source_failures": [
    "DEXH-300660-5ace7f722401:business_presence",
    "DEXH-300660-5ace7f722401:customer_validation",
    "DEXH-300660-5ace7f722401:order_or_delivery",
    "DEXH-300660-5ace7f722401:product_or_prototype",
    "DEXH-300660-5ace7f722401:recognized_profit",
    "DEXH-300660-5ace7f722401:recognized_revenue"
  ],
  "count_snapshots": {
    "before": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33847,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    },
    "after_dry_run": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33847,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    },
    "after_collect_1": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33848,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    },
    "after_collect_2": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33848,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    },
    "after_real_score": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33848,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    },
    "inside_synthetic_before_rollback": {
      "raw_evidence_documents": 33659,
      "evidence_extracted_facts": 33851,
      "business_tag_evidence_events": 38165,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 8,
      "business_tag_operating_quality_scores": 8,
      "business_tag_benefit_scores": 8,
      "business_tag_selection_scores": 8,
      "business_tag_pool_state": 7,
      "business_tag_pool_transition_log": 7,
      "evidence_collection_jobs": 40
    },
    "after_synthetic_rollback": {
      "raw_evidence_documents": 33657,
      "evidence_extracted_facts": 33848,
      "business_tag_evidence_events": 38162,
      "evidence_gaps": 0,
      "business_tag_authenticity_scores": 6,
      "business_tag_operating_quality_scores": 6,
      "business_tag_benefit_scores": 6,
      "business_tag_selection_scores": 6,
      "business_tag_pool_state": 6,
      "business_tag_pool_transition_log": 6,
      "evidence_collection_jobs": 40
    }
  },
  "real_company_review_status": {
    "before": {
      "003021": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "300007": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "300660": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "603662": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "603728": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      }
    },
    "after": {
      "003021": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "300007": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "300660": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "603662": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      },
      "603728": {
        "confirmed_fact_ids": [],
        "approved_event_ids": [],
        "approved_monitor_ids": [],
        "approved_stage_ids": []
      }
    },
    "evidence": "read-only set equality"
  },
  "pool_counts": {
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 6
  },
  "axial_flux": {
    "scope": "unrestricted_candidate_universe",
    "requirement_id": "dexterous_axial_flux_motor",
    "seed_company_codes": [],
    "hits": 1,
    "excluded": 0,
    "pending": 1,
    "inserted_documents": 0,
    "duplicate_documents": 1,
    "failed_tasks": [],
    "data_limitations": [],
    "network_requests": 12,
    "mapped_collect_scope": [
      "003021",
      "300007",
      "300660",
      "603662",
      "603728"
    ],
    "independent_discovery_scope": "unrestricted_candidate_universe",
    "first_run": {
      "scope": "unrestricted_candidate_universe",
      "requirement_id": "dexterous_axial_flux_motor",
      "seed_company_codes": [],
      "hits": 1,
      "excluded": 0,
      "pending": 1,
      "inserted_documents": 0,
      "duplicate_documents": 1,
      "failed_tasks": [],
      "data_limitations": [],
      "network_requests": 12
    },
    "failures": [
      "DEXH-300660-5ace7f722401:business_presence",
      "DEXH-300660-5ace7f722401:customer_validation",
      "DEXH-300660-5ace7f722401:order_or_delivery",
      "DEXH-300660-5ace7f722401:product_or_prototype",
      "DEXH-300660-5ace7f722401:recognized_profit",
      "DEXH-300660-5ace7f722401:recognized_revenue"
    ],
    "evidence": "mapped collect fixed to five companies; AF discovery used unrestricted candidates"
  },
  "missing_inputs": [
    "Repository/scorer contracts force derived FACT-/EV-/score/transition IDs; exact fact/event IDs were read from PendingDocumentOutcome and all derived rows were verified by exact ID or mapping_id after rollback.",
    "adapter_error:DocumentFetchError: official_ir: DocumentFetchError: official IR failures: official IR homepage HTTP 403 or empty response",
    "missing_audited_stage",
    "missing_catalyst_score",
    "missing_claim_risk_penalty_score",
    "missing_evidence_delta_score",
    "missing_expectation_gap_score",
    "missing_market_expectation_score",
    "missing_node_score",
    "missing_risk_score",
    "unaudited_commercial_stage",
    "模型仍为 staging；本 UAT 不具有投资有效性，不构成自动买入结论。"
  ],
  "rollback_cleanup": {
    "counts": {
      "business_tag_mapping": 0,
      "evidence_source_catalog": 0,
      "raw_evidence_documents": 0,
      "evidence_extracted_facts": 0,
      "business_tag_evidence_events": 0,
      "business_tag_expectation_monitor": 0,
      "business_tag_stage_tracking": 0,
      "business_tag_authenticity_scores": 0,
      "business_tag_operating_quality_scores": 0,
      "business_tag_benefit_scores": 0,
      "business_tag_selection_scores": 0,
      "business_tag_pool_state": 0,
      "business_tag_pool_transition_log": 0
    },
    "evidence": "fresh-connection exact-ID zero residual"
  }
}
```

## 设计偏差

Repository/scorer contracts force derived FACT-/EV-/score/transition IDs; exact fact/event IDs were read from PendingDocumentOutcome and all derived rows were verified by exact ID or mapping_id after rollback.
