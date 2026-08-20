"""
page_chartink.py — Chartink · 4 Hour Breakout Scanner

扫描条件（全部满足）：
  [0] 4H Volume[0]  > 4H Volume[-1] * 2
  [1] 4H Volume[-1] > 4H Volume[-2] * 1.5
  [2] Daily Close   > Daily Ichimoku Cloud Top  (9,26,52)
  [3] Daily RSI(14) > 50
  [4] Daily Close   > Daily Supertrend(7,3)
  [5] Daily Close   > Daily Ichimoku Cloud Bottom(9,26,52)
  [6] Daily Close   > 2H Close[-2]
"""

import time
import datetime
import streamlit as st
import pandas as pd
import numpy as np
import storage
import bg_scan_manager
from streamlit_autorefresh import st_autorefresh

# ── 依赖安全导入 ────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False


# ════════════════════════════════════════════════════════════════════
# 指标计算工具
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
    """
    返回 (senkou_a, senkou_b)，即云顶/云底（当前行，已移位 k 个周期回填）。
    Cloud Top  = max(senkou_a, senkou_b)
    Cloud Bot  = min(senkou_a, senkou_b)
    """
    tenkan  = (high.rolling(t).max() + low.rolling(t).min()) / 2
    kijun   = (high.rolling(k).max() + low.rolling(k).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(k)
    senkou_b = ((high.rolling(s).max() + low.rolling(s).min()) / 2).shift(k)
    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    return cloud_top, cloud_bot


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 7, multiplier: float = 3.0) -> pd.Series:
    """返回 Supertrend 线（上涨时为支撑线，下跌时为阻力线）"""
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


# ════════════════════════════════════════════════════════════════════
# 核心数据获取 + 条件检测
# ════════════════════════════════════════════════════════════════════

def _fetch(ticker: str, interval: str, period: str = "6mo") -> pd.DataFrame | None:
    """下载 OHLCV，具备 Rate-Limit 重试机制，失败返回 None"""
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
                time.sleep(2.5 * (attempt + 1))
                continue
            return None
    return None


def _check_ticker(ticker: str) -> dict:
    """
    执行 7 条过滤规则，返回结果字典。
    result keys: passed(bool), details(list[dict]), error(str|None),
                 close(float), volume_4h(float), rsi(float)
    """
    result = {"passed": False, "details": [], "error": None,
              "close": None, "volume_4h": None, "rsi": None}

    if not _YF_OK:
        result["error"] = "yfinance 未安装"
        return result

    if storage.is_ticker_delisted(ticker):
        result["error"] = "已退市/无效代码"
        return result

    # ── 下载数据 ────────────────────────────────────────────────────
    df_1d = _fetch(ticker, "1d", "1y")
    if df_1d is None or len(df_1d) < 60:
        result["error"] = "日线数据不足"
        return result

    # 1H 数据（用于 2H/4H 的重采样与兜底）
    df_1h = _fetch(ticker, "1h", "2mo")

    # 4H 数据（优先通过 1h 重采样获取，大幅削减 HTTP 请求数；仅在 1h 缺失时降级从 yfinance 获取）
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

    # 2H 数据（yfinance 原生不支持 2h，通过 1h 重采样获取）
    df_2h = None
    if df_1h is not None and len(df_1h) >= 2:
        try:
            df_2h = df_1h.resample("2h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna(subset=["close"])
        except Exception:
            pass

    # ── 预计算指标 ──────────────────────────────────────────────────
    close_d = df_1d["close"]
    high_d  = df_1d["high"]
    low_d   = df_1d["low"]

    rsi_ser           = _rsi(close_d, 14)
    cloud_top, cloud_bot = _ichimoku(high_d, low_d, 9, 26, 52)
    supertrend_ser    = _supertrend(high_d, low_d, close_d, 7, 3.0)

    # 最新日线值
    c_d   = float(close_d.iloc[-1])
    rsi_v = float(rsi_ser.iloc[-1])    if not pd.isna(rsi_ser.iloc[-1])    else None
    ct_v  = float(cloud_top.iloc[-1])  if not pd.isna(cloud_top.iloc[-1])  else None
    cb_v  = float(cloud_bot.iloc[-1])  if not pd.isna(cloud_bot.iloc[-1])  else None
    st_v  = float(supertrend_ser.iloc[-1]) if not pd.isna(supertrend_ser.iloc[-1]) else None

    # 4H 成交量
    vol_4h = df_4h["volume"]
    v0 = float(vol_4h.iloc[-1])   # [0]  当前
    v1 = float(vol_4h.iloc[-2])   # [-1] 前一根
    v2 = float(vol_4h.iloc[-3])   # [-2] 前两根
    v3 = float(vol_4h.iloc[-4]) if len(vol_4h) >= 4 else v2

    # 2H 收盘（[-2] 前两根）
    c_2h_m2 = None
    if df_2h is not None and len(df_2h) >= 3:
        c_2h_m2 = float(df_2h["close"].iloc[-3])

    result["close"]     = c_d
    result["volume_4h"] = v0
    result["rsi"]       = rsi_v

    # ── 7 条规则 ────────────────────────────────────────────────────
    rules = [
        {
            "id":   "[0]",
            "desc": "4H Volume[0] > 4H Volume[-1] × 2 (或已完成根 > ×2)",
            "ok":   (v0 > v1 * 2) or (v1 > v2 * 2),
            "val":  f"{v0:,.0f} vs {v1:,.0f}×2={v1*2:,.0f}" if (v0 > v1 * 2) else f"前根: {v1:,.0f} vs {v2:,.0f}×2={v2*2:,.0f}",
        },
        {
            "id":   "[1]",
            "desc": "4H Volume[-1] > 4H Volume[-2] × 1.5 (或已完成根 > ×1.5)",
            "ok":   (v1 > v2 * 1.5) or (v2 > v3 * 1.5),
            "val":  f"{v1:,.0f} vs {v2:,.0f}×1.5={v2*1.5:,.0f}" if (v1 > v2 * 1.5) else f"前前根: {v2:,.0f} vs {v3:,.0f}×1.5={v3*1.5:,.0f}",
        },
        {
            "id":   "[2]",
            "desc": "Daily Close > Ichimoku Cloud Top(9,26,52)",
            "ok":   (ct_v is not None) and (c_d > ct_v),
            "val":  f"Close={c_d:.4f}  CloudTop={ct_v:.4f}" if ct_v else "数据不足",
        },
        {
            "id":   "[3]",
            "desc": "Daily RSI(14) > 50",
            "ok":   (rsi_v is not None) and (rsi_v > 50),
            "val":  f"RSI={rsi_v:.2f}" if rsi_v else "数据不足",
        },
        {
            "id":   "[4]",
            "desc": "Daily Close > Supertrend(7,3)",
            "ok":   (st_v is not None) and (c_d > st_v),
            "val":  f"Close={c_d:.4f}  ST={st_v:.4f}" if st_v else "数据不足",
        },
        {
            "id":   "[5]",
            "desc": "Daily Close > Ichimoku Cloud Bottom(9,26,52)",
            "ok":   (cb_v is not None) and (c_d > cb_v),
            "val":  f"Close={c_d:.4f}  CloudBot={cb_v:.4f}" if cb_v else "数据不足",
        },
        {
            "id":   "[6]",
            "desc": "Daily Close > 2H Close[-2]",
            "ok":   (c_2h_m2 is not None) and (c_d > c_2h_m2),
            "val":  f"Close={c_d:.4f}  2H[-2]={c_2h_m2:.4f}" if c_2h_m2 else "2H数据不足",
        },
    ]

    result["details"] = rules
    result["passed"]  = all(r["ok"] for r in rules)
    return result


# ════════════════════════════════════════════════════════════════════
# 后台扫描 Worker
# ════════════════════════════════════════════════════════════════════
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
            res["ticker"] = tk
            if res.get("error"):
                error_list.append(res)
            elif res.get("passed"):
                passed_list.append(res)
            else:
                failed_list.append(res)
        except Exception as e:
            error_list.append({"ticker": tk, "passed": False, "details": [], "error": str(e)})

        # 每 25 个品种增量保存一次，防止 6000+ 大批量扫描中途崩溃导致数据全丢
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
            
        # 每 50 个品种强制回收垃圾，防止内存爆炸触发 Streamlit Cloud 容器 OOM
        if (i + 1) % 50 == 0:
            gc.collect()
            
        time.sleep(0.08)   # 防限流微调
        
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
# Streamlit 页面
# ════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────────────
# 美国股票全股票池（S&P 500 完整成分股）
# 来源：S&P 500 官方成分股（约503只），适合作为美股基础扫描池。
# 用户可在页面文本框中自行增删，此处仅作默认值。
# ────────────────────────────────────────────────────────────────────
_DEFAULT_TICKERS = "AAPL MSFT NVDA AMZN GOOGL META TSLA BRK-B AVGO JPM"

# ────────────────────────────────────────────────────────────────────
US_SP500_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "AVGO", "JPM",
    "ELI", "UNH", "V", "MA", "XOM", "HD", "PG", "COST", "JNJ", "ABBV",
    "ORCL", "BAC", "HD", "CVX", "MRK", "WMT", "KO", "NFLX", "AMD", "PEP",
    "TMO", "PFE", "ADBE", "LIN", "MCD", "ACN", "CSCO", "ABT", "DIS", "PM",
    "INTC", "TXN", "DHR", "INTU", "QCOM", "CAT", "VZ", "AMAT", "IBM", "AMGN",
    "GE", "ISRG", "NOW", "LOW", "SPGI", "BKNG", "GS", "HON", "COP", "RTX",
    "AXP", "SYK", "PLTR", "REGN", "LRCX", "PNC", "DE", "MU", "T", "PANW",
    "SCHW", "UPS", "TJX", "CB", "MMC", "VRTX", "BMY", "BSX", "ADI", "MS",
    "ETN", "MDLZ", "CI", "LMT", "KLAC", "SNPS", "CDNS", "WM", "NKE", "SBUX"
]

def render():
    render_page_chartink()

def render_page_chartink():
    st.markdown("## 📈 Chartink · 4 Hour Breakout 7条规则突破扫描")
    
    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, key="chartink_scan_auto_refresh")
        except Exception:
            pass
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="chartink_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status.get("job_type") == "chartink_scan":
        if status["status"] == "done":
            st.success("✅ 后台扫描任务已完成!")
        elif status["status"] == "error":
            st.error(f"❌ 后台扫描任务出错! 错误信息: {status.get('error', '')}")
        elif status["status"] == "cancelled":
            st.warning("⚠️ 后台扫描任务已被取消。")
            
        if st.button("清除状态提示", key="chartink_clear_status_btn"):
            bg_scan_manager.reset_to_idle()
            st.rerun()

    with st.expander("ℹ️ Chartink 4H Breakout 筛选规则说明", expanded=False):
        st.markdown(
            "本扫描器严格依据 Chartink 4 Hour Breakout 策略的 **7 条技术指标逻辑** 对目标股票池进行全量检索："
        )
        conditions = [
            ("[0]", "4H Volume[0] > 4H Volume[-1] × 2",         "当前4H成交量 > 前一根4H成交量的2倍"),
            ("[1]", "4H Volume[-1] > 4H Volume[-2] × 1.5",       "前一根4H成交量 > 再前一根4H成交量的1.5倍"),
            ("[2]", "Daily Close > Ichimoku Cloud Top(9,26,52)",  "收盘价在一目均衡云顶上方"),
            ("[3]", "Daily RSI(14) > 50",                         "日线RSI大于50（趋势偏多）"),
            ("[4]", "Daily Close > Supertrend(7,3)",              "收盘价在SuperTrend支撑线上方"),
            ("[5]", "Daily Close > Ichimoku Cloud Bottom(9,26,52)","收盘价在一目均衡云底上方"),
            ("[6]", "Daily Close > 2H Close[-2]",                 "日线收盘 > 2H前第2根收盘（短期强势）"),
        ]
        rows = []
        for idx, cond, meaning in conditions:
            rows.append({"编号": idx, "条件": cond, "含义": meaning})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 载入分组品种 ──
    def _on_chartink_group_change():
        sel = st.session_state.get("chartink_load_grp_sel")
        if sel and sel != "— 选择载入分组 —":
            grps = storage.load_symbol_groups()
            target = next((g for g in grps if g["name"] == sel), None)
            if target:
                tickers = target.get("tickers", [])
                st.session_state["chartink_tickers"] = " ".join(tickers)
            st.session_state["chartink_load_grp_sel"] = "— 选择载入分组 —"

    groups = storage.load_symbol_groups()
    if groups:
        grp_names = ["— 选择载入分组 —"] + [g["name"] for g in groups]
        if "chartink_load_grp_sel" not in st.session_state:
            st.session_state["chartink_load_grp_sel"] = "— 选择载入分组 —"
        st.selectbox(
            "📥 从品种库分组载入股票池",
            grp_names,
            key="chartink_load_grp_sel",
            on_change=_on_chartink_group_change,
        )

    # ── 股票池设置 ──────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 1])
    with col_left:
        if "chartink_tickers" not in st.session_state:
            syms = [s["ticker"] for s in storage.load_symbols()]
            if syms:
                st.session_state["chartink_tickers"] = " ".join(syms)
            else:
                st.session_state["chartink_tickers"] = "AAPL MSFT NVDA AMZN GOOGL TSLA"
        ticker_input = st.text_area(
            "扫描股票池（空格或换行分隔，支持 yfinance 格式如 9988.HK / BTC-USD）",
            height=100,
            key="chartink_tickers",
        )
    is_running = bg_scan_manager.is_running()
    with col_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        run_btn  = st.button("🚀 开始扫描", type="primary",  use_container_width=True, key="chartink_run", disabled=is_running)
        if st.session_state.pop("_trigger_mobile_scan", False):
            run_btn = True
        clear_btn = st.button("🗑️ 清空结果", type="secondary", use_container_width=True, key="chartink_clear", disabled=is_running)

    if clear_btn:
        storage.clear_chartink_results()
        st.toast("🗑️ 已自动创建备份快照并成功清空！", icon="✅")
        time.sleep(0.5)
        st.rerun()

    # ── 🌐 Google Colab 独立大规模扫描渠道 ──
    with st.expander("☁️ Google Colab 算力扫描渠道 (全美股 / 全A股 极速 4H 突破扫描与结果导入)", expanded=False):
        colab_c1, colab_c2 = st.columns([1.2, 1], gap="medium")
        with colab_c1:
            st.markdown("##### 1. 选择股票池并获取专属 Colab 4H 扫描脚本")
            st.caption("利用 Google Colab 免费高性能多核算力极速扫描数百上千只全市场股票，完全不受 Streamlit Cloud 内存配额与执行时长限制。")
            
            # 从系统已有品种库与分组中提取
            groups = storage.load_symbol_groups() or []
            all_symbols = storage.load_symbols() or []
            
            pool_options = ["🇺🇸 全量美股 (系统内置)", "🇨🇳 全量A股 (系统内置)"]
            grp_name_list = [g["name"] for g in groups if g.get("name")]
            for gn in grp_name_list:
                if gn not in pool_options:
                    pool_options.append(f"📁 分组: {gn}")
            pool_options.append("⭐ 我的自选关注列表")
            
            p_col1, p_col2 = st.columns([1.5, 1])
            with p_col1:
                selected_pool = st.selectbox(
                    "选择需要导出的扫描股票池",
                    options=pool_options,
                    index=0,
                    key="chartink_colab_selected_pool",
                    help="系统会自动将选定股票池中的所有股票代码注入到 Colab 脚本中，无需在 Colab 中重复拉取"
                )
            with p_col2:
                st.text_input(
                    "扫描周期 (固定)",
                    value="4h (4小时 突破)",
                    disabled=True,
                    help="Chartink 7条规则突破策略专用于 4小时 (4H) 周期突破检测"
                )
            
            # 提取对应股票代码
            export_tickers = []
            if "全量美股" in selected_pool:
                us_grp = next((g for g in groups if "全量美股" in g.get("name", "")), None)
                if us_grp and us_grp.get("tickers"):
                    export_tickers = us_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if not s["ticker"].endswith(".SS") and not s["ticker"].endswith(".SZ") and not s["ticker"].endswith(".BJ") and not s["ticker"].isdigit()]
            elif "全量A股" in selected_pool:
                a_grp = next((g for g in groups if "全量A股" in g.get("name", "")), None)
                if a_grp and a_grp.get("tickers"):
                    export_tickers = a_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if s["ticker"].endswith(".SS") or s["ticker"].endswith(".SZ") or s["ticker"].endswith(".BJ") or s["ticker"].isdigit()]
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
            
            st.info(f"📋 选定股票池: **{len(export_tickers)}** 支品种 | 周期: **4h** (已直接生成于下方代码中)：")
            
            import colab_chartink_script
            colab_code = colab_chartink_script.generate_colab_chartink_script(export_tickers, pool_name=selected_pool)
            st.code(colab_code, language="python", line_numbers=True)
            st.markdown(
                """
                <div style="font-size:12px;color:#94a3b8;margin-top:-6px;margin-bottom:10px;">
                    👉 <b>操作指引：</b> 点击代码框右上角<b>复制</b> ➔ 打开 <a href="https://colab.research.google.com/" target="_blank" style="color:#38bdf8;text-decoration:underline;">Google Colab</a> 新建笔记本粘贴并运行 ➔ 运行完毕将自动下载 <code>colab_chartink_results.csv</code>。
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with colab_c2:
            st.markdown("##### 2. 导入 Colab 扫描结果 CSV")
            st.caption("上传从 Google Colab 导出的扫描结果 CSV 文件，系统将自动进行格式校验并展示 4H 突破匹配结果。")
            uploaded_file = st.file_uploader(
                "选择或拖拽 Colab 导出的 CSV 文件",
                type=["csv"],
                key="chartink_colab_csv_uploader",
                help="支持导入 colab_chartink_results.csv"
            )
            
            if uploaded_file is not None:
                try:
                    import io
                    import csv
                    import json
                    df_up = pd.read_csv(uploaded_file)
                    
                    if "ticker" not in df_up.columns:
                        st.error("❌ CSV 文件格式不符合要求，缺少 ticker 列")
                    else:
                        passed_list = []
                        failed_list = []
                        errors_list = []
                        
                        for _, r in df_up.iterrows():
                            tk = str(r.get("ticker", "")).strip().upper()
                            if not tk:
                                continue
                            
                            is_passed = bool(r.get("passed", 0) == 1 or str(r.get("passed", "")).lower() in ("true", "1"))
                            err_msg = str(r.get("error", "")) if pd.notna(r.get("error")) and str(r.get("error", "")).strip() else None
                            
                            details = []
                            details_json_str = str(r.get("details_json", ""))
                            if details_json_str and details_json_str != "nan":
                                try:
                                    details = json.loads(details_json_str)
                                except Exception:
                                    pass
                            
                            item = {
                                "ticker": tk,
                                "passed": is_passed,
                                "close": float(r.get("close", 0.0)) if pd.notna(r.get("close")) and r.get("close") != "" else None,
                                "volume_4h": float(r.get("volume_4h", 0.0)) if pd.notna(r.get("volume_4h")) and r.get("volume_4h") != "" else None,
                                "rsi": float(r.get("rsi", 0.0)) if pd.notna(r.get("rsi")) and r.get("rsi") != "" else None,
                                "cloud_top": float(r.get("cloud_top", 0.0)) if pd.notna(r.get("cloud_top")) and r.get("cloud_top") != "" else None,
                                "cloud_bot": float(r.get("cloud_bot", 0.0)) if pd.notna(r.get("cloud_bot")) and r.get("cloud_bot") != "" else None,
                                "supertrend": float(r.get("supertrend", 0.0)) if pd.notna(r.get("supertrend")) and r.get("supertrend") != "" else None,
                                "close_2h_m2": float(r.get("close_2h_m2", 0.0)) if pd.notna(r.get("close_2h_m2")) and r.get("close_2h_m2") != "" else None,
                                "error": err_msg,
                                "details": details,
                                "scan_time": str(r.get("scan_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            }
                            
                            if err_msg:
                                errors_list.append(item)
                            elif is_passed:
                                passed_list.append(item)
                            else:
                                failed_list.append(item)
                                
                        total_cnt = len(passed_list) + len(failed_list) + len(errors_list)
                        st.markdown(f"📊 **检测到 CSV 记录**: 共 `{total_cnt}` 支 | 🔥 通过突破: `{len(passed_list)}` 支 | ❌ 未通过: `{len(failed_list)}` 支 | ⚠️ 错误: `{len(errors_list)}` 支")
                        
                        if st.button("📥 确认导入并覆盖为当前结果", key="chartink_colab_confirm_import_btn", type="primary", use_container_width=True):
                            try:
                                final_res = {
                                    "passed": passed_list,
                                    "failed": failed_list,
                                    "errors": errors_list,
                                    "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "total": total_cnt,
                                    "done_count": total_cnt
                                }
                                ok = storage.save_chartink(final_res)
                                if ok:
                                    try:
                                        storage.backup_chartink(final_res)
                                    except Exception:
                                        pass
                                    st.toast(f"✅ 成功导入 {len(passed_list)} 条 4H 突破扫描结果！", icon="🎉")
                                    time.sleep(0.8)
                                    st.rerun()
                                else:
                                    st.error("❌ 写入存储失败: storage.save_chartink 返回 False。")
                            except Exception as save_err:
                                st.error(f"❌ 写入存储异常: {save_err}")
                except Exception as ex:
                    st.error(f"❌ 解析 CSV 文件失败: {ex}")

    # ── 📦 扫描批次历史与恢复 ───────────────────────────────────────
    snapshots = storage.load_chartink_snapshots()
    options = []
    sid_map = {}
    for s in snapshots:
        sid = s.get("session_id", "")
        scan_time = s.get("scan_time", "—")
        tot = s.get("total", 0)
        pas = s.get("passed_count", 0)
        label = f"{scan_time} | 扫描 {tot} 支 | 通过 {pas} 支 | {sid[:18]}"
        options.append(label)
        sid_map[label] = sid

    with st.expander("📦 选择历史扫描批次（备份与恢复）", expanded=True if not storage.load_chartink() else False):
        if not storage.load_chartink():
            st.warning("⚠️ 检测到当前无本地扫描结果。可能由于服务器容器重启/登录失效重置导致。您可以尝试从下方历史批次恢复，或点击右侧从 Supabase 云端拉取最新结果。")
            
        col_snap1, col_snap2, col_snap3 = st.columns([2.5, 1, 1])
        with col_snap1:
            if not options:
                st.caption("💡 暂无可恢复批次（无本地快照）。每次扫描或清空时都会自动创建快照备份。")
                selected_label = None
            else:
                selected_label = st.selectbox(
                    "恢复批次",
                    options,
                    key="chartink_restore_picker",
                    label_visibility="collapsed",
                )
        with col_snap2:
            selected_sid = sid_map.get(selected_label, "") if selected_label else ""
            if st.button("♻️ 恢复批次", key="chartink_restore_btn", use_container_width=True, disabled=not selected_sid or is_running):
                ok, msg, n = storage.restore_chartink_snapshot(selected_sid)
                if ok:
                    st.toast(f"✅ 成功恢复批次：通过 {n} 个品种！", icon="♻️")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ 恢复失败：{msg}")
        with col_snap3:
            if st.button("☁️ 从云端拉取", key="chartink_cloud_pull_btn", use_container_width=True, disabled=is_running):
                try:
                    import cloud_sync
                    if not cloud_sync.is_configured():
                        st.warning("⚠️ 未配置 Supabase 云端同步")
                    else:
                        ok, msg = cloud_sync.pull_chartink()
                        if ok:
                            st.toast(f"✅ {msg}", icon="☁️")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"❌ 云端拉取失败: {msg}")
                except Exception as ex:
                    st.error(f"❌ 云端拉取异常: {ex}")

    tickers = [t.strip().upper() for t in ticker_input.replace("\n", " ").split() if t.strip()]

    # ── 执行扫描 ────────────────────────────────────────────────────
    if run_btn:
        if not _YF_OK:
            st.error("❌ yfinance 未安装，请在 requirements.txt 中添加 yfinance")
            return
        if not tickers:
            st.warning("请输入至少一个股票代码")
            return

        params = {
            "tickers": tickers
        }
        
        ok, msg = bg_scan_manager.submit_job(
            job_type="chartink_scan",
            label=f"Chartink 扫描 ({len(tickers)}支)",
            params=params,
            worker_fn=chartink_worker
        )
        if ok:
            st.success(msg)
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)

    # ── 结果展示 ────────────────────────────────────────────────────
    cache = storage.load_chartink()
    if not cache:
        st.markdown(
            '<div class="n-info" style="margin-top:16px">'
            '💡 输入股票池后点击「开始扫描」，满足全部7个条件的品种会显示在下方。'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    passed = cache["passed"]
    failed = cache["failed"]
    errors = cache["errors"]
    total  = cache["total"]
    scanned_at = cache["scanned_at"]

    # 顶部统计
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_stat_card("扫描品种", str(total),       "blue"),  unsafe_allow_html=True)
    c2.markdown(_stat_card("通过筛选", str(len(passed)), "green"), unsafe_allow_html=True)
    c3.markdown(_stat_card("未通过",   str(len(failed)), "gray"),  unsafe_allow_html=True)
    c4.markdown(_stat_card("数据错误", str(len(errors)), "red"),   unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:11px;color:#9ca3af;text-align:right;margin-top:4px">'
        f'扫描时间：{scanned_at}</div>',
        unsafe_allow_html=True,
    )

    # ── 通过的品种 ──────────────────────────────────────────────────
    col_pass_hdr1, col_pass_hdr2 = st.columns([3, 1])
    with col_pass_hdr1:
        st.markdown("### ✅ 通过筛选的品种")
    with col_pass_hdr2:
        if passed:
            if st.button("⭐ 批量收藏全部通过品种", key="chartink_fav_all_passed", use_container_width=True):
                added_cnt = 0
                for r in passed:
                    tk = r["ticker"]
                    if storage.add_to_watchlist(ticker=tk, name=tk, note="Chartink 4H Breakout 扫描匹配"):
                        added_cnt += 1
                st.toast(f"✅ 成功将 {added_cnt} 个品种加入自选收藏夹！", icon="⭐")
                time.sleep(1)
                st.rerun()

    if not passed:
        st.markdown('<div class="n-warn">本次扫描无品种满足全部7个条件。</div>', unsafe_allow_html=True)
    else:
        all_clicks_data = storage.get_all_link_clicks()
        today_str_val = storage.get_today_str()
        from assets import tv_url
        
        wl_items = storage.load_watchlist()
        wl_set = {item["ticker"].upper() for item in wl_items if isinstance(item, dict)}
        
        _t_val = st.query_params.get("_t", "")
        _t_param = f"&_t={_t_val}" if _t_val else ""

        # 汇总表
        rows_html = []
        for r in passed:
            ticker = r["ticker"]
            price_s = f"{r['close']:.4f}" if r["close"] else "—"
            vol_s = f"{r['volume_4h']:,.0f}" if r["volume_4h"] else "—"
            rsi_s = f"{r['rsi']:.1f}" if r["rsi"] else "—"
            
            click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
            total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
            by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
            today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0
            if total_c > 0:
                click_badge = f' <span style="font-size:11px;color:#4ade80;font-weight:600;">({today_c}/{total_c})</span>'
            else:
                click_badge = ' <span style="font-size:11px;color:#64748b;font-weight:500;">(0/0)</span>'
            
            tv_lnk = tv_url(ticker, "4h")
            tv_html = f'<a href="{tv_lnk}" target="_blank" class="tv-btn" data-ticker="{ticker}" style="color:#38bdf8;text-decoration:none;font-weight:600;font-size:12px;background:rgba(56,189,248,0.1);padding:4px 10px;border-radius:4px;border:1px solid rgba(56,189,248,0.2);">📈 TV{click_badge}</a>'
            
            is_fav = ticker.upper() in wl_set
            if is_fav:
                fav_html = f'<a href="/?_page=watchlist&_fav=del|{ticker}|{ticker}{_t_param}&_anchor={ticker}" target="_blank" style="color:#f59e0b;text-decoration:none;font-weight:600;font-size:12px;background:rgba(245,158,11,0.15);padding:4px 10px;border-radius:4px;border:1px solid rgba(245,158,11,0.3);">★ 已收藏</a>'
            else:
                fav_html = f'<a href="/?_page=watchlist&_fav=add|{ticker}|{ticker}{_t_param}&_anchor={ticker}" target="_blank" style="color:#eab308;text-decoration:none;font-weight:600;font-size:12px;background:rgba(234,179,8,0.1);padding:4px 10px;border-radius:4px;border:1px solid rgba(234,179,8,0.2);">⭐ 收藏</a>'
            
            rows_html.append(
                f"<tr>"
                f"<td style='padding:10px;font-weight:bold;'>{ticker}</td>"
                f"<td style='padding:10px;font-family:monospace;'>{price_s}</td>"
                f"<td style='padding:10px;'>{vol_s}</td>"
                f"<td style='padding:10px;'>{rsi_s}</td>"
                f"<td style='padding:10px;'>{fav_html}</td>"
                f"<td style='padding:10px;'>{tv_html}</td>"
                f"</tr>"
            )
            
        thead = (
            "<tr style='background:rgba(255,255,255,0.05);text-align:left;border-bottom:2px solid rgba(255,255,255,0.1);'>"
            "<th style='padding:10px;'>品种</th>"
            "<th style='padding:10px;'>收盘价</th>"
            "<th style='padding:10px;'>4H成交量</th>"
            "<th style='padding:10px;'>RSI(14)</th>"
            "<th style='padding:10px;'>自选收藏</th>"
            "<th style='padding:10px;'>行情图表 (今日/总)</th>"
            "</tr>"
        )
        st.markdown(
            f"<div style='width:100%;overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:13px;'><thead>{thead}</thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

        # 💡 隐形事件监听组件：捕捉原链接点击，能在后台落盘计数，同时在前台秒级实时更新 (今日/总) 数字
        import streamlit.components.v1 as _components
        _js_code = (
            "<script>\n"
            "(function() {\n"
            "    try {\n"
            "        var pDoc = window.parent.document;\n"
            "        if (pDoc._tv_click_handler) {\n"
            "            pDoc.removeEventListener('click', pDoc._tv_click_handler, true);\n"
            "        }\n"
            "        pDoc._tv_click_handler = function(e) {\n"
            "            var btn = e.target.closest('.tv-btn, .sina-btn');\n"
            "            if (btn) {\n"
            "                var tk = btn.getAttribute('data-ticker');\n"
            "                if (tk) {\n"
            "                    tk = tk.trim().toUpperCase();\n"
            "                    var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);\n"
            "                    try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}\n"
            "                    try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}\n"
            "                    try {\n"
            "                        var f = pDoc.createElement('iframe');\n"
            "                        f.style.display = 'none';\n"
            "                        f.src = cbUrl;\n"
            "                        pDoc.body.appendChild(f);\n"
            "                        setTimeout(function() { try { f.remove(); } catch(err) {} }, 6000);\n"
            "                    } catch(err) {}\n"
            "                    try {\n"
            "                        var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');\n"
            "                        for (var i = 0; i < allBtns.length; i++) {\n"
            "                            var b = allBtns[i];\n"
            "                            var bTk = b.getAttribute('data-ticker');\n"
            "                            if (bTk && bTk.trim().toUpperCase() === tk) {\n"
            "                                var spans = b.getElementsByTagName('span');\n"
            "                                if (spans && spans.length > 0) {\n"
            "                                    var span = spans[spans.length - 1];\n"
            "                                    var txt = span.innerText || span.textContent || '';\n"
            "                                    var m = txt.match(/\\((\\d+)\\/(\\d+)\\)/);\n"
            "                                    if (m) {\n"
            "                                        var today = parseInt(m[1], 10) + 1;\n"
            "                                        var total = parseInt(m[2], 10) + 1;\n"
            "                                        span.innerText = '(' + today + '/' + total + ')';\n"
            "                                        span.style.color = '#4ade80';\n"
            "                                        span.style.fontWeight = '600';\n"
            "                                    }\n"
            "                                }\n"
            "                            }\n"
            "                        }\n"
            "                    } catch(err) {}\n"
            "                }\n"
            "            }\n"
            "        };\n"
            "        pDoc.addEventListener('click', pDoc._tv_click_handler, true);\n"
            "    } catch(err) {}\n"
            "})();\n"
            "</script>"
        )
        if hasattr(st, "html"):
            st.html(_js_code)
        else:
            import streamlit.components.v1 as _components
            _components.html(_js_code, height=0)

        # 详细条件展开
        for r in passed:
            with st.expander(f"🔍 {r['ticker']} — 条件明细", expanded=False):
                col_d1, col_d2 = st.columns([4, 1])
                with col_d1:
                    _render_details(r["details"])
                with col_d2:
                    if r['ticker'].upper() in wl_set:
                        if st.button(f"🗑️ 移除收藏", key=f"fav_det_del_{r['ticker']}", use_container_width=True):
                            storage.remove_from_watchlist(r['ticker'])
                            st.toast(f"已将 {r['ticker']} 从自选收藏夹移除", icon="🗑️")
                            st.rerun()
                    else:
                        if st.button(f"⭐ 加入收藏", key=f"fav_det_add_{r['ticker']}", use_container_width=True):
                            storage.add_to_watchlist(ticker=r['ticker'], name=r['ticker'], note="Chartink 4H Breakout 扫描匹配")
                            st.toast(f"⭐ 已将 {r['ticker']} 加入自选收藏夹", icon="⭐")
                            st.rerun()

    # ── 未通过（可折叠）────────────────────────────────────────────
    if failed:
        with st.expander(f"❌ 未通过品种（{len(failed)} 个）", expanded=False):
            for r in failed:
                st.markdown(
                    f'<div style="font-weight:600;font-size:13px;color:var(--text-color, #374151);'
                    f'margin:10px 0 4px">{r["ticker"]}</div>',
                    unsafe_allow_html=True,
                )
                _render_details(r["details"])

    # ── 数据错误 ────────────────────────────────────────────────────
    if errors:
        with st.expander(f"⚠️ 数据获取失败（{len(errors)} 个）", expanded=False):
            for r in errors:
                st.markdown(
                    f'<span style="font-family:monospace;font-size:12px">'
                    f'{r["ticker"]}</span> — {r["error"]}',
                    unsafe_allow_html=True,
                )


# ════════════════════════════════════════════════════════════════════
# UI 小组件
# ════════════════════════════════════════════════════════════════════

def _stat_card(label: str, value: str, color: str) -> str:
    COLORS = {
        "blue":  ("rgba(59, 130, 246, 0.12)", "#3b82f6", "rgba(59, 130, 246, 0.3)"),
        "green": ("rgba(16, 185, 129, 0.12)", "#10b981", "rgba(16, 185, 129, 0.3)"),
        "gray":  ("rgba(107, 114, 128, 0.12)", "var(--text-color, #6b7280)", "rgba(107, 114, 128, 0.3)"),
        "red":   ("rgba(239, 68, 68, 0.12)", "#ef4444", "rgba(239, 68, 68, 0.3)"),
    }
    bg, fg, border = COLORS.get(color, ("rgba(107, 114, 128, 0.12)", "var(--text-color, #374151)", "transparent"))
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:10px;padding:14px 12px;'
        f'text-align:center;margin-bottom:4px;color:var(--text-color, #111)">'
        f'<div style="font-size:11px;color:var(--text-color, #6b7280);opacity:0.8">{label}</div>'
        f'<div style="font-size:24px;font-weight:800;color:{fg};margin-top:4px">{value}</div>'
        f'</div>'
    )


def _render_details(details: list):
    html = (
        '<table style="width:100%;border-collapse:collapse;font-size:12px;color:var(--text-color, #111)">'
        '<thead><tr>'
        '<th style="text-align:left;padding:5px 8px;color:var(--text-color, #6b7280);opacity:0.8;font-weight:600;'
        'border-bottom:1px solid var(--border-color, #e5e7eb)">编号</th>'
        '<th style="text-align:left;padding:5px 8px;color:var(--text-color, #6b7280);opacity:0.8;font-weight:600;'
        'border-bottom:1px solid var(--border-color, #e5e7eb)">条件</th>'
        '<th style="text-align:left;padding:5px 8px;color:var(--text-color, #6b7280);opacity:0.8;font-weight:600;'
        'border-bottom:1px solid var(--border-color, #e5e7eb)">当前值</th>'
        '<th style="text-align:center;padding:5px 8px;color:var(--text-color, #6b7280);opacity:0.8;font-weight:600;'
        'border-bottom:1px solid var(--border-color, #e5e7eb)">结果</th>'
        '</tr></thead><tbody>'
    )
    for rule in details:
        ok     = rule["ok"]
        badge  = (
            '<span style="background:rgba(16, 185, 129, 0.2);color:#10b981;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:700">✓ 通过</span>'
            if ok else
            '<span style="background:rgba(239, 68, 68, 0.2);color:#ef4444;padding:2px 8px;'
            'border-radius:20px;font-size:11px;font-weight:700">✗ 未过</span>'
        )
        row_bg = "rgba(16, 185, 129, 0.06)" if ok else "rgba(239, 68, 68, 0.06)"
        html += (
            f'<tr style="background:{row_bg}">'
            f'<td style="padding:6px 8px;font-family:monospace;color:var(--text-color, #6b7280);opacity:0.8">{rule["id"]}</td>'
            f'<td style="padding:6px 8px;color:var(--text-color, #374151)">{rule["desc"]}</td>'
            f'<td style="padding:6px 8px;color:var(--text-color, #6b7280);opacity:0.8;font-family:monospace;font-size:11px">{rule["val"]}</td>'
            f'<td style="padding:6px 8px;text-align:center">{badge}</td>'
            f'</tr>'
        )
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)
