"""
page_failed_breakdown.py
======================================================================
💥 假跌破 + 4.236 爆发扫描器 (Failed Breakdown & 4.236 Breakout Scanner)
- 周期：仅 15 分钟 (15m)
- 判定标准：
  ① 0点（局部低）> 前局部低 (Higher Low 结构)
  ② 0点收盘未跌破前低 (下影线探底拉回收盘企稳)
  ③ 价格强势突破 1点 (15分钟颈线 Swing High)
  ④ 价格触碰或超过 4.236 斐波那契延伸位
======================================================================
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

import storage
import colab_failed_breakdown_script

logger = logging.getLogger(__name__)


def _fetch_name(ticker: str) -> str:
    """获取股票名称"""
    try:
        from page_watchlist import _fetch_ticker_name
        return _fetch_ticker_name(ticker) or ticker
    except Exception:
        return ticker


def _tv_link(ticker: str, period: str = "15m") -> str:
    """生成 TradingView 链接"""
    clean_tk = ticker.strip().upper()
    if clean_tk.endswith(".SS"):
        clean_tk = "SSE:" + clean_tk.replace(".SS", "")
    elif clean_tk.endswith(".SZ"):
        clean_tk = "SZSE:" + clean_tk.replace(".SZ", "")
    elif clean_tk.endswith(".BJ"):
        clean_tk = "BSE:" + clean_tk.replace(".BJ", "")
    return f"https://www.tradingview.com/chart/?symbol={clean_tk}&interval=15"


def _sina_link(ticker: str) -> str:
    """生成新浪财经链接"""
    clean_tk = ticker.strip().upper()
    if clean_tk.endswith(".SS"):
        code = "sh" + clean_tk.replace(".SS", "")
    elif clean_tk.endswith(".SZ"):
        code = "sz" + clean_tk.replace(".SZ", "")
    elif clean_tk.endswith(".BJ"):
        code = "bj" + clean_tk.replace(".BJ", "")
    else:
        code = "gb_" + clean_tk.lower()
    return f"https://finance.sina.com.cn/realstock/company/{code}/nc.shtml"


_STAT_MAP = {
    "all": "全部状态",
    "hit": "💥 已达成 4.236 (爆发确认)",
    "active": "🚀 突破推进中",
}
_STAT_REVERSE_MAP = {v: k for k, v in _STAT_MAP.items()}

_TIME_MAP = {
    "all": "全部时效",
    "24h": "最近 24 小时",
    "3d": "最近 3 天",
    "7d": "最近 7 天",
    "30d": "最近 30 天",
}
_TIME_REVERSE_MAP = {v: k for k, v in _TIME_MAP.items()}

_SORT_MAP = {
    "gain_desc": "🔥 爆发涨幅最高",
    "fibo_desc": "🌟 斐波倍数最高",
    "time_desc": "⏱️ 最新突破触发",
    "vol_desc": "📊 20根均量最高",
}
_SORT_REVERSE_MAP = {v: k for k, v in _SORT_MAP.items()}


def render_failed_breakdown_page():
    st.markdown(
        """
        <style>
        .fb-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        .fb-title {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .fb-banner {
            background: linear-gradient(135deg, rgba(234, 88, 12, 0.15), rgba(249, 115, 22, 0.05));
            border: 1px solid rgba(249, 115, 22, 0.3);
            border-radius: 10px;
            padding: 12px 18px;
            margin-bottom: 16px;
            color: #fed7aa;
            font-size: 13.5px;
            line-height: 1.6;
        }
        .fb-stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 18px;
        }
        .fb-stat-card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .fb-stat-val {
            font-size: 22px;
            font-weight: 800;
            color: #f97316;
        }
        .fb-stat-lbl {
            font-size: 12px;
            color: #94a3b8;
        }
        .fb-card {
            background: #0f172a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 14px;
            transition: all 0.2s ease;
        }
        .fb-card-hit {
            border: 1px solid rgba(249, 115, 22, 0.4);
            box-shadow: 0 0 15px rgba(249, 115, 22, 0.1);
        }
        .fb-card:hover {
            border-color: rgba(249, 115, 22, 0.6);
            transform: translateY(-2px);
        }
        .fb-badge-hit {
            background: linear-gradient(135deg, #f97316, #ea580c);
            color: #fff;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }
        .fb-badge-active {
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.4);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }
        .fb-progress-container {
            background: rgba(30, 41, 59, 0.8);
            border-radius: 6px;
            height: 10px;
            width: 100%;
            overflow: hidden;
            margin: 8px 0 4px 0;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        .tp-pagination {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin: 14px 0;
            padding: 8px 12px;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
        }
        .tp-page-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 14px;
            background: rgba(59, 130, 246, 0.15);
            color: #93c5fd !important;
            border: 1px solid rgba(59, 130, 246, 0.35);
            border-radius: 6px;
            text-decoration: none !important;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .tp-page-btn:hover {
            background: rgba(59, 130, 246, 0.3);
            color: #ffffff !important;
            border-color: rgba(59, 130, 246, 0.7);
            text-decoration: none !important;
        }
        .tp-page-btn.disabled {
            background: rgba(148, 163, 184, 0.08);
            color: #64748b !important;
            border-color: rgba(148, 163, 184, 0.15);
            cursor: not-allowed;
            pointer-events: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 1. 顶部标题
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown('<div class="fb-title">💥 15分钟假跌破 + 4.236 爆发扫描</div>', unsafe_allow_html=True)
    with col_t2:
        pass

    st.markdown(
        """
        <div class="fb-banner">
            🎯 <b>核心筛选逻辑</b>：在 <b>15分钟 (15m)</b> 图表上，识别 <b>Higher Low (0点 > 前低 且未破前低)</b>，经假跌破探底拉回后，价格强势突破 <b>1点颈线</b>，并最终触碰或超越 <b>4.236 斐波那契延伸位</b> 的超强势爆发品种。
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. 读取数据
    all_records = storage.load_failed_breakdown()

    # 3. URL 状态双向同步与免密 Token 保留
    _url_stat = st.query_params.get("_stat", "all")
    _url_time = st.query_params.get("_time", "all")
    _url_sort = st.query_params.get("_sort", "gain_desc")
    _url_q = st.query_params.get("_q", "")
    _url_ps = st.query_params.get("_ps", "20")

    if "fb_filter_status" not in st.session_state:
        st.session_state["fb_filter_status"] = _STAT_MAP.get(_url_stat, "全部状态")
    if "fb_filter_time" not in st.session_state:
        st.session_state["fb_filter_time"] = _TIME_MAP.get(_url_time, "全部时效")
    if "fb_sort_by" not in st.session_state:
        st.session_state["fb_sort_by"] = _SORT_MAP.get(_url_sort, "🔥 爆发涨幅最高")
    if "fb_search_query" not in st.session_state:
        st.session_state["fb_search_query"] = _url_q
    if "fb_page_size" not in st.session_state:
        try:
            st.session_state["fb_page_size"] = int(_url_ps)
        except Exception:
            st.session_state["fb_page_size"] = 20

    def _sync_fb_url_params(target_page: int = 1):
        params = {}
        _t_val = st.query_params.get("_t", "") or st.session_state.get("_t", "")
        if _t_val:
            params["_t"] = _t_val

        for k, v in st.query_params.items():
            if not k.startswith("_"):
                params[k] = v
        params["_page"] = "failed_breakdown"

        _cur_stat = st.session_state.get("fb_filter_status", "全部状态")
        _stat_k = _STAT_REVERSE_MAP.get(_cur_stat, "all")
        if _stat_k != "all":
            params["_stat"] = _stat_k

        _cur_time = st.session_state.get("fb_filter_time", "全部时效")
        _time_k = _TIME_REVERSE_MAP.get(_cur_time, "all")
        if _time_k != "all":
            params["_time"] = _time_k

        _cur_sort = st.session_state.get("fb_sort_by", "🔥 爆发涨幅最高")
        _sort_k = _SORT_REVERSE_MAP.get(_cur_sort, "gain_desc")
        if _sort_k != "gain_desc":
            params["_sort"] = _sort_k

        _cur_q = str(st.session_state.get("fb_search_query", "")).strip()
        if _cur_q:
            params["_q"] = _cur_q

        _cur_ps = st.session_state.get("fb_page_size", 20)
        if _cur_ps != 20:
            params["_ps"] = str(_cur_ps)

        params["_p"] = str(target_page)

        st.query_params.clear()
        st.query_params.update(params)

    # 4. 统计卡片
    hit_count = sum(1 for r in all_records if r.get("is_hit_4236"))
    active_count = sum(1 for r in all_records if not r.get("is_hit_4236"))
    avg_gain = round(float(np.mean([r.get("gain_pct", 0) for r in all_records if r.get("is_hit_4236")])), 1) if hit_count > 0 else 0.0

    st.markdown(
        f"""
        <div class="fb-stat-grid">
            <div class="fb-stat-card">
                <div class="fb-stat-val">💥 {hit_count}</div>
                <div class="fb-stat-lbl">已达成 4.236 爆发品种</div>
            </div>
            <div class="fb-stat-card">
                <div class="fb-stat-val" style="color:#60a5fa;">🚀 {active_count}</div>
                <div class="fb-stat-lbl">突破颈线推进中</div>
            </div>
            <div class="fb-stat-card">
                <div class="fb-stat-val" style="color:#10b981;">📈 +{avg_gain}%</div>
                <div class="fb-stat-lbl">4.236 达成平均涨幅</div>
            </div>
            <div class="fb-stat-card">
                <div class="fb-stat-val" style="color:#cbd5e1;">📊 {len(all_records)}</div>
                <div class="fb-stat-lbl">总检出记录数</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 5. 操作栏：Colab 脚本生成器、CSV 导入/导出、快照管理
    with st.expander("🛠️ 扫描与数据管理 (Google Colab 脚本生成 / CSV 导入导出 / 快照备份)", expanded=False):
        tab_colab, tab_csv, tab_snap = st.tabs(["🚀 Google Colab 极速扫描", "📥 导入与导出 CSV", "📦 快照备份与恢复"])

        with tab_colab:
            st.markdown("#### 🚀 一键生成 15m 假跌破+4.236 爆发 Colab 极速扫描脚本")
            st.caption("脚本内置 Yahoo Finance 高并发异步引擎，每秒可扫描 50+ 只品种。运行后会自动下载 `colab_failed_breakdown_results.csv`。")

            c_p1, c_p2 = st.columns([2, 1])
            with c_p1:
                pool_choice = st.selectbox(
                    "选择扫描股票池",
                    ["系统全品种库", "A 股股票池 (沪深京)", "美股主要品种池 (标普/纳指)", "我的收藏夹自选股"],
                    key="fb_colab_pool_sel",
                )
            with c_p2:
                min_vol_val = st.number_input("最小均量过滤 (股)", min_value=0, value=50000, step=10000, key="fb_colab_vol_min")

            tickers_to_scan = []
            if pool_choice == "我的收藏夹自选股":
                wl = storage.load_watchlist()
                tickers_to_scan = [w.get("ticker", "") for w in wl if w.get("ticker")]
            elif pool_choice == "A 股股票池 (沪深京)":
                syms = storage.load_symbols()
                tickers_to_scan = [s.get("ticker", "") for s in syms if any(str(s.get("ticker", "")).endswith(x) for x in (".SS", ".SZ", ".BJ"))]
            elif pool_choice == "美股主要品种池 (标普/纳指)":
                syms = storage.load_symbols()
                tickers_to_scan = [s.get("ticker", "") for s in syms if not any(str(s.get("ticker", "")).endswith(x) for x in (".SS", ".SZ", ".BJ"))]
            else:
                syms = storage.load_symbols()
                tickers_to_scan = [s.get("ticker", "") for s in syms if s.get("ticker")]

            if not tickers_to_scan:
                tickers_to_scan = ["MRVL", "NVDA", "AAPL", "AMD", "TSLA", "MSFT", "GOOGL", "AMZN", "META", "601919.SS", "002230.SZ", "300059.SZ"]

            st.write(f"当前选定股票池: **{len(tickers_to_scan)}** 支品种")
            script_code = colab_failed_breakdown_script.generate_colab_script_for_tickers(
                tickers_to_scan, pool_name=pool_choice, min_volume=int(min_vol_val)
            )

            st.code(script_code[:1200] + "\n\n# ... (完整代码已生成，点击下方按钮下载) ...", language="python")
            st.download_button(
                "📥 下载完整 Colab 扫描脚本 (.py)",
                data=script_code,
                file_name="run_failed_breakdown_15m_scan.py",
                mime="text/x-python",
                use_container_width=True,
            )

        with tab_csv:
            st.markdown("#### 📥 导入 Colab 扫描结果 CSV")
            uploaded_file = st.file_uploader(
                "拖入 colab_failed_breakdown_results.csv",
                type=["csv"],
                key="fb_csv_uploader",
            )
            if uploaded_file is not None:
                try:
                    df_up = pd.read_csv(uploaded_file)
                    new_records = df_up.to_dict(orient="records")
                    if st.button("🚀 一键合并导入到系统", type="primary", key="fb_btn_import"):
                        ok = storage.append_failed_breakdown_results(new_records)
                        if ok:
                            st.success(f"🎉 成功导入 {len(new_records)} 条记录！")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("导入保存失败")
                except Exception as e:
                    st.error(f"解析 CSV 失败: {e}")

            st.divider()
            st.markdown("#### 📤 导出当前数据")
            if all_records:
                df_export = pd.DataFrame(all_records)
                csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    "📥 导出为 CSV 文件",
                    data=csv_bytes,
                    file_name=f"failed_breakdown_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        with tab_snap:
            st.markdown("#### 📦 快照备份与恢复")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                if st.button("💾 创建当前数据快照", use_container_width=True, key="fb_btn_snap"):
                    sid = storage.backup_failed_breakdown(all_records)
                    if sid:
                        st.success(f"✅ 快照已生成: {sid}")
                    else:
                        st.info("数据为空，无需备份")
            with col_s2:
                if st.button("🗑️ 清空所有扫描结果", type="secondary", use_container_width=True, key="fb_btn_clear"):
                    storage.clear_failed_breakdown_results()
                    st.warning("已清空当前扫描数据（自动创建了快照）。")
                    time.sleep(1)
                    st.rerun()

            snaps = storage.load_fb_snapshots()
            if snaps:
                st.write(f"历史快照数量: {len(snaps)}")
                for sp in snaps[:5]:
                    col_sp1, col_sp2 = st.columns([3, 1])
                    with col_sp1:
                        st.write(f"🗂️ `{sp['session_id']}` ({sp['scan_time']}) · {sp['count']} 条")
                    with col_sp2:
                        if st.button("恢复", key=f"fb_restore_{sp['session_id']}"):
                            ok, msg, cnt = storage.restore_fb_snapshot(sp['session_id'])
                            if ok:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)

    # 6. 筛选控制栏
    f_c1, f_c2, f_c3, f_c4, f_c5 = st.columns([1.5, 1.2, 1.5, 1.5, 1.2])

    with f_c1:
        cur_stat_val = st.selectbox(
            "形态状态",
            list(_STAT_MAP.values()),
            index=list(_STAT_MAP.values()).index(st.session_state["fb_filter_status"])
            if st.session_state["fb_filter_status"] in _STAT_MAP.values() else 0,
            key="fb_filter_status_widget",
        )
        if cur_stat_val != st.session_state["fb_filter_status"]:
            st.session_state["fb_filter_status"] = cur_stat_val
            _sync_fb_url_params(target_page=1)
            st.rerun()

    with f_c2:
        cur_time_val = st.selectbox(
            "时间时效",
            list(_TIME_MAP.values()),
            index=list(_TIME_MAP.values()).index(st.session_state["fb_filter_time"])
            if st.session_state["fb_filter_time"] in _TIME_MAP.values() else 0,
            key="fb_filter_time_widget",
        )
        if cur_time_val != st.session_state["fb_filter_time"]:
            st.session_state["fb_filter_time"] = cur_time_val
            _sync_fb_url_params(target_page=1)
            st.rerun()

    with f_c3:
        cur_sort_val = st.selectbox(
            "排序方式",
            list(_SORT_MAP.values()),
            index=list(_SORT_MAP.values()).index(st.session_state["fb_sort_by"])
            if st.session_state["fb_sort_by"] in _SORT_MAP.values() else 0,
            key="fb_sort_by_widget",
        )
        if cur_sort_val != st.session_state["fb_sort_by"]:
            st.session_state["fb_sort_by"] = cur_sort_val
            _sync_fb_url_params(target_page=1)
            st.rerun()

    with f_c4:
        search_query = st.text_input(
            "搜索品种",
            value=st.session_state.get("fb_search_query", ""),
            placeholder="输入代码或名称 (如 MRVL)...",
            key="fb_search_query_widget",
        )
        if search_query != st.session_state.get("fb_search_query", ""):
            st.session_state["fb_search_query"] = search_query
            _sync_fb_url_params(target_page=1)
            st.rerun()

    with f_c5:
        ps_options = [20, 50, 100]
        cur_ps_val = st.selectbox(
            "每页条数",
            ps_options,
            index=ps_options.index(st.session_state["fb_page_size"])
            if st.session_state["fb_page_size"] in ps_options else 0,
            key="fb_page_size_widget",
        )
        if cur_ps_val != st.session_state["fb_page_size"]:
            st.session_state["fb_page_size"] = cur_ps_val
            _sync_fb_url_params(target_page=1)
            st.rerun()

    # 7. 过滤数据
    filtered = []
    now = datetime.now()

    for r in all_records:
        if cur_stat_val == "💥 已达成 4.236 (爆发确认)" and not r.get("is_hit_4236"):
            continue
        if cur_stat_val == "🚀 突破推进中" and r.get("is_hit_4236"):
            continue

        if cur_time_val != "全部时效":
            t_str = r.get("breakout_time") or r.get("scan_time") or ""
            try:
                dt_obj = datetime.fromisoformat(t_str) if "T" in t_str else datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                diff = now - dt_obj
                if cur_time_val == "最近 24 小时" and diff > timedelta(days=1):
                    continue
                elif cur_time_val == "最近 3 天" and diff > timedelta(days=3):
                    continue
                elif cur_time_val == "最近 7 天" and diff > timedelta(days=7):
                    continue
                elif cur_time_val == "最近 30 天" and diff > timedelta(days=30):
                    continue
            except Exception:
                pass

        if search_query:
            sym = str(r.get("symbol", "")).upper()
            name = _fetch_name(sym).upper()
            q_clean = search_query.strip().upper()
            if q_clean not in sym and q_clean not in name:
                continue

        filtered.append(r)

    # 8. 排序
    if cur_sort_val == "🔥 爆发涨幅最高":
        filtered.sort(key=lambda x: (x.get("is_hit_4236", False), float(x.get("gain_pct", 0.0))), reverse=True)
    elif cur_sort_val == "🌟 斐波倍数最高":
        filtered.sort(key=lambda x: float(x.get("fibo_multiple", 0.0)), reverse=True)
    elif cur_sort_val == "⏱️ 最新突破触发":
        filtered.sort(key=lambda x: str(x.get("breakout_time", x.get("scan_time", ""))), reverse=True)
    elif cur_sort_val == "📊 20根均量最高":
        filtered.sort(key=lambda x: float(x.get("avg_volume_20", 0.0)), reverse=True)

    # 9. 分页
    page_size = st.session_state.get("fb_page_size", 20)
    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    try:
        cur_page = int(st.query_params.get("_p", "1"))
    except Exception:
        cur_page = 1
    cur_page = max(1, min(cur_page, total_pages))

    start_idx = (cur_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = filtered[start_idx:end_idx]

    def _make_fb_page_url(target_p: int) -> str:
        params = {}
        _t_val = st.query_params.get("_t", "") or st.session_state.get("_t", "")
        if _t_val:
            params["_t"] = _t_val

        for k, v in st.query_params.items():
            if not k.startswith("_"):
                params[k] = v
        params["_page"] = "failed_breakdown"

        _stat_k = _STAT_REVERSE_MAP.get(cur_stat_val, "all")
        if _stat_k != "all":
            params["_stat"] = _stat_k

        _time_k = _TIME_REVERSE_MAP.get(cur_time_val, "all")
        if _time_k != "all":
            params["_time"] = _time_k

        _sort_k = _SORT_REVERSE_MAP.get(cur_sort_val, "gain_desc")
        if _sort_k != "gain_desc":
            params["_sort"] = _sort_k

        if search_query:
            params["_q"] = search_query

        if page_size != 20:
            params["_ps"] = str(page_size)

        params.pop("_p", None)
        params["_p"] = str(target_p)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"/?{qs}"

    def _render_pagination_bar():
        if total_pages <= 1:
            return
        p_links = []
        if cur_page > 1:
            p_links.append(f'<a href="{_make_fb_page_url(1)}" target="_self" style="color:#f97316;text-decoration:none;padding:4px 8px;border:1px solid rgba(249,115,22,0.3);border-radius:4px;margin-right:6px;">⏮ 首页</a>')
            p_links.append(f'<a href="{_make_fb_page_url(cur_page - 1)}" target="_self" style="color:#f97316;text-decoration:none;padding:4px 8px;border:1px solid rgba(249,115,22,0.3);border-radius:4px;margin-right:8px;">◀ 上一页</a>')
        else:
            p_links.append('<span style="color:#64748b;padding:4px 8px;border:1px solid rgba(255,255,255,0.05);border-radius:4px;margin-right:6px;">⏮ 首页</span>')
            p_links.append('<span style="color:#64748b;padding:4px 8px;border:1px solid rgba(255,255,255,0.05);border-radius:4px;margin-right:8px;">◀ 上一页</span>')

        p_links.append(f'<span style="color:#f8fafc;font-weight:700;margin:0 10px;">第 {cur_page} / {total_pages} 页 (共 {total_items} 支)</span>')

        if cur_page < total_pages:
            p_links.append(f'<a href="{_make_fb_page_url(cur_page + 1)}" target="_self" style="color:#f97316;text-decoration:none;padding:4px 8px;border:1px solid rgba(249,115,22,0.3);border-radius:4px;margin-left:8px;margin-right:6px;">下一页 ▶</a>')
            p_links.append(f'<a href="{_make_fb_page_url(total_pages)}" target="_self" style="color:#f97316;text-decoration:none;padding:4px 8px;border:1px solid rgba(249,115,22,0.3);border-radius:4px;">末页 ⏭</a>')
        else:
            p_links.append('<span style="color:#64748b;padding:4px 8px;border:1px solid rgba(255,255,255,0.05);border-radius:4px;margin-left:8px;margin-right:6px;">下一页 ▶</span>')
            p_links.append('<span style="color:#64748b;padding:4px 8px;border:1px solid rgba(255,255,255,0.05);border-radius:4px;">末页 ⏭</span>')

        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:center;margin:14px 0;font-size:13px;">{"".join(p_links)}</div>',
            unsafe_allow_html=True,
        )

    _render_pagination_bar()

    # 10. 渲染品种卡片列表
    if not page_items:
        st.info("💡 当前筛选条件下无符合品种，请尝试放宽筛选条件或在上方生成 Colab 脚本进行新一轮全市场扫描。")
    else:
        starred_tickers = set(storage.load_starred_tickers())

        for r in page_items:
            ticker = str(r.get("symbol", "")).upper()
            name = _fetch_name(ticker)
            is_hit = r.get("is_hit_4236", False)
            gain_pct = r.get("gain_pct", 0.0)
            fibo_mult = r.get("fibo_multiple", 0.0)

            p_prev_low = r.get("pt_prev_low", 0.0)
            p_low_0 = r.get("pt_low_0", 0.0)
            p_high_1 = r.get("pt_high_1", r.get("neckline", 0.0))
            fib_4236 = r.get("fib_4236", 0.0)
            max_high = r.get("max_high_post", 0.0)
            latest_close = r.get("latest_close", 0.0)

            breakout_time = r.get("breakout_time") or r.get("scan_time") or "—"
            tv_url = _tv_link(ticker, "15m")
            sina_url = _sina_link(ticker)
            is_starred = ticker in starred_tickers

            prog_pct = min(100.0, max(0.0, (fibo_mult / 4.236) * 100.0)) if fibo_mult > 0 else 0.0

            card_cls = "fb-card fb-card-hit" if is_hit else "fb-card"
            badge_html = (
                f'<span class="fb-badge-hit">💥 达成 4.236 延伸位 (+{gain_pct}%)</span>'
                if is_hit
                else f'<span class="fb-badge-active">🚀 突破颈线推进中 (+{gain_pct}%)</span>'
            )

            market_lbl = "A股" if any(ticker.endswith(x) for x in (".SS", ".SZ", ".BJ")) else "美股"

            st.markdown(
                f"""
                <div class="{card_cls}">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div style="display:flex;align-items:center;gap:10px;">
                            <span style="font-size:18px;font-weight:800;color:#f8fafc;">{ticker}</span>
                            <span style="font-size:14px;color:#94a3b8;">{name}</span>
                            <span style="font-size:11px;background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px;color:#94a3b8;">{market_lbl} · 15m</span>
                        </div>
                        <div>
                            {badge_html}
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:8px;font-size:12.5px;margin-bottom:10px;background:rgba(0,0,0,0.25);padding:10px;border-radius:6px;">
                        <div><span style="color:#64748b;">前局部低:</span> <b style="color:#94a3b8;">{p_prev_low}</b></div>
                        <div><span style="color:#64748b;">0点 (Higher Low):</span> <b style="color:#38bdf8;">{p_low_0}</b></div>
                        <div><span style="color:#64748b;">1点 (15m颈线):</span> <b style="color:#fbbf24;">{p_high_1}</b></div>
                        <div><span style="color:#64748b;">4.236 目标位:</span> <b style="color:#f97316;">{fib_4236}</b></div>
                        <div><span style="color:#64748b;">最高触碰:</span> <b style="color:#4ade80;">{max_high}</b></div>
                        <div><span style="color:#64748b;">斐波延伸:</span> <b style="color:#f97316;">{fibo_mult}x</b></div>
                    </div>
                    <div>
                        <div style="display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;">
                            <span>斐波那契延伸进度</span>
                            <span><b>{prog_pct:.1f}%</b> (当前倍数: {fibo_mult}x / 4.236x)</span>
                        </div>
                        <div class="fb-progress-container">
                            <div class="fb-progress-bar" style="width: {prog_pct}%;"></div>
                        </div>
                        <div class="fb-ladder">
                            <span>0 (0点)</span>
                            <span>1.0 (颈线)</span>
                            <span>1.618</span>
                            <span>2.618</span>
                            <span>3.618</span>
                            <span style="color:#f97316;font-weight:700;">4.236 (目标)</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_b1, col_b2, col_b3, col_b4 = st.columns([2, 2, 2, 4])
            with col_b1:
                st.markdown(
                    f'<a href="{tv_url}" target="_blank" data-ticker="{ticker}" class="tv-link" style="display:inline-flex;align-items:center;justify-content:center;width:100%;padding:6px 12px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-size:12px;font-weight:600;text-align:center;">📈 TradingView 15m</a>',
                    unsafe_allow_html=True,
                )
            with col_b2:
                st.markdown(
                    f'<a href="{sina_url}" target="_blank" style="display:inline-flex;align-items:center;justify-content:center;width:100%;padding:6px 12px;background:rgba(255,255,255,0.06);color:#cbd5e1;text-decoration:none;border-radius:6px;font-size:12px;text-align:center;">📰 行情/资讯</a>',
                    unsafe_allow_html=True,
                )
            with col_b3:
                star_btn_lbl = "⭐ 已收藏" if is_starred else "☆ 收藏"
                if st.button(star_btn_lbl, key=f"fb_star_{ticker}", use_container_width=True):
                    storage.toggle_star_ticker(ticker)
                    st.rerun()
            with col_b4:
                st.caption(f"突破时间: {breakout_time} | 20根均量: {r.get('avg_volume_20', 0):,.0f}")

    _render_pagination_bar()

    _js_code = """
    <script>
    (function() {
        try {
            var pDoc = window.parent.document;
            if (pDoc._tv_click_handler) {
                pDoc.removeEventListener('click', pDoc._tv_click_handler, true);
            }
            pDoc._tv_click_handler = function(e) {
                var target = e.target.closest('a');
                if (target && target.href && target.href.indexOf('tradingview.com') !== -1) {
                    var tk = target.getAttribute('data-ticker') || '';
                    if (!tk) {
                        var match = target.href.match(/symbol=([^&]+)/);
                        if (match && match[1]) {
                            tk = decodeURIComponent(match[1]).replace(/^(SSE:|SZSE:|BSE:)/, '');
                        }
                    }
                    if (tk) {
                        try {
                            if (window.parent && window.parent.__sendTvClickToStreamlit) {
                                window.parent.__sendTvClickToStreamlit(tk);
                            }
                        } catch(err) {}
                    }
                }
            };
            pDoc.addEventListener('click', pDoc._tv_click_handler, true);
        } catch(err) {}
    })();
    </script>
    """
    if hasattr(st, "html"):
        st.html(_js_code)
    else:
        import streamlit.components.v1 as _components
        _components.html(_js_code, height=0, width=0)




if __name__ == "__main__":
    render_failed_breakdown_page()
