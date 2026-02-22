"""
scanner.py — Fibonacci 扫描引擎（多数据源 v2）
================================================================
数据源覆盖情况（全部免费，无需 API Key）：

  品种类型    主数据源                       备用/兜底
  ─────────  ────────────────────────────  ──────────────────
  A股        AKShare(东方财富) ✅ 5454支    yfinance(.SS/.SZ)
  港股       AKShare(东方财富) ✅ 2516支    yfinance(.HK)
  美股       AKShare(东方财富) ✅ 16527支   yfinance
  美股指数    yfinance ✅                   —
  外汇       yfinance ✅                   TwelveData(可选)
  期货/商品  yfinance ✅                   TwelveData(可选)
  加密货币   yfinance ✅                   —

AKShare 核心接口（东方财富数据源，稳定免费）：
  A股历史：  ak.stock_zh_a_hist(symbol="000001", period="daily", adjust="qfq")
  A股列表：  ak.stock_zh_a_spot_em()           → 5000+ 支
  港股历史：  ak.stock_hk_hist(symbol="00700", period="daily", adjust="qfq")
  港股列表：  ak.stock_hk_main_board_spot_em()  → 2280 支
  美股历史：  ak.stock_us_hist(symbol="105.AAPL", period="daily", adjust="qfq")
  美股列表：  ak.stock_us_spot_em()             → 16000+ 支
================================================================
"""

import time
import hashlib
import logging
import re
import warnings
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

import storage
from assets import ASSETS, TIMEFRAMES, tv_symbol, tv_url
from alerts import dispatch_alerts

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Ticker 类型检测
# ════════════════════════════════════════════════════════════════════
def _ticker_type(ticker: str) -> str:
    t = ticker.strip().upper()
    if re.match(r"^\d{6}$", t):               return "a_bare"
    if re.match(r"^\d{6}\.(SS|SH|SZ|BJ)$", t): return "a_share"
    if re.match(r"^\d{4,5}\.HK$", t):         return "hk_stock"
    if re.match(r"^[A-Z]{1,5}$", t):          return "us_stock"
    if re.match(r"^[A-Z]+-[A-Z]+$", t):       return "crypto"
    if t.endswith("=X"):                       return "forex"
    if t.endswith("=F"):                       return "futures"
    if t.startswith("^"):                      return "index"
    return "other"


# ════════════════════════════════════════════════════════════════════
# 日期辅助
# ════════════════════════════════════════════════════════════════════
def _start_date(days_back: int) -> str:
    return (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

def _today() -> str:
    return datetime.now().strftime("%Y%m%d")

_AK_PERIOD: Dict[str, Tuple[str, int]] = {
    "1d":  ("daily",   365 * 3),
    "1wk": ("weekly",  365 * 6),
    "1mo": ("monthly", 365 * 15),
}


# ════════════════════════════════════════════════════════════════════
# 通用 OHLC 标准化
# ════════════════════════════════════════════════════════════════════
def _to_ohlc(df: pd.DataFrame,
             date_col:  str = "日期",
             open_col:  str = "开盘",
             high_col:  str = "最高",
             low_col:   str = "最低",
             close_col: str = "收盘") -> Optional[pd.DataFrame]:
    try:
        if df is None or df.empty:
            return None
        rename = {}
        for c in df.columns:
            cs = str(c).strip()
            if cs in (open_col,  "open",  "Open"):   rename[c] = "Open"
            elif cs in (high_col, "high",  "High"):  rename[c] = "High"
            elif cs in (low_col,  "low",   "Low"):   rename[c] = "Low"
            elif cs in (close_col,"close", "Close"): rename[c] = "Close"
        df = df.rename(columns=rename)
        need = {"Open", "High", "Low", "Close"}
        if not need.issubset(set(df.columns)):
            return None
        if date_col in df.columns:
            df = df.set_index(date_col)
        elif "date" in df.columns:
            df = df.set_index("date")
        df = df[["Open", "High", "Low", "Close"]].copy()
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()].sort_index()
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        return df if not df.empty else None
    except Exception as e:
        logger.debug(f"_to_ohlc: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# AKShare — A股（东方财富，5454支）
# ════════════════════════════════════════════════════════════════════
def _ak_a_share(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        import akshare as ak
        symbol = re.sub(r"\.(SS|SH|SZ|BJ)$", "", ticker.upper())
        if not re.match(r"^\d{6}$", symbol):
            return None
        period, days = _AK_PERIOD.get(interval, ("daily", 365 * 3))
        df = ak.stock_zh_a_hist(
            symbol=symbol, period=period,
            start_date=_start_date(days), end_date=_today(),
            adjust="qfq"
        )
        return _to_ohlc(df)
    except Exception as e:
        logger.debug(f"ak_a_share {ticker}: {e}")
        return None


def get_all_a_share_tickers() -> List[Tuple[str, str]]:
    """返回全量 A 股 [(6位代码, 名称)]，约 5454 支。"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        result = []
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            name = str(row.get("名称", ""))
            if code and name:
                result.append((code, name))
        return result
    except Exception as e:
        logger.warning(f"get_all_a_share_tickers: {e}")
        return []


# ════════════════════════════════════════════════════════════════════
# AKShare — 港股（东方财富，2516支）
# ════════════════════════════════════════════════════════════════════
def _ak_hk_stock(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        import akshare as ak
        # 0700.HK → 去掉 .HK → 补全5位 → "00700"（东方财富格式）
        code = re.sub(r"\.HK$", "", ticker.upper(), flags=re.IGNORECASE)
        code = code.zfill(5)
        period, days = _AK_PERIOD.get(interval, ("daily", 365 * 3))
        df = ak.stock_hk_hist(
            symbol=code, period=period,
            start_date=_start_date(days), end_date=_today(),
            adjust="qfq"
        )
        return _to_ohlc(df)
    except Exception as e:
        logger.debug(f"ak_hk_stock {ticker}: {e}")
        return None


def get_all_hk_tickers() -> List[Tuple[str, str]]:
    """返回全量港股 [(XXXX.HK, 名称)]，约 2280 支。"""
    try:
        import akshare as ak
        df = ak.stock_hk_main_board_spot_em()
        result = []
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).zfill(5)
            name = str(row.get("名称", ""))
            if code and name:
                yf_code = f"{int(code):04d}.HK"
                result.append((yf_code, name))
        return result
    except Exception as e:
        logger.warning(f"get_all_hk_tickers: {e}")
        return []


# ════════════════════════════════════════════════════════════════════
# AKShare — 美股（东方财富，16527支）
# ════════════════════════════════════════════════════════════════════
# 东方财富前缀：105=NASDAQ, 106=NYSE, 107=AMEX
_US_CODE_CACHE: Dict[str, str] = {}   # ticker → "105.AAPL"


def _ak_us_stock(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        import akshare as ak
        t = ticker.upper()
        period, days = _AK_PERIOD.get(interval, ("daily", 365 * 3))
        start, end   = _start_date(days), _today()

        # 优先使用缓存中已知的完整代码
        known = _US_CODE_CACHE.get(t)
        candidates = [known] if known else [f"{p}.{t}" for p in ["105", "106", "107"]]

        for code in candidates:
            try:
                df = ak.stock_us_hist(
                    symbol=code, period=period,
                    start_date=start, end_date=end, adjust="qfq"
                )
                result = _to_ohlc(df)
                if result is not None:
                    _US_CODE_CACHE[t] = code
                    return result
            except Exception:
                continue
        return None
    except Exception as e:
        logger.debug(f"ak_us_stock {ticker}: {e}")
        return None


def get_all_us_tickers() -> List[Tuple[str, str]]:
    """返回全量美股 [(TICKER, 名称)]，约 16527 支，同时预热代码缓存。"""
    try:
        import akshare as ak
        df = ak.stock_us_spot_em()
        result = []
        for _, row in df.iterrows():
            raw  = str(row.get("代码", ""))   # 例：105.AAPL
            name = str(row.get("名称", ""))
            if "." in raw:
                ticker = raw.split(".", 1)[1]
                _US_CODE_CACHE[ticker.upper()] = raw   # 预热缓存
            else:
                ticker = raw
            if ticker and name:
                result.append((ticker, name))
        return result
    except Exception as e:
        logger.warning(f"get_all_us_tickers: {e}")
        return []


# ════════════════════════════════════════════════════════════════════
# yfinance — 通用兜底
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
        out = df[["Open", "High", "Low", "Close"]].dropna()
        return out if not out.empty else None
    except Exception as e:
        logger.debug(f"yfinance {ticker}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# TwelveData — 可选付费补充
# ════════════════════════════════════════════════════════════════════
def fetch_twelvedata(ticker: str, interval: str, period: str,
                     api_key: str) -> Optional[pd.DataFrame]:
    if not api_key:
        return None
    try:
        import requests
        td_map = {"1d": "1day", "1wk": "1week", "1mo": "1month"}
        td_int = td_map.get(interval)
        if not td_int:
            return None
        size = {"2y": 520, "5y": 260, "10y": 120}.get(period, 200)
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": ticker, "interval": td_int,
                    "outputsize": size, "apikey": api_key},
            timeout=12,
        )
        data = r.json()
        if data.get("status") == "error":
            return None
        vals = data.get("values", [])
        if not vals:
            return None
        rows = [{"Date": v["datetime"],
                 "Open": float(v["open"]), "High": float(v["high"]),
                 "Low":  float(v["low"]),  "Close": float(v["close"])}
                for v in vals]
        return pd.DataFrame(rows).set_index("Date").sort_index()
    except Exception as e:
        logger.debug(f"twelvedata {ticker}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# 智能路由
# ════════════════════════════════════════════════════════════════════
def fetch_data(ticker: str, interval: str, period: str,
               cfg: Optional[Dict] = None) -> Optional[pd.DataFrame]:
    cfg    = cfg or {}
    tt     = _ticker_type(ticker)
    td_key = cfg.get("twelvedata_key", "")

    if tt in ("a_share", "a_bare"):
        df = _ak_a_share(ticker, interval)
        return df if df is not None else fetch_yfinance(ticker, interval, period)

    if tt == "hk_stock":
        df = _ak_hk_stock(ticker, interval)
        return df if df is not None else fetch_yfinance(ticker, interval, period)

    if tt == "us_stock":
        df = _ak_us_stock(ticker, interval)
        if df is not None:
            return df
        df = fetch_yfinance(ticker, interval, period)
        if df is not None:
            return df
        return fetch_twelvedata(ticker, interval, period, td_key) if td_key else None

    # 外汇/期货/指数/加密/其他
    if cfg.get("data_source") == "twelvedata" and td_key:
        df = fetch_twelvedata(ticker, interval, period, td_key)
        if df is not None:
            return df
    df = fetch_yfinance(ticker, interval, period)
    if df is not None:
        return df
    return fetch_twelvedata(ticker, interval, period, td_key) if td_key else None


# ════════════════════════════════════════════════════════════════════
# Fibonacci 计算
# ════════════════════════════════════════════════════════════════════
def compute_fibo(df:       Optional[pd.DataFrame],
                 lookback: int   = 100,
                 zone_lo:  float = 0.5,
                 zone_hi:  float = 0.618) -> Optional[Dict]:
    try:
        if df is None or len(df) < max(10, lookback // 2):
            return None
        window     = df.tail(lookback)
        swing_high = float(window["High"].max())
        swing_low  = float(window["Low"].min())
        if swing_high <= swing_low:
            return None
        rng         = swing_high - swing_low
        current     = float(df["Close"].iloc[-1])
        retrace_pct = (swing_high - current) / rng * 100
        zone_top    = swing_high - zone_lo * rng
        zone_bot    = swing_high - zone_hi * rng
        in_zone     = zone_bot <= current <= zone_top
        fibs        = [0.0, 0.136, 0.236, 0.382, 0.5, 0.618,
                       0.705, 0.786, 0.886, 1.0]
        fib_prices  = {r: swing_high - r * rng for r in fibs}
        nearest_r   = min(fibs, key=lambda r: abs(fib_prices[r] - current))
        dist_pct    = (
            abs(current - zone_top) / rng * 100 if current > zone_top else
            abs(current - zone_bot) / rng * 100 if current < zone_bot else 0.0
        )
        return {
            "swing_high":   swing_high,
            "swing_low":    swing_low,
            "current":      current,
            "retrace_pct":  round(retrace_pct, 2),
            "zone_top":     round(zone_top, 6),
            "zone_bot":     round(zone_bot, 6),
            "in_zone":      in_zone,
            "nearest_fibo": nearest_r,
            "dist_pct":     round(dist_pct, 2),
        }
    except Exception as e:
        logger.debug(f"compute_fibo: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# 共振评分
# ════════════════════════════════════════════════════════════════════
def confluence_score(tf_map: Dict[str, Optional[Dict]]) -> Dict:
    in_tfs   = [tf for tf, f in tf_map.items() if f and f["in_zone"]]
    near_tfs = [tf for tf, f in tf_map.items()
                if f and not f["in_zone"] and f.get("dist_pct", 999) < 5]
    score = min(len(in_tfs) * 3 + len(near_tfs), 10)
    if len(in_tfs) == 3:   label = "🔥🔥🔥 三框架共振"
    elif len(in_tfs) == 2: label = "🔥🔥 双框架共振"
    elif len(in_tfs) == 1: label = "🔥 单框架黄金区"
    elif near_tfs:         label = "👀 接近区间"
    else:                  label = "·"
    return {"score": score, "label": label,
            "in_tfs": in_tfs, "near_tfs": near_tfs}


# ════════════════════════════════════════════════════════════════════
# 主扫描入口
# ════════════════════════════════════════════════════════════════════
def run_full_scan(
    cfg:               Optional[Dict]     = None,
    assets:            Optional[Dict]     = None,
    note:              str                = "manual",
    progress_callback: Optional[Callable] = None,
) -> Tuple[Optional[Dict], Optional[str]]:

    cfg    = cfg    or storage.load_config()
    assets = assets or ASSETS

    lookback = int(cfg.get("lookback", 100))
    zone_lo  = float(cfg.get("fibo_low",  0.5))
    zone_hi  = float(cfg.get("fibo_high", 0.618))

    now        = datetime.now()
    scan_date  = str(now.date())
    session_id = (now.strftime("%Y%m%d_%H%M%S_") +
                  hashlib.md5(now.isoformat().encode()).hexdigest()[:6])

    t0          = time.time()
    total_items = len(assets) * len(TIMEFRAMES)
    done        = 0
    tf_map: Dict[str, Dict[str, Optional[Dict]]] = {t: {} for t in assets}

    for ticker, (name, category) in assets.items():
        for tf_name, (interval, period) in TIMEFRAMES.items():
            if progress_callback:
                progress_callback(done / total_items,
                                  f"🔍 {name} ({ticker}) · {tf_name}")
            df   = fetch_data(ticker, interval, period, cfg)
            fibo = compute_fibo(df, lookback, zone_lo, zone_hi)
            tf_map[ticker][tf_name] = fibo
            done += 1

    if progress_callback:
        progress_callback(0.95, "💾 计算共振评分并保存…")

    conf_map = {t: confluence_score(tf_map[t]) for t in assets}

    result_rows: List[Dict] = []
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
        "data_source":  cfg.get("data_source", "auto"),
        "note":         note,
        "asset_count":  len(assets),
    }

    ok = storage.save_scan(session_row, result_rows)
    if not ok:
        return None, "❌ 写入本地 JSON 失败"

    for ticker, (name, _) in assets.items():
        for tf_name in TIMEFRAMES:
            fibo = tf_map[ticker].get(tf_name)
            if fibo and fibo["in_zone"]:
                dispatch_alerts(ticker=ticker, name=name, timeframe=tf_name,
                                fibo=fibo, conf=conf_map[ticker], cfg=cfg)

    if progress_callback:
        progress_callback(1.0, "✅ 扫描完成！")

    return {
        "session_id":   session_id,
        "scan_date":    scan_date,
        "total_checks": len(result_rows),
        "inzone_count": inzone_count,
        "triple_conf":  triple_conf,
        "elapsed_ms":   elapsed_ms,
        "asset_count":  len(assets),
    }, None
