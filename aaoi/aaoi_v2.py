"""
================================================================================
BACKTEST SCRIPT: AAOI ALTERNATIVE STRATEGY COMPARISON
================================================================================
EXECUTIVE SUMMARY & OBJECTIVE:
    Applied Optoelectronics (AAOI) is a high-volatility stock characterized by 
    massive cyclical rallies followed by deep, violent pullbacks (often 50% to 80%). 
    
    Previous backtesting revealed that standard trend-following exits (like ATR 
    trailing stops or 100/200 moving average breaches) fail completely on AAOI 
    because daily price noise constantly triggers "whipsaw" exits at local bottoms, 
    locking in losses on pyramided positions.

    The objective of this script is to compare 4 structurally distinct strategies 
    to see how alternative entry/exit models handle AAOI's extreme volatility:

================================================================================
STRATEGIES BEING EVALUATED:

1. STRATEGY 1: Donchian Momentum + Pyramiding + Buy & Hold
   - Purpose: Benchmark for trend momentum without exit whipsaws.
   - Entry: Buy 1 share on a 55-day Donchian High breakout.
   - Pyramiding: Every 30 days, if price is >5% above the last check/buy point, 
     add $1,000 worth of shares.
   - Exit: Never exit (Hold indefinitely).

2. STRATEGY 2: Volatility-Adjusted Rebalancing (Constant-Mix 20/80)
   - Purpose: Monetize wild price swings without timing market exits.
   - Mechanics: Start with a portfolio split (20% AAOI / 80% Cash).
   - Rules: Rebalance back to 20/80 monthly, or whenever AAOI's target share of 
     the portfolio strays outside a 10% tolerance band (i.e., <10% or >30%).
   - Rationale: Systematically takes profits into parabolic rallies and buys 
     bargain shares during deep crashes.

3. STRATEGY 3: Asymmetric Oversold Scaling (RSI + Bollinger + Tranche Exits)
   - Purpose: Avoid buying at local peaks; de-risk principal systematically.
   - Entry: Buy when 14-day RSI < 30 OR price touches the Lower Bollinger Band 
     (20-day SMA - 2 Std Dev), provided price is above the 200-day SMA (macro uptrend).
   - Exit (Tranches): Sell 25% of open position at +50% gain, another 25% at 
     +100% gain, and leave the remaining 50% as a "free runner."

4. STRATEGY 4: Volatility Channel Mean-Reversion (3 Std Dev Bollinger Bands)
   - Purpose: Trade short-term extreme oversold bounces back to average value.
   - Entry: Buy 100% available cash when daily price pierces below the lower 3.0 
     Standard Deviation Bollinger Band.
   - Exit: Sell 100% of position when price recovers back up to the 20-day SMA.

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
start_date = "2014-01-01"  # Buffer for 200-day moving average calculation
end_date = "2026-08-04"
INITIAL_CAPITAL = 20000.0

print(f"Fetching market data for {symbol}...")
df = yf.download(symbol, start=start_date, end=end_date, progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# Technical Indicators
df['Donchian_55'] = df['High'].shift(1).rolling(55).max()
df['SMA_200'] = df['Close'].rolling(200).mean()

# 20-day Bollinger Bands (2.0 Std Dev for Strategy 3)
df['SMA_20'] = df['Close'].rolling(20).mean()
df['Std_20'] = df['Close'].rolling(20).std()
df['BB_Lower_2'] = df['SMA_20'] - (2.0 * df['Std_20'])

# 20-day Bollinger Bands (3.0 Std Dev for Strategy 4)
df['BB_Lower_3'] = df['SMA_20'] - (3.0 * df['Std_20'])

# 14-day RSI
delta = df['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rs = gain / loss
df['RSI_14'] = 100 - (100 / (1 + rs))

# Filter to actual backtest window
df_backtest = df.loc['2015-01-01':].copy()


# ==========================================
# 2. STRATEGY SIMULATIONS
# ==========================================

# ------------------------------------------
# STRATEGY 1: Momentum Donchian + Buy & Hold
# ------------------------------------------
def run_strat1(data):
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
# STRATEGY 2: Constant-Mix Rebalancing (20/80)
# ------------------------------------------
def run_strat2(data, target_weight=0.20, tolerance=0.10):
    cash = INITIAL_CAPITAL * (1.0 - target_weight)
    shares = int((INITIAL_CAPITAL * target_weight) // data['Close'].iloc[0])
    cash += (INITIAL_CAPITAL * target_weight) - (shares * data['Close'].iloc[0])
    
    last_rebalance_date = data.index[0]
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        total_val = cash + (shares * price)
        aaoi_weight = (shares * price) / total_val if total_val > 0 else 0

        days_passed = (date - last_rebalance_date).days
        weight_diff = abs(aaoi_weight - target_weight)

        # Trigger rebalance monthly or if weight strays outside tolerance (+-10%)
        if days_passed >= 30 or weight_diff >= tolerance:
            target_aaoi_val = total_val * target_weight
            target_shares = int(target_aaoi_val // price)
            shares_diff = target_shares - shares

            if shares_diff > 0:  # Buy AAOI
                cost = shares_diff * price
                if cash >= cost:
                    shares += shares_diff
                    cash -= cost
            elif shares_diff < 0:  # Sell AAOI
                proceeds = abs(shares_diff) * price
                shares += shares_diff
                cash += proceeds

            last_rebalance_date = date

        equity_curve.append(cash + (shares * price))

    return pd.Series(equity_curve, index=data.index)


# ------------------------------------------
# STRATEGY 3: Asymmetric Oversold Scaling
# ------------------------------------------
def run_strat3(data):
    cash = INITIAL_CAPITAL
    shares = 0
    tranche1_sold = False
    tranche2_sold = False
    avg_cost = 0.0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        rsi = row['RSI_14']
        bb_low = row['BB_Lower_2']
        sma_200 = row['SMA_200']

        if pd.isna(rsi) or pd.isna(sma_200):
            equity_curve.append(cash)
            continue

        # Entry Condition: Oversold + Macro Uptrend
        if shares == 0:
            if (rsi < 30 or price <= bb_low) and price > sma_200:
                shares = int(cash // price)
                if shares > 0:
                    avg_cost = price
                    cash -= shares * price
                    tranche1_sold = False
                    tranche2_sold = False
        else:
            # Tranche 1 Exit: +50% Gain -> Sell 25% of initial position
            if not tranche1_sold and price >= avg_cost * 1.50:
                shares_to_sell = max(1, int(shares * 0.25))
                cash += shares_to_sell * price
                shares -= shares_to_sell
                tranche1_sold = True

            # Tranche 2 Exit: +100% Gain -> Sell 25% of initial position
            if not tranche2_sold and price >= avg_cost * 2.00:
                shares_to_sell = max(1, int(shares * 0.25))
                cash += shares_to_sell * price
                shares -= shares_to_sell
                tranche2_sold = True

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ------------------------------------------
# STRATEGY 4: Volatility Channel Mean-Reversion
# ------------------------------------------
def run_strat4(data):
    cash = INITIAL_CAPITAL
    shares = 0
    equity_curve = []

    for date, row in data.iterrows():
        price = row['Close']
        bb_low_3 = row['BB_Lower_3']
        sma_20 = row['SMA_20']

        if pd.isna(bb_low_3):
            equity_curve.append(cash)
            continue

        # Entry: Price pierces below 3 Std Dev Band
        if shares == 0 and price < bb_low_3:
            shares = int(cash // price)
            if shares > 0:
                cash -= shares * price

        # Exit: Price reaches 20-day SMA midpoint
        elif shares > 0 and price >= sma_20:
            cash += shares * price
            shares = 0

        total_val = cash + (shares * price)
        equity_curve.append(total_val)

    return pd.Series(equity_curve, index=data.index)


# ==========================================
# 3. RUN & EVALUATE ALL STRATEGIES
# ==========================================
print("Running simulations...")
eq1 = run_strat1(df_backtest)
eq2 = run_strat2(df_backtest)
eq3 = run_strat3(df_backtest)
eq4 = run_strat4(df_backtest)

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
    "Strat 1: Momentum + Hold": calc_metrics(eq1),
    "Strat 2: Constant-Mix 20/80": calc_metrics(eq2),
    "Strat 3: Asymmetric Oversold": calc_metrics(eq3),
    "Strat 4: Mean-Reversion (3 SD)": calc_metrics(eq4),
}

summary_df = pd.DataFrame(results, index=["Final Portfolio ($)", "Net Profit ($)", "ROI (%)", "Max Drawdown (%)"]).T

# Print Summary Table
print("\n" + "=" * 80)
print("             AAOI STRATEGY COMPARISON RESULTS (2015 - 2026)")
print("=================================================================================")
print(summary_df.to_string())
print("=" * 80)

# ==========================================
# 4. VISUALIZATION
# ==========================================
plt.figure(figsize=(12, 6))
plt.plot(eq1.index, eq1.values, label="Strat 1: Momentum + Hold", alpha=0.9)
plt.plot(eq2.index, eq2.values, label="Strat 2: Constant-Mix (20/80 Rebalance)", alpha=0.9)
plt.plot(eq3.index, eq3.values, label="Strat 3: Asymmetric Oversold Scaling", alpha=0.9)
plt.plot(eq4.index, eq4.values, label="Strat 4: Mean-Reversion (3 SD BB)", alpha=0.9)

plt.axhline(INITIAL_CAPITAL, color='grey', linestyle='--', label="Initial Capital ($20,000)")
plt.title("AAOI Alternative Strategy Comparison: Portfolio Value Over Time ($)")
plt.xlabel("Date")
plt.ylabel("Total Portfolio Equity ($)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

'''
================================================================================
             AAOI STRATEGY COMPARISON RESULTS (2015 - 2026)
=================================================================================
                                Final Portfolio ($)  Net Profit ($)  ROI (%)  Max Drawdown (%)
Strat 1: Momentum + Hold                   61666.12        41666.12   208.33            -85.94
Strat 2: Constant-Mix 20/80                67703.17        47703.17   238.52            -49.07
Strat 3: Asymmetric Oversold               92730.59        72730.59   363.65            -80.75
Strat 4: Mean-Reversion (3 SD)             12661.15        -7338.85   -36.69            -59.39
================================================================================

These updated results paint a clear picture of how different mechanics handle AAOI's extreme volatility. Switching away from "all-or-nothing" trend exits dramatically improves performance across the board (except for short-term mean reversion).

Here is the strategic analysis of why these results played out the way they did.

---

## Executive Summary & Comparison Table

| Strategy | Final Portfolio | Net Profit | ROI (%) | Max Drawdown (%) | Performance Profile |
| --- | --- | --- | --- | --- | --- |
| **Strat 3: Asymmetric Oversold** | **$92,730.59** | **$72,730.59** | **+363.65%** | -80.75% | **Highest Profit / Highest Risk** |
| **Strat 2: Constant-Mix 20/80** | **$67,703.17** | **$47,703.17** | **+238.52%** | **-49.07%** | **Best Risk-Adjusted Return** |
| **Strat 1: Momentum + Hold** | $61,666.12 | $41,666.12 | +208.33% | -85.94% | Strong Gains / Severe Drawdowns |
| **Strat 4: Mean-Reversion (3 SD)** | $12,661.15 | -$7,338.85 | **-36.69%** | -59.39% | **Failed Strategy** |

---

## Key Takeaways & Strategic Insights

### 1. The Clear Winner for Raw Returns: Strategy 3 (Asymmetric Oversold Scaling)

* **ROI:** +363.65% ($72,730 profit on a $20k start)
* **Why it crushed the rest:**
1. **Disciplined Entries:** By requiring an oversold trigger (RSI < 30 / Lower BB) *and* a macro uptrend (> 200 SMA), it bought full positions near cycle bottoms rather than chasing local highs.
2. **Tranche Exits Lock in Gains:** Selling 25% at +50% and 25% at +100% took original principal off the table during parabolic runs (notice the green spikes in 2017 and 2026 reaching nearly $175,000).
3. **The "Free Runner":** Leaving the remaining 50% untouched allowed the strategy to ride massive long-term macro waves.


* **The Catch:** It still suffers an **-80.75% Max Drawdown**. When AAOI crashes, the uncapped "free runner" portion loses a lot of paper value.

---

### 2. The Best Risk-Adjusted Model: Strategy 2 (Constant-Mix 20/80)

* **ROI:** +238.52% ($47,703 profit)
* **Max Drawdown:** **-49.07%** (nearly half the drawdown of all other strategies)
* **Why it shines:**
* It beat the standard **Strategy 1 (Momentum + Hold)** on total return while reducing maximum drawdown from **-85.94% to -49.07%**.
* By systematically taking profits into strength (selling when AAOI grew beyond 30% of portfolio) and buying dips when AAOI fell below 10%, it acted as an automated "buy-low, sell-high" machine.
* **Verdict:** This is the most practical real-world strategy for a trader who cannot emotionally handle an 80%+ portfolio collapse.



---

### 3. Strategy 1 (Momentum + Hold) Benchmark

* **ROI:** +208.33%
* **Drawdown:** -85.94%
* **Insight:** Holding works because AAOI’s upside is so explosive, but buying breakouts at local 55-day highs causes you to accumulate heavy inventory right before violent retracements, resulting in brutal multi-year paper losses (e.g., 2018–2023 flatline on the blue line).

---

### 4. Why Strategy 4 (3 SD Mean-Reversion) Failed

* **ROI:** -36.69% ($7,338 loss)
* **Why it failed:** AAOI is a **momentum/trend stock**, not a quiet range-bound stock.
* When AAOI breaks down past a 3.0 Standard Deviation band, it is rarely just a temporary "oversold bounce." It is usually the start of a multi-month fundamental collapse.
* Buying extreme dips and selling immediately at the 20-day SMA caps your upside completely while exposing you to massive downside risk when the stock keeps falling.



---

## Final Verdict & Recommendation

If your goal is to trade AAOI effectively:

1. **If seeking maximum capital growth:** Use **Strategy 3 (Asymmetric Oversold)**. It catches lower entries than momentum breakouts and systematically locks in profits without getting shaken out.
2. **If seeking portfolio stability and peace of mind:** Use **Strategy 2 (Constant-Mix 20/80)**. It captures a huge chunk of AAOI's parabolic moves while cutting portfolio drawdowns roughly in half.
'''