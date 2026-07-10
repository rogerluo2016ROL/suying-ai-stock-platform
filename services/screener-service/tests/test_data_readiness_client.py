from app import data_readiness_client


def test_screening_blocks_when_data_service_reports_stale(monkeypatch):
    monkeypatch.setenv("KRONOS_ENV", "production")
    class Response:
        def read(self): return b'{"status":"blocked"}'
        def __enter__(self): return self
        def __exit__(self, *_): return False
    monkeypatch.setattr(data_readiness_client, "urlopen", lambda *_args, **_kwargs: Response())
    try:
        data_readiness_client.require_ready("daily_screening_v1", "2026-07-10")
    except RuntimeError as exc:
        assert "DATA_NOT_READY" in str(exc)
    else:
        raise AssertionError("stale data must block production screening")
