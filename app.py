"""
STRX Automatic Fibo Scanner Pro v3
====================================
Streamlit Cloud 原生版 · 平铺文件结构 · JSON 存储
"""

import sys
import os

# ── 确保当前目录在 sys.path（Streamlit Cloud 必须）──────────────────
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

st.set_page_config(
    page_title="STRX Fibo Scanner",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局 CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Inter:wght@400;600;700;800&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif!important;}

.m-card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;text-align:center;margin-bottom:4px;}
.m-card.teal{border-color:#6ee7b7;background:#ecfdf5;}
.m-card.gold{border-color:#fcd34d;background:#fffbeb;}
.m-card.red {border-color:#fca5a5;background:#fef2f2;}
.m-card.blue{border-color:#93c5fd;background:#eff6ff;}
.m-val{font-size:28px;font-weight:800;line-height:1.1;margin:4px 0;}
.m-lbl{font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;}
.m-sub{font-size:11px;color:#9ca3af;font-family:'IBM Plex Mono',monospace;}

.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap;}
.b-green {background:#dcfce7;color:#15803d;border:1px solid #86efac;}
.b-yellow{background:#fef9c3;color:#a16207;border:1px solid #fde047;}
.b-gray  {background:#f3f4f6;color:#6b7280;}
.b-red   {background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;}
.b-orange{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;}
.b-blue  {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;}

.n-ok  {background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
.n-warn{background:#fffbeb;color:#92400e;border:1px solid #fde68a;border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
.n-info{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}

div[data-testid="stSidebar"] .stButton>button{
  border-radius:8px!important;font-weight:600!important;width:100%;
  margin-bottom:4px;border:1px solid #e5e7eb;background:#fff;
  text-align:left!important;justify-content:flex-start!important;padding:8px 12px!important;
}
div[data-testid="stSidebar"] .stButton>button:hover{background:#f9fafb!important;}
</style>
""", unsafe_allow_html=True)

# ── 导入页面模块（直接 import，无子文件夹）──────────────────────────
import page_scanner
import page_confluence
import page_history
import page_alerts
import page_settings


# ── 侧边栏 ─────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;padding:6px 0 18px">
          <div style="background:linear-gradient(135deg,#e85d04,#f97316);color:#fff;
               width:38px;height:38px;border-radius:10px;display:flex;align-items:center;
               justify-content:center;font-weight:900;font-size:17px;">F↗</div>
          <div>
            <div style="font-weight:800;font-size:15px;color:#111">STRX <span style="color:#e85d04">Fibo</span></div>
            <div style="font-size:10px;color:#9ca3af;font-family:monospace">SCANNER PRO v3.0</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        NAV = [
            ("📊", "实时扫描",  "scanner"),
            ("🔥", "共振检测",  "confluence"),
            ("📂", "历史记录",  "history"),
            ("🔔", "告警配置",  "alerts"),
            ("⚙️", "系统设置",  "settings"),
        ]
        p = st.session_state.get("page", "scanner")
        for icon, label, key in NAV:
            if st.button(f"{icon}  {label}", key=f"nav_{key}", width="stretch"):
                st.session_state.page = key
                st.rerun()

        st.markdown("---")

        # 品种统计
        try:
            from assets import ASSET_GROUPS
            total = sum(len(g) for g in ASSET_GROUPS.values())
            groups = len(ASSET_GROUPS)
        except Exception:
            total, groups = 0, 0

        st.markdown(f"""
        <div style="font-size:11px;color:#9ca3af;line-height:1.9">
        <b>📐 公式</b><br>
        fp(r) = H − r×(H−L)<br>
        黄金区: 0.500 – 0.618<br><br>
        <b>📦 品种库</b><br>
        {total} 个品种 / {groups} 组<br>
        支持分批扫描<br><br>
        <b>💾 存储</b>: JSON 本地文件<br>
        <b>📡 数据</b>: yfinance (免费)
        </div>
        """, unsafe_allow_html=True)


# ── 路由 ──────────────────────────────────────────────────────────
def main():
    if "page" not in st.session_state:
        st.session_state.page = "scanner"

    sidebar()

    p = st.session_state.get("page", "scanner")
    dispatch = {
        "scanner":    page_scanner.render,
        "confluence": page_confluence.render,
        "history":    page_history.render,
        "alerts":     page_alerts.render,
        "settings":   page_settings.render,
    }
    dispatch.get(p, page_scanner.render)()


if __name__ == "__main__":
    main()
