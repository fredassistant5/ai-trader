"""Alpaca client wrapper. Loads credentials from ~/.config/alpaca/credentials.json"""

import json
import logging
import time
from pathlib import Path
from functools import wraps
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logger = logging.getLogger("client")

CREDENTIALS_PATH = Path.home() / ".config" / "alpaca" / "credentials.json"

CRYPTO_SYMBOLS = {"BTC/USD", "ETH/USD", "SOL/USD", "BTCUSD", "ETHUSD", "SOLUSD"}


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


def _is_crypto_symbol(symbol: str) -> bool:
    """Check if a symbol is a crypto pair."""
    clean = symbol.replace("/", "")
    return clean in {s.replace("/", "") for s in CRYPTO_SYMBOLS}


def api_retry(max_retries=3, base_delay=1.0):
    """Exponential backoff decorator for API calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    err_str = str(e)
                    # Rate limit or transient errors — retry
                    if attempt < max_retries and ("429" in err_str or "rate" in err_str.lower()
                            or "503" in err_str or "timeout" in err_str.lower()):
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"API call {func.__name__} failed (attempt {attempt+1}): {e}. "
                                       f"Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        raise
            raise last_exc
        return wrapper
    return decorator


class AlpacaClient:
    """Wrapper around Alpaca Trading API with retry logic."""

    def __init__(self, credentials_path: Path = CREDENTIALS_PATH):
        creds = load_credentials(credentials_path)
        self.base_url = creds.get("base_url", "https://paper-api.alpaca.markets")
        self.client = TradingClient(
            api_key=creds["api_key"],
            secret_key=creds["secret_key"],
            paper=("paper" in self.base_url),
        )

    @api_retry()
    def get_account(self):
        """Get account info."""
        return self.client.get_account()

    @api_retry()
    def get_positions(self):
        """Get all open positions."""
        return self.client.get_all_positions()

    @api_retry()
    def get_orders(self, status="open"):
        """Get orders by status."""
        from alpaca.trading.requests import GetOrdersRequest
        request = GetOrdersRequest(status=status)
        return self.client.get_orders(filter=request)

    @api_retry()
    def get_order_by_id(self, order_id: str):
        """Get a specific order by ID."""
        return self.client.get_order_by_id(order_id)

    @api_retry()
    def market_order(self, symbol: str, qty: float, side: str = "buy",
                     time_in_force: TimeInForce = None):
        """Submit a market order. Auto-selects GTC for crypto, DAY for equities."""
        if time_in_force is None:
            time_in_force = TimeInForce.GTC if _is_crypto_symbol(symbol) else TimeInForce.DAY
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=time_in_force,
        )
        return self.client.submit_order(order_data=request)

    @api_retry()
    def stop_order(self, symbol: str, qty: float, stop_price: float,
                   side: str = "sell", time_in_force: TimeInForce = None):
        """Submit a stop order (server-side stop loss). Auto-selects GTC for crypto."""
        if time_in_force is None:
            time_in_force = TimeInForce.GTC if _is_crypto_symbol(symbol) else TimeInForce.DAY
        request = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=time_in_force,
            stop_price=round(stop_price, 2),
        )
        return self.client.submit_order(order_data=request)

    @api_retry()
    def limit_order(self, symbol: str, qty: float, limit_price: float, side: str = "buy",
                    time_in_force: TimeInForce = None):
        """Submit a limit order."""
        if time_in_force is None:
            time_in_force = TimeInForce.GTC if _is_crypto_symbol(symbol) else TimeInForce.DAY
        request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=time_in_force,
            limit_price=limit_price,
        )
        return self.client.submit_order(order_data=request)

    @api_retry()
    def cancel_order(self, order_id: str):
        """Cancel a specific order."""
        return self.client.cancel_order_by_id(order_id)

    @api_retry()
    def cancel_all_orders(self):
        """Cancel all open orders."""
        return self.client.cancel_orders()

    @api_retry()
    def close_position(self, symbol: str):
        """Close a position."""
        return self.client.close_position(symbol)

    @api_retry()
    def close_all_positions(self):
        """Close all positions."""
        return self.client.close_all_positions()
