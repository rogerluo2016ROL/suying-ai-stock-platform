import pandas as pd

from kronos_factors.backtest.bom_oos_cache import (
    CacheConfig,
    CACHE_NAMES,
    MANIFEST_NAME,
    append_cache_frames,
    cache_input_paths,
    fetch_all_a_codes,
    fetch_company_frames,
    fetch_company_payload,
    load_processed_codes,
    load_cache_frames,
    mark_code_processed,
    parse_code_list,
    parse_cache_args,
    prepare_cache_output_dir,
    to_ts_code,
)


class FakePro:
    def __init__(self):
        self.calls = []

    def stock_basic(self, **kwargs):
        self.calls.append(("stock_basic", kwargs))
        return pd.DataFrame(
            [
                {"ts_code": "688017.SH", "symbol": "688017", "name": "绿的谐波"},
                {"ts_code": "300503.SZ", "symbol": "300503", "name": "昊志机电"},
                {"ts_code": "920001.BJ", "symbol": "920001", "name": "北交样本"},
            ]
        )

    def fina_indicator(self, **kwargs):
        self.calls.append(("fina_indicator", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "ann_date": "20250430", "q_sales_yoy": 20}])

    def forecast(self, **kwargs):
        self.calls.append(("forecast", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "ann_date": "20250415", "p_change_max": 30}])

    def irm_qa_sh(self, **kwargs):
        self.calls.append(("irm_qa_sh", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "trade_date": "20250301", "q": "Q", "a": "A"}])

    def irm_qa_sz(self, **kwargs):
        self.calls.append(("irm_qa_sz", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "trade_date": "20250301", "q": "Q", "a": "A"}])

    def research_report(self, **kwargs):
        self.calls.append(("research_report", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "trade_date": "20250302", "title": "研报"}])

    def fina_mainbz_vip(self, **kwargs):
        self.calls.append(("fina_mainbz_vip", kwargs))
        return pd.DataFrame([{"ts_code": kwargs["ts_code"], "end_date": "20241231", "bz_item": "谐波减速器", "bz_sales": 300}])


class ErrorPro(FakePro):
    def forecast(self, **kwargs):
        self.calls.append(("forecast", kwargs))
        raise RuntimeError("forecast permission denied")


def test_to_ts_code_maps_a_share_suffixes():
    assert to_ts_code("688017") == "688017.SH"
    assert to_ts_code("300503") == "300503.SZ"
    assert to_ts_code("920001") == "920001.BJ"


def test_parse_code_list_normalizes_comma_separated_codes():
    assert parse_code_list("688017, 300503.SZ,000551") == [
        ("688017", "688017.SH"),
        ("300503", "300503.SZ"),
        ("000551", "000551.SZ"),
    ]
    assert parse_code_list("") == []


def test_fetch_all_a_codes_uses_stock_basic_listed_a_shares():
    pro = FakePro()

    codes = fetch_all_a_codes(pro)

    assert codes == [("688017", "688017.SH"), ("300503", "300503.SZ"), ("920001", "920001.BJ")]
    assert pro.calls[0] == (
        "stock_basic",
        {"exchange": "", "list_status": "L", "fields": "ts_code,symbol,name,market"},
    )


def test_fetch_company_frames_adds_code6_and_routes_qa_api_by_exchange():
    pro = FakePro()
    config = CacheConfig(start="20240101", end="20260615")

    frames = fetch_company_frames(pro, "688017", "688017.SH", config)

    assert set(frames) == {"fina_indicator", "forecast", "irm_qa", "research_report", "fina_mainbz"}
    assert frames["fina_mainbz"].iloc[0]["code6"] == "688017"
    assert ("irm_qa_sh", {"ts_code": "688017.SH", "start_date": "20240101", "end_date": "20260615"}) in pro.calls

    pro_sz = FakePro()
    fetch_company_frames(pro_sz, "300503", "300503.SZ", config)
    assert ("irm_qa_sz", {"ts_code": "300503.SZ", "start_date": "20240101", "end_date": "20260615"}) in pro_sz.calls


def test_fetch_company_payload_returns_frames_and_errors():
    pro = ErrorPro()
    config = CacheConfig(start="20240101", end="20260615")

    payload = fetch_company_payload(pro, "688017", "688017.SH", config)

    assert "fina_indicator" in payload["frames"]
    assert "forecast" not in payload["frames"]
    assert payload["errors"] == {"forecast": "forecast permission denied"}


def test_parse_cache_args_defaults_to_bom36_and_accepts_all_a():
    defaults = parse_cache_args([])
    assert defaults.universe == "bom36"
    assert defaults.start == "20240101"
    assert defaults.end == "20260615"
    assert defaults.sleep_seconds == 0.3
    assert defaults.limit == 0
    assert defaults.out_dir == "outputs/bom_oos_cache"
    assert not defaults.overwrite
    assert not defaults.resume
    assert defaults.codes == ""

    all_a = parse_cache_args([
        "--universe",
        "all_a",
        "--start",
        "20250101",
        "--end",
        "20250630",
        "--sleep-seconds",
        "0",
        "--limit",
        "5",
        "--out-dir",
        "outputs/bom_oos_cache_smoke",
        "--overwrite",
        "--resume",
        "--codes",
        "688017,300503",
    ])
    assert all_a.universe == "all_a"
    assert all_a.start == "20250101"
    assert all_a.end == "20250630"
    assert all_a.sleep_seconds == 0
    assert all_a.limit == 5
    assert all_a.out_dir == "outputs/bom_oos_cache_smoke"
    assert all_a.overwrite
    assert all_a.resume
    assert all_a.codes == "688017,300503"


def test_prepare_cache_output_dir_blocks_existing_cache_without_overwrite(tmp_path):
    out_dir = tmp_path / "cache"
    out_dir.mkdir()
    existing = out_dir / "fina_indicator.csv"
    existing.write_text("code6\n688017\n", encoding="utf-8")

    try:
        prepare_cache_output_dir(out_dir, overwrite=False)
    except FileExistsError as exc:
        assert "fina_indicator.csv" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")

    paths = prepare_cache_output_dir(out_dir, overwrite=True)
    assert set(paths) == set(CACHE_NAMES)
    assert paths["fina_indicator"] == existing

    resume_paths = prepare_cache_output_dir(out_dir, overwrite=False, resume=True)
    assert resume_paths["fina_indicator"] == existing


def test_prepare_cache_output_dir_creates_missing_directory(tmp_path):
    out_dir = tmp_path / "new-cache"

    paths = prepare_cache_output_dir(out_dir, overwrite=False)

    assert out_dir.is_dir()
    assert paths["fina_mainbz"] == out_dir / "fina_mainbz.csv"


def test_load_cache_frames_reads_required_files_and_normalizes_code6(tmp_path):
    out_dir = tmp_path / "cache"
    out_dir.mkdir()
    for name in CACHE_NAMES:
        (out_dir / f"{name}.csv").write_text("code6,value\n551,1\n688017,2\n", encoding="utf-8")

    frames = load_cache_frames(out_dir)

    assert set(frames) == set(CACHE_NAMES)
    assert frames["fina_mainbz"]["code6"].tolist() == ["000551", "688017"]
    assert cache_input_paths(out_dir)["forecast"] == out_dir / "forecast.csv"


def test_load_cache_frames_reports_missing_required_files(tmp_path):
    out_dir = tmp_path / "cache"
    out_dir.mkdir()
    for name in CACHE_NAMES:
        if name != "forecast":
            (out_dir / f"{name}.csv").write_text("code6,value\n688017,1\n", encoding="utf-8")

    try:
        load_cache_frames(out_dir)
    except FileNotFoundError as exc:
        assert "forecast.csv" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_append_cache_frames_appends_without_repeating_header(tmp_path):
    out_dir = tmp_path / "cache"
    paths = prepare_cache_output_dir(out_dir, overwrite=False)

    append_cache_frames(paths, {"fina_indicator": pd.DataFrame([{"code6": "688017", "value": 1}])})
    append_cache_frames(paths, {"fina_indicator": pd.DataFrame([{"code6": "300503", "value": 2}])})

    rows = (out_dir / "fina_indicator.csv").read_text(encoding="utf-8").splitlines()
    assert rows == ["code6,value", "688017,1", "300503,2"]


def test_append_cache_frames_aligns_to_existing_header(tmp_path):
    out_dir = tmp_path / "cache"
    paths = prepare_cache_output_dir(out_dir, overwrite=False)

    append_cache_frames(paths, {"irm_qa": pd.DataFrame([{"code6": "688017", "q": "Q1", "a": "A1"}])})
    append_cache_frames(paths, {"irm_qa": pd.DataFrame([{"code6": "300503", "q": "Q2", "a": "A2", "industry": "制造业"}])})

    df = pd.read_csv(out_dir / "irm_qa.csv", dtype={"code6": str})
    assert df.columns.tolist() == ["code6", "q", "a"]
    assert df["code6"].tolist() == ["688017", "300503"]


def test_processed_manifest_records_and_loads_completed_codes(tmp_path):
    manifest = tmp_path / MANIFEST_NAME

    assert load_processed_codes(manifest) == set()
    mark_code_processed(
        manifest,
        code6="688017",
        ts_code="688017.SH",
        frame_counts={"fina_indicator": 1, "forecast": 0},
    )
    mark_code_processed(
        manifest,
        code6="300503",
        ts_code="300503.SZ",
        frame_counts={"fina_indicator": 2},
    )

    assert load_processed_codes(manifest) == {"688017", "300503"}
    text = manifest.read_text(encoding="utf-8")
    assert "code6,ts_code,status" in text
    assert "688017,688017.SH,ok" in text


def test_processed_manifest_does_not_skip_zero_row_ok_records(tmp_path):
    manifest = tmp_path / MANIFEST_NAME

    mark_code_processed(
        manifest,
        code6="688017",
        ts_code="688017.SH",
        frame_counts={name: 0 for name in CACHE_NAMES},
        status="ok",
    )
    mark_code_processed(
        manifest,
        code6="300503",
        ts_code="300503.SZ",
        frame_counts={"fina_mainbz": 1},
        status="ok",
    )
    mark_code_processed(
        manifest,
        code6="002896",
        ts_code="002896.SZ",
        frame_counts={"fina_mainbz": 1},
        status="no_data",
    )

    assert load_processed_codes(manifest) == {"300503"}


def test_processed_manifest_records_error_summary(tmp_path):
    manifest = tmp_path / MANIFEST_NAME

    mark_code_processed(
        manifest,
        code6="688017",
        ts_code="688017.SH",
        frame_counts={name: 0 for name in CACHE_NAMES},
        status="error",
        errors={"forecast": "permission denied", "fina_mainbz": "rate limit"},
    )

    text = manifest.read_text(encoding="utf-8")
    assert "error_summary" in text.splitlines()[0]
    assert "forecast: permission denied" in text
    assert "fina_mainbz: rate limit" in text
