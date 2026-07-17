"""
page_settings.py — 系统设置
"""
import streamlit as st
import storage
from assets import ASSET_GROUPS, ASSETS, TIMEFRAMES


def render():
    st.markdown("## ⚙️ 系统设置")
    cfg = storage.load_config()

    tab1, tab2, tab3 = st.tabs(["📐 Fibonacci 参数", "📡 数据源", "⚙️ 系统与缓存"])

    # ── Tab1: Fibo 参数 ───────────────────────────────────────────────
    with tab1:
        st.markdown("### Fibonacci 计算参数")
        col1, col2 = st.columns(2)
        with col1:
            lookback = st.slider("Lookback（观察周期）", 20, 500,
                                 int(cfg.get("lookback", 100)), 5,
                                 help="用于确定摆动高低点的K线数量")
            zone_lo = st.slider("黄金区间上沿 (0.5)", 0.3, 0.6,
                                float(cfg.get("fibo_low", 0.5)), 0.01)
        with col2:
            zone_hi = st.slider("黄金区间下沿 (0.618)", 0.5, 0.9,
                                float(cfg.get("fibo_high", 0.618)), 0.01)
            watch_dist = st.slider("接近区间阈值 (%)", 1.0, 20.0,
                                   float(cfg.get("watch_dist", 5.0)), 0.5)
        st.markdown("""
        **公式（与 STRX Pine Script 完全一致）：**
        ```
        swingHigh = ta.highest(high, lookback)
        swingLow  = ta.lowest(low, lookback)
        fp(r)     = swingHigh - r × (swingHigh - swingLow)
        黄金区间  = fp(0.618) ≤ close ≤ fp(0.500)
        ```
        """)
        
        if st.button("💾 保存参数", type="primary"):
            cfg.update({"lookback": lookback, "fibo_low": zone_lo,
                        "fibo_high": zone_hi, "watch_dist": watch_dist})
            if storage.save_config(cfg):
                st.success("✅ 参数已保存")

    # ── Tab2: 数据源 ─────────────────────────────────────────────────
    with tab2:
        st.markdown("### 数据源配置")
        src = st.radio("数据源", ["yfinance（免费）", "Twelve Data（需API Key）"],
                       index=0 if cfg.get("data_source", "yfinance") == "yfinance" else 1)
        ds = "yfinance" if "yfinance" in src else "twelvedata"

        if ds == "twelvedata":
            tdkey = st.text_input("Twelve Data API Key",
                                  value=cfg.get("twelvedata_key", ""),
                                  type="password")
            st.caption("免费版：800次/天 | https://twelvedata.com")
        else:
            tdkey = cfg.get("twelvedata_key", "")
            st.markdown("""
            **yfinance（默认推荐）**
            - 完全免费，无需注册
            - 支持：美股 / ETF / 期货 / 外汇 / 指数 / 港股 / 加密货币
            - A股支持：需使用 `600519.SS` / `000858.SZ` 格式
            - 限制：批量请求较慢（每品种约0.5-1秒）
            """)

        if st.button("🔗 测试连接"):
            try:
                import yfinance as yf
                t = yf.Ticker("AAPL")
                h = t.history(period="5d")
                if not h.empty:
                    st.success(f"✅ 连接成功！AAPL 最新收盘价 ${float(h['Close'].iloc[-1]):.2f}")
                else:
                    st.warning("⚠️ 连接成功但无数据")
            except Exception as e:
                st.error(f"❌ 连接失败：{e}")

        if st.button("💾 保存数据源设置", type="primary"):
            cfg.update({"data_source": ds, "twelvedata_key": tdkey})
            if storage.save_config(cfg): st.success("✅ 已保存")

    # ── Tab3: 系统与缓存 ─────────────────────────────────────────────
    with tab3:
        st.markdown("### 🌍 全球时区设置")
        import zoneinfo
        try:
            all_tzs = sorted(list(zoneinfo.available_timezones()))
        except Exception:
            all_tzs = ["Asia/Shanghai", "UTC", "America/New_York", "Europe/London", "Asia/Tokyo", "Asia/Singapore"]
        
        common_tzs = ["Asia/Shanghai", "UTC", "America/New_York", "Europe/London", "Asia/Tokyo", "Asia/Singapore"]
        other_tzs = [tz for tz in all_tzs if tz not in common_tzs]
        display_tzs = common_tzs + other_tzs
        
        current_tz = cfg.get("timezone", "Asia/Shanghai")
        if current_tz not in display_tzs:
            display_tzs.insert(0, current_tz)
            
        tz_index = display_tzs.index(current_tz)
        
        with st.form("timezone_settings_form"):
            selected_tz = st.selectbox(
                "显示时区",
                options=display_tzs,
                index=tz_index,
                help="设置后，系统将自动转换并以该时区显示所有的告警记录和时间戳。"
            )
            if st.form_submit_button("💾 保存时区设置"):
                cfg["timezone"] = selected_tz
                if storage.save_config(cfg):
                    st.success(f"✅ 系统时区已成功切换为 {selected_tz}")
                    st.rerun()
                    
        st.markdown("---")
        st.markdown("### 🎨 显示与主页个性化设置")
        with st.form("appearance_settings_form"):
            col_app1, col_app2, col_app3 = st.columns(3)
            with col_app1:
                font_size_opt = st.selectbox(
                    "全局字体大小",
                    options=["默认 (14px)", "大 (16px)", "超大 (18px)"],
                    index=["默认 (14px)", "大 (16px)", "超大 (18px)"].index(cfg.get("font_size", "默认 (14px)")),
                    help="调整系统正文、列表、卡片和表格的字体大小。"
                )
            with col_app2:
                theme_style_opt = st.selectbox(
                    "系统显示风格 (主题)",
                    options=["原厂默认", "极简深邃 (Minimal Dark)", "温暖护眼 (Warm Sepia)", "清新雅致 (Sage Forest)"],
                    index=["原厂默认", "极简深邃 (Minimal Dark)", "温暖护眼 (Warm Sepia)", "清新雅致 (Sage Forest)"].index(cfg.get("theme_style", "原厂默认")),
                    help="提供护眼、极简暗黑等不同配色风格，适合长期盯盘使用。"
                )
            with col_app3:
                homepages_map = {
                    "watchlist": "⭐ 自选收藏",
                    "hotlist": "🔥 热门品种",
                    "scanner": "📊 实时扫描",
                    "confluence": "⚡ 共振检测",
                    "triple_bottom": "📐 三重底扫描",
                    "chartink": "📈 4H Breakout",
                    "schedule": "⏰ 定时扫描",
                    "universe": "🌍 全量品种库",
                    "symbols": "💎 品种库",
                    "history": "📂 历史记录",
                    "alert_logs": "📋 告警日志",
                    "alerts": "🔔 告警配置",
                    "cloud": "☁️ 云端同步",
                    "settings": "⚙️ 系统设置"
                }
                homepage_keys = list(homepages_map.keys())
                current_home = cfg.get("homepage", "watchlist")
                if current_home not in homepage_keys:
                    current_home = "watchlist"
                homepage_opt = st.selectbox(
                    "默认主页",
                    options=homepage_keys,
                    format_func=lambda x: homepages_map[x],
                    index=homepage_keys.index(current_home),
                    help="设置登录后或者重新打开网址时默认显示的系统页面。"
                )
            if st.form_submit_button("💾 保存显示与个性化设置"):
                cfg["font_size"] = font_size_opt
                cfg["theme_style"] = theme_style_opt
                cfg["homepage"] = homepage_opt
                if storage.save_config(cfg):
                    st.success("✅ 显示与主页个性化设置已成功保存！")
                    st.rerun()
                    
        st.markdown("---")
        st.markdown("### 💾 存储 & 缓存管理")
        stats = storage.storage_stats()
        total_symbols = sum(len(g) for g in ASSET_GROUPS.values())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("缓存品种数", stats["unique_tickers"])
        c2.metric("总检查条目", stats["total_cached_results"])
        c3.metric("扫描会话数", stats["sessions"])
        c4.metric("数据大小", f"{stats['allres_kb']} KB")

        # 已扫描组
        scanned = stats.get("scanned_groups", [])
        unscanned = [g for g in ASSET_GROUPS if g not in scanned]
        all_groups = list(ASSET_GROUPS.keys())

        st.markdown(f"""
        #### 分批扫描进度
        - 总组数：**{len(all_groups)}** 组（共 {total_symbols} 个品种）
        - 已扫描：**{len(scanned)}** 组 ✅
        - 未扫描：**{len(unscanned)}** 组
        """)

        if scanned:
            st.markdown("**已扫描组：**")
            cols = st.columns(4)
            for i, g in enumerate(scanned):
                cols[i % 4].markdown(f"✅ {g[:20]}")
        if unscanned:
            st.markdown("**未扫描组：**")
            cols = st.columns(4)
            for i, g in enumerate(unscanned):
                cols[i % 4].markdown(f"⬜ {g[:20]}")

        st.markdown("---")
        st.markdown("**缓存升级路径**")
        st.markdown("""
        当前：JSON 文件（Streamlit Cloud 临时存储）  
        升级：替换 `storage.py` 中 7 个函数即可切换至 Supabase / PostgreSQL，
        其他所有文件无需修改。
        """)

        col_clr1, col_clr2, col_clr3 = st.columns(3)
        with col_clr1:
            if st.button("🗑️ 清空所有缓存", type="secondary"):
                storage.clear_all_data()
                st.success("✅ 已清空")
                st.rerun()
        with col_clr2:
            if st.button("🔄 重置已扫描记录"):
                storage.clear_scanned_groups()
                st.success("✅ 已重置，下次扫描将视为全新")
                st.rerun()
        with col_clr3:
            if st.button("🔧 重置参数为默认"):
                if storage.save_config({}):
                    st.success("✅ 已重置"); st.rerun()

        st.markdown("---")
        st.markdown("### 🚫 退市与无效代码过滤管理")
        delisted_list = storage.load_delisted_tickers()
        if delisted_list:
            st.warning(f"⚠️ 当前已自动过滤以下 {len(delisted_list)} 个连续失败的无效/退市代码（扫描时将自动跳过，避免无效请求导致 API 限流）：")
            st.text_area("已过滤代码", value=", ".join(delisted_list), height=80, disabled=True, label_visibility="collapsed")
            
            sub_col1, sub_col2 = st.columns([2, 3])
            with sub_col1:
                if st.button("🗑️ 清空过滤列表", key="clear_delisted_btn", type="secondary", use_container_width=True):
                    storage.save_delisted_tickers([])
                    st.success("✅ 已清空过滤列表，下次扫描将重新尝试获取这些代码的数据")
                    st.rerun()
            with sub_col2:
                del_ticker = st.text_input("手动移出过滤列表", placeholder="例如: 601138.SS", key="del_ticker_inp", label_visibility="collapsed").strip().upper()
                if del_ticker:
                    if st.button("🔓 移出", key="remove_single_delisted_btn", type="primary", use_container_width=True):
                        storage.remove_delisted_ticker(del_ticker)
                        storage.reset_scan_failure(del_ticker)
                        st.success(f"✅ 已将 {del_ticker} 移出过滤列表")
                        st.rerun()
        else:
            st.success("✅ 当前无过滤的退市/无效代码。")
            manual_add = st.text_input("手动添加退市/无效代码", placeholder="例如: 000000.SS", key="add_ticker_inp").strip().upper()
            if manual_add:
                if st.button("🚫 过滤该代码", key="add_single_delisted_btn", type="primary"):
                    storage.add_delisted_ticker(manual_add)
                    st.success(f"✅ 已将 {manual_add} 加入过滤列表")
                    st.rerun()
