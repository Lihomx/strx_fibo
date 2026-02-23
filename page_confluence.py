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
    .cf-hdr{font-size:12px;color:#6b7280;font-weight:600;
            padding:5px 0;border-bottom:2px solid #e5e7eb;white-space:nowrap}
    .cf-cell{font-size:13px;padding:5px 0;
             border-bottom:1px solid #f3f4f6;
             min-height:40px;display:flex;align-items:center;flex-wrap:wrap}
    </style>
    """, unsafe_allow_html=True)

    # 列宽: 资产 类别 价格 日线 周线 月线 共振 评分 TV 收藏
    W = [2.8, 1.0, 1.6, 0.8, 0.8, 0.8, 1.8, 1.4, 0.8, 0.8]
    HDRS = ["资产", "类别", "当前价格", "日线", "周线", "月线", "共振信号", "评分", "TV", "收藏"]

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

    # ── 表头 ────────────────────────────────────────────────────
    hcols = st.columns(W)
    for c, h in zip(hcols, HDRS):
        c.markdown(f'<div class="cf-hdr">{h}</div>', unsafe_allow_html=True)

    # ── 数据行（每行 st.columns，收藏按钮在最后一列）──────────
    for idx, (ticker, info) in enumerate(filtered):
        tfs    = info["tfs"]
        score  = info["conf_score"]
        label  = info["conf_label"]
        price  = info["current_price"]
        is_fav = ticker in watchlist_tickers

        price_s = f"{float(price):,.4f}" if price is not None else "—"

        rc = st.columns(W)

        rc[0].markdown(
            f'<div class="cf-cell"><div><b>{info["name"]}</b><br>'
            f'<span style="color:#9ca3af;font-size:11px;font-family:monospace">{ticker}</span>'
            f'</div></div>', unsafe_allow_html=True)

        rc[1].markdown(
            f'<div class="cf-cell">'
            f'<span class="badge b-gray">{_cat_label(info["category"])}</span></div>',
            unsafe_allow_html=True)

        rc[2].markdown(
            f'<div class="cf-cell" style="justify-content:flex-end;'
            f'font-family:monospace;font-size:12px">{price_s}</div>',
            unsafe_allow_html=True)

        for i, tf in enumerate(TFS):
            icon = _tf_icon(tfs.get(tf))
            rc[3 + i].markdown(
                f'<div class="cf-cell" style="justify-content:center">{icon}</div>',
                unsafe_allow_html=True)

        rc[6].markdown(
            f'<div class="cf-cell">{label}</div>', unsafe_allow_html=True)

        rc[7].markdown(
            f'<div class="cf-cell"><div style="width:100%">'
            f'<span style="font-size:12px;font-family:monospace">{score}/10</span>'
            f'{_score_bar(score)}</div></div>',
            unsafe_allow_html=True)

        rc[8].markdown(
            f'<div class="cf-cell">'
            f'<a href="{info["tv_url"]}" target="_blank" '
            f'style="color:#e85d04;font-size:12px">📈 TV</a></div>',
            unsafe_allow_html=True)

        # 收藏按钮：直接在同行最后一列
        lbl = "★" if is_fav else "☆"
        tip = f"{'取消收藏' if is_fav else '收藏'}：{info['name']}"
        if rc[9].button(lbl, key=f"cf_fav_{ticker}_{idx}",
                        help=tip, use_container_width=True):
            st.session_state["_cf_fav_action"] = (
                "del" if is_fav else "add", ticker, info["name"])
            st.rerun()

    st.markdown(
        f'<hr style="border:none;border-top:1px solid #e5e7eb;margin:4px 0">'
        f'<div style="color:#9ca3af;font-size:11px">'
        f'✅ 黄金区间 &nbsp;👀 接近区间(&lt;5%) &nbsp;· 区间外 &nbsp;｜&nbsp;'
        f'显示 {len(filtered)} 个品种 &nbsp;｜&nbsp; 点击收藏列 ☆/★ 即可操作'
        f'</div>', unsafe_allow_html=True)

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
