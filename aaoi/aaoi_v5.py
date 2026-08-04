"""
================================================================================
BACKTEST SCRIPT: AAOI TARGETED EXIT MECHANISMS & INDEX BENCHMARKS
================================================================================
OBJECTIVE:
    Isolated evaluation of AAOI strategies alongside benchmark buy-and-hold 
    baselines (100% QQQ and 100% VOO), with relative performance metrics vs QQQ.

================================================================================
TESTING WINDOW: January 1, 2015 – August 4, 2026
STARTING CAPITAL: $200,000
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
symbols = ["AAOI", "QQQ", "VOO"]
start_date = "2013-06-01"  # Buffer for technical indicators
end_date = "2026-08-04"
INITIAL_CAPITAL = 200000.0

print("Fetching market data for AAOI, QQQ, and VOO...")
df_raw = yf.download(symbols, start=start_date, end=end_date, progress=False)

# Standardize DataFrame columns if multi-index
if isinstance(df_raw.columns, pd.MultiIndex):
    aaoi = df_raw.xs('AAOI', level=1, axis=1).copy()
    qqq = df_raw.xs('QQQ', level=1, axis=1).copy()
    voo = df_raw.xs('VOO', level=1, axis=1).copy()
else:
    aaoi = df_raw['AAOI'].copy()
    qqq = df_raw['QQQ'].copy()
    voo = df_raw['VOO'].copy()

# Technical Indicators for AAOI Entry & Exits
aaoi['Donchian_55_High'] = aaoi['High'].shift(1).rolling(55).max()
aaoi['Donchian_22_Low']  = aaoi['Low'].shift(1).rolling(22).min()
aaoi['Donchian_55_Low']  = aaoi['Low'].shift(1).rolling(55).min()

aaoi['DMA_100'] = aaoi['Close'].rolling(100).mean()
aaoi['DMA_200'] = aaoi['Close'].rolling(200).mean()

# ATR Calculation (14-day ATR)
high_low = aaoi['High'] - aaoi['Low']
high_close = np.abs(aaoi['High'] - aaoi['Close'].shift(1))
low_close = np.abs(aaoi['Low'] - aaoi['Close'].shift(1))
tr = np.maximum(high_low, np.maximum(high_close, low_close))
aaoi['ATR_14'] = tr.rolling(14).mean()

# Trim to backtest target window
aaoi = aaoi.loc['2015-01-01':].copy()
qqq = qqq.loc['2015-01-01':].copy()
voo = voo.loc['2015-01-01':].copy()


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
        
        # Deploy initial capital into QQQ
        first_qqq_price = qqq['Close'].iloc[0]
        self.qqq_shares = initial_cash / first_qqq_price

    def buy_aaoi(self, date, price, dollar_amount):
        qqq_price = qqq.loc[date, 'Close']
        max_available = self.qqq_shares * qqq_price
        spend = min(dollar_amount, max_available)
        
        shares_to_buy = spend / price
        if shares_to_buy > 0:
            self.qqq_shares -= spend / qqq_price
            
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

    def sell_all_aaoi(self, date, price):
        if self.aaoi_shares <= 0:
            return
        
        proceeds = self.aaoi_shares * price
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0
        
        # Re-invest proceeds into QQQ
        qqq_price = qqq.loc[date, 'Close']
        self.qqq_shares += proceeds / qqq_price

    def total_value(self, date, aaoi_price):
        qqq_price = qqq.loc[date, 'Close']
        return (self.qqq_shares * qqq_price) + (self.aaoi_shares * aaoi_price)


# ==========================================
# 3. SIMULATION ENGINES
# ==========================================

def run_buy_and_hold_benchmark(asset_df):
    """Calculates pure buy-and-hold equity curve for an ETF asset."""
    initial_shares = INITIAL_CAPITAL / asset_df['Close'].iloc[0]
    return initial_shares * asset_df['Close']


def run_base_strategy():
    """Base Strategy: Donchian 55 Breakout + Pyramiding + QQQ Sweep (No Exit)"""
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        donchian_high = row['Donchian_55_High']

        if pd.isna(donchian_high):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares == 0:
            if price > donchian_high:
                p.buy_aaoi(date, price, price)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price))

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index)


def run_exit_strategy(exit_type, param=None):
    """
    Runs Strategy Framework (55-day Breakout + Pyramiding + 180d Stagnation Exit)
    with custom overlay exit mechanisms (Chandelier ATR, DMA, or Donchian Lows).
    """
    p = Portfolio(INITIAL_CAPITAL)
    equity = []

    for date, row in aaoi.iterrows():
        price = row['Close']
        high = row['High']
        donchian_high = row['Donchian_55_High']
        atr = row['ATR_14']

        if pd.isna(donchian_high):
            equity.append(p.total_value(date, price))
            continue

        # Position Management & Exit Logic
        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            trigger_exit = False

            # Evaluate Specific Exit Mechanisms
            if exit_type == "chandelier":
                chandelier_stop = p.peak_price - (param * atr)
                if price < chandelier_stop:
                    trigger_exit = True

            elif exit_type == "dma":
                dma_val = row[f'DMA_{param}']
                if pd.notna(dma_val) and price < dma_val:
                    trigger_exit = True

            elif exit_type == "donchian_low":
                donchian_low_val = row[f'Donchian_{param}_Low']
                if pd.notna(donchian_low_val) and price < donchian_low_val:
                    trigger_exit = True

            # Evaluate Standard 180-day Stagnation Rule
            drawdown = (price - p.peak_price) / p.peak_price
            if drawdown < -0.30:
                p.days_below_30pct += 1
            else:
                p.days_below_30pct = 0

            if p.days_below_30pct >= 180:
                trigger_exit = True

            # Execute Exit to QQQ
            if trigger_exit:
                p.sell_all_aaoi(date, price)

        # Entry & Scale-In Logic
        if p.aaoi_shares == 0:
            if price > donchian_high:
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
# 4. RUN SIMULATIONS & CALCULATE METRICS
# ==========================================
print("Running isolated strategy backtests...")

simulations = {
    "Benchmark: 100% QQQ": run_buy_and_hold_benchmark(qqq),
    "Benchmark: 100% VOO": run_buy_and_hold_benchmark(voo),
    "Base: Buy & Hold (AAOI + QQQ Sweep)": run_base_strategy(),
    "Chandelier Trailing Exit (3x ATR)": run_exit_strategy("chandelier", param=3.0),
    "Chandelier Trailing Exit (5x ATR)": run_exit_strategy("chandelier", param=5.0),
    "Chandelier Trailing Exit (6x ATR)": run_exit_strategy("chandelier", param=6.0),
    "DMA Exit (100 DMA)": run_exit_strategy("dma", param=100),
    "DMA Exit (200 DMA)": run_exit_strategy("dma", param=200),
    "Donchian Exit (22d Lower Bound)": run_exit_strategy("donchian_low", param=22),
    "Donchian Exit (55d Lower Bound)": run_exit_strategy("donchian_low", param=55)
}

# Baseline QQQ reference value for relative comparison
qqq_final_val = simulations["Benchmark: 100% QQQ"].iloc[-1]

def calc_metrics(eq):
    final_val = eq.iloc[-1]
    net_profit = final_val - INITIAL_CAPITAL
    roi = (net_profit / INITIAL_CAPITAL) * 100
    peak = eq.cummax()
    max_dd = ((eq - peak) / peak).min() * 100
    
    # Comparisons against Benchmark: 100% QQQ
    diff_vs_qqq_dlr = final_val - qqq_final_val
    diff_vs_qqq_pct = ((final_val - qqq_final_val) / qqq_final_val) * 100
    
    return {
        "Final Portfolio ($)": round(final_val, 2),
        "Net Profit ($)": round(net_profit, 2),
        "ROI (%)": round(roi, 2),
        "Max Drawdown (%)": round(max_dd, 2),
        "vs QQQ ($)": round(diff_vs_qqq_dlr, 2),
        "vs QQQ (%)": round(diff_vs_qqq_pct, 2)
    }

results = {name: calc_metrics(series) for name, series in simulations.items()}
summary_df = pd.DataFrame(results).T

print("\n" + "=" * 115)
print("             AAOI MACRO EXIT COMPARISON RESULTS (2015 - 2026)")
print("                 (Includes Relative Metrics vs 100% QQQ Hold)")
print("===========================================================================================================")
print(summary_df.to_string())
print("=" * 115)

# ==========================================
# 5. VISUALIZATION
# ==========================================
plt.figure(figsize=(14, 8))

# Passive Index Baselines
plt.plot(simulations["Benchmark: 100% QQQ"].index, 
         simulations["Benchmark: 100% QQQ"].values, 
         label="Benchmark: 100% QQQ", color="gray", linestyle=":", linewidth=2)
plt.plot(simulations["Benchmark: 100% VOO"].index, 
         simulations["Benchmark: 100% VOO"].values, 
         label="Benchmark: 100% VOO", color="darkgray", linestyle=":", linewidth=2)

# Base AAOI Strategy
plt.plot(simulations["Base: Buy & Hold (AAOI + QQQ Sweep)"].index, 
         simulations["Base: Buy & Hold (AAOI + QQQ Sweep)"].values, 
         label="Base: AAOI Buy & Hold", color="black", linestyle="--", alpha=0.6)

# Chandelier Group
plt.plot(simulations["Chandelier Trailing Exit (3x ATR)"].index, 
         simulations["Chandelier Trailing Exit (3x ATR)"].values, 
         label="Chandelier 3x ATR", linewidth=1.5)
plt.plot(simulations["Chandelier Trailing Exit (5x ATR)"].index, 
         simulations["Chandelier Trailing Exit (5x ATR)"].values, 
         label="Chandelier 5x ATR", linewidth=1.5)
plt.plot(simulations["Chandelier Trailing Exit (6x ATR)"].index, 
         simulations["Chandelier Trailing Exit (6x ATR)"].values, 
         label="Chandelier 6x ATR", linewidth=2, color="crimson")

# DMA & Donchian Group
plt.plot(simulations["DMA Exit (100 DMA)"].index, 
         simulations["DMA Exit (100 DMA)"].values, 
         label="100 DMA Exit", linewidth=1.5, linestyle="-.")
plt.plot(simulations["DMA Exit (200 DMA)"].index, 
         simulations["DMA Exit (200 DMA)"].values, 
         label="200 DMA Exit", linewidth=1.5, linestyle="-.")
plt.plot(simulations["Donchian Exit (22d Lower Bound)"].index, 
         simulations["Donchian Exit (22d Lower Bound)"].values, 
         label="Donchian 22d Low Exit", linewidth=1.5, linestyle=":")
plt.plot(simulations["Donchian Exit (55d Lower Bound)"].index, 
         simulations["Donchian Exit (55d Lower Bound)"].values, 
         label="Donchian 55d Low Exit", linewidth=1.5, linestyle=":")

plt.axhline(INITIAL_CAPITAL, color='black', linestyle='-', alpha=0.2, label=f"Initial Capital (${INITIAL_CAPITAL:,.0f})")
plt.title("AAOI Strategy Comparison vs. Pure Index Benchmarks (QQQ & VOO)")
plt.xlabel("Date")
plt.ylabel("Total Portfolio Equity ($)")
plt.legend(loc="upper left")
plt.grid(True)
plt.tight_layout()
plt.show()

'''
===================================================================================================================
             AAOI MACRO EXIT COMPARISON RESULTS (2015 - 2026)
                 (Includes Relative Metrics vs 100% QQQ Hold)
===========================================================================================================
                                     Final Portfolio ($)  Net Profit ($)  ROI (%)  Max Drawdown (%)  vs QQQ ($)  vs QQQ (%)
Benchmark: 100% QQQ                           1480671.40      1280671.40   640.34            -35.12        0.00        0.00
Benchmark: 100% VOO                            899876.89       699876.89   349.94            -33.99  -580794.52      -39.23
Base: Buy & Hold (AAOI + QQQ Sweep)           1454395.83      1254395.83   627.20            -35.22   -26275.58       -1.77
Chandelier Trailing Exit (3x ATR)             1483277.13      1283277.13   641.64            -35.12     2605.73        0.18
Chandelier Trailing Exit (5x ATR)             1485183.02      1285183.02   642.59            -35.14     4511.61        0.30
Chandelier Trailing Exit (6x ATR)             1523182.74      1323182.74   661.59            -35.14    42511.34        2.87
DMA Exit (100 DMA)                            1518757.74      1318757.74   659.38            -35.12    38086.33        2.57
DMA Exit (200 DMA)                            1480119.12      1280119.12   640.06            -35.12     -552.29       -0.04
Donchian Exit (22d Lower Bound)               1485424.05      1285424.05   642.71            -35.15     4752.64        0.32
Donchian Exit (55d Lower Bound)               1513749.75      1313749.75   656.87            -35.15    33078.35        2.23
===================================================================================================================
'''