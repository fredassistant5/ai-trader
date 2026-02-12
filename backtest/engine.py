"""
Backtesting Engine - Core replay logic that simulates the live trader.

Replays historical data through the actual strategy classes with mock clients
that simulate realistic fills, slippage, and commissions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from mock_client import MockAlpacaClient
from mock_data import MockMarketData
from mock_risk import MockRiskManager
from mock_state import MockStateManager

# Import actual strategies
from src.strategies.crypto_mean_reversion import CryptoMeanReversion
from src.strategies.equity_mean_reversion import EquityMeanReversion

logger = logging.getLogger("engine")


class BacktestEngine:
    """Main backtesting engine that orchestrates the simulation."""
    
    def __init__(self, initial_capital: float = 100000.0, commission_pct: float = 0.005, slippage_pct: float = 0.001):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        
        # Initialize mock components
        self.mock_client = MockAlpacaClient(initial_capital, commission_pct, slippage_pct)
        self.mock_data = MockMarketData()
        self.mock_risk = MockRiskManager()
        self.mock_state = MockStateManager()
        
        # Wire mock components together
        self.mock_data.set_mock_client(self.mock_client)
        
        # Results tracking
        self.portfolio_values: List[Tuple[datetime, float]] = []
        self.trades: List[Dict] = []
        
        logger.info(f"BacktestEngine initialized with ${initial_capital:,.2f} capital")
    
    def run(self, strategy_name: str, start_date: datetime, end_date: datetime) -> Dict:
        """Run backtest for a specific strategy over the given date range."""
        logger.info(f"Starting backtest: {strategy_name} from {start_date} to {end_date}")
        
        # Reset state
        self.mock_client.reset(self.initial_capital)
        self.mock_data.set_date_range(start_date, end_date)
        self.portfolio_values = []
        self.trades = []
        
        # Initialize strategy
        if strategy_name == "crypto_mean_reversion":
            strategy = CryptoMeanReversion(
                client=self.mock_client,
                market_data=self.mock_data,
                risk_manager=self.mock_risk,
                state_manager=self.mock_state
            )
            interval_minutes = 15  # Strategy runs on 15-min bars
            
        elif strategy_name == "equity_mean_reversion":
            strategy = EquityMeanReversion(
                client=self.mock_client,
                market_data=self.mock_data,
                risk_manager=self.mock_risk,
                state_manager=self.mock_state
            )
            interval_minutes = 5  # Strategy runs on 5-min bars
            
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        # Main simulation loop - step through time
        current_time = start_date
        step_size = timedelta(minutes=interval_minutes)
        last_date = None  # Track date changes for daily risk reset
        
        total_steps = int((end_date - start_date).total_seconds() / (interval_minutes * 60))
        step_count = 0
        
        logger.info(f"Simulating {total_steps:,} time steps of {interval_minutes} minutes each")
        
        while current_time < end_date:
            step_count += 1
            
            # Check for date boundary and reset daily risk controls
            current_date = current_time.date()
            if last_date is not None and current_date != last_date:
                self.mock_risk.reset_daily()
                logger.debug(f"Daily risk reset at {current_date}")
            last_date = current_date
            
            # Update mock data to current time
            self.mock_data.set_current_time(current_time)
            
            # Update account equity in mock client 
            self.mock_client.update_time(current_time)
            
            try:
                # Run strategy evaluation - this calls the actual strategy logic
                actions = strategy.run(current_time=current_time)
                
                # Process any actions (entries/exits)
                for action in actions:
                    self._process_action(action, current_time)
                
                # Record portfolio value
                account = self.mock_client.get_account()
                portfolio_value = float(account.equity)
                self.portfolio_values.append((current_time, portfolio_value))
                
                # Log progress periodically
                if step_count % 1000 == 0 or step_count == total_steps:
                    pct_complete = (step_count / total_steps) * 100
                    logger.info(f"Progress: {step_count:,}/{total_steps:,} steps ({pct_complete:.1f}%) - "
                              f"Portfolio: ${portfolio_value:,.2f}")
            
            except Exception as e:
                logger.warning(f"Error at {current_time}: {e}")
                # Continue simulation despite errors
            
            current_time += step_size
        
        # Get final trades from mock client
        self.trades = self.mock_client.get_trade_history()
        
        final_value = self.portfolio_values[-1][1] if self.portfolio_values else self.initial_capital
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        logger.info(f"Backtest completed - Final value: ${final_value:,.2f} "
                   f"(Return: {total_return:.2%}, Trades: {len(self.trades)})")
        
        return {
            'portfolio_values': self.portfolio_values,
            'trades': self.trades,
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'strategy': strategy_name
        }
    
    def _process_action(self, action: Dict, timestamp: datetime):
        """Process a strategy action (entry/exit/etc)."""
        action_type = action.get('action', '')
        symbol = action.get('symbol', '')
        
        # Log the action
        if 'enter' in action_type:
            qty = action.get('qty', 0)
            price = action.get('price', 0)
            logger.debug(f"{timestamp}: {action_type} {symbol} qty={qty} price=${price:.4f}")
        elif 'exit' in action_type:
            price = action.get('price', 0)
            logger.debug(f"{timestamp}: {action_type} {symbol} price=${price:.4f}")
        
        # Actions are already processed by the mock client during strategy.run()
        # This method is mainly for logging and could be extended for additional processing