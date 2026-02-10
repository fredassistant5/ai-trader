"""Risk Manager — enforces all portfolio-level risk constraints before any order."""

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

logger = logging.getLogger("risk")

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_fh = RotatingFileHandler(LOG_DIR / "risk.log", maxBytes=10_000_000, backupCount=5)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)
logger.setLevel(logging.INFO)


class RiskState:
    """Persistent risk state tracking."""

    def __init__(self):
        self.day_start_equity: Optional[float] = None
        self.week_start_equity: Optional[float] = None
        self.peak_equity: Optional[float] = None
        self.daily_halted = False
        self.kill_switch = False
        self.size_multiplier = 1.0
        self.weekly_loss_until: Optional[datetime] = None

    def reset_daily(self, equity: float):
        self.day_start_equity = equity
        self.daily_halted = False
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    def reset_weekly(self, equity: float):
        self.week_start_equity = equity
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity


class RiskManager:
    """Central risk gate — every order must pass pre_trade_check()."""

    # Hard limits
    DAILY_LOSS_PCT = 0.02
    WEEKLY_LOSS_PCT = 0.05
    MAX_DRAWDOWN_PCT = 0.10
    MAX_SINGLE_POSITION_PCT = 0.05
    MAX_CRYPTO_EXPOSURE_PCT = 0.30
    MAX_CONCURRENT_POSITIONS = 15
    MIN_CASH_RESERVE_PCT = 0.10

    CRYPTO_SYMBOLS = {"BTC/USD", "ETH/USD", "SOL/USD", "BTCUSD", "ETHUSD", "SOLUSD"}

    def __init__(self, client):
        self.client = client
        self.state = RiskState()
        self._lock = threading.Lock()  # C4: prevent race conditions
        self._pending_notional = 0.0  # tracks in-flight order notional
        self._init_state()

    def _init_state(self):
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
            self.state.reset_daily(equity)
            self.state.reset_weekly(equity)
            self.state.peak_equity = equity
            logger.info(f"RiskManager initialized. Equity=${equity:,.2f}")
        except Exception as e:
            logger.error(f"Failed to init risk state: {e}")

    def refresh(self):
        """Call periodically to update risk state and check circuit breakers."""
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
        except Exception as e:
            logger.error(f"Cannot refresh account: {e}")
            return

        if self.state.peak_equity is None or equity > self.state.peak_equity:
            self.state.peak_equity = equity

        # Reset pending notional each refresh (orders from last cycle should be settled)
        self._pending_notional = 0.0

        # Check weekly loss half-size expiry
        if self.state.weekly_loss_until and datetime.utcnow() > self.state.weekly_loss_until:
            self.state.size_multiplier = 1.0
            self.state.weekly_loss_until = None
            logger.info("Weekly loss half-size period expired, restoring full size")

        # Daily loss check
        if self.state.day_start_equity:
            daily_pnl_pct = (equity - self.state.day_start_equity) / self.state.day_start_equity
            if daily_pnl_pct <= -self.DAILY_LOSS_PCT:
                if not self.state.daily_halted:
                    self.state.daily_halted = True
                    logger.warning(f"DAILY LOSS BREAKER: {daily_pnl_pct:.2%} — halting all trading")

        # Weekly loss check
        if self.state.week_start_equity:
            weekly_pnl_pct = (equity - self.state.week_start_equity) / self.state.week_start_equity
            if weekly_pnl_pct <= -self.WEEKLY_LOSS_PCT and self.state.weekly_loss_until is None:
                self.state.size_multiplier = 0.5
                self.state.weekly_loss_until = datetime.utcnow() + timedelta(days=3)
                logger.warning(f"WEEKLY LOSS BREAKER: {weekly_pnl_pct:.2%} — halving sizes for 3 days")

        # Max drawdown kill switch
        if self.state.peak_equity:
            drawdown = (equity - self.state.peak_equity) / self.state.peak_equity
            if drawdown <= -self.MAX_DRAWDOWN_PCT:
                if not self.state.kill_switch:
                    self.state.kill_switch = True
                    logger.critical(f"KILL SWITCH: {drawdown:.2%} drawdown — stopping everything")

    def is_trading_allowed(self) -> bool:
        if self.state.kill_switch:
            return False
        if self.state.daily_halted:
            return False
        return True

    def pre_trade_check(self, symbol: str, notional: float, side: str = "buy") -> tuple[bool, str]:
        """
        Validate a proposed trade against all risk limits.
        Returns (allowed, reason). Thread-safe with pending notional tracking.
        """
        with self._lock:
            self.refresh()

            if not self.is_trading_allowed():
                reason = "kill_switch" if self.state.kill_switch else "daily_halt"
                logger.info(f"BLOCKED {side} {symbol} ${notional:.2f}: {reason}")
                return False, reason

            try:
                acct = self.client.get_account()
                equity = float(acct.equity)
                cash = float(acct.cash)
                positions = self.client.get_positions()
            except Exception as e:
                logger.error(f"Cannot fetch account for pre-trade: {e}")
                return False, f"api_error: {e}"

            # Max single position size
            if notional > self.MAX_SINGLE_POSITION_PCT * equity:
                reason = f"position_too_large: ${notional:.0f} > {self.MAX_SINGLE_POSITION_PCT:.0%} of ${equity:.0f}"
                logger.info(f"BLOCKED {side} {symbol}: {reason}")
                return False, reason

            # Max concurrent positions
            if len(positions) >= self.MAX_CONCURRENT_POSITIONS:
                existing = [p for p in positions if p.symbol == symbol.replace("/", "")]
                if not existing:
                    reason = f"max_positions: {len(positions)} >= {self.MAX_CONCURRENT_POSITIONS}"
                    logger.info(f"BLOCKED {side} {symbol}: {reason}")
                    return False, reason

            # H1: Cash reserve check only for buys (sells free cash, not consume it)
            if side == "buy":
                min_cash = self.MIN_CASH_RESERVE_PCT * equity
                effective_cash = cash - self._pending_notional  # C4: account for in-flight orders
                if effective_cash - notional < min_cash:
                    reason = f"cash_reserve: cash ${effective_cash:.0f} - ${notional:.0f} < min ${min_cash:.0f}"
                    logger.info(f"BLOCKED {side} {symbol}: {reason}")
                    return False, reason

            # Crypto exposure limit
            sym_clean = symbol.replace("/", "")
            crypto_set = {s.replace("/", "") for s in self.CRYPTO_SYMBOLS}
            is_crypto = sym_clean in crypto_set
            if is_crypto and side == "buy":
                crypto_exposure = sum(
                    abs(float(p.market_value))
                    for p in positions
                    if p.symbol in crypto_set
                )
                if crypto_exposure + notional > self.MAX_CRYPTO_EXPOSURE_PCT * equity:
                    reason = f"crypto_limit: ${crypto_exposure + notional:.0f} > {self.MAX_CRYPTO_EXPOSURE_PCT:.0%} of ${equity:.0f}"
                    logger.info(f"BLOCKED {side} {symbol}: {reason}")
                    return False, reason

            # C4: Track pending notional for this cycle
            if side == "buy":
                self._pending_notional += notional

            logger.info(f"APPROVED {side} {symbol} ${notional:.2f}")
            return True, "approved"

    def get_size_multiplier(self) -> float:
        return self.state.size_multiplier

    def apply_regime_multiplier(self, regime_mult: float):
        base = 0.5 if self.state.weekly_loss_until else 1.0
        self.state.size_multiplier = base * regime_mult

    def new_day(self):
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
            self.state.reset_daily(equity)
            logger.info(f"New day. Equity=${equity:,.2f}")
        except Exception as e:
            logger.error(f"new_day failed: {e}")

    def new_week(self):
        try:
            acct = self.client.get_account()
            equity = float(acct.equity)
            self.state.reset_weekly(equity)
            logger.info(f"New week. Equity=${equity:,.2f}")
        except Exception as e:
            logger.error(f"new_week failed: {e}")
