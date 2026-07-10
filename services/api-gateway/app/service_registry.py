from dataclasses import dataclass

@dataclass(frozen=True)
class Service:
    name: str
    prefix: str
    host_env: str
    compose_host: str
    port: int

SERVICES = (
    Service("data-service", "/api/v1/data", "GATEWAY_DATA_HOST", "data-service", 8010),
)

def sanitize_client_headers(headers, claims=None):
    blocked = {"x-owner-user-id", "x-service-auth", "x-service-token", "x-internal-user-id"}
    clean = {str(k): str(v) for k, v in headers.items() if str(k).lower() not in blocked}
    if claims:
        if claims.get("sub"):
            clean["X-Owner-User-Id"] = str(claims["sub"])
    return clean
