"""
Report Generator - Creates backtest reports in text and CSV formats.

Generates comprehensive reports with performance metrics, trade logs,
and portfolio value charts.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any
import pandas as pd

logger = logging.getLogger("report")


class ReportGenerator:
    """Generates backtest reports."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ReportGenerator initialized, output dir: {self.output_dir}")
    
    def generate_report(
        self,
        strategy: str,
        metrics: Dict[str, Any],
        trades: List[Dict],
        portfolio_values: List[Tuple[datetime, float]],
        start_date: datetime,
        end_date: datetime
    ) -> Path:
        """Generate comprehensive report for a single strategy."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_prefix = f"{strategy}_{timestamp}"
        
        # Generate text summary
        summary_file = self.output_dir / f"{report_prefix}_summary.txt"
        self._generate_text_summary(summary_file, strategy, metrics, start_date, end_date)
        
        # Generate trades CSV
        trades_file = self.output_dir / f"{report_prefix}_trades.csv"
        self._generate_trades_csv(trades_file, trades)
        
        # Generate portfolio values CSV
        portfolio_file = self.output_dir / f"{report_prefix}_portfolio.csv"
        self._generate_portfolio_csv(portfolio_file, portfolio_values)
        
        logger.info(f"Generated reports: {summary_file.name}, {trades_file.name}, {portfolio_file.name}")
        
        return summary_file
    
    def generate_combined_report(
        self,
        metrics: Dict[str, Any],
        strategy_results: Dict[str, Dict],
        start_date: datetime,
        end_date: datetime
    ) -> Path:
        """Generate report for combined strategy portfolio."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_prefix = f"combined_portfolio_{timestamp}"
        
        # Generate text summary
        summary_file = self.output_dir / f"{report_prefix}_summary.txt"
        self._generate_combined_summary(summary_file, metrics, strategy_results, start_date, end_date)
        
        # Generate combined trades CSV
        all_trades = []
        for strategy_name, result in strategy_results.items():
            for trade in result['trades']:
                trade_copy = trade.copy()
                trade_copy['strategy'] = strategy_name
                all_trades.append(trade_copy)
        
        trades_file = self.output_dir / f"{report_prefix}_trades.csv"
        self._generate_trades_csv(trades_file, all_trades)
        
        logger.info(f"Generated combined reports: {summary_file.name}, {trades_file.name}")
        
        return summary_file
    
    def _generate_text_summary(
        self,
        file_path: Path,
        strategy: str,
        metrics: Dict[str, Any],
        start_date: datetime,
        end_date: datetime
    ):
        """Generate text summary report."""
        
        content = f"""
AI TRADER BACKTESTING REPORT
============================

Strategy: {strategy.upper()}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

PERIOD
------
Start Date: {start_date.strftime('%Y-%m-%d')}
End Date: {end_date.strftime('%Y-%m-%d')} 
Total Days: {metrics['total_days']:,}

PERFORMANCE SUMMARY
------------------
Initial Capital: ${metrics['initial_capital']:,.2f}
Final Value: ${metrics['final_value']:,.2f}
Total Return: {metrics['total_return']:.2%}
Annualized Return: {metrics['annualized_return']:.2%}

RISK METRICS
-----------
Volatility (Annual): {metrics['volatility']:.2%}
Sharpe Ratio: {metrics['sharpe_ratio']:.3f}
Maximum Drawdown: {metrics['max_drawdown']:.2%}
Calmar Ratio: {metrics['calmar_ratio']:.3f}

TRADING STATISTICS
-----------------
Total Trades: {metrics['total_trades']:,}
Winning Trades: {metrics['winning_trades']:,}
Losing Trades: {metrics['losing_trades']:,}
Win Rate: {metrics['win_rate']:.2%}

Average Trade P&L: ${metrics['avg_trade_pnl']:.2f}
Average Winning Trade: ${metrics['avg_winning_trade']:.2f}
Average Losing Trade: ${metrics['avg_losing_trade']:.2f}
Profit Factor: {metrics['profit_factor']:.2f}

Largest Winner: ${metrics['largest_winner']:.2f}
Largest Loser: ${metrics['largest_loser']:.2f}

COSTS
-----
Total Commissions: ${metrics['total_fees']:.2f}
Commission Impact: {metrics['total_fees']/metrics['initial_capital']:.3%} of capital

NOTES
-----
* Slippage and commissions are included in all calculations
* Returns are calculated on actual filled prices
* Risk metrics assume 252 trading days per year
* Sharpe ratio uses 2% risk-free rate
* Maximum drawdown measured from peak equity
"""
        
        with open(file_path, 'w') as f:
            f.write(content.strip())
        
        logger.info(f"Generated text summary: {file_path}")
    
    def _generate_combined_summary(
        self,
        file_path: Path,
        metrics: Dict[str, Any],
        strategy_results: Dict[str, Dict],
        start_date: datetime,
        end_date: datetime
    ):
        """Generate text summary for combined strategies."""
        
        # Individual strategy summaries
        strategy_summaries = []
        for strategy_name, result in strategy_results.items():
            final_val = result['portfolio_values'][-1][1] if result['portfolio_values'] else result['initial_capital']
            strategy_return = (final_val - result['initial_capital']) / result['initial_capital']
            trade_count = len(result['trades'])
            
            strategy_summaries.append(f"""
{strategy_name.upper()}:
  Return: {strategy_return:.2%}
  Trades: {trade_count:,}
  Final Value: ${final_val:,.2f}""")
        
        content = f"""
AI TRADER COMBINED PORTFOLIO BACKTESTING REPORT
==============================================

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
Strategies: {', '.join(strategy_results.keys())}

PERIOD
------
Start Date: {start_date.strftime('%Y-%m-%d')}
End Date: {end_date.strftime('%Y-%m-%d')}
Total Days: {metrics['total_days']:,}

COMBINED PERFORMANCE SUMMARY
---------------------------
Initial Capital: ${metrics['initial_capital']:,.2f}
Final Value: ${metrics['final_value']:,.2f}
Total Return: {metrics['total_return']:.2%}
Annualized Return: {metrics['annualized_return']:.2%}

COMBINED RISK METRICS
--------------------
Volatility (Annual): {metrics['volatility']:.2%}
Sharpe Ratio: {metrics['sharpe_ratio']:.3f}
Maximum Drawdown: {metrics['max_drawdown']:.2%}
Calmar Ratio: {metrics['calmar_ratio']:.3f}

COMBINED TRADING STATISTICS
--------------------------
Total Trades: {metrics['total_trades']:,}
Winning Trades: {metrics['winning_trades']:,}
Losing Trades: {metrics['losing_trades']:,}
Win Rate: {metrics['win_rate']:.2%}

Average Trade P&L: ${metrics['avg_trade_pnl']:.2f}
Profit Factor: {metrics['profit_factor']:.2f}

INDIVIDUAL STRATEGY PERFORMANCE
------------------------------{''.join(strategy_summaries)}

COSTS
-----
Total Commissions: ${metrics['total_fees']:.2f}
Commission Impact: {metrics['total_fees']/metrics['initial_capital']:.3%} of capital

NOTES
-----
* Portfolio assumes equal allocation between strategies
* All metrics include slippage and commissions
* Individual strategy results are scaled to portfolio allocation
* Risk metrics assume 252 trading days per year
"""
        
        with open(file_path, 'w') as f:
            f.write(content.strip())
        
        logger.info(f"Generated combined summary: {file_path}")
    
    def _generate_trades_csv(self, file_path: Path, trades: List[Dict]):
        """Generate CSV file with all trades."""
        
        if not trades:
            # Create empty CSV with headers
            df = pd.DataFrame(columns=[
                'timestamp', 'symbol', 'side', 'qty', 'price', 'notional', 'commission', 'strategy'
            ])
        else:
            df = pd.DataFrame(trades)
            
            # Ensure consistent columns
            required_columns = ['timestamp', 'symbol', 'side', 'qty', 'price', 'notional', 'commission']
            for col in required_columns:
                if col not in df.columns:
                    df[col] = None
            
            # Add strategy column if not present
            if 'strategy' not in df.columns:
                df['strategy'] = 'unknown'
            
            # Sort by timestamp
            if 'timestamp' in df.columns:
                df = df.sort_values('timestamp')
        
        df.to_csv(file_path, index=False)
        logger.info(f"Generated trades CSV: {file_path} ({len(trades)} trades)")
    
    def _generate_portfolio_csv(self, file_path: Path, portfolio_values: List[Tuple[datetime, float]]):
        """Generate CSV file with portfolio value over time."""
        
        df = pd.DataFrame(portfolio_values, columns=['timestamp', 'portfolio_value'])
        df.to_csv(file_path, index=False)
        logger.info(f"Generated portfolio CSV: {file_path} ({len(portfolio_values)} data points)")