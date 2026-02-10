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

    def __init__(self, client, market_data, risk_manager):
        self.client = client
        self.data = market_data
        self.risk = risk_manager
        self.active_trades: dict[str, dict] = {}  # symbol -> {side, entry_price, stop_price}

    def run(self) -> list[dict]:
        """Evaluate all crypto symbols. Returns list of actions taken."""
        actions = []
        for symbol, params in UNIVERSE.items():
            try:
                action = self._evaluate(symbol, params)
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}")
        return actions

    def _evaluate(self, symbol: str, params: dict) -> Optional[dict]:
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

        # Check if we have an existing position
        positions = self.client.get_positions()
        pos = next((p for p in positions if p.symbol == sym_clean), None)

        # EXIT LOGIC
        if pos is not None:
            qty = float(pos.qty)
            side = "long" if qty > 0 else "short"

            # Check stop loss
            if symbol in self.active_trades:
                trade = self.active_trades[symbol]
                stop = trade.get("stop_price")
                if stop:
                    if (side == "long" and price <= stop) or (side == "short" and price >= stop):
                        logger.info(f"STOP HIT {symbol} @ {price:.2f} (stop={stop:.2f})")
                        self.client.close_position(sym_clean)
                        del self.active_trades[symbol]
                        return {"action": "stop_exit", "symbol": symbol, "price": price}

            # RSI exit
            if side == "long" and rsi >= RSI_EXIT_LONG:
                logger.info(f"EXIT LONG {symbol}: RSI={rsi:.1f} >= {RSI_EXIT_LONG}")
                self.client.close_position(sym_clean)
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                return {"action": "exit_long", "symbol": symbol, "rsi": rsi, "price": price}

            if side == "short" and rsi <= RSI_EXIT_SHORT:
                logger.info(f"EXIT SHORT {symbol}: RSI={rsi:.1f} <= {RSI_EXIT_SHORT}")
                self.client.close_position(sym_clean)
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                return {"action": "exit_short", "symbol": symbol, "rsi": rsi, "price": price}

            return None  # hold

        # ENTRY LOGIC — only if no position
        if rsi < RSI_ENTRY_LONG:
            return self._enter(symbol, "buy", price, atr, params)

        # Short entry (if desired — currently enabled)
        # if rsi > RSI_ENTRY_SHORT:
        #     return self._enter(symbol, "sell", price, atr, params)

        return None

    def _enter(self, symbol: str, side: str, price: float, atr: float, params: dict) -> Optional[dict]:
        """Size and submit an entry order."""
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
        except Exception:
            return None

        # Position sizing: volatility-adjusted, capped
        max_notional = params["max_pct"] * equity * params["vol_mult"]
        # Apply risk manager multiplier
        max_notional *= self.risk.get_size_multiplier()

        # Risk check
        allowed, reason = self.risk.pre_trade_check(symbol, max_notional, side)
        if not allowed:
            logger.info(f"RISK BLOCKED {side} {symbol}: {reason}")
            return None

        qty = max_notional / price
        if qty <= 0:
            return None

        # Round qty for crypto
        if "BTC" in symbol:
            qty = round(qty, 5)
        elif "ETH" in symbol:
            qty = round(qty, 4)
        else:
            qty = round(qty, 3)

        if qty <= 0:
            return None

        # Stop loss
        stop_price = price - (ATR_STOP_MULT * atr) if side == "buy" else price + (ATR_STOP_MULT * atr)

        logger.info(
            f"ENTER {side.upper()} {symbol}: qty={qty}, price={price:.2f}, "
            f"stop={stop_price:.2f}, notional=${max_notional:.0f}, RSI={self._get_rsi(symbol):.1f}"
        )

        try:
            order = self.client.market_order(symbol.replace("/", ""), qty, side)
            self.active_trades[symbol] = {
                "side": side,
                "entry_price": price,
                "stop_price": stop_price,
                "qty": qty,
                "time": datetime.utcnow().isoformat(),
            }
            return {"action": f"enter_{side}", "symbol": symbol, "qty": qty, "price": price}
        except Exception as e:
            logger.error(f"Order failed {side} {symbol}: {e}")
            return None

    def _get_rsi(self, symbol: str) -> float:
        df = self.data.get_bars_with_indicators(symbol, timeframe=TIMEFRAME, limit=20)
        if df is not None and "rsi_7" in df.columns:
            return df["rsi_7"].iloc[-1]
        return 50.0
