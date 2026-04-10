# Kronos Trader — Completion & Launch Plan

## Current State
The project is **~95% built** with a complete, production-grade codebase:
- 6 packages (shared, alpaca_client, kronos_model, signal_engine, agent, execution)
- Full dashboard with dark theme, P&L charts, risk bars, kill switch, predictions vs actuals, signal table, trade history, audit log
- Docker infrastructure (docker-compose with postgres, execution, agent)
- Comprehensive risk management (position limits, daily loss, concentration, crypto allocation, kill switch)
- Unit tests for core business logic (edge, confidence, sizing, ensemble)

## What Needs To Be Done

### Phase 1: Get It Running Locally (this session)

**Step 1 — Install dependencies**
- Run `uv sync` in the project root to install all workspace packages
- Verify the virtual environment is set up correctly

**Step 2 — Generate database migrations**
- Alembic framework is configured but has no migration versions
- Run `alembic revision --autogenerate -m "Initial schema"` to generate from SQLAlchemy models
- Review and apply: `alembic upgrade head`

**Step 3 — Start services with Docker Compose**
- `docker compose up -d postgres` — start the database
- Apply migrations against the containerized postgres
- `docker compose up execution` — start execution service
- Verify dashboard loads at http://localhost:8001
- Verify API health at http://localhost:8001/api/v1/health

**Step 4 — Validate Alpaca connection**
- Write a quick smoke test that uses the paper trading credentials from .env
- Verify: account info, historical bars fetch, position listing
- Confirm the IEX data feed works for the instrument universe (crypto + ETFs + small-caps)

**Step 5 — Test Kronos model loading**
- The .env specifies `KRONOS_DEVICE=cuda` but we're developing locally
- For local dev: temporarily set to `cpu` (or `mps` on Apple Silicon)
- Test loading `NeoQuasar/Kronos-small` from HuggingFace Hub
- Run a single prediction on sample OHLCV data to verify the pipeline works end-to-end

**Step 6 — End-to-end smoke test**
- Start agent service
- Trigger one manual pipeline cycle
- Verify: data fetch → Kronos prediction → signal generation → trade submission (paper) → dashboard update
- Fix any integration bugs discovered

### Phase 2: Polish & Harden (follow-up)

- Add integration tests for execution service routes
- Add E2E test using Alpaca paper trading
- Complete `evaluate_predictions()` stub in pipeline
- Position sync scheduling in agent
- AWS CDK infrastructure (ECS + RDS + GPU instance for Kronos)
- Monitoring & alerting

## Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                    AGENT SERVICE                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │Scheduler │→ │ Pipeline │→ │ Execution Client │───┤──→ Execution Service
│  │(APSched) │  │ (daily + │  │   (HTTP client)  │   │
│  └──────────┘  │ intraday │  └──────────────────┘   │
│                │ + crypto) │                         │
│                └──┬───┬───┘                         │
│                   │   │                              │
│        ┌──────────┘   └──────────┐                  │
│        ▼                         ▼                  │
│  ┌──────────┐             ┌──────────┐              │
│  │  Alpaca  │             │  Kronos  │              │
│  │Data Fetch│             │Predictor │              │
│  │(OHLCV)  │             │(Ensemble)│              │
│  └──────────┘             └──────────┘              │
│        │                         │                  │
│        └──────────┐   ┌──────────┘                  │
│                   ▼   ▼                             │
│              ┌──────────┐                           │
│              │  Signal   │                           │
│              │  Engine   │                           │
│              │(edge+conf)│                           │
│              └──────────┘                           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│               EXECUTION SERVICE (FastAPI)            │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐    │
│  │Dashboard │  │ Risk Mgr │  │Trade Executor  │    │
│  │(Jinja2 + │  │(limits,  │  │(Alpaca orders) │    │
│  │Chart.js) │  │kill sw.) │  └────────────────┘    │
│  └──────────┘  └──────────┘                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐    │
│  │Prediction│  │Position  │  │ Audit Logger   │    │
│  │Tracker   │  │Tracker   │  │                │    │
│  └──────────┘  └──────────┘  └────────────────┘    │
│                    │                                 │
│              ┌─────▼─────┐                          │
│              │ PostgreSQL │                          │
│              │  (async)   │                          │
│              └───────────┘                          │
└─────────────────────────────────────────────────────┘
```

## Instruments Universe

| Category | Symbols | Rationale |
|----------|---------|-----------|
| Crypto | BTC/USD, ETH/USD | 24/7, volatile, less efficient |
| Commodity ETFs | GLD, SLV, USO, DBA | Indirect commodity exposure via Alpaca |
| Bond ETFs | TLT, IEF, HYG, LQD | Interest rate / credit plays |
| Small-caps | Dynamically screened from Alpaca | Less analyst coverage |

## Risk Limits (from .env, conservative paper-trading defaults)

| Limit | Value |
|-------|-------|
| Max position exposure | $1,000 |
| Max daily loss | $200 |
| Max single trade | $500 |
| Max trades/hour | 50 |
| Max crypto allocation | 30% |
| Max single-symbol concentration | 25% |
