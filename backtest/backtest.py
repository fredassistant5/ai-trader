#!/usr/bin/env python3
"""
AI Trader Backtesting Framework

Replays the EXACT same strategies from the live trader against historical data.
Simulates fills with realistic slippage and commission modeling.

Usage:
    python backtest.py --strategy crypto_mean_reversion --start 2025-01-01 --end 2026-02-01
    python backtest.py --strategy equity_mean_reversion --start 2025-06-01 --end 2025-12-31
    python backtest.py --strategy all --start 2025-01-01 --end 2026-01-31
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add the parent directory to path to import from src/
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from engine import BacktestEngine
from performance import PerformanceAnalyzer
from report import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "backtest.log")
    ]
)

logger = logging.getLogger("backtest")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AI Trader Backtesting Framework")
    
    parser.add_argument(
        "--strategy", 
        required=True,
        choices=["crypto_mean_reversion", "equity_mean_reversion", "all"],
        help="Strategy to backtest"
    )
    
    parser.add_argument(
        "--start", 
        required=True,
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--end", 
        required=True, 
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--initial-capital", 
        type=float, 
        default=100000.0,
        help="Initial capital (default: $100,000)"
    )
    
    parser.add_argument(
        "--commission", 
        type=float, 
        default=0.001,
        help="Commission per trade as percentage (default: 0.001 = 0.1% for crypto, 0.0% for equities)"
    )
    
    parser.add_argument(
        "--slippage", 
        type=float, 
        default=0.001,
        help="Slippage per trade as percentage (default: 0.001 = 0.1%)"
    )
    
    parser.add_argument(
        "--output-dir", 
        type=str, 
        default=None,
        help="Output directory for results (default: ./results/)"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


def validate_dates(start_str: str, end_str: str) -> tuple[datetime, datetime]:
    """Validate and parse date strings."""
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        sys.exit(1)
    
    if start >= end:
        logger.error("Start date must be before end date")
        sys.exit(1)
    
    return start, end


def main():
    """Main backtesting entry point."""
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate inputs
    start_date, end_date = validate_dates(args.start, args.end)
    
    # Set up output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting backtest: {args.strategy} from {args.start} to {args.end}")
    logger.info(f"Initial capital: ${args.initial_capital:,.2f}")
    logger.info(f"Commission: {args.commission:.3%}, Slippage: {args.slippage:.3%}")
    
    try:
        # Initialize backtest engine
        engine = BacktestEngine(
            initial_capital=args.initial_capital,
            commission_pct=args.commission,
            slippage_pct=args.slippage
        )
        
        # Run the backtest
        if args.strategy == "all":
            strategies = ["crypto_mean_reversion", "equity_mean_reversion"]
        else:
            strategies = [args.strategy]
        
        results = {}
        for strategy in strategies:
            logger.info(f"Running backtest for strategy: {strategy}")
            result = engine.run(strategy, start_date, end_date)
            results[strategy] = result
        
        # Analyze performance
        analyzer = PerformanceAnalyzer()
        
        # Generate reports for each strategy
        for strategy, result in results.items():
            logger.info(f"Analyzing performance for {strategy}")
            
            metrics = analyzer.calculate_metrics(
                result['portfolio_values'],
                result['trades'],
                args.initial_capital
            )
            
            # Generate report
            report_gen = ReportGenerator(output_dir)
            report_file = report_gen.generate_report(
                strategy=strategy,
                metrics=metrics,
                trades=result['trades'],
                portfolio_values=result['portfolio_values'],
                start_date=start_date,
                end_date=end_date
            )
            
            logger.info(f"Report generated: {report_file}")
            
            # Print summary to console
            print(f"\n=== {strategy.upper()} RESULTS ===")
            print(f"Total Return: {metrics['total_return']:.2%}")
            print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.3f}")
            print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
            print(f"Win Rate: {metrics['win_rate']:.2%}")
            print(f"Total Trades: {metrics['total_trades']}")
            print(f"Avg Trade P&L: ${metrics['avg_trade_pnl']:.2f}")
        
        # If running all strategies, create a combined report
        if len(results) > 1:
            logger.info("Generating combined strategy report")
            combined_metrics = analyzer.combine_strategies(results, args.initial_capital)
            
            report_gen = ReportGenerator(output_dir)
            combined_file = report_gen.generate_combined_report(
                combined_metrics,
                results,
                start_date,
                end_date
            )
            
            logger.info(f"Combined report generated: {combined_file}")
            
            print(f"\n=== COMBINED PORTFOLIO RESULTS ===")
            print(f"Total Return: {combined_metrics['total_return']:.2%}")
            print(f"Sharpe Ratio: {combined_metrics['sharpe_ratio']:.3f}")
            print(f"Max Drawdown: {combined_metrics['max_drawdown']:.2%}")
    
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info("Backtest completed successfully!")


if __name__ == "__main__":
    main()