"""
page_scanner.py — 实时扫描（支持分批扫描）
"""
import pandas as pd
import streamlit as st

import storage
import scanner as sc
from assets import ASSET_GROUPS, TIMEFRAMES


def _badge(in_zone: bool, dist: float) -> str:
    if in_zone:
        return '<span class="badge b-green">✅ 黄金区</span>'
    if dist < 5:
        return '<span class="badge b-yellow">👀 接近</span>'
    return '<span class="badge b-gray">—</span>'


def _conf_badge(label: str) -> str:
    if "三" in label:
        return f'<span class="badge b-red">{label}</span>'
    if "双" in label:
        return f'<span class="badge b-orange">{label}</span>'
    if "单" in label or "接近" in label:
        return f'<span class="badge b-yellow">{label}</span>'
    return f'<span class="badge b-gray">{label}</span>'


def render():
    st.markdown("## 📊 Fibonacci 实时扫描")

    cfg = storage.load_config()

    # ── 分批扫描控制区 ───────────────────────────────────────────────
    with st.expander("📦 选择扫描品种组（分批扫描）", expanded=True):
        group_names = list(ASSET_GROUPS.keys())
        total_assets = sum(len(g) for g in ASSET_GROUPS.values())

        st.markdown(
            f'<div class="n-info">💡 共 <b>{total_assets}</b> 个品种，分 <b>{len(group_names)}</b> 组。'
            f'每批约 15-32 个品种 × 3 框架，单批扫描约 1-2 分钟。'
            f'可选一组或多组，结果自动合并缓存。</div>',
            unsafe_allow_html=True
        )

        col_sel, col_all = st.columns([5, 1])
        with col_all:
            if st.button("☑️ 全选", use_container_width=True):
                st.session_state["scan_groups"] = group_names
            if st.button("🔲 清空", use_container_width=True):
                st.session_state["scan_groups"] = []

        default_sel = st.session_state.get("scan_groups", [group_names[0]])
        selected_groups = st.multiselect(
            "选择品种组",
            options=group_names,
            default=default_sel,
            label_visibility="collapsed",
            key="scan_groups_widget",
        )
        st.session_state["scan_groups"] = selected_groups

        if selected_groups:
            sel_assets = {}
            for g in selected_groups:
                sel_assets.update(ASSET_GROUPS[g])
            checks = len(sel_assets) * len(TIMEFRAMES)
            st.caption(f"已选 {len(sel_assets)} 个品种 × 3 框架 = {checks} 次检查")
        else:
            sel_assets = {}
            st.warning("请至少选择一组品种")

    # ── 操作栏 ──────────────────────────────────────────────────────
    col_btn, col_kw, col_tf, col_cat, col_zone = st.columns([2,3,2,2,2])
    with col_btn:
        do_scan = st.button(
            f"🚀 扫描 ({len(sel_assets)} 品种)" if sel_assets else "🚀 开始扫描",
            type="primary", use_container_width=True,
            disabled=not sel_assets
        )
    with col_kw:
        kw = st.text_input("🔍", placeholder="搜索名称/代码…", label_visibility="collapsed")
    with col_tf:
        tf_sel = st.selectbox("框架", ["全部","Daily","Weekly","Monthly"],
                              label_visibility="collapsed")
    with col_cat:
        all_cats = ["全部","futures","index","forex","us_stock","cn_stock","a_stock","crypto"]
        cat_sel = st.selectbox("类别", all_cats, label_visibility="collapsed")
    with col_zone:
        zone_only = st.checkbox("仅黄金区", value=False)

    # ── 扫描执行 ─────────────────────────────────────────────────────
    if do_scan and sel_assets:
        pb  = st.progress(0, "准备中…")
        msg = st.empty()

        def cb(pct, text):
            pb.progress(min(pct, 1.0), text)
            msg.caption(text)

        group_label = "、".join(selected_groups[:3]) + (
            f" 等{len(selected_groups)}组" if len(selected_groups) > 3 else ""
        )

        with st.spinner(""):
            summary, err = sc.run_full_scan(
                cfg=cfg,
                assets=sel_assets,
                note=f"manual_{group_label}",
                progress_callback=cb,
            )

        pb.empty(); msg.empty()
        if err:
            st.error(err)
        else:
            st.success(
                f"✅ 完成！共 **{summary['asset_count']}** 个品种  |  "
                f"黄金区 **{summary['inzone_count']}** 个  |  "
                f"三框架共振 **{summary['triple_conf']}** 个  |  "
                f"耗时 {summary['elapsed_ms']/1000:.1f}s"
            )
            st.rerun()

    # ── 展示区 ───────────────────────────────────────────────────────
    if not storage.has_scan_data():
        st.markdown('<div class="n-info">💡 尚无扫描数据，请选择品种组后点击「🚀 扫描」。</div>',
                    unsafe_allow_html=True)
        _show_metrics(0, 0, 0, 0)
        return

    rows     = storage.load_latest_results(inzone_only=False)
    sessions = storage.load_sessions(limit=1)
    last_s   = sessions[0] if sessions else {}

    total   = len(set(r["ticker"] for r in rows))
    inzone  = sum(1 for r in rows if r["in_zone"])
    near    = sum(1 for r in rows
                  if not r["in_zone"] and (r.get("dist_pct") or 999) < 5)
    triple  = last_s.get("triple_conf", 0)
    _show_metrics(total, inzone, near, triple)

    note_txt = last_s.get("note","")
    st.caption(
        f"📅 {last_s.get('scan_time','—')}  |  "
        f"品种: {last_s.get('asset_count', total)}  |  "
        f"数据源: {last_s.get('data_source','yfinance')}  |  "
        f"{note_txt}"
    )

    # ── 过滤 ────────────────────────────────────────────────────────
    df = pd.DataFrame(rows)
    if zone_only:   df = df[df["in_zone"]]
    if tf_sel  != "全部": df = df[df["timeframe"] == tf_sel]
    if cat_sel != "全部": df = df[df["category"]  == cat_sel]
    if kw:
        mask = (df["name"].str.contains(kw, case=False, na=False) |
                df["ticker"].str.contains(kw, case=False, na=False))
        df = df[mask]

    if df.empty:
        st.info("没有符合条件的结果")
        return

    # ── 渲染表格 ─────────────────────────────────────────────────────
    rows_html = []
    for _, r in df.iterrows():
        in_zone = bool(r.get("in_zone", False))
        dist    = r.get("dist_pct") if r.get("dist_pct") is not None else 999
        conf_l  = r.get("confluence_label", "—") or "—"
        price   = r.get("current_price")
        retrace = r.get("retrace_pct")
        tv_lnk  = r.get("tv_url", "#")

        try:    dist = float(dist)
        except: dist = 999.0

        price_s   = f"{price:,.4f}"   if price   is not None else "—"
        retrace_s = f"{retrace:.1f}%" if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        rows_html.append(
            f"<tr style='border-bottom:1px solid #f3f4f6'>"
            f"<td style='padding:8px 10px'><b>{r.get('name','')}</b><br>"
            f"<small style='color:#9ca3af;font-family:monospace'>{r.get('ticker','')}</small></td>"
            f"<td style='padding:8px 6px'><span class='badge b-gray'>{r.get('category','')}</span></td>"
            f"<td style='padding:8px 6px'><span class='badge b-gray'>{r.get('timeframe','')}</span></td>"
            f"<td style='padding:8px 6px'>{_badge(in_zone, dist)}</td>"
            f"<td style='padding:8px 10px;font-family:monospace;text-align:right'>{price_s}</td>"
            f"<td style='padding:8px 10px;text-align:right'>{retrace_s}</td>"
            f"<td style='padding:8px 10px;text-align:right'>{dist_s}</td>"
            f"<td style='padding:8px 6px'>{_conf_badge(conf_l)}</td>"
            f"<td style='padding:8px 10px'>"
            f"<a href='{tv_lnk}' target='_blank' style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
            f"</tr>"
        )

    st.markdown(f"""
    <div style="overflow-x:auto;margin-top:12px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
    <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb">
      <th style="padding:8px 10px;text-align:left">资产</th>
      <th style="padding:8px 6px;text-align:left">类别</th>
      <th style="padding:8px 6px;text-align:left">框架</th>
      <th style="padding:8px 6px;text-align:left">状态</th>
      <th style="padding:8px 10px;text-align:right">当前价格</th>
      <th style="padding:8px 10px;text-align:right">回撤%</th>
      <th style="padding:8px 10px;text-align:right">距区间</th>
      <th style="padding:8px 6px;text-align:left">共振</th>
      <th style="padding:8px 10px;text-align:left">图表</th>
    </tr>
    </thead>
    <tbody>{''.join(rows_html)}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)
    st.caption(f"共 {len(df)} 条记录")

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 下载 CSV", csv,
                       file_name=f"strx_fibo_{last_s.get('scan_date','')}.csv",
                       mime="text/csv")


def _show_metrics(total, inzone, near, triple):
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
                    f'<div class="m-sub">距离 &lt;5%</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="m-card red"><div class="m-lbl">三框架共振</div>'
                    f'<div class="m-val" style="color:#dc2626">{triple}</div>'
                    f'<div class="m-sub">最强信号</div></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
