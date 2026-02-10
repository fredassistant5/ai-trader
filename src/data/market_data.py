"""Market Data Module — fetches OHLCV from Alpaca and calculates technical indicators."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np
import ta

from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from src.core.client import load_credentials

logger = logging.getLogger("market_data")

TIMEFRAME_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "4Hour": TimeFrame(4, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}

# Aliases
TIMEFRAME_ALIASES = {
    "1min": "1Min", "5min": "5Min", "15min": "15Min",
    "1h": "1Hour", "1H": "1Hour", "4h": "4Hour", "4H": "4Hour",
    "1d": "1Day", "1D": "1Day",
}

CRYPTO_SYMBOLS = {"BTC/USD", "ETH/USD", "SOL/USD", "BTCUSD", "ETHUSD", "SOLUSD"}


def _normalize_tf(timeframe: str) -> str:
    return TIMEFRAME_ALIASES.get(timeframe, timeframe)


def _is_crypto(symbol: str) -> bool:
    return symbol.replace("/", "") in {s.replace("/", "") for s in CRYPTO_SYMBOLS} or "/" in symbol


class MarketData:
    """Fetches bars from Alpaca and computes indicators. Caches results."""

    def __init__(self):
        creds = load_credentials()
        self.stock_client = StockHistoricalDataClient(
            api_key=creds["api_key"], secret_key=creds["secret_key"]
        )
        self.crypto_client = CryptoHistoricalDataClient(
            api_key=creds["api_key"], secret_key=creds["secret_key"]
        )
        self._cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._cache_ttl = 60  # seconds

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5Min",
        limit: int = 100,
        start: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV bars. Returns DataFrame with columns: open, high, low, close, volume."""
        tf_key = _normalize_tf(timeframe)
        cache_key = f"{symbol}:{tf_key}:{limit}"

        # Check cache
        if cache_key in self._cache:
            ts, df = self._cache[cache_key]
            if (datetime.utcnow() - ts).total_seconds() < self._cache_ttl:
                return df.copy()

        tf = TIMEFRAME_MAP.get(tf_key)
        if tf is None:
            logger.error(f"Unknown timeframe: {timeframe}")
            return None

        if start is None:
            # Estimate start time from limit and timeframe
            start = datetime.utcnow() - timedelta(days=max(limit * 2, 30))

        try:
            if _is_crypto(symbol):
                # Ensure format is SYMBOL/USD
                sym = symbol if "/" in symbol else symbol[:-3] + "/" + symbol[-3:]
                request = CryptoBarsRequest(
                    symbol_or_symbols=sym,
                    timeframe=tf,
                    start=start,
                    limit=limit,
                )
                barset = self.crypto_client.get_crypto_bars(request)
                bars = barset[sym] if sym in barset else list(barset.values())[0] if barset else []
            else:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf,
                    start=start,
                    limit=limit,
                )
                barset = self.stock_client.get_stock_bars(request)
                bars = barset[symbol] if symbol in barset else list(barset.values())[0] if barset else []

            if not bars:
                logger.warning(f"No bars returned for {symbol} {tf_key}")
                return None

            df = pd.DataFrame([{
                "timestamp": b.timestamp,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            } for b in bars])

            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            # Trim to requested limit
            if len(df) > limit:
                df = df.iloc[-limit:]

            self._cache[cache_key] = (datetime.utcnow(), df)
            return df.copy()

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None

    def get_bars_with_indicators(
        self,
        symbol: str,
        timeframe: str = "5Min",
        limit: int = 100,
    ) -> Optional[pd.DataFrame]:
        """Fetch bars and add all standard indicators."""
        df = self.get_bars(symbol, timeframe, limit=max(limit + 50, 150))
        if df is None or len(df) < 20:
            return df

        df = self.add_indicators(df)
        return df.iloc[-limit:] if len(df) > limit else df

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to a DataFrame with OHLCV columns."""
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # RSI
        df["rsi_7"] = ta.momentum.RSIIndicator(c, window=7).rsi()
        df["rsi_14"] = ta.momentum.RSIIndicator(c, window=14).rsi()

        # EMA
        df["ema_8"] = ta.trend.EMAIndicator(c, window=8).ema_indicator()
        df["ema_21"] = ta.trend.EMAIndicator(c, window=21).ema_indicator()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(c, window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()

        # VWAP (session-based approximation)
        tp = (h + l + c) / 3
        cumvol = v.cumsum()
        cumtpvol = (tp * v).cumsum()
        df["vwap"] = cumtpvol / cumvol.replace(0, np.nan)

        # ADX
        adx = ta.trend.ADXIndicator(h, l, c, window=14)
        df["adx"] = adx.adx()

        # ATR
        atr = ta.volatility.AverageTrueRange(h, l, c, window=14)
        df["atr_14"] = atr.average_true_range()

        # Z-score (20-period)
        rolling_mean = c.rolling(20).mean()
        rolling_std = c.rolling(20).std()
        df["zscore"] = (c - rolling_mean) / rolling_std.replace(0, np.nan)

        return df
