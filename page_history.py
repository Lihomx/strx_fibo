"""
page_history.py - 历史扫描记录
"""
import pandas as pd
import streamlit as st

import storage


def render():
    st.markdown("## 📂 历史扫描记录")

    sessions = storage.load_sessions(limit=30)
    sessions = [s for s in sessions if isinstance(s, dict) and s.get("session_id")]
    if not sessions:
        st.markdown('<div class="n-info">💡 暂无历史记录，请先执行扫描。</div>',
                    unsafe_allow_html=True)
        return

    st.markdown(f'<div class="n-ok">共 {len(sessions)} 次扫描记录（最多保留 30 次）</div>',
                unsafe_allow_html=True)

    options = {
        f"{s.get('scan_time', '?')} — 黄金区 {s.get('inzone_count', 0)} / 三共振 {s.get('triple_conf', 0)}": s["session_id"]
        for s in sessions
    }
    selected_label = st.selectbox("选择扫描记录", list(options.keys()))
    selected_sid = options[selected_label]
    sel_sess = next(s for s in sessions if s["session_id"] == selected_sid)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("扫描时间", sel_sess.get("scan_date", "—"))
    with c2:
        st.metric("黄金区间", sel_sess.get("inzone_count", 0))
    with c3:
        st.metric("三框架共振", sel_sess.get("triple_conf", 0))
    with c4:
        dur = sel_sess.get("duration_ms", 0)
        st.metric("耗时", f"{dur/1000:.1f}s" if dur else "—")

    st.caption(
        f"数据源: {sel_sess.get('data_source', 'yfinance')}  |  "
        f"总检查: {sel_sess.get('total_checks', 0)}  |  "
        f"Session ID: {selected_sid[:20]}…"
    )

    raw_rows = storage.load_session_results(session_id=selected_sid)
    has_snap = storage.has_scan_snapshot(selected_sid)
    if has_snap:
        st.caption("✅ 该批次有完整快照，可一键恢复到实时扫描面板。")
    else:
        st.caption("⚠️ 该批次暂无独立快照，建议先补建快照。")

    a1, a2 = st.columns([3, 2])
    with a1:
        if st.button("♻️ 恢复该批次到实时扫描", type="primary",
                     key=f"restore_scan_{selected_sid}", disabled=not has_snap):
            ok, msg, n = storage.restore_scan_snapshot(selected_sid, replace_allres=True)
            if ok:
                st.session_state["_scanner_restore_notice"] = f"已恢复批次 {selected_sid[:12]}…（{n} 条）"
                st.session_state["page"] = "scanner"
                st.rerun()
            st.error(msg)
    with a2:
        if (not has_snap) and st.button("💾 补建快照", key=f"build_snap_{selected_sid}",
                                        disabled=(len(raw_rows) == 0)):
            if storage.save_scan_snapshot(sel_sess, raw_rows):
                st.success("快照已保存，可立即恢复。")
                st.rerun()
            else:
                st.error("快照保存失败。")

    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        zone_only = st.checkbox("仅黄金区间", value=True)
    with col2:
        tf_sel = st.selectbox("框架", ["全部", "Daily", "Weekly", "Monthly"],
                              key="hist_tf", label_visibility="collapsed")
    with col3:
        cat_sel = st.selectbox("类别",
                               ["全部", "commodity", "forex", "index", "stock", "crypto"],
                               key="hist_cat", label_visibility="collapsed")

    rows = raw_rows
    if zone_only:
        rows = [r for r in rows if r.get("in_zone")]
    df = pd.DataFrame(rows)

    if df.empty:
        st.info("该次扫描暂无数据")
        return

    if tf_sel != "全部":
        df = df[df["timeframe"] == tf_sel]
    if cat_sel != "全部":
        df = df[df["category"] == cat_sel]
    if df.empty:
        st.info("过滤后无数据")
        return

    display_cols = {
        "name": "资产名称", "ticker": "代码",
        "category": "类别", "timeframe": "框架",
        "in_zone": "黄金区", "current_price": "当前价格",
        "retrace_pct": "回撤%", "dist_pct": "距区间%",
        "nearest_fibo": "最近Fibo", "confluence_label": "共振信号",
        "swing_high": "结构高点", "swing_low": "结构低点",
    }
    show_df = df[[c for c in display_cols if c in df.columns]].copy()
    show_df.rename(columns=display_cols, inplace=True)

    for col in ["回撤%", "距区间%"]:
        if col in show_df.columns:
            show_df[col] = show_df[col].apply(
                lambda x: f"{x:.2f}" if x is not None and x != "" else "—"
            )
    if "最近Fibo" in show_df.columns:
        show_df["最近Fibo"] = show_df["最近Fibo"].apply(
            lambda x: f"{x:.3f}" if x is not None else "—"
        )
    for col in ["当前价格", "结构高点", "结构低点"]:
        if col in show_df.columns:
            show_df[col] = show_df[col].apply(
                lambda x: f"{x:,.4f}" if x is not None else "—"
            )

    st.dataframe(show_df, width="stretch", height=420)
    st.caption(f"共 {len(df)} 条")

    st.download_button(
        "⬇️ 下载此次扫描 CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"strx_{selected_sid[:15]}.csv",
        mime="text/csv",
    )

    with st.expander("📦 下载全部历史数据"):
        all_rows = storage.load_latest_results(inzone_only=False)
        if all_rows:
            all_df = pd.DataFrame(all_rows)
            st.download_button(
                "⬇️ 下载全部历史 CSV",
                all_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="strx_all_history.csv",
                mime="text/csv",
            )
            st.caption(f"全部历史：{len(all_df)} 条记录")
