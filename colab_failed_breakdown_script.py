"""
colab_failed_breakdown_script.py — Google Colab 独立 15分钟「假跌破 + 4.236 爆发」扫描脚本生成器
========================================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整极速扫描脚本。
核心逻辑：
  1. 15分钟 K 线周期数据抓取 (Yahoo Finance v8 直连引擎)
  2. 识别 Higher Low (0点 > 前局部低) 且收盘未跌破前低
  3. 假跌破下探确认后价格强势突破 1点 (15分钟颈线 Swing High)
  4. 测算 0->1 波幅及 1.618 / 2.618 / 3.618 / 4.236 斐波那契延伸位
  5. 重点筛选与捕捉涨幅触碰或超过 4.236 延伸位的强势爆发品种
  6. 自动导出并下载 colab_failed_breakdown_results.csv
"""

import json
import pandas as pd
import numpy as np


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


def scan_failed_breakdown_15m(df: pd.DataFrame, symbol: str = "", swing_window: int = 3, lookback_bars: int = 160) -> list:
    if len(df) < swing_window * 2 + 20:
        return []

    df = df.tail(lookback_bars).reset_index(drop=True)
    df.columns = [str(c).lower() for c in df.columns]
    df = find_swing_points(df, window=swing_window)

    swing_low_idx = df.index[df["is_swing_low"]].tolist()
    swing_high_idx = df.index[df["is_swing_high"]].tolist()
    n_bars = len(df)
    latest_close = float(df.loc[df.index[-1], "close"])

    latest_vol = float(df.loc[df.index[-1], "volume"]) if "volume" in df.columns and pd.notna(df.loc[df.index[-1], "volume"]) else 0.0
    vol_slice = df["volume"].dropna().tail(20) if "volume" in df.columns else pd.Series()
    avg_vol_20 = float(vol_slice.mean()) if len(vol_slice) > 0 else latest_vol
    avg_turnover = round(avg_vol_20 * latest_close, 2)

    results = []

    if len(swing_low_idx) < 2 or len(swing_high_idx) < 1:
        return []

    for a in range(len(swing_low_idx) - 1):
        i_prev_low = swing_low_idx[a]
        i_low_0 = swing_low_idx[a + 1]

        prev_low = float(df.loc[i_prev_low, "low"])
        low_0 = float(df.loc[i_low_0, "low"])
        close_0 = float(df.loc[i_low_0, "close"])

        if low_0 <= prev_low * 1.001:
            continue

        if close_0 < prev_low:
            continue

        highs_between = [h_idx for h_idx in swing_high_idx if i_prev_low <= h_idx < i_low_0]
        if not highs_between:
            if i_low_0 - i_prev_low >= 2:
                seg_high = df.loc[i_prev_low:i_low_0, "high"]
                i_high_1 = int(seg_high.idxmax())
            else:
                continue
        else:
            i_high_1 = max(highs_between, key=lambda idx: float(df.loc[idx, "high"]))

        high_1 = float(df.loc[i_high_1, "high"])

        if high_1 <= low_0 * 1.01:
            continue

        wave_height = high_1 - low_0
        if wave_height <= 0:
            continue

        fib_1618 = round(low_0 + wave_height * 1.618, 3)
        fib_2618 = round(low_0 + wave_height * 2.618, 3)
        fib_3618 = round(low_0 + wave_height * 3.618, 3)
        fib_4236 = round(low_0 + wave_height * 4.236, 3)

        seg_after_0 = df.loc[i_low_0:]
        if len(seg_after_0) < 2:
            continue

        breakout_mask = seg_after_0["high"] > high_1
        if not breakout_mask.any():
            continue

        first_break_idx = seg_after_0.index[breakout_mask][0]
        seg_after_break = df.loc[first_break_idx:]

        max_high_post = float(seg_after_break["high"].max())
        breakout_time_str = str(df.index[first_break_idx]) if hasattr(df.index, "strftime") else ""
        bars_since = int(n_bars - 1 - first_break_idx)

        is_hit_4236 = bool(max_high_post >= fib_4236 * 0.998)
        
        gain_pct = round((max_high_post - high_1) / high_1 * 100.0, 2)
        fibo_mult = round((max_high_post - low_0) / wave_height, 3)

        if is_hit_4236:
            status = "completed"
            reason = f"已达成 4.236 延伸位 ({fib_4236:.2f})，最高冲至 {max_high_post:.2f} (+{gain_pct}%)"
            conf = 0.96
        else:
            status = "active"
            reason = f"突破颈线 ({high_1:.2f})，当前最高 {max_high_post:.2f}，朝 4.236 ({fib_4236:.2f}) 推进"
            conf = 0.85

        results.append({
            "symbol": symbol,
            "direction": "bullish",
            "pattern": "假跌破 4.236 爆发型",
            "period": "15m",
            "confidence": conf,
            "idx_prev_low": int(i_prev_low),
            "idx_low_0": int(i_low_0),
            "idx_high_1": int(i_high_1),
            "pt_prev_low": round(prev_low, 3),
            "pt_low_0": round(low_0, 3),
            "pt_high_1": round(high_1, 3),
            "neckline": round(high_1, 3),
            "entry_price": round(high_1, 3),
            "stop_loss": round(low_0 * 0.995, 3),
            "fib_1618": fib_1618,
            "fib_2618": fib_2618,
            "fib_3618": fib_3618,
            "fib_4236": fib_4236,
            "max_high_post": round(max_high_post, 3),
            "latest_close": round(latest_close, 3),
            "gain_pct": gain_pct,
            "fibo_multiple": fibo_mult,
            "is_hit_4236": is_hit_4236,
            "status": status,
            "status_reason": reason,
            "bars_since_breakout": bars_since,
            "breakout_time": breakout_time_str,
            "volume": round(latest_vol, 1),
            "avg_volume_20": round(avg_vol_20, 1),
            "turnover": avg_turnover,
        })

    results.sort(key=lambda x: (x["is_hit_4236"], x["gain_pct"]), reverse=True)
    return results[:2]


def generate_colab_script_for_tickers(tickers: list[str], pool_name: str = "系统品种库", min_volume: int = 50000) -> str:
    """生成内置指定股票池代码的 15分钟假跌破+4.236爆发 Google Colab 扫描脚本"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · 💥「15分钟假跌破 + 4.236 爆发」极速形态扫描
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: 15m (15分钟)
# 判定标准: Higher Low (0点>前低) + 突破15m颈线(1点) + 触碰/超越 4.236 斐波那契延伸位
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行极速扫描
# 4. 扫描完成后会自动下载 `colab_failed_breakdown_results.csv`
# 5. 回到 Streamlit 应用「💥 假跌破爆发」页面，拖入该 CSV 文件即可一键合并展示！
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
import requests
from requests.adapters import HTTPAdapter
import pandas as pd
import numpy as np

# ⏱️ 强制全局网络超时防卡死 (8秒自动熔断)
socket.setdefaulttimeout(8)

# 🤫 全局静音警告提示
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.captureWarnings(True)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("urllib3.connectionpool").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 扫描参数配置
# ------------------------------------------------------------------------------
PERIOD = "15m"
RANGE_STR = "60d"
SWING_WINDOW = 3
LOOKBACK_BARS = 160
MIN_AVG_VOLUME = {min_volume}

SCAN_TICKERS = {tickers_json}


# ------------------------------------------------------------------------------
# 🧠 假跌破 + 4.236 爆发核心识别算法
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


def scan_failed_breakdown_15m(df: pd.DataFrame, symbol: str = "") -> list:
    if len(df) < SWING_WINDOW * 2 + 20:
        return []

    df = df.tail(LOOKBACK_BARS).reset_index(drop=True)
    df.columns = [str(c).lower() for c in df.columns]
    df = find_swing_points(df, window=SWING_WINDOW)

    swing_low_idx = df.index[df["is_swing_low"]].tolist()
    swing_high_idx = df.index[df["is_swing_high"]].tolist()
    n_bars = len(df)
    latest_close = float(df.loc[df.index[-1], "close"])

    latest_vol = float(df.loc[df.index[-1], "volume"]) if "volume" in df.columns and pd.notna(df.loc[df.index[-1], "volume"]) else 0.0
    vol_slice = df["volume"].dropna().tail(20) if "volume" in df.columns else pd.Series()
    avg_vol_20 = float(vol_slice.mean()) if len(vol_slice) > 0 else latest_vol
    avg_turnover = round(avg_vol_20 * latest_close, 2)

    results = []

    if len(swing_low_idx) < 2 or len(swing_high_idx) < 1:
        return []

    for a in range(len(swing_low_idx) - 1):
        i_prev_low = swing_low_idx[a]
        i_low_0 = swing_low_idx[a + 1]

        prev_low = float(df.loc[i_prev_low, "low"])
        low_0 = float(df.loc[i_low_0, "low"])
        close_0 = float(df.loc[i_low_0, "close"])

        if low_0 <= prev_low * 1.001:
            continue

        if close_0 < prev_low:
            continue

        highs_between = [h_idx for h_idx in swing_high_idx if i_prev_low <= h_idx < i_low_0]
        if not highs_between:
            if i_low_0 - i_prev_low >= 2:
                seg_high = df.loc[i_prev_low:i_low_0, "high"]
                i_high_1 = int(seg_high.idxmax())
            else:
                continue
        else:
            i_high_1 = max(highs_between, key=lambda idx: float(df.loc[idx, "high"]))

        high_1 = float(df.loc[i_high_1, "high"])

        if high_1 <= low_0 * 1.01:
            continue

        wave_height = high_1 - low_0
        if wave_height <= 0:
            continue

        fib_1618 = round(low_0 + wave_height * 1.618, 3)
        fib_2618 = round(low_0 + wave_height * 2.618, 3)
        fib_3618 = round(low_0 + wave_height * 3.618, 3)
        fib_4236 = round(low_0 + wave_height * 4.236, 3)

        seg_after_0 = df.loc[i_low_0:]
        if len(seg_after_0) < 2:
            continue

        breakout_mask = seg_after_0["high"] > high_1
        if not breakout_mask.any():
            continue

        first_break_idx = seg_after_0.index[breakout_mask][0]
        seg_after_break = df.loc[first_break_idx:]

        max_high_post = float(seg_after_break["high"].max())
        breakout_time_str = str(df.index[first_break_idx]) if hasattr(df.index, "strftime") else ""
        bars_since = int(n_bars - 1 - first_break_idx)

        is_hit_4236 = bool(max_high_post >= fib_4236 * 0.998)
        
        gain_pct = round((max_high_post - high_1) / high_1 * 100.0, 2)
        fibo_mult = round((max_high_post - low_0) / wave_height, 3)

        if is_hit_4236:
            status = "completed"
            reason = f"已达成 4.236 延伸位 ({{fib_4236:.2f}})，最高冲至 {{max_high_post:.2f}} (+{{gain_pct}}%)"
            conf = 0.96
        else:
            status = "active"
            reason = f"突破颈线 ({{high_1:.2f}})，当前最高 {{max_high_post:.2f}}，朝 4.236 ({{fib_4236:.2f}}) 推进"
            conf = 0.85

        results.append({{
            "symbol": symbol,
            "direction": "bullish",
            "pattern": "假跌破 4.236 爆发型",
            "period": "15m",
            "confidence": conf,
            "idx_prev_low": int(i_prev_low),
            "idx_low_0": int(i_low_0),
            "idx_high_1": int(i_high_1),
            "pt_prev_low": round(prev_low, 3),
            "pt_low_0": round(low_0, 3),
            "pt_high_1": round(high_1, 3),
            "neckline": round(high_1, 3),
            "entry_price": round(high_1, 3),
            "stop_loss": round(low_0 * 0.995, 3),
            "fib_1618": fib_1618,
            "fib_2618": fib_2618,
            "fib_3618": fib_3618,
            "fib_4236": fib_4236,
            "max_high_post": round(max_high_post, 3),
            "latest_close": round(latest_close, 3),
            "gain_pct": gain_pct,
            "fibo_multiple": fibo_mult,
            "is_hit_4236": is_hit_4236,
            "status": status,
            "status_reason": reason,
            "bars_since_breakout": bars_since,
            "breakout_time": breakout_time_str,
            "volume": round(latest_vol, 1),
            "avg_volume_20": round(avg_vol_20, 1),
            "turnover": avg_turnover,
        }})

    results.sort(key=lambda x: (x["is_hit_4236"], x["gain_pct"]), reverse=True)
    return results[:2]


# ------------------------------------------------------------------------------
# 🚀 批量 15m 高并发极速抓取引擎
# ------------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor, as_completed

_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=1)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)
_SESSION.headers.update({{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}})

def _fetch_direct_chart_15m(ticker: str) -> pd.DataFrame:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{{ticker}}?range=60d&interval=15m&indicators=quote&includeTimestamps=true"
        r = _SESSION.get(url, timeout=(2.5, 4.5))
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {{}}).get("result")
            if result:
                res = result[0]
                timestamps = res.get("timestamp", [])
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


def _scan_single_ticker(ticker: str) -> list:
    try:
        df = _fetch_direct_chart_15m(ticker)
        if df is None or df.empty or len(df) < 30:
            return []

        if MIN_AVG_VOLUME > 0:
            vol_slice = df["volume"].dropna().tail(20) if "volume" in df.columns else pd.Series()
            c_vol = float(vol_slice.mean()) if len(vol_slice) > 0 else 0.0
            if c_vol < MIN_AVG_VOLUME:
                return []

        matches = scan_failed_breakdown_15m(df, symbol=ticker)
        for m in matches:
            m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return matches
    except Exception:
        return []


# ------------------------------------------------------------------------------
# 🚀 主执行入口
# ------------------------------------------------------------------------------
print(f"\\n" + "="*80)
print(f"🚀 开始「💥 15分钟假跌破 + 4.236 爆发」极速扫描 | 股票池: {{len(SCAN_TICKERS)}} 支品种")
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
            hit_cnt = sum(1 for r in all_results if r.get("is_hit_4236"))
            print(f"[{{completed}}/{{total_cnt}}] 进度: {{completed/total_cnt*100:.1f}}% ({{rate:.1f}}只/秒, 预估剩余: {{int(eta)}}s) -> 💥 已达4.236: {{hit_cnt}} / 总检出: {{len(all_results)}}")

print("\\n" + "="*80)
print(f"🎉 扫描全部完成！耗时: {{time.time() - start_t:.1f}} 秒，共检出 {{len(all_results)}} 条假跌破形态 (其中 {{sum(1 for r in all_results if r.get('is_hit_4236'))}} 支达成 4.236 爆发)")
print("="*80)

# ------------------------------------------------------------------------------
# 💾 保存与自动导出 CSV
# ------------------------------------------------------------------------------
csv_filename = "colab_failed_breakdown_results.csv"
if all_results:
    df_res = pd.DataFrame(all_results)
    cols = [
        "symbol", "direction", "pattern", "period", "confidence",
        "idx_prev_low", "idx_low_0", "idx_high_1",
        "pt_prev_low", "pt_low_0", "pt_high_1", "neckline",
        "entry_price", "stop_loss",
        "fib_1618", "fib_2618", "fib_3618", "fib_4236",
        "max_high_post", "latest_close", "gain_pct", "fibo_multiple",
        "is_hit_4236", "status", "status_reason", "bars_since_breakout",
        "breakout_time", "volume", "avg_volume_20", "turnover", "scan_time"
    ]
    existing_cols = [c for c in cols if c in df_res.columns]
    df_res = df_res[existing_cols]
    df_res.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    print(f"\\n✅ CSV 已成功保存到当前目录: {{csv_filename}}")

    try:
        from google.colab import files
        print("📥 正在调起浏览器自动下载...")
        files.download(csv_filename)
        print("🎉 下载指令已发送！请在 Streamlit 「💥 假跌破爆发」页面导入该 CSV 文件即可查看！")
    except Exception as e:
        print(f"💡 本地环境已保存 {{csv_filename}}，请在左侧文件栏中直接下载。")
else:
    print("\\n⚠️ 本次扫描未检出符合条件的假跌破形态。")
'''
    return script
