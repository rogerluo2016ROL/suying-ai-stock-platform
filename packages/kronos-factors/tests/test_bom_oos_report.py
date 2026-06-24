import csv
import json
import math

from kronos_factors.backtest.bom_oos_report import (
    build_oos_audit_report,
    hash_file,
    summarize_oos_verdict,
    write_oos_audit_artifacts,
)


def test_hash_file_returns_sha256(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("code,score\n688017,74\n", encoding="utf-8")

    assert hash_file(path) == "2131951b758936d643134140cf269b7b2e059aedda77f6a4ae97420c84fa791b"


def test_build_oos_audit_report_marks_fixed_universe_bias(tmp_path):
    cache_path = tmp_path / "fina_indicator.csv"
    cache_path.write_text("code6,q_sales_yoy\n688017,61\n", encoding="utf-8")
    results = {
        "train_h20": {
            "label": "train h20",
            "n": 1,
            "mean_rank_ic": -0.031,
            "p": 0.716,
            "per_cutoff": [{"cutoff": "2025-09-30", "n": 19, "rank_ic": -0.12, "ic": -0.08, "hit": 0.47}],
        },
        "test_h20": {
            "label": "test h20",
            "n": 1,
            "mean_rank_ic": 0.093,
            "p": 0.007,
            "per_cutoff": [{"cutoff": "2025-10-31", "n": 19, "rank_ic": 0.244, "ic": 0.18, "hit": 0.63}],
        },
    }

    report = build_oos_audit_report(
        model_version="supply_chain_bom_v5",
        universe_mode="fixed_current_mapping",
        universe_codes=["688017", "300503"],
        results=results,
        config={"horizons": [20], "train_range": ["2025-01", "2025-09"], "test_range": ["2025-10", "2026-05"]},
        cache_paths=[cache_path],
        git_commit="abc123",
    )

    assert report["model_version"] == "supply_chain_bom_v5"
    assert report["git_commit"] == "abc123"
    assert report["universe"]["mode"] == "fixed_current_mapping"
    assert report["universe"]["size"] == 2
    assert "当前固定公司池会保留选择偏差" in report["bias_warnings"][0]
    assert report["inputs"]["fina_indicator.csv"]["sha256"] == hash_file(cache_path)
    assert report["results"]["test_h20"]["mean_rank_ic"] == 0.093


def test_build_oos_audit_report_marks_cutoff_cache_universe_limit(tmp_path):
    cache_path = tmp_path / "fina_mainbz.csv"
    cache_path.write_text("code6,end_date,bz_item,bz_sales\n688017,20241231,谐波减速器,300\n", encoding="utf-8")

    report = build_oos_audit_report(
        model_version="supply_chain_bom_v5",
        universe_mode="cutoff_rebuilt_cache",
        universe_codes=["688017"],
        results={},
        config={"horizons": [20]},
        cache_paths=[cache_path],
    )

    assert report["universe"]["mode"] == "cutoff_rebuilt_cache"
    assert "缓存覆盖范围仍决定候选宇宙上限" in report["bias_warnings"][0]


def test_write_oos_audit_artifacts_outputs_json_and_cutoff_csv(tmp_path):
    report = {
        "generated_at": "2026-06-24T12:00:00+08:00",
        "model_version": "supply_chain_bom_v5",
        "universe": {"mode": "fixed_current_mapping", "size": 2, "codes": ["688017", "300503"]},
        "results": {
            "test_h20": {
                "label": "test h20",
                "per_cutoff": [
                    {"cutoff": "2025-10-31", "n": 19, "rank_ic": 0.244, "ic": 0.18, "hit": 0.63},
                    {"cutoff": "2025-11-30", "n": 19, "rank_ic": 0.014, "ic": 0.01, "hit": 0.53},
                ],
            }
        },
    }

    paths = write_oos_audit_artifacts(report, tmp_path)

    report_path = tmp_path / "bom_oos_audit_supply_chain_bom_v5_fixed_current_mapping.json"
    cutoff_path = tmp_path / "bom_oos_cutoffs_fixed_current_mapping_test_h20.csv"
    assert paths == {"report_json": str(report_path), "test_h20_csv": str(cutoff_path)}
    assert json.loads(report_path.read_text(encoding="utf-8"))["model_version"] == "supply_chain_bom_v5"

    with cutoff_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["cutoff"] == "2025-10-31"
    assert rows[0]["rank_ic"] == "0.244"


def test_summarize_oos_verdict_marks_no_effective_cutoffs_as_inconclusive():
    verdict = summarize_oos_verdict({"n": 0, "mean_rank_ic": 0, "p": 1})

    assert verdict["status"] == "INCONCLUSIVE"
    assert "无有效 cutoff" in verdict["message"]


def test_summarize_oos_verdict_marks_positive_significant_test_as_pass():
    verdict = summarize_oos_verdict({"n": 7, "mean_rank_ic": 0.08, "p": 0.013})

    assert verdict["status"] == "PASS"
    assert "显著为正" in verdict["message"]


def test_summarize_oos_verdict_marks_nan_p_value_as_inconclusive():
    verdict = summarize_oos_verdict({"n": 7, "mean_rank_ic": 0.0, "p": math.nan})

    assert verdict["status"] == "INCONCLUSIVE"
    assert "统计量不可用" in verdict["message"]
