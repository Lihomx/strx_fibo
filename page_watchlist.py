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
import streamlit as st
import streamlit.components.v1 as _components
import storage

def _tv_link(ticker: str) -> str:
    try:
        from assets import tv_url as _tv_url
        return _tv_url(ticker)
    except Exception:
        return f"https://cn.tradingview.com/chart/?symbol={ticker}"


def _sina_link(ticker: str):
    """A股返回新浪财经链接，否则返回 None"""
    t = ticker.upper()
    if t.endswith(".SS"):
        code = t[:-3]
        return f"https://finance.sina.com.cn/realstock/company/sh{code}/nc.shtml"
    if t.endswith(".SZ"):
        code = t[:-3]
        return f"https://finance.sina.com.cn/realstock/company/sz{code}/nc.shtml"
    return None


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


# ══════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## ⭐ 自选收藏夹")

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
    # ── 待跳转 TV URL：rerun 后在页面顶部注入 window.open ──────────
    _pending = st.session_state.pop("_pending_tv_url", None)
    if _pending:
        import streamlit.components.v1 as _cv1
        _safe = _pending.replace('"', '%22').replace("'", "%27")
        _cv1.html(
            f'<script>window.open("{_safe}", "_blank");</script>',
            height=0,
        )

    items      = storage.load_watchlist()
    cats       = storage.load_wl_categories()
    result_map = _cached_result_map()

    _hl = st.session_state.pop("_wl_highlight", None)
    if _hl:
        _hl_name = next((i.get("name","") for i in items if i["ticker"]==_hl), _hl)
        st.success(f"⭐ 已收藏 **{_hl_name}**（`{_hl}`）")

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
    total  = len(items)
    done   = sum(1 for i in items if i["ticker"].upper() in viewed_set)
    pct    = int(done / total * 100) if total else 0
    bar_c  = "#22c55e" if pct == 100 else "#3b82f6"
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
    tc1, tc2, tc3, tc4 = st.columns([4, 2, 2, 2])
    with tc1:
        search = st.text_input("🔍", placeholder="搜索 Ticker / 名称…",
                               key="wl_search", label_visibility="collapsed")
    with tc2:
        sel_cat = "__ALL__"
        if cats:
            _cf_ids   = ["__ALL__", "__NONE__"]
            _cf_names = {"__ALL__": "📋 全部", "__NONE__": "❓ 未分类"}
            def _wc(nodes, depth=0):
                for n in sorted(nodes, key=lambda x: x.get("order",0)):
                    _cf_ids.append(n["id"])
                    _cf_names[n["id"]] = "  "*depth + n["name"]
                    if n.get("children"): _wc(n["children"], depth+1)
            _wc(storage.build_cat_tree(cats))
            sel_cat = st.selectbox("分类", _cf_ids,
                                   format_func=lambda x: _cf_names.get(x, x),
                                   key="wl_cat_filter_id",
                                   label_visibility="collapsed")
    with tc3:
        if st.button("⚙️ 管理分类", key="wl_go_cats_btn", use_container_width=True):
            st.session_state["_wl_go_cats"] = True
            st.rerun()
    with tc4:
        if st.button("🗑️ 清空", key="wl_clear_all", use_container_width=True):
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
    q = search.strip().upper()
    filtered = items
    if q:
        filtered = [i for i in items
                    if q in i["ticker"].upper() or q in i.get("name","").upper()]
    if cats and sel_cat == "__NONE__":
        _known = {c["id"] for c in cats} | {c["name"] for c in cats}
        filtered = [i for i in filtered
                    if not i.get("category_id") or i["category_id"] not in _known]
    elif cats and sel_cat not in ("__ALL__", None, ""):
        _valid  = {sel_cat} | storage._collect_descendants(cats, sel_cat)
        _vnames = {c["name"] for c in cats if c["id"] in _valid}
        filtered = [i for i in filtered
                    if i.get("category_id") in _valid or i.get("category_id") in _vnames]

    pinned  = [i for i in filtered if i.get("pinned")]
    others  = [i for i in filtered if not i.get("pinned")]
    display = pinned + others

    pinned_cnt = len(pinned)
    _stats_open = st.session_state.get("wl_stats_open", True)
    _stats_label = (
        f"共 {len(items)} 个 · 显示 {len(display)} 个"
        + (f" · 📌 {pinned_cnt} 个置顶" if pinned_cnt else "")
        + f" · ✅ {done}/{total} 今日已看"
        + (" ▲" if _stats_open else " ▼")
    )
    if st.button(_stats_label, key="wl_stats_toggle",
                 help="点击收起/展开统计"):
        st.session_state["wl_stats_open"] = not _stats_open
        st.rerun()

    if not display:
        st.info("没有符合条件的品种。")
        return

    if not st.session_state.get("wl_stats_open", True):
        st.info("点击上方统计栏展开品种列表。")
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
            f"{'✅' if all_done else '📁'} {gname}  ·  {g_done}/{g_total} 已看",
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
    st.download_button("⬇️ 导出收藏夹 CSV", csv,
                       file_name="strx_watchlist.csv", mime="text/csv",
                       key="wl_dl")


# ══════════════════════════════════════════════════════════════════════
def _render_item_row(item, result_map, cats, viewed_set):
    ticker  = item["ticker"]
    name    = item.get("name", "")
    pinned  = item.get("pinned", False)
    viewed  = ticker.upper() in viewed_set
    results = result_map.get(ticker.upper(), [])
    latest  = _latest_note(item)
    tv_link = _tv_link(ticker)
    sina_link = _sina_link(ticker)

    if viewed:
        row_style = "background:#f0fdf4;border:1px solid #bbf7d0;opacity:0.85;"
    elif pinned:
        row_style = "background:#fffbeb;border:1px solid #fde047;"
    else:
        row_style = "background:#ffffff;border:1px solid #e5e7eb;"

    display_name = _he(name or ticker)
    ticker_badge = (
        f' <span style="font-family:monospace;font-size:10px;color:#9ca3af;'
        f'background:#f3f4f6;padding:1px 5px;border-radius:3px">{_he(ticker)}</span>'
    ) if name else ""
    pin_icon  = "📌 " if pinned else ""
    view_icon = "✅ " if viewed else ""

    fibo_html = ""
    for r in results[:3]:
        tf      = r.get("timeframe","?")[:2]
        in_zone = r.get("in_zone", False)
        dist    = r.get("dist_pct")
        dist_s  = f"{dist:.0f}%" if dist is not None else "—"
        bg = "#fef9c3" if in_zone else "#f1f5f9"
        bd = "#fde047" if in_zone else "#e2e8f0"
        ico = "⚡" if in_zone else "·"
        fibo_html += (
            f'<span style="background:{bg};border:1px solid {bd};border-radius:5px;'
            f'padding:2px 6px;font-size:10px;white-space:nowrap;margin-right:3px">'
            f'<b style="color:#374151">{_he(tf)}</b> '
            f'<span style="color:#6b7280">{ico}{dist_s}</span></span>'
        )

    note_html = ""
    if latest:
        nt = latest.get("text","")
        nt_s = (nt[:50]+"…") if len(nt)>50 else nt
        note_html = (
            f'<div style="color:#ef4444;font-size:12px;font-weight:600;margin-top:3px">'
            f'📝 {_he(nt_s)}</div>'
        )

    st.markdown(
        f'<div style="{row_style}border-radius:8px;padding:8px 12px;margin-bottom:4px">'
        f'<div style="font-size:14px;font-weight:700;color:#111">'
        f'{pin_icon}{view_icon}{display_name}{ticker_badge}</div>'
        + (f'<div style="margin-top:4px">{fibo_html}</div>' if fibo_html else "")
        + note_html
        + '</div>',
        unsafe_allow_html=True,
    )

    if sina_link:
        bc1, bc2, bc3, bc4, bc5, bc6 = st.columns([1, 1, 1, 1, 1, 4])
    else:
        bc1, bc2, bc3, bc4, bc5 = st.columns([1, 1, 1, 1, 4])

    with bc1:
        if st.button("✅" if viewed else "👁️",
                     key=f"wl_v_{ticker}",
                     help="取消已看" if viewed else "标记已看"):
            if viewed: _unmark_viewed(ticker)
            else:      _mark_viewed(ticker)
            st.rerun()
    with bc2:
        if st.button("📈", key=f"wl_tv_{ticker}",
                     help="打开 TradingView（自动标记已看）"):
            _mark_viewed(ticker)
            st.session_state["_pending_tv_url"] = tv_link
            st.rerun()
    if sina_link:
        with bc3:
            if st.button("🏦", key=f"wl_sina_{ticker}", help="新浪财经"):
                st.session_state["_pending_tv_url"] = sina_link
                st.rerun()
        with bc4:
            if st.button("🔓" if pinned else "📌",
                         key=f"wl_pin_{ticker}", help="置顶/取消"):
                storage.toggle_pin_watchlist(ticker)
                st.rerun()
        with bc5:
            if st.button("🗑", key=f"wl_del_{ticker}", help="删除（移入存档）"):
                storage.remove_from_watchlist(ticker)
                st.toast(f"已移入存档：{ticker}", icon="🗂️")
                st.rerun()
        with bc6:
            _render_inline_controls(item, ticker, cats)
    else:
        with bc3:
            if st.button("🔓" if pinned else "📌",
                         key=f"wl_pin_{ticker}", help="置顶/取消"):
                storage.toggle_pin_watchlist(ticker)
                st.rerun()
        with bc4:
            if st.button("🗑", key=f"wl_del_{ticker}", help="删除（移入存档）"):
                storage.remove_from_watchlist(ticker)
                st.toast(f"已移入存档：{ticker}", icon="🗂️")
                st.rerun()
        with bc5:
            _render_inline_controls(item, ticker, cats)

    # ── 编辑全称 ────────────────────────────────────────────────
    if st.session_state.get(f"wl_edit_name_open_{ticker}"):
        en1, en2, en3 = st.columns([4, 1, 1])
        with en1:
            new_name_val = st.text_input(
                "编辑全称", value=name,
                key=f"wl_edit_name_val_{ticker}",
                label_visibility="collapsed",
                placeholder="输入品种全称…",
            )
        with en2:
            if st.button("💾", key=f"wl_edit_name_save_{ticker}", help="保存"):
                items_all = storage.load_watchlist()
                for it in items_all:
                    if it["ticker"].upper() == ticker.upper():
                        it["name"] = new_name_val.strip()
                        break
                storage.save_watchlist(items_all)
                st.session_state.pop(f"wl_edit_name_open_{ticker}", None)
                st.toast(f"已更新：{ticker} → {new_name_val.strip()}", icon="✏️")
                st.rerun()
        with en3:
            if st.button("✕", key=f"wl_edit_name_cancel_{ticker}", help="取消"):
                st.session_state.pop(f"wl_edit_name_open_{ticker}", None)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════
def _render_inline_controls(item, ticker, cats):
    cc = st.columns([1, 1, 1, 1, 5])
    with cc[0]:
        if st.button("🏷️", key=f"wl_cat_btn_{ticker}", help="设置分类"):
            k = f"wl_cat_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            if st.session_state[k]:
                st.session_state[f"wl_cat_init_{ticker}"] = True
            st.rerun()
    with cc[1]:
        if st.button("✏️", key=f"wl_note_btn_{ticker}", help="添加备注"):
            k = f"wl_note_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            st.rerun()
    with cc[2]:
        notes = _all_notes(item)
        if len(notes) >= 1:
            hist_open = st.session_state.get(f"wl_hist_open_{ticker}", True)
            btn_label = "📋▲" if hist_open else f"📋({len(notes)})"
            if st.button(btn_label, key=f"wl_hist_btn_{ticker}",
                         help="收起历史备注" if hist_open else f"展开历史备注({len(notes)})"):
                st.session_state[f"wl_hist_open_{ticker}"] = not hist_open
                st.rerun()
    with cc[3]:
        if st.button("🖊️", key=f"wl_edit_name_btn_{ticker}", help="编辑全称"):
            k = f"wl_edit_name_open_{ticker}"
            st.session_state[k] = not st.session_state.get(k, False)
            st.rerun()

    if st.session_state.get(f"wl_cat_open_{ticker}"):
        if not cats:
            st.warning("尚无分类，请先在「🏷️ 分类管理」标签创建。")
        else:
            _as_ids   = ["__UNCAT__"]
            _as_names = {"__UNCAT__": "（未分类）"}
            def _fill(nodes, depth=0):
                pfx = ("  "*depth+"└ ") if depth else ""
                for n in sorted(nodes, key=lambda x: x.get("order",0)):
                    _as_ids.append(n["id"])
                    _as_names[n["id"]] = pfx + n["name"]
                    if n.get("children"): _fill(n["children"], depth+1)
            _fill(storage.build_cat_tree(cats))

            _sel_key  = f"wl_cat_sel_{ticker}"
            _init_key = f"wl_cat_init_{ticker}"
            if st.session_state.pop(_init_key, False):
                cur = item.get("category_id")
                _default = "__UNCAT__"
                if cur:
                    if cur in _as_ids: _default = cur
                    else:
                        m = next((c["id"] for c in cats if c["name"]==cur), None)
                        if m: _default = m
                st.session_state[_sel_key] = _default
            if st.session_state.get(_sel_key) not in _as_ids:
                st.session_state[_sel_key] = "__UNCAT__"

            chosen = st.selectbox(
                f"📂 「{item.get('name') or ticker}」的分类",
                _as_ids, format_func=lambda x: _as_names.get(x, x),
                key=_sel_key,
            )
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("💾 保存分类", key=f"wl_cat_save_{ticker}", type="primary"):
                    storage.set_watchlist_item_category(
                        ticker, None if chosen=="__UNCAT__" else chosen)
                    st.session_state.pop(f"wl_cat_open_{ticker}", None)
                    st.session_state.pop(_sel_key, None)
                    st.toast(f"已设置：{_as_names.get(chosen,'')}", icon="🏷️")
                    st.rerun()
            with sc2:
                if st.button("取消", key=f"wl_cat_cancel_{ticker}"):
                    st.session_state.pop(f"wl_cat_open_{ticker}", None)
                    st.session_state.pop(_sel_key, None)
                    st.rerun()

    if st.session_state.get(f"wl_note_open_{ticker}"):
        new_text = st.text_input("备注内容 *", key=f"wl_note_txt_{ticker}",
                                 placeholder="输入本次备注…")
        new_img  = st.text_input("图片链接（选填）", key=f"wl_note_img_{ticker}",
                                 placeholder="https://...").strip()
        sn1, sn2 = st.columns(2)
        with sn1:
            if st.button("💾 保存备注", key=f"wl_note_save_{ticker}", type="primary"):
                if not new_text.strip():
                    st.warning("备注不能为空")
                else:
                    storage.add_watchlist_note(ticker, new_text.strip(), new_img)
                    st.session_state.pop(f"wl_note_open_{ticker}", None)
                    st.toast(f"备注已保存：{ticker}", icon="📝")
                    st.rerun()
        with sn2:
            if st.button("取消", key=f"wl_note_cancel_{ticker}"):
                st.session_state.pop(f"wl_note_open_{ticker}", None)
                st.rerun()

    if st.session_state.get(f"wl_hist_open_{ticker}", True):
        notes = _all_notes(item)
        if notes:
            for n in reversed(notes):
                img_url_n = n.get("img_url", "")
                st.markdown(
                    f'<div style="border-left:2px solid #e5e7eb;padding:5px 10px;'
                    f'margin:3px 0;font-size:12px;">'
                    f'<span style="color:#9ca3af">{n.get("ts","")}</span>&nbsp;&nbsp;'
                    f'<span style="color:#374151">{_he(str(n["text"]))}</span>'
                    + (f'&nbsp;<a href="{_he(img_url_n)}" target="_blank" style="font-size:11px;color:#3b82f6">🖼️图</a>' if img_url_n else "")
                    + '</div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════
def _render_add_form():
    c1, c2 = st.columns([2, 2])
    with c1:
        new_ticker = st.text_input(
            "Ticker 代码 *", placeholder="例: AAPL  600519.SS",
            key="wl_new_ticker",
        ).strip().upper()
    with c2:
        new_name = st.text_input(
            "品种全称（可选）", placeholder="例: 苹果公司",
            key="wl_new_name",
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
                for k in ["wl_new_ticker","wl_new_name",
                          "wl_new_note_text","wl_new_img_url"]:
                    st.session_state.pop(k, None)
                _cached_result_map.clear()
                st.rerun()
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
            st.rerun()


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
            def _fill_par(nodes, depth=0):
                pfx = ("  "*depth+"└ ") if depth else ""
                for n in sorted(nodes, key=lambda x: x.get("order",0)):
                    _par_ids.append(n["id"])
                    _par_names[n["id"]] = pfx + n["name"]
                    if n.get("children") and depth < 1:
                        _fill_par(n["children"], depth+1)
            _fill_par(storage.build_cat_tree(cats))
            parent_id = st.selectbox("父级分类（可选）", _par_ids,
                format_func=lambda x: _par_names.get(x, x),
                key="wl_new_cat_parent")
        if st.button("➕ 创建分类", key="wl_cat_create", type="primary"):
            if not new_cat_name.strip():
                st.warning("分类名称不能为空")
            else:
                _par = None if parent_id == "__ROOT__" else parent_id
                storage.add_wl_category(new_cat_name.strip(), parent_id=_par)
                st.session_state.pop("wl_new_cat_name", None)
                st.toast(f"✅ 已创建：{new_cat_name.strip()}", icon="🏷️")
                st.rerun()

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
        cnt   = _count_items(node["id"])
        lvl   = ["一级","二级","三级"][min(depth,2)]
        indent = "　" * depth
        with st.expander(f"{indent}📁 {node['name']}{lvl}{cnt} 个品种",
                         expanded=False):
            ec1, ec2, ec3, ec4 = st.columns([3, 1, 1, 1])
            with ec1:
                new_name = st.text_input("重命名", value=node["name"],
                    key=f"wl_cat_rename_{node['id']}",
                    label_visibility="collapsed")
            with ec2:
                if st.button("💾", key=f"wl_cat_save_name_{node['id']}",
                             help="保存"):
                    if new_name.strip() and new_name.strip() != node["name"]:
                        storage.rename_wl_category(node["id"], new_name.strip())
                        st.toast(f"已重命名：{new_name.strip()}", icon="✏️")
                        st.rerun()
            with ec3:
                if st.button("⬆️", key=f"wl_cat_up_{node['id']}", help="上移"):
                    storage.move_wl_category(node["id"], -1)
                    st.rerun()
            with ec4:
                if st.button("🗑", key=f"wl_cat_del_{node['id']}", help="删除"):
                    st.session_state[f"_del_cat_confirm_{node['id']}"] = True
                    st.rerun()

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
                        st.rerun()
                with dd2:
                    if st.button("取消", key=f"wl_cat_del_no_{node['id']}"):
                        st.session_state.pop(f"_del_cat_confirm_{node['id']}", None)
                        st.rerun()

            if node.get("children"):
                for child in sorted(node["children"],
                                    key=lambda x: x.get("order",0)):
                    _render_cat_node(child, depth+1)

    for node in sorted(tree, key=lambda x: x.get("order", 0)):
        _render_cat_node(node)

    st.markdown("---")
    st.markdown("#### 📦 批量修改分类")
    all_items = storage.load_watchlist()
    _b_names  = {i["ticker"]: f"{i['ticker']} {i.get('name','')}" for i in all_items}
    _bt_ids   = ["__UNCAT__"] + [c["id"] for c in cats]
    _bt_names = {"__UNCAT__": "（未分类）"}
    _bt_names.update({c["id"]: c["name"] for c in cats})

    selected_tickers = st.multiselect(
        "选择品种", list(_b_names.keys()),
        format_func=lambda x: _b_names.get(x, x),
        key="cat_batch_tickers",
    )
    target_cat = st.selectbox("目标分类", _bt_ids,
        format_func=lambda x: _bt_names.get(x, x),
        key="cat_batch_target_id")
    if st.button("批量设置分类", key="cat_batch_save", type="primary"):
        if not selected_tickers:
            st.warning("请先选择品种")
        else:
            for tk in selected_tickers:
                storage.set_watchlist_item_category(
                    tk, None if target_cat == "__UNCAT__" else target_cat)
            st.toast(f"✅ 已为 {len(selected_tickers)} 个品种设置分类", icon="🏷️")
            st.rerun()


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
                + f"  <span style='color:#9ca3af;font-size:11px'>删除于 {del_at}</span>",
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("♻️ 恢复", key=f"arc_restore_{ticker}"):
                storage.restore_from_archive(ticker)
                st.toast(f"已恢复：{ticker}", icon="♻️")
                st.rerun()
        with c3:
            if st.button("🗑 永久删除", key=f"arc_perm_{ticker}"):
                arch = storage.load_watchlist_archive()
                arch = [a for a in arch if a["ticker"].upper() != ticker.upper()]
                storage.save_watchlist_archive(arch)
                st.toast(f"已永久删除：{ticker}", icon="🗑️")
                st.rerun()


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
    uploaded = st.file_uploader("上传 JSON 备份文件", type=["json"],
                                key="wl_import_file")
    merge_mode = st.checkbox("合并模式（保留现有数据）",
                             value=True, key="wl_import_merge")
    if uploaded is not None:
        if st.button("导入", key="wl_import_btn", type="primary"):
            content = uploaded.read().decode("utf-8")
            ok, msg = storage.import_watchlist_json(content, merge=merge_mode)
            if ok:
                st.success(f"✅ {msg}")
                _cached_result_map.clear()
                st.rerun()
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
                            st.rerun()
                        else:
                            st.error(f"❌ {msg2}")
        else:
            st.info("暂无本地备份记录。")
    except Exception as e:
        st.info(f"备份功能初始化中… ({e})")
