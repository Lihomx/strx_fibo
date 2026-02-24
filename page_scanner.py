"""
page_scanner.py — 实时扫描（支持 20 组分批扫描 + 自定义品种 + 结果收藏）
"""
import pandas as pd
import streamlit as st

import storage
import scanner as sc
from assets import ASSET_GROUPS, ASSETS, TIMEFRAMES, CATEGORY_LABELS, tv_url


# ════════════════════════════════════════════════════════════════════
# 徽章辅助
# ════════════════════════════════════════════════════════════════════
def _badge(in_zone: bool, dist) -> str:
    try:    dist = float(dist) if dist is not None else 999.0
    except: dist = 999.0
    if in_zone:  return '<span class="badge b-green">✅ 黄金区</span>'
    if dist < 5: return '<span class="badge b-yellow">👀 接近</span>'
    return '<span class="badge b-gray">—</span>'

def _conf_badge(label: str) -> str:
    label = label or "—"
    if "三" in label: return f'<span class="badge b-red">{label}</span>'
    if "双" in label: return f'<span class="badge b-orange">{label}</span>'
    if "单" in label or "接近" in label: return f'<span class="badge b-yellow">{label}</span>'
    return f'<span class="badge b-gray">{label}</span>'

def _cat_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, cat)


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## 📊 Fibonacci 实时扫描")
    cfg = storage.load_config()

    # ── 分批扫描控制区 ──────────────────────────────────────────────
    with st.expander("📦 选择扫描批次（点击展开/收起）", expanded=True):
        _render_batch_selector(cfg)

    # ── 自定义品种扫描区 ────────────────────────────────────────────
    with st.expander("🔎 自定义品种扫描（输入单个品种代码）", expanded=False):
        _render_custom_scan(cfg)

    # ── 工具栏 ──────────────────────────────────────────────────────
    col_kw, col_tf, col_cat, col_zone, col_sort = st.columns([3, 2, 2, 2, 2])
    with col_kw:
        kw = st.text_input("🔍 搜索", placeholder="名称 / 代码…",
                           label_visibility="collapsed")
    with col_tf:
        tf_sel = st.selectbox("框架", ["全部","Daily","Weekly","Monthly"],
                              label_visibility="collapsed")
    with col_cat:
        all_cat_keys = ["全部"] + sorted(set(CATEGORY_LABELS.keys()))
        cat_sel = st.selectbox("类别", all_cat_keys, label_visibility="collapsed",
                               format_func=lambda x: _cat_label(x) if x != "全部" else "全部类别")
    with col_zone:
        zone_only = st.checkbox("仅黄金区", value=False)
    with col_sort:
        sort_by = st.selectbox("排序", ["共振评分↓","回撤%↑","距离%↑","名称"],
                               label_visibility="collapsed")

    # ── 数据展示区 ───────────────────────────────────────────────────
    if not storage.has_scan_data():
        st.markdown('<div class="n-info">💡 尚无数据，请选择品种组后点击「🚀 扫描选中组」，或在上方「自定义品种扫描」中输入品种代码。</div>',
                    unsafe_allow_html=True)
        _metrics(0, 0, 0, 0)
        return

    rows     = storage.load_latest_results(inzone_only=False)
    sessions = storage.load_sessions(limit=5)
    last_s   = sessions[0] if sessions else {}

    # 合并多次扫描的最新数据（同一 ticker+timeframe 取最新）
    # sessions 已按时间倒序，第一次遇到即为最新
    latest_map = {}
    for sess in sessions:   # sessions[0] = 最新，直接正序遍历覆盖即可
        sess_rows = storage.load_session_results(sess["session_id"])
        for r in sess_rows:
            key = (r["ticker"], r["timeframe"])
            if key not in latest_map:
                latest_map[key] = r
    merged_rows = list(latest_map.values()) if latest_map else rows

    total  = len(set(r["ticker"] for r in merged_rows))
    inzone = sum(1 for r in merged_rows if r.get("in_zone"))
    near   = sum(1 for r in merged_rows
                 if not r.get("in_zone") and (r.get("dist_pct") or 999) < 5)
    triple = sum(
        1 for t in set(r["ticker"] for r in merged_rows)
        if sum(1 for r in merged_rows
               if r["ticker"] == t and r.get("in_zone")) == 3
    )
    _metrics(total, inzone, near, triple)

    scanned_groups = storage.load_scanned_groups()
    if scanned_groups:
        st.caption(f"📦 已扫描组：{'、'.join(scanned_groups[-8:])}  "
                   f"| 品种：{total}  | 更新：{last_s.get('scan_time','—')}")

    # ── 过滤 ─────────────────────────────────────────────────────────
    df = pd.DataFrame(merged_rows)
    if zone_only:           df = df[df["in_zone"]]
    if tf_sel != "全部":    df = df[df["timeframe"] == tf_sel]
    if cat_sel != "全部":   df = df[df["category"]  == cat_sel]
    if kw:
        mask = (df["name"].str.contains(kw, case=False, na=False) |
                df["ticker"].str.contains(kw, case=False, na=False))
        df = df[mask]

    # 排序
    def safe_float(v, default=999.0):
        try: return float(v) if v is not None else default
        except: return default

    if sort_by == "共振评分↓":
        df = df.sort_values("confluence_score", ascending=False)
    elif sort_by == "回撤%↑":
        df["_r"] = df["retrace_pct"].apply(lambda x: safe_float(x, 999))
        df = df.sort_values("_r")
    elif sort_by == "距离%↑":
        df["_d"] = df["dist_pct"].apply(lambda x: safe_float(x, 999))
        df = df.sort_values("_d")
    else:
        df = df.sort_values("name")

    if df.empty:
        st.info("没有符合条件的结果"); return

    _render_results_table(df, last_s, safe_float)


# ════════════════════════════════════════════════════════════════════
# 结果表（含逐行收藏按钮）
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — st.columns 逐行渲染，收藏按钮与数据天然同行同高，彻底解决错位
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — HTML 表格 + 内嵌可点击收藏按钮（彻底同行对齐）
# 方案：主内容用 HTML 表格渲染（完美对齐）
#       收藏列用 st.columns 逐行对应，通过 CSS margin-top 精确校准
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — 完全 HTML 表格方案，收藏通过 query_params 触发，永远同行对齐
# ════════════════════════════════════════════════════════════════════
def _render_results_table(df: pd.DataFrame, last_s: dict, safe_float):

    # ── 处理 query_params 收藏指令（页面渲染前执行）────────────
    try:
        fav_act = st.query_params.get("_fav", "")
        if fav_act:
            parts = fav_act.split("|", 2)   # "add|TICKER|NAME" 或 "del|TICKER|NAME"
            if len(parts) == 3:
                act, tk, nm = parts
                if act == "add":
                    storage.add_to_watchlist(ticker=tk, name=nm)
                    st.toast(f"已收藏：{nm}", icon="⭐")
                elif act == "del":
                    storage.remove_from_watchlist(tk)
                    st.toast(f"已移除：{nm}", icon="🗑️")
            # 清除 query param，避免刷新重复执行
            st.query_params.pop("_fav", None)
            st.rerun()
    except Exception:
        pass

    # 兼容旧的 session_state 方式
    _pending = st.session_state.pop("_fav_action", None)
    if _pending:
        act, tk, nm = _pending
        if act == "add":
            storage.add_to_watchlist(ticker=tk, name=nm)
            st.toast(f"已收藏：{nm}", icon="⭐")
        else:
            storage.remove_from_watchlist(tk)
            st.toast(f"已移除：{nm}", icon="🗑️")
        st.rerun()

    watchlist         = storage.load_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    # ── CSS ──────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .rt3{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
    .rt3 th{padding:9px 6px;background:#f9fafb;border-bottom:2px solid #e5e7eb;
            font-size:12px;color:#374151;font-weight:600;white-space:nowrap}
    .rt3 td{padding:9px 6px;border-bottom:1px solid #f3f4f6;vertical-align:middle;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .rt3 tr.zone td{background:#fffbeb}
    .rt3 tr:hover td{background:#f8fafc}
    .rt3 tr.zone:hover td{background:#fef3c7}
    .fav-btn{font-size:20px;cursor:pointer;text-decoration:none;line-height:1;
             display:block;text-align:center;padding:2px 0;transition:transform .1s}
    .fav-btn:hover{transform:scale(1.3)}
    .fav-star{color:#f59e0b}
    .fav-empty{color:#d1d5db}
    </style>
    """, unsafe_allow_html=True)

    seen: set = set()
    rows_html = []

    for _, r in df.iterrows():
        in_zone   = bool(r.get("in_zone", False))
        dist      = safe_float(r.get("dist_pct"))
        price     = r.get("current_price")
        retrace   = r.get("retrace_pct")
        conf_l    = r.get("confluence_label", "—") or "—"
        tv_lnk    = r.get("tv_url", "#")
        cat       = r.get("category", "")
        ticker    = r.get("ticker", "")
        name      = r.get("name", "")
        tf        = r.get("timeframe", "")

        price_s   = f"{float(price):,.4f}"   if price   is not None else "—"
        retrace_s = f"{float(retrace):.1f}%" if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        is_first = ticker not in seen
        seen.add(ticker)
        is_fav   = ticker in watchlist_tickers

        # 收藏列：用 <a href> 触发 query_params，完全在 HTML 表格内，永远对齐
        if is_first:
            if is_fav:
                fav_param = f"del|{ticker}|{name}"
                fav_html  = (
                    f'<a href="?_t={st.query_params.get("_t","")}&_fav={fav_param}" '
                    f'class="fav-btn fav-star" title="取消收藏 {name}">★</a>'
                )
            else:
                fav_param = f"add|{ticker}|{name}"
                fav_html  = (
                    f'<a href="?_t={st.query_params.get("_t","")}&_fav={fav_param}" '
                    f'class="fav-btn fav-empty" title="收藏 {name}">☆</a>'
                )
        else:
            fav_html = ""

        zone_cls = ' class="zone"' if in_zone else ""
        rows_html.append(
            f"<tr{zone_cls}>"
            f"<td style='width:20%'><b>{name}</b>"
            f"<br><small style='color:#9ca3af;font-family:monospace'>{ticker}</small></td>"
            f"<td style='width:8%'><span class='badge b-gray'>{_cat_label(cat)}</span></td>"
            f"<td style='width:7%'><span class='badge b-gray'>{tf}</span></td>"
            f"<td style='width:9%'>{_badge(in_zone, dist)}</td>"
            f"<td style='width:12%;font-family:monospace;font-size:12px;text-align:right'>{price_s}</td>"
            f"<td style='width:8%;text-align:right'>{retrace_s}</td>"
            f"<td style='width:8%;text-align:right'>{dist_s}</td>"
            f"<td style='width:13%'>{_conf_badge(conf_l)}</td>"
            f"<td style='width:7%'><a href='{tv_lnk}' target='_blank' "
            f"style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
            f"<td style='width:5%;text-align:center'>{fav_html}</td>"
            f"</tr>"
        )

    thead = (
        "<tr>"
        "<th style='width:20%'>资产</th>"
        "<th style='width:8%'>类别</th>"
        "<th style='width:7%'>框架</th>"
        "<th style='width:9%'>状态</th>"
        "<th style='width:12%;text-align:right'>当前价格</th>"
        "<th style='width:8%;text-align:right'>回撤%</th>"
        "<th style='width:8%;text-align:right'>距区间</th>"
        "<th style='width:13%'>共振</th>"
        "<th style='width:7%'>TV</th>"
        "<th style='width:5%;text-align:center'>收藏</th>"
        "</tr>"
    )
    st.markdown(
        f"<table class='rt3'><thead>{thead}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="color:#9ca3af;font-size:11px;margin-top:6px">'
        f'共 {len(df)} 条 &nbsp;｜&nbsp; 点击 ☆/★ 收藏/取消收藏</div>',
        unsafe_allow_html=True,
    )

    csv = df.drop(columns=[c for c in ["_r", "_d"] if c in df.columns],
                  errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ 下载 CSV", csv,
        file_name=f"strx_fibo_{last_s.get('scan_date', 'today')}.csv",
        mime="text/csv",
    )

# ════════════════════════════════════════════════════════════════════

# 常见格式错误规则：(pattern, 修正函数, 说明)
_CORRECTION_RULES = [
    # A 股：6位数字 → 根据首位数字自动判断交易所
    # 6开头 = 上交所(SS)，0/3开头 = 深交所(SZ)，4/8/9开头 = 北交所(BJ)
    (r"^(\d{6})$",
     lambda m: (
         [f"{m.group(1)}.SS"] if m.group(1)[0] == "6"
         else [f"{m.group(1)}.SZ"] if m.group(1)[0] in ("0","3")
         else [f"{m.group(1)}.BJ"]
     ),
     "A股代码自动识别交易所（6开头→上交所.SS / 0/3开头→深交所.SZ / 4/8/9开头→北交所.BJ）"),
    # 港股：去掉 .HK 前导零不够4位
    (r"^(\d{1,3})\.HK$",   lambda m: [f"{int(m.group(1)):04d}.HK"],
     "港股代码需补全为4位数字（如 700.HK → 0700.HK）"),
    # 港股：纯数字 1-4 位没有 .HK 后缀
    (r"^(\d{1,4})$",       lambda m: [f"{int(m.group(1)):04d}.HK"],
     "纯数字可能是港股，建议加 .HK 后缀"),
    # 外汇：EURUSD 没有 =X
    (r"^([A-Z]{6})$",      lambda m: [f"{m.group(1)}=X"],
     "外汇品种代码通常需在末尾加 =X（如 EURUSD=X）"),
    # 加密：BTC/ETH 没有 -USD（需先于通用2-3字母规则）
    (r"^(BTC|ETH|BNB|SOL|ADA|XRP|DOGE|AVAX|DOT|LINK)$",
     lambda m: [f"{m.group(1)}-USD"],
     "加密货币代码通常需加 -USD（如 BTC-USD）"),
    # 期货：GC / CL / SI 没有 =F
    (r"^([A-Z]{2,3})$",    lambda m: [f"{m.group(1)}=F"],
     "期货品种代码通常需在末尾加 =F（如 GC=F / CL=F）"),
]

# 常见品种名称/别名 → yfinance ticker 映射
_NAME_ALIAS: dict[str, tuple[str, str]] = {
    "黄金": ("GC=F", "黄金期货"),
    "GOLD": ("GC=F", "黄金期货"),
    "白银": ("SI=F", "白银期货"),
    "SILVER": ("SI=F", "白银期货"),
    "原油": ("CL=F", "原油期货"),
    "OIL": ("CL=F", "原油期货"),
    "比特币": ("BTC-USD", "比特币"),
    "BITCOIN": ("BTC-USD", "比特币"),
    "以太坊": ("ETH-USD", "以太坊"),
    "ETHEREUM": ("ETH-USD", "以太坊"),
    "纳斯达克": ("^IXIC", "纳斯达克综合"),
    "NASDAQ": ("^IXIC", "纳斯达克综合"),
    "标普": ("^GSPC", "标普500"),
    "SP500": ("^GSPC", "标普500"),
    "S&P": ("^GSPC", "标普500"),
    "道琼斯": ("^DJI", "道琼斯"),
    "DJI": ("^DJI", "道琼斯"),
    "上证": ("000001.SS", "上证指数"),
    "沪深300": ("000300.SS", "沪深300"),
    "恒生": ("^HSI", "恒生指数"),
    "HSI": ("^HSI", "恒生指数"),
    "欧元美元": ("EURUSD=X", "欧元/美元"),
    "EURUSD": ("EURUSD=X", "欧元/美元"),
    "美元日元": ("USDJPY=X", "美元/日元"),
    "USDJPY": ("USDJPY=X", "美元/日元"),
    "VIX": ("^VIX", "VIX恐慌指数"),
    "苹果": ("AAPL", "苹果"),
    "特斯拉": ("TSLA", "特斯拉"),
    "英伟达": ("NVDA", "英伟达"),
    "NVIDIA": ("NVDA", "英伟达"),
    "腾讯": ("0700.HK", "腾讯控股"),
    "茅台": ("600519.SS", "贵州茅台"),
}


import re

def _suggest_corrections(raw: str) -> list[dict]:
    """返回修正建议列表，每项 {ticker, reason}"""
    raw = raw.strip().upper()
    suggestions = []

    # 1. 名称/别名匹配
    alias_match = _NAME_ALIAS.get(raw) or _NAME_ALIAS.get(raw.upper())
    if alias_match:
        suggestions.append({
            "ticker": alias_match[0],
            "name":   alias_match[1],
            "reason": f"识别为「{alias_match[1]}」的常用名称",
        })

    # 2. 格式规则匹配
    for pattern, fix_fn, reason in _CORRECTION_RULES:
        m = re.match(pattern, raw)
        if m:
            try:
                candidates = fix_fn(m)
                for c in candidates:
                    if c != raw and not any(s["ticker"] == c for s in suggestions):
                        suggestions.append({"ticker": c, "name": "", "reason": reason})
            except Exception:
                pass

    # 3. 从品种库中模糊匹配
    try:
        from assets import ASSETS
        kw = raw.lower()
        for tk, (nm, _cat) in ASSETS.items():
            if (kw in tk.lower() or kw in nm.lower()) and tk != raw:
                if not any(s["ticker"] == tk for s in suggestions):
                    suggestions.append({
                        "ticker": tk,
                        "name":   nm,
                        "reason": f"品种库中找到相似品种：{nm}",
                    })
                if len(suggestions) >= 5:
                    break
    except Exception:
        pass

    return suggestions[:5]


def _try_fetch_ticker(ticker: str) -> bool:
    """尝试用 yfinance 获取该 ticker 最近1条数据，判断是否有效。"""
    try:
        import yfinance as yf
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(ticker, period="5d", interval="1d",
                             progress=False, auto_adjust=True)
        return df is not None and not df.empty
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# 自定义品种扫描
# ════════════════════════════════════════════════════════════════════
def _render_custom_scan(cfg):
    st.markdown("""
    <div class="n-info">
    💡 输入任意 <b>yfinance 品种代码</b>进行单独扫描。<br>
    示例：<code>AAPL</code>（苹果）、<code>BTC-USD</code>（比特币）、
    <code>000001.SS</code>（上证指数）、<code>0700.HK</code>（腾讯）、
    <code>EURUSD=X</code>（欧元/美元）、<code>GC=F</code>（黄金期货）
    </div>
    """, unsafe_allow_html=True)

    col_ticker, col_name, col_btn = st.columns([3, 3, 2])

    with col_ticker:
        # 若用户刚点了建议代码，将其预填入输入框
        if "custom_ticker_prefill" in st.session_state:
            st.session_state["custom_ticker_input"] = st.session_state.pop("custom_ticker_prefill")
        raw_input = st.text_input(
            "品种代码",
            placeholder="如：TSLA / 600519.SS / GC=F / 腾讯",
            key="custom_ticker_input",
        ).strip()
        custom_ticker = raw_input.upper()

    with col_name:
        custom_name = st.text_input(
            "自定义名称（可选）",
            placeholder="如：特斯拉 / 贵州茅台 / 黄金",
            key="custom_name_input",
        ).strip()

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        do_custom = st.button("🔍 立即扫描", type="primary",
                              width="stretch", key="custom_scan_btn")

    # ── 实时修正提示（输入时即显示建议，无需点扫描）──────────────
    confirmed_ticker = custom_ticker  # 最终使用的 ticker

    if custom_ticker and not do_custom:
        suggestions = _suggest_corrections(custom_ticker)
        if suggestions:
            st.markdown(
                '<div style="background:#fffbeb;border:1px solid #fde68a;'
                'border-radius:8px;padding:10px 14px;margin:6px 0;">'
                '<b style="color:#92400e">💡 格式建议</b>',
                unsafe_allow_html=True,
            )
            for i, sug in enumerate(suggestions):
                c1, c2 = st.columns([5, 2])
                with c1:
                    name_part = f" — {sug['name']}" if sug.get("name") else ""
                    st.markdown(
                        f'<span style="font-family:monospace;font-weight:600;color:#1d4ed8">'
                        f'{sug["ticker"]}</span>{name_part}'
                        f'<br><span style="color:#6b7280;font-size:11px">{sug["reason"]}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(f"使用 {sug['ticker']}", key=f"use_sug_{i}_{sug['ticker']}"):
                        # 将选定代码写入 prefill，下次 rerun 时自动填入输入框
                        st.session_state["custom_ticker_prefill"]  = sug["ticker"]
                        st.session_state["custom_name_confirmed"]  = sug.get("name", "")
                        # 清除之前的确认状态
                        st.session_state.pop("custom_ticker_confirmed", None)
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # 检查是否有已确认的修正代码（来自扫描失败后点击建议）
    confirmed_ticker = custom_ticker
    if st.session_state.get("custom_ticker_confirmed"):
        confirmed_ticker = st.session_state["custom_ticker_confirmed"]
        if not custom_name and st.session_state.get("custom_name_confirmed"):
            custom_name = st.session_state["custom_name_confirmed"]
        col_info, col_cancel = st.columns([6, 2])
        with col_info:
            st.info(f"ℹ️ 将使用修正后的代码：**{confirmed_ticker}**")
        with col_cancel:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✖ 取消修正", key="cancel_correction"):
                st.session_state.pop("custom_ticker_confirmed", None)
                st.session_state.pop("custom_name_confirmed", None)
                st.rerun()

    if not do_custom:
        return

    # ── 执行扫描 ────────────────────────────────────────────────
    final_ticker = confirmed_ticker or custom_ticker
    if not final_ticker:
        st.warning("请输入品种代码"); return

    display_name  = custom_name or final_ticker

    # 先验证 ticker 是否可以取到数据
    with st.spinner(f"🔍 验证品种代码 {final_ticker}…"):
        valid = _try_fetch_ticker(final_ticker)

    if not valid:
        suggestions = _suggest_corrections(final_ticker)
        st.error(
            f"❌ 无法获取 **{final_ticker}** 的数据（可能是代码格式错误或已退市）"
        )
        if suggestions:
            st.markdown("**💡 您是否想扫描以下品种？**")
            for i, sug in enumerate(suggestions):
                c1, c2 = st.columns([6, 2])
                with c1:
                    name_part = f" — {sug['name']}" if sug.get("name") else ""
                    st.markdown(
                        f'**{sug["ticker"]}**{name_part}  '
                        f'<span style="color:#6b7280;font-size:12px">{sug["reason"]}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(f"扫描 {sug['ticker']}", key=f"err_sug_{i}_{sug['ticker']}",
                                 type="primary"):
                        st.session_state["custom_ticker_confirmed"] = sug["ticker"]
                        st.session_state["custom_name_confirmed"]   = sug.get("name", "")
                        st.rerun()
        return

    # 清除确认状态
    st.session_state.pop("custom_ticker_confirmed", None)
    st.session_state.pop("custom_name_confirmed", None)

    custom_assets = {final_ticker: (display_name, "custom")}
    pb  = st.progress(0, "准备中…")
    msg = st.empty()

    def cb(pct, text):
        pb.progress(min(float(pct), 1.0), text)
        msg.caption(text)

    with st.spinner(""):
        summary, err = sc.run_full_scan(
            cfg=cfg,
            assets=custom_assets,
            note=f"custom:{final_ticker}",
            progress_callback=cb,
        )

    pb.empty(); msg.empty()

    if err:
        st.error(f"扫描失败：{err}"); return

    inzone  = summary.get("inzone_count", 0)
    elapsed = summary.get("elapsed_ms", 0) / 1000

    if inzone > 0:
        st.success(
            f"✅ **{display_name}** ({final_ticker}) 扫描完成！"
            f"黄金区命中 **{inzone}** 个框架 | 耗时 {elapsed:.1f}s"
        )
    else:
        st.info(
            f"✅ **{display_name}** ({final_ticker}) 扫描完成，"
            f"当前未在黄金区间。耗时 {elapsed:.1f}s"
        )

    # 一键加入自选
    watchlist  = storage.load_watchlist()
    wl_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}
    if final_ticker not in wl_tickers:
        _, col_add = st.columns([5, 2])
        with col_add:
            if st.button("⭐ 加入自选收藏", key="custom_add_watchlist"):
                storage.add_to_watchlist(
                    ticker=final_ticker, name=display_name, note="自定义扫描添加"
                )
                st.toast(f"已添加到自选：{display_name}", icon="⭐")
                st.rerun()
    else:
        st.caption(f"✅ {display_name} 已在您的自选收藏中")

    st.rerun()


# ════════════════════════════════════════════════════════════════════
# 分批扫描选择器
# ════════════════════════════════════════════════════════════════════
def _render_batch_selector(cfg):
    group_names  = list(ASSET_GROUPS.keys())
    total_assets = sum(len(g) for g in ASSET_GROUPS.values())
    n_groups     = len(group_names)

    st.markdown(f"""
    <div class="n-info">
    📦 品种库：共 <b>{total_assets}</b> 个品种，分 <b>{n_groups}</b> 组。
    每组约 13–30 个品种 × 3 框架，单批约 1–3 分钟。
    多次扫描结果自动缓存合并，无需一次全部完成。
    </div>
    """, unsafe_allow_html=True)

    r1c1,r1c2,r1c3,r1c4,r1c5 = st.columns(5)
    with r1c1:
        if st.button("☑️ 全选(40组)", width="stretch"):
            st.session_state.scan_groups = group_names[:]
    with r1c2:
        if st.button("🥇 期货+指数", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["期货","指数","全球","ETF"])]
    with r1c3:
        if st.button("🇺🇸 美股+ETF", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names if "美股" in g or "ETF" in g]
    with r1c4:
        if st.button("🇨🇳 中股全部", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["中概","港股","A股","中国"])]
    with r1c5:
        if st.button("💱 外汇+期货", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["外汇","期货"])]

    r2c1,r2c2,r2c3,r2c4,r2c5 = st.columns(5)
    with r2c1:
        if st.button("🌏 亚太全部", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["日本","韩国","台湾","印度","澳大利亚","东南亚"])]
    with r2c2:
        if st.button("🌍 欧洲全部", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["英国","德国","法国","北欧","欧洲"])]
    with r2c3:
        if st.button("🌎 新兴市场", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names
                if any(k in g for k in ["加拿大","拉美","新兴","非洲","中东"])]
    with r2c4:
        if st.button("₿ 加密全部", width="stretch"):
            st.session_state.scan_groups = [g for g in group_names if "加密" in g]
    with r2c5:
        if st.button("🔲 清空", width="stretch"):
            st.session_state.scan_groups = []

    raw_default = st.session_state.get("scan_groups", [group_names[0]])
    if not isinstance(raw_default, list):
        raw_default = [group_names[0]]
    default_sel = [g for g in raw_default if g in group_names]
    if not default_sel:
        default_sel = [group_names[0]]

    selected = st.multiselect(
        "选择要扫描的品种组（可多选）：",
        options=group_names,
        default=default_sel,
    )
    st.session_state.scan_groups = selected

    if not selected:
        st.warning("请至少选择一组品种"); return

    sel_assets = {}
    for g in selected:
        sel_assets.update(ASSET_GROUPS[g])
    checks = len(sel_assets) * 3

    scanned   = storage.load_scanned_groups()
    unscanned = [g for g in selected if g not in scanned]
    already   = [g for g in selected if g in scanned]

    col_info, col_btn = st.columns([4, 2])
    with col_info:
        st.markdown(
            f"**选中：** {len(selected)} 组 · **{len(sel_assets)}** 个品种 · "
            f"**{checks}** 次检查"
        )
        if already:
            st.caption(f"✅ 已缓存（可跳过）: {' · '.join(already[:4])}"
                       + (f" 等{len(already)}组" if len(already)>4 else ""))
        if unscanned:
            st.caption(f"🆕 未扫描: {' · '.join(unscanned[:4])}"
                       + (f" 等{len(unscanned)}组" if len(unscanned)>4 else ""))

    with col_btn:
        do_scan = st.button(f"🚀 扫描选中 {len(sel_assets)} 品种",
                            type="primary", width="stretch")

    if do_scan:
        pb  = st.progress(0, "准备中…")
        msg = st.empty()

        def cb(pct, text):
            pb.progress(min(float(pct), 1.0), text)
            msg.caption(text)

        group_label = "、".join(selected[:3]) + \
                      (f"等{len(selected)}组" if len(selected) > 3 else "")

        with st.spinner(""):
            summary, err = sc.run_full_scan(
                cfg=cfg,
                assets=sel_assets,
                note=f"batch:{group_label}",
                progress_callback=cb,
            )

        pb.empty(); msg.empty()
        if err:
            st.error(err)
        else:
            storage.save_scanned_groups(selected)
            st.success(
                f"✅ 完成！品种 **{summary['asset_count']}** | "
                f"黄金区 **{summary['inzone_count']}** | "
                f"三框架共振 **{summary['triple_conf']}** | "
                f"耗时 {summary['elapsed_ms']/1000:.1f}s"
            )
            st.rerun()


# ════════════════════════════════════════════════════════════════════
# 指标卡
# ════════════════════════════════════════════════════════════════════
def _metrics(total, inzone, near, triple):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="m-card"><div class="m-lbl">监控品种</div>'
                    f'<div class="m-val">{total}</div>'
                    f'<div class="m-sub">×3 框架</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="m-card teal"><div class="m-lbl">黄金区间</div>'
                    f'<div class="m-val" style="color:#059669">{inzone}</div>'
                    f'<div class="m-sub">0.500–0.618</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="m-card gold"><div class="m-lbl">接近区间</div>'
                    f'<div class="m-val" style="color:#d97706">{near}</div>'
                    f'<div class="m-sub">距离&lt;5%</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="m-card red"><div class="m-lbl">三框架共振</div>'
                    f'<div class="m-val" style="color:#dc2626">{triple}</div>'
                    f'<div class="m-sub">最强信号</div></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
