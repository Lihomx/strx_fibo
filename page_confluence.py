"""
page_confluence.py — 多框架共振检测（修复版）
Bug修复：安全访问 dist_pct，避免 None 比较 TypeError
"""
import pandas as pd
import streamlit as st

import storage


def _safe_dist(r: dict) -> float:
    """安全获取 dist_pct，返回 float，None → 999.0"""
    v = r.get("dist_pct")
    try:
        return float(v) if v is not None else 999.0
    except (TypeError, ValueError):
        return 999.0


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

    sessions  = storage.load_sessions(limit=1)
    last_sess = sessions[0] if sessions else {}
    note      = last_sess.get("note", "")
    st.caption(
        f"基于最近扫描 · {last_sess.get('scan_time','—')}  |  "
        f"品种: {last_sess.get('asset_count', '?')}  |  {note}"
    )

    # ── 按 ticker 分组 ───────────────────────────────────────────────
    ticker_info: dict = {}
    for r in rows:
        t = r.get("ticker","")
        if not t:
            continue
        if t not in ticker_info:
            ticker_info[t] = {
                "name":       r.get("name",""),
                "category":   r.get("category",""),
                "tv_url":     r.get("tv_url","#"),
                "conf_label": r.get("confluence_label","—") or "—",
                "conf_score": int(r.get("confluence_score") or 0),
                "tfs":        {},
            }
        tf = r.get("timeframe","")
        if tf:
            ticker_info[t]["tfs"][tf] = {
                "in_zone":  bool(r.get("in_zone", False)),
                "dist_pct": _safe_dist(r),
            }

    # ── 过滤：有信号的品种 ──────────────────────────────────────────
    signal = []
    for t, info in ticker_info.items():
        has_signal = any(
            v["in_zone"] or v["dist_pct"] < 5
            for v in info["tfs"].values()
        )
        if has_signal:
            signal.append((t, info))

    signal.sort(key=lambda x: x[1]["conf_score"], reverse=True)

    if not signal:
        st.markdown('<div class="n-warn">⚠️ 当前扫描结果中没有处于黄金区间或接近区间的品种。'
                    '请扩大扫描范围或等待价格靠近 Fibo 区间。</div>',
                    unsafe_allow_html=True)

        # 仍展示摘要统计
        total_tickers = len(ticker_info)
        st.markdown(f"共扫描 **{total_tickers}** 个品种，暂无信号。")
        return

    # ── 统计卡 ──────────────────────────────────────────────────────
    triple = sum(1 for _, i in signal if i["conf_score"] >= 9)
    double = sum(1 for _, i in signal if 6 <= i["conf_score"] < 9)
    single = sum(1 for _, i in signal if 1 <= i["conf_score"] < 6)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="m-card red"><div class="m-lbl">🔥🔥🔥 三框架共振</div>'
                    f'<div class="m-val" style="color:#dc2626">{triple}</div>'
                    f'<div class="m-sub">最强信号</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="m-card gold"><div class="m-lbl">🔥🔥 双框架</div>'
                    f'<div class="m-val" style="color:#d97706">{double}</div>'
                    f'<div class="m-sub">强信号</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="m-card teal"><div class="m-lbl">🔥 单框架/接近</div>'
                    f'<div class="m-val" style="color:#059669">{single}</div>'
                    f'<div class="m-sub">观察信号</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="m-card blue"><div class="m-lbl">信号总计</div>'
                    f'<div class="m-val">{len(signal)}</div>'
                    f'<div class="m-sub">品种数</div></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── 过滤器 ───────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        min_score = st.slider("最低评分", 0, 10, 0, 1)
    with col2:
        cat_filter = st.selectbox(
            "品种类别",
            ["全部","futures","index","forex","us_stock","cn_stock","a_stock","crypto"],
            label_visibility="collapsed",
        )
    with col3:
        kw = st.text_input("搜索", placeholder="名称/代码…", label_visibility="collapsed")

    filtered = [
        (t, i) for t, i in signal
        if i["conf_score"] >= min_score
        and (cat_filter == "全部" or i["category"] == cat_filter)
        and (not kw or kw.lower() in t.lower() or kw.lower() in i["name"].lower())
    ]

    if not filtered:
        st.info("过滤后无结果")
        return

    # ── 共振表 ───────────────────────────────────────────────────────
    TFS = ["Daily", "Weekly", "Monthly"]

    def tf_cell(tf_data):
        if not tf_data:
            return "<td style='text-align:center;color:#d1d5db;padding:8px 6px'>·</td>"
        if tf_data["in_zone"]:
            return "<td style='text-align:center;padding:8px 6px'>✅</td>"
        if tf_data["dist_pct"] < 5:
            return "<td style='text-align:center;padding:8px 6px'>👀</td>"
        return "<td style='text-align:center;color:#d1d5db;padding:8px 6px'>·</td>"

    def score_bar(score):
        pct   = score * 10
        color = "#dc2626" if pct >= 90 else "#f59e0b" if pct >= 60 else "#10b981"
        return (f"<div style='background:#f3f4f6;border-radius:4px;height:6px;margin-top:4px'>"
                f"<div style='background:{color};width:{pct}%;height:6px;border-radius:4px'></div>"
                f"</div>")

    def cat_label(cat: str) -> str:
        mapping = {
            "futures":"期货","index":"指数","forex":"外汇",
            "us_stock":"美股","cn_stock":"中港股","a_stock":"A股","crypto":"加密",
        }
        return mapping.get(cat, cat)

    rows_html = []
    for ticker, info in filtered:
        tfs   = info["tfs"]
        score = info["conf_score"]
        label = info["conf_label"]
        rows_html.append(
            f"<tr style='border-bottom:1px solid #f3f4f6'>"
            f"<td style='padding:10px 10px'>"
            f"  <b>{info['name']}</b><br>"
            f"  <small style='color:#9ca3af;font-family:monospace'>{ticker}</small>"
            f"</td>"
            f"<td style='padding:8px 8px'>"
            f"  <span class='badge b-gray'>{cat_label(info['category'])}</span>"
            f"</td>"
            + "".join(tf_cell(tfs.get(tf)) for tf in TFS) +
            f"<td style='padding:8px 10px'>{label}</td>"
            f"<td style='padding:8px 10px;min-width:90px'>"
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
      <th style="padding:8px 8px;text-align:left">类别</th>
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
    st.caption(f"显示 {len(filtered)} 个有信号品种")

    # CSV 下载
    export_rows = []
    for ticker, info in filtered:
        row = {
            "ticker": ticker, "name": info["name"],
            "category": info["category"],
            "conf_score": info["conf_score"],
            "conf_label": info["conf_label"],
        }
        for tf in TFS:
            td = info["tfs"].get(tf, {})
            row[f"{tf}_in_zone"] = td.get("in_zone", False)
            row[f"{tf}_dist"]    = td.get("dist_pct", None)
        export_rows.append(row)

    st.download_button(
        "⬇️ 下载共振报告 CSV",
        pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8-sig"),
        file_name="strx_confluence.csv",
        mime="text/csv",
    )
