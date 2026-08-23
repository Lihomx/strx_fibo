"""
triple_pattern_scanner.py
======================================================================
🌟 三重底 & 三重顶 (Triple Bottom & Triple Top) 双向形态扫描核心算法引擎
基于 Al Brooks 价格行为学分类与 TFLab MT4 经典几何结构判定：

【做多看涨 · 三重底变体 (Triple Bottom)】
  1. Perfect Triple Bottom        完美三重底 (三低点持平)
  2. Head & Shoulders Bottom      头肩底/截断楔形 (中间低点最低，两肩对称)
  3. Failed BO below HL DB        抬高双底失败突破型 (低点抬高且出现假跌破拉回)
  4. Failed BO below DB           双底跌破失败型 (短暂刺穿支撑但迅速收回)
  5. Double Bottom Pullback       双底回调型 (双底确立后回踩确认)
  6. Wedge Bottom                 楔形三重底 (低点依次降低，通道收窄)
  7. Triangle Bottom              收敛三角形三重底 (低点抬高，高点走低)

【做空看跌 · 三重顶变体 (Triple Top)】
  1. Perfect Triple Top           完美三重顶 (三高点持平)
  2. Head & Shoulders Top         头肩顶/截断上升楔形 (中间头部最高，两肩对称)
  3. Failed BO above LH DT        降低双顶失败突破型 (高点降低且出现假突破回落)
  4. Failed BO above DT           双顶突破失败型 (短暂冲破阻力但迅速回落)
  5. Double Top Pullback          双顶回调型 (双顶确立后反弹回踩阻力)
  6. Rising Wedge Top             上升楔形三重顶 (高点依次抬高，动能衰竭)
  7. Descending Triangle Top      下降三角形三重顶 (高点依次走低，水平颈线支撑)

【交易计划与目标位预测 (TFLab 风格)】
  - 入场位 (Entry): 颈线突破位
  - 止损位 (SL): 最极端低点下方 (底) / 最高点上方 (顶)
  - 第一目标 (TP1 1:1): 颈线 + 1.0 × 形态高度 (底) / 颈线 - 1.0 × 形态高度 (顶)
  - 第二目标 (TP2 1.618): 颈线 + 1.618 × 形态高度 (底) / 颈线 - 1.618 × 形态高度 (顶)
  - 盈亏比 (R:R): (TP1 - Entry) / (Entry - SL)
======================================================================
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple


# ----------------------------------------------------------------------
# 1. 基础工具：找 swing low / swing high（分形法）
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
# 2. 形态定义与判定结果结构
# ----------------------------------------------------------------------

@dataclass
class PatternMatch:
    symbol: str
    direction: str               # "bullish" (看涨做多 · 三重底) 或 "bearish" (看跌做空 · 三重顶)
    pattern: str                 # 形态分类名称（中文+英文）
    period: str = "1d"           # 扫描周期
    idx1: int = 0                # 第1点索引
    idx2: int = 0                # 第2点索引
    idx3: int = 0                # 第3点索引
    p1: float = 0.0              # 点1价格 (Low1 或 High1)
    p2: float = 0.0              # 点2价格 (Low2 或 High2)
    p3: float = 0.0              # 点3价格 (Low3 或 High3)
    neckline: float = 0.0        # 颈线阻力位 (底) 或 颈线支撑位 (顶)
    entry_price: float = 0.0     # 建议入场参考价
    stop_loss: float = 0.0       # 建议止损价 (SL)
    tp1: float = 0.0             # 第一目标位 (TP1 1:1 投影)
    tp2: float = 0.0             # 第二目标位 (TP2 1.618 斐波那契扩展)
    risk_reward: float = 1.0     # 盈亏比 (R:R)
    confidence: float = 0.8      # 置信度 (0~1)
    note: str = ""               # 结构特征描述
    status: str = "active"       # "active" (观望中), "confirmed" (已突破), "invalidated" (已失效), "expired" (已过期)
    status_reason: str = ""      # 状态原因
    bars_since_p3: int = 0       # 距第3点已过 K 线根数
    latest_close: float = 0.0    # 最新收盘价
    scan_time: str = ""          # 扫描生成时间

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
# 4. 看涨三重底 (Triple Bottom) 分类与目标位计算
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
    d13 = _pct_diff(low1, low3)

    descending = (low1 > low2 > low3) or (
        low1 >= low2 * (1 - flat_tol) and low2 > low3
    )  # 低点依次降低（楔形）
    ascending = (low1 < low2 < low3)  # 低点依次抬高
    flat_all = d12 <= flat_tol and d23 <= flat_tol  # 三点基本持平

    # 1. 完美三重底
    if flat_all:
        return "完美三重底 (Perfect Triple Bottom)", 0.92, \
            f"三低点差异 {max(d12, d23):.2%}，水平持平构筑坚实底部"

    # 2. 头肩底
    if low2 < low1 and low2 < low3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(low1, low3)
        conf = 0.88 if shoulder_diff < 0.03 else 0.72
        return "头肩底/截断楔形 (Head & Shoulders Bottom)", conf, \
            f"头部创更低点 ({low2:.2f})，左右双肩对称差异 {shoulder_diff:.2%}"

    # 3. 抬高双底失败突破型
    if ascending and broke_support_23:
        return "抬高双底失败突破型 (Failed BO below HL DB)", 0.85, \
            "底部逐步抬高，第3次回踩刺穿短暂支撑后被强劲拉回"

    # 4. 双底跌破失败型 / 双底回调型
    if broke_support_23:
        if d23 <= flat_tol * 2:
            return "双底回调型 (Double Bottom Pullback)", 0.80, \
                "双底确立后价格回踩，第3低点贴近前低有效支撑"
        else:
            return "双底跌破失败型 (Failed BO below DB)", 0.80, \
                "价格短暂跌破前低支撑但多头迅速收复"

    # 5. 楔形三重底
    if descending and not flat_all:
        return "楔形三重底 (Wedge Bottom)", 0.75, \
            f"低点依次降低 (L1:{low1:.2f} > L2:{low2:.2f} > L3:{low3:.2f})，下行动能衰竭"

    # 6. 三角形三重底
    if ascending and mid_high_12 > mid_high_23:
        return "三角形三重底 (Triangle Bottom)", 0.75, \
            "低点抬高同时中间高点走低，形成收敛三角形等待向上突破"

    return "未分类三次探底 (Unclassified Triple Bottom)", 0.55, \
        "满足三次探底特征，底部结构清晰"


# ----------------------------------------------------------------------
# 5. 看跌三重顶 (Triple Top) 分类与目标位计算
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
    d13 = _pct_diff(high1, high3)

    ascending = (high1 < high2 < high3) or (
        high1 <= high2 * (1 + flat_tol) and high2 < high3
    )  # 高点依次抬高（上升楔形）
    descending = (high1 > high2 > high3)  # 高点依次降低
    flat_all = d12 <= flat_tol and d23 <= flat_tol  # 三高点基本持平

    # 1. 完美三重顶
    if flat_all:
        return "完美三重顶 (Perfect Triple Top)", 0.92, \
            f"三高点差异 {max(d12, d23):.2%}，水平受阻构筑坚固阻力顶"

    # 2. 头肩顶
    if high2 > high1 and high2 > high3 and d12 > flat_tol and d23 > flat_tol:
        shoulder_diff = _pct_diff(high1, high3)
        conf = 0.88 if shoulder_diff < 0.03 else 0.72
        return "头肩顶/截断上升楔形 (Head & Shoulders Top)", conf, \
            f"头部创更高点 ({high2:.2f})，左右双肩受阻差异 {shoulder_diff:.2%}"

    # 3. 降低双顶失败突破型
    if descending and broke_resist_23:
        return "降低双顶失败突破型 (Failed BO above LH DT)", 0.85, \
            "高点逐步走低，第3次冲高刺穿阻力后被空头强力打压"

    # 4. 双顶突破失败型 / 双顶回调型
    if broke_resist_23:
        if d23 <= flat_tol * 2:
            return "双顶回调型 (Double Top Pullback)", 0.80, \
                "双顶确立后价格反弹，第3高点贴近前高阻力受阻"
        else:
            return "双顶突破失败型 (Failed BO above DT)", 0.80, \
                "价格短暂冲破前高阻力但多头无力维持，迅速跌回"

    # 5. 上升楔形三重顶
    if ascending and not flat_all:
        return "上升楔形三重顶 (Rising Wedge Top)", 0.75, \
            f"高点依次抬高 (H1:{high1:.2f} < H2:{high2:.2f} < H3:{high3:.2f})，上行动能衰竭"

    # 6. 下降三角形三重顶
    if descending and mid_low_12 < mid_low_23:
        return "下降三角形三重顶 (Descending Triangle Top)", 0.75, \
            "高点走低同时中间低点平齐，形成下降三角形等待向下破位"

    return "未分类三次探顶 (Unclassified Triple Top)", 0.55, \
        "满足三次探顶特征，顶部承压结构清晰"


# ----------------------------------------------------------------------
# 6. 主扫描函数：单标的看涨三重底 + 看跌三重顶双向扫描
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
    # 🐂 A. 看涨三重底 (Triple Bottom) 扫描
    # ==================================================================
    if scan_bottoms and len(swing_low_idx) >= 3:
        for a in range(len(swing_low_idx) - 2):
            i1, i2, i3 = swing_low_idx[a], swing_low_idx[a + 1], swing_low_idx[a + 2]
            spacing_12 = i2 - i1
            spacing_23 = i3 - i2
            if not (min_spacing <= spacing_12 <= max_spacing and min_spacing <= spacing_23 <= max_spacing):
                continue

            low1, low2, low3 = float(df.loc[i1, "low"]), float(df.loc[i2, "low"]), float(df.loc[i3, "low"])
            seg_12 = df.loc[i1:i2, "high"]
            seg_23 = df.loc[i2:i3, "high"]
            mid_high_12 = float(seg_12.max()) if len(seg_12) else low1
            mid_high_23 = float(seg_23.max()) if len(seg_23) else low2

            support_level = min(low1, low2)
            broke = False
            seg_break = df.loc[i2:i3]
            if len(seg_break):
                min_low_in_seg = float(seg_break["low"].min())
                close_at_end = float(df.loc[i3, "close"])
                if min_low_in_seg < support_level * (1 - break_tol) and close_at_end > support_level:
                    broke = True

            pattern_name, conf, note = classify_triple_bottom(
                low1, low2, low3, mid_high_12, mid_high_23, broke, flat_tol=flat_tol
            )

            # 目标位与交易计划计算
            neckline = max(mid_high_12, mid_high_23)
            lowest_point = min(low1, low2, low3)
            height = max(neckline - lowest_point, neckline * 0.01)

            entry_price = round(neckline, 3)
            stop_loss = round(lowest_point * (1 - 0.006), 3)
            tp1 = round(neckline + height * 1.0, 3)
            tp2 = round(neckline + height * 1.618, 3)
            risk = max(entry_price - stop_loss, entry_price * 0.005)
            reward = tp1 - entry_price
            rr = round(reward / risk, 2) if risk > 0 else 1.0

            # 状态判定
            seg_post = df.loc[i3:]
            bars_since_p3 = int(total_bars - 1 - i3)
            has_broken_support = bool((seg_post["close"] < lowest_point * (1 - break_tol)).any())
            has_broken_neckline = bool((seg_post["close"] > neckline).any())

            if has_broken_support:
                status = "invalidated"
                status_reason = f"已失效：价格跌破最低支撑 {lowest_point:.2f}"
            elif bars_since_p3 > 45:
                status = "expired"
                status_reason = f"已过期：形态生成后已有 {bars_since_p3} 根 K 线未突破"
            elif has_broken_neckline:
                status = "confirmed"
                status_reason = f"已突破：收盘站上颈线 {neckline:.2f}"
            else:
                status = "active"
                status_reason = f"观望中：价格在 {lowest_point:.2f} ~ {neckline:.2f} 震荡蓄势"

            matches.append(PatternMatch(
                symbol=symbol,
                direction="bullish",
                pattern=pattern_name,
                period=period,
                idx1=i1, idx2=i2, idx3=i3,
                p1=round(low1, 3), p2=round(low2, 3), p3=round(low3, 3),
                neckline=round(neckline, 3),
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1, tp2=tp2,
                risk_reward=rr,
                confidence=conf,
                note=note,
                status=status,
                status_reason=status_reason,
                bars_since_p3=bars_since_p3,
                latest_close=round(latest_close, 3),
            ))

    # ==================================================================
    # 🐻 B. 看跌三重顶 (Triple Top) 扫描
    # ==================================================================
    if scan_tops and len(swing_high_idx) >= 3:
        for a in range(len(swing_high_idx) - 2):
            i1, i2, i3 = swing_high_idx[a], swing_high_idx[a + 1], swing_high_idx[a + 2]
            spacing_12 = i2 - i1
            spacing_23 = i3 - i2
            if not (min_spacing <= spacing_12 <= max_spacing and min_spacing <= spacing_23 <= max_spacing):
                continue

            high1, high2, high3 = float(df.loc[i1, "high"]), float(df.loc[i2, "high"]), float(df.loc[i3, "high"])
            seg_12 = df.loc[i1:i2, "low"]
            seg_23 = df.loc[i2:i3, "low"]
            mid_low_12 = float(seg_12.min()) if len(seg_12) else high1
            mid_low_23 = float(seg_23.min()) if len(seg_23) else high2

            resist_level = max(high1, high2)
            broke = False
            seg_break = df.loc[i2:i3]
            if len(seg_break):
                max_high_in_seg = float(seg_break["high"].max())
                close_at_end = float(df.loc[i3, "close"])
                if max_high_in_seg > resist_level * (1 + break_tol) and close_at_end < resist_level:
                    broke = True

            pattern_name, conf, note = classify_triple_top(
                high1, high2, high3, mid_low_12, mid_low_23, broke, flat_tol=flat_tol
            )

            # 目标位与交易计划计算
            neckline = min(mid_low_12, mid_low_23)
            highest_point = max(high1, high2, high3)
            height = max(highest_point - neckline, neckline * 0.01)

            entry_price = round(neckline, 3)
            stop_loss = round(highest_point * (1 + 0.006), 3)
            tp1 = round(max(0.001, neckline - height * 1.0), 3)
            tp2 = round(max(0.001, neckline - height * 1.618), 3)
            risk = max(stop_loss - entry_price, entry_price * 0.005)
            reward = entry_price - tp1
            rr = round(reward / risk, 2) if risk > 0 else 1.0

            # 状态判定
            seg_post = df.loc[i3:]
            bars_since_p3 = int(total_bars - 1 - i3)
            has_broken_resist = bool((seg_post["close"] > highest_point * (1 + break_tol)).any())
            has_broken_neckline = bool((seg_post["close"] < neckline).any())

            if has_broken_resist:
                status = "invalidated"
                status_reason = f"已失效：价格突破最高阻力 {highest_point:.2f}"
            elif bars_since_p3 > 45:
                status = "expired"
                status_reason = f"已过期：形态生成后已有 {bars_since_p3} 根 K 线未破位"
            elif has_broken_neckline:
                status = "confirmed"
                status_reason = f"已突破：收盘跌破颈线 {neckline:.2f}"
            else:
                status = "active"
                status_reason = f"观望中：价格在 {neckline:.2f} ~ {highest_point:.2f} 承压运行"

            matches.append(PatternMatch(
                symbol=symbol,
                direction="bearish",
                pattern=pattern_name,
                period=period,
                idx1=i1, idx2=i2, idx3=i3,
                p1=round(high1, 3), p2=round(high2, 3), p3=round(high3, 3),
                neckline=round(neckline, 3),
                entry_price=entry_price,
                stop_loss=stop_loss,
                tp1=tp1, tp2=tp2,
                risk_reward=rr,
                confidence=conf,
                note=note,
                status=status,
                status_reason=status_reason,
                bars_since_p3=bars_since_p3,
                latest_close=round(latest_close, 3),
            ))

    # 最近的排在最前
    matches.sort(key=lambda m: (m.idx3, m.confidence), reverse=True)
    return matches
