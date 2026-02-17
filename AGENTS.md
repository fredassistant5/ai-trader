# AI Trader (Fred Trader)

## Overview
Autonomous trading system on Alpaca paper account. Crypto mean reversion (BTC/ETH/SOL 24/7) + Equity mean reversion (10 large caps, market hours).

## Architecture
- `main.py` — Entry point, strategy orchestration
- `strategies/` — Mean reversion strategies (crypto + equity)
- `risk_manager.py` — Thread-safe risk management
- `state/` — Persistent state files for position tracking

## Account
- Alpaca paper trading (~$96K equity)
- Credentials: `~/.config/alpaca/credentials.json`

## Risk Controls
- 2% daily halt, 5% weekly, 10% kill switch
- 30% crypto allocation cap, 10% cash reserve
- Server-side Alpaca stop orders on every position

## Services
- `ai-trader.service` — Main service (enabled, auto-restart)

## Do NOT
- Switch to live/real money trading
- Modify risk limits without explicit instruction
- Hardcode any credentials
- Remove stop-loss logic
