"""pages/page_history.py — 历史记录页面"""

import io
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from core.supabase_client import get_sessions, get_results, get_results_by_date


def render():
    st.markdown("## 📂 历史扫描记录")
    st.markdown("按日期浏览每次扫描存档，支持区间筛选与 CSV 下载。")

    # ── 日期筛选 ─────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        date_from = st.date_input("开始日期", value=date.today() - timedelta(days=30))
    with col2:
        date_to = st.date_input("结束日期", value=date.today())
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        col3a, col3b = st.columns(2)
        with col3a:
            search_btn = st.button("🔍 查询", use_container_width=True, type="primary")
        with col3b:
            dl_range = st.button("⬇️ 下载区间 CSV", use_container_width=True)

    # ── 下载日期区间数据 ──────────────────────────────────────────
    if dl_range:
        rows = get_results_by_date(str(date_from), str(date_to))
        if not rows:
            st.warning("该日期区间内无数据")
        else:
            df_dl = pd.DataFrame(rows)
            buf = io.BytesIO()
            df_dl.to_csv(buf, index=False, encoding="utf-8-sig")
            st.download_button(
                f"📥 下载 {date_from} ~ {date_to} CSV ({len(rows)} 条)",
                data=buf.getvalue(),
                file_name=f"fibo_{date_from}_{date_to}.csv",
                mime="text/csv",
            )

    st.divider()

    # ── 批次列表 ─────────────────────────────────────────────────
    sessions = get_sessions(str(date_from), str(date_to), limit=100)

    if not sessions:
        st.info("该日期范围内无历史记录。请先运行扫描，或调整日期范围。")
        return

    st.markdown(f"**找到 {len(sessions)} 条扫描记录**")

    # ── 列表 + 详情 ───────────────────────────────────────────────
    left, right = st.columns([1, 2])

    with left:
        st.markdown("**📋 扫描批次**")
        selected_sid = st.session_state.get("selected_session")

        for s in sessions:
            inz   = s.get("inzone_count", 0)
            total = s.get("total_checks", 0)
            triple = s.get("triple_conf", 0)
            t     = (s.get("scan_time") or "")[:16].replace("T", " ")
            label = f"{s['scan_date']}  {t[11:16]}"

            is_sel = (selected_sid == s["session_id"])
            border = "2px solid #e85d04" if is_sel else "1px solid #e2e6ea"
            bg     = "#fff7ed" if is_sel else "white"

            st.markdown(f"""
            <div style="border:{border};background:{bg};border-radius:8px;
                        padding:10px 14px;margin-bottom:8px;cursor:pointer">
              <div style="font-weight:700;font-size:13px">{label}</div>
              <div style="font-size:11px;color:#6b7280;font-family:'IBM Plex Mono',monospace">
                {total} 次检查 ·
                <span style="color:#0d9488;font-weight:700">{inz} 区间内</span>
                {f'· <span style="color:#dc2626">🔥×3: {triple}</span>' if triple else ''}
              </div>
              <div style="font-size:10px;color:#9ca3af;margin-top:2px">{s.get('note','')[:50]}</div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"查看详情", key=f"sel_{s['session_id']}", use_container_width=True):
                st.session_state.selected_session = s["session_id"]
                st.rerun()

    with right:
        sid = st.session_state.get("selected_session")
        if not sid:
            st.markdown('<div class="notice-info">👈 点击左侧批次查看详情</div>', unsafe_allow_html=True)
            return

        # 找到对应 session 信息
        sess_info = next((s for s in sessions if s["session_id"] == sid), None)
        rows = get_results(sid)
        if not rows:
            st.warning("该批次无结果数据")
            return

        df = pd.DataFrame(rows)
        inzone_df = df[df["in_zone"] == True]

        # 摘要
        if sess_info:
            st.markdown(f"### 📋 {sess_info['scan_date']} 扫描详情")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("总检查", sess_info.get("total_checks", len(df)))
            c2.metric("区间内", sess_info.get("inzone_count", len(inzone_df)),
                      delta=f"+{len(inzone_df)}" if len(inzone_df) > 0 else None)
            c3.metric("三框架共振", sess_info.get("triple_conf", 0))
            c4.metric("耗时", f"{sess_info.get('duration_ms',0)}ms")

        # 下载该批次
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ 下载此批次 CSV",
            data=buf.getvalue(),
            file_name=f"fibo_{sid}.csv",
            mime="text/csv",
        )

        # 切换：全部 / 仅区间内
        show_all = st.checkbox("显示全部结果（含未在区间内）", value=False)
        display_df = df if show_all else inzone_df

        if display_df.empty:
            st.info("该批次没有处于黄金区间的信号")
            return

        # 精简展示列
        cols = ["ticker", "name", "timeframe", "in_zone",
                "current_price", "zone_top", "zone_bot",
                "retrace_pct", "dist_pct", "confluence_label"]
        display_df = display_df[[c for c in cols if c in display_df.columns]].copy()
        display_df.columns = [
            "Ticker","名称","框架","区间内","价格",
            "Fibo 0.500","Fibo 0.618","回撤%","距区间%","共振"
        ][:len(display_df.columns)]

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
        )
