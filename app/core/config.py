from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./im.db"
    REDIS_URL: str | None = None
    TENANT_ID: str | None = None
    JWT_SECRET: str = "change_me"  # 最小可用：用于 WS 鉴权
    JWT_ALGORITHM: str = "HS256"
    INSTANCE_ID: str = "im-instance-1"
    RATE_LIMIT_PER_SEC: int = 10
    # 生产建议强制要求 Redis（用于 seq 与 Pub/Sub），否则拒绝启动
    REQUIRE_REDIS: bool = True
    # 开发便捷项：是否在启动时自动建表（生产应使用 Alembic 迁移）
    DEV_AUTO_CREATE_TABLES: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


