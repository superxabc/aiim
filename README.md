# IM Platform

轻量级 IM 服务（FastAPI + SQLAlchemy + Redis 可选），支持：
- 1:1 会话、消息入库与查询
- WebSocket 实时推送（订阅、发送、心跳）
- 会话内严格有序（seq，Redis 优先）与断线补偿（after_seq）
- 送达/已读回执
- AI 流式分片（stream_chunk/stream_end）
- 指标 `/metrics`、健康 `/health`、最小 JWT 鉴权

## 运行

开发（本地）：
```bash
uvicorn main:app --reload --port 8083
```

环境变量（建议创建 `.env`）：
```
JWT_SECRET=please_change_me
JWT_ALGORITHM=HS256
DATABASE_URL=sqlite:///./im.db
# DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/im
REDIS_URL=
INSTANCE_ID=im-instance-1
RATE_LIMIT_PER_SEC=10
```

Docker：
```bash
docker build -t im-platform:local .
docker run --rm -p 8083:8083 -e JWT_SECRET=change_me im-platform:local
# 启用 Redis（推荐）
docker run -d --name im-redis -p 6379:6379 redis:7
docker run --rm -p 8083:8083 \
  -e JWT_SECRET=change_me \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  im-platform:local
```

docker-compose（Postgres + Redis + IM）：
```bash
docker compose up -d --build
```

## API 摘要

- REST（需 Authorization: Bearer <JWT>）
  - POST `/api/im/conversations`
  - GET `/api/im/conversations`
  - POST `/api/im/messages`
  - GET `/api/im/messages/{conversation_id}?limit&before_id&after_seq`
  - POST `/api/im/messages/stream`（流式分片）
  - POST `/api/im/receipts/delivered`、POST `/api/im/receipts/read`

- WebSocket `/api/im/ws?token=<JWT>`
  - `subscribe`/`unsubscribe`
  - `send_msg` → ack `{message_id, seq}`，同时推送 `message.created`
  - `stream_chunk` → ack `{message_id, seq, stream_end}`，推送 `message.stream_chunk`
  - `delivered`（送达回执）
  - `ping/pong`（心跳 + 在线路由续期）

## 技术架构

- FastAPI（路由：REST `app/api/im_api.py`，WS `app/api/im_ws.py`）
- SQLAlchemy（模型：`app/models/im.py`，会话/成员/消息/seq）
- Pub/Sub：`app/core/pubsub.py`（Redis 优先，内存回退）
- 序列：`app/core/seq.py`（会话内 seq，Redis INCR 优先）
- 鉴权：`app/core/ws_auth.py`（JWT）
- 事件：`app/core/events.py`（统一异步发布）
- 中间件：指标 `app/core/metrics.py`，限流 `app/core/ratelimit.py`
- 迁移：Alembic（`alembic/`）

## 生产化建议

- 切换 PostgreSQL + Alembic 迁移（已提供）
- 启用 Redis（跨进程推送和 seq 一致性）
- 使用 `gunicorn -k uvicorn.workers.UvicornWorker -w <N>`
- 强化 JWT（issuer/audience）、TLS 终止、CORS、安全头
- 日志 JSON 化、Prometheus 指标扩展、OpenTelemetry（可选）
