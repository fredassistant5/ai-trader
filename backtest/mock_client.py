"""
Mock Alpaca Client - Simulates trading with realistic slippage and commissions.

Implements the same interface as the real AlpacaClient but tracks positions
and executes trades against historical data with realistic market impact.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import uuid

logger = logging.getLogger("mock_client")


@dataclass
class MockPosition:
    """Mock position that matches Alpaca position structure."""
    symbol: str
    qty: str  # String to match Alpaca API
    side: str
    market_value: str
    cost_basis: str
    unrealized_pl: str
    unrealized_plpc: str
    current_price: str


@dataclass 
class MockAccount:
    """Mock account that matches Alpaca account structure."""
    equity: str  # String to match Alpaca API
    cash: str
    portfolio_value: str
    buying_power: str
    long_market_value: str
    short_market_value: str


@dataclass
class MockOrder:
    """Mock order that matches Alpaca order structure."""
    id: str
    symbol: str
    qty: str
    side: str
    order_type: str
    status: str
    filled_avg_price: str = None
    filled_qty: str = None


class MockAlpacaClient:
    """Mock client that simulates Alpaca trading with realistic fills."""
    
    def __init__(self, initial_capital: float, commission_pct: float = 0.001, slippage_pct: float = 0.001):
        self.initial_capital = initial_capital
        self.crypto_commission_pct = commission_pct  # e.g., 0.001 = 0.1% for crypto
        self.equity_commission_pct = 0.0  # 0% for equities (like Alpaca)
        self.slippage_pct = slippage_pct      # e.g., 0.001 = 0.1%
        
        # State
        self.cash = initial_capital
        self.positions: Dict[str, MockPosition] = {}
        self.orders: List[MockOrder] = []
        self.trade_history: List[Dict] = []
        self.current_time: Optional[datetime] = None
        
        # For market data lookups
        self.current_prices: Dict[str, float] = {}
        
        logger.info(f"MockAlpacaClient initialized with ${initial_capital:,.2f}")
    
    def reset(self, initial_capital: float):
        """Reset client state for new backtest."""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions.clear()
        self.orders.clear() 
        self.trade_history.clear()
        self.current_prices.clear()
        self.current_time = None
    
    def update_time(self, current_time: datetime):
        """Update current time for the simulation."""
        self.current_time = current_time
        
        # Evaluate stop orders against current prices
        self._evaluate_stop_orders()
    
    def set_current_price(self, symbol: str, price: float):
        """Set current market price for a symbol (called by mock market data)."""
        self.current_prices[symbol] = price
    
    def _evaluate_stop_orders(self):
        """Evaluate stop orders against current prices and execute if triggered."""
        orders_to_fill = []
        
        for order in self.orders:
            if order.status != "new" or order.order_type != "stop":
                continue
                
            symbol = order.symbol
            if symbol not in self.current_prices:
                continue
                
            current_price = self.current_prices[symbol]
            
            # Check if we have an actual position to close
            if symbol not in self.positions:
                # Position was closed manually, cancel this stop order
                order.status = "cancelled"
                continue
            
            pos = self.positions[symbol]
            pos_qty = float(pos.qty)
            order_qty = float(order.qty)
            
            # Determine if stop should trigger based on position direction
            should_trigger = False
            
            if pos_qty > 0:  # Long position, stop loss triggers on price decline
                # Need to find stop price - simplified approach: assume 2% below entry
                entry_price = float(pos.cost_basis)
                stop_price = entry_price * 0.98  # 2% stop loss
                if current_price <= stop_price:
                    should_trigger = True
                    
            elif pos_qty < 0:  # Short position, stop triggers on price rise 
                entry_price = float(pos.cost_basis)
                stop_price = entry_price * 1.02  # 2% stop loss
                if current_price >= stop_price:
                    should_trigger = True
            
            if should_trigger:
                orders_to_fill.append(order)
        
        # Fill triggered stop orders
        for order in orders_to_fill:
            try:
                # Execute as market order
                symbol = order.symbol
                qty = float(order.qty)
                side = order.side
                
                # Determine correct quantity direction
                if symbol in self.positions:
                    pos_qty = float(self.positions[symbol].qty)
                    if pos_qty > 0 and side == "sell":
                        qty = pos_qty  # Close entire long position
                    elif pos_qty < 0 and side == "buy":
                        qty = abs(pos_qty)  # Close entire short position
                
                self.market_order(symbol, qty, side)
                order.status = "filled"
                order.filled_avg_price = str(self.current_prices[symbol])
                order.filled_qty = str(qty)
                
                logger.info(f"Stop order filled: {order.id} {symbol} {side} {qty} @ {self.current_prices[symbol]:.4f}")
                
            except Exception as e:
                logger.error(f"Failed to fill stop order {order.id}: {e}")
                order.status = "rejected"
    
    def market_order(self, symbol: str, qty: float, side: str) -> MockOrder:
        """Execute a market order with slippage."""
        if symbol not in self.current_prices:
            raise Exception(f"No price data available for {symbol}")
        
        base_price = self.current_prices[symbol]
        
        # Apply slippage (worse fill price)
        if side.lower() in ['buy', 'long']:
            fill_price = base_price * (1 + self.slippage_pct)
        else:
            fill_price = base_price * (1 - self.slippage_pct)
        
        # Calculate trade value and commission based on asset type
        notional = abs(qty) * fill_price
        
        # Use appropriate commission rate based on asset type
        if "/" in symbol or symbol in ["BTCUSD", "ETHUSD", "SOLUSD"]:
            commission = notional * self.crypto_commission_pct
        else:
            commission = notional * self.equity_commission_pct
        
        order_id = str(uuid.uuid4())[:8]
        
        # Execute the trade
        if side.lower() in ['buy', 'long']:
            # Check if we have enough cash
            total_cost = notional + commission
            if total_cost > self.cash:
                raise Exception(f"Insufficient cash: need ${total_cost:.2f}, have ${self.cash:.2f}")
            
            self.cash -= total_cost
            # Track cost basis WITHOUT commission to avoid double counting
            self._add_position(symbol, qty, fill_price, commission)
            
        else:  # sell/short
            # Check if we have the position to sell
            if symbol in self.positions:
                pos_qty = float(self.positions[symbol].qty)
                if abs(qty) > abs(pos_qty):
                    raise Exception(f"Insufficient position: trying to sell {qty}, have {pos_qty}")
            
            # Proceed with sale
            self.cash += (notional - commission)
            self._reduce_position(symbol, qty, fill_price, commission)
        
        # Record the trade
        self._record_trade(symbol, qty, fill_price, side, commission)
        
        order = MockOrder(
            id=order_id,
            symbol=symbol,
            qty=str(abs(qty)),
            side=side,
            order_type="market",
            status="filled",
            filled_avg_price=str(fill_price),
            filled_qty=str(abs(qty))
        )
        
        self.orders.append(order)
        return order
    
    def stop_order(self, symbol: str, qty: float, stop_price: float, side: str) -> MockOrder:
        """Create a stop order (for compatibility - simplified in backtest)."""
        order_id = str(uuid.uuid4())[:8]
        
        order = MockOrder(
            id=order_id,
            symbol=symbol, 
            qty=str(abs(qty)),
            side=side,
            order_type="stop",
            status="new"
        )
        
        self.orders.append(order)
        return order
    
    def close_position(self, symbol: str):
        """Close entire position in a symbol."""
        if symbol not in self.positions:
            raise Exception(f"No position in {symbol} to close")
        
        pos = self.positions[symbol]
        qty = float(pos.qty)
        
        if qty > 0:
            self.market_order(symbol, -qty, "sell")
        else:
            self.market_order(symbol, -qty, "buy")
    
    def cancel_order(self, order_id: str):
        """Cancel an order."""
        for order in self.orders:
            if order.id == order_id:
                order.status = "cancelled"
                return
        logger.warning(f"Order {order_id} not found for cancellation")
    
    def get_positions(self) -> List[MockPosition]:
        """Get current positions."""
        # Update unrealized P&L based on current prices
        for symbol, pos in self.positions.items():
            if symbol in self.current_prices:
                current_price = self.current_prices[symbol]
                qty = float(pos.qty)
                cost_basis = float(pos.cost_basis)
                current_value = qty * current_price
                unrealized_pl = current_value - (qty * cost_basis)
                unrealized_plpc = unrealized_pl / (qty * cost_basis) if cost_basis > 0 else 0
                
                pos.current_price = str(current_price)
                pos.market_value = str(abs(current_value))
                pos.unrealized_pl = str(unrealized_pl)
                pos.unrealized_plpc = str(unrealized_plpc)
        
        return list(self.positions.values())
    
    def get_account(self) -> MockAccount:
        """Get current account information."""
        positions = self.get_positions()
        
        long_market_value = sum(float(p.market_value) for p in positions if float(p.qty) > 0)
        short_market_value = sum(float(p.market_value) for p in positions if float(p.qty) < 0)
        portfolio_value = self.cash + long_market_value - short_market_value
        
        return MockAccount(
            equity=str(portfolio_value),
            cash=str(self.cash),
            portfolio_value=str(portfolio_value),
            buying_power=str(self.cash * 2),  # Simplified 2:1 margin
            long_market_value=str(long_market_value),
            short_market_value=str(short_market_value)
        )
    
    def get_trade_history(self) -> List[Dict]:
        """Get complete trade history."""
        return self.trade_history.copy()
    
    def _add_position(self, symbol: str, qty: float, price: float, commission: float = 0.0):
        """Add to position (or create new). Cost basis excludes commission to avoid double-counting."""
        if symbol in self.positions:
            # Add to existing position (average cost basis)
            existing = self.positions[symbol]
            existing_qty = float(existing.qty)
            existing_cost = float(existing.cost_basis)
            
            total_qty = existing_qty + qty
            # Cost basis weighted by quantity, excluding commission
            total_cost = (existing_qty * existing_cost + qty * price) / total_qty if total_qty != 0 else price
            
            self.positions[symbol].qty = str(total_qty)
            self.positions[symbol].cost_basis = str(total_cost)
        else:
            # Create new position - cost basis is just the fill price (no commission)
            self.positions[symbol] = MockPosition(
                symbol=symbol,
                qty=str(qty),
                side="long" if qty > 0 else "short",
                market_value=str(abs(qty * price)),
                cost_basis=str(price),  # Price only, commission handled separately
                unrealized_pl="0",
                unrealized_plpc="0",
                current_price=str(price)
            )
    
    def _reduce_position(self, symbol: str, qty_to_sell: float, price: float, commission: float = 0.0):
        """Reduce position (or remove if fully sold)."""
        if symbol in self.positions:
            pos = self.positions[symbol]
            current_qty = float(pos.qty)
            # Use absolute value to ensure we're always reducing, not increasing
            new_qty = current_qty - abs(qty_to_sell)
            
            if abs(new_qty) < 0.00001:  # Essentially zero - close position
                del self.positions[symbol]
            else:
                pos.qty = str(new_qty)
                pos.side = "long" if new_qty > 0 else "short"
    
    def _record_trade(self, symbol: str, qty: float, price: float, side: str, commission: float):
        """Record a trade in history."""
        trade = {
            'timestamp': self.current_time,
            'symbol': symbol,
            'qty': qty,
            'price': price, 
            'side': side,
            'commission': commission,
            'notional': abs(qty) * price
        }
        self.trade_history.append(trade)