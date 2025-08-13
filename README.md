# AIIM - AI Instant Messaging

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

AIIM是一个轻量级、高性能的即时消息服务，专为AI应用场景设计。基于FastAPI + SQLAlchemy + Redis构建，支持实时消息传递、AI流式消息处理和多端同步。

## ✨ 核心特性

- 🚀 **实时通信**: WebSocket双向通信，支持订阅/发布模式
- 🔄 **消息顺序**: 基于Redis的严格消息序列保证
- 📱 **多端同步**: 支持多设备消息同步和状态管理
- 🤖 **AI集成**: 原生支持AI流式消息处理
- 📊 **送达回执**: 完整的消息状态跟踪（已发送/已送达/已读）
- 🔍 **可观测性**: 内置健康检查、Prometheus指标监控
- 🔐 **安全认证**: JWT认证，支持租户隔离
- 📈 **高可用**: 支持水平扩展，生产就绪

## 🚀 快速开始

### 使用Docker Compose（推荐）

```bash
# 克隆仓库
git clone https://github.com/superxabc/aiim.git
cd aiim

# 配置环境变量
cp env.example .env
# 编辑 .env 文件，设置 JWT_SECRET 等配置

# 启动服务（包含PostgreSQL + Redis + AIIM）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f aiim
```

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp env.example .env

# 运行开发服务器
DEV_AUTO_CREATE_TABLES=true uvicorn main:app --reload --port 8083
```

### 生产部署

```bash
# 使用生产配置
docker-compose -f docker-compose.prod.yml up -d
```

## 🔧 配置说明

关键环境变量：

| 变量名 | 描述 | 默认值 | 必填 |
|--------|------|--------|------|
| `JWT_SECRET` | JWT签名密钥 | - | ✅ |
| `DATABASE_URL` | 数据库连接URL | `sqlite:///./im.db` | ❌ |
| `REDIS_URL` | Redis连接URL | - | 生产环境必填 |
| `RATE_LIMIT_PER_SEC` | 速率限制（请求/秒） | `10` | ❌ |
| `REQUIRE_REDIS` | 强制要求Redis | `false` | ❌ |

完整配置请参考 `env.example` 文件。

## API 摘要

- REST（需 Authorization: Bearer <JWT>）
  - POST `/api/aiim/conversations`
  - GET `/api/aiim/conversations`
  - POST `/api/aiim/messages`
  - GET `/api/aiim/messages/{conversation_id}?limit&before_id&after_seq`
  - POST `/api/aiim/messages/stream`（流式分片）
  - POST `/api/aiim/receipts/delivered`、POST `/api/aiim/receipts/read`

- WebSocket `/api/aiim/ws?token=<JWT>`
  - `subscribe`/`unsubscribe`
  - `send_msg` → ack `{message_id, seq}`，同时推送 `message.created`
  - `stream_chunk` → ack `{message_id, seq, stream_end}`，推送 `message.stream_chunk`
  - `delivered`（送达回执）
  - `ping/pong`（心跳 + 在线路由续期）

## 🏗️ 技术架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client Apps   │    │   AI Services   │    │   Admin Panel   │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │              ┌───────▼───────┐              │
          └──────────────►│  AIIM Gateway │◄─────────────┘
                         │  (FastAPI)    │
                         └───────┬───────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
            ┌───────▼───────┐   │   ┌────────▼────────┐
            │  Message Bus  │   │   │   Auth & Rate   │
            │  (Redis)      │   │   │   Limiter       │
            └───────────────┘   │   └─────────────────┘
                                │
                       ┌────────▼────────┐
                       │   PostgreSQL    │
                       │   (Messages,    │
                       │   Conversations)│
                       └─────────────────┘
```

### 核心组件

- **FastAPI**: 异步Web框架，提供REST API和WebSocket支持
- **SQLAlchemy**: ORM框架，支持PostgreSQL和SQLite
- **Redis**: 消息队列、序列生成、在线状态管理
- **Alembic**: 数据库迁移工具
- **Prometheus**: 指标监控
- **JWT**: 身份认证

### 项目结构

```
aiim/
├── app/
│   ├── api/           # API路由层
│   ├── core/          # 核心功能（认证、序列、事件等）
│   ├── models/        # 数据模型
│   └── services/      # 业务逻辑层
├── alembic/           # 数据库迁移
├── tests/             # 测试用例
└── docker-compose.yml # 容器编排
```

## 📚 API文档

启动服务后，访问以下地址查看API文档：

- **Swagger UI**: http://localhost:8083/docs
- **ReDoc**: http://localhost:8083/redoc
- **健康检查**: http://localhost:8083/health
- **监控指标**: http://localhost:8083/metrics

### API测试

导入 `AIIM.postman_collection.json` 到Postman进行API测试。

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行覆盖率测试
pytest --cov=app tests/

# 运行特定测试
pytest tests/test_im_service.py -v
```

## 🚀 生产部署

### 环境要求

- **Python**: 3.11+
- **数据库**: PostgreSQL 12+ (生产推荐) 或 SQLite (开发)
- **缓存**: Redis 6+ (生产必需)
- **容器**: Docker + Docker Compose

### 性能调优

- 启用Redis用于消息队列和序列生成
- 使用PostgreSQL替代SQLite
- 配置适当的worker数量
- 启用连接池和缓存

### 监控

- Prometheus指标: `/metrics`
- 健康检查: `/health`
- 应用日志: 结构化JSON格式

## 🤝 贡献

我们欢迎各种形式的贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细信息。

### 快速开始贡献

1. Fork 项目
2. 创建特性分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🔗 相关链接

- [技术架构文档](IM%20服务技术方案.md)
- [迁移指南](MIGRATION_TO_AIIM.md)
- [WebSocket测试页面](ws_test.html)

## 📞 支持

- 🐛 [报告Bug](https://github.com/superxabc/aiim/issues)
- 💡 [功能请求](https://github.com/superxabc/aiim/issues)
- 📧 技术支持：通过GitHub Issues

---

⭐ 如果这个项目对您有帮助，请给我们一个星星！
