# AI Trader — SYSTEM.md
**Status:** Phase 1 BUILT — Ready for Code Review  
**Last Updated:** 2026-02-10  
**Account:** Alpaca Paper (~$96K)

## Architecture

```
src/
├── core/client.py           # Alpaca API wrapper (market/limit orders, positions, account)
├── data/market_data.py      # OHLCV bars + indicators (RSI, EMA, BB, VWAP, ADX, ATR, Z-score)
├── risk/
│   ├── manager.py           # Central risk gate (daily/weekly/drawdown breakers, position limits)
│   └── regime.py            # VIX proxy (UVXY) regime detection → size multiplier
├── strategies/
│   ├── crypto_mean_reversion.py  # RSI(7) on 15-min BTC/ETH/SOL — 24/7
│   └── equity_mean_reversion.py  # BB(20,2)+RSI(7)<20 on 5-min large-caps — market hours
└── main.py                  # Main loop: risk→regime→crypto→equity, 60s intervals
scripts/
└── dashboard.py             # Terminal dashboard: equity, P&L, positions, orders
```

## Risk Controls
- 2% daily loss → halt trading
- 5% weekly loss → half size for 3 days
- 10% max drawdown → kill switch
- Max 5% per position, 30% crypto, 15 concurrent positions, 10% cash reserve
- UVXY >5% daily → risk-off (25% position sizes)

## Credentials
- `~/.config/alpaca/credentials.json` (api_key, secret_key, base_url)

## Running
```bash
cd ~/clawd/projects/ai-trader
source venv/bin/activate
python -m src.main           # Start trader
python scripts/dashboard.py  # View account status
```

## NOT Started — awaiting Code Review before first run.
