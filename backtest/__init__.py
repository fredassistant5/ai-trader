"""
AI Trader Backtesting Framework

This package provides comprehensive backtesting capabilities for the AI Trader strategies.
It replays historical data through the actual strategy logic with realistic slippage and commissions.
"""

from .engine import BacktestEngine
from .performance import PerformanceAnalyzer  
from .report import ReportGenerator
from .mock_client import MockAlpacaClient
from .mock_data import MockMarketData
from .mock_risk import MockRiskManager
from .mock_state import MockStateManager

__version__ = "1.0.0"
__all__ = [
    "BacktestEngine",
    "PerformanceAnalyzer", 
    "ReportGenerator",
    "MockAlpacaClient",
    "MockMarketData",
    "MockRiskManager", 
    "MockStateManager"
]