# Trader Bot API

A FastAPI-based trading bot API.

## Setup

1. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

### Development Mode (with auto-reload)
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```bash
python main.py
```

Or:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running, you can access:

- **Interactive API docs (Swagger UI):** http://localhost:8000/docs
- **Alternative API docs (ReDoc):** http://localhost:8000/redoc
- **OpenAPI schema:** http://localhost:8000/openapi.json

## Endpoints

- `GET /` - Root endpoint with API information
- `GET /health` - Health check endpoint

## Project Structure

```
trader-bot/
├── main.py              # FastAPI application
├── requirements.txt     # Project dependencies
├── .gitignore          # Git ignore file
├── .python-version     # Python version
└── README.md           # This file
```

## Development

Add new endpoints in `main.py` or create separate route modules in an `app/` directory as your project grows.
