"""
Performance Analyzer - Calculates trading performance metrics.

Computes standard metrics like total return, Sharpe ratio, max drawdown,
win rate, and other statistics from backtest results.
"""

import logging
from datetime import datetime
from typing import List, Dict, Tuple, Any
import pandas as pd
import numpy as np

logger = logging.getLogger("performance")


class PerformanceAnalyzer:
    """Analyzes trading performance from backtest results."""
    
    def __init__(self, risk_free_rate: float = 0.02):
        """Initialize analyzer with risk-free rate for Sharpe calculation."""
        self.risk_free_rate = risk_free_rate  # 2% annual risk-free rate
        logger.info(f"PerformanceAnalyzer initialized with {risk_free_rate:.1%} risk-free rate")
    
    def calculate_metrics(
        self, 
        portfolio_values: List[Tuple[datetime, float]], 
        trades: List[Dict], 
        initial_capital: float
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        
        if not portfolio_values:
            return self._empty_metrics()
        
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(portfolio_values, columns=['timestamp', 'portfolio_value'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        # Calculate returns
        df['returns'] = df['portfolio_value'].pct_change().fillna(0)
        daily_returns = self._resample_to_daily(df['returns'])
        
        # Basic metrics
        final_value = df['portfolio_value'].iloc[-1]
        total_return = (final_value - initial_capital) / initial_capital
        
        # Time-based metrics
        start_date = df.index[0]
        end_date = df.index[-1]
        total_days = (end_date - start_date).days
        annualized_return = (1 + total_return) ** (365 / total_days) - 1 if total_days > 0 else 0
        
        # Risk metrics
        volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 1 else 0
        sharpe_ratio = (annualized_return - self.risk_free_rate) / volatility if volatility > 0 else 0
        max_drawdown = self._calculate_max_drawdown(df['portfolio_value'])
        
        # Trade metrics
        trade_metrics = self._analyze_trades(trades)
        
        metrics = {
            # Returns
            'total_return': total_return,
            'annualized_return': annualized_return,
            'final_value': final_value,
            'initial_capital': initial_capital,
            
            # Risk
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            
            # Time
            'start_date': start_date,
            'end_date': end_date, 
            'total_days': total_days,
            
            # Trades
            'total_trades': trade_metrics['total_trades'],
            'winning_trades': trade_metrics['winning_trades'],
            'losing_trades': trade_metrics['losing_trades'],
            'win_rate': trade_metrics['win_rate'],
            'avg_trade_pnl': trade_metrics['avg_trade_pnl'],
            'avg_winning_trade': trade_metrics['avg_winning_trade'],
            'avg_losing_trade': trade_metrics['avg_losing_trade'],
            'profit_factor': trade_metrics['profit_factor'],
            'largest_winner': trade_metrics['largest_winner'],
            'largest_loser': trade_metrics['largest_loser'],
            
            # Additional metrics
            'calmar_ratio': annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0,
            'total_fees': sum(trade.get('commission', 0) for trade in trades),
        }
        
        logger.info(f"Calculated metrics: {total_return:.2%} return, {sharpe_ratio:.3f} Sharpe, "
                   f"{max_drawdown:.2%} max drawdown, {trade_metrics['total_trades']} trades")
        
        return metrics
    
    def combine_strategies(
        self, 
        strategy_results: Dict[str, Dict], 
        initial_capital: float
    ) -> Dict[str, Any]:
        """Combine multiple strategy results into portfolio metrics."""
        
        # For simplicity, assume equal allocation between strategies
        num_strategies = len(strategy_results)
        capital_per_strategy = initial_capital / num_strategies
        
        all_portfolio_values = []
        all_trades = []
        
        for strategy_name, result in strategy_results.items():
            # Scale portfolio values by allocation
            scaled_values = []
            for timestamp, value in result['portfolio_values']:
                # Scale based on allocated capital vs strategy's initial capital
                scale_factor = capital_per_strategy / result['initial_capital']
                scaled_value = (value - result['initial_capital']) * scale_factor + capital_per_strategy
                scaled_values.append((timestamp, scaled_value))
            
            all_portfolio_values.append(scaled_values)
            all_trades.extend(result['trades'])
        
        # Combine portfolio values by timestamp
        combined_values = self._combine_portfolio_values(all_portfolio_values, capital_per_strategy)
        
        # Calculate combined metrics
        return self.calculate_metrics(combined_values, all_trades, initial_capital)
    
    def _calculate_max_drawdown(self, portfolio_values: pd.Series) -> float:
        """Calculate maximum drawdown from portfolio value series."""
        peak = portfolio_values.expanding(min_periods=1).max()
        drawdown = (portfolio_values - peak) / peak
        return drawdown.min()  # Most negative value
    
    def _resample_to_daily(self, returns: pd.Series) -> pd.Series:
        """Resample returns to daily frequency."""
        if returns.empty:
            return returns
        
        # Group by date and compound returns within each day
        daily_returns = returns.groupby(returns.index.date).apply(
            lambda x: (1 + x).prod() - 1
        )
        
        return daily_returns
    
    def _analyze_trades(self, trades: List[Dict]) -> Dict[str, Any]:
        """Analyze individual trade performance."""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0, 
                'win_rate': 0,
                'avg_trade_pnl': 0,
                'avg_winning_trade': 0,
                'avg_losing_trade': 0,
                'profit_factor': 0,
                'largest_winner': 0,
                'largest_loser': 0,
            }
        
        # Group trades by symbol to calculate P&L per position
        positions = {}
        for trade in trades:
            symbol = trade['symbol']
            if symbol not in positions:
                positions[symbol] = []
            positions[symbol].append(trade)
        
        # Calculate P&L for each closed position
        trade_pnls = []
        for symbol, symbol_trades in positions.items():
            # Sort by timestamp
            symbol_trades.sort(key=lambda t: t['timestamp'])
            
            # Calculate P&L (simplified - assumes all positions are eventually closed)
            position_qty = 0
            position_cost = 0
            
            for trade in symbol_trades:
                if trade['side'].lower() in ['buy', 'long']:
                    position_qty += trade['qty']
                    position_cost += trade['qty'] * trade['price'] + trade['commission']
                else:
                    # Selling
                    qty_sold = min(abs(trade['qty']), position_qty)
                    if position_qty > 0:
                        avg_cost = position_cost / position_qty
                        pnl = qty_sold * (trade['price'] - avg_cost) - trade['commission']
                        trade_pnls.append(pnl)
                        
                        # Update position
                        position_qty -= qty_sold
                        position_cost -= qty_sold * avg_cost
        
        if not trade_pnls:
            return self._empty_trade_metrics()
        
        trade_pnls = np.array(trade_pnls)
        winning_trades = trade_pnls[trade_pnls > 0]
        losing_trades = trade_pnls[trade_pnls < 0]
        
        return {
            'total_trades': len(trade_pnls),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(trade_pnls) if trade_pnls.size > 0 else 0,
            'avg_trade_pnl': trade_pnls.mean(),
            'avg_winning_trade': winning_trades.mean() if len(winning_trades) > 0 else 0,
            'avg_losing_trade': losing_trades.mean() if len(losing_trades) > 0 else 0,
            'profit_factor': abs(winning_trades.sum() / losing_trades.sum()) if len(losing_trades) > 0 and losing_trades.sum() < 0 else 0,
            'largest_winner': trade_pnls.max(),
            'largest_loser': trade_pnls.min(),
        }
    
    def _combine_portfolio_values(
        self, 
        all_values: List[List[Tuple[datetime, float]]], 
        base_value: float
    ) -> List[Tuple[datetime, float]]:
        """Combine multiple portfolio value series."""
        # Convert to DataFrames and align timestamps
        dfs = []
        for i, values in enumerate(all_values):
            df = pd.DataFrame(values, columns=['timestamp', f'value_{i}'])
            df.set_index('timestamp', inplace=True)
            dfs.append(df)
        
        # Outer join to get all timestamps
        combined_df = pd.concat(dfs, axis=1, join='outer', sort=True)
        combined_df = combined_df.fillna(method='ffill').fillna(base_value)
        
        # Sum portfolio values
        combined_df['total'] = combined_df.sum(axis=1)
        
        # Convert back to list of tuples
        result = [(ts, val) for ts, val in combined_df['total'].items()]
        return result
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics dictionary."""
        return {
            'total_return': 0, 'annualized_return': 0, 'final_value': 0, 'initial_capital': 0,
            'volatility': 0, 'sharpe_ratio': 0, 'max_drawdown': 0,
            'start_date': None, 'end_date': None, 'total_days': 0,
            'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
            'win_rate': 0, 'avg_trade_pnl': 0, 'avg_winning_trade': 0, 'avg_losing_trade': 0,
            'profit_factor': 0, 'largest_winner': 0, 'largest_loser': 0,
            'calmar_ratio': 0, 'total_fees': 0
        }
    
    def _empty_trade_metrics(self) -> Dict[str, Any]:
        """Return empty trade metrics."""
        return {
            'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
            'win_rate': 0, 'avg_trade_pnl': 0, 'avg_winning_trade': 0, 'avg_losing_trade': 0,
            'profit_factor': 0, 'largest_winner': 0, 'largest_loser': 0
        }