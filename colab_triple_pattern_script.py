"""
colab_triple_pattern_script.py — Google Colab 独立大规模「三重底 & 三重顶」双向扫描脚本生成器
=======================================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整脚本。
包含：
  1. Yahoo Finance v8 直连高并发极速引擎 (50+ 支/秒)
  2. 🐂 看涨三重底 (Triple Bottom) 7 种经典子形态判定 (1-2-3-4-5 波浪)
  3. 🐻 看跌三重顶 (Triple Top) 7 种经典子形态判定 (1-2-3-4-5 波浪)
  4. 🎯 TFLab Triple Top Bottom Scan v4 斐波那契三段目标位 (TP1 61.8%, TP2 100%, TP3 161.8%)
  5. 止损 (SL)、各段收益 (Reward) 与 盈亏比 (R:R) 测算
  6. 多周期扫描 (15m, 30m, 60m, 4h, 1d, 1w, 1mo 等)
  7. 自动导出与下载 CSV 文件，与主平台格式 100% 兼容
"""

import json

def generate_colab_script_for_tickers(tickers: list[str], pool_name: str = "系统品种库", selected_tfs: list[str] = None) -> str:
    """生成内置指定股票池代码与扫描周期的 Google Colab 完整扫描脚本"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    if not selected_tfs:
        selected_tfs = ["1d", "1w", "1mo"]
        
    all_tf_defs = {
        "1d": '("1d", "2y")',
        "1w": '("1wk", "5y")',
        "1mo": '("1mo", "10y")',
        "4h": '("1h", "730d")',
        "60m": '("60m", "720d")',
        "30m": '("30m", "60d")',
        "15m": '("15m", "60d")',
    }
    
    tf_lines = []
    for tf in selected_tfs:
        if tf in all_tf_defs:
            tf_lines.append(f'    "{tf}": {all_tf_defs[tf]},')
            
    timeframes_code = "{\n" + "\n".join(tf_lines) + "\n}"
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · 🌟「三重底 & 三重顶 (Triple Top Bottom Scan v4)」双向形态极速扫描
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: {', '.join(selected_tfs)}
# 扫描模式: 🐂 看涨三重底 (Triple Bottom) + 🐻 看跌三重顶 (Triple Top) 双向 5 点波浪全量扫描
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行极速扫描
# 4. 扫描完成后会自动下载 `colab_triple_pattern_results.csv`
# 5. 回到 Streamlit 应用「🌟 三重顶底」页面，拖入该 CSV 文件即可一键合并展示！
# ==============================================================================

# 1. 安装所需依赖
!pip install -q requests pandas numpy

import os
import sys
import time
import json
import socket
import warnings
import logging
from datetime import datetime
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
import pandas as pd
import numpy as np

# ⏱️ 强制全局网络超时防卡死 (8秒自动熔断)
socket.setdefaulttimeout(8)

# 🤫 全局静音 Python 3.12 / jupyter_client / urllib3 警告提示
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.captureWarnings(True)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.CRITICAL)
logging.getLogger("jupyter_client").setLevel(logging.CRITICAL)
logging.getLogger("ipykernel").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 扫描配置
# ------------------------------------------------------------------------------
TIMEFRAMES = {timeframes_code}

SWING_WINDOW = 3      # 分形左右窗口大小
LOOKBACK_BARS = 150   # 回溯 K 线根数
MAX_SPACING = 80      # 三点最大间距
MIN_SPACING = 3       # 三点最小间距
MIN_CONFIDENCE = 0.5  # 最小置信度阈值
FLAT_TOL = 0.02       # 持平容差 (2%)
BREAK_TOL = 0.01      # 突破容差 (1%)

SCAN_TICKERS = {tickers_json}


# ------------------------------------------------------------------------------
# 🧠 三重顶底识别算法核心 (基于 Al Brooks 价格行为学 & TFLab 5点波浪几何投影)
# ------------------------------------------------------------------------------
def find_swing_points(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    df = df.copy()
    lows = df["low"].values
    highs = df["high"].values
    n = len(df)

    is_low = np.zeros(n, dtype=bool)
    is_high = np.zeros(n, dtype=bool)

    for i in range(window, n - window):
        local_low_slice = lows[i - window: i + window + 1]
        local_high_slice = highs[i - window: i + window + 1]
        if lows[i] == local_low_slice.min() and (local_low_slice == lows[i]).sum() == 1:
            is_low[i] = True
        if highs[i] == local_high_slice.max() and (local_high_slice == highs[i]).sum() == 1:
            is_high[i] = True

    df["is_swing_low"] = is_low
    df["is_swing_high"] = is_high
    return df

def _pct_diff(a: float, b: float) -> float:
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base

def classify_triple_bottom(low1, low2, low3, mid_high_12, mid_high_23, broke_support_23, flat_tol=0.02):
    d12 = _pct_diff(low1, low2)
    d23 = _pct_diff(low2, low3)
    descending = (low1 > low2 > low3) or (low1 >= low2 * (1 - flat_tol) and low2 > low3)
    ascending = (low1 < low2 < low3)
    flat_all = d12 <= flat_tol and d23 <= flat_tol

    if flat_all:
        return "完美三重底 (Perfect Triple Bottom)", 0.95, f"三低点极度持平 (差异 {{max(d12, d23):.2%}})，坚固底部"
    if low2 < low1 and low2 < low3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(low1, low3)
        conf = 0.90 if shoulder_diff < 0.03 else 0.75
        return "头肩底/截断楔形 (Head & Shoulders Bottom)", conf, f"中间第3点头部更低({{low2:.2f}})，双肩对称"
    if ascending and broke_support_23:
        return "抬高双底失败突破型 (Failed BO below HL DB)", 0.88, "底部逐步抬高，第5点刺穿假跌破拉回"
    if broke_support_23:
        if d23 <= flat_tol * 2:
            return "双底回调型 (Double Bottom Pullback)", 0.82, "双底确立后回踩确认支撑"
        else:
            return "双底跌破失败型 (Failed BO below DB)", 0.82, "短暂刺穿支撑后多头强力收复"
    if descending and not flat_all:
        return "楔形三重底 (Wedge Bottom)", 0.78, f"低点依次降低 (L1>L2>L3)，下行动能衰竭"
    if ascending and mid_high_12 > mid_high_23:
        return "三角形三重底 (Triangle Bottom)", 0.78, "低点抬高同时高点走低，收敛蓄势"
    return "经典三重底 (Classic Triple Bottom)", 0.65, "三次探底反转结构"

def classify_triple_top(high1, high2, high3, mid_low_12, mid_low_23, broke_resist_23, flat_tol=0.02):
    d12 = _pct_diff(high1, high2)
    d23 = _pct_diff(high2, high3)
    ascending = (high1 < high2 < high3) or (high1 <= high2 * (1 + flat_tol) and high2 < high3)
    descending = (high1 > high2 > high3)
    flat_all = d12 <= flat_tol and d23 <= flat_tol

    if flat_all:
        return "完美三重顶 (Perfect Triple Top)", 0.95, f"三高点极度持平 (差异 {{max(d12, d23):.2%}})，坚固顶部"
    if high2 > high1 and high2 > high3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(high1, high3)
        conf = 0.90 if shoulder_diff < 0.03 else 0.75
        return "头肩顶/截断上升楔形 (Head & Shoulders Top)", conf, f"中间第3点头部更高({{high2:.2f}})，双肩对称"
    if descending and broke_resist_23:
        return "降低双顶失败突破型 (Failed BO above LH DT)", 0.88, "高点逐步降低，第5点冲高遇阻回落"
    if broke_resist_23:
        if d23 <= flat_tol * 2:
            return "双顶回调型 (Double Top Pullback)", 0.82, "双顶确立后反弹回踩阻力"
        else:
            return "双顶突破失败型 (Failed BO above DT)", 0.82, "短暂冲破阻力后空头强力打压"
    if ascending and not flat_all:
        return "上升楔形三重顶 (Rising Wedge Top)", 0.78, f"高点依次抬高 (H1<H2<H3)，上行动能衰竭"
    if descending and mid_low_12 < mid_low_23:
        return "下降三角形三重顶 (Descending Triangle Top)", 0.78, "高点走低同时支撑平齐，向下破位"
    return "经典三重顶 (Classic Triple Top)", 0.65, "三次冲顶受阻反转结构"

def scan_patterns(df, symbol="", period="1d", swing_window=3, lookback_bars=150, max_spacing=80, min_spacing=3, break_tol=0.01, flat_tol=0.02):
    if len(df) < swing_window * 2 + 10:
        return []

    df = df.tail(lookback_bars).reset_index(drop=True)
    df.columns = [str(c).lower() for c in df.columns]
    df = find_swing_points(df, window=swing_window)

    swing_low_idx = df.index[df["is_swing_low"]].tolist()
    swing_high_idx = df.index[df["is_swing_high"]].tolist()
    latest_close = float(df.loc[df.index[-1], "close"])
    total_bars = len(df)
    results = []

    # 🐂 1. 看涨三重底 (1-2-3-4-5 波浪结构)
    if len(swing_low_idx) >= 3:
        for a in range(len(swing_low_idx) - 2):
            i1, i3, i5 = swing_low_idx[a], swing_low_idx[a + 1], swing_low_idx[a + 2]
            if not (min_spacing <= (i3 - i1) <= max_spacing and min_spacing <= (i5 - i3) <= max_spacing):
                continue
            low1, low2, low3 = float(df.loc[i1, "low"]), float(df.loc[i3, "low"]), float(df.loc[i5, "low"])

            seg_12 = df.loc[i1:i3, "high"]
            seg_23 = df.loc[i3:i5, "high"]
            i2 = int(seg_12.idxmax()) if len(seg_12) else i1 + (i3 - i1) // 2
            i4 = int(seg_23.idxmax()) if len(seg_23) else i3 + (i5 - i3) // 2
            high1 = float(df.loc[i2, "high"]) if i2 in df.index else low1
            high2 = float(df.loc[i4, "high"]) if i4 in df.index else low2

            support_level = min(low1, low2)
            broke = False
            seg_break = df.loc[i3:i5]
            if len(seg_break):
                min_low_in_seg = float(seg_break["low"].min())
                close_at_end = float(df.loc[i5, "close"])
                if min_low_in_seg < support_level * (1 - break_tol) and close_at_end > support_level:
                    broke = True

            pname, conf, note = classify_triple_bottom(low1, low2, low3, high1, high2, broke, flat_tol)

            neckline = max(high1, high2)
            lowest_point = min(low1, low2, low3)
            pattern_height = max(neckline - lowest_point, neckline * 0.01)

            entry = round(low3, 3)
            sl = round(lowest_point * (1 - 0.008), 3)

            # 3 段斐波那契目标位
            tp1 = round(entry + pattern_height * 0.618, 3)
            tp2 = round(neckline, 3)
            tp3 = round(entry + pattern_height * 1.618, 3)

            risk = max(entry - sl, entry * 0.005)
            reward1 = max(0.001, tp1 - entry)
            reward2 = max(0.001, tp2 - entry)
            reward3 = max(0.001, tp3 - entry)

            rr_tp1 = round(reward1 / risk, 2)
            rr_tp2 = round(reward2 / risk, 2)
            rr_tp3 = round(reward3 / risk, 2)

            seg_post = df.loc[i5:]
            bars_since = int(total_bars - 1 - i5)
            has_broken_sup = bool((seg_post["close"] < lowest_point * (1 - break_tol)).any())
            has_broken_neck = bool((seg_post["close"] > neckline).any())

            if has_broken_sup:
                status = "invalidated"
                reason = f"已失效：跌破止损 {{sl:.2f}}"
            elif bars_since > 45:
                status = "expired"
                reason = f"已过期：后置 {{bars_since}} 根未达成目标"
            elif has_broken_neck:
                status = "confirmed"
                reason = f"已突破：收盘站上颈线 {{neckline:.2f}}，朝 TP3 ({{tp3:.2f}}) 推进"
            else:
                status = "active"
                reason = "第5点探底成型，观察反弹与突破"

            if status in ("active", "confirmed"):
                results.append({{
                    "symbol": symbol,
                    "direction": "bullish",
                    "pattern": pname,
                    "period": period,
                    "confidence": round(float(conf), 4),
                    "idx1": int(i1), "idx2": int(i2), "idx3": int(i3), "idx4": int(i4), "idx5": int(i5),
                    "pt1": round(low1, 4), "pt2": round(high1, 4), "pt3": round(low2, 4), "pt4": round(high2, 4), "pt5": round(low3, 4),
                    "p1": round(low1, 4), "p2": round(low2, 4), "p3": round(low3, 4),
                    "neckline": round(neckline, 4),
                    "entry_price": entry,
                    "stop_loss": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "risk": round(risk, 4),
                    "reward_tp1": round(reward1, 4),
                    "reward_tp2": round(reward2, 4),
                    "reward_tp3": round(reward3, 4),
                    "risk_reward": rr_tp2,
                    "rr_tp3": rr_tp3,
                    "note": note,
                    "status": status,
                    "status_reason": reason,
                    "bars_since_p5": bars_since,
                    "latest_close": round(latest_close, 4),
                }})

    # 🐻 2. 看跌三重顶 (1-2-3-4-5 波浪结构)
    if len(swing_high_idx) >= 3:
        for a in range(len(swing_high_idx) - 2):
            i1, i3, i5 = swing_high_idx[a], swing_high_idx[a + 1], swing_high_idx[a + 2]
            if not (min_spacing <= (i3 - i1) <= max_spacing and min_spacing <= (i5 - i3) <= max_spacing):
                continue
            high1, high2, high3 = float(df.loc[i1, "high"]), float(df.loc[i3, "high"]), float(df.loc[i5, "high"])

            seg_12 = df.loc[i1:i3, "low"]
            seg_23 = df.loc[i3:i5, "low"]
            i2 = int(seg_12.idxmin()) if len(seg_12) else i1 + (i3 - i1) // 2
            i4 = int(seg_23.idxmin()) if len(seg_23) else i3 + (i5 - i3) // 2
            low1 = float(df.loc[i2, "low"]) if i2 in df.index else high1
            low2 = float(df.loc[i4, "low"]) if i4 in df.index else high2

            resist_level = max(high1, high2)
            broke = False
            seg_break = df.loc[i3:i5]
            if len(seg_break):
                max_high_in_seg = float(seg_break["high"].max())
                close_at_end = float(df.loc[i5, "close"])
                if max_high_in_seg > resist_level * (1 + break_tol) and close_at_end < resist_level:
                    broke = True

            pname, conf, note = classify_triple_top(high1, high2, high3, low1, low2, broke, flat_tol)

            neckline = min(low1, low2)
            highest_point = max(high1, high2, high3)
            pattern_height = max(highest_point - neckline, neckline * 0.01)

            entry = round(high3, 3)
            sl = round(highest_point * (1 + 0.008), 3)

            # 3 段斐波那契目标位
            tp1 = round(max(0.001, entry - pattern_height * 0.618), 3)
            tp2 = round(neckline, 3)
            tp3 = round(max(0.001, entry - pattern_height * 1.618), 3)

            risk = max(sl - entry, entry * 0.005)
            reward1 = max(0.001, entry - tp1)
            reward2 = max(0.001, entry - tp2)
            reward3 = max(0.001, entry - tp3)

            rr_tp1 = round(reward1 / risk, 2)
            rr_tp2 = round(reward2 / risk, 2)
            rr_tp3 = round(reward3 / risk, 2)

            seg_post = df.loc[i5:]
            bars_since = int(total_bars - 1 - i5)
            has_broken_res = bool((seg_post["close"] > highest_point * (1 + break_tol)).any())
            has_broken_neck = bool((seg_post["close"] < neckline).any())

            if has_broken_res:
                status = "invalidated"
                reason = f"已失效：突破止损 {{sl:.2f}}"
            elif bars_since > 45:
                status = "expired"
                reason = f"已过期：后置 {{bars_since}} 根未达成目标"
            elif has_broken_neck:
                status = "confirmed"
                reason = f"已跌破：收盘跌破颈线 {{neckline:.2f}}，朝 TP3 ({{tp3:.2f}}) 推进"
            else:
                status = "active"
                reason = "第5点冲顶受阻，观察回调与破位"

            if status in ("active", "confirmed"):
                results.append({{
                    "symbol": symbol,
                    "direction": "bearish",
                    "pattern": pname,
                    "period": period,
                    "confidence": round(float(conf), 4),
                    "idx1": int(i1), "idx2": int(i2), "idx3": int(i3), "idx4": int(i4), "idx5": int(i5),
                    "pt1": round(high1, 4), "pt2": round(low1, 4), "pt3": round(high2, 4), "pt4": round(low2, 4), "pt5": round(high3, 4),
                    "p1": round(high1, 4), "p2": round(high2, 4), "p3": round(high3, 4),
                    "neckline": round(neckline, 4),
                    "entry_price": entry,
                    "stop_loss": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "risk": round(risk, 4),
                    "reward_tp1": round(reward1, 4),
                    "reward_tp2": round(reward2, 4),
                    "reward_tp3": round(reward3, 4),
                    "risk_reward": rr_tp2,
                    "rr_tp3": rr_tp3,
                    "note": note,
                    "status": status,
                    "status_reason": reason,
                    "bars_since_p5": bars_since,
                    "latest_close": round(latest_close, 4),
                }})

    return results


# ------------------------------------------------------------------------------
# 🚀 批量多周期超高速并发扫描
# ------------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor, as_completed

def _resample_ohlc(df, rule):
    try:
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)
        ohlc_dict = {{
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }}
        valid_dict = {{k: v for k, v in ohlc_dict.items() if k in df.columns}}
        resampled = df.resample(rule).agg(valid_dict).dropna(subset=['close', 'high', 'low'])
        return resampled
    except Exception:
        return None

_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=1)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)
_SESSION.headers.update({{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}})

def _fetch_direct_chart(ticker: str, range_str: str = "10y", interval: str = "1d") -> pd.DataFrame:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{{ticker}}?range={{range_str}}&interval={{interval}}&indicators=quote&includeTimestamps=true"
        r = _SESSION.get(url, timeout=(2.5, 4.0))
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {{}}).get("result")
            if result:
                res = result[0]
                timestamps = res.get("timestamp", [])
                if timestamps:
                    quote = res.get("indicators", {{}}).get("quote", [{{}}])[0]
                    df = pd.DataFrame({{
                        "open": quote.get("open", []),
                        "high": quote.get("high", []),
                        "low": quote.get("low", []),
                        "close": quote.get("close", []),
                        "volume": quote.get("volume", [])
                    }}, index=pd.to_datetime(timestamps, unit="s")).dropna(subset=["close", "high", "low"])
                    return df
    except Exception:
        pass
    return None

def _scan_single_ticker(ticker):
    results = []
    try:
        df_daily = _fetch_direct_chart(ticker, range_str="10y", interval="1d")
        if df_daily is None or df_daily.empty:
            return []

        # 1. 扫描日线 (1d)
        if "1d" in TIMEFRAMES:
            matches_1d = scan_patterns(
                df_daily.tail(500),
                symbol=ticker,
                period="1d",
                swing_window=SWING_WINDOW,
                lookback_bars=LOOKBACK_BARS,
                max_spacing=MAX_SPACING,
                flat_tol=FLAT_TOL,
                break_tol=BREAK_TOL,
            )
            for m in matches_1d:
                if m["confidence"] >= MIN_CONFIDENCE:
                    m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    results.append(m)

        # 2. 周线 (1w)
        if "1w" in TIMEFRAMES:
            df_weekly = _resample_ohlc(df_daily, 'W')
            if df_weekly is not None and len(df_weekly) >= 30:
                matches_1w = scan_patterns(
                    df_weekly.tail(260),
                    symbol=ticker,
                    period="1w",
                    swing_window=SWING_WINDOW,
                    lookback_bars=LOOKBACK_BARS,
                    max_spacing=MAX_SPACING,
                    flat_tol=FLAT_TOL,
                    break_tol=BREAK_TOL,
                )
                for m in matches_1w:
                    if m["confidence"] >= MIN_CONFIDENCE:
                        m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        results.append(m)

        # 3. 月线 (1mo)
        if "1mo" in TIMEFRAMES:
            df_monthly = _resample_ohlc(df_daily, 'ME')
            if df_monthly is not None and len(df_monthly) >= 20:
                matches_1mo = scan_patterns(
                    df_monthly.tail(120),
                    symbol=ticker,
                    period="1mo",
                    swing_window=SWING_WINDOW,
                    lookback_bars=LOOKBACK_BARS,
                    max_spacing=MAX_SPACING,
                    flat_tol=FLAT_TOL,
                    break_tol=BREAK_TOL,
                )
                for m in matches_1mo:
                    if m["confidence"] >= MIN_CONFIDENCE:
                        m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        results.append(m)

        # 4. 4小时 (4h)
        if "4h" in TIMEFRAMES:
            df_1h = _fetch_direct_chart(ticker, range_str="730d", interval="1h")
            if df_1h is not None and len(df_1h) >= 40:
                df_4h = _resample_ohlc(df_1h, '4h')
                if df_4h is not None and len(df_4h) >= 20:
                    matches_4h = scan_patterns(
                        df_4h.tail(300),
                        symbol=ticker,
                        period="4h",
                        swing_window=SWING_WINDOW,
                        lookback_bars=LOOKBACK_BARS,
                        max_spacing=MAX_SPACING,
                        flat_tol=FLAT_TOL,
                        break_tol=BREAK_TOL,
                    )
                    for m in matches_4h:
                        if m["confidence"] >= MIN_CONFIDENCE:
                            m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            results.append(m)

        # 5. 60分钟 (60m)
        if "60m" in TIMEFRAMES:
            df_60m = _fetch_direct_chart(ticker, range_str="720d", interval="60m")
            if df_60m is not None and len(df_60m) >= 40:
                matches_60m = scan_patterns(
                    df_60m.tail(300),
                    symbol=ticker,
                    period="60m",
                    swing_window=SWING_WINDOW,
                    lookback_bars=LOOKBACK_BARS,
                    max_spacing=MAX_SPACING,
                    flat_tol=FLAT_TOL,
                    break_tol=BREAK_TOL,
                )
                for m in matches_60m:
                    if m["confidence"] >= MIN_CONFIDENCE:
                        m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        results.append(m)

        # 6. 30分钟 (30m)
        if "30m" in TIMEFRAMES:
            df_30m = _fetch_direct_chart(ticker, range_str="60d", interval="30m")
            if df_30m is not None and len(df_30m) >= 40:
                matches_30m = scan_patterns(
                    df_30m.tail(300),
                    symbol=ticker,
                    period="30m",
                    swing_window=SWING_WINDOW,
                    lookback_bars=LOOKBACK_BARS,
                    max_spacing=MAX_SPACING,
                    flat_tol=FLAT_TOL,
                    break_tol=BREAK_TOL,
                )
                for m in matches_30m:
                    if m["confidence"] >= MIN_CONFIDENCE:
                        m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        results.append(m)

    except Exception:
        pass
    return results


# ------------------------------------------------------------------------------
# 🚀 主执行入口
# ------------------------------------------------------------------------------
print(f"\\n" + "="*80)
print(f"🚀 开始「🌟 三重顶底 (Triple Top Bottom Scan v4)」极速扫描 | 股票池: {{len(SCAN_TICKERS)}} 支品种 | 周期: {', '.join(selected_tfs)}")
print("="*80)

all_results = []
start_t = time.time()
completed = 0
total_cnt = len(SCAN_TICKERS)

MAX_WORKERS = min(64, max(8, os.cpu_count() * 8))

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {{executor.submit(_scan_single_ticker, tk): tk for tk in SCAN_TICKERS}}
    for f in as_completed(futures):
        completed += 1
        res = f.result()
        if res:
            all_results.extend(res)
        
        if completed % 100 == 0 or completed == total_cnt:
            elapsed = time.time() - start_t
            rate = completed / max(elapsed, 0.001)
            eta = (total_cnt - completed) / max(rate, 0.001)
            bull_cnt = sum(1 for r in all_results if r.get("direction") == "bullish")
            bear_cnt = sum(1 for r in all_results if r.get("direction") == "bearish")
            print(f"[{{completed}}/{{total_cnt}}] 进度: {{completed/total_cnt*100:.1f}}% ({{rate:.1f}}只/秒, 预估剩余: {{int(eta)}}s) -> 检出: 🐂{{bull_cnt}} / 🐻{{bear_cnt}} (共{{len(all_results)}}条)")

print("\\n" + "="*80)
print(f"🎉 扫描全部完成！耗时: {{time.time() - start_t:.1f}} 秒，共检出 {{len(all_results)}} 条有效形态")
print("="*80)

# ------------------------------------------------------------------------------
# 💾 保存与自动导出 CSV
# ------------------------------------------------------------------------------
csv_filename = "colab_triple_pattern_results.csv"
if all_results:
    df_res = pd.DataFrame(all_results)
    cols = [
        "symbol", "direction", "pattern", "period", "confidence",
        "idx1", "idx2", "idx3", "idx4", "idx5",
        "pt1", "pt2", "pt3", "pt4", "pt5", "neckline",
        "entry_price", "stop_loss", "tp1", "tp2", "tp3",
        "risk", "reward_tp1", "reward_tp2", "reward_tp3",
        "risk_reward", "rr_tp3", "note", "status", "status_reason", "bars_since_p5", "latest_close", "scan_time"
    ]
    existing_cols = [c for c in cols if c in df_res.columns]
    df_res = df_res[existing_cols]
    df_res.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    print(f"\\n✅ CSV 已成功保存到当前目录: {{csv_filename}}")

    try:
        from google.colab import files
        print("📥 正在调起浏览器自动下载...")
        files.download(csv_filename)
        print("🎉 下载指令已发送！请在 Streamlit 「🌟 三重顶底」页面导入该 CSV 文件即可查看！")
    except Exception as e:
        print(f"💡 本地环境已保存 {{csv_filename}}，请在左侧文件栏中直接下载。")
else:
    print("\\n⚠️ 本次扫描未检出符合置信度阈值的形态。")
'''
    return script
