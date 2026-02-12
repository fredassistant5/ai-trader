"""Crypto Mean Reversion Strategy — 24/7 RSI-based on BTC, ETH, SOL."""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("strategy.crypto_mr")

UNIVERSE = {
    "BTC/USD": {"vol_mult": 1.0, "max_pct": 0.10},
    "ETH/USD": {"vol_mult": 1.0, "max_pct": 0.10},
    "SOL/USD": {"vol_mult": 0.5, "max_pct": 0.05},  # half size for SOL
}

RSI_PERIOD = 7
TIMEFRAME = "15Min"
RSI_ENTRY_LONG = 25
RSI_ENTRY_SHORT = 75
RSI_EXIT_LONG = 45
RSI_EXIT_SHORT = 55
ATR_STOP_MULT = 1.5


class CryptoMeanReversion:
    """RSI(7) mean reversion on 15-min bars for crypto."""

    def __init__(self, client, market_data, risk_manager, state_manager=None):
        self.client = client
        self.data = market_data
        self.risk = risk_manager
        self.state_mgr = state_manager
        self.active_trades: dict[str, dict] = {}

    def load_state(self, trades: dict):
        """Load persisted active_trades."""
        self.active_trades = trades

    def run(self, positions_cache: list = None, current_time: datetime = None) -> list[dict]:
        """Evaluate all crypto symbols. Returns list of actions taken."""
        actions = []
        for symbol, params in UNIVERSE.items():
            try:
                action = self._evaluate(symbol, params, positions_cache)
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")
        return actions

    def _save_state(self):
        """Persist active_trades after any change."""
        if self.state_mgr:
            self.state_mgr.save_active_trades({
                "crypto": self.active_trades,
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

    def _evaluate(self, symbol: str, params: dict, positions_cache: list = None) -> Optional[dict]:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=50)
        if df is None or len(df) < 20:
            return None

        latest = df.iloc[-1]
        rsi = latest.get("rsi_7")
        atr = latest.get("atr_14")
        price = latest["close"]

        if rsi is None or atr is None:
            return None

        sym_clean = symbol.replace("/", "")

        # Use cached positions if available (H6: reduce API calls)
        positions = positions_cache if positions_cache is not None else self.client.get_positions()
        pos = next((p for p in positions if p.symbol == sym_clean), None)

        # EXIT LOGIC
        if pos is not None:
            qty = float(pos.qty)
            side = "long" if qty > 0 else "short"

            # Server-side stops handle stop exits — RSI exit still managed here
            if side == "long" and rsi >= RSI_EXIT_LONG:
                logger.info(f"EXIT LONG {symbol}: RSI={rsi:.1f} >= {RSI_EXIT_LONG}")
                self._cancel_stop_order(symbol)
                try:
                    self.client.close_position(sym_clean)
                    if symbol in self.active_trades:
                        del self.active_trades[symbol]
                    self._save_state()
                except Exception as e:
                    logger.error(f"Failed to close {symbol}: {e}")
                    return None
                return {"action": "exit_long", "symbol": symbol, "rsi": rsi, "price": price}

            if side == "short" and rsi <= RSI_EXIT_SHORT:
                logger.info(f"EXIT SHORT {symbol}: RSI={rsi:.1f} <= {RSI_EXIT_SHORT}")
                self._cancel_stop_order(symbol)
                try:
                    self.client.close_position(sym_clean)
                    if symbol in self.active_trades:
                        del self.active_trades[symbol]
                    self._save_state()
                except Exception as e:
                    logger.error(f"Failed to close {symbol}: {e}")
                    return None
                return {"action": "exit_short", "symbol": symbol, "rsi": rsi, "price": price}

            return None  # hold — server-side stop protects us

        # If no position but we have active_trade, stop was hit server-side — clean up
        if symbol in self.active_trades:
            logger.info(f"Position gone for {symbol} — server-side stop likely filled. Cleaning up.")
            del self.active_trades[symbol]
            self._save_state()

        # ENTRY LOGIC — only if no position
        if rsi < RSI_ENTRY_LONG:
            return self._enter(symbol, "buy", price, atr, params)

        # Short entry (disabled)
        # if rsi > RSI_ENTRY_SHORT:
        #     return self._enter(symbol, "sell", price, atr, params)

        return None

    def _enter(self, symbol: str, side: str, price: float, atr: float, params: dict) -> Optional[dict]:
        """Size and submit an entry order with server-side stop loss."""
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
        except Exception:
            return None

        max_notional = params["max_pct"] * equity * params["vol_mult"]
        max_notional *= self.risk.get_size_multiplier()

        allowed, reason = self.risk.pre_trade_check(symbol, max_notional, side)
        if not allowed:
            logger.info(f"RISK BLOCKED {side} {symbol}: {reason}")
            return None

        qty = max_notional / price
        if qty <= 0:
            return None

        if "BTC" in symbol:
            qty = round(qty, 5)
        elif "ETH" in symbol:
            qty = round(qty, 4)
        else:
            qty = round(qty, 3)

        if qty <= 0:
            return None

        stop_price = price - (ATR_STOP_MULT * atr) if side == "buy" else price + (ATR_STOP_MULT * atr)

        logger.info(
            f"ENTER {side.upper()} {symbol}: qty={qty}, price={price:.2f}, "
            f"stop={stop_price:.2f}, notional=${max_notional:.0f}"
        )

        # Submit market order first
        try:
            order = self.client.market_order(symbol.replace("/", ""), qty, side)
        except Exception as e:
            logger.error(f"Market order failed {side} {symbol}: {e}")
            return None

        # Market order succeeded — record trade immediately so position is tracked
        order_id = order.id if hasattr(order, 'id') else str(order)
        self.active_trades[symbol] = {
            "side": side,
            "entry_price": price,
            "stop_price": stop_price,
            "qty": qty,
            "order_id": order_id,
            "stop_order_id": None,
            "time": datetime.utcnow().isoformat(),
        }
        self._save_state()

        # Now submit server-side stop order separately
        stop_side = "sell" if side == "buy" else "buy"
        for attempt in range(3):
            try:
                stop_order = self.client.stop_order(
                    symbol.replace("/", ""), qty, stop_price, side=stop_side
                )
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

        return {"action": f"enter_{side}", "symbol": symbol, "qty": qty, "price": price}

    def _get_rsi(self, symbol: str) -> float:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=20)
        if df is not None and "rsi_7" in df.columns:
            return df["rsi_7"].iloc[-1]
        return 50.0
