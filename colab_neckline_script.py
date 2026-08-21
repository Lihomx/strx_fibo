"""
colab_neckline_script.py — Google Colab 独立 4H 结构颈线突破扫描脚本生成器
========================================================================================
严格对齐 6 条突破确认核心条件：
  1. 价格突破: CLOSE > NECKLINE 或 HIGH > NECKLINE (判断价格是否跨过颈线)
  2. 突破幅度: CLOSE > NECKLINE * 1.01 或 CLOSE > NECKLINE + 1.2 * ATR (过滤盘中假刺穿)
  3. 成交量放大: VOL > MA(VOL,5) * 1.3 或 VOL > REF(HHV(VOL,2),1) (确认增量资金进场)
  4. 站稳天数: 连续3根四小时K线收盘价在颈线上方 (避免单日冲高回落)
  5. 均线趋势: MA5 > MA10 且 MA10 > MA20 (确认趋势方向一致)
  6. 波动率过滤: 突破幅度 (CLOSE - NECKLINE) >= 1.2 * ATR(14) (排除低波动假突破)
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
# 6 条突破确认核心条件（全部满足）：
#   [1] 价格突破: CLOSE > NECKLINE 或 HIGH > NECKLINE
#   [2] 突破幅度: CLOSE > NECKLINE * 1.01 或 CLOSE > NECKLINE + 1.2 * ATR
#   [3] 成交量放大: VOL > MA(VOL,5) * 1.3 或 VOL > REF(HHV(VOL,2),1)
#   [4] 站稳天数: 连续3根四小时K线收盘价在颈线上方
#   [5] 均线趋势: MA5 > MA10 且 MA10 > MA20
#   [6] 波动率过滤: 突破幅度 (CLOSE - NECKLINE) >= 1.2 * ATR(14)
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
        if df is None or len(df) < 25:
            res["error"] = "4H K线数据不足 (需至少 25 根)"
            return res

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        c_last = float(close.iloc[-1])
        c_prev1 = float(close.iloc[-2]) if len(close) >= 2 else c_last
        c_prev2 = float(close.iloc[-3]) if len(close) >= 3 else c_prev1

        h_last = float(high.iloc[-1])
        v_last = float(volume.iloc[-1])
        v_prev1 = float(volume.iloc[-2]) if len(volume) >= 2 else v_last
        v_prev2 = float(volume.iloc[-3]) if len(volume) >= 3 else v_prev1

        # 计算 ATR(14)
        atr_ser = calculate_atr(df, 14)
        atr_val = float(atr_ser.iloc[-1]) if not pd.isna(atr_ser.iloc[-1]) else (c_last * 0.02)
        res["atr14"] = atr_val
        res["close"] = c_last
        res["volume_4h"] = v_last

        # 1. 结构识别与确定颈线位 NECKLINE
        box_n = min(20, len(df) - 1)
        sub_high = high.iloc[-box_n-1:-1]
        box_high = float(sub_high.max())

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

        is_box = c_last >= box_high * 0.99
        is_double = (b2_low >= b1_low * 0.96) and (b2_low <= b1_low * 1.05) and (c_last >= neckline_double * 0.99)
        
        patterns = []
        necklines = []
        if is_box:
            patterns.append("箱体突破")
            necklines.append(box_high)
        if is_double:
            patterns.append("双底突破")
            necklines.append(neckline_double)
            
        if not necklines:
            primary_neckline = box_high
            primary_pattern = "箱体/前高结构"
        else:
            primary_neckline = float(np.mean(necklines))
            primary_pattern = " + ".join(patterns)

        res["neckline"] = primary_neckline
        res["pattern"] = primary_pattern
        breakout_amount = c_last - primary_neckline
        res["breakout_pct"] = ((breakout_amount) / primary_neckline * 100) if primary_neckline else 0.0

        # 2. 突破确认的 6 条源码条件

        # [0] 价格突破
        ok0_price_break = bool((c_last > primary_neckline) or (h_last > primary_neckline))
        val0 = f"Close={{c_last:.4f}}, High={{h_last:.4f}} vs 颈线={{primary_neckline:.4f}}"

        # [1] 突破幅度
        target_margin_pct = primary_neckline * 1.01
        target_margin_atr = primary_neckline + 1.2 * atr_val
        ok1_amount_break = bool((c_last > target_margin_pct) or (c_last > target_margin_atr))
        val1 = f"Close={{c_last:.4f}} vs 1.01倍={{target_margin_pct:.4f}} / +1.2ATR={{target_margin_atr:.4f}}"

        # [2] 成交量放大
        vol_ma5 = float(volume.rolling(5).mean().iloc[-1]) if len(volume) >= 5 else v_last
        vol_ratio = (v_last / vol_ma5) if vol_ma5 > 0 else 1.0
        res["vol_ratio"] = vol_ratio
        max_prev2_vol = max(v_prev1, v_prev2)
        ok2_vol_break = bool((v_last > vol_ma5 * 1.3) or (v_last > max_prev2_vol))
        val2 = f"4H量={{v_last:,.0f}} vs 1.3×MA5={{vol_ma5*1.3:,.0f}} ({{vol_ratio:.2f}}倍) / 前2根最大={{max_prev2_vol:,.0f}}"

        # [3] 站稳天数
        if len(close) >= 3:
            recent_3_closes = close.iloc[-3:].values
            ok3_stand_still = bool(all(float(c) > primary_neckline * 0.998 for c in recent_3_closes))
            val3 = f"近3根4H: [{{float(recent_3_closes[0]):.2f}}, {{float(recent_3_closes[1]):.2f}}, {{float(recent_3_closes[2]):.2f}}] > 颈线 {{primary_neckline:.2f}}"
        else:
            ok3_stand_still = bool(c_last > primary_neckline)
            val3 = f"Close={{c_last:.4f}} > 颈线 {{primary_neckline:.4f}}"

        # [4] 均线趋势
        ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else c_last
        ma10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else c_last
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else c_last
        ok4_ma_trend = bool((ma5 > ma10) and (ma10 > ma20))
        val4 = f"MA5={{ma5:.3f}} > MA10={{ma10:.3f}} > MA20={{ma20:.3f}}"

        # [5] 波动率过滤
        atr_req = 1.2 * atr_val
        ok5_volatility = bool(breakout_amount >= atr_req)
        val5 = f"突破幅度={{breakout_amount:.4f}} (+{{res['breakout_pct']:.2f}}%) vs 1.2×ATR={{atr_req:.4f}}"

        rules = [
            {{
                "id": "价格突破",
                "desc": "CLOSE > NECKLINE 或 HIGH > NECKLINE",
                "purpose": "判断价格是否跨过颈线",
                "ok": ok0_price_break,
                "val": val0,
            }},
            {{
                "id": "突破幅度",
                "desc": "CLOSE > NECKLINE * 1.01 或 CLOSE > NECKLINE + 1.2 * ATR",
                "purpose": "过滤盘中假刺穿",
                "ok": ok1_amount_break,
                "val": val1,
            }},
            {{
                "id": "成交量放大",
                "desc": "VOL > MA(VOL,5) * 1.3 或 VOL > REF(HHV(VOL,2),1)",
                "purpose": "确认增量资金进场",
                "ok": ok2_vol_break,
                "val": val2,
            }},
            {{
                "id": "站稳天数",
                "desc": "连续3根四小时K线收盘价在颈线上方",
                "purpose": "避免单日冲高回落",
                "ok": ok3_stand_still,
                "val": val3,
            }},
            {{
                "id": "均线趋势",
                "desc": "MA5 > MA10，MA10 > MA20",
                "purpose": "确认趋势方向一致",
                "ok": ok4_ma_trend,
                "val": val4,
            }},
            {{
                "id": "波动率过滤",
                "desc": "突破幅度 ≥ 1.2 * ATR(14)",
                "purpose": "排除低波动假突破",
                "ok": ok5_volatility,
                "val": val5,
            }},
        ]

        res["details"] = rules
        res["passed"] = bool(ok0_price_break and ok1_amount_break and ok2_vol_break and ok3_stand_still and ok4_ma_trend and ok5_volatility)

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
                    print(f"  🔥 [发现突破] {{tk}} 满足 6 条 4H 结构突破确认条件! (形态: {{res['pattern']}}, 价格: {{res['close']}}, 颈线: {{res['neckline']}}, 4H量比: {{res['vol_ratio']:.2f}}x)")
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
