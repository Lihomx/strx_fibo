"""
page_triple_bottom.py — 三重底多周期扫描页面
=========================================
实现思路：
  - 新增独立页面展现，避免对原有实时扫描页造成性能卡顿
  - 支持多周期切换：30分钟、1小时、4小时、日线
  - 支持对自选股、热门品种或指定股票进行多周期即时扫描
  - 提供形态子类型分类过滤 (7种 Al Brooks 三重底变体)
  - 集成 Plotly 交互 K 线图，在图表上以标记点 (Scatter) 突出展示 3 个低点、支撑线与形态特征
  - 一键同步/添加到自选收藏夹，并自动附带 "TripleBottom" 与具体形态标签
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime
import plotly.graph_objects as go

import storage
import bg_scan_manager
from streamlit_autorefresh import st_autorefresh
from scanner import fetch_data
from triple_bottom_scanner import scan_triple_bottoms, PatternMatch

# ── 支持的时间框架配置 ──
TRIPLE_BOTTOM_TIMEFRAMES = {
    "30m": ("30m", "60d", "30分钟"),
    "60m": ("60m", "720d", "1小时"),
    "4h":  ("4h",  "2y",   "4小时"),
    "1d":  ("1d",  "2y",   "日线"),
    "1w":  ("1wk", "5y",   "周线"),
    "1mo": ("1mo", "10y",  "月线"),
}

# ── TradingView 周期映射（period key → TV interval 参数） ──
_TB_TV_INTERVAL = {
    "30m": "30",
    "60m": "60",
    "4h":  "240",
    "1d":  "D",
    "1w":  "W",
    "1mo": "M",
}

def _tv_link(ticker: str, period: str = "1d") -> str:
    """生成带周期参数的 TradingView CN 链接"""
    try:
        from assets import tv_symbol
        sym = tv_symbol(ticker)
    except Exception:
        sym = ticker
    interval = _TB_TV_INTERVAL.get(period, "D")
    return f"https://cn.tradingview.com/chart/?symbol={sym}&interval={interval}"


def _render_tb_restore_session_controls():
    sessions = storage.load_tb_snapshots()
    options = []
    sid_map = {}
    for s in sessions:
        sid = str(s.get("session_id", "")).strip()
        scan_time = s.get("scan_time") or "—"
        count = s.get("count", 0)
        label = f"{scan_time} | 数量 {count} | {sid[:15]}…"
        options.append(label)
        sid_map[label] = sid

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🗑️ 清空扫描结果", key="tb_clear_results_btn", help="清空当前所有扫描结果，清空前会自动备份快照", use_container_width=True):
            storage.clear_triple_bottom_results()
            st.success("已成功清空当前扫描结果（已自动备份）")
            time.sleep(1)
            st.rerun()

    with col2:
        if not options:
            st.selectbox(
                "恢复批次",
                ["暂无可恢复批次（无快照）"],
                key="tb_restore_session_picker_empty",
                disabled=True,
                label_visibility="collapsed",
            )
            st.button(
                "♻️ 恢复所选批次",
                key="tb_restore_selected_scan_btn_disabled",
                disabled=True,
                use_container_width=True,
            )
        else:
            sub_col1, sub_col2 = st.columns([2, 1])
            with sub_col1:
                selected_label = st.selectbox(
                    "恢复批次",
                    options,
                    key="tb_restore_session_picker",
                    label_visibility="collapsed",
                )
            with sub_col2:
                sid = sid_map.get(selected_label, "")
                if st.button(
                    "♻️ 恢复所选批次",
                    key="tb_restore_selected_scan_btn",
                    help="恢复你当前选择的三重底扫描批次快照",
                    type="secondary",
                    use_container_width=True,
                    disabled=not sid,
                ):
                    ok, msg, n = storage.restore_tb_snapshot(sid)
                    if ok:
                        st.toast(f"已恢复批次 {sid[:12]}…（{n} 条）", icon="♻️")
                        time.sleep(1)
                        st.rerun()
                    st.error(msg)


def _row_anchor_id(ticker: str, period: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", f"{ticker}_{period}".upper())
    return f"tb_row_{safe}"

def _fetch_name(ticker: str) -> str:
    """复用 Watchlist 的公司名获取逻辑，带 session_state 缓存"""
    cache = st.session_state.setdefault("_yfname_cache", {})
    key = ticker.upper().strip()
    if key in cache:
        return cache[key]
    
    # 简单新浪/yfinance查名
    name = key
    if key.isdigit() and len(key) == 6:
        # A股
        try:
            import requests
            prefix = "sh" if key.startswith("6") or key.startswith("5") else "sz"
            r = requests.get(f"https://hq.sinajs.cn/list={prefix}{key}", headers={"Referer": "https://finance.sina.com.cn"}, timeout=3)
            r.encoding = "gbk"
            text = r.text
            start = text.find('"')
            end = text.rfind('"')
            if start != -1 and end > start:
                fields = text[start+1:end].split(",")
                if fields and fields[0]:
                    name = fields[0]
        except Exception:
            pass
    cache[key] = name
    return name

def triple_bottom_worker(params, update_progress, cancel_check):
    tickers_to_scan = params["tickers_to_scan"]
    selected_periods = params["selected_periods"]
    swing_win = params["swing_win"]
    lookback = params["lookback"]
    max_sp = params["max_sp"]
    min_conf = params["min_conf"]
    flat_tol = params.get("flat_tol", 0.02)
    break_tol = params.get("break_tol", 0.01)
    
    total_steps = len(tickers_to_scan) * len(selected_periods)
    step = 0
    new_results = []
    
    for ticker in tickers_to_scan:
        if cancel_check():
            break
        for period_key in selected_periods:
            if cancel_check():
                break
            step += 1
            interval, yf_period, period_desc = TRIPLE_BOTTOM_TIMEFRAMES[period_key]
            update_progress(step, total_steps, f"{ticker} ({period_desc})")
            try:
                df = fetch_data(ticker, interval=interval, period=yf_period)
                if df is not None and not df.empty:
                    matches = scan_triple_bottoms(
                        df,
                        symbol=ticker,
                        swing_window=int(swing_win),
                        lookback_bars=int(lookback),
                        max_spacing=int(max_sp),
                        flat_tol=flat_tol,
                        break_tol=break_tol,
                    )
                    for m in matches:
                        if m.confidence >= min_conf:
                            new_results.append({
                                "symbol": m.symbol,
                                "period": period_key,
                                "pattern": m.pattern,
                                "confidence": m.confidence,
                                "idx1": int(m.idx1),
                                "idx2": int(m.idx2),
                                "idx3": int(m.idx3),
                                "low1": float(m.low1),
                                "low2": float(m.low2),
                                "low3": float(m.low3),
                                "mid_high": float(m.mid_high),
                                "note": m.note,
                                "status": m.status,
                                "status_reason": m.status_reason,
                                "bars_since_low3": int(m.bars_since_low3),
                                "latest_close": float(m.latest_close),
                                "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
            except Exception:
                pass
                
    storage.save_triple_bottom(new_results)


def render_triple_bottom_page():
    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        st_autorefresh(interval=3000, key="triple_bottom_auto_refresh")
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="tb_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status["job_type"] == "triple_bottom":
        if status["status"] == "done":
            st.success(f"✅ 后台扫描任务已完成!")
        elif status["status"] == "error":
            st.error(f"❌ 后台扫描任务出错! 错误信息: {status.get('error', '')}")
        elif status["status"] == "cancelled":
            st.warning("⚠️ 后台扫描任务已被取消。")
            
        if st.button("清除状态提示", key="tb_clear_status_btn"):
            bg_scan_manager.reset_to_idle()
            st.rerun()

    st.markdown("### 📊 三重底多周期扫描")
    st.markdown(
        "<div style='font-size:13px;color:#6b7280;margin-bottom:15px;'>"
        "基于 Al Brooks 价格行为学设计，自动寻找支撑带附近的三次下探尝试，"
        "识别完美三重底、头肩底、双底回调以及失败突破跌破等 7 种细分形态。"
        "</div>",
        unsafe_allow_html=True
    )

    # ── 恢复/清空扫描结果控件 ──
    _render_tb_restore_session_controls()
    st.markdown("<hr style='margin:15px 0; border-color:#e5e7eb'>", unsafe_allow_html=True)


    # ── 1. 侧边栏及控制面板 ──
    st.sidebar.markdown("### ⚙️ 三重底扫描配置")
    
    # 选择周期（可多选进行扫描，单选进行展示）
    selected_periods = st.sidebar.multiselect(
        "选择扫描周期",
        options=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
        default=["4h", "1d"],
        format_func=lambda x: TRIPLE_BOTTOM_TIMEFRAMES[x][2]
    )

    min_conf = st.sidebar.slider("置信度阈值", 0.3, 1.0, 0.5, 0.05,
        help="置信度越低，筛选越宽松。建议先用 0.4~0.5 试扫")
    swing_win = st.sidebar.number_input("分形阶数 (Window)", 2, 10, 3,
        help="左右各看几根K线来确认局部低点，越小越灵敏")
    max_sp = st.sidebar.number_input("三点最大跨度 (K线数)", 20, 200, 80,
        help="三个探底低点最大允许间隔，越大形态跨度越长")
    lookback = st.sidebar.number_input("扫描回溯长度 (Bars)", 50, 500, 150,
        help="向前看多少根K线内的数据")

    st.sidebar.markdown("**📐 形态宽松度**")
    flat_tol_pct = st.sidebar.slider("低点容差 (%)", 0.5, 10.0, 2.0, 0.5,
        help="三个低点之间允许的最大百分比差异。越大越容易匹配，建议 1.5~3%")
    break_tol_pct = st.sidebar.slider("跌破容差 (%)", 0.2, 5.0, 1.0, 0.2,
        help="失败突破型：允许价格跌破支撑多少百分比后被视为'失败突破'")
    flat_tol = flat_tol_pct / 100.0
    break_tol = break_tol_pct / 100.0

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ 扫描控制")
    scan_target = st.sidebar.radio("扫描目标", ["自选股 (Watchlist)", "热门品种 (Hotlist)", "自定义分组", "指定代码"])

    custom_ticker_input = ""
    selected_group_id = None
    if scan_target == "指定代码":
        custom_ticker_input = st.sidebar.text_input("输入代码 (多个用逗号隔开)", "AAPL,BTC-USD,000001.SS")
    elif scan_target == "自定义分组":
        groups = storage.load_symbol_groups()
        if not groups:
            st.sidebar.warning("⚠️ 暂无自定义分组，请前往 品种库 页面创建。")
        else:
            grp_map = {g["name"]: g["id"] for g in groups}
            selected_grp_name = st.sidebar.selectbox("选择分组", list(grp_map.keys()))
            selected_group_id = grp_map[selected_grp_name]

    is_running = bg_scan_manager.is_running()
    run_scan = st.sidebar.button("🚀 开始分析扫描", type="primary", use_container_width=True, disabled=is_running)
    if st.session_state.pop("_trigger_mobile_scan", False):
        run_scan = True

    # ── 2. 扫描数据存取 ──
    results = storage.load_triple_bottom()

    if run_scan:
        if not selected_periods:
            st.error("请至少选择一个扫描周期！")
            return

        tickers_to_scan = []
        if scan_target == "自选股 (Watchlist)":
            wl = storage.load_watchlist()
            tickers_to_scan = [item["ticker"] for item in wl]
        elif scan_target == "热门品种 (Hotlist)":
            hl = storage.load_hotlist()
            tickers_to_scan = [item["ticker"] for item in hl]
        elif scan_target == "自定义分组":
            if selected_group_id:
                groups = storage.load_symbol_groups()
                target_grp = next((g for g in groups if g["id"] == selected_group_id), None)
                if target_grp:
                    tickers_to_scan = target_grp.get("tickers", [])
        else:
            tickers_to_scan = [t.strip().upper() for t in custom_ticker_input.split(",") if t.strip()]

        if not tickers_to_scan:
            st.warning("扫描队列为空，未找到任何代码。")
            return

        params = {
            "tickers_to_scan": tickers_to_scan,
            "selected_periods": selected_periods,
            "swing_win": swing_win,
            "lookback": lookback,
            "max_sp": max_sp,
            "min_conf": min_conf,
            "flat_tol": flat_tol,
            "break_tol": break_tol,
        }
        
        ok, msg = bg_scan_manager.submit_job(
            job_type="triple_bottom",
            label=f"三重底扫描 ({scan_target})",
            params=params,
            worker_fn=triple_bottom_worker
        )
        if ok:
            st.success(msg)
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)

    # ── 3. 主界面形态展示与过滤 ──
    if not results:
        st.info("💡 尚未运行过扫描或没有匹配形态。请在左侧配置参数并点击「🚀 开始分析扫描」。")
        return

    # 按置信度降序排列
    results = sorted(results, key=lambda x: x.get("confidence", 0.0), reverse=True)

    # 选项卡过滤：形态细分过滤
    pattern_types = [
        "全部",
        "完美三重底 (Perfect Triple Bottom)",
        "头肩底/截断楔形 (Head & Shoulders Bottom)",
        "双底跌破失败型 (Failed BO below DB)",
        "双底回调型 (Double Bottom Pullback)",
        "抬高双底失败突破型 (Failed BO below HL DB)",
        "楔形三重底 (Wedge)",
        "三角形三重底 (Triangle)",
        "未分类三次探底 (Unclassified 3-push)"
    ]

    col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 1.6])
    with col_f1:
        sel_patt = st.selectbox("筛选形态类别", pattern_types)
    with col_f2:
        st_period = st.multiselect(
            "筛选周期",
            options=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
            default=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
            format_func=lambda x: TRIPLE_BOTTOM_TIMEFRAMES[x][2]
        )
    with col_f3:
        st_status = st.multiselect(
            "筛选有效状态",
            options=["观望中 (active)", "已突破 (confirmed)", "已失效 (invalidated)", "已过期 (expired)"],
            default=["观望中 (active)", "已突破 (confirmed)"],
            help="失效或过期的形态默认被隐藏，勾选即可恢复显示"
        )

    # 映射 status
    selected_statuses = []
    for s in st_status:
        if "active" in s:
            selected_statuses.append("active")
        elif "confirmed" in s:
            selected_statuses.append("confirmed")
        elif "invalidated" in s:
            selected_statuses.append("invalidated")
        elif "expired" in s:
            selected_statuses.append("expired")

    # 执行前端筛选
    filtered = []
    for r in results:
        if sel_patt != "全部" and sel_patt not in r.get("pattern", ""):
            continue
        if r.get("period") not in st_period:
            continue
        status_val = r.get("status", "active")
        if status_val not in selected_statuses:
            continue
        filtered.append(r)

    st.markdown(f"**符合当前筛选条件的形态：{len(filtered)} / {len(results)} 个**")
    st.markdown("<hr style='margin:10px 0; border-color:#e5e7eb'>", unsafe_allow_html=True)

    # 循环渲染每一项
    for i, r in enumerate(filtered):
        ticker = r["symbol"]
        period = r["period"]
        patt_desc = r["pattern"]
        conf = r["confidence"]
        note = r["note"]
        status_val = r.get("status", "active")
        status_reason = r.get("status_reason", "")
        period_desc = TRIPLE_BOTTOM_TIMEFRAMES[period][2]
        name = _fetch_name(ticker)

        anchor = _row_anchor_id(ticker, period)
        st.markdown(f"<div id='{anchor}'></div>", unsafe_allow_html=True)

        # 构造状态徽章
        if status_val == "active":
            status_badge = f"<span style='font-size:12px;background-color:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-weight:600;'>观望中</span>"
        elif status_val == "confirmed":
            status_badge = f"<span style='font-size:12px;background-color:#dcfce7;color:#15803d;padding:2px 8px;border-radius:4px;font-weight:600;'>已突破 🚀</span>"
        elif status_val == "invalidated":
            status_badge = f"<span style='font-size:12px;background-color:#fee2e2;color:#b91c1c;padding:2px 8px;border-radius:4px;font-weight:600;'>已失效 ❌</span>"
        else: # expired
            status_badge = f"<span style='font-size:12px;background-color:#f3f4f6;color:#4b5563;padding:2px 8px;border-radius:4px;font-weight:600;'>已过期 ⏰</span>"

        with st.container(border=True):
            # 卡片标题栏
            col_t1, col_t2 = st.columns([5, 3])
            with col_t1:
                st.markdown(
                    f"#### **{ticker}** · {name} "
                    f"<span style='font-size:12px;background-color:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-weight:600;'>{period_desc}</span> "
                    f"<span style='font-size:12px;background-color:#fef3c7;color:#d97706;padding:2px 8px;border-radius:4px;font-weight:600;'>置信度: {conf:.0%}</span> "
                    f"{status_badge}",
                    unsafe_allow_html=True
                )
            with col_t2:
                # ── 按钮区：K线图 / TradingView / 收藏 ──
                chart_key = f"tb_chart_open_{ticker}_{period}"
                is_open = st.session_state.get(chart_key, False)

                btn_col1, btn_col2, btn_col3 = st.columns(3)
                
                with btn_col1:
                    if st.button("📊 K线图" if not is_open else "❌ 关闭图", key=f"tb_chart_btn_{i}", use_container_width=True):
                        st.session_state[chart_key] = not is_open
                        st.rerun()

                with btn_col2:
                    st.link_button(
                        "📈 TV",
                        _tv_link(ticker, period),
                        help=f"在 TradingView 中打开 {ticker} 的 {period_desc} 图表",
                        use_container_width=True
                    )

                with btn_col3:
                    wl = storage.load_watchlist()
                    is_in_wl = any(item["ticker"].upper() == ticker.upper() for item in wl)
                    
                    if not is_in_wl:
                        if st.button("⭐ 收藏", key=f"tb_add_wl_{i}", help="将该品种加入自选收藏夹，并标记 TripleBottom 标签", use_container_width=True):
                            new_item = {
                                "ticker": ticker,
                                "name": name,
                                "category_id": "unclassified", # 默认未分类
                                "tags": ["TripleBottom", patt_desc.split(" (")[0]],
                                "notes": [{"text": f"三重底自动扫描导入：{patt_desc}", "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}],
                                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            wl.append(new_item)
                            storage.save_watchlist(wl)
                            st.toast(f"已成功添加 {ticker} 至自选收藏夹", icon="⭐")
                            st.rerun()
                    else:
                        if st.button("✅ 已加", key=f"tb_sync_tag_{i}", help="该股票已在自选收藏夹中，点击为该股票追加 TripleBottom 与形态标签", use_container_width=True):
                            for item in wl:
                                if item["ticker"].upper() == ticker.upper():
                                    tags = item.setdefault("tags", [])
                                    added_any = False
                                    if "TripleBottom" not in tags:
                                        tags.append("TripleBottom")
                                        added_any = True
                                    sub_patt = patt_desc.split(" (")[0]
                                    if sub_patt not in tags:
                                        tags.append(sub_patt)
                                        added_any = True
                                    if added_any:
                                        item.setdefault("notes", []).append({
                                            "text": f"三重底自动扫描更新标签：{patt_desc}",
                                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                            storage.save_watchlist(wl)
                            st.toast(f"已成功为 {ticker} 追加三重底识别标签", icon="🏷️")
                            st.rerun()

            # 卡片详细内容
            st.markdown(
                f"<div style='font-size:13px;line-height:1.6;color:#374151;'>"
                f"🏷️ <b>识别形态</b>：{patt_desc}<br>"
                f"🔍 <b>状态跟踪</b>：{status_reason if status_reason else '运行于支撑与颈线之间'}<br>"
                f"📝 <b>形态判定说明</b>：{note}<br>"
                f"📐 <b>低值详情</b>：Low1: {r['low1']:.3f} | Low2: {r['low2']:.3f} | Low3: {r['low3']:.3f} (中间高点: {r['mid_high']:.3f})"
                f"</div>",
                unsafe_allow_html=True
            )



            # ── 展开 K 线图展示（核心高光） ──
            if st.session_state.get(chart_key):
                with st.container(border=True):
                    st.markdown(f"##### 📊 {ticker} - {period_desc} 蜡烛形态图")
                    with st.spinner("拉取数据并标绘形态中..."):
                        try:
                            interval, yf_period, _ = TRIPLE_BOTTOM_TIMEFRAMES[period]
                            df = fetch_data(ticker, interval=interval, period=yf_period)
                            if df is not None and not df.empty:
                                # 获得最尾部的数据
                                df_slice = df.tail(lookback).copy()
                                if isinstance(df_slice.columns, pd.MultiIndex):
                                    df_slice.columns = [c[0].lower() for c in df_slice.columns]
                                else:
                                    df_slice.columns = [c.lower() for c in df_slice.columns]
                                
                                # 将 index 重置为递增自然序号方便用 idx1, idx2, idx3 精准描绘
                                df_slice = df_slice.reset_index()
                                date_col = df_slice.columns[0]
                                
                                fig = go.Figure()
                                # 绘制 K 线
                                fig.add_trace(go.Candlestick(
                                    x=df_slice[date_col],
                                    open=df_slice['open'],
                                    high=df_slice['high'],
                                    low=df_slice['low'],
                                    close=df_slice['close'],
                                    name='蜡烛图',
                                    increasing_line_color='#ef4444',
                                    decreasing_line_color='#10b981'
                                ))

                                # 标记三个低点 (idx1, idx2, idx3)
                                # 注意：如果 df_slice 的长度与扫描时的 lookback 不同，需映射索引位置。
                                # 由于我们 reset 并且重设长度为 lookback，因此索引位置 idx1, idx2, idx3 应该完美对应
                                pts_idx = [r["idx1"], r["idx2"], r["idx3"]]
                                pts_idx = [p for p in pts_idx if 0 <= p < len(df_slice)]
                                
                                if len(pts_idx) == 3:
                                    dates = df_slice.loc[pts_idx, date_col]
                                    lows = df_slice.loc[pts_idx, 'low']
                                    
                                    # 用 Scatter 突出小圆点
                                    fig.add_trace(go.Scatter(
                                        x=dates,
                                        y=lows,
                                        mode='markers+text',
                                        marker=dict(symbol='circle-open', size=15, color='#f59e0b', line=dict(width=3)),
                                        text=["Low1", "Low2", "Low3"],
                                        textposition="bottom center",
                                        textfont=dict(color="#f59e0b", size=12, family="Outfit, Inter"),
                                        name='探底支撑点'
                                    ))

                                    # 绘制最低的支撑线
                                    min_low = min(r["low1"], r["low2"])
                                    fig.add_hline(
                                        y=min_low,
                                        line_dash="dash",
                                        line_color="#d97706",
                                        annotation_text=f"支撑带: {min_low:.3f}",
                                        annotation_position="bottom right"
                                    )

                                fig.update_layout(
                                    xaxis_rangeslider_visible=False,
                                    height=300,
                                    margin=dict(l=10, r=10, t=20, b=10),
                                    template="plotly_dark",
                                    plot_bgcolor="rgba(0,0,0,0)"
                                )
                                st.plotly_chart(fig, use_container_width=True, key=f"tb_fig_{ticker}_{period}_{i}")
                            else:
                                st.warning("未找到足够长的历史 K 线数据，无法还原形态图。")
                        except Exception as ex:
                            st.error(f"渲染图形出错: {ex}")
