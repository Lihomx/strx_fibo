"""
page_universe.py — 🌍 全量品种库
通过 AKShare 实时获取全市场品种列表，无需 API Key。

覆盖：
  A股  ~5454 支（上交所 + 深交所 + 北交所）
  港股  ~2516 支（港交所主板）
  美股  ~16527 支（NASDAQ + NYSE + AMEX）
"""

import streamlit as st
import pandas as pd

import storage
import scanner as sc


# ════════════════════════════════════════════════════════════════════
# 带 30 分钟缓存的列表加载（避免每次切换都重新拉取）
# ════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _load_a():
    return sc.get_all_a_share_tickers()   # [(6位code, 名称)]

@st.cache_data(ttl=1800, show_spinner=False)
def _load_hk():
    return sc.get_all_hk_tickers()        # [(XXXX.HK, 名称)]

@st.cache_data(ttl=1800, show_spinner=False)
def _load_us():
    return sc.get_all_us_tickers()        # [(TICKER, 名称)]


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## 🌍 全量品种库")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '数据来自 <b>AKShare（东方财富）</b>，免费实时，无需 API Key。'
        '支持搜索、收藏、单支扫描、批量扫描。</p>',
        unsafe_allow_html=True,
    )

    # ── 数据源说明卡片 ───────────────────────────────────────────
    st.markdown("""
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;
                padding:12px 16px;margin-bottom:16px;font-size:13px">
    <b>📡 数据源架构</b>（自动路由，无需手动选择）<br><br>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
    <tr style="background:#e0f2fe">
      <th style="padding:5px 8px;text-align:left">品种类型</th>
      <th style="padding:5px 8px;text-align:left">主数据源</th>
      <th style="padding:5px 8px;text-align:left">备用数据源</th>
      <th style="padding:5px 8px;text-align:right">覆盖数量</th>
    </tr>
    <tr style="border-top:1px solid #bae6fd">
      <td style="padding:5px 8px">🇨🇳 A股</td>
      <td style="padding:5px 8px;color:#059669">AKShare（东方财富）✅ 免费</td>
      <td style="padding:5px 8px;color:#6b7280">yfinance（.SS/.SZ）</td>
      <td style="padding:5px 8px;text-align:right"><b>5,454</b> 支</td>
    </tr>
    <tr style="border-top:1px solid #bae6fd">
      <td style="padding:5px 8px">🇭🇰 港股</td>
      <td style="padding:5px 8px;color:#059669">AKShare（东方财富）✅ 免费</td>
      <td style="padding:5px 8px;color:#6b7280">yfinance（.HK）</td>
      <td style="padding:5px 8px;text-align:right"><b>2,516</b> 支</td>
    </tr>
    <tr style="border-top:1px solid #bae6fd">
      <td style="padding:5px 8px">🇺🇸 美股</td>
      <td style="padding:5px 8px;color:#059669">AKShare（东方财富）✅ 免费</td>
      <td style="padding:5px 8px;color:#6b7280">yfinance</td>
      <td style="padding:5px 8px;text-align:right"><b>16,527</b> 支</td>
    </tr>
    <tr style="border-top:1px solid #bae6fd">
      <td style="padding:5px 8px">🌐 外汇/期货/指数/加密</td>
      <td style="padding:5px 8px;color:#059669">yfinance ✅ 免费</td>
      <td style="padding:5px 8px;color:#6b7280">TwelveData（需 Key）</td>
      <td style="padding:5px 8px;text-align:right">全覆盖</td>
    </tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

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
def _render_market(market_key: str, load_fn, category: str,
                   cfg: dict, label: str):
    # ── 加载品种列表 ────────────────────────────────────────────
    with st.spinner(f"📡 从 AKShare 获取全量{label}品种列表…"):
        try:
            raw_list: list = load_fn()
        except Exception as e:
            st.error(
                f"❌ 加载失败：{e}\n\n"
                f"请确认 `akshare` 已安装（`requirements.txt` 中已包含）。\n"
                f"Streamlit Cloud 首次部署时会自动安装。"
            )
            return

    if not raw_list:
        st.warning("⚠️ 未获取到品种数据，请检查网络连接或稍后重试。")
        return

    total_raw = len(raw_list)
    st.success(f"✅ 已加载 **{total_raw:,}** 个{label}品种")

    # name_map 供后续批量扫描使用
    name_map: dict[str, str] = {t: n for t, n in raw_list}

    # ── 搜索 + 分页设置 ─────────────────────────────────────────
    col_kw, col_sort, col_ps = st.columns([4, 2, 2])
    with col_kw:
        kw = st.text_input(
            "🔍 搜索品种",
            placeholder="输入代码或名称关键词",
            key=f"univ_kw_{market_key}",
        )
    with col_sort:
        sort_mode = st.selectbox(
            "排序", ["默认顺序", "按代码 A→Z", "按名称 A→Z"],
            key=f"univ_sort_{market_key}",
        )
    with col_ps:
        page_size = st.selectbox(
            "每页显示", [50, 100, 200, 500],
            key=f"univ_ps_{market_key}",
        )

    # 过滤
    kw_u = kw.strip().upper()
    if kw_u:
        filtered = [(t, n) for t, n in raw_list
                    if kw_u in t.upper() or kw_u in n.upper()]
    else:
        filtered = raw_list

    # 排序
    if sort_mode == "按代码 A→Z":
        filtered = sorted(filtered, key=lambda x: x[0])
    elif sort_mode == "按名称 A→Z":
        filtered = sorted(filtered, key=lambda x: x[1])

    total_filtered = len(filtered)
    n_pages = max(1, (total_filtered + page_size - 1) // page_size)

    page_idx = st.number_input(
        f"页码（共 {n_pages} 页，共 {total_filtered:,} 条）",
        min_value=1, max_value=n_pages, value=1,
        key=f"univ_page_{market_key}",
    ) - 1

    page_items = filtered[page_idx * page_size: (page_idx + 1) * page_size]

    # ── 自选收藏状态 ─────────────────────────────────────────────
    watchlist    = storage.load_watchlist()
    wl_set: set  = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    # ── 批量选择状态 ─────────────────────────────────────────────
    sel_key = f"univ_sel_{market_key}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = set()
    selected: set = st.session_state[sel_key]

    # ── 全选当页 / 清除选择 ──────────────────────────────────────
    col_selall, col_clr, col_info = st.columns([2, 2, 6])
    with col_selall:
        if st.button("☑️ 全选当页", key=f"univ_selall_{market_key}"):
            for t, _ in page_items:
                selected.add(t)
            st.session_state[sel_key] = selected
            st.rerun()
    with col_clr:
        if st.button("✖ 清除选择", key=f"univ_clr_{market_key}"):
            st.session_state[sel_key] = set()
            st.rerun()
    with col_info:
        st.markdown(
            f'<div style="color:#6b7280;font-size:12px;padding-top:8px">'
            f'显示 {page_idx*page_size+1:,}–{min((page_idx+1)*page_size, total_filtered):,} 条'
            f'（已选 {len(selected)} 支）</div>',
            unsafe_allow_html=True,
        )

    # ── 表头 ─────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .ut {width:100%;border-collapse:collapse;font-size:13px}
    .ut th {padding:7px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb}
    .ut td {padding:6px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
    </style>
    <table class="ut"><thead><tr>
      <th style="text-align:left;width:5%">#</th>
      <th style="text-align:left;width:20%">代码</th>
      <th style="text-align:left;width:40%">名称</th>
      <th style="text-align:center;width:8%">选择</th>
      <th style="text-align:center;width:8%">收藏</th>
      <th style="text-align:center;width:8%">扫描</th>
      <th style="text-align:center;width:8%">TV</th>
    </tr></thead></table>
    """, unsafe_allow_html=True)

    # ── 逐行渲染 ─────────────────────────────────────────────────
    for i, (ticker, name) in enumerate(page_items):
        global_i = page_idx * page_size + i + 1
        is_fav   = ticker in wl_set
        is_sel   = ticker in selected

        # TV 链接（A股跳深交所/上交所，港股/美股跳 TradingView）
        if market_key == "a_share":
            prefix = "SZ" if ticker.startswith(("0", "3")) else "SH"
            tv_link = f"https://www.tradingview.com/chart/?symbol={prefix}{ticker}"
        elif market_key == "hk_stock":
            code_num = ticker.replace(".HK", "").lstrip("0") or "0"
            tv_link  = f"https://www.tradingview.com/chart/?symbol=HKEX:{code_num}"
        else:
            tv_link = f"https://www.tradingview.com/chart/?symbol=NASDAQ:{ticker}"

        col_info, col_sel, col_fav, col_scan, col_tv = st.columns([9, 1, 1, 1, 1])

        with col_info:
            st.markdown(
                f'<table class="ut"><tbody><tr>'
                f'<td style="width:5%;color:#9ca3af">{global_i:,}</td>'
                f'<td style="width:22%;font-family:monospace;font-weight:600">{ticker}</td>'
                f'<td style="width:40%">{name}</td>'
                f'</tr></tbody></table>',
                unsafe_allow_html=True,
            )

        with col_sel:
            new_checked = st.checkbox(
                "", value=is_sel,
                key=f"univ_chk_{market_key}_{i}_{ticker}",
                label_visibility="collapsed",
            )
            if new_checked and not is_sel:
                selected.add(ticker)
                st.session_state[sel_key] = selected
            elif not new_checked and is_sel:
                selected.discard(ticker)
                st.session_state[sel_key] = selected

        with col_fav:
            icon = "★" if is_fav else "☆"
            if st.button(icon, key=f"univ_fav_{market_key}_{i}_{ticker}",
                         help=f"{'移除' if is_fav else '收藏'} {name}"):
                if is_fav:
                    storage.remove_from_watchlist(ticker)
                    st.toast(f"已移除：{name}", icon="🗑️")
                else:
                    storage.add_to_watchlist(ticker=ticker, name=name,
                                             note=f"{label}全量库添加")
                    st.toast(f"已收藏：{name}", icon="⭐")
                st.rerun()

        with col_scan:
            if st.button("🔍", key=f"univ_scan_{market_key}_{i}_{ticker}",
                         help=f"扫描 {name}"):
                _run_single(ticker, name, category, cfg)

        with col_tv:
            st.link_button("📈", tv_link, help=f"TradingView {ticker}")

    # ── 批量扫描 ─────────────────────────────────────────────────
    st.markdown("---")
    n_sel = len(selected)
    col_l, col_r = st.columns([6, 2])
    with col_l:
        if n_sel:
            est = n_sel * 3 * 2   # 约每次请求 2 秒
            st.info(
                f"✅ 已选 **{n_sel}** 支品种 | "
                f"约需 {est} 秒 | "
                f"将进行 {n_sel * 3} 次 Fibonacci 检查"
            )
        else:
            st.caption("☑️ 勾选品种后可批量扫描，也可点击单支 🔍 立即扫描")
    with col_r:
        if st.button(
            f"🚀 批量扫描 {n_sel} 支",
            type="primary",
            disabled=(n_sel == 0),
            key=f"univ_batch_{market_key}",
        ):
            assets_batch = {t: (name_map.get(t, t), category) for t in selected}
            _run_batch(assets_batch, cfg)


# ════════════════════════════════════════════════════════════════════
# 单支扫描
# ════════════════════════════════════════════════════════════════════
def _run_single(ticker: str, name: str, category: str, cfg: dict):
    with st.container():
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
# 批量扫描
# ════════════════════════════════════════════════════════════════════
def _run_batch(assets: dict, cfg: dict):
    if not assets:
        return
    with st.spinner(f"🚀 正在扫描 {len(assets)} 支品种…"):
        pb  = st.progress(0, "初始化…")
        msg = st.empty()

        def cb(pct, text):
            pb.progress(min(float(pct), 1.0), text)
            msg.caption(text)

        summary, err = sc.run_full_scan(
            cfg=cfg,
            assets=assets,
            note=f"universe_batch:{len(assets)}支",
            progress_callback=cb,
        )
        pb.empty(); msg.empty()

    if err:
        st.error(f"批量扫描失败：{err}")
    else:
        st.success(
            f"✅ 完成！品种 **{summary['asset_count']}** | "
            f"黄金区命中 **{summary['inzone_count']}** | "
            f"三框架共振 **{summary['triple_conf']}** | "
            f"耗时 {summary['elapsed_ms']/1000:.1f}s"
        )
    st.rerun()
