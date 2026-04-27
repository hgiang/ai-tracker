# AI Tracker

Personal AI news aggregator built with Python and FastAPI. Collects daily AI news about LLMs, deep learning, and agentic AI from multiple sources.

## Sources

- Hacker News (top stories)
- Reddit (r/MachineLearning, r/LocalLLaMA)
- arXiv (cs.AI, cs.CL)
- GitHub (trending AI repos)
- RSS feeds (OpenAI, Anthropic, Google AI, Hugging Face blogs)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # edit with your API keys
```

## Run

```bash
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/sources` | List all sources |
| POST | `/api/sources/sync` | Sync all enabled sources |
| POST | `/api/sources/sync/{slug}` | Sync a single source |
| GET | `/api/items` | List items (supports `page`, `limit`, `content_type`, `source_id`, `min_score`, `q`) |
| GET | `/api/items/{id}` | Get item detail |
| GET | `/api/digests/latest` | Get latest digest |
| POST | `/api/digests/generate` | Generate today's digest |
| POST | `/api/digests/cleanup` | Delete expired items |

## Tests

```bash
pytest -v
pytest --cov=app --cov-report=term-missing
```

## Architecture

```
app/
├── adapters/     # One adapter per source (fetch + normalize only)
├── models/       # SQLAlchemy models (sources, items, digests)
├── routes/       # FastAPI route handlers
├── schemas/      # Pydantic request/response schemas
├── services/     # Business logic (ingestion, dedup, retention, digest)
├── config.py     # Settings from environment
├── database.py   # Async SQLAlchemy engine
└── main.py       # FastAPI app with lifespan
```
