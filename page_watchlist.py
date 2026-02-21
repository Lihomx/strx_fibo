"""
page_watchlist.py — 自选收藏夹
支持手动添加 Ticker / 备注 / 删除 / 一键扫描
"""

import streamlit as st
import pandas as pd
from storage import (
    load_watchlist, save_watchlist,
    add_to_watchlist, remove_from_watchlist, update_watchlist_note,
    load_latest_results,
)


# ── 颜色辅助 ────────────────────────────────────────────────────────
def _badge(txt: str, cls: str) -> str:
    return f'<span class="badge b-{cls}">{txt}</span>'

def _zone_badge(in_zone):
    if in_zone:
        return _badge("✦ 黄金区", "yellow")
    return _badge("区外", "gray")


def render():
    st.markdown("## ⭐ 自选收藏夹")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">收藏重点品种，随时查看 Fibonacci 状态。</p>',
        unsafe_allow_html=True,
    )

    items = load_watchlist()

    # ── 添加新品种 ─────────────────────────────────────────────────
    with st.expander("➕ 添加新品种", expanded=len(items) == 0):
        c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
        with c1:
            new_ticker = st.text_input(
                "Ticker 代码",
                placeholder="例: AAPL  600519.SS",
                key="wl_new_ticker",
            ).strip().upper()
        with c2:
            new_name = st.text_input(
                "简称（可选）",
                placeholder="例: 苹果 / 茅台",
                key="wl_new_name",
            )
        with c3:
            new_note = st.text_input(
                "备注（可选）",
                placeholder="例: 关注 0.618 支撑",
                key="wl_new_note",
            )
        with c4:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("添加", key="wl_add_btn", type="primary"):
                if not new_ticker:
                    st.warning("请输入 Ticker 代码")
                elif add_to_watchlist(new_ticker, new_name, new_note):
                    st.success(f"✅ 已添加 {new_ticker}")
                    st.rerun()
                else:
                    st.warning(f"⚠️ {new_ticker} 已在收藏夹中或格式有误")

        # 批量导入
        st.markdown("---")
        st.markdown("**批量导入**（每行一个 Ticker，可附上简称，用空格分隔）")
        bulk_text = st.text_area(
            "批量输入",
            placeholder="AAPL 苹果\nTSLA 特斯拉\n600519.SS 茅台",
            height=100,
            key="wl_bulk",
            label_visibility="collapsed",
        )
        if st.button("批量添加", key="wl_bulk_btn"):
            added, skipped = [], []
            for line in bulk_text.strip().splitlines():
                parts = line.strip().split(None, 1)
                if not parts:
                    continue
                tk = parts[0].upper()
                nm = parts[1] if len(parts) > 1 else ""
                if add_to_watchlist(tk, nm):
                    added.append(tk)
                else:
                    skipped.append(tk)
            if added:
                st.success(f"✅ 新增 {len(added)} 个：{', '.join(added)}")
            if skipped:
                st.info(f"已跳过（重复或无效）：{', '.join(skipped)}")
            if added:
                st.rerun()

    # ── 空状态 ───────────────────────────────────────────────────
    items = load_watchlist()
    if not items:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;color:#9ca3af;">
          <div style="font-size:48px">⭐</div>
          <div style="font-size:16px;font-weight:600;margin:12px 0 6px;color:#374151">收藏夹为空</div>
          <div style="font-size:13px">点击上方「添加新品种」开始收藏重点关注的标的</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── 获取已有扫描数据用于显示 Fibo 状态 ──────────────────────
    all_results = load_latest_results()
    result_map = {}   # ticker -> list of results
    for r in all_results:
        tk = r.get("ticker", "").upper()
        result_map.setdefault(tk, []).append(r)

    # ── 工具栏 ───────────────────────────────────────────────────
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
        st.warning("⚠️ 确定要清空所有收藏吗？")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("确认清空", key="wl_clear_yes", type="primary"):
                save_watchlist([])
                st.session_state["wl_confirm_clear"] = False
                st.rerun()
        with cc2:
            if st.button("取消", key="wl_clear_no"):
                st.session_state["wl_confirm_clear"] = False
                st.rerun()

    # 过滤
    q = search.strip().upper()
    display_items = items
    if q:
        display_items = [
            i for i in items
            if q in i["ticker"].upper() or q in i.get("name", "").upper()
        ]

    st.markdown(f"<div style='color:#6b7280;font-size:12px;margin-bottom:8px'>共 {len(items)} 个品种 · 显示 {len(display_items)} 个</div>", unsafe_allow_html=True)

    # ── 品种卡片列表 ─────────────────────────────────────────────
    for idx, item in enumerate(display_items):
        ticker = item["ticker"]
        name   = item.get("name", "")
        note   = item.get("note", "")
        added  = item.get("added_at", "")

        # 从扫描缓存中找最新结果
        results = result_map.get(ticker, [])
        has_data = bool(results)

        with st.container():
            st.markdown(f"""
            <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;
                        padding:14px 18px 10px;margin-bottom:8px;">
            """, unsafe_allow_html=True)

            row_top, row_actions = st.columns([7, 1])

            with row_top:
                # Ticker + Name
                display_label = f"**{ticker}**"
                if name:
                    display_label += f"  <span style='color:#6b7280;font-size:13px'>{name}</span>"
                st.markdown(display_label, unsafe_allow_html=True)

                if has_data:
                    # 显示所有时间框架的 Fibo 状态
                    cols = st.columns(min(len(results), 6))
                    for ci, res in enumerate(results[:6]):
                        with cols[ci]:
                            tf = res.get("timeframe", "?")
                            dist = res.get("dist_pct")
                            in_zone = res.get("in_zone", False)
                            fib_val = res.get("nearest_fib", "")

                            dist_str = f"{dist:.1f}%" if dist is not None else "—"
                            fib_str  = str(fib_val) if fib_val else "—"

                            zone_color = "#fef9c3" if in_zone else "#f9fafb"
                            zone_border = "#fde047" if in_zone else "#e5e7eb"
                            zone_icon = "⚡" if in_zone else "·"

                            st.markdown(f"""
                            <div style="background:{zone_color};border:1px solid {zone_border};
                                        border-radius:8px;padding:6px 10px;text-align:center;font-size:11px;">
                              <div style="font-weight:700;color:#374151">{tf}</div>
                              <div style="color:#e85d04;font-weight:600">{fib_str}</div>
                              <div style="color:#6b7280">{zone_icon} {dist_str}</div>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<span style="color:#9ca3af;font-size:12px">暂无扫描数据 · 请先在扫描页扫描该品种</span>',
                        unsafe_allow_html=True,
                    )

                # 备注行
                note_col, edit_col = st.columns([4, 2])
                with note_col:
                    if note:
                        st.markdown(
                            f'<div style="color:#6b7280;font-size:12px;margin-top:4px">📝 {note}</div>',
                            unsafe_allow_html=True,
                        )
                with edit_col:
                    if st.button("✏️ 编辑备注", key=f"wl_edit_{ticker}_{idx}"):
                        st.session_state[f"wl_editing_{ticker}"] = True

                if st.session_state.get(f"wl_editing_{ticker}"):
                    new_note_val = st.text_input(
                        "备注内容",
                        value=note,
                        key=f"wl_note_input_{ticker}_{idx}",
                        placeholder="输入备注…",
                    )
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        if st.button("保存", key=f"wl_note_save_{ticker}_{idx}", type="primary"):
                            update_watchlist_note(ticker, new_note_val)
                            st.session_state[f"wl_editing_{ticker}"] = False
                            st.rerun()
                    with ec2:
                        if st.button("取消", key=f"wl_note_cancel_{ticker}_{idx}"):
                            st.session_state[f"wl_editing_{ticker}"] = False
                            st.rerun()

            with row_actions:
                st.markdown(
                    f'<div style="color:#9ca3af;font-size:10px;text-align:right;margin-bottom:4px">{added}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("🗑", key=f"wl_del_{ticker}_{idx}", help=f"删除 {ticker}"):
                    remove_from_watchlist(ticker)
                    st.rerun()
                # 快速跳转到扫描页并预填 Ticker
                if st.button("🔍", key=f"wl_scan_{ticker}_{idx}", help=f"跳转扫描 {ticker}"):
                    st.session_state["page"] = "scanner"
                    st.session_state["wl_jump_ticker"] = ticker
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    # ── 导出功能 ─────────────────────────────────────────────────
    st.markdown("---")
    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        if st.button("📥 导出收藏夹 (CSV)", key="wl_export"):
            rows = []
            for item in items:
                ticker = item["ticker"]
                results = result_map.get(ticker, [])
                row = {
                    "ticker":   ticker,
                    "name":     item.get("name", ""),
                    "note":     item.get("note", ""),
                    "added_at": item.get("added_at", ""),
                    "timeframes_with_data": len(results),
                    "in_zone_any": any(r.get("in_zone") for r in results),
                }
                rows.append(row)
            df = pd.DataFrame(rows)
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "⬇️ 下载 CSV",
                data=csv.encode("utf-8-sig"),
                file_name="strx_watchlist.csv",
                mime="text/csv",
                key="wl_dl",
            )

    with exp_col2:
        # 一键把收藏夹 Ticker 列表复制为文本
        ticker_list = "\n".join(i["ticker"] for i in items)
        st.text_area(
            "Ticker 列表（可复制）",
            value=ticker_list,
            height=80,
            key="wl_ticker_list",
            label_visibility="visible",
        )
