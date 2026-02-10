"""Main Runner — orchestrates strategies, risk management, and regime detection."""

import logging
import signal
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytz

# Setup logging with rotation (M5)
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        RotatingFileHandler(LOG_DIR / "trader.log", maxBytes=10_000_000, backupCount=5),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

from src.core.client import AlpacaClient
from src.core.state import StateManager
from src.data.market_data import MarketData
from src.risk.manager import RiskManager
from src.risk.regime import RegimeDetector
from src.strategies.crypto_mean_reversion import CryptoMeanReversion
from src.strategies.equity_mean_reversion import EquityMeanReversion, is_market_hours

ET = pytz.timezone("US/Eastern")
LOOP_INTERVAL = 60
ORPHAN_STOP_PCT = 0.05  # default stop for orphaned positions


class Trader:
    """Main trading loop."""

    def __init__(self):
        logger.info("Initializing AI Trader...")
        self.client = AlpacaClient()
        self.market_data = MarketData()
        self.risk_manager = RiskManager(self.client)
        self.regime = RegimeDetector(self.market_data)
        self.state_mgr = StateManager()

        self.crypto_strategy = CryptoMeanReversion(
            self.client, self.market_data, self.risk_manager, self.state_mgr
        )
        self.equity_strategy = EquityMeanReversion(
            self.client, self.market_data, self.risk_manager, self.state_mgr
        )

        self._running = True
        self._last_day = None
        self._last_week = None

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # C3: Load persisted state
        self._load_persisted_state()

        # H2: Reconcile positions on startup
        self._reconcile_positions()

        logger.info("AI Trader initialized successfully")

    def _load_persisted_state(self):
        """Load active_trades from disk."""
        saved = self.state_mgr.load_active_trades()
        if "crypto" in saved:
            self.crypto_strategy.load_state(saved["crypto"])
            logger.info(f"Loaded {len(saved['crypto'])} crypto active trades")
        if "equity" in saved:
            self.equity_strategy.load_state(saved["equity"])
            logger.info(f"Loaded {len(saved['equity'])} equity active trades")

    def _reconcile_positions(self):
        """H2: On startup, check for orphaned positions (positions without active_trade entries)."""
        try:
            positions = self.client.get_positions()
        except Exception as e:
            logger.error(f"Failed to fetch positions for reconciliation: {e}")
            return

        crypto_set = {"BTCUSD", "ETHUSD", "SOLUSD"}
        crypto_trades = self.crypto_strategy.active_trades
        equity_trades = self.equity_strategy.active_trades

        for pos in positions:
            sym = pos.symbol
            # Map back to slash format for crypto
            sym_slash = None
            for cs in ["BTC/USD", "ETH/USD", "SOL/USD"]:
                if cs.replace("/", "") == sym:
                    sym_slash = cs
                    break

            is_crypto = sym in crypto_set
            tracked = False
            if is_crypto and sym_slash and sym_slash in crypto_trades:
                tracked = True
            elif not is_crypto and sym in equity_trades:
                tracked = True

            if not tracked:
                price = abs(float(pos.avg_entry_price))
                qty = abs(float(pos.qty))
                side = "long" if float(pos.qty) > 0 else "short"

                # Submit a protective stop order for orphaned positions
                stop_price = round(price * (1 - ORPHAN_STOP_PCT) if side == "long"
                                   else price * (1 + ORPHAN_STOP_PCT), 2)
                stop_side = "sell" if side == "long" else "buy"

                logger.warning(
                    f"ORPHANED position found: {sym} qty={pos.qty} avg_entry={price:.2f}. "
                    f"Placing protective stop @ {stop_price:.2f}"
                )

                try:
                    order_sym = sym_slash.replace("/", "") if sym_slash else sym
                    stop_order = self.client.stop_order(order_sym, qty, stop_price, side=stop_side)
                    stop_id = stop_order.id if hasattr(stop_order, 'id') else str(stop_order)

                    trade_entry = {
                        "side": "buy" if side == "long" else "sell",
                        "entry_price": price,
                        "stop_price": stop_price,
                        "qty": qty,
                        "stop_order_id": stop_id,
                        "time": datetime.utcnow().isoformat(),
                        "orphan_reconciled": True,
                    }

                    if is_crypto and sym_slash:
                        crypto_trades[sym_slash] = trade_entry
                    else:
                        equity_trades[sym] = trade_entry

                except Exception as e:
                    logger.error(f"Failed to place protective stop for orphaned {sym}: {e}")

        # Save updated state
        self.state_mgr.save_active_trades({
            "crypto": crypto_trades,
            "equity": equity_trades,
        })

    def _shutdown(self, signum, frame):
        logger.info(f"Shutdown signal received ({signum}). Stopping gracefully...")
        self._running = False
        # Save state on shutdown
        self.state_mgr.save_active_trades({
            "crypto": self.crypto_strategy.active_trades,
            "equity": self.equity_strategy.active_trades,
        })

    def _check_day_week_reset(self):
        now = datetime.now(ET)
        today = now.date()
        week_num = today.isocalendar()[1]

        if self._last_day != today:
            self.risk_manager.new_day()
            self._last_day = today

        if self._last_week != week_num:
            self.risk_manager.new_week()
            self._last_week = week_num

    def run(self):
        """Main loop."""
        logger.info("Starting main trading loop")
        acct = self.client.get_account()
        logger.info(f"Account equity: ${float(acct.equity):,.2f}, cash: ${float(acct.cash):,.2f}")

        while self._running:
            try:
                self._check_day_week_reset()

                self.risk_manager.refresh()
                if not self.risk_manager.is_trading_allowed():
                    logger.warning("Trading halted by risk manager")
                    time.sleep(LOOP_INTERVAL)
                    continue

                regime_mult = self.regime.get_size_multiplier()
                self.risk_manager.apply_regime_multiplier(regime_mult)
                regime = self.regime.regime
                if regime != "normal":
                    logger.info(f"Regime: {regime}, size multiplier: {self.risk_manager.get_size_multiplier():.2f}")

                # H6: Cache positions once per loop iteration
                try:
                    positions_cache = self.client.get_positions()
                except Exception as e:
                    logger.error(f"Failed to fetch positions: {e}")
                    time.sleep(LOOP_INTERVAL)
                    continue

                # Run crypto strategy (24/7) with cached positions
                crypto_actions = self.crypto_strategy.run(positions_cache=positions_cache)
                for a in crypto_actions:
                    logger.info(f"CRYPTO: {a}")

                # Run equity strategy (market hours only) with cached positions
                if is_market_hours():
                    equity_actions = self.equity_strategy.run(positions_cache=positions_cache)
                    for a in equity_actions:
                        logger.info(f"EQUITY: {a}")

                time.sleep(LOOP_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)
                time.sleep(LOOP_INTERVAL)

        logger.info("Trader stopped.")


def main():
    trader = Trader()
    trader.run()


if __name__ == "__main__":
    main()
