# AI 智能客服系统 - 后端 (Backend)

基于 FastAPI 的智能客服后端服务，集成 RAG（检索增强生成）与自建 Agent 框架能力。

## 技术栈 (Tech Stack)

- **Web 框架**: FastAPI 0.115 + Uvicorn 0.51（ASGI 服务器）
- **ORM / 数据库**: SQLAlchemy 2.0 + PyMySQL，底层数据库 **MySQL**
- **向量检索**: ChromaDB（本地向量库，用于 RAG 检索与相似度匹配）
- **LLM / 嵌入**: OpenAI SDK（兼容 DashScope / Ollama 等提供商）、FlagEmbedding（文本向量化）
- **数据校验 / 配置**: Pydantic 2.x + pydantic-settings
- **认证**: python-jose（JWT）+ bcrypt（密码哈希，带 72 字节截断）
- **限流**: slowapi（基于 slowapi 的速率限制）
- **文档解析**: pypdf（PDF）、python-docx（Word）
- **测试**: pytest + pytest-asyncio

## 目录结构 (Project Structure)

```
backend/
├── main.py              # 进程入口：加载 app.server:app 并启动 Uvicorn
├── app/
│   ├── server.py        # FastAPI 应用实例：路由注册、CORS、中间件、异常处理
│   ├── config.py        # 配置（pydantic-settings，读取 .env）
│   ├── database.py      # 数据库引擎 / Session 工厂
│   ├── agent/           # 意图分类、路由等 Agent 相关逻辑
│   ├── api/             # API 路由层（auth / chat / knowledge / session ...）
│   ├── core/            # 核心工具（日志、异常、统一响应、追踪、限流）
│   ├── models/          # SQLAlchemy 模型
│   ├── schemas/         # Pydantic 请求 / 响应模型
│   ├── services/        # 业务逻辑层（chat / auth / knowledge / session ...）
│   ├── rag/             # RAG 核心（retriever / context_builder / prompt_builder / loader / llm_client）
│   ├── framework/       # 自建 Agent 框架原语（llm / memory / planner / agent / tools ...）
│   ├── utils/           # 通用工具（依赖注入、鉴权）
│   └── static/          # 静态资源
├── tests/               # 测试用例
├── scripts/             # 辅助脚本
├── data/                # 本地数据 / 向量库（已 gitignore）
├── init_db.sql          # 数据库初始化脚本
├── init_kb.py           # 知识库初始化脚本
├── requirements.txt     # Python 依赖清单
├── pytest.ini           # pytest 配置
└── .env.example         # 环境变量模板
```

## 安装 (Setup)

1. 创建并激活虚拟环境：

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 配置环境变量：

```bash
cp .env.example .env
# 编辑 .env，填入 MySQL 连接串、LLM API Key、JWT 密钥等
```

4. 初始化数据库：

```bash
mysql -u <user> -p <ai_customer_service> < init_db.sql
```

## 运行 (Running)

开发模式（推荐）：

```bash
python main.py
```

或使用 uvicorn 直接启动：

```bash
uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
```

## API 文档 & 健康检查

- Swagger UI: http://localhost:8000/docs
- ReDoc:      http://localhost:8000/redoc
- 健康检查:   http://localhost:8000/health
