# 企业客服知识库AI助手

基于 Vue 3 + FastAPI + PostgreSQL/pgvector 的企业级智能客服知识库系统。

## 功能特性

- **账号权限管理** — JWT认证 + 角色控制（管理员/编辑者/查看者）
- **知识文档上传** — 支持 PDF、Word(.docx)、Markdown 格式
- **文本智能切分** — 混合切分策略（结构化 + 滑动窗口 + 表格保护）
- **向量检索** — 基于 pgvector 的 HNSW 索引近似最近邻搜索
- **问答对话** — RAG 流式输出，严格基于检索内容回答
- **引用溯源** — 每条回答标注来源文档、页码、相似度
- **人工纠错** — 对错误回答进行纠正标记
- **会话记录** — 保存完整对话历史
- **敏感词过滤** — 输入输出双向过滤
- **反馈统计** — 评分收集与数据分析
- **后台配置** — 模型参数、切片参数、敏感词在线管理

## 技术架构

```
Frontend: Vue 3 + TypeScript + Element Plus + Pinia + Vite
Backend:  FastAPI + SQLAlchemy 2.0 (async) + Alembic
Database: PostgreSQL 16 + pgvector extension
AI:       OpenAI API (text-embedding-ada-002 + GPT-4)
```

## 项目结构

```
├── frontend/          # Vue 3 前端
│   ├── src/
│   │   ├── api/       # Axios 请求封装
│   │   ├── router/    # 路由配置
│   │   ├── stores/    # Pinia 状态管理
│   │   └── views/     # 页面组件
│   └── package.json
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── api/       # 路由处理器
│   │   ├── core/      # 安全、依赖注入
│   │   ├── models/    # ORM 模型
│   │   ├── schemas/   # Pydantic 模型
│   │   ├── services/  # 业务逻辑
│   │   └── tasks/     # 后台任务
│   ├── alembic/       # 数据库迁移
│   ├── tests/         # 测试
│   └── requirements.txt
├── docker-compose.yml
└── .env.example
```

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- OpenAI API Key

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入您的 OPENAI_API_KEY 和其他配置
```

### 2. 启动 PostgreSQL（含 pgvector）

```bash
docker-compose up -d
```

### 3. 启动后端

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt

# 执行数据库迁移
alembic upgrade head

# 初始化种子数据（创建管理员账号）
python seed.py

# 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 5. 访问系统

- 前端界面: http://localhost:5173
- API 文档: http://localhost:8000/docs
- 默认管理员账号: `admin@example.com` / `admin123`

## API 接口一览

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 认证 | POST | `/api/auth/register` | 用户注册 |
| 认证 | POST | `/api/auth/login` | 用户登录 |
| 认证 | POST | `/api/auth/refresh` | 刷新令牌 |
| 认证 | GET | `/api/auth/me` | 当前用户信息 |
| 知识库 | GET | `/api/kb` | 知识库列表 |
| 知识库 | POST | `/api/kb` | 创建知识库 |
| 知识库 | PUT | `/api/kb/{id}` | 更新知识库 |
| 知识库 | DELETE | `/api/kb/{id}` | 删除知识库 |
| 知识库 | POST | `/api/kb/{id}/access` | 授权访问 |
| 文档 | POST | `/api/documents/upload` | 上传文档 |
| 文档 | GET | `/api/documents` | 文档列表 |
| 文档 | PUT | `/api/documents/{id}` | 更新文档（重建索引） |
| 文档 | DELETE | `/api/documents/{id}` | 删除文档 |
| 对话 | POST | `/api/chat/` | 发送消息（SSE流式） |
| 对话 | GET | `/api/chat/conversations` | 会话列表 |
| 对话 | GET | `/api/chat/conversations/{id}` | 会话消息 |
| 对话 | PUT | `/api/chat/messages/{id}/correct` | 人工纠错 |
| 反馈 | POST | `/api/feedback/` | 提交评分 |
| 反馈 | GET | `/api/feedback/stats` | 反馈统计 |
| 管理 | GET | `/api/admin/users` | 用户列表 |
| 管理 | PUT | `/api/admin/users/{id}/role` | 修改角色 |
| 管理 | GET | `/api/admin/config/sensitive-words` | 敏感词列表 |
| 管理 | POST | `/api/admin/config/sensitive-words` | 添加敏感词 |
| 管理 | GET | `/api/admin/stats/dashboard` | 仪表盘统计 |

## 关键设计方案

### 防止模型幻觉

1. 系统提示词严格约束：仅允许基于检索到的上下文回答
2. 相似度阈值过滤（默认 0.75）：低于阈值直接回复"无法找到相关信息"
3. 强制引用标注：每个论述点必须关联到具体文档片段
4. 低温度参数（0.1）减少创造性输出

### 文档更新索引同步

1. 通过 SHA256 哈希检测文件变更
2. 原子替换策略：新建索引完成后才删除旧索引
3. 版本号追踪文档迭代历史
4. 后台异步处理，不阻塞用户请求

### 越权访问防护

1. JWT 令牌携带用户角色信息
2. 知识库三级访问控制：公开/内部/受限
3. `kb_access` 表实现细粒度权限授予
4. 向量检索 SQL 层面强制过滤可访问的知识库

### 长文本精确切分

1. 第一步：按结构标记切分（标题、分页符）
2. 第二步：按语义段落合并/拆分
3. 第三步：滑动窗口 + 重叠（512 tokens / 64 tokens overlap）
4. 表格整体保护，不在表格中间切断
5. 元数据保留：页码、章节标题

### 高并发性能优化

1. 异步 SQLAlchemy + asyncpg 连接池
2. OpenAI API 并发信号量控制（最大 10 并发）
3. 嵌入向量批量生成（每批 20 条）
4. pgvector HNSW 索引加速近似最近邻
5. SSE 流式响应，首 token 延迟极低

## 测试

```bash
cd backend

# 单元测试（不需要数据库）
pytest tests/test_unit.py -v

# API 集成测试（需要数据库运行）
pytest tests/test_api.py -v
```

## 数据库表结构

核心表: `users`, `knowledge_bases`, `documents`, `document_chunks`（含 VECTOR(1536) 列）, `conversations`, `messages`, `feedback`, `sensitive_words`, `system_config`, `kb_access`

详细字段定义见 `backend/app/models/__init__.py`。

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 连接串 | postgresql+asyncpg://kb_user:kb_password@localhost:5432/knowledge_base |
| OPENAI_API_KEY | OpenAI API 密钥 | - |
| OPENAI_CHAT_MODEL | 对话模型 | gpt-4 |
| OPENAI_EMBEDDING_MODEL | 嵌入模型 | text-embedding-ada-002 |
| JWT_SECRET_KEY | JWT 签名密钥 | change-me-in-production |
| CHUNK_SIZE | 切片大小(tokens) | 512 |
| CHUNK_OVERLAP | 切片重叠(tokens) | 64 |
| SIMILARITY_THRESHOLD | 检索相似度阈值 | 0.75 |

## License

MIT
