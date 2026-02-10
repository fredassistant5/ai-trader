"""Regime Detector — monitors VIX proxy (UVXY), TLT, BTC for risk-off conditions."""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("regime")


class RegimeDetector:
    """Simple regime detection: if VIX proxy (UVXY) up >5% in a day → risk-off."""

    PROXY_SYMBOL = "UVXY"
    RISK_OFF_THRESHOLD = 0.05  # 5% daily move in UVXY

    def __init__(self, market_data):
        """market_data: MarketData instance."""
        self.market_data = market_data
        self.regime = "normal"  # "normal" or "risk_off"
        self._last_check: Optional[datetime] = None

    def check(self) -> str:
        """
        Returns current regime: 'normal' or 'risk_off'.
        Updates at most every 5 minutes.
        """
        now = datetime.utcnow()
        if self._last_check and (now - self._last_check).total_seconds() < 300:
            return self.regime

        self._last_check = now

        try:
            bars = self.market_data.get_bars(self.PROXY_SYMBOL, timeframe="1Day", limit=2)
            if bars is None or len(bars) < 2:
                return self.regime

            prev_close = bars["close"].iloc[-2]
            curr_close = bars["close"].iloc[-1]
            change = (curr_close - prev_close) / prev_close

            if change > self.RISK_OFF_THRESHOLD:
                if self.regime != "risk_off":
                    logger.warning(f"REGIME → RISK-OFF: UVXY up {change:.1%}")
                self.regime = "risk_off"
            else:
                if self.regime != "normal":
                    logger.info(f"REGIME → NORMAL: UVXY change {change:.1%}")
                self.regime = "normal"

        except Exception as e:
            logger.error(f"Regime check failed: {e}")

        return self.regime

    def get_size_multiplier(self) -> float:
        """Returns position size multiplier based on regime."""
        regime = self.check()
        if regime == "risk_off":
            return 0.25
        return 1.0
