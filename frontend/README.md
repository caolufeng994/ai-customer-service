# AI Customer Service System - Frontend

React + TypeScript + Vite frontend for AI customer service system.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start development server:
```bash
npm run dev
```

3. Build for production:
```bash
npm run build
```

## Project Structure

```
frontend/
├── src/
│   ├── pages/        # Page components (Login, Sessions, KnowledgeBase)
│   ├── utils/        # Utilities (request, etc.)
│   ├── App.tsx       # Main app component with routing
│   ├── main.tsx      # Entry point
│   └── index.css     # Global styles
├── index.html        # HTML template
├── package.json      # Dependencies
├── vite.config.ts    # Vite configuration
└── tsconfig.json     # TypeScript configuration
```

## Pages

- **Login** (`/login`) - User authentication
- **Sessions** (`/sessions`) - Chat interface with streaming responses
- **Knowledge Base** (`/knowledge`) - Document management interface

## API Configuration

The frontend proxies API requests to the backend at `http://localhost:8000`. This is configured in `vite.config.ts`.

## Development

The development server runs on `http://localhost:5173`.
