"""
page_settings.py — 系统设置
"""
import streamlit as st

import storage


def render():
    st.markdown("## ⚙️ 系统设置")

    cfg = storage.load_config()

    tab1, tab2, tab3 = st.tabs(["📐 Fibonacci 参数", "📡 数据源", "💾 存储说明"])

    # ── Fibonacci 参数 ────────────────────────────────────────────────
    with tab1:
        st.markdown("#### Fibonacci 计算参数")
        st.markdown("""
        <div class="n-info">
        公式与 STRX Pine Script 完全对应：<br>
        <code>fp(r) = swingHigh − r × (swingHigh − swingLow)</code><br>
        黄金区间：<code>fp(0.618) ≤ 当前价格 ≤ fp(0.500)</code>
        </div>""", unsafe_allow_html=True)

        with st.form("fibo_form"):
            lookback = st.slider(
                "Lookback（回望K线数）",
                min_value=20, max_value=500,
                value=int(cfg.get("lookback", 100)),
                step=10,
                help="计算摆动高低点所用的K线数量，对应 Pine Script i_lookback"
            )
            col1, col2 = st.columns(2)
            with col1:
                fibo_low = st.number_input(
                    "黄金区上沿（Fibo 比例）",
                    min_value=0.1, max_value=0.9,
                    value=float(cfg.get("fibo_low", 0.5)),
                    step=0.001, format="%.3f",
                    help="默认 0.500（对应价格较高一端）"
                )
            with col2:
                fibo_high = st.number_input(
                    "黄金区下沿（Fibo 比例）",
                    min_value=0.1, max_value=0.99,
                    value=float(cfg.get("fibo_high", 0.618)),
                    step=0.001, format="%.3f",
                    help="默认 0.618（对应价格较低一端）"
                )
            watch_dist = st.slider(
                "「接近区间」判断阈值 (%)",
                min_value=1.0, max_value=20.0,
                value=float(cfg.get("watch_dist", 5.0)),
                step=0.5,
                help="价格距黄金区间的距离小于此值时，标记为「👀 接近」"
            )

            if st.form_submit_button("💾 保存 Fibonacci 参数", use_container_width=True):
                storage.save_config({
                    "lookback":    lookback,
                    "fibo_low":    fibo_low,
                    "fibo_high":   fibo_high,
                    "watch_dist":  watch_dist,
                })
                st.success("✅ 参数已保存，下次扫描生效")

        # 预览
        with st.expander("📊 当前 Fibo 参数预览"):
            import scanner as sc
            example_h, example_l = 100.0, 75.0
            rng = example_h - example_l
            fp  = lambda r: example_h - r * rng
            levels = [0.0,0.136,0.236,0.382,0.5,0.618,0.705,0.786,0.886,1.0]
            rows = [{"Fibo 比例": r, "价格示例 (H=100, L=75)": f"{fp(r):.2f}",
                     "说明": "🟠 结构高点" if r==0 else
                             "🟠 结构低点" if r==1 else
                             "✅ 黄金区上沿" if r==float(cfg.get("fibo_low",0.5)) else
                             "✅ 黄金区下沿" if r==float(cfg.get("fibo_high",0.618)) else ""}
                    for r in levels]
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── 数据源 ────────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### 数据源配置")

        with st.form("datasource_form"):
            data_src = st.radio(
                "选择数据源",
                options=["yfinance", "twelvedata"],
                index=0 if cfg.get("data_source","yfinance")=="yfinance" else 1,
                help="yfinance 免费无限制；Twelve Data 免费版 800次/天"
            )

            td_key = st.text_input(
                "Twelve Data API Key（仅选 Twelve Data 时需要）",
                value=cfg.get("twelvedata_key",""),
                type="password",
                placeholder="your_api_key_here"
            )

            if st.form_submit_button("💾 保存数据源", use_container_width=True):
                storage.save_config({
                    "data_source":    data_src,
                    "twelvedata_key": td_key,
                })
                st.success("✅ 数据源已保存")

        st.markdown("""
        | 数据源 | 费用 | 限制 | 覆盖 |
        |--------|------|------|------|
        | **yfinance** | 完全免费 | 无正式限制 | 全球股票/指数/期货/外汇/加密 |
        | **Twelve Data** | 免费 800次/天 | 每分钟有限 | 全球市场（覆盖更广） |

        > 💡 推荐先用 **yfinance**，稳定且免费。如需更高可靠性可切换 Twelve Data。
        """)

        if st.button("🔧 测试 yfinance 连接", use_container_width=False):
            with st.spinner("测试 AAPL 日线数据…"):
                df = sc_test()
            if df is not None:
                st.success(f"✅ yfinance 正常！获取 AAPL {len(df)} 条记录")
            else:
                st.error("❌ yfinance 获取失败，请检查网络")

    # ── 存储说明 ──────────────────────────────────────────────────────
    with tab3:
        st.markdown("#### 💾 存储架构说明")
        st.markdown("""
        <div class="n-info">
        当前使用 <b>JSON 本地文件存储</b>，适合 Streamlit Cloud 开发/演示阶段。
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        #### 数据文件

        | 文件 | 内容 | 大小限制 |
        |------|------|----------|
        | `data_config.json` | 系统配置（Fibo参数/告警设置） | ~5KB |
        | `data_history.json` | 扫描历史（最近30次） | ~2MB |
        | `data_alerts.json` | 告警日志（最近200条） | ~100KB |

        #### ⚠️ Streamlit Cloud 注意事项

        - **重启后数据重置**：Streamlit Cloud 容器重启时，本地文件会丢失
        - **适合演示**：当前架构足够用于功能验证和日常使用
        - **升级路径**：后期迁移到 Supabase 只需替换 `storage.py` 即可，其他代码不变

        #### 🔮 后期升级到 Supabase

        ```python
        # 只需在 storage.py 中替换以下函数实现：
        # - load_config() / save_config()
        # - save_scan() / load_sessions() / load_results()
        # - log_alert() / load_alert_log()
        # 其余所有页面代码完全不变
        ```
        """)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ 清空扫描历史", use_container_width=True):
                import os
                f = storage.F_HIST
                if os.path.exists(f):
                    os.remove(f)
                    st.success("✅ 扫描历史已清空")
                    st.rerun()
        with col2:
            if st.button("🔄 重置系统配置", use_container_width=True):
                storage.reset_config()
                st.success("✅ 配置已重置为默认值")
                st.rerun()


def sc_test():
    """测试 yfinance 连接"""
    try:
        import warnings
        import yfinance as yf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download("AAPL", interval="1d", period="1mo",
                             progress=False, auto_adjust=True)
        return df if not df.empty else None
    except Exception:
        return None


# 避免循环导入（settings 页内 import scanner 只用于测试）
try:
    import scanner as _sc_ref
except Exception:
    pass
