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

def generate_colab_chartink_script(tickers: list[str], pool_name: str = "系统品种库", min_volume: int = 100000, supabase_url: str = "", supabase_key: str = "", supabase_bucket: str = "strx", *args, **kwargs) -> str:
    """生成内置指定股票池代码的 Google Colab Chartink 4H 突破扫描脚本（支持结果自动直推 Supabase）"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · Chartink 4 Hour Breakout 7条规则突破极速扫描
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: 4小时 (4H Breakout)
# 判定标准: 100% 严格满足全部 7 条 Chartink 突破规则
# ==============================================================================
# 7条扫描条件（全部满足）：
#   [0] 4H Volume[0]  > 4H Volume[-1] × 2 (或已完成根 > ×2)
#   [1] 4H Volume[-1] > 4H Volume[-2] × 1.5 (或已完成根 > ×1.5)
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
# 4. 扫描完成后会自动将结果直推到 Supabase 云端，并自动下载 `colab_chartink_results.csv`
# 5. 回到 Streamlit 应用「📈 4H Breakout」页面，点击「☁️ 从云端同步」即可一键展示！
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
logging.getLogger("jupyter_client").setLevel(logging.CRITICAL)
logging.getLogger("ipykernel").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 股票池与云端直传配置
# ------------------------------------------------------------------------------
MIN_AVG_VOLUME = {min_volume}
SCAN_TICKERS = {tickers_json}

# ☁️ Supabase 云端同步配置（如为空可在运行前填入，或使用 Colab 左侧 Secrets）
SUPABASE_URL = "{supabase_url}"
SUPABASE_KEY = "{supabase_key}"
SUPABASE_BUCKET = "{supabase_bucket}"


# ------------------------------------------------------------------------------
# 🧠 高性能直连数据获取与指标工具 (直连 Yahoo v8 API)
# ------------------------------------------------------------------------------
_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=1)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)
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
        "symbol": ticker,
        "passed": False,
        "details": [],
        "error": None,
        "close": None,
        "volume_4h": None,
        "avg_volume_20": 0.0,
        "turnover": 0.0,
        "rsi": None,
        "cloud_top": None,
        "cloud_bot": None,
        "supertrend": None,
        "close_2h_m2": None,
        "vol_ratio_0": None,
        "vol_ratio_1": None,
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }}

    try:
        # 1. 获取日线数据 (1y)
        df_1d = _fetch(ticker, "1d", "1y")
        if df_1d is None or len(df_1d) < 60:
            res["error"] = "日线数据不足"
            return res

        # 均量过滤
        vols_d = df_1d["volume"].dropna().values
        avg_v20 = float(np.mean(vols_d[-20:])) if len(vols_d) >= 20 else float(np.mean(vols_d))
        latest_c = float(df_1d["close"].iloc[-1])
        res["avg_volume_20"] = avg_v20
        res["turnover"] = avg_v20 * latest_c

        if MIN_AVG_VOLUME > 0 and avg_v20 < MIN_AVG_VOLUME:
            res["error"] = f"均量不足 ({{avg_v20:,.0f}} < {{MIN_AVG_VOLUME:,.0f}})"
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

        vr0 = (v0 / max(v1, 1.0)) if v0 > v1 * 2 else (v1 / max(v2, 1.0))
        vr1 = (v1 / max(v2, 1.0)) if v1 > v2 * 1.5 else (v2 / max(v3, 1.0))

        res["close"]       = c_d
        res["volume_4h"]   = v0
        res["vol_ratio_0"] = round(vr0, 2)
        res["vol_ratio_1"] = round(vr1, 2)
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

        is_passed = all(r["ok"] for r in rules)
        
        # 跑势进度与形态阶段划分 (以云顶/Supertrend 为突破基准)
        ref_p = ct_v if (ct_v and ct_v > 0) else (st_v if (st_v and st_v > 0) else c_d)
        if c_d and ref_p and c_d >= ref_p:
            prog = round(max(0.0, ((c_d - ref_p) / ref_p) * 100.0), 1)
        else:
            prog = 0.0

        if not is_passed or prog == 0.0:
            if cb_v and c_d < cb_v:
                status_str = "invalidated"
            else:
                status_str = "active"
        else:
            status_str = "confirmed"

        res["details"] = rules
        res["passed"]  = is_passed
        res["status"]  = status_str
        res["breakout_progress"] = prog
    except Exception as e:
        res["error"] = str(e)

    return res


# ------------------------------------------------------------------------------
# 🚀 极速多线程并发执行引擎
# ------------------------------------------------------------------------------
def run_chartink_scanner():
    tickers = SCAN_TICKERS
    total_tickers = len(tickers)
    MAX_WORKERS = min(64, max(8, (os.cpu_count() or 4) * 8))
    
    print(f"\\n🚀 开启 Chartink 4H Breakout 极速并发扫描 (共 {{total_tickers}} 只股票, 线程数: {{MAX_WORKERS}})...\\n")
    sys.stdout.flush()
    
    start_time = time.time()
    completed = 0
    passed_records = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {{executor.submit(_check_ticker_chartink, tk): tk for tk in tickers}}
        
        for future in as_completed(future_map):
            completed += 1
            tk = future_map[future]
            try:
                res = future.result()
                if res.get("passed"):
                    passed_records.append(res)
                    print(f"  🔥 [发现突破] {{tk}} 满足全部 7 条 4H 突破规则! (Close: {{res['close']}}, 4H Vol: {{res['volume_4h']:,.0f}}, RSI: {{res['rsi']:.1f}}, 阶段: {{res['status']}} {{res['breakout_progress']}}%)")
                    sys.stdout.flush()
            except Exception:
                pass
                
            print_step = 100 if total_tickers > 1000 else 25
            if completed % print_step == 0 or completed == total_tickers:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 1
                rem = (total_tickers - completed) / rate
                speed = completed / elapsed if elapsed > 0 else 0
                print(f"[{{completed}}/{{total_tickers}}] 进度: {{completed*100//total_tickers}}% ({{speed:.1f}}只/秒) | 已匹配 7条全部突破: {{len(passed_records)}} 支 | 预计剩余: {{int(rem//60)}}分{{int(rem%60)}}秒")
                sys.stdout.flush()

    total_min = (time.time() - start_time) / 60
    print(f"\\n🎉 扫描全部完成！共耗时 {{total_min:.1f}} 分钟，严格检出 {{len(passed_records)}} 支 100% 满足全部 7 条规则的 4H 突破股票！")
    sys.stdout.flush()

    # 导出 CSV
    if passed_records:
        csv_rows = []
        for r in passed_records:
            details_str = json.dumps(r.get("details", []), ensure_ascii=False)
            csv_rows.append({{
                "ticker": r.get("ticker", ""),
                "symbol": r.get("ticker", ""),
                "passed": 1 if r.get("passed") else 0,
                "status": r.get("status", "confirmed"),
                "breakout_progress": r.get("breakout_progress", 0.0),
                "close": r.get("close", ""),
                "volume_4h": r.get("volume_4h", ""),
                "vol_ratio_0": r.get("vol_ratio_0", ""),
                "vol_ratio_1": r.get("vol_ratio_1", ""),
                "avg_volume_20": r.get("avg_volume_20", 0),
                "turnover": r.get("turnover", 0),
                "rsi": r.get("rsi", ""),
                "cloud_top": r.get("cloud_top", ""),
                "cloud_bot": r.get("cloud_bot", ""),
                "supertrend": r.get("supertrend", ""),
                "close_2h_m2": r.get("close_2h_m2", ""),
                "details_json": details_str,
                "scan_time": r.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }})
        
        out_df = pd.DataFrame(csv_rows)
        csv_filename = "colab_chartink_results.csv"
        out_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
        print(f"💾 结果已保存至本地: {{csv_filename}} (共 {{len(passed_records)}} 支 7条全中突破标的)")
        
        # ☁️ 自动全量覆盖上传到 Supabase
        sb_url = SUPABASE_URL.strip().rstrip("/")
        sb_key = SUPABASE_KEY.strip()
        sb_bucket = SUPABASE_BUCKET.strip()
        
        # 兼容读取 Colab Secrets (如有)
        if not sb_url or not sb_key:
            try:
                from google.colab import userdata
                sb_url = sb_url or userdata.get('SUPABASE_URL') or ""
                sb_key = sb_key or userdata.get('SUPABASE_KEY') or ""
            except Exception:
                pass

        if sb_url and sb_key:
            print("\\n☁️ 正在将最新扫描结果推送到 Supabase 云端存储 (全量覆盖更新)...")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payload_dict = {{
                "passed": passed_records,
                "failed": [],
                "errors": [],
                "scanned_at": now_str,
                "total": len(passed_records),
                "done_count": len(passed_records),
                "pool": "{pool_name}",
                "min_volume": MIN_AVG_VOLUME
            }}
            payload_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
            hdrs = {{
                "apikey": sb_key,
                "Authorization": f"Bearer {{sb_key}}",
                "Content-Type": "application/octet-stream",
                "x-upsert": "true",
            }}
            target_url = f"{{sb_url}}/storage/v1/object/{{sb_bucket}}/latest/data_chartink.json"
            try:
                r_up = requests.post(target_url, headers=hdrs, data=payload_bytes, timeout=30)
                if r_up.status_code in (400, 409, 422):
                    r_up = requests.put(target_url, headers=hdrs, data=payload_bytes, timeout=30)
                if r_up.status_code in (200, 201):
                    print("🎉 [成功] 结果已全量覆盖推送至 Supabase 云端！")
                    print("👉 回到 Streamlit 应用「📈 4H Breakout」页面，点击「☁️ 从云端同步」即可立即查看！")
                    
                    # 额外备份一份带时间戳的历史快照
                    ts_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
                    snap_url = f"{{sb_url}}/storage/v1/object/{{sb_bucket}}/backups/chartink_{{ts_snap}}.json"
                    try:
                        requests.post(snap_url, headers=hdrs, data=payload_bytes, timeout=15)
                    except Exception:
                        pass
                else:
                    print(f"⚠️ 云端直传失败 (HTTP {{r_up.status_code}}): {{r_up.text[:120]}}")
            except Exception as e_sb:
                print(f"⚠️ 云端直传网络异常: {{e_sb}}")
        else:
            print("💡 提示：如需扫描后全自动推送到 Streamlit，请在脚本顶部填入 SUPABASE_URL 与 SUPABASE_KEY。")

        try:
            from google.colab import files
            print("⬇️ 正在触发备用 CSV 自动下载...")
            files.download(csv_filename)
        except Exception:
            print(f"💡 备用下载：可在 Colab 左侧文件树中右键下载 `{{csv_filename}}`")
    else:
        print("⚠️ 未产生扫描结果（无符合全部 7 条规则的突破品种）。")

if __name__ == "__main__":
    run_chartink_scanner()
'''
    return script

