import yfinance as yf
import pandas as pd
import numpy as np

# 1. Download QQQ historical data
ticker = "QQQ"
df = yf.download(ticker, start="2000-01-01")

# Clean up multi-level columns if present in newer yfinance versions
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# 2. Calculate the 200-day moving average
df['200_DMA'] = df['Close'].rolling(window=200).mean()
df = df.dropna(subset=['200_DMA']).copy()

# 3. Generate Signals based on Close, to be executed the next day
df['Above_200'] = df['Close'] > df['200_DMA']
df['Position'] = df['Above_200'].shift(1).fillna(False).astype(int)

# 4. Track Trades and Generate Log Data
starting_capital = 10000
current_capital = starting_capital
in_position = False
shares_held = 0
entry_date = None
entry_price = 0

trade_log = []

# Iterate through the rows to capture exact next-day execution prices (Open price of the day)
for i in range(len(df)):
    date = df.index[i]
    pos_today = df['Position'].iloc[i]
    pos_prev = df['Position'].iloc[i-1] if i > 0 else 0
    open_price = df['Open'].iloc[i]
    close_price = df['Close'].iloc[i]
    
    # Update current capital if we are holding shares
    if in_position:
        # Evaluate performance using the daily closing price change
        prev_close = df['Close'].iloc[i-1]
        daily_return = (close_price - prev_close) / prev_close
        current_capital *= (1 + daily_return)

    # Trigger Entry: Position changed from 0 to 1
    if pos_today == 1 and pos_prev == 0 and not in_position:
        in_position = True
        entry_date = date
        entry_price = open_price # Executes the day after signal at the Open
        shares_held = current_capital / entry_price
        
    # Trigger Exit: Position changed from 1 to 0
    elif pos_today == 0 and pos_prev == 1 and in_position:
        exit_price = open_price # Executes the day after signal at the Open
        # Adjust capital to reflect the final exit execution price
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

# Final accounting if still in a trade at the end of the data stream
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

# Calculate Buy and Hold for comparison
bh_shares = starting_capital / df['Open'].iloc[0]
final_bh = bh_shares * df['Close'].iloc[-1]

# 5. Write the Log File
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
