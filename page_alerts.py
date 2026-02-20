"""pages/page_alerts.py — 告警配置页面"""

import streamlit as st
from core.supabase_client import load_config, save_config, get_alert_log
from core.alerts import send_dingtalk, send_telegram, build_message


def render():
    st.markdown("## 🔔 告警配置")
    st.markdown("进入 Fibonacci 黄金区间时，自动推送实时通知到钉钉或 Telegram。")

    cfg = load_config()

    tab1, tab2, tab3 = st.tabs(["🔔 钉钉告警", "📱 Telegram", "📋 告警日志"])

    # ══════════════════════════════════════════════
    with tab1:
        st.markdown("### 钉钉机器人配置")

        st.markdown("""
        <div class="notice-info">
        <b>获取步骤：</b><br>
        ① 进入钉钉群 → 群设置 → 智能群助手 → 添加机器人 → 选「自定义」<br>
        ② 安全设置选「<b>加签</b>」，复制 Webhook URL 和 Secret 填入下方<br>
        ③ 机器人关键词配置中添加「STRX」或「Fibo」（否则消息会被拒绝）
        </div>
        """, unsafe_allow_html=True)

        dt_enabled = st.toggle("启用钉钉告警", value=bool(cfg.get("dingtalk_enabled")))
        dt_webhook = st.text_input(
            "Webhook URL",
            value=cfg.get("dingtalk_webhook", ""),
            placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            type="password",
        )
        dt_secret = st.text_input(
            "加签 Secret（如选了加签安全方式则必填）",
            value=cfg.get("dingtalk_secret", ""),
            placeholder="SEC...",
            type="password",
        )
        cooldown = st.number_input(
            "告警冷却时间（分钟）",
            min_value=5, max_value=1440,
            value=int(cfg.get("alert_cooldown", 240)),
            help="同一资产+时间框架冷却期内不重复推送，防止刷屏",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存钉钉配置", type="primary", use_container_width=True):
                ok = save_config({
                    "dingtalk_enabled": dt_enabled,
                    "dingtalk_webhook": dt_webhook,
                    "dingtalk_secret":  dt_secret,
                    "alert_cooldown":   cooldown,
                })
                if ok:
                    st.success("✅ 配置已保存到 Supabase")
                else:
                    st.error("❌ 保存失败，请检查 Supabase 连接")

        with col2:
            if st.button("📤 发送测试消息", use_container_width=True):
                test_cfg = {
                    "dingtalk_webhook": dt_webhook,
                    "dingtalk_secret":  dt_secret,
                }
                test_text = (
                    "📐 STRX Fibo Scanner — 测试消息\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "✅ 钉钉告警配置成功！\n"
                    "🔥 当出现 Fibonacci 黄金区间信号时将自动推送"
                )
                ok, msg = send_dingtalk(test_text, test_cfg)
                if ok:
                    st.success("✅ 测试消息发送成功！请查看钉钉群")
                else:
                    st.error(f"❌ 发送失败：{msg}")

        st.markdown("---")
        st.markdown("**推送消息预览：**")
        st.code(
            "📐 STRX Fibo 信号  🔥🔥🔥 三框架共振\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🏷  Gold Futures (GC=F)\n"
            "📅 时间框架: Daily\n"
            "💰 当前价格: 2,345.2000\n"
            "📏 黄金区间: 2,301.4400 – 2,360.1000\n"
            "📉 回撤深度: 52.1%\n"
            "🔗 https://www.tradingview.com/chart/?symbol=COMEX:GC1!\n"
            "🕐 2026-02-19 09:00",
            language="text"
        )

    # ══════════════════════════════════════════════
    with tab2:
        st.markdown("### Telegram Bot 配置")

        st.markdown("""
        <div class="notice-info">
        <b>获取步骤：</b><br>
        ① 在 Telegram 搜索 <b>@BotFather</b> → 发送 /newbot → 按提示创建，获得 Bot Token<br>
        ② 和你的机器人发一条消息，然后访问：<br>
        &nbsp;&nbsp;&nbsp;<code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code><br>
        ③ 在返回 JSON 中找到 <code>result[0].message.chat.id</code> 字段
        </div>
        """, unsafe_allow_html=True)

        tg_enabled = st.toggle("启用 Telegram 告警", value=bool(cfg.get("telegram_enabled")))
        tg_token = st.text_input(
            "Bot Token",
            value=cfg.get("telegram_token", ""),
            placeholder="1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
            type="password",
        )
        tg_chat = st.text_input(
            "Chat ID",
            value=cfg.get("telegram_chat_id", ""),
            placeholder="个人为正数，群组为负数，如 -1001234567890",
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存 Telegram 配置", type="primary", use_container_width=True):
                ok = save_config({
                    "telegram_enabled":  tg_enabled,
                    "telegram_token":    tg_token,
                    "telegram_chat_id":  tg_chat,
                })
                if ok:
                    st.success("✅ 配置已保存到 Supabase")
                else:
                    st.error("❌ 保存失败")

        with col2:
            if st.button("📤 发送测试消息 ", use_container_width=True):
                test_cfg = {"telegram_token": tg_token, "telegram_chat_id": tg_chat}
                ok, msg = send_telegram(
                    "📐 STRX Fibo Scanner — 测试消息\n✅ Telegram 告警配置成功！",
                    test_cfg
                )
                if ok:
                    st.success("✅ 测试消息发送成功！请查看 Telegram")
                else:
                    st.error(f"❌ 发送失败：{msg}")

    # ══════════════════════════════════════════════
    with tab3:
        st.markdown("### 📋 最近 100 条告警记录")

        if st.button("🔄 刷新日志"):
            st.rerun()

        logs = get_alert_log(100)
        if not logs:
            st.info("暂无告警记录")
        else:
            import pandas as pd
            df = pd.DataFrame(logs)
            df["alert_time"] = pd.to_datetime(df["alert_time"]).dt.strftime("%Y-%m-%d %H:%M:%S")

            # 颜色标记 status
            def style_status(val):
                if val == "ok":
                    return "color: #15803d; font-weight: bold"
                return "color: #dc2626; font-weight: bold"

            show_cols = ["alert_time","ticker","name","timeframe","channel","status","message"]
            show_cols = [c for c in show_cols if c in df.columns]
            df_show   = df[show_cols].rename(columns={
                "alert_time":"时间","ticker":"Ticker","name":"名称",
                "timeframe":"框架","channel":"渠道","status":"状态","message":"详情"
            })

            st.dataframe(df_show, use_container_width=True, height=450)
