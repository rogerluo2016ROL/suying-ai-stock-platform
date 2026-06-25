import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.verify_auction_collection import evaluate_auction_status


def test_evaluate_auction_status_reports_missing_tushare_token_blocker():
    readiness = {
        "components": {
            "service_alive": True,
            "scheduler_running": True,
            "pg_ok": True,
            "tushare_configured": False,
        }
    }
    status = {"jobs": []}

    result = evaluate_auction_status(readiness, status, "2026-06-26")

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["blocker"] == "TUSHARE_TOKEN not configured"


def test_evaluate_auction_status_passes_when_today_auction_has_rows():
    readiness = {
        "components": {
            "service_alive": True,
            "scheduler_running": True,
            "pg_ok": True,
            "tushare_configured": True,
        }
    }
    status = {
        "jobs": [
            {
                "id": "auction",
                "last_run": "2026-06-26T09:25:02",
                "last_status": "ok",
                "last_result": "{'status': 'ok', 'source': 'tushare_stk_auction', 'stocks': 5100}",
                "pg_written": 0,
            }
        ]
    }

    result = evaluate_auction_status(readiness, status, "2026-06-26")

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["auction"]["stocks"] == 5100


def test_evaluate_auction_status_fails_when_auction_has_not_run_today():
    readiness = {
        "components": {
            "service_alive": True,
            "scheduler_running": True,
            "pg_ok": True,
            "tushare_configured": True,
        }
    }
    status = {
        "jobs": [
            {
                "id": "auction",
                "last_run": "2026-06-25T09:25:02",
                "last_status": "ok",
                "last_result": "{'status': 'ok', 'stocks': 5100}",
                "pg_written": 0,
            }
        ]
    }

    result = evaluate_auction_status(readiness, status, "2026-06-26")

    assert result["ok"] is False
    assert result["exit_code"] == 3
    assert result["blocker"] == "auction job has not run for target date"
