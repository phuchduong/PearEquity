"""
================================================================================
SCRIPT HEADER & OVERVIEW
================================================================================
Script Name:    aaoi_macro_exits_backtest.py
Description:    Backtests algorithmic trend-following and macro exit strategies 
                for Applied Optoelectronics, Inc. (AAOI) against QQQ and VOO 
                benchmarks.
                
                The engine records every transactional event (entries, pyramids, 
                take-profit tiers, macro exits, and stagnation exits) to a date-
                stamped log file suitable for Gemini prompt analysis.
================================================================================
"""

import sys
import os
import datetime
import numpy as np
import pandas as pd
import yfinance as yf


# ==============================================================================
# SECTION 0: GLOBAL PARAMETERS & CONFIGURATION
# ==============================================================================
"""
PARAMETER DESCRIPTIONS:
- FETCH_START_DATE: Historical data fetching start date to allow technical indicators (e.g., 200 DMA) to warm up.
- FETCH_END_DATE: Backtest evaluation end date.
- BACKTEST_START_DATE: Effective evaluation start date for trading strategies.
- INITIAL_CAPITAL: Starting portfolio value in USD (allocated initially to QQQ).
- LOG_EVENT_LEVEL: Controls detailed trade event tracing (buys, sells, exits) into the log file.
"""
FETCH_START_DATE = "2013-06-01"
FETCH_END_DATE = "2026-08-04"
BACKTEST_START_DATE = "2015-01-01"
INITIAL_CAPITAL = 200000.0


# ==============================================================================
# SECTION 1: LOGGING SETUP & FILE SYSTEM INITIALIZATION
# ==============================================================================
"""
Sets up a double-logging pipeline that outputs formatted summary tables to both 
the console standard output and a dedicated timestamped log file.

Log Filename Pattern: <Script_Base_Name>_YYYY-MM-DD.txt
"""
def get_log_filename():
    # Retrieve current script name without directory paths or file extension
    if hasattr(sys.modules['__main__'], '__file__'):
        script_path = sys.modules['__main__'].__file__
        base_name = os.path.splitext(os.path.basename(script_path))[0]
    else:
        base_name = "aaoi_backtest"

    date_suffix = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"{base_name}_{date_suffix}.txt"

LOG_FILENAME = get_log_filename()

class DualLogger:
    """Redirects stdout to both console output and an appended text log file."""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log_file = open(filename, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()

# Activate dual logging stdout capture
logger = DualLogger(LOG_FILENAME)
sys.stdout = logger


# ==============================================================================
# SECTION 2: DATA ACQUISITION & INDICATOR CALCULATION
# ==============================================================================
"""
Fetches historical OHLCV data from Yahoo Finance, aligns common trading dates,
and computes core technical indicators:
1. Donchian Channels (55-day High, 22-day Low, 55-day Low)
2. Simple Moving Averages (100 DMA, 200 DMA)
3. Average True Range (14-day ATR)
"""
print("=" * 80)
print(f"INITIALIZING BACKTEST ENGINE | LOG FILE: {LOG_FILENAME}")
print("=" * 80)
print(f"Fetching clean market data for AAOI, QQQ, and VOO ({FETCH_START_DATE} to {FETCH_END_DATE})...")

aaoi_raw = yf.download("AAOI", start=FETCH_START_DATE, end=FETCH_END_DATE, progress=False)
qqq_raw = yf.download("QQQ", start=FETCH_START_DATE, end=FETCH_END_DATE, progress=False)
voo_raw = yf.download("VOO", start=FETCH_START_DATE, end=FETCH_END_DATE, progress=False)

# Flatten columns if yfinance returns a MultiIndex DataFrame
for df in [aaoi_raw, qqq_raw, voo_raw]:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

# Align dataset index
common_idx = aaoi_raw.index.intersection(qqq_raw.index).intersection(voo_raw.index)

aaoi = aaoi_raw.loc[common_idx, ["Close", "High", "Low"]].copy()
qqq = qqq_raw.loc[common_idx, ["Close"]].copy()
voo = voo_raw.loc[common_idx, ["Close"]].copy()

# Compute Donchian Channels
aaoi["Donchian_55_High"] = aaoi["High"].shift(1).rolling(55).max()
aaoi["Donchian_22_Low"] = aaoi["Low"].shift(1).rolling(22).min()
aaoi["Donchian_55_Low"] = aaoi["Low"].shift(1).rolling(55).min()

# Compute Moving Averages
aaoi["DMA_100"] = aaoi["Close"].rolling(100).mean()
aaoi["DMA_200"] = aaoi["Close"].rolling(200).mean()

# Compute 14-day True Range and ATR
high_low = aaoi["High"] - aaoi["Low"]
high_close = np.abs(aaoi["High"] - aaoi["Close"].shift(1))
low_close = np.abs(aaoi["Low"] - aaoi["Close"].shift(1))
tr = np.maximum(high_low, np.maximum(high_close, low_close))
aaoi["ATR_14"] = tr.rolling(14).mean()

# Slice to backtest evaluation window
aaoi = aaoi.loc[BACKTEST_START_DATE:].copy()
qqq = qqq.loc[BACKTEST_START_DATE:].copy()
voo = voo.loc[BACKTEST_START_DATE:].copy()


# ==============================================================================
# SECTION 3: PORTFOLIO & AUDIT TRACKING CLASS
# ==============================================================================
"""
Manages cash/equity allocations, active positions, average cost tracking, 
and logs granular transaction actions (BUY, SELL_PARTIAL, EXIT) for AI analysis.
"""
class Portfolio:
    def __init__(self, initial_cash):
        self.qqq_shares = initial_cash / qqq["Close"].iloc[0]
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.initial_entry_spend = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0

        self.tp1_taken = False
        self.tp2_taken = False
        self.tp3_taken = False
        self.tp4_taken = False

    def buy_aaoi(self, date, price, target_spend, reason, log_events=False, event_logs=None):
        qqq_price = qqq.loc[date, "Close"]
        max_available = self.qqq_shares * qqq_price
        spend = min(target_spend, max_available)

        shares_to_buy = spend / price
        if shares_to_buy > 0:
            self.qqq_shares -= spend / qqq_price
            total_shares = self.aaoi_shares + shares_to_buy

            if self.aaoi_shares == 0:
                self.aaoi_avg_cost = price
                self.initial_entry_spend = spend
            else:
                self.aaoi_avg_cost = (
                    (self.aaoi_shares * self.aaoi_avg_cost) + (shares_to_buy * price)
                ) / total_shares

            self.aaoi_shares = total_shares
            self.last_buy_date = date
            self.last_buy_price = price
            if self.peak_price == 0:
                self.peak_price = price

            if log_events and event_logs is not None:
                dt_str = date.strftime("%Y-%m-%d")
                event_logs.append(
                    f"[{dt_str}] ACTION: BUY | Shares: {shares_to_buy:10.2f} @ ${price:7.2f} | "
                    f"Cost Basis: ${self.aaoi_avg_cost:7.2f} | Reason: {reason}"
                )

    def sell_partial_aaoi(self, date, price, pct_of_current, reason, log_events=False, event_logs=None):
        if self.aaoi_shares <= 0:
            return

        shares_to_sell = self.aaoi_shares * pct_of_current
        proceeds = shares_to_sell * price
        self.aaoi_shares -= shares_to_sell

        qqq_price = qqq.loc[date, "Close"]
        self.qqq_shares += proceeds / qqq_price

        if log_events and event_logs is not None:
            dt_str = date.strftime("%Y-%m-%d")
            event_logs.append(
                f"[{dt_str}] ACTION: PARTIAL SELL ({pct_of_current*100:.0f}%) | "
                f"Shares Sold: {shares_to_sell:10.2f} @ ${price:7.2f} | "
                f"Remaining: {self.aaoi_shares:10.2f} | Reason: {reason}"
            )

    def sell_all_aaoi(self, date, price, reason, log_events=False, event_logs=None):
        if self.aaoi_shares <= 0:
            return

        sold_shares = self.aaoi_shares
        proceeds = self.aaoi_shares * price
        
        if log_events and event_logs is not None:
            dt_str = date.strftime("%Y-%m-%d")
            event_logs.append(
                f"[{dt_str}] ACTION: FULL EXIT | Shares Sold: {sold_shares:10.2f} @ ${price:7.2f} | "
                f"Proceeds: ${proceeds:10.2f} | Reason: {reason}"
            )

        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.initial_entry_spend = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0

        self.tp1_taken = False
        self.tp2_taken = False
        self.tp3_taken = False
        self.tp4_taken = False

        qqq_price = qqq.loc[date, "Close"]
        self.qqq_shares += proceeds / qqq_price

    def total_value(self, date, aaoi_price):
        qqq_price = qqq.loc[date, "Close"]
        return (self.qqq_shares * qqq_price) + (self.aaoi_shares * aaoi_price)


# ==============================================================================
# SECTION 4: BACKTEST SIMULATION ENGINE & METRICS
# ==============================================================================
"""
Calculates risk metrics and iterates through trade logic rules.
- Entry: Donchian 55-day High breakout.
- Pyramiding: Price > 5% above prior buy price after 30 days.
- Take Profit Rules: Multi-tier ratio-based or ATR-based profit taking.
- Macro Exits: Chandelier Trailing Stop, Moving Average Breaches, Donchian Channel Lows.
- Stagnation Exit: Exit if price stays >30% below peak for 180 trading days.
"""
def calculate_metrics(equity_series: pd.Series, qqq_baseline_series: pd.Series) -> dict:
    final_val = float(equity_series.iloc[-1])
    qqq_final_val = float(qqq_baseline_series.iloc[-1])

    net_profit = final_val - INITIAL_CAPITAL
    roi = (net_profit / INITIAL_CAPITAL) * 100

    cummax = equity_series.cummax()
    drawdown = ((equity_series - cummax) / cummax) * 100
    max_dd = float(drawdown.min())

    vs_qqq_val = final_val - qqq_final_val
    vs_qqq_pct = (vs_qqq_val / qqq_final_val) * 100 if qqq_final_val != 0 else 0.0

    return {
        "Final Portfolio ($)": final_val,
        "Net Profit ($)": net_profit,
        "ROI (%)": roi,
        "Max Drawdown (%)": max_dd,
        "vs QQQ ($)": vs_qqq_val,
        "vs QQQ (%)": vs_qqq_pct,
    }

def run_buy_and_hold(asset_close_series: pd.Series) -> pd.Series:
    initial_shares = INITIAL_CAPITAL / asset_close_series.iloc[0]
    return initial_shares * asset_close_series

def run_exit_strategy(exit_type, param=None, tp_mode="none", log_events=False):
    p = Portfolio(INITIAL_CAPITAL)
    equity = []
    event_logs = []

    for date, row in aaoi.iterrows():
        price = row["Close"]
        high = row["High"]
        donchian_high = row["Donchian_55_High"]
        atr = row["ATR_14"]

        if pd.isna(donchian_high):
            equity.append(p.total_value(date, price))
            continue

        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            trigger_full_exit = False
            exit_reason = ""

            # Take Profit Checks
            if tp_mode != "none" and p.aaoi_avg_cost > 0:
                cost_ratio = price / p.aaoi_avg_cost

                if tp_mode == "atr_tp" and pd.notna(atr):
                    if not p.tp1_taken and price >= (p.aaoi_avg_cost + 3.0 * atr):
                        p.sell_partial_aaoi(date, price, 0.25, "ATR Take Profit Tier 1 (+3x ATR)", log_events, event_logs)
                        p.tp1_taken = True
                    if not p.tp2_taken and price >= (p.aaoi_avg_cost + 6.0 * atr):
                        p.sell_partial_aaoi(date, price, 0.25, "ATR Take Profit Tier 2 (+6x ATR)", log_events, event_logs)
                        p.tp2_taken = True
                    if not p.tp3_taken and price >= (p.aaoi_avg_cost + 10.0 * atr):
                        p.sell_partial_aaoi(date, price, 0.25, "ATR Take Profit Tier 3 (+10x ATR)", log_events, event_logs)
                        p.tp3_taken = True
                else:
                    if not p.tp1_taken and cost_ratio >= 2.0:
                        p.sell_partial_aaoi(date, price, 0.25, "2-Tier Take Profit (2x Cost Basis)", log_events, event_logs)
                        p.tp1_taken = True
                    if not p.tp2_taken and cost_ratio >= 3.0:
                        p.sell_partial_aaoi(date, price, 0.25, "2-Tier Take Profit (3x Cost Basis)", log_events, event_logs)
                        p.tp2_taken = True
                    if tp_mode == "4tier":
                        if not p.tp3_taken and cost_ratio >= 4.0:
                            p.sell_partial_aaoi(date, price, 0.25, "4-Tier Take Profit (4x Cost Basis)", log_events, event_logs)
                            p.tp3_taken = True
                        if not p.tp4_taken and cost_ratio >= 5.0:
                            trigger_full_exit = True
                            exit_reason = "4-Tier Take Profit Final Tier (5x Cost Basis Target Reached)"

            # Macro Exit Checks
            if not trigger_full_exit:
                if exit_type == "chandelier":
                    if price < (p.peak_price - param * atr):
                        trigger_full_exit = True
                        exit_reason = f"Chandelier Exit Breach ({param}x ATR below peak of ${p.peak_price:.2f})"
                elif exit_type == "dma":
                    dma_val = row[f"DMA_{param}"]
                    if pd.notna(dma_val) and price < dma_val:
                        trigger_full_exit = True
                        exit_reason = f"DMA Breach (Price closed below DMA {param} at ${dma_val:.2f})"
                elif exit_type == "donchian_low":
                    donchian_low_val = row[f"Donchian_{param}_Low"]
                    if pd.notna(donchian_low_val) and price < donchian_low_val:
                        trigger_full_exit = True
                        exit_reason = f"Donchian Low Breach (Price closed below {param}-day low at ${donchian_low_val:.2f})"

                # 180-day Stagnation Exit
                if (price - p.peak_price) / p.peak_price < -0.30:
                    p.days_below_30pct += 1
                else:
                    p.days_below_30pct = 0

                if p.days_below_30pct >= 180:
                    trigger_full_exit = True
                    exit_reason = "Stagnation Exit (180 consecutive days >30% below peak)"

            if trigger_full_exit:
                p.sell_all_aaoi(date, price, exit_reason, log_events, event_logs)

        # Entry and Pyramiding Logic
        if p.aaoi_shares == 0:
            if price > donchian_high:
                qqq_val = p.qqq_shares * qqq.loc[date, "Close"]
                p.buy_aaoi(date, price, target_spend=qqq_val, reason=f"Initial Breakout Entry (Donchian 55 High at ${donchian_high:.2f})", log_events=log_events, event_logs=event_logs)
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                if (price - p.last_buy_price) / p.last_buy_price > 0.05:
                    pyramid_spend = p.initial_entry_spend * 0.10
                    p.buy_aaoi(date, price, target_spend=pyramid_spend, reason="Pyramid Add (+5% Gain after 30+ Days)", log_events=log_events, event_logs=event_logs)

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index), event_logs


# ==============================================================================
# SECTION 5: EXECUTION PIPELINE & BENCHMARK COMPARISON
# ==============================================================================
"""
Runs strategy iterations, constructs metric tables, prints results to stdout/log,
and appends execution logs for LLM backtest evaluation.
"""
qqq_equity = run_buy_and_hold(qqq["Close"])
voo_equity = run_buy_and_hold(voo["Close"])

results = []
strategy_event_logs = {}

# Benchmarks
m_qqq = calculate_metrics(qqq_equity, qqq_equity)
m_qqq["Strategy"] = "Benchmark: 100% QQQ"
results.append(m_qqq)

m_voo = calculate_metrics(voo_equity, qqq_equity)
m_voo["Strategy"] = "Benchmark: 100% VOO"
results.append(m_voo)

# Strategy Configurations Array
strategy_configs = [
    ("Chandelier 3x ATR", "chandelier", 3.0, "none"),
    ("Chandelier 3x ATR (2-Tier Take Profit)", "chandelier", 3.0, "2tier"),
    ("Chandelier 3x ATR (4-Tier Take Profit)", "chandelier", 3.0, "4tier"),
    ("Chandelier 3x ATR (ATR-Based Take Profit)", "chandelier", 3.0, "atr_tp"),
    ("Chandelier 5x ATR", "chandelier", 5.0, "none"),
    ("Chandelier 5x ATR (2-Tier Take Profit)", "chandelier", 5.0, "2tier"),
    ("Chandelier 5x ATR (4-Tier Take Profit)", "chandelier", 5.0, "4tier"),
    ("Chandelier 5x ATR (ATR-Based Take Profit)", "chandelier", 5.0, "atr_tp"),
    ("Chandelier 6x ATR", "chandelier", 6.0, "none"),
    ("Chandelier 6x ATR (2-Tier Take Profit)", "chandelier", 6.0, "2tier"),
    ("Chandelier 6x ATR (4-Tier Take Profit)", "chandelier", 6.0, "4tier"),
    ("Chandelier 6x ATR (ATR-Based Take Profit)", "chandelier", 6.0, "atr_tp"),
    ("DMA 100 Exit", "dma", 100, "none"),
    ("DMA 100 Exit (2-Tier Take Profit)", "dma", 100, "2tier"),
    ("DMA 100 Exit (4-Tier Take Profit)", "dma", 100, "4tier"),
    ("DMA 100 Exit (ATR-Based Take Profit)", "dma", 100, "atr_tp"),
    ("DMA 200 Exit", "dma", 200, "none"),
    ("DMA 200 Exit (2-Tier Take Profit)", "dma", 200, "2tier"),
    ("DMA 200 Exit (4-Tier Take Profit)", "dma", 200, "4tier"),
    ("DMA 200 Exit (ATR-Based Take Profit)", "dma", 200, "atr_tp"),
    ("Donchian 22d Low Exit", "donchian_low", 22, "none"),
    ("Donchian 22d Low Exit (2-Tier Take Profit)", "donchian_low", 22, "2tier"),
    ("Donchian 22d Low Exit (4-Tier Take Profit)", "donchian_low", 22, "4tier"),
    ("Donchian 22d Low Exit (ATR-Based Take Profit)", "donchian_low", 22, "atr_tp"),
    ("Donchian 55d Low Exit", "donchian_low", 55, "none"),
    ("Donchian 55d Low Exit (2-Tier Take Profit)", "donchian_low", 55, "2tier"),
    ("Donchian 55d Low Exit (4-Tier Take Profit)", "donchian_low", 55, "4tier"),
    ("Donchian 55d Low Exit (ATR-Based Take Profit)", "donchian_low", 55, "atr_tp"),
]

print("\nRunning backtest simulations across strategies...\n")

for name, stype, param, tp in strategy_configs:
    eq, logs = run_exit_strategy(stype, param, tp, log_events=True)
    m = calculate_metrics(eq, qqq_equity)
    m["Strategy"] = name
    results.append(m)
    strategy_event_logs[name] = logs

df_res = pd.DataFrame(results)

# ==============================================================================
# SECTION 6: RESULTS SUMMARY TABLE DISPLAY
# ==============================================================================
print("\n" + "=" * 135)
print(f"{'AAOI MACRO EXIT & EXTENDED TAKE-PROFIT COMPARISON RESULTS (2015 - 2026)':^135}")
print("=" * 135)
print(f"{'Strategy':<45} {'Final Portfolio ($)':>18} {'Net Profit ($)':>16} {'ROI (%)':>9} {'Max Drawdown (%)':>17} {'vs QQQ ($)':>13} {'vs QQQ (%)':>11}")
print("-" * 135)

for _, r in df_res.iterrows():
    print(f"{r['Strategy']:<45} {r['Final Portfolio ($)']:18.2f} {r['Net Profit ($)']:16.2f} {r['ROI (%)']:9.2f} {r['Max Drawdown (%)']:17.2f} {r['vs QQQ ($)']:13.2f} {r['vs QQQ (%)']:11.2f}")

print("=" * 135 + "\n")


# ==============================================================================
# SECTION 7: DETAILED STRATEGY ACTION LOGS FOR GEMINI ANALYSIS
# ==============================================================================
"""
Outputs detailed transactional trace sequences DIRECTLY to the log file.
These logs bypass console stdout to keep terminal output clean while preserving
full event history for Gemini prompt analysis.
"""
log_file = logger.log_file  # Directly access the underlying log file handle

log_file.write("=" * 135 + "\n")
log_file.write(f"{'DETAILED STRATEGY TRANSACTION ACTION LOGS FOR GEMINI PROMPT ANALYSIS':^135}\n")
log_file.write("=" * 135 + "\n")

for name, logs in strategy_event_logs.items():
    log_file.write(f"\n--- STRATEGY: {name} ---\n")
    if not logs:
        log_file.write("  [No trades executed during this backtest window]\n")
    else:
        for log_entry in logs:
            log_file.write(f"  {log_entry}\n")

log_file.write("\n" + "=" * 135 + "\n")
log_file.write(f"BACKTEST COMPLETE | LOG SAVED TO {LOG_FILENAME}\n")
log_file.write("=" * 135 + "\n")

# Console notice once file logging finishes
print(f"Detailed trade logs successfully written to {LOG_FILENAME}.")

# Restore stdout and close file handle
sys.stdout = logger.terminal
logger.close()
