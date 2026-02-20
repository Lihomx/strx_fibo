"""pages/page_scanner.py — 实时扫描页面"""

import io
import streamlit as st
import pandas as pd

from core.scanner import run_full_scan, ASSETS, TIMEFRAMES, tv_url, tv_symbol
from core.supabase_client import get_results, get_latest_session_id, get_db_stats, load_config


def render():
    st.markdown("""
    <div class="main-header">
      <div class="logo-mark">F↗</div>
      <div class="header-text">
        <h1>📊 Fibonacci 黄金区间扫描器</h1>
        <p>Golden Zone 0.500–0.618 · Supabase 实时存档 · 自动告警</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 扫描控制 ──────────────────────────────────────────────────
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button("▶  立即扫描", type="primary", use_container_width=True)
    with col_info:
        stats = get_db_stats()
        latest = stats.get("latest_session")
        if latest:
            st.info(f"📅 最近扫描：**{latest['note']}** | 耗时 {latest.get('duration_ms',0)}ms")
        else:
            st.info("尚无历史数据，点击「立即扫描」开始")

    # ── 执行扫描 ──────────────────────────────────────────────────
    if run_btn:
        cfg = load_config()
        progress_bar = st.progress(0, text="准备扫描…")
        status_text  = st.empty()

        def on_progress(pct: float, msg: str):
            progress_bar.progress(min(pct, 1.0), text=msg)
            status_text.text(msg)

        with st.spinner(""):
            summary, err = run_full_scan(cfg=cfg, note="manual",
                                         progress_callback=on_progress)

        progress_bar.empty()
        status_text.empty()

        if err:
            st.error(f"❌ 扫描失败：{err}")
        else:
            st.success(
                f"✅ 扫描完成！"
                f" 共检查 **{summary['total_checks']}** 次"
                f" · 区间内 **{summary['inzone_count']}** 个"
                f" · 三框架共振 **{summary['triple_conf']}** 个"
                f" · 耗时 {summary['elapsed_ms']}ms"
            )
            st.rerun()

    # ── 加载最新数据 ──────────────────────────────────────────────
    sid = get_latest_session_id()
    if not sid:
        st.markdown('<div class="notice-warn">⚠️ 暂无扫描数据，请点击上方按钮执行首次扫描。</div>',
                    unsafe_allow_html=True)
        return

    rows = get_results(sid)
    if not rows:
        st.warning("该批次无结果")
        return

    df = pd.DataFrame(rows)

    # ── 统计卡 ───────────────────────────────────────────────────
    inzone  = df["in_zone"].sum()
    watching= df[~df["in_zone"] & (df["dist_pct"] < 5)].shape[0]
    triple  = _count_triple(df)
    assets_n= df["ticker"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    _metric(c1, "扫描资产",    str(assets_n),  "× 3 时间框架")
    _metric(c2, "🎯 处于区间", str(int(inzone)), "Golden Zone 内", "teal")
    _metric(c3, "👀 接近区间", str(watching),   "距离 <5%",        "gold")
    _metric(c4, "🔥 三框架共振",str(triple),    "D+W+M 全命中",    "red")
    _metric(c5, "总批次数",    str(get_db_stats().get("total_sessions",0)), "历史存档")

    st.markdown("---")

    # ── 过滤控件 ─────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
    with fc1:
        search = st.text_input("🔍 搜索 Ticker / 名称", placeholder="如 BTC、Gold、NVDA…")
    with fc2:
        tf_filter = st.selectbox("时间框架", ["全部","Daily","Weekly","Monthly"])
    with fc3:
        cat_filter = st.selectbox("资产类别", ["全部","commodity","forex","index","stock","crypto"])
    with fc4:
        zone_only = st.checkbox("仅显示区间内", value=False)

    # ── 应用过滤 ─────────────────────────────────────────────────
    fdf = df.copy()
    if search:
        mask = (fdf["ticker"].str.contains(search, case=False) |
                fdf["name"].str.contains(search, case=False))
        fdf = fdf[mask]
    if tf_filter != "全部":
        fdf = fdf[fdf["timeframe"] == tf_filter]
    if cat_filter != "全部":
        fdf = fdf[fdf["category"] == cat_filter]
    if zone_only:
        fdf = fdf[fdf["in_zone"] == True]

    fdf = fdf.sort_values(["confluence_score","in_zone"], ascending=[False, False])

    # ── 渲染表格 ─────────────────────────────────────────────────
    st.markdown(f"**共 {len(fdf)} 条记录**")

    _render_table(fdf)

    # ── 下载 CSV ─────────────────────────────────────────────────
    csv_buf = io.BytesIO()
    fdf.to_csv(csv_buf, index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇️ 下载当前筛选结果 CSV",
        data=csv_buf.getvalue(),
        file_name=f"fibo_scan_{sid}.csv",
        mime="text/csv",
    )


def _metric(col, label, value, sub, style=""):
    with col:
        css = f"metric-card {style}" if style else "metric-card"
        color = {"teal":"#0d9488","gold":"#b45309","red":"#dc2626","orange":"#e85d04"}.get(style,"#0f1923")
        st.markdown(f"""
        <div class="{css}">
          <div class="metric-lbl">{label}</div>
          <div class="metric-val" style="color:{color}">{value}</div>
          <div class="metric-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)


def _render_table(df: pd.DataFrame):
    if df.empty:
        st.info("暂无匹配数据")
        return

    rows_html = []
    for _, r in df.iterrows():
        in_zone = bool(r["in_zone"])
        dist    = r.get("dist_pct") or 0
        rt      = r.get("retrace_pct") or 0

        # 状态徽章
        if in_zone:
            status = '<span class="badge badge-inzone">✅ IN ZONE</span>'
            row_bg = "background:#f0fdf4;"
        elif dist < 5:
            status = '<span class="badge badge-watch">👀 接近</span>'
            row_bg = "background:#fffbeb;"
        else:
            status = '<span class="badge badge-neutral">—</span>'
            row_bg = ""

        # 时间框架徽章
        tf_color = {"Daily":"#1d4ed8","Weekly":"#6d28d9","Monthly":"#e85d04"}.get(r["timeframe"],"#6b7280")
        tf_badge = f'<span style="color:{tf_color};font-weight:700;font-size:11px">{r["timeframe"]}</span>'

        # 共振徽章
        cs = r.get("confluence_score") or 0
        cl = r.get("confluence_label") or "—"
        if cs >= 9:   conf_b = f'<span class="badge badge-fire3">{cl}</span>'
        elif cs >= 6: conf_b = f'<span class="badge badge-fire2">{cl}</span>'
        elif cs >= 3: conf_b = f'<span class="badge badge-fire1">{cl}</span>'
        else:         conf_b = '<span class="badge badge-neutral">—</span>'

        # 回撤进度条
        rt_color = "#0d9488" if 48 <= rt <= 64 else "#9ca3af"
        rbar = f"""<div style="display:flex;align-items:center;gap:5px">
          <div style="width:50px;height:5px;background:#e5e7eb;border-radius:3px;overflow:hidden">
            <div style="width:{min(rt,100):.0f}%;height:100%;background:{rt_color};border-radius:3px"></div>
          </div>
          <span style="color:{rt_color};font-size:11px;font-family:'IBM Plex Mono',monospace">{rt:.1f}%</span>
        </div>"""

        # TradingView 链接
        tvsym = r.get("tv_symbol") or tv_symbol(r["ticker"])
        tv    = f'<a href="https://www.tradingview.com/chart/?symbol={tvsym}" target="_blank" style="color:#1d4ed8;font-weight:700;font-size:11px;text-decoration:none">📊 TV ↗</a>'

        def fmt(v):
            try: return f"{float(v):,.4f}"
            except: return "—"

        dist_txt = "0.0%" if in_zone else f"{dist:.1f}%"
        dist_color = "#0d9488" if in_zone else ("#b45309" if dist < 5 else "#9ca3af")

        rows_html.append(f"""
        <tr style="{row_bg}">
          <td style="font-family:'IBM Plex Mono',monospace;font-weight:600">{r['ticker']}</td>
          <td style="font-weight:700">{r['name']}</td>
          <td>{tf_badge}</td>
          <td>{status}</td>
          <td>{conf_b}</td>
          <td style="font-family:'IBM Plex Mono',monospace;font-weight:600">{fmt(r.get('current_price'))}</td>
          <td style="font-family:'IBM Plex Mono',monospace;color:#0d9488">{fmt(r.get('zone_top'))}</td>
          <td style="font-family:'IBM Plex Mono',monospace;color:#b45309">{fmt(r.get('zone_bot'))}</td>
          <td>{rbar}</td>
          <td style="font-family:'IBM Plex Mono',monospace;color:{dist_color}">{dist_txt}</td>
          <td>{tv}</td>
        </tr>""")

    table_html = f"""
    <div style="overflow-x:auto;border:1px solid #e2e6ea;border-radius:10px;background:white">
    <table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:#f8f9fa">
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea;white-space:nowrap">Ticker</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">名称</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">框架</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">状态</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">共振</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">当前价格</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">Fibo 0.500</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">Fibo 0.618</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">回撤%</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">距区间%</th>
      <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#6b7280;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #e2e6ea">图表</th>
    </tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
    </table></div>"""

    st.markdown(table_html, unsafe_allow_html=True)


def _count_triple(df: pd.DataFrame) -> int:
    grouped = df[df["in_zone"]].groupby("ticker")["timeframe"].count()
    return int((grouped >= 3).sum())
