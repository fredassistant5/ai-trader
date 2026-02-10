"""Equity Mean Reversion Strategy — BB + RSI on liquid large-caps during market hours."""

import logging
from datetime import datetime
from typing import Optional
import pytz

logger = logging.getLogger("strategy.equity_mr")

UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]
TIMEFRAME = "5Min"
RSI_ENTRY = 20
RSI_EXIT = 50
MAX_POSITION_PCT = 0.05
ATR_STOP_MULT = 1.5
ET = pytz.timezone("US/Eastern")


def is_market_hours() -> bool:
    """Check if US equity markets are open (9:30-16:00 ET)."""
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:  # Saturday/Sunday
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


class EquityMeanReversion:
    """Bollinger Bands(20,2) + RSI(7) < 20 mean reversion on 5-min bars."""

    def __init__(self, client, market_data, risk_manager):
        self.client = client
        self.data = market_data
        self.risk = risk_manager
        self.active_trades: dict[str, dict] = {}

    def run(self) -> list[dict]:
        """Evaluate all equity symbols. Only runs during market hours."""
        if not is_market_hours():
            return []

        actions = []
        for symbol in UNIVERSE:
            try:
                action = self._evaluate(symbol)
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")
        return actions

    def _evaluate(self, symbol: str) -> Optional[dict]:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=50)
        if df is None or len(df) < 25:
            return None

        latest = df.iloc[-1]
        price = latest["close"]
        rsi = latest.get("rsi_7")
        bb_lower = latest.get("bb_lower")
        bb_middle = latest.get("bb_middle")
        atr = latest.get("atr_14")

        if any(v is None for v in [rsi, bb_lower, bb_middle, atr]):
            return None

        # Check existing position
        positions = self.client.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)

        # EXIT LOGIC
        if pos is not None:
            qty = float(pos.qty)
            if qty <= 0:
                return None

            # Check stop
            if symbol in self.active_trades:
                stop = self.active_trades[symbol].get("stop_price")
                if stop and price <= stop:
                    logger.info(f"STOP HIT {symbol} @ {price:.2f} (stop={stop:.2f})")
                    self.client.close_position(symbol)
                    del self.active_trades[symbol]
                    return {"action": "stop_exit", "symbol": symbol, "price": price}

            # Exit: price hits BB midline OR RSI > 50
            if price >= bb_middle or rsi >= RSI_EXIT:
                reason = f"bb_mid={bb_middle:.2f}" if price >= bb_middle else f"rsi={rsi:.1f}"
                logger.info(f"EXIT LONG {symbol}: {reason}")
                self.client.close_position(symbol)
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                return {"action": "exit_long", "symbol": symbol, "price": price, "reason": reason}

            return None

        # ENTRY LOGIC: price at/below lower BB AND RSI < 20
        if price <= bb_lower and rsi < RSI_ENTRY:
            return self._enter(symbol, price, atr)

        return None

    def _enter(self, symbol: str, price: float, atr: float) -> Optional[dict]:
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
        except Exception:
            return None

        notional = MAX_POSITION_PCT * equity * self.risk.get_size_multiplier()

        allowed, reason = self.risk.pre_trade_check(symbol, notional, "buy")
        if not allowed:
            logger.info(f"RISK BLOCKED buy {symbol}: {reason}")
            return None

        qty = int(notional / price)
        if qty <= 0:
            return None

        stop_price = price - (ATR_STOP_MULT * atr)

        logger.info(
            f"ENTER LONG {symbol}: qty={qty}, price={price:.2f}, "
            f"stop={stop_price:.2f}, RSI={self._get_rsi(symbol):.1f}, BB_lower={price:.2f}"
        )

        try:
            self.client.market_order(symbol, qty, "buy")
            self.active_trades[symbol] = {
                "side": "buy",
                "entry_price": price,
                "stop_price": stop_price,
                "qty": qty,
                "time": datetime.utcnow().isoformat(),
            }
            return {"action": "enter_long", "symbol": symbol, "qty": qty, "price": price}
        except Exception as e:
            logger.error(f"Order failed buy {symbol}: {e}")
            return None

    def _get_rsi(self, symbol: str) -> float:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=20)
        if df is not None and "rsi_7" in df.columns:
            return df["rsi_7"].iloc[-1]
        return 50.0
