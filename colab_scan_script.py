"""
colab_scan_script.py — Google Colab 独立大规模三重底扫描脚本生成器
=====================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整脚本。
包含：
  1. yfinance 批量下载
  2. Al Brooks 三重底 7 种形态识别算法
  3. 预设股票池 (直接从系统品种库/分组中提取)
  4. 多周期扫描 (日线 1d, 4小时 4h, 周线 1w 等)
  5. 自动导出与下载 CSV 文件，与主平台格式 100% 兼容
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
    }
    
    tf_lines = []
    for tf in selected_tfs:
        if tf in all_tf_defs:
            tf_lines.append(f'    "{tf}": {all_tf_defs[tf]},')
            
    timeframes_code = "{\n" + "\n".join(tf_lines) + "\n}"
    
    script = f'''# ==============================================================================
# 🚀 Google Colab 三重底 (Triple Bottom) 大规模扫描脚本
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: {', '.join(selected_tfs)}
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行极速扫描
# 4. 扫描完成后会自动下载 `colab_triple_bottom_results.csv`
# 5. 回到 Streamlit 应用页面，拖入该 CSV 文件即可一键合并展示！
# ==============================================================================

# 1. 安装所需依赖
!pip install -q yfinance pandas numpy

import os
import time
import json
from datetime import datetime
from dataclasses import dataclass
import pandas as pd
import numpy as np
import yfinance as yf

# ------------------------------------------------------------------------------
# ⚙️ 扫描配置
# ------------------------------------------------------------------------------
# 扫描周期配置 (已选: {', '.join(selected_tfs)})
TIMEFRAMES = {timeframes_code}

# 形态识别参数 (与 Streamlit 系统完全对齐)
SWING_WINDOW = 3      # 分形左右窗口大小
LOOKBACK_BARS = 150   # 回溯 K 线根数
MAX_SPACING = 80      # 三个低点最大间距
MIN_SPACING = 3       # 三个低点最小间距
MIN_CONFIDENCE = 0.5  # 最小置信度阈值
FLAT_TOL = 0.02       # 底部持平容差 (2%)
BREAK_TOL = 0.01      # 跌破容差 (1%)

# 📊 从系统内置品种库中提取的股票池代码列表 (无需重复拉取)
SCAN_TICKERS = {tickers_json}


# ------------------------------------------------------------------------------
# 🧠 三重底识别算法核心 (基于 Al Brooks 价格行为学)
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

def classify_triple(low1, low2, low3, mid_high_12, mid_high_23, broke_support_23, flat_tol=0.02):
    d12 = _pct_diff(low1, low2)
    d23 = _pct_diff(low2, low3)
    d13 = _pct_diff(low1, low3)

    descending = (low1 > low2 > low3) or (low1 >= low2 * (1 - flat_tol) and low2 > low3)
    ascending = (low1 < low2 < low3)
    flat_all = d12 <= flat_tol and d23 <= flat_tol

    if flat_all:
        return "完美三重底 (Perfect Triple Bottom)", 0.9, f"三低点差异 {{max(d12, d23):.2%}}，接近持平"

    if low2 < low1 and low2 < low3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(low1, low3)
        conf = 0.85 if shoulder_diff < 0.02 else 0.65
        return "头肩底/截断楔形 (Head & Shoulders Bottom)", conf, f"中间低点更低(头部)，两肩差异 {{shoulder_diff:.2%}}"

    if ascending and broke_support_23:
        return "抬高双底失败突破型 (Failed BO below HL DB)", 0.8, "低点逐级抬高(HL)，且第3次出现跌破支撑后被拉回"

    if broke_support_23:
        if d23 <= flat_tol * 3:
            return "双底回调型 (Double Bottom Pullback)", 0.75, "双底确立后价格回踩，第3低点贴近前低"
        else:
            return "双底跌破失败型 (Failed BO below DB)", 0.75, "价格短暂跌破前低支撑但迅速拉回"

    if descending and not flat_all:
        return "楔形三重底 (Wedge)", 0.7, f"低点依次降低 low1>{{low1:.4f}} > low2>{{low2:.4f}} > low3>{{low3:.4f}}"

    if ascending and mid_high_12 > mid_high_23:
        return "三角形三重底 (Triangle)", 0.65, "低点抬高，同时中间高点走低，形成收敛三角形"

    return "未分类三次探底 (Unclassified 3-push)", 0.4, "满足三次探低但未匹配到具体子形态，建议人工复核"

def scan_triple_bottoms(df, symbol="", swing_window=3, lookback_bars=150, max_spacing=80, min_spacing=3, break_tol=0.01, flat_tol=0.02):
    if len(df) < swing_window * 2 + 10:
        return []

    df_sw = find_swing_points(df, window=swing_window)
    df_recent = df_sw.iloc[-lookback_bars:].copy()
    offset = len(df_sw) - len(df_recent)

    swing_low_indices = df_recent.index[df_recent["is_swing_low"]].tolist()
    if len(swing_low_indices) < 3:
        return []

    results = []
    n_lows = len(swing_low_indices)

    for i in range(n_lows - 2):
        for j in range(i + 1, n_lows - 1):
            for k in range(j + 1, n_lows):
                idx1_loc = swing_low_indices[i]
                idx2_loc = swing_low_indices[j]
                idx3_loc = swing_low_indices[k]

                pos1 = df_recent.index.get_loc(idx1_loc)
                pos2 = df_recent.index.get_loc(idx2_loc)
                pos3 = df_recent.index.get_loc(idx3_loc)

                sp12 = pos2 - pos1
                sp23 = pos3 - pos2
                total_sp = pos3 - pos1

                if not (min_spacing <= sp12 <= max_spacing and min_spacing <= sp23 <= max_spacing and total_sp <= max_spacing * 2):
                    continue

                low1 = df_recent.loc[idx1_loc, "low"]
                low2 = df_recent.loc[idx2_loc, "low"]
                low3 = df_recent.loc[idx3_loc, "low"]

                mid_high_12 = df_recent.iloc[pos1:pos2 + 1]["high"].max()
                mid_high_23 = df_recent.iloc[pos2:pos3 + 1]["high"].max()
                mid_high = max(mid_high_12, mid_high_23)

                support_level = min(low1, low2)
                broke_support = (low3 < support_level * (1 - break_tol)) and (low3 >= support_level * 0.90)

                pattern_name, confidence, note = classify_triple(
                    low1, low2, low3, mid_high_12, mid_high_23, broke_support, flat_tol=flat_tol
                )

                global_pos3 = offset + pos3
                bars_since_low3 = len(df_sw) - 1 - global_pos3
                latest_close = float(df_sw.iloc[-1]["close"])

                results.append({{
                    "symbol": symbol,
                    "pattern": pattern_name,
                    "confidence": round(float(confidence), 4),
                    "idx1": int(offset + pos1),
                    "idx2": int(offset + pos2),
                    "idx3": int(offset + pos3),
                    "low1": round(float(low1), 4),
                    "low2": round(float(low2), 4),
                    "low3": round(float(low3), 4),
                    "mid_high": round(float(mid_high), 4),
                    "note": note,
                    "status": "active",
                    "status_reason": "",
                    "bars_since_low3": int(bars_since_low3),
                    "latest_close": round(latest_close, 4),
                }})
    return results


# ------------------------------------------------------------------------------
# 🚀 批量多周期扫描主程序
# ------------------------------------------------------------------------------
def run_scanner():
    tickers = SCAN_TICKERS
    all_results = []
    
    total_tickers = len(tickers)
    print(f"\\n🚀 开始执行扫描任务 (共 {{total_tickers}} 只股票, 周期: {{list(TIMEFRAMES.keys())}})...\\n")
    
    start_time = time.time()
    for idx, ticker in enumerate(tickers, 1):
        if idx % 10 == 0 or idx == total_tickers:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 1
            rem = (total_tickers - idx) / rate
            print(f"[{{idx}}/{{total_tickers}}] 正在扫描: {{ticker}} (已发现 {{len(all_results)}} 个形态, 预计剩余 {{int(rem//60)}}分{{int(rem%60)}}秒)")
            
        for period_key, (yf_interval, yf_period) in TIMEFRAMES.items():
            try:
                # yfinance 下载
                df = yf.download(ticker, interval=yf_interval, period=yf_period, progress=False)
                if df is None or df.empty:
                    continue
                
                # 多级索引展平
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                
                if not all(k in df.columns for k in ["close", "high", "low"]):
                    continue
                    
                matches = scan_triple_bottoms(
                    df,
                    symbol=ticker,
                    swing_window=SWING_WINDOW,
                    lookback_bars=LOOKBACK_BARS,
                    max_spacing=MAX_SPACING,
                    flat_tol=FLAT_TOL,
                    break_tol=BREAK_TOL,
                )
                
                for m in matches:
                    if m["confidence"] >= MIN_CONFIDENCE:
                        m["period"] = period_key
                        m["scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        all_results.append(m)
            except Exception as e:
                pass
                
    # 汇总并输出
    print(f"\\n🎉 扫描完成！共耗时 {{int((time.time()-start_time)//60)}} 分钟，匹配到 {{len(all_results)}} 条三重底形态！")
    
    if all_results:
        out_df = pd.DataFrame(all_results)
        cols = [
            "symbol", "period", "pattern", "confidence", "idx1", "idx2", "idx3",
            "low1", "low2", "low3", "mid_high", "note", "status", "status_reason",
            "bars_since_low3", "latest_close", "scan_time"
        ]
        out_df = out_df[[c for c in cols if c in out_df.columns]]
        
        csv_filename = "colab_triple_bottom_results.csv"
        out_df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
        print(f"💾 结果已保存至: {{csv_filename}}")
        
        # 尝试自动触发浏览器下载
        try:
            from google.colab import files
            print("⬇️ 正在触发自动下载到本地...")
            files.download(csv_filename)
        except Exception:
            print(f"💡 可在 Colab 左侧文件树中右键下载 `{{csv_filename}}`")
    else:
        print("⚠️ 未发现符合条件的三重底形态。")

# 执行主程序
if __name__ == "__main__":
    run_scanner()
'''
    return script
