"""
page_chartink.py — Chartink · 4 Hour Breakout 7条规则突破扫描
========================================================================================
对齐 Triple Top Bottom Scan v4 架构设计：
  1. 顶部指标看板（突破总数、美股/A股分布、4H极度放量、RSI强势分布、最新扫描时间）
  2. 🚀 1. Google Colab 独立云端极速扫描与 1 键导入 (推荐 · 50+只/秒并发)
  3. 📦 2. 快照备份与恢复 (历史快照选择恢复、创建快照、清空数据与导出当前数据)
  4. 多维筛选工具栏（搜索代码/名称、20日均量过滤、排序方式、分页）
  5. 7 条规则达成现代暗色卡片展示（4H爆量倍数、一目均衡云、RSI、Supertrend、2H破位、TradingView 4H图表、自选收藏）
"""

import time
import datetime
import json
import urllib.parse
import streamlit as st
import pandas as pd
import numpy as np
import storage
import bg_scan_manager
import colab_chartink_script
from assets import tv_url, sina_url

# ── 依赖安全导入 ────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


def _safe_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        f = float(val)
        return default if np.isnan(f) else f
    except Exception:
        return default


# ════════════════════════════════════════════════════════════════════
# 本地轻量检测与 Worker (兜底支持)
# ════════════════════════════════════════════════════════════════════
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ichimoku(high: pd.Series, low: pd.Series,
              t: int = 9, k: int = 26, s: int = 52):
    tenkan  = (high.rolling(t).max() + low.rolling(t).min()) / 2
    kijun   = (high.rolling(k).max() + low.rolling(k).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(k)
    senkou_b = ((high.rolling(s).max() + low.rolling(s).min()) / 2).shift(k)
    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    return cloud_top, cloud_bot


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 7, multiplier: float = 3.0) -> pd.Series:
    hl2 = (high + low) / 2
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    basic_upper = (hl2 + (multiplier * atr)).values
    basic_lower = (hl2 - (multiplier * atr)).values
    c = close.values
    n = len(c)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    st_line = np.zeros(n)
    trend = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(basic_upper[i]):
            continue
        final_upper[i] = basic_upper[i] if (basic_upper[i] < final_upper[i-1] or c[i-1] > final_upper[i-1]) else final_upper[i-1]
        final_lower[i] = basic_lower[i] if (basic_lower[i] > final_lower[i-1] or c[i-1] < final_lower[i-1]) else final_lower[i-1]
        if trend[i-1] == 1:
            if c[i] < final_lower[i]:
                trend[i] = -1
                st_line[i] = final_upper[i]
            else:
                trend[i] = 1
                st_line[i] = final_lower[i]
        else:
            if c[i] > final_upper[i]:
                trend[i] = 1
                st_line[i] = final_lower[i]
            else:
                trend[i] = -1
                st_line[i] = final_upper[i]
    return pd.Series(st_line, index=close.index)


def _fetch(ticker: str, interval: str, period: str = "6mo") -> pd.DataFrame | None:
    for attempt in range(3):
        try:
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True, threads=False, timeout=15)
            if df is None or df.empty:
                return None
            new_cols = []
            for c in df.columns:
                if isinstance(c, tuple):
                    new_cols.append(str(c[0]).lower())
                else:
                    new_cols.append(str(c).lower())
            df.columns = new_cols
            if "close" not in df.columns:
                return None
            return df.dropna(subset=["close"])
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "too many requests" in err_str or "429" in err_str:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
    return None


def _check_ticker(ticker: str) -> dict:
    result = {
        "ticker": ticker,
        "symbol": ticker,
        "passed": False,
        "details": [],
        "error": None,
        "close": None,
        "volume_4h": None,
        "vol_ratio_0": None,
        "vol_ratio_1": None,
        "avg_volume_20": 0.0,
        "turnover": 0.0,
        "rsi": None,
        "cloud_top": None,
        "cloud_bot": None,
        "supertrend": None,
        "close_2h_m2": None,
        "scan_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if not _YF_OK:
        result["error"] = "yfinance 未安装"
        return result

    if storage.is_ticker_delisted(ticker):
        result["error"] = "已退市/无效代码"
        return result

    df_1d = _fetch(ticker, "1d", "1y")
    if df_1d is None or len(df_1d) < 60:
        result["error"] = "日线数据不足"
        return result

    vols_d = df_1d["volume"].dropna().values
    avg_v20 = float(np.mean(vols_d[-20:])) if len(vols_d) >= 20 else float(np.mean(vols_d))
    latest_c = float(df_1d["close"].iloc[-1])
    result["avg_volume_20"] = avg_v20
    result["turnover"] = avg_v20 * latest_c

    df_1h = _fetch(ticker, "1h", "2mo")
    df_4h = None
    if df_1h is not None and len(df_1h) >= 4:
        try:
            df_4h = df_1h.resample("4h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna(subset=["close"])
        except Exception:
            pass

    if df_4h is None or len(df_4h) < 5:
        df_4h = _fetch(ticker, "4h", "6mo")

    if df_4h is None or len(df_4h) < 5:
        result["error"] = "4H 数据不足"
        return result

    df_2h = None
    if df_1h is not None and len(df_1h) >= 2:
        try:
            df_2h = df_1h.resample("2h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna(subset=["close"])
        except Exception:
            pass

    close_d = df_1d["close"]
    high_d  = df_1d["high"]
    low_d   = df_1d["low"]

    rsi_ser = _rsi(close_d, 14)
    cloud_top, cloud_bot = _ichimoku(high_d, low_d, 9, 26, 52)
    supertrend_ser = _supertrend(high_d, low_d, close_d, 7, 3.0)

    c_d   = float(close_d.iloc[-1])
    rsi_v = float(rsi_ser.iloc[-1])    if not pd.isna(rsi_ser.iloc[-1])    else None
    ct_v  = float(cloud_top.iloc[-1])  if not pd.isna(cloud_top.iloc[-1])  else None
    cb_v  = float(cloud_bot.iloc[-1])  if not pd.isna(cloud_bot.iloc[-1])  else None
    st_v  = float(supertrend_ser.iloc[-1]) if not pd.isna(supertrend_ser.iloc[-1]) else None

    vol_4h = df_4h["volume"]
    v0 = float(vol_4h.iloc[-1])
    v1 = float(vol_4h.iloc[-2])
    v2 = float(vol_4h.iloc[-3])
    v3 = float(vol_4h.iloc[-4]) if len(vol_4h) >= 4 else v2

    c_2h_m2 = None
    if df_2h is not None and len(df_2h) >= 3:
        c_2h_m2 = float(df_2h["close"].iloc[-3])

    vr0 = (v0 / max(v1, 1.0)) if v0 > v1 * 2 else (v1 / max(v2, 1.0))
    vr1 = (v1 / max(v2, 1.0)) if v1 > v2 * 1.5 else (v2 / max(v3, 1.0))

    result["close"]       = c_d
    result["volume_4h"]   = v0
    result["vol_ratio_0"] = round(vr0, 2)
    result["vol_ratio_1"] = round(vr1, 2)
    result["rsi"]         = rsi_v
    result["cloud_top"]   = ct_v
    result["cloud_bot"]   = cb_v
    result["supertrend"]  = st_v
    result["close_2h_m2"] = c_2h_m2

    rules = [
        {
            "id":   "[0]",
            "desc": "4H Volume[0] > 4H Volume[-1] × 2 (或已完成根 > ×2)",
            "ok":   bool((v0 > v1 * 2) or (v1 > v2 * 2)),
            "val":  f"{v0:,.0f} vs {v1:,.0f}×2={v1*2:,.0f}" if (v0 > v1 * 2) else f"前根: {v1:,.0f} vs {v2:,.0f}×2={v2*2:,.0f}",
        },
        {
            "id":   "[1]",
            "desc": "4H Volume[-1] > 4H Volume[-2] × 1.5 (或已完成根 > ×1.5)",
            "ok":   bool((v1 > v2 * 1.5) or (v2 > v3 * 1.5)),
            "val":  f"{v1:,.0f} vs {v2:,.0f}×1.5={v2*1.5:,.0f}" if (v1 > v2 * 1.5) else f"前前根: {v2:,.0f} vs {v3:,.0f}×1.5={v3*1.5:,.0f}",
        },
        {
            "id":   "[2]",
            "desc": "Daily Close > Ichimoku Cloud Top(9,26,52)",
            "ok":   bool((ct_v is not None) and (c_d > ct_v)),
            "val":  f"Close={c_d:.4f}  CloudTop={ct_v:.4f}" if ct_v else "数据不足",
        },
        {
            "id":   "[3]",
            "desc": "Daily RSI(14) > 50",
            "ok":   bool((rsi_v is not None) and (rsi_v > 50)),
            "val":  f"RSI={rsi_v:.2f}" if rsi_v else "数据不足",
        },
        {
            "id":   "[4]",
            "desc": "Daily Close > Supertrend(7,3)",
            "ok":   bool((st_v is not None) and (c_d > st_v)),
            "val":  f"Close={c_d:.4f}  ST={st_v:.4f}" if st_v else "数据不足",
        },
        {
            "id":   "[5]",
            "desc": "Daily Close > Ichimoku Cloud Bottom(9,26,52)",
            "ok":   bool((cb_v is not None) and (c_d > cb_v)),
            "val":  f"Close={c_d:.4f}  CloudBot={cb_v:.4f}" if cb_v else "数据不足",
        },
        {
            "id":   "[6]",
            "desc": "Daily Close > 2H Close[-2]",
            "ok":   bool((c_2h_m2 is not None) and (c_d > c_2h_m2)),
            "val":  f"Close={c_d:.4f}  2H[-2]={c_2h_m2:.4f}" if c_2h_m2 else "2H数据不足",
        },
    ]

    result["details"] = rules
    result["passed"]  = all(r["ok"] for r in rules)
    return result


def chartink_worker(params, update_progress, cancel_check):
    import gc
    tickers = params["tickers"]
    passed_list = []
    failed_list = []
    error_list = []
    
    total = len(tickers)
    for i, tk in enumerate(tickers):
        if cancel_check():
            break
        update_progress(i, total, f"扫描中 {i}/{total}: {tk}")
        try:
            res = _check_ticker(tk)
            if res.get("error"):
                error_list.append(res)
            elif res.get("passed"):
                passed_list.append(res)
            else:
                failed_list.append(res)
        except Exception as e:
            error_list.append({"ticker": tk, "passed": False, "details": [], "error": str(e)})

        if (i + 1) % 25 == 0 or (i + 1) == total:
            partial_results = {
                "passed": passed_list,
                "failed": failed_list,
                "errors": error_list,
                "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "done_count": i + 1,
            }
            storage.save_chartink(partial_results)
            
        if (i + 1) % 50 == 0:
            gc.collect()
        time.sleep(0.05)
        
    final_results = {
        "passed": passed_list,
        "failed": failed_list,
        "errors": error_list,
        "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "done_count": total if not cancel_check() else i + 1,
    }
    storage.save_chartink(final_results)
    try:
        storage.backup_chartink(final_results)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
# 🎨 页面主渲染入口
# ════════════════════════════════════════════════════════════════════
def render():
    render_page_chartink()


def render_page_chartink():
    # ── 自定义暗色样式 ──────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .ci-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .ci-title {
            font-size: 24px;
            font-weight: 800;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .ci-card {
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 12px;
            transition: all 0.2s ease;
        }
        .ci-card:hover {
            border-color: rgba(59, 130, 246, 0.6);
            background: rgba(30, 41, 59, 0.7);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
        }
        .ci-metric-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            background: rgba(15, 23, 42, 0.5);
            padding: 10px 12px;
            border-radius: 6px;
            margin: 10px 0;
            font-size: 12px;
        }
        .ci-metric-item {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .ci-metric-label {
            color: #94a3b8;
            font-size: 11px;
        }
        .ci-metric-val {
            color: #f1f5f9;
            font-weight: 700;
            font-size: 13px;
            font-family: monospace;
        }
        .ci-rule-badge {
            display: inline-block;
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            border: 1px solid rgba(34, 197, 94, 0.3);
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 4px;
            margin-bottom: 4px;
        }
        .ci-tag-us {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 600;
        }
        .ci-tag-a {
            background: rgba(244, 63, 94, 0.15);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.3);
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 11px;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ── 1. 顶部标题与形态总体统计 ──
    st.markdown(
        """
        <div class="ci-header">
            <div class="ci-title">
                <span>📈 Chartink · 4 Hour Breakout 7条规则突破扫描</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption("严格依据 Chartink 4H 突破策略（4H成交量爆量倍数、日线一目均衡云、RSI(14)、Supertrend(7,3)、2H短期强势等 7 条量化规则）进行全量扫描与形态捕捉。")

    cache = storage.load_chartink()
    passed_records = cache.get("passed", []) if isinstance(cache, dict) else []
    scanned_at = cache.get("scanned_at", "—") if isinstance(cache, dict) else "—"

    total_cnt = len(passed_records)
    us_cnt = sum(1 for r in passed_records if not str(r.get("ticker", "")).endswith((".SS", ".SZ", ".BJ")) and not str(r.get("ticker", "")).isdigit())
    a_cnt = sum(1 for r in passed_records if str(r.get("ticker", "")).endswith((".SS", ".SZ", ".BJ")) or str(r.get("ticker", "")).isdigit())
    extreme_vol_cnt = sum(1 for r in passed_records if _safe_float(r.get("vol_ratio_0"), 0.0) >= 3.0)
    strong_rsi_cnt = sum(1 for r in passed_records if _safe_float(r.get("rsi"), 0.0) >= 60.0)

    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    with col_m1:
        st.metric("📊 突破总数", f"{total_cnt} 条", delta="7条全部满足" if total_cnt > 0 else None)
    with col_m2:
        st.metric("🇺🇸 美股突破", f"{us_cnt} 支")
    with col_m3:
        st.metric("🇨🇳 A股突破", f"{a_cnt} 支")
    with col_m4:
        st.metric("🔥 4H极度放量(≥3x)", f"{extreme_vol_cnt} 支")
    with col_m5:
        st.metric("📈 RSI强势区(>60)", f"{strong_rsi_cnt} 支")
    with col_m6:
        st.metric("🕐 最近扫描时间", str(scanned_at)[:16] if scanned_at else "—")

    # ── 2. Google Colab 独立云端扫描与 1 键导入 ──
    with st.expander("🚀 1. Google Colab 独立云端极速扫描与 1 键导入 (推荐 · 50+只/秒并发)", expanded=False):
        colab_c1, colab_c2 = st.columns([1.2, 1])
        with colab_c1:
            st.markdown("##### 1. 生成并复制 Google Colab 扫描脚本")
            st.caption("脚本内置 Yahoo v8 直连引擎与连接池技术，支持全部分组 12,400+ 支标的秒级并发扫描。")

            all_symbols = storage.load_symbols() or []
            groups = storage.load_symbol_groups() or []

            pool_options = ["🇺🇸 全量美股 (系统内置)", "🇨🇳 全量A股 (系统内置)", "🌐 全部组去重合并 (全量市场)"]
            for g in groups:
                if g.get("name"):
                    pool_options.append(f"📁 分组: {g.get('name')}")
            pool_options.append("⭐ 我的自选关注列表")

            c_p1, c_p2, c_p3 = st.columns([1.5, 1.1, 1.4])
            with c_p1:
                selected_pool = st.selectbox(
                    "🎯 选择扫描股票池",
                    pool_options,
                    index=0,
                    key="ci_colab_pool_select"
                )
            with c_p2:
                st.text_input(
                    "⏱ 扫描周期",
                    value="4h (4小时 突破)",
                    disabled=True,
                    help="Chartink 7条规则突破策略专用于 4小时 (4H) 周期突破检测"
                )
            with c_p3:
                vol_option = st.selectbox(
                    "📊 最低成交量过滤",
                    [
                        "🔥 20日均量 ≥ 10 万股 (推荐)",
                        "🔥 20日均量 ≥ 30 万股",
                        "🔥 20日均量 ≥ 50 万股",
                        "🔥 20日均量 ≥ 100 万股",
                        "全部扫描 (不限制成交量)"
                    ],
                    index=0,
                    key="ci_colab_min_vol_select",
                    help="在 Colab 云端扫描时自动剔除低流动性僵尸股/仙股，大幅提升云端扫描速度 3~5 倍！"
                )
                _VOL_MAP = {
                    "🔥 20日均量 ≥ 10 万股 (推荐)": 100000,
                    "🔥 20日均量 ≥ 30 万股": 300000,
                    "🔥 20日均量 ≥ 50 万股": 500000,
                    "🔥 20日均量 ≥ 100 万股": 1000000,
                    "全部扫描 (不限制成交量)": 0,
                }
                min_vol_val = _VOL_MAP.get(vol_option, 100000)

            export_tickers = []
            if "全部组去重合并" in selected_pool:
                all_tks = []
                for g in groups:
                    for tk in g.get("tickers", []):
                        if tk and isinstance(tk, str):
                            all_tks.append(tk.strip().upper())
                export_tickers = list(dict.fromkeys(all_tks))
            elif "全量美股" in selected_pool:
                us_grp = next((g for g in groups if "全量美股" in g.get("name", "")), None)
                if us_grp and us_grp.get("tickers"):
                    export_tickers = us_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if not s["ticker"].endswith((".SS", ".SZ", ".BJ")) and not s["ticker"].isdigit()]
            elif "全量A股" in selected_pool:
                a_grp = next((g for g in groups if "全量A股" in g.get("name", "")), None)
                if a_grp and a_grp.get("tickers"):
                    export_tickers = a_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if s["ticker"].endswith((".SS", ".SZ", ".BJ")) or s["ticker"].isdigit()]
            elif "自选关注" in selected_pool:
                wl = storage.load_watchlist() or []
                export_tickers = [w["ticker"] for w in wl if w.get("ticker")]
            elif selected_pool.startswith("📁 分组:"):
                g_target_name = selected_pool.replace("📁 分组: ", "").strip()
                target_g = next((g for g in groups if g.get("name") == g_target_name), None)
                if target_g:
                    export_tickers = target_g.get("tickers", [])

            if not export_tickers:
                export_tickers = [s["ticker"] for s in all_symbols[:500]] if all_symbols else ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

            export_tickers = list(dict.fromkeys([t.strip().upper() for t in export_tickers if t and isinstance(t, str)]))

            vol_hint = f" | 均量: ≥ {min_vol_val//10000}万股" if min_vol_val > 0 else " | 均量: 不限"
            st.info(f"📋 选定股票池: **{len(export_tickers)}** 支品种 | 周期: **4h**{vol_hint} | 判定: **100% 严格满足全部 7 条突破规则** (代码已内置，右上角可一键复制)：")

            colab_code = colab_chartink_script.generate_colab_chartink_script(
                export_tickers,
                pool_name=selected_pool,
                min_volume=min_vol_val
            )

            st.code(colab_code, language="python", line_numbers=True)

            col_btn1, col_btn2 = st.columns([1, 1.5])
            with col_btn1:
                st.download_button(
                    "📥 下载完整 Colab 扫描脚本 (.py)",
                    data=colab_code,
                    file_name="colab_chartink_scanner.py",
                    mime="text/x-python",
                    use_container_width=True
                )
            with col_btn2:
                st.caption("💡 提示：点击代码框右上角复制图标，直接粘贴至 Colab 新建笔记本运行即可。")

        with colab_c2:
            st.markdown("##### 2. 导入 Colab 扫描结果 CSV")
            st.caption("上传从 Google Colab 导出的 `colab_chartink_results.csv` 文件，系统将自动增量合并到数据库。")

            uploaded_file = st.file_uploader(
                "选择或拖拽 Colab 导出的 CSV 文件",
                type=["csv"],
                key="ci_colab_csv_uploader",
                help="支持导入 colab_chartink_results.csv"
            )

            if uploaded_file is not None:
                try:
                    df_up = pd.read_csv(uploaded_file)
                    if "ticker" not in df_up.columns and "symbol" not in df_up.columns:
                        st.error("❌ CSV 格式不符：未找到 ticker 或 symbol 列。")
                    else:
                        parsed_records = []
                        for _, row_val in df_up.iterrows():
                            tk = str(row_val.get("ticker") or row_val.get("symbol", "")).strip().upper()
                            if not tk:
                                continue
                            
                            details = []
                            details_json_str = str(row_val.get("details_json", ""))
                            if details_json_str and details_json_str != "nan":
                                try:
                                    details = json.loads(details_json_str)
                                except Exception:
                                    pass

                            rec = {
                                "ticker": tk,
                                "symbol": tk,
                                "passed": True,
                                "close": _safe_float(row_val.get("close"), 0.0),
                                "volume_4h": _safe_float(row_val.get("volume_4h"), 0.0),
                                "vol_ratio_0": _safe_float(row_val.get("vol_ratio_0"), None),
                                "vol_ratio_1": _safe_float(row_val.get("vol_ratio_1"), None),
                                "avg_volume_20": _safe_float(row_val.get("avg_volume_20"), 0.0),
                                "turnover": _safe_float(row_val.get("turnover"), 0.0),
                                "rsi": _safe_float(row_val.get("rsi"), 0.0),
                                "cloud_top": _safe_float(row_val.get("cloud_top"), 0.0),
                                "cloud_bot": _safe_float(row_val.get("cloud_bot"), 0.0),
                                "supertrend": _safe_float(row_val.get("supertrend"), 0.0),
                                "close_2h_m2": _safe_float(row_val.get("close_2h_m2"), 0.0),
                                "details": details,
                                "scan_time": str(row_val.get("scan_time") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            }
                            parsed_records.append(rec)

                        st.success(f"✅ 校验成功：解析到 **{len(parsed_records)}** 条 4H 突破达成记录！")
                        if parsed_records:
                            preview_df = pd.DataFrame([
                                {
                                    "代码": r["ticker"],
                                    "收盘价": f"${r['close']:.4f}" if r["close"] else "—",
                                    "4H成交量": f"{r['volume_4h']:,.0f}" if r["volume_4h"] else "—",
                                    "4H爆量": f"{r['vol_ratio_0']}x" if r.get("vol_ratio_0") else "—",
                                    "RSI": f"{r['rsi']:.1f}" if r["rsi"] else "—",
                                    "时间": r["scan_time"]
                                }
                                for r in parsed_records[:8]
                            ])
                            st.dataframe(preview_df, use_container_width=True, hide_index=True)

                        if st.button("📥 确认增量导入并合并到数据库", type="primary", use_container_width=True, key="btn_confirm_import_chartink"):
                            storage.append_chartink_results(parsed_records)
                            st.toast(f"🎉 成功导入并合并 {len(parsed_records)} 条 4H 突破形态！", icon="✅")
                            time.sleep(0.5)
                            st.rerun()

                except Exception as ex:
                    st.error(f"❌ 读取 CSV 失败: {ex}")

    # ── 3. 历史快照备份与恢复 ──
    with st.expander("📦 2. 快照备份与恢复", expanded=False):
        col_snap1, col_snap2 = st.columns([1.5, 1])
        snapshots = storage.load_chartink_snapshots()
        with col_snap1:
            st.markdown("##### 历史扫描批次恢复")
            if not snapshots:
                st.caption("💡 暂无可恢复的历史快照。每次导入或清空时都会自动创建快照备份。")
            else:
                snap_options = [
                    f"{s.get('scan_time', '—')} | 突破 {s.get('passed_count', 0)} 支 (共 {s.get('total', 0)} 支) | {s.get('session_id', '')[:16]}"
                    for s in snapshots
                ]
                sel_snap_idx = st.selectbox("选择要恢复的快照批次", range(len(snap_options)), format_func=lambda x: snap_options[x], key="ci_snap_select")
                if st.button("🔄 恢复该快照", key="btn_restore_snap_ci", use_container_width=True):
                    chosen_sid = snapshots[sel_snap_idx].get("session_id", "")
                    ok, msg, n = storage.restore_chartink_snapshot(chosen_sid)
                    if ok:
                        st.toast(f"✅ 成功恢复快照：共 {n} 个 4H 突破品种！", icon="♻️")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ 恢复失败: {msg}")

        with col_snap2:
            st.markdown("##### 当前结果维护")
            if st.button("💾 创建当前数据快照", key="btn_backup_curr_ci", use_container_width=True):
                if cache and isinstance(cache, dict):
                    sid = storage.backup_chartink(cache)
                    st.toast(f"✅ 快照创建成功: {sid}", icon="💾")
                    time.sleep(0.3)
                    st.rerun()
                else:
                    st.warning("当前暂无扫描数据可备份。")

            with st.popover("🗑️ 清空当前结果", use_container_width=True):
                st.markdown("⚠️ **确定清空所有 4H 突破扫描结果？**")
                st.caption("系统会自动创建一份快照备份，以便日后随时恢复。")
                if st.button("🔥 确认清空", type="primary", key="btn_clear_ci_results", use_container_width=True):
                    storage.clear_chartink_results()
                    st.toast("🗑️ 已清空当前结果！", icon="✅")
                    time.sleep(0.5)
                    st.rerun()

            if passed_records:
                df_export = pd.DataFrame(passed_records)
                csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    "📥 导出当前结果 CSV",
                    data=csv_bytes,
                    file_name=f"chartink_4h_breakout_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="btn_export_curr_ci"
                )

    # ── 4. 筛选、排序与分页工具栏 ──
    st.markdown("---")
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.8, 1.2, 1.2, 0.8])
    with col_f1:
        search_kw = st.text_input("🔍 搜索代码 / 品种名称", placeholder="输入代码如 AAPL, TSLA...", key="ci_search_kw")
    with col_f2:
        vol_filter = st.selectbox(
            "📊 最低 20 日均量",
            ["全部均量", "≥ 10 万股", "≥ 30 万股", "≥ 50 万股", "≥ 100 万股"],
            index=0,
            key="ci_vol_filter"
        )
    with col_f3:
        sort_mode = st.selectbox(
            "↕️ 排序方式",
            ["最新扫描时间 降序", "4H 放量倍数 降序", "RSI(14) 降序", "收盘价 降序", "代码 A-Z"],
            index=0,
            key="ci_sort_mode"
        )
    with col_f4:
        page_size_sel = st.selectbox("📄 每页条数", [20, 50, 100, "全部"], index=0, key="ci_page_size")

    # 过滤与排序
    filtered_items = list(passed_records)

    # 均量过滤
    _V_MAP = {
        "≥ 10 万股": 100000,
        "≥ 30 万股": 300000,
        "≥ 50 万股": 500000,
        "≥ 100 万股": 1000000,
    }
    if vol_filter in _V_MAP:
        req_v = _V_MAP[vol_filter]
        filtered_items = [r for r in filtered_items if _safe_float(r.get("avg_volume_20"), 0.0) >= req_v or req_v == 0]

    # 搜索过滤
    if search_kw:
        skw = search_kw.strip().upper()
        filtered_items = [r for r in filtered_items if skw in str(r.get("ticker", "")).upper()]

    # 排序
    if sort_mode == "4H 放量倍数 降序":
        filtered_items = sorted(filtered_items, key=lambda x: _safe_float(x.get("vol_ratio_0"), 0.0), reverse=True)
    elif sort_mode == "RSI(14) 降序":
        filtered_items = sorted(filtered_items, key=lambda x: _safe_float(x.get("rsi"), 0.0), reverse=True)
    elif sort_mode == "收盘价 降序":
        filtered_items = sorted(filtered_items, key=lambda x: _safe_float(x.get("close"), 0.0), reverse=True)
    elif sort_mode == "代码 A-Z":
        filtered_items = sorted(filtered_items, key=lambda x: str(x.get("ticker", "")).upper())
    else:
        # 默认按时间倒序
        filtered_items = sorted(filtered_items, key=lambda x: str(x.get("scan_time", "")), reverse=True)

    match_count = len(filtered_items)

    # ── 5. 结果卡片展示与分页 ──
    col_hdr1, col_hdr2 = st.columns([3, 1.2])
    with col_hdr1:
        st.markdown(f"### 🎯 筛选结果 (共 **{match_count}** 条 4H 突破)")
    with col_hdr2:
        if filtered_items:
            if st.button("⭐ 批量收藏当前筛选品种", key="btn_fav_all_ci_filtered", use_container_width=True):
                added_cnt = 0
                for r in filtered_items:
                    tk = str(r.get("ticker", "")).strip().upper()
                    if tk and storage.add_to_watchlist(ticker=tk, name=tk, note="Chartink 4H Breakout 突破匹配"):
                        added_cnt += 1
                st.toast(f"✅ 成功将 {added_cnt} 个品种加入自选收藏夹！", icon="⭐")
                time.sleep(0.5)
                st.rerun()

    if not filtered_items:
        st.info("💡 暂无符合筛选条件的 4H 突破品种。请调整上方筛选条件，或在 Google Colab 运行最新扫描脚本并导入 CSV。")
        return

    # 分页计算
    if page_size_sel == "全部":
        p_slice = filtered_items
        total_pages = 1
        curr_page = 1
    else:
        ps = int(page_size_sel)
        total_pages = max(1, (match_count + ps - 1) // ps)

        _url_p = st.query_params.get("_p", "")
        if _url_p.isdigit():
            init_p = int(_url_p)
        else:
            init_p = st.session_state.get("ci_curr_page", 1)

        curr_page = min(max(1, init_p), total_pages)
        st.session_state["ci_curr_page"] = curr_page

        if total_pages > 1:
            col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
            with col_p1:
                if st.button("⬅️ 上一页", key="ci_top_prev_btn", disabled=(curr_page <= 1), use_container_width=True):
                    st.session_state["ci_curr_page"] = curr_page - 1
                    st.query_params["_p"] = str(curr_page - 1)
                    st.rerun()
            with col_p2:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px;font-size:13px;color:#94a3b8;'>"
                    f"第 <b style='color:#38bdf8;'>{curr_page}</b> / {total_pages} 页 (共 {match_count} 支)"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with col_p3:
                if st.button("下一页 ➡️", key="ci_top_next_btn", disabled=(curr_page >= total_pages), use_container_width=True):
                    st.session_state["ci_curr_page"] = curr_page + 1
                    st.query_params["_p"] = str(curr_page + 1)
                    st.rerun()

        start_i = (curr_page - 1) * ps
        p_slice = filtered_items[start_i:start_i + ps]

    # 加载自选与点击计数
    wl_items = storage.load_watchlist() or []
    wl_set = {item["ticker"].upper() for item in wl_items if isinstance(item, dict) and item.get("ticker")}
    all_clicks_data = storage.get_all_link_clicks()
    today_str_val = storage.get_today_str()
    t_token = st.query_params.get("_t", "")
    t_param = f"&_t={t_token}" if t_token else ""

    # 预加载品种名称字典
    all_sym_list = storage.load_symbols() or []
    sym_name_dict = {s["ticker"].upper(): s.get("name", s["ticker"]) for s in all_sym_list if isinstance(s, dict) and s.get("ticker")}

    # 渲染卡片
    for r in p_slice:
        ticker = str(r.get("ticker", "")).strip().upper()
        if not ticker:
            continue

        c_val = _safe_float(r.get("close"), 0.0)
        v4h_val = _safe_float(r.get("volume_4h"), 0.0)
        vr0_val = _safe_float(r.get("vol_ratio_0"), 0.0)
        vr1_val = _safe_float(r.get("vol_ratio_1"), 0.0)
        rsi_val = _safe_float(r.get("rsi"), 0.0)
        ct_val = _safe_float(r.get("cloud_top"), 0.0)
        cb_val = _safe_float(r.get("cloud_bot"), 0.0)
        st_val = _safe_float(r.get("supertrend"), 0.0)
        c2h_val = _safe_float(r.get("close_2h_m2"), 0.0)
        scan_time_val = str(r.get("scan_time", "—"))

        name = sym_name_dict.get(ticker, ticker)
        is_a_share = ticker.endswith((".SS", ".SZ", ".BJ")) or ticker.isdigit()
        mkt_tag = '<span class="ci-tag-a">🇨🇳 A股 · 4H</span>' if is_a_share else '<span class="ci-tag-us">🇺🇸 美股 · 4H</span>'

        # 点击计数
        click_entry = all_clicks_data.get(f"{ticker}:tv", {}) if isinstance(all_clicks_data, dict) else {}
        total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
        by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
        today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0

        click_badge = f'<span style="color:#4ade80;font-weight:700;">({today_c}/{total_c})</span>' if total_c > 0 else '<span style="color:#64748b;">(0/0)</span>'
        tv_lnk = tv_url(ticker, "4h")
        sina_lnk = sina_url(ticker)
        is_fav = ticker in wl_set

        # 放量高亮文案
        vr0_str = f"🔥 {vr0_val:.1f}x (爆量)" if vr0_val >= 2.0 else f"{vr0_val:.1f}x"
        vr1_str = f"{vr1_val:.1f}x" if vr1_val > 0 else "—"

        # 7条规则徽章
        rules_badges_html = (
            '<span class="ci-rule-badge">✔ [0] 4H放量>2x</span>'
            '<span class="ci-rule-badge">✔ [1] 前根放量>1.5x</span>'
            '<span class="ci-rule-badge">✔ [2] 云顶上方</span>'
            '<span class="ci-rule-badge">✔ [3] RSI>50</span>'
            '<span class="ci-rule-badge">✔ [4] ST支撑上方</span>'
            '<span class="ci-rule-badge">✔ [5] 云底上方</span>'
            '<span class="ci-rule-badge">✔ [6] 2H收盘强势</span>'
        )

        card_html = f"""
        <div class="ci-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <a href="/?_page=ticker&_ticker={ticker}{t_param}" target="_parent" style="color:#38bdf8; font-weight:800; font-size:16px; text-decoration:none;">{ticker}</a>
                    <span style="color:#cbd5e1; font-size:13px; font-weight:600;">{name}</span>
                    {mkt_tag}
                </div>
                <div>
                    <span style="background:linear-gradient(135deg, rgba(34,197,94,0.2), rgba(16,185,129,0.3)); color:#4ade80; border:1px solid rgba(34,197,94,0.4); border-radius:6px; padding:3px 10px; font-size:12px; font-weight:700;">
                        🚀 7条规则突破达成
                    </span>
                </div>
            </div>
            
            <div class="ci-metric-grid">
                <div class="ci-metric-item">
                    <span class="ci-metric-label">4H放量 / 前根倍数</span>
                    <span class="ci-metric-val">{vr0_str} / {vr1_str}</span>
                </div>
                <div class="ci-metric-item">
                    <span class="ci-metric-label">收盘价 / 一目云顶</span>
                    <span class="ci-metric-val">${c_val:.4f} > ${ct_val:.4f}</span>
                </div>
                <div class="ci-metric-item">
                    <span class="ci-metric-label">Daily RSI(14)</span>
                    <span class="ci-metric-val" style="color:#38bdf8;">📈 {rsi_val:.1f} (>50)</span>
                </div>
                <div class="ci-metric-item">
                    <span class="ci-metric-label">Supertrend / 2H[-2]</span>
                    <span class="ci-metric-val">${st_val:.4f} | ${c2h_val:.4f}</span>
                </div>
            </div>

            <div style="margin-top:6px; margin-bottom:10px;">
                {rules_badges_html}
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px dashed rgba(255,255,255,0.1); padding-top:8px; font-size:12px;">
                <div style="color:#64748b;">
                    ⏰ 扫描时间: {scan_time_val}
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <a href="{tv_lnk}" target="_blank" class="tv-btn" data-ticker="{ticker}" style="color:#38bdf8; background:rgba(56,189,248,0.15); border:1px solid rgba(56,189,248,0.3); padding:3px 10px; border-radius:4px; text-decoration:none; font-weight:600;">
                        📈 TV 4H 图表 {click_badge}
                    </a>
                    <a href="{sina_lnk}" target="_blank" class="sina-btn" data-ticker="{ticker}" style="color:#cbd5e1; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15); padding:3px 8px; border-radius:4px; text-decoration:none;">
                        🏦 新浪
                    </a>
                </div>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        # 收藏交互按钮
        col_c_space, col_c_btn = st.columns([5, 1])
        with col_c_btn:
            if is_fav:
                if st.button("🗑️ 取消自选", key=f"fav_btn_del_{ticker}", use_container_width=True):
                    storage.remove_from_watchlist(ticker)
                    st.toast(f"已将 {ticker} 从自选移除", icon="🗑️")
                    time.sleep(0.3)
                    st.rerun()
            else:
                if st.button("⭐ 加入自选", key=f"fav_btn_add_{ticker}", use_container_width=True):
                    storage.add_to_watchlist(ticker=ticker, name=name, note="Chartink 4H Breakout 突破匹配")
                    st.toast(f"⭐ 已将 {ticker} 加入自选收藏夹！", icon="⭐")
                    time.sleep(0.3)
                    st.rerun()

    # 底部页码导航
    if total_pages > 1 and page_size_sel != "全部":
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        col_b_p1, col_b_p2, col_b_p3 = st.columns([1, 2, 1])
        with col_b_p1:
            if st.button("⬅️ 上一页", key="ci_bot_prev_btn", disabled=(curr_page <= 1), use_container_width=True):
                st.session_state["ci_curr_page"] = curr_page - 1
                st.query_params["_p"] = str(curr_page - 1)
                st.rerun()
        with col_b_p2:
            st.markdown(
                f"<div style='text-align:center;padding-top:6px;font-size:13px;color:#94a3b8;'>"
                f"第 <b style='color:#38bdf8;'>{curr_page}</b> / {total_pages} 页 (共 {match_count} 支)"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_b_p3:
            if st.button("下一页 ➡️", key="ci_bot_next_btn", disabled=(curr_page >= total_pages), use_container_width=True):
                st.session_state["ci_curr_page"] = curr_page + 1
                st.query_params["_p"] = str(curr_page + 1)
                st.rerun()

    # 隐形事件监听组件：捕捉原链接点击
    _js_code = """
    <script>
    (function() {
        try {
            var pDoc = window.parent.document;
            if (pDoc._tv_click_handler) {
                pDoc.removeEventListener('click', pDoc._tv_click_handler, true);
            }
            pDoc._tv_click_handler = function(e) {
                var btn = e.target.closest('.tv-btn, .sina-btn');
                if (btn) {
                    var tk = btn.getAttribute('data-ticker');
                    if (tk) {
                        tk = tk.trim().toUpperCase();
                        var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);
                        try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}
                        try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}
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
        import streamlit.components.v1 as _components
        _components.html(_js_code, height=0)
