def test_screener_does_not_register_training_mock_routes():
    from app.main import app
    assert not any(route.path.startswith("/api/v1/training") for route in app.routes)
