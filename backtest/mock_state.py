"""
Mock State Manager - Simulates persistent state for backtesting.

Implements the same interface as the real StateManager but keeps
everything in memory for the simulation.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("mock_state")


class MockStateManager:
    """Mock state manager that keeps state in memory."""
    
    def __init__(self):
        self.active_trades: Dict[str, Dict] = {}
        self.state_data: Dict[str, Any] = {}
        
        logger.info("MockStateManager initialized")
    
    def save_active_trades(self, trades: Dict[str, Dict]):
        """Save active trades state."""
        self.active_trades.update(trades)
        logger.debug(f"Saved active trades state: {len(self.active_trades)} strategies")
    
    def load_active_trades(self) -> Dict[str, Dict]:
        """Load active trades state."""
        return self.active_trades.copy()
    
    def save_state(self, key: str, data: Any):
        """Save arbitrary state data."""
        self.state_data[key] = data
        logger.debug(f"Saved state: {key}")
    
    def load_state(self, key: str, default: Any = None) -> Any:
        """Load arbitrary state data."""
        return self.state_data.get(key, default)
    
    def clear_state(self):
        """Clear all state (for new backtest runs)."""
        self.active_trades.clear()
        self.state_data.clear()
        logger.info("Cleared all state")