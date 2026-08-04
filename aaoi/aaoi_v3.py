"""
================================================================================
BACKTEST SCRIPT: AAOI MACRO REGIME & STAGNATION EXIT COMPARISON
================================================================================
EXECUTIVE SUMMARY & OBJECTIVE:
    Applied Optoelectronics (AAOI) is a hyper-volatile stock that experiences 
    massive multi-year bull runs followed by severe 80%+ multi-year drawdowns 
    (such as the 2018–2023 slump). 

    While buying and holding AAOI can produce high long-term paper gains, it suffers 
    from severe "Opportunity Cost of Capital"—tying up funds in dead-money or 
    declining assets for years when that capital could be earning returns elsewhere.

    The objective of this script is to compare a "Buy & Hold" base strategy 
    against 3 macro-level exit engines designed to liquidate positions when the 
    macro regime turns bearish or stagnant, freeing up capital while avoiding 
    daily whipsaw exits.

================================================================================
STRATEGIES EVALUATED:

1. BASE STRATEGY: Donchian Momentum + Pyramiding + Buy & Hold
   - Purpose: Benchmark momentum strategy without exits.
   - Entry: Buy 1 share on a 55-day Donchian High breakout.
   - Pyramiding: Every 30 days, if price is >5% above the last check/buy point, 
     add $1,000 worth of shares.
   - Exit: Never exit (Hold indefinitely).

2. STRATEGY 1: Macro Regime Exit (50 / 200 SMA Death Cross Filter)
   - Purpose: Exit entire position when the macro market turns bearish.
   - Mechanics: Liquidate 100% of holdings immediately if the 50-day SMA 
     crosses below the 200-day SMA (Death Cross).
   - Re-entry: Only allowed after a Golden Cross (50 SMA > 200 SMA) AND a fresh 
     55-day Donchian breakout occurs.

3. STRATEGY 2: Hard Time-Based Capital Stagnation Exit
   - Purpose: Put a strict expiration date on underperforming capital.
   - Mechanics: Liquidate 100% of holdings if price remains >30% below the trade's 
     peak high for more than 180 consecutive calendar days.
   - Re-entry: Full reset required (waits for a fresh 55-day Donchian breakout).

4. STRATEGY 3: Macro Trend-Trailing Stop (Monthly Close < 10-Month EMA)
   - Purpose: Ignore intra-month daily noise while capturing major cycle shifts.
   - Mechanics: Evaluated only on the final trading day of each month. Liquidate 100% 
     if the monthly close falls below the 10-month Exponential Moving Average (~210 days).
   - Re-entry: Re-enters when price breaks out above the 55-day Donchian channel.

================================================================================
TESTING WINDOW: January 1, 2015 – August 4, 2026
STARTING CAPITAL: $20,000 (Standardized across strategies for fair evaluation)
================================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# ==========================================
# 1. DATA FETCHING & PREPARATION
# ==========================================
symbol = "AAOI"
start_date = "2013-06-01"  # Buffer for 10-Month EMA and 200-day SMA calculations
end_date = "2026-08-04"
INITIAL_CAPITAL = 20000.0

print(f"Fetching market data for {symbol}...")
df = yf.download(symbol, start=start_date, end=end_date, progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Technical Indicators
df['Donchian_55'] = df['High'].shift(1).rolling(55).max()
df['SMA_50'] = df['Close'].rolling(50).mean()
df['SMA_200'] = df['Close'].rolling(200).mean()

# Calculate Monthly 10-EMA and map back to daily chart
df_monthly = df['Close'].resample('ME').last().to_frame()
df_monthly['EMA_10_M'] = df_monthly['Close'].ewm(span=10, adjust=False).mean()

# Align monthly 10-EMA to daily dataframe without lookahead bias
df['Monthly_EMA_10'] = df_monthly['EMA_10_M'].reindex(df.index, method='ffill')
df['Is_Month_End'] = df.index.isin(df_monthly.index)

# Filter dataset to target backtest window
df_backtest = df.loc['2015-01-01':].copy()


# ==========================================
# 2. STRATEGY SIMULATIONS
# ==========================================

# ------------------------------------------
# BASE STRATEGY: Momentum + Buy & Hold
# ------------------------------------------
def run_base_strategy(data):
    cash = INITIAL_CAPITAL
    shares = 0
    last_buy_date = None
    last_buy_price = 0.0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity_curve.append(cash)
            continue

        if shares == 0:
            if price > donchian and cash >= price:
                shares = 1
                cash -= price
                last_buy_date = date
                last_buy_price = price
        else:
            days_passed = (date - last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - last_buy_price) / last_buy_price
                if appreciation > 0.05:
                    buy_amount = min(cash, max(1000.0, price))
                    shares_to_buy = int(buy_amount // price)
                    if shares_to_buy > 0:
                        cost = shares_to_buy * price
                        shares += shares_to_buy
                        cash -= cost
                        last_buy_date = date
                        last_buy_price = price

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ------------------------------------------
# STRATEGY 1: Macro Regime Exit (50 / 200 Death Cross)
# ------------------------------------------
def run_strat1_death_cross(data):
    cash = INITIAL_CAPITAL
    shares = 0
    last_buy_date = None
    last_buy_price = 0.0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        donchian = row['Donchian_55']
        sma_50 = row['SMA_50']
        sma_200 = row['SMA_200']

        if pd.isna(donchian) or pd.isna(sma_200):
            equity_curve.append(cash)
            continue

        # Check Death Cross Exit (100% Cash)
        if shares > 0 and sma_50 < sma_200:
            cash += shares * price
            shares = 0
            last_buy_date = None

        # Entry logic: Must have Golden Cross (SMA_50 > SMA_200) AND Donchian Breakout
        if shares == 0:
            if sma_50 > sma_200 and price > donchian and cash >= price:
                shares = 1
                cash -= price
                last_buy_date = date
                last_buy_price = price
        else:
            # Pyramiding logic
            days_passed = (date - last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - last_buy_price) / last_buy_price
                if appreciation > 0.05:
                    buy_amount = min(cash, max(1000.0, price))
                    shares_to_buy = int(buy_amount // price)
                    if shares_to_buy > 0:
                        cost = shares_to_buy * price
                        shares += shares_to_buy
                        cash -= cost
                        last_buy_date = date
                        last_buy_price = price

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ------------------------------------------
# STRATEGY 2: Hard Stagnation Exit (>30% drawdown for >180 days)
# ------------------------------------------
def run_strat2_stagnation(data):
    cash = INITIAL_CAPITAL
    shares = 0
    last_buy_date = None
    last_buy_price = 0.0
    peak_price = 0.0
    days_below_30pct = 0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        high = row['High']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity_curve.append(cash)
            continue

        if shares > 0:
            peak_price = max(peak_price, high)
            drawdown_from_peak = (price - peak_price) / peak_price

            if drawdown_from_peak < -0.30:
                days_below_30pct += 1
            else:
                days_below_30pct = 0

            # Stagnation Exit Trigger (Liquidate 100%)
            if days_below_30pct >= 180:
                cash += shares * price
                shares = 0
                peak_price = 0.0
                days_below_30pct = 0
                last_buy_date = None

        # Entry logic
        if shares == 0:
            if price > donchian and cash >= price:
                shares = 1
                cash -= price
                last_buy_date = date
                last_buy_price = price
                peak_price = high
                days_below_30pct = 0
        else:
            # Pyramiding logic
            days_passed = (date - last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - last_buy_price) / last_buy_price
                if appreciation > 0.05:
                    buy_amount = min(cash, max(1000.0, price))
                    shares_to_buy = int(buy_amount // price)
                    if shares_to_buy > 0:
                        cost = shares_to_buy * price
                        shares += shares_to_buy
                        cash -= cost
                        last_buy_date = date
                        last_buy_price = price

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ------------------------------------------
# STRATEGY 3: Monthly Close < 10-Month EMA Exit
# ------------------------------------------
def run_strat3_monthly_ema(data):
    cash = INITIAL_CAPITAL
    shares = 0
    last_buy_date = None
    last_buy_price = 0.0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        donchian = row['Donchian_55']
        monthly_ema = row['Monthly_EMA_10']
        is_month_end = row['Is_Month_End']

        if pd.isna(donchian) or pd.isna(monthly_ema):
            equity_curve.append(cash)
            continue

        # Exit trigger evaluated ONLY on month-end close
        if shares > 0 and is_month_end:
            if price < monthly_ema:
                cash += shares * price
                shares = 0
                last_buy_date = None

        # Entry logic
        if shares == 0:
            if price > donchian and cash >= price:
                shares = 1
                cash -= price
                last_buy_date = date
                last_buy_price = price
        else:
            # Pyramiding logic
            days_passed = (date - last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - last_buy_price) / last_buy_price
                if appreciation > 0.05:
                    buy_amount = min(cash, max(1000.0, price))
                    shares_to_buy = int(buy_amount // price)
                    if shares_to_buy > 0:
                        cost = shares_to_buy * price
                        shares += shares_to_buy
                        cash -= cost
                        last_buy_date = date
                        last_buy_price = price

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ==========================================
# 3. RUN & EVALUATE ALL STRATEGIES
# ==========================================
print("Running backtest simulations...")
eq_base = run_base_strategy(df_backtest)
eq_s1 = run_strat1_death_cross(df_backtest)
eq_s2 = run_strat2_stagnation(df_backtest)
eq_s3 = run_strat3_monthly_ema(df_backtest)

def calc_metrics(equity_series):
    final_val = equity_series.iloc[-1]
    net_profit = final_val - INITIAL_CAPITAL
    roi = (net_profit / INITIAL_CAPITAL) * 100
    
    # Calculate Max Drawdown
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_dd = drawdown.min() * 100

    return round(final_val, 2), round(net_profit, 2), round(roi, 2), round(max_dd, 2)

results = {
    "Base: Buy & Hold": calc_metrics(eq_base),
    "Strat 1: Death Cross Exit (50/200)": calc_metrics(eq_s1),
    "Strat 2: Stagnation Exit (>180d)": calc_metrics(eq_s2),
    "Strat 3: Monthly 10-EMA Exit": calc_metrics(eq_s3),
}

summary_df = pd.DataFrame(results, index=["Final Portfolio ($)", "Net Profit ($)", "ROI (%)", "Max Drawdown (%)"]).T

# Print Summary Table
print("\n" + "=" * 85)
print("               AAOI MACRO EXIT STRATEGY RESULTS (2015 - 2026)")
print("====================================================================================")
print(summary_df.to_string())
print("=" * 85)

# ==========================================
# 4. VISUALIZATION
# ==========================================
plt.figure(figsize=(12, 6))
plt.plot(eq_base.index, eq_base.values, label="Base: Buy & Hold", alpha=0.8)
plt.plot(eq_s1.index, eq_s1.values, label="Strat 1: Death Cross Exit (50/200)", alpha=0.9)
plt.plot(eq_s2.index, eq_s2.values, label="Strat 2: Stagnation Exit (>180d)", alpha=0.9)
plt.plot(eq_s3.index, eq_s3.values, label="Strat 3: Monthly 10-EMA Exit", alpha=0.9)

plt.axhline(INITIAL_CAPITAL, color='grey', linestyle='--', label="Initial Capital ($20,000)")
plt.title("AAOI Macro Exit Strategy Comparison: Portfolio Value Over Time ($)")
plt.xlabel("Date")
plt.ylabel("Total Portfolio Equity ($)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

'''
=====================================================================================
               AAOI MACRO EXIT STRATEGY RESULTS (2015 - 2026)
====================================================================================
                                    Final Portfolio ($)  Net Profit ($)  ROI (%)  Max Drawdown (%)
Base: Buy & Hold                               61666.12        41666.12   208.33            -85.94
Strat 1: Death Cross Exit (50/200)             22634.72         2634.72    13.17            -45.79
Strat 2: Stagnation Exit (>180d)              114743.94        94743.94   473.72            -66.54
Strat 3: Monthly 10-EMA Exit                   31126.04        11126.04    55.63            -51.54
=====================================================================================
'''