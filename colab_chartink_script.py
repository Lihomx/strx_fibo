"""
colab_chartink_script.py — Google Colab 独立大规模 Chartink 4H Breakout 7条规则突破扫描脚本生成器
========================================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整脚本。
包含：
  1. yfinance 批量高速下载（1D + 1H/4H/2H 高效重采样）
  2. Chartink 4 Hour Breakout 7条规则识别算法（RSI, Ichimoku Cloud, Supertrend, 4H Volume, 2H Close）
  3. 预设股票池 (全量美股 / 全量A股 / 自选 / 分组)
  4. 专注于 4小时 (4H) 突破扫描
  5. 自动导出与下载 CSV 文件，与主平台格式 100% 兼容
"""

import json

def generate_colab_chartink_script(tickers: list[str], pool_name: str = "系统品种库") -> str:
    """生成内置指定股票池代码的 Google Colab Chartink 4H 突破扫描脚本"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · Chartink 4 Hour Breakout 7条规则突破扫描脚本
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: 4小时 (4H Breakout)
# ==============================================================================
# 7条扫描条件（全部满足）：
#   [0] 4H Volume[0]  > 4H Volume[-1] * 2 (或已完成根 > *2)
#   [1] 4H Volume[-1] > 4H Volume[-2] * 1.5 (或已完成根 > *1.5)
#   [2] Daily Close   > Daily Ichimoku Cloud Top (9,26,52)
#   [3] Daily RSI(14) > 50
#   [4] Daily Close   > Daily Supertrend(7,3)
#   [5] Daily Close   > Daily Ichimoku Cloud Bottom (9,26,52)
#   [6] Daily Close   > 2H Close[-2]
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行 64 线程极速并发扫描
# 4. 扫描完成后会自动下载 `colab_chartink_results.csv`
# 5. 回到 Streamlit 应用页面，拖入该 CSV 文件即可一键合并展示！
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
import numpy as np

# ⏱️ 强制全局网络超时防卡死 (8秒自动熔断)
socket.setdefaulttimeout(8)

# 🤫 全局静音 Python 3.12 / jupyter_client 警告提示
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.captureWarnings(True)
logging.getLogger("jupyter_client").setLevel(logging.CRITICAL)
logging.getLogger("ipykernel").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 股票池配置
# ------------------------------------------------------------------------------
SCAN_TICKERS = {tickers_json}


# ------------------------------------------------------------------------------
# 🧠 高性能直连数据获取与指标工具 (直连 Yahoo v8 API，杜绝 Cookie/Crumb 锁死卡顿)
# ------------------------------------------------------------------------------
_SESSION = requests.Session()
_SESSION.headers.update({{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}})

def _fetch_direct_chart(ticker: str, range_str: str = "60d", interval: str = "1h") -> pd.DataFrame:
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
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])
                    
                    df = pd.DataFrame({{
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": vols
                    }}, index=pd.to_datetime(timestamps, unit="s")).dropna(subset=["close"])
                    return df
    except Exception:
        pass
    return None


# ------------------------------------------------------------------------------
# 🧠 指标计算工具
# ------------------------------------------------------------------------------
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ichimoku(high: pd.Series, low: pd.Series, t: int = 9, k: int = 26, s: int = 52):
    tenkan  = (high.rolling(t).max() + low.rolling(t).min()) / 2
    kijun   = (high.rolling(k).max() + low.rolling(k).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(k)
    senkou_b = ((high.rolling(s).max() + low.rolling(s).min()) / 2).shift(k)
    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    return cloud_top, cloud_bot


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 7, multiplier: float = 3.0) -> pd.Series:
    hl2 = (high + low) / 2
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    basic_upper = (hl2 + (multiplier * atr)).values
    basic_lower = (hl2 - (multiplier * atr)).values
    c = close.values
    n = len(c)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    st_line = np.zeros(n)
    trend = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(basic_upper[i]):
            continue
        final_upper[i] = basic_upper[i] if (basic_upper[i] < final_upper[i-1] or c[i-1] > final_upper[i-1]) else final_upper[i-1]
        final_lower[i] = basic_lower[i] if (basic_lower[i] > final_lower[i-1] or c[i-1] < final_lower[i-1]) else final_lower[i-1]
        if trend[i-1] == 1:
            if c[i] < final_lower[i]:
                trend[i] = -1
                st_line[i] = final_upper[i]
            else:
                trend[i] = 1
                st_line[i] = final_lower[i]
        else:
            if c[i] > final_upper[i]:
                trend[i] = 1
                st_line[i] = final_lower[i]
            else:
                trend[i] = -1
                st_line[i] = final_upper[i]
    return pd.Series(st_line, index=close.index)


# ------------------------------------------------------------------------------
# 📥 数据拉取与 7 条规则校验核心
# ------------------------------------------------------------------------------
def _fetch(ticker: str, interval: str, period: str = "6mo") -> pd.DataFrame:
    range_map = {{"1y": "1y", "2mo": "60d", "6mo": "6mo", "1mo": "1mo", "5d": "5d"}}
    r_str = range_map.get(period, "60d")
    return _fetch_direct_chart(ticker, range_str=r_str, interval=interval)


def _check_ticker_chartink(ticker: str) -> dict:
    """执行 7 条过滤规则并返回检测结果"""
    res = {{
        "ticker": ticker,
        "passed": False,
        "details": [],
        "error": None,
        "close": None,
        "volume_4h": None,
        "rsi": None,
        "cloud_top": None,
        "cloud_bot": None,
        "supertrend": None,
        "close_2h_m2": None,
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }}

    try:
        # 1. 获取日线数据 (1y)
        df_1d = _fetch(ticker, "1d", "1y")
        if df_1d is None or len(df_1d) < 60:
            res["error"] = "日线数据不足"
            return res

        # 2. 获取 1H 数据并重采样为 4H 与 2H (大幅提升速度与成功率)
        df_1h = _fetch(ticker, "1h", "2mo")
        df_4h = None
        if df_1h is not None and len(df_1h) >= 4:
            try:
                df_4h = df_1h.resample("4h").agg({{
                    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                }}).dropna(subset=["close"])
            except Exception:
                pass

        if df_4h is None or len(df_4h) < 5:
            df_4h = _fetch(ticker, "4h", "6mo")

        if df_4h is None or len(df_4h) < 5:
            res["error"] = "4H 数据不足"
            return res

        # 2H 重采样
        df_2h = None
        if df_1h is not None and len(df_1h) >= 2:
            try:
                df_2h = df_1h.resample("2h").agg({{
                    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                }}).dropna(subset=["close"])
            except Exception:
                pass

        # 计算指标
        close_d = df_1d["close"]
        high_d  = df_1d["high"]
        low_d   = df_1d["low"]

        rsi_ser = _rsi(close_d, 14)
        cloud_top, cloud_bot = _ichimoku(high_d, low_d, 9, 26, 52)
        supertrend_ser = _supertrend(high_d, low_d, close_d, 7, 3.0)

        c_d   = float(close_d.iloc[-1])
        rsi_v = float(rsi_ser.iloc[-1])    if not pd.isna(rsi_ser.iloc[-1])    else None
        ct_v  = float(cloud_top.iloc[-1])  if not pd.isna(cloud_top.iloc[-1])  else None
        cb_v  = float(cloud_bot.iloc[-1])  if not pd.isna(cloud_bot.iloc[-1])  else None
        st_v  = float(supertrend_ser.iloc[-1]) if not pd.isna(supertrend_ser.iloc[-1]) else None

        vol_4h = df_4h["volume"]
        v0 = float(vol_4h.iloc[-1])
        v1 = float(vol_4h.iloc[-2])
        v2 = float(vol_4h.iloc[-3])
        v3 = float(vol_4h.iloc[-4]) if len(vol_4h) >= 4 else v2

        c_2h_m2 = None
        if df_2h is not None and len(df_2h) >= 3:
            c_2h_m2 = float(df_2h["close"].iloc[-3])

        res["close"]       = c_d
        res["volume_4h"]   = v0
        res["rsi"]         = rsi_v
        res["cloud_top"]   = ct_v
        res["cloud_bot"]   = cb_v
        res["supertrend"]  = st_v
        res["close_2h_m2"] = c_2h_m2

        # 7条规则判定
        rules = [
            {{
                "id": "[0]",
                "desc": "4H Volume[0] > 4H Volume[-1] × 2 (或已完成根 > ×2)",
                "ok": bool((v0 > v1 * 2) or (v1 > v2 * 2)),
                "val": f"{{v0:,.0f}} vs {{v1:,.0f}}×2={{v1*2:,.0f}}" if (v0 > v1 * 2) else f"前根: {{v1:,.0f}} vs {{v2:,.0f}}×2={{v2*2:,.0f}}",
            }},
            {{
                "id": "[1]",
                "desc": "4H Volume[-1] > 4H Volume[-2] × 1.5 (或已完成根 > ×1.5)",
                "ok": bool((v1 > v2 * 1.5) or (v2 > v3 * 1.5)),
                "val": f"{{v1:,.0f}} vs {{v2:,.0f}}×1.5={{v2*1.5:,.0f}}" if (v1 > v2 * 1.5) else f"前前根: {{v2:,.0f}} vs {{v3:,.0f}}×1.5={{v3*1.5:,.0f}}",
            }},
            {{
                "id": "[2]",
                "desc": "Daily Close > Ichimoku Cloud Top(9,26,52)",
                "ok": bool((ct_v is not None) and (c_d > ct_v)),
                "val": f"Close={{c_d:.4f}}  CloudTop={{ct_v:.4f}}" if ct_v else "数据不足",
            }},
            {{
                "id": "[3]",
                "desc": "Daily RSI(14) > 50",
                "ok": bool((rsi_v is not None) and (rsi_v > 50)),
                "val": f"RSI={{rsi_v:.2f}}" if rsi_v else "数据不足",
            }},
            {{
                "id": "[4]",
                "desc": "Daily Close > Supertrend(7,3)",
                "ok": bool((st_v is not None) and (c_d > st_v)),
                "val": f"Close={{c_d:.4f}}  ST={{st_v:.4f}}" if st_v else "数据不足",
            }},
            {{
                "id": "[5]",
                "desc": "Daily Close > Ichimoku Cloud Bottom(9,26,52)",
                "ok": bool((cb_v is not None) and (c_d > cb_v)),
                "val": f"Close={{c_d:.4f}}  CloudBot={{cb_v:.4f}}" if cb_v else "数据不足",
            }},
            {{
                "id": "[6]",
                "desc": "Daily Close > 2H Close[-2]",
                "ok": bool((c_2h_m2 is not None) and (c_d > c_2h_m2)),
                "val": f"Close={{c_d:.4f}}  2H[-2]={{c_2h_m2:.4f}}" if c_2h_m2 else "2H数据不足",
            }},
        ]

        res["details"] = rules
        res["passed"]  = all(r["ok"] for r in rules)
    except Exception as e:
        res["error"] = str(e)

    return res


# ------------------------------------------------------------------------------
# 🚀 极速多线程并发执行引擎
# ------------------------------------------------------------------------------
def run_chartink_scanner():
    tickers = SCAN_TICKERS
    total_tickers = len(tickers)
    MAX_WORKERS = 32
    
    print(f"\\n🚀 开启 Chartink 4H Breakout 极速并发扫描 (共 {{total_tickers}} 只股票, 线程数: {{MAX_WORKERS}})...\\n")
    sys.stdout.flush()
    
    start_time = time.time()
    completed = 0
    passed_records = []
    all_records = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {{executor.submit(_check_ticker_chartink, tk): tk for tk in tickers}}
        
        for future in as_completed(future_map):
            completed += 1
            tk = future_map[future]
            try:
                res = future.result()
                all_records.append(res)
                if res.get("passed"):
                    passed_records.append(res)
                    print(f"  🔥 [发现突破] {{tk}} 满足全部 7 条 4H 突破规则! (Close: {{res['close']}}, 4H Vol: {{res['volume_4h']:,.0f}}, RSI: {{res['rsi']:.1f}})")
                    sys.stdout.flush()
            except Exception as e:
                all_records.append({{"ticker": tk, "passed": False, "details": [], "error": str(e), "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}})
                
            print_step = 50 if total_tickers > 1000 else 25
            if completed % print_step == 0 or completed == total_tickers:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 1
                rem = (total_tickers - completed) / rate
                speed = completed / elapsed if elapsed > 0 else 0
                print(f"[{{completed}}/{{total_tickers}}] 进度: {{completed*100//total_tickers}}% ({{speed:.1f}}只/秒) | 已匹配突破: {{len(passed_records)}} 支 | 预计剩余: {{int(rem//60)}}分{{int(rem%60)}}秒")
                sys.stdout.flush()

    total_min = (time.time() - start_time) / 60
    print(f"\\n🎉 扫描全部完成！共耗时 {{total_min:.1f}} 分钟，匹配到 {{len(passed_records)}} 支 4H 突破股票！")
    sys.stdout.flush()

    # 导出 CSV
    if all_records:
        csv_rows = []
        for r in all_records:
            details_str = json.dumps(r.get("details", []), ensure_ascii=False)
            csv_rows.append({{
                "ticker": r.get("ticker", ""),
                "passed": 1 if r.get("passed") else 0,
                "close": r.get("close", ""),
                "volume_4h": r.get("volume_4h", ""),
                "rsi": r.get("rsi", ""),
                "cloud_top": r.get("cloud_top", ""),
                "cloud_bot": r.get("cloud_bot", ""),
                "supertrend": r.get("supertrend", ""),
                "close_2h_m2": r.get("close_2h_m2", ""),
                "error": r.get("error", "") or "",
                "details_json": details_str,
                "scan_time": r.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }})
        
        out_df = pd.DataFrame(csv_rows)
        csv_filename = "colab_chartink_results.csv"
        out_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
        print(f"💾 结果已保存至: {{csv_filename}} (包含通过 {{len(passed_records)}} 支, 共 {{len(all_records)}} 支)")
        
        try:
            from google.colab import files
            print("⬇️ 正在触发自动下载到本地...")
            files.download(csv_filename)
        except Exception:
            print(f"💡 可在 Colab 左侧文件树中右键下载 `{{csv_filename}}`")
    else:
        print("⚠️ 未产生扫描结果。")

if __name__ == "__main__":
    run_chartink_scanner()
'''
    return script
