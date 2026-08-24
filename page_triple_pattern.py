"""
page_triple_pattern.py
======================================================================
🌟 三重底 & 三重顶 (Triple Top Bottom Scan v4 / TFLab MT4) 双向形态扫描器
- 🐂 看涨三重底 (Bullish Triple Bottom 1-2-3-4-5 波浪结构)
- 🐻 看跌三重顶 (Bearish Triple Top 1-2-3-4-5 波浪结构)
- 🏃 跑势进度体系 (breakout_progress: active=0%, confirmed=突破后推进百分比)
- 🎯 刚突破 (≤20%) 与 5点蓄势中优先过滤，支持动态滑块调节跑势进度上限 (0%~300%)
- 🎯 TFLab 风格 Entry, Stop Loss (粉色区), TP1 (61.8%), TP2 (100%), TP3 (161.8%) 斐波那契目标区
- ⚖️ 风险点数 (Risk) 与 收益点数 (Reward) & 盈亏比 (Risk to Reward 1:4+)
- 📈 深度还原 MT4 指标的 K 线图、粉绿多重目标阴影区与 1-2-3-4-5 拐点折线
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

import storage
import triple_pattern_scanner
import colab_triple_pattern_script

logger = logging.getLogger(__name__)

# 支持的周期映射: (interval, yfinance_period, 显示文本)
TRIPLE_PATTERN_TIMEFRAMES = {
    "1d":  ("1d",  "2y",  "日线 (D1)"),
    "1w":  ("1wk", "5y",  "周线 (W1)"),
    "1mo": ("1mo", "10y", "月线 (MN)"),
    "4h":  ("1h",  "730d", "4小时 (H4)"),
    "60m": ("60m", "720d", "1小时 (H1)"),
    "30m": ("30m", "60d",  "30分钟 (M30)"),
    "15m": ("15m", "60d",  "15分钟 (M15)"),
}


def _fetch_name(ticker: str) -> str:
    """获取股票名称"""
    try:
        from page_watchlist import _fetch_ticker_name
        return _fetch_ticker_name(ticker) or ticker
    except Exception:
        return ticker


def _tv_link(ticker: str, period: str) -> str:
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


def render_triple_pattern_page():
    st.markdown(
        """
        <style>
        .tp-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .tp-title {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .tp-plan-box {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 12px 14px;
            margin-top: 8px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
            gap: 10px;
        }
        .tp-plan-item {
            display: flex;
            flex-direction: column;
        }
        .tp-plan-label {
            font-size: 11px;
            color: #94a3b8;
            font-weight: 600;
        }
        .tp-plan-val {
            font-size: 14px;
            font-weight: 800;
            font-family: monospace;
            margin-top: 2px;
        }
        .click-count-badge {
            display: inline-block;
            font-size: 11px;
            font-weight: 700;
            padding: 1px 6px;
            border-radius: 10px;
            margin-left: 4px;
            line-height: 1.3;
        }
        .click-count-badge.today-active {
            background: rgba(245, 158, 11, 0.25);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.6);
        }
        .click-count-badge.history-active {
            background: rgba(34, 197, 94, 0.25);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.6);
        }
        .click-count-badge.no-clicks {
            background: rgba(148, 163, 184, 0.15);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .progress-track {
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            height: 6px;
            width: 100%;
            overflow: hidden;
            margin: 6px 0 6px 0;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        .tp-pagination {
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
        .tp-page-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 14px;
            background: rgba(59, 130, 246, 0.15);
            color: #93c5fd !important;
            border: 1px solid rgba(59, 130, 246, 0.35);
            border-radius: 6px;
            text-decoration: none !important;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .tp-page-btn:hover {
            background: rgba(59, 130, 246, 0.3);
            color: #ffffff !important;
            border-color: rgba(59, 130, 246, 0.7);
            text-decoration: none !important;
        }
        .tp-page-btn.disabled {
            background: rgba(148, 163, 184, 0.08);
            color: #64748b !important;
            border-color: rgba(148, 163, 184, 0.15);
            cursor: not-allowed;
            pointer-events: none;
        }
        .tp-page-info {
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

    # ── 行情链接点击双向 WebSocket 桥接器 ──
    try:
        import frontend_bridge
        _bridge_data = frontend_bridge.render_tv_click_bridge(key="tp_page_tv_bridge")
        if _bridge_data and isinstance(_bridge_data, dict):
            _tk = str(_bridge_data.get("ticker", "")).strip().upper()
            _ts = _bridge_data.get("ts", 0)
            _last_ts = st.session_state.get("_last_tp_bridge_click_ts", 0)
            if _tk and _ts != _last_ts:
                st.session_state["_last_tp_bridge_click_ts"] = _ts
                storage.increment_link_click(_tk, "tv")
    except Exception:
        pass

    all_patterns = storage.load_triple_pattern()

    # ── 从 URL _dir 参数恢复「形态方向」下拉状态 ──
    # 用户通过链接切换页面时 (_dir=bullish/bearish/all)，session_state 会丢失,
    # 在 selectbox 渲染前注入正确值，保证方向不被重置。
    _DIR_URL_MAP = {
        "bullish": "🐂 仅看涨 (三重底)",
        "bearish": "🐻 仅看跌 (三重顶)",
        "all":     "全部方向",
    }
    _url_dir_raw = str(st.query_params.get("_dir", "")).strip().lower()
    if _url_dir_raw in _DIR_URL_MAP:
        _desired_dir = _DIR_URL_MAP[_url_dir_raw]
        # 仅在与当前 session_state 不一致时写入，避免用户手动更改被覆盖
        if st.session_state.get("tp_filter_direction") != _desired_dir:
            st.session_state["tp_filter_direction"] = _desired_dir

    # ── 1. 顶部标题与形态总体统计 ──
    st.markdown(
        """
        <div class="tp-header">
            <div class="tp-title">
                <span>🌟 三重底 & 三重顶 (Triple Top Bottom Scan v4)</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption("对齐 TFLab MT4 经典 5 点波浪 (1-2-3-4-5) 几何反转形态与三段斐波那契目标体系 (TP1 61.8%, TP2 100%, TP3 161.8%)，支持实时跑势进度过滤。")

    total_patterns_cnt = len(all_patterns)
    bull_cnt = sum(1 for r in all_patterns if r.get("direction") == "bullish")
    bear_cnt = sum(1 for r in all_patterns if r.get("direction") == "bearish")
    active_cnt = sum(1 for r in all_patterns if r.get("status") == "active")
    early_break_cnt = sum(1 for r in all_patterns if r.get("status") == "confirmed" and float(r.get("breakout_progress", 0.0)) <= 20.0)
    far_break_cnt = sum(1 for r in all_patterns if r.get("status") == "confirmed" and float(r.get("breakout_progress", 0.0)) > 20.0)

    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    with col_m1:
        st.metric("📊 形态总数", f"{total_patterns_cnt} 条")
    with col_m2:
        st.metric("🐂 看涨三重底", f"{bull_cnt} 条")
    with col_m3:
        st.metric("🐻 看跌三重顶", f"{bear_cnt} 条")
    with col_m4:
        st.metric("👀 5点蓄势中", f"{active_cnt} 条")
    with col_m5:
        st.metric("🚀 刚突破 (≤20%)", f"{early_break_cnt} 条", delta="绝佳进场区" if early_break_cnt > 0 else None)
    with col_m6:
        st.metric("🏃 已推进 (>20%)", f"{far_break_cnt} 条")

    # ── 2. Google Colab 独立云端扫描与 1 键导入 ──
    with st.expander("🚀 1. Google Colab 独立云端极速扫描与 1 键导入 (推荐 · 50+只/秒并发)", expanded=False):
        colab_c1, colab_c2 = st.columns([1.2, 1])
        with colab_c1:
            st.markdown("##### 1. 生成并复制 Google Colab 扫描脚本")
            st.caption("脚本内置 Yahoo v8 直连引擎与连接池技术，支持全部分组 12,400+ 支标的多周期秒级并发扫描。")

            all_symbols = storage.load_symbols() or []
            groups = storage.load_symbol_groups() or []

            pool_options = ["🇺🇸 全量美股 (系统内置)", "🇨🇳 全量A股 (系统内置)", "🌐 全部组去重合并 (全量市场)"]
            for g in groups:
                if g.get("name"):
                    pool_options.append(f"📁 分组: {g.get('name')}")

            c_p1, c_p2 = st.columns([2, 1])
            with c_p1:
                selected_pool = st.selectbox(
                    "🎯 选择扫描股票池",
                    pool_options,
                    index=0,
                    key="tp_colab_pool_select"
                )
            with c_p2:
                tf_map_keys = st.multiselect(
                    "⏱ 扫描周期",
                    options=list(TRIPLE_PATTERN_TIMEFRAMES.keys()),
                    default=["1d", "1w", "1mo"],
                    format_func=lambda x: TRIPLE_PATTERN_TIMEFRAMES[x][2],
                    key="tp_colab_tf_select"
                )

            export_tickers = []
            if selected_pool == "🌐 全部组去重合并 (全量市场)":
                for g in groups:
                    export_tickers.extend(g.get("tickers", []))
                if not export_tickers:
                    export_tickers = [s["ticker"] for s in all_symbols]
            elif "全量美股" in selected_pool:
                export_tickers = [s["ticker"] for s in all_symbols if not (s["ticker"].endswith(".SS") or s["ticker"].endswith(".SZ") or s["ticker"].endswith(".BJ") or s["ticker"].isdigit())]
            elif "全量A股" in selected_pool:
                export_tickers = [s["ticker"] for s in all_symbols if s["ticker"].endswith(".SS") or s["ticker"].endswith(".SZ") or s["ticker"].endswith(".BJ") or s["ticker"].isdigit()]
            elif selected_pool.startswith("📁 分组:"):
                g_name = selected_pool.replace("📁 分组: ", "").strip()
                target_g = next((g for g in groups if g.get("name") == g_name), None)
                if target_g:
                    export_tickers = target_g.get("tickers", [])

            if not export_tickers:
                export_tickers = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL", "META"]

            export_tickers = list(dict.fromkeys([t.strip().upper() for t in export_tickers if t and isinstance(t, str)]))
            st.info(f"📋 选定股票池: **{len(export_tickers)}** 支品种 | 周期: **{', '.join(tf_map_keys)}** (代码已内置)：")

            colab_code = colab_triple_pattern_script.generate_colab_script_for_tickers(
                export_tickers, pool_name=selected_pool, selected_tfs=tf_map_keys
            )
            st.code(colab_code, language="python", line_numbers=True)

        with colab_c2:
            st.markdown("##### 2. 导入 Colab 扫描结果 CSV")
            st.caption("上传从 Google Colab 导出的 `colab_triple_pattern_results.csv`，系统将自动增量合并。")
            uploaded_file = st.file_uploader(
                "选择或拖拽 Colab 导出的 CSV 文件",
                type=["csv"],
                key="tp_colab_csv_uploader",
                help="支持导入 colab_triple_pattern_results.csv"
            )

            if uploaded_file is not None:
                try:
                    df_up = pd.read_csv(uploaded_file)
                    req_fields = ["symbol", "pattern", "confidence", "direction", "idx1", "idx3", "idx5"]
                    missing = [f for f in req_fields if f not in df_up.columns]
                    if missing:
                        st.error(f"❌ CSV 格式校验未通过，缺少关键字段: {missing}")
                    else:
                        st.success(f"📊 检测到有效双向形态记录: **{len(df_up)}** 条 (🐂 {sum(df_up['direction'] == 'bullish')} / 🐻 {sum(df_up['direction'] == 'bearish')})")
                        if st.button("📥 确认增量导入并合并到数据库", key="tp_confirm_import_csv", use_container_width=True):
                            new_records = df_up.to_dict(orient="records")
                            ok = storage.append_triple_pattern_results(new_records)
                            if ok:
                                st.toast(f"✅ 成功增量导入 {len(new_records)} 条形态记录！", icon="🎉")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ 数据库写入失败，请重试")
                except Exception as e:
                    st.error(f"❌ 解析 CSV 出错: {e}")

    # ── 3. 快照与清空管理 ──
    with st.expander("📦 2. 快照备份与恢复", expanded=False):
        c_bk1, c_bk2 = st.columns([2, 1])
        with c_bk1:
            snapshots = storage.load_tp_snapshots()
            if snapshots:
                st.markdown(f"当前历史快照共 **{len(snapshots)}** 个：")
                options = {s["session_id"]: f"{s['scan_time']} | 数量: {s['count']} 条 | ID: {s['session_id'][:16]}..." for s in snapshots}
                sel_sid = st.selectbox("选择要恢复的历史快照", list(options.keys()), format_func=lambda x: options[x], key="tp_sel_snap")
                if st.button("♻️ 从选定快照恢复", key="tp_btn_restore_snap"):
                    ok, msg, n = storage.restore_tp_snapshot(sel_sid)
                    if ok:
                        st.toast(f"✅ 成功恢复 {n} 条形态记录！", icon="♻️")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.caption("暂无历史快照备份。")
        with c_bk2:
            st.markdown("⚠️ **数据维护**")
            if st.button("🗑️ 清空当前结果库", key="tp_btn_clear_data", use_container_width=True):
                storage.clear_triple_pattern_results()
                st.toast("已清空结果库并自动创建安全快照", icon="🗑️")
                time.sleep(1)
                st.rerun()

    # ── 4. 主界面形态展示与多维筛选 ──
    if not all_patterns:
        st.markdown(
            """
            <div style="text-align:center;padding:40px 20px;background:rgba(255,255,255,0.02);border:1px dashed rgba(255,255,255,0.1);border-radius:12px;margin:20px 0;">
                <div style="font-size:36px;margin-bottom:8px;">🌟</div>
                <div style="font-size:16px;font-weight:700;color:#f8fafc;">暂无「三重底 & 三重顶」扫描记录</div>
                <div style="font-size:13px;color:#94a3b8;margin-top:6px;">
                    请展开上方 <b>「1. Google Colab 独立云端极速扫描」</b>，运行云端脚本并导入 CSV 结果。<br>
                    或在系统后台自动扫描完成后即可在此查看全量多周期形态！
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    # 筛选面板 第一行
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.2, 1.5, 1.3, 1.8])

    # 方向改变时写入 URL _dir 参数，保证翻页/刷新后可恢复
    def _on_tp_dir_change():
        _val = st.session_state.get("tp_filter_direction", "全部方向")
        _DIR_REVERSE = {
            "🐂 仅看涨 (三重底)": "bullish",
            "🐻 仅看跌 (三重顶)": "bearish",
        }
        try:
            st.query_params["_dir"] = _DIR_REVERSE.get(_val, "all")
            # 方向变化时重置翻页到第 1 页
            st.query_params["_p"] = "1"
            st.session_state.tp_current_page = 1
        except Exception:
            pass

    with col_f1:
        st_direction = st.selectbox(
            "🧭 形态方向",
            ["全部方向", "🐂 仅看涨 (三重底)", "🐻 仅看跌 (三重顶)"],
            key="tp_filter_direction",
            on_change=_on_tp_dir_change,
        )
    with col_f2:
        st_patt = st.selectbox(
            "🏷️ 形态子类",
            [
                "全部形态",
                "完美形态 (Perfect)",
                "头肩形态 (Head & Shoulders)",
                "失败突破假破型 (Failed BO)",
                "双顶底回调型 (Pullback)",
                "楔形形态 (Wedge)",
                "收敛三角形 (Triangle)"
            ],
            index=0,
            key="tp_filter_pattern"
        )
    with col_f3:
        st_period = st.multiselect(
            "⏱️ 扫描周期",
            options=list(TRIPLE_PATTERN_TIMEFRAMES.keys()),
            default=list(TRIPLE_PATTERN_TIMEFRAMES.keys()),
            format_func=lambda x: TRIPLE_PATTERN_TIMEFRAMES[x][2],
            key="tp_filter_period"
        )
    with col_f4:
        st_status = st.multiselect(
            "📌 形态阶段状态",
            options=[
                "👀 观望蓄势中 (active 0%)",
                "🚀 刚突破 (confirmed ≤20%)",
                "⚡ 推进中 (confirmed 20~100%)",
                "🏁 已超TP2目标 (confirmed >100%)",
                "❌ 已失效 (invalidated)",
                "⏰ 已过期 (expired)"
            ],
            default=[
                "👀 观望蓄势中 (active 0%)",
                "🚀 刚突破 (confirmed ≤20%)"
            ],
            key="tp_filter_status"
        )

    # 筛选面板 第二行：跑势进度上限滑块
    col_sl1, col_sl2 = st.columns([2.5, 1])
    with col_sl1:
        progress_limit = st.slider(
            "🏃 跑势进度上限 (0% ~ 300%)",
            min_value=0,
            max_value=300,
            value=20,
            step=5,
            help="【核心过滤】：默认 20%，只保留 5 点成型蓄势中 (0%) 以及突破颈线 20% 形态高度以内的标的。已突破跑很远 (>20%) 的标的将被自动过滤。向右拉大滑块可查看更多推进中的形态。",
            key="tp_progress_slider"
        )
    with col_sl2:
        st.markdown(
            f"<div style='margin-top:28px;font-size:13px;color:#38bdf8;font-weight:600;'>"
            f"🎯 当前过滤: <b>0% ~ {progress_limit}%</b>"
            f"</div>",
            unsafe_allow_html=True
        )

    # 执行过滤
    filtered = []
    for r in all_patterns:
        # 方向过滤
        d = r.get("direction", "bullish")
        if st_direction == "🐂 仅看涨 (三重底)" and d != "bullish":
            continue
        if st_direction == "🐻 仅看跌 (三重顶)" and d != "bearish":
            continue

        # 形态子类过滤
        pname = r.get("pattern", "")
        if st_patt == "完美形态 (Perfect)" and "完美" not in pname: continue
        elif st_patt == "头肩形态 (Head & Shoulders)" and "头肩" not in pname: continue
        elif st_patt == "失败突破假破型 (Failed BO)" and "失败突破" not in pname: continue
        elif st_patt == "双顶底回调型 (Pullback)" and "回调" not in pname: continue
        elif st_patt == "楔形形态 (Wedge)" and "楔形" not in pname: continue
        elif st_patt == "收敛三角形 (Triangle)" and "三角" not in pname: continue

        # 周期过滤
        if r.get("period") not in st_period:
            continue

        # 状态阶段划分与跑势过滤
        st_val = r.get("status", "active")
        prog = float(r.get("breakout_progress", 0.0))

        # 状态多选过滤
        is_active = (st_val == "active")
        is_early = (st_val == "confirmed" and prog <= 20.0)
        is_mid = (st_val == "confirmed" and 20.0 < prog <= 100.0)
        is_far = (st_val == "confirmed" and prog > 100.0)
        is_invalidated = (st_val == "invalidated")
        is_expired = (st_val == "expired")

        matched_status = False
        for s in st_status:
            if "观望蓄势中" in s and is_active: matched_status = True
            elif "刚突破" in s and is_early: matched_status = True
            elif "推进中" in s and is_mid: matched_status = True
            elif "已超TP2目标" in s and is_far: matched_status = True
            elif "已失效" in s and is_invalidated: matched_status = True
            elif "已过期" in s and is_expired: matched_status = True

        if not matched_status:
            continue

        # 跑势进度上限滑块过滤 (只对 active 和 confirmed 生效)
        if st_val in ("active", "confirmed") and prog > progress_limit:
            continue

        filtered.append(r)

    # 搜索与排序
    col_s1, col_s2, col_s3 = st.columns([2, 1.4, 1])
    with col_s1:
        search_query = st.text_input("🔍 搜索代码 / 名称", "", placeholder="输入股票代码或名称关键词...", key="tp_search_query")
    with col_s2:
        sort_by = st.selectbox(
            "↕️ 排序方式",
            [
                "🏃 跑势进度 (低 → 高 · 优先蓄势/刚突破)",
                "置信度 (高 → 低)",
                "TP3 黄金盈亏比 (高 → 低)",
                "TP2 颈线盈亏比 (高 → 低)",
                "🏃 跑势进度 (高 → 低)",
                "最新扫描时间 (新 → 旧)",
                "股票代码 (A → Z)"
            ],
            index=0,
            key="tp_sort_by"
        )
    with col_s3:
        page_size = st.selectbox("📄 每页条数", [20, 50, 100], index=0, key="tp_page_size")

    if search_query.strip():
        q = search_query.strip().upper()
        filtered = [r for r in filtered if q in str(r.get("symbol", "")).upper() or q in _fetch_name(str(r.get("symbol", ""))).upper()]

    if sort_by == "🏃 跑势进度 (低 → 高 · 优先蓄势/刚突破)":
        filtered.sort(key=lambda x: (float(x.get("breakout_progress", 0.0)), -float(x.get("confidence", 0.0))))
    elif sort_by == "🏃 跑势进度 (高 → 低)":
        filtered.sort(key=lambda x: (float(x.get("breakout_progress", 0.0)), float(x.get("confidence", 0.0))), reverse=True)
    elif sort_by == "置信度 (高 → 低)":
        filtered.sort(key=lambda x: (float(x.get("confidence", 0.0)), float(x.get("rr_tp3", 2.0))), reverse=True)
    elif sort_by == "TP3 黄金盈亏比 (高 → 低)":
        filtered.sort(key=lambda x: float(x.get("rr_tp3", x.get("risk_reward", 1.0))), reverse=True)
    elif sort_by == "TP2 颈线盈亏比 (高 → 低)":
        filtered.sort(key=lambda x: float(x.get("risk_reward", 1.0)), reverse=True)
    elif sort_by == "最新扫描时间 (新 → 旧)":
        filtered.sort(key=lambda x: str(x.get("scan_time", "")), reverse=True)
    elif sort_by == "股票代码 (A → Z)":
        filtered.sort(key=lambda x: str(x.get("symbol", "")).upper())

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    # ── 页码状态管理 (双向绑定 URL 参数与按钮交互) ──
    url_p_raw = str(st.query_params.get("_p", "") or st.query_params.get("p", "")).strip()
    seen_url_p = str(st.session_state.get("_tp_url_p_seen", "")).strip()

    if url_p_raw and url_p_raw != seen_url_p:
        try:
            st.session_state.tp_current_page = int(url_p_raw)
        except Exception:
            st.session_state.tp_current_page = 1
        st.session_state._tp_url_p_seen = url_p_raw
    elif "tp_current_page" not in st.session_state:
        st.session_state.tp_current_page = 1
        st.session_state._tp_url_p_seen = ""

    current_page = max(1, min(total_pages, int(st.session_state.tp_current_page)))
    st.session_state.tp_current_page = current_page
    st.session_state._tp_url_p_seen = str(current_page)

    try:
        st.query_params["_p"] = str(current_page)
    except Exception:
        pass

    def _make_tp_page_url(target_page: int) -> str:
        params = {}
        for k, v in st.query_params.items():
            params[k] = v
        params["_page"] = "triple_pattern"
        params["_p"] = str(target_page)
        
        _cur_dir = st.session_state.get("tp_filter_direction", "全部方向")
        _DIR_MAP = {"🐂 仅看涨 (三重底)": "bullish", "🐻 仅看跌 (三重顶)": "bearish"}
        if _cur_dir in _DIR_MAP:
            params["_dir"] = _DIR_MAP[_cur_dir]
        elif "_dir" in params and params["_dir"] not in ("bullish", "bearish"):
            params["_dir"] = "all"
            
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"/?{qs}"

    def _render_tp_pagination_bar(cur_p: int, tot_p: int, tot_items: int, p_sz: int, is_bottom: bool = False):
        first_url = _make_tp_page_url(1)
        prev_url = _make_tp_page_url(max(1, cur_p - 1))
        next_url = _make_tp_page_url(min(tot_p, cur_p + 1))
        last_url = _make_tp_page_url(tot_p)
        
        first_cls = "tp-page-btn disabled" if cur_p <= 1 else "tp-page-btn"
        prev_cls = "tp-page-btn disabled" if cur_p <= 1 else "tp-page-btn"
        next_cls = "tp-page-btn disabled" if cur_p >= tot_p else "tp-page-btn"
        last_cls = "tp-page-btn disabled" if cur_p >= tot_p else "tp-page-btn"
        
        start_n = (cur_p - 1) * p_sz + 1 if tot_items > 0 else 0
        end_n = min(cur_p * p_sz, tot_items)
        
        if not is_bottom:
            info_text = f"📄 第 <span style='color:#f59e0b;'>{cur_p}</span> / {tot_p} 页 (符合筛选 <span style='color:#38bdf8;'>{tot_items}</span> 条，显示 {start_n} - {end_n} 条)"
        else:
            info_text = f"📄 第 <span style='color:#f59e0b;'>{cur_p}</span> / {tot_p} 页 (共 <span style='color:#38bdf8;'>{tot_items}</span> 条)"
            
        st.markdown(
            f"""
            <div class="tp-pagination">
                <div style="display:flex;gap:6px;">
                    <a href="{first_url}" target="_self" class="{first_cls}">⏮ 首页</a>
                    <a href="{prev_url}" target="_self" class="{prev_cls}">◀ 上一页</a>
                </div>
                <div class="tp-page-info">
                    {info_text}
                </div>
                <div style="display:flex;gap:6px;">
                    <a href="{next_url}" target="_self" class="{next_cls}">下一页 ▶</a>
                    <a href="{last_url}" target="_self" class="{last_cls}">末页 ⏭</a>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 分页导航条（顶部）
    _render_tp_pagination_bar(current_page, total_pages, total_items, page_size, is_bottom=False)

    # 切片当前页数据
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = filtered[start_idx:end_idx]

    all_clicks_data = storage.get_all_link_clicks()
    wl = storage.load_watchlist()
    today_str_val = storage.get_today_str()

    for i, r in enumerate(page_items):
        item_idx = start_idx + i
        ticker = r["symbol"]
        period = r.get("period", "1d")
        direction = r.get("direction", "bullish")
        patt_desc = r.get("pattern", "形态")
        conf = float(r.get("confidence", 0.8))
        note = r.get("note", "")
        status_val = r.get("status", "active")
        status_reason = r.get("status_reason", "")
        prog_val = float(r.get("breakout_progress", 0.0))
        period_desc = TRIPLE_PATTERN_TIMEFRAMES.get(period, (None, None, period))[2]
        name = _fetch_name(ticker)

        # 5 点波浪与关键价位
        pt1 = r.get("pt1", r.get("p1", 0.0))
        pt2 = r.get("pt2", r.get("neckline", 0.0))
        pt3 = r.get("pt3", r.get("p2", 0.0))
        pt4 = r.get("pt4", r.get("neckline", 0.0))
        pt5 = r.get("pt5", r.get("p3", 0.0))

        entry_p = r.get("entry_price", pt5)
        sl_p = r.get("stop_loss", 0.0)
        tp1_p = r.get("tp1", 0.0)
        tp2_p = r.get("tp2", 0.0)
        tp3_p = r.get("tp3", 0.0)
        risk_pips = r.get("risk", abs(entry_p - sl_p))
        rr_tp1 = round(abs(tp1_p - entry_p) / max(0.001, risk_pips), 2)
        rr_tp2 = r.get("risk_reward", round(abs(tp2_p - entry_p) / max(0.001, risk_pips), 2))
        rr_tp3 = r.get("rr_tp3", round(abs(tp3_p - entry_p) / max(0.001, risk_pips), 2))

        # 方向徽章
        if direction == "bullish":
            dir_badge = "<span style='font-size:12px;background:rgba(34,197,94,0.18);color:#4ade80;border:1px solid rgba(34,197,94,0.4);padding:2px 8px;border-radius:4px;font-weight:700;'>🐂 看涨三重底 (Bullish)</span>"
            p_lbls = ["1: L1", "2: H1", "3: L2", "4: H2", "5: L3 (Entry)"]
        else:
            dir_badge = "<span style='font-size:12px;background:rgba(239,68,68,0.18);color:#f87171;border:1px solid rgba(239,68,68,0.4);padding:2px 8px;border-radius:4px;font-weight:700;'>🐻 看跌三重顶 (Bearish)</span>"
            p_lbls = ["1: H1", "2: L1", "3: H2", "4: L2", "5: H3 (Entry)"]

        # 状态与跑势进度徽章
        if status_val == "active":
            status_badge = "<span style='font-size:12px;background:rgba(59,130,246,0.18);color:#93c5fd;border:1px solid rgba(59,130,246,0.4);padding:2px 8px;border-radius:4px;font-weight:700;'>👀 5点蓄势中 (0%)</span>"
            bar_color = "#3b82f6"
            bar_width = 5
        elif status_val == "confirmed":
            if prog_val <= 20.0:
                status_badge = f"<span style='font-size:12px;background:rgba(34,197,94,0.22);color:#4ade80;border:1px solid rgba(34,197,94,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>🚀 刚突破颈线 ({prog_val:.1f}%)</span>"
                bar_color = "#22c55e"
                bar_width = max(8, min(100, int(prog_val)))
            elif prog_val <= 100.0:
                status_badge = f"<span style='font-size:12px;background:rgba(245,158,11,0.2);color:#fde047;border:1px solid rgba(245,158,11,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>⚡ 推进中 ({prog_val:.1f}%)</span>"
                bar_color = "#f59e0b"
                bar_width = max(10, min(100, int(prog_val)))
            else:
                status_badge = f"<span style='font-size:12px;background:rgba(249,115,22,0.2);color:#fb923c;border:1px solid rgba(249,115,22,0.5);padding:2px 8px;border-radius:4px;font-weight:700;'>🏁 已超TP2 ({prog_val:.1f}%)</span>"
                bar_color = "#f97316"
                bar_width = 100
        elif status_val == "invalidated":
            status_badge = "<span style='font-size:12px;background:rgba(239,68,68,0.15);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>已触及止损 ❌</span>"
            bar_color = "#ef4444"
            bar_width = 100
        else:
            status_badge = "<span style='font-size:12px;background:rgba(100,116,139,0.15);color:#94a3b8;border:1px solid rgba(100,116,139,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>已过期 ⏰</span>"
            bar_color = "#64748b"
            bar_width = 0

        with st.container(border=True):
            col_t1, col_t2 = st.columns([5, 3])
            with col_t1:
                st.markdown(
                    f"<div style='margin-bottom:6px;'>"
                    f"<span style='font-size:18px;font-weight:800;color:#f8fafc;'>{ticker}</span> "
                    f"<span style='font-size:14px;color:#94a3b8;margin-right:8px;'>· {name}</span> "
                    f"{dir_badge} "
                    f"<span style='font-size:12px;background:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>{period_desc}</span> "
                    f"<span style='font-size:12px;background:rgba(245,158,11,0.15);color:#fde047;border:1px solid rgba(245,158,11,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>置信度: {conf:.0%}</span> "
                    f"{status_badge}"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with col_t2:
                btn_col1, btn_col2, btn_col3 = st.columns(3)
                chart_key = f"tp_chart_open_{ticker}_{period}_{direction}"
                is_open = st.session_state.get(chart_key, False)

                with btn_col1:
                    if st.button("📊 MT4图" if not is_open else "❌ 关闭图", key=f"tp_chart_btn_{item_idx}", use_container_width=True):
                        st.session_state[chart_key] = not is_open
                        st.rerun()

                with btn_col2:
                    click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
                    total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
                    by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
                    today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0

                    if today_c > 0:
                        click_badge_html = f'<span class="click-count-badge today-active">({today_c}/{total_c})</span>'
                    elif total_c > 0:
                        click_badge_html = f'<span class="click-count-badge history-active">({today_c}/{total_c})</span>'
                    else:
                        click_badge_html = f'<span class="click-count-badge no-clicks">(0/0)</span>'

                    tv_url_val = _tv_link(ticker, period)
                    st.markdown(
                        f'<a href="{tv_url_val}" target="_blank" class="tv-btn" data-ticker="{ticker}" '
                        f'style="display:block;text-align:center;padding:6px 0;background:rgba(30,144,255,0.15);'
                        f'border:1px solid rgba(30,144,255,0.3);color:#38bdf8;'
                        f'border-radius:4px;text-decoration:none;font-weight:600;font-size:13px;">'
                        f'📈 TV {click_badge_html}</a>',
                        unsafe_allow_html=True
                    )

                with btn_col3:
                    is_fav = any(w.get("ticker", "").upper() == ticker.upper() for w in wl)
                    if not is_fav:
                        if st.button("⭐ 收藏", key=f"tp_add_wl_{item_idx}", use_container_width=True):
                            ok = storage.add_to_watchlist(ticker=ticker, name=name, note=f"三重顶底: {patt_desc}")
                            if ok:
                                st.toast(f"已添加 {ticker} 至自选收藏夹", icon="⭐")
                                st.rerun()
                    else:
                        st.button("✅ 已加", disabled=True, key=f"tp_is_fav_{item_idx}", use_container_width=True)

            # 跑势进度条指示
            st.markdown(
                f"""
                <div class="progress-track" title="跑势进度: {prog_val:.1f}% (0%=颈线位, 100%=TP2颈线目标)">
                    <div class="progress-fill" style="width:{bar_width}%; background:{bar_color};"></div>
                </div>
                <div style="font-size:13px; line-height:1.7; color:#cbd5e1; margin-top: 2px;">
                    <div>🏷️ <b>形态分类</b>：<span style="color:#f59e0b; font-weight:600;">{patt_desc}</span> | 🏃 <b>跑势进度</b>：<span style="color:{bar_color}; font-weight:700;">{prog_val:.1f}%</span></div>
                    <div>🔍 <b>跟踪观察</b>：{status_reason}</div>
                    <div style="color:#94a3b8; font-size:12px; margin-top:2px;">📝 <b>特征说明</b>：{note}</div>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;">
                    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);padding:3px 8px;border-radius:6px;font-size:11px;">{p_lbls[0]}: <b>{pt1:.3f}</b></div>
                    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);padding:3px 8px;border-radius:6px;font-size:11px;">{p_lbls[1]}: <b>{pt2:.3f}</b></div>
                    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);padding:3px 8px;border-radius:6px;font-size:11px;">{p_lbls[2]}: <b>{pt3:.3f}</b></div>
                    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);padding:3px 8px;border-radius:6px;font-size:11px;">{p_lbls[3]}: <b>{pt4:.3f}</b></div>
                    <div style="background:rgba(59,130,246,0.15);border:1px solid rgba(59,130,246,0.4);padding:3px 8px;border-radius:6px;font-size:11px;color:#93c5fd;">{p_lbls[4]}: <b>{pt5:.3f}</b></div>
                </div>
                <div class="tp-plan-box">
                    <div class="tp-plan-item">
                        <span class="tp-plan-label">🎯 Entry Point (5)</span>
                        <span class="tp-plan-val" style="color:#38bdf8;">{entry_p:.3f}</span>
                    </div>
                    <div class="tp-plan-item">
                        <span class="tp-plan-label">🛡️ Stop Loss (粉色区)</span>
                        <span class="tp-plan-val" style="color:#f43f5e;">{sl_p:.3f} <span style="font-size:10px;color:#94a3b8;">({risk_pips:.3f})</span></span>
                    </div>
                    <div class="tp-plan-item">
                        <span class="tp-plan-label">🏁 TP1 (61.8% Fibo)</span>
                        <span class="tp-plan-val" style="color:#22c55e;">{tp1_p:.3f} <span style="font-size:10px;color:#86efac;">(1:{rr_tp1})</span></span>
                    </div>
                    <div class="tp-plan-item">
                        <span class="tp-plan-label">🎯 TP2 (100% 颈线)</span>
                        <span class="tp-plan-val" style="color:#10b981;">{tp2_p:.3f} <span style="font-size:10px;color:#86efac;">(1:{rr_tp2})</span></span>
                    </div>
                    <div class="tp-plan-item">
                        <span class="tp-plan-label">🚀 TP3 (161.8% 黄金)</span>
                        <span class="tp-plan-val" style="color:#a855f7;">{tp3_p:.3f} <span style="font-size:10px;color:#d8b4fe;">(1:{rr_tp3})</span></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ── 展开 MT4 风格深度 K 线图与粉绿目标阴影区 ──
            if st.session_state.get(chart_key):
                with st.container(border=True):
                    st.markdown(f"##### 📊 {ticker} - {period_desc} MT4 Triple Top Bottom Scan v4 还原图")
                    with st.spinner("拉取历史数据并渲染 1-2-3-4-5 波浪与斐波那契目标区..."):
                        try:
                            from scanner import fetch_data
                            interval, yf_period, _ = TRIPLE_PATTERN_TIMEFRAMES.get(period, ("1d", "2y", "日线"))
                            df = fetch_data(ticker, interval=interval, period=yf_period)
                            if df is not None and not df.empty:
                                df_slice = df.tail(120).copy()
                                if isinstance(df_slice.columns, pd.MultiIndex):
                                    df_slice.columns = [c[0].lower() for c in df_slice.columns]
                                else:
                                    df_slice.columns = [c.lower() for c in df_slice.columns]
                                
                                df_slice = df_slice.reset_index()
                                date_col = df_slice.columns[0]
                                
                                fig = go.Figure()
                                # 1. 蜡烛图
                                fig.add_trace(go.Candlestick(
                                    x=df_slice[date_col],
                                    open=df_slice['open'],
                                    high=df_slice['high'],
                                    low=df_slice['low'],
                                    close=df_slice['close'],
                                    name='K线',
                                    increasing_line_color='#22c55e',
                                    decreasing_line_color='#ef4444'
                                ))

                                # 2. 标绘 1, 2, 3, 4, 5 点
                                idx_map = [r.get("idx1"), r.get("idx2"), r.get("idx3"), r.get("idx4"), r.get("idx5")]
                                pts_y = [pt1, pt2, pt3, pt4, pt5]
                                valid_pts_x = []
                                valid_pts_y = []
                                valid_texts = []

                                for p_i, idx_v in enumerate(idx_map):
                                    if idx_v is not None and 0 <= idx_v < len(df_slice):
                                        valid_pts_x.append(df_slice.loc[idx_v, date_col])
                                        valid_pts_y.append(pts_y[p_i])
                                        valid_texts.append(str(p_i + 1))

                                if len(valid_pts_x) >= 3:
                                    fig.add_trace(go.Scatter(
                                        x=valid_pts_x,
                                        y=valid_pts_y,
                                        mode='lines+markers+text',
                                        line=dict(color='#3b82f6', width=3),
                                        marker=dict(size=12, color='#1d4ed8', line=dict(color='#93c5fd', width=2)),
                                        text=valid_texts,
                                        textposition="bottom center" if direction == "bullish" else "top center",
                                        textfont=dict(color="#ffffff", size=13, family="monospace"),
                                        name='1-2-3-4-5 波浪结构'
                                    ))

                                # 3. 绘制 Stop Loss (粉色带) 与 TP (绿色带) 阴影区域
                                x_start = valid_pts_x[-1] if valid_pts_x else df_slice[date_col].iloc[-20]
                                x_end = df_slice[date_col].iloc[-1]

                                # 粉色止损阴影
                                fig.add_hrect(
                                    y0=min(entry_p, sl_p),
                                    y1=max(entry_p, sl_p),
                                    fillcolor="rgba(244, 63, 94, 0.22)",
                                    line=dict(color="rgba(244, 63, 94, 0.7)", width=1, dash="dot"),
                                    annotation_text=f"Stop Loss ({sl_p:.3f})",
                                    annotation_position="bottom right" if direction == "bullish" else "top right"
                                )

                                # 绿色盈利目标阴影 (TP1 ~ TP3)
                                fig.add_hrect(
                                    y0=min(entry_p, tp3_p),
                                    y1=max(entry_p, tp3_p),
                                    fillcolor="rgba(34, 197, 94, 0.18)",
                                    line=dict(color="rgba(34, 197, 94, 0.6)", width=1, dash="dash"),
                                    annotation_text=f"TP3 161.8% ({tp3_p:.3f})",
                                    annotation_position="top right" if direction == "bullish" else "bottom right"
                                )

                                # 目标参考线
                                fig.add_hline(y=tp1_p, line_dash="dot", line_color="#22c55e", annotation_text=f"TP1 61.8%: {tp1_p:.3f}", annotation_position="right")
                                fig.add_hline(y=tp2_p, line_dash="dash", line_color="#10b981", annotation_text=f"TP2 100%: {tp2_p:.3f}", annotation_position="right")

                                fig.update_layout(
                                    xaxis_rangeslider_visible=False,
                                    height=360,
                                    margin=dict(l=10, r=10, t=25, b=10),
                                    template="plotly_dark",
                                    plot_bgcolor="rgba(0,0,0,0)"
                                )
                                st.plotly_chart(fig, use_container_width=True, key=f"tp_fig_{ticker}_{period}_{direction}_{item_idx}")
                            else:
                                st.warning("未拉取到足够的历史 K 线数据，无法还原形态图。")
                        except Exception as ex:
                            st.error(f"渲染图形出错: {ex}")

    # 分页导航条（底部）
    if total_pages > 1:
        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        _render_tp_pagination_bar(current_page, total_pages, total_items, page_size, is_bottom=True)

    # 💡 隐形事件监听组件：捕捉原链接点击，能在后台落盘计数，同时在前台秒级实时更新 (今日/总) 数字
    _js_code = r"""
    <script>
    (function() {
        try {
            var pDoc = window.parent.document;
            if (pDoc._tv_click_handler) {
                pDoc.removeEventListener('click', pDoc._tv_click_handler, true);
            }
            pDoc._tv_click_handler = function(e) {
                var btn = e.target.closest('.tv-btn, .sina-btn');
                if (btn) {
                    var tk = btn.getAttribute('data-ticker');
                    if (tk) {
                        tk = tk.trim().toUpperCase();
                        var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);

                        // 1. 前台 DOM 瞬间更新该 ticker 所有对应按钮数值 (秒级反馈)
                        try {
                            var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');
                            for (var i = 0; i < allBtns.length; i++) {
                                var b = allBtns[i];
                                var bTk = b.getAttribute('data-ticker');
                                if (bTk && bTk.trim().toUpperCase() === tk) {
                                    var spans = b.getElementsByTagName('span');
                                    if (spans && spans.length > 0) {
                                        var span = spans[spans.length - 1];
                                        var txt = span.innerText || span.textContent || "";
                                        var m = txt.match(/\((\d+)\/(\d+)\)/);
                                        if (m) {
                                            var today = parseInt(m[1], 10) + 1;
                                            var total = parseInt(m[2], 10) + 1;
                                            span.innerText = '(' + today + '/' + total + ')';
                                            span.className = 'click-count-badge today-active';
                                        }
                                    }
                                }
                            }
                        } catch(err) {}

                        // 2. 通过 Streamlit 双向组件桥接器通知 Python 后台永久落盘
                        try {
                            if (window.parent && window.parent.__sendTvClickToStreamlit) {
                                window.parent.__sendTvClickToStreamlit(tk);
                            }
                        } catch(err) {}
                        try {
                            window.parent.postMessage({ type: "record_tv_click", ticker: tk }, "*");
                        } catch(err) {}
                        try {
                            var iframes = pDoc.querySelectorAll('iframe');
                            for (var j = 0; j < iframes.length; j++) {
                                try {
                                    iframes[j].contentWindow.postMessage({ type: "record_tv_click", ticker: tk }, "*");
                                } catch(err) {}
                            }
                        } catch(err) {}
                    }
                }
            };
            pDoc.addEventListener('click', pDoc._tv_click_handler, true);
        } catch(err) {}
    })();
    </script>
    """
    if hasattr(st, "html"):
        st.html(_js_code)
    else:
        import streamlit.components.v1 as _components
        _components.html(_js_code, height=0, width=0)


if __name__ == "__main__":
    render_triple_pattern_page()
