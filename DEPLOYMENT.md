# AIIM 部署指南

本文档详细说明如何在不同环境中部署AIIM服务。

## 🎯 部署选项

### 1. Docker Compose（推荐）

适用于开发、测试和小规模生产环境。

#### 开发环境

```bash
# 克隆项目
git clone https://github.com/superxabc/aiim.git
cd aiim

# 配置环境变量
cp env.example .env

# 编辑 .env 文件
# JWT_SECRET=your_secret_key_here
# POSTGRES_PASSWORD=secure_password

# 启动服务
docker-compose up -d

# 检查服务状态
docker-compose ps
docker-compose logs -f aiim
```

#### 生产环境

```bash
# 使用生产配置
docker-compose -f docker-compose.prod.yml up -d

# 或者同时启用Nginx
docker-compose -f docker-compose.prod.yml --profile nginx up -d
```

### 2. Kubernetes 部署

适用于大规模生产环境和云原生部署。

#### 基础 Kubernetes 配置

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aiim
---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: aiim-config
  namespace: aiim
data:
  JWT_ALGORITHM: "HS256"
  RATE_LIMIT_PER_SEC: "20"
  REQUIRE_REDIS: "true"
  INSTANCE_ID: "aiim-k8s"
---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: aiim-secrets
  namespace: aiim
type: Opaque
data:
  JWT_SECRET: <base64_encoded_jwt_secret>
  POSTGRES_PASSWORD: <base64_encoded_password>
---
# k8s/postgres.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: aiim
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_USER
          value: aiim_user
        - name: POSTGRES_DB
          value: aiim_db
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: aiim-secrets
              key: POSTGRES_PASSWORD
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: aiim
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
---
# k8s/redis.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: aiim
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        command: ["redis-server"]
        args: ["--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"]
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: aiim
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
---
# k8s/aiim.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aiim
  namespace: aiim
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aiim
  template:
    metadata:
      labels:
        app: aiim
    spec:
      containers:
      - name: aiim
        image: aiim:latest
        ports:
        - containerPort: 8083
        env:
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: aiim-secrets
              key: JWT_SECRET
        - name: DATABASE_URL
          value: "postgresql+psycopg2://aiim_user:$(POSTGRES_PASSWORD)@postgres:5432/aiim_db"
        - name: REDIS_URL
          value: "redis://redis:6379/0"
        envFrom:
        - configMapRef:
            name: aiim-config
        livenessProbe:
          httpGet:
            path: /health
            port: 8083
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8083
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: aiim
  namespace: aiim
spec:
  selector:
    app: aiim
  ports:
  - port: 8083
    targetPort: 8083
  type: LoadBalancer
```

#### 部署到Kubernetes

```bash
# 创建命名空间和配置
kubectl apply -f k8s/

# 检查部署状态
kubectl get pods -n aiim
kubectl get services -n aiim

# 查看日志
kubectl logs -f deployment/aiim -n aiim
```

### 3. 云服务部署

#### AWS ECS

```json
{
  "family": "aiim",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::account:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "aiim",
      "image": "your-account.dkr.ecr.region.amazonaws.com/aiim:latest",
      "portMappings": [
        {
          "containerPort": 8083,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "REDIS_URL",
          "value": "redis://your-elasticache-endpoint:6379"
        },
        {
          "name": "DATABASE_URL",
          "value": "postgresql+psycopg2://user:pass@your-rds-endpoint:5432/aiim"
        }
      ],
      "secrets": [
        {
          "name": "JWT_SECRET",
          "valueFrom": "arn:aws:ssm:region:account:parameter/aiim/jwt-secret"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/aiim",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

#### Google Cloud Run

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: aiim
  annotations:
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/vpc-access-connector: projects/PROJECT/locations/REGION/connectors/CONNECTOR
    spec:
      containers:
      - image: gcr.io/PROJECT/aiim:latest
        ports:
        - containerPort: 8083
        env:
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: aiim-secrets
              key: jwt-secret
        - name: DATABASE_URL
          value: postgresql+psycopg2://user:pass@CLOUD_SQL_IP:5432/aiim
        - name: REDIS_URL
          value: redis://MEMORYSTORE_IP:6379
        resources:
          limits:
            memory: 1Gi
            cpu: 1000m
```

### 4. 裸机部署

#### 系统要求

- Ubuntu 20.04+ / CentOS 8+ / Alibaba Cloud Linux 3
- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- Nginx (可选)

#### 安装步骤

```bash
# 1. 安装系统依赖
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql redis-server nginx

# 2. 创建应用用户
sudo useradd -m -s /bin/bash aiim
sudo -u aiim -i

# 3. 下载和配置应用
git clone https://github.com/superxabc/aiim.git
cd aiim

# 4. 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. 配置数据库
sudo -u postgres createuser aiim
sudo -u postgres createdb aiim_db -O aiim
sudo -u postgres psql -c "ALTER USER aiim PASSWORD 'secure_password';"

# 6. 配置环境变量
cp env.example .env
# 编辑 .env 文件

# 7. 运行数据库迁移
alembic upgrade head

# 8. 创建systemd服务
sudo tee /etc/systemd/system/aiim.service << EOF
[Unit]
Description=AIIM Service
After=network.target

[Service]
Type=exec
User=aiim
Group=aiim
WorkingDirectory=/home/aiim/aiim
Environment=PATH=/home/aiim/aiim/venv/bin
ExecStart=/home/aiim/aiim/venv/bin/gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8083 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 9. 启动服务
sudo systemctl daemon-reload
sudo systemctl enable aiim
sudo systemctl start aiim

# 10. 配置Nginx
sudo tee /etc/nginx/sites-available/aiim << 'EOF'
upstream aiim_backend {
    server 127.0.0.1:8083;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://aiim_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/aiim/ws {
        proxy_pass http://aiim_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/aiim /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 🔧 环境配置

### 必需的环境变量

| 变量名 | 描述 | 示例值 |
|--------|------|--------|
| `JWT_SECRET` | JWT签名密钥（必须强密码） | `your-super-secret-jwt-key-here` |
| `DATABASE_URL` | 数据库连接URL | `postgresql+psycopg2://user:pass@host:5432/db` |
| `REDIS_URL` | Redis连接URL | `redis://localhost:6379/0` |

### 可选的环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `INSTANCE_ID` | 实例标识符 | `aiim-instance-1` |
| `RATE_LIMIT_PER_SEC` | 速率限制 | `10` |
| `REQUIRE_REDIS` | 强制要求Redis | `false` |
| `DEV_AUTO_CREATE_TABLES` | 自动创建表（仅开发） | `false` |

## 📊 监控和维护

### 健康检查

```bash
# 检查服务健康状态
curl http://localhost:8083/health

# 检查Prometheus指标
curl http://localhost:8083/metrics
```

### 日志管理

```bash
# Docker Compose
docker-compose logs -f aiim

# Kubernetes
kubectl logs -f deployment/aiim -n aiim

# Systemd
sudo journalctl -u aiim -f
```

### 备份策略

#### 数据库备份

```bash
# PostgreSQL备份
pg_dump -h localhost -U aiim_user aiim_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 定时备份（crontab）
0 2 * * * pg_dump -h localhost -U aiim_user aiim_db > /backups/aiim_$(date +\%Y\%m\%d).sql
```

#### Redis备份

```bash
# Redis备份
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb /backups/redis_$(date +%Y%m%d).rdb
```

### 更新部署

#### Docker更新

```bash
# 拉取最新镜像
docker-compose pull

# 重新部署
docker-compose up -d

# 清理旧镜像
docker image prune
```

#### Kubernetes更新

```bash
# 更新镜像
kubectl set image deployment/aiim aiim=aiim:new-version -n aiim

# 检查滚动更新状态
kubectl rollout status deployment/aiim -n aiim

# 回滚（如果需要）
kubectl rollout undo deployment/aiim -n aiim
```

## 🔒 安全最佳实践

1. **使用强JWT密钥**：至少32字符的随机字符串
2. **启用HTTPS**：生产环境必须使用SSL/TLS
3. **网络隔离**：数据库和Redis不要暴露到公网
4. **定期更新**：及时更新依赖包和基础镜像
5. **访问控制**：使用防火墙限制访问端口
6. **日志审计**：记录重要操作和访问日志

## 🚨 故障排查

### 常见问题

1. **服务无法启动**
   ```bash
   # 检查端口占用
   netstat -tlnp | grep 8083
   
   # 检查配置文件
   cat .env
   
   # 检查日志
   docker-compose logs aiim
   ```

2. **数据库连接失败**
   ```bash
   # 测试数据库连接
   psql -h localhost -U aiim_user -d aiim_db
   
   # 检查数据库服务
   sudo systemctl status postgresql
   ```

3. **Redis连接问题**
   ```bash
   # 测试Redis连接
   redis-cli ping
   
   # 检查Redis服务
   sudo systemctl status redis
   ```

4. **WebSocket连接问题**
   - 检查Nginx配置中的WebSocket升级设置
   - 确认防火墙没有阻止WebSocket连接
   - 检查JWT token是否有效

### 性能调优

1. **数据库优化**
   ```sql
   -- 创建索引
   CREATE INDEX CONCURRENTLY idx_messages_conversation_seq ON im_messages(conversation_id, seq);
   
   -- 配置连接池
   -- 在DATABASE_URL中添加: ?pool_size=20&max_overflow=30
   ```

2. **Redis优化**
   ```conf
   # redis.conf
   maxmemory 256mb
   maxmemory-policy allkeys-lru
   save 900 1
   save 300 10
   ```

3. **应用层优化**
   ```bash
   # 增加worker数量
   gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 4 --worker-connections 100
   ```

## 📞 支持

如果遇到部署问题，请：

1. 查看本文档的故障排查部分
2. 检查[GitHub Issues](https://github.com/superxabc/aiim/issues)
3. 创建新的Issue描述问题

---

希望这个部署指南对您有帮助！如有任何问题，欢迎提出Issue或贡献改进建议。
