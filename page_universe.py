"""
page_universe.py — 🌍 全量品种库

⚠️ 关于"全量扫描"的说明：
  A股 5454 支 × 3 个时间框架 = 16362 次网络请求
  按每次 1-2 秒估算 = 约 4-9 小时，Streamlit 会超时中断！

  正确用法：
  1. 使用搜索框找到目标品种
  2. 勾选感兴趣的品种（建议每次 ≤50 支）
  3. 点击「批量扫描选中品种」
  中断后结果会保存，可继续追加扫描更多品种。
"""

import time
import streamlit as st
import pandas as pd

import storage
import scanner as sc
import bg_scan_manager
from streamlit_autorefresh import st_autorefresh


# ════════════════════════════════════════════════════════════════════
# 带 30 分钟缓存的列表加载
# ════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def _load_a():
    """加载A股列表：AKShare → 静态兜底"""
    try:
        result = sc.get_all_a_share_tickers()
        if result:
            return result
    except Exception:
        pass
    # AKShare 失败 → 返回空，让调用方使用静态兜底
    return []

@st.cache_data(ttl=1800, show_spinner=False)
def _load_hk():
    """加载港股列表：AKShare → 静态兜底"""
    try:
        result = sc.get_all_hk_tickers()
        if result:
            return result
    except Exception:
        pass
    return []

@st.cache_data(ttl=1800, show_spinner=False)
def _load_us():
    """加载美股列表：AKShare → yfinance screener → 静态兜底"""
    # 方案1：AKShare（东方财富）
    try:
        result = sc.get_all_us_tickers()
        if result:
            return result
    except Exception:
        pass
    # 方案2：通过 yfinance 获取 S&P500 成分股（requests + Wikipedia）
    try:
        import requests
        import pandas as pd
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            tables = pd.read_html(resp.text)
            if tables:
                df = tables[0]
                result = []
                for _, row in df.iterrows():
                    ticker = str(row.get("Symbol","")).replace(".","-")
                    name   = str(row.get("Security",""))
                    if ticker and name:
                        result.append((ticker, name))
                if result:
                    return result
    except Exception:
        pass
    return []


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        st_autorefresh(interval=3000, key="univ_scan_auto_refresh")
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="univ_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status["job_type"] == "fibo_scan":
        if status["status"] == "done":
            st.success(f"✅ 后台扫描任务已完成!")
        elif status["status"] == "error":
            st.error(f"❌ 后台扫描任务出错! 错误信息: {status.get('error', '')}")
        elif status["status"] == "cancelled":
            st.warning("⚠️ 后台扫描任务已被取消。")
            
        if st.button("清除状态提示", key="univ_clear_status_btn"):
            bg_scan_manager.reset_to_idle()
            st.rerun()

    st.markdown("## 🌍 全量品种库")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '数据来自 <b>AKShare（东方财富）</b>，免费实时，无需 API Key。</p>',
        unsafe_allow_html=True,
    )

    # ── 重要说明横幅 ────────────────────────────────────────────
    st.markdown("""
    <div style="background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.3);border-radius:10px;
                padding:12px 16px;margin-bottom:12px;font-size:13px;color:var(--text-color);">
    <b>⚠️ 关于全量扫描</b><br>
    A股 5454 支 × 3 框架 = <b>16362 次</b>网络请求，约需 <b>4-9 小时</b>，Streamlit 会超时中断。<br>
    <b>推荐用法</b>：搜索 → 勾选目标品种（建议每批 ≤50 支）→ 批量扫描。<br>
    每次扫描结果会<b>自动保存累积</b>，中断后重新扫描其他品种，结果叠加展示。
    </div>
    """, unsafe_allow_html=True)

    # ── 数据源说明 ───────────────────────────────────────────────
    with st.expander("📡 数据源架构说明", expanded=False):
        st.markdown("""
        | 品种类型 | 主数据源 | 备用数据源 | 覆盖数量 |
        |---------|---------|---------|---------|
        | 🇨🇳 A股 | AKShare（东方财富）✅ 免费 | yfinance（.SS/.SZ） | **5,454** 支 |
        | 🇭🇰 港股 | AKShare（东方财富）✅ 免费 | yfinance（.HK） | **2,516** 支 |
        | 🇺🇸 美股 | AKShare（东方财富）✅ 免费 | yfinance | **16,527** 支 |
        | 🌐 外汇/期货/指数/加密 | yfinance ✅ 免费 | TwelveData（需Key） | 全覆盖 |
        """)

    # ── 市场选择 ────────────────────────────────────────────────
    market = st.radio(
        "选择市场",
        ["🇨🇳 A股（约5454支）", "🇭🇰 港股（约2516支）", "🇺🇸 美股（约16527支）"],
        horizontal=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    cfg = storage.load_config()

    if "A股" in market:
        _render_market("a_share", _load_a, "a_stock", cfg, "A股")
    elif "港股" in market:
        _render_market("hk_stock", _load_hk, "cn_stock", cfg, "港股")
    else:
        _render_market("us_stock", _load_us, "us_stock", cfg, "美股")


# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
# 静态兜底品种（AKShare 无法访问时使用 — 扩充至 300+ 支）
# ════════════════════════════════════════════════════════════════════
_FALLBACK_US = [
    # 科技巨头
    ("AAPL","苹果"),("MSFT","微软"),("GOOGL","谷歌A"),("GOOG","谷歌C"),("AMZN","亚马逊"),
    ("NVDA","英伟达"),("META","Meta"),("TSLA","特斯拉"),("NFLX","Netflix"),("ORCL","甲骨文"),
    ("ADBE","Adobe"),("CRM","Salesforce"),("AMD","AMD"),("INTC","英特尔"),("QCOM","高通"),
    ("AVGO","博通"),("TXN","德州仪器"),("MU","美光科技"),("AMAT","应用材料"),("LRCX","拉姆研究"),
    ("KLAC","科磊"),("MRVL","迈威科技"),("SMCI","超微电脑"),("PLTR","Palantir"),("SNOW","Snowflake"),
    ("CRWD","CrowdStrike"),("PANW","Palo Alto"),("ZS","Zscaler"),("FTNT","飞塔"),("OKTA","Okta"),
    # 金融
    ("JPM","摩根大通"),("BAC","美国银行"),("GS","高盛"),("MS","摩根士丹利"),("WFC","富国银行"),
    ("C","花旗"),("BLK","贝莱德"),("SCHW","嘉信理财"),("AXP","美国运通"),("V","Visa"),("MA","万事达"),
    ("PYPL","PayPal"),("SQ","Block"),("COF","首都一号"),("USB","美国合众"),("BK","纽约梅隆"),
    # 医疗健康
    ("JNJ","强生"),("PFE","辉瑞"),("MRNA","Moderna"),("ABBV","艾伯维"),("LLY","礼来"),
    ("BMY","百时美施贵宝"),("AMGN","安进"),("GILD","吉利德"),("BIIB","渤健"),("REGN","再生元"),
    ("ISRG","直觉外科"),("MDT","美敦力"),("ABT","雅培"),("TMO","赛默飞"),("DHR","丹纳赫"),
    ("UNH","联合健康"),("CVS","CVS Health"),("CI","信诺"),("HUM","好未来"),
    # 能源
    ("XOM","埃克森美孚"),("CVX","雪佛龙"),("COP","康菲石油"),("EOG","EOG资源"),("SLB","斯伦贝谢"),
    ("HAL","哈里伯顿"),("BKR","贝克休斯"),("DVN","德文能源"),("MPC","马拉松石油"),("VLO","瓦莱罗"),
    # 消费/零售
    ("WMT","沃尔玛"),("COST","好市多"),("TGT","塔吉特"),("HD","家得宝"),("LOW","劳氏"),
    ("NKE","耐克"),("SBUX","星巴克"),("MCD","麦当劳"),("YUM","百胜"),("CMG","奇波雷"),
    ("AMZN","亚马逊"),("BABA","阿里巴巴"),("JD","京东"),("PDD","拼多多"),("BIDU","百度"),
    # 工业/材料
    ("CAT","卡特彼勒"),("DE","约翰迪尔"),("BA","波音"),("LMT","洛克希德马丁"),("RTX","雷神技术"),
    ("GE","通用电气"),("HON","霍尼韦尔"),("MMM","3M"),("EMR","艾默生"),("ITW","伊利诺伊工具"),
    # 中概股
    ("NIO","蔚来"),("LI","理想汽车"),("XPEV","小鹏汽车"),("RIVN","Rivian"),
    ("BILI","哔哩哔哩"),("IQ","爱奇艺"),("TAL","好未来"),("EDU","新东方"),
    # ETF
    ("SPY","标普500ETF"),("QQQ","纳斯达克ETF"),("IWM","罗素2000ETF"),("DIA","道琼斯ETF"),
    ("VTI","全美股市ETF"),("GLD","黄金ETF"),("SLV","白银ETF"),("USO","原油ETF"),
    ("TLT","长期国债ETF"),("HYG","高收益债ETF"),("EEM","新兴市场ETF"),("FXI","中国ETF"),
    ("ARKK","ARK创新ETF"),("XLF","金融ETF"),("XLK","科技ETF"),("XLE","能源ETF"),
    ("XLV","医疗ETF"),("XLI","工业ETF"),("SOXX","半导体ETF"),
    # 汽车/电动车
    ("F","福特"),("GM","通用汽车"),("TM","丰田"),("HMC","本田"),("STLA","Stellantis"),
    ("LCID","路西德"),("FSR","菲斯克"),
    # 通信/媒体
    ("T","AT&T"),("VZ","Verizon"),("TMUS","T-Mobile"),("DIS","迪士尼"),("CMCSA","康卡斯特"),
    ("PARA","派拉蒙"),("WBD","华纳兄弟"),
    # 电商/互联网
    ("UBER","Uber"),("LYFT","Lyft"),("SNAP","Snap"),("PINS","Pinterest"),("RDDT","Reddit"),
    ("ABNB","Airbnb"),("DASH","DoorDash"),("HOOD","Robinhood"),
]

_FALLBACK_A = [
    # 金融
    ("600519","贵州茅台"),("601318","中国平安"),("600036","招商银行"),("601398","工商银行"),
    ("601288","农业银行"),("601166","兴业银行"),("600016","民生银行"),("600030","中信证券"),
    ("601601","中国太保"),("601628","中国人寿"),("601336","新华保险"),("601688","华泰证券"),
    ("000001","平安银行"),("600000","浦发银行"),("601169","北京银行"),("600015","华夏银行"),
    # 消费
    ("000858","五粮液"),("600887","伊利股份"),("603288","海天味业"),("000895","双汇发展"),
    ("002304","洋河股份"),("600009","上海机场"),("601888","中国国旅"),("000568","泸州老窖"),
    ("002507","涪陵榨菜"),("603587","地素时尚"),("002601","龙蟒佰利"),
    # 科技/新能源
    ("300750","宁德时代"),("601012","隆基绿能"),("002594","比亚迪"),("300014","亿纬锂能"),
    ("002415","海康威视"),("000063","中兴通讯"),("002230","科大讯飞"),("688111","金山办公"),
    ("603501","韦尔股份"),("002049","紫光国微"),("688012","中微公司"),("688041","海光信息"),
    ("688990","晶合集成"),("688256","寒武纪"),("300124","汇川技术"),("002236","大华股份"),
    # 工业/制造
    ("601888","中国国旅"),("000333","美的集团"),("000651","格力电器"),("600104","上汽集团"),
    ("601766","中国中车"),("601390","中国中铁"),("601800","中国交建"),("600028","中国石化"),
    ("601857","中国石油"),("600900","长江电力"),("601985","中国核电"),("600309","万华化学"),
    # 医疗
    ("600276","恒瑞医药"),("002007","华兰生物"),("300601","康泰生物"),("600763","通策医疗"),
    ("603259","药明康德"),("688363","华熙生物"),("000661","长春高新"),
    # 地产/建材
    ("000002","万科A"),("600048","保利发展"),("001979","招商蛇口"),("600606","绿地控股"),
    # 大盘ETF（按A股代码录入）
    ("510300","沪深300ETF"),("510500","中证500ETF"),("159915","创业板ETF"),
    ("588000","科创50ETF"),("510050","上证50ETF"),
]

_FALLBACK_HK = [
    # 科技互联网
    ("0700","腾讯控股"),("9988","阿里巴巴"),("3690","美团"),("9618","京东集团"),
    ("1024","快手"),("9999","网易"),("0241","阿里健康"),("0020","友邦保险"),
    # 金融
    ("1398","工商银行"),("0939","建设银行"),("3988","中国银行"),("1288","农业银行"),
    ("2318","中国平安"),("0002","中电控股"),("0388","香港交易所"),("0005","汇丰控股"),
    ("2388","中银香港"),("3328","交通银行"),("0011","恒生银行"),
    # 新能源/汽车
    ("1211","比亚迪股份"),("0175","吉利汽车"),("2015","理想汽车"),("9868","小鹏汽车"),
    ("9863","蔚来汽车"),("0285","比亚迪电子"),
    # 消费/零售
    ("0941","中国移动"),("0762","中国联通"),("0883","中国海洋石油"),
    ("2020","安踏体育"),("0960","龙湖集团"),("1928","金沙中国"),
    ("0291","华润啤酒"),("0027","银河娱乐"),("2382","舜宇光学"),
    # 医疗
    ("1177","中升控股"),("3799","敏实集团"),("1093","石药集团"),("0857","中国石油股份"),
    ("2313","申洲国际"),("0669","创科实业"),("1044","恒安国际"),
]

# 通用市场渲染
# ════════════════════════════════════════════════════════════════════
def _render_market(market_key: str, load_fn, category: str, cfg: dict, label: str):
    from html import escape as _he
    from urllib.parse import quote as _qu, unquote as _uq
    import re as _re

    # ── 处理 query_params 动作（选择/收藏）──────────────────────
    _univ_act = st.query_params.get(f"_u_{market_key}", "")
    if _univ_act:
        _univ_act = _uq(_univ_act)
        _u_parts = _univ_act.split("|", 2)   # "sel_add|ticker|name" etc
        if len(_u_parts) >= 2:
            _u_cmd, _u_tk = _u_parts[0], _u_parts[1]
            _u_nm = _u_parts[2] if len(_u_parts) > 2 else _u_tk
            _sel_key = f"univ_sel_{market_key}"
            if _u_cmd == "sel_add" and _re.match(r"^[\w.\-\^=]+$", _u_tk):
                _s = st.session_state.get(_sel_key, set())
                _s.add(_u_tk); st.session_state[_sel_key] = _s
            elif _u_cmd == "sel_del" and _re.match(r"^[\w.\-\^=]+$", _u_tk):
                _s = st.session_state.get(_sel_key, set())
                _s.discard(_u_tk); st.session_state[_sel_key] = _s
            elif _u_cmd == "fav_add" and _re.match(r"^[\w.\-\^=]+$", _u_tk):
                import storage as _st2
                _st2.add_to_watchlist(ticker=_u_tk, name=_u_nm[:60],
                                      note=f"{label}品种库添加")
                st.toast(f"已收藏：{_u_nm[:30]}", icon="⭐")
            elif _u_cmd == "fav_del" and _re.match(r"^[\w.\-\^=]+$", _u_tk):
                import storage as _st2
                _st2.remove_from_watchlist(_u_tk)
                st.toast(f"已移除：{_u_nm[:30]}", icon="🗑️")
        st.query_params.pop(f"_u_{market_key}", None)
        st.rerun()

    # ── 加载品种列表（带重试 + 缓存清除）──────────────────────
    cache_key = f"_uni_retry_{market_key}"
    if st.session_state.get(cache_key):
        # 用户点击重试：清除缓存强制重新拉取
        st.cache_data.clear()
        st.session_state.pop(cache_key, None)

    with st.spinner(f"📡 从 AKShare 获取{label}品种列表（约5-15秒）…"):
        try:
            raw_list: list = load_fn()
        except Exception as e:
            err_msg = str(e)
            st.error(f"❌ 加载 {label} 品种列表失败")
            with st.expander("查看错误详情"):
                st.code(err_msg)
            st.markdown("""
            **常见原因及解决方案：**
            - 🌐 **网络问题**：AKShare 需要访问东方财富服务器，Streamlit Cloud 的网络有时不稳定
            - 📦 **依赖未安装**：首次部署后等待 2-3 分钟让 akshare 完成安装
            - ⏱️ **临时超时**：点击下方「重新获取」按钮重试
            """)
            col_retry, col_manual = st.columns(2)
            with col_retry:
                if st.button("🔄 重新获取品种列表", key=f"retry_{market_key}", type="primary"):
                    st.session_state[cache_key] = True
                    st.rerun()
            with col_manual:
                st.info("💡 或在「自定义品种扫描」中直接输入 Ticker 代码使用")
            return

    if not raw_list:
        # 使用内置静态兜底数据
        fallback_map = {
            "a_share":  _FALLBACK_A,
            "hk_stock": _FALLBACK_HK,
            "us_stock": _FALLBACK_US,
        }
        raw_list = fallback_map.get(market_key, [])
        if raw_list:
            st.info(
                f"📦 已加载 **{len(raw_list)}** 个内置{label}品种（实时列表暂不可用）。"
                f"可直接勾选扫描，或点击「🔄 重新获取」重试实时列表。"
            )
            col_r, _ = st.columns([2, 5])
            with col_r:
                if st.button("🔄 重新获取实时列表", key=f"retry3_{market_key}"):
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.warning("⚠️ 未获取到品种数据，请检查网络或稍后重试。")
            if st.button("🔄 重新获取", key=f"retry2_{market_key}"):
                st.cache_data.clear()
                st.rerun()
            return

    total_raw = len(raw_list)
    name_map: dict = {t: n for t, n in raw_list}

    col_stat, col_tip = st.columns([3, 5])
    with col_stat:
        st.success(f"✅ 已加载 **{total_raw:,}** 个{label}品种")
    with col_tip:
        st.markdown(
            f'<div style="color:#6b7280;font-size:12px;padding-top:8px">'
            f'💡 搜索后勾选目标品种，点击「批量扫描」开始分析（建议每批 ≤50 支）</div>',
            unsafe_allow_html=True,
        )

    # ── 搜索 + 排序 + 分页 ──────────────────────────────────────
    col_kw, col_sort, col_ps = st.columns([4, 2, 2])
    with col_kw:
        kw = st.text_input(
            "🔍 搜索品种",
            placeholder="输入代码或名称关键词（如：茅台、AAPL、0700）",
            key=f"univ_kw_{market_key}",
        )
    with col_sort:
        sort_mode = st.selectbox(
            "排序", ["默认顺序", "按代码 A→Z", "按名称"],
            key=f"univ_sort_{market_key}",
        )
    with col_ps:
        page_size = st.selectbox(
            "每页显示", [50, 100, 200],
            key=f"univ_ps_{market_key}",
        )

    # 过滤
    kw_u = kw.strip().upper()
    filtered = (
        [(t, n) for t, n in raw_list if kw_u in t.upper() or kw_u in n.upper()]
        if kw_u else raw_list
    )

    # 排序
    if sort_mode == "按代码 A→Z":
        filtered = sorted(filtered, key=lambda x: x[0])
    elif sort_mode == "按名称":
        filtered = sorted(filtered, key=lambda x: x[1])

    total_f = len(filtered)
    n_pages = max(1, (total_f + page_size - 1) // page_size)

    page_idx = st.number_input(
        f"页码（共 {n_pages} 页，{total_f:,} 条）",
        min_value=1, max_value=n_pages, value=1,
        key=f"univ_page_{market_key}",
    ) - 1

    page_items = filtered[page_idx * page_size: (page_idx + 1) * page_size]

    # ── 批量选择状态 ─────────────────────────────────────────────
    sel_key = f"univ_sel_{market_key}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = set()
    selected: set = st.session_state[sel_key]

    # 全选/清除
    col_selall, col_clr, col_warn, col_cnt = st.columns([2, 2, 4, 2])
    with col_selall:
        if st.button(f"☑️ 全选当页({len(page_items)}支)", key=f"univ_selall_{market_key}"):
            for t, _ in page_items:
                selected.add(t)
            st.session_state[sel_key] = selected
            st.rerun()
    with col_clr:
        if st.button("✖ 清除全部选择", key=f"univ_clr_{market_key}"):
            st.session_state[sel_key] = set()
            st.rerun()
    with col_warn:
        if len(selected) > 50:
            st.markdown(
                f'<span style="color:#dc2626;font-size:12px">'
                f'⚠️ 已选 {len(selected)} 支，建议每批 ≤50 支以避免超时</span>',
                unsafe_allow_html=True,
            )
    with col_cnt:
        st.markdown(
            f'<div style="color:#6b7280;font-size:12px;padding-top:8px;text-align:right">'
            f'已选 <b>{len(selected)}</b> 支</div>',
            unsafe_allow_html=True,
        )

    # ── 自选收藏状态 ─────────────────────────────────────────────
    watchlist = storage.load_watchlist()
    wl_set    = {w["ticker"] for w in watchlist if isinstance(w, dict)}

    # ── 品种列表：使用纯 st.columns 逐行渲染，彻底解决按钮错位 ────
    # 每行直接在同一个 st.columns 内渲染：序号|代码|名称|选择按钮|收藏按钮|扫描按钮|TV链接
    # 这是 Streamlit 中保证按钮与文字完全同行对齐的唯一可靠方式

    # 表头（纯 HTML，仅做视觉对齐参考）
    st.markdown("""
    <style>
    .ut3-hdr{display:grid;grid-template-columns:40px 120px 1fr 90px 70px 90px 70px;
             gap:4px;padding:6px 8px;background:var(--secondary-background-color, #f9fafb);border-bottom:2px solid var(--border-color, #e5e7eb);
             border-radius:6px 6px 0 0;font-size:12px;font-weight:600;color:var(--text-color, #374151);
             align-items:center;margin-bottom:0}
    .ut3-hdr span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .ut3-body{border:1px solid var(--border-color, #e5e7eb);border-top:none;border-radius:0 0 6px 6px;
              margin-bottom:12px}
    /* 让行内每个 st.columns 的按钮样式更紧凑 */
    .row-item .stButton>button{
        padding:3px 6px !important;
        font-size:12px !important;
        min-height:28px !important;
        border-radius:5px !important;
    }
    @media(max-width:768px){
      .ut3-hdr{grid-template-columns:30px 80px 1fr 70px 50px 70px 50px;font-size:11px}
    }
    </style>
    <div class="ut3-hdr">
      <span>#</span>
      <span>代码</span>
      <span>名称</span>
      <span style="text-align:center">选择</span>
      <span style="text-align:center">收藏</span>
      <span style="text-align:center">扫描</span>
      <span style="text-align:center">图表</span>
    </div>
    <div class="ut3-body">
    """, unsafe_allow_html=True)

    for i, (ticker, name) in enumerate(page_items):
        global_i = page_idx * page_size + i + 1
        is_fav   = ticker in wl_set
        is_sel   = ticker in selected

        # TV link
        if market_key == "a_share":
            exch   = "SH" if ticker[0] == "6" else ("BJ" if ticker[0] in ("4","8","9") else "SZ")
            tv_lnk = f"https://cn.tradingview.com/chart/?symbol={exch}{ticker}"
        elif market_key == "hk_stock":
            num    = ticker.replace(".HK","").lstrip("0") or "0"
            tv_lnk = f"https://cn.tradingview.com/chart/?symbol=HKEX:{num}"
        else:
            tv_lnk = f"https://cn.tradingview.com/chart/?symbol={ticker}"

        # 奇偶行背景
        row_bg = "background:rgba(107,114,128,0.03)" if i % 2 == 0 else "background:transparent"
        if is_sel:
            row_bg = "background:rgba(59,130,246,0.08)"

        st.markdown(
            f'<div style="{row_bg};padding:4px 8px;border-bottom:1px solid var(--border-color, #f3f4f6);'
            f'display:flex;align-items:center;min-height:36px;color:var(--text-color)">',
            unsafe_allow_html=True
        )

        # 7列：# | 代码 | 名称 | [选择按钮] | [收藏按钮] | [扫描按钮] | [TV链接]
        c_no, c_tk, c_nm, c_sel, c_fav, c_scan, c_tv = st.columns(
            [0.5, 1.3, 3.2, 1.1, 0.8, 1.1, 0.8]
        )
        with c_no:
            st.markdown(
                f'<div style="color:#9ca3af;font-size:11px;text-align:center;'
                f'padding-top:4px">{global_i}</div>',
                unsafe_allow_html=True
            )
        with c_tk:
            st.markdown(
                f'<div style="font-family:monospace;font-size:12px;font-weight:600;'
                f'padding-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                f'{ticker}</div>',
                unsafe_allow_html=True
            )
        with c_nm:
            st.markdown(
                f'<div style="font-size:12px;padding-top:4px;overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap" title="{name}">'
                f'{name}</div>',
                unsafe_allow_html=True
            )
        with c_sel:
            sel_lbl = "✅ 已选" if is_sel else "⬜ 选择"
            sel_type = "primary" if is_sel else "secondary"
            if st.button(sel_lbl, key=f"sel_{market_key}_{page_idx}_{i}",
                         help=f"{'取消选择' if is_sel else '选择'} {name}",
                         use_container_width=True, type=sel_type):
                if is_sel:
                    selected.discard(ticker)
                else:
                    selected.add(ticker)
                st.session_state[sel_key] = selected
                st.rerun()
        with c_fav:
            fav_lbl = "★" if is_fav else "☆"
            if st.button(fav_lbl, key=f"fav_{market_key}_{page_idx}_{i}",
                         help=f"{'取消收藏' if is_fav else '收藏'} {name}",
                         use_container_width=True):
                if is_fav:
                    storage.remove_from_watchlist(ticker)
                    st.toast(f"已移除：{name}", icon="🗑️")
                else:
                    storage.add_to_watchlist(ticker=ticker, name=name,
                                             note=f"{label}品种库添加")
                    st.toast(f"已收藏：{name}", icon="⭐")
                st.rerun()
        with c_scan:
            if st.button("🔍 扫描", key=f"scan_{market_key}_{page_idx}_{i}",
                         help=f"单独扫描 {name}（约6秒）",
                         use_container_width=True,
                         disabled=bg_scan_manager.is_running()):
                _run_single(ticker, name, category, cfg)
        with c_tv:
            st.markdown(
                f'<a href="{tv_lnk}" target="_blank" '
                f'style="color:#e85d04;font-size:12px;text-decoration:none;'
                f'display:block;text-align:center;padding-top:4px">📈 TV</a>',
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="color:#9ca3af;font-size:11px;margin:4px 0 12px">'
        f'共 {len(page_items)} 条｜✅已选 {len(selected)} 支｜点击按钮可选择/收藏/扫描单支品种</div>',
        unsafe_allow_html=True,
    )

        # ── 批量扫描 ─────────────────────────────────────────────────
    st.markdown("---")
    n_sel = len(selected)

    if n_sel > 0:
        est_sec = n_sel * 3 * 2
        est_min = est_sec // 60
        col_l, col_r = st.columns([7, 3])
        with col_l:
            if n_sel <= 50:
                st.info(
                    f"✅ 已选 **{n_sel}** 支 | 预计耗时约 **{est_sec}秒**（{est_min}分钟）"
                    f" | {n_sel*3} 次 Fibonacci 检查"
                )
            else:
                st.warning(
                    f"⚠️ 已选 **{n_sel}** 支 | 预计耗时 **{est_min}分钟** ｜"
                    f" 建议分批，每批 ≤50 支"
                )
        with col_r:
            if st.button(
                f"🚀 批量扫描 {n_sel} 支",
                type="primary",
                key=f"univ_batch_{market_key}",
                disabled=bg_scan_manager.is_running(),
            ):
                assets_batch = {t: (name_map.get(t, t), category) for t in selected}
                _run_batch(assets_batch, cfg)
    else:
        st.caption("☑️ 请先勾选品种，再点击批量扫描")


# ════════════════════════════════════════════════════════════════════
# 后台扫描 Worker
# ════════════════════════════════════════════════════════════════════
def fibo_scan_worker(params, update_progress, cancel_check):
    cfg = params["cfg"]
    assets = params["assets"]
    note = params["note"]
    timeframe_names = params.get("timeframe_names")
    
    import re as _re
    
    def cb(pct, text):
        if cancel_check():
            raise bg_scan_manager.CancelException("Scan cancelled by user")
        
        m = _re.search(r"(\d+)/(\d+)", text)
        if m:
            done_count = int(m.group(1))
            total_count = int(m.group(2))
        else:
            done_count = int(pct * 100)
            total_count = 100
            
        update_progress(done_count, total_count, text)
        
    try:
        summary, err = sc.run_full_scan(
            cfg=cfg,
            assets=assets,
            note=note,
            timeframe_names=timeframe_names,
            progress_callback=cb,
        )
        if err:
            raise Exception(err)
            
    except bg_scan_manager.CancelException:
        pass


# ════════════════════════════════════════════════════════════════════
# 单支扫描
# ════════════════════════════════════════════════════════════════════
def _run_single(ticker: str, name: str, category: str, cfg: dict):
    params = {
        "cfg": cfg,
        "assets": {ticker: (name, category)},
        "note": f"universe_single:{ticker}"
    }
    
    ok, msg = bg_scan_manager.submit_job(
        job_type="fibo_scan",
        label=f"单股扫描 ({name})",
        params=params,
        worker_fn=fibo_scan_worker
    )
    if ok:
        st.success(msg)
        time.sleep(1)
        st.rerun()
    else:
        st.error(msg)


# ════════════════════════════════════════════════════════════════════
# 批量扫描（带进度条）
# ════════════════════════════════════════════════════════════════════
def _run_batch(assets: dict, cfg: dict):
    if not assets:
        return

    n = len(assets)
    params = {
        "cfg": cfg,
        "assets": assets,
        "note": f"universe_batch:{n}支"
    }
    
    ok, msg = bg_scan_manager.submit_job(
        job_type="fibo_scan",
        label=f"品种库批量扫描 ({n}支)",
        params=params,
        worker_fn=fibo_scan_worker
    )
    if ok:
        st.success(msg)
        time.sleep(1)
        st.rerun()
    else:
        st.error(msg)
