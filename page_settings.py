"""pages/page_settings.py — 系统设置"""

import streamlit as st
from core.supabase_client import (
    load_config, save_config, supabase_ok, SUPABASE_DDL
)


def render():
    st.markdown("## ⚙️ 系统设置")

    cfg = load_config()

    tab1, tab2, tab3 = st.tabs(["📐 Fibonacci 参数", "📡 数据源", "🗄️ Supabase 连接"])

    # ══════════════════════════════════════════
    with tab1:
        st.markdown("### Fibonacci 扫描参数")
        st.markdown("""
        <div class="notice-info">
        📐 Pine Script 对应公式：<code>fp(r) = swingHigh - r × (swingHigh - swingLow)</code><br>
        黄金区间：<code>fp(0.618) ≤ price ≤ fp(0.500)</code>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            lookback = st.number_input(
                "回望期 Lookback（K线数）",
                min_value=10, max_value=500,
                value=int(cfg.get("lookback", 100)),
                help="用于确定摆动高低点的 K 线数量，对应 Pine Script 的 ta.highest/ta.lowest",
            )
            fibo_low = st.number_input(
                "黄金区间上沿（Fibo 0.500）",
                min_value=0.1, max_value=0.99, step=0.001,
                value=float(cfg.get("fibo_low", 0.500)),
                format="%.3f",
            )
        with col2:
            fibo_high = st.number_input(
                "黄金区间下沿（Fibo 0.618）",
                min_value=0.1, max_value=0.99, step=0.001,
                value=float(cfg.get("fibo_high", 0.618)),
                format="%.3f",
            )
            watch_pct = st.number_input(
                "接近区间阈值（%）",
                min_value=0.5, max_value=20.0, step=0.5,
                value=float(cfg.get("watch_pct", 5.0)),
                help="价格距区间小于此值标记为「👀 接近」",
            )

        if st.button("💾 保存 Fibo 参数", type="primary"):
            ok = save_config({
                "lookback":  lookback,
                "fibo_low":  fibo_low,
                "fibo_high": fibo_high,
                "watch_pct": watch_pct,
            })
            st.success("✅ 参数已保存" if ok else "❌ 保存失败")

    # ══════════════════════════════════════════
    with tab2:
        st.markdown("### 市场数据源")

        source = st.selectbox(
            "当前数据源",
            ["yfinance", "twelvedata"],
            index=0 if cfg.get("data_source","yfinance") == "yfinance" else 1,
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **Yahoo Finance (yfinance)** ✅ 推荐
            - 完全免费，无需注册
            - 支持全球股票 / 期货 / 外汇 / 加密
            - 日 / 周 / 月线多年历史数据
            - ⚠️ 非官方 API，价格约 15 分钟延迟
            """)
        with col2:
            st.markdown("""
            **Twelve Data** 🔑 需要 API Key
            - 免费 800 次/天，8 次/分钟
            - 支持美股 / 港股 / 外汇 / 加密 / ETF
            - ⚠️ A 股数据需付费计划
            - [获取免费 Key →](https://twelvedata.com/pricing)
            """)

        td_key = ""
        if source == "twelvedata":
            td_key = st.text_input(
                "Twelve Data API Key",
                value=cfg.get("twelvedata_key", ""),
                type="password",
                placeholder="粘贴你的免费 API Key",
            )

        if st.button("💾 保存数据源配置", type="primary"):
            ok = save_config({
                "data_source":    source,
                "twelvedata_key": td_key,
            })
            st.success("✅ 已保存" if ok else "❌ 保存失败")

    # ══════════════════════════════════════════
    with tab3:
        st.markdown("### Supabase 数据库连接")

        ok, msg = supabase_ok()
        if ok:
            st.markdown('<div class="notice-ok">✅ Supabase 连接正常</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="notice-warn">⚠️ 连接失败：{msg}</div>',
                        unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 配置方式")

        tab_a, tab_b = st.tabs(["本地开发（secrets.toml）", "Streamlit Cloud（Secrets）"])

        with tab_a:
            st.markdown("在项目根目录创建 `.streamlit/secrets.toml`：")
            st.code("""
[supabase]
url = "https://xxxxxxxxxxxx.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
""", language="toml")
            st.markdown("""
            ⚠️ **重要：** 将 `.streamlit/secrets.toml` 加入 `.gitignore`，不要提交到 GitHub！
            """)

        with tab_b:
            st.markdown("""
            1. 打开 [share.streamlit.io](https://share.streamlit.io) → 选择你的应用
            2. 点击右上角 **Settings** → **Secrets**
            3. 粘贴以下内容（填入你的真实值）：
            """)
            st.code("""
[supabase]
url = "https://xxxxxxxxxxxx.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
""", language="toml")

        st.divider()
        st.markdown("#### 🗄️ 数据库初始化 SQL")
        st.markdown("""
        **首次使用时，在 Supabase Dashboard → SQL Editor 执行以下 DDL：**
        """)
        st.code(SUPABASE_DDL, language="sql")

        st.markdown("#### 📍 如何获取 Supabase 连接信息")
        st.markdown("""
        1. 登录 [supabase.com](https://supabase.com) → 新建项目（免费 Free tier 足够）
        2. 进入项目 → **Settings** → **API**
        3. 复制：
           - **Project URL**（即 `url`）
           - **anon public** key（即 `key`）— 不要用 service_role key
        """)
