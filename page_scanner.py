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
    latest_map = {}
    for sess in reversed(sessions):
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
def _render_results_table(df: pd.DataFrame, last_s: dict, safe_float):
    watchlist        = storage.load_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    # 表头
    st.markdown("""
    <style>
    .res-table {width:100%;border-collapse:collapse;font-size:13px}
    .res-table th {padding:7px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb;white-space:nowrap}
    .res-table td {padding:6px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle}
    </style>
    <table class="res-table">
    <thead><tr>
      <th style="text-align:left">资产</th>
      <th style="text-align:left">类别</th>
      <th style="text-align:left">框架</th>
      <th style="text-align:left">状态</th>
      <th style="text-align:right">当前价格</th>
      <th style="text-align:right">回撤%</th>
      <th style="text-align:right">距区间</th>
      <th style="text-align:left">共振</th>
      <th style="text-align:left">TV</th>
    </tr></thead>
    </table>
    """, unsafe_allow_html=True)

    seen_tickers: set = set()

    for idx, r in df.iterrows():
        in_zone  = bool(r.get("in_zone", False))
        dist     = safe_float(r.get("dist_pct"))
        price    = r.get("current_price")
        retrace  = r.get("retrace_pct")
        conf_l   = r.get("confluence_label", "—") or "—"
        tv_lnk   = r.get("tv_url", "#")
        cat      = r.get("category", "")
        ticker   = r.get("ticker", "")
        name     = r.get("name", "")

        price_s   = f"{float(price):,.4f}"    if price   is not None else "—"
        retrace_s = f"{float(retrace):.1f}%"  if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        is_first  = ticker not in seen_tickers
        seen_tickers.add(ticker)
        is_fav    = ticker in watchlist_tickers

        # 每行：[宽列(表格内容) | 窄列(收藏按钮)]
        col_row, col_btn = st.columns([11, 1])

        with col_row:
            st.markdown(
                f'<table class="res-table"><tbody><tr>'
                f'<td style="width:18%"><b>{name}</b><br>'
                f'<small style="color:#9ca3af;font-family:monospace">{ticker}</small></td>'
                f'<td style="width:8%"><span class="badge b-gray">{_cat_label(cat)}</span></td>'
                f'<td style="width:7%"><span class="badge b-gray">{r.get("timeframe","")}</span></td>'
                f'<td style="width:9%">{_badge(in_zone, dist)}</td>'
                f'<td style="width:12%;font-family:monospace;text-align:right">{price_s}</td>'
                f'<td style="width:8%;text-align:right">{retrace_s}</td>'
                f'<td style="width:8%;text-align:right">{dist_s}</td>'
                f'<td style="width:12%">{_conf_badge(conf_l)}</td>'
                f'<td style="width:8%"><a href="{tv_lnk}" target="_blank" '
                f'style="color:#e85d04;font-size:12px">📈 TV</a></td>'
                f'</tr></tbody></table>',
                unsafe_allow_html=True,
            )

        with col_btn:
            if is_first:
                if is_fav:
                    if st.button("★", key=f"unfav_{ticker}_{idx}",
                                 help=f"从自选移除：{name}", type="secondary"):
                        storage.remove_from_watchlist(ticker)
                        st.toast(f"已移除：{name}", icon="🗑️")
                        st.rerun()
                else:
                    if st.button("☆", key=f"fav_{ticker}_{idx}",
                                 help=f"添加到自选：{name}", type="secondary"):
                        storage.add_to_watchlist(ticker=ticker, name=name)
                        st.toast(f"已收藏：{name}", icon="⭐")
                        st.rerun()

    st.caption(f"共 {len(df)} 条  ｜  ☆ 点击收藏 / ★ 点击取消收藏")
    csv = df.drop(columns=[c for c in ["_r","_d"] if c in df.columns],
                  errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 下载 CSV", csv,
                       file_name=f"strx_fibo_{last_s.get('scan_date','today')}.csv",
                       mime="text/csv")


# ════════════════════════════════════════════════════════════════════
# Ticker 自动修正建议
# ════════════════════════════════════════════════════════════════════

# 常见格式错误规则：(pattern, 修正函数, 说明)
_CORRECTION_RULES = [
    # A 股：6位数字 → 加 .SS 或 .SZ
    (r"^(\d{6})$",         lambda m: [f"{m.group(1)}.SS", f"{m.group(1)}.SZ"],
     "A股代码需加交易所后缀（上交所 .SS / 深交所 .SZ）"),
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
                        st.session_state["custom_ticker_confirmed"] = sug["ticker"]
                        st.session_state["custom_name_confirmed"]   = sug.get("name", "")
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # 使用确认的 ticker（若用户点击了建议）
    if st.session_state.get("custom_ticker_confirmed"):
        confirmed_ticker = st.session_state["custom_ticker_confirmed"]
        if not custom_name and st.session_state.get("custom_name_confirmed"):
            custom_name = st.session_state["custom_name_confirmed"]
        st.info(f"ℹ️ 将使用修正后的代码：**{confirmed_ticker}**　"
                f"[点此取消](# '取消修正')")

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
