"""
page_universe.py — 🌍 全量品种库

⚠️ 关于"全量扫描"的说明：
  A股 5454 支 × 3 个时间框架 = 16362 次网络请求
  按每次 1-2 秒估算 = 约 4-9 小时，Streamlit 会超时中断！

  正确用法：
  1. 使用搜索框找到目标品种
  2. 勾选感兴趣的品种（建议每次 ≤50 支）
  3. 点击「批量扫描选中品种」
  中断后结果会保存，可继续追加扫描更多品种。
"""

import streamlit as st
import pandas as pd

import storage
import scanner as sc


# ════════════════════════════════════════════════════════════════════
# 带 30 分钟缓存的列表加载
# ════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _load_a():
    return sc.get_all_a_share_tickers()

@st.cache_data(ttl=1800, show_spinner=False)
def _load_hk():
    return sc.get_all_hk_tickers()

@st.cache_data(ttl=1800, show_spinner=False)
def _load_us():
    return sc.get_all_us_tickers()


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## 🌍 全量品种库")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '数据来自 <b>AKShare（东方财富）</b>，免费实时，无需 API Key。</p>',
        unsafe_allow_html=True,
    )

    # ── 重要说明横幅 ────────────────────────────────────────────
    st.markdown("""
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;
                padding:12px 16px;margin-bottom:12px;font-size:13px">
    <b>⚠️ 关于全量扫描</b><br>
    A股 5454 支 × 3 框架 = <b>16362 次</b>网络请求，约需 <b>4-9 小时</b>，Streamlit 会超时中断。<br>
    <b>推荐用法</b>：搜索 → 勾选目标品种（建议每批 ≤50 支）→ 批量扫描。<br>
    每次扫描结果会<b>自动保存累积</b>，中断后重新扫描其他品种，结果叠加展示。
    </div>
    """, unsafe_allow_html=True)

    # ── 数据源说明 ───────────────────────────────────────────────
    with st.expander("📡 数据源架构说明", expanded=False):
        st.markdown("""
        | 品种类型 | 主数据源 | 备用数据源 | 覆盖数量 |
        |---------|---------|---------|---------|
        | 🇨🇳 A股 | AKShare（东方财富）✅ 免费 | yfinance（.SS/.SZ） | **5,454** 支 |
        | 🇭🇰 港股 | AKShare（东方财富）✅ 免费 | yfinance（.HK） | **2,516** 支 |
        | 🇺🇸 美股 | AKShare（东方财富）✅ 免费 | yfinance | **16,527** 支 |
        | 🌐 外汇/期货/指数/加密 | yfinance ✅ 免费 | TwelveData（需Key） | 全覆盖 |
        """)

    # ── 市场选择 ────────────────────────────────────────────────
    market = st.radio(
        "选择市场",
        ["🇨🇳 A股（约5454支）", "🇭🇰 港股（约2516支）", "🇺🇸 美股（约16527支）"],
        horizontal=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    cfg = storage.load_config()

    if "A股" in market:
        _render_market("a_share", _load_a, "a_stock", cfg, "A股")
    elif "港股" in market:
        _render_market("hk_stock", _load_hk, "cn_stock", cfg, "港股")
    else:
        _render_market("us_stock", _load_us, "us_stock", cfg, "美股")


# ════════════════════════════════════════════════════════════════════
# 通用市场渲染
# ════════════════════════════════════════════════════════════════════
def _render_market(market_key: str, load_fn, category: str, cfg: dict, label: str):

    # ── 加载品种列表 ────────────────────────────────────────────
    with st.spinner(f"📡 从 AKShare 获取{label}品种列表（约5-15秒）…"):
        try:
            raw_list: list = load_fn()
        except Exception as e:
            st.error(
                f"❌ 加载失败：{e}\n\n"
                f"请确认 `akshare` 已安装（`requirements.txt` 中已包含）。"
            )
            st.info("💡 Streamlit Cloud 首次部署时会自动安装 akshare，约需 1-2 分钟。")
            return

    if not raw_list:
        st.warning("⚠️ 未获取到品种数据，请检查网络连接或稍后重试。")
        return

    total_raw = len(raw_list)
    name_map: dict = {t: n for t, n in raw_list}

    col_stat, col_tip = st.columns([3, 5])
    with col_stat:
        st.success(f"✅ 已加载 **{total_raw:,}** 个{label}品种")
    with col_tip:
        st.markdown(
            f'<div style="color:#6b7280;font-size:12px;padding-top:8px">'
            f'💡 搜索后勾选目标品种，点击「批量扫描」开始分析（建议每批 ≤50 支）</div>',
            unsafe_allow_html=True,
        )

    # ── 搜索 + 排序 + 分页 ──────────────────────────────────────
    col_kw, col_sort, col_ps = st.columns([4, 2, 2])
    with col_kw:
        kw = st.text_input(
            "🔍 搜索品种",
            placeholder="输入代码或名称关键词（如：茅台、AAPL、0700）",
            key=f"univ_kw_{market_key}",
        )
    with col_sort:
        sort_mode = st.selectbox(
            "排序", ["默认顺序", "按代码 A→Z", "按名称"],
            key=f"univ_sort_{market_key}",
        )
    with col_ps:
        page_size = st.selectbox(
            "每页显示", [50, 100, 200],
            key=f"univ_ps_{market_key}",
        )

    # 过滤
    kw_u = kw.strip().upper()
    filtered = (
        [(t, n) for t, n in raw_list if kw_u in t.upper() or kw_u in n.upper()]
        if kw_u else raw_list
    )

    # 排序
    if sort_mode == "按代码 A→Z":
        filtered = sorted(filtered, key=lambda x: x[0])
    elif sort_mode == "按名称":
        filtered = sorted(filtered, key=lambda x: x[1])

    total_f = len(filtered)
    n_pages = max(1, (total_f + page_size - 1) // page_size)

    page_idx = st.number_input(
        f"页码（共 {n_pages} 页，{total_f:,} 条）",
        min_value=1, max_value=n_pages, value=1,
        key=f"univ_page_{market_key}",
    ) - 1

    page_items = filtered[page_idx * page_size: (page_idx + 1) * page_size]

    # ── 批量选择状态 ─────────────────────────────────────────────
    sel_key = f"univ_sel_{market_key}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = set()
    selected: set = st.session_state[sel_key]

    # 全选/清除
    col_selall, col_clr, col_warn, col_cnt = st.columns([2, 2, 4, 2])
    with col_selall:
        if st.button(f"☑️ 全选当页({len(page_items)}支)", key=f"univ_selall_{market_key}"):
            for t, _ in page_items:
                selected.add(t)
            st.session_state[sel_key] = selected
            st.rerun()
    with col_clr:
        if st.button("✖ 清除全部选择", key=f"univ_clr_{market_key}"):
            st.session_state[sel_key] = set()
            st.rerun()
    with col_warn:
        if len(selected) > 50:
            st.markdown(
                f'<span style="color:#dc2626;font-size:12px">'
                f'⚠️ 已选 {len(selected)} 支，建议每批 ≤50 支以避免超时</span>',
                unsafe_allow_html=True,
            )
    with col_cnt:
        st.markdown(
            f'<div style="color:#6b7280;font-size:12px;padding-top:8px;text-align:right">'
            f'已选 <b>{len(selected)}</b> 支</div>',
            unsafe_allow_html=True,
        )

    # ── 自选收藏状态 ─────────────────────────────────────────────
    watchlist = storage.load_watchlist()
    wl_set    = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    # ── 表格：CSS ────────────────────────────────────────────────
    st.markdown("""
    <style>
    .ut2 {width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
    .ut2 th {padding:7px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb;
             white-space:nowrap;overflow:hidden}
    .ut2 td {padding:6px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle;
             overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    </style>
    """, unsafe_allow_html=True)

    # ── 构建表格行 ───────────────────────────────────────────────
    rows_html = []
    scan_singles  = []   # 单支扫描按钮
    fav_btns      = []   # 收藏按钮

    for i, (ticker, name) in enumerate(page_items):
        global_i = page_idx * page_size + i + 1
        is_fav   = ticker in wl_set
        is_sel   = ticker in selected

        # TV 链接
        if market_key == "a_share":
            exch   = "SH" if ticker[0] == "6" else ("BJ" if ticker[0] in ("4","8","9") else "SZ")
            tv_lnk = f"https://www.tradingview.com/chart/?symbol={exch}{ticker}"
        elif market_key == "hk_stock":
            num    = ticker.replace(".HK","").lstrip("0") or "0"
            tv_lnk = f"https://www.tradingview.com/chart/?symbol=HKEX:{num}"
        else:
            tv_lnk = f"https://www.tradingview.com/chart/?symbol={ticker}"

        sel_icon = "✅" if is_sel else "⬜"
        fav_icon = "★"  if is_fav else "☆"

        rows_html.append(
            f"<tr style='border-bottom:1px solid #f3f4f6'>"
            f"<td style='width:4%;color:#9ca3af;text-align:center'>{global_i}</td>"
            f"<td style='width:20%;font-family:monospace;font-weight:600'>{ticker}</td>"
            f"<td style='width:38%'>{name}</td>"
            f"<td style='width:9%;text-align:center'>{sel_icon}</td>"
            f"<td style='width:9%;text-align:center'>{fav_icon}</td>"
            f"<td style='width:10%;text-align:center'>"
            f"<a href='{tv_lnk}' target='_blank' style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
            f"</tr>"
        )
        scan_singles.append((ticker, name, i))
        fav_btns.append((ticker, name, is_fav, is_sel, i))

    # 整体输出表格（保证列对齐）
    st.markdown(
        f'<table class="ut2"><thead><tr>'
        f'<th style="text-align:center;width:4%">#</th>'
        f'<th style="text-align:left;width:20%">代码</th>'
        f'<th style="text-align:left;width:38%">名称</th>'
        f'<th style="text-align:center;width:9%">选择</th>'
        f'<th style="text-align:center;width:9%">收藏</th>'
        f'<th style="text-align:center;width:10%">图表</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table>',
        unsafe_allow_html=True,
    )

    # ── 操作按钮区（勾选 / 收藏 / 单支扫描）─────────────────────
    st.markdown(
        '<div style="font-size:11px;color:#9ca3af;margin:6px 0 4px">'
        '操作按钮（点击切换）：</div>',
        unsafe_allow_html=True,
    )

    # 每行最多 6 个按钮
    n_cols = min(6, len(fav_btns))
    if n_cols > 0:
        chunk_size = n_cols
        for chunk_start in range(0, len(fav_btns), chunk_size):
            chunk = fav_btns[chunk_start: chunk_start + chunk_size]
            btn_cols = st.columns(len(chunk))
            for j, (ticker, name, is_fav, is_sel, i) in enumerate(chunk):
                with btn_cols[j]:
                    # 勾选按钮
                    sel_label = f"✅ {ticker}" if is_sel else f"⬜ {ticker}"
                    if st.button(sel_label, key=f"univ_sel_{market_key}_{page_idx}_{i}",
                                 help=f"{'取消选择' if is_sel else '选择'} {name}"):
                        if is_sel:
                            selected.discard(ticker)
                        else:
                            selected.add(ticker)
                        st.session_state[sel_key] = selected
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # 收藏 + 单支扫描按钮
        for chunk_start in range(0, len(fav_btns), chunk_size):
            chunk = fav_btns[chunk_start: chunk_start + chunk_size]
            btn_cols = st.columns(len(chunk) * 2)
            for j, (ticker, name, is_fav, is_sel, i) in enumerate(chunk):
                with btn_cols[j * 2]:
                    fav_label = f"★ {ticker}" if is_fav else f"☆ {ticker}"
                    if st.button(fav_label, key=f"univ_fav_{market_key}_{page_idx}_{i}",
                                 help=f"{'取消收藏' if is_fav else '收藏'} {name}"):
                        if is_fav:
                            storage.remove_from_watchlist(ticker)
                            st.toast(f"已移除：{name}", icon="🗑️")
                        else:
                            storage.add_to_watchlist(ticker=ticker, name=name,
                                                     note=f"{label}品种库添加")
                            st.toast(f"已收藏：{name}", icon="⭐")
                        st.rerun()
                with btn_cols[j * 2 + 1]:
                    if st.button(f"🔍 {ticker}", key=f"univ_scan1_{market_key}_{page_idx}_{i}",
                                 help=f"单独扫描 {name}（约6秒）"):
                        _run_single(ticker, name, category, cfg)

    # ── 批量扫描 ─────────────────────────────────────────────────
    st.markdown("---")
    n_sel = len(selected)

    if n_sel > 0:
        est_sec = n_sel * 3 * 2
        est_min = est_sec // 60
        col_l, col_r = st.columns([7, 3])
        with col_l:
            if n_sel <= 50:
                st.info(
                    f"✅ 已选 **{n_sel}** 支 | 预计耗时约 **{est_sec}秒**（{est_min}分钟）"
                    f" | {n_sel*3} 次 Fibonacci 检查"
                )
            else:
                st.warning(
                    f"⚠️ 已选 **{n_sel}** 支 | 预计耗时 **{est_min}分钟** ｜"
                    f" 建议分批，每批 ≤50 支"
                )
        with col_r:
            if st.button(
                f"🚀 批量扫描 {n_sel} 支",
                type="primary",
                key=f"univ_batch_{market_key}",
            ):
                assets_batch = {t: (name_map.get(t, t), category) for t in selected}
                _run_batch(assets_batch, cfg)
    else:
        st.caption("☑️ 请先勾选品种，再点击批量扫描")


# ════════════════════════════════════════════════════════════════════
# 单支扫描
# ════════════════════════════════════════════════════════════════════
def _run_single(ticker: str, name: str, category: str, cfg: dict):
    pb  = st.progress(0, "准备中…")
    msg = st.empty()

    def cb(pct, text):
        pb.progress(min(float(pct), 1.0), text)
        msg.caption(text)

    summary, err = sc.run_full_scan(
        cfg=cfg,
        assets={ticker: (name, category)},
        note=f"universe_single:{ticker}",
        progress_callback=cb,
    )
    pb.empty(); msg.empty()

    if err:
        st.error(f"扫描失败：{err}")
    else:
        inzone  = summary.get("inzone_count", 0)
        elapsed = summary.get("elapsed_ms", 0) / 1000
        if inzone > 0:
            st.success(f"✅ **{name}** ({ticker}) 黄金区命中 **{inzone}** 框架 | {elapsed:.1f}s")
        else:
            st.info(f"✅ **{name}** ({ticker}) 扫描完成，当前区间外 | {elapsed:.1f}s")
    st.rerun()


# ════════════════════════════════════════════════════════════════════
# 批量扫描（带进度条）
# ════════════════════════════════════════════════════════════════════
def _run_batch(assets: dict, cfg: dict):
    if not assets:
        return

    n    = len(assets)
    pb   = st.progress(0, f"准备扫描 {n} 支品种…")
    msg  = st.empty()

    def cb(pct, text):
        pb.progress(min(float(pct), 1.0), text)
        msg.caption(text)

    summary, err = sc.run_full_scan(
        cfg=cfg,
        assets=assets,
        note=f"universe_batch:{n}支",
        progress_callback=cb,
    )
    pb.empty(); msg.empty()

    if err:
        st.error(f"批量扫描失败：{err}")
    else:
        st.success(
            f"✅ 批量扫描完成！"
            f"品种 **{summary['asset_count']}** | "
            f"黄金区命中 **{summary['inzone_count']}** | "
            f"三框架共振 **{summary['triple_conf']}** | "
            f"耗时 **{summary['elapsed_ms']/1000:.1f}s**"
        )
        st.info("💡 本次结果已保存，可继续勾选其他品种追加扫描，结果会自动累积显示。")
    st.rerun()
