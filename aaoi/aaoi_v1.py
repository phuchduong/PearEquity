"""
================================================================================
BACKTEST SCRIPT: AAOI EXIT STRATEGY OPTIMIZATION
================================================================================
Objective:
    Evaluate and determine the optimal exit strategy for Applied Optoelectronics 
    (AAOI) using a Donchian breakout entry system paired with a monthly performance-
    based pyramiding ruleset.

Backtest Parameters & Logic:
    1. Ticker: AAOI
    2. Testing Window: January 1, 2015 - August 4, 2026
    
    3. Initial Entry:
       - Triggered when price breaks out above the 55-day Donchian High Channel 
         (pre-calculated with shift(1) to avoid lookahead bias).
       - Buys an initial position of 1 share when no active position exists.

    4. Position Scaling (Pyramiding):
       - Checked every 30 calendar days while a position is active.
       - Condition: Stock must show > 5% price appreciation since the last 
         buy/check point.
       - Action: Add at least $1,000 in whole share increments.

    5. Exit Strategies Evaluated:
       - 3x ATR: Trailing stop based on 3x 14-day ATR off trade high.
       - 5x ATR: Trailing stop based on 5x 14-day ATR off trade high.
       - 100 DMA: Exit when daily close falls below the 100-day Simple Moving Average.
       - 200 DMA: Exit when daily close falls below the 200-day Simple Moving Average.
       - HOLD: Never exit (buy and hold baseline).
================================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# ==========================================
# 1. FETCH & PREPARE DATA
# ==========================================
symbol = "AAOI"
start_date = "2014-06-01"  # Extra lookback buffer for 200 DMA & 55-day Donchian
end_date = "2026-08-04"

print(f"Fetching data for {symbol}...")
df = yf.download(symbol, start=start_date, end=end_date, progress=False)

# Handle multi-level column indexing if present in newer yfinance versions
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Calculate Technical Indicators
# 55-day high (Shifted by 1 to avoid lookahead bias)
df['Donchian_55'] = df['High'].shift(1).rolling(window=55).max()

# Moving Averages
df['SMA_100'] = df['Close'].rolling(window=100).mean()
df['SMA_200'] = df['Close'].rolling(window=200).mean()

# True Range & 14-period ATR
df['Prev_Close'] = df['Close'].shift(1)
df['TR'] = np.maximum(
    df['High'] - df['Low'],
    np.maximum(
        (df['High'] - df['Prev_Close']).abs(),
        (df['Low'] - df['Prev_Close']).abs()
    )
)
df['ATR_14'] = df['TR'].rolling(window=14).mean()

# Filter dataset to actual target backtest window
df_backtest = df.loc['2015-01-01':].copy()

# ==========================================
# 2. BACKTEST ENGINE
# ==========================================
def run_backtest(data, exit_strategy_type):
    """
    exit_strategy_type: 
      - '3x_ATR'
      - '5x_ATR'
      - '100_DMA'
      - '200_DMA'
      - 'HOLD'
    """
    position_shares = 0
    total_invested_cash = 0.0
    cash_realized_pnl = 0.0
    trades = []
    
    # State tracking
    highest_price_in_trade = 0.0
    last_buy_date = None
    last_buy_price_for_monthly_check = 0.0
    current_trade_cost = 0.0
    
    portfolio_history = []

    for date, row in data.iterrows():
        price = row['Close']
        high = row['High']
        low = row['Low']
        donchian = row['Donchian_55']
        sma_100 = row['SMA_100']
        sma_200 = row['SMA_200']
        atr = row['ATR_14']
        
        # Skip if necessary indicators are incomplete
        if pd.isna(donchian) or pd.isna(sma_200) or pd.isna(atr):
            portfolio_history.append({'Date': date, 'Portfolio_Value': 0.0, 'Invested': 0.0})
            continue

        # ----------------------------------
        # CHECK EXIT STRATEGY (If holding)
        # ----------------------------------
        exit_triggered = False
        
        if position_shares > 0:
            highest_price_in_trade = max(highest_price_in_trade, high)
            
            if exit_strategy_type == '3x_ATR':
                trailing_stop = highest_price_in_trade - (3 * atr)
                if low <= trailing_stop:
                    exit_triggered = True
            elif exit_strategy_type == '5x_ATR':
                trailing_stop = highest_price_in_trade - (5 * atr)
                if low <= trailing_stop:
                    exit_triggered = True
            elif exit_strategy_type == '100_DMA':
                if price < sma_100:
                    exit_triggered = True
            elif exit_strategy_type == '200_DMA':
                if price < sma_200:
                    exit_triggered = True
            elif exit_strategy_type == 'HOLD':
                exit_triggered = False  # Never sell

            if exit_triggered:
                # Sell all position
                proceeds = position_shares * price
                trade_pnl = proceeds - current_trade_cost
                cash_realized_pnl += trade_pnl
                
                trades.append({
                    'Exit_Date': date,
                    'Shares': position_shares,
                    'Exit_Price': price,
                    'Invested_Capital': current_trade_cost,
                    'PnL': trade_pnl,
                    'Return_%': (trade_pnl / current_trade_cost) * 100
                })
                
                # Reset state
                position_shares = 0
                current_trade_cost = 0.0
                highest_price_in_trade = 0.0
                last_buy_date = None

        # ----------------------------------
        # CHECK ENTRY & RE-ENTRY
        # ----------------------------------
        if position_shares == 0:
            # Rule 3: Entry when no position & 55-day high break
            if price > donchian:
                position_shares = 1  # Initial 1 share purchase
                total_invested_cash += price
                current_trade_cost = price
                highest_price_in_trade = high
                last_buy_date = date
                last_buy_price_for_monthly_check = price
        else:
            # Rule 4: Pyramiding - Check every 30 calendar days
            days_since_last_buy = (date - last_buy_date).days
            if days_since_last_buy >= 30:
                # Check > 5% appreciation since last check/buy
                appreciation = (price - last_buy_price_for_monthly_check) / last_buy_price_for_monthly_check
                if appreciation > 0.05:
                    # Buy at least $1000 in whole share increments
                    shares_to_buy = max(1, int(1000 // price))
                    cost = shares_to_buy * price
                    
                    position_shares += shares_to_buy
                    total_invested_cash += cost
                    current_trade_cost += cost
                    
                    last_buy_date = date
                    last_buy_price_for_monthly_check = price

        # Track daily equity
        current_val = position_shares * price
        portfolio_history.append({
            'Date': date,
            'Portfolio_Value': current_val,
            'Realized_PnL': cash_realized_pnl,
            'Invested_Capital': total_invested_cash
        })

    history_df = pd.DataFrame(portfolio_history).set_index('Date')
    return history_df, pd.DataFrame(trades), total_invested_cash

# ==========================================
# 3. RUN ALL STRATEGIES & COMPARE
# ==========================================
strategies = ['3x_ATR', '5x_ATR', '100_DMA', '200_DMA', 'HOLD']
results = {}

print("\nRunning Backtests...")
for strat in strategies:
    hist, trades, total_inv = run_backtest(df_backtest, strat)
    
    final_val = hist['Portfolio_Value'].iloc[-1]
    total_realized_pnl = hist['Realized_PnL'].iloc[-1]
    
    # Net PnL = (Current Equity + Realized PnL from past exits) - Total Cash Invested
    net_pnl = (final_val + total_realized_pnl) - total_inv
    roi = (net_pnl / total_inv * 100) if total_inv > 0 else 0
    
    num_trades = len(trades)
    win_rate = (len(trades[trades['PnL'] > 0]) / num_trades * 100) if num_trades > 0 else 0
    
    results[strat] = {
        'Total Invested ($)': round(total_inv, 2),
        'Final Equity ($)': round(final_val, 2),
        'Realized PnL ($)': round(total_realized_pnl, 2),
        'Net Profit ($)': round(net_pnl, 2),
        'ROI (%)': round(roi, 2),
        'Total Exits': num_trades,
        'Win Rate (%)': round(win_rate, 2)
    }

# Display Summary Table
summary_df = pd.DataFrame(results).T
print("\n" + "="*70)
print("             AAOI EXIT STRATEGY BACKTEST RESULTS (2015 - 2026)")
print("="*70)
print(summary_df.to_string())
print("="*70)

# Optional Plotting
plt.figure(figsize=(12, 6))
for strat in strategies:
    hist, _, _ = run_backtest(df_backtest, strat)
    plt.plot(hist.index, hist['Portfolio_Value'] + hist['Realized_PnL'] - hist['Invested_Capital'], label=strat)

plt.title("AAOI Strategy Comparison: Cumulative Net PnL ($)")
plt.xlabel("Date")
plt.ylabel("Net Profit / Loss ($)")
plt.legend()
plt.grid(True)
plt.show()


'''
======================================================================
             AAOI EXIT STRATEGY BACKTEST RESULTS (2015 - 2026)
======================================================================
         Total Invested ($)  Final Equity ($)  Realized PnL ($)  Net Profit ($)  ROI (%)  Total Exits  Win Rate (%)
3x_ATR             10653.83              0.00            904.60        -9749.23   -91.51         38.0         34.21
5x_ATR             26823.13              0.00           2860.97       -23962.16   -89.33         21.0         28.57
100_DMA            32499.08              0.00           8623.64       -23875.44   -73.46         20.0         30.00
200_DMA            28748.54              0.00            825.99       -27922.54   -97.13         30.0         33.33
HOLD               17430.92          63040.12              0.00        45609.20   261.66          0.0          0.00
======================================================================
'''
