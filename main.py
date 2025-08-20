import time
import logging
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.database import engine
from app.core.metrics import add_metrics_middleware
from app.core.ratelimit import RateLimitMiddleware
from app.core.pubsub import pubsub
from app.models.base import Base
from app.core.security import SecurityHeaders
from app.core.monitoring import (
    HealthChecker,
    MetricsCollector,
    performance_monitor,
    LoggingConfig,
)

from app.api import im_api, im_ws, media_api, call_api

# 设置日志
try:
    LoggingConfig.setup_logging()
except Exception:
    # 如果日志设置失败，使用基本配置
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# 创建表
if settings.DEV_AUTO_CREATE_TABLES:
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AIIM - AI-Powered Instant Messaging",
    version=getattr(settings, "VERSION", "1.0.0"),
    description="企业级即时通讯系统，支持音视频通话",
    docs_url="/docs" if getattr(settings, "LOG_LEVEL", "INFO") == "DEBUG" else None,
    redoc_url="/redoc" if getattr(settings, "LOG_LEVEL", "INFO") == "DEBUG" else None,
)

# 中间件顺序很重要！
# 1. 安全头中间件
try:
    app.add_middleware(SecurityHeaders)
except Exception as e:
    logger.warning(f"Failed to add security middleware: {e}")

# 2. CORS中间件
if getattr(settings, "ENABLE_CORS", False):
    origins = [
        origin.strip()
        for origin in getattr(settings, "ALLOWED_ORIGINS", "*").split(",")
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )


# 3. 性能监控中间件
@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    start_time = time.time()

    try:
        # 处理请求
        response = await call_next(request)

        # 计算响应时间
        process_time = time.time() - start_time

        # 记录指标
        try:
            MetricsCollector.record_request(request, process_time, response.status_code)
            performance_monitor.record_request_time(process_time)
        except Exception:
            pass  # 不让监控失败影响正常请求

        # 添加响应头
        response.headers["X-Process-Time"] = str(process_time)

        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed: {e}")
        try:
            performance_monitor.record_error(type(e).__name__)
        except Exception:
            pass
        raise


# 4. 速率限制和指标中间件
app.add_middleware(RateLimitMiddleware)
add_metrics_middleware(app)


# 健康检查端点
@app.get("/health")
async def health():
    """增强版健康检查"""
    try:
        health_status = await HealthChecker.comprehensive_health_check()
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        # 降级到简单检查
        dep: dict = {"redis": False}
        try:
            if settings.REQUIRE_REDIS:
                from app.core.seq import _redis_client  # type: ignore

                dep["redis"] = _redis_client is not None
        except Exception:
            dep["redis"] = False
        status = "ok" if (not settings.REQUIRE_REDIS or dep["redis"]) else "degraded"
        return {"status": status, "dependencies": dep}


# 简单健康检查
@app.get("/healthz")
async def simple_health_check():
    """简单健康检查（K8s风格）"""
    return {"status": "ok"}


# 准备就绪检查
@app.get("/ready")
async def readiness_check():
    """准备就绪检查"""
    try:
        db_status = await HealthChecker.check_database()
        if db_status["status"] != "healthy":
            return Response(status_code=503, content="Database not ready")
        return {"status": "ready"}
    except Exception:
        return Response(status_code=503, content="Service not ready")


# Prometheus指标端点
@app.get("/metrics")
async def metrics():
    """Prometheus指标端点"""
    try:
        return PlainTextResponse(
            MetricsCollector.get_metrics(), media_type=CONTENT_TYPE_LATEST
        )
    except Exception:
        # 降级到基本指标
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# 性能统计端点 (调试用)
@app.get("/stats")
async def performance_stats():
    """性能统计端点"""
    if getattr(settings, "LOG_LEVEL", "INFO") != "DEBUG":
        return {"message": "Stats endpoint disabled in production"}
    try:
        return performance_monitor.get_stats()
    except Exception as e:
        return {"error": str(e)}


# API路由
app.include_router(im_api.router, prefix="/api/aiim", tags=["AIIM社交"])
app.include_router(im_ws.router, prefix="/api/aiim", tags=["AIIM实时"])
app.include_router(media_api.router, prefix="/api/aiim/media", tags=["AIIM媒体"])
app.include_router(call_api.router, prefix="/api/aiim/calls", tags=["AIIM通话"])


# 根路径
@app.get("/")
def root():
    """根路径信息"""
    return {
        "service": "AIIM",
        "version": getattr(settings, "VERSION", "1.0.0"),
        "status": "running",
        "docs": (
            "/docs" if getattr(settings, "LOG_LEVEL", "INFO") == "DEBUG" else "disabled"
        ),
    }


# 事件处理
@app.on_event("shutdown")
async def on_shutdown():
    """优雅关闭"""
    logger.info("Shutting down AIIM service...")
    try:
        if hasattr(pubsub, "close"):
            await pubsub.close()  # type: ignore
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    logger.info("AIIM service stopped.")
