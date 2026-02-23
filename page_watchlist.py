"""
page_watchlist.py — 自选收藏夹
功能：
  - 备注：文字（必填）+ 图片链接（选填）+ 自动时间戳，历史全量保留
  - 图片链接显示缩略图，点击跳转大图
  - 删除 = 软删除，可从存档恢复
  - 最新备注标红显示
  - TradingView 跳转按钮
"""

from datetime import datetime
import streamlit as st
import pandas as pd

import storage
from assets import tv_url as _tv_url


# ════════════════════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════════════════════
def _tv_link(ticker: str) -> str:
    try:
        return _tv_url(ticker)
    except Exception:
        return f"https://www.tradingview.com/chart/?symbol={ticker}"


def _thumb_html(img_url: str, max_w: int = 120) -> str:
    """将图片链接渲染为可点击的缩略图 HTML。"""
    if not img_url:
        return ""
    return (
        f'<a href="{img_url}" target="_blank" title="点击查看大图">'
        f'<img src="{img_url}" style="max-width:{max_w}px;max-height:90px;'
        f'border-radius:6px;border:1px solid #e5e7eb;object-fit:cover;'
        f'vertical-align:middle;margin-top:4px" '
        f'onerror="this.style.display=\'none\'">'
        f'</a>'
    )


def _latest_note(item: dict) -> dict | None:
    notes = item.get("notes", [])
    if not notes:
        # 兼容旧格式
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
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## ⭐ 自选收藏夹")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '收藏重点品种，保存多条带图备注，支持随时查看 Fibonacci 状态。</p>',
        unsafe_allow_html=True,
    )

    # ── Tab：收藏 / 存档 / 备份 ────────────────────────────────
    tab_main, tab_archive, tab_backup = st.tabs(
        ["⭐ 当前收藏", "🗂️ 已删除存档", "💾 备份与恢复"]
    )

    with tab_main:
        _render_main()

    with tab_archive:
        _render_archive()

    with tab_backup:
        _render_backup()


# ════════════════════════════════════════════════════════════════════
# 当前收藏
# ════════════════════════════════════════════════════════════════════
def _render_main():
    items = storage.load_watchlist()

    # ── 添加新品种 ──────────────────────────────────────────────
    with st.expander("➕ 添加新品种", expanded=len(items) == 0):
        c1, c2 = st.columns([2, 2])
        with c1:
            new_ticker = st.text_input(
                "Ticker 代码 *", placeholder="例: AAPL  600519.SS  0700.HK",
                key="wl_new_ticker",
            ).strip().upper()
        with c2:
            new_name = st.text_input(
                "品种全称（可选）", placeholder="例: 苹果公司 / 贵州茅台",
                key="wl_new_name",
            )
        note_text = st.text_input(
            "📝 备注 *（必填）", placeholder="例: 关注 0.618 支撑，等待回踩确认",
            key="wl_new_note_text",
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
                st.warning("备注为必填项，请输入备注内容")
            else:
                ok = storage.add_to_watchlist(new_ticker, new_name, note_text.strip(), img_url)
                if ok:
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
                if not parts:
                    continue
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

    # 刷新 items
    items = storage.load_watchlist()

    if not items:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;color:#9ca3af;">
          <div style="font-size:48px">⭐</div>
          <div style="font-size:16px;font-weight:600;margin:12px 0 6px;color:#374151">收藏夹为空</div>
          <div style="font-size:13px">点击上方「添加新品种」开始收藏</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 扫描结果缓存
    all_results = storage.load_latest_results()
    result_map: dict = {}
    for r in all_results:
        tk = r.get("ticker", "").upper()
        result_map.setdefault(tk, []).append(r)

    # 工具栏
    col_l, col_r = st.columns([6, 2])
    with col_l:
        search = st.text_input(
            "🔍 搜索", placeholder="按 Ticker 或名称过滤…",
            key="wl_search", label_visibility="collapsed"
        )
    with col_r:
        if st.button("🗑️ 清空收藏夹", key="wl_clear_all"):
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

    q = search.strip().upper()
    display_items = items
    if q:
        display_items = [
            i for i in items
            if q in i["ticker"].upper() or q in i.get("name", "").upper()
        ]

    # ── 置顶排序：pinned=True 的排在前面 ──────────────────────
    display_items = sorted(display_items, key=lambda x: (0 if x.get("pinned") else 1))

    pinned_cnt = sum(1 for i in display_items if i.get("pinned"))
    st.markdown(
        f"<div style='color:#6b7280;font-size:12px;margin-bottom:8px'>"
        f"共 {len(items)} 个品种 · 显示 {len(display_items)} 个"
        + (f" · 📌 {pinned_cnt} 个置顶" if pinned_cnt else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── 品种卡片 ────────────────────────────────────────────────
    for idx, item in enumerate(display_items):
        _render_card(item, idx, result_map)

    # ── 导出 ─────────────────────────────────────────────────────
    st.markdown("---")
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        rows = []
        for item in items:
            tk     = item["ticker"]
            results = result_map.get(tk, [])
            latest  = _latest_note(item)
            rows.append({
                "ticker":      tk,
                "name":        item.get("name", ""),
                "latest_note": latest["text"] if latest else "",
                "added_at":    item.get("added_at", ""),
                "pinned":      item.get("pinned", False),
                "in_zone_any": any(r.get("in_zone") for r in results),
            })
        df = pd.DataFrame(rows)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 导出收藏夹 CSV", csv,
                           file_name="strx_watchlist.csv", mime="text/csv",
                           key="wl_dl")
    with exp_col2:
        ticker_list = "\n".join(i["ticker"] for i in items)
        st.text_area("Ticker 列表（可复制）", value=ticker_list, height=80,
                     key="wl_ticker_list")


# ════════════════════════════════════════════════════════════════════
# 单张品种卡片
# 修改：
#   1. 第一行优先显示品种全称（name），再显示 ticker
#   2. 置顶按钮
#   3. 最新备注移到最后（添加备注按钮之前）
# ════════════════════════════════════════════════════════════════════
def _render_card(item: dict, idx: int, result_map: dict):
    ticker  = item["ticker"]
    name    = item.get("name", "")
    added   = item.get("added_at", "")
    pinned  = item.get("pinned", False)
    results = result_map.get(ticker, [])
    notes   = _all_notes(item)
    latest  = notes[-1] if notes else None
    tv_link = _tv_link(ticker)

    # 卡片边框：置顶时高亮
    border_color = "#f59e0b" if pinned else "#e5e7eb"
    pin_bg       = "background:#fffbeb;" if pinned else ""

    with st.container():
        st.markdown(
            f'<div style="background:#fff;border:1.5px solid {border_color};'
            f'border-radius:10px;padding:14px 18px 12px;margin-bottom:10px;{pin_bg}">',
            unsafe_allow_html=True,
        )

        # ── 标题行：全称 优先，Ticker 次之 ──────────────────────
        col_title, col_actions = st.columns([7, 3])

        with col_title:
            # 优先显示全称，没有全称时显示 ticker
            if name:
                # 有全称：大字显示全称，小字显示 ticker
                pin_icon = "📌 " if pinned else ""
                st.markdown(
                    f"<div style='margin-bottom:2px'>"
                    f"<span style='font-size:16px;font-weight:700;color:#111'>{pin_icon}{name}</span>&nbsp;&nbsp;"
                    f"<span style='font-family:monospace;font-size:12px;color:#9ca3af;"
                    f"background:#f3f4f6;padding:2px 6px;border-radius:4px'>{ticker}</span>"
                    f"</div>"
                    f"<span style='color:#9ca3af;font-size:11px'>收藏于 {added}</span>",
                    unsafe_allow_html=True,
                )
            else:
                # 没有全称：直接显示 ticker
                pin_icon = "📌 " if pinned else ""
                st.markdown(
                    f"<div style='margin-bottom:2px'>"
                    f"<span style='font-size:16px;font-weight:700;font-family:monospace;color:#111'>{pin_icon}{ticker}</span>"
                    f"</div>"
                    f"<span style='color:#9ca3af;font-size:11px'>收藏于 {added}</span>",
                    unsafe_allow_html=True,
                )

        with col_actions:
            # 操作按钮：置顶 + TV + 扫描 + 删除
            btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)
            with btn_c1:
                pin_label = "📌" if not pinned else "🔓"
                pin_help  = "置顶此品种" if not pinned else "取消置顶"
                if st.button(pin_label, key=f"wl_pin_{ticker}_{idx}", help=pin_help):
                    storage.toggle_pin_watchlist(ticker)
                    st.rerun()
            with btn_c2:
                st.link_button("📈", tv_link, help=f"在 TradingView 查看 {ticker}")
            with btn_c3:
                if st.button("🔍", key=f"wl_scan_{ticker}_{idx}",
                             help=f"跳转扫描 {ticker}"):
                    st.session_state["page"] = "scanner"
                    st.session_state["wl_jump_ticker"] = ticker
                    st.rerun()
            with btn_c4:
                if st.button("🗑", key=f"wl_del_{ticker}_{idx}",
                             help=f"删除（移入存档）{ticker}"):
                    storage.remove_from_watchlist(ticker)
                    st.toast(f"已移入存档：{ticker}", icon="🗂️")
                    st.rerun()

        # ── Fibo 状态 ──────────────────────────────────────────
        if results:
            fibo_cols = st.columns(min(len(results), 4))
            for ci, res in enumerate(results[:4]):
                with fibo_cols[ci]:
                    tf       = res.get("timeframe", "?")
                    dist     = res.get("dist_pct")
                    in_zone  = res.get("in_zone", False)
                    fib_val  = res.get("nearest_fibo", res.get("nearest_fib", ""))
                    dist_str = f"{dist:.1f}%" if dist is not None else "—"
                    fib_str  = str(fib_val) if fib_val else "—"
                    bg       = "#fef9c3" if in_zone else "#f9fafb"
                    bd       = "#fde047" if in_zone else "#e5e7eb"
                    icon     = "⚡" if in_zone else "·"
                    st.markdown(
                        f'<div style="background:{bg};border:1px solid {bd};'
                        f'border-radius:8px;padding:6px 10px;text-align:center;font-size:11px;">'
                        f'<div style="font-weight:700;color:#374151">{tf}</div>'
                        f'<div style="color:#e85d04;font-weight:600">{fib_str}</div>'
                        f'<div style="color:#6b7280">{icon} {dist_str}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                '<span style="color:#9ca3af;font-size:12px">'
                '暂无扫描数据 · 请先在扫描页扫描该品种</span>',
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # ── 历史备注（折叠展示） ──────────────────────────────────
        older = notes[:-1]  # 除最后一条之外的历史备注
        if older:
            with st.expander(f"📋 查看历史备注（共 {len(older)} 条）"):
                for n in reversed(older):
                    thumb = _thumb_html(n.get("img_url", ""), 120)
                    st.markdown(
                        f'<div style="border-left:2px solid #e5e7eb;'
                        f'padding:5px 10px;margin:4px 0;font-size:12px;">'
                        f'<span style="color:#9ca3af">{n.get("ts","")}</span>&nbsp;&nbsp;'
                        f'<span style="color:#374151">{n["text"]}</span>'
                        f'{("<br>" + thumb) if thumb else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── 添加新备注按钮 ──────────────────────────────────────
        if st.button("✏️ 添加备注", key=f"wl_edit_btn_{ticker}_{idx}",
                     use_container_width=False):
            st.session_state[f"wl_adding_{ticker}"] = True

        if st.session_state.get(f"wl_adding_{ticker}"):
            new_text = st.text_input(
                "备注内容 *（必填）",
                key=f"wl_note_text_{ticker}_{idx}",
                placeholder="输入本次备注…",
            )
            new_img = st.text_input(
                "图片链接（选填）",
                key=f"wl_note_img_{ticker}_{idx}",
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

        # ── 最新备注（标红，放在最后）─────────────────────────────
        if latest:
            thumb = _thumb_html(latest.get("img_url", ""), 140)
            st.markdown(
                f'<div style="background:#fff1f2;border-left:3px solid #ef4444;'
                f'border-radius:0 6px 6px 0;padding:7px 12px;margin:6px 0 2px;">'
                f'<span style="color:#ef4444;font-size:11px;font-weight:600">'
                f'📝 最新备注 · {latest.get("ts","")}</span><br>'
                f'<span style="color:#1f2937;font-size:13px">{latest["text"]}</span>'
                f'{("<br>" + thumb) if thumb else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)


def _render_archive():
    archive = storage.load_watchlist_archive()

    if not archive:
        st.markdown("""
        <div style="text-align:center;padding:40px;color:#9ca3af;">
          <div style="font-size:36px">🗂️</div>
          <div style="font-size:14px;margin-top:8px">暂无已删除品种</div>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown(
        f'<p style="color:#6b7280;font-size:13px">共 {len(archive)} 个已删除品种，'
        f'可一键恢复（含所有历史备注）。</p>',
        unsafe_allow_html=True,
    )

    for idx, item in enumerate(reversed(archive)):
        ticker     = item["ticker"]
        name       = item.get("name", "")
        deleted_at = item.get("deleted_at", "")
        notes      = _all_notes(item)
        latest     = notes[-1] if notes else None

        col_info, col_btn = st.columns([8, 2])
        with col_info:
            name_part = f" — {name}" if name else ""
            st.markdown(
                f"<b>{ticker}</b>{name_part}  "
                f"<span style='color:#9ca3af;font-size:11px'>删除于 {deleted_at}</span>",
                unsafe_allow_html=True,
            )
            if latest:
                st.markdown(
                    f'<span style="color:#6b7280;font-size:12px">'
                    f'最后备注：{latest["text"][:60]}{"…" if len(latest["text"])>60 else ""}'
                    f'</span>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                f'<span style="color:#9ca3af;font-size:11px">'
                f'共 {len(notes)} 条备注</span>',
                unsafe_allow_html=True,
            )

        with col_btn:
            if st.button("🔄 恢复", key=f"arch_restore_{ticker}_{idx}",
                         type="primary"):
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
# 备份与恢复
# ════════════════════════════════════════════════════════════════════
def _render_backup():
    items = storage.load_watchlist()
    n = len(items)

    # ── 当前状态 ────────────────────────────────────────────────
    st.markdown(f"### 📊 当前状态：共 **{n}** 个收藏品种")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            '<div class="m-card teal"><div class="m-lbl">当前收藏</div>'
            f'<div class="m-val">{n}</div>'
            '<div class="m-sub">个品种</div></div>',
            unsafe_allow_html=True,
        )
    with col_b:
        baks = storage.list_backups()
        wl_baks = [b for b in baks if "data_watchlist" in b[0]]
        st.markdown(
            '<div class="m-card blue"><div class="m-lbl">本地备份</div>'
            f'<div class="m-val">{len(wl_baks)}</div>'
            '<div class="m-sub">个文件</div></div>',
            unsafe_allow_html=True,
        )
    with col_c:
        total_notes = sum(len(i.get("notes", [])) for i in items)
        st.markdown(
            '<div class="m-card gold"><div class="m-lbl">备注总数</div>'
            f'<div class="m-val">{total_notes}</div>'
            '<div class="m-sub">条备注</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 方案1：手动下载 JSON
    # ════════════════════════════════════════════════════════════
    st.markdown("### 📥 方案1：下载备份文件（推荐，最简单）")
    st.markdown(
        '<div class="n-info">'
        '每次修改收藏夹后，点击下方按钮下载 JSON 文件保存到本地。'
        '下次重启后可通过「导入」功能恢复。'
        '</div>',
        unsafe_allow_html=True,
    )

    json_str = storage.export_watchlist_json()
    import time as _time
    ts = _time.strftime("%Y%m%d_%H%M")
    st.download_button(
        label=f"⬇️ 下载收藏夹备份 JSON（{n}个品种）",
        data=json_str.encode("utf-8"),
        file_name=f"strx_watchlist_backup_{ts}.json",
        mime="application/json",
        type="primary",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 方案2：Streamlit Secrets 永久持久化
    # ════════════════════════════════════════════════════════════
    st.markdown("### 🔐 方案2：Streamlit Secrets 永久持久化（推荐，自动恢复）")
    st.markdown(
        '<div class="n-ok">'
        '✅ <b>最佳方案</b>：将收藏夹编码存入 Streamlit Secrets，<br>'
        '每次 App 重启时<b>自动恢复</b>，无需手动操作。'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("📋 查看操作步骤", expanded=True):
        st.markdown("""
**操作步骤：**
1. 点击下方「生成 Secrets 配置」按钮
2. 复制生成的内容
3. 打开 Streamlit Cloud → 你的 App → 右上角 **⋮** → **Settings** → **Secrets**
4. 粘贴内容（追加，不要删除已有的 `APP_PASSWORD` 行）
5. 点击 **Save** → App 自动重启 → 收藏夹自动恢复 ✅

> **注意**：每次修改收藏夹后，需重新执行一次此操作更新 Secrets。
        """)

        if st.button("🔧 生成 Secrets 配置", type="primary", key="gen_secrets"):
            hint = storage.save_to_secrets_hint()
            st.code(hint, language="toml")
            st.info(
                "⬆️ 复制以上内容，粘贴到 Streamlit Cloud Settings → Secrets 中保存。"
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 方案3：从文件恢复
    # ════════════════════════════════════════════════════════════
    st.markdown("### 📤 导入备份文件（从之前下载的 JSON 恢复）")

    uploaded = st.file_uploader(
        "选择备份 JSON 文件",
        type=["json"],
        key="wl_import_file",
        help="上传之前导出的 strx_watchlist_backup_*.json 文件",
    )

    if uploaded:
        merge_mode = st.radio(
            "导入方式",
            ["合并（新增不存在的，保留已有的）", "替换（清空现有收藏，完全替换）"],
            key="wl_import_mode",
        )
        merge = "合并" in merge_mode

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 确认导入", type="primary", key="wl_do_import"):
                try:
                    json_str_up = uploaded.read().decode("utf-8")
                    ok, msg = storage.import_watchlist_json(json_str_up, merge=merge)
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
                except Exception as e:
                    st.error(f"❌ 导入失败：{e}")
        with col2:
            # Preview
            try:
                import json
                preview_str = uploaded.read()  # may already be read above
            except Exception:
                preview_str = b""

    st.markdown("<br>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════
    # 本地自动备份列表
    # ════════════════════════════════════════════════════════════
    st.markdown("### 🗄️ 本地自动备份记录（每次修改收藏夹自动创建）")
    st.markdown(
        '<div class="n-info">'
        '每次添加/删除收藏品种时，系统自动在 <code>backups/</code> 目录'
        '保留一份带时间戳的备份（最多保留30个）。'
        '<br>⚠️ Streamlit Cloud 重启后本地文件会丢失，请优先使用「下载备份」或「Secrets 持久化」。'
        '</div>',
        unsafe_allow_html=True,
    )

    baks = storage.list_backups()
    wl_baks = [b for b in baks if "data_watchlist" in b[0] and "archive" not in b[0]]

    if not wl_baks:
        st.info("暂无本地备份（添加或删除收藏品种后自动生成）")
    else:
        for fname, fpath, size_kb, mtime in wl_baks[:10]:
            col_info, col_btn = st.columns([7, 2])
            with col_info:
                st.markdown(
                    f'<span style="font-family:monospace;font-size:12px">{fname}</span>'
                    f'<span style="color:#9ca3af;font-size:11px;margin-left:12px">'
                    f'{mtime} · {max(size_kb,1)} KB</span>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    "🔄 从此备份恢复",
                    key=f"bak_restore_{fname}",
                    help=f"从 {fname} 合并恢复数据",
                ):
                    ok, msg = storage.restore_from_backup_file(fpath, merge=True)
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
