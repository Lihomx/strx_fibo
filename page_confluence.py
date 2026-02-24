"""
page_confluence.py — 多框架共振检测
新增：当前价格列 + 每行添加到自选收藏按钮
"""
import pandas as pd
import streamlit as st

import storage
from assets import CATEGORY_LABELS


def _safe_dist(r: dict) -> float:
    v = r.get("dist_pct")
    try:
        return float(v) if v is not None else 999.0
    except (TypeError, ValueError):
        return 999.0


def _cat_label(cat: str) -> str:
    mapping = {
        "futures": "期货", "index": "指数", "forex": "外汇",
        "us_stock": "美股", "cn_stock": "中港股", "a_stock": "A股",
        "crypto": "加密", "custom": "自定义",
    }
    return mapping.get(cat, CATEGORY_LABELS.get(cat, cat))


def render():
    # ── 处理收藏操作（session_state 方式）──────────────────────
    _pending = st.session_state.pop("_cf_fav_action", None)
    if _pending:
        _act, _tk, _nm = _pending
        if _act == "add":
            storage.add_to_watchlist(ticker=_tk, name=_nm)
            st.toast(f"已收藏：{_nm}", icon="⭐")
        else:
            storage.remove_from_watchlist(_tk)
            st.toast(f"已移除：{_nm}", icon="🗑️")
        st.rerun()

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

    # ── 按 ticker 分组，同时采集当前价格 ────────────────────────────
    ticker_info: dict = {}
    for r in rows:
        t = r.get("ticker", "")
        if not t:
            continue
        if t not in ticker_info:
            ticker_info[t] = {
                "name":          r.get("name", ""),
                "category":      r.get("category", ""),
                "tv_url":        r.get("tv_url", "#"),
                "conf_label":    r.get("confluence_label", "—") or "—",
                "conf_score":    int(r.get("confluence_score") or 0),
                "current_price": None,
                "tfs":           {},
            }
        tf = r.get("timeframe", "")
        if tf:
            ticker_info[t]["tfs"][tf] = {
                "in_zone":  bool(r.get("in_zone", False)),
                "dist_pct": _safe_dist(r),
            }
        # 取日线价格作为当前价格（或任意一个非空的）
        price = r.get("current_price")
        if price is not None and ticker_info[t]["current_price"] is None:
            ticker_info[t]["current_price"] = price
        if tf == "Daily" and price is not None:
            ticker_info[t]["current_price"] = price

    # ── 过滤：有信号的品种 ──────────────────────────────────────────
    signal = []
    for t, info in ticker_info.items():
        has_signal = any(
            v["in_zone"] or (v["dist_pct"] is not None and v["dist_pct"] < 5)
            for v in info["tfs"].values()
        )
        if has_signal:
            signal.append((t, info))

    signal.sort(key=lambda x: x[1]["conf_score"], reverse=True)

    if not signal:
        st.markdown('<div class="n-warn">⚠️ 当前扫描结果中没有处于黄金区间或接近区间的品种。'
                    '请扩大扫描范围或等待价格靠近 Fibo 区间。</div>',
                    unsafe_allow_html=True)
        st.markdown(f"共扫描 **{len(ticker_info)}** 个品种，暂无信号。")
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
            ["全部", "futures", "index", "forex", "us_stock",
             "cn_stock", "a_stock", "crypto"],
            label_visibility="collapsed",
        )
    with col3:
        kw = st.text_input("搜索", placeholder="名称/代码…",
                           label_visibility="collapsed")

    filtered = [
        (t, i) for t, i in signal
        if i["conf_score"] >= min_score
        and (cat_filter == "全部" or i["category"] == cat_filter)
        and (not kw or kw.lower() in t.lower() or kw.lower() in i["name"].lower())
    ]

    if not filtered:
        st.info("过滤后无结果")
        return

    watchlist         = storage.load_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    TFS = ["Daily", "Weekly", "Monthly"]

    # ── CSS ──────────────────────────────────────────────────────
    st.markdown("""
    <style>
    .cf2{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
    .cf2 th{padding:8px 6px;background:#f9fafb;border-bottom:2px solid #e5e7eb;
            font-size:12px;color:#374151;font-weight:600;white-space:nowrap}
    .cf2 td{padding:8px 6px;border-bottom:1px solid #f3f4f6;vertical-align:middle;
            overflow:hidden;text-overflow:ellipsis;height:46px}
    </style>
    """, unsafe_allow_html=True)

    def _tf_icon(tf_data):
        if not tf_data:
            return '<span style="color:#d1d5db">·</span>'
        if tf_data.get("in_zone"):
            return "✅"
        if tf_data.get("dist_pct") is not None and tf_data["dist_pct"] < 5:
            return "👀"
        return '<span style="color:#d1d5db">·</span>'

    def _score_bar(score):
        pct   = score * 10
        color = "#dc2626" if pct >= 90 else "#f59e0b" if pct >= 60 else "#10b981"
        return (
            f'<div style="background:#f3f4f6;border-radius:3px;height:5px;'
            f'margin-top:3px;width:100%">'
            f'<div style="background:{color};width:{pct}%;height:5px;border-radius:3px"></div>'
            f'</div>'
        )

    # ── 收集行数据 ────────────────────────────────────────────
    rows_data = []
    for idx, (ticker, info) in enumerate(filtered):
        tfs    = info["tfs"]
        score  = info["conf_score"]
        label  = info["conf_label"]
        price  = info["current_price"]
        is_fav = ticker in watchlist_tickers
        price_s = f"{float(price):,.4f}" if price is not None else "—"
        rows_data.append({
            "ticker": ticker, "info": info, "tfs": tfs,
            "score": score, "label": label, "price_s": price_s,
            "is_fav": is_fav, "idx": idx,
        })

    # ── 双列布局：HTML 表格(93%) + 收藏列(7%) ────────────────
    col_table, col_fav = st.columns([13, 1])

    with col_table:
        thead = (
            "<tr>"
            "<th style='width:20%'>资产</th>"
            "<th style='width:8%'>类别</th>"
            "<th style='width:11%;text-align:right'>当前价格</th>"
            "<th style='width:7%;text-align:center'>日线</th>"
            "<th style='width:7%;text-align:center'>周线</th>"
            "<th style='width:7%;text-align:center'>月线</th>"
            "<th style='width:13%'>共振信号</th>"
            "<th style='width:10%'>评分</th>"
            "<th style='width:7%'>TV</th>"
            "</tr>"
        )
        rows_html = []
        for rd in rows_data:
            info   = rd["info"]
            ticker = rd["ticker"]
            rows_html.append(
                f"<tr>"
                f"<td><b>{info['name']}</b>"
                f"<br><small style='color:#9ca3af;font-family:monospace'>{ticker}</small></td>"
                f"<td><span class='badge b-gray'>{_cat_label(info['category'])}</span></td>"
                f"<td style='font-family:monospace;font-size:12px;text-align:right'>{rd['price_s']}</td>"
                + "".join(
                    f"<td style='text-align:center'>{_tf_icon(rd['tfs'].get(tf))}</td>"
                    for tf in TFS
                )
                + f"<td>{rd['label']}</td>"
                f"<td><span style='font-size:12px;font-family:monospace'>{rd['score']}/10</span>"
                f"{_score_bar(rd['score'])}</td>"
                f"<td><a href='{info['tv_url']}' target='_blank' "
                f"style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
                f"</tr>"
            )
        st.markdown(
            f"<table class='cf2'><thead>{thead}</thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table>",
            unsafe_allow_html=True,
        )

    with col_fav:
        # 表头占位
        st.markdown(
            '<div style="font-size:12px;color:#374151;font-weight:600;'
            'padding:8px 0;border-bottom:2px solid #e5e7eb;text-align:center">收藏</div>',
            unsafe_allow_html=True,
        )
        for rd in rows_data:
            lbl = "★" if rd["is_fav"] else "☆"
            tip = f"{'取消收藏' if rd['is_fav'] else '收藏'}：{rd['info']['name']}"
            if st.button(lbl, key=f"cf_fav_{rd['ticker']}_{rd['idx']}",
                         help=tip, use_container_width=True):
                st.session_state["_cf_fav_action"] = (
                    "del" if rd["is_fav"] else "add",
                    rd["ticker"], rd["info"]["name"])
                st.rerun()

    st.markdown(
        f'<div style="color:#9ca3af;font-size:11px;margin-top:4px">'
        f'✅ 黄金区间 &nbsp;👀 接近区间(&lt;5%) &nbsp;· 区间外 &nbsp;｜&nbsp;'
        f'显示 {len(filtered)} 个品种 &nbsp;｜&nbsp; 点击收藏列 ☆/★ 即可操作'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── CSV 下载 ─────────────────────────────────────────────────
    export_rows = []
    for ticker, info in filtered:
        row = {
            "ticker":        ticker,
            "name":          info["name"],
            "category":      info["category"],
            "current_price": info["current_price"],
            "conf_score":    info["conf_score"],
            "conf_label":    info["conf_label"],
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
