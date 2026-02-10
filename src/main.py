"""Main Runner — orchestrates strategies, risk management, and regime detection."""

import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import pytz

# Setup logging
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trader.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

from src.core.client import AlpacaClient
from src.data.market_data import MarketData
from src.risk.manager import RiskManager
from src.risk.regime import RegimeDetector
from src.strategies.crypto_mean_reversion import CryptoMeanReversion
from src.strategies.equity_mean_reversion import EquityMeanReversion, is_market_hours

ET = pytz.timezone("US/Eastern")
LOOP_INTERVAL = 60  # seconds between strategy evaluations


class Trader:
    """Main trading loop."""

    def __init__(self):
        logger.info("Initializing AI Trader...")
        self.client = AlpacaClient()
        self.market_data = MarketData()
        self.risk_manager = RiskManager(self.client)
        self.regime = RegimeDetector(self.market_data)
        self.crypto_strategy = CryptoMeanReversion(self.client, self.market_data, self.risk_manager)
        self.equity_strategy = EquityMeanReversion(self.client, self.market_data, self.risk_manager)
        self._running = True
        self._last_day = None
        self._last_week = None

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("AI Trader initialized successfully")

    def _shutdown(self, signum, frame):
        logger.info(f"Shutdown signal received ({signum}). Stopping gracefully...")
        self._running = False

    def _check_day_week_reset(self):
        """Reset daily/weekly risk state at appropriate boundaries."""
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

                # Refresh risk state
                self.risk_manager.refresh()
                if not self.risk_manager.is_trading_allowed():
                    logger.warning("Trading halted by risk manager")
                    time.sleep(LOOP_INTERVAL)
                    continue

                # Update regime and apply to risk manager
                regime_mult = self.regime.get_size_multiplier()
                self.risk_manager.apply_regime_multiplier(regime_mult)
                regime = self.regime.regime
                if regime != "normal":
                    logger.info(f"Regime: {regime}, size multiplier: {self.risk_manager.get_size_multiplier():.2f}")

                # Run crypto strategy (24/7)
                crypto_actions = self.crypto_strategy.run()
                for a in crypto_actions:
                    logger.info(f"CRYPTO: {a}")

                # Run equity strategy (market hours only)
                if is_market_hours():
                    equity_actions = self.equity_strategy.run()
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
