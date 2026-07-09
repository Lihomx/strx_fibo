"""
triple_bottom_scanner.py

三重底（Triple Bottom）及其变体形态扫描核心模块
基于 Al Brooks 价格行为学分类：
  1. Perfect Triple Bottom      完美三重底
  2. Head & Shoulders Bottom    头肩底（截断楔形）
  3. Failed BO below DB         双底跌破失败型
  4. Wedge                      楔形三重底（低点依次降低）
  5. Double Bottom Pullback     双底回调型
  6. Failed BO below HL DB      抬高双底失败突破型
  7. Triangle                   三角形三重底（收敛）

设计思路：
  - 先用分形法（fractal）找出所有 swing low（局部低点）和 swing high（局部高点）
  - 在最近的 K 根 swing low 中取"三次探低"组合
  - 根据三个低点的相对高度关系、中间高点的位置、以及是否出现
    "跌破支撑后又快速拉回"（失败突破）等特征，对形态分类打分
  - 返回结构化结果，可直接接入你现有系统的选股/下单模块

依赖：pandas, numpy
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List


# ----------------------------------------------------------------------
# 1. 基础工具：找 swing low / swing high（分形法）
# ----------------------------------------------------------------------

def find_swing_points(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    在 df（须含 high, low 列，index 为时间或自然序号）上标记 swing low / swing high。
    window: 左右各看几根K线来确认局部极值（分形阶数）。

    返回新增两列的 df:
      is_swing_low  : bool
      is_swing_high : bool
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
    pattern: str                 # 形态名称（中文）
    idx1: int                    # 第1个低点位置(索引)
    idx2: int                    # 第2个低点位置
    idx3: int                    # 第3个低点位置
    low1: float
    low2: float
    low3: float
    mid_high: float              # 1-2之间和2-3之间的高点(取较高者)
    confidence: float            # 0~1 简单打分
    note: str = ""


# ----------------------------------------------------------------------
# 3. 核心分类逻辑
# ----------------------------------------------------------------------

def _pct_diff(a: float, b: float) -> float:
    """相对百分比差，避免除零"""
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base


def classify_triple(
    low1: float, low2: float, low3: float,
    mid_high_12: float, mid_high_23: float,
    broke_support_23: bool,       # 第2或第3次是否跌破了前面的支撑但又拉回(失败突破)
    flat_tol: float = 0.02,       # 判定"基本持平"的容差, 默认2%（真实市场建议1-3%）
) -> tuple[str, float, str]:
    """
    根据三个低点及中间高点关系，返回 (形态名, 置信度, 备注)
    这是规则打分，不是严格数学证明，实际用时可结合成交量/均线进一步过滤。
    """

    d12 = _pct_diff(low1, low2)
    d23 = _pct_diff(low2, low3)
    d13 = _pct_diff(low1, low3)

    descending = (low1 > low2 > low3) or (
        low1 >= low2 * (1 - flat_tol) and low2 > low3
    )  # 低点依次降低（楔形）
    ascending = (low1 < low2 < low3)  # 低点依次抬高
    flat_all = d12 <= flat_tol and d23 <= flat_tol  # 三点基本持平

    mid_high = max(mid_high_12, mid_high_23)

    # --- 1. 完美三重底：三点几乎持平 ---
    if flat_all:
        return "完美三重底 (Perfect Triple Bottom)", 0.9, \
            f"三低点差异 {max(d12, d23):.2%}，接近持平"

    # --- 2. 头肩底：中间低点明显更低，两边高 ---
    if low2 < low1 and low2 < low3 and d12 > flat_tol and d23 > flat_tol:
        # 两肩(low1, low3)相对接近
        shoulder_diff = _pct_diff(low1, low3)
        conf = 0.85 if shoulder_diff < 0.02 else 0.65
        return "头肩底/截断楔形 (Head & Shoulders Bottom)", conf, \
            f"中间低点更低(头部)，两肩差异 {shoulder_diff:.2%}"

    # --- 6. 抬高双底失败突破型：低点持续抬高 + 出现失败下破 ---
    if ascending and broke_support_23:
        return "抬高双底失败突破型 (Failed BO below HL DB)", 0.8, \
            "低点逐级抬高(HL)，且第3次出现跌破支撑后被拉回"

    # --- 3 / 5. 有跌破支撑但拉回：双底跌破失败型 / 双底回调型 ---
    if broke_support_23:
        # 若第3个低点相对第2个变化不大，属于"回调再确认"型
        if d23 <= flat_tol * 3:
            return "双底回调型 (Double Bottom Pullback)", 0.75, \
                "双底确立后价格回踩，第3低点贴近前低"
        else:
            return "双底跌破失败型 (Failed BO below DB)", 0.75, \
                "价格短暂跌破前低支撑但迅速拉回"

    # --- 4. 楔形三重底：低点依次降低，通道收窄 ---
    if descending and not flat_all:
        return "楔形三重底 (Wedge)", 0.7, \
            f"低点依次降低 low1>{low1:.4f} > low2>{low2:.4f} > low3>{low3:.4f}"

    # --- 7. 三角形三重底：低点抬高 + 高点降低（需要额外传入高点序列判断，这里给出基础判断） ---
    if ascending and mid_high_12 > mid_high_23:
        return "三角形三重底 (Triangle)", 0.65, \
            "低点抬高，同时中间高点走低，形成收敛三角形"

    return "未分类三次探底 (Unclassified 3-push)", 0.4, \
        "满足三次探低但未匹配到具体子形态，建议人工复核"


# ----------------------------------------------------------------------
# 4. 主扫描函数：输入单支股票OHLC数据，输出候选三重底形态
# ----------------------------------------------------------------------

def scan_triple_bottoms(
    df: pd.DataFrame,
    symbol: str = "",
    swing_window: int = 3,
    lookback_bars: int = 150,          # 只在最近 N 根K线内寻找形态
    max_spacing: int = 80,             # 三个低点之间最大跨度(K线数)，太远则不算同一形态
    min_spacing: int = 3,              # 三个低点之间最小跨度，太近视为噪音
    break_tol: float = 0.01,           # 判定"跌破支撑"的容差(相对百分比)，默认1%
    flat_tol: float = 0.02,            # 判定"基本持平"的容差，默认2%
) -> List[PatternMatch]:
    """
    df 需含列: open, high, low, close (index 建议为日期或整数序号，按时间升序排列)
    返回按时间倒序排列的 PatternMatch 列表(最近的形态排前面)
    """
    if len(df) < swing_window * 2 + 10:
        return []

    df = df.tail(lookback_bars).reset_index(drop=True)

    # 列名统一转小写，兼容 fetch_data 返回的 Open/High/Low/Close 和小写两种形式
    df.columns = [str(c).lower() for c in df.columns]

    df = find_swing_points(df, window=swing_window)

    swing_low_idx = df.index[df["is_swing_low"]].tolist()
    swing_high_idx = df.index[df["is_swing_high"]].tolist()

    matches: List[PatternMatch] = []

    # 在所有 swing low 中枚举三个一组的组合（相邻的三个低点，效率高、逻辑贴合"三次探底"）
    for a in range(len(swing_low_idx) - 2):
        i1, i2, i3 = swing_low_idx[a], swing_low_idx[a + 1], swing_low_idx[a + 2]

        spacing_12 = i2 - i1
        spacing_23 = i3 - i2
        if not (min_spacing <= spacing_12 <= max_spacing):
            continue
        if not (min_spacing <= spacing_23 <= max_spacing):
            continue

        low1, low2, low3 = df.loc[i1, "low"], df.loc[i2, "low"], df.loc[i3, "low"]

        # 找 1-2 之间 与 2-3 之间 的最高点（用来判断头肩底"肩部"抬高 / 三角形收敛）
        seg_12 = df.loc[i1:i2, "high"]
        seg_23 = df.loc[i2:i3, "high"]
        mid_high_12 = seg_12.max() if len(seg_12) else np.nan
        mid_high_23 = seg_23.max() if len(seg_23) else np.nan

        # 判断第2或第3次探低时，是否出现了"跌破前面支撑但又快速拉回"的失败突破特征
        support_level = min(low1, low2)
        broke = False
        # 看 i2~i3 区间内的最低点是否短暂跌破 support_level*(1-break_tol) 后收盘拉回到支撑之上
        seg_break = df.loc[i2:i3]
        if len(seg_break):
            min_low_in_seg = seg_break["low"].min()
            close_at_end = df.loc[i3, "close"]
            if min_low_in_seg < support_level * (1 - break_tol) and close_at_end > support_level:
                broke = True

        pattern, conf, note = classify_triple(
            low1, low2, low3, mid_high_12, mid_high_23, broke,
            flat_tol=flat_tol
        )

        matches.append(PatternMatch(
            symbol=symbol,
            pattern=pattern,
            idx1=i1, idx2=i2, idx3=i3,
            low1=float(low1), low2=float(low2), low3=float(low3),
            mid_high=float(max(mid_high_12, mid_high_23)),
            confidence=conf,
            note=note,
        ))

    # 最近的排前面
    matches.sort(key=lambda m: m.idx3, reverse=True)
    return matches


# ----------------------------------------------------------------------
# 5. 多股票批量扫描（接入你自己的数据源）
# ----------------------------------------------------------------------

def scan_universe(
    data_dict: dict[str, pd.DataFrame],
    min_confidence: float = 0.6,
    **scan_kwargs,
) -> pd.DataFrame:
    """
    data_dict: {symbol: df}，df 需含 open/high/low/close
    返回汇总 DataFrame，按 confidence 降序排列，只保留最近一次匹配（每个symbol）
    """
    rows = []
    for symbol, df in data_dict.items():
        try:
            results = scan_triple_bottoms(df, symbol=symbol, **scan_kwargs)
        except Exception as e:
            print(f"[WARN] {symbol} 扫描出错: {e}")
            continue
        if not results:
            continue
        best = results[0]  # 最近一次形态
        if best.confidence < min_confidence:
            continue
        rows.append({
            "symbol": best.symbol,
            "pattern": best.pattern,
            "confidence": best.confidence,
            "low1": best.low1,
            "low2": best.low2,
            "low3": best.low3,
            "idx1": best.idx1,
            "idx2": best.idx2,
            "idx3": best.idx3,
            "note": best.note,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "symbol", "pattern", "confidence", "low1", "low2", "low3",
            "idx1", "idx2", "idx3", "note"
        ])

    out = pd.DataFrame(rows).sort_values("confidence", ascending=False).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------
# 6. 示例：如何接入你自己的系统
# ----------------------------------------------------------------------

if __name__ == "__main__":
    # ------- 用随机模拟数据演示，实际使用时替换为你的行情数据 -------
    rng = np.random.default_rng(42)

    def fake_ohlc(n=150, seed_shift=0.0):
        base = 100 + seed_shift
        noise = np.cumsum(rng.normal(0, 0.6, n))
        close = base + noise
        # 人为压出一个"三重底"形态，方便验证代码能跑通
        dip_start = n // 3
        close[dip_start:dip_start + 30] -= np.linspace(0, 6, 30)
        close[dip_start + 30:dip_start + 60] += np.linspace(0, 5, 30)
        high = close + rng.uniform(0.1, 0.6, n)
        low = close - rng.uniform(0.1, 0.6, n)
        open_ = close + rng.normal(0, 0.2, n)
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})

    demo_data = {
        "STOCK_A": fake_ohlc(seed_shift=0),
        "STOCK_B": fake_ohlc(seed_shift=5),
        "STOCK_C": fake_ohlc(seed_shift=-3),
    }

    result_df = scan_universe(demo_data, min_confidence=0.3)
    print(result_df.to_string(index=False))
