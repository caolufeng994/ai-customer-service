# AI Customer Service System - Backend

FastAPI-based backend for AI-powered customer service with RAG capabilities.

## Setup

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Initialize database:
```bash
mysql -u root -p < init_db.sql
```

## Running

Development mode:
```bash
python -m app.main
```

Or using uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
backend/
├── app/
│   ├── api/           # API route handlers
│   ├── core/          # Core utilities (logging, exceptions, response)
│   ├── models/        # SQLAlchemy models
│   ├── schemas/       # Pydantic schemas
│   ├── services/      # Business logic layer
│   ├── rag/           # RAG core modules
│   └── main.py        # Application entry point
├── init_db.sql        # Database initialization script
├── requirements.txt   # Python dependencies
└── .env.example       # Environment configuration template
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Health Check

```bash
curl http://localhost:8000/health
```
