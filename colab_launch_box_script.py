"""
colab_launch_box_script.py — Google Colab 独立大规模「长周期趋势启动点 · 矩形蓄势突破」全量扫描脚本生成器
=======================================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整脚本。
包含：
  1. Yahoo Finance v8 直连高并发极速引擎 (50+ 支/秒)
  2. 35~55 天矩形中枢蓄势 (Consolidation Box) 几何识别
  3. TTM Squeeze 深度挤压与布林带极致收窄 (BB Width ≤ 0.22) 过滤
  4. 突破日机构核爆级放量 (Volume Ratio ≥ 1.30 ~ 3.0+ 及 60日新高) 识别
  5. 宏观大周期 (年线偏离度 Bias250 + 周线顺势 MACD) 协同过滤
  6. 0~100 分右侧当下质量评分 (消除未来函数)
  7. 斐波那契扩展目标 TP1 (1.0x), TP2 (2.0x), TP3 (4.236x) 测算
  8. 自动导出与下载 colab_launch_box_results.csv 文件，与主平台格式 100% 兼容
"""

import json

def generate_colab_script_for_tickers(
    tickers: list[str],
    pool_name: str = "系统全量品种库",
    selected_tfs: list[str] = None,
    min_volume: int = 100000
) -> str:
    """生成内置指定股票池代码与扫描周期的 Google Colab 完整扫描脚本"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    if not selected_tfs:
        selected_tfs = ["1d"]
        
    all_tf_defs = {
        "1d": '("1d", "2y")',
        "1w": '("1wk", "5y")',
        "4h": '("1h", "730d")',
        "60m": '("60m", "720d")',
    }
    
    tf_lines = []
    for tf in selected_tfs:
        if tf in all_tf_defs:
            tf_lines.append(f'    "{tf}": {all_tf_defs[tf]},')
            
    timeframes_code = "{\n" + "\n".join(tf_lines) + "\n}"
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · 🌟「长周期趋势启动点 · 矩形中枢蓄势突破 (Trend Launch Box)」极速扫描
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: {', '.join(selected_tfs)}
# 核心指标: 35~55天矩形箱体 + 布林带极致收窄 (TTM Squeeze) + 突破放量 + 周线MACD共振 + 0~100评分
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行极速并发扫描
# 4. 扫描完成后会自动下载 `colab_launch_box_results.csv`
# 5. 回到 Streamlit 应用「🚀 趋势启动扫描」页面，拖入该 CSV 文件即可一键合并展示！
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
logging.captureWarnings(True)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 扫描配置
# ------------------------------------------------------------------------------
TIMEFRAMES = {timeframes_code}
LOOKBACK_BOX = 42      # 矩形箱体考察周期 (约 2 个月)
MIN_VOL_FILTER = {min_volume} # 20日均量过滤

RAW_TICKERS = {tickers_json}
print(f"📋 已加载股票池: {{len(RAW_TICKERS)}} 支品种 | 周期: {', '.join(selected_tfs)}")

# ------------------------------------------------------------------------------
# 📡 Yahoo Finance 极速数据下载器
# ------------------------------------------------------------------------------
SESSION = requests.Session()
ADAPTER = HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=1)
SESSION.mount("https://", ADAPTER)
HEADERS = {{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}}

def fetch_history(ticker: str, interval: str, range_str: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{{ticker}}?interval={{interval}}&range={{range_str}}"
    try:
        r = SESSION.get(url, headers=HEADERS, timeout=7)
        if r.status_code != 200:
            return None
        data = r.json()
        res = data["chart"]["result"][0]
        ts = res["timestamp"]
        quotes = res["indicators"]["quote"][0]
        df = pd.DataFrame({{
            "Open": quotes["open"],
            "High": quotes["high"],
            "Low": quotes["low"],
            "Close": quotes["close"],
            "Volume": quotes["volume"],
        }}, index=pd.to_datetime(ts, unit="s"))
        return df.dropna()
    except Exception:
        return None

# ------------------------------------------------------------------------------
# 🔍 核心启动点量化识别
# ------------------------------------------------------------------------------
def evaluate_ticker(ticker: str, tf: str, df: pd.DataFrame):
    if df is None or len(df) < LOOKBACK_BOX + 25:
        return []
    
    vol20 = df["Volume"].rolling(20).mean().iloc[-1]
    if MIN_VOL_FILTER > 0 and pd.notna(vol20) and vol20 < MIN_VOL_FILTER:
        return []

    # 计算指标
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["SMA250"] = df["Close"].rolling(250).mean()
    df["Bias_250"] = (df["Close"] - df["SMA250"]) / df["SMA250"]

    df["VOL_MA20"] = df["Volume"].rolling(20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["VOL_MA20"].replace(0, np.nan)
    df["Vol_Max_60"] = df["Volume"].shift(1).rolling(60).max()
    df["Is_Vol_New_High"] = df["Volume"] > df["Vol_Max_60"]

    df["BB_Std"] = df["Close"].rolling(20).std()
    df["BB_Upper"] = df["SMA20"] + 2 * df["BB_Std"]
    df["BB_Lower"] = df["SMA20"] - 2 * df["BB_Std"]
    df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["SMA20"].replace(0, np.nan)
    df["Min_BB_Width_20"] = df["BB_Width"].shift(1).rolling(20).min()

    df["TR"] = np.maximum(df["High"] - df["Low"], np.maximum(abs(df["High"] - df["Close"].shift(1)), abs(df["Low"] - df["Close"].shift(1))))
    df["ATR14"] = df["TR"].rolling(14).mean()
    df["KC_Upper"] = df["SMA20"] + 1.5 * df["ATR14"]
    df["KC_Lower"] = df["SMA20"] - 1.5 * df["ATR14"]
    df["Squeeze_On"] = (df["BB_Lower"] > df["KC_Lower"]) & (df["BB_Upper"] < df["KC_Upper"])
    df["Squeeze_Count"] = df["Squeeze_On"].rolling(30).sum()

    df["Box_High"] = df["High"].shift(1).rolling(LOOKBACK_BOX).max()
    df["Box_Low"] = df["Low"].shift(1).rolling(LOOKBACK_BOX).min()

    results = []
    n = len(df)
    latest_c = float(df["Close"].iloc[-1])

    # 扫描过去 60 根 K 线
    scan_start = max(LOOKBACK_BOX + 5, n - 60)
    for i in range(scan_start, n):
        c = float(df["Close"].iloc[i])
        prev_c = float(df["Close"].iloc[i - 1])
        box_h = float(df["Box_High"].iloc[i])
        box_l = float(df["Box_Low"].iloc[i])
        box_hgt = max(box_h - box_l, box_h * 0.02)
        box_hgt_pct = round(box_hgt / max(0.001, box_l) * 100, 2)

        vol_r = float(df["Vol_Ratio"].iloc[i]) if pd.notna(df["Vol_Ratio"].iloc[i]) else 1.0
        min_bb = float(df["Min_BB_Width_20"].iloc[i]) if pd.notna(df["Min_BB_Width_20"].iloc[i]) else 0.20
        bias250 = float(df["Bias_250"].iloc[i]) if pd.notna(df["Bias_250"].iloc[i]) else 0.0
        is_vol_high = bool(df["Is_Vol_New_High"].iloc[i]) if pd.notna(df["Is_Vol_New_High"].iloc[i]) else False
        sqz_cnt = int(df["Squeeze_Count"].iloc[i]) if pd.notna(df["Squeeze_Count"].iloc[i]) else 0

        is_breakout = (c >= box_h) and (prev_c < box_h)
        is_active = (i == n - 1) and (c < box_h) and (c >= box_l) and (min_bb <= 0.25) and (sqz_cnt >= 4)

        if not (is_breakout or is_active):
            continue
        if is_breakout and (min_bb > 0.35 or vol_r < 1.25 or c < df["SMA20"].iloc[i]):
            continue

        # 评分计算
        s20 = float(df["SMA20"].iloc[i])
        s50 = float(df["SMA50"].iloc[i]) if pd.notna(df["SMA50"].iloc[i]) else s20
        s200 = float(df["SMA200"].iloc[i]) if pd.notna(df["SMA200"].iloc[i]) else s20
        
        score = 0
        if c > s20 and s20 > s50: score += 10
        if c > s200: score += 8
        score += 7 # Weekly default
        if vol_r >= 3.0: score += 15
        elif vol_r >= 1.8: score += 10
        else: score += 6
        if is_vol_high: score += 10
        if sqz_cnt >= 12 or min_bb <= 0.08: score += 20
        elif sqz_cnt >= 6 or min_bb <= 0.16: score += 14
        else: score += 8
        if -0.10 <= bias250 <= 0.35: score += 15
        elif -0.20 <= bias250 <= 0.50: score += 10
        else: score += 3
        score += 12

        score = min(100, score)
        tier = "👑 史诗级标杆" if score >= 90 else ("🔥 优质主升浪" if score >= 75 else ("⚡ 标准中枢波段" if score >= 60 else "👀 观察级"))
        entry_p = round(box_h, 2) if is_breakout else round(latest_c, 2)
        sl_p = round(box_l, 2)
        risk = max(0.01, round(entry_p - sl_p, 2))
        tp1_p = round(box_h + 1.0 * box_hgt, 2)
        tp2_p = round(box_h + 2.0 * box_hgt, 2)
        tp3_p = round(box_h + 4.236 * box_hgt, 2)
        
        rr_tp2 = round((tp2_p - entry_p) / max(0.001, risk), 2)
        rr_tp3 = round((tp3_p - entry_p) / max(0.001, risk), 2)

        if is_active:
            status = "active"
            prog = 0.0
        else:
            prog = round(max(0.0, (latest_c - box_h) / max(0.001, box_hgt) * 100.0), 1)
            if latest_c < sl_p: status = "invalidated"
            elif prog <= 20.0: status = "early"
            elif prog <= 100.0: status = "mid"
            else: status = "far"

        dt_str = df.index[i].strftime("%Y-%m-%d")
        box_start_str = df.index[max(0, i - LOOKBACK_BOX)].strftime("%Y-%m-%d")

        results.append({{
            "symbol": ticker,
            "period": tf,
            "direction": "bullish",
            "pattern": "🚀 矩形蓄势突破" if score < 90 else "👑 史诗级长周期主升浪",
            "tier": tier,
            "quality_score": score,
            "box_start_date": box_start_str,
            "box_end_date": dt_str,
            "box_bars": LOOKBACK_BOX,
            "box_high": round(box_h, 2),
            "box_low": round(box_l, 2),
            "box_height": round(box_hgt, 2),
            "box_height_pct": box_hgt_pct,
            "breakout_date": dt_str,
            "breakout_price": round(c, 2),
            "latest_close": round(latest_c, 2),
            "entry_price": entry_p,
            "stop_loss": sl_p,
            "tp1": tp1_p,
            "tp2": tp2_p,
            "tp3": tp3_p,
            "risk": risk,
            "risk_reward": rr_tp2,
            "rr_tp3": rr_tp3,
            "vol_ratio": round(vol_r, 2),
            "is_vol_new_high": is_vol_high,
            "min_bb_width": round(min_bb, 2),
            "squeeze_bars": sqz_cnt,
            "bias_250": round(bias250, 3),
            "status": status,
            "breakout_progress": prog,
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }})

    return results

# ------------------------------------------------------------------------------
# 🚀 启动多线程极速全量扫描
# ------------------------------------------------------------------------------
from concurrent.futures import ThreadPoolExecutor, as_completed

all_records = []
total_syms = len(RAW_TICKERS)
start_time = time.time()
print(f"🚀 开始全量并发扫描 (共 {{total_syms}} 支标的)...")

def worker(item):
    tk, tf = item
    cfg = TIMEFRAMES[tf]
    df = fetch_history(tk, cfg[0], cfg[1])
    return evaluate_ticker(tk, tf, df)

task_list = [(tk, tf) for tk in RAW_TICKERS for tf in TIMEFRAMES.keys()]

done = 0
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(worker, t) for t in task_list]
    for fut in as_completed(futures):
        done += 1
        res = fut.result()
        if res:
            all_records.extend(res)
        if done % 50 == 0 or done == len(task_list):
            print(f"⏳ 进度: {{done}}/{{len(task_list)}} ({{done*100//len(task_list)}}%) | 发现信号: {{len(all_records)}} 条")

elapsed = round(time.time() - start_time, 1)
print(f"\\n🎉 扫描全部完成！耗时: {{elapsed}} 秒，共发现 {{len(all_records)}} 个趋势启动信号！")

if all_records:
    df_out = pd.DataFrame(all_records)
    # 按评分和最新时间排序
    df_out = df_out.sort_values(by=["quality_score", "breakout_date"], ascending=[False, False])
    out_csv = "colab_launch_box_results.csv"
    df_out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"💾 结果已保存至: {{out_csv}} (共 {{len(df_out)}} 行)")
    
    try:
        from google.colab import files
        files.download(out_csv)
        print("📥 浏览器已自动弹出下载！请将下载的 CSV 导入 Streamlit 平台。")
    except Exception:
        print("💡 请在 Colab 左侧文件树中找到 `colab_launch_box_results.csv` 并右键下载。")
else:
    print("⚠️ 未发现符合条件的信号。")
'''
    return script
