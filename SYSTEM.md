# SYSTEM.md — AI Trader

## Project
AI Trader — Pure AI-driven stock/crypto trading via Alpaca paper trading.

## Account
- **Type:** Paper trading
- **Balance:** ~$96K
- **Broker:** Alpaca Markets

## Credentials
- **Location:** `~/.config/alpaca/credentials.json`
- **Format:** `{"api_key": "...", "secret_key": "...", "base_url": "https://paper-api.alpaca.markets"}`
- **NEVER in git.** Loaded at runtime only.

## Architecture
```
src/
  core/        — Alpaca client wrapper, order management
  strategies/  — Trading strategy implementations
  research/    — Market analysis, signal generation
  risk/        — Risk management, position sizing
  data/        — Market data fetching, technical indicators
scripts/       — Utility scripts (account status, etc.)
config/        — Config templates (no secrets)
tests/         — Test files
logs/          — Runtime logs (gitignored)
```

## Key Design Decisions
- All credentials loaded from `~/.config/alpaca/credentials.json`
- Paper trading only until strategies are validated
- Modular strategy system — each strategy is a separate module
- Risk management is mandatory before any order execution

## Status
- **2026-02-10:** Initial project setup, repo created
