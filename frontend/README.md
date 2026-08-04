# AI 智能客服系统 - 前端 (Frontend)

基于 React + TypeScript + Vite 的智能客服前端，对接后端 REST API，支持流式对话、知识库管理等功能。

## 技术栈 (Tech Stack)

- **框架**: React 18 + TypeScript 5
- **构建工具**: Vite 5
- **路由**: react-router-dom 6
- **UI 组件库**: Ant Design (antd) 5
- **HTTP 客户端**: axios 1.6
- **代码质量**: ESLint 8 + Prettier 3 + TypeScript 严格模式

## 目录结构 (Project Structure)

```
frontend/
├── src/
│   ├── pages/           # 页面组件（Login 登录 / Sessions 会话 / Knowledge 知识库）
│   ├── utils/           # 工具函数（请求封装 request 等）
│   ├── App.tsx          # 应用根组件，路由配置
│   ├── main.tsx         # 入口文件（挂载 React）
│   └── index.css        # 全局样式
├── index.html           # HTML 模板
├── vite.config.ts       # Vite 配置（含开发代理）
├── tsconfig.json        # TypeScript 配置
├── tsconfig.node.json   # 构建用 TS 配置
└── package.json         # 依赖与脚本
```

## 安装 (Setup)

```bash
npm install
```

## 运行 (Running)

开发服务器（默认 http://localhost:5173）：

```bash
npm run dev
```

生产构建：

```bash
npm run build      # 输出到 dist/
npm run preview    # 本地预览构建产物
```

代码检查：

```bash
npm run lint
```

## 接口代理 (API Proxy)

开发模式下，前端通过 Vite 代理将 `/api` 请求转发到后端 `http://localhost:8000`，配置见 `vite.config.ts`（server.proxy）。

## 主要页面

- **登录** (`/login`) - 用户认证
- **会话** (`/sessions`) - 聊天界面，支持流式响应
- **知识库** (`/knowledge`) - 文档管理界面
