# NOTES.md

## AI 生成代码修改记录

本文档记录对 AI 生成代码的修改、原因及未解决的问题。

---

## 后端修改

### 1. chat_service.py - LLM 降级链路接线
**文件**: `backend/app/services/chat_service.py`

**修改内容**: 在 `chat_stream` 方法中添加了 LLM 降级逻辑
- 将主 LLM 调用包裹在 try-except 块中
- 捕获异常后调用 `fallback_to_ollama()` 切换到本地模型
- 添加 SSE status 事件提示用户模型切换

**修改原因**: 原代码中 `fallback_to_ollama()` 方法已定义但从未被调用，导致主模型故障时服务直接中断

**修改行数**: 约 15 行

---

### 2. chat_service.py - 引用片段与 Token 统计修复
**文件**: `backend/app/services/chat_service.py`

**修改内容**:
- 将 token 统计从伪造值 (`token_in=0`, `token_out=len(content)//2`) 改为近似计算 (`len(context)//4`, `len(full_response)//4`)
- 从 `retrieval_results` 中提取实际内容作为引用片段 (snippet)，截断至 120 字符
- 构建完整的 citations 数组传递给 `save_assistant_message`

**修改原因**:
- 引用片段恒为空导致 RAG 可信度无法验证
- Token 统计失真导致成本复盘数据不准确

**修改行数**: 约 20 行

---

### 3. chat_service.py - 模型客户端单例化
**文件**: `backend/app/services/chat_service.py`

**修改内容**:
- 添加 `@lru_cache` 装饰的单例函数：`get_retriever()`, `get_context_builder()`, `get_prompt_builder()`, `get_llm_client()`
- 修改 `chat_stream` 方法调用单例函数而非每次请求创建新实例

**修改原因**: 每次请求重建模型客户端导致性能瓶颈，特别是本地 embedding 模型每次重载

**修改行数**: 约 25 行

---

## 前端修改

### 1. request.ts - SSE 流式请求实现
**文件**: `frontend/src/utils/request.ts`

**修改内容**: 新增 `postStream` 函数
- 使用 `fetch` 发起 POST 请求
- 通过 `ReadableStream` 读取响应体
- 按 `\n\n` 分割 SSE 帧
- 解析 `data:` 行并回调 `onEvent`
- 处理 UTF-8 分包截断（buffer 拼接）
- 支持 `AbortController` 取消请求

**修改原因**: 原前端使用 axios 非流式请求，无法对接后端 SSE 接口

**修改行数**: 约 80 行

---

### 2. Sessions.tsx - SSE 流式对接与契约对齐
**文件**: `frontend/src/pages/Sessions.tsx`

**修改内容**:
- 导入 `postStream` 函数
- 将 `sendMessage` 改用 `postStream` 调用 `/api/chat/stream`
- 处理 SSE 事件类型：`session_id`, `status`, `content`, `done`, `error`
- 请求体字段从 `question` 改为 `message`（对齐后端 `ChatRequest.message`）
- 移除 `response.data.answer` 读取
- `loadMessages` 从 `/sessions/${id}/messages` 改为 `/sessions/${id}`，从返回的 `messages` 字段取数

**修改原因**:
- 前端未实现 SSE 流式对接，核心功能不可用
- 字段契约与后端错位导致 422 错误

**修改行数**: 约 50 行

---

### 3. Sessions.tsx - 修复 done 事件 stale closure
**文件**: `frontend/src/pages/Sessions.tsx`

**修改内容**:
- 添加 `streamingRef` (useRef) 用于累积流式内容
- 修改 `content` 事件处理：使用 `streamingRef.current += event.data` 累加，然后更新 state
- 修改 `done` 事件处理：从 `streamingRef.current` 读取完整内容而非闭包快照
- 移除未使用的 `navigate` 导入

**修改原因**: 原代码在 `done` 事件中使用闭包变量 `streamingContent`，该变量恒为初始值 `''`，导致最终消息内容丢失

**修改行数**: 约 10 行

---

### 4. Sessions.tsx - 清理自定义 CSS（内联样式）
**文件**: `frontend/src/pages/Sessions.tsx`, `frontend/src/index.css`

**修改内容**:
- 移除 `Sessions.tsx` 中所有 `style={{...}}` 内联样式
- 将样式迁移到 `index.css` 中的 CSS 类：`.sider-header`, `.content-container`, `.messages-container`
- 修改 JSX 使用 className 替代 style

**修改原因**: 违反「零自定义 CSS」红线，应回归 AntD 默认样式

**修改行数**: 约 30 行（删除内联样式 + 新增 CSS 类）

---

### 5. index.css - 清理自定义全局样式
**文件**: `frontend/src/index.css`

**修改内容**:
- 删除深色背景 `#242424`
- 删除 `color-scheme` 设置
- 删除 `:root` 中的字体合成、文本渲染等样式
- 删除 `*` 的全局重置样式
- 仅保留 `@import 'antd/dist/reset.css'` 和基础 body/root 样式
- 新增组件样式类（见修改 4）

**修改原因**: 深色背景与 AntD 浅色主题冲突，违反规范

**修改行数**: 从 32 行增加到 36 行（删除全局样式 + 新增组件样式）

---

## 配置文件新增

### 1. 前端 Lint 配置
**新增文件**:
- `frontend/.eslintrc.cjs` - ESLint 配置
- `frontend/.prettierrc` - Prettier 配置

**修改内容**:
- 添加 TypeScript、React、React Hooks 规则
- 设置行宽 100，单引号，无分号
- 添加 `eslint-plugin-react` 到 package.json

**修改原因**: 缺少可执行的 lint 配置，规范无法落地

---

### 2. 后端 Lint 配置
**新增文件**: `backend/ruff.toml`

**修改内容**:
- 配置 Ruff 规则集（E, F, I, N, W, UP）
- 设置行宽 100，目标 Python 3.9
- 添加 `ruff==0.1.9` 到 requirements.txt

**修改原因**: 缺少 Python 代码检查工具

---

## 未解决的问题

### 1. 前端 TypeScript 类型错误
**问题**: IDE 显示大量 TypeScript 类型错误（无法找到模块声明）
**原因**: 依赖未安装（需要运行 `npm install`）
**解决**: 待用户按《使用说明.md》安装依赖后自动解决

---

## 待验证项

1. **SSE 流式响应**: 需启动后端和前端，实际测试流式聊天功能
2. **LLM 降级**: 需模拟主模型故障，验证降级到 Ollama 是否正常
3. **引用片段**: 需验证前端是否正确显示引用来源
4. **Token 统计**: 需对比实际 API 返回的 usage 字段验证准确性
5. **Lint 检查**: 需运行 `npm run lint` 和 `ruff check .` 验证配置
6. **done 事件修复**: 需验证流式回答完成后消息内容是否正确保存

---

## 修改统计

- **后端修改**: 1 个文件，约 60 行
- **前端修改**: 2 个文件，约 170 行（含新增 80 行）
- **配置新增**: 4 个文件
- **总计**: 7 个文件修改/新增

---

## 备注

所有修改均遵循《AI智能客服系统_执行方案》、《改进建议.md》和《项目完整文档》的要求，优先解决 R0/R1 级别的核心功能问题，然后处理 R2/R3 级别的规范治理问题。
