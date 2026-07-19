"""
================================================================================
STRATEGY BACKTESTER: QQQ TREND FOLLOWING (CHANDELIER STOP EXIT)
================================================================================
Asset:          QQQ (Invesco QQQ Trust)
Starting Capital: $10,000
Data Source:    Yahoo Finance (yfinance)

STRATEGY RULES:
--------------------------------------------------------------------------------
[ENTRY CONDITION]
Execute a LONG position at the market OPEN the day after BOTH of these conditions 
are met at the market close:
  1. The closing price is above the 200-day Moving Average (DMA).
  2. The 50-day Moving Average is greater than the 200-day Moving Average.

[EXIT CONDITION]
Liquidate the position to 100% CASH at the market OPEN the day after:
  1. The closing price drops below the Chandelier Stop level (20-day highest 
     high minus 3x the 20-day ATR).

[LOGGING]
Outputs a 'backtest_log.txt' file featuring a high-level performance overview 
compared against a standard Buy & Hold strategy, accompanied by a sequential 
transaction ledger recording entry/exit metrics and net dollar gains/losses.
================================================================================
"""

import yfinance as yf
import pandas as pd
import numpy as np

# 1. Download QQQ historical data
ticker = "QQQ"
df = yf.download(ticker, start="2000-01-01")

# Clean up multi-level columns if present in newer yfinance versions
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 2. Calculate the moving averages and Chandelier Stop components
df['50_DMA'] = df['Close'].rolling(window=50).mean()
df['200_DMA'] = df['Close'].rolling(window=200).mean()

# True Range and ATR calculations (20 trading day lookback)
df['High_Low'] = df['High'] - df['Low']
df['High_PrevClose'] = (df['High'] - df['Close'].shift(1)).abs()
df['Low_PrevClose'] = (df['Low'] - df['Close'].shift(1)).abs()
df['TR'] = df[['High_Low', 'High_PrevClose', 'Low_PrevClose']].max(axis=1)
df['ATR_20'] = df['TR'].rolling(window=20).mean()

# Chandelier Stop Formula: 20-day Highest High - 3 * 20-day ATR
df['Max_High_20'] = df['High'].rolling(window=20).max()
df['Chandelier_Stop'] = df['Max_High_20'] - (3 * df['ATR_20'])

# Drop rows without enough data to calculate all indicators safely
df = df.dropna(subset=['200_DMA', 'Chandelier_Stop']).copy()

# 3. Generate Signals sequentially to track the active trailing stop state
signals = []
current_state = 0  # 0 means in cash, 1 means in position

for i in range(len(df)):
    close_price = df['Close'].iloc[i]
    ma50 = df['50_DMA'].iloc[i]
    ma200 = df['200_DMA'].iloc[i]
    c_stop = df['Chandelier_Stop'].iloc[i]
    
    if current_state == 0:
        # Check Entry Conditions
        if close_price > ma200 and ma50 > ma200:
            current_state = 1
    else:
        # Check Exit Condition: Close drops below Chandelier Stop
        if close_price < c_stop:
            current_state = 0
            
    signals.append(current_state)

df['Signal_Today'] = signals

# Shift by 1 day to execute at tomorrow's market open
df['Position'] = df['Signal_Today'].shift(1).fillna(0).astype(int)

# 4. Track Trades and Generate Log Data
starting_capital = 10000
current_capital = starting_capital
in_position = False
shares_held = 0
entry_date = None
entry_price = 0

trade_log = []

# Iterate through rows to calculate next-day market execution metrics
for i in range(len(df)):
    date = df.index[i]
    pos_today = df['Position'].iloc[i]
    pos_prev = df['Position'].iloc[i-1] if i > 0 else 0
    open_price = df['Open'].iloc[i]
    close_price = df['Close'].iloc[i]
    
    # Update portfolio equity based on market performance if currently holding shares
    if in_position:
        prev_close = df['Close'].iloc[i-1]
        daily_return = (close_price - prev_close) / prev_close
        current_capital *= (1 + daily_return)

    # Trigger Entry: Position shifts from 0 to 1
    if pos_today == 1 and pos_prev == 0 and not in_position:
        in_position = True
        entry_date = date
        entry_price = open_price  # Executes at market Open the day after signal
        shares_held = current_capital / entry_price
        
    # Trigger Exit: Position shifts from 1 to 0
    elif pos_today == 0 and pos_prev == 1 and in_position:
        exit_price = open_price  # Executes at market Open the day after signal
        trade_return = (exit_price - df['Close'].iloc[i-1]) / df['Close'].iloc[i-1]
        current_capital *= (1 + trade_return)
        
        gain_loss = current_capital - (shares_held * entry_price)
        
        trade_log.append({
            'Type': 'TRADE',
            'Entry Date': entry_date.strftime('%Y-%m-%d'),
            'Entry Price': f"${entry_price:.2f}",
            'Exit Date': date.strftime('%Y-%m-%d'),
            'Exit Price': f"${exit_price:.2f}",
            'Gain/Loss ($)': f"${gain_loss:,.2f}"
        })
        
        in_position = False
        shares_held = 0

# Adjust account totals if a trade remains open at the conclusion of the backtest
if in_position:
    exit_price = df['Close'].iloc[-1]
    gain_loss = current_capital - (shares_held * entry_price)
    trade_log.append({
        'Type': 'OPEN POSITION',
        'Entry Date': entry_date.strftime('%Y-%m-%d'),
        'Entry Price': f"${entry_price:.2f}",
        'Exit Date': df.index[-1].strftime('%Y-%m-%d'),
        'Exit Price': f"${exit_price:.2f} (Current Close)",
        'Gain/Loss ($)': f"${gain_loss:,.2f}"
    })

# Calculate basic Buy and Hold strategy results for reference benchmarks
bh_shares = starting_capital / df['Open'].iloc[0]
final_bh = bh_shares * df['Close'].iloc[-1]

# 5. Write performance documentation out to text file
log_filename = "backtest_log.txt"
with open(log_filename, "w") as f:
    f.write("==================================================\n")
    f.write(f"           BACKTEST RESULTS: {ticker}\n")
    f.write("==================================================\n")
    f.write(f"Starting Capital:          ${starting_capital:,.2f}\n")
    f.write(f"Final Strategy Value:      ${current_capital:,.2f}\n")
    f.write(f"Final Buy & Hold Value:    ${final_bh:,.2f}\n")
    f.write(f"Total Completed Trades:    {len(trade_log)}\n\n")
    
    f.write("==================================================\n")
    f.write("           DETAILED TRANSACTION LOG\n")
    f.write("==================================================\n")
    
    for t in trade_log:
        f.write(f"Type:        {t['Type']}\n")
        f.write(f"Entry Date:  {t['Entry Date']} @ {t['Entry Price']}\n")
        f.write(f"Exit Date:   {t['Exit Date']} @ {t['Exit Price']}\n")
        f.write(f"Gain/Loss:   {t['Gain/Loss ($)']}\n")
        f.write("--------------------------------------------------\n")

print(f"Backtest complete. Detailed results written to {log_filename}")
