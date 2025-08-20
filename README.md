# AIIM - AI Instant Messaging

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

AIIM v2.0是一个企业级即时通讯系统，专为AI应用场景设计。基于FastAPI + SQLAlchemy + Redis构建，支持实时消息传递、音视频通话、AI流式消息处理和多端同步。

## ✨ 核心特性

### 基础IM功能
- 🚀 **实时通信**: WebSocket双向通信，支持订阅/发布模式
- 🔄 **消息顺序**: 基于Redis的严格消息序列保证
- 📱 **多端同步**: 支持多设备消息同步和状态管理
- 🤖 **AI集成**: 原生支持AI流式消息处理
- 📊 **送达回执**: 完整的消息状态跟踪（已发送/已送达/已读）

### 音视频功能 (v2.0新增)
- 🎵 **语音消息**: 异步语音消息录制、上传、播放
- 📞 **实时通话**: WebRTC音视频通话支持
- 📁 **媒体存储**: 集成MinIO/阿里云OSS对象存储
- 🌐 **NAT穿越**: 内置STUN/TURN服务器支持

### 企业级特性
- 🔍 **可观测性**: 内置健康检查、Prometheus指标监控
- 🔐 **安全认证**: 多层认证（JWT、API Key、内容验证）
- 🛡️ **安全加固**: 速率限制、安全头、防攻击机制
- 📈 **高可用**: 支持分布式部署、水平扩展、生产就绪

## 🚀 快速开始

### 开发环境

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

### 生产环境部署

⚠️ **重要提醒**：生产环境部署请使用专门的部署脚本，支持分布式架构和音视频功能。

```bash
# 生产环境部署（推荐）
cd ../deployment-scripts

# 主服务器部署（ECS-1: 2核2GB）
./orchestration/deploy_complete_aiim_cluster.sh --role main --media-server <媒体服务器IP>

# 媒体服务器部署（ECS-2: 2核4GB）  
./orchestration/deploy_complete_aiim_cluster.sh --role media --main-server <主服务器IP>
```

详细部署文档请参考 [deployment-scripts/README.md](../deployment-scripts/README.md)

## 🔧 配置说明

关键环境变量：

| 变量名 | 描述 | 默认值 | 必填 |
|--------|------|--------|------|
| `JWT_SECRET` | JWT签名密钥 | - | ✅ |
| `DATABASE_URL` | 数据库连接URL | `sqlite:///./im.db` | ❌ |
| `REDIS_URL` | Redis连接URL | - | 生产环境必填 |
| `MINIO_ENDPOINT` | 对象存储端点 | `localhost:9000` | 音视频功能必填 |
| `MINIO_ACCESS_KEY` | 对象存储访问密钥 | - | 音视频功能必填 |
| `STUN_SERVERS` | STUN服务器列表 | Google公共STUN | ❌ |
| `TURN_SERVER` | TURN服务器地址 | - | WebRTC通话推荐 |
| `RATE_LIMIT_PER_SEC` | 速率限制（请求/秒） | `10` | ❌ |

完整配置请参考 `env.example` 文件。

## 📋 API概览

### REST API（需 Authorization: Bearer <JWT>）

**基础IM功能:**
- `POST /api/aiim/conversations` - 创建会话
- `GET /api/aiim/conversations` - 获取会话列表
- `POST /api/aiim/messages` - 发送消息（支持文本、音频等）
- `GET /api/aiim/messages/{conversation_id}` - 获取消息历史
- `POST /api/aiim/messages/stream` - 流式消息发送

**媒体功能 (v2.0):**
- `POST /api/aiim/media/upload_token` - 获取媒体上传令牌
- `POST /api/aiim/media/upload_complete` - 完成媒体上传
- `GET /api/aiim/media/{media_id}/download` - 下载媒体文件
- `GET /api/aiim/media/{media_id}/metadata` - 获取媒体元数据

**通话功能 (v2.0):**
- `POST /api/aiim/calls/initiate` - 发起通话
- `POST /api/aiim/calls/{call_id}/accept` - 接受通话
- `POST /api/aiim/calls/{call_id}/reject` - 拒绝通话
- `POST /api/aiim/calls/{call_id}/hangup` - 挂断通话
- `GET /api/aiim/calls/ice-configuration` - 获取WebRTC配置

### WebSocket `/api/aiim/ws?token=<JWT>`

**消息功能:**
- `subscribe`/`unsubscribe` - 订阅/取消订阅会话
- `send_msg` → 消息发送确认 + `message.created` 事件
- `stream_chunk` → 流式消息片段 + `message.stream_chunk` 事件
- `delivered` - 消息送达回执

**通话功能 (v2.0):**
- `call.initiate` - 发起通话信令
- `call.webrtc.signal` - WebRTC信令交换
- `call.accept`/`call.reject`/`call.hangup` - 通话控制

**系统功能:**
- `ping`/`pong` - 心跳保活 + 在线状态维护

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

**应用框架:**
- **FastAPI**: 异步Web框架，提供REST API和WebSocket支持
- **SQLAlchemy**: ORM框架，支持PostgreSQL和SQLite
- **Alembic**: 数据库迁移工具

**存储与缓存:**
- **PostgreSQL**: 主数据库，存储消息、会话、通话记录
- **Redis**: 消息队列、序列生成、在线状态管理
- **MinIO/阿里云OSS**: 对象存储，用于媒体文件

**通信与安全:**
- **WebRTC**: 实时音视频通话技术
- **coturn**: STUN/TURN服务器，NAT穿越
- **JWT**: 身份认证和授权

**监控与运维:**
- **Prometheus**: 指标监控和告警
- **Nginx**: 反向代理和负载均衡
- **Docker**: 容器化部署

### 项目结构

```
aiim/
├── app/
│   ├── api/           # API路由层
│   │   ├── im_api.py      # 基础IM接口
│   │   ├── im_ws.py       # WebSocket实时通信
│   │   ├── media_api.py   # 媒体文件接口 (NEW)
│   │   └── call_api.py    # 通话管理接口 (NEW)
│   ├── core/          # 核心功能
│   │   ├── config.py          # 配置管理
│   │   ├── media_storage.py   # 媒体存储服务 (NEW)
│   │   ├── turn_service.py    # TURN服务集成 (NEW)
│   │   ├── security.py        # 安全中间件 (NEW)
│   │   └── monitoring.py      # 监控系统 (NEW)
│   ├── models/        # 数据模型
│   │   └── im.py          # 扩展支持音视频消息
│   └── services/      # 业务逻辑层
│       └── call_service.py    # 通话管理服务 (NEW)
├── alembic/           # 数据库迁移
├── docker-compose.yml         # 开发环境
├── docker-compose.prod.yml    # 生产环境基础配置
└── env.production.example     # 生产环境配置模板 (NEW)
```

## 📚 API文档

启动服务后，访问以下地址查看API文档：

- **Swagger UI**: http://localhost:8083/docs
- **ReDoc**: http://localhost:8083/redoc
- **健康检查**: http://localhost:8083/health
- **监控指标**: http://localhost:8083/metrics

### API测试

1. **开发环境**: 查看 `/docs` 或 `/redoc` 进行交互式API测试
2. **生产环境**: 使用专业API测试工具，参考技术方案文档中的API规范

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

**基础运行环境:**
- **Python**: 3.11+
- **数据库**: PostgreSQL 15+ (推荐) 或 SQLite (开发)
- **缓存**: Redis 7+ (生产必需)
- **容器**: Docker + Docker Compose

**音视频功能依赖 (v2.0):**
- **对象存储**: MinIO 或 阿里云OSS
- **TURN服务器**: coturn (用于NAT穿越)
- **负载均衡**: Nginx (生产环境)

### 分布式部署架构

```
生产环境推荐配置:
├── ECS-1 (2核2GB) - 主应用服务器
│   ├── AIIM应用 + PostgreSQL + Redis
│   └── Nginx反向代理
└── ECS-2 (2核4GB) - 媒体服务器  
    ├── coturn (TURN服务器)
    └── MinIO (对象存储)
```

### 监控和可观测性

- **健康检查**: `/health`, `/healthz`, `/ready`
- **Prometheus指标**: `/metrics` - 业务和系统指标
- **结构化日志**: JSON格式，支持集中化日志收集
- **性能监控**: 请求响应时间、错误率、资源使用情况

## 🤝 贡献

我们欢迎各种形式的贡献！

### 快速开始贡献

1. Fork 项目
2. 创建特性分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送分支: `git push origin feature/amazing-feature`
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🔗 相关链接

- [技术架构文档](aiim技术方案-v2.md) - 详细的v2.0技术方案
- [部署脚本文档](../deployment-scripts/README.md) - 生产环境部署指南

## 📞 支持

- 🐛 [报告Bug](https://github.com/superxabc/aiim/issues)
- 💡 [功能请求](https://github.com/superxabc/aiim/issues)
- 📧 技术支持：通过GitHub Issues

---

⭐ 如果这个项目对您有帮助，请给我们一个星星！
