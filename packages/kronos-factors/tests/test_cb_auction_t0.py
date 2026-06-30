from kronos_factors.engine.cb_auction_t0 import (
    _is_noise_concept,
    _normalize_stock_code,
    _risk_notes,
    _theme_score,
)
from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine


def test_normalize_stock_code_handles_suffix_and_plain_code():
    assert _normalize_stock_code("300001.SZ") == "300001"
    assert _normalize_stock_code("600000") == "600000"
    assert _normalize_stock_code(None) == ""


def test_noise_concept_filter_removes_style_and_region_labels():
    assert _is_noise_concept("昨日涨停") is True
    assert _is_noise_concept("百日新高") is True
    assert _is_noise_concept("浙江") is True
    assert _is_noise_concept("机器人") is False
    assert _is_noise_concept("固态电池") is False


def test_risk_notes_are_annotations():
    row = {
        "call_status": "公告实施强赎",
        "premium_rate": 68.2,
        "cb_amount": 5_000_000,
        "remain_size": 1_800_000_000,
        "delist_date": "2026-07-05",
    }

    notes = _risk_notes(row)

    assert "强赎中" in notes
    assert "高溢价68.2%" in notes
    assert "成交额偏低500.0万" in notes
    assert "剩余规模18.00亿" in notes
    assert "退市日期2026-07-05" in notes


def test_theme_score_ignores_risk_fields():
    safe = {
        "is_direct_trigger": False,
        "matched_concept_count": 2,
        "trigger_stock_count_sum": 3,
        "matched_fd_amount": 2_000_000_000,
        "concept_size_min": 8,
        "premium_rate": 2.0,
        "call_status": "安全",
    }
    risky = dict(safe, premium_rate=80.0, call_status="公告实施强赎")

    assert _theme_score(safe) == _theme_score(risky)


def test_assemble_result_sorts_by_theme_relevance_and_keeps_risky_bond():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = [
        {
            "trigger_stock_code": "300001",
            "trigger_stock_name": "触发科技",
            "fd_amount": 1_500_000_000,
            "fd_amount_yi": 15.0,
            "first_time": "09:25:00",
            "prev_was_limit_up": False,
        }
    ]
    concepts = [
        {
            "concept_code": "886001.TI",
            "concept_name": "机器人",
            "trigger_stock_count": 1,
            "concept_fd_amount": 1_500_000_000,
            "concept_fd_amount_yi": 15.0,
            "trigger_sources": ["300001"],
            "concept_size": 2,
        }
    ]
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "触发转债",
            "stk_code": "300001",
            "stk_name": "触发科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_500_000_000,
            "concept_size_min": 2,
            "premium_rate": 85.0,
            "cb_amount": 1_000_000,
            "remain_size": 2_000_000_000,
            "call_status": "公告实施强赎",
            "delist_date": "2026-07-05",
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "跟随转债",
            "stk_code": "300002",
            "stk_name": "跟随科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_500_000_000,
            "concept_size_min": 2,
            "premium_rate": 3.0,
            "cb_amount": 80_000_000,
            "remain_size": 300_000_000,
            "call_status": "安全",
            "delist_date": None,
        },
    ]

    result = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=10)

    assert [bond["cb_code"] for bond in result["bonds"]] == ["123001.SZ", "123002.SZ"]
    assert result["bonds"][0]["relation_reason"] == "正股为触发股，命中机器人"
    assert "强赎中" in result["bonds"][0]["risk_notes"]
    assert "高溢价85.0%" in result["bonds"][0]["risk_notes"]


def test_assemble_result_dedupes_same_bond_and_merges_concepts():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = []
    concepts = []
    raw_bonds = [
        {
            "cb_code": "123003.SZ",
            "cb_name": "多题材转债",
            "stk_code": "300003",
            "stk_name": "多题材",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_100_000_000,
            "concept_size_min": 6,
        },
        {
            "cb_code": "123003.SZ",
            "cb_name": "多题材转债",
            "stk_code": "300003",
            "stk_name": "多题材",
            "matched_concepts": ["减速器"],
            "trigger_sources": ["300004"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_200_000_000,
            "concept_size_min": 4,
        },
    ]

    result = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=None)

    assert len(result["bonds"]) == 1
    assert result["bonds"][0]["matched_concepts"] == ["减速器", "机器人"]
    assert result["bonds"][0]["trigger_sources"] == ["300001", "300004"]


def test_assemble_result_normalizes_trigger_stock_code_for_direct_match():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = [
        {
            "trigger_stock_code": "300001.SZ",
            "trigger_stock_name": "触发科技",
        }
    ]
    concepts = []
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "直接转债",
            "stk_code": "300001",
            "stk_name": "触发科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001.SZ"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_100_000_000,
            "concept_size_min": 3,
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "非直接转债",
            "stk_code": "300002",
            "stk_name": "跟随科技",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001.SZ"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_200_000_000,
            "concept_size_min": 3,
        },
    ]

    result = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=10)

    assert result["bonds"][0]["cb_code"] == "123001.SZ"
    assert result["bonds"][0]["is_direct_trigger"] is True
    assert result["bonds"][1]["is_direct_trigger"] is False


def test_assemble_result_top_n_zero_and_none():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    triggers = [
        {
            "trigger_stock_code": "300001",
            "trigger_stock_name": "触发科技",
        }
    ]
    concepts = []
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "第一只转债",
            "stk_code": "300001",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_500_000_000,
            "concept_size_min": 3,
            "matched_concept_count": 1,
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "第二只转债",
            "stk_code": "300002",
            "matched_concepts": ["机器人"],
            "trigger_sources": ["300001"],
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 1_400_000_000,
            "concept_size_min": 3,
            "matched_concept_count": 1,
        },
    ]

    zero = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=0)
    all_bonds = engine._assemble_result("2026-06-30", triggers, concepts, raw_bonds, top_n=None)

    assert zero["bonds"] == []
    assert len(all_bonds["bonds"]) == 2


def test_run_assembles_fetcher_outputs_without_postgres(monkeypatch):
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")

    class DummyCursor:
        pass

    class DummyConn:
        closed = False

        def cursor(self):
            return DummyCursor()

        def close(self):
            self.closed = True

    engine._conn = DummyConn()
    monkeypatch.setattr(engine, "_fetch_effective_trade_date", lambda cur, trade_date: "2026-06-30")
    monkeypatch.setattr(engine, "_fetch_previous_trade_date", lambda cur, trade_date: "2026-06-29")
    monkeypatch.setattr(
        engine,
        "_fetch_trigger_stocks",
        lambda cur, trade_date, prev_trade_date: (
            [
                {
                    "trigger_stock_code": "300001",
                    "trigger_stock_name": "触发科技",
                    "fd_amount": 1_500_000_000,
                    "fd_amount_yi": 15.0,
                    "first_time": "09:25:00",
                    "prev_was_limit_up": False,
                }
            ],
            [{"code": "300009", "reason": "封单金额缺失"}],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_fetch_concepts",
        lambda cur, triggers: (
            [
                {
                    "concept_code": "886001.TI",
                    "concept_name": "机器人",
                    "trigger_stock_count": 1,
                    "concept_fd_amount": 1_500_000_000,
                    "concept_fd_amount_yi": 15.0,
                    "trigger_sources": ["300001"],
                    "concept_size": 2,
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        engine,
        "_fetch_bonds",
        lambda cur, trade_date, concepts: (
            [
                {
                    "cb_code": "123001.SZ",
                    "cb_name": "触发转债",
                    "stk_code": "300001",
                    "stk_name": "触发科技",
                    "matched_concepts": ["机器人"],
                    "trigger_sources": ["300001"],
                    "matched_concept_count": 1,
                    "trigger_stock_count_sum": 1,
                    "matched_fd_amount": 1_500_000_000,
                    "concept_size_min": 2,
                }
            ],
            [],
        ),
    )

    result = engine.run(top_n=5)

    assert result["trade_date"] == "2026-06-30"
    assert result["trigger_stocks"][0]["trigger_stock_code"] == "300001"
    assert result["bonds"][0]["cb_code"] == "123001.SZ"
    assert result["rejections"] == [{"code": "300009", "reason": "封单金额缺失"}]


def test_cli_write_outputs_creates_json_and_csv(tmp_path):
    import json
    import importlib.util
    from pathlib import Path

    tool_path = Path("tools/cb_auction_t0_picks.py")
    spec = importlib.util.spec_from_file_location("cb_auction_t0_picks", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = {
        "trade_date": "2026-06-30",
        "trigger_stocks": [],
        "concepts": [],
        "bonds": [
            {
                "cb_code": "123001.SZ",
                "cb_name": "触发转债",
                "stk_code": "300001",
                "stk_name": "触发科技",
                "matched_concepts": ["机器人"],
                "trigger_sources": ["300001"],
                "theme_score": 111.0,
                "premium_rate": 85.0,
                "cb_amount": 1_000_000,
                "remain_size_yi": 20.0,
                "call_status": "公告实施强赎",
                "risk_notes": ["强赎中", "高溢价85.0%"],
                "relation_reason": "正股为触发股，命中机器人",
            }
        ],
        "rejections": [],
    }

    json_path, csv_path = module.write_outputs(result, str(tmp_path))

    assert Path(json_path).exists()
    assert Path(csv_path).exists()
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert data["bonds"][0]["risk_notes"] == ["强赎中", "高溢价85.0%"]
    csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
    assert "触发转债" in csv_text
    assert "公告实施强赎" in csv_text
    assert "高溢价85.0%" in csv_text
    assert "85.0" in csv_text
    assert "20.0" in csv_text


def test_engine_package_exports_cb_auction_t0():
    from kronos_factors.engine import CbAuctionT0Engine

    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    assert engine.pg_url == "postgresql://unit/unit"
