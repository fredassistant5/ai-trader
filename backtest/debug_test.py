#!/usr/bin/env python3
"""
Debug test to understand why the backtester isn't generating trades.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add the parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from mock_data import MockMarketData
from mock_client import MockAlpacaClient  
from mock_risk import MockRiskManager
from mock_state import MockStateManager
from src.strategies.crypto_mean_reversion import CryptoMeanReversion

def debug_backtest():
    """Debug the backtesting process step by step."""
    
    print("=== DEBUGGING BACKTEST PROCESS ===\n")
    
    # Test dates where we know we have data (from test_data.py output)
    start_date = datetime(2025, 4, 19)
    end_date = datetime(2025, 4, 20)  # Just 1 day for debugging
    
    print(f"Testing date range: {start_date} to {end_date}\n")
    
    # Initialize mock components
    mock_client = MockAlpacaClient(10000, 0.005, 0.001)
    mock_data = MockMarketData()
    mock_risk = MockRiskManager()
    mock_state = MockStateManager()
    
    # Wire them together
    mock_data.set_mock_client(mock_client)
    
    print("1. Setting up mock data...")
    mock_data.set_date_range(start_date, end_date)
    
    print("2. Testing data loading for crypto symbols...")
    symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
    
    for symbol in symbols:
        print(f"\n   Testing {symbol}:")
        # Set current time to middle of range
        test_time = start_date + timedelta(hours=12)
        mock_data.set_current_time(test_time)
        
        # Try to get data
        df = mock_data.get_bars_with_indicators(symbol, "15Min", 50)
        if df is not None and len(df) > 0:
            print(f"     ✓ Got {len(df)} bars")
            print(f"     Latest close: ${df['close'].iloc[-1]:.4f}")
            if 'rsi_7' in df.columns:
                rsi = df['rsi_7'].iloc[-1]
                print(f"     Latest RSI: {rsi:.2f}")
                if rsi < 30:
                    print(f"     🔥 RSI signals BUY (< 30)")
                elif rsi > 70:
                    print(f"     📈 RSI high (> 70)")
            else:
                print(f"     ⚠ No RSI data")
        else:
            print(f"     ✗ No data available")
    
    print("\n3. Testing strategy initialization...")
    try:
        strategy = CryptoMeanReversion(
            client=mock_client,
            market_data=mock_data,
            risk_manager=mock_risk,
            state_manager=mock_state
        )
        print("   ✓ Strategy initialized successfully")
    except Exception as e:
        print(f"   ✗ Strategy initialization failed: {e}")
        return
    
    print("\n4. Testing strategy evaluation...")
    
    # Set a specific time and test strategy
    test_time = start_date + timedelta(hours=12)
    mock_data.set_current_time(test_time)
    mock_client.update_time(test_time)
    
    try:
        actions = strategy.run()
        print(f"   Strategy returned {len(actions)} actions")
        for action in actions:
            print(f"     Action: {action}")
    except Exception as e:
        print(f"   ✗ Strategy evaluation failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n5. Testing manual data request...")
    test_time = start_date + timedelta(hours=12)
    mock_data.set_current_time(test_time)
    
    for symbol in ["BTC/USD"]:
        try:
            df = mock_data.get_bars_with_indicators(symbol, "15Min", 50)
            if df is not None and len(df) > 0:
                print(f"   {symbol}: {len(df)} bars, latest RSI: {df['rsi_7'].iloc[-1]:.2f}")
                
                # Check if conditions would trigger entry
                rsi = df['rsi_7'].iloc[-1]
                price = df['close'].iloc[-1]
                print(f"   Entry check: RSI={rsi:.2f} (target: <25), Price=${price:.2f}")
                
                if rsi < 25:
                    print(f"   🔥 Would trigger BUY signal!")
                else:
                    print(f"   📊 No signal (RSI not low enough)")
            else:
                print(f"   {symbol}: No data available")
        except Exception as e:
            print(f"   {symbol}: Error - {e}")

if __name__ == "__main__":
    debug_backtest()