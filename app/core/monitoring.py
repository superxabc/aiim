"""监控和健康检查"""

import time
import psutil
from typing import Dict, Any, Optional
from fastapi import Request
from sqlalchemy import text
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry
import logging

from .database import get_db
from .config import settings

# 创建自定义注册表避免冲突
CUSTOM_REGISTRY = CollectorRegistry()

# Prometheus metrics
REQUEST_COUNT = Counter('aiim_http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'], registry=CUSTOM_REGISTRY)
REQUEST_DURATION = Histogram('aiim_http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'], registry=CUSTOM_REGISTRY)
ACTIVE_CONNECTIONS = Gauge('aiim_websocket_connections_active', 'Active WebSocket connections', registry=CUSTOM_REGISTRY)
MESSAGE_COUNT = Counter('aiim_messages_total', 'Total messages processed', ['type'], registry=CUSTOM_REGISTRY)
CALL_COUNT = Counter('aiim_calls_total', 'Total calls processed', ['status'], registry=CUSTOM_REGISTRY)
DB_QUERY_DURATION = Histogram('aiim_db_query_duration_seconds', 'Database query duration', ['operation'], registry=CUSTOM_REGISTRY)

# System metrics
SYSTEM_CPU_USAGE = Gauge('aiim_system_cpu_usage_percent', 'System CPU usage percentage', registry=CUSTOM_REGISTRY)
SYSTEM_MEMORY_USAGE = Gauge('aiim_system_memory_usage_percent', 'System memory usage percentage', registry=CUSTOM_REGISTRY)
SYSTEM_DISK_USAGE = Gauge('aiim_system_disk_usage_percent', 'System disk usage percentage', registry=CUSTOM_REGISTRY)

logger = logging.getLogger(__name__)


class HealthChecker:
    """健康检查器"""
    
    @staticmethod
    async def check_database() -> Dict[str, Any]:
        """检查数据库连接"""
        try:
            db = next(get_db())
            start_time = time.time()
            
            # 执行简单查询
            result = db.execute(text("SELECT 1")).fetchone()
            
            duration = time.time() - start_time
            
            return {
                "status": "healthy" if result else "unhealthy",
                "response_time": duration,
                "details": "Database connection successful" if result else "Database query failed"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "response_time": None,
                "details": f"Database connection failed: {str(e)}"
            }
    
    @staticmethod
    async def check_redis() -> Dict[str, Any]:
        """检查Redis连接"""
        if not settings.REDIS_URL:
            return {
                "status": "disabled",
                "response_time": None,
                "details": "Redis not configured"
            }
        
        try:
            import redis.asyncio as redis
            
            r = redis.from_url(settings.REDIS_URL)
            start_time = time.time()
            
            # 执行ping命令
            pong = await r.ping()
            await r.close()
            
            duration = time.time() - start_time
            
            return {
                "status": "healthy" if pong else "unhealthy",
                "response_time": duration,
                "details": "Redis connection successful" if pong else "Redis ping failed"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "response_time": None,
                "details": f"Redis connection failed: {str(e)}"
            }
    
    @staticmethod
    def check_system_resources() -> Dict[str, Any]:
        """检查系统资源"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # 更新Prometheus metrics
            SYSTEM_CPU_USAGE.set(cpu_percent)
            SYSTEM_MEMORY_USAGE.set(memory_percent)
            SYSTEM_DISK_USAGE.set(disk_percent)
            
            return {
                "cpu_usage": cpu_percent,
                "memory_usage": memory_percent,
                "disk_usage": disk_percent,
                "status": "healthy" if all([
                    cpu_percent < 90,
                    memory_percent < 90,
                    disk_percent < 90
                ]) else "warning"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "details": f"System resource check failed: {str(e)}"
            }
    
    @staticmethod
    async def comprehensive_health_check() -> Dict[str, Any]:
        """综合健康检查"""
        checks = {
            "database": await HealthChecker.check_database(),
            "redis": await HealthChecker.check_redis(),
            "system": HealthChecker.check_system_resources()
        }
        
        # 确定整体状态
        overall_status = "healthy"
        for service, check in checks.items():
            if check["status"] == "unhealthy":
                overall_status = "unhealthy"
                break
            elif check["status"] == "warning":
                overall_status = "warning"
        
        return {
            "status": overall_status,
            "timestamp": time.time(),
            "checks": checks,
            "version": getattr(settings, 'VERSION', 'unknown')
        }


class MetricsCollector:
    """指标收集器"""
    
    @staticmethod
    def record_request(request: Request, response_time: float, status_code: int):
        """记录HTTP请求指标"""
        method = request.method
        endpoint = request.url.path
        
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(response_time)
    
    @staticmethod
    def record_message(message_type: str):
        """记录消息指标"""
        MESSAGE_COUNT.labels(type=message_type).inc()
    
    @staticmethod
    def record_call(call_status: str):
        """记录通话指标"""
        CALL_COUNT.labels(status=call_status).inc()
    
    @staticmethod
    def record_db_query(operation: str, duration: float):
        """记录数据库查询指标"""
        DB_QUERY_DURATION.labels(operation=operation).observe(duration)
    
    @staticmethod
    def update_active_connections(count: int):
        """更新活跃连接数"""
        ACTIVE_CONNECTIONS.set(count)
    
    @staticmethod
    def get_metrics() -> str:
        """获取Prometheus格式的指标"""
        return generate_latest(CUSTOM_REGISTRY)


class PerformanceMonitor:
    """性能监控"""
    
    def __init__(self):
        self.request_times = []
        self.error_counts = {}
        self.start_time = time.time()
    
    def record_request_time(self, duration: float):
        """记录请求时间"""
        self.request_times.append(duration)
        
        # 只保留最近1000个请求的数据
        if len(self.request_times) > 1000:
            self.request_times = self.request_times[-1000:]
    
    def record_error(self, error_type: str):
        """记录错误"""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        if not self.request_times:
            return {"message": "No request data available"}
        
        return {
            "uptime": time.time() - self.start_time,
            "total_requests": len(self.request_times),
            "avg_response_time": sum(self.request_times) / len(self.request_times),
            "min_response_time": min(self.request_times),
            "max_response_time": max(self.request_times),
            "error_counts": self.error_counts,
            "requests_per_minute": len([t for t in self.request_times if time.time() - t < 60])
        }


# 全局实例
performance_monitor = PerformanceMonitor()


class LoggingConfig:
    """日志配置"""
    
    @staticmethod
    def setup_logging():
        """设置生产环境日志"""
        import logging.config
        
        config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'detailed': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s (%(filename)s:%(lineno)d)'
                },
                'simple': {
                    'format': '%(levelname)s: %(message)s'
                },
                'json': {
                    'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "module": "%(module)s", "line": %(lineno)d}'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': 'INFO',
                    'formatter': 'simple',
                    'stream': 'ext://sys.stdout'
                },
                'file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'DEBUG',
                    'formatter': 'detailed',
                    'filename': '/app/logs/aiim.log',
                    'maxBytes': 10485760,  # 10MB
                    'backupCount': 5
                },
                'error_file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'ERROR',
                    'formatter': 'json',
                    'filename': '/app/logs/error.log',
                    'maxBytes': 10485760,  # 10MB
                    'backupCount': 10
                }
            },
            'root': {
                'level': 'INFO',
                'handlers': ['console', 'file', 'error_file']
            },
            'loggers': {
                'aiim': {
                    'level': 'DEBUG',
                    'handlers': ['file'],
                    'propagate': False
                },
                'uvicorn.access': {
                    'level': 'INFO',
                    'handlers': ['file'],
                    'propagate': False
                }
            }
        }
        
        logging.config.dictConfig(config)
