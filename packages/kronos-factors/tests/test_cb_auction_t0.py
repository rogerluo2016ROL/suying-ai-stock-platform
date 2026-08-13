import pytest

from kronos_factors.engine.cb_auction_t0 import (
    CbAuctionT0V21Engine,
    _is_noise_concept,
    _normalize_stock_code,
    _risk_notes,
    _theme_score,
)
from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine, CbAuctionT0V2Engine


def test_normalize_stock_code_handles_suffix_and_plain_code():
    assert _normalize_stock_code("300001.SZ") == "300001"
    assert _normalize_stock_code("600000") == "600000"
    assert _normalize_stock_code(None) == ""


def test_noise_concept_filter_removes_style_and_region_labels():
    assert _is_noise_concept("昨日涨停") is True
    assert _is_noise_concept("百日新高") is True
    assert _is_noise_concept("近期强势") is True
    assert _is_noise_concept("上证380成份股") is True
    assert _is_noise_concept("中证500成份股") is True
    assert _is_noise_concept("沪股通") is True
    assert _is_noise_concept("最近多板") is True
    assert _is_noise_concept("增持计划") is True
    assert _is_noise_concept("社保新进") is True
    assert _is_noise_concept("融资融券") is True
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


def test_theme_score_does_not_reward_narrow_concepts():
    wide = {
        "is_direct_trigger": False,
        "matched_concept_count": 1,
        "trigger_stock_count_sum": 1,
        "matched_fd_amount": 600_000_000,
        "concept_size_min": 80,
    }
    narrow = dict(wide, concept_size_min=2)

    assert _theme_score(wide) == _theme_score(narrow)


def test_assemble_result_does_not_sort_by_concept_size():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "宽概念转债",
            "stk_code": "300101",
            "stk_name": "宽概念",
            "matched_concepts": ["强势概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 600_000_000,
            "concept_size_min": 80,
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "窄概念转债",
            "stk_code": "300102",
            "stk_name": "窄概念",
            "matched_concepts": ["强势概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 600_000_000,
            "concept_size_min": 2,
        },
    ]

    result = engine._assemble_result("2026-06-30", [], [], raw_bonds, top_n=None)

    assert [bond["cb_code"] for bond in result["bonds"]] == ["123001.SZ", "123002.SZ"]


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
        lambda cur, triggers, trade_date=None: (
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


def test_fetch_trigger_stocks_uses_limit_list_ts_code_schema():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    engine.use_kpl_list_fallback = False

    class SchemaCheckingCursor:
        calls = 0

        def execute(self, sql, params):
            self.calls += 1
            assert "l.code" not in sql
            assert "p.code" not in sql
            assert "l.ts_code" in sql
            assert "p.ts_code" in sql

        def fetchall(self):
            return []

    triggers, rejections = engine._fetch_trigger_stocks(
        SchemaCheckingCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert triggers == []
    assert rejections == []


def test_fetch_trigger_stocks_normalizes_hhmmss_first_time_in_sql():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    engine.use_kpl_list_fallback = False
    engine.use_eastmoney_limit_pool_fallback = False
    captured = {}

    class TimeCheckingCursor:
        calls = 0

        def execute(self, sql, params):
            self.calls += 1
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    engine._fetch_trigger_stocks(
        TimeCheckingCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert "LPAD(REPLACE(l.first_time, ':', ''), 6, '0') <= %s" in captured["sql"]
    assert "SELECT DISTINCT ON (SPLIT_PART(l.ts_code, '.', 1))" in captured["sql"]
    assert "093000" in captured["params"]


def test_fetch_trigger_stocks_rejects_missing_small_and_yesterday_limit_up():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")

    class DummyCursor:
        def execute(self, sql, params):
            pass

        def fetchall(self):
            return [
                ("300001.SZ", "封单缺失", None, "09:25:00", "limit_list_d", False),
                ("300002.SZ", "封单不足", 500_000_000, "09:25:00", "limit_list_d", False),
                ("300003.SZ", "昨日涨停", 1_500_000_000, "09:25:00", "limit_list_d", True),
                ("300004.SZ", "有效触发", 510_000_000, "09:25:00", "limit_list_d", False),
            ]

    triggers, rejections = engine._fetch_trigger_stocks(
        DummyCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert triggers == [
        {
            "trigger_stock_code": "300004",
            "trigger_stock_name": "有效触发",
            "fd_amount": 510_000_000.0,
            "fd_amount_yi": 5.1,
            "first_time": "09:25:00",
            "prev_was_limit_up": False,
            "trigger_data_source": "limit_list_d",
        }
    ]
    assert rejections == [
        {"code": "300001", "name": "封单缺失", "reason": "封单金额缺失"},
        {"code": "300002", "name": "封单不足", "reason": "封单金额不足5亿"},
        {"code": "300003", "name": "昨日涨停", "reason": "昨日已涨停"},
    ]


def test_v2_fetch_trigger_stocks_requires_seven_yi_fd_amount():
    engine = CbAuctionT0V2Engine(pg_url="postgresql://unit/unit")

    class DummyCursor:
        def execute(self, sql, params):
            pass

        def fetchall(self):
            return [
                ("300002.SZ", "六亿封单", 650_000_000, "09:25:00", "limit_list_d", False),
                ("300004.SZ", "七亿封单", 710_000_000, "09:25:00", "limit_list_d", False),
            ]

    triggers, rejections = engine._fetch_trigger_stocks(
        DummyCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert [row["trigger_stock_code"] for row in triggers] == ["300004"]
    assert rejections == [{"code": "300002", "name": "六亿封单", "reason": "封单金额不足7亿"}]


def test_fetch_trigger_stocks_falls_back_to_kpl_list_limit_order_when_limit_list_empty():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")

    class FallbackCursor:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params):
            self.calls += 1
            if self.calls == 1:
                assert "FROM limit_list_d l" in sql
            else:
                assert "FROM kpl_list k" in sql
                assert "k.limit_order AS fd_amount" in sql

        def fetchall(self):
            if self.calls == 1:
                return []
            return [
                ("300010.SZ", "开盘啦触发", 900_000_000, "09:25:00", "kpl_list", False),
            ]

    triggers, rejections = engine._fetch_trigger_stocks(
        FallbackCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert triggers == [
        {
            "trigger_stock_code": "300010",
            "trigger_stock_name": "开盘啦触发",
            "fd_amount": 900_000_000.0,
            "fd_amount_yi": 9.0,
            "first_time": "09:25:00",
            "prev_was_limit_up": False,
            "trigger_data_source": "kpl_list",
        }
    ]
    assert rejections == [
        {
            "reason": "limit_list_d为空，使用kpl_list.limit_order作为封单金额",
            "data_source": "kpl_list",
        }
    ]


def test_fetch_pending_confirmation_stocks_uses_auction_price_and_limit_price_only():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")

    class PendingCursor:
        def execute(self, sql, params):
            assert "FROM stk_auction_o a" in sql
            assert "JOIN stk_limit l" in sql
            assert "l.code = a.code" in sql
            assert "a.open >= l.up_limit" in sql

        def fetchall(self):
            return [
                ("300020.SZ", "待确认一字", 11.0, 120_000_000, 11.0, False),
                ("300021.SZ", "昨日涨停", 12.0, 80_000_000, 12.0, True),
            ]

    pending = engine._fetch_pending_confirmation_stocks(
        PendingCursor(),
        "2026-06-30",
        "2026-06-29",
    )

    assert pending == [
        {
            "trigger_stock_code": "300020",
            "trigger_stock_name": "待确认一字",
            "auction_price": 11.0,
            "auction_amount": 120_000_000.0,
            "auction_amount_yi": 1.2,
            "up_limit": 11.0,
            "confirmation_status": "待确认真实封单金额",
            "data_source": "stk_auction+stk_limit",
        }
    ]


def test_v2_filters_weak_theme_concepts_before_selecting_top_two():
    engine = CbAuctionT0V2Engine(pg_url="postgresql://unit/unit")

    class DummyCursor:
        def execute(self, sql, params):
            pass

        def fetchall(self):
            return [
                ("881001.TI", "沪深300样本股", "300001", 300, 3.0, 300),
                ("886001.TI", "机器人", "300001", 40, 0.2, 40),
                ("886002.TI", "低市盈率", "300001", 120, 0.5, 120),
            ]

    concepts, rejections = engine._fetch_concepts(
        DummyCursor(),
        [
            {
                "trigger_stock_code": "300001",
                "trigger_stock_name": "触发科技",
                "fd_amount": 800_000_000,
            }
        ],
        "2026-06-30",
    )

    assert [row["concept_name"] for row in concepts] == ["机器人"]
    assert rejections == []


def test_v2_assemble_result_adds_quality_tiers_from_concept_strength():
    engine = CbAuctionT0V2Engine(pg_url="postgresql://unit/unit")
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "A档转债",
            "stk_code": "300101",
            "stk_name": "强题材",
            "matched_concepts": ["强概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.12,
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "B档转债",
            "stk_code": "300102",
            "stk_name": "普通题材",
            "matched_concepts": ["普通概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.05,
        },
        {
            "cb_code": "123003.SZ",
            "cb_name": "C档转债",
            "stk_code": "300103",
            "stk_name": "弱题材",
            "matched_concepts": ["弱概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": -0.01,
        },
    ]

    result = engine._assemble_result("2026-06-30", [], [], raw_bonds, top_n=None)

    assert result["model"] == "cb_auction_t0_v2"
    assert [bond["quality_tier"] for bond in result["bonds"]] == ["A", "B", "C"]


def test_v21_assemble_result_keeps_a_tier_main_and_non_a_observation():
    engine = CbAuctionT0V21Engine(pg_url="postgresql://unit/unit")
    raw_bonds = [
        {
            "cb_code": "123001.SZ",
            "cb_name": "A档转债",
            "stk_code": "300101",
            "stk_name": "强题材",
            "matched_concepts": ["强概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.12,
        },
        {
            "cb_code": "123002.SZ",
            "cb_name": "B档转债",
            "stk_code": "300102",
            "stk_name": "普通题材",
            "matched_concepts": ["普通概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.05,
        },
        {
            "cb_code": "123005.SZ",
            "cb_name": "负概念转债",
            "stk_code": "300105",
            "stk_name": "负概念题材",
            "matched_concepts": ["弱概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": -0.03,
        },
        {
            "cb_code": "123003.SZ",
            "cb_name": "ST转债",
            "stk_code": "300103",
            "stk_name": "*ST题材",
            "matched_concepts": ["强概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.2,
        },
        {
            "cb_code": "123004.SZ",
            "cb_name": "已退转债",
            "stk_code": "300104",
            "stk_name": "退市题材",
            "matched_concepts": ["强概念"],
            "trigger_sources": ["300001"],
            "matched_concept_count": 1,
            "trigger_stock_count_sum": 1,
            "matched_fd_amount": 800_000_000,
            "concept_size_min": 20,
            "matched_concept_strength": 0.2,
            "delist_date": "2026-06-01",
        },
    ]

    result = engine._assemble_result("2026-06-30", [], [], raw_bonds, top_n=None)

    assert result["model"] == "cb_auction_t0_v2_1"
    assert [bond["cb_code"] for bond in result["bonds"]] == ["123001.SZ"]
    assert result["bonds"][0]["quality_tier"] == "A"
    assert [bond["cb_code"] for bond in result["observation_bonds"]] == ["123002.SZ", "123005.SZ"]
    assert [bond["list_type"] for bond in result["observation_bonds"]] == ["观察", "观察"]
    assert [bond["observation_reason"] for bond in result["observation_bonds"]] == ["非A档观察", "非A档观察"]
    assert {item["reason"] for item in result["rejections"]} == {"ST正股剔除", "已退市转债剔除"}


def test_rolling_weak_concept_filter_uses_prior_calendar_when_enabled():
    class RollingWeakConceptEngine(CbAuctionT0V21Engine):
        rolling_weak_concept_window = 20
        rolling_weak_concept_strength_max = -0.2
        rolling_weak_concept_min_samples = 5

    engine = RollingWeakConceptEngine(pg_url="postgresql://unit/unit")
    captured_params = []
    captured_sql = []

    class DummyCursor:
        def execute(self, sql, params):
            captured_sql.append(sql)
            captured_params.append(params)

        def fetchall(self):
            if len(captured_params) == 1:
                return [("886001.TI", "历史弱概念")]
            return [
                ("886001.TI", "历史弱概念", "300001", 20, 0.5, 20),
                ("886002.TI", "当日强概念", "300001", 20, 0.4, 20),
            ]

    concepts, rejections = engine._fetch_concepts(
        DummyCursor(),
        [
            {
                "trigger_stock_code": "300001",
                "trigger_stock_name": "触发科技",
                "fd_amount": 800_000_000,
            }
        ],
        "2026-06-30",
    )

    assert captured_params[0] == ("2026-06-30", 20, -0.2, 5)
    assert "SELECT cal_date" in captured_sql[0]
    assert "td.cal_date = a.trade_date" in captured_sql[0]
    assert [row["concept_name"] for row in concepts] == ["当日强概念"]
    assert rejections == []


def test_fetch_concepts_keeps_top_two_by_auction_strength_without_size_tiebreak():
    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    trigger_stocks = [
        {
            "trigger_stock_code": "300001",
            "trigger_stock_name": "触发科技",
            "fd_amount": 600_000_000,
        }
    ]

    class DummyCursor:
        def execute(self, sql, params):
            assert "stk_auction_o" in sql
            assert "ths_daily" not in sql
            assert "(a.open / NULLIF(a.close, 0) - 1) * 100" in sql
            assert "COUNT(*) OVER (PARTITION BY m.ts_code) AS concept_size" in sql

        def fetchall(self):
            return [
                ("886001.TI", "弱势窄概念", "300001", 3, 1.0, 10),
                ("886002.TI", "最强概念", "300001", 80, 8.0, 20),
                ("886003.TI", "次强概念", "300001", 60, 6.0, 15),
                ("886004.TI", "第三概念", "300001", 2, 5.0, 5),
            ]

    concepts, rejections = engine._fetch_concepts(DummyCursor(), trigger_stocks)

    assert [item["concept_name"] for item in concepts] == ["最强概念", "次强概念"]
    assert [item["concept_strength"] for item in concepts] == [8.0, 6.0]
    assert [item["concept_strength_source"] for item in concepts] == ["auction_avg", "auction_avg"]
    assert [item["auction_sample_count"] for item in concepts] == [20, 15]
    assert rejections == []


def test_cli_write_outputs_creates_json_and_csv(tmp_path):
    import json
    import importlib.util
    from pathlib import Path

    tool_path = Path(__file__).resolve().parents[3] / "tools" / "cb_auction_t0_picks.py"
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
                "list_type": "主买",
            }
        ],
        "observation_bonds": [
            {
                "cb_code": "123002.SZ",
                "cb_name": "观察转债",
                "stk_code": "300002",
                "stk_name": "观察科技",
                "matched_concepts": ["机器人"],
                "trigger_sources": ["300001"],
                "theme_score": 11.0,
                "risk_notes": [],
                "quality_tier": "B",
                "quality_tier_reason": "概念竞价强度0.05%",
                "list_type": "观察",
                "observation_reason": "非A档观察",
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
    assert "观察转债" in csv_text
    assert "主买" in csv_text
    assert "观察" in csv_text
    assert "非A档观察" in csv_text
    assert "公告实施强赎" in csv_text
    assert "高溢价85.0%" in csv_text
    assert "85.0" in csv_text
    assert "20.0" in csv_text


def test_cli_rejects_negative_top_n_before_running_engine(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    tool_path = Path(__file__).resolve().parents[3] / "tools" / "cb_auction_t0_picks.py"
    spec = importlib.util.spec_from_file_location("cb_auction_t0_picks_negative", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class DummyEngine:
        def __init__(self, *args, **kwargs):
            raise AssertionError("engine should not run when --top-n is invalid")

    monkeypatch.setattr(module, "CbAuctionT0Engine", DummyEngine)

    with pytest.raises(SystemExit) as exc:
        module.main(["2026-06-30", "--top-n", "-1", "--output-dir", str(tmp_path)])

    assert exc.value.code == 2
    assert "--top-n must be >= 0" in capsys.readouterr().err


def test_cli_model_v2_uses_optimized_engine(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    from pathlib import Path

    tool_path = Path(__file__).resolve().parents[3] / "tools" / "cb_auction_t0_picks.py"
    spec = importlib.util.spec_from_file_location("cb_auction_t0_picks_v2", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class DummyV2Engine:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, trade_date=None, top_n=50):
            return {
                "model": "cb_auction_t0_v2",
                "trade_date": trade_date,
                "trigger_stocks": [],
                "concepts": [],
                "bonds": [],
                "rejections": [],
            }

        def close(self):
            pass

    monkeypatch.setattr(module, "CbAuctionT0V2Engine", DummyV2Engine)

    assert module.main(["2026-06-30", "--model", "v2", "--output-dir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    json_path = output.split("JSON: ", 1)[1].splitlines()[0]
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert data["model"] == "cb_auction_t0_v2"


def test_cli_model_v21_uses_steady_engine(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    from pathlib import Path

    tool_path = Path(__file__).resolve().parents[3] / "tools" / "cb_auction_t0_picks.py"
    spec = importlib.util.spec_from_file_location("cb_auction_t0_picks_v21", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class DummyV21Engine:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, trade_date=None, top_n=50):
            return {
                "model": "cb_auction_t0_v2_1",
                "trade_date": trade_date,
                "trigger_stocks": [],
                "concepts": [],
                "bonds": [],
                "rejections": [],
            }

        def close(self):
            pass

    monkeypatch.setattr(module, "CbAuctionT0V21Engine", DummyV21Engine)

    assert module.main(["2026-06-30", "--model", "v2.1", "--output-dir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    json_path = output.split("JSON: ", 1)[1].splitlines()[0]
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert data["model"] == "cb_auction_t0_v2_1"


def test_engine_package_exports_cb_auction_t0():
    from kronos_factors.engine import CbAuctionT0Engine, CbAuctionT0V21Engine, CbAuctionT0V2Engine

    engine = CbAuctionT0Engine(pg_url="postgresql://unit/unit")
    assert engine.pg_url == "postgresql://unit/unit"
    v2_engine = CbAuctionT0V2Engine(pg_url="postgresql://unit/unit")
    assert v2_engine.model_id == "cb_auction_t0_v2"
    v21_engine = CbAuctionT0V21Engine(pg_url="postgresql://unit/unit")
    assert v21_engine.model_id == "cb_auction_t0_v2_1"
    assert v21_engine.rolling_weak_concept_window == 0
