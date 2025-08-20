from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 基础配置
    DATABASE_URL: str = "sqlite:///./im.db"
    REDIS_URL: str | None = None
    TENANT_ID: str | None = None
    
    # 认证配置
    JWT_SECRET: str = "change_me"  # 生产环境必须修改
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # 服务配置
    INSTANCE_ID: str = "im-instance-1"
    RATE_LIMIT_PER_SEC: int = 10
    REQUIRE_REDIS: bool = True
    DEV_AUTO_CREATE_TABLES: bool = False
    
    # 性能配置
    MAX_CONNECTIONS: int = 100
    CONNECTION_POOL_SIZE: int = 10
    QUERY_TIMEOUT: int = 30
    
    # 安全配置
    API_KEY: str | None = None
    ENABLE_CORS: bool = False
    ALLOWED_ORIGINS: str = "*"
    WEBHOOK_SECRET: str | None = None
    
    # 监控配置
    ENABLE_METRICS: bool = True
    METRICS_PATH: str = "/metrics"
    LOG_LEVEL: str = "INFO"
    
    # 应用版本
    VERSION: str = "1.0.0"
    
    # Media Storage Settings
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "aiim-media"
    MINIO_SECURE: bool = False
    MEDIA_MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    MEDIA_ALLOWED_TYPES: str = "audio/mpeg,audio/wav,audio/ogg,audio/mp4,audio/webm,audio/aac"
    MEDIA_URL_EXPIRE_SECONDS: int = 3600  # 1 hour
    
    # STUN/TURN Settings  
    STUN_SERVERS: str = "stun:stun.l.google.com:19302"
    TURN_SERVER: str | None = None
    TURN_USERNAME: str | None = None
    TURN_PASSWORD: str | None = None
    TURN_CREDENTIAL_TTL: int = 300  # 5 minutes

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
