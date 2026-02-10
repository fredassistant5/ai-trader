"""Alpaca client wrapper. Loads credentials from ~/.config/alpaca/credentials.json"""

import json
import os
from pathlib import Path
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


CREDENTIALS_PATH = Path.home() / ".config" / "alpaca" / "credentials.json"


def load_credentials(path: Path = CREDENTIALS_PATH) -> dict:
    """Load Alpaca API credentials from local config file."""
    if not path.exists():
        raise FileNotFoundError(
            f"Credentials not found at {path}. "
            f"Create it with: {{\"api_key\": \"...\", \"secret_key\": \"...\", \"base_url\": \"...\"}}"
        )
    with open(path) as f:
        creds = json.load(f)
    for key in ("api_key", "secret_key"):
        if key not in creds:
            raise ValueError(f"Missing '{key}' in credentials file")
    return creds


class AlpacaClient:
    """Wrapper around Alpaca Trading API."""

    def __init__(self, credentials_path: Path = CREDENTIALS_PATH):
        creds = load_credentials(credentials_path)
        self.base_url = creds.get("base_url", "https://paper-api.alpaca.markets")
        self.client = TradingClient(
            api_key=creds["api_key"],
            secret_key=creds["secret_key"],
            paper=("paper" in self.base_url),
        )

    def get_account(self):
        """Get account info."""
        return self.client.get_account()

    def get_positions(self):
        """Get all open positions."""
        return self.client.get_all_positions()

    def get_orders(self, status="open"):
        """Get orders by status."""
        from alpaca.trading.requests import GetOrdersRequest
        request = GetOrdersRequest(status=status)
        return self.client.get_orders(filter=request)

    def market_order(self, symbol: str, qty: float, side: str = "buy"):
        """Submit a market order."""
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=request)

    def limit_order(self, symbol: str, qty: float, limit_price: float, side: str = "buy"):
        """Submit a limit order."""
        request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
        )
        return self.client.submit_order(order_data=request)

    def cancel_all_orders(self):
        """Cancel all open orders."""
        return self.client.cancel_orders()

    def close_position(self, symbol: str):
        """Close a position."""
        return self.client.close_position(symbol)

    def close_all_positions(self):
        """Close all positions."""
        return self.client.close_all_positions()
