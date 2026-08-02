# NOTES（AI 改动 / 踩坑 / 偏离记录）

> 本文件是 AI 协助开发过程中的**知识沉淀**，记录「改了什么、为何改、踩过什么坑、哪些地方偏离了规范」。
> 接到任何新任务前，**先读本文件**，再结合 `docs/文档索引.md` 定位具体规范。本文件优先级高于记忆。

---

## 〇、项目速览（随时可能用到的硬事实）

- **入口**：`backend/main.py` → `uvicorn.run("app.server:app", ...)`。单入口，不要再用旧的 `app/main.py`。
- **启动**：在 `backend/` 下 `python main.py`；`PORT`（默认 8000）、`RELOAD`（默认 false，设 `RELOAD=true` 开热重载）为环境变量。
- **数据库**：**严格 MySQL**。库名 `ai_customer_service`（真实库）。**测试 `pytest` 会 `drop_all`+`create_all` 清空真实库**，跑前请确认数据可丢。
- **文档站点**：`/docs`（Swagger，本地静态资源 `app/static/`）、`/redoc`、`/health`。FastAPI 内置 docs 已被禁用（离线可用）。
- **当前分支**：`feature/agent-doc-index`；保护分支名为 `master`（非 `main`）。

## 一、近期 AI 改动时间线

- **2026-08-02**：定位并修复 `python main.py` 启动即崩 —— 根因 `.env` 含 UTF-8 中文注释，中文 Windows 用 GBK 读导致 `UnicodeDecodeError: 'gbk'`。修复：`.env` 改纯 ASCII + `config.py` 加 `env_file_encoding="utf-8"` 兜底。
- **2026-08-02**：`main.py` 的 `uvicorn.run(reload=True)` 改为默认 `reload=False`（由环境变量控制）。修复 Windows 下 Ctrl+C 残留孤儿进程。
- **2026-08-02**：测试库 `ai_customer_service_test` 删除，`tests/conftest.py` 改连真实库（`settings.db_name`）。
- **2026-08-02**：补全缺失接口（代码侧）：knowledge `GET/PUT /api/kb/documents/{id}`、feedback `GET /api/feedback` + `GET/DELETE /api/feedback/{id}`、chat `POST /api/chat/send` + `GET /api/chat/history`。RAG 管线抽成共享生成器 `_chat_events`，`/stream` 与 `/send` 共用。
- **2026-08-03（本轮）**：
  - **P0**：`docs/API文档.md` 补 7 个接口定义 + 刷新「已知差距」；本 `NOTES.md` 新建；`docs/文档索引.md` 移除两份悬空引用、强化 NOTES 引用。
  - **P1**：9 个模型由旧式 `Column(...)` 迁移为 SQLAlchemy 2.0 风格 `Mapped[...]` + `mapped_column(...)`（SQLAlchemy 2.0.29）；`chat_service.py` 查询改用 `select()`；chat 历史查询从 API 层下沉到 `ChatService.get_history`（消除 API 层直查 DB 的分层违规）；新建 25 条问答评测集。
  - **P2/P3**：仅为 4 处公开函数补 docstring（未做返回注解/分支/提交信息整改）；**P3 的 pre-commit/CI 强制 lint 项已决策不采纳**（见下方「与规范的偏离」）。

## 二、踩坑记录（踩过的雷，避免重踩）

1. **`.env` 中文注释 + 中文 Windows = GBK 解码崩溃**。教训：配置文件保持 ASCII；或 `config.py` 设 `env_file_encoding="utf-8"`。
2. **`reload=True` 在 Windows 下 Ctrl+C 可能残留 uvicorn 子进程**，占着 8000 端口。已默认关闭。
3. **FastAPI 0.115.0 内置 `/docs` 硬编码 jsDelivr CDN**，离线打开空白。已改为禁用内置路由 + 本地 `app/static/` 资源 + 自定义 `/docs`/`/redoc`。
4. **沙箱与本机进程隔离**：WorkBuddy 内终端看不到本机进程，`taskkill` 对本机/沙箱自身进程无效；本机残留进程需在本机真实终端清理。
5. **`pytest` 会清空真实库**：`conftest` 每用例 `drop_all`+`create_all`。跑测试前务必确认数据可丢或先备份。

## 三、与规范的偏离（需向评审/面试解释的地方）

- **sessions 更新接口**：`PUT /api/sessions/{id}` 的 `title` 仍走 **Query 参数**（非 Body），为不破坏已绿的 52 接口测试套件而保留。规范偏好的 REST 风格是放 Body。
- **返回类型注解**：123 个函数中有 52 个缺 `->`（多为 FastAPI 路由与 `__init__`）。规范字面要求全带，业界常豁免路由/`__init__`，尚未统一决策。
- **无 CI / 未强制 lint（已决策）**：不引入 pre-commit / `.github/workflows` / CI 强制。提交由手动 `git commit` 完成；`backend/ruff.toml` 已删除（原 ruff 配置不再保留）。本地可自选 `ruff check` / `black` 自查，但非门禁。
- **ORM `select()` 未全量迁移**：本轮仅 `chat_service.py` 改用 `select()`，其余 service 仍用 `db.query(...)`（SQLAlchemy 2.0 仍兼容）。全量迁移属更大改动，应配合测试覆盖进行。

## 四、待验证 / 待办

- [ ] 评测集（`backend/tests/eval/qa_set.json`）需**实跑服务 + DashScope** 后填写真实检索/回答/引用准确率（门禁：检索>80%、回答>75%、引用>90%），当前仅有用例与占位结果。
- [ ] 是否将 sessions `PUT` 的 `title` 改为 Body（并同步改 `test_session_api.py`）。
- [ ] 是否补 return annotation 或明文豁免。
- [ ] 交付前：`pytest` 跑通全量（会清空真实库）→ 用种子/初始化脚本重建业务数据 → 提交 → 推送。

## 五、关键文件路径速查

| 内容 | 路径 |
|------|------|
| 启动入口 | `backend/main.py` |
| 应用本体 / 自定义 docs 路由 | `backend/app/server.py` |
| 配置（含 db、jwt、配额） | `backend/app/config.py` |
| 接口路由 | `backend/app/api/{auth,session,knowledge,chat,feedback}.py` |
| 业务逻辑 | `backend/app/services/*.py` |
| ORM 模型（2.0 风格） | `backend/app/models/*.py` |
| 统一响应 / 异常 | `backend/app/core/response.py`、`backend/app/core/exceptions.py` |
| RAG 模块 | `backend/app/rag/{loader,splitter,embedder,vector_store,retriever,context_builder,prompt_builder,llm_client}.py` |
| 测试 | `backend/tests/`（conftest 连真实库）、`backend/tests/eval/qa_set.json` |
| 规范文档 | `docs/*.md`、`文档索引.md` |
