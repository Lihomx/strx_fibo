"""
scanner.py — Fibonacci 扫描引擎
公式与 STRX Pine Script 完全对应：
  swingHigh = ta.highest(high, lookback)
  swingLow  = ta.lowest(low,  lookback)
  fp(r)     = swingHigh - r * (swingHigh - swingLow)
  in_zone:  fp(0.618) ≤ close ≤ fp(0.500)
"""

import time
import hashlib
import logging
import warnings
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

import storage
from alerts import dispatch_alerts

# ════════════════════════════════════════════════════════════════════
# 资产列表
# ════════════════════════════════════════════════════════════════════

ASSETS: Dict[str, Tuple[str, str]] = {
    # 大宗商品
    "GC=F":      ("Gold Futures",   "commodity"),
    "SI=F":      ("Silver Futures", "commodity"),
    "CL=F":      ("Crude Oil WTI",  "commodity"),
    "BZ=F":      ("Brent Crude",    "commodity"),
    "NG=F":      ("Natural Gas",    "commodity"),
    "HG=F":      ("Copper",         "commodity"),
    "ZW=F":      ("Wheat",          "commodity"),
    "ZC=F":      ("Corn",           "commodity"),
    # 外汇
    "EURUSD=X":  ("EUR/USD",        "forex"),
    "GBPUSD=X":  ("GBP/USD",        "forex"),
    "USDJPY=X":  ("USD/JPY",        "forex"),
    "USDCNH=X":  ("USD/CNH",        "forex"),
    "AUDUSD=X":  ("AUD/USD",        "forex"),
    "USDCAD=X":  ("USD/CAD",        "forex"),
    # 指数
    "^GSPC":     ("S&P 500",        "index"),
    "^NDX":      ("NASDAQ 100",     "index"),
    "^DJI":      ("Dow Jones",      "index"),
    "000001.SS": ("上证综指",        "index"),
    "399001.SZ": ("深证成指",        "index"),
    "^HSI":      ("恒生指数",        "index"),
    # 美股
    "AAPL":      ("Apple",          "stock"),
    "MSFT":      ("Microsoft",      "stock"),
    "NVDA":      ("NVIDIA",         "stock"),
    "AMZN":      ("Amazon",         "stock"),
    "GOOGL":     ("Alphabet",       "stock"),
    "META":      ("Meta",           "stock"),
    "TSLA":      ("Tesla",          "stock"),
    # 中概 / 港股
    "BIDU":      ("Baidu ADR",      "stock"),
    "PDD":       ("PDD Holdings",   "stock"),
    "JD":        ("JD.com",         "stock"),
    "9988.HK":   ("Alibaba HK",     "stock"),
    "700.HK":    ("Tencent HK",     "stock"),
    # 加密
    "BTC-USD":   ("Bitcoin",        "crypto"),
    "ETH-USD":   ("Ethereum",       "crypto"),
    "SOL-USD":   ("Solana",         "crypto"),
    "BNB-USD":   ("BNB",            "crypto"),
}

TIMEFRAMES: Dict[str, Tuple[str, str]] = {
    "Daily":   ("1d",  "2y"),
    "Weekly":  ("1wk", "5y"),
    "Monthly": ("1mo", "10y"),
}

TV_MAP: Dict[str, str] = {
    "GC=F":"COMEX:GC1!","SI=F":"COMEX:SI1!","CL=F":"NYMEX:CL1!",
    "BZ=F":"NYMEX:BB1!","NG=F":"NYMEX:NG1!","HG=F":"COMEX:HG1!",
    "ZW=F":"CBOT:ZW1!","ZC=F":"CBOT:ZC1!",
    "EURUSD=X":"FX:EURUSD","GBPUSD=X":"FX:GBPUSD","USDJPY=X":"FX:USDJPY",
    "USDCNH=X":"FX:USDCNH","AUDUSD=X":"FX:AUDUSD","USDCAD=X":"FX:USDCAD",
    "^GSPC":"SP:SPX","^NDX":"NASDAQ:NDX","^DJI":"DJ:DJI",
    "000001.SS":"SSE:000001","399001.SZ":"SZSE:399001","^HSI":"TVC:HSI",
    "9988.HK":"HKEX:9988","700.HK":"HKEX:700",
    "BTC-USD":"BINANCE:BTCUSDT","ETH-USD":"BINANCE:ETHUSDT",
    "SOL-USD":"BINANCE:SOLUSDT","BNB-USD":"BINANCE:BNBUSDT",
}


def tv_symbol(ticker: str) -> str:
    return TV_MAP.get(ticker,
           ticker.replace("=X","").replace("=F","").replace("^",""))


def tv_url(ticker: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol={tv_symbol(ticker)}"


# ════════════════════════════════════════════════════════════════════
# 数据获取
# ════════════════════════════════════════════════════════════════════

def fetch_yfinance(ticker: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(ticker, interval=interval, period=period,
                             progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        return df[["Open","High","Low","Close"]].dropna()
    except Exception as e:
        logging.warning(f"yfinance {ticker}: {e}")
        return None


def fetch_twelvedata(ticker: str, interval: str, period: str,
                     api_key: str) -> Optional[pd.DataFrame]:
    if not api_key:
        return None
    try:
        import requests
        td_map = {"1d":"1day","1wk":"1week","1mo":"1month"}
        td_int = td_map.get(interval)
        if not td_int:
            return None
        size = {"2y":520,"5y":260,"10y":120}.get(period, 200)
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol":ticker,"interval":td_int,"outputsize":size,"apikey":api_key},
            timeout=12,
        )
        data = r.json()
        if data.get("status") == "error":
            return None
        vals = data.get("values", [])
        if not vals:
            return None
        rows = [{"Date":v["datetime"],"Open":float(v["open"]),
                 "High":float(v["high"]),"Low":float(v["low"]),
                 "Close":float(v["close"])} for v in vals]
        return pd.DataFrame(rows).set_index("Date").sort_index()
    except Exception as e:
        logging.warning(f"twelvedata {ticker}: {e}")
        return None


def fetch_data(ticker: str, interval: str, period: str,
               cfg: Dict) -> Optional[pd.DataFrame]:
    if cfg.get("data_source") == "twelvedata":
        return fetch_twelvedata(ticker, interval, period,
                                cfg.get("twelvedata_key",""))
    return fetch_yfinance(ticker, interval, period)


# ════════════════════════════════════════════════════════════════════
# Fibonacci 计算
# ════════════════════════════════════════════════════════════════════

def compute_fibo(df: Optional[pd.DataFrame],
                 lookback: int = 100,
                 zone_lo: float = 0.5,
                 zone_hi: float = 0.618) -> Optional[Dict]:
    if df is None or len(df) < 5:
        return None
    lb  = min(lookback, len(df))
    win = df.iloc[-lb:]
    sh  = float(win["High"].max())
    sl  = float(win["Low"].min())
    cp  = float(df["Close"].iloc[-1])
    rng = sh - sl
    if rng == 0:
        return None

    fp      = lambda r: sh - r * rng
    zt      = fp(zone_lo)    # 0.500 → 价格较高
    zb      = fp(zone_hi)    # 0.618 → 价格较低
    in_zone = zb <= cp <= zt
    retrace = (sh - cp) / rng * 100

    if in_zone:
        dist = 0.0
    elif cp > zt:
        dist = (cp - zt) / rng * 100
    else:
        dist = (zb - cp) / rng * 100

    ratios  = [0.0,0.136,0.236,0.382,0.5,0.618,0.705,0.786,0.886,1.0]
    nearest = min(ratios, key=lambda r: abs(fp(r) - cp))

    return {
        "swing_high":   sh,
        "swing_low":    sl,
        "current":      cp,
        "zone_top":     zt,
        "zone_bot":     zb,
        "in_zone":      in_zone,
        "retrace_pct":  retrace,
        "dist_pct":     dist,
        "nearest_fibo": nearest,
    }


def confluence_score(tf_results: Dict[str, Optional[Dict]]) -> Dict:
    in_tfs   = [tf for tf, r in tf_results.items() if r and r["in_zone"]]
    near_tfs = [tf for tf, r in tf_results.items()
                if r and not r["in_zone"] and r["dist_pct"] < 5]
    score    = min(len(in_tfs) * 3 + len(near_tfs), 10)
    if   len(in_tfs) == 3: label = "🔥🔥🔥 三框架共振"
    elif len(in_tfs) == 2: label = "🔥🔥 双框架共振"
    elif len(in_tfs) == 1: label = "🔥 单框架"
    elif near_tfs:         label = "👀 接近区间"
    else:                  label = "—"
    return {"score":score,"label":label,"in_tfs":in_tfs,"near_tfs":near_tfs}


# ════════════════════════════════════════════════════════════════════
# 完整扫描
# ════════════════════════════════════════════════════════════════════

def run_full_scan(
    cfg:               Optional[Dict]     = None,
    assets:            Optional[Dict]     = None,
    note:              str                = "manual",
    progress_callback: Optional[Callable] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    执行完整扫描并将结果写入本地 JSON。
    progress_callback(pct: float, msg: str)
    返回 (summary_dict, error_msg)
    """
    cfg    = cfg    or storage.load_config()
    assets = assets or ASSETS

    lookback = int(cfg.get("lookback", 100))
    zone_lo  = float(cfg.get("fibo_low",  0.5))
    zone_hi  = float(cfg.get("fibo_high", 0.618))

    now        = datetime.now()
    scan_date  = str(now.date())
    session_id = now.strftime("%Y%m%d_%H%M%S_") + \
                 hashlib.md5(now.isoformat().encode()).hexdigest()[:6]

    t0          = time.time()
    total_items = len(assets) * len(TIMEFRAMES)
    done        = 0
    tf_map:     Dict[str, Dict[str, Optional[Dict]]] = {t: {} for t in assets}
    result_rows: List[Dict] = []

    for ticker, (name, category) in assets.items():
        for tf_name, (interval, period) in TIMEFRAMES.items():
            if progress_callback:
                progress_callback(done / total_items,
                                  f"🔍 {name} · {tf_name}")
            df   = fetch_data(ticker, interval, period, cfg)
            fibo = compute_fibo(df, lookback, zone_lo, zone_hi)
            tf_map[ticker][tf_name] = fibo
            done += 1

    if progress_callback:
        progress_callback(0.95, "💾 计算共振 & 保存结果…")

    conf_map = {t: confluence_score(tf_map[t]) for t in assets}

    for ticker, (name, category) in assets.items():
        conf = conf_map[ticker]
        for tf_name in TIMEFRAMES:
            fibo = tf_map[ticker].get(tf_name)
            result_rows.append({
                "session_id":       session_id,
                "scan_date":        scan_date,
                "ticker":           ticker,
                "name":             name,
                "category":         category,
                "timeframe":        tf_name,
                "in_zone":          bool(fibo and fibo["in_zone"]),
                "current_price":    fibo["current"]      if fibo else None,
                "swing_high":       fibo["swing_high"]   if fibo else None,
                "swing_low":        fibo["swing_low"]    if fibo else None,
                "zone_top":         fibo["zone_top"]     if fibo else None,
                "zone_bot":         fibo["zone_bot"]     if fibo else None,
                "retrace_pct":      fibo["retrace_pct"]  if fibo else None,
                "dist_pct":         fibo["dist_pct"]     if fibo else None,
                "nearest_fibo":     fibo["nearest_fibo"] if fibo else None,
                "confluence_score": conf["score"],
                "confluence_label": conf["label"],
                "tv_symbol":        tv_symbol(ticker),
                "tv_url":           tv_url(ticker),
            })

    elapsed_ms   = int((time.time() - t0) * 1000)
    inzone_count = sum(1 for r in result_rows if r["in_zone"])
    triple_conf  = sum(1 for t in assets if len(conf_map[t]["in_tfs"]) == 3)

    session_row = {
        "session_id":   session_id,
        "scan_date":    scan_date,
        "scan_time":    now.isoformat(timespec="seconds"),
        "total_checks": len(result_rows),
        "inzone_count": inzone_count,
        "triple_conf":  triple_conf,
        "duration_ms":  elapsed_ms,
        "data_source":  cfg.get("data_source","yfinance"),
        "note":         note,
    }

    ok = storage.save_scan(session_row, result_rows)
    if not ok:
        return None, "❌ 写入本地 JSON 失败"

    # 发送告警
    for ticker, (name, _) in assets.items():
        for tf_name in TIMEFRAMES:
            fibo = tf_map[ticker].get(tf_name)
            if fibo and fibo["in_zone"]:
                dispatch_alerts(
                    ticker=ticker, name=name,
                    timeframe=tf_name, fibo=fibo,
                    conf=conf_map[ticker], cfg=cfg,
                )

    if progress_callback:
        progress_callback(1.0, "✅ 扫描完成！")

    return {
        "session_id":   session_id,
        "scan_date":    scan_date,
        "total_checks": len(result_rows),
        "inzone_count": inzone_count,
        "triple_conf":  triple_conf,
        "elapsed_ms":   elapsed_ms,
    }, None
