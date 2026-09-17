"""
page_launch_box.py
======================================================================
🚀 长周期趋势启动点 · 矩形中枢蓄势突破扫描器 (Trend Launch Box Scanner)
基于 9 只标杆历史案例量化提炼的四维右侧实盘系统：
  1. 35~55 天矩形中枢蓄势 (Consolidation Box)
  2. TTM Squeeze 深度挤压与布林带极致收窄 (BB Width Compression)
  3. 机构核爆级放量突破 (Volume Surge & 60-day Volume High)
  4. 宏观大周期顺势共振 (Weekly EMA/MACD & Annual Line Safe Zone)
  5. 右侧当下 0~100 分质量评级（完全无未来函数）
  6. 斐波那契三段目标位 (TP1 1.0x, TP2 2.0x, TP3 4.236x 黄金超级主升浪)
======================================================================
"""

import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

import importlib
import storage

if not hasattr(storage, "load_launch_box"):
    try:
        storage = importlib.reload(storage)
    except Exception:
        pass


def _safe_load_launch_box() -> List[Dict]:
    global storage
    if not hasattr(storage, "load_launch_box"):
        try:
            storage = importlib.reload(storage)
        except Exception:
            pass
    if hasattr(storage, "load_launch_box"):
        try:
            return storage.load_launch_box()
        except Exception:
            pass
    try:
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        f_path = os.path.join(base_dir, "data_launch_box.json")
        if os.path.exists(f_path):
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []


def _safe_append_launch_box_results(items: List[Dict]) -> bool:
    global storage
    if not hasattr(storage, "append_launch_box_results"):
        try:
            storage = importlib.reload(storage)
        except Exception:
            pass
    if hasattr(storage, "append_launch_box_results"):
        try:
            return storage.append_launch_box_results(items)
        except Exception:
            pass
    return False


def _safe_clear_launch_box_results() -> bool:
    global storage
    if not hasattr(storage, "clear_launch_box_results"):
        try:
            storage = importlib.reload(storage)
        except Exception:
            pass
    if hasattr(storage, "clear_launch_box_results"):
        try:
            return storage.clear_launch_box_results()
        except Exception:
            pass
    return False


def _safe_init_demo_launch_boxes() -> List[Dict]:
    global storage
    if not hasattr(storage, "init_demo_launch_boxes"):
        try:
            storage = importlib.reload(storage)
        except Exception:
            pass
    if hasattr(storage, "init_demo_launch_boxes"):
        try:
            return storage.init_demo_launch_boxes()
        except Exception:
            pass
    return []


import launch_box_scanner
import colab_launch_box_script

logger = logging.getLogger(__name__)

# 支持的周期映射
LAUNCH_BOX_TIMEFRAMES = {
    "1d":  ("1d",  "2y",  "日线 (D1)"),
    "1w":  ("1wk", "5y",  "周线 (W1)"),
    "4h":  ("1h",  "730d", "4小时 (H4)"),
    "60m": ("60m", "720d", "1小时 (H1)"),
}



def _fetch_name(ticker: str) -> str:
    """获取股票名称"""
    try:
        from page_watchlist import _fetch_ticker_name
        return _fetch_ticker_name(ticker) or ticker
    except Exception:
        return ticker


def _tv_link(ticker: str, period: str = "1d") -> str:
    """生成 TradingView 链接"""
    clean_tk = ticker.strip().upper()
    if clean_tk.endswith(".SS"):
        clean_tk = "SSE:" + clean_tk.replace(".SS", "")
    elif clean_tk.endswith(".SZ"):
        clean_tk = "SZSE:" + clean_tk.replace(".SZ", "")
    elif clean_tk.endswith(".BJ"):
        clean_tk = "BSE:" + clean_tk.replace(".BJ", "")
    return f"https://www.tradingview.com/chart/?symbol={clean_tk}"


def _sina_link(ticker: str) -> str:
    """生成新浪财经链接"""
    clean_tk = ticker.strip().upper()
    if clean_tk.endswith(".SS"):
        code = "sh" + clean_tk.replace(".SS", "")
    elif clean_tk.endswith(".SZ"):
        code = "sz" + clean_tk.replace(".SZ", "")
    elif clean_tk.endswith(".BJ"):
        code = "bj" + clean_tk.replace(".BJ", "")
    else:
        code = "gb_" + clean_tk.lower()
    return f"https://finance.sina.com.cn/realstock/company/{code}/nc.shtml"


def render_launch_box_chart(item: Dict) -> go.Figure:
    """绘制专业 TradingView 风格交互式 K 线图，还原矩形箱体、布林带挤压及斐波那契目标位"""
    ticker = item.get("symbol", "")
    entry_p = float(item.get("entry_price", 0.0))
    sl_p = float(item.get("stop_loss", 0.0))
    tp1_p = float(item.get("tp1", 0.0))
    tp2_p = float(item.get("tp2", 0.0))
    tp3_p = float(item.get("tp3", 0.0))
    box_h = float(item.get("box_high", entry_p))
    box_l = float(item.get("box_low", sl_p))
    b_start = item.get("box_start_date", "")
    b_end = item.get("breakout_date", "")

    fig = go.Figure()

    # 尝试从 yfinance 拉取绘图数据
    try:
        import yfinance as yf
        raw = yf.download(ticker, start="2015-01-01", end=datetime.now().strftime("%Y-%m-%d"), progress=False, auto_adjust=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        df = raw.dropna()
        if b_end and b_end in df.index:
            end_loc = df.index.get_loc(b_end)
            plot_df = df.iloc[max(0, end_loc - 120) : min(len(df), end_loc + 60)]
        else:
            plot_df = df.tail(150)
            
        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df['Open'],
            high=plot_df['High'],
            low=plot_df['Low'],
            close=plot_df['Close'],
            name=f"{ticker} K线",
            increasing_line_color='#22c55e',
            decreasing_line_color='#ef4444'
        ))

        # 均线
        plot_df['SMA20'] = plot_df['Close'].rolling(20).mean()
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['SMA20'],
            mode='lines', line=dict(color='#38bdf8', width=1.2),
            name='EMA/SMA 20'
        ))

        # 绘制矩形箱体 (紫色半透明蓄势框)
        if b_start and b_end:
            fig.add_shape(
                type="rect",
                x0=b_start, y0=box_l,
                x1=b_end, y1=box_h,
                line=dict(color="#a855f7", width=2, dash="solid"),
                fillcolor="rgba(168, 85, 247, 0.18)",
                name="蓄势矩形箱体"
            )
            fig.add_annotation(
                x=b_start, y=box_h,
                text=f"📦 中枢蓄势箱体 [{box_l:.2f} ~ {box_h:.2f}]",
                showarrow=False,
                yshift=14, xshift=10,
                font=dict(color="#d8b4fe", size=11, family="monospace"),
                bgcolor="rgba(15, 23, 42, 0.85)",
                bordercolor="#a855f7"
            )

        # 目标位水平虚线
        fig.add_hline(y=box_h, line_dash="dash", line_color="#a855f7", annotation_text=f"箱顶/买点: {box_h:.2f}", annotation_position="top right")
        fig.add_hline(y=sl_p, line_dash="dot", line_color="#ef4444", annotation_text=f"箱底止损: {sl_p:.2f}", annotation_position="bottom right")
        if tp1_p > 0:
            fig.add_hline(y=tp1_p, line_dash="dash", line_color="#38bdf8", annotation_text=f"TP1 (1.0x): {tp1_p:.2f}", annotation_position="top right")
        if tp2_p > 0:
            fig.add_hline(y=tp2_p, line_dash="dash", line_color="#22c55e", annotation_text=f"TP2 (2.0x): {tp2_p:.2f}", annotation_position="top right")
        if tp3_p > 0:
            fig.add_hline(y=tp3_p, line_dash="dash", line_color="#f59e0b", annotation_text=f"TP3 (4.236x): {tp3_p:.2f}", annotation_position="top right")

    except Exception:
        # 若无法拉取K线则绘制简化几何架构图
        fig.add_trace(go.Scatter(
            x=["箱体起点", "箱体突破点", "TP1目标", "TP2目标", "TP3超级目标"],
            y=[box_l, box_h, tp1_p, tp2_p, tp3_p],
            mode="lines+markers+text",
            text=[f"箱底 {box_l:.2f}", f"突破 {box_h:.2f}", f"TP1 {tp1_p:.2f}", f"TP2 {tp2_p:.2f}", f"TP3 {tp3_p:.2f}"],
            textposition="top center",
            line=dict(color="#a855f7", width=3),
            marker=dict(size=10, color=["#ef4444", "#a855f7", "#38bdf8", "#22c55e", "#f59e0b"])
        ))

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        paper_bgcolor="rgba(15, 23, 42, 0.4)",
        plot_bgcolor="rgba(15, 23, 42, 0.6)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def render():
    st.markdown(
        """
        <style>
        .lb-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .lb-title {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .lb-plan-box {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 12px 14px;
            margin-top: 8px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
        }
        .lb-plan-item {
            display: flex;
            flex-direction: column;
        }
        .lb-plan-label {
            font-size: 11px;
            color: #94a3b8;
            font-weight: 600;
        }
        .lb-plan-val {
            font-size: 14px;
            font-weight: 800;
            font-family: monospace;
            margin-top: 2px;
        }
        .score-badge {
            display: inline-block;
            font-size: 12px;
            font-weight: 800;
            padding: 2px 8px;
            border-radius: 6px;
            line-height: 1.3;
        }
        .score-epic {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(217, 119, 6, 0.4));
            color: #fef08a;
            border: 1px solid rgba(245, 158, 11, 0.8);
            box-shadow: 0 0 10px rgba(245, 158, 11, 0.25);
        }
        .score-prime {
            background: rgba(34, 197, 94, 0.25);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.6);
        }
        .score-standard {
            background: rgba(56, 189, 248, 0.2);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.4);
        }
        .lb-progress-track {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            height: 6px;
            width: 100%;
            overflow: hidden;
            margin: 6px 0;
            position: relative;
        }
        .lb-progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        .lb-pagination {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin: 14px 0;
            padding: 8px 12px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
        }
        .lb-page-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 14px;
            background: rgba(168, 85, 247, 0.15);
            color: #d8b4fe !important;
            border: 1px solid rgba(168, 85, 247, 0.35);
            border-radius: 6px;
            text-decoration: none !important;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .lb-page-btn:hover {
            background: rgba(168, 85, 247, 0.3);
            color: #ffffff !important;
            border-color: rgba(168, 85, 247, 0.7);
        }
        .lb-page-btn.disabled {
            background: rgba(148, 163, 184, 0.08);
            color: #64748b !important;
            border-color: rgba(148, 163, 184, 0.15);
            cursor: not-allowed;
            pointer-events: none;
        }
        .lb-page-info {
            color: #cbd5e1;
            font-size: 14px;
            font-weight: 600;
            text-align: center;
            flex: 1;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # 自动加载启动点数据
    all_patterns = _safe_load_launch_box()

    # ── 1. 状态映射 ──
    _STAT_OPTIONS = [
        "👀 观望蓄势中 (active 0%)",
        "🚀 刚突破 (confirmed ≤20%)",
        "⚡ 推进中 (confirmed 20~100%)",
        "🏁 已超TP2目标 (confirmed >100%)",
        "❌ 已失效 (invalidated)"
    ]
    _STAT_URL_MAP = {
        "active":      "👀 观望蓄势中 (active 0%)",
        "early":       "🚀 刚突破 (confirmed ≤20%)",
        "mid":         "⚡ 推进中 (confirmed 20~100%)",
        "far":         "🏁 已超TP2目标 (confirmed >100%)",
        "invalidated": "❌ 已失效 (invalidated)"
    }
    _STAT_REVERSE_MAP = {v: k for k, v in _STAT_URL_MAP.items()}
    _DEFAULT_STATS = ["👀 观望蓄势中 (active 0%)", "🚀 刚突破 (confirmed ≤20%)", "⚡ 推进中 (confirmed 20~100%)", "🏁 已超TP2目标 (confirmed >100%)"]

    # ── 2. 评级质量映射 ──
    _TIER_OPTIONS = [
        "全部评级 (0~100分)",
        "👑 仅看史诗级标杆 (≥90分)",
        "🔥 优质主升浪 (≥75分)",
        "⚡ 标准中枢波段 (≥60分)"
    ]
    _TIER_URL_MAP = {
        "all":      "全部评级 (0~100分)",
        "epic":     "👑 仅看史诗级标杆 (≥90分)",
        "prime":    "🔥 优质主升浪 (≥75分)",
        "standard": "⚡ 标准中枢波段 (≥60分)"
    }
    _TIER_REVERSE_MAP = {v: k for k, v in _TIER_URL_MAP.items()}

    # ── 3. 排序方式映射 ──
    _SORT_OPTIONS = [
        "👑 启动质量评分 (高 → 低)",
        "🏃 跑势进度 (低 → 高 · 优先刚突破)",
        "📊 突破放量倍数 (高 → 低)",
        "🎯 TP3 黄金盈亏比 (高 → 低)",
        "🏃 跑势进度 (高 → 低)",
        "⏱️ 突破日期 (新 → 旧)",
        "股票代码 (A → Z)"
    ]
    _SORT_URL_MAP = {
        "score_desc":    "👑 启动质量评分 (高 → 低)",
        "progress_asc":  "🏃 跑势进度 (低 → 高 · 优先刚突破)",
        "volume_desc":   "📊 突破放量倍数 (高 → 低)",
        "rr_tp3_desc":   "🎯 TP3 黄金盈亏比 (高 → 低)",
        "progress_desc": "🏃 跑势进度 (高 → 低)",
        "time_desc":     "⏱️ 突破日期 (新 → 旧)",
        "ticker_asc":    "股票代码 (A → Z)"
    }
    _SORT_REVERSE_MAP = {v: k for k, v in _SORT_URL_MAP.items()}

    # ── 4. 形态时效映射 ──
    _TIME_OPTIONS = [
        "全部时间 (不限制)",
        "🔥 近 1 个月内突破 (≤4周)",
        "🌟 近 2 个月内突破 (≤8周 · 推荐)",
        "⏱️ 近 3 个月内突破 (≤12周)",
        "🗓️ 近半年内突破 (≤26周)"
    ]
    _TIME_URL_MAP = {
        "all": "全部时间 (不限制)",
        "1m":  "🔥 近 1 个月内突破 (≤4周)",
        "2m":  "🌟 近 2 个月内突破 (≤8周 · 推荐)",
        "3m":  "⏱️ 近 3 个月内突破 (≤12周)",
        "6m":  "🗓️ 近半年内突破 (≤26周)"
    }
    _TIME_REVERSE_MAP = {v: k for k, v in _TIME_URL_MAP.items()}

    # ── 5. 从 URL 参数同步状态 ──
    _url_stat_raw = str(st.query_params.get("_stat", "")).strip().lower()
    if _url_stat_raw:
        _stats = [_STAT_URL_MAP[s.strip()] for s in _url_stat_raw.split(",") if s.strip() in _STAT_URL_MAP]
        if _stats:
            st.session_state["lb_filter_status"] = _stats
    if "lb_filter_status" not in st.session_state:
        st.session_state["lb_filter_status"] = list(_DEFAULT_STATS)

    _url_tier_raw = str(st.query_params.get("_tier", "")).strip().lower()
    if _url_tier_raw in _TIER_URL_MAP:
        st.session_state["lb_filter_tier"] = _TIER_URL_MAP[_url_tier_raw]
    elif "lb_filter_tier" not in st.session_state:
        st.session_state["lb_filter_tier"] = "全部评级 (0~100分)"

    _url_sort_raw = str(st.query_params.get("_sort", "")).strip().lower()
    if _url_sort_raw in _SORT_URL_MAP:
        st.session_state["lb_sort_by"] = _SORT_URL_MAP[_url_sort_raw]
    elif "lb_sort_by" not in st.session_state:
        st.session_state["lb_sort_by"] = _SORT_OPTIONS[0]

    _url_time_raw = str(st.query_params.get("_time", "")).strip().lower()
    if _url_time_raw in _TIME_URL_MAP:
        st.session_state["lb_filter_time"] = _TIME_URL_MAP[_url_time_raw]
    elif "lb_filter_time" not in st.session_state:
        st.session_state["lb_filter_time"] = "全部时间 (不限制)"

    _url_prog_raw = str(st.query_params.get("_prog", "")).strip()
    if _url_prog_raw.isdigit():
        st.session_state["lb_progress_slider"] = max(0, min(3000, int(_url_prog_raw)))
    elif "lb_progress_slider" not in st.session_state:
        st.session_state["lb_progress_slider"] = 3000

    _url_p_raw = str(st.query_params.get("_p", "1")).strip()
    current_page = int(_url_p_raw) if _url_p_raw.isdigit() and int(_url_p_raw) > 0 else 1

    def _sync_url_params():
        cur_stat_list = st.session_state.get("lb_filter_status", _DEFAULT_STATS)
        cur_stat_keys = [_STAT_REVERSE_MAP[s] for s in cur_stat_list if s in _STAT_REVERSE_MAP]
        st.query_params["_stat"] = ",".join(cur_stat_keys) if cur_stat_keys else "all"

        cur_tier = st.session_state.get("lb_filter_tier", "全部评级 (0~100分)")
        st.query_params["_tier"] = _TIER_REVERSE_MAP.get(cur_tier, "all")

        cur_sort = st.session_state.get("lb_sort_by", _SORT_OPTIONS[0])
        st.query_params["_sort"] = _SORT_REVERSE_MAP.get(cur_sort, "score_desc")

        cur_time = st.session_state.get("lb_filter_time", "全部时间 (不限制)")
        st.query_params["_time"] = _TIME_REVERSE_MAP.get(cur_time, "all")

        cur_prog = st.session_state.get("lb_progress_slider", 3000)
        st.query_params["_prog"] = str(cur_prog)
        st.query_params["_p"] = str(current_page)

    # ── 顶栏标题与统计指标卡 ──
    st.markdown(
        """
        <div class="lb-header">
            <div class="lb-title">
                <span>🚀 长周期趋势启动点 · 矩形蓄势突破扫描器</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption("35~55天矩形中枢蓄势 · 布林带极致收窄挤压 (TTM Squeeze) · 突破放量与量创新高 · 周线顺势共振 · 0~100分右侧质量体系")

    # 统计核心指标
    total_cnt = len(all_patterns)
    epic_cnt = sum(1 for r in all_patterns if int(r.get("quality_score", 0)) >= 90)
    early_cnt = sum(1 for r in all_patterns if r.get("status") == "early" or (r.get("status") == "confirmed" and float(r.get("breakout_progress", 0)) <= 20.0))
    active_cnt = sum(1 for r in all_patterns if r.get("status") == "active")
    avg_rr3 = round(np.mean([float(r.get("rr_tp3", 4.0)) for r in all_patterns]), 1) if all_patterns else 4.2

    c_m1, c_m2, c_m3, c_m4, c_m5 = st.columns(5)
    with c_m1:
        st.metric("🎯 扫描信号总数", f"{total_cnt} 支", help="当前数据库中所有符合矩形箱体蓄势启动的信号")
    with c_m2:
        st.metric("👑 史诗级标杆", f"{epic_cnt} 支", delta=f"{round(epic_cnt/max(1, total_cnt)*100, 1)}%", help="右侧评分 ≥ 90分，具备机构核爆量能与极致挤压")
    with c_m3:
        st.metric("🚀 刚突破 (≤20%)", f"{early_cnt} 支", help="突破箱顶在 20% 空间内，处于绝佳启动建仓窗口")
    with c_m4:
        st.metric("👀 蓄势中 (0%)", f"{active_cnt} 支", help="价格在箱体内且处于布林挤压中，未破箱顶随时爆发")
    with c_m5:
        st.metric("⚖️ 平均黄金盈亏比", f"1 : {avg_rr3}", help="达到 TP3 斐波那契超级主升目标的平均风险回报比")

    # ── 选项卡构建 ──
    tab_list, tab_colab, tab_import = st.tabs([
        "📊 启动点列表 (Card / Table / Charts)",
        "🚀 Google Colab 云端全量扫描脚本",
        "📥 导入 Colab 扫描结果 CSV / 本地即时单股扫描"
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 1: 启动点列表与筛选过滤
    # ──────────────────────────────────────────────────────────────────────────
    with tab_list:
        with st.container():
            st.markdown("##### 🔍 复合条件智能筛选")
            f_c1, f_c2, f_c3 = st.columns([1.5, 1.2, 1.3])
            with f_c1:
                st_status = st.multiselect(
                    "🚦 状态阶段过滤",
                    _STAT_OPTIONS,
                    default=st.session_state.get("lb_filter_status", _DEFAULT_STATS),
                    key="lb_filter_status_widget",
                    help="支持同时筛选处于箱体内蓄势中、刚突破或正在推进中的标的"
                )
                st.session_state["lb_filter_status"] = st_status
            with f_c2:
                st_tier = st.selectbox(
                    "👑 启动质量评级",
                    _TIER_OPTIONS,
                    index=_TIER_OPTIONS.index(st.session_state.get("lb_filter_tier", _TIER_OPTIONS[0])),
                    key="lb_filter_tier_widget"
                )
                st.session_state["lb_filter_tier"] = st_tier
            with f_c3:
                st_time = st.selectbox(
                    "⏱️ 突破时间窗口",
                    _TIME_OPTIONS,
                    index=_TIME_OPTIONS.index(st.session_state.get("lb_filter_time", _TIME_OPTIONS[0])),
                    key="lb_filter_time_widget"
                )
                st.session_state["lb_filter_time"] = st_time

            f_c4, f_c5, f_c6 = st.columns([2, 1.5, 1])
            with f_c4:
                search_query = st.text_input("🔍 搜索代码 / 名称", value="", placeholder="输入股票代码或名称关键词...", key="lb_search_query")
            with f_c5:
                sort_by = st.selectbox(
                    "↕️ 排序方式",
                    _SORT_OPTIONS,
                    index=_SORT_OPTIONS.index(st.session_state.get("lb_sort_by", _SORT_OPTIONS[0])),
                    key="lb_sort_by_widget"
                )
                st.session_state["lb_sort_by"] = sort_by
            with f_c6:
                page_size = st.selectbox("📄 每页条数", [10, 20, 50], index=0, key="lb_page_size")

            _sync_url_params()

        # 执行过滤逻辑
        filtered = []
        for r in all_patterns:
            score = int(r.get("quality_score", 0))
            if "史诗级标杆" in st_tier and score < 90:
                continue
            elif "优质主升浪" in st_tier and score < 75:
                continue
            elif "标准中枢波段" in st_tier and score < 60:
                continue

            st_val = r.get("status", "early")
            prog = float(r.get("breakout_progress", 0.0))
            matched_stat = False
            for s in st_status:
                if "观望蓄势中" in s and st_val == "active": matched_stat = True
                elif "刚突破" in s and (st_val == "early" or (st_val == "confirmed" and prog <= 20.0)): matched_stat = True
                elif "推进中" in s and (st_val == "mid" or (st_val == "confirmed" and 20.0 < prog <= 100.0)): matched_stat = True
                elif "已超TP2目标" in s and (st_val == "far" or (st_val == "confirmed" and prog > 100.0)): matched_stat = True
                elif "已失效" in s and st_val == "invalidated": matched_stat = True
            if not matched_stat:
                continue

            # 搜索过滤
            if search_query.strip():
                q = search_query.strip().upper()
                if q not in str(r.get("symbol", "")).upper() and q not in _fetch_name(str(r.get("symbol", ""))).upper():
                    continue

            filtered.append(r)

        # 排序
        if sort_by == "👑 启动质量评分 (高 → 低)":
            filtered.sort(key=lambda x: (int(x.get("quality_score", 0)), str(x.get("breakout_date", ""))), reverse=True)
        elif sort_by == "🏃 跑势进度 (低 → 高 · 优先刚突破)":
            filtered.sort(key=lambda x: (float(x.get("breakout_progress", 0.0)), -int(x.get("quality_score", 0))))
        elif sort_by == "📊 突破放量倍数 (高 → 低)":
            filtered.sort(key=lambda x: float(x.get("vol_ratio", 1.0)), reverse=True)
        elif sort_by == "🎯 TP3 黄金盈亏比 (高 → 低)":
            filtered.sort(key=lambda x: float(x.get("rr_tp3", 4.0)), reverse=True)
        elif sort_by == "🏃 跑势进度 (高 → 低)":
            filtered.sort(key=lambda x: float(x.get("breakout_progress", 0.0)), reverse=True)
        elif sort_by == "⏱️ 突破日期 (新 → 旧)":
            filtered.sort(key=lambda x: str(x.get("breakout_date", "")), reverse=True)
        elif sort_by == "股票代码 (A → Z)":
            filtered.sort(key=lambda x: str(x.get("symbol", "")).upper())

        total_items = len(filtered)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(current_page, total_pages)

        # 分页工具栏
        def _make_url(p_num: int) -> str:
            params = dict(st.query_params)
            params["_page"] = "launch_box"
            params["_p"] = str(p_num)
            return "/?" + "&".join(f"{k}={v}" for k, v in params.items())

        first_cls = "lb-page-btn disabled" if current_page <= 1 else "lb-page-btn"
        prev_cls = "lb-page-btn disabled" if current_page <= 1 else "lb-page-btn"
        next_cls = "lb-page-btn disabled" if current_page >= total_pages else "lb-page-btn"
        last_cls = "lb-page-btn disabled" if current_page >= total_pages else "lb-page-btn"

        st.markdown(
            f"""
            <div class="lb-pagination">
                <div style="display:flex;gap:6px;">
                    <a href="{_make_url(1)}" target="_self" class="{first_cls}">⏮ 首页</a>
                    <a href="{_make_url(max(1, current_page - 1))}" target="_self" class="{prev_cls}">◀ 上一页</a>
                </div>
                <div class="lb-page-info">
                    📄 第 <span style="color:#a855f7;">{current_page}</span> / {total_pages} 页 (共 <span style="color:#38bdf8;">{total_items}</span> 条有效启动信号)
                </div>
                <div style="display:flex;gap:6px;">
                    <a href="{_make_url(min(total_pages, current_page + 1))}" target="_self" class="{next_cls}">下一页 ▶</a>
                    <a href="{_make_url(total_pages)}" target="_self" class="{last_cls}">末页 ⏭</a>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        page_items = filtered[start_idx:end_idx]

        if not page_items:
            st.info("💡 当前筛选条件下暂无信号。可放宽过滤条件或切换至「🚀 Google Colab 全量扫描」运行新一轮扫描。")

        # 遍历渲染每一张卡片
        for idx, item in enumerate(page_items):
            sym = item.get("symbol", "")
            nm = item.get("name") or _fetch_name(sym)
            score = int(item.get("quality_score", 85))
            b_date = item.get("breakout_date", "")
            b_high = float(item.get("box_high", 0.0))
            b_low = float(item.get("box_low", 0.0))
            entry_p = float(item.get("entry_price", b_high))
            sl_p = float(item.get("stop_loss", b_low))
            tp1_p = float(item.get("tp1", 0.0))
            tp2_p = float(item.get("tp2", 0.0))
            tp3_p = float(item.get("tp3", 0.0))
            rr3 = float(item.get("rr_tp3", 4.0))
            vol_r = float(item.get("vol_ratio", 1.8))
            min_bb = float(item.get("min_bb_width", 0.08))
            sqz_bars = int(item.get("squeeze_bars", 12))
            bias250 = float(item.get("bias_250", 0.15))
            prog = float(item.get("breakout_progress", 0.0))
            st_val = item.get("status", "early")
            note = item.get("note", "")

            # 评分徽章样式
            if score >= 90:
                score_badge_html = f"<span class='score-badge score-epic'>👑 {score}分 · 史诗级标杆</span>"
            elif score >= 75:
                score_badge_html = f"<span class='score-badge score-prime'>🔥 {score}分 · 优质主升</span>"
            else:
                score_badge_html = f"<span class='score-badge score-standard'>⚡ {score}分 · 标准波段</span>"

            # 状态徽章
            if st_val == "active":
                stat_html = "<span style='font-size:12px;background:rgba(59,130,246,0.2);color:#93c5fd;border:1px solid rgba(59,130,246,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>👀 蓄势成型中 (0%)</span>"
            elif prog <= 20.0:
                stat_html = f"<span style='font-size:12px;background:rgba(234,88,12,0.2);color:#fdba74;border:1px solid rgba(234,88,12,0.6);padding:2px 8px;border-radius:4px;font-weight:700;'>🚀 刚突破 ({prog}%)</span>"
            elif prog <= 100.0:
                stat_html = f"<span style='font-size:12px;background:rgba(34,197,94,0.2);color:#86efac;border:1px solid rgba(34,197,94,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>⚡ 推进中 ({prog}%)</span>"
            else:
                stat_html = f"<span style='font-size:12px;background:rgba(168,85,247,0.2);color:#d8b4fe;border:1px solid rgba(168,85,247,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>🏁 已达标 ({prog}%)</span>"

            # 渲染卡片头部
            with st.expander(f"📦 【{score}分】{sym} {nm} · 突破日 {b_date} · 放量 {vol_r}x · 进度 {prog}%", expanded=(idx < 2)):
                c_hd1, c_hd2 = st.columns([3, 1])
                with c_hd1:
                    st.markdown(
                        f"""
                        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px;">
                            <span style="font-size:18px;font-weight:800;color:#f8fafc;">{sym} · {nm}</span>
                            {score_badge_html}
                            {stat_html}
                            <span style="font-size:12px;background:rgba(148,163,184,0.15);color:#cbd5e1;padding:2px 8px;border-radius:4px;">⏱️ 突破日: {b_date}</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                with c_hd2:
                    st.markdown(
                        f"""
                        <div style="display:flex;gap:8px;justify-content:flex-end;">
                            <a href="{_tv_link(sym)}" target="_blank" style="font-size:12px;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:4px 8px;border-radius:4px;text-decoration:none;font-weight:600;">📈 TradingView</a>
                            <a href="{_sina_link(sym)}" target="_blank" style="font-size:12px;background:rgba(234,88,12,0.15);color:#fb923c;border:1px solid rgba(234,88,12,0.4);padding:4px 8px;border-radius:4px;text-decoration:none;font-weight:600;">📰 新浪行情</a>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # 跑势进度条
                p_width = min(100, max(5, int(prog))) if prog > 0 else 5
                p_color = "#22c55e" if prog <= 100 else "#f59e0b"
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#94a3b8;margin-bottom:2px;">
                        <span>🏃 突破推进进度: <b style="color:{p_color};">{prog}%</b></span>
                        <span>0% (箱顶) ──── 100% (TP1对翻) ──── 200% (TP2翻倍) ──── 423.6% (TP3极值)</span>
                    </div>
                    <div class="lb-progress-track">
                        <div class="lb-progress-fill" style="width:{p_width}%;background:{p_color};"></div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # 关键价位与硬指标网格
                st.markdown(
                    f"""
                    <div class="lb-plan-box">
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">📦 箱顶 (买点)</span>
                            <span class="lb-plan-val" style="color:#a855f7;">{b_high:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">📦 箱底 (支撑)</span>
                            <span class="lb-plan-val" style="color:#94a3b8;">{b_low:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">🛑 止损位 (SL)</span>
                            <span class="lb-plan-val" style="color:#f87171;">{sl_p:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">🎯 TP1 (1.0x高度)</span>
                            <span class="lb-plan-val" style="color:#38bdf8;">{tp1_p:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">🚀 TP2 (2.0x高度)</span>
                            <span class="lb-plan-val" style="color:#4ade80;">{tp2_p:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">👑 TP3 (4.236x极值)</span>
                            <span class="lb-plan-val" style="color:#fbbf24;">{tp3_p:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">⚖️ 盈亏比 (TP3)</span>
                            <span class="lb-plan-val" style="color:#f59e0b;">1 : {rr3:.1f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">📊 突破放量</span>
                            <span class="lb-plan-val" style="color:#38bdf8;">{vol_r:.2f} 倍</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">🤏 布林带最小宽</span>
                            <span class="lb-plan-val" style="color:#a855f7;">{min_bb:.2f}</span>
                        </div>
                        <div class="lb-plan-item">
                            <span class="lb-plan-label">🌐 年线偏离</span>
                            <span class="lb-plan-val" style="color:#94a3b8;">{bias250*100:+.1f}%</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if note:
                    st.caption(f"💡 **结构特征与复盘备注**：{note}")

                # 交互式图表展示
                fig = render_launch_box_chart(item)
                st.plotly_chart(fig, use_container_width=True, key=f"lb_chart_{sym}_{b_date}")

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 2: Google Colab 云端全量极速扫描脚本
    # ──────────────────────────────────────────────────────────────────────────
    with tab_colab:
        st.markdown("#### 🚀 一键生成 Google Colab 云端高并发全量扫描脚本")
        st.caption("Google Colab 云端拥有 50+ 线程高并发引擎，可在 2~3 分钟内极速扫完 6,000+ 支美股/A股全市场！扫描完毕自动下载 CSV 文件，导入本平台即可直接展现！")

        colab_c1, colab_c2 = st.columns([1.5, 1])
        with colab_c1:
            try:
                from assets import ASSET_GROUPS
                group_names = list(ASSET_GROUPS.keys())
            except Exception:
                group_names = []

            pool_options = ["🌐 全量A股 (约 5,000 支)", "🇺🇸 全量美股 (约 4,000 支)", "⭐ 自选股票池", "🔥 热门资产组"]
            if group_names:
                pool_options.extend([f"📁 分组: {g}" for g in group_names])

            selected_pool = st.selectbox("📋 选择扫描股票池", pool_options, index=0, key="lb_colab_pool_sel")

        with colab_c2:
            vol_opt = st.selectbox(
                "📊 最低成交量过滤",
                [
                    "🔥 20日均量 ≥ 10 万股 (推荐 · 剔除仙股)",
                    "🔥 20日均量 ≥ 30 万股",
                    "🔥 20日均量 ≥ 50 万股",
                    "全部扫描 (不限制成交量)"
                ],
                index=0,
                key="lb_colab_vol_sel"
            )
            _VOL_M = {
                "🔥 20日均量 ≥ 10 万股 (推荐 · 剔除仙股)": 100000,
                "🔥 20日均量 ≥ 30 万股": 300000,
                "🔥 20日均量 ≥ 50 万股": 500000,
                "全部扫描 (不限制成交量)": 0
            }
            min_vol_val = _VOL_M.get(vol_opt, 100000)

        # 准备待导出股票列表
        all_syms = []
        try:
            if hasattr(storage, "load_symbols"):
                all_syms = storage.load_symbols() or []
            elif hasattr(storage, "load_universe"):
                all_syms = storage.load_universe() or []
            else:
                import os
                base_dir = os.path.dirname(os.path.abspath(__file__))
                f_path = os.path.join(base_dir, "data_symbols.json")
                if os.path.exists(f_path):
                    with open(f_path, "r", encoding="utf-8") as f:
                        all_syms = json.load(f)
        except Exception:
            all_syms = []

        export_tickers = []
        if "全量A股" in selected_pool:
            export_tickers = [s["ticker"] for s in all_syms if isinstance(s, dict) and (s.get("ticker", "").endswith(".SS") or s.get("ticker", "").endswith(".SZ") or s.get("ticker", "").endswith(".BJ") or s.get("ticker", "").isdigit())]
            if not export_tickers:
                export_tickers = ["603993.SS", "301151.SZ", "600487.SS", "688110.SS", "002475.SZ", "000858.SZ", "600519.SS", "300750.SZ"]
        elif "全量美股" in selected_pool:
            export_tickers = [s["ticker"] for s in all_syms if isinstance(s, dict) and not (s.get("ticker", "").endswith(".SS") or s.get("ticker", "").endswith(".SZ") or s.get("ticker", "").endswith(".BJ") or s.get("ticker", "").isdigit())]
            if not export_tickers:
                export_tickers = ["MARA", "TSLA", "MRVL", "OXY", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META"]
        elif "自选" in selected_pool:
            try:
                wl = storage.load_watchlist() if hasattr(storage, "load_watchlist") else []
            except Exception:
                wl = []
            export_tickers = [w.get("ticker", "") for w in wl if isinstance(w, dict) and w.get("ticker")]
            if not export_tickers:
                export_tickers = ["MARA", "TSLA", "603993.SS", "301151.SZ", "OXY"]
        elif selected_pool.startswith("📁 分组:"):
            g_name = selected_pool.replace("📁 分组: ", "").strip()
            try:
                from assets import ASSET_GROUPS
                export_tickers = ASSET_GROUPS.get(g_name, [])
            except Exception:
                export_tickers = []
        else:
            export_tickers = [s["ticker"] for s in all_syms if isinstance(s, dict) and s.get("ticker")]

        export_tickers = list(dict.fromkeys([t.strip().upper() for t in export_tickers if t]))
        st.info(f"📋 当前股票池共 **{len(export_tickers)}** 支标的 | 周期: **日线 (D1)** | 算法: **35~55天矩形中枢蓄势 + 布林带挤压 + 放量突破**")

        colab_code = colab_launch_box_script.generate_colab_script_for_tickers(
            export_tickers, pool_name=selected_pool, selected_tfs=["1d"], min_volume=min_vol_val
        )

        st.code(colab_code, language="python", line_numbers=True)

        c_act1, c_act2 = st.columns(2)
        with c_act1:
            st.download_button(
                "📥 下载完整 Colab 扫描脚本 (.py)",
                data=colab_code,
                file_name=f"launch_box_scan_{len(export_tickers)}tickers.py",
                mime="text/x-python",
                use_container_width=True
            )
        with c_act2:
            st.link_button("🌐 打开 Google Colab", "https://colab.research.google.com/", use_container_width=True)

    # ──────────────────────────────────────────────────────────────────────────
    # TAB 3: 导入 CSV 与本地即时单股扫描
    # ──────────────────────────────────────────────────────────────────────────
    with tab_import:
        st.markdown("#### 📥 导入 Colab 扫描结果 CSV / 本地即时单股扫描")
        c_imp1, c_imp2 = st.columns(2)

        with c_imp1:
            st.markdown("##### 1. 上传从 Google Colab 导出的 CSV")
            st.caption("在 Google Colab 运行完成后会自动下载 `colab_launch_box_results.csv`，在此拖入即可一键合并展示。")
            uploaded_csv = st.file_uploader("拖入或选择 colab_launch_box_results.csv", type=["csv"], key="lb_csv_uploader")
            if uploaded_csv is not None:
                try:
                    df_up = pd.read_csv(uploaded_csv)
                    req_fields = ["symbol", "breakout_date", "box_high", "box_low"]
                    if not all(f in df_up.columns for f in req_fields):
                        st.error(f"❌ CSV 格式校验失败，缺少关键字段: {req_fields}")
                    else:
                        st.success(f"📊 成功读取有效信号记录: **{len(df_up)}** 条")
                        if st.button("📥 确认导入并合并至数据库", key="lb_confirm_import_btn", use_container_width=True):
                            new_items = df_up.to_dict(orient="records")
                            _safe_append_launch_box_results(new_items)
                            st.toast(f"✅ 成功导入 {len(new_items)} 条记录！", icon="🎉")
                            time.sleep(1)
                            st.rerun()
                except Exception as e:
                    st.error(f"❌ 解析 CSV 失败: {e}")

        with c_imp2:
            st.markdown("##### 2. 本地即时单股扫描与校验")
            st.caption("输入任意股票代码（如 MARA、OXY、301151.SZ、603993.SS），系统将拉取数据并执行全量扫描。")
            test_sym = st.text_input("股票代码 (Ticker)", value="MARA", key="lb_test_single_sym")
            if st.button("⚡ 立即扫描该标的", key="lb_btn_scan_single", use_container_width=True, type="primary"):
                with st.spinner(f"正在拉取 {test_sym} 历史走势并运行矩形蓄势算法..."):
                    try:
                        import yfinance as yf
                        raw = yf.download(test_sym, start="2014-01-01", end=datetime.now().strftime("%Y-%m-%d"), progress=False, auto_adjust=False)
                        if isinstance(raw.columns, pd.MultiIndex):
                            raw.columns = [c[0] for c in raw.columns]
                        df = raw.dropna()
                        results = launch_box_scanner.calculate_launch_box(df, symbol=test_sym.upper(), period="1d")
                        if results:
                            res_dicts = [r.to_dict() for r in results]
                            _safe_append_launch_box_results(res_dicts)
                            st.success(f"🎉 扫描完成！共发现 **{len(results)}** 个中枢启动信号，已自动保存！")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning(f"⚠️ 在 {test_sym} 的走势中未检测到严格符合条件的矩形蓄势突破信号。")
                    except Exception as e:
                        st.error(f"❌ 扫描发生异常: {e}")

        st.markdown("---")
        # 清空与重置管理
        c_rst1, c_rst2 = st.columns([3, 1])
        with c_rst1:
            st.caption("重置数据库将恢复至出厂预设的 8 个经典标杆案例（洛阳钼业、MARA、TSLA、冠龙节能、西方石油、五粮液等）。")
        with c_rst2:
            if st.button("🗑️ 恢复预设标杆数据库", key="lb_btn_reset_demo"):
                _safe_clear_launch_box_results()
                _safe_init_demo_launch_boxes()
                st.toast("✅ 已恢复预设经典标杆案例！", icon="♻️")
                time.sleep(1)
                st.rerun()

