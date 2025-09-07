import argparse
import time
import random

import pandas as pd
import yfinance as yf
import talib

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

US_ETF_TICKERS = ["SPY","IVV","VOO","VTI","QQQ","VUG","VTV","BND","AGG","IEMG"]
HK_ETF_TICKERS = ["2800.HK","2805.HK","2836.HK","3040.HK","3110.HK"]

SLEEP_MIN, SLEEP_MAX = 0.3, 0.8
MAX_RETRIES, RETRY_DELAY = 3, 5

# Technical thresholds
RSI_MAX       = 35
ATR_PCT_MAX   = 0.06   # stocks
ETF_ATR_MAX   = 0.05   # ETFs
TECH_SCORE_MIN = 2     # require at least 2/3 signals to pass


# ─── UNIVERSE FUNCTIONS ───────────────────────────────────────────────────────

def get_sp500_tickers():
    df = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", header=0)[0]
    return df["Symbol"].tolist()

def get_hang_seng_tickers():
    tables = pd.read_html("https://en.wikipedia.org/wiki/Hang_Seng_Index", header=0)
    for df in tables:
        for col in ("Code","Ticker","Stock Code"):
            if col in df.columns:
                out=[]
                for code in df[col].dropna().astype(str):
                    d="".join(filter(str.isdigit, code))
                    if d: out.append(d.zfill(4)+".HK")
                if out: return out
    return []

def get_us_etf_tickers(): return US_ETF_TICKERS
def get_hk_etf_tickers(): return HK_ETF_TICKERS


# ─── SAFE DOWNLOAD + COLUMN NORMALIZATION ────────────────────────────────────

def safe_download(ticker, period="90d", interval="1d"):
    """Download raw OHLC (auto_adjust=False) with retries, flatten & normalize columns."""
    for attempt in range(1, MAX_RETRIES+1):
        try:
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=False)
            # flatten MultiIndex -> field names (level 0)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            # normalize names
            df.columns = [c.lower().replace(" ", "") for c in df.columns]
            return df
        except Exception as e:
            print(f"❌ [{ticker}] download failed (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    return pd.DataFrame()


# ─── SCREENING LOGIC ──────────────────────────────────────────────────────────

def screen_stock(ticker):
    df = safe_download(ticker)
    if df.empty or any(col not in df.columns for col in ("close","high","low")):
        return None
    df = df.dropna(subset=["close","high","low"])
    if len(df) < 60:
        return None

    arr_close = df["close"].to_numpy().astype(float)
    arr_high  = df["high"].to_numpy().astype(float)
    arr_low   = df["low"].to_numpy().astype(float)

    info = yf.Ticker(ticker).info
    pe, roe = info.get("forwardPE"), info.get("returnOnEquity")
    if pe is None or roe is None or pe > 25 or roe < 0.10:
        return None

    # calculate indicators
    ma20 = pd.Series(arr_close).rolling(20).mean().iloc[-1]
    ma50 = pd.Series(arr_close).rolling(50).mean().iloc[-1]
    rsi  = talib.RSI(arr_close, timeperiod=14)[-1]
    atr  = talib.ATR(arr_high, arr_low, arr_close, timeperiod=14)[-1]
    atr_pct = atr / arr_close[-1]

    # build signals
    sig_mom  = int(ma20 > ma50)
    sig_rsi  = int(rsi < RSI_MAX)
    sig_vol  = int(atr_pct < ATR_PCT_MAX)
    tech_score = sig_mom + sig_rsi + sig_vol

    if tech_score < TECH_SCORE_MIN:
        return None

    return {
        "Ticker":    ticker,
        "Type":      "Stock",
        "Sector":    info.get("sector","Unknown"),
        "PE":        round(pe,2),
        "ROE":       round(roe,2),
        "MA20":      round(ma20,2),
        "MA50":      round(ma50,2),
        "RSI":       round(rsi,2),
        "ATR%":      round(atr_pct,4),
        "Momentum":  sig_mom,
        "Oversold":  sig_rsi,
        "LowVol":    sig_vol,
        "Score":     tech_score
    }


def screen_etf(ticker):
    df = safe_download(ticker)
    if df.empty or any(col not in df.columns for col in ("close","high","low")):
        return None
    df = df.dropna(subset=["close","high","low"])
    if len(df) < 60:
        return None

    arr_close = df["close"].to_numpy().astype(float)
    arr_high  = df["high"].to_numpy().astype(float)
    arr_low   = df["low"].to_numpy().astype(float)

    info    = yf.Ticker(ticker).info
    expense = info.get("expenseRatio", None)
    if expense is not None and expense > 0.01:
        return None

    # indicators
    ma20 = pd.Series(arr_close).rolling(20).mean().iloc[-1]
    ma50 = pd.Series(arr_close).rolling(50).mean().iloc[-1]
    rsi  = talib.RSI(arr_close, timeperiod=14)[-1]
    atr  = talib.ATR(arr_high, arr_low, arr_close, timeperiod=14)[-1]
    atr_pct = atr / arr_close[-1]

    sig_mom  = int(ma20 > ma50)
    sig_rsi  = int(rsi < RSI_MAX)
    sig_vol  = int(atr_pct < ETF_ATR_MAX)
    tech_score = sig_mom + sig_rsi + sig_vol

    if tech_score < TECH_SCORE_MIN:
        return None

    return {
        "Ticker":       ticker,
        "Type":         "ETF",
        "ExpenseRatio": round(expense,4) if expense else None,
        "MA20":         round(ma20,2),
        "MA50":         round(ma50,2),
        "RSI":          round(rsi,2),
        "ATR%":         round(atr_pct,4),
        "Momentum":     sig_mom,
        "Oversold":     sig_rsi,
        "LowVol":       sig_vol,
        "Score":        tech_score
    }


# ─── MAIN SCREENER ────────────────────────────────────────────────────────────

def screen_market(mode="all"):
    sources = {
        "US-stock": get_sp500_tickers,
        "HK-stock": get_hang_seng_tickers,
        "US-ETF":   get_us_etf_tickers,
        "HK-ETF":   get_hk_etf_tickers,
    }

    # build category→tickers map
    to_check = {"Stock": [], "ETF": []}
    if mode == "all":
        to_check["Stock"] = sources["US-stock"]()  + sources["HK-stock"]()
        to_check["ETF"]   = sources["US-ETF"]()    + sources["HK-ETF"]()
    else:
        cat = "ETF" if "ETF" in mode else "Stock"
        to_check[cat] = sources[mode]()

    total = sum(len(v) for v in to_check.values())
    print(f"🔍 Screening {total} tickers in mode: {mode}\n")

    results, count = [], 0
    for cat, tickers in to_check.items():
        for t in tickers:
            count += 1
            print(f"{count}/{total} – {t} ({cat})")
            fn  = screen_etf if cat=="ETF" else screen_stock
            res = fn(t)
            print(f"   {'✅' if res else '❌'}")
            if res:
                results.append(res)

            delay = random.uniform(SLEEP_MIN, SLEEP_MAX)
            print(f"   ⏱ sleeping {delay:.2f}s\n")
            time.sleep(delay)

    out_file = f"screened_candidates_{mode}.csv"
    pd.DataFrame(results).to_csv(out_file, index=False)
    print(f"\n✅ Done! Results saved to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Screener")
    parser.add_argument(
        "--mode",
        choices=["US-stock", "HK-stock", "US-ETF", "HK-ETF", "all"],
        default="all",
        help="Which universe to screen",
    )
    args = parser.parse_args()
    screen_market(args.mode)
