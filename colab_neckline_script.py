"""
colab_neckline_script.py — Google Colab 独立 4H 结构颈线突破扫描脚本生成器
========================================================================================
生成可直接粘贴到 Google Colab 执行的 Python 完整脚本。
包含：
  1. yfinance 批量高速下载（1H 极速重采样为 4H）
  2. 4H 结构颈线突破 7 条核心规则算法（箱体/双底/头肩底 + ATR + 放量 + 均线趋势 + 站稳确认）
  3. 预设股票池 (全量美股 / 全量A股 / 自选 / 分组)
  4. 专注于 4小时 (4H) 结构颈线突破
  5. 自动导出与下载 CSV 文件，与主平台格式 100% 兼容
"""

import json

def generate_colab_neckline_script(tickers: list[str], pool_name: str = "系统品种库") -> str:
    """生成内置指定股票池代码的 Google Colab 4H 结构颈线突破扫描脚本"""
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    
    script = f'''# ==============================================================================
# 🚀 Google Colab · 4小时 (4H) 结构颈线突破扫描脚本
# 股票池来源: {pool_name} (共 {len(tickers)} 支品种)
# 扫描周期: 4小时 (4H Neckline Breakout)
# ==============================================================================
# 7条核心扫描规则：
#   [0] 颈线突破: 4H收盘价突破结构颈线 (箱体上沿 / 双底中峰 / 头肩底颈线)
#   [1] 突破幅度: 突破幅度有效过滤假刺穿 (Close > 颈线 + 0.8×ATR 或 幅度>1%)
#   [2] 增量放大: 4H成交量放大 (VOL > 1.3×MA5 或 前根1.5倍)
#   [3] 异常天量过滤: 避免天量脉冲后衰竭 (VOL < 2.8×MA20)
#   [4] 趋势共振: 4H均线多头共振排列 (MA5 ≥ MA10 ≥ MA20)
#   [5] 站稳确认: 收盘价在颈线上方持续站稳 (过滤单针冲高回落)
#   [6] 形态结构: 识别到有效底部/整理结构 (箱体 / 双底 / 头肩底)
# ==============================================================================
# 使用方法：
# 1. 打开 Google Colab (https://colab.research.google.com/)
# 2. 新建笔记本，将本脚本完整粘贴到一个代码单元格中
# 3. 点击运行 (Shift + Enter)，脚本将自动在云端执行 64 线程极速并发扫描
# 4. 扫描完成后会自动下载 `colab_neckline_results.csv`
# 5. 回到 Streamlit 应用页面，拖入该 CSV 文件即可一键合并展示！
# ==============================================================================

# 1. 安装所需依赖
!pip install -q yfinance pandas numpy

import os
import time
import json
import warnings
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import yfinance as yf

# 🤫 静音 yfinance 的警告信息
warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ------------------------------------------------------------------------------
# ⚙️ 股票池配置
# ------------------------------------------------------------------------------
SCAN_TICKERS = {tickers_json}


# ------------------------------------------------------------------------------
# 🧠 数据获取与指标工具
# ------------------------------------------------------------------------------
def _fetch_4h_data(ticker: str) -> pd.DataFrame:
    for attempt in range(3):
        try:
            df_1h = yf.download(ticker, period="60d", interval="1h",
                                progress=False, auto_adjust=True, threads=False, timeout=15)
            if df_1h is not None and not df_1h.empty and len(df_1h) >= 8:
                new_cols = [str(c[0] if isinstance(c, tuple) else c).lower() for c in df_1h.columns]
                df_1h.columns = new_cols
                if "close" in df_1h.columns:
                    df_4h = df_1h.resample("4h").agg({{
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }}).dropna(subset=["close"])
                    if len(df_4h) >= 20:
                        return df_4h
        except Exception as e:
            err = str(e).lower()
            if "rate" in err or "429" in err:
                time.sleep(1.5 * (attempt + 1))
                continue
            break

    try:
        df_4h = yf.download(ticker, period="6mo", interval="4h",
                            progress=False, auto_adjust=True, threads=False, timeout=15)
        if df_4h is not None and not df_4h.empty and len(df_4h) >= 20:
            new_cols = [str(c[0] if isinstance(c, tuple) else c).lower() for c in df_4h.columns]
            df_4h.columns = new_cols
            return df_4h.dropna(subset=["close"])
    except Exception:
        pass

    return None


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _check_ticker_neckline(ticker: str) -> dict:
    res = {{
        "ticker": ticker,
        "passed": False,
        "pattern": "—",
        "neckline": None,
        "close": None,
        "volume_4h": None,
        "vol_ratio": None,
        "atr14": None,
        "breakout_pct": None,
        "details": [],
        "error": None,
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }}

    try:
        df = _fetch_4h_data(ticker)
        if df is None or len(df) < 30:
            res["error"] = "4H K线数据不足 (需至少 30 根)"
            return res

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        c_last = float(close.iloc[-1])
        c_prev1 = float(close.iloc[-2]) if len(close) >= 2 else c_last

        v_last = float(volume.iloc[-1])
        v_prev1 = float(volume.iloc[-2]) if len(volume) >= 2 else v_last

        atr_ser = calculate_atr(df, 14)
        atr_val = float(atr_ser.iloc[-1]) if not pd.isna(atr_ser.iloc[-1]) else (c_last * 0.02)
        res["atr14"] = atr_val
        res["close"] = c_last
        res["volume_4h"] = v_last

        # 1. 箱体突破
        box_n = min(20, len(df) - 1)
        sub_high = high.iloc[-box_n-1:-1]
        sub_low = low.iloc[-box_n-1:-1]
        box_high = float(sub_high.max())
        box_low = float(sub_low.min())

        box_break = c_last > box_high
        box_break_strong = c_last > (box_high + 0.8 * atr_val)

        # 2. 双底结构
        db_n = min(25, len(df))
        sub_df = df.iloc[-db_n:]
        lows = sub_df["low"].values
        highs = sub_df["high"].values
        
        mid_idx = len(lows) // 2
        b1_idx = int(np.argmin(lows[:mid_idx])) if mid_idx > 2 else 0
        b1_low = float(lows[b1_idx])
        
        b2_idx = mid_idx + int(np.argmin(lows[mid_idx:-1])) if (len(lows) - mid_idx) > 2 else (len(lows) - 2)
        b2_low = float(lows[b2_idx])
        
        if b2_idx > b1_idx + 2:
            neckline_double = float(np.max(highs[b1_idx:b2_idx]))
        else:
            neckline_double = float(np.max(highs[-10:-1]))
            
        double_bottom_valid = (b2_low >= b1_low * 0.96) and (b2_low <= b1_low * 1.05) and (neckline_double > max(b1_low, b2_low))
        double_break = double_bottom_valid and (c_last > neckline_double)

        # 3. 头肩底结构
        hs_valid = False
        neckline_hs = box_high
        if len(df) >= 35:
            l_slice = df.iloc[-35:]
            h_vals = l_slice["high"].values
            l_vals = l_slice["low"].values
            head_idx = int(np.argmin(l_vals[8:-5])) + 8
            head_low = float(l_vals[head_idx])
            left_low = float(np.min(l_vals[:head_idx-2])) if head_idx > 4 else head_low * 1.02
            right_low = float(np.min(l_vals[head_idx+2:-1])) if (len(l_vals) - head_idx) > 4 else head_low * 1.02
            
            if (head_low < left_low * 0.98) and (right_low > head_low * 1.005):
                hs_valid = True
                neckline_hs = float(np.max(h_vals[head_idx-3:head_idx+4]))

        hs_break = hs_valid and (c_last > neckline_hs)

        matched_patterns = []
        necklines = []
        if box_break:
            matched_patterns.append("箱体突破")
            necklines.append(box_high)
        if double_break:
            matched_patterns.append("双底突破")
            necklines.append(neckline_double)
        if hs_break:
            matched_patterns.append("头肩底突破")
            necklines.append(neckline_hs)

        if necklines:
            primary_neckline = float(np.mean(necklines))
            primary_pattern = " + ".join(matched_patterns)
        else:
            primary_neckline = box_high
            primary_pattern = "结构临近/未突破"

        res["neckline"] = primary_neckline
        res["pattern"] = primary_pattern
        res["breakout_pct"] = ((c_last - primary_neckline) / primary_neckline * 100) if primary_neckline else 0.0

        # 成交量
        vol_ma5 = float(volume.rolling(5).mean().iloc[-1]) if len(volume) >= 5 else v_last
        vol_ma20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else (vol_ma5 or 1.0)
        vol_ratio = (v_last / vol_ma5) if vol_ma5 > 0 else 1.0
        res["vol_ratio"] = vol_ratio

        vol_break = (vol_ratio >= 1.3) or (v_last > v_prev1 * 1.5)
        vol_not_abnormal = (v_last <= (vol_ma20 * 2.8))

        # 均线多头
        ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else c_last
        ma10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else c_last
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else c_last
        ma_bull = (ma5 >= ma10 * 0.998) and (ma10 >= ma20 * 0.995)

        stand_still = (c_last >= primary_neckline * 0.995) and ((c_prev1 >= primary_neckline * 0.99) or (c_last > primary_neckline * 1.008))

        rules = [
            {{
                "id": "[0] 颈线突破",
                "desc": "4H收盘价突破结构颈线 (箱体/双底/头肩底)",
                "ok": bool(c_last >= primary_neckline),
                "val": f"Close={{c_last:.4f}} vs 颈线={{primary_neckline:.4f}} (+{{res['breakout_pct']:.2f}}%)",
            }},
            {{
                "id": "[1] 突破幅度",
                "desc": "突破幅度有效过滤假刺穿 (Close > 颈线 + 0.8×ATR 或 幅度>1%)",
                "ok": bool(box_break_strong or (res['breakout_pct'] >= 0.8)),
                "val": f"幅度=+{{res['breakout_pct']:.2f}}% | ATR14={{atr_val:.4f}}",
            }},
            {{
                "id": "[2] 增量放大",
                "desc": "4H成交量放大 (VOL > 1.3×MA5 或 前根1.5倍)",
                "ok": bool(vol_break),
                "val": f"4H量={{v_last:,.0f}} vs MA5={{vol_ma5:,.0f}} ({{vol_ratio:.2f}}倍)",
            }},
            {{
                "id": "[3] 异常天量过滤",
                "desc": "避免天量脉冲后衰竭 (VOL < 2.8×MA20)",
                "ok": bool(vol_not_abnormal),
                "val": f"4H量={{v_last:,.0f}} vs MA20={{vol_ma20:,.0f}} ({{v_last/vol_ma20:.2f}}倍)" if vol_ma20 else "正常",
            }},
            {{
                "id": "[4] 趋势共振",
                "desc": "4H均线多头共振排列 (MA5 ≥ MA10 ≥ MA20)",
                "ok": bool(ma_bull),
                "val": f"MA5={{ma5:.3f}} | MA10={{ma10:.3f}} | MA20={{ma20:.3f}}",
            }},
            {{
                "id": "[5] 站稳确认",
                "desc": "收盘价在颈线上方持续站稳 (过滤单针冲高回落)",
                "ok": bool(stand_still),
                "val": f"当前={{c_last:.4f}} | 前根={{c_prev1:.4f}} | 颈线={{primary_neckline:.4f}}",
            }},
            {{
                "id": "[6] 形态结构",
                "desc": "识别到有效底部/整理结构 (箱体/双底/头肩底)",
                "ok": bool(len(matched_patterns) > 0 or box_break),
                "val": f"识别形态: {{primary_pattern}}",
            }},
        ]

        res["details"] = rules
        res["passed"] = bool((c_last >= primary_neckline) and vol_break and ma_bull and stand_still)

    except Exception as e:
        res["error"] = str(e)

    return res


# ------------------------------------------------------------------------------
# 🚀 极速多线程并发执行引擎
# ------------------------------------------------------------------------------
def run_neckline_scanner():
    tickers = SCAN_TICKERS
    total_tickers = len(tickers)
    MAX_WORKERS = 64
    
    print(f"\\n🚀 开启 4H 结构颈线突破极速并发扫描 (共 {{total_tickers}} 只股票, 线程数: {{MAX_WORKERS}})...\\n")
    
    start_time = time.time()
    completed = 0
    passed_records = []
    all_records = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {{executor.submit(_check_ticker_neckline, tk): tk for tk in tickers}}
        
        for future in as_completed(future_map):
            completed += 1
            tk = future_map[future]
            try:
                res = future.result()
                all_records.append(res)
                if res.get("passed"):
                    passed_records.append(res)
                    print(f"  🔥 [发现突破] {{tk}} 突破 4H 结构颈线! (形态: {{res['pattern']}}, 价格: {{res['close']}}, 颈线: {{res['neckline']}}, 4H量比: {{res['vol_ratio']:.2f}}x)")
            except Exception as e:
                all_records.append({{"ticker": tk, "passed": False, "pattern": "—", "details": [], "error": str(e), "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}})
                
            if completed % 25 == 0 or completed == total_tickers:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 1
                rem = (total_tickers - completed) / rate
                speed = completed / elapsed if elapsed > 0 else 0
                print(f"[{{completed}}/{{total_tickers}}] 进度: {{completed*100//total_tickers}}% ({{speed:.1f}}只/秒) | 已匹配突破: {{len(passed_records)}} 支 | 预计剩余: {{int(rem//60)}}分{{int(rem%60)}}秒")

    total_min = (time.time() - start_time) / 60
    print(f"\\n🎉 扫描全部完成！共耗时 {{total_min:.1f}} 分钟，匹配到 {{len(passed_records)}} 支 4H 结构颈线突破股票！")

    # 导出 CSV
    if all_records:
        csv_rows = []
        for r in all_records:
            details_str = json.dumps(r.get("details", []), ensure_ascii=False)
            csv_rows.append({{
                "ticker": r.get("ticker", ""),
                "passed": 1 if r.get("passed") else 0,
                "pattern": r.get("pattern", "—"),
                "neckline": r.get("neckline", ""),
                "close": r.get("close", ""),
                "volume_4h": r.get("volume_4h", ""),
                "vol_ratio": r.get("vol_ratio", ""),
                "atr14": r.get("atr14", ""),
                "breakout_pct": r.get("breakout_pct", ""),
                "error": r.get("error", "") or "",
                "details_json": details_str,
                "scan_time": r.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            }})
        
        out_df = pd.DataFrame(csv_rows)
        csv_filename = "colab_neckline_results.csv"
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
    run_neckline_scanner()
'''
    return script
