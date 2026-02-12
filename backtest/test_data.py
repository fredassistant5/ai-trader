#!/usr/bin/env python3
"""
Test script to validate market data loading.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add the parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.data.market_data import MarketData

def test_data_loading():
    """Test loading market data for crypto and equity symbols."""
    md = MarketData()
    
    # Test crypto data
    print("Testing crypto data loading...")
    crypto_symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    
    for symbol in crypto_symbols:
        print(f"\nTesting {symbol}:")
        try:
            df = md.get_bars_with_indicators(symbol, timeframe="15Min", limit=10)
            if df is not None and len(df) > 0:
                print(f"  ✓ Loaded {len(df)} bars")
                print(f"  Latest price: ${df['close'].iloc[-1]:.4f}")
                print(f"  Date range: {df.index[0]} to {df.index[-1]}")
                if 'rsi_7' in df.columns:
                    print(f"  Latest RSI: {df['rsi_7'].iloc[-1]:.2f}")
            else:
                print(f"  ✗ No data loaded")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Test equity data  
    print("\n" + "="*50)
    print("Testing equity data loading...")
    equity_symbols = ["SPY", "AAPL", "MSFT"]
    
    for symbol in equity_symbols:
        print(f"\nTesting {symbol}:")
        try:
            df = md.get_bars_with_indicators(symbol, timeframe="5Min", limit=10)
            if df is not None and len(df) > 0:
                print(f"  ✓ Loaded {len(df)} bars")
                print(f"  Latest price: ${df['close'].iloc[-1]:.2f}")
                print(f"  Date range: {df.index[0]} to {df.index[-1]}")
                if 'rsi_7' in df.columns:
                    print(f"  Latest RSI: {df['rsi_7'].iloc[-1]:.2f}")
                if 'bb_lower' in df.columns:
                    print(f"  Latest BB Lower: ${df['bb_lower'].iloc[-1]:.2f}")
            else:
                print(f"  ✗ No data loaded")
        except Exception as e:
            print(f"  ✗ Error: {e}")

if __name__ == "__main__":
    test_data_loading()