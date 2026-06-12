def calculate_position_size(account_equity: float, entry_price: float, atr: float, risk_pct: float = 0.01) -> int:
    """
    Risk Management: Size dynamically based on the Kelly Criterion or strict 1% account risk.
    Stop loss is dynamically placed at Entry - (1.5 * ATR).
    """
    risk_dollars = account_equity * risk_pct
    stop_distance = atr * 1.5
    
    if stop_distance <= 0:
        return 0
        
    shares = int(risk_dollars / stop_distance)
    return shares
