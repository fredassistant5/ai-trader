#!/usr/bin/env python3
"""Account Dashboard — pretty terminal display of account status."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.client import AlpacaClient


def fmt_money(val) -> str:
    v = float(val)
    color = "\033[92m" if v >= 0 else "\033[91m"
    return f"{color}${v:,.2f}\033[0m"


def fmt_pct(val) -> str:
    v = float(val)
    color = "\033[92m" if v >= 0 else "\033[91m"
    return f"{color}{v:+.2f}%\033[0m"


def main():
    client = AlpacaClient()
    acct = client.get_account()

    equity = float(acct.equity)
    cash = float(acct.cash)
    buying_power = float(acct.buying_power)
    pnl_today = float(acct.equity) - float(acct.last_equity)
    pnl_pct = (pnl_today / float(acct.last_equity) * 100) if float(acct.last_equity) else 0

    print("\n" + "=" * 60)
    print("  🤖  AI TRADER — Account Dashboard")
    print("=" * 60)
    print(f"  Equity:        {fmt_money(equity)}")
    print(f"  Cash:          {fmt_money(cash)}")
    print(f"  Buying Power:  {fmt_money(buying_power)}")
    print(f"  P&L Today:     {fmt_money(pnl_today)}  ({fmt_pct(pnl_pct)})")
    print("-" * 60)

    # Positions
    positions = client.get_positions()
    if positions:
        print(f"\n  📊 Open Positions ({len(positions)})")
        print(f"  {'Symbol':<10} {'Qty':>8} {'Entry':>10} {'Current':>10} {'P&L':>12} {'P&L%':>8}")
        print("  " + "-" * 58)
        for p in positions:
            sym = p.symbol
            qty = float(p.qty)
            entry = float(p.avg_entry_price)
            current = float(p.current_price)
            upl = float(p.unrealized_pl)
            upl_pct = float(p.unrealized_plpc) * 100
            print(f"  {sym:<10} {qty:>8.4f} {entry:>10.2f} {current:>10.2f} {fmt_money(upl):>20} {fmt_pct(upl_pct):>16}")
    else:
        print("\n  📊 No open positions")

    # Orders
    orders = client.get_orders("open")
    if orders:
        print(f"\n  📋 Active Orders ({len(orders)})")
        print(f"  {'Symbol':<10} {'Side':<6} {'Qty':>8} {'Type':<12} {'Status':<10}")
        print("  " + "-" * 46)
        for o in orders:
            print(f"  {o.symbol:<10} {o.side:<6} {o.qty:>8} {o.type:<12} {o.status:<10}")
    else:
        print("\n  📋 No active orders")

    # Recent filled orders
    filled = client.get_orders("closed")
    if filled:
        recent = filled[:10]
        print(f"\n  📜 Recent Trades (last {len(recent)})")
        print(f"  {'Symbol':<10} {'Side':<6} {'Qty':>8} {'Price':>10} {'Time'}")
        print("  " + "-" * 55)
        for o in recent:
            price = o.filled_avg_price or "N/A"
            t = str(o.filled_at or o.submitted_at)[:19]
            print(f"  {o.symbol:<10} {o.side:<6} {o.qty:>8} {str(price):>10} {t}")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
