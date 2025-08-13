# 贡献指南

感谢您对AIIM项目的关注！我们欢迎各种形式的贡献。

## 开发环境设置

### 本地开发

1. **克隆仓库**
   ```bash
   git clone https://github.com/superxabc/aiim.git
   cd aiim
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或 venv\Scripts\activate  # Windows
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置环境变量**
   ```bash
   cp env.example .env
   # 编辑 .env 文件，设置必要的配置
   ```

5. **运行开发服务器**
   ```bash
   DEV_AUTO_CREATE_TABLES=true uvicorn main:app --reload --port 8083
   ```

### Docker开发

```bash
# 构建开发镜像
docker build -t aiim:dev .

# 运行开发容器
docker run -p 8083:8083 -e JWT_SECRET=dev_secret aiim:dev

# 或使用docker-compose
docker-compose up -d
```

## 代码规范

### Python代码风格

- 遵循 PEP 8 规范
- 使用 Black 进行代码格式化
- 使用 isort 对导入进行排序
- 使用 mypy 进行类型检查

```bash
# 安装开发工具
pip install black isort mypy

# 格式化代码
black .
isort .

# 类型检查
mypy app/
```

### 提交规范

使用约定式提交（Conventional Commits）：

- `feat:` 新功能
- `fix:` 修复bug
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建过程或辅助工具的变动

示例：
```
feat: 添加消息加密功能
fix: 修复WebSocket连接超时问题
docs: 更新API文档
```

## 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_im_service.py

# 运行覆盖率测试
pytest --cov=app tests/
```

### 编写测试

- 为新功能编写单元测试
- API测试应包含正常和异常情况
- WebSocket功能需要集成测试
- 测试文件放在 `tests/` 目录下

## API文档

### 自动生成的文档

启动服务后访问：
- Swagger UI: http://localhost:8083/docs
- ReDoc: http://localhost:8083/redoc

### 手动测试

使用提供的Postman集合：
1. 导入 `AIIM.postman_collection.json`
2. 设置环境变量 `base_url` 和 `jwt_token`
3. 执行测试用例

## 数据库迁移

### 创建迁移

```bash
# 生成新的迁移文件
alembic revision --autogenerate -m "描述你的更改"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

### 迁移最佳实践

- 仔细检查生成的迁移文件
- 为重要的数据变更提供数据迁移脚本
- 测试迁移的前向和后向兼容性

## 提交拉取请求

1. **Fork项目** 到你的GitHub账户

2. **创建特性分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **提交更改**
   ```bash
   git add .
   git commit -m "feat: 描述你的更改"
   ```

4. **推送分支**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **创建拉取请求**
   - 在GitHub上创建Pull Request
   - 详细描述你的更改
   - 关联相关的issue（如果有）

## 拉取请求检查清单

- [ ] 代码遵循项目规范
- [ ] 添加了必要的测试
- [ ] 所有测试通过
- [ ] 更新了相关文档
- [ ] 提交信息清晰明确
- [ ] 没有破坏性变更（或已适当标注）

## 报告问题

在GitHub Issues中报告bug时，请提供：

1. **环境信息**
   - 操作系统
   - Python版本
   - AIIM版本

2. **重现步骤**
   - 详细的步骤描述
   - 预期结果
   - 实际结果

3. **相关日志**
   - 错误日志
   - 配置信息（隐藏敏感信息）

## 功能请求

提交功能请求时，请包含：

1. **用例描述** - 为什么需要这个功能
2. **详细说明** - 功能应该如何工作
3. **可能的实现** - 如果有想法的话

## 代码审查

我们重视代码质量，所有PR都需要经过代码审查：

- **功能性** - 代码是否实现了预期功能
- **可读性** - 代码是否清晰易懂
- **性能** - 是否有性能影响
- **安全性** - 是否引入安全问题
- **兼容性** - 是否保持向后兼容

## 社区准则

- 保持友好和专业的态度
- 尊重不同的观点和经验水平
- 建设性地提供反馈
- 帮助新贡献者融入社区

## 许可证

通过贡献代码，您同意您的贡献将在MIT许可证下发布。

## 联系方式

- GitHub Issues: 技术问题和bug报告
- GitHub Discussions: 一般讨论和问题

感谢您的贡献！🎉
