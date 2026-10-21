"""
================================================================================
BACKTEST SCRIPT: AAOI ADVANCED MACRO EXIT & BENCHMARK CAPITAL DEPLOYMENT
================================================================================
EXECUTIVE SUMMARY & OBJECTIVE:
    Applied Optoelectronics (AAOI) is a hyper-volatile asset characterized by 
    explosive parabolic surges and protracted 80%+ multi-year drawdowns. 

    While holding through drawdowns ties up capital in "dead money" for years, 
    sitting in 0% cash during off-periods creates a severe opportunity cost. 

    This script benchmarks a base momentum strategy against 6 refined macro exit 
    and profit-locking mechanisms. Crucially, WHENEVER CAPITAL IS NOT ALLOCATED 
    TO AAOI, IT IS DEPLOYED INTO QQQ to compound capital continuously.

================================================================================
STRATEGIES EVALUATED:

1. BASE STRATEGY: Donchian Momentum + Pyramiding + Hold (Idle Capital in QQQ)
   - Entry: Buy 1 share of AAOI on a 55-day Donchian High breakout.
   - Pyramiding: Every 30 days, if price is >5% above last buy point, add $1,000.
   - Exit: Never exit AAOI.
   - Cash Management: Any unallocated starting capital stays in QQQ.

2. STRATEGY 1: Macro Regime Exit (50 / 200 SMA Death Cross)
   - Mechanics: Liquidate 100% of AAOI into QQQ on a 50/200 SMA Death Cross.
   - Re-entry: Requires Golden Cross (50 SMA > 200 SMA) AND a 55-day Donchian breakout.

3. STRATEGY 2: Hard Capital Stagnation Exit (>30% drawdown for >180 days)
   - Mechanics: Liquidate 100% of AAOI into QQQ if price stays >30% below peak high 
     for more than 180 consecutive calendar days.

4. STRATEGY 3: Strategy #2 + Tranche Take-Profit Rules
   - Mechanics: Adds profit targets on top of Strategy #2:
     * Sell 25% of active AAOI position size at +100% gain (proceeds moved to QQQ).
     * Sell 25% of active AAOI position size at +200% gain (proceeds moved to QQQ).
     * Remaining 50% trails under the 180-day stagnation rule.

5. STRATEGY 4: Strategy #2 + Dynamic Stagnation Window (Adaptive Time Stop)
   - Mechanics: Adapts the stagnation window based on open trade performance:
     * If trade is in a LOSS (<0%): Use a 60-day stagnation window to exit fast.
     * If trade is in PROFIT (>=50%): Extend window to 180 days to give room.
     * Otherwise (0% to <50%): Use a baseline 120-day window.

6. STRATEGY 5: Strategy #2 Benchmark Compounder (Pure QQQ Sweep)
   - Mechanics: Re-runs Strategy #2 with precise tracking of QQQ compounding whenever 
     AAOI positions are liquidated or partially unallocated.

7. STRATEGY 6: Strategy #2 + Volatility-Based Trailing Stop (Chandelier Exit)
   - Mechanics: Liquidates 100% of AAOI into QQQ if price drops below 
     `Peak High - (6 x 14-day ATR)`, acting as an immediate crash guard before 
     the 180-day clock even finishes.

================================================================================
TESTING WINDOW: January 1, 2015 – August 4, 2026
STARTING CAPITAL: $20,000
BENCHMARK FOR IDLE CASH: Invesco QQQ Trust (QQQ)
================================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# ==========================================
# 1. DATA FETCHING & PREPARATION
# ==========================================
symbols = ["AAOI", "QQQ"]
start_date = "2013-06-01"  # Buffer for technical moving averages
end_date = "2026-08-04"
INITIAL_CAPITAL = 20000.0

print("Fetching market data for AAOI and QQQ...")
df_raw = yf.download(symbols, start=start_date, end=end_date, progress=False)

# Standardize DataFrame columns if multi-index
if isinstance(df_raw.columns, pd.MultiIndex):
    aaoi = df_raw.xs('AAOI', level=1, axis=1).copy()
    qqq = df_raw.xs('QQQ', level=1, axis=1).copy()
else:
    aaoi = df_raw['AAOI'].copy()
    qqq = df_raw['QQQ'].copy()

# Technical Indicators for AAOI
aaoi['Donchian_55'] = aaoi['High'].shift(1).rolling(55).max()
aaoi['SMA_50'] = aaoi['Close'].rolling(50).mean()
aaoi['SMA_200'] = aaoi['Close'].rolling(200).mean()

# ATR Calculation for Strategy 6 (14-day ATR)
high_low = aaoi['High'] - aaoi['Low']
high_close = np.abs(aaoi['High'] - aaoi['Close'].shift(1))
low_close = np.abs(aaoi['Low'] - aaoi['Close'].shift(1))
tr = np.maximum(high_low, np.maximum(high_close, low_close))
aaoi['ATR_14'] = tr.rolling(14).mean()

# Trim to backtest target window
aaoi = aaoi.loc['2015-01-01':].copy()
qqq = qqq.loc['2015-01-01':].copy()


# ==========================================
# 2. HELPER CLASS FOR QQQ CAPITAL MANAGEMENT
# ==========================================
class Portfolio:
    """Manages dual positions in AAOI and QQQ automatically."""
    def __init__(self, initial_cash):
        self.qqq_shares = 0.0
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0
        self.tranche_100_sold = False
        self.tranche_200_sold = False
        
        # Deploy initial capital into QQQ
        first_qqq_price = qqq['Close'].iloc[0]
        self.qqq_shares = initial_cash / first_qqq_price

    def buy_aaoi(self, date, price, dollar_amount):
        qqq_price = qqq.loc[date, 'Close']
        max_available = self.qqq_shares * qqq_price
        spend = min(dollar_amount, max_available)
        
        shares_to_buy = spend / price
        if shares_to_buy > 0:
            # Sell equivalent from QQQ
            self.qqq_shares -= spend / qqq_price
            
            # Update AAOI tracking
            total_shares = self.aaoi_shares + shares_to_buy
            if self.aaoi_shares == 0:
                self.aaoi_avg_cost = price
            else:
                self.aaoi_avg_cost = ((self.aaoi_shares * self.aaoi_avg_cost) + (shares_to_buy * price)) / total_shares
            
            self.aaoi_shares = total_shares
            self.last_buy_date = date
            self.last_buy_price = price
            if self.peak_price == 0:
                self.peak_price = price

    def sell_aaoi_pct(self, date, price, pct):
        if self.aaoi_shares <= 0:
            return
        
        shares_to_sell = self.aaoi_shares * pct
        proceeds = shares_to_sell * price
        self.aaoi_shares -= shares_to_sell
        
        # Move proceeds into QQQ
        qqq_price = qqq.loc[date, 'Close']
        self.qqq_shares += proceeds / qqq_price

    def sell_all_aaoi(self, date, price):
        self.sell_aaoi_pct(date, price, 1.0)
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0
        self.tranche_100_sold = False
        self.tranche_200_sold = False

    def total_value(self, date, aaoi_price):
        qqq_price = qqq.loc[date, 'Close']
        return (self.qqq_shares * qqq_price) + (self.aaoi_shares * aaoi_price)


# ==========================================
# 3. STRATEGY SIMULATION ENGINES
# ==========================================

def run_base_strategy():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares == 0:
            if price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_strat1_death_cross():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        donchian = row['Donchian_55']
        sma_50 = row['SMA_50']
        sma_200 = row['SMA_200']

        if pd.isna(donchian) or pd.isna(sma_200):
            equity.append(p.total_value(date, price))
            continue

        # Exit trigger: Death Cross
        if p.aaoi_shares > 0 and sma_50 < sma_200:
            p.sell_all_aaoi(date, price)

        # Entry trigger: Golden Cross + Donchian Breakout
        if p.aaoi_shares == 0:
            if sma_50 > sma_200 and price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_strat2_stagnation():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        high = row['High']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            drawdown = (price - p.peak_price) / p.peak_price

            if drawdown < -0.30:
                p.days_below_30pct += 1
            else:
                p.days_below_30pct = 0

            if p.days_below_30pct >= 180:
                p.sell_all_aaoi(date, price)

        if p.aaoi_shares == 0:
            if price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_strat3_tranche_take_profit():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        high = row['High']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            gain = (price - p.aaoi_avg_cost) / p.aaoi_avg_cost

            # Tranche Take-Profits
            if gain >= 1.00 and not p.tranche_100_sold:
                p.sell_aaoi_pct(date, price, 0.25)
                p.tranche_100_sold = True

            if gain >= 2.00 and not p.tranche_200_sold:
                p.sell_aaoi_pct(date, price, 0.25)
                p.tranche_200_sold = True

            # Stagnation timer
            drawdown = (price - p.peak_price) / p.peak_price
            if drawdown < -0.30:
                p.days_below_30pct += 1
            else:
                p.days_below_30pct = 0

            if p.days_below_30pct >= 180:
                p.sell_all_aaoi(date, price)

        if p.aaoi_shares == 0:
            if price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_strat4_dynamic_stagnation():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        high = row['High']
        donchian = row['Donchian_55']

        if pd.isna(donchian):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            drawdown = (price - p.peak_price) / p.peak_price
            gain = (price - p.aaoi_avg_cost) / p.aaoi_avg_cost

            # Determine dynamic threshold window
            if gain < 0:
                threshold_days = 60
            elif gain >= 0.50:
                threshold_days = 180
            else:
                threshold_days = 120

            if drawdown < -0.30:
                p.days_below_30pct += 1
            else:
                p.days_below_30pct = 0

            if p.days_below_30pct >= threshold_days:
                p.sell_all_aaoi(date, price)

        if p.aaoi_shares == 0:
            if price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_strat6_chandelier_exit():
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        high = row['High']
        donchian = row['Donchian_55']
        atr = row['ATR_14']

        if pd.isna(donchian) or pd.isna(atr):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            chandelier_stop = p.peak_price - (6.0 * atr)

            # Trailing stop or stagnation trigger
            if price < chandelier_stop:
                p.sell_all_aaoi(date, price)
            else:
                drawdown = (price - p.peak_price) / p.peak_price
                if drawdown < -0.30:
                    p.days_below_30pct += 1
                else:
                    p.days_below_30pct = 0

                if p.days_below_30pct >= 180:
                    p.sell_all_aaoi(date, price)

        if p.aaoi_shares == 0:
            if price > donchian:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


# ==========================================
# 4. RUN ALL SIMULATIONS & CALC METRICS
# ==========================================
print("Running strategy simulations...")
eq_base = run_base_strategy()
eq_s1 = run_strat1_death_cross()
eq_s2 = run_strat2_stagnation()
eq_s3 = run_strat3_tranche_take_profit()
eq_s4 = run_strat4_dynamic_stagnation()
eq_s5 = eq_s2  # Strategy 5 is the full QQQ sweep benchmark version of Strategy 2
eq_s6 = run_strat6_chandelier_exit()

def calc_metrics(eq):
    final_val = eq.iloc[-1]
    net_profit = final_val - INITIAL_CAPITAL
    roi = (net_profit / INITIAL_CAPITAL) * 100
    peak = eq.cummax()
    max_dd = ((eq - peak) / peak).min() * 100
    return round(final_val, 2), round(net_profit, 2), round(roi, 2), round(max_dd, 2)

results = {
    "Base: Buy & Hold (QQQ Sweep)": calc_metrics(eq_base),
    "Strat 1: Death Cross Exit (50/200)": calc_metrics(eq_s1),
    "Strat 2: Hard Stagnation Exit (>180d)": calc_metrics(eq_s2),
    "Strat 3: Tranche Take-Profits (100%/200%)": calc_metrics(eq_s3),
    "Strat 4: Dynamic Stagnation (Adaptive)": calc_metrics(eq_s4),
    "Strat 5: Strategy #2 (Pure QQQ Sweep)": calc_metrics(eq_s5),
    "Strat 6: Chandelier Trailing Exit (6xATR)": calc_metrics(eq_s6),
}

summary_df = pd.DataFrame(results, index=["Final Portfolio ($)", "Net Profit ($)", "ROI (%)", "Max Drawdown (%)"]).T

print("\n" + "=" * 90)
print("             AAOI ADVANCED MACRO EXIT STRATEGY RESULTS (2015 - 2026)")
print("                 (All Idle Cash Automatically Deployed in QQQ)")
print("==========================================================================================")
print(summary_df.to_string())
print("=" * 90)

# ==========================================
# 5. VISUALIZATION
# ==========================================
plt.figure(figsize=(14, 7))
plt.plot(eq_base.index, eq_base.values, label="Base: Buy & Hold", alpha=0.5, linestyle='--')
plt.plot(eq_s2.index, eq_s2.values, label="Strat 2: Hard Stagnation (>180d)", linewidth=2)
plt.plot(eq_s3.index, eq_s3.values, label="Strat 3: Tranche Take-Profits", linewidth=2)
plt.plot(eq_s4.index, eq_s4.values, label="Strat 4: Dynamic Stagnation", linewidth=2)
plt.plot(eq_s6.index, eq_s6.values, label="Strat 6: Chandelier Trailing Stop (6xATR)", linewidth=2)

plt.axhline(INITIAL_CAPITAL, color='grey', linestyle=':', label="Initial Capital ($20,000)")
plt.title("AAOI Strategy Comparison: Portfolio Equity with QQQ Idle Capital Sweep ($)")
plt.xlabel("Date")
plt.ylabel("Total Portfolio Equity ($)")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()

'''
==========================================================================================
             AAOI ADVANCED MACRO EXIT STRATEGY RESULTS (2015 - 2026)
                 (All Idle Cash Automatically Deployed in QQQ)
==========================================================================================
                                           Final Portfolio ($)  Net Profit ($)  ROI (%)  Max Drawdown (%)
Base: Buy & Hold (QQQ Sweep)                         121791.58       101791.58   508.96            -70.83
Strat 1: Death Cross Exit (50/200)                   139677.97       119677.97   598.39            -35.12
Strat 2: Hard Stagnation Exit (>180d)                215296.78       195296.78   976.48            -58.55
Strat 3: Tranche Take-Profits (100%/200%)            225858.12       205858.12  1029.29            -40.01
Strat 4: Dynamic Stagnation (Adaptive)               127057.77       107057.77   535.29            -49.67
Strat 5: Strategy #2 (Pure QQQ Sweep)                215296.78       195296.78   976.48            -58.55
Strat 6: Chandelier Trailing Exit (6xATR)            190578.47       170578.47   852.89            -35.31
==========================================================================================
'''