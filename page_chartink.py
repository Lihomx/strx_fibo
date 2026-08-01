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
    """下载 OHLCV，失败返回 None"""
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
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
    except Exception:
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

    # ── 下载数据 ────────────────────────────────────────────────────
    df_1d = _fetch(ticker, "1d", "1y")
    if df_1d is None or len(df_1d) < 60:
        result["error"] = "日线数据不足"
        return result

    # 1H 数据（用于 2H/4H 的重采样与兜底）
    df_1h = _fetch(ticker, "1h", "2mo")

    # 4H 数据（优先使用原生 4h，若缺失或异常则通过 1h 重采样）
    df_4h = _fetch(ticker, "4h", "6mo")
    if (df_4h is None or len(df_4h) < 5) and (df_1h is not None and len(df_1h) >= 4):
        try:
            df_4h = df_1h.resample("4h").agg({
                "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
            }).dropna(subset=["close"])
        except Exception:
            pass

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
    tickers = params["tickers"]
    passed_list = []
    failed_list = []
    error_list = []
    
    total = len(tickers)
    for i, tk in enumerate(tickers):
        if cancel_check():
            raise bg_scan_manager.CancelException("Scan cancelled by user")
            
        update_progress(i, total, f"扫描中 {i}/{total}: {tk}")
        
        try:
            res = _check_ticker(tk)
            res["ticker"] = tk
            if res["error"]:
                error_list.append(res)
            elif res["passed"]:
                passed_list.append(res)
            else:
                failed_list.append(res)
        except Exception as e:
            error_list.append({"ticker": tk, "passed": False, "details": [], "error": str(e)})
            
        time.sleep(0.15)   # 避免 yfinance 限流
        
    results = {
        "passed": passed_list,
        "failed": failed_list,
        "errors": error_list,
        "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
    }
    storage.save_chartink(results)


# ════════════════════════════════════════════════════════════════════
# Streamlit 页面
# ════════════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────────────
# 美国股票全股票池（S&P 500 完整成分股）
# 来源：S&P 500 官方成分股（约503只），适合作为美股基础扫描池。
# 用户可在页面文本框中自行增删，此处仅作默认值。
# ────────────────────────────────────────────────────────────────────
_DEFAULT_TICKERS = """
MMM AOS ABT ABBV ACN ATVI ADM ADP ADBE AES AFL A APD AKAM ALK ALB
ARE ALGN ALLE LNT ALL GOOGL GOOG MO AMZN AMCR AMD AEE AAL AEP AXP
AIG AMGN APH ADI ANSS AON APA AIV APH AAPL AMAT APTV ACGL ANET AJG
AWK AMP ABC AME AMTM AXON APA APTV ARES APA APO APD ARNC ATMUS ARW
T ATO ADSK AZO AVB AVY AXON BKR BALL BAC BK BBWI BAX BDX WRB BRK.B
BBY BIO TECH BLK BX BK BMY AVGO BR BSX BLDR BXP COF CDNS CZR CPB
COO COP CSCO C CFG CLX CME CMS KO CTLT CMCS COG CL CTSH ED CNC CF
CINF CTAS CSCO CPAY CRL CVS CVX CDAY CHD CI CINF CTRA CMG CB CCL
CPRT CAH KMX CCL CAT CBOE CBRE CDW CE CF CHTR CMI CMS CNP COF COO
COP CRM COST CPRT CSX CTAS CTLT CTSH CVS CVX CDAY DHR DHI XRAY DVN
DXCM DE DAL DDOG DFS DAY DLR DLTR DOV DOW DTE ECL ED EIX EMN ETN EA
EMR ENPH EFX EPAM EL ELV EXC EXPE EXPD EXR XOM EXR FFIV FDS FICO
FAST FDX FIS FITB FMC F FTV FOXA FOX BEN FCX GRMN IT GEHC GE GEV
GEN GNRC GIS GPC GPN GPS GL GLW GM GS HIG HAL HAS HCA PEAK HSIC HSY
HES HPE HIG HPQ HRL HST HD HON HWM HUM HBAN HII IBM ICE IEX ILMN
INCY IR INTC INTU ISRG IVZ INVH IQV IRM JBHT J JKHY JCI JNJ JPM JNPR
K KDP KEY KEYS KMB KIM KMI KLAC KHC KR LHX LH LRCX LW LVS LDOS LEN
LLY LIN LYV LKQ LMT LOW LULU LYB MTB MRO MPC MKTX MAR MMC MLM MAS MA
MKC MELI MCK MDT MET MDB MGM MCK MDLZ MOH HPE META MOS MSI MSFT MU
MUR MRK MCO MS MSCI NDAQ NEE NKE NEM NTRS NWS NWSA NOC NVR NFLX
NVDA NRG NUE NXPI ODFL OMC ON OKE ORCL OXY ORTX OTIS PCAR PKG PANW
PYPL PAYX PNR ABBV PBCT PFE PCG PM PSA PGR PTC PTR PEG PSX PXD PFG
PPG PPL PRU PEG PEP QRVO QCOM RL RTX O REG REGN RF RSG RMD ROK ROL
ROP ROST RCL SPGI CRM SBAC SLB STE STX SRE NOW SHW SIRI SWKS SJM
SNA SOLV SO LUV SPG SBUX STT STLD STE STZ SWK SYF SYK SYY TMUS TROW
TGT TDY TFC GOOGL TJX TSCO TT TMO TDG TRV TRMB TFC TYL TSN UDR ULTA
USB UPS URI UNH UNP VLO VTR VRSN VRSK VZ VRTX VLTO VST V WBA WMT WBD
WM WAT WEC WST WFC WYNN WDC WHR WMB WTW GWW WRK XEL XYL YUM ZBRA ZBH
ZION ZTS
""".split()


def render():
    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        st_autorefresh(interval=3000, key="chartink_scan_auto_refresh")
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="chartink_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status["job_type"] == "chartink_scan":
        if status["status"] == "done":
            st.success(f"✅ 后台扫描任务已完成!")
        elif status["status"] == "error":
            st.error(f"❌ 后台扫描任务出错! 错误信息: {status.get('error', '')}")
        elif status["status"] == "cancelled":
            st.warning("⚠️ 后台扫描任务已被取消。")
            
        if st.button("清除状态提示", key="chartink_clear_status_btn"):
            bg_scan_manager.reset_to_idle()
            st.rerun()

    st.markdown("## 📈 Chartink · 4 Hour Breakout")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '扫描满足全部 7 个条件的品种：4H 量能爆发 + 日线趋势多头（一云 / RSI / Supertrend）'
        '</p>',
        unsafe_allow_html=True,
    )

    # ── 条件说明卡片 ────────────────────────────────────────────────
    with st.expander("📋 扫描条件说明", expanded=False):
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
        cache = storage.load_chartink()
        if cache and isinstance(cache, dict) and (cache.get("passed") or cache.get("total")):
            storage._save_with_backup(storage.F_CHARTINK, cache)
            try:
                import cloud_sync
                if cloud_sync.is_configured():
                    cloud_sync._upload_snapshot("chartink", cache)
            except Exception:
                pass
        storage.save_chartink({})
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.push_chartink()
        except Exception:
            pass
        st.toast("🗑️ 已自动备份当前扫描结果并成功清空！", icon="✅")
        time.sleep(0.5)
        st.rerun()

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
        today_str_val = datetime.datetime.now().strftime("%Y-%m-%d")
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
                fav_html = f'<a href="/?_page=chartink&_fav=del|{ticker}|{ticker}{_t_param}" target="_self" style="color:#f59e0b;text-decoration:none;font-weight:600;font-size:12px;background:rgba(245,158,11,0.15);padding:4px 10px;border-radius:4px;border:1px solid rgba(245,158,11,0.3);">★ 已收藏</a>'
            else:
                fav_html = f'<a href="/?_page=chartink&_fav=add|{ticker}|{ticker}{_t_param}" target="_self" style="color:#eab308;text-decoration:none;font-weight:600;font-size:12px;background:rgba(234,179,8,0.1);padding:4px 10px;border-radius:4px;border:1px solid rgba(234,179,8,0.2);">⭐ 收藏</a>'
            
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
        _components.html(r"""
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

                            // 1. fetch 强制 no-store 穿透所有浏览器/CDN 缓存
                            try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}

                            // 2. sendBeacon 后台保障发送
                            try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}

                            // 3. IFrame 静音发送
                            try {
                                var f = pDoc.createElement('iframe');
                                f.style.display = 'none';
                                f.src = cbUrl;
                                pDoc.body.appendChild(f);
                                setTimeout(function() {
                                    try { f.remove(); } catch(err) {}
                                }, 6000);
                            } catch(err) {}

                            // 4. 前台 DOM 瞬间更新该 ticker 所有对应按钮数值 (秒级反馈)
                            try {
                                var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');
                                for (var i = 0; i < allBtns.length; i++) {
                                    var b = allBtns[i];
                                    var bTk = b.getAttribute('data-ticker');
                                    if (bTk && bTk.trim().toUpperCase() === tk) {
                                        var spans = b.getElementsByTagName('span');
                                        if (spans && spans.length > 0) {
                                            var span = spans[spans.length - 1];
                                            var txt = span.innerText || span.textContent || "";
                                            var m = txt.match(/\((\d+)\/(\d+)\)/);
                                            if (m) {
                                                var today = parseInt(m[1], 10) + 1;
                                                var total = parseInt(m[2], 10) + 1;
                                                span.innerText = '(' + today + '/' + total + ')';
                                                span.style.color = '#4ade80';
                                                span.style.fontWeight = '600';
                                            }
                                        }
                                    }
                                }
                            } catch(err) {}
                        }
                    }
                };
                pDoc.addEventListener('click', pDoc._tv_click_handler, true);
            } catch(err) {}
        })();
        </script>
        """, height=0)

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
    """渲染7条规则的逐条状态表格"""
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
