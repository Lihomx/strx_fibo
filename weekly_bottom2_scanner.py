"""
weekly_bottom2_scanner.py
======================================================================
🎯 周线前底与潜在底2监测器 (Weekly Bottom 2 & Termination Zone Monitor)
核心算法引擎：
- 识别周线宏观前底 (Point 1 / 底1 / L1) 与独立颈线波峰 (Peak / 颈线)
- 终止区 (Termination Zone / 灰色框) 回踩判定 [L1, L1 * (1 + b2_buffer%)]
- 零容忍周线基准收盘价生死线 (Anchor Weekly Close: C_now >= C_base)
- 【高胜率 V2.0 升级架构】：
  1. 底部抬高过滤 (L1 之前必须存在更低的历史大底，确保属于次低点/右侧上升二浪结构)
  2. 双底时间跨度过滤 (L1 与当前底2 必须间隔 >= 4 周，坚决剔除 2~3 周急跌中继假双底)
  3. 颈线波峰反抽强度过滤 (波峰反抽 >= 10%，大资金真正介入过)
  4. 生死线安全垫超额保护 (C_now >= C_base * 1.008)
- 架构设计：模块化配置驱动 (Bottom2Config)，支持未来持续无缝热升级与扩展
======================================================================
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Callable
import concurrent.futures
import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. 算法配置驱动类 (方便后期随时升级与参数调优)
# ----------------------------------------------------------------------
@dataclass
class Bottom2Config:
    version: str = "v2_high_winrate"    # 算法版本标识 (v1_classic, v2_high_winrate, v3_volume_breakout)
    left_bars: int = 2                  # 周线左侧分型确认周数
    right_bars: int = 1                 # 周线右侧分型确认周数
    min_rebound: float = 10.0           # 颈线波峰最小反抽幅度% (V2升级为 10.0%)
    b2_buffer: float = 2.8              # 终止区(灰色框)上沿容忍上限% (默认 2.8%)
    min_spacing_weeks: int = 4          # 底1与底2最小时间间隔周数 (V2升级为 >= 4周)
    max_search_weeks: int = 25          # 向前回溯搜索周数上限
    require_not_lowest: bool = True     # 必须底部抬高 (底1非全局最低点，前期必有更低大底)
    close_safety_buffer: float = 0.8    # 周收盘生死线安全垫% (默认超额 0.8%)


# ----------------------------------------------------------------------
# 2. 匹配结果数据模型
# ----------------------------------------------------------------------
@dataclass
class Bottom2Match:
    symbol: str                         # 标的代码
    name: str                           # 标的名称
    period: str = "1w"                  # 时间周期 (周线 1w)
    curr_c: float = 0.0                 # 当前收盘价
    curr_l: float = 0.0                 # 当前周最低价
    curr_h: float = 0.0                 # 当前周最高价
    l1_val: float = 0.0                 # 底1价格 (L1)
    l1_close: float = 0.0               # 底1基准周收盘价 (C_base)
    l1_date: str = ""                   # 底1日期
    l1_idx: int = 0                     # 底1在序列中的K线序号
    prior_min: float = 0.0              # 前期更低大底价格 (若有)
    prior_diff_pct: float = 0.0         # 底部较前期大底抬高幅度%
    is_lifted: bool = False             # 是否属于底部抬高形态
    peak_val: float = 0.0               # 独立颈线波峰最高价
    peak_date: str = ""                 # 颈线波峰日期
    rebound_pct: float = 0.0            # 颈线波峰相对底1的反抽幅度%
    box_bottom: float = 0.0             # 终止区灰色框底 (L1)
    box_top: float = 0.0                # 终止区灰色框顶 (L1 * (1 + buffer))
    in_box: bool = False                # 当前价格/低点是否正在灰色框内
    close_ok: bool = False              # 当前周收盘是否守住基准生死线 (C_now >= C_base)
    close_diff_pct: float = 0.0         # 当前周收盘相对基准线的超额比例%
    weeks_spaced: int = 0               # 底1与当前潜在底2的时间跨度(周)
    status: str = "active_in_zone"      # active_in_zone(终止区潜伏), bounced_out(企稳突破拉升), held(守住观察), broken(跌破失效)
    status_label: str = ""              # 状态文字描述
    confidence: float = 0.85            # 综合置信度得分 (0.0 ~ 1.0)
    note: str = ""                      # 形态特征备注
    updated_at: str = ""                # 扫描更新时间

    def to_dict(self) -> Dict:
        return asdict(self)


# ----------------------------------------------------------------------
# 3. 核心单品种检测算法
# ----------------------------------------------------------------------
def detect_bottom2(
    df: pd.DataFrame,
    symbol: str = "",
    name: str = "",
    config: Optional[Bottom2Config] = None
) -> Optional[Bottom2Match]:
    """
    在单品种周K线数据上运行《周线前底与潜在底2》监测算法。
    df: 包含 ['Open', 'High', 'Low', 'Close'] 的 DataFrame，index 为 DatetimeIndex
    """
    if config is None:
        config = Bottom2Config()

    if df is None or len(df) < 20:
        return None

    # 标准化列名
    cols = {c.lower(): c for c in df.columns}
    if not all(k in cols for k in ['open', 'high', 'low', 'close']):
        return None

    lows = df[cols['low']].values
    highs = df[cols['high']].values
    closes = df[cols['close']].values
    dates = [str(d)[:10] for d in df.index]
    n = len(df)

    # 倒序数组：最新K线在 index 0，往前推进
    w_lows = list(lows[::-1])
    w_highs = list(highs[::-1])
    w_closes = list(closes[::-1])
    w_dates = list(dates[::-1])

    arr_len = len(w_lows)
    max_search = min(config.max_search_weeks, arr_len - config.left_bars - 1)

    l1_val = None
    l1_close = None
    l1_date = None
    l1_idx = 0
    peak_val = 0.0
    peak_date = None
    prior_min = 0.0
    prior_diff = 0.0
    is_lifted = False
    rebound = 0.0

    # 遍历寻找合格底1 (从最近符合间隔的周往前回溯)
    start_i = max(2, config.min_spacing_weeks)
    for i in range(start_i, max_search + 1):
        cand_l = float(w_lows[i])
        cand_c = float(w_closes[i])

        # 分型局部低点验证
        is_pivot = True
        for l in range(1, config.left_bars + 1):
            if i + l < arr_len and w_lows[i + l] < cand_l:
                is_pivot = False
                break
        for r in range(1, config.right_bars + 1):
            if i - r >= 0 and w_lows[i - r] < cand_l:
                is_pivot = False
                break
        if not is_pivot:
            continue

        # 检查底1与当前bar之间是否没有创更低低点 (区间未实质破位)
        no_lower = True
        max_h = 0.0
        max_h_rel_idx = 0
        for k in range(0, i):
            if w_lows[k] < cand_l * 0.998:
                no_lower = False
            if w_highs[k] > max_h:
                max_h = w_highs[k]
                max_h_rel_idx = k

        rebound = (max_h - cand_l) / cand_l * 100.0
        if not (no_lower and rebound >= config.min_rebound):
            continue

        # 检查底1之前是否存在更低大底 (底部抬高形态验证)
        prior_lows = w_lows[i + 1:]
        has_prior_lower = False
        if len(prior_lows) > 0:
            p_min = min(prior_lows)
            if p_min < cand_l * 0.985:
                has_prior_lower = True
                prior_min = p_min
                prior_diff = (cand_l - p_min) / p_min * 100.0
                is_lifted = True

        if config.require_not_lowest and not has_prior_lower:
            continue

        # 成功锁定底1
        l1_val = cand_l
        l1_close = cand_c
        l1_date = w_dates[i]
        l1_idx = i
        peak_val = max_h
        peak_date = w_dates[max_h_rel_idx]
        break

    if l1_val is None:
        return None

    # 当前行情与终止区关系测算
    curr_c = float(w_closes[0])
    curr_l = float(w_lows[0])
    curr_h = float(w_highs[0])

    box_bottom = l1_val
    box_top = l1_val * (1.0 + config.b2_buffer / 100.0)

    # 是否落入终止区灰色框
    in_box = (curr_l >= box_bottom * 0.985) and (curr_l <= box_top or curr_c <= box_top * 1.015)
    close_ok = (curr_c >= l1_close * (1.0 + config.close_safety_buffer / 100.0))
    close_diff_pct = (curr_c - l1_close) / l1_close * 100.0
    weeks_spaced = l1_idx

    # 状态定性
    if in_box and close_ok:
        status = "active_in_zone"
        status_label = "🟢 正在终止区内 (守住生死线)"
    elif curr_c > box_top and close_ok:
        status = "bounced_out"
        status_label = "🚀 企稳向上拉升 (已脱离灰框)"
    elif in_box and not close_ok:
        status = "held"
        status_label = "🟡 在框内但贴近生死线"
    else:
        status = "broken"
        status_label = "🔴 跌破生死线失效"

    # 计算综合置信度得分 (0.0 ~ 1.0)
    score = 0.70
    if is_lifted:
        score += 0.10
    if rebound >= 15.0:
        score += 0.08
    elif rebound >= 10.0:
        score += 0.05
    if weeks_spaced >= 6:
        score += 0.07
    if close_diff_pct >= 2.0:
        score += 0.05
    score = min(0.98, score)

    note = f"底1: {l1_val:.2f} ({l1_date})，反弹波峰 {peak_val:.2f} (+{rebound:.1f}%)，双底跨度 {weeks_spaced}周"
    if is_lifted:
        note += f"，较前底抬高 +{prior_diff:.1f}%"

    match = Bottom2Match(
        symbol=symbol,
        name=name or symbol,
        period="1w",
        curr_c=round(curr_c, 2),
        curr_l=round(curr_l, 2),
        curr_h=round(curr_h, 2),
        l1_val=round(l1_val, 2),
        l1_close=round(l1_close, 2),
        l1_date=l1_date,
        l1_idx=l1_idx,
        prior_min=round(prior_min, 2),
        prior_diff_pct=round(prior_diff, 1),
        is_lifted=is_lifted,
        peak_val=round(peak_val, 2),
        peak_date=peak_date,
        rebound_pct=round(rebound, 1),
        box_bottom=round(box_bottom, 2),
        box_top=round(box_top, 2),
        in_box=in_box,
        close_ok=close_ok,
        close_diff_pct=round(close_diff_pct, 2),
        weeks_spaced=weeks_spaced,
        status=status,
        status_label=status_label,
        confidence=round(score, 2),
        note=note,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    return match


# ----------------------------------------------------------------------
# 4. 批量多线程扫描引擎
# ----------------------------------------------------------------------
def scan_symbols_batch(
    symbols_with_names: List[Tuple[str, str]],
    config: Optional[Bottom2Config] = None,
    max_workers: int = 8,
    progress_cb: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict]:
    """
    多线程批量下载周线数据并运行底2扫描。
    symbols_with_names: [(symbol, name), ...]
    返回符合条件的字典列表
    """
    if config is None:
        config = Bottom2Config()

    sym_dict = {s: n for s, n in symbols_with_names}
    tickers = list(sym_dict.keys())
    if not tickers:
        return []

    logger.info(f"开始周线底2多线程批量扫描: {len(tickers)} 只标的...")
    data_w = yf.download(
        tickers,
        period="2y",
        interval="1wk",
        group_by="ticker",
        threads=True,
        progress=False
    )

    results = []
    total = len(tickers)

    for idx, sym in enumerate(tickers):
        try:
            if progress_cb:
                progress_cb(idx + 1, total, sym)

            if total == 1:
                df = data_w.dropna()
            else:
                if sym not in data_w.columns.levels[0]:
                    continue
                df = data_w[sym].dropna()

            if len(df) < 20:
                continue

            match = detect_bottom2(df, symbol=sym, name=sym_dict.get(sym, sym), config=config)
            if match and match.status in ["active_in_zone", "bounced_out", "held"]:
                results.append(match.to_dict())
        except Exception as e:
            logger.debug(f"扫描 {sym} 出现异常: {e}")
            continue

    # 排序：优先在终止区内、按置信度和安全垫排序
    results.sort(
        key=lambda x: (
            1 if x.get("status") == "active_in_zone" else (2 if x.get("status") == "bounced_out" else 3),
            -float(x.get("confidence", 0)),
            -float(x.get("close_diff_pct", 0))
        )
    )
    return results
