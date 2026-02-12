# AI Trader Backtesting Framework

A comprehensive backtesting framework that replays the EXACT same strategies from the live AI Trader against historical data with realistic slippage and commission modeling.

## Features

- **Strategy Reuse**: Imports and runs the actual strategy classes from the live trader (DRY principle)
- **Historical Data**: Uses Alpaca's historical data API for both crypto and equity markets
- **Realistic Simulation**: Includes slippage, commissions, and market impact modeling
- **Comprehensive Metrics**: Calculates Sharpe ratio, max drawdown, win rate, and other key metrics
- **Multiple Output Formats**: Generates text summaries and CSV files for detailed analysis
- **CLI Interface**: Easy-to-use command line interface

## Requirements

- Python 3.8+
- Alpaca API credentials configured in `~/.config/alpaca/credentials.json`
- All dependencies from the main AI trader project

## Installation

The backtesting framework is included as part of the AI trader project. Make sure you have the main project environment activated:

```bash
cd ~/clawd/projects/ai-trader
source venv/bin/activate
```

## Usage

### Basic Usage

```bash
# Backtest crypto mean reversion strategy
python backtest/backtest.py --strategy crypto_mean_reversion --start 2025-01-01 --end 2026-02-01

# Backtest equity mean reversion strategy  
python backtest/backtest.py --strategy equity_mean_reversion --start 2025-06-01 --end 2025-12-31

# Backtest all strategies together
python backtest/backtest.py --strategy all --start 2025-01-01 --end 2026-01-31
```

### Advanced Options

```bash
# Custom initial capital and costs
python backtest/backtest.py \
    --strategy crypto_mean_reversion \
    --start 2025-01-01 \
    --end 2026-02-01 \
    --initial-capital 50000 \
    --commission 0.001 \
    --slippage 0.0005 \
    --output-dir ./my_results

# Verbose logging
python backtest/backtest.py \
    --strategy all \
    --start 2025-01-01 \
    --end 2026-01-31 \
    --verbose
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--strategy` | Strategy to test: `crypto_mean_reversion`, `equity_mean_reversion`, or `all` | Required |
| `--start` | Start date (YYYY-MM-DD) | Required |
| `--end` | End date (YYYY-MM-DD) | Required |
| `--initial-capital` | Initial capital amount | $100,000 |
| `--commission` | Commission rate (as decimal) | 0.005 (0.5%) |
| `--slippage` | Slippage rate (as decimal) | 0.001 (0.1%) |
| `--output-dir` | Output directory for results | `./results/` |
| `--verbose` | Enable verbose logging | False |

## Output Files

The backtester generates several output files in the results directory:

### Single Strategy Results
- `{strategy}_{timestamp}_summary.txt` - Text summary with key metrics
- `{strategy}_{timestamp}_trades.csv` - Detailed trade log
- `{strategy}_{timestamp}_portfolio.csv` - Portfolio value over time

### Combined Strategy Results
- `combined_portfolio_{timestamp}_summary.txt` - Combined portfolio summary
- `combined_portfolio_{timestamp}_trades.csv` - All trades from all strategies

## Strategy Details

### Crypto Mean Reversion
- **Universe**: BTC/USD, ETH/USD, SOL/USD
- **Timeframe**: 15-minute bars
- **Logic**: RSI(7) oversold/overbought with ATR stops
- **Hours**: 24/7 trading
- **Entry**: RSI < 25 (long only in backtest)
- **Exit**: RSI > 45 or ATR-based stop loss

### Equity Mean Reversion  
- **Universe**: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD
- **Timeframe**: 5-minute bars
- **Logic**: Bollinger Bands + RSI oversold
- **Hours**: Market hours only (9:30-16:00 ET)
- **Entry**: Price <= BB lower band AND RSI < 20
- **Exit**: Price >= BB middle band OR RSI > 50 OR ATR-based stop loss

## Key Metrics Explained

- **Total Return**: (Final Value - Initial Capital) / Initial Capital
- **Annualized Return**: Return adjusted to annual basis
- **Sharpe Ratio**: (Annualized Return - Risk Free Rate) / Volatility
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross Profit / Gross Loss
- **Calmar Ratio**: Annualized Return / |Maximum Drawdown|

## Limitations & Notes

1. **Market Impact**: Simplified slippage model may not capture large order impact
2. **Data Quality**: Results depend on quality of Alpaca historical data
3. **Execution**: Perfect fills at specified prices (plus slippage)
4. **Hours**: Exact market hours enforcement may differ from live trading
5. **Fees**: Uses percentage-based commission model vs actual Alpaca fees
6. **Risk Management**: Simplified risk controls vs full live system

## Troubleshooting

### Common Issues

**"No price data available"**
- Check your Alpaca API credentials
- Ensure the date range has market data available
- Try a smaller date range first

**"Insufficient cash"**
- Reduce initial capital or increase it
- Check if commission/slippage rates are too high

**"No data retrieved"**
- Check internet connection
- Verify Alpaca API status
- Ensure symbols exist for the date range

**Import errors**
- Make sure you're in the ai-trader directory
- Activate the virtual environment
- Check that all dependencies are installed

### Performance Tips

- Use shorter date ranges for faster testing
- Start with single strategies before testing 'all'
- Enable verbose mode (`--verbose`) for debugging
- Check the log files for detailed execution info

## Contributing

When modifying the backtesting framework:

1. Maintain compatibility with existing strategy interfaces
2. Add tests for any new functionality
3. Update this README for new features
4. Follow the existing code style and logging patterns

## Support

For issues or questions:
1. Check the log files in `backtest.log`
2. Review the generated reports for clues
3. Ensure your setup matches the main AI trader requirements
4. Verify Alpaca API access and data availability