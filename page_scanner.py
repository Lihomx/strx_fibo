"""
page_scanner.py — 实时扫描页面
"""
import pandas as pd
import streamlit as st

import storage
import scanner as sc


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
    if "单" in label:
        return f'<span class="badge b-yellow">{label}</span>'
    if "接近" in label:
        return f'<span class="badge b-yellow">{label}</span>'
    return f'<span class="badge b-gray">{label}</span>'


def render():
    st.markdown("## 📊 实时 Fibonacci 扫描")

    cfg = storage.load_config()

    # ── 操作栏 ──────────────────────────────────────────────────────
    col_btn, col_filter, col_tf, col_cat, col_zone = st.columns([2,3,2,2,2])
    with col_btn:
        do_scan = st.button("🚀 开始扫描", type="primary", use_container_width=True)
    with col_filter:
        kw = st.text_input("🔍 搜索", placeholder="名称 / Ticker…", label_visibility="collapsed")
    with col_tf:
        tf_sel = st.selectbox("时间框架", ["全部","Daily","Weekly","Monthly"],
                              label_visibility="collapsed")
    with col_cat:
        cat_sel = st.selectbox("类别", ["全部","commodity","forex","index","stock","crypto"],
                               label_visibility="collapsed")
    with col_zone:
        zone_only = st.checkbox("仅黄金区", value=False)

    # ── 扫描 ────────────────────────────────────────────────────────
    if do_scan:
        pb  = st.progress(0, "准备扫描…")
        msg = st.empty()
        err_box = st.empty()

        def cb(pct, text):
            pb.progress(min(pct, 1.0), text)
            msg.caption(text)

        with st.spinner(""):
            summary, err = sc.run_full_scan(cfg=cfg, progress_callback=cb)

        pb.empty(); msg.empty()
        if err:
            err_box.error(err)
        else:
            st.success(
                f"✅ 扫描完成  |  黄金区 **{summary['inzone_count']}** 个  |  "
                f"三框架共振 **{summary['triple_conf']}** 个  |  "
                f"耗时 {summary['elapsed_ms']/1000:.1f}s"
            )
            st.rerun()

    # ── 数据展示 ─────────────────────────────────────────────────────
    if not storage.has_scan_data():
        st.markdown("""
        <div class="n-info">
        💡 尚无扫描数据。点击「🚀 开始扫描」开始第一次扫描，约需 1-2 分钟。
        </div>""", unsafe_allow_html=True)
        _show_metrics(0, 0, 0, 0)
        return

    rows = storage.load_latest_results(inzone_only=False)
    sessions = storage.load_sessions(limit=1)
    last_sess = sessions[0] if sessions else {}

    # ── 指标卡 ──────────────────────────────────────────────────────
    total   = len(set(r["ticker"] for r in rows))
    inzone  = sum(1 for r in rows if r["in_zone"])
    near    = sum(1 for r in rows if not r["in_zone"] and (r.get("dist_pct") or 999) < 5)
    triple  = last_sess.get("triple_conf", 0)
    _show_metrics(total, inzone, near, triple)

    st.caption(
        f"📅 扫描时间: {last_sess.get('scan_time','—')}  |  "
        f"数据源: {last_sess.get('data_source','yfinance')}  |  "
        f"总检查: {last_sess.get('total_checks',0)} 项"
    )

    # ── 过滤 ────────────────────────────────────────────────────────
    df = pd.DataFrame(rows)
    if zone_only:
        df = df[df["in_zone"]]
    if tf_sel  != "全部":
        df = df[df["timeframe"] == tf_sel]
    if cat_sel != "全部":
        df = df[df["category"] == cat_sel]
    if kw:
        mask = (df["name"].str.contains(kw, case=False, na=False) |
                df["ticker"].str.contains(kw, case=False, na=False))
        df = df[mask]

    if df.empty:
        st.info("没有符合条件的结果")
        return

    # ── 构建展示表格 ─────────────────────────────────────────────────
    rows_html = []
    for _, r in df.iterrows():
        in_zone = r.get("in_zone", False)
        dist    = r.get("dist_pct") or 999
        conf_l  = r.get("confluence_label", "—")
        price   = r.get("current_price")
        retrace = r.get("retrace_pct")
        tv_lnk  = r.get("tv_url", "#")

        price_s   = f"{price:,.4f}"   if price   is not None else "—"
        retrace_s = f"{retrace:.1f}%" if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        rows_html.append(
            f"<tr>"
            f"<td><b>{r.get('name','')}</b><br>"
            f"<small style='color:#9ca3af'>{r.get('ticker','')}</small></td>"
            f"<td><span class='badge b-gray'>{r.get('timeframe','')}</span></td>"
            f"<td>{_badge(in_zone, dist)}</td>"
            f"<td style='font-family:monospace'>{price_s}</td>"
            f"<td>{retrace_s}</td>"
            f"<td>{dist_s}</td>"
            f"<td>{_conf_badge(conf_l)}</td>"
            f"<td><a href='{tv_lnk}' target='_blank' "
            f"style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
            f"</tr>"
        )

    table_html = f"""
    <div style="overflow-x:auto;margin-top:12px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
    <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb">
      <th style="padding:8px 10px;text-align:left">资产</th>
      <th style="padding:8px 10px;text-align:left">框架</th>
      <th style="padding:8px 10px;text-align:left">状态</th>
      <th style="padding:8px 10px;text-align:right">当前价格</th>
      <th style="padding:8px 10px;text-align:right">回撤</th>
      <th style="padding:8px 10px;text-align:right">距区间</th>
      <th style="padding:8px 10px;text-align:left">共振</th>
      <th style="padding:8px 10px;text-align:left">图表</th>
    </tr>
    </thead>
    <tbody>
    {''.join(rows_html)}
    </tbody>
    </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)
    st.caption(f"共 {len(df)} 条记录")

    # ── CSV 下载 ─────────────────────────────────────────────────────
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 下载 CSV", csv,
                       file_name=f"strx_fibo_{last_sess.get('scan_date','')}.csv",
                       mime="text/csv")


def _show_metrics(total, inzone, near, triple):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="m-card">
        <div class="m-lbl">监控资产</div>
        <div class="m-val">{total}</div>
        <div class="m-sub">×3 框架</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="m-card teal">
        <div class="m-lbl">黄金区间</div>
        <div class="m-val" style="color:#059669">{inzone}</div>
        <div class="m-sub">0.500–0.618</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="m-card gold">
        <div class="m-lbl">接近区间</div>
        <div class="m-val" style="color:#d97706">{near}</div>
        <div class="m-sub">距离 &lt;5%</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="m-card red">
        <div class="m-lbl">三框架共振</div>
        <div class="m-val" style="color:#dc2626">{triple}</div>
        <div class="m-sub">最强信号</div></div>""", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
