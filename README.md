# Trader Bot - Automated Trading Platform

An automated day/swing trading bot built with FastAPI, PostgreSQL, and Python. Designed for SPY (S&P 500 ETF) trading with minute-level data ingestion and multi-timeframe analysis.

## Features

- **Real-time Data Ingestion**: Polygon.io (Massive) integration for minute-level OHLCV data
- **Multi-Timeframe Analysis**: Automatic aggregations (1min, 5min, 15min, 30min, daily) via materialized views
- **Partitioned Storage**: PostgreSQL native partitioning for efficient time-series data management
- **Pluggable Strategies**: Drop-in strategy framework for easy strategy development
- **Broker Agnostic**: Supports Tastytrade, Tradier, and paper trading
- **Risk Management**: Position sizing, portfolio limits, daily loss limits
- **Backtesting**: Event-driven backtesting engine for strategy validation
- **REST API**: FastAPI-based API with automatic documentation
- **WebSocket Support**: Real-time updates for prices, trades, and signals

## Project Status

**Week 1 Complete** ✓
- ✅ Database setup (PostgreSQL with native partitioning)
- ✅ Project structure
- ✅ Configuration management
- ✅ Database migrations (Alembic)
- ✅ FastAPI application with health endpoints
- ✅ Structured logging

**Next Steps** (Week 2-8)
- Data ingestion from Polygon.io
- Strategy framework
- Risk management & order execution
- Broker integrations
- Backtesting engine
- WebSocket implementation

## Architecture

### Database

- **Primary**: PostgreSQL 18 with native partitioning
- **Partitioning**: Weekly partitions for OHLCV data (optimized for time-series)
- **Indexes**: BRIN indexes for time columns, B-tree for symbol lookups
- **Aggregations**: Materialized views for multi-timeframe data

### Technology Stack

- **FastAPI**: Modern async web framework
- **PostgreSQL**: Time-series optimized with partitioning
- **asyncpg**: Async PostgreSQL driver
- **Alembic**: Database migrations
- **APScheduler**: Background task scheduling
- **Pydantic**: Data validation and settings
- **pandas-ta**: Technical indicators

## Setup

### Prerequisites

- Python 3.13+
- PostgreSQL 18+ (via Postgres.app or Homebrew)
- Polygon.io API key (optional for development)

### Installation

1. **Clone the repository** (if applicable)

2. **Activate virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

## Running the Application

### Development Mode (with auto-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
python app/main.py
```

Or:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once the server is running:

- **Interactive API docs (Swagger UI):** http://localhost:8000/docs
- **Alternative API docs (ReDoc):** http://localhost:8000/redoc
- **Root endpoint:** http://localhost:8000/

## API Endpoints

### Health & Status

- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed component health status

### Coming Soon

- Trading control (start/stop)
- Position management
- Order history
- Signal history
- Strategy management
- Market data queries
- Backtesting

## Database Schema

### Core Tables

- **ohlcv_1min** - Partitioned table for minute-level OHLCV data (with volume)
- **trades** - Executed trades log
- **orders** - Order history
- **positions** - Current and historical positions
- **signals** - Strategy signals
- **strategies** - Strategy configurations
- **account_snapshots** - Daily account snapshots

### Materialized Views

- **ohlcv_5min** - 5-minute aggregated data
- **ohlcv_15min** - 15-minute aggregated data
- **ohlcv_30min** - 30-minute aggregated data
- **ohlcv_daily** - Daily aggregated data

## Database Management

### View Migrations

```bash
# View migration status
alembic current

# View migration history
alembic history

# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision_id>
```

### Create New Migration

```bash
alembic revision -m "description_of_change"
```

## Configuration

Configuration is managed via environment variables in the `.env` file:

- **Database**: PostgreSQL connection settings
- **Polygon.io**: API key and endpoints
- **Broker**: Tastytrade, Tradier, or paper trading
- **Trading**: Risk management parameters
- **Safety**: Enable trading flags

See `.env.example` for all available options.

## Development

### Project Structure

```
trader-bot/
├── app/                    # Application code
│   ├── api/               # REST API endpoints
│   ├── brokers/           # Broker integrations
│   ├── db/                # Database layer
│   ├── models/            # Pydantic models
│   ├── services/          # Business logic
│   ├── strategies/        # Strategy framework
│   ├── tasks/             # Background tasks
│   ├── utils/             # Utilities
│   ├── websockets/        # WebSocket endpoints
│   ├── config.py          # Configuration
│   └── main.py            # FastAPI app
├── alembic/               # Database migrations
├── strategies/            # User strategies
├── tests/                 # Tests
├── scripts/               # Utility scripts
├── .env                   # Environment config
├── requirements.txt       # Dependencies
├── IMPLEMENTATION_PLAN.md # Detailed plan
└── README.md             # This file
```

### Adding Strategies

Strategies will be loaded from the `strategies/` directory. Create a Python file implementing the `Strategy` base class (coming in Week 3).

### Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=app --cov-report=html
```

## Deployment

### Local Development

The application is designed to run locally with zero cloud costs:

- PostgreSQL on local machine
- FastAPI server on localhost
- Can execute live trades during market hours

### Cloud Deployment (Future)

When strategies prove profitable, deploy to:

- **GCP Cloud Run**: Serverless FastAPI hosting
- **Timescale Cloud**: Managed TimescaleDB (~$48/month)
- **OR**: GCP Compute Engine with self-hosted PostgreSQL (~$67/month)

## Safety Features

- **Double Enable Flags**: Both `ENABLE_TRADING` and `ENABLE_LIVE_TRADING` must be true
- **Paper Trading Default**: Always defaults to paper broker
- **Daily Loss Limits**: Automatic halt on excessive losses
- **Position Size Limits**: Prevent over-concentration
- **End-of-Day Closure**: Mandatory position closure for day trading

## Documentation

- **Implementation Plan**: See `IMPLEMENTATION_PLAN.md` for detailed architecture and roadmap
- **API Docs**: Available at `/docs` when server is running
- **Database Schema**: See Alembic migrations in `alembic/versions/`

## License

[Add your license here]

## Support

For questions or issues, please refer to the `IMPLEMENTATION_PLAN.md` or open an issue.

---

**Version**: 1.0.0 (Week 1 Complete)
**Last Updated**: 2025-11-06
