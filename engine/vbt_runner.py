import vectorbt as vbt
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any

def run_backtest(symbol: str, strategy: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # Download data using yfinance
    data = yf.download(symbol, start="2022-01-01", progress=False)
    if data.empty:
        raise ValueError(f"No data found for symbol {symbol}")
        
    close = data['Close']

    if strategy == "RSI_DIVERGENCE":
        rsi_period = int(params.get("rsi_period", 14))
        rsi = vbt.RSI.run(close, window=rsi_period)
        
        # Simple Logic: Buy when RSI < 30, Sell when RSI > 70
        entries = rsi.rsi_below(30)
        exits = rsi.rsi_above(70)
        
    elif strategy == "EMA_CROSS":
        fast_period = int(params.get("fast_period", 10))
        slow_period = int(params.get("slow_period", 50))
        fast_ma = vbt.MA.run(close, window=fast_period)
        slow_ma = vbt.MA.run(close, window=slow_period)
        
        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)
    else:
        raise ValueError(f"Unknown strategy {strategy}")

    # Run Portfolio
    portfolio = vbt.Portfolio.from_signals(
        close, 
        entries, 
        exits, 
        init_cash=10000, 
        fees=0.001
    )
    
    # Calculate stats safely
    try:
        stats = portfolio.stats()
        # Convert index to native types if needed
        total_return = round(stats.get('Total Return [%]', 0.0), 2)
        win_rate = round(stats.get('Win Rate [%]', 0.0), 2)
        max_drawdown = round(stats.get('Max Drawdown [%]', 0.0), 2)
        expectancy = round(stats.get('Expectancy', 0.0), 2)
        sharpe_ratio = round(stats.get('Sharpe Ratio', 0.0), 2)
    except Exception:
        total_return = win_rate = max_drawdown = expectancy = sharpe_ratio = 0.0
    
    # Extract equity curve
    try:
        equity_curve = portfolio.value()
        # Ensure flat series (yf downloads sometimes have MultiIndex columns)
        if isinstance(equity_curve, pd.DataFrame):
            equity_curve = equity_curve.iloc[:, 0]
        curve_data = [{"date": str(idx.date()), "value": float(val)} for idx, val in equity_curve.items()]
    except Exception:
        curve_data = []
    
    return {
        "symbol": symbol,
        "strategy": strategy,
        "total_return": float(total_return) if not np.isnan(total_return) else 0.0,
        "win_rate": float(win_rate) if not np.isnan(win_rate) else 0.0,
        "max_drawdown": float(max_drawdown) if not np.isnan(max_drawdown) else 0.0,
        "expectancy": float(expectancy) if not np.isnan(expectancy) else 0.0,
        "sharpe_ratio": float(sharpe_ratio) if not np.isnan(sharpe_ratio) else 0.0,
        "equity_curve": curve_data
    }
