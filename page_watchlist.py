"""
page_watchlist.py — 自选收藏夹 v7
架构重点：
- 分类分组展示，已全看的分类自动折叠
- 今日巡视进度条（session_state，刷新不丢失）
- 标记已看/取消已看按钮（轻量操作，不重载数据）
- @st.cache_data 缓存扫描结果 60s，杜绝重复读大文件
- 操作按钮精简，减少 rerun 频次
"""

from datetime import date
from html import escape as _he
import re
import streamlit as st
import storage
from scanner import fetch_data

def _tv_link(ticker: str) -> str:
    try:
        from assets import tv_url as _tv_url
        return _tv_url(ticker)
    except Exception:
        return f"https://cn.tradingview.com/chart/?symbol={ticker}"


def _sina_link(ticker: str):
    """A股返回新浪财经链接，支持 600519.SS / 000001.SZ 及纯6位数字。"""
    t = ticker.upper().strip()
    if t.endswith(".SS"):
        return f"https://finance.sina.com.cn/realstock/company/sh{t[:-3]}/nc.shtml"
    if t.endswith(".SZ"):
        return f"https://finance.sina.com.cn/realstock/company/sz{t[:-3]}/nc.shtml"
    if t.isdigit() and len(t) == 6:
        if t.startswith("6") or t.startswith("5"):
            return f"https://finance.sina.com.cn/realstock/company/sh{t}/nc.shtml"
        if t.startswith("0") or t.startswith("3") or t.startswith("2"):
            return f"https://finance.sina.com.cn/realstock/company/sz{t}/nc.shtml"
    return None

def _row_anchor_id(ticker: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", str(ticker).upper())
    return f"wl_row_{safe}"

def _remember_focus_row(ticker: str):
    st.session_state["_wl_focus_anchor"] = _row_anchor_id(ticker)

def _restore_focus_row_if_needed():
    anchor = st.session_state.pop("_wl_focus_anchor", None)
    if not anchor:
        return
    anchor = str(anchor).replace('"', "").replace("'", "")
    st.markdown(
        f"""
        <script>
        setTimeout(function() {{
          try {{
            const el = parent.document.getElementById("{anchor}");
            if (el) {{
              el.scrollIntoView({{behavior: "instant", block: "center"}});
            }}
          }} catch (e) {{}}
        }}, 40);
        </script>
        """,
        unsafe_allow_html=True,
    )

def _get_viewed() -> set:
    return storage.load_viewed_today()

def _mark_viewed(ticker: str):
    storage.mark_viewed(ticker)

def _unmark_viewed(ticker: str):
    storage.unmark_viewed(ticker)

def _latest_note(item: dict):
    notes = item.get("notes", [])
    if notes:
        return notes[-1]
    old = item.get("note", "")
    if old:
        return {"text": old, "img_url": "", "ts": item.get("added_at", "")}
    return None

def _all_notes(item: dict) -> list:
    notes = item.get("notes", [])
    if notes:
        return notes
    old = item.get("note", "")
    if old:
        return [{"text": old, "img_url": "", "ts": item.get("added_at", "")}]
    return []

@st.cache_data(ttl=60, show_spinner=False)
def _cached_result_map():
    """扫描结果缓存 60 秒，避免每次 rerun 重读大文件。"""
    rm = {}
    for r in storage.load_latest_results():
        tk = r.get("ticker", "").upper()
        rm.setdefault(tk, []).append(r)
    return rm


# ── Ticker 名称自动获取（session_state 缓存，避免 cache_data 与 session_state 冲突）
def _fetch_ticker_name(ticker: str) -> str:
    """查询 ticker 的公司/品种全称。
    - A股（纯6位数字 或 .SS/.SZ 后缀）：优先从新浪财经 API 获取中文名
    - 其他：yfinance 查询
    结果存入 session_state['_yfname_cache'] 字典，同一会话不重复请求。
    """
    cache = st.session_state.setdefault("_yfname_cache", {})
    key   = ticker.upper().strip()
    if key in cache:
        return cache[key]

    # ── 判断是否 A股，确定新浪代码 ──────────────────────────────
    sina_code = None  # e.g. "sh601138" / "sz000001"
    yf_ticker = key

    if key.isdigit() and len(key) == 6:
        if key.startswith("6") or key.startswith("5"):
            sina_code = "sh" + key
            yf_ticker = key + ".SS"
        elif key.startswith("0") or key.startswith("3") or key.startswith("2"):
            sina_code = "sz" + key
            yf_ticker = key + ".SZ"
    elif key.endswith(".SS"):
        sina_code = "sh" + key[:-3]
    elif key.endswith(".SZ"):
        sina_code = "sz" + key[:-3]

    name = ""

    # ── A股：新浪实时行情接口（返回中文名）────────────────────────
    if sina_code:
        try:
            import requests
            r = requests.get(
                f"https://hq.sinajs.cn/list={sina_code}",
                headers={"Referer": "https://finance.sina.com.cn"},
                timeout=5,
            )
            r.encoding = "gbk"
            # 返回格式：var hq_str_sh601138="工业富联,xxx,...";
            text = r.text
            start = text.find('"')
            end   = text.rfind('"')
            if start != -1 and end > start:
                fields = text[start+1:end].split(",")
                if fields and fields[0].strip():
                    name = fields[0].strip()
        except Exception:
            pass

    # ── fallback：yfinance（非A股 或 新浪失败）──────────────────
    if not name:
        try:
            import yfinance as yf
            info = yf.Ticker(yf_ticker).info
            name = (info.get("shortName") or info.get("longName") or "").strip()
        except Exception:
            name = ""

    cache[key] = name
    return name


# ══════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## ⭐ 自选收藏夹")

    # ── 品种名内联编辑按钮样式 + 按钮行美化 + 移动端列强制水平排列 ──
    st.markdown("""
    <style>
    /* ── 品种名编辑按钮：透明风格 ── */
    button[id*="wl_name_click_"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        color: var(--text-color, #e2e8f0) !important;
        box-shadow: none !important;
        text-align: left !important;
        cursor: text !important;
        text-decoration: underline dotted rgba(148,163,184,0.5) !important;
    }
    button[id*="wl_name_click_"]:hover {
        background: rgba(59,130,246,0.1) !important;
        color: #38bdf8 !important;
    }

    /* ═══ 第一行操作按钮：👁 标记已看 / 📈 TradingView / 🏦 新浪 / 📌 置顶 / 🗑 删除 ═══ */
    button[id*="wl_v_"],
    button[id*="wl_pin_"],
    button[id*="wl_del_"] {
        background: rgba(255,255,255,0.07) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 8px !important;
        color: #cbd5e1 !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        min-height: 42px !important;
        transition: background 0.15s, border-color 0.15s, transform 0.12s !important;
    }
    button[id*="wl_v_"]:hover {
        background: rgba(34,197,94,0.2) !important;
        border-color: rgba(34,197,94,0.55) !important;
        color: #4ade80 !important;
        transform: translateY(-1px) !important;
    }
    button[id*="wl_pin_"]:hover {
        background: rgba(234,179,8,0.18) !important;
        border-color: rgba(234,179,8,0.5) !important;
        color: #fbbf24 !important;
        transform: translateY(-1px) !important;
    }
    button[id*="wl_del_"]:hover {
        background: rgba(239,68,68,0.18) !important;
        border-color: rgba(239,68,68,0.5) !important;
        color: #f87171 !important;
        transform: translateY(-1px) !important;
    }

    /* ═══ 第二行控制按钮：📁 分类 / 🏷️ 标签 / ✏️ 备注 / 📋 历史 / 📊 K线 ═══ */
    button[id*="wl_cat_btn_"],
    button[id*="wl_tags_btn_"],
    button[id*="wl_note_btn_"],
    button[id*="wl_hist_btn_"],
    button[id*="wl_chart_btn_"] {
        background: rgba(99,102,241,0.1) !important;
        border: 1px solid rgba(99,102,241,0.25) !important;
        border-radius: 6px !important;
        color: #a5b4fc !important;
        font-size: 15px !important;
        min-height: 34px !important;
        transition: background 0.15s, border-color 0.15s !important;
    }
    button[id*="wl_cat_btn_"]:hover,
    button[id*="wl_tags_btn_"]:hover,
    button[id*="wl_note_btn_"]:hover,
    button[id*="wl_hist_btn_"]:hover,
    button[id*="wl_chart_btn_"]:hover {
        background: rgba(99,102,241,0.25) !important;
        border-color: rgba(99,102,241,0.6) !important;
        color: #c7d2fe !important;
    }

    /* ═══ 移动端：强制水平排列 ═══ */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            gap: 3px !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            min-width: 0 !important;
            flex: 1 1 0 !important;
        }
        div[data-testid="stHorizontalBlock"] button {
            min-height: 32px !important;
            font-size: 13px !important;
        }
        div[data-testid="stHorizontalBlock"] a[data-testid="stBaseLinkButton-secondary"] {
            min-height: 32px !important;
            font-size: 13px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    _tab_idx = 0
    if st.session_state.pop("_wl_go_cats", False):
        _tab_idx = 1

    tab_main, tab_cats, tab_archive, tab_backup = st.tabs(
        ["⭐ 当前收藏", "🏷️ 分类管理", "🗂️ 已删除存档", "💾 备份与恢复"]
    )

    with tab_main:
        _render_main()
    with tab_cats:
        _render_categories()
    with tab_archive:
        _render_archive()
    with tab_backup:
        _render_backup()


# ══════════════════════════════════════════════════════════════════════
def _render_main():
    items      = storage.load_watchlist()
    cats       = storage.load_wl_categories()
    result_map = _cached_result_map()

    with st.expander("➕ 添加新品种", expanded=len(items) == 0):
        _render_add_form()

    items = storage.load_watchlist()
    if not items:
        st.markdown("""<div style="text-align:center;padding:60px 20px;color:#9ca3af;">
            <div style="font-size:48px">⭐</div>
            <div style="font-size:16px;font-weight:600;margin:12px 0 6px;color:#374151">收藏夹为空</div>
            <div style="font-size:13px">点击上方「添加新品种」开始收藏</div>
        </div>""", unsafe_allow_html=True)
        return

    # ── 今日进度条 ──────────────────────────────────────────────
    viewed_set = _get_viewed()
    total = len(items)
    done  = sum(1 for i in items if i["ticker"].upper() in viewed_set)
    pct   = int(done / total * 100) if total else 0
    bar_c = "#22c55e" if pct == 100 else "#3b82f6"
    st.markdown(
        f'<div style="margin:8px 0 14px">'
        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;margin-bottom:4px">'
        f'<span>📅 今日巡视进度</span>'
        f'<span style="font-weight:700;color:{bar_c}">{done}/{total} 已看 ({pct}%)</span>'
        f'</div>'
        f'<div style="height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden">'
        f'<div style="width:{pct}%;height:100%;background:{bar_c};border-radius:3px;transition:width .4s"></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── 工具栏 ──────────────────────────────────────────────────
    tc1, tc2, tc2_5, tc3, tc4 = st.columns([3, 2, 2, 2, 1])
    with tc1:
        search = st.text_input("🔍", placeholder="搜索 Ticker / 名称…",
                               key="wl_search", label_visibility="collapsed")
    with tc2:
        sel_cat = "__ALL__"
        if cats:
            _cf_ids   = ["__ALL__", "__NONE__"]
            _cf_names = {"__ALL__": "📁 全部分类", "__NONE__": "❓ 未分类"}
            def _wc(nodes, _ids=_cf_ids, _names=_cf_names, depth=0):
                for n in sorted(nodes, key=lambda x: x.get("order", 0)):
                    _ids.append(n["id"])
                    _names[n["id"]] = " " * depth + n["name"]
                    if n.get("children"):
                        _wc(n["children"], _ids, _names, depth + 1)
            _wc(storage.build_cat_tree(cats))
            sel_cat = st.selectbox("分类", _cf_ids,
                                   format_func=lambda x, m=_cf_names: m.get(x, x),
                                   key="wl_cat_filter_id",
                                   label_visibility="collapsed")
    with tc2_5:
        # 收集所有收藏品已有的标签
        all_tags = set()
        for item in items:
            for t in item.get("tags", []):
                all_tags.add(t)
        tag_options = ["📋 全部标签"] + sorted(list(all_tags))
        sel_tag = st.selectbox("标签过滤", tag_options, key="wl_tag_filter", label_visibility="collapsed")

    with tc3:
        if st.button("⚙️ 管理分类", key="wl_go_cats_btn", use_container_width=True):
            st.session_state["_wl_go_cats"] = True
    with tc4:
        if st.button("🗑️", key="wl_clear_all", use_container_width=True, help="清空收藏"):
            st.session_state["wl_confirm_clear"] = True

    if st.session_state.get("wl_confirm_clear"):
        st.warning("⚠️ 确定清空所有收藏？（将移入存档，可恢复）")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("确认清空", key="wl_clear_yes", type="primary"):
                for item in items: storage.remove_from_watchlist(item["ticker"])
                st.session_state["wl_confirm_clear"] = False
                st.rerun()
        with cc2:
            if st.button("取消", key="wl_clear_no"):
                st.session_state["wl_confirm_clear"] = False
                st.rerun()

    # ── 过滤 ────────────────────────────────────────────────────
    q        = search.strip().upper()
    filtered = items
    if q:
        filtered = [i for i in items
                    if q in i["ticker"].upper() or q in i.get("name","").upper()]
    if cats and sel_cat == "__NONE__":
        _known   = {c["id"] for c in cats} | {c["name"] for c in cats}
        filtered = [i for i in filtered
                    if not i.get("category_id") or i["category_id"] not in _known]
    elif cats and sel_cat not in ("__ALL__", None, ""):
        _valid  = {sel_cat} | storage._collect_descendants(cats, sel_cat)
        _vnames = {c["name"] for c in cats if c["id"] in _valid}
        filtered = [i for i in filtered
                    if i.get("category_id") in _valid or i.get("category_id") in _vnames]

    if sel_tag != "📋 全部标签":
        filtered = [i for i in filtered if sel_tag in i.get("tags", [])]

    pinned    = [i for i in filtered if i.get("pinned")]
    others    = [i for i in filtered if not i.get("pinned")]
    display   = pinned + others
    pinned_cnt = len(pinned)

    st.markdown(
        f"<div style='color:#6b7280;font-size:12px;margin-bottom:10px'>"
        f"共 {len(items)} 个 · 显示 {len(display)} 个"
        + (f" · 📌 {pinned_cnt} 个置顶" if pinned_cnt else "")
        + f" · ✅ {done}/{total} 今日已看</div>",
        unsafe_allow_html=True,
    )

    if not display:
        st.info("没有符合条件的品种。")
        return

    # ── 分组展示 ──────────────────────────────────────────────────
    cat_name_map = {c["id"]: c["name"] for c in cats}
    groups: dict = {}
    for item in display:
        cid = item.get("category_id") or "__NONE__"
        if cid != "__NONE__" and cid not in cat_name_map:
            m = next((c["id"] for c in cats if c["name"] == cid), None)
            cid = m if m else "__NONE__"
        gname = "❓ 未分类" if cid == "__NONE__" else cat_name_map.get(cid, "❓ 未分类")
        groups.setdefault(gname, []).append(item)

    def _gorder(name):
        for c in sorted(cats, key=lambda x: x.get("order", 0)):
            if c["name"] == name: return c.get("order", 99)
        return 999

    sorted_groups = sorted(groups.items(),
                           key=lambda x: 999 if x[0] == "❓ 未分类" else _gorder(x[0]))

    for gname, gitems in sorted_groups:
        g_done  = sum(1 for i in gitems if i["ticker"].upper() in viewed_set)
        g_total = len(gitems)
        all_done = g_done == g_total
        with st.expander(
            f"{'✅' if all_done else '📁'} {gname} · {g_done}/{g_total} 已看",
            expanded=not all_done,
        ):
            for item in gitems:
                _render_item_row(item, result_map, cats, viewed_set)

    # ── 导出 ─────────────────────────────────────────────────────
    st.markdown("---")
    import pandas as pd
    rows = []
    for item in items:
        tk = item["ticker"]
        ln = _latest_note(item)
        rows.append({
            "ticker":      tk,
            "name":        item.get("name",""),
            "latest_note": ln["text"] if ln else "",
            "added_at":    item.get("added_at",""),
            "pinned":      item.get("pinned", False),
        })
    df  = pd.DataFrame(rows)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    
    # Excel 导出
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='自选收藏')
    excel_data = excel_buffer.getvalue()

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button("⬇️ 导出收藏夹 CSV", csv,
                           file_name="strx_watchlist.csv", mime="text/csv",
                           key="wl_dl")
    with col_dl2:
        st.download_button("⬇️ 导出收藏夹 Excel", excel_data,
                           file_name="strx_watchlist.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="wl_dl_xlsx")
    _restore_focus_row_if_needed()


# ══════════════════════════════════════════════════════════════════════
def _render_item_row(item, result_map, cats, viewed_set):
    ticker = item["ticker"]
    name   = item.get("name", "")
    pinned = item.get("pinned", False)
    viewed = ticker.upper() in viewed_set
    results = result_map.get(ticker.upper(), [])
    latest  = _latest_note(item)
    tv_link   = _tv_link(ticker)
    sina_link = _sina_link(ticker)
    st.markdown(f'<div id="{_row_anchor_id(ticker)}"></div>', unsafe_allow_html=True)

    if viewed:
        row_style = (
            "background:rgba(34,197,94,0.10);"
            "border-left:3px solid rgba(34,197,94,0.7);"
            "border-top:1px solid rgba(34,197,94,0.2);"
            "border-right:1px solid rgba(34,197,94,0.2);"
            "border-bottom:1px solid rgba(34,197,94,0.2);"
            "opacity:0.88;"
        )
    elif pinned:
        row_style = (
            "background:rgba(234,179,8,0.10);"
            "border-left:3px solid rgba(234,179,8,0.7);"
            "border-top:1px solid rgba(234,179,8,0.25);"
            "border-right:1px solid rgba(234,179,8,0.25);"
            "border-bottom:1px solid rgba(234,179,8,0.25);"
        )
    else:
        row_style = (
            "background:var(--secondary-background-color, rgba(30,41,59,0.6));"
            "border:1px solid var(--border-color, rgba(255,255,255,0.1));"
        )

    display_name = _he(name or ticker)
    ticker_badge = (
        f' <span style="font-family:monospace;font-size:10px;'
        f'color:rgba(148,163,184,0.9);background:rgba(148,163,184,0.12);'
        f'border:1px solid rgba(148,163,184,0.2);'
        f'padding:1px 6px;border-radius:4px;vertical-align:middle">{_he(ticker)}</span>'
    ) if name else ""
    pin_icon  = "📌 " if pinned else ""
    view_icon = "✅ " if viewed else ""

    fibo_html = ""
    for r in results[:3]:
        tf     = r.get("timeframe","?")[:2]
        in_zone = r.get("in_zone", False)
        dist   = r.get("dist_pct")
        dist_s = f"{dist:.0f}%" if dist is not None else "—"
        bg = "rgba(234,179,8,0.18)" if in_zone else "rgba(107,114,128,0.12)"
        bd = "rgba(234,179,8,0.5)" if in_zone else "rgba(107,114,128,0.25)"
        fc = "#fbbf24" if in_zone else "#94a3b8"
        ico = "⚡" if in_zone else "·"
        fibo_html += (
            f'<span style="background:{bg};border:1px solid {bd};border-radius:5px;'
            f'padding:2px 7px;font-size:10px;white-space:nowrap;margin-right:4px;color:{fc};">'
            f'<b>{_he(tf)}</b> {ico}{dist_s}</span>'
        )

    note_html = ""
    note_lines = []
    if latest:
        nt   = latest.get("text","")
        nt_s = (nt[:50]+"…") if len(nt)>50 else nt
        note_lines.append(f'<span style="color:#60a5fa;">📝 自选：</span>{_he(nt_s)}')

    ticker_notes_data = storage.load_ticker_notes(ticker)
    ticker_note_text = ticker_notes_data.get("text", "").strip()
    if ticker_note_text:
        nt_s = (ticker_note_text[:50]+"…") if len(ticker_note_text)>50 else ticker_note_text
        note_lines.append(f'<span style="color:#f87171;">💎 备注：</span>{_he(nt_s)}')

    if note_lines:
        inner_html = "<br>".join(note_lines)
        note_html = (
            f'<div style="font-size:12px;font-weight:500;margin-top:5px;'
            f'padding-top:5px;border-top:1px solid rgba(255,255,255,0.08);line-height:1.4;">'
            f'{inner_html}</div>'
        )

    # ── 编辑状态key ──────────────────────────────────────────────
    _edit_key   = f"wl_edit_name_{ticker}"   # True = 编辑中
    _val_key    = f"wl_edit_val_{ticker}"    # 输入框当前值
    is_editing  = st.session_state.get(_edit_key, False)

    if is_editing:
        # ── 编辑模式：显示 text_input，on_change 触发保存 ────────
        def _save_name():
            new_val = st.session_state.get(_val_key, "").strip()
            items_all = storage.load_watchlist()
            for it in items_all:
                if it["ticker"].upper() == ticker.upper():
                    it["name"] = new_val
                    break
            storage.save_watchlist(items_all)
            st.session_state[_edit_key] = False

        st.text_input(
            "品种全称",
            value=name,
            key=_val_key,
            label_visibility="collapsed",
            placeholder="输入品种全称，回车保存…",
            on_change=_save_name,
        )
    else:
        # ── 展示模式 ─────────────────────────────────────────────
        tags_html = ""
        for t in item.get("tags", []):
            tags_html += (
                f'<span style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.35);border-radius:4px;'
                f'padding:2px 7px;font-size:10px;white-space:nowrap;margin-right:4px;color:#a5b4fc;font-weight:500;">'
                f'🏷️ {t}</span>'
            )
        t_token = st.query_params.get("_t", "")
        ticker_url = f"/?_page=ticker&_ticker={ticker}&_t={t_token}"
        display_name_html = f'<a href="{ticker_url}" target="_self" style="color:inherit; text-decoration:none; transition:color 0.2s;" onmouseover="this.style.color=\'#38bdf8\'" onmouseout="this.style.color=\'inherit\'">{pin_icon}{view_icon}{display_name}</a>'
        ticker_badge_html = f'<a href="{ticker_url}" target="_self" style="text-decoration:none; margin-left:6px;">{ticker_badge}</a>'
        
        st.markdown(
            f'<div style="{row_style}border-radius:10px;padding:10px 14px;margin-bottom:2px;">'
            f'<div style="font-size:15px;font-weight:700;color:var(--text-color,#f1f5f9);line-height:1.3;">'
            f'{display_name_html}{ticker_badge_html}</div>'
            + (f'<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px;">{fibo_html}{tags_html}</div>' if fibo_html or tags_html else "")
            + note_html
            + '</div>',
            unsafe_allow_html=True,
        )
        # 品种名按钮 → 进入编辑
        if st.button(
            f"✎ {name or ticker}",
            key=f"wl_name_click_{ticker}",
            help="点击编辑品种全称",
            use_container_width=False,
        ):
            st.session_state[_edit_key] = True
            st.session_state[_val_key]  = name

    if sina_link:
        bc1, bc2, bc3, bc4, bc5 = st.columns(5)
    else:
        bc1, bc2, bc3, bc4 = st.columns(4)

    with bc1:
        if st.button("✅" if viewed else "👁️",
                     key=f"wl_v_{ticker}",
                     help="取消已看" if viewed else "标记已看",
                     use_container_width=True):
            _remember_focus_row(ticker)
            if viewed: _unmark_viewed(ticker)
            else:      _mark_viewed(ticker)
            st.rerun()
    with bc2:
        st.link_button(
            "📈",
            tv_link,
            help="打开 TradingView（极速直连，不触发页面重载）",
            use_container_width=True,
        )
    if sina_link:
        with bc3:
            st.link_button(
                "🏦",
                sina_link,
                help="打开新浪财经（极速直连，不触发页面重载）",
                use_container_width=True,
            )
        with bc4:
            if st.button("🔓" if pinned else "📌",
                         key=f"wl_pin_{ticker}", help="置顶/取消",
                         use_container_width=True):
                _remember_focus_row(ticker)
                storage.toggle_pin_watchlist(ticker)
                st.rerun()
        with bc5:
            if st.button("🗑", key=f"wl_del_{ticker}", help="删除（移入存档）",
                         use_container_width=True):
                _remember_focus_row(ticker)
                storage.remove_from_watchlist(ticker)
                st.toast(f"已移入存档：{ticker}", icon="🗂️")
                st.rerun()
    else:
        with bc3:
            if st.button("🔓" if pinned else "📌",
                         key=f"wl_pin_{ticker}", help="置顶/取消",
                         use_container_width=True):
                _remember_focus_row(ticker)
                storage.toggle_pin_watchlist(ticker)
                st.rerun()
        with bc4:
            if st.button("🗑", key=f"wl_del_{ticker}", help="删除（移入存档）",
                         use_container_width=True):
                _remember_focus_row(ticker)
                storage.remove_from_watchlist(ticker)
                st.toast(f"已移入存档：{ticker}", icon="🗂️")
                st.rerun()

    # ── 第二行：操作/详情 ──
    _render_inline_controls(item, ticker, cats)


# ══════════════════════════════════════════════════════════════════════
def _build_cat_options(cats):
    """构建分类选项列表，每次调用返回全新的列表和字典，避免多品种共享污染。"""
    ids   = ["__UNCAT__"]
    names = {"__UNCAT__": "（未分类）"}

    def _walk(nodes, depth=0):
        pfx = (" " * depth + "└ ") if depth else ""
        for n in sorted(nodes, key=lambda x: x.get("order", 0)):
            ids.append(n["id"])
            names[n["id"]] = pfx + n["name"]
            if n.get("children"):
                _walk(n["children"], depth + 1)

    _walk(storage.build_cat_tree(cats))
    return ids, names


def _render_inline_controls(item, ticker, cats):
    cc = st.columns(5)

    with cc[0]:
        if st.button("📁", key=f"wl_cat_btn_{ticker}", help="设置分类", use_container_width=True):
            _remember_focus_row(ticker)
            k = f"wl_cat_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            if st.session_state[k]:
                st.session_state[f"wl_cat_init_{ticker}"] = True
            st.rerun()

    with cc[1]:
        if st.button("🏷️", key=f"wl_tags_btn_{ticker}", help="管理标签", use_container_width=True):
            _remember_focus_row(ticker)
            k = f"wl_tags_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            st.rerun()

    with cc[2]:
        if st.button("✏️", key=f"wl_note_btn_{ticker}", help="添加备注", use_container_width=True):
            _remember_focus_row(ticker)
            k = f"wl_note_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            st.rerun()

    with cc[3]:
        notes = _all_notes(item)
        if notes:
            hist_open = st.session_state.get(f"wl_hist_open_{ticker}", True)
            btn_label = "📋▲" if hist_open else f"📋({len(notes)})"
            if st.button(btn_label, key=f"wl_hist_btn_{ticker}",
                         help="收起备注" if hist_open else f"展开备注({len(notes)})",
                         use_container_width=True):
                _remember_focus_row(ticker)
                st.session_state[f"wl_hist_open_{ticker}"] = not hist_open
                st.rerun()
        else:
            st.button("📋", key=f"wl_hist_btn_disabled_{ticker}", disabled=True, use_container_width=True)

    with cc[4]:
        chart_open = st.session_state.get(f"wl_chart_open_{ticker}", False)
        chart_lbl = "📊▲" if chart_open else "📊"
        if st.button(chart_lbl, key=f"wl_chart_btn_{ticker}", help="查看 K线趋势图", use_container_width=True):
            _remember_focus_row(ticker)
            st.session_state[f"wl_chart_open_{ticker}"] = not chart_open
            st.rerun()

    # ── 标签管理面板 ──────────────────────────────────────────────
    if st.session_state.get(f"wl_tags_open_{ticker}"):
        with st.container(border=True):
            st.markdown(f"##### 🏷️ 「{item.get('name') or ticker}」的标签")
            cur_tags = ", ".join(item.get("tags", []))
            new_tags_input = st.text_input(
                "标签（多个用英文逗号 , 隔开）",
                value=cur_tags,
                key=f"wl_tags_input_{ticker}",
                placeholder="例如: 待入场, 已持仓, 观察中"
            )
            quick_tags = ["待入场", "已持仓", "观察中", "止损观察", "突破买入"]
            st.caption("常用标签点击快速选择：")
            cols = st.columns(len(quick_tags))
            for idx, qt in enumerate(quick_tags):
                with cols[idx]:
                    if st.button(qt, key=f"wl_qt_{ticker}_{idx}", use_container_width=True):
                        existing_tags = [t.strip() for t in st.session_state.get(f"wl_tags_input_{ticker}", "").split(",") if t.strip()]
                        if qt not in existing_tags:
                            existing_tags.append(qt)
                            st.session_state[f"wl_tags_input_{ticker}"] = ", ".join(existing_tags)
                            st.rerun()
            
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                if st.button("💾 保存标签", key=f"wl_tags_save_{ticker}", type="primary"):
                    _remember_focus_row(ticker)
                    tags_list = [t.strip() for t in st.session_state.get(f"wl_tags_input_{ticker}", "").split(",") if t.strip()]
                    items_all = storage.load_watchlist()
                    for it in items_all:
                        if it["ticker"].upper() == ticker.upper():
                            it["tags"] = tags_list
                            break
                    storage.save_watchlist(items_all)
                    st.session_state.pop(f"wl_tags_open_{ticker}", None)
                    st.toast("标签已更新", icon="🏷️")
                    st.rerun()
            with t_col2:
                if st.button("取消", key=f"wl_tags_cancel_{ticker}"):
                    _remember_focus_row(ticker)
                    st.session_state.pop(f"wl_tags_open_{ticker}", None)
                    st.rerun()

    # ── K线图面板 ──────────────────────────────────────────────────
    if st.session_state.get(f"wl_chart_open_{ticker}"):
        with st.container(border=True):
            st.markdown(f"##### 📊 {item.get('name') or ticker} 趋势图")
            try:
                import plotly.graph_objects as go
                import pandas as pd
                df = fetch_data(ticker, interval="1d", period="1y")
                if df is not None and not df.empty:
                    df_slice = df.tail(100)
                    if isinstance(df_slice.columns, pd.MultiIndex):
                        df_slice.columns = [c[0].lower() for c in df_slice.columns]
                    else:
                        df_slice.columns = [c.lower() for c in df_slice.columns]
                    
                    h_val = float(df_slice["high"].max())
                    l_val = float(df_slice["low"].min())
                    diff = h_val - l_val
                    f50 = h_val - 0.5 * diff
                    f618 = h_val - 0.618 * diff
                    
                    fig = go.Figure(data=[go.Candlestick(
                        x=df_slice.index,
                        open=df_slice['open'],
                        high=df_slice['high'],
                        low=df_slice['low'],
                        close=df_slice['close'],
                        name='K线'
                    )])
                    fig.add_hrect(
                        y0=f618, y1=f50,
                        fillcolor="rgba(245, 158, 11, 0.15)",
                        line_width=0,
                        annotation_text="黄金区 (0.50-0.618)",
                        annotation_position="top left",
                        annotation_font_color="#f59e0b"
                    )
                    fig.add_hline(y=h_val, line_dash="dash", line_color="#ef4444", annotation_text=f"高点: {h_val:.2f}")
                    fig.add_hline(y=l_val, line_dash="dash", line_color="#10b981", annotation_text=f"低点: {l_val:.2f}")
                    
                    fig.update_layout(
                        xaxis_rangeslider_visible=False,
                        height=280,
                        margin=dict(l=10, r=10, t=20, b=10),
                        template="plotly_dark"
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"wl_chart_fig_{ticker}")
                else:
                    st.warning("未能拉取到该品种的K线数据，请检查网络或代码。")
            except Exception as e:
                st.error(f"加载图表时发生异常: {e}")

    # ── 设置分类面板 ──────────────────────────────────────────────
    if st.session_state.get(f"wl_cat_open_{ticker}"):
        if not cats:
            st.warning("尚无分类，请先在「🏷️ 分类管理」标签创建。")
        else:
            # 每次调用返回全新列表，不同品种之间完全隔离
            _as_ids, _as_names = _build_cat_options(cats)

            _sel_key  = f"wl_cat_sel_{ticker}"
            _init_key = f"wl_cat_init_{ticker}"
            if st.session_state.pop(_init_key, False):
                cur      = item.get("category_id")
                _default = "__UNCAT__"
                if cur:
                    if cur in _as_ids:
                        _default = cur
                    else:
                        m = next((c["id"] for c in cats if c["name"] == cur), None)
                        if m:
                            _default = m
                st.session_state[_sel_key] = _default

            if st.session_state.get(_sel_key) not in _as_ids:
                st.session_state[_sel_key] = "__UNCAT__"

            # format_func 用默认参数固定捕获当前 _as_names，避免闭包问题
            chosen = st.selectbox(
                f"📂 「{item.get('name') or ticker}」的分类",
                _as_ids,
                format_func=lambda x, m=_as_names: m.get(x, x),
                key=_sel_key,
            )
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("💾 保存分类", key=f"wl_cat_save_{ticker}", type="primary"):
                    _remember_focus_row(ticker)
                    storage.set_watchlist_item_category(
                        ticker, None if chosen == "__UNCAT__" else chosen)
                    st.session_state.pop(f"wl_cat_open_{ticker}", None)
                    st.session_state.pop(_sel_key, None)
                    st.toast(f"已设置：{_as_names.get(chosen, '')}", icon="🏷️")
                    st.rerun()
            with sc2:
                if st.button("取消", key=f"wl_cat_cancel_{ticker}"):
                    _remember_focus_row(ticker)
                    st.session_state.pop(f"wl_cat_open_{ticker}", None)
                    st.session_state.pop(_sel_key, None)

    # ── 添加备注面板 ──────────────────────────────────────────────
    with st.container():
        if st.session_state.get(f"wl_note_open_{ticker}"):
            with st.container(border=True):
                new_text = st.text_input("备注内容 *", key=f"wl_note_txt_{ticker}",
                                         placeholder="输入本次备注…")
                new_img  = st.text_input("图片链接（选填）", key=f"wl_note_img_{ticker}",
                                         placeholder="https://...").strip()
                sn1, sn2 = st.columns(2)
                with sn1:
                    if st.button("💾 保存备注", key=f"wl_note_save_{ticker}", type="primary"):
                        _remember_focus_row(ticker)
                        if not new_text.strip():
                            st.warning("备注不能为空")
                        else:
                            storage.add_watchlist_note(ticker, new_text.strip(), new_img)
                            st.session_state.pop(f"wl_note_open_{ticker}", None)
                            st.toast(f"备注已保存：{ticker}", icon="📝")
                            st.rerun()
                with sn2:
                    if st.button("取消", key=f"wl_note_cancel_{ticker}"):
                        _remember_focus_row(ticker)
                        st.session_state.pop(f"wl_note_open_{ticker}", None)

    if st.session_state.get(f"wl_hist_open_{ticker}", True):
        notes = _all_notes(item)
        for n in reversed(notes):
            img_url_n = n.get("img_url", "")
            img_part  = (
                f' &nbsp;<a href="{_he(img_url_n)}" target="_blank" '
                f'style="font-size:11px;color:var(--primary-color, #3b82f6);text-decoration:none">🖼️</a>'
            ) if img_url_n else ""
            st.markdown(
                f'<div style="border-left:2px solid var(--border-color, #e5e7eb);padding:5px 10px;'
                f'margin:3px 0;font-size:12px;color:var(--text-color);">'
                f'<span style="opacity:0.6;color:var(--text-color);">{n.get("ts","")}</span>&nbsp;&nbsp;'
                f'<span style="color:var(--text-color);">{_he(str(n["text"]))}</span>'
                f'{img_part}</div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════
def _render_add_form():
    _prev_key    = "_wl_add_prev_ticker"
    _fetched_key = "_wl_add_fetched_name"

    c1, c2 = st.columns([2, 2])
    with c1:
        new_ticker = st.text_input(
            "Ticker 代码 *", placeholder="例: AAPL  600519.SS",
            key="wl_new_ticker",
        ).strip().upper()

    # ── 查询逻辑：在 c2 渲染之前执行，写入 wl_new_name 才有效 ────
    if new_ticker:
        prev = st.session_state.get(_prev_key, "")
        if new_ticker != prev:
            # ticker 变化 → 先清空名称栏，再查询填入
            st.session_state[_prev_key]    = new_ticker
            st.session_state[_fetched_key] = ""
            st.session_state["wl_new_name"] = ""   # 先清空，避免残留旧品种名
            fetched = _fetch_ticker_name(new_ticker)
            st.session_state[_fetched_key] = fetched
            if fetched:
                st.session_state["wl_new_name"] = fetched  # 直接填入，不判断是否为空
    else:
        st.session_state.pop(_prev_key,    None)
        st.session_state.pop(_fetched_key, None)
        if st.session_state.get("wl_new_name") == st.session_state.get(_fetched_key, "__NONE__"):
            st.session_state.pop("wl_new_name", None)

    # c2 在此渲染，读到的 wl_new_name 已是上面写入的值
    with c2:
        new_name = st.text_input(
            "品种全称（可选）", placeholder="例: 苹果公司",
            key="wl_new_name",
        )

    # ── 状态提示 ──────────────────────────────────────────────────
    fetched_name = st.session_state.get(_fetched_key, "")
    if new_ticker and st.session_state.get(_prev_key) == new_ticker:
        if fetched_name:
            if new_name.strip() == fetched_name:
                st.markdown(
                    f'<div style="font-size:12px;color:#16a34a;margin-top:-10px;margin-bottom:6px">'
                    f'✅ 已自动填入：<b>{_he(fetched_name)}</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="font-size:12px;color:#6b7280;margin-top:-10px;margin-bottom:6px">'
                    f'💡 查询到全称：<b>{_he(fetched_name)}</b>（已手动修改）</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="font-size:12px;color:#9ca3af;margin-top:-10px;margin-bottom:6px">'
                '— 未查询到全称，可手动填写</div>',
                unsafe_allow_html=True,
            )

    note_text = st.text_input(
        "📝 备注 *（必填）", placeholder="例: 关注 0.618 支撑",
        key="wl_new_note_text",
    )
    img_url = st.text_input(
        "🖼️ 图片链接（选填）", placeholder="https://...",
        key="wl_new_img_url",
    ).strip()

    if st.button("➕ 添加到收藏夹", key="wl_add_btn", type="primary"):
        if not new_ticker:
            st.warning("请输入 Ticker 代码")
        elif not note_text.strip():
            st.warning("备注为必填项")
        else:
            ok = storage.add_to_watchlist(new_ticker, new_name,
                                          note_text.strip(), img_url)
            if ok:
                st.success(f"✅ 已添加 {new_ticker}")
                for k in ["wl_new_ticker", "wl_new_name",
                          "wl_new_note_text", "wl_new_img_url",
                          _prev_key, _fetched_key]:
                    st.session_state.pop(k, None)
                _cached_result_map.clear()
            else:
                st.warning(f"⚠️ {new_ticker} 已在收藏夹中")

    st.markdown("---")
    st.markdown("**批量导入**（每行一个 Ticker，可附简称）")
    bulk_text = st.text_area("批量输入",
                             placeholder="AAPL 苹果\nTSLA 特斯拉\n600519.SS 茅台",
                             height=80, key="wl_bulk", label_visibility="collapsed")
    if st.button("批量添加", key="wl_bulk_btn"):
        added, skipped = [], []
        for line in bulk_text.strip().splitlines():
            parts = line.strip().split(None, 1)
            if not parts: continue
            tk = parts[0].upper()
            nm = parts[1] if len(parts) > 1 else ""
            if storage.add_to_watchlist(tk, nm, note="批量导入"):
                added.append(tk)
            else:
                skipped.append(tk)
        if added:
            st.success(f"✅ 新增 {len(added)} 个：{', '.join(added)}")
        if skipped:
            st.info(f"跳过：{', '.join(skipped)}")
        if added:
            _cached_result_map.clear()


# ══════════════════════════════════════════════════════════════════════
def _render_categories():
    st.markdown("### 🏷️ 分类管理")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '创建品种分类目录（支持三级），在品种卡片上点击 🏷️ 可指派分类。</p>',
        unsafe_allow_html=True,
    )

    cats = storage.load_wl_categories()

    with st.expander("➕ 新增分类", expanded=False):
        nc1, nc2 = st.columns([3, 2])
        with nc1:
            new_cat_name = st.text_input("分类名称 *",
                                         placeholder="例: 1.大结构突破", key="wl_new_cat_name")
        with nc2:
            _par_ids   = ["__ROOT__"]
            _par_names = {"__ROOT__": "（顶级分类）"}
            def _fill_par(nodes, _ids=_par_ids, _names=_par_names, depth=0):
                pfx = (" " * depth + "└ ") if depth else ""
                for n in sorted(nodes, key=lambda x: x.get("order", 0)):
                    _ids.append(n["id"])
                    _names[n["id"]] = pfx + n["name"]
                    if n.get("children") and depth < 1:
                        _fill_par(n["children"], _ids, _names, depth + 1)
            _fill_par(storage.build_cat_tree(cats))
            parent_id = st.selectbox("父级分类（可选）", _par_ids,
                                     format_func=lambda x, m=_par_names: m.get(x, x),
                                     key="wl_new_cat_parent")

        if st.button("➕ 创建分类", key="wl_cat_create", type="primary"):
            if not new_cat_name.strip():
                st.warning("分类名称不能为空")
            else:
                _par = None if parent_id == "__ROOT__" else parent_id
                storage.add_wl_category(new_cat_name.strip(), parent_id=_par)
                st.session_state.pop("wl_new_cat_name", None)
                st.toast(f"✅ 已创建：{new_cat_name.strip()}", icon="🏷️")

    cats = storage.load_wl_categories()
    if not cats:
        st.info("尚无分类，请点击上方「➕ 新增分类」创建。")
        return

    st.markdown("#### 📋 分类目录（可展开编辑、重命名、排序、删除）")
    tree      = storage.build_cat_tree(cats)
    all_items = storage.load_watchlist()

    def _count_items(cat_id):
        _valid  = {cat_id} | storage._collect_descendants(cats, cat_id)
        _vnames = {c["name"] for c in cats if c["id"] in _valid}
        return sum(1 for i in all_items
                   if i.get("category_id") in _valid
                   or i.get("category_id") in _vnames)

    def _render_cat_node(node, depth=0):
        cnt    = _count_items(node["id"])
        lvl    = ["一级","二级","三级"][min(depth,2)]
        indent = "　" * depth
        with st.expander(f"{indent}📁 {node['name']}（{lvl}）· {cnt} 个品种",
                         expanded=False):
            ec1, ec2, ec3, ec4 = st.columns([3, 1, 1, 1])
            with ec1:
                new_name = st.text_input("重命名", value=node["name"],
                                         key=f"wl_cat_rename_{node['id']}",
                                         label_visibility="collapsed")
            with ec2:
                if st.button("💾", key=f"wl_cat_save_name_{node['id']}", help="保存"):
                    if new_name.strip() and new_name.strip() != node["name"]:
                        storage.rename_wl_category(node["id"], new_name.strip())
                        st.toast(f"已重命名：{new_name.strip()}", icon="✏️")
            with ec3:
                if st.button("⬆️", key=f"wl_cat_up_{node['id']}", help="上移"):
                    storage.reorder_wl_category(node["id"], "up")
            with ec4:
                if st.button("🗑", key=f"wl_cat_del_{node['id']}", help="删除"):
                    st.session_state[f"_del_cat_confirm_{node['id']}"] = True

            if st.session_state.get(f"_del_cat_confirm_{node['id']}"):
                st.error(f"确认删除「{node['name']}」？品种将变为未分类。")
                dd1, dd2 = st.columns(2)
                with dd1:
                    if st.button("确认删除",
                                 key=f"wl_cat_del_yes_{node['id']}",
                                 type="primary"):
                        storage.delete_wl_category(node["id"])
                        st.session_state.pop(f"_del_cat_confirm_{node['id']}", None)
                        st.toast(f"已删除：{node['name']}", icon="🗑️")
                with dd2:
                    if st.button("取消", key=f"wl_cat_del_no_{node['id']}"):
                        st.session_state.pop(f"_del_cat_confirm_{node['id']}", None)

            if node.get("children"):
                for child in sorted(node["children"], key=lambda x: x.get("order",0)):
                    _render_cat_node(child, depth+1)

    for node in sorted(tree, key=lambda x: x.get("order", 0)):
        _render_cat_node(node)

    st.markdown("---")
    st.markdown("#### 📦 批量修改分类")
    all_items  = storage.load_watchlist()
    _b_names   = {i["ticker"]: f"{i['ticker']} {i.get('name','')}" for i in all_items}
    _bt_ids    = ["__UNCAT__"] + [c["id"] for c in cats]
    _bt_names  = {"__UNCAT__": "（未分类）"}
    _bt_names.update({c["id"]: c["name"] for c in cats})

    selected_tickers = st.multiselect(
        "选择品种", list(_b_names.keys()),
        format_func=lambda x, m=_b_names: m.get(x, x),
        key="cat_batch_tickers",
    )
    target_cat = st.selectbox("目标分类", _bt_ids,
                              format_func=lambda x, m=_bt_names: m.get(x, x),
                              key="cat_batch_target_id")

    if st.button("批量设置分类", key="cat_batch_save", type="primary"):
        if not selected_tickers:
            st.warning("请先选择品种")
        else:
            for tk in selected_tickers:
                storage.set_watchlist_item_category(
                    tk, None if target_cat == "__UNCAT__" else target_cat)
            st.toast(f"✅ 已为 {len(selected_tickers)} 个品种设置分类", icon="🏷️")


# ══════════════════════════════════════════════════════════════════════
def _render_archive():
    st.markdown("### 🗂️ 已删除存档")
    archive = storage.load_watchlist_archive()
    if not archive:
        st.info("存档为空。")
        return

    for item in reversed(archive):
        ticker = item["ticker"]
        name   = item.get("name","")
        del_at = item.get("deleted_at","")
        c1, c2, c3 = st.columns([4, 2, 2])
        with c1:
            st.markdown(
                f"**{name or ticker}**"
                + (f" `{ticker}`" if name else "")
                + f" <span style='color:#9ca3af;font-size:11px'>删除于 {del_at}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("♻️ 恢复", key=f"arc_restore_{ticker}"):
                storage.restore_from_archive(ticker)
                st.toast(f"已恢复：{ticker}", icon="♻️")
        with c3:
            if st.button("🗑 永久删除", key=f"arc_perm_{ticker}"):
                arch = storage.load_watchlist_archive()
                arch = [a for a in arch if a["ticker"].upper() != ticker.upper()]
                storage.save_watchlist_archive(arch)
                st.toast(f"已永久删除：{ticker}", icon="🗑️")


# ══════════════════════════════════════════════════════════════════════
def _render_backup():
    st.markdown("### 💾 备份与恢复")
    st.markdown("#### ⬇️ 导出备份")
    json_str = storage.export_watchlist_json()
    st.download_button(
        "⬇️ 下载 JSON 备份",
        data=json_str.encode("utf-8"),
        file_name=f"strx_watchlist_backup_{date.today().isoformat()}.json",
        mime="application/json",
        key="wl_export_json",
    )

    st.markdown("#### ⬆️ 导入备份")
    uploaded   = st.file_uploader("上传 JSON 备份文件", type=["json"], key="wl_import_file")
    merge_mode = st.checkbox("合并模式（保留现有数据）", value=True, key="wl_import_merge")
    if uploaded is not None:
        if st.button("导入", key="wl_import_btn", type="primary"):
            content = uploaded.read().decode("utf-8")
            ok, msg = storage.import_watchlist_json(content, merge=merge_mode)
            if ok:
                st.success(f"✅ {msg}")
                _cached_result_map.clear()
            else:
                st.error(f"❌ {msg}")

    st.markdown("#### 📁 本地自动备份")
    try:
        backups = storage.list_backups()
        if backups:
            for b in backups[:10]:
                bc1, bc2 = st.columns([5, 2])
                with bc1:
                    st.markdown(
                        f"<span style='font-size:12px'>{b['name']}</span>"
                        f"<span style='font-size:11px;color:#9ca3af;margin-left:8px'>"
                        f"{b.get('size_kb','?')} KB</span>",
                        unsafe_allow_html=True,
                    )
                with bc2:
                    if st.button("还原", key=f"wl_restore_{b['name']}"):
                        ok2, msg2 = storage.restore_backup(b["name"])
                        if ok2:
                            st.success(f"✅ {msg2}")
                            _cached_result_map.clear()
                        else:
                            st.error(f"❌ {msg2}")
        else:
            st.info("暂无本地备份记录。")
    except Exception as e:
        st.info(f"备份功能初始化中… ({e})")
