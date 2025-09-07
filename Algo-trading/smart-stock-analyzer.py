import yfinance as yf
import pandas as pd
import talib
import datetime

# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

def run_analysis(screened_csv="screened_candidates_all.csv"):
    """
    Expect screened_csv to have columns: Ticker, Type (Stock|ETF), ...
    """
    df = pd.read_csv(screened_csv)
    results = []

    for _, row in df.iterrows():
        tkr  = row['Ticker']
        typ  = row['Type']
        if typ == 'ETF':
            results.append(analyze_etf(tkr))
        else:
            results.append(analyze_stock(tkr))

    out = pd.DataFrame(results)
    today = datetime.date.today().isoformat()
    out.to_csv(f"smart_analysis_{today}.csv", index=False)
    print("✅ Analysis complete:", out.shape[0], "rows")

# ─── STOCK ANALYSIS (unchanged) ───────────────────────────────────────────────

def analyze_stock(ticker):
    df = yf.download(ticker, period="120d", interval="1d", progress=False)
    if df.empty or len(df) < 60:
        return _blank_result(ticker, kind="Stock")

    info = yf.Ticker(ticker).info
    # your existing fundamental filters
    pe  = info.get("forwardPE", None)
    roe = info.get("returnOnEquity", None)

    # compute technicals
    df["MA20"] = df.Close.rolling(20).mean()
    df["MA50"] = df.Close.rolling(50).mean()
    rsi       = talib.RSI(df.Close, timeperiod=14).iloc[-1]
    atr       = talib.ATR(df.High, df.Low, df.Close, timeperiod=14).iloc[-1]
    price     = df.Close.iloc[-1]

    # build your scorecard
    scores = {}
    # … (same as before) …

    decision = _final_decision(scores, buy_thr=3, sell_thr=-2)

    return {
        "Ticker": ticker,
        "Type": "Stock",
        "PE": pe,
        "ROE": roe,
        "MA20": df.MA20.iloc[-1],
        "MA50": df.MA50.iloc[-1],
        "RSI": round(rsi,2),
        "ATR%": round(atr/price,4),
        "Score": round(sum(scores.values()),2),
        "Decision": decision
    }

# ─── ETF ANALYSIS (new) ───────────────────────────────────────────────────────

def analyze_etf(ticker):
    df = yf.download(ticker, period="120d", interval="1d", progress=False)
    if df.empty or len(df) < 60:
        return _blank_result(ticker, kind="ETF")

    info   = yf.Ticker(ticker).info
    expense= info.get("expenseRatio", None)
    yieldd = info.get("dividendYield", None)
    aum    = info.get("totalAssets", None)  # in USD

    # same technicals
    df["MA20"] = df.Close.rolling(20).mean()
    df["MA50"] = df.Close.rolling(50).mean()
    rsi       = talib.RSI(df.Close, timeperiod=14).iloc[-1]
    atr       = talib.ATR(df.High, df.Low, df.Close, timeperiod=14).iloc[-1]
    price     = df.Close.iloc[-1]

    scores = {}

    # 1) Technical momentum (same logic)
    scores["MA Crossover"] = +1.5 if df.MA20.iloc[-1] > df.MA50.iloc[-1] else -1.5
    scores["RSI"]          = +1.0 if rsi < 30 else -1.0 if rsi > 70 else 0
    scores["Volatility"]   = 0 if (atr/price) < 0.05 else -1.0

    # 2) Expense override: penalize high-cost ETFs
    if expense is not None and expense > 0.01:
        scores["Expense"] = -2.0
    else:
        scores["Expense"] = +1.0

    # 3) Yield override: reward decent distributions
    if yieldd and yieldd > 0.02:
        scores["Yield"] = +1.0
    else:
        scores["Yield"] = 0

    # 4) AUM/liquidity: small assets = risk
    if aum and aum < 50_000_000:
        scores["AUM"] = -1.5
    else:
        scores["AUM"] = +0.5

    decision = _final_decision(scores, buy_thr=2.5, sell_thr=-2)

    return {
        "Ticker": ticker,
        "Type": "ETF",
        "ExpenseRatio": expense,
        "Yield": yieldd,
        "AUM": aum,
        "MA20": df.MA20.iloc[-1],
        "MA50": df.MA50.iloc[-1],
        "RSI": round(rsi,2),
        "ATR%": round(atr/price,4),
        "Score": round(sum(scores.values()),2),
        "Decision": decision
    }

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _blank_result(tkr, kind):
    return {
        "Ticker": tkr,
        "Type": kind,
        "Decision": "N/A"
    }

def _final_decision(scores, buy_thr, sell_thr):
    total = sum(scores.values())
    if total >= buy_thr:
        return "Buy"
    if total <= sell_thr:
        return "Sell"
    return "Hold"

# ─── IF CALLED DIRECTLY ──────────────────────────────────────────────────────

if __name__ == "__main__":
    run_analysis("screened_candidates_all.csv")
