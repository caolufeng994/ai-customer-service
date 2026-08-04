# Framework Primitives - 演示库

## 重要说明

本目录下的框架原语（`llm.py`, `tools.py`, `memory.py`, `retriever.py`, `prompt.py`, `agent.py`, `planner.py`, `chain.py`）为**自建框架的演示实现**，用于展示对标LangChain等第三方框架的设计思路。

## 当前集成状态

| 模块 | 集成状态 | 说明 |
|------|---------|------|
| `llm.py` | ✅ 已集成 | `FallbackLLM` 已在 `llm_client.py` 中接线 |
| `memory.py` | ✅ 已集成 | `QueryRewriter` 已在 `chat_service.py` 中接线 |
| `tools.py` | ❌ 未集成 | 演示性质，未接入主流程 |
| `agent.py` | ❌ 未集成 | 演示性质，未接入主流程 |
| `planner.py` | ❌ 未集成 | 演示性质，未接入主流程 |
| `retriever.py` | ❌ 未集成 | 演示性质，使用现有 `app/rag/vector_store` |
| `prompt.py` | ❌ 未集成 | 演示性质，使用现有 `app/rag/prompt_builder` |
| `chain.py` | ❌ 未集成 | 演示性质，未接入主流程 |

## 生产集成计划

如需将框架原语集成到生产环境，需要完成以下工作：

1. **G1 工具调用链集成**
   - 将 `ReActAgent` 接入 `chat_service` 主流程
   - 提供 `/api/agent/tools` 接口
   - 实现 `tool_calls` 落库
   - 意图路由 `TOOL` 路径

2. **G5 检索增强集成**
   - 将 `VectorRetriever` 替换现有 `app/rag/vector_store`
   - 实现真实的 L1 重排（cross-encoder）
   - 实现 L3 分层摘要（LLM摘要）

3. **G8-G16 其他功能**
   - 可观测性持久化
   - 熔断限流
   - 会话管理
   - 状态机
   - 错误分类

## 设计原则

- **零依赖**: 不依赖 LangChain、LangGraph、LlamaIndex 等第三方框架
- **可扩展**: 抽象基类设计，支持多实现
- **可测试**: 每个原语都有对应的单元测试
- **向后兼容**: 现有业务代码无需修改即可运行

## 测试覆盖

框架原语单元测试位于 `tests/test_framework_primitives.py`，覆盖：
- `QueryRewriter`: 多轮指代改写
- `verify_citations`: 引用校验
- `WindowMemory`: 窗口记忆
- `CompactionMemory`: 压缩记忆
- `FallbackLLM`: 降级状态机
- `LLMResult`: 数据契约
