# AGENTS.md

## A. Project Purpose

This repository contains a Python Streamlit personal investment dashboard MVP.
The working project directory is `investment_dashboard/`.

The app provides research-oriented workflows:

- Market data lookup through replaceable data providers
- Watchlist management
- Stock scanner and technical indicators
- DART disclosure collection and classification
- Scoring and AI-comment prompt generation
- Backtesting
- Mock trading through virtual orders only

This project does not provide real trading, real investment advice, or an
automated trading system. It is a development and research MVP, not a financial
advisory product.

## B. Absolute Prohibitions

The following are not allowed without explicit project-owner approval:

- Implementing real order placement
- Calling a real brokerage order API
- Implementing real brokerage account lookup
- Replacing `TossBrokerPlaceholder` with a real `TossBroker`
- Hardcoding API keys, tokens, account numbers, or real trading data
- Committing `.env`, `.venv/`, `db/*.sqlite3`, `db/*.sqlite`, `*.log`, or
  `.streamlit/secrets.toml`
- Writing tests that depend on external APIs, live brokerage services, or real
  credentials

`MockBroker` must remain a virtual broker that records simulated orders only.
`TossBrokerPlaceholder` must remain a placeholder that does not call Toss or any
other brokerage API.

## C. Required Quality Checks

Run all commands from the project directory:

```bash
cd investment_dashboard
pip install -r requirements-dev.txt
python -m compileall .
python -m pytest -vv
ruff check .
black --check .
```

All changes must pass these checks before merge. GitHub Actions runs the same
quality gate on push and pull requests.

## D. Branch Strategy

Work on a separate branch for each feature area. Do not mix unrelated changes.

Example branches:

- `feature/data-provider`
- `feature/dart-risk-scoring`
- `feature/backtest-engine`
- `feature/ui-dashboard`
- `feature/test-coverage`
- `feature/docs`

## E. Multi-Agent Role Separation

### Agent 1: Data Provider

Allowed files:

- `investment_dashboard/src/data_providers/`
- `investment_dashboard/tests/test_data_provider_interface.py`
- `investment_dashboard/tests/test_market_data_provider.py`
- `investment_dashboard/tests/test_sample_provider.py`

Rules:

- Do not modify the broker layer.
- Do not add real order functionality.
- Preserve sample fallback when external data lookup fails.
- Keep quote/history outputs standardized with `data_source`, `provider`, and
  error reporting.

### Agent 2: DART / Disclosure Risk

Allowed files:

- `investment_dashboard/src/dart/`
- `investment_dashboard/src/scoring/`
- `investment_dashboard/tests/test_dart_client.py`
- `investment_dashboard/tests/test_scoring_engine.py`

Rules:

- Keep no-disclosure responses separate from API errors.
- Preserve `SAMPLE_FALLBACK` or equivalent source labeling on fallback data.
- Avoid wording that sounds like investment advice.

### Agent 3: Backtest Engine

Allowed files:

- `investment_dashboard/src/backtest/`
- `investment_dashboard/tests/test_backtest_engine.py`

Rules:

- Prevent look-ahead bias.
- Do not enter new positions on the last bar.
- Preserve fee and slippage handling.
- Do not connect backtests to real orders.

### Agent 4: UI / Streamlit Pages

Allowed files:

- `investment_dashboard/app.py`
- `investment_dashboard/pages/`
- `investment_dashboard/src/ui_helpers.py`

Rules:

- Preserve `SAMPLE`, `REAL_WITH_FALLBACK`, and `FALLBACK MODE` warnings.
- Do not use wording that implies real orders are sent.
- Always describe virtual trading as "모의매매" or "가상 주문".

### Agent 5: Tests / CI / Docs

Allowed files:

- `investment_dashboard/tests/`
- `.github/workflows/`
- `investment_dashboard/README.md`
- `AGENTS.md`
- `investment_dashboard/requirements-dev.txt`

Rules:

- Preserve the CI commands.
- Do not add tests that depend on external APIs.
- Do not hardcode real API keys, tokens, account numbers, or secrets.

## F. Shared File Rules

The following files are high-conflict shared files and should be owned by a
single worker per task:

- `investment_dashboard/src/models.py`
- `investment_dashboard/src/database.py`
- `investment_dashboard/app.py`
- `investment_dashboard/README.md`
- `investment_dashboard/requirements.txt`
- `investment_dashboard/requirements-dev.txt`
- `.github/workflows/ci.yml`

When a shared file must be changed:

- Record why the change is needed.
- Add or update related tests when behavior changes.
- Check for conflicts with other active agent work.
- Keep the edit narrowly scoped.

## G. Completion Report Format

Each agent should report work in this format:

- Working branch
- Changed files
- Core changes
- Added or updated tests
- Validation commands run
- Validation results
- Confirmation that no real order functionality was added
- Remaining limitations
- Suggested next work
