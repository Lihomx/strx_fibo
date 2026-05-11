"""
page_scanner.py — 实时扫描（支持 20 组分批扫描 + 自定义品种 + 结果收藏）
"""
import pandas as pd
import streamlit as st
from pathlib import Path

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

    with st.expander("📂 从 Doc/symbol 批量扫描（支持仅月图）", expanded=False):
        _render_symbol_path_scan(cfg)

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

    # load_latest_results 已内置"同 ticker+timeframe 取最新"合并逻辑
    # 直接使用，比 session 循环更健壮（session_id 过滤不一定覆盖所有来源）
    merged_rows = storage.load_latest_results(inzone_only=False)
    sessions    = storage.load_sessions(limit=5)
    last_s      = sessions[0] if sessions else {}

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

    # data quality check
    _has_price_data = any(r.get("current_price") is not None for r in merged_rows)
    if not _has_price_data and merged_rows:
        _warn_lines = [
            "⚠️ **数据获取失败**：所有品种的价格数据均为空。",
            "",
            "**可能原因**：",
            "- 数据服务器暂时无法连接（AKShare / Yahoo Finance 超时）",
            "- A股代码格式有误，需带交易所后缀，如 600048.SS",
            "",
            "**解决方法**：",
            "1. 点击下方[清空扫描结果]清除旧缓存",
            "2. 等待 1-2 分钟后重新扫描",
            "3. 先用[自定义品种扫描]测试单个品种（如 AAPL 或 600519.SS）",
        ]
        st.warning("\n".join(_warn_lines))

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

    try:
        if sort_by == "共振评分↓":
            if "confluence_score" in df.columns:
                df = df.sort_values("confluence_score", ascending=False)
        elif sort_by == "回撤%↑":
            if "retrace_pct" in df.columns:
                df["_r"] = df["retrace_pct"].apply(lambda x: safe_float(x, 999))
                df = df.sort_values("_r")
        elif sort_by == "距离%↑":
            if "dist_pct" in df.columns:
                df["_d"] = df["dist_pct"].apply(lambda x: safe_float(x, 999))
                df = df.sort_values("_d")
        elif "name" in df.columns:
            df = df.sort_values("name")
    except Exception:
        pass

    if df.empty:
        st.info("没有符合条件的结果"); return

    # 确保必需列存在（兼容旧格式数据）
    for _col in ["in_zone","current_price","retrace_pct","dist_pct",
                 "confluence_score","confluence_label","timeframe","category",
                 "ticker","name"]:
        if _col not in df.columns:
            df[_col] = None

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
        from urllib.parse import unquote as _uq
        import re as _re
        fav_act = st.query_params.get("_fav", "")
        if fav_act:
            fav_act = _uq(fav_act)          # URL decode
            parts = fav_act.split("|", 2)   # "add|TICKER|NAME"
            if len(parts) == 3:
                act, tk, nm = parts
                # 安全校验：action 只允许 add/del，ticker 只允许字母数字符号
                if act in ("add", "del") and _re.match(r"^[\w.\-\^=]+$", tk):
                    if act == "add":
                        storage.add_to_watchlist(ticker=tk, name=nm[:60])
                        # 收藏成功：触发新标签页打开自选页并定位
                        _t_val = st.query_params.get("_t", "")
                        st.session_state["_open_wl_tab"] = (tk, nm[:40], _t_val)
                    else:
                        storage.remove_from_watchlist(tk)
                        st.toast(f"已移除：{nm[:40]}", icon="🗑️")
            st.query_params.pop("_fav", None)
            st.rerun()
    except Exception:
        pass

    # 新标签页打开自选页（收藏成功时）
    _open_wl = st.session_state.pop("_open_wl_tab", None)
    if _open_wl:
        if len(_open_wl) == 3:
            _highlight_tk, _display_nm, _t_val = _open_wl
        else:
            _highlight_tk, _t_val = _open_wl
            _display_nm = _highlight_tk
        _wl_url = f"/?_t={_t_val}&_page=watchlist&_anchor={_highlight_tk}"
        import streamlit.components.v1 as _stc_v1
        _stc_v1.html(
            f"""<script>
            try {{ window.open('{_wl_url}', '_blank'); }} catch(e) {{}}
            </script>""",
            height=0,
        )
        st.success(f"⭐ 已收藏「{_display_nm}」| 自选页已在新标签页打开，已自动定位到该品种")

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
    /* ── 全站移动端适配 ── */
    @media(max-width:768px){
      /* 卡片间距收紧 */
      .block-container{padding:0.5rem 0.5rem 2rem !important;}
      /* 指标卡手机竖排 */
      .m-card{padding:10px 8px !important;margin:4px 2px !important;}
      .m-val{font-size:24px !important;}
      .m-lbl{font-size:11px !important;}
      /* 表格滚动 */
      .rt3-wrap,.ut2-wrap,.cf3-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;}
      /* 减小字体 */
      .rt3,.ut2,.cf3{font-size:11px !important;}
      .rt3 th,.rt3 td,.ut2 th,.ut2 td{padding:5px 4px !important;}
      /* 按钮满宽 */
      .stButton>button{width:100% !important;font-size:12px !important;padding:6px 4px !important;}
      /* 收藏按钮 */
      .fav-btn{font-size:18px;}
      /* 标题缩小 */
      h2{font-size:1.2rem !important;}
      h3{font-size:1rem !important;}
      /* 隐藏次要列在极窄屏 */
    }
    @media(max-width:480px){
      .rt3{min-width:360px;}
      .block-container{padding:0.3rem !important;}
    }
    /* 扫描结果表 */
    .rt3-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;}
    .rt3{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed;min-width:560px}
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

    from html import escape as _he
    seen: set = set()
    rows_html = []

    for _, r in df.iterrows():
        in_zone   = bool(r.get("in_zone", False))
        dist      = safe_float(r.get("dist_pct"))
        price     = r.get("current_price")
        retrace   = r.get("retrace_pct")
        conf_l    = r.get("confluence_label", "—") or "—"
        cat       = r.get("category", "")
        ticker    = str(r.get("ticker", ""))
        name      = str(r.get("name", ""))
        tf        = r.get("timeframe", "")
        # 始终从 ticker+timeframe 实时生成 TV 链接（不依赖存储的旧 URL）
        tv_lnk    = tv_url(ticker, tf) if ticker else "#"
        # XSS 防护：转义用户可控字段
        name_s    = _he(name)
        ticker_s  = _he(ticker)

        price_s   = f"{float(price):,.4f}"   if price   is not None else "—"
        retrace_s = f"{float(retrace):.1f}%" if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        is_first = ticker not in seen
        seen.add(ticker)
        is_fav   = ticker in watchlist_tickers

        # 收藏列：用 <a href> 触发 query_params
        from urllib.parse import quote as _qu
        _t = _he(st.query_params.get("_t", ""))
        if is_first:
            # URL encode ticker+name 防止注入
            fav_enc = _qu(f"{'del' if is_fav else 'add'}|{ticker}|{name}", safe="")
            _icon  = "★" if is_fav else "☆"
            _cls   = "fav-star" if is_fav else "fav-empty"
            _tip   = _he(f"{'取消收藏' if is_fav else '收藏'}：{name}")
            fav_html = (
                f'<a href="?_t={_t}&_fav={fav_enc}" '
                f'class="fav-btn {_cls}" title="{_tip}">{_icon}</a>'
            )
        else:
            fav_html = ""

        zone_cls = ' class="zone"' if in_zone else ""
        rows_html.append(
            f"<tr{zone_cls}>"
            f"<td style='width:20%'><b>{name_s}</b>"
            f"<br><small style='color:#9ca3af;font-family:monospace'>{ticker_s}</small></td>"
            f"<td style='width:8%'><span class='badge b-gray'>{_cat_label(cat)}</span></td>"
            f"<td style='width:7%'><span class='badge b-gray'>{_he(tf)}</span></td>"
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
        f"<div class='rt3-wrap'><table class='rt3'><thead>{thead}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="color:#9ca3af;font-size:11px;margin-top:6px">'
        f'共 {len(df)} 条 &nbsp;｜&nbsp; 点击 ☆/★ 收藏/取消收藏</div>',
        unsafe_allow_html=True,
    )

    csv = df.drop(columns=[c for c in ["_r", "_d"] if c in df.columns],
                  errors="ignore").to_csv(index=False).encode("utf-8-sig")
    _dl_col, _spacer, _clear_col = st.columns([3, 1, 2])
    with _dl_col:
        st.download_button(
            "⬇️ 下载 CSV", csv,
            file_name=f"strx_fibo_{last_s.get('scan_date', 'today')}.csv",
            mime="text/csv",
        )
    with _clear_col:
        # 仅清空本页扫描结果（保留自选收藏、配置、告警日志）
        if st.button("🗑️ 清空扫描结果", key="clear_scan_results_btn",
                     help="仅清除本次扫描结果缓存，不影响自选收藏和系统配置",
                     type="secondary", use_container_width=True):
            storage.clear_all_scan_data()
            st.toast("✅ 扫描结果已清空，可重新扫描", icon="🗑️")
            st.rerun()

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


_SCAN_TF_OPTIONS = ["Daily", "Weekly", "Monthly"]


def _normalize_scan_timeframes(selected) -> list[str]:
    tf_names = [t for t in (selected or _SCAN_TF_OPTIONS) if t in TIMEFRAMES]
    if not tf_names:
        tf_names = list(TIMEFRAMES.keys())
    return tf_names


def _resolve_symbol_token(token: str) -> tuple[str, tuple[str, str]] | None:
    key = token.strip()
    if not key:
        return None

    upper = key.upper()
    if upper in ASSETS:
        return upper, ASSETS[upper]

    # exact name match in assets
    for tk, (nm, cat) in ASSETS.items():
        if nm.strip().lower() == key.lower():
            return tk, (nm, cat)

    # alias fallback
    alias_match = _NAME_ALIAS.get(key) or _NAME_ALIAS.get(upper)
    if alias_match:
        tk = alias_match[0].upper()
        if tk in ASSETS:
            return tk, ASSETS[tk]
        return tk, (alias_match[1], "custom")

    # correction fallback
    suggestions = _suggest_corrections(key)
    if suggestions:
        tk = suggestions[0].get("ticker", "").upper()
        if tk:
            if tk in ASSETS:
                return tk, ASSETS[tk]
            return tk, (suggestions[0].get("name") or tk, "custom")
    return None


def _list_symbol_files() -> list[Path]:
    base = Path.cwd() / "Doc" / "symbol"
    files: list[Path] = []
    if base.exists() and base.is_dir():
        for ext in ("*.txt", "*.csv", "*.list"):
            files.extend(sorted(base.glob(ext)))
    return files


def _resolve_symbol_input_path(path_text: str) -> Path:
    raw = (path_text or "").strip().strip('"').strip("'")
    if not raw:
        return Path.cwd() / "Doc" / "symbol"

    candidates: list[Path] = []
    p = Path(raw).expanduser()
    candidates.append(p)

    if not p.is_absolute():
        candidates.append(Path.cwd() / raw)

    normalized = raw.replace("\\", "/")
    marker = "/doc/symbol/"
    low = normalized.lower()
    if marker in low:
        idx = low.index(marker)
        tail = normalized[idx + len(marker):].strip("/")
        mapped_base = Path.cwd() / "Doc" / "symbol"
        candidates.append(mapped_base / tail if tail else mapped_base)
    elif ":" in raw:
        candidates.append(Path.cwd() / "Doc" / "symbol" / Path(raw).name)

    for c in candidates:
        if c.exists():
            return c

    tried = " | ".join(str(c) for c in candidates[:4])
    raise FileNotFoundError(f"路径不存在：{raw}（尝试：{tried}）")


def _parse_symbol_text(text: str) -> tuple[dict, list[str]]:
    assets_map: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        token = line
        if "," in token:
            token = token.split(",", 1)[0].strip()
        if "\t" in token:
            token = token.split("\t", 1)[0].strip()
        if not token:
            continue

        resolved = _resolve_symbol_token(token)
        if resolved:
            tk, meta = resolved
            assets_map[tk] = meta
        else:
            unresolved.append(token)

    return assets_map, unresolved


def _load_symbols_assets_from_path(path_text: str) -> tuple[dict, list[str]]:
    p = _resolve_symbol_input_path(path_text)

    files: list[Path] = []
    if p.is_file():
        files = [p]
    else:
        for ext in ("*.txt", "*.csv", "*.list"):
            files.extend(sorted(p.glob(ext)))
    if not files:
        raise ValueError("未找到可读取的 symbol 文件（支持 .txt/.csv/.list）")

    assets_map: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []

    for file in files:
        text = file.read_text(encoding="utf-8", errors="ignore")
        parsed_assets, parsed_unresolved = _parse_symbol_text(text)
        assets_map.update(parsed_assets)
        unresolved.extend(parsed_unresolved)

    return assets_map, unresolved


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

    tf_selected = st.multiselect(
        "扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("custom_scan_tfs", _SCAN_TF_OPTIONS),
        key="custom_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    # 自动触发扫描（来自"建议代码"按钮或"扫描 XX.SS"按钮点击）
    _auto_trig = st.session_state.pop("_auto_scan_trigger", None)
    if _auto_trig:
        do_custom = True
        custom_ticker = _auto_trig.upper()
        # 同步更新 custom_name 若已预置
        if st.session_state.get("custom_name_confirmed"):
            custom_name = st.session_state["custom_name_confirmed"]

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
                    if st.button(f"✅ 扫描 {sug['ticker']}", key=f"err_sug_{i}_{sug['ticker']}",
                                 type="primary"):
                        # 清除旧 widget state，用 prefill 机制更新输入框
                        st.session_state.pop("custom_ticker_input", None)
                        st.session_state["custom_ticker_prefill"]  = sug["ticker"]
                        st.session_state["custom_name_confirmed"]  = sug.get("name", "")
                        st.session_state["custom_ticker_confirmed"]= sug["ticker"]
                        st.session_state["_auto_scan_trigger"]     = sug["ticker"]
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
            timeframe_names=tf_names,
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


def _render_symbol_path_scan(cfg):
    st.caption("支持读取文件或目录（.txt/.csv/.list），每行一个 ticker 或品种名称。")
    tf_selected = st.multiselect(
        "文件扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("symbol_file_scan_tfs", _SCAN_TF_OPTIONS),
        key="symbol_file_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    uploaded = st.file_uploader(
        "上传 symbol 文件（可选）",
        type=["txt", "csv", "list"],
        key="symbol_file_upload",
        help="云端推荐：直接上传 MG.txt，无需依赖服务器路径",
    )
    pasted_symbols = st.text_area(
        "或直接粘贴 symbols（可选）",
        value="",
        key="symbol_pasted_text",
        height=110,
        placeholder="每行一个代码或名称，例如：\nAAPL\nTSLA\n0700.HK\n贵州茅台",
    ).strip()

    path_text = st.text_input(
        "symbol 文件路径",
        value=st.session_state.get("symbol_file_path", "Doc/symbol"),
        key="symbol_file_path",
        placeholder="Doc/symbol 或 Doc/symbol/MG.txt",
    ).strip()

    do_file_scan = st.button("📂 扫描该路径中的品种", key="scan_from_symbol_path", type="primary")
    if not do_file_scan:
        return

    file_assets: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []
    source_label = ""

    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        file_assets, unresolved = _parse_symbol_text(text)
        source_label = f"upload:{uploaded.name}"
    elif pasted_symbols:
        file_assets, unresolved = _parse_symbol_text(pasted_symbols)
        source_label = "paste"
    else:
        try:
            file_assets, unresolved = _load_symbols_assets_from_path(path_text)
            source_label = f"path:{path_text}"
        except Exception as e:
            st.error(f"读取失败：{e}")
            files = _list_symbol_files()
            if files:
                sample = "、".join(f.name for f in files[:12])
                st.caption(f"可用文件：{sample}")
                st.caption("建议输入相对路径，例如：`Doc/symbol/MG.txt`")
            else:
                st.caption("当前部署环境未发现 `Doc/symbol` 文件。请改用“上传 symbol 文件”或直接粘贴 symbols。")
            return

    if not file_assets:
        st.warning("未解析到有效品种，请检查文件内容。")
        if unresolved:
            st.caption("未识别条目示例: " + "、".join(unresolved[:10]))
        return

    st.info(f"将扫描 {len(file_assets)} 个品种，周期：{' / '.join(tf_names)}")
    pb = st.progress(0, "准备扫描…")
    msg = st.empty()

    def cb2(pct, text):
        pb.progress(min(float(pct), 1.0), text)
        msg.caption(text)

    summary2, err2 = sc.run_full_scan(
        cfg=cfg,
        assets=file_assets,
        note=source_label,
        timeframe_names=tf_names,
        progress_callback=cb2,
    )
    pb.empty()
    msg.empty()

    if err2:
        st.error(f"文件扫描失败: {err2}")
        return
    st.success(
        f"文件扫描完成：{summary2.get('asset_count', len(file_assets))} 个品种，"
        f"黄金区 {summary2.get('inzone_count', 0)}，"
        f"周期 {' / '.join(summary2.get('timeframes', tf_names))}"
    )
    if unresolved:
        st.caption("未识别条目: " + "、".join(unresolved[:20]))
    st.rerun()


# ════════════════════════════════════════════════════════════════════
# 分批扫描选择器  ── 重新设计 v2
#
# 架构：
#   1. 唯一 session_state key：`_scan_sel`（set，存已选组名）
#   2. 快捷按钮直接写 `_scan_sel`，无第二个 key
#   3. 分类折叠面板：每个顶级分类独立一行，行内 checkbox 选子组
#   4. 底部固定状态栏 + 扫描按钮
# ════════════════════════════════════════════════════════════════════
def _render_batch_selector(cfg):
    """
    分批扫描选择器 v3 — 修复全选/扫描按钮失效问题
    ─────────────────────────────────────────────
    根本原因：
      Streamlit checkbox 有自己的 widget key，rerun 后 widget state 优先于 value=。
      旧代码：全选按钮写 _scan_sel → rerun → checkbox widget state 仍是旧值（False）
              → checkbox 返回 False → _new.discard(g) 把刚加进去的组立刻删掉。
    
    修复方案：
      1. checkbox 不使用固定 key（每次渲染重新生成），强制 value= 参数生效
      2. checkbox 变化时用 st.rerun() 让整个 UI 刷新，保证视觉一致
      3. 全选/快捷按钮 → 更新 _scan_sel → rerun（同上，无 key 冲突）
    """
    from collections import defaultdict

    group_names  = list(ASSET_GROUPS.keys())
    total_assets = sum(len(v) for v in ASSET_GROUPS.values())
    n_groups     = len(group_names)

    # ── session state 初始化 ─────────────────────────────────────
    if "_scan_sel" not in st.session_state:
        st.session_state["_scan_sel"] = set()

    # 读取当前已选（过滤无效组名）
    sel: set = {g for g in st.session_state["_scan_sel"] if g in ASSET_GROUPS}
    st.session_state["_scan_sel"] = sel   # 写回清洁版

    # ── 信息栏 ───────────────────────────────────────────────────
    st.markdown(
        f'<div class="n-info">📦 品种库：共 <b>{total_assets}</b> 个品种，分 '
        f'<b>{n_groups}</b> 组。每组约 13–30 个品种 × 3 框架，单批约 1–3 分钟。'
        f'多次扫描结果自动缓存合并，无需一次全部完成。</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**📅 批量扫描周期（可只选 Monthly）**")
    tf_selected = st.multiselect(
        "批量扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("batch_scan_tfs", _SCAN_TF_OPTIONS),
        key="batch_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    # ── 快捷选择按钮 ─────────────────────────────────────────────
    _QUICK = [
        ("☑️ 全选",      lambda g: True),
        ("🥇 期货+指数",  lambda g: any(k in g for k in ["期货","指数","全球","ETF"])),
        ("🇺🇸 美股+ETF",  lambda g: "美股" in g or "ETF" in g),
        ("🇨🇳 中股",      lambda g: any(k in g for k in ["中概","港股","A股","中国","中国指数"])),
        ("💱 外汇",       lambda g: "外汇" in g),
        ("₿ 加密",       lambda g: "加密" in g),
        ("🌏 亚太",       lambda g: any(k in g for k in ["日本","韩国","台湾","印度","澳大利亚","东南亚"])),
        ("🌍 欧洲",       lambda g: any(k in g for k in ["英国","德国","法国","北欧","欧洲"])),
        ("🌎 新兴",       lambda g: any(k in g for k in ["加拿大","拉美","新兴","非洲","中东"])),
        ("🔲 清空",       None),
    ]

    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] > div > div > button {
        padding: 4px 8px !important; font-size: 12px !important;
        min-height: 32px !important;
    }
    </style>""", unsafe_allow_html=True)

    cols = st.columns(len(_QUICK))
    for i, (label, fn) in enumerate(_QUICK):
        with cols[i]:
            if st.button(label, key=f"_qbtn_{i}", use_container_width=True):
                if fn is None:
                    st.session_state["_scan_sel"] = set()
                else:
                    st.session_state["_scan_sel"] = {g for g in group_names if fn(g)}
                st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── 构建 顶级分类 → [组名列表] ──────────────────────────────
    cat_groups: dict = defaultdict(list)
    for g in group_names:
        parts = g.split(" - ", 1)
        cat_groups[parts[0].strip()].append(g)

    sorted_cats = sorted(cat_groups.items(), key=lambda x: -len(x[1]))

    # ── 分类面板 ─────────────────────────────────────────────────
    scanned = storage.load_scanned_groups()
    st.markdown("**📋 按分类选择品种组**（点击分类名展开/收起）：")

    # 用于收集本轮 checkbox 产生的变更
    _pending_add    = set()
    _pending_remove = set()

    for cat, groups in sorted_cats:
        n_in_cat   = len(groups)
        sel_in_cat = sum(1 for g in groups if g in sel)
        all_sel    = (sel_in_cat == n_in_cat)

        with st.expander(
            f"{'✅' if all_sel else ('☑' if sel_in_cat > 0 else '⬜')} "
            f"{cat}  "
            f"{'（已全选）' if all_sel else f'（{sel_in_cat}/{n_in_cat}）'}",
            expanded=(sel_in_cat > 0),
        ):
            # ── 该分类全选 / 取消全选 ───────────────────────────
            c_all, c_none, _ = st.columns([2, 2, 6])
            with c_all:
                if st.button(f"全选 {n_in_cat} 组", key=f"_cat_all_{cat}",
                             use_container_width=True):
                    st.session_state["_scan_sel"] = sel | set(groups)
                    st.rerun()
            with c_none:
                if sel_in_cat > 0:
                    if st.button("取消全选", key=f"_cat_none_{cat}",
                                 use_container_width=True):
                        st.session_state["_scan_sel"] = sel - set(groups)
                        st.rerun()

            # ── 子组 checkbox（关键修复：不使用固定 key）────────
            # 不传 key 参数，Streamlit 每次重新渲染时不保留 widget state，
            # value= 参数始终生效，与 _scan_sel 完全同步。
            if n_in_cat == 1:
                g = groups[0]
                short      = g.split(" - ", 1)[-1] if " - " in g else g
                n_assets   = len(ASSET_GROUPS[g])
                is_scanned = g in scanned
                label_txt  = f"{short}  ({n_assets} 品种)" + (" ✅缓存" if is_scanned else "")
                new_checked = st.checkbox(label_txt, value=(g in sel))
                if new_checked != (g in sel):
                    if new_checked: _pending_add.add(g)
                    else:           _pending_remove.add(g)
            else:
                _cols = st.columns(3)
                for ci, g in enumerate(groups):
                    short      = g.split(" - ", 1)[-1] if " - " in g else g
                    n_assets   = len(ASSET_GROUPS[g])
                    is_scanned = g in scanned
                    label_txt  = f"{short}  ({n_assets})" + (" ✅" if is_scanned else "")
                    with _cols[ci % 3]:
                        new_checked = st.checkbox(label_txt, value=(g in sel))
                        if new_checked != (g in sel):
                            if new_checked: _pending_add.add(g)
                            else:           _pending_remove.add(g)

    # ── 应用 checkbox 变更（如有则 rerun 刷新 UI）────────────────
    if _pending_add or _pending_remove:
        new_sel = (sel | _pending_add) - _pending_remove
        st.session_state["_scan_sel"] = new_sel
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── 状态栏 + 扫描按钮（始终渲染，即使 sel 为空也显示提示）──
    sel_list   = sorted(sel, key=lambda g: group_names.index(g))
    sel_assets: dict = {}
    for g in sel_list:
        sel_assets.update(ASSET_GROUPS[g])
    checks = len(sel_assets) * len(tf_names)

    scanned_list = storage.load_scanned_groups()
    already   = [g for g in sel_list if g in scanned_list]
    unscanned = [g for g in sel_list if g not in scanned_list]

    col_info, col_btn = st.columns([5, 2])
    with col_info:
        if sel_list:
            st.markdown(
                f"**已选：{len(sel_list)} 组 · {len(sel_assets)} 个品种 · {checks} 次检查**"
            )
            st.caption(f"周期：{' / '.join(tf_names) if tf_names else '未选择'}")
            if already:
                st.caption(
                    f"✅ 已缓存（可跳过）：{'、'.join(g.split(' - ')[-1] for g in already[:5])}"
                    + (f" 等{len(already)}组" if len(already) > 5 else "")
                )
            if unscanned:
                st.caption(
                    f"🆕 未扫描：{'、'.join(g.split(' - ')[-1] for g in unscanned[:5])}"
                    + (f" 等{len(unscanned)}组" if len(unscanned) > 5 else "")
                )
        else:
            st.info("💡 请在上方选择至少一个品种组，或使用快捷按钮批量选择。")

    with col_btn:
        do_scan = st.button(
            f"🚀 扫描选中 {len(sel_assets)} 品种" if sel_assets else "🚀 扫描（请先选择组）",
            type="primary",
            use_container_width=True,
            disabled=(len(sel_assets) == 0 or len(tf_names) == 0),   # 未选时置灰，但按钮始终可见
        )

    if sel_assets and not tf_names:
        st.warning("请至少选择一个扫描周期。")

    if do_scan and sel_assets and tf_names:
        # ── 进度显示区：进度条 + 实时状态文字 ──────────────────
        pb      = st.progress(0.0, "🚀 启动扫描引擎…")
        msg     = st.empty()
        # 实时统计面板（扫描过程中持续刷新）
        stats_ph = st.empty()

        _done_ref   = [0]     # 用列表实现可变引用（闭包捕获）
        _inzone_ref = [0]

        def cb(pct, text):
            # 更新进度条
            pb.progress(min(float(pct), 1.0), text)
            # 从 text 里解析已完成数/黄金区数（格式: "✅ N/M  name  |  黄金区: X 个"）
            import re as _re
            m1 = _re.search(r"(\d+)/(\d+)", text)
            m2 = _re.search(r"黄金区[：:]\s*(\d+)", text)
            if m1:
                _done_ref[0]   = int(m1.group(1))
            if m2:
                _inzone_ref[0] = int(m2.group(2) if m2.lastindex == 2 else m2.group(1))
            # 小面板：实时展示进度数字
            done_n   = _done_ref[0]
            total_n  = len(sel_assets)
            inzone_n = _inzone_ref[0]
            remain   = max(total_n - done_n, 0)
            stats_ph.markdown(
                f"<div style='background:#f0fdf4;border:1px solid #bbf7d0;"
                f"border-radius:8px;padding:8px 16px;font-size:13px;'>"
                f"📊 已扫描 <b style='color:#166534'>{done_n}</b> / {total_n} 个品种 &nbsp;｜&nbsp; "
                f"剩余 <b>{remain}</b> &nbsp;｜&nbsp; "
                f"⭐ 黄金区命中 <b style='color:#d97706'>{inzone_n}</b> 个"
                f"</div>",
                unsafe_allow_html=True,
            )

        group_label = "、".join(g.split(" - ")[-1] for g in sel_list[:3]) + \
                      (f"等{len(sel_list)}组" if len(sel_list) > 3 else "")

        # 注意：不用 st.spinner（会遮盖进度条），直接调用
        summary, err = sc.run_full_scan(
            cfg=cfg,
            assets=sel_assets,
            note=f"batch:{group_label}",
            timeframe_names=tf_names,
            progress_callback=cb,
        )

        pb.empty(); msg.empty(); stats_ph.empty()
        if err:
            st.error(err)
        else:
            storage.save_scanned_groups(sel_list)
            inzone_c = summary['inzone_count']
            triple_c = summary['triple_conf']
            elapsed  = summary['elapsed_ms'] / 1000
            asset_c  = summary['asset_count']
            # 成功完成：绿色结果卡片
            st.markdown(
                f"<div style='background:#f0fdf4;border:2px solid #22c55e;"
                f"border-radius:10px;padding:12px 20px;margin:8px 0;'>"
                f"<b style='color:#166534;font-size:15px'>✅ 扫描完成！</b><br>"
                f"<span style='font-size:13px;color:#374151'>"
                f"扫描品种 <b>{asset_c}</b> 个 &nbsp;·&nbsp; "
                f"黄金区命中 <b style='color:#d97706'>{inzone_c}</b> 个 &nbsp;·&nbsp; "
                f"三框架共振 <b style='color:#dc2626'>{triple_c}</b> 个 &nbsp;·&nbsp; "
                f"耗时 <b>{elapsed:.1f}s</b>"
                f"</span></div>",
                unsafe_allow_html=True,
            )
            st.caption(f"本次周期：{' / '.join(summary.get('timeframes', tf_names))}")
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
