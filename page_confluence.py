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

    # 加载自选收藏状态
    watchlist         = storage.load_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    TFS = ["Daily", "Weekly", "Monthly"]

    # ── 表头 HTML ────────────────────────────────────────────────────
    # ── 先把所有行汇聚成完整 HTML 表格，确保列完全对齐 ─────────────
    st.markdown("""
    <style>
    .conf-table {width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
    .conf-table th {padding:8px 8px;background:#f9fafb;border-bottom:2px solid #e5e7eb;
                    white-space:nowrap;overflow:hidden}
    .conf-table td {padding:7px 8px;border-bottom:1px solid #f3f4f6;vertical-align:middle;
                    overflow:hidden;text-overflow:ellipsis}
    </style>
    """, unsafe_allow_html=True)

    rows_html_cf  = []
    fav_cf        = []   # (ticker, name, is_fav, idx)
    def _tf_cell(tf_data):
        if not tf_data:
            return "<td style='text-align:center;color:#d1d5db;padding:8px 6px'>·</td>"
        if tf_data["in_zone"]:
            return "<td style='text-align:center;padding:8px 6px'>✅</td>"
        if tf_data.get("dist_pct") is not None and tf_data["dist_pct"] < 5:
            return "<td style='text-align:center;padding:8px 6px'>👀</td>"
        return "<td style='text-align:center;color:#d1d5db;padding:8px 6px'>·</td>"

    def _score_bar(score):
        pct   = score * 10
        color = "#dc2626" if pct >= 90 else "#f59e0b" if pct >= 60 else "#10b981"
        return (
            f"<div style='background:#f3f4f6;border-radius:4px;height:6px;margin-top:4px'>"
            f"<div style='background:{color};width:{pct}%;height:6px;border-radius:4px'></div>"
            f"</div>"
        )

    for idx, (ticker, info) in enumerate(filtered):
        tfs    = info["tfs"]
        score  = info["conf_score"]
        label  = info["conf_label"]
        price  = info["current_price"]
        is_fav = ticker in watchlist_tickers

        price_s  = f"{float(price):,.4f}" if price is not None else "—"
        if is_fav:
            fav_cell_html = ("<td style='width:5%;text-align:center;"
                             "font-size:18px;color:#f59e0b'>★</td>")
        else:
            fav_cell_html = ("<td style='width:5%;text-align:center;"
                             "font-size:18px;color:#d1d5db'>☆</td>")

        rows_html_cf.append(
            f"<tr style='border-bottom:1px solid #f3f4f6'>"
            f"<td style='width:18%'><b>{info['name']}</b><br>"
            f"<small style='color:#9ca3af;font-family:monospace'>{ticker}</small></td>"
            f"<td style='width:7%'><span class='badge b-gray'>{_cat_label(info['category'])}</span></td>"
            f"<td style='width:11%;font-family:monospace;text-align:right;font-size:12px'>{price_s}</td>"
            + "".join(_tf_cell(tfs.get(tf)) for tf in TFS) +
            f"<td style='width:12%'>{label}</td>"
            f"<td style='width:9%'>"
            f"<span style='font-family:monospace;font-size:12px'>{score}/10</span>"
            f"{_score_bar(score)}</td>"
            f"<td style='width:6%'><a href='{info['tv_url']}' target='_blank' "
            f"style='color:#e85d04;font-size:12px'>📈 TV</a></td>"
            + fav_cell_html
            + f"</tr>"
        )
        fav_cf.append((ticker, info["name"], is_fav, idx))

    # 整体输出完整表格（保证列对齐）
    st.markdown(
        f'''<table class="conf-table">
        <thead><tr>
          <th style="text-align:left;width:18%">资产</th>
          <th style="text-align:left;width:7%">类别</th>
          <th style="text-align:right;width:11%">当前价格</th>
          <th style="text-align:center;width:7%">日线</th>
          <th style="text-align:center;width:7%">周线</th>
          <th style="text-align:center;width:7%">月线</th>
          <th style="text-align:left;width:12%">共振信号</th>
          <th style="text-align:left;width:9%">评分</th>
          <th style="text-align:left;width:6%">TV</th>
          <th style="text-align:center;width:5%">收藏</th>
        </tr></thead>
        <tbody>{'\n'.join(rows_html_cf)}</tbody>
        </table>''',
        unsafe_allow_html=True,
    )

    # ── 收藏操作按钮区（表格下方，每行8个，完全对齐）──────────────
    st.markdown(
        '<div style="color:#6b7280;font-size:11px;margin:8px 0 4px">'
        '✅ 黄金区间 &nbsp;👀 接近区间(&lt;5%) &nbsp;· 区间外 &nbsp;｜&nbsp;'
        f'显示 {len(filtered)} 个品种 &nbsp;｜&nbsp; 点击下方按钮收藏 / 取消收藏'
        '</div>',
        unsafe_allow_html=True,
    )
    N = 8
    for row_start in range(0, len(fav_cf), N):
        batch = fav_cf[row_start:row_start + N]
        cols  = st.columns(N)
        for i, (ticker, name, is_fav, _) in enumerate(batch):
            lbl = f"★ {ticker}" if is_fav else f"☆ {ticker}"
            tip = f"{'取消收藏' if is_fav else '收藏'}：{name}"
            if cols[i].button(lbl, key=f"cf_fav_{ticker}", help=tip):
                st.session_state["_cf_fav_action"] = (
                    "del" if is_fav else "add", ticker, name)
                st.rerun()

    # ── CSV 下载 ─────────────────────────────────────────────────────
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
