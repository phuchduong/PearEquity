"""
================================================================================
BACKTEST SCRIPT: AAOI MACRO EXITS WITH PROMPT-READY ACTION LOGS
================================================================================
OBJECTIVE:
    Runs backtests for AAOI exit strategies (including standard, 2-tier, and 
    4-tier take-profit variants), calculates comparative portfolio metrics,
    and extracts formatted price action event logs suitable for AI analysis.
    
LOGGING BEHAVIOR:
    - Results table is printed directly in the execution prompt and written
      at the top of the output log file.
    - Full execution & price action logs are written to a .txt file named:
      <script_name>_YYYY-MM-DD.txt
================================================================================
"""

import sys
import os
import datetime
import numpy as np
import pandas as pd
import yfinance as yf

# ==========================================
# 0. SETUP LOG FILE NAME & PATH
# ==========================================
try:
    script_path = os.path.basename(__file__)
    script_name = os.path.splitext(script_path)[0]
except NameError:
    # Fallback if executing in an interactive shell / REPL
    script_name = "aaoi_macro_exits"

current_date = datetime.datetime.now().strftime("%Y-%m-%d")
log_filename = f"{script_name}_{current_date}.txt"

# ==========================================
# 1. DATA FETCHING & PREPARATION
# ==========================================
symbols = ["AAOI", "QQQ", "VOO"]
start_date = "2013-06-01"  # Buffer for technical indicators
end_date = "2026-08-04"
INITIAL_CAPITAL = 200000.0

print(f"Fetching market data for AAOI, QQQ, and VOO...")
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
# 2. HELPER CLASS FOR PORTFOLIO & LOGGING
# ==========================================
class Portfolio:
    """Manages positions in AAOI and QQQ while logging price action events."""
    def __init__(self, initial_cash):
        self.qqq_shares = 0.0
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0
        
        # Flags for progressive 4-tier take-profit tranches
        self.tp1_taken = False
        self.tp2_taken = False
        self.tp3_taken = False
        self.tp4_taken = False
        
        # Action Log Storage
        self.action_logs = []
        
        # Deploy initial capital into QQQ
        first_qqq_price = qqq['Close'].iloc[0]
        self.qqq_shares = initial_cash / first_qqq_price

    def log_event(self, date, action_type, price, details=""):
        date_str = pd.to_datetime(date).strftime("%Y-%m-%d")
        total_val = self.total_value(date, price)
        self.action_logs.append({
            "Date": date_str,
            "Action": action_type,
            "AAOI_Price": round(price, 2),
            "Avg_Cost": round(self.aaoi_avg_cost, 2),
            "Remaining_Shares": round(self.aaoi_shares, 2),
            "Portfolio_Val": round(total_val, 2),
            "Details": details
        })

    def buy_aaoi(self, date, price, dollar_amount, action_label="BUY_ENTRY"):
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

            self.log_event(date, action_label, price, f"Bought {shares_to_buy:.2f} shares for ${spend:,.2f}")

    def sell_partial_aaoi(self, date, price, pct_of_current, action_label="TAKE_PROFIT"):
        if self.aaoi_shares <= 0:
            return
        
        shares_to_sell = self.aaoi_shares * pct_of_current
        proceeds = shares_to_sell * price
        self.aaoi_shares -= shares_to_sell
        
        qqq_price = qqq.loc[date, 'Close']
        self.qqq_shares += proceeds / qqq_price

        self.log_event(date, action_label, price, f"Sold {shares_to_sell:.2f} shares for ${proceeds:,.2f} proceeds to QQQ")

    def sell_all_aaoi(self, date, price, action_label="FULL_EXIT"):
        if self.aaoi_shares <= 0:
            return
        
        proceeds = self.aaoi_shares * price
        shares_sold = self.aaoi_shares
        
        self.aaoi_shares = 0.0
        self.aaoi_avg_cost = 0.0
        self.last_buy_date = None
        self.last_buy_price = 0.0
        self.peak_price = 0.0
        self.days_below_30pct = 0
        
        self.tp1_taken = False
        self.tp2_taken = False
        self.tp3_taken = False
        self.tp4_taken = False
        
        qqq_price = qqq.loc[date, 'Close']
        self.qqq_shares += proceeds / qqq_price

        self.log_event(date, action_label, price, f"Closed full position ({shares_sold:.2f} shares) for ${proceeds:,.2f}")

    def total_value(self, date, aaoi_price):
        qqq_price = qqq.loc[date, 'Close']
        return (self.qqq_shares * qqq_price) + (self.aaoi_shares * aaoi_price)


# ==========================================
# 3. SIMULATION ENGINES
# ==========================================
def calculate_metrics(equity_series, benchmark_series):
    net_profit = equity_series.iloc[-1] - INITIAL_CAPITAL
    roi = (net_profit / INITIAL_CAPITAL) * 100
    cummax = equity_series.cummax()
    drawdown = ((equity_series - cummax) / cummax) * 100
    max_dd = drawdown.min()
    
    vs_qqq_val = equity_series.iloc[-1] - benchmark_series.iloc[-1]
    vs_qqq_pct = ((equity_series.iloc[-1] - benchmark_series.iloc[-1]) / benchmark_series.iloc[-1]) * 100
    
    return {
        "Final Portfolio ($)": equity_series.iloc[-1],
        "Net Profit ($)": net_profit,
        "ROI (%)": roi,
        "Max Drawdown (%)": max_dd,
        "vs QQQ ($)": vs_qqq_val,
        "vs QQQ (%)": vs_qqq_pct
    }

def run_buy_and_hold(asset_df):
    initial_shares = INITIAL_CAPITAL / asset_df['Close'].iloc[0]
    return initial_shares * asset_df['Close']

def run_exit_strategy(exit_type, param=None, tp_mode="none"):
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

        # Position Management
        if p.aaoi_shares > 0:
            p.peak_price = max(p.peak_price, high)
            trigger_full_exit = False
            exit_reason = ""

            # --- PROGRESSIVE TAKE-PROFIT LOGIC ---
            if tp_mode != "none" and p.aaoi_avg_cost > 0:
                cost_ratio = price / p.aaoi_avg_cost
                
                # Tier 1: +100% Gain (2.0x cost)
                if not p.tp1_taken and cost_ratio >= 2.0:
                    p.sell_partial_aaoi(date, price, 0.25, "TP_TIER_1 (+100%)")
                    p.tp1_taken = True

                # Tier 2: +200% Gain (3.0x cost)
                if not p.tp2_taken and cost_ratio >= 3.0:
                    p.sell_partial_aaoi(date, price, 0.25, "TP_TIER_2 (+200%)")
                    p.tp2_taken = True

                if tp_mode == "4tier":
                    # Tier 3: +300% Gain (4.0x cost)
                    if not p.tp3_taken and cost_ratio >= 4.0:
                        p.sell_partial_aaoi(date, price, 0.25, "TP_TIER_3 (+300%)")
                        p.tp3_taken = True

                    # Tier 4: +400% Gain (5.0x cost -> Full Exit)
                    if not p.tp4_taken and cost_ratio >= 5.0:
                        trigger_full_exit = True
                        exit_reason = "TP_TIER_4 (+400% FULL EXIT)"

            # --- MACRO EXIT EVALUATION ---
            if not trigger_full_exit:
                if exit_type == "chandelier":
                    chandelier_stop = p.peak_price - (param * atr)
                    if price < chandelier_stop:
                        trigger_full_exit = True
                        exit_reason = f"MACRO_EXIT (Chandelier {param}x ATR)"

                elif exit_type == "dma":
                    dma_val = row[f'DMA_{param}']
                    if pd.notna(dma_val) and price < dma_val:
                        trigger_full_exit = True
                        exit_reason = f"MACRO_EXIT (Below DMA {param})"

                elif exit_type == "donchian_low":
                    donchian_low_val = row[f'Donchian_{param}_Low']
                    if pd.notna(donchian_low_val) and price < donchian_low_val:
                        trigger_full_exit = True
                        exit_reason = f"MACRO_EXIT (Below Donchian {param}d Low)"

                # Standard 180-day Stagnation Rule
                drawdown = (price - p.peak_price) / p.peak_price
                if drawdown < -0.30:
                    p.days_below_30pct += 1
                else:
                    p.days_below_30pct = 0

                if p.days_below_30pct >= 180:
                    trigger_full_exit = True
                    exit_reason = "MACRO_EXIT (180-day Stagnation)"

            # Execute Full Exit to QQQ
            if trigger_full_exit:
                p.sell_all_aaoi(date, price, exit_reason)

        # Entry & Scale-In Logic
        if p.aaoi_shares == 0:
            if price > donchian_high:
                p.buy_aaoi(date, price, price, "ENTRY_BUY (Donchian 55 Breakout)")
        else:
            days_passed = (date - p.last_buy_date).days
            if days_passed >= 30:
                appreciation = (price - p.last_buy_price) / p.last_buy_price
                if appreciation > 0.05:
                    p.buy_aaoi(date, price, max(1000.0, price), "PYRAMID_ADD (+5% Appreciation)")

        equity.append(p.total_value(date, price))

    return pd.Series(equity, index=aaoi.index), p.action_logs


# ==========================================
# 4. RUN ALL STRATEGY COMBINATIONS & METRICS
# ==========================================
print("Running strategy simulations...")

# Benchmarks
qqq_equity = run_buy_and_hold(qqq)
voo_equity = run_buy_and_hold(voo)

# Strategy Catalog
all_strategies = {
    "Benchmark: 100% QQQ": (None, None, "benchmark", qqq_equity),
    "Benchmark: 100% VOO": (None, None, "benchmark", voo_equity),
    "Chandelier 3x ATR": ("chandelier", 3.0, "none", None),
    "Chandelier 3x ATR (2-Tier Take Profit)": ("chandelier", 3.0, "2tier", None),
    "Chandelier 3x ATR (4-Tier Take Profit)": ("chandelier", 3.0, "4tier", None),
    "Chandelier 5x ATR": ("chandelier", 5.0, "none", None),
    "Chandelier 5x ATR (2-Tier Take Profit)": ("chandelier", 5.0, "2tier", None),
    "Chandelier 5x ATR (4-Tier Take Profit)": ("chandelier", 5.0, "4tier", None),
    "Chandelier 6x ATR": ("chandelier", 6.0, "none", None),
    "Chandelier 6x ATR (2-Tier Take Profit)": ("chandelier", 6.0, "2tier", None),
    "Chandelier 6x ATR (4-Tier Take Profit)": ("chandelier", 6.0, "4tier", None),
    "DMA 100 Exit": ("dma", 100, "none", None),
    "DMA 100 Exit (2-Tier Take Profit)": ("dma", 100, "2tier", None),
    "DMA 100 Exit (4-Tier Take Profit)": ("dma", 100, "4tier", None),
    "DMA 200 Exit": ("dma", 200, "none", None),
    "DMA 200 Exit (2-Tier Take Profit)": ("dma", 200, "2tier", None),
    "DMA 200 Exit (4-Tier Take Profit)": ("dma", 200, "4tier", None),
    "Donchian 22d Low Exit": ("donchian_low", 22, "none", None),
    "Donchian 22d Low Exit (2-Tier Take Profit)": ("donchian_low", 22, "2tier", None),
    "Donchian 22d Low Exit (4-Tier Take Profit)": ("donchian_low", 22, "4tier", None),
    "Donchian 55d Low Exit": ("donchian_low", 55, "none", None),
    "Donchian 55d Low Exit (2-Tier Take Profit)": ("donchian_low", 55, "2tier", None),
    "Donchian 55d Low Exit (4-Tier Take Profit)": ("donchian_low", 55, "4tier", None),
}

results_list = []
action_logs_dict = {}

for name, (exit_type, param, tp_mode, precalc_eq) in all_strategies.items():
    if exit_type == "benchmark":
        eq = precalc_eq
        logs = []
    else:
        eq, logs = run_exit_strategy(exit_type, param, tp_mode)
        action_logs_dict[name] = logs

    m = calculate_metrics(eq, qqq_equity)
    m["Strategy"] = name
    results_list.append(m)

# Format Results Table
df_results = pd.DataFrame(results_list)
cols = ["Strategy", "Final Portfolio ($)", "Net Profit ($)", "ROI (%)", "Max Drawdown (%)", "vs QQQ ($)", "vs QQQ (%)"]
df_results = df_results[cols]

# Generate Formatted Output Header String
table_header = "=" * 135 + "\n"
table_header += f"{'AAOI MACRO EXIT & EXTENDED TAKE-PROFIT COMPARISON RESULTS (2015 - 2026)':^135}\n"
table_header += f"{'(Includes 2-Tier & 4-Tier Progressive Profit-Taking Variants)':^135}\n"
table_header += "=" * 135 + "\n"

# Column Formats
table_rows = []
header_row = f"{'Strategy':<45} {'Final Portfolio ($)':>18} {'Net Profit ($)':>16} {'ROI (%)':>9} {'Max Drawdown (%)':>17} {'vs QQQ ($)':>13} {'vs QQQ (%)':>11}"
table_rows.append(header_row)

for _, row in df_results.iterrows():
    r_str = f"{row['Strategy']:<45} {row['Final Portfolio ($)']:18.2f} {row['Net Profit ($)']:16.2f} {row['ROI (%)']:9.2f} {row['Max Drawdown (%)']:17.2f} {row['vs QQQ ($)']:13.2f} {row['vs QQQ (%)']:11.2f}"
    table_rows.append(r_str)

table_rows.append("=" * 135)
results_table_str = table_header + "\n".join(table_rows)


# ==========================================
# 5. PRINT TO CONSOLE & WRITE LOG FILE
# ==========================================

# 1. Print Results Table directly to the prompt console
print("\n" + results_table_str + "\n")

# 2. Open text log file and write results table at the beginning, followed by prompt-ready logs
with open(log_filename, "w") as f:
    f.write(results_table_str + "\n\n")
    
    # Prompt Header for Gemini Analysis
    f.write("=" * 135 + "\n")
    f.write("                             COPY/PASTE PROMPT FOR GEMINI STRATEGY ANALYSIS\n")
    f.write("=" * 135 + "\n\n")
    
    prompt_instruction = (
        "PROMPT FOR GEMINI ANALYTICS:\n"
        "You are an expert quantitative trader and portfolio risk manager.\n"
        "Below is the historical execution log containing exact price action events (Entries, Pyramids, Partial Take Profits, and Exits)\n"
        "for the AAOI trading strategy across key market cycles (2015-2026).\n\n"
        "Review the trade logs and execution timeline below and answer:\n"
        "1. What were the biggest weaknesses, false breakouts, or premature exits in this strategy's price action execution?\n"
        "2. How did the 4-tier progressive take-profit mechanism perform relative to holding full positions into major trend reversals?\n"
        "3. What concrete algorithmic adjustments (e.g., dynamic trailing stop scaling, volume filters, RSI overbought overlays) would optimize net returns and drawdown?\n\n"
        "=======================================================================================================\n"
        "                                 AAOI STRATEGY ACTION & PRICE LOGS\n"
        "=======================================================================================================\n\n"
    )
    f.write(prompt_instruction)

    # Write strategy execution logs sequentially to log file
    for strat_name, logs in action_logs_dict.items():
        f.write(f"--- STRATEGY: {strat_name} ---\n")
        log_df = pd.DataFrame(logs)
        if not log_df.empty:
            f.write(log_df.to_string(index=False) + "\n")
        else:
            f.write("No trade events triggered.\n")
        f.write("\n" + "-" * 100 + "\n\n")

print(f"[SUCCESS] Results table printed to prompt. Full prompt-ready execution log saved to: {log_filename}")