#!/usr/bin/env python3
"""Show Alpaca account status: balance, positions, and open orders."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.client import AlpacaClient


def main():
    client = AlpacaClient()
    
    # Account info
    account = client.get_account()
    print("=" * 60)
    print("ACCOUNT STATUS")
    print("=" * 60)
    print(f"  Equity:          ${float(account.equity):>12,.2f}")
    print(f"  Cash:            ${float(account.cash):>12,.2f}")
    print(f"  Buying Power:    ${float(account.buying_power):>12,.2f}")
    print(f"  Portfolio Value:  ${float(account.portfolio_value):>12,.2f}")
    print(f"  Day P&L:         ${float(account.equity) - float(account.last_equity):>12,.2f}")
    print(f"  Status:          {account.status}")
    print(f"  Paper:           {account.account_number}")
    
    # Positions
    positions = client.get_positions()
    print(f"\n{'=' * 60}")
    print(f"POSITIONS ({len(positions)})")
    print("=" * 60)
    if positions:
        print(f"  {'Symbol':<10} {'Qty':>8} {'Avg Entry':>12} {'Current':>12} {'P&L':>12} {'P&L %':>8}")
        print(f"  {'-'*10} {'-'*8} {'-'*12} {'-'*12} {'-'*12} {'-'*8}")
        for p in positions:
            pnl = float(p.unrealized_pl)
            pnl_pct = float(p.unrealized_plpc) * 100
            print(f"  {p.symbol:<10} {float(p.qty):>8.2f} ${float(p.avg_entry_price):>11,.2f} ${float(p.current_price):>11,.2f} ${pnl:>11,.2f} {pnl_pct:>7.2f}%")
    else:
        print("  No open positions.")
    
    # Orders
    orders = client.get_orders("open")
    print(f"\n{'=' * 60}")
    print(f"OPEN ORDERS ({len(orders)})")
    print("=" * 60)
    if orders:
        print(f"  {'Symbol':<10} {'Side':<6} {'Type':<8} {'Qty':>8} {'Status':<12}")
        print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*12}")
        for o in orders:
            print(f"  {o.symbol:<10} {o.side:<6} {o.type:<8} {float(o.qty):>8.2f} {o.status:<12}")
    else:
        print("  No open orders.")
    
    print()


if __name__ == "__main__":
    main()
