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
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


class EquityMeanReversion:
    """Bollinger Bands(20,2) + RSI(7) < 20 mean reversion on 5-min bars."""

    def __init__(self, client, market_data, risk_manager, state_manager=None):
        self.client = client
        self.data = market_data
        self.risk = risk_manager
        self.state_mgr = state_manager
        self.active_trades: dict[str, dict] = {}

    def load_state(self, trades: dict):
        """Load persisted active_trades."""
        self.active_trades = trades

    def run(self, positions_cache: list = None) -> list[dict]:
        """Evaluate all equity symbols. Only runs during market hours."""
        if not is_market_hours():
            return []

        actions = []
        for symbol in UNIVERSE:
            try:
                action = self._evaluate(symbol, positions_cache)
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")
        return actions

    def _save_state(self):
        """Persist active_trades after any change."""
        if self.state_mgr:
            self.state_mgr.save_active_trades({
                "equity": self.active_trades,
            })

    def _cancel_stop_order(self, symbol: str):
        """Cancel the server-side stop order for a trade."""
        trade = self.active_trades.get(symbol, {})
        stop_id = trade.get("stop_order_id")
        if stop_id:
            try:
                self.client.cancel_order(stop_id)
                logger.info(f"Cancelled stop order {stop_id} for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to cancel stop order {stop_id} for {symbol}: {e}")

    def _evaluate(self, symbol: str, positions_cache: list = None) -> Optional[dict]:
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

        positions = positions_cache if positions_cache is not None else self.client.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)

        # EXIT LOGIC
        if pos is not None:
            qty = float(pos.qty)
            if qty <= 0:
                return None

            # Exit: price hits BB midline OR RSI > 50
            if price >= bb_middle or rsi >= RSI_EXIT:
                reason = f"bb_mid={bb_middle:.2f}" if price >= bb_middle else f"rsi={rsi:.1f}"
                logger.info(f"EXIT LONG {symbol}: {reason}")
                self._cancel_stop_order(symbol)
                try:
                    self.client.close_position(symbol)
                    if symbol in self.active_trades:
                        del self.active_trades[symbol]
                    self._save_state()
                except Exception as e:
                    logger.error(f"Failed to close {symbol}: {e}")
                    return None
                return {"action": "exit_long", "symbol": symbol, "price": price, "reason": reason}

            return None  # hold — server-side stop protects us

        # If no position but we have active_trade, stop was hit server-side — clean up
        if symbol in self.active_trades:
            logger.info(f"Position gone for {symbol} — server-side stop likely filled. Cleaning up.")
            del self.active_trades[symbol]
            self._save_state()

        # ENTRY LOGIC: price at/below lower BB AND RSI < 20
        if price <= bb_lower and rsi < RSI_ENTRY:
            return self._enter(symbol, price, atr)

        return None

    def _enter(self, symbol: str, price: float, atr: float) -> Optional[dict]:
        """Submit entry with server-side stop loss."""
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

        stop_price = round(price - (ATR_STOP_MULT * atr), 2)

        logger.info(
            f"ENTER LONG {symbol}: qty={qty}, price={price:.2f}, "
            f"stop={stop_price:.2f}"
        )

        # Submit market order first
        try:
            order = self.client.market_order(symbol, qty, "buy")
        except Exception as e:
            logger.error(f"Market order failed buy {symbol}: {e}")
            return None

        # Market order succeeded — record trade immediately so position is tracked
        order_id = order.id if hasattr(order, 'id') else str(order)
        self.active_trades[symbol] = {
            "side": "buy",
            "entry_price": price,
            "stop_price": stop_price,
            "qty": qty,
            "order_id": order_id,
            "stop_order_id": None,
            "time": datetime.utcnow().isoformat(),
        }
        self._save_state()

        # Now submit server-side stop order separately
        for attempt in range(3):
            try:
                stop_order = self.client.stop_order(symbol, qty, stop_price, side="sell")
                self.active_trades[symbol]["stop_order_id"] = (
                    stop_order.id if hasattr(stop_order, 'id') else str(stop_order)
                )
                self._save_state()
                break
            except Exception as e:
                logger.warning(f"Stop order attempt {attempt+1}/3 failed for {symbol}: {e}")
                if attempt == 2:
                    logger.critical(
                        f"STOP ORDER FAILED for {symbol} after 3 attempts — "
                        f"position UNPROTECTED. Manual intervention needed."
                    )

        return {"action": "enter_long", "symbol": symbol, "qty": qty, "price": price}

    def _get_rsi(self, symbol: str) -> float:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=20)
        if df is not None and "rsi_7" in df.columns:
            return df["rsi_7"].iloc[-1]
        return 50.0
