"""
page_confluence.py — 多框架共振检测
"""
import pandas as pd
import streamlit as st

import storage


def render():
    st.markdown("## 🔥 多框架共振检测")

    if not storage.has_scan_data():
        st.markdown('<div class="n-info">💡 请先在「实时扫描」页面执行一次扫描。</div>',
                    unsafe_allow_html=True)
        return

    rows = storage.load_latest_results(inzone_only=False)
    if not rows:
        st.info("暂无数据")
        return

    sessions = storage.load_sessions(limit=1)
    last_sess = sessions[0] if sessions else {}
    st.caption(f"基于最近扫描 · {last_sess.get('scan_time','—')}")

    # ── 按 ticker 分组计算共振 ──────────────────────────────────────
    ticker_info: dict = {}
    for r in rows:
        t = r["ticker"]
        if t not in ticker_info:
            ticker_info[t] = {
                "name":     r.get("name",""),
                "category": r.get("category",""),
                "tv_url":   r.get("tv_url","#"),
                "conf_label": r.get("confluence_label","—"),
                "conf_score": r.get("confluence_score",0),
                "tfs": {},
            }
        ticker_info[t]["tfs"][r["timeframe"]] = {
            "in_zone": r.get("in_zone",False),
            "dist_pct": r.get("dist_pct",999),
        }

    # 仅展示有信号的（至少一个框架在区间或接近）
    signal = [
        (t, info) for t, info in ticker_info.items()
        if any(v["in_zone"] or v["dist_pct"] < 5
               for v in info["tfs"].values())
    ]
    signal.sort(key=lambda x: x[1]["conf_score"], reverse=True)

    if not signal:
        st.info("当前无资产处于黄金区间或接近区间")
        return

    # ── 统计 ────────────────────────────────────────────────────────
    triple = sum(1 for _, i in signal if i["conf_score"] >= 9)
    double = sum(1 for _, i in signal if 6 <= i["conf_score"] < 9)
    single = sum(1 for _, i in signal if 1 <= i["conf_score"] < 6)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""<div class="m-card red">
        <div class="m-lbl">🔥🔥🔥 三框架共振</div>
        <div class="m-val" style="color:#dc2626">{triple}</div>
        <div class="m-sub">最强买入信号</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="m-card gold">
        <div class="m-lbl">🔥🔥 双框架共振</div>
        <div class="m-val" style="color:#d97706">{double}</div>
        <div class="m-sub">强信号</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="m-card teal">
        <div class="m-lbl">🔥 单框架 / 接近</div>
        <div class="m-val" style="color:#059669">{single}</div>
        <div class="m-sub">观察信号</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 共振表 ───────────────────────────────────────────────────────
    TFS = ["Daily", "Weekly", "Monthly"]

    def tf_cell(tf_data):
        if not tf_data:
            return "<td style='text-align:center;color:#d1d5db'>·</td>"
        if tf_data["in_zone"]:
            return "<td style='text-align:center'>✅</td>"
        if tf_data["dist_pct"] < 5:
            return "<td style='text-align:center'>👀</td>"
        return "<td style='text-align:center;color:#d1d5db'>·</td>"

    def score_bar(score):
        filled = int(score / 10 * 10)
        pct    = score * 10
        color  = "#dc2626" if pct >= 90 else "#f59e0b" if pct >= 60 else "#10b981"
        return (f"<div style='background:#f3f4f6;border-radius:4px;height:6px;margin-top:4px'>"
                f"<div style='background:{color};width:{pct}%;height:6px;border-radius:4px'></div>"
                f"</div>")

    rows_html = []
    for ticker, info in signal:
        tfs = info["tfs"]
        score = info["conf_score"]
        label = info["conf_label"]
        rows_html.append(
            f"<tr style='border-bottom:1px solid #f3f4f6'>"
            f"<td style='padding:10px 10px'>"
            f"  <b>{info['name']}</b><br>"
            f"  <small style='color:#9ca3af'>{ticker}</small>"
            f"</td>"
            f"<td style='padding:8px 10px'>"
            f"  <span class='badge b-gray'>{info['category']}</span>"
            f"</td>"
            + "".join(tf_cell(tfs.get(tf)) for tf in TFS) +
            f"<td style='padding:8px 10px'>{label}</td>"
            f"<td style='padding:8px 10px;min-width:80px'>"
            f"  <span style='font-family:monospace;font-size:12px'>{score}/10</span>"
            f"  {score_bar(score)}"
            f"</td>"
            f"<td style='padding:8px 10px'>"
            f"  <a href='{info['tv_url']}' target='_blank' "
            f"  style='color:#e85d04;font-size:12px'>📈 TV</a>"
            f"</td>"
            f"</tr>"
        )

    st.markdown(f"""
    <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead>
    <tr style="background:#f9fafb;border-bottom:2px solid #e5e7eb">
      <th style="padding:10px 10px;text-align:left">资产</th>
      <th style="padding:8px 10px;text-align:left">类别</th>
      <th style="padding:8px 10px;text-align:center">日线</th>
      <th style="padding:8px 10px;text-align:center">周线</th>
      <th style="padding:8px 10px;text-align:center">月线</th>
      <th style="padding:8px 10px;text-align:left">共振信号</th>
      <th style="padding:8px 10px;text-align:left">评分</th>
      <th style="padding:8px 10px;text-align:left">图表</th>
    </tr>
    </thead>
    <tbody>
    {''.join(rows_html)}
    </tbody>
    </table>
    </div>
    <p style="font-size:11px;color:#9ca3af;margin-top:8px">
    ✅ 黄金区间 (0.500–0.618) &nbsp;·&nbsp; 👀 接近区间 (&lt;5%) &nbsp;·&nbsp; · 区间外
    </p>
    """, unsafe_allow_html=True)
