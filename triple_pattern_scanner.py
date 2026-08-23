"""
triple_pattern_scanner.py
======================================================================
🌟 三重底 & 三重顶 (Triple Top Bottom Scan v4 / TFLab MT4) 双向形态扫描算法引擎
完全对齐 TFLab MT4 "Triple Top Bottom Scan v4" 指标几何结构与 5 点波浪 (1-2-3-4-5) 投影模型：

【5 点关键波浪结构 (5-Point Swing Sequence)】
  - 🐂 看涨三重底 (Bullish Triple Bottom):
      Point 1 (探底 L1) -> Point 2 (反弹峰 H1) -> Point 3 (探底 L2) -> Point 4 (反弹峰 H2) -> Point 5 (探底 L3 / 进场点 Entry Point)
  - 🐻 看跌三重顶 (Bearish Triple Top):
      Point 1 (冲顶 H1) -> Point 2 (回调谷 L1) -> Point 3 (冲顶 H2) -> Point 4 (回调谷 L2) -> Point 5 (冲顶 H3 / 进场点 Entry Point)

【三段斐波那契目标位体系 (3-Tier Fibonacci Take-Profit Targets)】
  - 入场位 (Entry Point): Point 5 确认触底/触顶反转价 (或突破颈线价)
  - 止损位 (Stop Loss): 粉色止损区 (最低探底价下方 / 最高冲顶价上方)
  - TP1 (61.8% Fibonacci): 入场位 ± 0.618 × 形态高度
  - TP2 (100.0% Fibonacci): 入场位 ± 1.000 × 形态高度 (颈线目标)
  - TP3 (161.8% Fibonacci): 入场位 ± 1.618 × 形态高度 (斐波那契黄金扩展目标)
  - 盈亏比 (Risk to Reward): 精准测算 1 : 1.5 ~ 1 : 4.0+ 盈亏比
======================================================================
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple


# ----------------------------------------------------------------------
# 1. 基础工具：找 swing low / swing high（分形波峰波谷）
# ----------------------------------------------------------------------

def find_swing_points(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    在 df（须含 high, low 列，index 为自然序号）上标记 swing low / swing high。
    window: 左右各看几根K线来确认局部极值（分形阶数）。
    """
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


# ----------------------------------------------------------------------
# 2. 形态定义与判定结果结构 (完全对齐 MT4 指标模型)
# ----------------------------------------------------------------------

@dataclass
class PatternMatch:
    symbol: str
    direction: str               # "bullish" (看涨三重底) 或 "bearish" (看跌三重顶)
    pattern: str                 # 形态分类名称
    period: str = "1d"           # 扫描周期
    # 5 点波浪位置索引 (1, 2, 3, 4, 5)
    idx1: int = 0
    idx2: int = 0
    idx3: int = 0
    idx4: int = 0
    idx5: int = 0
    # 5 点价格
    pt1: float = 0.0             # L1 (底) 或 H1 (顶)
    pt2: float = 0.0             # H1 (底) 或 L1 (顶)
    pt3: float = 0.0             # L2 (底) 或 H2 (顶)
    pt4: float = 0.0             # H2 (底) 或 L2 (顶)
    pt5: float = 0.0             # L3 (底) 或 H3 (顶)
    # 兼容旧代码字段
    p1: float = 0.0
    p2: float = 0.0
    p3: float = 0.0
    neckline: float = 0.0        # 颈线位
    entry_price: float = 0.0     # 建议入场位 (Point 5 反转或颈线)
    stop_loss: float = 0.0       # 建议止损位 (SL)
    tp1: float = 0.0             # TP1 (61.8% Fibonacci)
    tp2: float = 0.0             # TP2 (100% Fibonacci)
    tp3: float = 0.0             # TP3 (161.8% Fibonacci)
    risk: float = 0.0            # 风险点数/差价
    reward_tp1: float = 0.0      # TP1 收益
    reward_tp2: float = 0.0      # TP2 收益
    reward_tp3: float = 0.0      # TP3 收益
    risk_reward: float = 1.0     # 默认 TP2 盈亏比 (1:X)
    rr_tp3: float = 2.0          # TP3 黄金盈亏比 (1:X)
    confidence: float = 0.8      # 置信度 (0~1)
    note: str = ""               # 结构特征描述
    status: str = "active"       # "active" (观望中), "confirmed" (已突破), "invalidated" (已失效), "expired" (已过期)
    status_reason: str = ""      # 状态原因
    bars_since_p5: int = 0       # 距第5点已过 K 线根数
    latest_close: float = 0.0    # 最新收盘价
    scan_time: str = ""          # 扫描生成时间
    breakout_progress: float = 0.0  # 🏃 跑势进度 (%): active=0%, confirmed=(close-neckline)/pattern_height×100%

    def to_dict(self) -> Dict:
        return asdict(self)


# ----------------------------------------------------------------------
# 3. 辅助百分比计算
# ----------------------------------------------------------------------

def _pct_diff(a: float, b: float) -> float:
    """相对百分比差，避免除零"""
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base


# ----------------------------------------------------------------------
# 4. 看涨三重底 (Bullish Triple Bottom) 分类与目标位计算
# ----------------------------------------------------------------------

def classify_triple_bottom(
    low1: float, low2: float, low3: float,
    mid_high_12: float, mid_high_23: float,
    broke_support_23: bool,
    flat_tol: float = 0.02,
) -> Tuple[str, float, str]:
    """判定三重底子形态类别"""
    d12 = _pct_diff(low1, low2)
    d23 = _pct_diff(low2, low3)

    descending = (low1 > low2 > low3) or (
        low1 >= low2 * (1 - flat_tol) and low2 > low3
    )  # 低点依次降低（楔形）
    ascending = (low1 < low2 < low3)  # 低点依次抬高
    flat_all = d12 <= flat_tol and d23 <= flat_tol  # 三点基本持平

    if flat_all:
        return "完美三重底 (Perfect Triple Bottom)", 0.95, \
            f"三低点极度持平 (差异 {max(d12, d23):.2%})，坚固三底支撑"

    if low2 < low1 and low2 < low3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(low1, low3)
        conf = 0.90 if shoulder_diff < 0.03 else 0.75
        return "头肩底/截断楔形 (Head & Shoulders Bottom)", conf, \
            f"中间第3点更低(头部 {low2:.2f})，左右对称"

    if ascending and broke_support_23:
        return "抬高双底失败突破型 (Failed BO below HL DB)", 0.88, \
            "底部逐步抬高，第5点刺穿短暂支撑后被多头强力收复"

    if broke_support_23:
        if d23 <= flat_tol * 2:
            return "双底回调型 (Double Bottom Pullback)", 0.82, \
                "双底确立后回踩确认支撑，第5点贴近前低"
        else:
            return "双底跌破失败型 (Failed BO below DB)", 0.82, \
                "短暂刺穿支撑后多头迅速拉起"

    if descending and not flat_all:
        return "楔形三重底 (Wedge Bottom)", 0.78, \
            f"低点依次降低 (L1>L2>L3)，下行动能耗尽"

    if ascending and mid_high_12 > mid_high_23:
        return "三角形三重底 (Triangle Bottom)", 0.78, \
            "低点抬高同时中间高点走低，收敛三角形等待向上爆发"

    return "经典三重底 (Classic Triple Bottom)", 0.65, \
        "三次探底反转结构"


# ----------------------------------------------------------------------
# 5. 看跌三重顶 (Bearish Triple Top) 分类与目标位计算
# ----------------------------------------------------------------------

def classify_triple_top(
    high1: float, high2: float, high3: float,
    mid_low_12: float, mid_low_23: float,
    broke_resist_23: bool,
    flat_tol: float = 0.02,
) -> Tuple[str, float, str]:
    """判定三重顶子形态类别"""
    d12 = _pct_diff(high1, high2)
    d23 = _pct_diff(high2, high3)

    ascending = (high1 < high2 < high3) or (
        high1 <= high2 * (1 + flat_tol) and high2 < high3
    )  # 高点依次抬高（上升楔形）
    descending = (high1 > high2 > high3)  # 高点依次降低
    flat_all = d12 <= flat_tol and d23 <= flat_tol  # 三高点基本持平

    if flat_all:
        return "完美三重顶 (Perfect Triple Top)", 0.95, \
            f"三高点极度持平 (差异 {max(d12, d23):.2%})，坚固三顶受阻"

    if high2 > high1 and high2 > high3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(high1, high3)
        conf = 0.90 if shoulder_diff < 0.03 else 0.75
        return "头肩顶/截断上升楔形 (Head & Shoulders Top)", conf, \
            f"中间第3点更高(头部 {high2:.2f})，左右对称"

    if descending and broke_resist_23:
        return "降低双顶失败突破型 (Failed BO above LH DT)", 0.88, \
            "高点逐步走低，第5点冲高遇阻后空头强力打压"

    if broke_resist_23:
        if d23 <= flat_tol * 2:
            return "双顶回调型 (Double Top Pullback)", 0.82, \
                "双顶确立后反弹回踩阻力，第5点受阻"
        else:
            return "双顶突破失败型 (Failed BO above DT)", 0.82, \
                "短暂刺穿阻力但多头无力维持，迅速跌回"

    if ascending and not flat_all:
        return "上升楔形三重顶 (Rising Wedge Top)", 0.78, \
            f"高点依次抬高 (H1<H2<H3)，上行动能衰竭"

    if descending and mid_low_12 < mid_low_23:
        return "下降三角形三重顶 (Descending Triangle Top)", 0.78, \
            "高点走低同时支撑平齐，向下破位"

    return "经典三重顶 (Classic Triple Top)", 0.65, \
        "三次冲顶受阻反转结构"


# ----------------------------------------------------------------------
# 6. 主扫描函数：对齐 MT4 Triple Top Bottom Scan v4 算法
# ----------------------------------------------------------------------

def scan_triple_patterns(
    df: pd.DataFrame,
    symbol: str = "",
    period: str = "1d",
    swing_window: int = 3,
    lookback_bars: int = 150,
    max_spacing: int = 80,
    min_spacing: int = 3,
    break_tol: float = 0.01,
    flat_tol: float = 0.02,
    scan_bottoms: bool = True,
    scan_tops: bool = True,
) -> List[PatternMatch]:
    """
    输入 OHLC DataFrame，扫描三重底 (看涨) 与 三重顶 (看跌) 形态
    返回所有识别到的 PatternMatch 列表 (最近的排在前面)
    """
    if df is None or len(df) < swing_window * 2 + 10:
        return []

    df = df.tail(lookback_bars).reset_index(drop=True)
    df.columns = [str(c).lower() for c in df.columns]

    df = find_swing_points(df, window=swing_window)
    swing_low_idx = df.index[df["is_swing_low"]].tolist()
    swing_high_idx = df.index[df["is_swing_high"]].tolist()

    latest_close = float(df.loc[df.index[-1], "close"])
    total_bars = len(df)
    matches: List[PatternMatch] = []

    # ==================================================================
    # 🐂 A. 看涨三重底 (Bullish Triple Bottom: 1-2-3-4-5)
    # ==================================================================
    if scan_bottoms and len(swing_low_idx) >= 3:
        for a in range(len(swing_low_idx) - 2):
            i1, i3, i5 = swing_low_idx[a], swing_low_idx[a + 1], swing_low_idx[a + 2]
            if not (min_spacing <= (i3 - i1) <= max_spacing and min_spacing <= (i5 - i3) <= max_spacing):
                continue

            low1, low2, low3 = float(df.loc[i1, "low"]), float(df.loc[i3, "low"]), float(df.loc[i5, "low"])

            # 寻找波峰 2 (H1) 和波峰 4 (H2)
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

            pattern_name, conf, note = classify_triple_bottom(
                low1, low2, low3, high1, high2, broke, flat_tol=flat_tol
            )

            # 🎯 目标位与交易计划计算 (对齐 MT4 Triple Top Bottom Scan v4)
            neckline = max(high1, high2)
            lowest_point = min(low1, low2, low3)
            pattern_height = max(neckline - lowest_point, neckline * 0.01)

            entry_price = round(low3, 3) # MT4 指标以第 5 点探底确认或当前市价为进场参考
            stop_loss = round(lowest_point * (1 - 0.008), 3) # 止损粉色区

            # 3 段斐波那契目标位
            tp1 = round(entry_price + pattern_height * 0.618, 3)   # TP1 (61.8%)
            tp2 = round(neckline, 3)                               # TP2 (100.0% 颈线位)
            tp3 = round(entry_price + pattern_height * 1.618, 3)   # TP3 (161.8% 黄金扩展)

            risk = max(entry_price - stop_loss, entry_price * 0.005)
            reward1 = max(0.001, tp1 - entry_price)
            reward2 = max(0.001, tp2 - entry_price)
            reward3 = max(0.001, tp3 - entry_price)

            rr_tp1 = round(reward1 / risk, 2)
            rr_tp2 = round(reward2 / risk, 2)
            rr_tp3 = round(reward3 / risk, 2)

            # 状态判定
            seg_post = df.loc[i5:]
            bars_since_p5 = int(total_bars - 1 - i5)
            has_broken_support = bool((seg_post["close"] < lowest_point * (1 - break_tol)).any())
            has_broken_neckline = bool((seg_post["close"] > neckline).any())

            if has_broken_support:
                status = "invalidated"
                status_reason = f"已失效：价格跌破最低止损 {stop_loss:.2f}"
            elif bars_since_p5 > 45:
                status = "expired"
                status_reason = f"已过期：形态后已有 {bars_since_p5} 根 K 线未达成目标"
            elif has_broken_neckline:
                status = "confirmed"
                status_reason = f"已突破确认：收盘站上颈线 {neckline:.2f}，朝 TP3 ({tp3:.2f}) 推进"
            else:
                status = "active"
                status_reason = f"探底反弹中：价格在 {lowest_point:.2f} ~ {neckline:.2f} 运行"

            # 🏃 跑势进度：active=0%，confirmed=(当前收盘-颈线)/形态高度×100%
            if status == "confirmed":
                breakout_progress = round(max(0.0, (latest_close - neckline) / pattern_height * 100), 1)
            else:
                breakout_progress = 0.0

            matches.append(PatternMatch(
                symbol=symbol,
                direction="bullish",
                pattern=pattern_name,
                period=period,
                idx1=i1, idx2=i2, idx3=i3, idx4=i4, idx5=i5,
                pt1=round(low1, 3), pt2=round(high1, 3), pt3=round(low2, 3), pt4=round(high2, 3), pt5=round(low3, 3),
                p1=round(low1, 3), p2=round(low2, 3), p3=round(low3, 3),
                neckline=round(neckline, 3),
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1, tp2=tp2, tp3=tp3,
                risk=round(risk, 3),
                reward_tp1=round(reward1, 3),
                reward_tp2=round(reward2, 3),
                reward_tp3=round(reward3, 3),
                risk_reward=rr_tp2,
                rr_tp3=rr_tp3,
                confidence=conf,
                note=note,
                status=status,
                status_reason=status_reason,
                bars_since_p5=bars_since_p5,
                latest_close=round(latest_close, 3),
                breakout_progress=breakout_progress,
            ))

    # ==================================================================
    # 🐻 B. 看跌三重顶 (Bearish Triple Top: 1-2-3-4-5)
    # ==================================================================
    if scan_tops and len(swing_high_idx) >= 3:
        for a in range(len(swing_high_idx) - 2):
            i1, i3, i5 = swing_high_idx[a], swing_high_idx[a + 1], swing_high_idx[a + 2]
            if not (min_spacing <= (i3 - i1) <= max_spacing and min_spacing <= (i5 - i3) <= max_spacing):
                continue

            high1, high2, high3 = float(df.loc[i1, "high"]), float(df.loc[i3, "high"]), float(df.loc[i5, "high"])

            # 寻找波谷 2 (L1) 和波谷 4 (L2)
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

            pattern_name, conf, note = classify_triple_top(
                high1, high2, high3, low1, low2, broke, flat_tol=flat_tol
            )

            # 🎯 目标位与交易计划计算 (对齐 MT4 Triple Top Bottom Scan v4)
            neckline = min(low1, low2)
            highest_point = max(high1, high2, high3)
            pattern_height = max(highest_point - neckline, neckline * 0.01)

            entry_price = round(high3, 3) # MT4 指标以第 5 点冲顶受阻或当前市价为进场参考
            stop_loss = round(highest_point * (1 + 0.008), 3) # 止损粉色区

            # 3 段斐波那契目标位
            tp1 = round(max(0.001, entry_price - pattern_height * 0.618), 3)  # TP1 (61.8%)
            tp2 = round(neckline, 3)                                          # TP2 (100.0% 颈线位)
            tp3 = round(max(0.001, entry_price - pattern_height * 1.618), 3)  # TP3 (161.8% 黄金扩展)

            risk = max(stop_loss - entry_price, entry_price * 0.005)
            reward1 = max(0.001, entry_price - tp1)
            reward2 = max(0.001, entry_price - tp2)
            reward3 = max(0.001, entry_price - tp3)

            rr_tp1 = round(reward1 / risk, 2)
            rr_tp2 = round(reward2 / risk, 2)
            rr_tp3 = round(reward3 / risk, 2)

            # 状态判定
            seg_post = df.loc[i5:]
            bars_since_p5 = int(total_bars - 1 - i5)
            has_broken_resist = bool((seg_post["close"] > highest_point * (1 + break_tol)).any())
            has_broken_neckline = bool((seg_post["close"] < neckline).any())

            if has_broken_resist:
                status = "invalidated"
                status_reason = f"已失效：价格向上冲破止损 {stop_loss:.2f}"
            elif bars_since_p5 > 45:
                status = "expired"
                status_reason = f"已过期：形态后已有 {bars_since_p5} 根 K 线未达成目标"
            elif has_broken_neckline:
                status = "confirmed"
                status_reason = f"已跌破确认：收盘跌破颈线 {neckline:.2f}，朝 TP3 ({tp3:.2f}) 推进"
            else:
                status = "active"
                status_reason = f"冲顶受阻回落中：价格在 {neckline:.2f} ~ {highest_point:.2f} 承压"

            # 🏃 跑势进度：active=0%，confirmed=(颈线-当前收盘)/形态高度×100%
            if status == "confirmed":
                breakout_progress = round(max(0.0, (neckline - latest_close) / pattern_height * 100), 1)
            else:
                breakout_progress = 0.0

            matches.append(PatternMatch(
                symbol=symbol,
                direction="bearish",
                pattern=pattern_name,
                period=period,
                idx1=i1, idx2=i2, idx3=i3, idx4=i4, idx5=i5,
                pt1=round(high1, 3), pt2=round(low1, 3), pt3=round(high2, 3), pt4=round(low2, 3), pt5=round(high3, 3),
                p1=round(high1, 3), p2=round(high2, 3), p3=round(high3, 3),
                neckline=round(neckline, 3),
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1, tp2=tp2, tp3=tp3,
                risk=round(risk, 3),
                reward_tp1=round(reward1, 3),
                reward_tp2=round(reward2, 3),
                reward_tp3=round(reward3, 3),
                risk_reward=rr_tp2,
                rr_tp3=rr_tp3,
                confidence=conf,
                note=note,
                status=status,
                status_reason=status_reason,
                bars_since_p5=bars_since_p5,
                latest_close=round(latest_close, 3),
                breakout_progress=breakout_progress,
            ))

    # 最近的排在最前
    matches.sort(key=lambda m: (m.idx5, m.confidence), reverse=True)
    return matches
