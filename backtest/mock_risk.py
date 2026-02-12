"""
Mock Risk Manager - Simulates risk controls for backtesting.

Implements the same interface as the real RiskManager but with
simplified logic appropriate for simulation.
"""

import logging
from typing import Tuple

logger = logging.getLogger("mock_risk")


class MockRiskManager:
    """Mock risk manager that enforces basic position limits."""
    
    def __init__(self):
        self.size_multiplier = 1.0
        self.daily_halted = False
        self.kill_switch = False
        
        # Risk limits (same as real system)
        self.max_position_pct = 0.15  # 15% max per position
        self.max_crypto_pct = 0.30    # 30% max crypto exposure
        self.max_positions = 15       # Max 15 concurrent positions
        self.cash_reserve_pct = 0.10  # Keep 10% cash reserve
        
        logger.info("MockRiskManager initialized")
    
    def pre_trade_check(self, symbol: str, notional: float, side: str) -> Tuple[bool, str]:
        """Check if a trade is allowed based on risk limits."""
        
        # Kill switch check
        if self.kill_switch:
            return False, "Kill switch activated"
        
        # Daily halt check
        if self.daily_halted:
            return False, "Daily trading halted"
        
        # Basic checks that would be too complex to fully simulate:
        # - Portfolio concentration limits
        # - Sector exposure limits  
        # - Correlation limits
        # - VaR limits
        
        # For backtesting, we'll be more permissive but still enforce basic limits
        if notional <= 0:
            return False, "Invalid notional amount"
        
        # Position size check (simplified)
        if notional > 100000:  # Arbitrary large position limit for backtest
            return False, f"Position too large: ${notional:,.0f}"
        
        return True, "Approved"
    
    def get_size_multiplier(self) -> float:
        """Get current position sizing multiplier."""
        return self.size_multiplier
    
    def update_daily_pnl(self, pnl: float, equity: float):
        """Update daily P&L for risk monitoring (simplified for backtest)."""
        daily_return_pct = pnl / equity if equity > 0 else 0
        
        # Simplified daily halt logic
        if daily_return_pct < -0.02:  # -2% daily loss
            self.daily_halted = True
            logger.warning(f"Daily halt triggered at {daily_return_pct:.2%} loss")
    
    def reset_daily(self):
        """Reset daily risk state."""
        self.daily_halted = False
    
    def check_drawdown(self, current_equity: float, peak_equity: float):
        """Check maximum drawdown limits."""
        if peak_equity <= 0:
            return
        
        drawdown = (peak_equity - current_equity) / peak_equity
        
        if drawdown > 0.10:  # 10% max drawdown
            self.kill_switch = True
            logger.critical(f"Kill switch triggered at {drawdown:.2%} drawdown")
        elif drawdown > 0.05:  # 5% drawdown - reduce size
            self.size_multiplier = 0.5
            logger.warning(f"Size reduced to 50% at {drawdown:.2%} drawdown")
    
    def check_weekly_loss(self, weekly_return_pct: float):
        """Check weekly loss limits.""" 
        if weekly_return_pct < -0.05:  # -5% weekly loss
            self.size_multiplier = 0.5
            logger.warning(f"Size reduced to 50% due to {weekly_return_pct:.2%} weekly loss")