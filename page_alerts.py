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
            filter_4h = st.checkbox("🚀 EMA + Pivot 告警: 当前价格必须在 4小时 20-MA 均线之上",
                                    value=bool(cfg.get("filter_4h_ema20", False)),
                                    help="开启后，在进行 EMA20 + Daily Pivot 扫描时，当前价格必须运行在4小时周期的 20 EMA均线之上，否则进行过滤不触发告警。")
            
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
            
        # ── 筛选器面板 ────────────────────────────────────────────────
        with st.expander("🔍 筛选与自定义显示列", expanded=True):
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

            # 所有可选的列表字段映射 (key -> 中文名 & 默认显示)
            ALL_COLS_MAP = [
                ("time", "时间", True),
                ("ticker", "代码", True),
                ("name", "名称", True),
                ("scanner_name", "扫描器", True),
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
            def get_scanner_label(s):
                if s == "fibo":
                    return "Fibonacci"
                elif s == "ema_pivot":
                    return "EMA + Daily Pivot"
                return "其他/历史记录"
                
            df["scanner_name"] = df["scanner"].apply(get_scanner_label)
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
                
                for idx, row in df.iterrows():
                    status = row.get("status", "")
                    t_val = row.get("time", "")
                    ticker = row.get("ticker", "")
                    name = row.get("name", "")
                    
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
                    star_html = f'<a href="/?_page={curr_page}&_t={t_token}&_toggle_star={ticker}" target="_parent" class="star-btn {star_class}" title="标记重点关注">⭐</a>'

                    import urllib.parse
                    encoded_name = urllib.parse.quote(name)
                    if is_in_watchlist:
                        tv_html += f'<a href="/?_page={curr_page}&_t={t_token}&_fav=del%7C{ticker}%7C{encoded_name}" target="_parent" class="unfav-btn" title="从自选表移除并取消重点关注">🗑️ 取消自选</a>'
                    else:
                        tv_html += f'<a href="/?_page={curr_page}&_t={t_token}&_fav=add%7C{ticker}%7C{encoded_name}" target="_parent" class="fav-btn" title="添加到自选表">➕ 加入自选</a>'

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
                    name_html = f'<a href="/?_page=ticker&_ticker={ticker}&_t={t_token}" target="_parent" style="color:inherit; text-decoration:none;">{name}</a>'
                    
                    # 动态拼接每行的 td
                    td_map = {
                        "time": f"<td>{t_val}</td>",
                        "ticker": f"<td>{code_html}</td>",
                        "name": f"<td>{name_html}</td>",
                        "scanner_name": f"<td>{row.get('scanner_name', '—')}</td>",
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

                            // 处理⭐重点关注 / 🗑️取消自选 / ➕加入自选 按钮在 Streamlit 沙盒下的即时反馈与后台静音发送
                            var actionBtn = e.target.closest('.star-btn, .unfav-btn, .fav-btn');
                            if (actionBtn) {
                                var href = actionBtn.getAttribute('href');
                                if (href) {
                                    e.preventDefault();
                                    e.stopPropagation();

                                    // 1. 静音向 Streamlit 后端发送操作指令 URL (确保路径有效)
                                    var requestUrl = href + (href.indexOf('?') >= 0 ? '&' : '?') + '_cb=' + Date.now();
                                    try { fetch(requestUrl, { method: 'GET', cache: 'no-store', credentials: 'omit' }); } catch(err) {}
                                    try { if (navigator.sendBeacon) { navigator.sendBeacon(requestUrl); } } catch(err) {}

                                    // 2. 尝试全窗口导航，若浏览器沙盒拦截则进行秒级 DOM 界面实时联动反转
                                    var navigated = false;
                                    try {
                                        if (window.top && window.top.location) {
                                            window.top.location.href = href;
                                            navigated = true;
                                        }
                                    } catch(err) {}

                                    if (!navigated) {
                                        try {
                                            if (window.parent && window.parent.location) {
                                                window.parent.location.href = href;
                                                navigated = true;
                                            }
                                        } catch(err) {}
                                    }

                                    // 3. 沙盒环境下的秒级 DOM 前台反馈
                                    try {
                                        var tr = actionBtn.closest('tr');
                                        if (actionBtn.classList.contains('unfav-btn')) {
                                            // 切换为加入自选
                                            actionBtn.className = 'fav-btn';
                                            actionBtn.innerHTML = '➕ 加入自选';
                                            actionBtn.title = '添加到自选表';
                                            // 原 href 中的 _fav=del 替换为 _fav=add
                                            actionBtn.setAttribute('href', href.replace('_fav=del', '_fav=add'));

                                            // 联动取消星标
                                            if (tr) {
                                                var starBtn = tr.querySelector('.star-btn');
                                                if (starBtn) {
                                                    starBtn.className = 'star-btn star-inactive';
                                                }
                                                tr.classList.remove('alert-log-row-starred');
                                            }
                                        } else if (actionBtn.classList.contains('fav-btn')) {
                                            // 切换为取消自选
                                            actionBtn.className = 'unfav-btn';
                                            actionBtn.innerHTML = '🗑️ 取消自选';
                                            actionBtn.title = '从自选表移除并取消重点关注';
                                            actionBtn.setAttribute('href', href.replace('_fav=add', '_fav=del'));
                                        } else if (actionBtn.classList.contains('star-btn')) {
                                            // ⭐ 按钮手动切星
                                            if (actionBtn.classList.contains('star-active')) {
                                                actionBtn.className = 'star-btn star-inactive';
                                                if (tr) tr.classList.remove('alert-log-row-starred');
                                            } else {
                                                actionBtn.className = 'star-btn star-active';
                                                if (tr) tr.classList.add('alert-log-row-starred');
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
            except Exception as e:
                st.dataframe(df, use_container_width=True, height=850)


def render_log_page():
    st.markdown("## 📋 告警日志")
    render_alert_log_table(full_page=True)


