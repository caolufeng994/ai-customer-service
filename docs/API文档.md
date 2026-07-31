# API 文档

## 概述

AI智能客服系统提供RESTful API接口，支持用户认证、会话管理、知识库管理、流式聊天和反馈评价等功能。

**Base URL**: `http://localhost:8000/api`

**认证方式**: JWT Bearer Token

## 通用响应格式

所有API响应遵循统一格式：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**错误响应格式**：

```json
{
  "code": "ERROR_CODE",
  "message": "Error message description"
}
```

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
- `phone` (可选): 手机号，与email至少提供一个
- `email` (可选): 邮箱，与phone至少提供一个
- `password` (必填): 密码，6-100字符

**响应**：

```json
{
  "code": 0,
  "message": "Registration successful",
  "data": {
    "id": 1,
    "phone": "13800138000",
    "email": null,
    "created_at": "2024-01-01T00:00:00"
  }
}
```

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

**响应**：

```json
{
  "code": 0,
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

## 会话接口

### 获取会话列表

**GET** `/api/sessions`

获取当前用户的会话列表，支持分页。

**请求头**：
```
Authorization: Bearer {token}
```

**查询参数**：
- `skip` (可选): 跳过记录数，默认0
- `limit` (可选): 每页记录数，默认20，最大100

**响应**：

```json
{
  "code": 0,
  "data": {
    "items": [
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
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 创建会话

**POST** `/api/sessions`

创建新的对话会话。

**请求头**：
```
Authorization: Bearer {token}
```

**请求体**：

```json
{
  "title": "新对话"
}
```

**响应**：

```json
{
  "code": 0,
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

获取会话详情及所有消息。

**请求头**：
```
Authorization: Bearer {token}
```

**路径参数**：
- `session_id`: 会话ID

**响应**：

```json
{
  "code": 0,
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

### 更新会话

**PUT** `/api/sessions/{session_id}`

更新会话标题。

**请求头**：
```
Authorization: Bearer {token}
```

**路径参数**：
- `session_id`: 会话ID

**查询参数**：
- `title`: 新标题

**响应**：

```json
{
  "code": 0,
  "message": "Session updated successfully",
  "data": { ... }
}
```

### 删除会话

**DELETE** `/api/sessions/{session_id}`

删除会话及其所有消息。

**请求头**：
```
Authorization: Bearer {token}
```

**路径参数**：
- `session_id`: 会话ID

**响应**：

```json
{
  "code": 0,
  "message": "Session deleted successfully"
}
```

## 知识库接口

### 上传文档

**POST** `/api/kb/documents`

上传文档到知识库，支持异步处理。

**请求头**：
```
Authorization: Bearer {token}
Content-Type: multipart/form-data
```

**请求参数**：
- `file`: 文件对象（multipart/form-data）

**支持格式**：txt, md, pdf

**文件大小限制**：10MB

**响应**：

```json
{
  "code": 0,
  "message": "Document uploaded successfully",
  "data": {
    "document_id": 1,
    "status": "processing",
    "message": "Document uploaded and processing started"
  }
}
```

### 获取文档列表

**GET** `/api/kb/documents`

获取知识库中的所有文档。

**请求头**：
```
Authorization: Bearer {token}
```

**响应**：

```json
{
  "code": 0,
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

**文档状态**：
- `processing`: 处理中
- `ready`: 就绪
- `failed`: 失败
- `deleting`: 删除中

### 删除文档

**DELETE** `/api/kb/documents/{document_id}`

删除文档及其向量数据。

**请求头**：
```
Authorization: Bearer {token}
```

**路径参数**：
- `document_id`: 文档ID

**响应**：

```json
{
  "code": 0,
  "message": "Document deleted successfully"
}
```

## 聊天接口

### 流式聊天

**POST** `/api/chat/stream`

流式聊天接口，使用SSE（Server-Sent Events）返回响应。

**请求头**：
```
Authorization: Bearer {token}
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
- `session_id` (可选): 会话ID，不提供则创建新会话
- `message` (必填): 用户消息，最多500字符
- `kb_id` (可选): 知识库ID，默认"default"

**响应格式**：SSE流

```
data: {"type":"session_id","data":1}

data: {"type":"status","data":"generating"}

data: {"type":"content","data":"我"}

data: {"type":"content","data":"们的"}

data: {"type":"content","data":"产品"}

...

data: {"type":"done","data":{"message_id":2,"finish_reason":"stop","sources":[{"doc_id":1,"doc_name":"产品介绍.md","chunk_id":"doc_1_chunk_0","score":0.85}]}}
```

**SSE事件类型**：
- `session_id`: 会话ID
- `status`: 状态（generating）
- `content`: 内容片段
- `done`: 完成（包含message_id、finish_reason、sources）
- `error`: 错误信息

## 反馈接口

### 提交反馈

**POST** `/api/feedback`

对AI回答提交反馈评价。

**请求头**：
```
Authorization: Bearer {token}
```

**请求体**：

```json
{
  "message_id": 2,
  "rating": 1,
  "comment": "回答很有帮助"
}
```

**字段说明**：
- `message_id` (必填): 消息ID
- `rating` (必填): 评分（1点赞，-1点踩）
- `comment` (可选): 评论，最多500字符

**响应**：

```json
{
  "code": 0,
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

## 错误码

| 错误码 | 说明 |
|--------|------|
| `VALIDATION_ERROR` | 请求参数验证失败 |
| `AUTHENTICATION_ERROR` | 认证失败 |
| `NOT_FOUND` | 资源不存在 |
| `QUOTA_EXCEEDED` | 配额超限 |
| `DOCUMENT_PROCESSING_ERROR` | 文档处理错误 |
| `LLM_ERROR` | LLM调用错误 |
| `EMBEDDING_ERROR` | 向量化错误 |
| `INTERNAL_ERROR` | 内部服务器错误 |

## 业务规则

1. **消息长度限制**：单次消息最多500字符
2. **每日配额**：每个用户每日最多100次提问
3. **文件大小限制**：上传文档最大10MB
4. **Token过期时间**：24小时
5. **相似度阈值**：默认0.6，低于此值的检索结果会被过滤
6. **Top-K检索**：默认返回8个最相关的文档块
