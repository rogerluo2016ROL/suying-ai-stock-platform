"""统一 FastAPI 装配工厂(阶段4 create_app 工厂)。

各微服务 main.py 调 ``create_app()`` 统一装配 CORS / health 端点 / router / lifespan,
消除 11 份 main.py 的启动样板重复(CORS、health/live|ready、logging、FastAPI 构造)。

sys.path 注入共享 packages 依赖调用方 ``__file__``,故保留在各 main.py 顶部
(必须在 ``import app.routes`` 之前——routes 依赖 kronos-factors/core/data/auth)。
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Callable, Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .health import build_health, check_postgres


@asynccontextmanager
async def default_lifespan(app: FastAPI):
    """默认 lifespan:仅记录启停日志。复杂服务(模型加载/scheduler/adapter 注入)传自定义 lifespan 覆盖。"""
    logger = logging.getLogger(app.title)
    logger.info("Starting %s...", app.title)
    yield
    logger.info("%s stopped.", app.title)


def create_app(
    service_name: str,
    version: str,
    routers: Iterable,
    *,
    title: str | None = None,
    description: str = "",
    lifespan=None,
    cors_origins: list[str] | None = None,
    enable_health: bool = True,
    health_extra: dict | Callable[[], dict] | None = None,
) -> FastAPI:
    """装配 FastAPI 实例(CORS + health 端点 + routers + lifespan)。

    Args:
        service_name: 服务标识(alert-service),用于 health 端点 / title 推导。
        version: API 版本号。
        routers: 要 include 的 APIRouter 可迭代对象。
        title: FastAPI title;None 则由 service_name 推导(如 "速赢AI - Alert Service")。
        description: FastAPI description。
        lifespan: 自定义 async contextmanager;None 用 default_lifespan。
        cors_origins: CORS 白名单;None 读 env CORS_ALLOWED_ORIGINS(默认 5173/3000)。
        enable_health: 是否注册 /api/v1/health[/live|/ready] 三端点。
        health_extra: 合并进 /api/v1/health 响应的额外字段。静态用 dict(trade 的 mode);
            动态用 callable(prediction 的 model_loaded,运行时随 lifespan 变化)。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _title = title or f"速赢AI - {' '.join(p.title() for p in service_name.split('-'))}"
    app = FastAPI(
        title=_title,
        description=description,
        version=version,
        lifespan=lifespan or default_lifespan,
    )

    _origins = cors_origins or os.environ.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in routers:
        app.include_router(router)

    if enable_health:
        @app.get("/api/v1/health/live")
        async def _health_live():
            return {"live": True, "service": service_name, "version": version}

        @app.get("/api/v1/health/ready")
        async def _health_ready():
            return build_health(
                service_name, version, {"postgres": await check_postgres()}
            ).model_dump()

        @app.get("/api/v1/health")
        async def _health():
            resp = {"status": "healthy", "service": service_name, "version": version}
            if health_extra:
                extra = health_extra() if callable(health_extra) else health_extra
                resp.update(extra)
            return resp

    return app
