from app.supply_chain_graph_store import build_graph_records


def test_build_graph_records_from_extraction_result():
    extraction = {
        "policy_theme": "未来产业主攻方向",
        "bom_nodes": ["具身智能"],
        "companies": [{"code": "688001", "name": "测试科技"}],
        "products": ["关节模组"],
        "materials": ["高精密减速器"],
        "commercialization_stage": "小批量",
        "evidence": [{
            "summary": "关节模组已小批量交付",
            "excerpt": "公司公告：关节模组已小批量交付",
            "confidence": 0.82,
            "evidence_date": "2026-06-23",
            "source_type": "announcement",
        }],
    }
    source = {
        "title": "测试公告",
        "source_type": "announcement",
        "source_url": "https://example.test/notice",
        "published_at": "2026-06-23",
    }

    records = build_graph_records(extraction, source)

    assert records["source"]["title"] == "测试公告"
    assert records["source"]["source_id"].startswith("src_")
    assert records["mappings"][0]["code"] == "688001"
    assert records["mappings"][0]["product_name"] == "关节模组"
    assert records["mappings"][0]["material_name"] == "高精密减速器"
    assert records["mappings"][0]["status"] == "pending_review"
    assert records["evidence"][0]["evidence_type"] == "announcement"
    assert records["evidence"][0]["confidence"] == 0.82
    assert records["evidence"][0]["status"] == "pending_review"
