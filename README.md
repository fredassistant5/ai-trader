# AI Trader

AI-driven stock/crypto trading system using Alpaca paper trading.

## Setup

1. Create credentials file at `~/.config/alpaca/credentials.json`:
```json
{"api_key": "YOUR_KEY", "secret_key": "YOUR_SECRET", "base_url": "https://paper-api.alpaca.markets"}
```

2. Install dependencies:
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

3. Check account status:
```bash
python scripts/account_status.py
```

## Architecture

- `src/core/` — Alpaca client wrapper, order management
- `src/strategies/` — Trading strategy implementations
- `src/research/` — Market analysis, signal generation
- `src/risk/` — Risk management, position sizing
- `src/data/` — Market data fetching, technical indicators
- `scripts/` — Utility scripts
- `config/` — Configuration templates (no secrets)
