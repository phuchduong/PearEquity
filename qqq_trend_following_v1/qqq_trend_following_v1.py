#!/usr/bin/env python3
"""
Strategy Name: QQQ Moving Average Alignment Backtest vs. Buy and Hold
Description: Trend-following system that enters long positions when the price and 
             moving averages are completely stacked in a bullish configuration, 
             and exits when everything breaks below the long-term trend line.
             Includes a baseline comparison to a passive Buy and Hold strategy.

Rules:
  - Entry: Price > 50 DMA > 100 DMA > 200 DMA
  - Exit: Price < 200 DMA AND 50 DMA < 200 DMA AND 100 DMA < 200 DMA
  - Capital: $10,000 starting allocation
  - Timeline: Max historical data starting from QQQ inception (March 10, 1999)
"""

import backtrader as bt
import yfinance as yf

class MaAlignmentStrategy(bt.Strategy):
    def __init__(self):
        self.dataclose = self.datas[0].close
        
        # Define the moving averages
        self.dma50 = bt.indicators.SimpleMovingAverage(self.datas[0], period=50)
        self.dma100 = bt.indicators.SimpleMovingAverage(self.datas[0], period=100)
        self.dma200 = bt.indicators.SimpleMovingAverage(self.datas[0], period=200)
        
        # Variables to track Buy and Hold performance
        self.initial_cash = 10000.0
        self.bh_shares = 0
        self.bh_initialized = False

    def next(self):
        # Initialize Buy and Hold calculation on the first available data point
        if not self.bh_initialized:
            self.bh_shares = self.initial_cash / self.dataclose[0]
            self.bh_initialized = True

        # Active Strategy Logic
        if not self.position:
            # Entry condition: Price > 50 DMA > 100 DMA > 200 DMA
            if (self.dataclose[0] > self.dma50[0] and 
                self.dma50[0] > self.dma100[0] and 
                self.dma100[0] > self.dma200[0]):
                
                cash = self.broker.get_cash()
                size = int((cash * 0.95) / self.dataclose[0])
                if size > 0:
                    self.buy(size=size)
                    print(f"BUY ORDER PLACED | Price: {self.dataclose[0]:.2f} | Size: {size}")
        else:
            # Exit condition: Price < 200 DMA AND 50 DMA < 200 DMA AND 100 DMA < 200 DMA
            if (self.dataclose[0] < self.dma200[0] and 
                self.dma50[0] < self.dma200[0] and 
                self.dma100[0] < self.dma200[0]):
                
                self.close()
                print(f"SELL ORDER PLACED | Price: {self.dataclose[0]:.2f}")

    def stop(self):
        # Calculate final value for Buy and Hold baseline at the end of the backtest
        final_bh_value = self.bh_shares * self.dataclose[0]
        final_strategy_value = self.broker.getvalue()
        
        print("\n==================================================")
        print("FINAL BACKTEST PERFORMANCE COMPARISON")
        print("==================================================")
        print(f"Starting Capital:        ${self.initial_cash:,.2f}")
        print(f"Active MA Strategy:      ${final_strategy_value:,.2f}")
        print(f"Passive Buy and Hold:    ${final_bh_value:,.2f}")
        
        difference = final_strategy_value - final_bh_value
        if difference > 0:
            print(f"Result: Active strategy outperformed Buy and Hold by ${difference:,.2f}")
        else:
            print(f"Result: Buy and Hold outperformed Active strategy by ${abs(difference):,.2f}")
        print("==================================================")


if __name__ == "__main__":
    cerebro = bt.Cerebro()
    
    # Download QQQ historical data via yfinance starting from its official inception date
    data_df = yf.download("QQQ", start="1999-03-10", end="2026-07-01")
    
    # Clean the multi-index columns if yfinance returns them
    if isinstance(data_df.columns, bt.utils.py3.string_types) == False:
        data_df.columns = data_df.columns.get_level_values(0)
        
    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)
    
    # Add strategy
    cerebro.addstrategy(MaAlignmentStrategy)
    
    # Set starting capital
    cerebro.broker.setcash(10000.0)
    
    print("Running backtest engine...")
    cerebro.run()