"""
launch_box_scanner.py
======================================================================
🚀 长周期趋势启动点 · 矩形中枢蓄势突破 (Trend Launch Box Scanner) 量化算法引擎
基于 9 只标杆历史案例（洛阳钼业、MARA、TSLA、东芯股份、301151冠龙节能、OXY西方石油、五粮液等）
总结的四维右侧量化体系：

【核心量化几何结构】
  1. 矩形中枢蓄势 (Consolidation Box):
     35 ~ 55 个交易日（约 1.5 ~ 2.5 个月）横盘箱体，明确测算 Box High (箱顶/颈线) 与 Box Low (箱底/支撑)
  2. 波动率极致挤压 (TTM Squeeze / Bollinger Bandwidth Compression):
     箱体内日线布林带宽度 (BB Width) 压缩至极窄冰点 (蓝筹股 ≤ 0.08，成长股 ≤ 0.22)
  3. 突破放量与量创新高 (Volume Surge & Institutional Climax):
     突破日成交量放量 ≥ 1.30 ~ 3.0+ 倍，或创出近 60 日成交量新高
  4. 宏观大周期共振 (Macro Alignment & Zero-Cross):
     年线偏离度 Bias250 处于黄金安全区间 (-15% ~ +35%)，周线 EMA10/20 多头排列且周线 MACD 向上发散
  5. 斐波那契目标测算体系:
     - 入场位 (Entry): 箱顶价格 (Box High)
     - 止损位 (Stop Loss): 箱底 (Box Low) 或 箱中轴 (Box Mid)
     - TP1 (1.000x 箱高): 经典箱体对翻测量目标
     - TP2 (2.000x 箱高): 翻倍主升目标
     - TP3 (4.236x 箱高): 斐波那契超级黄金浪扩展目标
======================================================================
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple
from datetime import datetime


@dataclass
class LaunchBoxMatch:
    symbol: str
    name: str = ""
    period: str = "1d"
    direction: str = "bullish"       # 趋势启动方向 (bullish)
    pattern: str = "🚀 矩形蓄势突破"   # 启动子形态
    tier: str = "👑 史诗级标杆"       # 评级等级
    quality_score: int = 85          # 右侧当下量化评分 (0~100)
    
    # 矩形箱体几何结构
    box_start_date: str = ""
    box_end_date: str = ""
    box_bars: int = 42
    box_high: float = 0.0            # 箱顶 (颈线 / 阻力)
    box_low: float = 0.0             # 箱底 (支撑)
    box_height: float = 0.0          # 箱体高度
    box_height_pct: float = 0.0      # 箱体振幅百分比
    
    # 突破点与交易计划
    breakout_date: str = ""
    breakout_price: float = 0.0
    latest_close: float = 0.0
    entry_price: float = 0.0         # 建议入场位
    stop_loss: float = 0.0           # 建议止损位
    tp1: float = 0.0                 # TP1 (1.0x 箱高)
    tp2: float = 0.0                 # TP2 (2.0x 箱高)
    tp3: float = 0.0                 # TP3 (4.236x 黄金主升目标)
    risk: float = 0.0                # 风险点数
    reward_tp1: float = 0.0
    reward_tp2: float = 0.0
    reward_tp3: float = 0.0
    risk_reward: float = 2.0         # TP2 盈亏比
    rr_tp3: float = 4.2              # TP3 盈亏比
    
    # 微观与宏观核心指标
    vol_ratio: float = 1.8           # 突破日成交量对比20日均量倍数
    is_vol_new_high: bool = False    # 成交量是否创近60日新高
    min_bb_width: float = 0.08       # 箱体内布林带最小宽度 (收敛程度)
    squeeze_bars: int = 12           # TTM 挤压天数
    bias_250: float = 0.15           # 年线偏离度 (Close - MA250)/MA250
    w_bullish: bool = True           # 周线 EMA10 >= EMA20
    w_macd_up: bool = True           # 周线 MACD 动能向上
    
    # 状态与进度
    status: str = "early"            # active (蓄势中), early (刚突破<=20%), mid (推进中), far (>100%), invalidated
    status_reason: str = ""
    breakout_progress: float = 0.0   # 突破推进百分比 (%)
    bars_since_breakout: int = 0
    scan_time: str = ""
    note: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def calculate_launch_box(
    df: pd.DataFrame,
    symbol: str = "",
    name: str = "",
    period: str = "1d",
    lookback_box: int = 42,
    min_box_bars: int = 30
) -> List[LaunchBoxMatch]:
    """
    扫描单一品种的全量历史或近期走势，返回符合「矩形中枢蓄势突破」的信号列表
    """
    if df is None or len(df) < max(lookback_box + 20, 60):
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.columns = [str(c).capitalize() for c in df.columns]
    if "Close" not in df.columns:
        return []

    # 1. 计算基础指标
    df['SMA20'] = df['Close'].rolling(20).mean()
    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()
    df['SMA250'] = df['Close'].rolling(250).mean()
    df['Bias_250'] = (df['Close'] - df['SMA250']) / df['SMA250']

    # 成交量
    df['VOL_MA20'] = df['Volume'].rolling(20).mean()
    df['Vol_Ratio'] = df['Volume'] / df['VOL_MA20'].replace(0, np.nan)
    df['Vol_Max_60'] = df['Volume'].shift(1).rolling(60).max()
    df['Is_Vol_New_High'] = df['Volume'] > df['Vol_Max_60']

    # 布林带与 TTM Squeeze
    df['BB_Std'] = df['Close'].rolling(20).std()
    df['BB_Upper'] = df['SMA20'] + 2 * df['BB_Std']
    df['BB_Lower'] = df['SMA20'] - 2 * df['BB_Std']
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['SMA20'].replace(0, np.nan)
    df['Min_BB_Width_20'] = df['BB_Width'].shift(1).rolling(20).min()

    # 肯特纳通道与挤压计数
    df['TR'] = np.maximum(
        df['High'] - df['Low'],
        np.maximum(abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1)))
    )
    df['ATR14'] = df['TR'].rolling(14).mean()
    df['KC_Upper'] = df['SMA20'] + 1.5 * df['ATR14']
    df['KC_Lower'] = df['SMA20'] - 1.5 * df['ATR14']
    df['Squeeze_On'] = (df['BB_Lower'] > df['KC_Lower']) & (df['BB_Upper'] < df['KC_Upper'])
    df['Squeeze_Count'] = df['Squeeze_On'].rolling(30).sum()

    # 日线 MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 周线级别指标
    try:
        df_w = df.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        df_w['W_EMA10'] = df_w['Close'].ewm(span=10, adjust=False).mean()
        df_w['W_EMA20'] = df_w['Close'].ewm(span=20, adjust=False).mean()
        df_w['W_Bullish'] = df_w['W_EMA10'] >= df_w['W_EMA20']
        w12 = df_w['Close'].ewm(span=12, adjust=False).mean()
        w26 = df_w['Close'].ewm(span=26, adjust=False).mean()
        df_w['W_MACD'] = w12 - w26
        df_w['W_MACD_Signal'] = df_w['W_MACD'].ewm(span=9, adjust=False).mean()
        df_w['W_MACD_Hist'] = df_w['W_MACD'] - df_w['W_MACD_Signal']

        df = df.merge(df_w[['W_EMA10', 'W_EMA20', 'W_Bullish', 'W_MACD', 'W_MACD_Hist']],
                      left_index=True, right_index=True, how='left').ffill()
    except Exception:
        df['W_Bullish'] = True
        df['W_MACD_Hist'] = 0.1

    # 箱体定义 (过去 lookback_box 根 K 线的极值)
    df['Box_High'] = df['High'].shift(1).rolling(lookback_box).max()
    df['Box_Low'] = df['Low'].shift(1).rolling(lookback_box).min()

    matches: List[LaunchBoxMatch] = []
    n = len(df)
    latest_bar_close = float(df['Close'].iloc[-1])

    # 遍历检测历史突破点与当前蓄势状态
    for i in range(max(lookback_box + 5, 50), n):
        dt = df.index[i]
        c = float(df['Close'].iloc[i])
        prev_c = float(df['Close'].iloc[i - 1])
        box_h = float(df['Box_High'].iloc[i])
        box_l = float(df['Box_Low'].iloc[i])
        box_hgt = max(box_h - box_l, box_h * 0.02)
        box_hgt_pct = round(box_hgt / max(0.001, box_l) * 100, 2)

        vol_r = float(df['Vol_Ratio'].iloc[i]) if pd.notna(df['Vol_Ratio'].iloc[i]) else 1.0
        min_bb = float(df['Min_BB_Width_20'].iloc[i]) if pd.notna(df['Min_BB_Width_20'].iloc[i]) else 0.20
        bias250 = float(df['Bias_250'].iloc[i]) if pd.notna(df['Bias_250'].iloc[i]) else 0.0
        is_vol_high = bool(df['Is_Vol_New_High'].iloc[i]) if pd.notna(df['Is_Vol_New_High'].iloc[i]) else False
        sqz_cnt = int(df['Squeeze_Count'].iloc[i]) if pd.notna(df['Squeeze_Count'].iloc[i]) else 0
        w_bull = bool(df['W_Bullish'].iloc[i]) if pd.notna(df['W_Bullish'].iloc[i]) else True

        w_macd_h = float(df['W_MACD_Hist'].iloc[i]) if pd.notna(df['W_MACD_Hist'].iloc[i]) else 0.0
        prev_w_macd_h = float(df['W_MACD_Hist'].iloc[max(0, i - 5)]) if pd.notna(df['W_MACD_Hist'].iloc[max(0, i - 5)]) else 0.0
        w_macd_up = (w_macd_h > 0 and w_macd_h > prev_w_macd_h) or (w_macd_h > prev_w_macd_h)

        # 判定突破：当日收盘大于等于箱顶，且前一日收盘小于箱顶
        is_breakout = (c >= box_h) and (prev_c < box_h)
        # 判定在箱体内蓄势中（适用于最靠近右侧的现行K线）
        is_active_box = (i == n - 1) and (c < box_h) and (c >= box_l) and (min_bb <= 0.25) and (sqz_cnt >= 4)

        if not (is_breakout or is_active_box):
            continue

        # 波动率与成交量确认条件
        if is_breakout:
            if min_bb > 0.35:  # 振幅未收敛
                continue
            if vol_r < 1.25:   # 量能不足
                continue
            if c < df['SMA20'].iloc[i]:
                continue

        # 冷却期去重（40天内不重复触发同一箱体突破）
        dt_str = dt.strftime('%Y-%m-%d')
        if matches and is_breakout:
            last_dt = datetime.strptime(matches[-1].breakout_date, '%Y-%m-%d')
            cur_dt = datetime.strptime(dt_str, '%Y-%m-%d')
            if (cur_dt - last_dt).days < 35:
                continue

        # ── 右侧当下量化打分体系 (0 ~ 100 分) ──
        s20 = float(df['SMA20'].iloc[i])
        s50 = float(df['SMA50'].iloc[i]) if pd.notna(df['SMA50'].iloc[i]) else s20
        s200 = float(df['SMA200'].iloc[i]) if pd.notna(df['SMA200'].iloc[i]) else s20

        # 1. 均线大周期排列分 (0~25)
        ma_score = 0
        if c > s20 and s20 > s50: ma_score += 10
        if c > s200: ma_score += 8
        if w_bull: ma_score += 7

        # 2. 机构量能爆发分 (0~25)
        vol_score = 0
        if vol_r >= 3.0: vol_score += 15
        elif vol_r >= 1.8: vol_score += 10
        else: vol_score += 6
        if is_vol_high: vol_score += 10

        # 3. 挤压蓄势深度分 (0~20)
        sqz_score = 0
        if sqz_cnt >= 12 or min_bb <= 0.08: sqz_score = 20
        elif sqz_cnt >= 6 or min_bb <= 0.16: sqz_score = 14
        else: sqz_score = 8

        # 4. 年线偏离度安全区 (0~15)
        bias_score = 0
        if -0.10 <= bias250 <= 0.35: bias_score = 15
        elif -0.20 <= bias250 <= 0.50: bias_score = 10
        else: bias_score = 3

        # 5. 周线 MACD 动能分 (0~15)
        w_score = 15 if (w_macd_h > 0 and w_macd_up) else (10 if w_macd_up else 4)

        quality_score = min(100, ma_score + vol_score + sqz_score + bias_score + w_score)

        # 评级划定
        if quality_score >= 90:
            tier = "👑 史诗级标杆"
            patt_name = "👑 史诗级长周期主升浪"
        elif quality_score >= 75:
            tier = "🔥 优质主升浪"
            patt_name = "🚀 矩形中枢蓄势突破"
        elif quality_score >= 60:
            tier = "⚡ 标准中枢波段"
            patt_name = "⚡ 紧凑收敛箱体突破"
        else:
            tier = "👀 观察级"
            patt_name = "👀 弱蓄势波段"

        # 交易计划目标位测算
        entry_price = round(box_h, 2) if is_breakout else round(latest_bar_close, 2)
        stop_loss = round(box_l, 2)
        risk = max(0.01, round(entry_price - stop_loss, 2))
        tp1 = round(box_h + 1.0 * box_hgt, 2)
        tp2 = round(box_h + 2.0 * box_hgt, 2)
        tp3 = round(box_h + 4.236 * box_hgt, 2)

        reward_tp1 = round(tp1 - entry_price, 2)
        reward_tp2 = round(tp2 - entry_price, 2)
        reward_tp3 = round(tp3 - entry_price, 2)

        rr_tp2 = round(reward_tp2 / max(0.001, risk), 2)
        rr_tp3 = round(reward_tp3 / max(0.001, risk), 2)

        # 跑势进度测算
        if is_active_box:
            status = "active"
            prog = 0.0
            bars_since = 0
            status_reason = "箱体内蓄势挤压中，密切关注向上放量突破"
        else:
            bars_since = n - 1 - i
            # 突破后推进百分比 (以 1.0x 箱高为 100%)
            prog = round(max(0.0, (latest_bar_close - box_h) / max(0.001, box_hgt) * 100.0), 1)
            if latest_bar_close < stop_loss:
                status = "invalidated"
                status_reason = "价格跌破箱底止损位，形态失效"
            elif prog <= 20.0:
                status = "early"
                status_reason = f"刚突破箱顶 (进度 {prog}%)，处于绝佳启动入场窗口"
            elif prog <= 100.0:
                status = "mid"
                status_reason = f"主升推进中 (进度 {prog}%)，向 TP2 目标进发"
            else:
                status = "far"
                status_reason = f"已超 TP2 翻倍目标 (进度 {prog}%)"

        start_idx = max(0, i - lookback_box)
        box_start_dt_str = df.index[start_idx].strftime('%Y-%m-%d')

        m = LaunchBoxMatch(
            symbol=symbol,
            name=name or symbol,
            period=period,
            direction="bullish",
            pattern=patt_name,
            tier=tier,
            quality_score=quality_score,
            box_start_date=box_start_dt_str,
            box_end_date=dt_str,
            box_bars=lookback_box,
            box_high=round(box_h, 2),
            box_low=round(box_l, 2),
            box_height=round(box_hgt, 2),
            box_height_pct=box_hgt_pct,
            breakout_date=dt_str,
            breakout_price=round(c, 2),
            latest_close=round(latest_bar_close, 2),
            entry_price=entry_price,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            risk=risk,
            reward_tp1=reward_tp1,
            reward_tp2=reward_tp2,
            reward_tp3=reward_tp3,
            risk_reward=rr_tp2,
            rr_tp3=rr_tp3,
            vol_ratio=round(vol_r, 2),
            is_vol_new_high=is_vol_high,
            min_bb_width=round(min_bb, 2),
            squeeze_bars=sqz_cnt,
            bias_250=round(bias250, 3),
            w_bullish=w_bull,
            w_macd_up=w_macd_up,
            status=status,
            status_reason=status_reason,
            breakout_progress=prog,
            bars_since_breakout=bars_since,
            scan_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            note=f"箱体高点 {round(box_h, 2)}，放量 {round(vol_r, 2)}倍，布林压缩至 {round(min_bb, 2)}，评分 {quality_score}分"
        )
        matches.append(m)

    return matches
