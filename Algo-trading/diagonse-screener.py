#!/usr/bin/env python3
"""
diagnose_screener.py with tunable thresholds
"""

import yfinance as yf
import pandas as pd
import talib
import random
import time

# ←––––– TUNE THESE ––––––→
RSI_THRESHOLD     = 50    # was 35
ATR_THRESHOLD     = 0.08  # was 0.06
PE_MAX           = 25
ROE_MIN          = 0.10
MA_MIN_DAYS      = 20     # days for MA crossover
MA_SLOW_DAYS     = 50

def get_sp500_tickers():
    df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    return df["Symbol"].dropna().tolist()

def safe_arr(series):
    return series.values.flatten().astype(float)

def debug_candidate(ticker):
    df = yf.download(ticker, period="90d", interval="1d", progress=False)
    if df.empty or len(df) < 60:
        return False, f"{ticker}: insufficient data"
    
    info = yf.Ticker(ticker).info
    pe, roe = info.get("forwardPE"), info.get("returnOnEquity")
    if pe is None or roe is None or pe > PE_MAX or roe < ROE_MIN:
        return False, f"{ticker}: PE/ROE filter ({pe=}, {roe=})"
    
    # MA Crossover
    df["MA_FAST"] = df["Close"].rolling(MA_MIN_DAYS).mean()
    df["MA_SLOW"] = df["Close"].rolling(MA_SLOW_DAYS).mean()
    ma_ok = df["MA_FAST"].iloc[-1] > df["MA_SLOW"].iloc[-1]
    
    close = safe_arr(df["Close"])
    rsi   = talib.RSI(close, timeperiod=14)[-1]
    rsi_ok = rsi < RSI_THRESHOLD
    
    atr   = talib.ATR(
        safe_arr(df["High"]), safe_arr(df["Low"]), close, timeperiod=14
    )[-1]
    atr_pct = atr / close[-1]
    vol_ok  = atr_pct < ATR_THRESHOLD
    
    if ma_ok and rsi_ok and vol_ok:
        return True, f"{ticker}: PASS (RSI={rsi:.1f} < {RSI_THRESHOLD}, ATR%={atr_pct:.3f} < {ATR_THRESHOLD})"
    else:
        reason = []
        if not ma_ok:     reason.append("MA✗")
        if not rsi_ok:    reason.append(f"RSI={rsi:.1f}✗")
        if not vol_ok:    reason.append(f"ATR%={atr_pct:.3f}✗")
        return False, f"{ticker}: {' & '.join(reason)}"
    
def run_test_batch(n=10):
    universe = get_sp500_tickers()
    sample   = random.sample(universe, n)
    results  = {"pass": 0, "fail": 0}
    
    for t in sample:
        ok, msg = debug_candidate(t)
        print(msg)
        if ok:    results["pass"] += 1
        else:     results["fail"] += 1
        time.sleep(1)
    
    print(f"\n→ {results['pass']}/{n} passed under thresholds:"
          f" RSI<{RSI_THRESHOLD}, ATR%<{ATR_THRESHOLD}")

if __name__ == "__main__":
    run_test_batch()
