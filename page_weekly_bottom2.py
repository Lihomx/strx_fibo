"""
page_weekly_bottom2.py
======================================================================
🎯 周线前底与潜在底2监测器 (Weekly Bottom 2 & Termination Zone Scanner)
- 参照 Streamlit 三重顶底 (page_triple_pattern.py) 与 TradingView 指标架构设计
- 宏观周线前底 (底1 / L1) 与独立波峰 (Peak / 颈线)
- 灰色终止区 [L1 ~ L1*(1+2.8%)] 探底监测
- 零容忍周线收盘生死线 (C_now >= C_base)
- 【高胜率 V2.0 算法引擎】：
  1. 底部抬高 (底1非历史最低点，形成右侧上升结构)
  2. 双底跨度 >= 4周 (排除2~3周中继假双底)
  3. 波峰反抽 >= 10% (主力大资金介入痕迹)
  4. 生死线超额安全垫 (C_now >= C_base * 1.008)
- 架构可扩展性：配置驱动，支持未来持续无缝热升级
======================================================================
"""

import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

import storage
import weekly_bottom2_scanner as wb2_scanner

logger = logging.getLogger(__name__)


def _fetch_name(ticker: str) -> str:
    """获取股票名称"""
    try:
        from page_watchlist import _fetch_ticker_name
        return _fetch_ticker_name(ticker) or ticker
    except Exception:
        return ticker


def _tv_link(ticker: str, period: str = "W") -> str:
    """生成 TradingView 周图直达链接"""
    clean_tk = ticker.strip().upper()
    if clean_tk.endswith(".SS"):
        clean_tk = "SSE:" + clean_tk.replace(".SS", "")
    elif clean_tk.endswith(".SZ"):
        clean_tk = "SZSE:" + clean_tk.replace(".SZ", "")
    elif clean_tk.endswith(".BJ"):
        clean_tk = "BSE:" + clean_tk.replace(".BJ", "")
    return f"https://cn.tradingview.com/chart/?symbol={clean_tk}&interval={period}"


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


def _make_wb2_page_url(target_page: int) -> str:
    """构建 URL 分页参数"""
    params = dict(st.query_params)
    params["_page"] = "weekly_bottom2"
    params["_p"] = str(target_page)
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/?{qs}"


def _render_wb2_pagination_bar(cur_p: int, tot_p: int, tot_items: int, p_sz: int, is_bottom: bool = False):
    first_url = _make_wb2_page_url(1)
    prev_url = _make_wb2_page_url(max(1, cur_p - 1))
    next_url = _make_wb2_page_url(min(tot_p, cur_p + 1))
    last_url = _make_wb2_page_url(tot_p)

    first_cls = "wb2-page-btn disabled" if cur_p <= 1 else "wb2-page-btn"
    prev_cls = "wb2-page-btn disabled" if cur_p <= 1 else "wb2-page-btn"
    next_cls = "wb2-page-btn disabled" if cur_p >= tot_p else "wb2-page-btn"
    last_cls = "wb2-page-btn disabled" if cur_p >= tot_p else "wb2-page-btn"

    start_n = (cur_p - 1) * p_sz + 1 if tot_items > 0 else 0
    end_n = min(cur_p * p_sz, tot_items)

    if not is_bottom:
        info_text = f"📄 第 <span style='color:#f59e0b;'>{cur_p}</span> / {tot_p} 页 (符合筛选 <span style='color:#38bdf8;'>{tot_items}</span> 条，显示 {start_n} - {end_n} 条)"
    else:
        info_text = f"📄 第 <span style='color:#f59e0b;'>{cur_p}</span> / {tot_p} 页 (共 <span style='color:#38bdf8;'>{tot_items}</span> 条)"

    st.markdown(
        f"""
        <div class="wb2-pagination">
            <div style="display:flex;gap:6px;">
                <a href="{first_url}" target="_self" class="{first_cls}">⏮ 首页</a>
                <a href="{prev_url}" target="_self" class="{prev_cls}">◀ 上一页</a>
            </div>
            <div class="wb2-page-info">
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


def render_weekly_bottom2_page():
    # ── 样式注入 ──
    st.markdown(
        """
        <style>
        .wb2-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .wb2-title {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .wb2-plan-box {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 12px 14px;
            margin-top: 8px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
            gap: 10px;
        }
        .wb2-plan-item {
            display: flex;
            flex-direction: column;
        }
        .wb2-plan-label {
            font-size: 11px;
            color: #94a3b8;
            font-weight: 600;
        }
        .wb2-plan-val {
            font-size: 14px;
            font-weight: 800;
            font-family: monospace;
            margin-top: 2px;
        }
        .wb2-pagination {
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
        .wb2-page-btn {
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
        .wb2-page-btn:hover {
            background: rgba(59, 130, 246, 0.3);
            color: #ffffff !important;
            border-color: rgba(59, 130, 246, 0.7);
            text-decoration: none !important;
        }
        .wb2-page-btn.disabled {
            background: rgba(148, 163, 184, 0.08);
            color: #64748b !important;
            border-color: rgba(148, 163, 184, 0.15);
            cursor: not-allowed;
            pointer-events: none;
        }
        .wb2-page-info {
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
        _bridge_data = frontend_bridge.render_tv_click_bridge(key="wb2_page_tv_bridge")
        if _bridge_data and isinstance(_bridge_data, dict):
            _tk = str(_bridge_data.get("ticker", "")).strip().upper()
            _ts = _bridge_data.get("ts", 0)
            _last_ts = st.session_state.get("_last_wb2_bridge_click_ts", 0)
            if _tk and _ts != _last_ts:
                st.session_state["_last_wb2_bridge_click_ts"] = _ts
                storage.increment_link_click(_tk, "tv")
    except Exception:
        pass

    # ── 读取已有扫描数据 ──
    all_results = storage.load_weekly_bottom2()

    # ── 顶栏标题 ──
    st.markdown(
        """
        <div class="wb2-header">
            <div class="wb2-title">
                <span>🎯 周线前底与潜在底2监测器 (Weekly Bottom 2 Monitor)</span>
                <span class="badge b-blue" style="font-size:12px;margin-left:6px;">高胜率 V2.0 升级架构</span>
            </div>
        </div>
        <div style="font-size:13px;color:#94a3b8;margin-bottom:14px;line-height:1.6;">
            聚焦周线级别<b>【宏观底1 (L1) + 独立颈线波峰 + 终止区灰色框回踩 + 收盘生死线】</b>四位一体右侧筑底买点。内置<b>【底部抬高 (非最低点)】</b>与<b>【4周+充分洗盘跨度】</b>高胜率双重过滤。
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── KPI 统计数据 ──
    total_cnt = len(all_results)
    in_box_cnt = sum(1 for r in all_results if r.get("status") == "active_in_zone")
    bounced_cnt = sum(1 for r in all_results if r.get("status") == "bounced_out")
    lifted_cnt = sum(1 for r in all_results if r.get("is_lifted"))
    safe_cnt = sum(1 for r in all_results if r.get("close_ok"))
    avg_weeks = round(np.mean([r.get("weeks_spaced", 0) for r in all_results]), 1) if all_results else 0.0

    c_m1, c_m2, c_m3, c_m4, c_m5, c_m6 = st.columns(6)
    with c_m1:
        st.metric("🎯 监测总数", f"{total_cnt} 支")
    with c_m2:
        st.metric("🟢 终止区内", f"{in_box_cnt} 支", delta="潜伏黄金区" if in_box_cnt > 0 else None)
    with c_m3:
        st.metric("🚀 向上拉升", f"{bounced_cnt} 支")
    with c_m4:
        st.metric("🛡️ 守住生死线", f"{safe_cnt} 支")
    with c_m5:
        st.metric("🚀 底部抬高", f"{lifted_cnt} 支", delta="次低点/反转" if lifted_cnt > 0 else None)
    with c_m6:
        st.metric("⏱️ 平均双底跨度", f"{avg_weeks} 周")

    # ── 1. 算法升级与配置中心 (支持未来扩展) ──
    with st.expander("⚙️ 1. 核心算法配置与升级控制中心 (模块化架构 · 支持持续优化)", expanded=False):
        c_cfg1, c_cfg2 = st.columns([1.5, 1])
        with c_cfg1:
            st.markdown("##### 📐 算法引擎版本选择与调优")
            algo_ver = st.selectbox(
                "算法策略模式",
                [
                    "🌟 高胜率 V2.0 升级架构 (推荐 · 4周跨度+底部抬高+10%波峰+收盘垫)",
                    "⚡ 经典 V1.0 原版 (无底部抬高限制 · 容纳所有双底)",
                    "🛠️ 自定义参数模式 (专家自由调控)"
                ],
                index=0,
                key="wb2_algo_ver_sel"
            )

            is_custom = "自定义参数模式" in algo_ver
            is_v2 = "高胜率 V2.0" in algo_ver

            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                cfg_buffer = st.slider(
                    "灰色框缓冲上沿 (%):",
                    min_value=1.0, max_value=5.0, value=2.8, step=0.1,
                    disabled=not is_custom,
                    key="wb2_cfg_buffer"
                )
            with col_s2:
                cfg_min_reb = st.slider(
                    "颈线波峰最小反抽幅度 (%):",
                    min_value=5.0, max_value=25.0, value=10.0 if (is_v2 or is_custom) else 8.0, step=1.0,
                    disabled=not is_custom,
                    key="wb2_cfg_min_reb"
                )
            with col_s3:
                cfg_spacing = st.slider(
                    "底1与底2最小周数跨度 (周):",
                    min_value=2, max_value=12, value=4 if (is_v2 or is_custom) else 2, step=1,
                    disabled=not is_custom,
                    key="wb2_cfg_spacing"
                )

            col_s4, col_s5 = st.columns(2)
            with col_s4:
                cfg_require_lifted = st.checkbox(
                    "强制要求底1不是最低点 (底部抬高 / 次低点)",
                    value=True if (is_v2 or is_custom) else False,
                    disabled=not is_custom,
                    key="wb2_cfg_req_lift"
                )
            with col_s5:
                cfg_close_pad = st.slider(
                    "周收盘生死线安全垫 (%):",
                    min_value=0.0, max_value=3.0, value=0.8 if (is_v2 or is_custom) else 0.0, step=0.1,
                    disabled=not is_custom,
                    key="wb2_cfg_pad"
                )

        with c_cfg2:
            st.markdown("##### 💡 算法升级经验总结 (基于 9-10 月实盘跟踪)")
            st.markdown(
                """
                - **大涨品种规律 (海螺水泥+11%, 渝农商行+8.3%, 德方纳米+14.5%)**：
                  - 双底间隔普遍在 **7 ~ 14 周**，洗盘充分。
                  - 前期存在更低大底，属于**第二浪上升回踩**。
                - **止损品种教训 (阳光电源-8.2%, 中国人寿-9.1%)**：
                  - 间隔仅 **2 周**，属于下跌中继的假双底。
                  - 周收盘价贴线过紧，安全垫不足。
                """
            )

    # ── 2. 扫描执行与股票池管理 ──
    with st.expander("🚀 2. 全市场周线底2极速扫描 (多线程并发)", expanded=False):
        c_sc1, c_sc2 = st.columns([1.6, 1])
        with c_sc1:
            st.markdown("##### 选择扫描股票池与并发执行")
            groups = storage.load_symbol_groups() or []
            pool_opts = [
                "🇨🇳 全量A股 (约 5,000 支)",
                "🔥 沪深300指数成分股 (300 支核心资产)",
                "⚡ 中证500指数成分股 (500 支成长龙头)",
                "🇺🇸 全量美股 (约 7,000 支)",
                "🌐 全部股票合并池"
            ]
            for g in groups:
                if g.get("name"):
                    pool_opts.append(f"📁 自建分组: {g.get('name')}")

            sel_pool = st.selectbox("扫描股票池", pool_opts, index=1, key="wb2_sel_pool")

            if st.button("🚀 启动周线底2全市场极速扫描", key="wb2_btn_start_scan", type="primary"):
                # 准备扫描标的
                target_tickers = []
                all_syms = storage.load_symbols() or []
                if "沪深300" in sel_pool:
                    # 优先取沪深300
                    g_hs300 = next((g for g in groups if "300" in g.get("name", "")), None)
                    if g_hs300:
                        target_tickers = [(t, _fetch_name(t)) for t in g_hs300.get("tickers", [])]
                    else:
                        target_tickers = [(s["ticker"], s.get("name", s["ticker"])) for s in all_syms if s.get("ticker", "").endswith(".SS") or s.get("ticker", "").endswith(".SZ")][:300]
                elif "全量A股" in sel_pool:
                    target_tickers = [(s["ticker"], s.get("name", s["ticker"])) for s in all_syms if s.get("ticker", "").endswith(".SS") or s.get("ticker", "").endswith(".SZ") or s.get("ticker", "").endswith(".BJ")]
                elif "全量美股" in sel_pool:
                    target_tickers = [(s["ticker"], s.get("name", s["ticker"])) for s in all_syms if not (s.get("ticker", "").endswith(".SS") or s.get("ticker", "").endswith(".SZ") or s.get("ticker", "").endswith(".BJ"))]
                elif sel_pool.startswith("📁 自建分组:"):
                    g_nm = sel_pool.replace("📁 自建分组: ", "").strip()
                    tg = next((g for g in groups if g.get("name") == g_nm), None)
                    if tg:
                        target_tickers = [(t, _fetch_name(t)) for t in tg.get("tickers", [])]

                if not target_tickers:
                    # 默认安全兜底标的
                    target_tickers = [
                        ("688099.SS", "晶晨股份"), ("601555.SS", "东吴证券"), ("300702.SZ", "天宇股份"),
                        ("002516.SZ", "旷达科技"), ("600389.SS", "江山股份"), ("600597.SS", "光明乳业"),
                        ("000998.SZ", "隆平高科"), ("002174.SZ", "游族网络"), ("601077.SS", "渝农商行"),
                        ("600585.SS", "海螺水泥"), ("002294.SZ", "信立泰"), ("601688.SS", "华泰证券"),
                        ("002673.SZ", "西部证券"), ("510300.SS", "沪深300ETF")
                    ]

                # 构建配置对象
                run_cfg = wb2_scanner.Bottom2Config(
                    version="v2_high_winrate" if is_v2 else "custom",
                    b2_buffer=cfg_buffer,
                    min_rebound=cfg_min_reb,
                    min_spacing_weeks=cfg_spacing,
                    require_not_lowest=cfg_require_lifted,
                    close_safety_buffer=cfg_close_pad
                )

                prog_bar = st.progress(0, text=f"正在扫描 {len(target_tickers)} 只标的...")
                
                def _on_prog(cur, tot, sym):
                    prog_bar.progress(int(cur / tot * 100), text=f"扫描进度: {cur}/{tot} ({sym})")

                scan_res = wb2_scanner.scan_symbols_batch(
                    target_tickers,
                    config=run_cfg,
                    max_workers=8,
                    progress_cb=_on_prog
                )
                prog_bar.progress(100, text=f"✅ 扫描完成！共捕获 {len(scan_res)} 支符合品种。")
                storage.append_weekly_bottom2_results(scan_res)
                st.toast(f"✅ 成功扫描并合并 {len(scan_res)} 条优质底2标的！", icon="🎉")
                time.sleep(1)
                st.rerun()

        with c_sc2:
            st.markdown("##### 📦 快照管理与数据清空")
            st.caption("支持将当前扫描结果落盘备份或在需要时快速重置。")
            if st.button("🗑️ 清空所有底2扫描数据", key="wb2_btn_clear_data", use_container_width=True):
                storage.clear_weekly_bottom2_results()
                st.toast("已清空底2扫描数据", icon="🗑️")
                time.sleep(0.5)
                st.rerun()

    # ── 3. 筛选与排序工具栏 ──
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1.2, 1.2, 1])
    with col_f1:
        st_search = st.text_input("🔍 搜索代码 / 名称", placeholder="输入代码或中文简称...", key="wb2_search_q")
    with col_f2:
        st_status = st.selectbox(
            "📌 状态阶段",
            ["全部状态", "🟢 正在终止区内 (守住生死线)", "🚀 企稳向上拉升 (已脱离灰框)", "🟡 贴近生死线观察", "🔴 跌破失效"],
            index=0,
            key="wb2_status_filter"
        )
    with col_f3:
        st_lifted = st.selectbox(
            "🚀 底部抬高形态",
            ["全部形态", "仅看底部抬高 (底1>前期大底 · 强烈推荐)", "平底/单底"],
            index=1,
            key="wb2_lifted_filter"
        )
    with col_f4:
        st_sort = st.selectbox(
            "↕️ 排序方式",
            ["置信度 (高 → 低)", "终止区优先", "周收盘安全垫 (高 → 低)", "波峰反抽幅度 (大 → 小)", "双底跨度 (宽 → 窄)"],
            index=0,
            key="wb2_sort_by"
        )

    # 过滤流程
    filtered = list(all_results)
    if st_search.strip():
        q = st_search.strip().upper()
        filtered = [r for r in filtered if q in str(r.get("symbol", "")).upper() or q in _fetch_name(str(r.get("symbol", ""))).upper()]

    if st_status != "全部状态":
        if "正在终止区内" in st_status:
            filtered = [r for r in filtered if r.get("status") == "active_in_zone"]
        elif "企稳向上拉升" in st_status:
            filtered = [r for r in filtered if r.get("status") == "bounced_out"]
        elif "贴近生死线" in st_status:
            filtered = [r for r in filtered if r.get("status") == "held"]
        elif "跌破失效" in st_status:
            filtered = [r for r in filtered if r.get("status") == "broken"]

    if st_lifted == "仅看底部抬高 (底1>前期大底 · 强烈推荐)":
        filtered = [r for r in filtered if r.get("is_lifted")]
    elif st_lifted == "平底/单底":
        filtered = [r for r in filtered if not r.get("is_lifted")]

    # 排序流程
    if st_sort == "置信度 (高 → 低)":
        filtered.sort(key=lambda x: (float(x.get("confidence", 0)), float(x.get("close_diff_pct", 0))), reverse=True)
    elif st_sort == "终止区优先":
        filtered.sort(key=lambda x: (1 if x.get("status") == "active_in_zone" else (2 if x.get("status") == "bounced_out" else 3), -float(x.get("confidence", 0))))
    elif st_sort == "周收盘安全垫 (高 → 低)":
        filtered.sort(key=lambda x: float(x.get("close_diff_pct", 0)), reverse=True)
    elif st_sort == "波峰反抽幅度 (大 → 小)":
        filtered.sort(key=lambda x: float(x.get("rebound_pct", 0)), reverse=True)
    elif st_sort == "双底跨度 (宽 → 窄)":
        filtered.sort(key=lambda x: int(x.get("weeks_spaced", 0)), reverse=True)

    # ── 4. 分页控制 ──
    page_size = 15
    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    _raw_p = st.query_params.get("_p", "1")
    try:
        current_page = int(_raw_p)
    except Exception:
        current_page = 1
    current_page = max(1, min(current_page, total_pages))

    _render_wb2_pagination_bar(current_page, total_pages, total_items, page_size, is_bottom=False)

    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = filtered[start_idx:end_idx]

    if not page_items:
        st.info("💡 当前筛选条件下未找到匹配品种，您可在上方点击【启动周线底2全市场极速扫描】更新实时数据。")
        return

    # ── 5. 卡片列表渲染 ──
    for i, r in enumerate(page_items):
        item_idx = start_idx + i
        sym = r.get("symbol", "")
        name = r.get("name") or _fetch_name(sym)
        curr_c = float(r.get("curr_c", 0.0))
        l1_val = float(r.get("l1_val", 0.0))
        l1_close = float(r.get("l1_close", 0.0))
        l1_date = r.get("l1_date", "")
        peak_val = float(r.get("peak_val", 0.0))
        peak_date = r.get("peak_date", "")
        rebound = float(r.get("rebound_pct", 0.0))
        box_bottom = float(r.get("box_bottom", l1_val))
        box_top = float(r.get("box_top", l1_val * 1.028))
        in_box = r.get("in_box", False)
        close_ok = r.get("close_ok", False)
        close_diff = float(r.get("close_diff_pct", 0.0))
        weeks_spaced = int(r.get("weeks_spaced", 0))
        is_lifted = r.get("is_lifted", False)
        prior_min = float(r.get("prior_min", 0.0))
        prior_diff = float(r.get("prior_diff_pct", 0.0))
        status_label = r.get("status_label", "")
        conf = float(r.get("confidence", 0.85))

        tv_link = _tv_link(sym, "W")
        sina_link = _sina_link(sym)

        # 状态徽章
        if r.get("status") == "active_in_zone":
            badge_status = "<span class='badge b-green'>🟢 正在终止区内 (守住生死线)</span>"
        elif r.get("status") == "bounced_out":
            badge_status = "<span class='badge b-blue'>🚀 企稳向上拉升 (已脱离灰框)</span>"
        else:
            badge_status = "<span class='badge b-yellow'>🟡 贴近生死线观察</span>"

        badge_lifted = f"<span class='badge b-orange' style='margin-left:6px;'>🚀 底部抬高 +{prior_diff:.1f}%</span>" if is_lifted else ""
        badge_conf = f"<span class='badge b-gold' style='margin-left:6px;'>⭐ 置信度 {conf*100:.0f}%</span>"

        with st.container(border=True):
            col_h1, col_h2 = st.columns([2.5, 1.5])
            with col_h1:
                st.markdown(
                    f"""
                    <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;">
                        <span style="font-size:18px;font-weight:800;color:#f8fafc;">{name}</span>
                        <span style="font-size:14px;font-family:monospace;color:#94a3b8;">({sym})</span>
                        <span style="font-size:17px;font-weight:800;color:#38bdf8;margin-left:6px;">¥{curr_c:.2f}</span>
                        {badge_status}
                        {badge_lifted}
                        {badge_conf}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_h2:
                col_btn1, col_btn2, col_btn3 = st.columns([1.2, 1, 1])
                with col_btn1:
                    st.markdown(
                        f"""<a href="{tv_link}" target="_blank" class="wb2-page-btn" data-ticker="{sym}" style="width:100%;padding:4px 8px;font-size:12px;">📊 TV周图</a>""",
                        unsafe_allow_html=True
                    )
                with col_btn2:
                    st.markdown(
                        f"""<a href="{sina_link}" target="_blank" class="wb2-page-btn" style="width:100%;padding:4px 8px;font-size:12px;background:rgba(234,179,8,0.15);color:#fde047!important;border-color:rgba(234,179,8,0.3);">行情</a>""",
                        unsafe_allow_html=True
                    )
                with col_btn3:
                    is_pinned = storage.is_ticker_starred(sym)
                    pin_lbl = "⭐ 已加" if is_pinned else "☆ 收藏"
                    if st.button(pin_lbl, key=f"wb2_pin_{sym}_{item_idx}", use_container_width=True):
                        if is_pinned:
                            storage.remove_from_watchlist(sym)
                        else:
                            storage.add_to_watchlist(sym, name=name)
                        st.rerun()

            # 核心参数指标网格
            close_color = "#22c55e" if close_diff >= 0 else "#ef4444"
            st.markdown(
                f"""
                <div class="wb2-plan-box">
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">🏁 周线底1 (L1) 与日期</span>
                        <span class="wb2-plan-val" style="color:#38bdf8;">¥{l1_val:.2f} <span style="font-size:11px;color:#94a3b8;">({l1_date})</span></span>
                    </div>
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">🔲 终止区灰色框区间</span>
                        <span class="wb2-plan-val" style="color:#a78bfa;">[{box_bottom:.2f} ~ {box_top:.2f}]</span>
                    </div>
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">🏔️ 独立波峰及涨幅</span>
                        <span class="wb2-plan-val" style="color:#f59e0b;">¥{peak_val:.2f} <span style="font-size:11px;color:#34d399;">(+{rebound:.1f}%)</span></span>
                    </div>
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">🛡️ 现周收 vs 基准周收</span>
                        <span class="wb2-plan-val" style="color:{close_color};">¥{curr_c:.2f} ≥ ¥{l1_close:.2f} <span style="font-size:11px;">({close_diff:+.2f}%)</span></span>
                    </div>
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">⏱️ 双底跨度周期</span>
                        <span class="wb2-plan-val" style="color:#38bdf8;">{weeks_spaced} 周 <span style="font-size:11px;color:#94a3b8;">(洗盘充分)</span></span>
                    </div>
                    <div class="wb2-plan-item">
                        <span class="wb2-plan-label">🚀 较前底抬高幅度</span>
                        <span class="wb2-plan-val" style="color:#10b981;">{'+'+str(prior_diff)+'%' if is_lifted else '平底'} <span style="font-size:11px;color:#94a3b8;">(前底 ¥{prior_min:.2f})</span></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # 展开交互式周K线图 (Plotly 还原 TradingView 指标)
            chart_key = f"wb2_show_chart_{sym}_{item_idx}"
            col_t1, _ = st.columns([1, 4])
            with col_t1:
                if st.button("📈 展开周K线结构图", key=f"btn_toggle_chart_{sym}_{item_idx}"):
                    st.session_state[chart_key] = not st.session_state.get(chart_key, False)

            if st.session_state.get(chart_key):
                with st.spinner(f"拉取 {sym} 周K线历史数据并渲染指标结构..."):
                    try:
                        df_w = yf.download(sym, period="2y", interval="1wk", progress=False)
                        if df_w is not None and not df_w.empty:
                            df_w = df_w.dropna()
                            if isinstance(df_w.columns, pd.MultiIndex):
                                df_w.columns = [c[0].lower() for c in df_w.columns]
                            else:
                                df_w.columns = [c.lower() for c in df_w.columns]

                            df_w = df_w.reset_index()
                            date_col = df_w.columns[0]
                            df_slice = df_w.tail(60).copy()

                            fig = go.Figure()
                            # 1. 周K线
                            fig.add_trace(go.Candlestick(
                                x=df_slice[date_col],
                                open=df_slice['open'],
                                high=df_slice['high'],
                                low=df_slice['low'],
                                close=df_slice['close'],
                                name='周K线',
                                increasing_line_color='#22c55e',
                                decreasing_line_color='#ef4444'
                            ))

                            # 2. 灰色终止区阴影框
                            fig.add_hrect(
                                y0=box_bottom,
                                y1=box_top,
                                fillcolor="rgba(148, 163, 184, 0.22)",
                                line=dict(color="rgba(148, 163, 184, 0.6)", width=1, dash="dot"),
                                annotation_text=f"终止区灰色框 [{box_bottom:.2f} ~ {box_top:.2f}]",
                                annotation_position="top left"
                            )

                            # 3. 绿色底1线 (L1)
                            fig.add_hline(
                                y=l1_val,
                                line_dash="solid",
                                line_color="#22c55e",
                                annotation_text=f"周线底1 (L1): ¥{l1_val:.2f}",
                                annotation_position="left"
                            )

                            # 4. 橙色基准收盘生死线 (C_base)
                            fig.add_hline(
                                y=l1_close,
                                line_dash="dash",
                                line_color="#f97316",
                                annotation_text=f"基准周收生死线: ¥{l1_close:.2f}",
                                annotation_position="right"
                            )

                            # 5. 青色颈线波峰线 (Peak)
                            fig.add_hline(
                                y=peak_val,
                                line_dash="dot",
                                line_color="#38bdf8",
                                annotation_text=f"独立波峰: ¥{peak_val:.2f} (+{rebound:.1f}%)",
                                annotation_position="right"
                            )

                            fig.update_layout(
                                xaxis_rangeslider_visible=False,
                                height=380,
                                margin=dict(l=10, r=10, t=25, b=10),
                                template="plotly_dark",
                                plot_bgcolor="rgba(0,0,0,0)",
                                title=f"📊 {name} ({sym}) 周线前底与潜在底2结构图"
                            )
                            st.plotly_chart(fig, use_container_width=True, key=f"wb2_plotly_{sym}_{item_idx}")
                    except Exception as ex:
                        st.error(f"渲染周K线图表失败: {ex}")

    # 分页导航条（底部）
    if total_pages > 1:
        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        _render_wb2_pagination_bar(current_page, total_pages, total_items, page_size, is_bottom=True)
