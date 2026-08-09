"""
page_alerts.py — 告警配置与测试
"""
import streamlit as st
import pandas as pd

import time
import storage
import alerts as alt


def render():
    st.markdown("## 🔔 告警配置")

    cfg = storage.load_config()

    tab1, tab2, tab3, tab4 = st.tabs(["📱 钉钉", "✈️ Telegram", "🖥️ 浏览器弹窗", "📋 告警日志"])

    # ── 钉钉 ─────────────────────────────────────────────────────────
    with tab1:
        st.markdown("#### 钉钉机器人配置")
        st.markdown("""
        <div class="n-info">
        💡 在钉钉群 → 群设置 → 机器人 → 自定义机器人，获取 Webhook 地址和安全密钥。<br>
        🔄 <b>多机器人轮换</b>：配置多个机器人后，系统每月自动切换（1月→机器人1，2月→机器人2……），月额度单独计算，不再超限。
        </div>""", unsafe_allow_html=True)

        # ── 当前生效机器人状态 ─────────────────────────────────────────
        pool = cfg.get("dingtalk_webhooks_pool", [])
        pool = [b for b in pool if isinstance(b, dict) and b.get("webhook", "").strip()]
        if pool:
            month_idx   = __import__("datetime").datetime.now().month - 1
            active_idx  = month_idx % len(pool)
            active_bot  = pool[active_idx]
            active_label = active_bot.get("label", f"机器人{active_idx + 1}")
            st.success(
                f"🟢 当前生效：**{active_label}**（共 {len(pool)} 个机器人，"
                f"本月 {__import__('datetime').datetime.now().month} 月使用第 {active_idx + 1} 个）"
            )
        else:
            single_wh = cfg.get("dingtalk_webhook", "").strip()
            if single_wh:
                st.info("🔵 当前使用：**单一机器人**（未配置轮换池）")
            else:
                st.warning("⚠️ 尚未配置任何钉钉机器人 Webhook")

        st.markdown("---")

        # ── 单一机器人（兼容旧配置，pool 为空时生效）─────────────────
        with st.expander("🤖 单一机器人配置（未使用轮换池时生效）",
                         expanded=not bool(pool)):
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
                    save_dt = st.form_submit_button("💾 保存", use_container_width=True)
                with col2:
                    test_dt = st.form_submit_button("🧪 测试发送", use_container_width=True)

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
                    "dingtalk_enabled":      True,
                    "dingtalk_webhook":      dt_wh,
                    "dingtalk_secret":       dt_sec,
                    "dingtalk_webhooks_pool": [],   # 测试时强制用当前填写的 webhook
                })
                ok, msg = alt.send_dingtalk(
                    "🧪 STRX Fibo Scanner 测试消息 — 连接成功！", test_cfg
                )
                if ok:
                    st.success("✅ 测试消息发送成功")
                else:
                    st.error(f"❌ 发送失败: {msg}")

        st.markdown("---")

        # ── 多机器人轮换池管理 ─────────────────────────────────────────
        st.markdown("#### 🔄 多机器人轮换池")
        st.caption("填入后系统每月自动选用对应机器人；池为空时使用上方单一配置。")

        # 显示现有机器人列表
        raw_pool = cfg.get("dingtalk_webhooks_pool", [])
        if not isinstance(raw_pool, list):
            raw_pool = []

        for i, bot in enumerate(raw_pool):
            if not isinstance(bot, dict):
                continue
            month_active = ((__import__("datetime").datetime.now().month - 1) % len(raw_pool) == i) if raw_pool else False
            tag = " 🟢 本月生效" if month_active else ""
            with st.expander(f"机器人 {i+1}：{bot.get('label', f'机器人{i+1}')}{tag}",
                             expanded=month_active):
                bc1, bc2, bc3 = st.columns([2, 1, 1])
                with bc1:
                    st.code(bot.get("webhook","")[:60] + "…" if len(bot.get("webhook","")) > 60
                            else bot.get("webhook",""), language=None)
                with bc2:
                    if st.button("🧪 测试", key=f"dt_pool_test_{i}", use_container_width=True):
                        test_cfg2 = dict(cfg)
                        test_cfg2.update({
                            "dingtalk_enabled":      True,
                            "dingtalk_webhooks_pool": [],
                            "dingtalk_webhook":      bot.get("webhook",""),
                            "dingtalk_secret":       bot.get("secret",""),
                        })
                        ok, msg = alt.send_dingtalk(
                            f"🧪 测试消息 — 机器人{i+1} 连接成功！", test_cfg2
                        )
                        if ok:
                            st.success("✅ 发送成功")
                        else:
                            st.error(f"❌ {msg}")
                with bc3:
                    if st.button("🗑 删除", key=f"dt_pool_del_{i}", use_container_width=True):
                        new_pool = [b for j, b in enumerate(raw_pool) if j != i]
                        storage.save_config({"dingtalk_webhooks_pool": new_pool})
                        st.success(f"已删除机器人 {i+1}")
                        st.rerun()

        # 添加新机器人
        st.markdown("##### ➕ 添加机器人到轮换池")
        with st.form("dt_pool_add_form", clear_on_submit=True):
            new_label = st.text_input("机器人名称（便于识别）",
                                      placeholder="例：7月备用机器人")
            new_wh    = st.text_input("Webhook 地址",
                                      placeholder="https://oapi.dingtalk.com/robot/send?access_token=…",
                                      type="password")
            new_sec   = st.text_input("加签密钥（可选）",
                                      placeholder="SEC…",
                                      type="password")
            if st.form_submit_button("➕ 添加到轮换池", use_container_width=True):
                if not new_wh.strip():
                    st.error("❌ Webhook 地址不能为空")
                else:
                    cur_pool = cfg.get("dingtalk_webhooks_pool", [])
                    if not isinstance(cur_pool, list):
                        cur_pool = []
                    cur_pool.append({
                        "label":   new_label.strip() or f"机器人{len(cur_pool)+1}",
                        "webhook": new_wh.strip(),
                        "secret":  new_sec.strip(),
                    })
                    storage.save_config({"dingtalk_webhooks_pool": cur_pool})
                    st.success(f"✅ 已添加到轮换池（当前共 {len(cur_pool)} 个机器人）")
                    st.rerun()

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
    
    tmpl_tab1, tmpl_tab2, tmpl_tab3 = st.tabs(["📐 Fibonacci 扫描模版", "🚀 EMA20 + Daily Pivot 模版", "📈 Chartink 4H Breakout 模版"])
    
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

    with tmpl_tab3:
        st.markdown("""
        <div class="n-info">
        💡 <b>Chartink 4H Breakout 模版支持占位符：</b><br>
        <code>{label}</code> - 信号类型 (4H 突破)<br>
        <code>{name}</code> - 品种中文名<br>
        <code>{ticker}</code> - 品种代码 (如 AAPL)<br>
        <code>{tf}</code> - 时间框架 (4h)<br>
        <code>{price}</code> - 当前收盘价格<br>
        <code>{volume_4h}</code> - 4H 成交量<br>
        <code>{rsi}</code> - Daily RSI 值<br>
        <code>{url}</code> - TradingView 图表链接<br>
        <code>{time}</code> - 触发时间
        </div>""", unsafe_allow_html=True)

        default_tmpl_ci = "📈 Chartink 4H Breakout 突破信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📊 4H成交量: {volume_4h}\n📈 RSI: {rsi}\n🔗 {url}\n🕐 {time}"
        
        with st.form("template_form_chartink"):
            tmpl_ci = st.text_area("消息模版",
                                   value=cfg.get("alert_template_chartink", default_tmpl_ci),
                                   height=220,
                                   help="自定义推送的消息格式，支持换行和纯文本占位符")
            
            col1, col2 = st.columns(2)
            with col1:
                save_tmpl_ci = st.form_submit_button("💾 保存模版", width="stretch")
            with col2:
                test_tmpl_ci = st.form_submit_button("🧪 测试模版效果", width="stretch")
                
        if save_tmpl_ci:
            storage.save_config({"alert_template_chartink": tmpl_ci})
            st.success("✅ Chartink 告警消息模版已保存")
            st.rerun()
            
        if test_tmpl_ci:
            rendered = alt.build_message_chartink("AAPL", "苹果公司", "4h", 100.5, 1250000, 62.5, "4H 突破", template=tmpl_ci)
            st.info("📢 模版渲染预览效果：")
            st.code(rendered, language="text")

    # ── 告警过滤与冷却设置（全局）────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ⚙️ 告警触发与冷却设置")
    with st.form("alert_settings_form"):
        col_rule1, col_rule2 = st.columns(2)
        with col_rule1:
            fibo_in_zone = st.checkbox("📐 Fibonacci 告警: 仅在黄金区内时发送",
                                        value=bool(cfg.get("alert_fibo_in_zone_only", True)),
                                        help="开启后，只有当价格处于黄金区内时才会发送告警；关闭则即使在黄金区外也发送。")
        with col_rule2:
            st.caption("🚀 **上涨扫描条件组（Bullish）**")
            filter_4h = st.checkbox("当前价格必须在 4小时 20-MA 均线之上",
                                    value=bool(cfg.get("filter_4h_ema20", False)),
                                    help="开启后，在进行 EMA20 + Daily Pivot 上涨扫描时，当前价格必须运行在4小时周期的 20 EMA均线之上，否则过滤不触发告警。")
            filter_1h = st.checkbox("当前价格必须在 1小时 20-MA 均线之上",
                                    value=bool(cfg.get("filter_1h_ema20", False)),
                                    help="开启后，在进行 EMA20 + Daily Pivot 上涨扫描时，当前价格必须运行在1小时周期的 20 EMA均线之上，否则过滤不触发告警。")
            filter_15m = st.checkbox("当前价格必须在 15分钟 20-MA 均线之上",
                                     value=bool(cfg.get("filter_15m_ema20", False)),
                                     help="开启后，在进行 EMA20 + Daily Pivot 上涨扫描时，当前价格必须运行在15分钟周期的 20 EMA均线之上，否则过滤不触发告警。")
            
            st.caption("🔻 **下跌扫描条件组（Bearish）**")
            filter_4h_bear = st.checkbox("当前价格必须在 4小时 20-MA 均线之下",
                                         value=bool(cfg.get("filter_4h_ema20_bear", False)),
                                         help="开启后，在进行 EMA20 + Daily Pivot 下跌扫描时，当前价格必须运行在4小时周期的 20 EMA均线之下，否则过滤不触发告警。")
            filter_1h_bear = st.checkbox("当前价格必须在 1小时 20-MA 均线之下",
                                         value=bool(cfg.get("filter_1h_ema20_bear", False)),
                                         help="开启后，在进行 EMA20 + Daily Pivot 下跌扫描时，当前价格必须运行在1小时周期的 20 EMA均线之下，否则过滤不触发告警。")
            filter_15m_bear = st.checkbox("当前价格必须在 15分钟 20-MA 均线之下",
                                          value=bool(cfg.get("filter_15m_ema20_bear", False)),
                                          help="开启后，在进行 EMA20 + Daily Pivot 下跌扫描时，当前价格必须运行在15分钟周期的 20 EMA均线之下，否则过滤不触发告警。")
            
        st.markdown("<div style='margin: 10px 0;'></div>", unsafe_allow_html=True)
        
        col_cd1, col_cd2, col_cd3 = st.columns(3)
        with col_cd1:
            cd_fibo = st.slider("📐 Fibonacci 扫描冷却时间（分钟）",
                                min_value=15, max_value=1440,
                                value=int(cfg.get("alert_cooldown_fibo", cfg.get("alert_cooldown", 240))),
                                step=15,
                                help="同一资产在 Fibonacci 扫描中的告警最小间隔（分钟）")
        with col_cd2:
            cd_ema = st.slider("🚀 EMA + Daily Pivot 冷却时间（分钟）",
                               min_value=15, max_value=1440,
                               value=int(cfg.get("alert_cooldown_ema_pivot", cfg.get("alert_cooldown", 240))),
                               step=15,
                               help="同一资产在 EMA + Daily Pivot 扫描中的告警最小间隔（分钟）")
        with col_cd3:
            cd_chartink = st.slider("📈 Chartink 4H Breakout 冷却时间（分钟）",
                                   min_value=15, max_value=1440,
                                   value=int(cfg.get("alert_cooldown_chartink", cfg.get("alert_cooldown", 240))),
                                   step=15,
                                   help="同一资产在 Chartink 扫描中的告警最小间隔（分钟）")
                               
        if st.form_submit_button("💾 保存设置", width="stretch"):
            storage.save_config({
                "alert_fibo_in_zone_only": fibo_in_zone,
                "filter_4h_ema20": filter_4h,
                "filter_1h_ema20": filter_1h,
                "filter_15m_ema20": filter_15m,
                "filter_4h_ema20_bear": filter_4h_bear,
                "filter_1h_ema20_bear": filter_1h_bear,
                "filter_15m_ema20_bear": filter_15m_bear,
                "alert_cooldown_fibo": cd_fibo,
                "alert_cooldown_ema_pivot": cd_ema,
                "alert_cooldown_chartink": cd_chartink,
            })
            st.success("✅ 告警过滤与冷却时间配置已保存")
            st.rerun()

    # ── 浏览器通知 ───────────────────────────────────────────────────
    with tab3:
        st.markdown("#### 🖥️ 浏览器桌面通知")
        st.markdown("""
        <div style="background-color: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.2); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <p style="margin: 0 0 8px 0; font-weight: bold; color: #fbbf24; font-size: 14px;">⚠️ 跨设备切换与浏览器通知限制说明：</p>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #cbd5e1; line-height: 1.6;">
                <li><b>局限性</b>：浏览器桌面通知<b>仅对当前正开着网页的这台电脑和当前浏览器页签有效</b>。它无法像 Telegram/钉钉那样把消息推送到离线设备。</li>
                <li><b>多设备切换</b>：由于您经常在<b>公司</b>和<b>家里</b>两台电脑切换使用，浏览器通知无法在未开网页的电脑上唤醒。<b>强烈建议您配置第一、第二选项卡的 🤖 Telegram 或 💬 钉钉</b>，即可在手机和所有电脑上同步且可靠地收到实时告警。</li>
                <li><b>手势授权限制</b>：现代浏览器（Chrome/Edge）为了防止骚扰，<b>禁止自动请求通知权限</b>，必须由您在页面上<b>手动点击按钮</b>才能唤醒授权弹窗。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # 使用自定义的 HTML 组件在前端处理权限申请与测试，彻底规避现代浏览器安全限制
        js_notify_ui = f"""
        <div style="background-color: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 20px; border-radius: 8px; font-family: sans-serif; color: #f3f4f6;">
            <div style="margin-bottom: 20px;">
                <h5 style="margin: 0 0 10px 0; font-size: 14px; color: #38bdf8;">🔑 第一步：授权浏览器通知</h5>
                <p style="margin: 0 0 10px 0; font-size: 12px; color: #94a3b8;">点击下方按钮以唤醒浏览器的通知权限申请弹窗（若已授权，会显示当前状态为已允许）：</p>
                <button id="btn-request" onclick="requestNotificationPermission()" style="background-color: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.2s;">
                    🔔 申请授权浏览器通知
                </button>
                <span id="permission-status" style="margin-left: 15px; font-size: 13px; font-weight: bold; color: #f59e0b;">检查中...</span>
            </div>
            
            <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.05); margin: 20px 0;" />
            
            <div>
                <h5 style="margin: 0 0 10px 0; font-size: 14px; color: #38bdf8;">🧪 第二步：直接在当前浏览器测试发送</h5>
                <p style="margin: 0 0 12px 0; font-size: 12px; color: #94a3b8;">点击下方按钮将在当前浏览器上立即弹出一行系统测试通知，并伴随提示音：</p>
                
                <div style="margin-bottom: 12px;">
                    <label style="display: block; font-size: 12px; color: #cbd5e1; margin-bottom: 4px;">测试标题</label>
                    <input type="text" id="test-title" value="📐 Fibo 信号发现" style="width: 100%; max-width: 400px; background: #1e293b; border: 1px solid #475569; padding: 6px 10px; border-radius: 4px; color: white; font-size: 13px;" />
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-size: 12px; color: #cbd5e1; margin-bottom: 4px;">测试内容</label>
                    <input type="text" id="test-body" value="贵州茅台 (600519.SS) 触及日线黄金区" style="width: 100%; max-width: 400px; background: #1e293b; border: 1px solid #475569; padding: 6px 10px; border-radius: 4px; color: white; font-size: 13px;" />
                </div>
                
                <button id="btn-test" onclick="sendTestNotification()" style="background-color: #10b981; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.2s;">
                    🧪 发送测试桌面通知
                </button>
            </div>
        </div>

        <script>
            function updatePermissionUI() {{
                const statusSpan = document.getElementById("permission-status");
                if (!("Notification" in window)) {{
                    statusSpan.innerText = "❌ 您的浏览器不支持桌面通知";
                    statusSpan.style.color = "#ef4444";
                    document.getElementById("btn-request").disabled = true;
                    return;
                }}
                
                const perm = Notification.permission;
                if (perm === "granted") {{
                    statusSpan.innerText = "✅ 已授权允许通知";
                    statusSpan.style.color = "#22c55e";
                }} else if (perm === "denied") {{
                    statusSpan.innerText = "❌ 已拒绝通知（请在浏览器地址栏左侧解锁）";
                    statusSpan.style.color = "#ef4444";
                }} else {{
                    statusSpan.innerText = "❔ 尚未授权（请点击左侧按钮申请）";
                    statusSpan.style.color = "#f59e0b";
                }}
            }}

            function requestNotificationPermission() {{
                if (!("Notification" in window)) return;
                Notification.requestPermission().then(function(perm) {{
                    updatePermissionUI();
                    if (perm === "granted") {{
                        alert("🎉 浏览器通知授权成功！");
                    }}
                }});
            }}

            function playBeepSound() {{
                try {{
                    const AudioContext = window.AudioContext || window.webkitAudioContext || window.parent.AudioContext || window.parent.webkitAudioContext;
                    const ctx = new AudioContext();
                    
                    // Beep 1
                    const osc1 = ctx.createOscillator();
                    const gain1 = ctx.createGain();
                    osc1.connect(gain1);
                    gain1.connect(ctx.destination);
                    osc1.frequency.setValueAtTime(880, ctx.currentTime);
                    gain1.gain.setValueAtTime(0.08, ctx.currentTime);
                    gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
                    osc1.start(ctx.currentTime);
                    osc1.stop(ctx.currentTime + 0.12);
                    
                    // Beep 2
                    const osc2 = ctx.createOscillator();
                    const gain2 = ctx.createGain();
                    osc2.connect(gain2);
                    gain2.connect(ctx.destination);
                    osc2.frequency.setValueAtTime(1046.5, ctx.currentTime + 0.15);
                    gain2.gain.setValueAtTime(0.08, ctx.currentTime + 0.15);
                    gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.32);
                    osc2.start(ctx.currentTime + 0.15);
                    osc2.stop(ctx.currentTime + 0.32);
                }} catch (e) {{
                    console.error("AudioContext play failed", e);
                }}
            }}

            function sendTestNotification() {{
                if (!("Notification" in window)) {{
                    alert("您的浏览器不支持桌面通知。");
                    return;
                }}
                
                const titleInput = document.getElementById("test-title").value;
                const bodyInput = document.getElementById("test-body").value;
                
                playBeepSound();

                if (Notification.permission === "granted") {{
                    new Notification(titleInput, {{
                        body: bodyInput
                    }});
                }} else {{
                    Notification.requestPermission().then(function(perm) {{
                        updatePermissionUI();
                        if (perm === "granted") {{
                            new Notification(titleInput, {{
                                body: bodyInput
                            }});
                        }} else {{
                            alert("❌ 无法发送通知：未获得浏览器授权。请先点击第一步按钮进行授权。");
                        }}
                    }});
                }}
            }}

            // 页面加载完成后自动更新一次UI状态
            setTimeout(updatePermissionUI, 500);
        </script>
        """
        st.components.v1.html(js_notify_ui, height=360, scrolling=False)
        
        # 后台依然保存静音/非静音设置
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        with st.form("browser_sound_config_form"):
            sound_enabled = bool(cfg.get("browser_notification_sound_enabled", False))
            b_sound = st.checkbox("🔊 启用后台声音提醒（仅在页面开启时随告警触发声音）", value=sound_enabled)
            if st.form_submit_button("💾 保存声音配置", use_container_width=True):
                storage.save_config({"browser_notification_sound_enabled": b_sound})
                st.success("✅ 声音配置已成功保存")
                st.rerun()

    # ── 告警日志 ─────────────────────────────────────────────────────
    with tab4:
        render_alert_log_table(full_page=False)


def render_alert_log_table(full_page=False):
    cfg = storage.load_config()
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
            
        # ── 时区转换处理 ─────────────────────────────────────────────
        tz_name = cfg.get("timezone", "Asia/Shanghai")
        
        def convert_tz(t_str):
            from datetime import datetime
            from zoneinfo import ZoneInfo
            if not t_str or not isinstance(t_str, str):
                return str(t_str)
            # 1. 尝试解析 ISO 格式 (带时区偏移)
            try:
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                tz = ZoneInfo(tz_name)
                return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            # 2. 尝试解析旧格式 "YYYY-MM-DD HH:MM"
            try:
                dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M")
                # 旧记录默认视为 UTC 时区时间，转换为目标时区
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                tz = ZoneInfo(tz_name)
                return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return t_str
                
        if "time" in df.columns:
            df["time"] = df["time"].apply(convert_tz)

        # ── 预加载重点关注品种与名称 ─────────────────────────────────────
        starred_tickers = storage.load_starred_tickers()
        starred_set = set(starred_tickers)
        
        # ── ⭐ 重点关注快捷汇总面板 (默认展开) ───────────────────────────
        if starred_set:
            with st.expander("⭐ 重点关注品种告警汇总", expanded=True):
                st.markdown("<div style='font-size:12px;color:#9ca3af;margin-bottom:8px;'>以下为标记重点关注的品种列表及最新告警快照：</div>", unsafe_allow_html=True)
                
                # 预加载品种全称
                custom_symbols = storage.load_symbols()
                watchlist_items = storage.load_watchlist()
                symbol_name_map = {item["ticker"].upper(): item["name"] for item in custom_symbols if item.get("name")}
                for item in watchlist_items:
                    if item.get("name") and item.get("ticker"):
                        symbol_name_map[item["ticker"].upper()] = item["name"]

                # ── 重点关注顺序调整 ──
                with st.expander("↕️ 拖动或修改排序调整卡片顺序", expanded=False):
                    st.caption("💡 可在此直接拖动表格行（按左侧行号拖拽）或修改「排序」列来调整卡片顺序，点击保存即可生效：")
                    df_stk_order = pd.DataFrame([
                        {"排序": idx + 1, "品种代码": tk, "品种名称": symbol_name_map.get(tk, tk)}
                        for idx, tk in enumerate(starred_tickers)
                    ])
                    edited_stk_df = st.data_editor(
                        df_stk_order,
                        num_rows="fixed",
                        row_height=38,
                        column_config={
                            "排序": st.column_config.NumberColumn("排序", min_value=1, max_value=len(starred_tickers), step=1),
                            "品种代码": st.column_config.TextColumn("品种代码", disabled=True),
                            "品种名称": st.column_config.TextColumn("品种名称", disabled=True),
                        },
                        use_container_width=True,
                        key="starred_order_editor_df",
                        hide_index=False,
                    )
                    if st.button("💾 保存最新卡片顺序", key="save_starred_cards_order_btn", type="primary", use_container_width=True):
                        try:
                            sorted_stk_df = edited_stk_df.sort_values("排序")
                            new_starred_order = sorted_stk_df["品种代码"].tolist()
                            storage.save_starred_tickers(new_starred_order)
                            st.success("✅ 重点关注卡片顺序已更新！")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as ex:
                            st.error(f"保存排序失败: {ex}")

                # 聚合每个重点品种的最新一条告警记录
                starred_cards_html = []
                starred_cards_html.append("<style>")
                starred_cards_html.append(".starred-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin-bottom: 5px; }")
                starred_cards_html.append(".starred-card { background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px 12px; transition: all 0.2s ease; cursor: grab; user-select: none; position: relative; }")
                starred_cards_html.append(".starred-card:hover { border-color: rgba(245, 158, 11, 0.6); background: rgba(245, 158, 11, 0.14); transform: translateY(-1px); }")
                starred_cards_html.append(".starred-card.dragging { opacity: 0.35; border: 2px dashed #fbbf24 !important; background: rgba(245, 158, 11, 0.2) !important; cursor: grabbing; }")
                starred_cards_html.append(".starred-card.drag-over { border: 2px solid #38bdf8 !important; background: rgba(56, 189, 248, 0.15) !important; }")
                starred_cards_html.append(".starred-title { font-weight: 700; font-size: 13px; color: #fbbf24; display: flex; justify-content: space-between; align-items: center; }")
                starred_cards_html.append(".starred-sub { font-size: 11px; color: #cbd5e1; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }")
                starred_cards_html.append(".starred-alert { font-size: 11px; margin-top: 6px; padding-top: 6px; border-top: 1px dashed rgba(245, 158, 11, 0.2); }")
                starred_cards_html.append(".filter-btn-mini { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 4px; padding: 1px 5px; font-size: 10px; text-decoration: none !important; font-weight: normal; cursor: pointer; transition: all 0.2s; }")
                starred_cards_html.append(".filter-btn-mini:hover { background: rgba(56, 189, 248, 0.3); color: #7dd3fc; }")
                starred_cards_html.append("</style>")
                starred_cards_html.append("<div class='starred-grid' id='starred_cards_grid'>")

                t_token = st.query_params.get("_t", "")
                curr_page = st.query_params.get("_page", "alert_logs")
                from assets import tv_url

                for stk in starred_tickers:
                    stk_u = stk.upper()
                    stk_name = symbol_name_map.get(stk_u) or stk_u
                    
                    sub_df = df[df["ticker"].str.upper() == stk_u]
                    if not sub_df.empty:
                        latest_row = sub_df.iloc[0]
                        l_time = str(latest_row.get("time", ""))
                        if len(l_time) > 16:
                            l_time = l_time[:16]
                        l_tf = str(latest_row.get("timeframe", ""))
                        l_lbl = str(latest_row.get("label", "") or "").strip()
                        
                        if "空头" in l_lbl or "跌" in l_lbl:
                            dir_tag = f"<span style='color:#f87171;'>🔻 {l_lbl or '下跌'}</span>"
                        elif "多头" in l_lbl or "突破" in l_lbl or "黄金区" in l_lbl:
                            dir_tag = f"<span style='color:#4ade80;'>🚀 {l_lbl or '上涨'}</span>"
                        elif l_lbl:
                            dir_tag = f"<span style='color:#38bdf8;'>{l_lbl}</span>"
                        else:
                            dir_tag = "<span style='color:#94a3b8;'>有告警</span>"

                        alert_str = f"⏰ {l_time} [{l_tf}] · {dir_tag}"
                    else:
                        alert_str = "<span style='color:#64748b;'>暂无近期告警</span>"
                        l_tf = "15m"

                    filter_href = f"/?_page={curr_page}&_t={t_token}&_search={stk_u}"
                    tv_href = tv_url(stk_u, l_tf if l_tf else "15m")

                    card = (
                        f"<div class='starred-card' draggable='true' data-ticker='{stk_u}' "
                        f"title=\"拖动卡片调整排序或点击进入详情\">"
                        f"<div class='starred-title'>"
                        f"<span>⭐ <a href='/?_page=ticker&_ticker={stk_u}&_t={t_token}' target='_parent' style='color:#fbbf24;text-decoration:none;' title='进入品种详情页'>{stk_u}</a></span>"
                        f"<div style='display:flex;gap:4px;align-items:center;'>"
                        f"<a href='{tv_href}' target='_blank' class='filter-btn-mini' style='background:rgba(30,144,255,0.15);color:#38bdf8;border-color:rgba(30,144,255,0.3);' title='打开 TradingView 图表'>📈 图表</a>"
                        f"<a href='{filter_href}' target='_top' class='filter-btn-mini' title='快速筛选此品种告警'>🔍 筛选</a>"
                        f"</div>"
                        f"</div>"
                        f"<div class='starred-sub'>{stk_name}</div>"
                        f"<div class='starred-alert'>{alert_str}</div>"
                        f"</div>"
                    )
                    starred_cards_html.append(card)

                starred_cards_html.append("</div>")

                # JS 脚本：直接在主网页 DOM 中绑定拖拽事件，并通过 URL 参数回写
                starred_cards_html.append(
                    "<img src='x' onerror=\""
                    "(function() {"
                    "  var doc = window.parent.document || document;"
                    "  var grid = doc.getElementById('starred_cards_grid');"
                    "  if (!grid || grid._drag_inited) return;"
                    "  grid._drag_inited = true;"
                    "  var dragItem = null;"
                    "  grid.addEventListener('dragstart', function(e) {"
                    "    var item = e.target.closest('.starred-card');"
                    "    if (!item) return;"
                    "    dragItem = item;"
                    "    item.classList.add('dragging');"
                    "    e.dataTransfer.effectAllowed = 'move';"
                    "  });"
                    "  grid.addEventListener('dragover', function(e) {"
                    "    e.preventDefault();"
                    "    var over = e.target.closest('.starred-card');"
                    "    if (over && over !== dragItem) {"
                    "      grid.querySelectorAll('.starred-card').forEach(function(c) { c.classList.remove('drag-over'); });"
                    "      over.classList.add('drag-over');"
                    "      var rect = over.getBoundingClientRect();"
                    "      if (e.clientX < rect.left + rect.width / 2) { grid.insertBefore(dragItem, over); }"
                    "      else { grid.insertBefore(dragItem, over.nextSibling); }"
                    "    }"
                    "  });"
                    "  grid.addEventListener('dragend', function(e) {"
                    "    grid.querySelectorAll('.starred-card').forEach(function(c) { c.classList.remove('dragging', 'drag-over'); });"
                    "    if (!dragItem) return;"
                    "    dragItem = null;"
                    "    var cards = grid.querySelectorAll('.starred-card[data-ticker]');"
                    "    var orderList = [];"
                    "    cards.forEach(function(c) {"
                    "      var tk = c.getAttribute('data-ticker');"
                    "      if (tk) orderList.push(tk);"
                    "    });"
                    "    if (orderList.length > 0) {"
                    "      var newOrderStr = orderList.join(',');"
                    "      var t = new URLSearchParams(window.parent.location.search).get('_t') || '';"
                    "      var targetUrl = '/?_page=alert_logs&_t=' + t + '&_reorder=' + encodeURIComponent(newOrderStr);"
                    "      window.parent.location.href = targetUrl;"
                    "    }"
                    "  });"
                    "})();"
                    "\" style='display:none;'>"
                )

                st.markdown("".join(starred_cards_html), unsafe_allow_html=True)
            
        # ── 筛选器面板 ────────────────────────────────────────────────
        with st.expander("🔍 筛选与自定义显示列", expanded=True):
            f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns([2, 2, 2, 2, 2])
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
                default_search = st.query_params.get("_search", "")
                search_q = st.text_input(
                    "🏷️ 代码 / 品种名",
                    value=default_search,
                    placeholder="输入搜索关键字...",
                    help="不区分大小写，搜索代码或资产名称",
                    key=f"alert_log_search_{'full' if full_page else 'tab'}"
                )
            with f_col3:
                scanner_opt = st.selectbox(
                    "🔍 扫描器与方向",
                    options=["全部", "🚀 上涨 (多头)", "🔻 下跌 (空头)", "Fibonacci 扫描", "EMA + Daily Pivot", "Chartink 4H", "其他"],
                    help="根据触发告警的类型或方向进行筛选",
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
            with f_col5:
                starred_opt = st.selectbox(
                    "⭐ 重点关注",
                    options=["全部品种", "仅重点关注", "仅非重点关注"],
                    help="筛选已标记重点关注的品种告警",
                    key=f"alert_log_starred_{'full' if full_page else 'tab'}"
                )

            # 所有可选的列表字段映射 (key -> 中文名 & 默认显示)
            ALL_COLS_MAP = [
                ("time", "时间", True),
                ("ticker", "代码", True),
                ("name", "名称", True),
                ("scanner_name", "扫描器", True),
                ("label_display", "信号类型", True),
                ("timeframe", "周期", True),
                ("tradingview", "行情链接", True),
                ("clicks", "点击统计", True),
                ("channel", "通知通道", False),  # 默认隐藏
                ("status", "发送状态", True),
                ("message", "返回消息", False), # 默认隐藏
            ]
            col_label_to_key = {label: k for k, label, _ in ALL_COLS_MAP}
            default_selected_labels = [label for _, label, is_def in ALL_COLS_MAP if is_def]

            selected_col_labels = st.multiselect(
                "⚙️ 选择并调整列的显示顺序（选项顺序即表格从左到右显示顺序）：",
                options=[label for _, label, _ in ALL_COLS_MAP],
                default=default_selected_labels,
                help="可勾选/取消勾选任意列，并按需选定其排列顺序",
                key=f"alert_log_cols_{'full' if full_page else 'tab'}"
            )
            selected_col_keys = [col_label_to_key[lbl] for lbl in selected_col_labels if lbl in col_label_to_key]

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
            
        # 3. 扫描器 / 方向筛选
        if scanner_opt == "🚀 上涨 (多头)":
            df = df[df.apply(lambda r: "空头" not in str(r.get("label", "")) and "跌" not in str(r.get("label", "")), axis=1)]
        elif scanner_opt == "🔻 下跌 (空头)":
            df = df[df.apply(lambda r: "空头" in str(r.get("label", "")) or "跌" in str(r.get("label", "")), axis=1)]
        elif scanner_opt == "Fibonacci 扫描":
            df = df[df["scanner"] == "fibo"]
        elif scanner_opt == "EMA + Daily Pivot":
            df = df[df["scanner"] == "ema_pivot"]
        elif scanner_opt == "Chartink 4H":
            df = df[df["scanner"] == "chartink"]
        elif scanner_opt == "其他":
            df = df[~df["scanner"].isin(["fibo", "ema_pivot", "chartink"])]
            
        # 4. 时间框架筛选
        if timeframe_opt:
            df = df[df["timeframe"].isin(timeframe_opt)]
            
        # 5. 重点关注筛选
        if starred_opt == "仅重点关注":
            df = df[df["ticker"].str.upper().isin(starred_set)]
        elif starred_opt == "仅非重点关注":
            df = df[~df["ticker"].str.upper().isin(starred_set)]
            
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
            
        # 自动监测新日志以触发 toast 提示
        total_logs = storage.load_alert_log(limit=0)
        current_total_count = len(total_logs)
        count_state_key = f"alert_log_prev_count_{'full' if full_page else 'tab'}"
        if count_state_key in st.session_state:
            prev_count = st.session_state[count_state_key]
            if current_total_count > prev_count:
                st.toast(f"🔔 检测到 {current_total_count - prev_count} 条新的告警日志已生成！", icon="🔔")
        st.session_state[count_state_key] = current_total_count

        # ── 操作工具栏（置于指标下方，日志上方） ──────────────────────────────
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1.5, 2, 1.5, 3])
        with col_btn1:
            if st.button("🔄 刷新日志", key=f"alert_log_refresh_top_{'full' if full_page else 'tab'}", use_container_width=True):
                st.rerun()
        with col_btn2:
            auto_refresh = st.checkbox("⏱️ 开启自动检测刷新 (30s)", 
                                       value=True, 
                                       key=f"alert_log_auto_refresh_chk_{'full' if full_page else 'tab'}",
                                       help="每30秒自动检测并刷新最新的告警日志")
        with col_btn3:
            if st.button("🗑️ 清空日志", key=f"alert_log_clear_top_{'full' if full_page else 'tab'}", use_container_width=True):
                storage.clear_alert_log()
                st.success("已成功清空所有日志记录")
                st.rerun()
        with col_btn4:
            pass

        # 启用自动刷新
        if auto_refresh:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=30000, key=f"alert_log_autorefresh_runner_{'full' if full_page else 'tab'}")

        # ── 列表渲染 ─────────────────────────────────────────────────
        if df.empty:
            st.warning("⚠️ 没有找到符合筛选条件的告警记录")
        else:
            from assets import tv_url
            import urllib.parse
            
            # 转换扫描器标签
            def get_scanner_label(row):
                s = str(row.get("scanner", ""))
                lbl = str(row.get("label", ""))
                msg = str(row.get("message", ""))
                
                # 判断上涨/下跌
                if "空头" in lbl or "跌" in lbl or "空头" in msg or "跌" in msg:
                    dir_tag = " (下跌)"
                elif "多头" in lbl or "突破" in lbl or "黄金区" in lbl or "多头" in msg or "突破" in msg:
                    dir_tag = " (上涨)"
                else:
                    dir_tag = ""

                if s == "fibo":
                    return f"Fibonacci{dir_tag}"
                elif s == "ema_pivot":
                    return f"EMA + Daily Pivot{dir_tag}"
                elif s == "chartink":
                    return f"Chartink 4H{dir_tag}"
                elif s:
                    return f"{s}{dir_tag}"
                return "其他/历史记录"
                
            df["scanner_name"] = df.apply(get_scanner_label, axis=1)
            df["tradingview"] = df["ticker"].apply(lambda t: tv_url(t, "15m"))
            df["clicks"] = ""  # 占位列
            
            # 预加载全量点击数据
            all_clicks_data = storage.get_all_link_clicks()
            today_str_val = storage.get_today_str()

            # 💡 用 HTML 渲染美观、大字体的表格，支持悬停高亮和批次底色交替，自适应深浅色主题
            try:
                # 获取展示数据中所有唯一时间戳并排序
                unique_times = sorted(df["time"].dropna().unique())
                time_to_group = {t: idx for idx, t in enumerate(unique_times)}
                
                # 开始构建 HTML 结构
                html_parts = []
                html_parts.append("<style>")
                html_parts.append(".alert-log-container { max-height: 850px; overflow-y: auto; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; margin-top: 15px; margin-bottom: 20px; }")
                html_parts.append(".alert-log-table { width: 100%; border-collapse: collapse; font-family: inherit; font-size: 14px; }")
                html_parts.append(".alert-log-table th { background-color: rgba(128, 128, 128, 0.1); color: inherit; font-weight: 600; padding: 14px 16px; text-align: left; border-bottom: 2px solid rgba(128, 128, 128, 0.2); position: sticky; top: 0; z-index: 10; font-size: 13px; }")
                html_parts.append(".alert-log-table td { padding: 14px 16px; border-bottom: 1px solid rgba(128, 128, 128, 0.1); vertical-align: middle; }")
                html_parts.append(".alert-log-row-odd { background-color: rgba(30, 144, 255, 0.05); }")
                html_parts.append(".alert-log-row-even { background-color: transparent; }")
                html_parts.append(".alert-log-row-fail { background-color: rgba(239, 68, 68, 0.12) !important; }")
                html_parts.append(".alert-log-table tr:hover { background-color: rgba(128, 128, 128, 0.08) !important; }")
                html_parts.append(".badge-success { background-color: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 12px; display: inline-block; border: 1px solid rgba(34, 197, 94, 0.3); }")
                html_parts.append(".badge-danger { background-color: rgba(239, 68, 68, 0.15); color: #f87171; padding: 4px 8px; border-radius: 4px; font-weight: 500; font-size: 12px; display: inline-block; border: 1px solid rgba(239, 68, 68, 0.3); }")
                html_parts.append(".tv-btn { display: inline-flex; align-items: center; background-color: rgba(30, 144, 255, 0.15); color: #38bdf8 !important; padding: 5px 10px; border-radius: 4px; text-decoration: none !important; font-size: 12px; font-weight: 500; transition: all 0.2s ease; border: 1px solid rgba(30, 144, 255, 0.3); }")
                html_parts.append(".tv-btn:hover { background-color: rgba(30, 144, 255, 0.3); color: #60a5fa !important; transform: translateY(-1px); }")
                html_parts.append(".sina-btn { display: inline-flex; align-items: center; background-color: rgba(255, 69, 0, 0.15); color: #ff6347 !important; padding: 5px 10px; border-radius: 4px; text-decoration: none !important; font-size: 12px; font-weight: 500; transition: all 0.2s ease; border: 1px solid rgba(255, 69, 0, 0.3); margin-left: 5px; }")
                html_parts.append(".sina-btn:hover { background-color: rgba(255, 69, 0, 0.3); color: #ff7f50 !important; transform: translateY(-1px); }")
                html_parts.append(".unfav-btn { display: inline-flex; align-items: center; background-color: rgba(239, 68, 68, 0.15); color: #f87171 !important; padding: 4px 8px; border-radius: 4px; text-decoration: none !important; font-size: 12px; font-weight: 500; transition: all 0.2s ease; border: 1px solid rgba(239, 68, 68, 0.3); margin-left: 5px; }")
                html_parts.append(".unfav-btn:hover { background-color: rgba(239, 68, 68, 0.3); color: #ef4444 !important; transform: translateY(-1px); }")
                html_parts.append(".fav-btn { display: inline-flex; align-items: center; background-color: rgba(34, 197, 94, 0.15); color: #4ade80 !important; padding: 4px 8px; border-radius: 4px; text-decoration: none !important; font-size: 12px; font-weight: 500; transition: all 0.2s ease; border: 1px solid rgba(34, 197, 94, 0.3); margin-left: 5px; }")
                html_parts.append(".fav-btn:hover { background-color: rgba(34, 197, 94, 0.3); color: #22c55e !important; transform: translateY(-1px); }")
                html_parts.append(".star-btn { text-decoration: none !important; font-size: 16px; margin-right: 6px; cursor: pointer; display: inline-block; transition: transform 0.2s ease; }")
                html_parts.append(".star-btn:hover { transform: scale(1.2); }")
                html_parts.append(".star-active { filter: none; opacity: 1; }")
                html_parts.append(".star-inactive { filter: grayscale(100%); opacity: 0.25; }")
                html_parts.append(".star-inactive:hover { filter: none; opacity: 0.8; }")
                html_parts.append(".alert-log-row-starred { background-color: rgba(245, 158, 11, 0.08) !important; font-weight: 500; }")
                html_parts.append(".click-count-badge { font-weight: 600; font-size: 12px; }")
                html_parts.append("</style>")
                html_parts.append("<div class=\"alert-log-container\">")
                html_parts.append("<table class=\"alert-log-table\">")
                
                # 预加载自选收藏列表
                watchlist_items = storage.load_watchlist()
                watchlist_tickers = {item.get("ticker", "").upper() for item in watchlist_items if isinstance(item, dict)}

                # 动态生成表头
                header_th_list = []
                for k in selected_col_keys:
                    lbl = next((l for key, l, _ in ALL_COLS_MAP if key == k), k)
                    if k == "clicks":
                        lbl = "📊 点击(今日/总)"
                    header_th_list.append(f"<th>{lbl}</th>")
                
                html_parts.append(f"<thead><tr>{''.join(header_th_list)}</tr></thead>")
                html_parts.append("<tbody>")
                
                t_token = st.query_params.get("_t", "")
                curr_page = st.query_params.get("_page", "alert_logs")
                
                # 预加载品种全称字典（从自定义品种库、自选库及线上新浪/yfinance实时API补全）
                from page_watchlist import _fetch_ticker_name
                custom_symbols = storage.load_symbols()
                symbol_name_map = {item["ticker"].upper(): item["name"] for item in custom_symbols if item.get("name")}
                for item in watchlist_items:
                    if item.get("name") and item.get("ticker"):
                        symbol_name_map[item["ticker"].upper()] = item["name"]

                for idx, row in df.iterrows():
                    status = row.get("status", "")
                    t_val = row.get("time", "")
                    ticker = row.get("ticker", "")
                    tk_upper = ticker.upper()
                    
                    # 若存储中尚无中文全称，由 Python 后端服务在渲染前直接调用 _fetch_ticker_name 实时查询填入
                    raw_name = symbol_name_map.get(tk_upper) or row.get("name", "")
                    if not raw_name or raw_name.strip().upper().replace(".", "") == tk_upper.replace(".", ""):
                        fetched_nm = _fetch_ticker_name(ticker)
                        if fetched_nm:
                            name = fetched_nm
                            symbol_name_map[tk_upper] = fetched_nm
                        else:
                            name = ticker
                    else:
                        name = raw_name
                    
                    is_starred = storage.is_ticker_starred(ticker)
                    is_in_watchlist = ticker.upper() in watchlist_tickers
                    
                    # 确定行样式类
                    row_class = ""
                    if status == "fail" or status == "失败":
                        row_class = 'class="alert-log-row-fail"'
                    elif is_starred:
                        row_class = 'class="alert-log-row-starred"'
                    else:
                        group_idx = time_to_group.get(t_val, 0)
                        if group_idx % 2 == 1:
                            row_class = 'class="alert-log-row-odd"'
                        else:
                            row_class = 'class="alert-log-row-even"'
                            
                    # 格式化状态徽标
                    if status == "fail" or status == "失败":
                        status_html = '<span class="badge-danger">❌ 失败</span>'
                    elif status == "ok" or status == "成功":
                        status_html = '<span class="badge-success">✅ 成功</span>'
                    else:
                        status_html = f'<span>{status}</span>'
                        
                    # 格式化 TradingView / 新浪 链接
                    tv_url_val = row.get("tradingview", "")
                    if tv_url_val:
                        tv_html = f'<a href="{tv_url_val}" target="_blank" class="tv-btn" data-ticker="{ticker}">📈 图表</a>'
                    else:
                        tv_html = "—"
                    
                    from assets import sina_url
                    sina_url_val = sina_url(ticker)
                    if sina_url_val:
                        tv_html += f'<a href="{sina_url_val}" target="_blank" class="sina-btn" data-ticker="{ticker}">🏦 新浪</a>'
                    
                    star_class = "star-active" if is_starred else "star-inactive"
                    star_href = f"/?_page={curr_page}&_t={t_token}&_toggle_star={ticker}"
                    star_html = f'<a href="{star_href}" target="_top" class="star-btn {star_class}" title="标记重点关注">⭐</a>'

                    import urllib.parse
                    encoded_name = urllib.parse.quote(name)
                    if is_in_watchlist:
                        fav_href = f"/?_page={curr_page}&_t={t_token}&_fav=del%7C{ticker}%7C{encoded_name}"
                        tv_html += f'<a href="{fav_href}" target="_top" class="unfav-btn" title="从自选表移除并取消重点关注">🗑️ 取消自选</a>'
                    else:
                        fav_href = f"/?_page={curr_page}&_t={t_token}&_fav=add%7C{ticker}%7C{encoded_name}"
                        tv_html += f'<a href="{fav_href}" target="_top" class="fav-btn" title="添加到自选表">➕ 加入自选</a>'

                    # 点击统计 HTML
                    click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
                    total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
                    by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
                    today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0
                    
                    if total_c > 0:
                        clicks_html = f'<span class="click-count-badge" style="color:#4ade80;">{today_c}</span> <span style="color:#94a3b8;font-size:11px;">/ {total_c}</span>'
                    else:
                        clicks_html = '<span style="color:#475569;">—</span>'
                    
                    code_html = f'{star_html}<a href="/?_page=ticker&_ticker={ticker}&_t={t_token}" target="_parent" style="color:#38bdf8; text-decoration:none; font-weight:bold;">{ticker}</a>'
                    name_html = f'<span class="name-text-wrap" style="display:inline-flex;align-items:center;gap:4px;"><a href="/?_page=ticker&_ticker={ticker}&_t={t_token}" target="_parent" style="color:inherit; text-decoration:none;">{name}</a><button class="edit-name-btn" data-ticker="{ticker}" data-name="{name}" title="修改品种名称" style="background:none;border:none;cursor:pointer;opacity:0.6;font-size:12px;padding:0 2px;transition:opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.6">✏️</button></span>'
                    
                    # 信号方向 badge 标签生成
                    raw_label = str(row.get("label", "") or "").strip()
                    if "空头" in raw_label or "跌" in raw_label:
                        label_html = f'<span style="background-color: rgba(239, 68, 68, 0.15); color: #f87171; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; border: 1px solid rgba(239, 68, 68, 0.3);">🔻 {raw_label or "空头破位"}</span>'
                    elif "多头" in raw_label or "突破" in raw_label or "黄金区" in raw_label:
                        label_html = f'<span style="background-color: rgba(34, 197, 94, 0.15); color: #4ade80; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; border: 1px solid rgba(34, 197, 94, 0.3);">🚀 {raw_label or "多头突破"}</span>'
                    elif raw_label:
                        label_html = f'<span style="background-color: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; border: 1px solid rgba(56, 189, 248, 0.3);">{raw_label}</span>'
                    else:
                        label_html = '<span style="color:#64748b;">—</span>'

                    # 动态拼接每行的 td
                    td_map = {
                        "time": f"<td>{t_val}</td>",
                        "ticker": f"<td>{code_html}</td>",
                        "name": f"<td>{name_html}</td>",
                        "scanner_name": f"<td>{row.get('scanner_name', '—')}</td>",
                        "label_display": f"<td>{label_html}</td>",
                        "timeframe": f"<td><code>{row.get('timeframe', '—')}</code></td>",
                        "tradingview": f"<td>{tv_html}</td>",
                        "clicks": f"<td>{clicks_html}</td>",
                        "channel": f"<td>{row.get('channel', '—')}</td>",
                        "status": f"<td>{status_html}</td>",
                        "message": f"<td>{row.get('message', '—')}</td>",
                    }
                    
                    row_tds = "".join([td_map[k] for k in selected_col_keys if k in td_map])
                    html_parts.append(f"<tr {row_class}>{row_tds}</tr>")
                
                html_parts.append("</tbody></table></div>")
                html_table = "".join(html_parts)
                st.markdown(html_table, unsafe_allow_html=True)

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
                                return;
                            }

                            // ✏️ 修改名称按钮：直接获取 Python 后端预先解析出的品种全称并弹出 Prompt
                            var editBtn = e.target.closest('.edit-name-btn');
                            if (editBtn) {
                                e.preventDefault();
                                e.stopPropagation();
                                var tk = editBtn.getAttribute('data-ticker');
                                var curName = editBtn.getAttribute('data-name') || tk;
                                var newName = prompt('✏️ 请输入 [' + tk + '] 的新名称：', curName);
                                if (newName !== null) {
                                    newName = newName.trim();
                                    if (newName && newName !== curName) {
                                        var targetUrl = '/?_page=alert_logs&_t=' + Date.now() + '&_rename=' + encodeURIComponent(tk + '|' + newName);
                                        try {
                                            window.top.location.href = targetUrl;
                                        } catch(err) {
                                            window.location.href = targetUrl;
                                        }
                                    }
                                }
                                return;
                            }

                            // ⭐/🗑️/➕ 按钮：统一在父页面上下文进行 URL 导航重定向
                            var actionBtn = e.target.closest('.star-btn, .unfav-btn, .fav-btn');
                            if (actionBtn) {
                                var href = actionBtn.getAttribute('href');
                                if (href) {
                                    e.preventDefault();
                                    e.stopPropagation();

                                    try {
                                        window.top.location.href = href;
                                    } catch(err) {
                                        window.location.href = href;
                                    }
                                }
                                return;
                            }
                        };
                        pDoc.addEventListener('click', pDoc._tv_click_handler, true);
                    } catch(err) {}
                })();
                </script>
                """, height=0)
            except Exception as e:
                st.dataframe(df, use_container_width=True, height=850)


def render_log_page():
    st.markdown("## 📋 告警日志")
    render_alert_log_table(full_page=True)


