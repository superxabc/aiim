IM 优化文档

  1. 概述 (Overview)

  本文档旨在设计一个高可用、可扩展的即时通讯（IM）服务平台。该平台作为后端基础设施，旨在为多个业务项目（多租户）提供统一的社交功能，包括但不限于 1:1
  聊天、富媒体消息（图片、文件、表情）以及实时音视频通话。

  2. 核心设计原则

   * 多租户隔离 (Multi-tenancy): 平台必须在逻辑和数据层面严格隔离不同项目（租户）的用户和数据，确保数据安全。
   * 高可用与可扩展 (High Availability & Scalability): 核心服务应设计为无状态或半无状态，易于水平扩展。通过消息队列解耦，确保系统在流量高峰期稳定运行。
   * 实时与可靠 (Real-time & Reliability): 消息传递追求低延迟，同时保证在网络波动或服务重启等异常情况下消息的有序性和不丢失。
   * 安全第一 (Security First): 所有通信链路必须加密，用户身份需严格鉴权，媒体资源访问需授权，并具备基础的防刷、防攻击能力。
   * 协议标准化 (Standardized Protocol): 定义清晰、可扩展的客户端-服务端通信协议，便于多端（Web, iOS, Android）接入和迭代。

  3. 系统架构 (System Architecture)

  下图是我们推荐的系统架构，它在现有项目的基础上进行了增强，以支持多租户和音视频通话。

    1 graph TD
    2     subgraph "客户端 (Clients)"
    3         direction LR
    4         Client_Web[Web/Mobile App<br>(Project A)]
    5         Client_AI[AI Service<br>(Project B)]
    6     end
    7 
    8     subgraph "接入层 (Access Layer)"
    9         WSS[WebSocket 网关 (Gateway)<br>管理长连接、信令转发]
   10         API[RESTful API<br>业务操作、历史消息]
   11     end
   12 
   13     subgraph "核心服务层 (Core Services)"
   14         AuthService[认证服务<br>JWT 签发与校验]
   15         MsgService[消息服务 (Message Service)<br>核心业务逻辑、消息持久化]
   16         RTCService[RTC 信令服务<br>处理音视频通话信令]
   17     end
   18 
   19     subgraph "数据与中间件 (Data & Middleware)"
   20         Kafka[Kafka<br>消息总线，服务解耦]
   21         Redis[Redis<br>在线路由、Seq 生成、缓存]
   22         Postgres[PostgreSQL<br>业务数据存储]
   23         S3[对象存储 (S3/OSS)<br>图片、文件、音视频]
   24         STUN_TURN[STUN/TURN 服务器<br>NAT 穿透]
   25     end
   26 
   27     Client_Web & Client_AI -->|HTTPS| API
   28     Client_Web & Client_AI -->|WSS| WSS
   29 
   30     API & WSS --> AuthService
   31     WSS --> RTCService
   32     API & WSS --> MsgService
   33 
   34     MsgService --> Kafka
   35     RTCService --> Kafka
   36 
   37     Kafka --> MsgService
   38     Kafka --> RTCService
   39 
   40     MsgService --> Postgres
   41     MsgService & WSS & RTCService --> Redis
   42     MsgService --> S3
   43 
   44     Client_Web -->|ICE| STUN_TURN
   45     Client_AI -->|ICE| STUN_TURN

  组件职责:

   * WebSocket 网关 (Gateway):
       * 基于 FastAPI 的 WebSocket 实现。
       * 职责: 维护客户端长连接，处理心跳，验证连接级 token，并将消息和信令路由到 Kafka。它是有状态的，但状态信息（如 user_id -> connection_id）存储在 Redis 中，使其自身可以水平扩展。
   * RESTful API:
       * 职责: 处理无状态的业务请求，如创建会话、拉取历史消息、生成文件上传凭证等。
   * 认证服务 (Auth Service):
       * 职责: 独立的服务或集成在 API 网关中，负责签发和校验包含 user_id 和 tenant_id 的 JWT。
   * 消息服务 (Message Service):
       * 职责: 消费来自 Kafka 的消息，处理核心业务逻辑（如消息存储、状态更新、生成离线推送），并将需要实时推送的消息再次推送到 Kafka 的特定 topic。它是无状态的，可以水平扩展。
   * RTC 信令服务 (RTC Signaling Service):
       * 职责: 专门处理 WebRTC 通话信令（如 offer, answer, ice-candidate）。消费并生产 Kafka 信令消息。同样是无状态的。
   * Kafka:
       * 职责: 作为系统的主动脉，所有跨服务的异步通信都通过 Kafka。它提供了削峰填谷、数据冗余和保证消息顺序的关键能力。
       * im-messages topic: 用于文本、图片等普通消息。
       * im-signaling topic: 用于音视频通话信令。
       * im-events topic: 用于消息回执、状态同步等事件。
   * Redis:
       * 职责:
           * 在线路由: 存储 user_id 到其连接所在的 WebSocket 网关实例 ID 的映射。
           * Seq 生成: 使用 INCR 为每个会话生成严格递增的消息序列号。
           * 缓存: 缓存用户信息、会话信息等热点数据。
   * PostgreSQL:
       * 职责: 持久化存储核心业务数据，如用户信息、会conversation、消息记录等。
   * 对象存储 (S3/OSS):
       * 职责: 存储用户上传的图片、文件等富媒体内容。客户端通过预签名 URL (Pre-signed URL) 的方式安全上传和下载。
   * STUN/TURN 服务器:
       * 职责: 这是实现音视频通话的关键。STUN 用于帮助客户端发现自己的公网地址，TURN 则在无法 P2P 直连时作为中继服务器转发媒体流。可以使用开源实现如 coturn。

  4. 数据模型设计 (增强版)

  为了支持多租户和更丰富的消息类型，我们对数据库模型进行优化。

  `conversations` 表

    1 CREATE TABLE conversations (
    2   id BIGSERIAL PRIMARY KEY,
    3   conv_id VARCHAR(128) UNIQUE NOT NULL, -- 会话的公开ID，如 c-uuid
    4   tenant_id VARCHAR(64) NOT NULL,       -- [新增] 租户ID，用于数据隔离
    5   type SMALLINT NOT NULL DEFAULT 1,     -- 1: 1v1私聊, 2: 群聊
    6   last_msg_id UUID,                     -- 最新一条消息的ID
    7   updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    8   -- 可选的元数据
    9   meta JSONB
   10 );
   11 CREATE INDEX idx_conversations_tenant_id ON conversations (tenant_id);

  `conversation_members` 表

    1 CREATE TABLE conversation_members (
    2   id BIGSERIAL PRIMARY KEY,
    3   conv_id VARCHAR(128) NOT NULL,
    4   user_id VARCHAR(64) NOT NULL,
    5   tenant_id VARCHAR(64) NOT NULL,       -- [新增] 租户ID
    6   unread_count INT DEFAULT 0,           -- 未读消息数
    7   last_read_seq BIGINT DEFAULT 0,       -- 最后已读消息的seq
    8   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    9   UNIQUE (conv_id, user_id)
   10 );
   11 CREATE INDEX idx_conversation_members_user_id ON conversation_members (user_id);

  `messages` 表

    1 CREATE TABLE messages (
    2   id BIGSERIAL PRIMARY KEY,
    3   msg_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(), -- 消息的公开ID
    4   conv_id VARCHAR(128) NOT NULL,
    5   tenant_id VARCHAR(64) NOT NULL,       -- [新增] 租户ID
    6   sender_id VARCHAR(64) NOT NULL,
    7   seq BIGINT NOT NULL,                  -- [核心] 会话内有序序列号
    8   type VARCHAR(32) NOT NULL,            -- text, image, file, audio, video, system, rtc_signal
    9   content JSONB NOT NULL,               -- [核心] 使用JSONB存储不同类型消息内容
   10   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   11 );
   12 -- 核心索引，用于拉取历史消息
   13 CREATE INDEX idx_messages_conv_id_seq_desc ON messages (conv_id, seq DESC);

  `content` 字段 `JSONB` 示例:

   * Text: {"text": "Hello, world!"}
   * Image: {"url": "...", "width": 800, "height": 600, "size": 102400}
   * File: {"url": "...", "fileName": "doc.pdf", "size": 204800}
   * System (e.g., call started): {"event": "call_started", "duration": 3600}
   * RTC Signal: {"signal_type": "offer", "sdp": "..."} (这类消息通常不展示给用户)

  5. 核心流程 (Core Workflows)

  5.1 消息收发流程

   1. 客户端 A 通过 WebSocket 发送消息: { "event": "send_message", "payload": { "conv_id": "...", "type": "text", "content": {"text": "Hi"} } }
   2. WebSocket 网关 收到消息，进行基础校验，然后将消息包装后（附加上 sender_id, tenant_id）发送到 Kafka 的 im-messages topic。
   3. 消息服务 消费该消息。
   4. 从 Redis 获取会话的下一个 seq: INCR seq:<conv_id>。
   5. 将消息（包含 seq）写入 PostgreSQL 的 messages 表。
   6. 更新 conversations 表的 last_msg_id 和 updated_at。
   7. 将完整的消息体（包含 seq, msg_id, created_at）发送到 Kafka 的 im-events topic。
   8. 所有在线的 WebSocket 网关实例都订阅 im-events。
   9. 网关根据消息中的 conv_id，查询会话成员。
   10. 对每个在线的会话成员（通过 Redis 在线路由查询），将消息通过其 WebSocket 连接推送下去。
   11. 客户端 B 收到消息，渲染 UI。

  5.2 语音/视频通话信令流程 (WebRTC)

   1. 客户端 A (发起方) 创建一个 WebRTC offer。
   2. 通过 WebSocket 发送信令: { "event": "rtc_signal", "payload": { "conv_id": "...", "to_user_id": "B", "type": "offer", "sdp": "..." } }
   3. WebSocket 网关 将信令转发到 Kafka 的 im-signaling topic。
   4. RTC 信令服务 消费该信令，然后将其再次推送到 im-events topic，目标是 to_user_id。
   5. 客户端 B (接收方) 的网关收到信令并转发。
   6. 客户端 B 收到 offer，创建一个 answer，并通过 WebSocket 发送回去。
   7. 信令 answer 沿相同路径（A -> Gateway -> Kafka -> RTC Service -> Kafka -> Gateway -> B）到达客户端 A。
   8. 在 offer/answer 交换的同时，双方客户端通过 STUN/TURN 服务器 收集 ICE candidates，并通过 WebSocket 沿上述路径交换。
   9. 一旦双方交换了足够的信息，P2P 连接建立，音视频流直接在客户端之间传输，不再经过我们的服务器。
   10. 通话开始、结束等状态变更，作为 system 类型的消息发送，用于在聊天界面显示“通话已开始”、“通话已结束”等。

  6. API 与 WebSocket 协议

  RESTful API (摘要)

   * POST /v1/im/conversations: 创建会话
   * GET /v1/im/conversations: 获取用户会话列表
   * GET /v1/im/messages: 分页拉取历史消息 (使用 seq 或 cursor)
   * POST /v1/im/media/upload-token: 获取上传文件到对象存储的预签名 URL

  WebSocket 协议

  使用统一的 JSON 格式: { "event": "<event_name>", "payload": { ... }, "ack_id": "<optional_uuid>" }

  Client -> Server Events:

   * authorize: { "token": "jwt_token" } - 连接建立后的第一个包，用于认证。
   * send_message: { "conv_id": "...", "client_msg_id": "...", "type": "text", "content": {...} } - 发送消息。
   * mark_read: { "conv_id": "...", "last_read_seq": 123 } - 标记已读。
   * rtc_signal: { "conv_id": "...", "to_user_id": "...", "type": "offer|answer|ice-candidate", ... } - 发送 WebRTC 信令。

  Server -> Client Events:

   * message_created: { "msg_id": "...", "conv_id": "...", "seq": 124, ... } - 新消息推送。
   * receipt_updated: { "conv_id": "...", "user_id": "...", "last_read_seq": 123 } - 对方已读回执。
   * rtc_signal: { "from_user_id": "...", "type": "...", ... } - 收到 WebRTC 信令。
   * ack: { "for_ack_id": "...", "success": true, "data": {...} } - 对客户端请求的确认回执。

  7. 总结与后续步骤

  这份设计文档提供了一个健壮且可扩展的 IM 平台蓝图。基于现有的 im-platform 项目，下一步的开发重点将是：

   1. 引入多租户支持: 在数据库模型和 JWT 中加入 tenant_id。
   2. 集成 Kafka: 替换现有的内存或 Redis Pub/Sub，作为服务间通信的主干。
   3. 拆分服务: 将消息处理逻辑和 RTC 信令逻辑从网关中剥离，形成独立的微服务。
   4. 实现 RTC 信令服务: 编写处理 WebRTC 信令转发的逻辑。
   5. 实现预签名 URL: 开发用于安全上传富媒体文件的 API。
   6. 客户端配合: 与客户端团队定义并实现详细的 WebSocket 协议和 WebRTC 集成。

  8.基于现有项目和设计，我们将采用以下技术栈和工具：

   * 后端语言: Python 3.10+
   * Web 框架: FastAPI (高性能、异步支持、自动文档)
   * ASGI 服务器: Uvicorn (生产环境推荐 Gunicorn + Uvicorn Worker)
   * 数据库 ORM: SQLAlchemy 2.0 (核心数据模型定义与操作)
   * 数据库迁移: Alembic
   * 消息队列: confluent-kafka-python (Kafka 客户端)
   * 缓存/Pub/Sub: redis-py 或 aioredis (异步 Redis 客户端)
   * 认证: python-jose (JWT 处理)
   * 配置管理: pydantic-settings (从环境变量或 .env 文件加载配置)
   * 监控: prometheus-client (暴露 Prometheus 指标)
   * 日志: Python logging 模块，配合结构化日志库 (如 python-json-logger)
   * 对象存储 SDK: 对应云服务商的 Python SDK (如 boto3 for AWS S3, oss2 for Aliyun OSS)
   * STUN/TURN 服务器: coturn (独立部署)
   * 容器化: Docker, Docker Compose
   * CI/CD: GitHub Actions, GitLab CI 或 Jenkins

  9. 开发规范与最佳实践 (Development Guidelines & Best Practices)

   * 代码风格: 遵循 PEP 8 规范，使用 Black 进行代码格式化，isort 整理导入。
   * 类型提示: 广泛使用 Python 类型提示 (mypy 进行静态检查)，提高代码可读性和可维护性。
   * 异步编程: 充分利用 async/await 关键字，避免阻塞操作，确保服务的高并发性能。
   * 错误处理:
       * 使用 FastAPI 的 HTTPException 统一处理 API 错误。
       * 对外部服务调用（如数据库、Redis、Kafka）进行 try...except 捕获，并记录详细日志。
       * 定义统一的错误码和错误信息。
   * 日志记录:
       * 使用结构化日志 (JSON 格式)，便于日志收集和分析。
       * 日志级别区分明确 (DEBUG, INFO, WARNING, ERROR, CRITICAL)。
       * 记录关键操作的上下文信息 (如 user_id, conv_id, request_id)。
   * 配置管理: 所有可变配置项通过环境变量或配置文件管理，禁止硬编码。
   * 依赖注入: 充分利用 FastAPI 的 Depends 机制进行依赖注入，提高模块的解耦性。
   * 数据库操作:
       * 所有数据库操作通过 ORM 进行，避免直接拼接 SQL。
       * 使用数据库事务保证数据一致性。
       * 注意 N+1 查询问题，合理使用 selectinload 或 joinedload。
   * 消息队列:
       * 生产者和消费者都应处理消息发送/消费失败的情况，实现重试机制。
       * 确保消息的幂等性处理，避免重复消费导致的问题。
   * 安全:
       * 永远不要在代码中硬编码敏感信息（如密钥、密码）。
       * 对所有用户输入进行校验和清理，防止注入攻击。
       * JWT 密钥定期轮换，并确保其安全存储。
       * 文件上传下载必须通过预签名 URL，并限制访问权限和有效期。

  10. 部署与运维考量 (Deployment & Operations Considerations)

   * 容器化: 所有服务都将打包成 Docker 镜像，便于部署和管理。
   * 编排: 使用 Kubernetes (K8s) 或 Docker Swarm 进行容器编排，实现服务的自动伸缩、故障恢复和负载均衡。
   * CI/CD: 建立自动化 CI/CD 流水线，从代码提交到生产部署的全流程自动化。
   * 监控与告警:
       * 应用指标: 通过 Prometheus 收集 FastAPI 服务的 QPS、延迟、错误率、连接数等指标。
       * 系统指标: 监控 CPU、内存、网络 I/O、磁盘使用率等。
       * 数据库指标: 监控 PostgreSQL 的连接数、慢查询、复制延迟等。
       * 消息队列指标: 监控 Kafka 的消息积压、生产/消费延迟。
       * Redis 指标: 监控 Redis 的内存使用、命中率、命令执行时间。
       * 日志聚合: 使用 ELK Stack (Elasticsearch, Logstash, Kibana) 或 Loki/Grafana 等工具进行日志集中收集、存储和查询。
       * 告警: 基于关键指标设置告警规则，通过 PagerDuty、钉钉、企业微信等通知相关人员。
   * 日志管理: 统一日志格式，将日志输出到标准输出，由容器运行时或日志代理收集。
   * 配置管理: 使用 K8s ConfigMap/Secret 或其他配置管理工具统一管理多环境配置。
   * 灰度发布与回滚: 支持小流量灰度发布，并具备快速回滚到上一稳定版本的能力。
   * 容量规划: 定期进行压力测试，评估系统承载能力，并根据业务增长进行容量规划。