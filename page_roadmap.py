"""pages/page_roadmap.py — 功能路线图"""

import streamlit as st


ROADMAP = [
    {
        "phase": "Phase 1 · 近期可实现",
        "color": "#0d9488",
        "icon":  "🟢",
        "items": [
            {
                "title": "📊 更多 Fibonacci 层级告警",
                "desc":  "在黄金区间（0.5–0.618）之外，增加对 0.382、0.786、0.886 的单独触达告警，并支持用户自定义监控哪几个层级。",
                "effort": "低",
                "value":  "高",
            },
            {
                "title": "👤 自定义资产 Watchlist",
                "desc":  "在 Web 界面直接增删自选资产，输入 Ticker 即可加入监控，无需修改源代码。数据存储在 Supabase 的 watchlist 表。",
                "effort": "低",
                "value":  "高",
            },
            {
                "title": "📧 企业微信 / 飞书 告警渠道",
                "desc":  "复用现有告警框架，增加企业微信群机器人 Webhook 和飞书卡片消息推送。对国内团队使用更方便。",
                "effort": "低",
                "value":  "中",
            },
            {
                "title": "📅 扫描频率精细化",
                "desc":  "从「每日一次」升级到支持盘前、盘中、盘后多次扫描，每次结果独立存档，可对比同日内市场变化。",
                "effort": "低",
                "value":  "中",
            },
        ],
    },
    {
        "phase": "Phase 2 · 中期增强",
        "color": "#1d4ed8",
        "icon":  "🔵",
        "items": [
            {
                "title": "📈 价格走势图内嵌 Fibo 可视化",
                "desc":  "在 Streamlit 界面内嵌 Plotly K 线图，直接标注黄金区间、摆动高低点、回撤层级，无需跳转 TradingView。",
                "effort": "中",
                "value":  "极高",
            },
            {
                "title": "🔔 价格突破告警（Breakout Alert）",
                "desc":  "当价格突破摆动高点（0.0 位）或跌破摆动低点（1.0 位）时触发突破信号告警，补充区间内信号。",
                "effort": "中",
                "value":  "高",
            },
            {
                "title": "📊 历史回测 Backtest 模块",
                "desc":  "统计过去 N 次「进入黄金区间」事件后的价格表现（+1天/+1周/+1月涨跌幅），量化 Fibonacci 信号胜率。",
                "effort": "中",
                "value":  "极高",
            },
            {
                "title": "🌐 多语言界面",
                "desc":  "新增英文 / 繁体中文界面切换，面向国际用户。基于 Streamlit session_state 实现，无需重载。",
                "effort": "低",
                "value":  "中",
            },
            {
                "title": "📤 每日摘要报告（邮件 / 钉钉）",
                "desc":  "每次定时扫描后自动生成 HTML 摘要报告：当日信号汇总表 + 共振资产列表 + 与昨日对比，发送到邮件或钉钉。",
                "effort": "中",
                "value":  "高",
            },
        ],
    },
    {
        "phase": "Phase 3 · 高级功能",
        "color": "#7c3aed",
        "icon":  "🟣",
        "items": [
            {
                "title": "🤖 AI 市场评论生成",
                "desc":  "接入 Claude API，对每个进入黄金区间的信号自动生成 2–3 句市场背景分析，附在告警消息中或生成日报。",
                "effort": "中",
                "value":  "极高",
            },
            {
                "title": "📱 移动端 PWA 推送",
                "desc":  "将 Streamlit 应用封装为 PWA，支持浏览器原生推送通知，无需安装 App，手机锁屏状态可接收信号。",
                "effort": "高",
                "value":  "高",
            },
            {
                "title": "🔗 TradingView Webhook 接入",
                "desc":  "提供 Webhook 接收端点，让 TradingView Pine Script 告警直接推送到本系统，数据更精准，无延迟。",
                "effort": "中",
                "value":  "极高",
            },
            {
                "title": "📊 多用户 / 团队协作",
                "desc":  "接入 Supabase Auth 实现多用户登录，每人管理自己的 Watchlist 和告警配置，团队共享历史扫描记录。",
                "effort": "高",
                "value":  "高",
            },
            {
                "title": "🧮 自定义策略规则引擎",
                "desc":  "在 Web 界面拖拽配置策略规则（如：「日线 IN ZONE 且 RSI < 40」），组合多个技术指标过滤信号，减少噪音。",
                "effort": "极高",
                "value":  "极高",
            },
            {
                "title": "📡 期权链 / 隐含波动率整合",
                "desc":  "当资产进入黄金区间时，同步拉取期权链数据（如 AAPL 的 IV、Put/Call Ratio），辅助判断市场方向预期。",
                "effort": "高",
                "value":  "高",
            },
        ],
    },
]

EFFORT_COLOR = {"低": "#15803d", "中": "#b45309", "高": "#dc2626", "极高": "#7c3aed"}
VALUE_COLOR  = {"中": "#b45309", "高": "#0d9488", "极高": "#e85d04"}


def render():
    st.markdown("## 🚀 功能路线图 · Future Roadmap")
    st.markdown(
        "以下是基于当前架构（Streamlit + Supabase + APScheduler）可以持续扩展的功能清单，"
        "按实现难度和商业价值分三个阶段排列。"
    )

    # 总览
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="metric-card teal">
          <div class="metric-lbl">🟢 Phase 1 近期</div>
          <div class="metric-val" style="color:#0d9488">4</div>
          <div class="metric-sub">低成本 · 快速交付</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="metric-card" style="border-color:#bfdbfe;background:#eff6ff">
          <div class="metric-lbl">🔵 Phase 2 中期</div>
          <div class="metric-val" style="color:#1d4ed8">5</div>
          <div class="metric-sub">中等投入 · 高价值</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="metric-card" style="border-color:#ddd6fe;background:#f5f3ff">
          <div class="metric-lbl">🟣 Phase 3 高级</div>
          <div class="metric-val" style="color:#7c3aed">6</div>
          <div class="metric-sub">深度功能 · 差异化竞争力</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 每个阶段
    for phase in ROADMAP:
        color = phase["color"]
        icon  = phase["icon"]
        title = phase["phase"]
        st.markdown(
            f"<h3 style='color:{color}'>{icon} {title}</h3>",
            unsafe_allow_html=True
        )

        for item in phase["items"]:
            effort_c = EFFORT_COLOR.get(item["effort"], "#6b7280")
            value_c  = VALUE_COLOR.get(item["value"],   "#6b7280")

            with st.expander(item["title"]):
                st.markdown(item["desc"])
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f'<span style="font-size:12px;font-weight:700;color:{effort_c}">⚡ 开发难度：{item["effort"]}</span>',
                        unsafe_allow_html=True
                    )
                with col2:
                    st.markdown(
                        f'<span style="font-size:12px;font-weight:700;color:{value_c}">💎 业务价值：{item["value"]}</span>',
                        unsafe_allow_html=True
                    )

        st.markdown("---")

    # 技术依赖速查
    st.markdown("### 🛠️ 扩展所需技术依赖速查")
    st.markdown("""
    | 功能 | 新增依赖 | 说明 |
    |------|---------|------|
    | K线图可视化 | `plotly`, `mplfinance` | Plotly 更易嵌入 Streamlit |
    | 历史回测 | `pandas` (已有) | 利用现有 Supabase 历史数据 |
    | AI 评论生成 | `anthropic` SDK | Claude API，按 Token 计费 |
    | 多用户登录 | `supabase` Auth | Supabase 内置，免额外服务 |
    | TradingView Webhook | `fastapi` 或 Supabase Edge Function | 需独立接收端点 |
    | 期权数据 | `yfinance` (已有) `.option_chain()` | yfinance 内置支持 |
    | 企业微信 / 飞书 | `requests` (已有) | 纯 HTTP Webhook |
    | 邮件报告 | `smtplib` (内置) | 无需额外安装 |
    """)

    st.markdown("### 💡 开发建议优先级")
    st.markdown("""
    **如果你是个人交易者：** Phase 1 全部 → **历史回测** → **K线图可视化**

    **如果你要分享给团队：** Phase 1 全部 → **每日摘要报告** → **多用户登录** → **自定义 Watchlist**

    **如果你要做成商业产品：** Phase 1 全部 → **TradingView Webhook 接入** → **AI 评论生成** → **策略规则引擎**
    """)
