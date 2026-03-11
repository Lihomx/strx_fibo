"""
page_watchlist.py — 自选收藏夹 v4
════════════════════════════════════════════════════════════════
核心升级（v4）：
1. 速度：@st.cache_data 缓存 result_map（扫描结果），消除重复读文件
2. 速度：_fast_patch() 只更新单条记录字段，不重写整个收藏夹文件
3. 已查看标记：每个品种一键"👁️已看"，今日会话内保留，页面进度条展示
4. 视图模式：📋分类看板（横向3列卡片）+ 📄列表（原竖排），一键切换
5. 今日进度条：顶部显示"今日已看 N/41"，一眼知道还剩多少
════════════════════════════════════════════════════════════════
"""

from datetime import datetime
import streamlit as st
import pandas as pd

import storage
from assets import tv_url as _tv_url
from html import escape as _he


# ════════════════════════════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════════════════════════════
_TODAY = datetime.now().strftime("%Y-%m-%d")
_SESSION_VIEWED_KEY = f"wl_viewed_{_TODAY}"   # 今日已查看 ticker set


# ════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════
def _tv_link(ticker: str) -> str:
    try:
        return _tv_url(ticker)
    except Exception:
        return f"https://cn.tradingview.com/chart/?symbol={ticker}"


def _thumb_html(img_url: str, max_w: int = 120) -> str:
    if not img_url:
        return ""
    url = str(img_url).strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        return ""
    ue = _he(url)
    return (
        f'<a href="{ue}" target="_blank" title="点击查看大图">'
        f'<img src="{ue}" style="max-width:{max_w}px;max-height:90px;'
        f'border-radius:6px;border:1px solid #e5e7eb;object-fit:cover;'
        f'vertical-align:middle;margin-top:4px" '
        f'onerror="this.style.display=\'none\'">'
        f'</a>'
    )


def _latest_note(item: dict) -> dict | None:
    notes = item.get("notes", [])
    if not notes:
        old = item.get("note", "")
        if old:
            return {"text": old, "img_url": "", "ts": item.get("added_at", "")}
        return None
    return notes[-1]


def _all_notes(item: dict) -> list:
    notes = item.get("notes", [])
    if not notes:
        old = item.get("note", "")
        if old:
            return [{"text": old, "img_url": "", "ts": item.get("added_at", "")}]
        return []
    return notes


# ════════════════════════════════════════════════════════════════════
# 速度优化：缓存扫描结果 map（TTL 60s）
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
# JS 辅助：点击 TV 按钮 → 标记已看 + 打开新标签页
# ════════════════════════════════════════════════════════════════════
def _open_tv_and_mark(ticker: str, url: str, btn_key: str) -> bool:
    """渲染一个普通按钮；点击后标记已看，并用 JS 打开 TradingView 链接。
    返回 True 表示本轮被点击。"""
    import streamlit.components.v1 as _stc
    clicked = st.button("📈", key=btn_key, help=f"在 TradingView 查看 {ticker}")
    if clicked:
        _mark_viewed(ticker)
        # 通过 iframe 注入 JS 打开新标签（Streamlit 唯一可行方式）
        _stc.html(
            f"<script>window.open({repr(url)}, '_blank');</script>",
            height=0,
        )
    return clicked

@st.cache_data(ttl=60, show_spinner=False)
def _cached_result_map() -> dict:
    result_map: dict = {}
    try:
        for r in storage.load_latest_results():
            tk = r.get("ticker", "").upper()
            result_map.setdefault(tk, []).append(r)
    except Exception:
        pass
    return result_map


# ════════════════════════════════════════════════════════════════════
# 速度优化：单条记录快速写盘
# ════════════════════════════════════════════════════════════════════
def _fast_patch(ticker: str, **fields) -> bool:
    ticker = ticker.strip().upper()
    items  = storage.load_watchlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            for k, v in fields.items():
                item[k] = v
            return storage.save_watchlist(items)
    return False


# ════════════════════════════════════════════════════════════════════
# 今日已查看状态
# ════════════════════════════════════════════════════════════════════
def _get_viewed() -> set:
    return st.session_state.get(_SESSION_VIEWED_KEY, set())


def _mark_viewed(ticker: str):
    v = _get_viewed(); v.add(ticker.upper())
    st.session_state[_SESSION_VIEWED_KEY] = v


def _unmark_viewed(ticker: str):
    v = _get_viewed(); v.discard(ticker.upper())
    st.session_state[_SESSION_VIEWED_KEY] = v


def _is_viewed(ticker: str) -> bool:
    return ticker.upper() in _get_viewed()


# ════════════════════════════════════════════════════════════════════
# 主渲染入口
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## ⭐ 自选收藏夹")

    _tab_default = 0
    if st.session_state.pop("_wl_go_cats", False) or \
       st.session_state.pop("_wl_tab", None) == "cats":
        _tab_default = 1

    tab_main, tab_cats, tab_archive, tab_backup = st.tabs(
        ["⭐ 当前收藏", "🏷️ 分类管理", "🗂️ 已删除存档", "💾 备份与恢复"]
    )
    with tab_main:    _render_main()
    with tab_cats:    _render_categories()
    with tab_archive: _render_archive()
    with tab_backup:  _render_backup()


# ════════════════════════════════════════════════════════════════════
# 当前收藏主页
# ════════════════════════════════════════════════════════════════════
def _render_main():
    # ── 拖拽结果即时保存（query_params 传入） ────────────────────────
    _drag_param = st.query_params.get("wl_drag")
    if _drag_param:
        import json as _json
        try:
            _drag_result = _json.loads(_drag_param)
            _all_wl = storage.load_watchlist()
            _changed = 0
            for _wi in _all_wl:
                _tk  = _wi["ticker"].upper()
                _new = _drag_result.get(_tk)
                if _new is not None:
                    _new_cat = None if _new == "__NONE__" else _new
                    if _wi.get("category_id") != _new_cat:
                        _wi["category_id"] = _new_cat
                        _changed += 1
            if _changed:
                storage.save_watchlist(_all_wl)
                st.toast(f"✅ 已保存 {_changed} 个品种的分类", icon="🎉")
        except Exception as _e:
            st.warning(f"拖拽保存失败：{_e}")
        st.query_params.clear()
        st.rerun()

    items      = storage.load_watchlist()
    cats       = storage.load_wl_categories()
    result_map = _cached_result_map()

    # 来自扫描页高亮
    _hl = st.session_state.pop("_wl_highlight", None)
    if _hl:
        _hl_name = next((i.get("name","") for i in items if i["ticker"]==_hl), _hl)
        st.success(f"⭐ 已收藏 **{_hl_name}**（`{_hl}`）")
        st.session_state["_hl_ticker"] = _hl

    # 添加新品种
    with st.expander("➕ 添加新品种", expanded=len(items) == 0):
        _render_add_form()

    items = storage.load_watchlist()
    if not items:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;color:#9ca3af;">
          <div style="font-size:48px">⭐</div>
          <div style="font-size:16px;font-weight:600;margin:12px 0 6px;color:#374151">收藏夹为空</div>
          <div style="font-size:13px">点击上方「添加新品种」开始收藏</div>
        </div>""", unsafe_allow_html=True)
        return

    # 今日进度条
    _render_today_progress(items)

    # 工具栏
    col_l, col_m, col_r = st.columns([4, 3, 2])
    with col_l:
        search = st.text_input(
            "🔍", placeholder="搜索 Ticker / 名称…",
            key="wl_search", label_visibility="collapsed"
        )
    with col_m:
        view_mode = st.radio(
            "视图", ["📋 分类看板", "📄 列表"],
            key="wl_view_mode", horizontal=True,
            label_visibility="collapsed",
        )
    with col_r:
        if st.button("🗑️ 清空", key="wl_clear_all"):
            st.session_state["wl_confirm_clear"] = True

    if st.session_state.get("wl_confirm_clear"):
        st.warning("⚠️ 确定清空所有收藏？（将移入存档，可恢复）")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("确认清空", key="wl_clear_yes", type="primary"):
                for item in items:
                    storage.remove_from_watchlist(item["ticker"])
                st.session_state["wl_confirm_clear"] = False
                st.rerun()
        with cc2:
            if st.button("取消", key="wl_clear_no"):
                st.session_state["wl_confirm_clear"] = False
                st.rerun()

    # 分类筛选
    _sel_cat_id, _cf_names = _render_cat_filter(cats)

    # 过滤
    q = search.strip().upper()
    display_items = items
    if q:
        display_items = [
            i for i in items
            if q in i["ticker"].upper() or q in i.get("name","").upper()
        ]
    if _sel_cat_id == "__NONE__":
        _known_ids   = {c["id"]   for c in cats}
        _known_names = {c["name"] for c in cats}
        display_items = [
            i for i in display_items
            if (not i.get("category_id"))
            or (i["category_id"] not in _known_ids
                and i["category_id"] not in _known_names)
        ]
    elif _sel_cat_id is not None:
        _valid_ids   = {_sel_cat_id} | storage._collect_descendants(cats, _sel_cat_id)
        _valid_names = {c["name"] for c in cats if c["id"] in _valid_ids}
        display_items = [
            i for i in display_items
            if i.get("category_id") in _valid_ids
            or i.get("category_id") in _valid_names
        ]

    # 排序：置顶 > 未查看 > 已查看
    display_items = sorted(
        display_items,
        key=lambda x: (
            0 if x.get("pinned") else 1,
            1 if _is_viewed(x["ticker"]) else 0,
        )
    )

    pinned_cnt = sum(1 for i in display_items if i.get("pinned"))
    viewed_cnt = sum(1 for i in display_items if _is_viewed(i["ticker"]))

    if _sel_cat_id == "__NONE__":
        _cat_disp = " · 🏷️ 未分类"
    elif _sel_cat_id and cats:
        _raw   = _cf_names.get(_sel_cat_id,"")
        _clean = _raw.replace("🏷️ ","").replace("  └ ","").strip()
        _cat_disp = f" · 🏷️ {_clean}"
    else:
        _cat_disp = ""

    st.markdown(
        f"<div style='color:#6b7280;font-size:12px;margin-bottom:6px'>"
        f"共 {len(items)} 个品种 · 显示 {len(display_items)} 个"
        + (f" · 📌 {pinned_cnt} 个置顶" if pinned_cnt else "")
        + (f" · ✅ {viewed_cnt} 个已看" if viewed_cnt else "")
        + _cat_disp + "</div>",
        unsafe_allow_html=True,
    )

    # 渲染
    if "看板" in view_mode:
        _render_kanban(display_items, result_map, cats)
    else:
        for idx, item in enumerate(display_items):
            _render_card(item, idx, result_map, cats)

    # 导出
    st.markdown("---")
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        rows = []
        for item in items:
            tk     = item["ticker"]
            latest = _latest_note(item)
            rows.append({
                "ticker":      tk, "name": item.get("name",""),
                "latest_note": latest["text"] if latest else "",
                "added_at":    item.get("added_at",""),
                "pinned":      item.get("pinned", False),
                "in_zone_any": any(r.get("in_zone") for r in result_map.get(tk,[])),
            })
        csv = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 导出收藏夹 CSV", csv,
                           file_name="strx_watchlist.csv", mime="text/csv",
                           key="wl_dl")
    with exp_col2:
        st.text_area("Ticker 列表（可复制）",
                     value="\n".join(i["ticker"] for i in items),
                     height=80, key="wl_ticker_list")


# ════════════════════════════════════════════════════════════════════
# 今日进度条
# ════════════════════════════════════════════════════════════════════
def _render_today_progress(items: list):
    total    = len(items)
    viewed   = _get_viewed()
    done_cnt = sum(1 for i in items if i["ticker"].upper() in viewed)
    pct      = done_cnt / total if total else 0
    bar_w    = max(int(pct * 100), 1)

    if pct >= 1.0:
        bar_color = "#22c55e"
        msg = "🎉 今日全部查看完毕！"
    elif pct >= 0.5:
        bar_color = "#f59e0b"
        msg = f"📊 今日已看 **{done_cnt}** / {total} 个，还剩 {total-done_cnt} 个"
    else:
        bar_color = "#3b82f6"
        msg = f"📊 今日已看 **{done_cnt}** / {total} 个品种"

    c1, c2 = st.columns([7, 2])
    with c1:
        _prog_html = (
            '<div style="margin:4px 0 10px">'
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">'
            f'<span style="font-size:13px;color:#374151">{msg}</span>'
            f'<span style="font-size:12px;color:#9ca3af">{int(pct*100)}%</span>'
            '</div>'
            '<div style="background:#e5e7eb;border-radius:99px;height:8px;overflow:hidden">'
            f'<div style="background:{bar_color};width:{bar_w}%;height:100%;border-radius:99px;transition:width 0.4s ease"></div>'
            '</div></div>'
        )
        st.markdown(_prog_html, unsafe_allow_html=True)
    with c2:
        if done_cnt > 0:
            if st.button("🔄 重置今日进度", key="wl_reset_viewed"):
                st.session_state[_SESSION_VIEWED_KEY] = set()
                st.rerun()


# ════════════════════════════════════════════════════════════════════
# 分类筛选器
# ════════════════════════════════════════════════════════════════════
def _render_cat_filter(cats: list):
    if not cats:
        st.markdown(
            '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
            'padding:8px 14px;margin:4px 0 8px;font-size:13px;color:#15803d">'
            '🏷️ <b>尚未创建分类</b> — 前往「分类管理」标签页创建分类目录</div>',
            unsafe_allow_html=True,
        )
        return None, {}

    _cf_ids   = ["__ALL__", "__NONE__"]
    _cf_names = {"__ALL__": "📋 全部", "__NONE__": "❓ 未分类"}

    def _walk(nodes, depth=0):
        prefix = "  " * depth + ("└ " if depth > 0 else "")
        for node in sorted(nodes, key=lambda x: x.get("order", 0)):
            _cf_ids.append(node["id"])
            _cf_names[node["id"]] = f"🏷️ {prefix}{node['name']}"
            if node.get("children"):
                _walk(node["children"], depth + 1)
    _walk(storage.build_cat_tree(cats))

    _col_catsel, _col_catmgr = st.columns([5, 2])
    with _col_catsel:
        _sel = st.selectbox(
            "🏷️ 按分类筛选", options=_cf_ids,
            format_func=lambda x: _cf_names.get(x, str(x)),
            key="wl_cat_filter_id",
        )
    with _col_catmgr:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("⚙️ 管理分类", key="wl_go_cats", use_container_width=True):
            st.session_state["_wl_tab"] = "cats"
            st.rerun()

    return (None if _sel == "__ALL__" else _sel), _cf_names


# ════════════════════════════════════════════════════════════════════
# 添加品种表单
# ════════════════════════════════════════════════════════════════════
def _render_add_form():
    c1, c2 = st.columns([2, 2])
    with c1:
        new_ticker = st.text_input(
            "Ticker 代码 *", placeholder="如: AAPL  600519.SS  0700.HK",
            key="wl_new_ticker",
        ).strip().upper()
    with c2:
        new_name = st.text_input(
            "品种全称（可选）", placeholder="如: 苹果公司 / 贵州茅台",
            key="wl_new_name",
        )
    st.markdown(
        '<span style="color:#ef4444;font-weight:700;font-size:13px">📝 备注 *（必填）</span>',
        unsafe_allow_html=True,
    )
    note_text = st.text_input(
        "备注", placeholder="如: 关注 0.618 支撑，等待回踩确认",
        key="wl_new_note_text",
        label_visibility="collapsed",
    )
    img_url = st.text_input(
        "🖼️ 图片链接（选填）", placeholder="https://...图片URL",
        key="wl_new_img_url",
    ).strip()
    if img_url:
        st.markdown(_thumb_html(img_url, 200), unsafe_allow_html=True)

    if st.button("➕ 添加到收藏夹", key="wl_add_btn", type="primary"):
        if not new_ticker:
            st.warning("请输入 Ticker 代码")
        elif not note_text.strip():
            st.warning("备注为必填项")
        else:
            ok = storage.add_to_watchlist(new_ticker, new_name, note_text.strip(), img_url)
            if ok:
                # 清空所有输入字段（通过删除 session_state 中对应的 key）
                for _k in ["wl_new_ticker", "wl_new_name", "wl_new_note_text", "wl_new_img_url"]:
                    st.session_state.pop(_k, None)
                st.success(f"✅ 已添加 {new_ticker}")
                st.rerun()
            else:
                st.warning(f"⚠️ {new_ticker} 已在收藏夹中")

    st.markdown("---")
    st.markdown("**批量导入**（每行一个 Ticker，可附简称，用空格分隔）")
    bulk_text = st.text_area(
        "批量输入", placeholder="AAPL 苹果\nTSLA 特斯拉\n600519.SS 茅台",
        height=90, key="wl_bulk", label_visibility="collapsed",
    )
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
            st.info(f"跳过（重复/无效）：{', '.join(skipped)}")
        if added:
            st.rerun()


# ════════════════════════════════════════════════════════════════════
# 📋 分类看板视图
# 每个分类一个区块，内部品种3列网格，附进度条
# ════════════════════════════════════════════════════════════════════
def _render_kanban(items: list, result_map: dict, cats: list):
    """
    收藏页看板视图 — 全HTML拖拽实现。
    拖完后通过 window.location 写入 ?wl_drag=... 触发 Streamlit rerun 保存。
    """
    import json
    import streamlit.components.v1 as _stc

    # ── 构建分类列顺序 ────────────────────────────────────────────
    tree = storage.build_cat_tree(cats)
    cat_name_map: dict = {}
    col_order = []

    def _collect(nodes):
        for n in sorted(nodes, key=lambda x: x.get("order", 0)):
            cat_name_map[n["id"]] = n["name"]
            col_order.append({"id": n["id"], "name": n["name"]})
            if n.get("children"):
                _collect(n["children"])
    _collect(tree)
    col_order.append({"id": "__NONE__", "name": "❓ 未分类"})

    # ── 分桶（所有 items，不仅 display_items 以保持完整） ─────────
    all_items = storage.load_watchlist()
    viewed_set = _get_viewed()

    board: dict = {col["id"]: [] for col in col_order}
    for item in all_items:
        cid = item.get("category_id") or "__NONE__"
        if cid != "__NONE__" and cid not in cat_name_map:
            matched = next((c["id"] for c in cats if c["name"] == cid), None)
            cid = matched if matched else "__NONE__"
        if cid not in board:
            cid = "__NONE__"
        latest_note = ""
        notes = item.get("notes") or []
        if notes:
            t = notes[-1].get("text","") if isinstance(notes[-1], dict) else str(notes[-1])
            latest_note = (t[:30]+"…") if len(t)>30 else t
        # fibo 徽章数据
        res_list = result_map.get(item["ticker"], [])
        fibo_badges = []
        for r in res_list[:3]:
            fibo_badges.append({
                "tf": r.get("timeframe","?")[:1],
                "in_zone": r.get("in_zone", False),
                "dist": f"{r['dist_pct']:.0f}%" if r.get("dist_pct") is not None else "—",
            })
        board[cid].append({
            "ticker":  item["ticker"],
            "name":    item.get("name",""),
            "pinned":  item.get("pinned", False),
            "viewed":  item["ticker"].upper() in viewed_set,
            "note":    latest_note,
            "fibo":    fibo_badges,
        })

    board_json   = json.dumps(board,     ensure_ascii=False)
    columns_json = json.dumps(col_order, ensure_ascii=False)

    # ── 计算动态高度 ──────────────────────────────────────────────
    max_col = max((len(v) for v in board.values()), default=1)
    board_height = max(480, max_col * 82 + 160)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#f1f5f9;padding:10px 8px 60px;}}
.board{{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;align-items:flex-start;}}
.col{{flex:0 0 152px;background:#fff;border-radius:10px;
  border:1.5px solid #e2e8f0;padding:6px 6px 8px;min-height:100px;
  transition:border-color .15s,background .15s;}}
.col.over{{border-color:#3b82f6!important;background:#eff6ff!important;}}
.col-hd{{font-size:10px;font-weight:700;color:#0f172a;padding:3px 4px 5px;
  border-bottom:1.5px solid #e2e8f0;margin-bottom:5px;
  display:flex;justify-content:space-between;align-items:center;
  line-height:1.3;gap:4px;}}
.col-hd span{{flex:1;word-break:break-all;}}
.cnt{{background:#e0e7ff;color:#3730a3;font-size:9px;
  padding:1px 5px;border-radius:7px;font-weight:700;white-space:nowrap;}}
.card{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;
  padding:5px 7px;margin-bottom:4px;cursor:grab;user-select:none;
  transition:box-shadow .12s,opacity .12s;}}
.card:hover{{box-shadow:0 2px 8px rgba(0,0,0,.12);border-color:#93c5fd;}}
.card.dragging{{opacity:.35;cursor:grabbing;}}
.card.pinned{{background:#fffbeb;border-color:#fde047;}}
.card.viewed{{background:#f0fdf4;border-color:#86efac;opacity:.82;}}
.cn{{font-size:11px;font-weight:700;color:#0f172a;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:128px;}}
.tk{{font-size:9px;color:#94a3b8;font-family:monospace;margin-bottom:3px;}}
.fibs{{display:flex;gap:2px;flex-wrap:wrap;margin-bottom:3px;}}
.fb{{font-size:9px;padding:1px 4px;border-radius:4px;text-align:center;line-height:1.4;}}
.fb.z{{background:#fef9c3;border:1px solid #fde047;color:#78350f;}}
.fb.n{{background:#f1f5f9;border:1px solid #e2e8f0;color:#475569;}}
.nt{{font-size:10px;color:#ef4444;font-weight:700;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:132px;}}
.nt.empty{{color:#d1d5db;font-style:italic;font-weight:400;}}
.ph{{border:2px dashed #93c5fd;border-radius:7px;height:34px;
  background:#eff6ff;margin-bottom:4px;}}
.bar{{position:fixed;bottom:0;left:0;right:0;background:#fff;
  border-top:1px solid #e2e8f0;padding:8px 12px;
  display:flex;align-items:center;gap:8px;z-index:99;}}
.btn-save{{background:#2563eb;color:#fff;border:none;border-radius:7px;
  padding:6px 18px;font-size:12px;font-weight:700;cursor:pointer;}}
.btn-save:hover{{background:#1d4ed8;}}
.btn-save:disabled{{background:#93c5fd;cursor:not-allowed;}}
.btn-reset{{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;
  border-radius:7px;padding:6px 12px;font-size:11px;cursor:pointer;}}
.badge{{background:#fef9c3;color:#92400e;font-size:10px;font-weight:700;
  padding:2px 8px;border-radius:7px;display:none;}}
.badge.on{{display:inline-block;}}
.hint{{font-size:10px;color:#94a3b8;margin-left:auto;}}
</style></head>
<body>
<div class="board" id="board"></div>
<div class="bar">
  <button class="btn-save" id="btnSave" onclick="doSave()" disabled>💾 保存分类</button>
  <button class="btn-reset" onclick="doReset()">↩ 还原</button>
  <span class="badge" id="badge"></span>
  <span class="hint">拖动卡片更换分类 · 保存后页面自动刷新</span>
</div>
<script>
const COLS  = {columns_json};
const ORIG  = {board_json};
let   STATE = JSON.parse(JSON.stringify(ORIG));
let   moved = 0;
let   dragging = null, fromCol = null;

function render(){{
  const bd = document.getElementById('board');
  bd.innerHTML='';
  COLS.forEach(col=>{{
    const cards = STATE[col.id]||[];
    const el = document.createElement('div');
    el.className='col'; el.dataset.cid=col.id;
    el.innerHTML=
      '<div class="col-hd"><span>'+col.name+'</span>'+
      '<span class="cnt">'+cards.length+'</span></div>';
    cards.forEach(c=>{{
      const d=document.createElement('div');
      let cls='card';
      if(c.pinned) cls+=' pinned';
      if(c.viewed) cls+=' viewed';
      d.className=cls; d.draggable=true;
      d.dataset.ticker=c.ticker; d.dataset.cid=col.id;
      // fibo badges
      let fibs='';
      if(c.fibo&&c.fibo.length){{
        c.fibo.forEach(f=>{{
          fibs+='<span class="fb '+(f.in_zone?'z':'n')+'">'+
            '<b>'+f.tf+'</b> '+f.dist+'</span>';
        }});
      }}
      const nt = c.note
        ? '<div class="nt">'+esc(c.note)+'</div>'
        : '<div class="nt empty">暂无备注</div>';
      d.innerHTML=
        '<div class="cn">'+(c.viewed?'✅ ':c.pinned?'📌 ':'')+esc(c.name||c.ticker)+'</div>'+
        '<div class="tk">'+esc(c.ticker)+'</div>'+
        (fibs?'<div class="fibs">'+fibs+'</div>':'')+
        nt;
      d.addEventListener('dragstart',e=>{{
        dragging=c.ticker; fromCol=col.id;
        setTimeout(()=>d.classList.add('dragging'),0);
        e.dataTransfer.effectAllowed='move';
      }});
      d.addEventListener('dragend',()=>{{
        d.classList.remove('dragging');
        document.querySelectorAll('.ph').forEach(p=>p.remove());
        document.querySelectorAll('.col').forEach(c=>c.classList.remove('over'));
      }});
      el.appendChild(d);
    }});
    el.addEventListener('dragover',e=>{{
      e.preventDefault();
      el.classList.add('over');
      if(!el.querySelector('.ph')){{
        const ph=document.createElement('div');
        ph.className='ph'; el.appendChild(ph);
      }}
    }});
    el.addEventListener('dragleave',e=>{{
      if(!el.contains(e.relatedTarget)){{
        el.classList.remove('over');
        el.querySelectorAll('.ph').forEach(p=>p.remove());
      }}
    }});
    el.addEventListener('drop',e=>{{
      e.preventDefault();
      el.classList.remove('over');
      el.querySelectorAll('.ph').forEach(p=>p.remove());
      const toCid=el.dataset.cid;
      if(!dragging||toCid===fromCol)return;
      STATE[fromCol]=STATE[fromCol].filter(c=>c.ticker!==dragging);
      let item=null;
      for(const cid in ORIG){{
        const f=ORIG[cid].find(c=>c.ticker===dragging);
        if(f){{item=f;break;}}
      }}
      if(item&&!(STATE[toCid]||[]).find(c=>c.ticker===dragging)){{
        if(!STATE[toCid]) STATE[toCid]=[];
        STATE[toCid].push(item);
      }}
      dragging=null; fromCol=null;
      // count moved
      moved=0;
      COLS.forEach(col=>{{
        const os=new Set((ORIG[col.id]||[]).map(c=>c.ticker));
        (STATE[col.id]||[]).forEach(c=>{{ if(!os.has(c.ticker)) moved++; }});
      }});
      const badge=document.getElementById('badge');
      const btn=document.getElementById('btnSave');
      if(moved>0){{
        badge.textContent=moved+' 个待保存'; badge.classList.add('on');
        btn.disabled=false;
      }}else{{
        badge.classList.remove('on'); btn.disabled=true;
      }}
      render();
    }});
    bd.appendChild(el);
  }});
}}

function esc(s){{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function doSave(){{
  const result={{}};
  COLS.forEach(col=>{{
    (STATE[col.id]||[]).forEach(c=>{{ result[c.ticker]=col.id; }});
  }});
  const param=encodeURIComponent(JSON.stringify(result));
  // 写入父窗口 URL 的 query param → Streamlit 检测到变化自动 rerun
  const url=new URL(window.parent.location.href);
  url.searchParams.set('wl_drag', decodeURIComponent(param));
  window.parent.location.href = url.toString();
}}

function doReset(){{
  STATE=JSON.parse(JSON.stringify(ORIG));
  moved=0;
  document.getElementById('badge').classList.remove('on');
  document.getElementById('btnSave').disabled=true;
  render();
}}

render();
</script>
</body></html>"""

    _stc.html(html, height=board_height, scrolling=True)



# ════════════════════════════════════════════════════════════════════
# 精简卡片（看板专用）
# ════════════════════════════════════════════════════════════════════
def _render_mini_card(item: dict, result_map: dict, cats: list):
    ticker  = item["ticker"]
    name    = item.get("name","")
    pinned  = item.get("pinned", False)
    viewed  = _is_viewed(ticker)
    notes   = _all_notes(item)
    latest  = notes[-1] if notes else None
    results = result_map.get(ticker, [])
    tv_link = _tv_link(ticker)

    if viewed:
        card_bg, card_bd, opacity = "#f0fdf4", "#86efac", "opacity:0.78;"
    elif pinned:
        card_bg, card_bd, opacity = "#fffbeb", "#fde047", ""
    else:
        card_bg, card_bd, opacity = "#ffffff", "#e2e8f0", ""

    # Fibo 小徽章
    fibo_html = ""
    for res in results[:3]:
        tf      = res.get("timeframe","?")[:1]
        in_zone = res.get("in_zone", False)
        dist    = res.get("dist_pct")
        dist_s  = f"{dist:.0f}%" if dist is not None else "—"
        dot_bg  = "#fef9c3" if in_zone else "#f1f5f9"
        dot_bd  = "#fde047" if in_zone else "#e2e8f0"
        dot_ico = "⚡" if in_zone else "·"
        fibo_html += (
            f'<div style="background:{dot_bg};border:1px solid {dot_bd};'
            f'border-radius:5px;padding:2px 5px;font-size:10px;text-align:center;">'
            f'<b style="color:#475569">{tf}</b><br>'
            f'<span style="color:#64748b">{dot_ico}{dist_s}</span></div>'
        )

    note_text = ""
    if latest:
        t = latest.get("text","")
        note_text = t[:38] + "…" if len(t) > 38 else t

    viewed_mark = "✅ " if viewed else ""
    pin_mark    = "📌 " if pinned else ""
    display     = _he((name or ticker)[:16])

    st.markdown(
        f"""<div style="background:{card_bg};border:1.5px solid {card_bd};
        border-radius:9px;padding:10px 12px;margin-bottom:8px;{opacity}">
        <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:1px">
          {viewed_mark}{pin_mark}{display}</div>
        <div style="font-family:monospace;font-size:10px;color:#94a3b8;
             margin-bottom:5px">{_he(ticker)}</div>
        <div style="display:flex;gap:4px;margin-bottom:6px;flex-wrap:wrap">
          {fibo_html or '<span style="color:#d1d5db;font-size:10px">暂无扫描数据</span>'}
        </div>
        <div style="border-top:1px solid {card_bd};padding-top:5px;line-height:1.5">
          {f'<span style="color:#ef4444;font-size:13px;font-weight:700">' + _he(note_text) + '</span>' if note_text else '<i style="color:#d1d5db;font-size:11px">暂无备注</i>'}
        </div></div>""",
        unsafe_allow_html=True,
    )

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("✅" if viewed else "👁️",
                     key=f"mc_view_{ticker}",
                     help="标记已看" if not viewed else "取消已看"):
            if viewed: _unmark_viewed(ticker)
            else:      _mark_viewed(ticker)
            st.rerun()
    with b2:
        _open_tv_and_mark(ticker, tv_link, f"mc_tv_{ticker}")
    with b3:
        if st.button("🔓" if pinned else "📌",
                     key=f"mc_pin_{ticker}", help="置顶/取消"):
            _fast_patch(ticker, pinned=not pinned)
            st.rerun()
    with b4:
        if st.button("✏️", key=f"mc_note_{ticker}", help="添加备注"):
            st.session_state[f"wl_adding_{ticker}"] = True
            st.rerun()

    if st.session_state.get(f"wl_adding_{ticker}"):
        new_text = st.text_input(
            "备注", key=f"mc_note_text_{ticker}",
            placeholder="输入备注…", label_visibility="collapsed",
        )
        sc1, sc2 = st.columns(2)
        with sc1:
            if st.button("💾", key=f"mc_note_save_{ticker}", type="primary"):
                if new_text.strip():
                    storage.add_watchlist_note(ticker, new_text.strip())
                    st.session_state.pop(f"wl_adding_{ticker}", None)
                    st.toast(f"已保存备注：{ticker}", icon="📝")
                    st.rerun()
        with sc2:
            if st.button("✖", key=f"mc_note_cancel_{ticker}"):
                st.session_state.pop(f"wl_adding_{ticker}", None)
                st.rerun()


# ════════════════════════════════════════════════════════════════════
# 完整卡片（列表模式）
# ════════════════════════════════════════════════════════════════════
def _render_card(item: dict, idx: int, result_map: dict, cats: list = None):
    ticker  = item["ticker"]
    name    = item.get("name","")
    added   = item.get("added_at","")
    pinned  = item.get("pinned", False)
    viewed  = _is_viewed(ticker)
    results = result_map.get(ticker, [])
    notes   = _all_notes(item)
    latest  = notes[-1] if notes else None
    tv_link = _tv_link(ticker)

    if viewed:
        border_color, bg_extra = "#86efac", "background:#f0fdf4;"
    elif pinned:
        border_color, bg_extra = "#fde047", "background:#fffbeb;"
    else:
        border_color, bg_extra = "#e5e7eb", ""

    _is_hl = (st.session_state.get("_hl_ticker","") == ticker)
    if _is_hl:
        border_color = "#3b82f6"
        _hl_extra    = "box-shadow:0 0 0 3px #bfdbfe;"
    else:
        _hl_extra = ""

    with st.container():
        st.markdown(
            f'<div id="wl-card-{ticker}" style="{bg_extra}border:1.5px solid {border_color};'
            f'border-radius:10px;padding:14px 18px 12px;margin-bottom:10px;{_hl_extra}">',
            unsafe_allow_html=True,
        )

        col_title, col_actions = st.columns([7, 3])
        with col_title:
            viewed_badge = (
                '<span style="background:#dcfce7;color:#166534;font-size:10px;'
                'padding:1px 7px;border-radius:10px;margin-right:5px">✅ 已看</span>'
                if viewed else ""
            )
            pin_icon = "📌 " if pinned else ""
            _cat_badge = ""
            _item_cat_id = item.get("category_id")
            if cats and _item_cat_id:
                _cn = next((c for c in cats if c["id"] == _item_cat_id), None)
                if not _cn:
                    _cn = next((c for c in cats if c["name"] == _item_cat_id), None)
                if _cn:
                    _cat_badge = (
                        f'<span style="background:#eff6ff;color:#1d4ed8;font-size:10px;'
                        f'padding:1px 6px;border-radius:10px;margin-left:6px">'
                        f'🏷️ {_he(_cn["name"])}</span>'
                    )
            if name:
                st.markdown(
                    f"<div style='margin-bottom:2px'>{viewed_badge}"
                    f"<span style='font-size:16px;font-weight:700;color:#111'>"
                    f"{pin_icon}{_he(name)}</span>&nbsp;&nbsp;"
                    f"<span style='font-family:monospace;font-size:12px;color:#9ca3af;"
                    f"background:#f3f4f6;padding:2px 6px;border-radius:4px'>{_he(ticker)}</span>"
                    f"{_cat_badge}</div>"
                    f"<span style='color:#9ca3af;font-size:11px'>收藏于 {_he(added)}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div style='margin-bottom:2px'>{viewed_badge}"
                    f"<span style='font-size:16px;font-weight:700;font-family:monospace;color:#111'>"
                    f"{pin_icon}{_he(ticker)}</span>{_cat_badge}</div>"
                    f"<span style='color:#9ca3af;font-size:11px'>收藏于 {_he(added)}</span>",
                    unsafe_allow_html=True,
                )

        with col_actions:
            b1, b2, b3, b4, b5 = st.columns(5)
            with b1:
                if st.button("✅" if viewed else "👁️",
                             key=f"wl_view_{ticker}_{idx}",
                             help="标记今日已看" if not viewed else "取消已看"):
                    if viewed: _unmark_viewed(ticker)
                    else:      _mark_viewed(ticker)
                    st.rerun()
            with b2:
                _open_tv_and_mark(ticker, tv_link, f"wl_tv_{ticker}_{idx}")
            with b3:
                if st.button("📌" if not pinned else "🔓",
                             key=f"wl_pin_{ticker}_{idx}",
                             help="置顶/取消置顶"):
                    _fast_patch(ticker, pinned=not pinned)
                    st.rerun()
            with b4:
                if st.button("🏷️", key=f"wl_cat_btn_{ticker}_{idx}",
                             help="设置分类"):
                    _k = f"wl_cat_editing_{ticker}"
                    _cur = st.session_state.get(_k, False)
                    st.session_state[_k] = not _cur
                    if not _cur:
                        st.session_state[f"wl_cat_init_{ticker}"] = True
                    st.rerun()
            with b5:
                if st.button("🗑", key=f"wl_del_{ticker}_{idx}",
                             help="删除（移入存档）"):
                    storage.remove_from_watchlist(ticker)
                    st.toast(f"已移入存档：{ticker}", icon="🗂️")
                    st.rerun()

        if st.session_state.get(f"wl_cat_editing_{ticker}"):
            _render_cat_assign_inline(ticker, name, item, cats)

        if results:
            fibo_cols = st.columns(min(len(results), 4))
            for ci, res in enumerate(results[:4]):
                with fibo_cols[ci]:
                    tf      = res.get("timeframe","?")
                    dist    = res.get("dist_pct")
                    in_zone = res.get("in_zone", False)
                    fib_val = res.get("nearest_fibo", res.get("nearest_fib",""))
                    bg      = "#fef9c3" if in_zone else "#f9fafb"
                    bd      = "#fde047" if in_zone else "#e5e7eb"
                    st.markdown(
                        f'<div style="background:{bg};border:1px solid {bd};'
                        f'border-radius:8px;padding:6px 10px;text-align:center;font-size:11px;">'
                        f'<div style="font-weight:700;color:#374151">{tf}</div>'
                        f'<div style="color:#e85d04;font-weight:600">'
                        f'{str(fib_val) if fib_val else "—"}</div>'
                        f'<div style="color:#6b7280">'
                        f'{"⚡" if in_zone else "·"} '
                        f'{f"{dist:.1f}%" if dist is not None else "—"}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        older = notes[:-1]
        if older:
            with st.expander(f"📋 历史备注（{len(older)} 条）"):
                for n in reversed(older):
                    thumb = _thumb_html(n.get("img_url",""), 120)
                    st.markdown(
                        f'<div style="border-left:2px solid #e5e7eb;'
                        f'padding:5px 10px;margin:4px 0;font-size:12px;">'
                        f'<span style="color:#9ca3af">{n.get("ts","")}</span>&nbsp;&nbsp;'
                        f'<span style="color:#374151">{_he(str(n["text"]))}</span>'
                        f'{("<br>"+thumb) if thumb else ""}</div>',
                        unsafe_allow_html=True,
                    )

        if st.button("✏️ 添加备注", key=f"wl_edit_btn_{ticker}_{idx}"):
            st.session_state[f"wl_adding_{ticker}"] = True

        if st.session_state.get(f"wl_adding_{ticker}"):
            new_text = st.text_input(
                "备注内容 *（必填）", key=f"wl_note_text_{ticker}_{idx}",
                placeholder="输入本次备注…",
            )
            new_img = st.text_input(
                "图片链接（选填）", key=f"wl_note_img_{ticker}_{idx}",
                placeholder="https://...图片URL",
            ).strip()
            if new_img:
                st.markdown(_thumb_html(new_img, 180), unsafe_allow_html=True)
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("💾 保存备注", key=f"wl_note_save_{ticker}_{idx}",
                             type="primary"):
                    if not new_text.strip():
                        st.warning("备注内容不能为空")
                    else:
                        storage.add_watchlist_note(ticker, new_text.strip(), new_img)
                        st.session_state[f"wl_adding_{ticker}"] = False
                        st.toast(f"备注已保存：{ticker}", icon="📝")
                        st.rerun()
            with sc2:
                if st.button("取消", key=f"wl_note_cancel_{ticker}_{idx}"):
                    st.session_state[f"wl_adding_{ticker}"] = False
                    st.rerun()

        if latest:
            thumb  = _thumb_html(latest.get("img_url",""), 140)
            ts_str = latest.get("ts","")
            st.markdown(
                f'<div style="background:#fff1f2;border-left:3px solid #ef4444;'
                f'border-radius:0 6px 6px 0;padding:8px 12px 6px;margin:6px 0 2px;">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:flex-start;margin-bottom:4px">'
                f'<span style="color:#ef4444;font-size:11px;font-weight:600">📝 最新备注</span>'
                f'<span style="color:#9ca3af;font-size:10px">{_he(ts_str)}</span></div>'
                f'<span style="color:#ef4444;font-size:15px;font-weight:700;line-height:1.5">{_he(str(latest["text"]))}</span>'
                f'{("<br>"+thumb) if thumb else ""}</div>',
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 分类指派内联表单
# ════════════════════════════════════════════════════════════════════
def _render_cat_assign_inline(ticker: str, name: str, item: dict, cats: list):
    if not cats:
        st.warning("⚠️ 尚无分类，请先在「🏷️ 分类管理」标签页创建分类。")
        return

    _cur_cat_id = item.get("category_id")
    _as_ids     = ["__UNCAT__"]
    _as_names   = {"__UNCAT__": "（未分类）"}

    def _fill(nodes, depth=0):
        pfx = ("  " * depth + "└ ") if depth > 0 else ""
        for nd in sorted(nodes, key=lambda x: x.get("order", 0)):
            _as_ids.append(nd["id"])
            _as_names[nd["id"]] = f"{pfx}{nd['name']}"
            if nd.get("children"):
                _fill(nd["children"], depth + 1)
    _fill(storage.build_cat_tree(cats))

    _assign_key = f"wl_cat_sel_id_{ticker}"
    _init_flag  = f"wl_cat_init_{ticker}"

    if st.session_state.pop(_init_flag, False):
        _default = "__UNCAT__"
        if _cur_cat_id:
            if _cur_cat_id in _as_ids:
                _default = _cur_cat_id
            else:
                _m = next((c["id"] for c in cats if c["name"] == _cur_cat_id), None)
                if _m: _default = _m
        st.session_state[_assign_key] = _default

    if st.session_state.get(_assign_key) not in _as_ids:
        st.session_state[_assign_key] = "__UNCAT__"

    _chosen = st.selectbox(
        f"📂 设置「{name or ticker}」的分类",
        options=_as_ids,
        format_func=lambda x: _as_names.get(x, str(x)),
        key=_assign_key,
    )
    sc1, sc2 = st.columns(2)
    with sc1:
        if st.button("💾 保存分类", key=f"wl_cat_save_{ticker}", type="primary"):
            _save_id = None if _chosen == "__UNCAT__" else _chosen
            storage.set_watchlist_item_category(ticker, _save_id)
            st.session_state.pop(f"wl_cat_editing_{ticker}", None)
            st.session_state.pop(_assign_key, None)
            st.toast(f"已设置分类：{_as_names.get(_chosen, _chosen)}", icon="🏷️")
            st.rerun()
    with sc2:
        if st.button("取消", key=f"wl_cat_cancel_{ticker}"):
            st.session_state.pop(f"wl_cat_editing_{ticker}", None)
            st.session_state.pop(_assign_key, None)
            st.rerun()


# ════════════════════════════════════════════════════════════════════
# 🏷️ 分类管理
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
# 🖱️  拖拽分类看板
# 原理：用 st.components.v1.html 渲染原生 DragAPI 看板
#       拖完后点「保存」→ 写入隐藏 text_area → Streamlit 检测变化保存
# ════════════════════════════════════════════════════════════════════
def _render_drag_board():
    import json
    import streamlit.components.v1 as _stc

    cats  = storage.load_wl_categories()
    items = storage.load_watchlist()

    if not cats:
        st.info("请先创建分类后再使用拖拽功能。")
        return
    if not items:
        st.info("收藏夹为空。")
        return

    # ── 构建看板数据：columns = 分类列表 + 未分类列 ──────────────
    tree = storage.build_cat_tree(cats)
    # 扁平顺序（按树顺序）
    col_order = []
    def _flatten(nodes):
        for n in sorted(nodes, key=lambda x: x.get("order", 0)):
            col_order.append({"id": n["id"], "name": n["name"]})
            if n.get("children"):
                _flatten(n["children"])
    _flatten(tree)
    col_order.append({"id": "__NONE__", "name": "❓ 未分类"})

    # 品种 → 当前列
    cat_name_map = {c["id"]: c["name"] for c in cats}
    board = {col["id"]: [] for col in col_order}
    for item in items:
        cid = item.get("category_id") or "__NONE__"
        if cid != "__NONE__" and cid not in cat_name_map:
            matched = next((c["id"] for c in cats if c["name"] == cid), None)
            cid = matched if matched else "__NONE__"
        if cid not in board:
            cid = "__NONE__"
        board[cid].append({
            "ticker": item["ticker"],
            "name":   item.get("name", ""),
        })

    board_json   = json.dumps(board,     ensure_ascii=False)
    columns_json = json.dumps(col_order, ensure_ascii=False)

    # ── 接收拖拽结果 ─────────────────────────────────────────────
    result_key = "drag_board_result"
    result_raw = st.text_area(
        "拖拽结果（内部使用）",
        key=result_key,
        value="",
        label_visibility="collapsed",
        height=1,
    )

    # 如果有结果 → 保存 → 清空
    if result_raw and result_raw.strip().startswith("{"):
        try:
            result = json.loads(result_raw)
            saved_count = 0
            all_wl = storage.load_watchlist()
            changed = False
            for wl_item in all_wl:
                tk = wl_item["ticker"].upper()
                new_cat = result.get(tk)   # cat_id or "__NONE__" or None
                old_cat = wl_item.get("category_id")
                if new_cat == "__NONE__":
                    new_cat = None
                if new_cat != old_cat:
                    wl_item["category_id"] = new_cat
                    changed = True
                    saved_count += 1
            if changed:
                storage.save_watchlist(all_wl)
                st.session_state.pop(result_key, None)
                st.toast(f"✅ 已保存 {saved_count} 个品种的分类变更", icon="🎉")
                st.rerun()
        except Exception as e:
            st.error(f"保存失败：{e}")

    # ── 渲染拖拽看板 HTML ─────────────────────────────────────────
    col_count  = len(col_order)
    board_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f1f5f9;
    padding: 12px;
    min-height: 100vh;
  }}
  h3 {{
    font-size: 13px; color: #64748b; margin-bottom: 10px;
    font-weight: 500;
  }}
  .board {{
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 8px;
    align-items: flex-start;
  }}
  .column {{
    flex: 0 0 160px;
    background: #fff;
    border-radius: 10px;
    border: 1.5px solid #e2e8f0;
    padding: 8px;
    min-height: 120px;
    transition: border-color 0.15s;
  }}
  .column.drag-over {{
    border-color: #3b82f6;
    background: #eff6ff;
  }}
  .col-title {{
    font-size: 11px;
    font-weight: 700;
    color: #0f172a;
    padding: 4px 6px 6px;
    border-bottom: 1.5px solid #e2e8f0;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .col-count {{
    background: #e0e7ff;
    color: #3730a3;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    font-weight: 600;
  }}
  .card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 6px 8px;
    margin-bottom: 5px;
    cursor: grab;
    user-select: none;
    transition: box-shadow 0.15s, opacity 0.15s;
  }}
  .card:hover {{
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    border-color: #93c5fd;
  }}
  .card.dragging {{
    opacity: 0.4;
    box-shadow: 0 4px 16px rgba(59,130,246,0.3);
    cursor: grabbing;
  }}
  .card-name {{
    font-size: 12px;
    font-weight: 700;
    color: #0f172a;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 130px;
  }}
  .card-ticker {{
    font-size: 10px;
    color: #94a3b8;
    font-family: monospace;
  }}
  .drop-placeholder {{
    border: 2px dashed #93c5fd;
    border-radius: 7px;
    height: 36px;
    background: #eff6ff;
    margin-bottom: 5px;
  }}
  .save-bar {{
    position: sticky;
    bottom: 0;
    background: #fff;
    border-top: 1px solid #e2e8f0;
    padding: 10px 12px;
    margin-top: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-radius: 0 0 8px 8px;
  }}
  .btn-save {{
    background: #2563eb;
    color: #fff;
    border: none;
    border-radius: 7px;
    padding: 7px 20px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }}
  .btn-save:hover {{ background: #1d4ed8; }}
  .btn-save:disabled {{ background: #93c5fd; cursor: not-allowed; }}
  .btn-reset {{
    background: #f1f5f9;
    color: #475569;
    border: 1px solid #e2e8f0;
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 12px;
    cursor: pointer;
  }}
  .change-badge {{
    background: #fef9c3;
    color: #92400e;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 8px;
    font-weight: 600;
    display: none;
  }}
  .change-badge.visible {{ display: inline-block; }}
  .hint {{
    font-size: 11px;
    color: #94a3b8;
    margin-left: auto;
  }}
</style>
</head>
<body>
<h3>🖱️ 拖动品种卡片到目标分类列，拖完后点「保存分类」</h3>
<div class="board" id="board"></div>
<div class="save-bar">
  <button class="btn-save" id="btnSave" onclick="saveChanges()" disabled>💾 保存分类</button>
  <button class="btn-reset" onclick="resetBoard()">↩ 还原</button>
  <span class="change-badge" id="changeBadge"></span>
  <span class="hint">拖动后保存 → 页面自动刷新</span>
</div>

<script>
const BOARD_DATA   = {board_json};
const COL_ORDER    = {columns_json};

// 深拷贝初始状态（用于还原）
let boardState     = JSON.parse(JSON.stringify(BOARD_DATA));
let originalState  = JSON.parse(JSON.stringify(BOARD_DATA));
let dragTicker     = null;
let dragFromCol    = null;
let changeCount    = 0;

function renderBoard() {{
  const boardEl = document.getElementById('board');
  boardEl.innerHTML = '';
  COL_ORDER.forEach(col => {{
    const cards = boardState[col.id] || [];
    const colEl = document.createElement('div');
    colEl.className = 'column';
    colEl.dataset.colId = col.id;
    colEl.innerHTML =
      '<div class="col-title">' +
        '<span>' + col.name + '</span>' +
        '<span class="col-count">' + cards.length + '</span>' +
      '</div>';
    cards.forEach(item => {{
      const card = document.createElement('div');
      card.className = 'card';
      card.draggable = true;
      card.dataset.ticker = item.ticker;
      card.dataset.colId  = col.id;
      card.innerHTML =
        '<div class="card-name">' + (item.name || item.ticker) + '</div>' +
        '<div class="card-ticker">' + item.ticker + '</div>';
      card.addEventListener('dragstart', onDragStart);
      card.addEventListener('dragend',   onDragEnd);
      colEl.appendChild(card);
    }});
    colEl.addEventListener('dragover',  onDragOver);
    colEl.addEventListener('dragleave', onDragLeave);
    colEl.addEventListener('drop',      onDrop);
    boardEl.appendChild(colEl);
  }});
}}

function onDragStart(e) {{
  dragTicker  = e.currentTarget.dataset.ticker;
  dragFromCol = e.currentTarget.dataset.colId;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
}}
function onDragEnd(e) {{
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.column').forEach(c => c.classList.remove('drag-over'));
  document.querySelectorAll('.drop-placeholder').forEach(p => p.remove());
}}
function onDragOver(e) {{
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const col = e.currentTarget;
  col.classList.add('drag-over');
  // 占位符
  if (!col.querySelector('.drop-placeholder')) {{
    const ph = document.createElement('div');
    ph.className = 'drop-placeholder';
    col.appendChild(ph);
  }}
}}
function onDragLeave(e) {{
  if (!e.currentTarget.contains(e.relatedTarget)) {{
    e.currentTarget.classList.remove('drag-over');
    e.currentTarget.querySelectorAll('.drop-placeholder').forEach(p => p.remove());
  }}
}}
function onDrop(e) {{
  e.preventDefault();
  const toColId = e.currentTarget.dataset.colId;
  if (!dragTicker || toColId === dragFromCol) {{
    renderBoard(); return;
  }}
  // 从源列移除
  boardState[dragFromCol] = boardState[dragFromCol].filter(i => i.ticker !== dragTicker);
  // 找到被拖项的完整对象（从原始数据）
  let dragItem = null;
  for (const cid in BOARD_DATA) {{
    const found = BOARD_DATA[cid].find(i => i.ticker === dragTicker);
    if (found) {{ dragItem = found; break; }}
  }}
  if (dragItem && !boardState[toColId].find(i => i.ticker === dragTicker)) {{
    boardState[toColId].push(dragItem);
  }}
  dragTicker = null; dragFromCol = null;
  // 计算变更数
  changeCount = 0;
  COL_ORDER.forEach(col => {{
    const orig = (originalState[col.id] || []).map(i => i.ticker).sort().join(',');
    const curr = (boardState[col.id]    || []).map(i => i.ticker).sort().join(',');
    if (orig !== curr) changeCount += Math.abs(
      (boardState[col.id]||[]).length - (originalState[col.id]||[]).length
    );
  }});
  // 精确计算移动数
  let moved = 0;
  COL_ORDER.forEach(col => {{
    const origSet = new Set((originalState[col.id]||[]).map(i=>i.ticker));
    const currSet = new Set((boardState[col.id]||[]).map(i=>i.ticker));
    currSet.forEach(t => {{ if (!origSet.has(t)) moved++; }});
  }});
  changeCount = moved;
  const badge = document.getElementById('changeBadge');
  const btn   = document.getElementById('btnSave');
  if (changeCount > 0) {{
    badge.textContent = changeCount + ' 个品种待保存';
    badge.classList.add('visible');
    btn.disabled = false;
  }} else {{
    badge.classList.remove('visible');
    btn.disabled = true;
  }}
  renderBoard();
}}

function saveChanges() {{
  // 构建 ticker→catId 映射
  const result = {{}};
  COL_ORDER.forEach(col => {{
    (boardState[col.id]||[]).forEach(item => {{
      result[item.ticker] = col.id;
    }});
  }});
  // 写入 Streamlit 的隐藏 textarea
  // Streamlit 组件嵌在 iframe 里，用 postMessage 通知父窗口
  window.parent.postMessage({{
    type: 'streamlit:setComponentValue',
    value: JSON.stringify(result)
  }}, '*');
  // 同时尝试直接写 textarea（本地运行时可行）
  try {{
    const frames = window.parent.document.querySelectorAll('iframe');
    frames.forEach(fr => {{
      try {{
        const ta = fr.contentDocument.querySelector('textarea[data-testid]');
        if (ta) {{ ta.value = JSON.stringify(result); ta.dispatchEvent(new Event('input', {{bubbles:true}})); }}
      }} catch(e) {{}}
    }});
  }} catch(e) {{}}
  document.getElementById('btnSave').textContent = '⏳ 保存中…';
  document.getElementById('btnSave').disabled = true;
}}

function resetBoard() {{
  boardState  = JSON.parse(JSON.stringify(originalState));
  changeCount = 0;
  document.getElementById('changeBadge').classList.remove('visible');
  document.getElementById('btnSave').disabled = true;
  document.getElementById('btnSave').textContent = '💾 保存分类';
  renderBoard();
}}

renderBoard();
</script>
</body>
</html>"""

    board_height = max(400, len(items) * 14 + 200)
    _stc.html(board_html, height=board_height, scrolling=True)

    # ── 备用方案：用 st.form + selectbox 批量修改（折叠） ─────────
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📝 备用：下拉选择批量修改分类（不支持拖拽时使用）"):
        items_all = storage.load_watchlist()
        if not items_all:
            st.info("收藏夹为空")
        else:
            b1, b2, b3 = st.columns([3,3,2])
            with b1:
                _batch_tickers = st.multiselect(
                    "选择品种",
                    options=[f"{i['ticker']} {i.get('name','')}" for i in items_all],
                    key="cat_batch_tickers_v1",
                    placeholder="选择要批量设置分类的品种…",
                )
            with b2:
                _bb_ids, _bb_names = ["__UNCAT__"], {"__UNCAT__": "（未分类）"}
                def _fill_b(nodes, depth=0):
                    pfx = "  " * depth + ("└ " if depth > 0 else "")
                    for node in sorted(nodes, key=lambda x: x.get("order", 0)):
                        _bb_ids.append(node["id"])
                        _bb_names[node["id"]] = f"{pfx}{node['name']}"
                        if node.get("children"):
                            _fill_b(node["children"], depth + 1)
                _fill_b(storage.build_cat_tree(cats))
                _bc = st.selectbox("目标分类", options=_bb_ids,
                                   format_func=lambda x: _bb_names.get(x, str(x)),
                                   key="cat_batch_target_id2")
                _batch_cat_id = None if _bc == "__UNCAT__" else _bc
            with b3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 批量设置", key="cat_batch_save2",
                             type="primary", use_container_width=True):
                    if _batch_tickers:
                        for ts in _batch_tickers:
                            storage.set_watchlist_item_category(ts.split()[0], _batch_cat_id)
                        st.success(f"✅ 已为 {len(_batch_tickers)} 个品种设置分类")
                        st.rerun()
                    else:
                        st.warning("请先选择品种")

def _render_categories():
    st.markdown("### 🏷️ 分类管理")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '创建品种分类目录（支持三级），在品种卡片上点击 🏷️ 可指派分类。</p>',
        unsafe_allow_html=True,
    )

    cats = storage.load_wl_categories()
    tree = storage.build_cat_tree(cats)

    # ── 拖拽看板（核心入口） ──────────────────────────────────────
    if cats:
        with st.expander("🖱️ 拖拽分类看板（拖动品种到目标分类）", expanded=True):
            _render_drag_board()
        st.markdown("---")

    with st.expander("➕ 新增分类", expanded=len(cats) == 0):
        _add_col1, _add_col2, _add_col3 = st.columns([3, 3, 2])
        with _add_col1:
            _new_cat_name = st.text_input(
                "分类名称 *", placeholder="如：A股 / 美股科技",
                key="cat_new_name",
            ).strip()
        with _add_col2:
            _pp_ids   = ["__ROOT__"]
            _pp_names = {"__ROOT__": "顶级分类（一级）"}
            def _fill_parent(nodes, depth=0):
                if depth >= 2: return
                pfx = "  " * depth + ("└ " if depth > 0 else "")
                for node in sorted(nodes, key=lambda x: x.get("order", 0)):
                    _pp_ids.append(node["id"])
                    _pp_names[node["id"]] = f"{pfx}{node['name']}"
                    if node.get("children"):
                        _fill_parent(node["children"], depth + 1)
            _fill_parent(tree)
            _pc = st.selectbox("父级分类", options=_pp_ids,
                               format_func=lambda x: _pp_names.get(x, str(x)),
                               key="cat_new_parent_id")
            _parent_id = None if _pc == "__ROOT__" else _pc
        with _add_col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ 添加分类", key="cat_add_btn", type="primary",
                         use_container_width=True):
                if not _new_cat_name:
                    st.warning("请输入分类名称")
                else:
                    new_id = storage.add_wl_category(_new_cat_name, _parent_id)
                    if new_id:
                        st.success(f"✅ 已添加：{_new_cat_name}")
                        st.rerun()
                    else:
                        st.warning(f"⚠️ 同级分类「{_new_cat_name}」已存在")

    if not cats:
        st.markdown("""
        <div style="text-align:center;padding:40px 20px;color:#9ca3af;">
          <div style="font-size:36px">🏷️</div>
          <div style="font-size:15px;margin:10px 0 6px;color:#374151;font-weight:600">尚无分类</div>
          <div style="font-size:13px">点击上方「新增分类」创建您的第一个分类</div>
        </div>""", unsafe_allow_html=True)
        return

    st.markdown("---")
    st.markdown("**📋 分类目录**（可展开编辑、重命名、排序、删除）")

    items = storage.load_watchlist()

    def _count_in_cat(cat_id, cats_flat):
        all_ids = {cat_id} | storage._collect_descendants(cats_flat, cat_id)
        return sum(1 for i in items if i.get("category_id") in all_ids)

    def _render_cat_node(node, cats_flat, depth=0):
        indent      = "&nbsp;" * (depth * 4)
        depth_label = ["一","二","三"][min(depth,2)]
        item_cnt    = _count_in_cat(node["id"], cats_flat)
        badge_color = ["#dbeafe","#dcfce7","#fef9c3"][min(depth,2)]
        badge_text  = ["#1d4ed8","#15803d","#92400e"][min(depth,2)]

        with st.container():
            col_icon, col_info, col_ops = st.columns([0.3, 5, 4])
            with col_icon:
                st.markdown(
                    f'<div style="font-size:20px;padding-top:6px;text-align:center">'
                    f'{["📁","📂","📄"][min(depth,2)]}</div>',
                    unsafe_allow_html=True,
                )
            with col_info:
                st.markdown(
                    f'{indent}<span style="font-size:14px;font-weight:600;color:#111">'
                    f'{_he(node["name"])}</span>'
                    f'<span style="background:{badge_color};color:{badge_text};'
                    f'font-size:10px;padding:1px 7px;border-radius:10px;margin-left:8px">'
                    f'{depth_label}级</span>'
                    f'<span style="color:#9ca3af;font-size:11px;margin-left:8px">'
                    f'{item_cnt} 个品种</span>',
                    unsafe_allow_html=True,
                )
            with col_ops:
                o1, o2, o3, o4, o5 = st.columns(5)
                with o1:
                    if st.button("✏️", key=f"cat_edit_{node['id']}", help="重命名"):
                        st.session_state[f"cat_renaming_{node['id']}"] = True
                        st.rerun()
                with o2:
                    if st.button("⬆️", key=f"cat_up_{node['id']}", help="上移"):
                        storage.reorder_wl_category(node["id"], "up"); st.rerun()
                with o3:
                    if st.button("⬇️", key=f"cat_dn_{node['id']}", help="下移"):
                        storage.reorder_wl_category(node["id"], "down"); st.rerun()
                with o4:
                    if depth < 2:
                        if st.button("➕", key=f"cat_sub_{node['id']}", help="子分类"):
                            st.session_state[f"cat_adding_sub_{node['id']}"] = True
                            st.rerun()
                with o5:
                    if st.button("🗑️", key=f"cat_del_{node['id']}", help="删除"):
                        st.session_state[f"cat_del_confirm_{node['id']}"] = True
                        st.rerun()

            if st.session_state.get(f"cat_renaming_{node['id']}"):
                r1, r2, r3 = st.columns([4,1,1])
                with r1:
                    rv = st.text_input("新名称", value=node["name"],
                                       key=f"cat_rn_input_{node['id']}")
                with r2:
                    if st.button("💾", key=f"cat_rn_save_{node['id']}"):
                        if rv.strip():
                            storage.rename_wl_category(node["id"], rv.strip())
                            st.session_state.pop(f"cat_renaming_{node['id']}", None)
                            st.rerun()
                with r3:
                    if st.button("✖", key=f"cat_rn_cancel_{node['id']}"):
                        st.session_state.pop(f"cat_renaming_{node['id']}", None)
                        st.rerun()

            if st.session_state.get(f"cat_del_confirm_{node['id']}"):
                desc_cnt = len(storage._collect_descendants(cats_flat, node["id"]))
                st.warning(
                    f"⚠️ 确认删除「{node['name']}」"
                    + (f"（含 {desc_cnt} 个子分类）" if desc_cnt else "")
                    + f"？{item_cnt} 个品种将变为未分类。"
                )
                d1, d2 = st.columns(2)
                with d1:
                    if st.button("✅ 确认删除", key=f"cat_del_yes_{node['id']}",
                                 type="primary"):
                        storage.delete_wl_category(node["id"])
                        st.session_state.pop(f"cat_del_confirm_{node['id']}", None)
                        st.rerun()
                with d2:
                    if st.button("取消", key=f"cat_del_no_{node['id']}"):
                        st.session_state.pop(f"cat_del_confirm_{node['id']}", None)
                        st.rerun()

            if st.session_state.get(f"cat_adding_sub_{node['id']}"):
                s1, s2, s3 = st.columns([4,1,1])
                with s1:
                    sn = st.text_input(f"子分类（{node['name']} 下）",
                                       key=f"cat_sub_input_{node['id']}",
                                       placeholder="子分类名称…")
                with s2:
                    if st.button("➕", key=f"cat_sub_save_{node['id']}"):
                        if sn.strip():
                            nid = storage.add_wl_category(sn.strip(), node["id"])
                            if nid:
                                st.session_state.pop(f"cat_adding_sub_{node['id']}", None)
                                st.rerun()
                            else:
                                st.warning("同级已存在同名分类")
                with s3:
                    if st.button("✖", key=f"cat_sub_cancel_{node['id']}"):
                        st.session_state.pop(f"cat_adding_sub_{node['id']}", None)
                        st.rerun()

        for child in sorted(node.get("children",[]), key=lambda x: x.get("order",0)):
            _render_cat_node(child, cats_flat, depth + 1)

        if depth == 0:
            st.markdown(
                '<div style="border-bottom:1px solid #f3f4f6;margin:4px 0"></div>',
                unsafe_allow_html=True,
            )

    for root_node in sorted(tree, key=lambda x: x.get("order", 0)):
        _render_cat_node(root_node, cats)

    st.markdown("---")
    with st.expander("📦 批量设置品种分类"):
        items_all = storage.load_watchlist()
        if not items_all:
            st.info("收藏夹为空")
        else:
            b1, b2, b3 = st.columns([3,3,2])
            with b1:
                _batch_tickers = st.multiselect(
                    "选择品种",
                    options=[f"{i['ticker']} {i.get('name','')}" for i in items_all],
                    key="cat_batch_tickers",
                    placeholder="选择要批量设置分类的品种…",
                )
            with b2:
                _bb_ids, _bb_names = ["__UNCAT__"], {"__UNCAT__": "（未分类）"}
                def _fill_batch(nodes, depth=0):
                    pfx = "  " * depth + ("└ " if depth > 0 else "")
                    for node in sorted(nodes, key=lambda x: x.get("order", 0)):
                        _bb_ids.append(node["id"])
                        _bb_names[node["id"]] = f"{pfx}{node['name']}"
                        if node.get("children"):
                            _fill_batch(node["children"], depth + 1)
                _fill_batch(storage.build_cat_tree(cats))
                _bc = st.selectbox("目标分类", options=_bb_ids,
                                   format_func=lambda x: _bb_names.get(x, str(x)),
                                   key="cat_batch_target_id")
                _batch_cat_id = None if _bc == "__UNCAT__" else _bc
            with b3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 批量设置", key="cat_batch_save_v1",
                             type="primary", use_container_width=True):
                    if _batch_tickers:
                        for ts in _batch_tickers:
                            storage.set_watchlist_item_category(ts.split()[0], _batch_cat_id)
                        st.success(f"✅ 已为 {len(_batch_tickers)} 个品种设置分类")
                        st.rerun()
                    else:
                        st.warning("请先选择品种")


# ════════════════════════════════════════════════════════════════════
# 🗂️ 已删除存档
# ════════════════════════════════════════════════════════════════════
def _render_archive():
    archive = storage.load_watchlist_archive()
    if not archive:
        st.markdown("""
        <div style="text-align:center;padding:40px;color:#9ca3af;">
          <div style="font-size:36px">🗂️</div>
          <div style="font-size:14px;margin-top:8px">暂无已删除品种</div>
        </div>""", unsafe_allow_html=True)
        return

    st.markdown(
        f'<p style="color:#6b7280;font-size:13px">共 {len(archive)} 个已删除品种，'
        f'可一键恢复（含所有历史备注）。</p>',
        unsafe_allow_html=True,
    )

    for idx, item in enumerate(reversed(archive)):
        ticker     = item["ticker"]
        name       = item.get("name","")
        deleted_at = item.get("deleted_at","")
        notes      = _all_notes(item)
        latest     = notes[-1] if notes else None

        col_info, col_btn = st.columns([8, 2])
        with col_info:
            st.markdown(
                f"<b>{_he(ticker)}</b>"
                + (f" — {_he(name)}" if name else "")
                + f"&nbsp;&nbsp;<span style='color:#9ca3af;font-size:11px'>"
                f"删除于 {_he(deleted_at)}</span>",
                unsafe_allow_html=True,
            )
            if latest:
                t = latest["text"]
                st.markdown(
                    f'<span style="color:#6b7280;font-size:12px">最后备注：'
                    f'{_he(t[:60])}{"…" if len(t)>60 else ""}</span>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<span style="color:#9ca3af;font-size:11px">共 {len(notes)} 条备注</span>',
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("🔄 恢复", key=f"arch_restore_{ticker}_{idx}", type="primary"):
                ok = storage.restore_from_archive(ticker)
                if ok:
                    st.toast(f"已恢复：{ticker}", icon="✅")
                    st.rerun()
                else:
                    st.error("恢复失败（可能已在收藏夹中）")

        st.markdown(
            '<hr style="border:none;border-top:1px solid #f3f4f6;margin:6px 0">',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════
# 💾 备份与恢复
# ════════════════════════════════════════════════════════════════════
def _render_backup():
    items = storage.load_watchlist()
    n     = len(items)

    st.markdown(f"### 📊 当前状态：共 **{n}** 个收藏品种")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            '<div class="m-card teal"><div class="m-lbl">当前收藏</div>'
            f'<div class="m-val">{n}</div><div class="m-sub">个品种</div></div>',
            unsafe_allow_html=True,
        )
    with col_b:
        baks    = storage.list_backups()
        wl_baks = [b for b in baks if "data_watchlist" in b[0]]
        st.markdown(
            '<div class="m-card blue"><div class="m-lbl">本地备份</div>'
            f'<div class="m-val">{len(wl_baks)}</div><div class="m-sub">个文件</div></div>',
            unsafe_allow_html=True,
        )
    with col_c:
        total_notes = sum(len(i.get("notes",[])) for i in items)
        st.markdown(
            '<div class="m-card gold"><div class="m-lbl">备注总数</div>'
            f'<div class="m-val">{total_notes}</div><div class="m-sub">条备注</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📥 方案1：下载备份文件（推荐）")
    import time as _time
    json_str = storage.export_watchlist_json()
    ts = _time.strftime("%Y%m%d_%H%M")
    st.download_button(
        label=f"⬇️ 下载收藏夹备份 JSON（{n}个品种）",
        data=json_str.encode("utf-8"),
        file_name=f"strx_watchlist_backup_{ts}.json",
        mime="application/json", type="primary",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🔐 方案2：Streamlit Secrets 永久持久化")
    with st.expander("📋 查看操作步骤", expanded=True):
        st.markdown("""
**操作步骤：**
1. 点击下方「生成 Secrets 配置」按钮
2. 复制生成的内容
3. 打开 Streamlit Cloud → 你的 App → 右上角 **⋮** → **Settings** → **Secrets**
4. 粘贴内容（追加，不要删除已有的 `APP_PASSWORD` 行）
5. 点击 **Save** → App 自动重启 → 收藏夹自动恢复 ✅
        """)
        if st.button("🔧 生成 Secrets 配置", type="primary", key="gen_secrets"):
            hint = storage.save_to_secrets_hint()
            st.code(hint, language="toml")
            st.info("⬆️ 复制以上内容，粘贴到 Streamlit Cloud Settings → Secrets 中保存。")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📤 导入备份文件")
    uploaded = st.file_uploader("选择备份 JSON 文件", type=["json"], key="wl_import_file")
    if uploaded:
        merge_mode = st.radio(
            "导入方式",
            ["合并（新增不存在的，保留已有的）", "替换（清空现有收藏，完全替换）"],
            key="wl_import_mode",
        )
        if st.button("✅ 确认导入", type="primary", key="wl_do_import"):
            try:
                ok, msg = storage.import_watchlist_json(
                    uploaded.read().decode("utf-8"), merge=("合并" in merge_mode)
                )
                if ok: st.success(f"✅ {msg}"); st.rerun()
                else:  st.error(f"❌ {msg}")
            except Exception as e:
                st.error(f"❌ 导入失败：{e}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🗄️ 本地自动备份记录")
    baks    = storage.list_backups()
    wl_baks = [b for b in baks if "data_watchlist" in b[0] and "archive" not in b[0]]
    if not wl_baks:
        st.info("暂无本地备份（添加或删除收藏品种后自动生成）")
    else:
        for fname, fpath, size_kb, mtime in wl_baks[:10]:
            ci, cb = st.columns([7, 2])
            with ci:
                st.markdown(
                    f'<span style="font-family:monospace;font-size:12px">{_he(fname)}</span>'
                    f'<span style="color:#9ca3af;font-size:11px;margin-left:12px">'
                    f'{_he(str(mtime))} · {max(size_kb,1)} KB</span>',
                    unsafe_allow_html=True,
                )
            with cb:
                if st.button("🔄 从此备份恢复", key=f"bak_restore_{fname}"):
                    ok, msg = storage.restore_from_backup_file(fpath, merge=True)
                    if ok: st.success(f"✅ {msg}"); st.rerun()
                    else:  st.error(f"❌ {msg}")
