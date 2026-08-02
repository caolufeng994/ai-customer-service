# API 文档

> 本文档已根据代码实现逐一核对修正（响应信封、分页结构、错误格式、错误码名称与取值、Base URL、健康检查接口等）。SSE 流式对话的协议细节按当前代码描述，需求规格中 `meta`/`suggestion` 等增强事件见文末「已知差距」。

## 概述

AI 智能客服系统提供 RESTful API 接口，支持用户认证、会话管理、知识库管理、流式聊天和反馈评价等功能。

**Base URL**：`http://localhost:8000`

> 注意：所有接口路径均以 `/api` 开头（例如 `POST /api/auth/register`），Base URL 本身不再包含 `/api`。

**认证方式**：JWT Bearer Token。在请求头中携带：

```
Authorization: Bearer <token>
```

> Swagger UI（`/docs`）中点击右上角 **Authorize** 后，**只需填入 token 本身，不要加 `Bearer ` 前缀**（Swagger 会自动拼接为 `Authorization: Bearer <token>`）。

## 通用响应格式

### 成功响应（统一信封 ApiResponse）

所有成功响应（HTTP 200/201）遵循统一信封结构：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Operation successful",
  "data": { }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 请求是否成功，`true` |
| `code` | string | 业务结果码，成功恒为 `"SUCCESS"` |
| `message` | string | 人类可读提示信息 |
| `data` | object / array / null | 业务数据载体，结构因接口而异 |

### 分页响应

列表类接口在成功信封基础上，额外返回 `meta` 字段描述分页信息，`data` 为**数组**（不再是 `{items, total}` 结构）：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Operation successful",
  "data": [
    {
      "id": 1,
      "title": "产品咨询"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

### 错误响应

所有业务/校验错误统一返回 HTTP 状态码 + 如下结构：

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Error message description"
  }
}
```

- `code`：机器可读错误码（字符串，见「错误码」章节）。
- HTTP 状态码表示错误类别（401 认证 / 403 权限 / 404 资源不存在 / 400 参数 / 429 配额 / 500 / 503）。
- 绝大多数接口通过 `HTTPException(detail={"code":..., "message":...})` 返回上述结构；仅**未捕获的 500 内部异常**会走 `ApiResponse` 信封（`{"success":false,"code":"INTERNAL_ERROR","message":"An unexpected error occurred"}`）。

#### 字段级校验失败（HTTP 422）

当请求体/参数不符合 Pydantic 模型约束（缺必填字段、类型错误、超出长度/数值边界等），框架直接返回 **HTTP 422**，响应体为 `detail` **数组**（非 `{code, message}` 对象）：

```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "Field required",
      "type": "missing",
      "input": null
    }
  ]
}
```

> 测试中大量异常场景（缺密码、非法邮箱、超长消息、rating 越界等）实际返回 422，而非 400。本文档已补充该说明。

## 认证接口

### 用户注册

**POST** `/api/auth/register`

注册新用户账户。

**请求体**：

```json
{
  "phone": "13800138000",
  "email": "user@example.com",
  "password": "password123"
}
```

**字段说明**：
- `phone` (可选): 手机号，与 `email` 至少提供一个
- `email` (可选): 邮箱，与 `phone` 至少提供一个
- `password` (必填): 密码，6–100 字符

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Registration successful",
  "data": {
    "id": 1,
    "phone": "13800138000",
    "email": null,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

**常见错误**：
- `422`：`phone` 与 `email` 均未提供、密码短于 6 字符、邮箱格式非法（字段级校验）。
- `400` + `detail.code = VALIDATION_ERROR`：`phone` 已被注册 / `email` 已被注册（业务层校验）。

### 用户登录

**POST** `/api/auth/login`

用户登录获取访问令牌。

**请求体**：

```json
{
  "phone_or_email": "13800138000",
  "password": "password123"
}
```

**字段说明**：
- `phone_or_email` (必填): 手机号或邮箱
- `password` (必填): 密码

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Login successful",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": 1,
      "phone": "13800138000",
      "email": null,
      "created_at": "2024-01-01T00:00:00"
    }
  }
}
```

**常见错误**：
- `401` + `detail.code = AUTH_ERROR`：账号不存在 / 密码错误 / token 无效。
- `422`：`phone_or_email` 或 `password` 缺失。

## 会话接口

所有会话接口需在请求头携带 `Authorization: Bearer <token>`。

### 获取会话列表

**GET** `/api/sessions`

获取当前用户的会话列表，支持分页。

**查询参数**：
- `skip` (可选): 跳过记录数，默认 0（负数会被字段校验拦截返回 422）
- `limit` (可选): 每页记录数，默认 20，最大 100（超过 100 返回 422）

**响应（200，分页结构）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": [
    {
      "id": 1,
      "user_id": 1,
      "title": "产品咨询",
      "intent_tag": "product_consult",
      "msg_count": 5,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T01:00:00"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

**常见错误**：`401` + `detail.code = AUTH_ERROR`（未携带/无效 token）。

### 创建会话

**POST** `/api/sessions`

创建新的对话会话。

**请求体**：

```json
{
  "title": "新对话"
}
```

**字段说明**：
- `title` (可选): 会话标题，最长 255 字符（超出返回 422）

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Session created successfully",
  "data": {
    "id": 2,
    "user_id": 1,
    "title": "新对话",
    "intent_tag": null,
    "msg_count": 0,
    "created_at": "2024-01-01T02:00:00",
    "updated_at": "2024-01-01T02:00:00"
  }
}
```

### 获取会话详情

**GET** `/api/sessions/{session_id}`

获取会话详情及全部消息。

**路径参数**：
- `session_id`: 会话 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": {
    "session": {
      "id": 1,
      "user_id": 1,
      "title": "产品咨询",
      "intent_tag": "product_consult",
      "msg_count": 2,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T01:00:00"
    },
    "messages": [
      {
        "id": 1,
        "session_id": 1,
        "role": "user",
        "content": "产品价格是多少？",
        "intent": null,
        "token_in": 0,
        "token_out": 0,
        "latency_ms": 0,
        "finish_reason": null,
        "created_at": "2024-01-01T00:00:00"
      },
      {
        "id": 2,
        "session_id": 1,
        "role": "assistant",
        "content": "我们的产品基础版价格为¥2,999/月...",
        "intent": null,
        "token_in": 0,
        "token_out": 0,
        "latency_ms": 0,
        "finish_reason": null,
        "created_at": "2024-01-01T00:00:01"
      }
    ]
  }
}
```

> 说明：当前消息对象 **不包含 `citation`（引用）字段**。需求规格要求的历史溯源能力（`MessageCitationResponse`）模型已定义但尚未在会话详情中填充，详见文末「已知差距」。

**常见错误**：`404` + `detail.code = NOT_FOUND`（会话不存在）；`401` + `detail.code = AUTH_ERROR`。

### 更新会话

**PUT** `/api/sessions/{session_id}`

更新会话标题。

**路径参数**：
- `session_id`: 会话 ID

**查询参数**：
- `title` (必填): 新标题，非空且最长 255 字符（缺省或超长返回 422）

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Session updated successfully",
  "data": { }
}
```

### 删除会话

**DELETE** `/api/sessions/{session_id}`

删除会话及其全部消息。

**路径参数**：
- `session_id`: 会话 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Session deleted successfully"
}
```

## 知识库接口

所有知识库接口需在请求头携带 `Authorization: Bearer <token>`。当前系统仅内置一个知识库，`kb_id` 固定为 `"default"`，文档中「多知识库」的表述仅指未来扩展能力。

### 上传文档

**POST** `/api/kb/documents`

上传文档到知识库，处理在后台异步进行；接口立即返回 `processing` 状态。

**请求头**：

```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**请求参数**：
- `file`: 文件对象（multipart/form-data）

**支持格式**：`txt`、`md`、`pdf`

**文件大小限制**：10 MB

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Document uploaded successfully",
  "data": {
    "document_id": 1,
    "status": "processing",
    "message": "Document uploaded and processing started"
  }
}
```

**常见错误**：
- `400` + `detail.code = INVALID_FILE_TYPE`：文件类型不支持（仅 txt/md/pdf）。
- `400` + `detail.code = FILE_TOO_LARGE`：文件超过 10 MB。
- `401` + `detail.code = AUTH_ERROR`：未认证。

### 获取文档列表

**GET** `/api/kb/documents`

获取当前用户知识库中的全部文档（非分页，直接返回数组）。

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": [
    {
      "id": 1,
      "kb_id": "default",
      "name": "产品介绍.md",
      "file_type": "md",
      "size": 1024,
      "char_count": 500,
      "chunk_count": 5,
      "status": "ready",
      "error_msg": null,
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

**文档状态（`status`）**：
- `processing`: 处理中
- `ready`: 就绪
- `failed`: 失败
- `deleting`: 删除中

### 删除文档

**DELETE** `/api/kb/documents/{document_id}`

删除文档及其向量数据。

**路径参数**：
- `document_id`: 文档 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Document deleted successfully"
}
```

**常见错误**：`404` + `detail.code = NOT_FOUND`（文档不存在）；`401` + `detail.code = AUTH_ERROR`。

### 获取文档详情

**GET** `/api/kb/documents/{document_id}`

获取单个知识库文档的元信息（不含向量内容）。

**路径参数**：
- `document_id`: 文档 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": {
    "id": 1,
    "kb_id": "default",
    "name": "产品介绍.md",
    "file_type": "md",
    "size": 1024,
    "char_count": 500,
    "chunk_count": 5,
    "status": "ready",
    "error_msg": null,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

**常见错误**：`404` + `detail.code = NOT_FOUND`（文档不存在）；`401` + `detail.code = AUTH_ERROR`。

### 更新文档

**PUT** `/api/kb/documents/{document_id}`

更新文档名称或重新上传文件内容（重新触发后台向量化）。`name` 与 `file` 至少提供一项，否则返回 `400`。

**请求头**：

```
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**请求参数**：
- `name` (可选): 新文档名，最长 255 字符
- `file` (可选): 新文件（`multipart/form-data`），类型限 `txt/md/pdf`，大小 ≤ 10 MB

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Document updated successfully",
  "data": {
    "id": 1,
    "kb_id": "default",
    "name": "产品介绍（新版）.md",
    "file_type": "md",
    "size": 2048,
    "char_count": 500,
    "chunk_count": 5,
    "status": "processing",
    "error_msg": null,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

> 说明：仅改名时 `status` 保持原值；重新上传文件时 `status` 置为 `processing` 并异步重新向量化。

**常见错误**：
- `400` + `detail.code = VALIDATION_ERROR`：`name` 与 `file` 均未提供。
- `400` + `detail.code = INVALID_FILE_TYPE` / `FILE_TOO_LARGE`：重新上传时文件不合规。
- `404` + `detail.code = NOT_FOUND`（文档不存在）；`401` + `detail.code = AUTH_ERROR`。

## 聊天接口

### 流式聊天

**POST** `/api/chat/stream`

流式聊天接口，使用 SSE（Server-Sent Events）返回响应。需在请求头携带 `Authorization: Bearer <token>`。

**请求头**：

```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体**：

```json
{
  "session_id": 1,
  "message": "产品价格是多少？",
  "kb_id": "default"
}
```

**字段说明**：
- `session_id` (可选): 会话 ID，不提供则创建新会话
- `message` (必填): 用户消息，最多 500 字符（超出返回 422）
- `kb_id` (可选): 知识库 ID，默认 `"default"`

**响应格式**：SSE 流（`Content-Type: text/event-stream`），每个事件以 `data: ` 前缀、空行分隔：

```
data: {"type":"session_id","data":1}

data: {"type":"status","data":"generating"}

data: {"type":"content","data":"我"}

data: {"type":"content","data":"们的"}

...

data: {"type":"done","data":{"message_id":2,"finish_reason":"stop","sources":[{"doc_id":1,"doc_name":"产品介绍.md","chunk_id":"doc_1_chunk_0","score":0.85}]}}
```

**SSE 事件类型**：
- `session_id`: 会话 ID
- `status`: 状态（如 `generating`）
- `content`: 内容片段（逐片推送）
- `done`: 完成，携带 `message_id`、`finish_reason`、`sources`（引用来源）
- `error`: 错误信息

> 关于 SSE 协议与需求规格的增强项（如 `meta` 事件、`suggestion` 追问建议、`citation` 在正文前推送等），当前代码未实现，按用户确认延后处理，详见文末「已知差距」。

**常见错误**：
- `401` + `detail.code = AUTH_ERROR`：未认证。
- `422`：`message` 缺失或超过 500 字符。
- `400` + `detail.code = VALIDATION_ERROR`：会话不存在等业务校验（注：字段长度等由 Pydantic 先拦截为 422）。
- `429` + `detail.code = QUOTA_EXCEEDED`：超出每日提问配额。

### 非流式发送

**POST** `/api/chat/send`

非流式聊天接口：复用与 `/stream` 完全相同的 RAG 管线，但将完整回答作为单个 JSON 对象一次性返回（不逐片推送）。需在请求头携带 `Authorization: Bearer <token>`。

**请求头**：

```
Authorization: Bearer <token>
Content-Type: application/json
```

**请求体**：

```json
{
  "session_id": 1,
  "message": "产品价格是多少？",
  "kb_id": "default"
}
```

**字段说明**（同 `/stream`）：
- `session_id` (可选): 会话 ID，不提供则创建新会话
- `message` (必填): 用户消息，最多 500 字符（超出返回 422）
- `kb_id` (可选): 知识库 ID，默认 `"default"`

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Message sent successfully",
  "data": {
    "session_id": 1,
    "message_id": 2,
    "content": "我们的产品基础版价格为¥2,999/月……",
    "finish_reason": "stop",
    "sources": [
      {"doc_id": 1, "doc_name": "产品介绍.md", "chunk_id": "doc_1_chunk_0", "score": 0.85}
    ]
  }
}
```

**`data` 字段说明**：
- `session_id`: 会话 ID
- `message_id`: 助手消息 ID
- `content`: 完整回答文本
- `finish_reason`: 结束原因（`stop` / `no_context` / `error`）
- `sources`: 引用来源列表（同 `/stream` 的 `done` 事件 `sources`）

**常见错误**：与 `/stream` 一致 —— `401` + `detail.code = AUTH_ERROR`；`422`（`message` 缺失或超长）；`400` + `detail.code = VALIDATION_ERROR`（会话不存在）；`429` + `detail.code = QUOTA_EXCEEDED`（超出每日配额）。

### 获取历史消息

**GET** `/api/chat/history`

获取某会话的历史消息（按时间正序）。会话归属会被校验（仅能读取自己的会话）。

**查询参数**：
- `session_id` (必填): 会话 ID
- `skip` (可选): 跳过记录数，默认 0（负数返回 422）
- `limit` (可选): 返回条数，默认 50，范围 1–200（越界返回 422）

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": [
    {
      "id": 1,
      "session_id": 1,
      "role": "user",
      "content": "产品价格是多少？",
      "intent": null,
      "token_in": 0,
      "token_out": 0,
      "latency_ms": 0,
      "finish_reason": null,
      "created_at": "2024-01-01T00:00:00"
    },
    {
      "id": 2,
      "session_id": 1,
      "role": "assistant",
      "content": "我们的产品基础版价格为¥2,999/月……",
      "intent": null,
      "token_in": 0,
      "token_out": 0,
      "latency_ms": 0,
      "finish_reason": "stop",
      "created_at": "2024-01-01T00:00:01"
    }
  ]
}
```

**常见错误**：`404` + `detail.code = NOT_FOUND`（会话不存在或不属于当前用户）；`401` + `detail.code = AUTH_ERROR`；`422`（`session_id` 缺失 / `skip` 负数 / `limit` 越界）。

## 反馈接口

### 提交反馈

**POST** `/api/feedback`

对 AI 回答提交反馈评价。需在请求头携带 `Authorization: Bearer <token>`。

**请求体**：

```json
{
  "message_id": 2,
  "rating": 1,
  "comment": "回答很有帮助"
}
```

**字段说明**：
- `message_id` (必填): 消息 ID，必须为正整数（`> 0`；填 0 或缺失返回 422）
- `rating` (必填): 评分，**取值 `-1`（点踩）、`0`（中立）、`1`（点赞）**；越界返回 422
- `comment` (可选): 评论，最多 500 字符

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Feedback submitted successfully",
  "data": {
    "id": 1,
    "message_id": 2,
    "user_id": 1,
    "rating": 1,
    "comment": "回答很有帮助",
    "created_at": "2024-01-01T00:00:00"
  }
}
```

**常见错误**：
- `422`：`message_id` 缺失/为 0、`rating` 越界、`comment` 超长等字段级校验。
- `404` + `detail.code = NOT_FOUND`：对应的 `message_id` 不存在（需先用 `/api/chat/stream` 产生真实消息）。
- `400` + `detail.code = VALIDATION_ERROR`：该消息已提交过反馈（重复反馈）。
- `401` + `detail.code = AUTH_ERROR`：未认证。

### 反馈列表

**GET** `/api/feedback`

获取当前用户提交的反馈列表，支持分页与按评分过滤。

**查询参数**：
- `skip` (可选): 跳过记录数，默认 0（负数返回 422）
- `limit` (可选): 每页条数，默认 20，范围 1–100（越界返回 422）
- `rating` (可选): 按评分过滤，`-1`（点踩）/ `0`（中立）/ `1`（点赞）

**响应（200，分页结构）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": [
    {
      "id": 1,
      "message_id": 2,
      "user_id": 1,
      "rating": 1,
      "comment": "回答很有帮助",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

**常见错误**：`401` + `detail.code = AUTH_ERROR`（未认证）。

### 反馈详情

**GET** `/api/feedback/{feedback_id}`

获取单条反馈（按当前用户隔离，无法查看他人反馈）。

**路径参数**：
- `feedback_id`: 反馈 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "data": {
    "id": 1,
    "message_id": 2,
    "user_id": 1,
    "rating": 1,
    "comment": "回答很有帮助",
    "created_at": "2024-01-01T00:00:00"
  }
}
```

**常见错误**：`404` + `detail.code = NOT_FOUND`（反馈不存在或不属于当前用户）；`401` + `detail.code = AUTH_ERROR`。

### 删除反馈

**DELETE** `/api/feedback/{feedback_id}`

删除单条反馈（按当前用户隔离）。

**路径参数**：
- `feedback_id`: 反馈 ID

**响应（200）**：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Feedback deleted successfully"
}
```

**常见错误**：`404` + `detail.code = NOT_FOUND`（反馈不存在或不属于当前用户）；`401` + `detail.code = AUTH_ERROR`。

## 健康检查

**GET** `/health`

无认证，用于探活。

**响应（200）**：

```json
{
  "status": "healthy",
  "app_name": "AI Customer Service System",
  "version": "1.0.0"
}
```

> 注意：该接口**不**使用 `ApiResponse` 信封，直接返回上述原始对象。

## 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| `VALIDATION_ERROR` | 400 / 422 | 参数校验失败（业务层，如消息过长、重复反馈）。注意 pydantic 字段级校验返回 422，无 `code` 字段 |
| `AUTH_ERROR` | 401 | 认证失败（缺失/无效 token、账号不存在、密码错误） |
| `AUTHORIZATION_ERROR` | 403 | 权限不足 |
| `NOT_FOUND` | 404 | 资源不存在（会话/文档/消息等） |
| `QUOTA_EXCEEDED` | 429 | 超出每日提问配额 |
| `INVALID_FILE_TYPE` | 400 | 上传文件类型不支持（仅 txt/md/pdf） |
| `FILE_TOO_LARGE` | 400 | 上传文件超过 10 MB |
| `DOC_PROCESSING_ERROR` | 500 | 文档处理失败 |
| `LLM_ERROR` | 503 | LLM 调用失败 |
| `EMBEDDING_ERROR` | 503 | 向量化失败 |
| `VECTOR_STORE_ERROR` | 503 | 向量库错误 |
| `INTERNAL_ERROR` | 500 | 未预期的内部错误（仅未捕获异常） |

## 业务规则

1. **消息长度限制**：单次消息最多 500 字符
2. **每日配额**：每个用户每日最多 100 次提问（超出返回 `QUOTA_EXCEEDED` / 429）
3. **文件大小限制**：上传文档最大 10 MB
4. **Token 过期时间**：24 小时
5. **相似度阈值**：默认 0.6，低于此值的检索结果会被过滤
6. **Top-K 检索**：默认返回 8 个最相关的文档块
7. **`intent_tag` 字段**：由系统自动标注的可选字符串（如 `product_consult`），非固定枚举；查询/创建时可为 `null`

## 已知差距（未在本轮文档修复中处理）

以下问题属于**功能缺口或后续优化项**，已与用户确认暂不纳入本轮交付，记录于此以便追踪：

> 注：知识库增改（`GET`/`PUT /api/kb/documents/{document_id}`）、反馈列表/详情/删除（`GET`/`GET`/`DELETE /api/feedback[/...]`）、聊天历史（`GET /api/chat/history`）与非流式发送（`POST /api/chat/send`）接口已在正文章节补充，不再属于差距项。

1. **会话消息引用（citation）缺失**：需求要求对话历史可溯源至引用来源，`MessageCitationResponse` 模型已定义但 `GET /api/sessions/{id}` 的 `messages` 未填充 `citation` 字段。
2. **缺 `GET /api/stats/overview` 统计接口**：需求规格（P2，可选）中列出的概览统计接口当前未实现。
3. **SSE 增强事件未实现**：需求 §3.5 要求的 `meta` 事件、`suggestion`（追问建议）事件、以及「引用先于正文」的推送顺序，当前代码未实现；引用来源目前仅在 `done` 事件以 `sources` 形式返回。用户已确认 SSE 测试困难可延后处理。
4. **错误响应格式不统一（可选优化）**：绝大多数业务错误返回 `{"detail":{code,message}}`，而未捕获 500 走 `ApiResponse` 信封。建议后续统一为单一信封结构以降低客户端解析成本。
