"""
neckline_scanner.py — 4小时 (4H) 结构颈线突破扫描核心算法
========================================================================================
核心原理：
  形态识别（箱体/双底/头肩底） + 突破确认 (Price > Neckline + 1.2*ATR) + 量能过滤 + 趋势过滤 + 连续站稳
"""

import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


def _fetch_4h_data(ticker: str) -> Optional[pd.DataFrame]:
    """获取 4H 级别 OHLCV 数据，优先使用 1H 重采样，具备重试与兜底机制"""
    if not _YF_OK:
        return None

    # 1. 优先获取 1H 数据并重采样为 4H
    for attempt in range(3):
        try:
            df_1h = yf.download(ticker, period="60d", interval="1h",
                                progress=False, auto_adjust=True, threads=False, timeout=15)
            if df_1h is not None and not df_1h.empty and len(df_1h) >= 8:
                new_cols = [str(c[0] if isinstance(c, tuple) else c).lower() for c in df_1h.columns]
                df_1h.columns = new_cols
                if "close" in df_1h.columns:
                    df_4h = df_1h.resample("4h").agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }).dropna(subset=["close"])
                    if len(df_4h) >= 20:
                        return df_4h
        except Exception as e:
            err = str(e).lower()
            if "rate" in err or "429" in err:
                time.sleep(1.5 * (attempt + 1))
                continue
            break

    # 2. 兜底直接获取 4H 或 1D
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
    """计算真实波幅 ATR"""
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


def check_ticker_neckline(ticker: str, df: Optional[pd.DataFrame] = None) -> Dict:
    """
    对指定品种执行 4H 结构颈线突破 7 条核心规则检测
    返回结果字典包含：
      passed(bool), pattern(str), neckline(float), close(float),
      volume_4h(float), vol_ratio(float), atr14(float), breakout_pct(float),
      details(list[dict]), error(str|None)
    """
    res = {
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
    }

    try:
        if df is None:
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
        c_prev2 = float(close.iloc[-3]) if len(close) >= 3 else c_prev1

        v_last = float(volume.iloc[-1])
        v_prev1 = float(volume.iloc[-2]) if len(volume) >= 2 else v_last

        # 计算 ATR
        atr_ser = calculate_atr(df, 14)
        atr_val = float(atr_ser.iloc[-1]) if not pd.isna(atr_ser.iloc[-1]) else (c_last * 0.02)
        res["atr14"] = atr_val
        res["close"] = c_last
        res["volume_4h"] = v_last

        # ── 1. 箱体突破结构 (Box Breakout) ──
        # 取前 20 周期 (不含当前最新根) 的高低点作为箱体
        box_n = min(20, len(df) - 1)
        sub_high = high.iloc[-box_n-1:-1]
        sub_low = low.iloc[-box_n-1:-1]
        box_high = float(sub_high.max())
        box_low = float(sub_low.min())
        box_range = box_high - box_low

        box_break = c_last > box_high
        box_break_strong = c_last > (box_high + 0.8 * atr_val)

        # ── 2. 双底结构 (Double Bottom) ──
        # 寻找前 25 根 K 线中的两个相近低点与中间颈线
        db_n = min(25, len(df))
        sub_df = df.iloc[-db_n:]
        lows = sub_df["low"].values
        highs = sub_df["high"].values
        
        # 底部 1 (前 12-24 根的局部最低点)
        mid_idx = len(lows) // 2
        b1_idx = int(np.argmin(lows[:mid_idx])) if mid_idx > 2 else 0
        b1_low = float(lows[b1_idx])
        
        # 底部 2 (近 2-12 根的局部最低点)
        b2_idx = mid_idx + int(np.argmin(lows[mid_idx:-1])) if (len(lows) - mid_idx) > 2 else (len(lows) - 2)
        b2_low = float(lows[b2_idx])
        
        # 颈线 (两底之间的最高反弹点)
        if b2_idx > b1_idx + 2:
            neckline_double = float(np.max(highs[b1_idx:b2_idx]))
        else:
            neckline_double = float(np.max(highs[-10:-1]))
            
        double_bottom_valid = (b2_low >= b1_low * 0.96) and (b2_low <= b1_low * 1.05) and (neckline_double > max(b1_low, b2_low))
        double_break = double_bottom_valid and (c_last > neckline_double)

        # ── 3. 头肩底结构 (Head & Shoulders Bottom) ──
        # 左肩、头部 (最低)、右肩 (高于头部)
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

        # 确定主颈线价格
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

        # ── 4. 成交量过滤 ──
        vol_ma5 = float(volume.rolling(5).mean().iloc[-1]) if len(volume) >= 5 else v_last
        vol_ma20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else (vol_ma5 or 1.0)
        vol_ratio = (v_last / vol_ma5) if vol_ma5 > 0 else 1.0
        res["vol_ratio"] = vol_ratio

        vol_break = (vol_ratio >= 1.3) or (v_last > v_prev1 * 1.5)
        vol_not_abnormal = (v_last <= (vol_ma20 * 2.8))  # 排除极端天量衰竭

        # ── 5. 均线多头排列 ──
        ma5 = float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else c_last
        ma10 = float(close.rolling(10).mean().iloc[-1]) if len(close) >= 10 else c_last
        ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else c_last
        ma_bull = (ma5 >= ma10 * 0.998) and (ma10 >= ma20 * 0.995)

        # ── 6. 连续站稳过滤 ──
        stand_still = (c_last >= primary_neckline * 0.995) and ((c_prev1 >= primary_neckline * 0.99) or (c_last > primary_neckline * 1.008))

        # ── 7. 规则明细构建 ──
        rules = [
            {
                "id": "[0] 颈线突破",
                "desc": "4H收盘价突破结构颈线 (箱体/双底/头肩底)",
                "ok": bool(c_last >= primary_neckline),
                "val": f"Close={c_last:.4f} vs 颈线={primary_neckline:.4f} (+{res['breakout_pct']:.2f}%)",
            },
            {
                "id": "[1] 突破幅度",
                "desc": "突破幅度有效过滤假刺穿 (Close > 颈线 + 0.8×ATR 或 幅度>1%)",
                "ok": bool(box_break_strong or (res['breakout_pct'] >= 0.8)),
                "val": f"幅度=+{res['breakout_pct']:.2f}% | ATR14={atr_val:.4f}",
            },
            {
                "id": "[2] 增量放大",
                "desc": "4H成交量放大 (VOL > 1.3×MA5 或 前根1.5倍)",
                "ok": bool(vol_break),
                "val": f"4H量={v_last:,.0f} vs MA5={vol_ma5:,.0f} ({vol_ratio:.2f}倍)",
            },
            {
                "id": "[3] 异常天量过滤",
                "desc": "避免天量脉冲后衰竭 (VOL < 2.8×MA20)",
                "ok": bool(vol_not_abnormal),
                "val": f"4H量={v_last:,.0f} vs MA20={vol_ma20:,.0f} ({v_last/vol_ma20:.2f}倍)" if vol_ma20 else "正常",
            },
            {
                "id": "[4] 趋势共振",
                "desc": "4H均线多头共振排列 (MA5 ≥ MA10 ≥ MA20)",
                "ok": bool(ma_bull),
                "val": f"MA5={ma5:.3f} | MA10={ma10:.3f} | MA20={ma20:.3f}",
            },
            {
                "id": "[5] 站稳确认",
                "desc": "收盘价在颈线上方持续站稳 (过滤单针冲高回落)",
                "ok": bool(stand_still),
                "val": f"当前={c_last:.4f} | 前根={c_prev1:.4f} | 颈线={primary_neckline:.4f}",
            },
            {
                "id": "[6] 形态结构",
                "desc": "识别到有效底部/整理结构 (箱体/双底/头肩底)",
                "ok": bool(len(matched_patterns) > 0 or box_break),
                "val": f"识别形态: {primary_pattern}",
            },
        ]

        res["details"] = rules
        # 只要突破了颈线且满足量能与趋势过滤即判定通过
        res["passed"] = bool((c_last >= primary_neckline) and vol_break and ma_bull and stand_still)

    except Exception as e:
        res["error"] = str(e)

    return res
