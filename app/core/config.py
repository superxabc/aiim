from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./im.db"
    REDIS_URL: str | None = None
    TENANT_ID: str | None = None
    JWT_SECRET: str = "change_me"  # 最小可用：用于 WS 鉴权
    JWT_ALGORITHM: str = "HS256"
    INSTANCE_ID: str = "im-instance-1"
    RATE_LIMIT_PER_SEC: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


