import os
import sys
from datetime import datetime
import pandas as pd
import yfinance as yf

# Configure logging to a file named after this script plus 'log' and current timestamp
script_name = os.path.splitext(os.path.basename(__file__))[0]
timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"{script_name}_log_{timestamp_str}.txt"

class Tee:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Tee(log_filename)

print(f"Log file created: {log_filename}")
print(f"Execution started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Parameters
START_DATE = "2021-08-01"
END_DATE = "2026-08-01"
INITIAL_CAPITAL = 200000.0
TICKERS = ["QQQ", "VOO", "VTI", "SOXQ", "RSP"]

def run_backtest(ticker, initial_capital, start_date, end_date):
    print(f"\n==================================================")
    print(f"STARTING BACKTEST FOR STRATEGY: BUY AND HOLD {ticker}")
    print(f"==================================================")

    # Download historical price and dividend/split data.
    # BUG FIX #1: actions=True is required or yfinance never returns a
    # 'Dividends' column, so the old code silently treated every ticker
    # as if it paid $0 in dividends.
    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False,
                        actions=True, progress=False)

    if data.empty:
        print(f"Error: No data retrieved for {ticker}.")
        return None

    # Flatten multi-index columns if present in newer yfinance versions
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Ensure required columns exist
    if 'Adj Close' not in data.columns:
        data['Adj Close'] = data['Close']
    if 'Dividends' not in data.columns:
        # Legitimately no dividend data available for this ticker/date range
        data['Dividends'] = 0.0

    cash = initial_capital
    shares = 0.0

    # Initial Buy on the first available trading day
    first_date = data.index[0]
    initial_price = float(data.loc[first_date, 'Close'])

    # Spend entire starting capital
    shares = cash / initial_price
    cash = 0.0

    print(f"[{first_date.strftime('%Y-%m-%d')}] INITIAL BUY: Purchased {shares:.4f} shares of {ticker} at ${initial_price:.2f} per share. Total invested: ${initial_price * shares:,.2f}.")

    # Iterate through each trading day to handle dividend reinvestment
    for date, row in data.iterrows():
        if date == first_date:
            continue

        dividend_rate = float(row['Dividends'])
        if dividend_rate > 0:
            div_amount = shares * dividend_rate
            current_close = float(row['Close'])

            # Vanguard automatic dividend reinvestment: purchase fractional
            # shares immediately with the cash dividend.
            additional_shares = div_amount / current_close
            shares += additional_shares

            # BUG FIX #2: previously 'cash' was never reset to 0 after being
            # used to buy shares, so leftover cash from earlier dividends
            # kept accumulating and got "reinvested" again at every
            # subsequent dividend date, inflating share counts. Dividends
            # are spent immediately and cash stays at 0 throughout.
            cash = 0.0

            print(f"[{date.strftime('%Y-%m-%d')}] DIVIDEND REINVESTMENT: Received ${div_amount:,.2f} dividends (${dividend_rate:.4f}/share). Purchased {additional_shares:.4f} shares at ${current_close:.2f}. Total shares now: {shares:.4f}.")

    # Final Portfolio Valuation
    final_date = data.index[-1]
    final_close = float(data.loc[final_date, 'Close'])
    final_portfolio_value = (shares * final_close) + cash
    total_return_pct = ((final_portfolio_value - initial_capital) / initial_capital) * 100

    print(f"\n--- PERFORMANCE SUMMARY FOR {ticker} ---")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Final Portfolio Value: ${final_portfolio_value:,.2f}")
    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Final Share Count: {shares:.4f}")
    print(f"Final Closing Price ({final_date.strftime('%Y-%m-%d')}): ${final_close:.2f}")

    return {
        "Ticker": ticker,
        "Initial Capital": initial_capital,
        "Final Value": final_portfolio_value,
        "Total Return (%)": total_return_pct,
        "Final Shares": shares
    }

results = []

for ticker in TICKERS:
    result = run_backtest(ticker, INITIAL_CAPITAL, START_DATE, END_DATE)
    if result:
        results.append(result)

print(f"\n==================================================")
print("FINAL COMPARATIVE RESULTS ACROSS ALL STRATEGIES")
print(f"==================================================")

results_df = pd.DataFrame(results)

# Format columns for display and logging output
results_df["Initial Capital"] = results_df["Initial Capital"].map("${:,.2f}".format)
results_df["Final Value"] = results_df["Final Value"].map("${:,.2f}".format)
results_df["Total Return (%)"] = results_df["Total Return (%)"].map("{:.2f}%".format)
results_df["Final Shares"] = results_df["Final Shares"].map("{:.4f}".format)

print(results_df.to_string(index=False))

print(f"\nExecution finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")