from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.responses import Response

from app.core.database import engine
from app.core.metrics import add_metrics_middleware
from app.core.ratelimit import RateLimitMiddleware
from app.core.pubsub import pubsub
from app.models.base import Base
from app.models import im as im_model
from app.api import im_api, im_ws


app = FastAPI(title="IM Platform", version="0.1.0")

add_metrics_middleware(app)
app.add_middleware(RateLimitMiddleware)

# 临时：开发期自动建表（生产请改为 Alembic 迁移）
Base.metadata.create_all(bind=engine)

app.include_router(im_api.router, prefix="/api/im", tags=["IM社交"])
app.include_router(im_ws.router, prefix="/api/im", tags=["IM实时"])


@app.get("/")
def root():
    return {"service": "im-platform", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


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



