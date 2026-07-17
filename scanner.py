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
            
        # 1. 检查是否为分钟级别/日内数据 (例如: 15m, 4h)
        m = re.match(r"^(\d+)([mhMH])$", interval)
        if m:
            val = int(m.group(1))
            unit = m.group(2).lower()
            minutes = val * 60 if unit == "h" else val
            if minutes in (1, 5, 15, 30, 60):
                period = str(minutes)
                df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=period, adjust="qfq")
                return _to_ohlc(df, date_col="时间")
            elif minutes == 240:  # 4h 降采样自 60m
                df_60m = ak.stock_zh_a_hist_min_em(symbol=symbol, period="60", adjust="qfq")
                df = _to_ohlc(df_60m, date_col="时间")
                if df is not None and not df.empty:
                    df = df.resample("4H").agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last"
                    }).dropna()
                return df

        # 2. 日线/周线/月线级别数据
        period, days = _AK_PERIOD.get(interval, ("daily", 365 * 3))
        df = ak.stock_zh_a_hist(
            symbol=symbol, period=period,
            start_date=_start_date(days), end_date=_today(),
            adjust="qfq"
        )
        return _to_ohlc(df)
    except Exception as e:
        logger.debug(f"ak_a_share {ticker} ({interval}): {e}")
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
    import time
    import random
    # 随机微小延迟，降低高并发冲突
    time.sleep(random.uniform(0.1, 0.4))
    
    for attempt in range(2):
        try:
            import yfinance as yf
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = yf.download(ticker, interval=interval, period=period,
                                 progress=False, auto_adjust=True)
            if df is None or df.empty:
                if attempt == 0:
                    time.sleep(random.uniform(1.0, 2.0))
                    continue
                return None
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            out = df[["Open", "High", "Low", "Close"]].dropna()
            return out if not out.empty else None
        except Exception as e:
            logger.debug(f"yfinance {ticker} (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(random.uniform(1.0, 2.0))
                continue
            return None
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
# 网易财经 — A股备用数据源（免费公开API，无需登录）
# ════════════════════════════════════════════════════════════════════
def _netease_a_share(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    """
    网易财经历史K线接口（第三备用，AKShare和yfinance均失败时启用）
    沪市600xxx → code=0600xxx, 深市000xxx/300xxx → code=1000xxx/1300xxx
    北交所: 使用 yfinance 即可
    """
    try:
        import requests
        symbol = re.sub(r"\.(SS|SH|SZ|BJ)$", "", ticker.upper())
        if not re.match(r"^\d{6}$", symbol):
            return None
        # 判断交易所前缀
        first = symbol[0]
        if first == "6":
            code = "0" + symbol    # 沪市
        elif first in ("0", "3"):
            code = "1" + symbol    # 深市
        else:
            return None            # 北交所等暂不支持

        from datetime import datetime, timedelta
        days_map = {"1d": 730, "1wk": 1825, "1mo": 5475}
        days = days_map.get(interval, 730)
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end   = datetime.now().strftime("%Y%m%d")

        url = (
            f"http://quotes.money.163.com/service/chddata.html"
            f"?code={code}&start={start}&end={end}"
            f"&fields=TCLOSE;HIGH;LOW;TOPEN;VOTURNOVER"
        )
        headers = {"User-Agent": "Mozilla/5.0 (compatible; STRX/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        from io import StringIO
        # 网易返回 GBK 编码 CSV
        text = resp.content.decode("gbk", errors="replace")
        df = pd.read_csv(StringIO(text))
        if df is None or df.empty:
            return None

        # 列名映射: 日期,股票代码,名称,收盘价,最高价,最低价,开盘价,...
        col_map = {}
        for c in df.columns:
            cs = str(c).strip()
            if cs in ("日期", "DATE", "date"):      col_map[c] = "Date"
            elif cs in ("开盘价", "TOPEN"):          col_map[c] = "Open"
            elif cs in ("最高价", "HIGH"):           col_map[c] = "High"
            elif cs in ("最低价", "LOW"):            col_map[c] = "Low"
            elif cs in ("收盘价", "TCLOSE"):         col_map[c] = "Close"
        df = df.rename(columns=col_map)

        if not {"Open","High","Low","Close"}.issubset(set(df.columns)):
            return None

        if "Date" in df.columns:
            df = df.set_index("Date")
        df = df[["Open","High","Low","Close"]].copy()
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()].sort_index()
        for col in ["Open","High","Low","Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()

        # 对周/月线进行降采样
        if interval == "1wk":
            df = df.resample("W").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()
        elif interval == "1mo":
            df = df.resample("ME").agg({"Open":"first","High":"max","Low":"min","Close":"last"}).dropna()

        return df if not df.empty else None
    except Exception as e:
        logger.debug(f"netease_a_share {ticker}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# 新浪财经 — A股第四备用数据源（实时/历史）
# ════════════════════════════════════════════════════════════════════
def _sina_a_share(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    """
    新浪财经 mish 接口，日线/周线/月线历史数据
    代码格式: sh600048 / sz000001
    """
    try:
        import requests
        symbol = re.sub(r"\.(SS|SH|SZ|BJ)$", "", ticker.upper())
        if not re.match(r"^\d{6}$", symbol):
            return None
        prefix = "sh" if symbol[0] == "6" else "sz"
        code   = prefix + symbol

        scale_map = {"1d": 240, "1wk": 1200, "1mo": 4800}  # 分钟数
        scale = scale_map.get(interval, 240)
        datalen = 500

        url = (
            f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
            f"/CN_MarketData.getKLineData?symbol={code}"
            f"&scale={scale}&ma=5&datalen={datalen}"
        )
        headers = {"Referer": "https://finance.sina.com.cn",
                   "User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        import json
        data = resp.json()
        if not data or not isinstance(data, list):
            return None

        rows = []
        for item in data:
            try:
                rows.append({
                    "Date":  item.get("d") or item.get("date", ""),
                    "Open":  float(item.get("o", 0) or item.get("open", 0)),
                    "High":  float(item.get("h", 0) or item.get("high", 0)),
                    "Low":   float(item.get("l", 0) or item.get("low", 0)),
                    "Close": float(item.get("c", 0) or item.get("close", 0)),
                })
            except Exception:
                continue
        if not rows:
            return None

        df = pd.DataFrame(rows).set_index("Date")
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[df.index.notna()].sort_index()
        df = df[["Open","High","Low","Close"]]
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        df = df[df["Close"] > 0]  # 过滤无效行
        return df if not df.empty else None
    except Exception as e:
        logger.debug(f"sina_a_share {ticker}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════
# 智能路由
# ════════════════════════════════════════════════════════════════════
import streamlit as st

@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_data(ticker: str, interval: str, period: str, data_source: str, td_key: str) -> Optional[pd.DataFrame]:
    return _fetch_data_impl(ticker, interval, period, data_source, td_key)

def _fetch_data_impl(ticker: str, interval: str, period: str, data_source: str, td_key: str) -> Optional[pd.DataFrame]:
    tt = _ticker_type(ticker)
    if tt in ("a_share", "a_bare"):
        # 1. 如果用户强制指定使用 yfinance，则直接调用 yfinance
        if data_source == "yfinance":
            return fetch_yfinance(ticker, interval, period)

        # 2. 否则，按优先级尝试 A股专用数据源：AKShare > 网易财经 > 新浪财经
        df = _ak_a_share(ticker, interval)
        if df is not None:
            return df
        df = _netease_a_share(ticker, interval)
        if df is not None:
            return df
        df = _sina_a_share(ticker, interval)
        if df is not None:
            return df

        # 3. 如果以上全部失败或不可用（例如部署在 Streamlit Cloud），使用 yfinance 兜底获取数据
        return fetch_yfinance(ticker, interval, period)

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
    if data_source == "twelvedata" and td_key:
        df = fetch_twelvedata(ticker, interval, period, td_key)
        if df is not None:
            return df
    df = fetch_yfinance(ticker, interval, period)
    if df is not None:
        return df
    return fetch_twelvedata(ticker, interval, period, td_key) if td_key else None

def fetch_data(ticker: str, interval: str, period: str,
               cfg: Optional[Dict] = None) -> Optional[pd.DataFrame]:
    t = ticker.strip().upper()
    if not t:
        return None
    # 检查是否在已过滤列表中
    if storage.is_ticker_delisted(t):
        logger.debug(f"fetch_data skipped for delisted/invalid ticker: {t}")
        return None

    cfg = cfg or {}
    data_source = cfg.get("data_source", "auto")
    td_key = cfg.get("twelvedata_key", "")
    try:
        df = _cached_fetch_data(t, interval, period, data_source, td_key)
    except Exception as e:
        logger.warning(f"cache_data failure, falling back to direct fetch: {e}")
        df = _fetch_data_impl(t, interval, period, data_source, td_key)

    # 如果抓取到了有效数据，且之前曾经被记过失败，可以重置失败计数
    if df is not None and not df.empty:
        try:
            storage.reset_scan_failure(t)
        except Exception:
            pass

    return df


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
                if f and not f["in_zone"] and (f.get("dist_pct") if f.get("dist_pct") is not None else 999) < 5]
    score = min(len(in_tfs) * 3 + len(near_tfs), 10)
    if len(in_tfs) == 3:   label = "🔥🔥🔥 三框架共振"
    elif len(in_tfs) == 2: label = "🔥🔥 双框架共振"
    elif len(in_tfs) == 1: label = "🔥 单框架黄金区"
    elif near_tfs:         label = "👀 接近区间"
    else:                  label = "·"
    return {"score": score, "label": label,
            "in_tfs": in_tfs, "near_tfs": near_tfs}


# ════════════════════════════════════════════════════════════════════
# 并发数据获取（线程池加速，独立于 Streamlit 线程安全）
# ════════════════════════════════════════════════════════════════════
def _fetch_ticker_all_tfs(
    ticker: str,
    name: str,
    category: str,
    cfg: Dict,
    lookback: int,
    zone_lo: float,
    zone_hi: float,
    session_id: str,
    scan_date: str,
    timeframe_names: Optional[List[str]] = None,
) -> List[Dict]:
    """抓取一个品种的3个时间框架数据并计算 Fibo，返回3行结果。
    设计为线程安全：不写全局状态，只返回数据。
    """
    tf_names = [t for t in (timeframe_names or list(TIMEFRAMES.keys())) if t in TIMEFRAMES]
    if not tf_names:
        tf_names = list(TIMEFRAMES.keys())

    tf_results: Dict[str, Optional[Dict]] = {}
    has_any_success = False
    for tf_name in tf_names:
        interval, period = TIMEFRAMES[tf_name]
        try:
            df   = fetch_data(ticker, interval, period, cfg)
            fibo = compute_fibo(df, lookback, zone_lo, zone_hi)
            if fibo is not None:
                has_any_success = True
        except Exception as e:
            logger.debug(f"scan {ticker} {tf_name}: {e}")
            fibo = None
        tf_results[tf_name] = fibo

    if not has_any_success:
        try:
            storage.increment_scan_failure(ticker)
        except Exception:
            pass

    conf = confluence_score(tf_results)
    rows = []
    for tf_name in tf_names:
        fibo = tf_results.get(tf_name)
        rows.append({
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
            "tv_url":           tv_url(ticker, tf_name),
        })
    return rows


# ════════════════════════════════════════════════════════════════════
# 主扫描入口 v3 — 边扫边存 + 并发加速
# ════════════════════════════════════════════════════════════════════
def run_full_scan(
    cfg:               Optional[Dict]     = None,
    assets:            Optional[Dict]     = None,
    note:              str                = "manual",
    timeframe_names:   Optional[List[str]] = None,
    progress_callback: Optional[Callable] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    核心改进：
    1. 边扫边存（每扫完一个品种立即写入 storage），中断不丢数据
    2. 并发线程池（MAX_WORKERS 个线程同时拉取多个品种），速度提升 3-6x
    3. 进度实时刷新（已完成/总数 + 黄金区命中计数）
    4. 超时保护（单品种最长 30s，防止卡死）
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
    import threading

    cfg    = cfg    or storage.load_config()
    if assets is None:
        syms = storage.load_symbols()
        if syms:
            assets = {s["ticker"]: (s["name"], "custom") for s in syms}
        else:
            assets = ASSETS
    tf_names = [t for t in (timeframe_names or list(TIMEFRAMES.keys())) if t in TIMEFRAMES]
    if not tf_names:
        tf_names = list(TIMEFRAMES.keys())

    lookback = int(cfg.get("lookback", 100))
    zone_lo  = float(cfg.get("fibo_low",  0.5))
    zone_hi  = float(cfg.get("fibo_high", 0.618))

    now        = datetime.now()
    scan_date  = str(now.date())
    session_id = (now.strftime("%Y%m%d_%H%M%S_") +
                  hashlib.md5(now.isoformat().encode()).hexdigest()[:6])

    t0          = time.time()
    total       = len(assets)
    done_count  = 0
    inzone_acc  = 0          # 累计黄金区品种数
    all_rows:   List[Dict] = []
    lock        = threading.Lock()

    # ── 并发线程数：根据品种类型动态调整 ────────────────────────
    # A股/港股用 AKShare（东方财富 HTTP），并发友好，最多 6 线程
    # 美股/外汇/期货用 yfinance，并发适中，最多 5 线程
    # 保守上限：避免触发数据源限流
    MAX_WORKERS = 5

    def _task(ticker_info):
        ticker, (name, category) = ticker_info
        return _fetch_ticker_all_tfs(
            ticker, name, category, cfg,
            lookback, zone_lo, zone_hi,
            session_id, scan_date,
            timeframe_names=tf_names,
        )

    asset_items = list(assets.items())

    # ── 创建 session_row 骨架（先写入，后续 save_scan 会合并）──
    # 采用"先建立会话记录，再逐品种追加"的模式
    # storage.save_scan 内部会合并到 allres，所以可以多次调用

    def _flush_rows(rows: List[Dict]):
        """将一批结果立即持久化到本地 JSON（边扫边存）"""
        if not rows:
            return
        nonlocal inzone_acc
        inzone_in_batch = sum(1 for r in rows if r["in_zone"])
        with lock:
            inzone_acc += inzone_in_batch
            all_rows.extend(rows)
        # 直接写 allres（不走 save_scan 的会话日志，避免重复写 session）
        try:
            import json, os
            F = storage.get_allres_path(scan_date)
            with storage.IO_LOCK:
                # 读当前
                try:
                    with open(F, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    existing = []
                # 合并：同 ticker+timeframe 取最新
                merge_map = {(r["ticker"], r.get("timeframe","")): r for r in existing}
                for r in rows:
                    merge_map[(r["ticker"], r.get("timeframe",""))] = r
                merged = list(merge_map.values())
                if len(merged) > 5000:
                    merged = merged[-5000:]
                with open(F, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"_flush_rows: {e}")

    if progress_callback:
        progress_callback(0.01, f"🚀 开始扫描 {total} 个品种（{MAX_WORKERS} 线程并发）…")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_map = {executor.submit(_task, item): item[0]
                      for item in asset_items}

        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                rows = future.result(timeout=45)   # 单品种最长等 45s
            except FuturesTimeout:
                logger.warning(f"scan timeout: {ticker}")
                rows = []
            except Exception as e:
                logger.warning(f"scan error {ticker}: {e}")
                rows = []

            # ── 立即写盘（边扫边存！）──────────────────────────
            _flush_rows(rows)
            done_count += 1

            if progress_callback:
                pct  = done_count / total
                name = assets[ticker][0] if ticker in assets else ticker
                progress_callback(
                    pct,
                    f"✅ {done_count}/{total}  {name} ({ticker})"
                    f"  |  黄金区: {inzone_acc} 个"
                )

    # ── 最终汇总：写 session 日志（只写一次）────────────────────
    if progress_callback:
        progress_callback(0.98, "💾 保存扫描会话记录…")

    elapsed_ms   = int((time.time() - t0) * 1000)
    inzone_count = sum(1 for r in all_rows if r["in_zone"])
    # 三框架共振：同一 ticker 的3个 tf 都在黄金区
    triple_conf  = sum(
        1 for t in assets
        if sum(1 for r in all_rows if r["ticker"] == t and r["in_zone"]) == len(tf_names)
    )

    session_row = {
        "session_id":   session_id,
        "scan_date":    scan_date,
        "scan_time":    now.isoformat(timespec="seconds"),
        "total_checks": len(all_rows),
        "inzone_count": inzone_count,
        "triple_conf":  triple_conf,
        "duration_ms":  elapsed_ms,
        "data_source":  cfg.get("data_source", "auto"),
        "note":         note,
        "asset_count":  len(assets),
        "timeframes":   tf_names,
    }

    # 写会话日志（不重复写 allres，_flush_rows 已经写过了）
    try:
        import json
        hist = storage._load(storage.F_HIST, [])
        if not isinstance(hist, list):
            hist = []
        hist.append(session_row)
        if len(hist) > 50:
            hist = hist[-50:]
        storage._save(storage.F_HIST, hist)
    except Exception as e:
        logger.warning(f"save session: {e}")

    try:
        storage.save_scan_snapshot(session_row, all_rows)
    except Exception as e:
        logger.warning(f"save snapshot: {e}")

    # ── 告警发送 ──────────────────────────────────────────────
    try:
        fibo_in_zone_only = bool(cfg.get("alert_fibo_in_zone_only", True))
        for ticker, (name, _) in assets.items():
            t_rows = [r for r in all_rows if r["ticker"] == ticker]
            tf_res = {r["timeframe"]: {"in_zone": r["in_zone"], "dist_pct": r.get("dist_pct") if r.get("dist_pct") is not None else 999}
                      for r in t_rows}
            conf = confluence_score(tf_res)
            for r in t_rows:
                if (not fibo_in_zone_only) or r["in_zone"]:
                    fibo_mock = {
                        "current":     r.get("current_price"),
                        "swing_high":  r.get("swing_high"),
                        "swing_low":   r.get("swing_low"),
                        "in_zone":     bool(r.get("in_zone")),
                        "dist_pct":    r.get("dist_pct", 0),
                        "retrace_pct": r.get("retrace_pct", 0),
                    }
                    dispatch_alerts(ticker=ticker, name=name,
                                    timeframe=r["timeframe"],
                                    fibo=fibo_mock, conf=conf, cfg=cfg)
                    break
    except Exception as e:
        logger.warning(f"alerts: {e}")

    if progress_callback:
        progress_callback(1.0, f"✅ 扫描完成！{len(assets)} 个品种  |  黄金区 {inzone_count} 个  |  耗时 {elapsed_ms/1000:.1f}s")

    return {
        "session_id":   session_id,
        "scan_date":    scan_date,
        "total_checks": len(all_rows),
        "inzone_count": inzone_count,
        "triple_conf":  triple_conf,
        "elapsed_ms":   elapsed_ms,
        "asset_count":  len(assets),
        "timeframes":   tf_names,
    }, None


def scan_ema_pivot(ticker: str, cfg: Dict) -> Optional[Dict]:
    """
    计算 EMA20 + Daily Pivot Point 多头条件 (15分钟)
    返回: {
        "is_signal": bool,
        "price": float,
        "ema": float,
        "pivot": float,
        "triggered_now": bool
    } 或 None (计算失败时)
    """
    try:
        # 1. 获取 15m 级别的数据，最近 5 天以确保有足够的 Bar 计算 EMA20
        df_15m = fetch_data(ticker, interval="15m", period="5d", cfg=cfg)
        if df_15m is None or len(df_15m) < 21:
            logger.debug(f"scan_ema_pivot {ticker}: 15m data not enough or empty")
            return None
            
        # 2. 获取 1d 级别的数据，最近 5 天计算昨日 Daily Pivot
        df_1d = fetch_data(ticker, interval="1d", period="5d", cfg=cfg)
        if df_1d is None or len(df_1d) < 2:
            logger.debug(f"scan_ema_pivot {ticker}: 1d data not enough or empty")
            return None

        # 3. 计算昨日的 Pivot = (昨日 High + 昨日 Low + 昨日 Close) / 3
        # 确定最后一天是否是今天。如果是今天，则前一天是 df_1d.index[-2]；否则是 df_1d.index[-1]
        last_row_date = df_1d.index[-1]
        if hasattr(last_row_date, "date"):
            last_row_date = last_row_date.date()
        
        now_date = datetime.now().date()
        if last_row_date >= now_date:
            prev_day = df_1d.iloc[-2]
        else:
            prev_day = df_1d.iloc[-1]
            
        prev_high = float(prev_day["High"])
        prev_low = float(prev_day["Low"])
        prev_close = float(prev_day["Close"])
        daily_pivot = (prev_high + prev_low + prev_close) / 3.0

        # 4. 计算 15m K 线的 EMA20
        # Pine Script: ema20 = ta.ema(close, 20)
        # Python: df_15m["Close"].ewm(span=20, adjust=False).mean()
        ema_series = df_15m["Close"].ewm(span=20, adjust=False).mean()
        
        c_0 = float(df_15m["Close"].iloc[-1])

        # 4.5. 4小时 20-MA 过滤限制 (如果启用)
        if cfg.get("filter_4h_ema20", False):
            # 获取 4h 级别的数据，最近 30 天以确保有足够的 Bar 计算 EMA20
            df_4h = fetch_data(ticker, interval="4h", period="30d", cfg=cfg)
            if df_4h is not None and len(df_4h) >= 20:
                ema_4h_series = df_4h["Close"].ewm(span=20, adjust=False).mean()
                ema_4h_0 = float(ema_4h_series.iloc[-1])
                if c_0 <= ema_4h_0:
                    logger.debug(f"scan_ema_pivot {ticker}: 过滤拦截 (当前价 {c_0:.4f} <= 4h EMA20 {ema_4h_0:.4f})")
                    return {
                        "is_signal": False,
                        "price": c_0,
                        "ema": float(ema_series.iloc[-1]),
                        "pivot": daily_pivot,
                        "triggered_now": False
                    }
            else:
                logger.warning(f"scan_ema_pivot {ticker}: 4h数据不足，跳过4h过滤验证")
        
        # 5. 条件判断
        # latest close
        ema_0 = float(ema_series.iloc[-1])
        cond_0 = c_0 > ema_0 and c_0 > daily_pivot

        # previous close (for change check: not condition[1])
        c_1 = float(df_15m["Close"].iloc[-2])
        ema_1 = float(ema_series.iloc[-2])
        cond_1 = c_1 > ema_1 and c_1 > daily_pivot

        triggered_now = cond_0 and not cond_1

        return {
            "is_signal": cond_0,
            "price": c_0,
            "ema": ema_0,
            "pivot": daily_pivot,
            "triggered_now": triggered_now
        }
    except Exception as e:
        logger.warning(f"scan_ema_pivot {ticker} error: {e}")
        return None
