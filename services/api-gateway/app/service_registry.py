from dataclasses import dataclass

@dataclass(frozen=True)
class Service:
    name: str
    prefix: str
    host_env: str
    compose_host: str
    port: int

SERVICE_REGISTRY = (
 Service("backend", "/api/v1/auth", "GATEWAY_BACKEND_HOST", "backend", 9001),
 Service("backend", "/api/v1/admin", "GATEWAY_BACKEND_HOST", "backend", 9001),
 Service("screener-service", "/api/v1/screener", "GATEWAY_SCREENER_HOST", "screener-service", 8001),
 Service("prediction-service", "/api/v1/prediction", "GATEWAY_PREDICTION_HOST", "prediction-service", 8002),
 Service("strategy-service", "/api/v1/strategy", "GATEWAY_STRATEGY_HOST", "strategy-service", 8003),
 Service("signal-service", "/api/v1/signal", "GATEWAY_SIGNAL_HOST", "signal-service", 8004),
 Service("screener-service", "/api/v1/dashboard", "GATEWAY_SCREENER_HOST", "screener-service", 8001),
 Service("data-service", "/api/v1/data", "GATEWAY_DATA_HOST", "data-service", 8010),
 Service("alert-service", "/api/v1/alert", "GATEWAY_ALERT_HOST", "alert-service", 8005),
 Service("trade-service", "/api/v1/trade", "GATEWAY_TRADE_HOST", "trade-service", 8006),
 Service("backtest-service", "/api/v1/backtest", "GATEWAY_BACKTEST_HOST", "backtest-service", 8007),
 Service("training-service", "/api/v1/training", "GATEWAY_TRAINING_HOST", "training-service", 8008),
 Service("diagnosis-service", "/api/v1/diagnosis", "GATEWAY_DIAGNOSIS_HOST", "diagnosis-service", 8009),
)

def sanitize_client_headers(headers, claims=None):
    blocked = {"x-owner-user-id", "x-service-auth", "x-service-token", "x-internal-user-id"}
    clean = {str(k): str(v) for k, v in headers.items() if str(k).lower() not in blocked}
    if claims:
        if claims.get("sub"):
            clean["X-Owner-User-Id"] = str(claims["sub"])
    return clean
