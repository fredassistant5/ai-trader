"""
Mock Market Data - Provides historical data replay for backtesting.

Implements the same interface as the real MarketData class but replays
historical data in a time-aware manner for simulation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pandas as pd
import numpy as np

# Import the real market data class to reuse data fetching and indicator logic
from src.data.market_data import MarketData, _is_crypto, _normalize_tf, TIMEFRAME_MAP

logger = logging.getLogger("mock_data")


class MockMarketData:
    """Mock market data that provides historical data replay."""
    
    def __init__(self):
        self.real_data = MarketData()  # Use real data fetcher for historical data
        self.current_time: Optional[datetime] = None
        self.start_date: Optional[datetime] = None 
        self.end_date: Optional[datetime] = None
        
        # Cache historical data for efficient replay
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.price_cache: Dict[str, float] = {}
        
        logger.info("MockMarketData initialized")
    
    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for data storage and retrieval."""
        # Store both forms to handle mismatch - the real data API might expect one or the other
        return symbol
    
    def set_date_range(self, start_date: datetime, end_date: datetime):
        """Set the date range for the backtest."""
        self.start_date = start_date
        self.end_date = end_date
        logger.info(f"Set backtest date range: {start_date} to {end_date}")
    
    def set_current_time(self, current_time: datetime):
        """Set current simulation time."""
        self.current_time = current_time
        
        # Update current prices for mock client
        self._update_current_prices()
    
    def get_bars_with_indicators(
        self, 
        symbol: str, 
        timeframe: str = "5Min", 
        limit: int = 100
    ) -> Optional[pd.DataFrame]:
        """Get bars up to current simulation time with indicators."""
        if self.current_time is None:
            logger.warning("Current time not set - fetching latest data")
            # Fall back to real-time behavior
            return self.real_data.get_bars_with_indicators(symbol, timeframe, limit)
        
        # For backtesting, fetch historical data up to current time
        # Add buffer for indicators
        start_time = self.current_time - timedelta(days=max(limit * 2, 30))
        
        try:
            df = self.real_data.get_bars(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit * 2,  # Get extra for filtering
                start=start_time
            )
            
            if df is None or len(df) == 0:
                return None
            
            # Filter to only data up to current simulation time FIRST to avoid lookahead bias
            # Convert current_time to UTC if needed
            import pytz
            current_time = self.current_time
            if current_time.tzinfo is None:
                current_time = pytz.utc.localize(current_time)
            
            # Ensure df.index is timezone-aware for proper comparison
            if df.index.tz is None:
                df.index = pd.to_datetime(df.index, utc=True)
            elif df.index.tz != current_time.tzinfo:
                df.index = df.index.tz_convert(current_time.tzinfo)
            
            # Filter to simulation time BEFORE adding indicators
            replay_data = df[df.index <= current_time].copy()
            
            if len(replay_data) == 0:
                return None
            
            # NOW add indicators to the filtered data (no lookahead bias)
            replay_data = self.real_data.add_indicators(replay_data)
            
            # Return only the requested number of bars
            if len(replay_data) > limit:
                replay_data = replay_data.iloc[-limit:]
            
            # Update current price for mock client
            if len(replay_data) > 0:
                latest_price = replay_data['close'].iloc[-1]
                self.price_cache[symbol] = latest_price
                # For crypto symbols, also store the version without slash for position lookups
                if "/" in symbol:
                    symbol_no_slash = symbol.replace("/", "")
                    self.price_cache[symbol_no_slash] = latest_price
                
                if hasattr(self, '_mock_client'):
                    self._mock_client.set_current_price(symbol, latest_price)
                    # Also set price for both forms of crypto symbols
                    if "/" in symbol:
                        self._mock_client.set_current_price(symbol.replace("/", ""), latest_price)
            
            return replay_data
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5Min", 
        limit: int = 100,
        start: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """Get raw OHLCV bars (without indicators)."""
        # For backtesting, we'll always use the cached data approach
        df_with_indicators = self.get_bars_with_indicators(symbol, timeframe, limit)
        if df_with_indicators is None:
            return None
        
        # Return only OHLCV columns
        ohlcv_columns = ['open', 'high', 'low', 'close', 'volume']
        available_columns = [col for col in ohlcv_columns if col in df_with_indicators.columns]
        
        return df_with_indicators[available_columns].copy()
    
    def _get_all_symbols(self) -> List[str]:
        """Get all symbols that strategies might use."""
        # From strategies
        crypto_symbols = ["BTC/USD", "ETH/USD", "SOL/USD"]
        equity_symbols = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]
        
        return crypto_symbols + equity_symbols
    
    def _get_timeframes_for_symbol(self, symbol: str) -> List[str]:
        """Get timeframes needed for each symbol.""" 
        if "/" in symbol or _is_crypto(symbol):
            return ["15Min"]  # Crypto strategy uses 15-min
        else:
            return ["5Min"]   # Equity strategy uses 5-min
    
    def _preload_symbol_data(
        self, 
        symbol: str, 
        timeframe: str, 
        start_date: datetime, 
        end_date: datetime
    ):
        """Preload and cache historical data for a symbol."""
        cache_key = f"{symbol}:{timeframe}"
        
        logger.info(f"Preloading data for {cache_key} from {start_date} to {end_date}")
        
        # Calculate how many bars we need (with some buffer)
        tf_minutes = self._timeframe_to_minutes(timeframe)
        total_minutes = (end_date - start_date).total_seconds() / 60
        estimated_bars = int(total_minutes / tf_minutes) + 200  # Extra buffer
        
        # Use the real market data class to fetch historical data
        df = self.real_data.get_bars_with_indicators(
            symbol=symbol,
            timeframe=timeframe,
            limit=min(estimated_bars, 10000)  # API limits
        )
        
        if df is None or len(df) == 0:
            logger.warning(f"No data retrieved for {cache_key}")
            return
        
        # Filter to our date range (keep some buffer for indicators)
        buffer_start = start_date - timedelta(days=30)
        
        # Make sure datetime objects are timezone-aware for comparison
        import pytz
        if buffer_start.tzinfo is None:
            buffer_start = pytz.utc.localize(buffer_start)
        if end_date.tzinfo is None:
            end_date = pytz.utc.localize(end_date)
        
        filtered_df = df[(df.index >= buffer_start) & (df.index <= end_date)].copy()
        
        if len(filtered_df) == 0:
            logger.warning(f"No data in date range for {cache_key}")
            return
        
        self.data_cache[cache_key] = filtered_df
        logger.info(f"Cached {len(filtered_df)} bars for {cache_key}")
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        tf_map = {
            "1Min": 1,
            "5Min": 5, 
            "15Min": 15,
            "1Hour": 60,
            "4Hour": 240,
            "1Day": 1440
        }
        return tf_map.get(timeframe, 5)
    
    def _update_current_prices(self):
        """Update current prices for the mock client.""" 
        if self.current_time is None:
            return
        
        # Update latest prices for each symbol at current time
        import pytz
        current_time = self.current_time
        if current_time and current_time.tzinfo is None:
            current_time = pytz.utc.localize(current_time)
            
        for cache_key, df in self.data_cache.items():
            symbol = cache_key.split(':')[0]
            
            # Get the most recent bar up to current time
            if current_time:
                # Ensure timezone compatibility for comparison
                df_index = df.index
                if df_index.tz is None:
                    df_index = pd.to_datetime(df_index, utc=True)
                elif df_index.tz != current_time.tzinfo:
                    df_index = df_index.tz_convert(current_time.tzinfo)
                
                current_data = df[df_index <= current_time]
                if len(current_data) > 0:
                    latest_price = current_data['close'].iloc[-1]
                    self.price_cache[symbol] = latest_price
                    
                    # Also update the mock client if available
                    # This is a bit of coupling, but necessary for realistic simulation
                    if hasattr(self, '_mock_client'):
                        self._mock_client.set_current_price(symbol, latest_price)
    
    def set_mock_client(self, mock_client):
        """Set reference to mock client for price updates."""
        self._mock_client = mock_client
    
    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Add indicators - delegate to real market data class."""
        return MarketData.add_indicators(df)