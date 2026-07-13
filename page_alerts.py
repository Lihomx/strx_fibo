"""
page_alerts.py — 告警配置与测试
"""
import streamlit as st
import pandas as pd

import storage
import alerts as alt


def render():
    st.markdown("## 🔔 告警配置")

    cfg = storage.load_config()

    tab1, tab2, tab3 = st.tabs(["📱 钉钉", "✈️ Telegram", "📋 告警日志"])

    # ── 钉钉 ─────────────────────────────────────────────────────────
    with tab1:
        st.markdown("#### 钉钉机器人配置")
        st.markdown("""
        <div class="n-info">
        💡 在钉钉群 → 群设置 → 机器人 → 自定义机器人，获取 Webhook 地址和安全密钥。
        </div>""", unsafe_allow_html=True)

        with st.form("dingtalk_form"):
            dt_en  = st.checkbox("启用钉钉告警", value=bool(cfg.get("dingtalk_enabled")))
            dt_wh  = st.text_input("Webhook 地址",
                                   value=cfg.get("dingtalk_webhook",""),
                                   placeholder="https://oapi.dingtalk.com/robot/send?access_token=…",
                                   type="password")
            dt_sec = st.text_input("加签密钥（可选）",
                                   value=cfg.get("dingtalk_secret",""),
                                   placeholder="SEC…",
                                   type="password")
            col1, col2 = st.columns(2)
            with col1:
                save_dt = st.form_submit_button("💾 保存", width="stretch")
            with col2:
                test_dt = st.form_submit_button("🧪 测试发送", width="stretch")

        if save_dt:
            storage.save_config({
                "dingtalk_enabled": dt_en,
                "dingtalk_webhook": dt_wh,
                "dingtalk_secret":  dt_sec,
            })
            st.success("✅ 钉钉配置已保存")

        if test_dt:
            test_cfg = dict(cfg)
            test_cfg.update({
                "dingtalk_enabled": True,
                "dingtalk_webhook": dt_wh,
                "dingtalk_secret":  dt_sec,
            })
            ok, msg = alt.send_dingtalk(
                "🧪 STRX Fibo Scanner 测试消息 — 连接成功！", test_cfg
            )
            if ok:
                st.success("✅ 测试消息发送成功")
            else:
                st.error(f"❌ 发送失败: {msg}")

    # ── Telegram ─────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Telegram Bot 配置")
        st.markdown("""
        <div class="n-info">
        💡 通过 @BotFather 创建 Bot 获取 Token；Chat ID 可通过 @userinfobot 获取。
        </div>""", unsafe_allow_html=True)

        with st.form("telegram_form"):
            tg_en  = st.checkbox("启用 Telegram 告警", value=bool(cfg.get("telegram_enabled")))
            tg_tok = st.text_input("Bot Token",
                                   value=cfg.get("telegram_token",""),
                                   placeholder="123456:ABC-…",
                                   type="password")
            tg_cid = st.text_input("Chat ID",
                                   value=cfg.get("telegram_chat_id",""),
                                   placeholder="-100123456789")
            col1, col2 = st.columns(2)
            with col1:
                save_tg = st.form_submit_button("💾 保存", width="stretch")
            with col2:
                test_tg = st.form_submit_button("🧪 测试发送", width="stretch")

        if save_tg:
            storage.save_config({
                "telegram_enabled": tg_en,
                "telegram_token":   tg_tok,
                "telegram_chat_id": tg_cid,
            })
            st.success("✅ Telegram 配置已保存")

        if test_tg:
            test_cfg = dict(cfg)
            test_cfg.update({
                "telegram_enabled": True,
                "telegram_token":   tg_tok,
                "telegram_chat_id": tg_cid,
            })
            ok, msg = alt.send_telegram(
                "🧪 STRX Fibo Scanner 测试消息 — 连接成功！", test_cfg
            )
            if ok:
                st.success("✅ 测试消息发送成功")
            else:
                st.error(f"❌ 发送失败: {msg}")

    # ── 自定义模版 ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 💬 自定义告警消息模版")
    
    tmpl_tab1, tmpl_tab2 = st.tabs(["📐 Fibonacci 扫描模版", "🚀 EMA20 + Daily Pivot 模版"])
    
    with tmpl_tab1:
        st.markdown("""
        <div class="n-info">
        💡 <b>Fibonacci 模版支持占位符：</b><br>
        <code>{label}</code> - 信号类型 (例如: 日线黄金区 / 三框架共振)<br>
        <code>{name}</code> - 品种中文名<br>
        <code>{ticker}</code> - 品种代码 (如 AAPL)<br>
        <code>{tf}</code> - 时间框架 (Daily/Weekly/Monthly)<br>
        <code>{price}</code> - 当前价格<br>
        <code>{zone_bot}</code> - 黄金区下轨<br>
        <code>{zone_top}</code> - 黄金区上轨<br>
        <code>{retrace_pct}</code> - 回撤比例 (%)<br>
        <code>{url}</code> - TradingView 图表链接<br>
        <code>{time}</code> - 触发时间
        </div>""", unsafe_allow_html=True)

        default_tmpl = "📐 STRX Fibo 信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📏 黄金区: {zone_bot} – {zone_top}\n📉 回撤: {retrace_pct}%\n🔗 {url}\n🕐 {time}"
        
        with st.form("template_form_fibo"):
            tmpl = st.text_area("消息模版",
                                value=cfg.get("alert_template", default_tmpl),
                                height=220,
                                help="自定义推送的消息格式，支持换行和纯文本占位符")
            
            col1, col2 = st.columns(2)
            with col1:
                save_tmpl = st.form_submit_button("💾 保存模版", width="stretch")
            with col2:
                test_tmpl = st.form_submit_button("🧪 测试模版效果", width="stretch")
                
        if save_tmpl:
            storage.save_config({"alert_template": tmpl})
            st.success("✅ Fibonacci 告警消息模版已保存")
            st.rerun()
            
        if test_tmpl:
            mock_fibo = {"current": 100.5, "zone_bot": 95.0, "zone_top": 105.0, "retrace_pct": 50.0}
            mock_conf = {"label": "日线黄金区"}
            rendered = alt.build_message("AAPL", "苹果公司", "Daily", mock_fibo, mock_conf, template=tmpl)
            st.info("📢 模版渲染预览效果：")
            st.code(rendered, language="text")

    with tmpl_tab2:
        st.markdown("""
        <div class="n-info">
        💡 <b>EMA20 + Daily Pivot 模版支持占位符：</b><br>
        <code>{label}</code> - 信号类型 (多头突破)<br>
        <code>{name}</code> - 品种中文名<br>
        <code>{ticker}</code> - 品种代码 (如 AAPL)<br>
        <code>{tf}</code> - 时间框架 (15m)<br>
        <code>{price}</code> - 当前收盘价格<br>
        <code>{ema}</code> - EMA20 均线值<br>
        <code>{pivot}</code> - Daily Pivot Point 值<br>
        <code>{url}</code> - TradingView 图表链接<br>
        <code>{time}</code> - 触发时间
        </div>""", unsafe_allow_html=True)

        default_tmpl_ep = "🚀 EMA20 + Daily Pivot 信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📈 EMA20: {ema}\n🎯 Pivot: {pivot}\n🔗 {url}\n🕐 {time}"
        
        with st.form("template_form_ema_pivot"):
            tmpl_ep = st.text_area("消息模版",
                                   value=cfg.get("alert_template_ema_pivot", default_tmpl_ep),
                                   height=220,
                                   help="自定义推送的消息格式，支持换行和纯文本占位符")
            
            col1, col2 = st.columns(2)
            with col1:
                save_tmpl_ep = st.form_submit_button("💾 保存模版", width="stretch")
            with col2:
                test_tmpl_ep = st.form_submit_button("🧪 测试模版效果", width="stretch")
                
        if save_tmpl_ep:
            storage.save_config({"alert_template_ema_pivot": tmpl_ep})
            st.success("✅ EMA + Pivot 告警消息模版已保存")
            st.rerun()
            
        if test_tmpl_ep:
            rendered = alt.build_message_ema_pivot("AAPL", "苹果公司", "15m", 100.5, 99.2, 98.5, "多头突破", template=tmpl_ep)
            st.info("📢 模版渲染预览效果：")
            st.code(rendered, language="text")

    # ── 冷却设置（全局）──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ⏱️ 告警冷却设置")
    with st.form("cooldown_form"):
        cd = st.slider("冷却时间（分钟）",
                       min_value=30, max_value=1440,
                       value=int(cfg.get("alert_cooldown", 240)),
                       step=30,
                       help="同一资产同一框架两次告警之间的最短间隔")
        if st.form_submit_button("💾 保存冷却设置", width="stretch"):
            storage.save_config({"alert_cooldown": cd})
            st.success(f"✅ 冷却时间已设为 {cd} 分钟")

    # ── 告警日志 ─────────────────────────────────────────────────────
    with tab3:
        render_alert_log_table(full_page=False)


def render_alert_log_table(full_page=False):
    # 顶部视图切换
    try:
        view_mode = st.segmented_control(
            "显示范围",
            options=["最近 20 条", "最近 50 条", "最近 100 条", "全部记录"],
            default="最近 100 条",
            key=f"alert_log_view_mode_{'full' if full_page else 'tab'}"
        ) or "最近 100 条"
    except Exception:
        view_mode = st.radio(
            "显示范围",
            options=["最近 20 条", "最近 50 条", "最近 100 条", "全部记录"],
            index=2,
            horizontal=True,
            key=f"alert_log_view_mode_{'full' if full_page else 'tab'}"
        )
        
    limit_map = {"最近 20 条": 20, "最近 50 条": 50, "最近 100 条": 100, "全部记录": 0}
    limit_val = limit_map[view_mode]
    
    logs = storage.load_alert_log(limit=limit_val)
    
    if not logs:
        st.info("暂无告警记录")
    else:
        df = pd.DataFrame(logs)
        
        # 兼容处理历史数据缺少 scanner 字段的情况
        if "scanner" not in df.columns:
            df["scanner"] = ""
        else:
            df["scanner"] = df["scanner"].fillna("")
            
        # ── 筛选器面板 ────────────────────────────────────────────────
        with st.expander("🔍 筛选过滤条件", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            with f_col1:
                import datetime
                today = datetime.date.today()
                seven_days_ago = today - datetime.timedelta(days=7)
                selected_dates = st.date_input(
                    "📅 日期范围",
                    value=(seven_days_ago, today),
                    help="筛选触发告警的日期区间",
                    key=f"alert_log_date_{'full' if full_page else 'tab'}"
                )
            with f_col2:
                search_q = st.text_input(
                    "🏷️ 代码 / 品种名",
                    placeholder="输入搜索关键字...",
                    help="不区分大小写，搜索代码或资产名称",
                    key=f"alert_log_search_{'full' if full_page else 'tab'}"
                )
            with f_col3:
                scanner_opt = st.selectbox(
                    "🔍 扫描器类型",
                    options=["全部", "Fibonacci 扫描", "EMA + Daily Pivot", "其他"],
                    help="根据触发告警的扫描类型进行筛选",
                    key=f"alert_log_scanner_{'full' if full_page else 'tab'}"
                )
            with f_col4:
                # 获取日志中已有的时间周期
                available_tf = []
                if "timeframe" in df.columns:
                    available_tf = sorted(list(df["timeframe"].dropna().unique()))
                if not available_tf:
                    available_tf = ["15m", "4H", "Daily", "Weekly", "Monthly"]
                timeframe_opt = st.multiselect(
                    "⏱️ 时间框架",
                    options=available_tf,
                    help="多选过滤时间框架",
                    key=f"alert_log_tf_{'full' if full_page else 'tab'}"
                )
        
        # ── 应用筛选逻辑 ─────────────────────────────────────────────
        # 1. 日期筛选
        if selected_dates:
            if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
                start_date, end_date = selected_dates
            elif isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 1:
                start_date = selected_dates[0]
                end_date = selected_dates[0]
            else:
                start_date = selected_dates
                end_date = selected_dates
                
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            df = df[df["time"].apply(lambda t: start_str <= str(t)[:10] <= end_str)]
            
        # 2. 文本搜索
        if search_q:
            q = search_q.strip().lower()
            df = df[
                df["ticker"].str.lower().str.contains(q, na=False) |
                df["name"].str.lower().str.contains(q, na=False)
            ]
            
        # 3. 扫描器筛选
        if scanner_opt == "Fibonacci 扫描":
            df = df[df["scanner"] == "fibo"]
        elif scanner_opt == "EMA + Daily Pivot":
            df = df[df["scanner"] == "ema_pivot"]
        elif scanner_opt == "其他":
            df = df[~df["scanner"].isin(["fibo", "ema_pivot"])]
            
        # 4. 时间框架筛选
        if timeframe_opt:
            df = df[df["timeframe"].isin(timeframe_opt)]
            
        # ── 统计摘要指标 ─────────────────────────────────────────────
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.metric("📊 过滤后记录数", f"{len(df)} 条")
        with m_col2:
            ok_count = len(df[df["status"] == "ok"]) if "status" in df.columns else 0
            st.metric("✅ 发送成功", f"{ok_count} 条")
        with m_col3:
            fail_count = len(df[df["status"] == "fail"]) if "status" in df.columns else 0
            st.metric("❌ 发送失败", f"{fail_count} 条", delta=f"{fail_count} 次异常" if fail_count > 0 else None, delta_color="inverse")
            
        # ── 列表渲染 ─────────────────────────────────────────────────
        if df.empty:
            st.warning("⚠️ 没有找到符合筛选条件的告警记录")
        else:
            from assets import tv_url
            
            # 转换扫描器标签
            def get_scanner_label(s):
                if s == "fibo":
                    return "Fibonacci"
                elif s == "ema_pivot":
                    return "EMA + Daily Pivot"
                return "其他/历史记录"
                
            df["scanner_name"] = df["scanner"].apply(get_scanner_label)
            df["tradingview"] = df["ticker"].apply(lambda t: tv_url(t, "15m"))
            
            show_cols = ["time", "ticker", "name", "scanner_name", "timeframe", "tradingview", "channel", "status", "message"]
            show_df = df[[c for c in show_cols if c in df.columns]]
            
            # 重命名表头以提升视觉体验
            show_df = show_df.rename(columns={
                "time": "时间",
                "ticker": "代码",
                "name": "名称",
                "scanner_name": "扫描器",
                "timeframe": "周期",
                "tradingview": "TradingView (15m)",
                "channel": "通知通道",
                "status": "发送状态",
                "message": "返回消息"
            })
            
            # 💡 动态为行着色：同时间批次的正常记录使用同一种交替色，失败记录保持红色高亮
            try:
                # 获取展示数据中所有唯一时间戳并排序
                unique_times = sorted(show_df["时间"].dropna().unique())
                time_to_group = {t: idx for idx, t in enumerate(unique_times)}
                
                def make_style(row):
                    status = row.get("发送状态", "")
                    if status == "fail" or status == "失败":
                        # 失败：柔和红背景，保持高亮警示
                        return ["background-color: rgba(239, 68, 68, 0.12);"] * len(row)
                    
                    # 正常记录交替分组底色
                    t_val = row.get("时间", "")
                    group_idx = time_to_group.get(t_val, 0)
                    if group_idx % 2 == 1:
                        # 奇数批次时间组：柔和灰蓝色背景
                        return ["background-color: rgba(30, 144, 255, 0.05);"] * len(row)
                    else:
                        # 偶数批次时间组：不加底色（保持透明）
                        return [""] * len(row)
                styled_df = show_df.style.apply(make_style, axis=1)
            except Exception:
                styled_df = show_df
            
            st.dataframe(
                styled_df,
                column_config={
                    "TradingView (15m)": st.column_config.LinkColumn(
                        "TradingView (15m)",
                        display_text="📈 打开图表",
                        help="点击在 TradingView 中以 15m 周期查看"
                    )
                },
                use_container_width=True,
                height=700
            )
            
        # 操作按钮：刷新 & 清空
        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
        with col_btn1:
            if st.button("🔄 刷新日志", key=f"alert_log_refresh_{'full' if full_page else 'tab'}", use_container_width=True):
                st.rerun()
        with col_btn2:
            if st.button("🗑️ 清空所有日志", key=f"alert_log_clear_{'full' if full_page else 'tab'}", use_container_width=True):
                storage.clear_alert_log()
                st.success("已成功清空所有日志记录")
                st.rerun()


def render_log_page():
    st.markdown("## 📋 告警日志")
    render_alert_log_table(full_page=True)


