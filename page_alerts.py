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
                save_tg = st.form_submit_button("💾 保存", use_container_width=True)
            with col2:
                test_tg = st.form_submit_button("🧪 测试发送", use_container_width=True)

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

    # ── 冷却设置（全局）──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ⏱️ 告警冷却设置")
    with st.form("cooldown_form"):
        cd = st.slider("冷却时间（分钟）",
                       min_value=30, max_value=1440,
                       value=int(cfg.get("alert_cooldown", 240)),
                       step=30,
                       help="同一资产同一框架两次告警之间的最短间隔")
        if st.form_submit_button("💾 保存冷却设置", use_container_width=True):
            storage.save_config({"alert_cooldown": cd})
            st.success(f"✅ 冷却时间已设为 {cd} 分钟")

    # ── 告警日志 ─────────────────────────────────────────────────────
    with tab3:
        st.markdown("#### 最近告警记录")
        logs = storage.load_alert_log(limit=100)
        if not logs:
            st.info("暂无告警记录")
        else:
            df = pd.DataFrame(logs)
            show_cols = ["time","ticker","name","timeframe","channel","status","message"]
            show_df   = df[[c for c in show_cols if c in df.columns]]
            st.dataframe(show_df, use_container_width=True, height=400)
            col1, col2 = st.columns([1,3])
            with col1:
                if st.button("🗑️ 清空日志", use_container_width=True):
                    storage.clear_alert_log()
                    st.success("已清空")
                    st.rerun()
