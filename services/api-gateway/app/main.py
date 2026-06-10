"""API Gateway — minimal reverse proxy with rate limiting"""
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
import httpx

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_rate_store = {}

SERVICES = {
    "/api/v1/auth": "http://localhost:9001",
    "/api/v1/admin": "http://localhost:9001",
    "/api/v1/screener": "http://localhost:8001",
    "/api/v1/prediction": "http://localhost:8002",
    "/api/v1/strategy": "http://localhost:8003",
    "/api/v1/signal": "http://localhost:8004",
    "/api/v1/alert": "http://localhost:8005",
    "/api/v1/trade": "http://localhost:8006",
    "/api/v1/backtest": "http://localhost:8007",
    "/api/v1/training": "http://localhost:8008",
    "/api/v1/diagnosis": "http://localhost:8009",
}

def _rate_check(ip: str) -> bool:
    now = time.time()
    w = [t for t in _rate_store.get(ip, []) if now - t < 60]
    _rate_store[ip] = w
    if len(w) >= 60: return False
    w.append(now); return True

@app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH","OPTIONS"])
async def gateway(request: Request, path: str):
    # Health check
    if path in ("api/health", "health"):
        return {"status": "healthy", "gateway": "api-gateway:8000"}
    
    # Rate limit
    ip = request.client.host if request.client else "unknown"
    if not _rate_check(ip):
        return JSONResponse({"detail": "Rate limit exceeded"}, 429)
    
    # Route mapping
    full = "/" + path
    target_base = None
    for prefix, svc in SERVICES.items():
        if full.startswith(prefix):
            target_base = svc
            break
    
    if not target_base:
        return JSONResponse({"detail": f"Not Found: {full}"}, 404)
    
    target = f"{target_base}{full}"
    if request.url.query:
        q = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
        target += f"?{q}"
    
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host",)}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method=request.method, url=target, headers=headers, content=body)
            return Response(content=resp.content, status_code=resp.status_code,
                          media_type=resp.headers.get("content-type", "application/json"))
    except httpx.ConnectError as e:
        return JSONResponse({"detail": f"Upstream unavailable", "error": str(e)}, 502)
