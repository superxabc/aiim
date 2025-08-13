from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.responses import Response

from app.core.database import engine
from app.core.metrics import add_metrics_middleware
from app.core.ratelimit import RateLimitMiddleware
from app.core.pubsub import pubsub
from app.models.base import Base

from app.api import im_api, im_ws
from app.core.config import settings


app = FastAPI(title="aiim", version="0.1.0")

add_metrics_middleware(app)
app.add_middleware(RateLimitMiddleware)

if settings.DEV_AUTO_CREATE_TABLES:
    Base.metadata.create_all(bind=engine)

app.include_router(im_api.router, prefix="/api/aiim", tags=["AIIM社交"])
app.include_router(im_ws.router, prefix="/api/aiim", tags=["AIIM实时"])


@app.get("/")
def root():
    return {"service": "im-platform", "status": "ok"}


@app.get("/health")
def health():
    # 简单依赖健康检查：Redis 可选但在 REQUIRE_REDIS=True 时必须可用
    dep: dict = {"redis": False}
    try:
        if settings.REQUIRE_REDIS:
            from app.core.seq import _redis_client  # type: ignore

            dep["redis"] = _redis_client is not None
    except Exception:
        dep["redis"] = False
    status = "ok" if (not settings.REQUIRE_REDIS or dep["redis"]) else "degraded"
    return {"status": status, "dependencies": dep}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.on_event("shutdown")
async def on_shutdown():
    # 释放 redis 连接等资源
    try:
        if hasattr(pubsub, "close"):
            await pubsub.close()  # type: ignore
    except Exception:
        pass
