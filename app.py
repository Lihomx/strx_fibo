"""
╔══════════════════════════════════════════════════════════════════╗
║        STRX Automatic Fibo Scanner Pro                          ║
║        Streamlit + Supabase Production Edition                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Stack:  Streamlit (UI) · Supabase (PostgreSQL cloud DB)        ║
║          APScheduler (cron) · yfinance (market data)            ║
║          DingTalk / Telegram (alerts)                           ║
╚══════════════════════════════════════════════════════════════════╝

部署方式:
  本地:        streamlit run app.py
  Streamlit Cloud: 推送到 GitHub → 在 share.streamlit.io 部署
  Secrets:     在 .streamlit/secrets.toml 或 Streamlit Cloud Secrets 设置
"""

import streamlit as st

# ── 页面配置（必须是第一个 st 调用）─────────────────────────────
st.set_page_config(
    page_title="STRX Fibo Scanner Pro",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://www.tradingview.com",
        "Report a bug": None,
        "About": "STRX Automatic Fibo Scanner Pro — Streamlit + Supabase Edition",
    }
)

# ── 全局 CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── 基础字体与配色 ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Manrope:wght@500;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Manrope', sans-serif !important;
}

/* 顶部标题栏 */
.main-header {
    background: linear-gradient(135deg, #fff 0%, #fff7ed 100%);
    border: 1.5px solid #fed7aa;
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.logo-mark {
    background: #e85d04;
    color: white;
    width: 44px;
    height: 44px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 800;
    flex-shrink: 0;
}
.header-text h1 {
    font-size: 22px !important;
    font-weight: 800 !important;
    margin: 0 !important;
    color: #0f1923 !important;
}
.header-text p { margin: 2px 0 0; color: #6b7280; font-size: 12px; }
.orange { color: #e85d04; }

/* 指标卡 */
.metric-card {
    background: white;
    border: 1px solid #e2e6ea;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.metric-card.teal   { border-color: #99f6e4; background: #f0fdfa; }
.metric-card.gold   { border-color: #fde68a; background: #fffbeb; }
.metric-card.red    { border-color: #fecaca; background: #fef2f2; }
.metric-card.orange { border-color: #fed7aa; background: #fff7ed; }
.metric-val  { font-size: 32px; font-weight: 800; line-height: 1; margin: 4px 0; }
.metric-lbl  { font-size: 11px; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: .08em; }
.metric-sub  { font-size: 11px; color: #9ca3af; font-family: 'IBM Plex Mono', monospace; }

/* 信号徽章 */
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .04em;
}
.badge-inzone  { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.badge-watch   { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-neutral { background: #f3f4f6; color: #9ca3af; }
.badge-fire3   { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.badge-fire2   { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-fire1   { background: #fff7ed; color: #e85d04; border: 1px solid #fed7aa; }

/* 告警预览框 */
.alert-preview {
    background: #1e2433;
    color: #c9d1d9;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    line-height: 1.8;
    padding: 16px;
    border-radius: 8px;
    white-space: pre;
}

/* Notice */
.notice-info { background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;margin:8px 0; }
.notice-warn { background:#fffbeb;color:#b45309;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;font-size:12px;margin:8px 0; }
.notice-ok   { background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px;font-size:12px;margin:8px 0; }

/* Streamlit 覆盖 */
div[data-testid="stSidebar"] { background: white !important; }
.stButton>button {
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-family: 'Manrope', sans-serif !important;
}
.stTabs [data-baseweb="tab"] { font-weight: 700; }
div[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e2e6ea;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.05);
}
</style>
""", unsafe_allow_html=True)

# ── 导入各页面模块 ────────────────────────────────────────────────
from pages import (
    page_scanner,
    page_confluence,
    page_history,
    page_alerts,
    page_schedule,
    page_settings,
    page_roadmap,
)
from core.supabase_client import init_supabase, supabase_ok
from core.scheduler import start_scheduler_if_needed

# ── Sidebar 导航 ─────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0 16px">
          <div style="background:#e85d04;color:#fff;width:36px;height:36px;border-radius:8px;
                      display:flex;align-items:center;justify-content:center;font-weight:800;font-size:16px">F↗</div>
          <div>
            <div style="font-weight:800;font-size:15px">STRX <span style="color:#e85d04">Fibo</span></div>
            <div style="font-size:10px;color:#9ca3af;font-family:'IBM Plex Mono',monospace">SCANNER PRO</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # DB连接状态
        ok, msg = supabase_ok()
        if ok:
            st.markdown('<div class="notice-ok">✅ Supabase 已连接</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="notice-warn">⚠️ DB未连接<br><small>{msg}</small></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**📊 扫描结果**")
        pages = {
            "📊 实时扫描":     "scanner",
            "🔥 共振检测":     "confluence",
            "📂 历史记录":     "history",
        }
        alert_pages = {
            "🔔 告警配置":     "alerts",
            "⏰ 定时任务":     "schedule",
        }
        sys_pages = {
            "⚙️ 系统设置":     "settings",
            "🚀 功能路线图":   "roadmap",
        }

        for label, key in pages.items():
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state.page = key

        st.markdown("**⚙️ 配置**")
        for label, key in alert_pages.items():
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state.page = key

        st.markdown("**🛠 系统**")
        for label, key in sys_pages.items():
            if st.button(label, key=f"nav_{key}", use_container_width=True):
                st.session_state.page = key

        st.markdown("---")
        st.markdown(
            '<div style="font-size:10px;color:#9ca3af;font-family:\'IBM Plex Mono\',monospace">'
            'Fibonacci 0.500–0.618<br>Pine Script 对应公式<br>fp(r) = H - r×(H-L)'
            '</div>',
            unsafe_allow_html=True
        )

# ── 主路由 ───────────────────────────────────────────────────────
def main():
    # 初始化 session state
    if "page" not in st.session_state:
        st.session_state.page = "scanner"

    # 初始化 Supabase
    init_supabase()

    # 启动定时器（只在生产环境启动一次）
    start_scheduler_if_needed()

    sidebar()

    page = st.session_state.get("page", "scanner")
    if page == "scanner":       page_scanner.render()
    elif page == "confluence":  page_confluence.render()
    elif page == "history":     page_history.render()
    elif page == "alerts":      page_alerts.render()
    elif page == "schedule":    page_schedule.render()
    elif page == "settings":    page_settings.render()
    elif page == "roadmap":     page_roadmap.render()
    else:                       page_scanner.render()

if __name__ == "__main__":
    main()
