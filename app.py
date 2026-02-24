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
import page_watchlist
import page_universe
import page_cloud
import cloud_sync
import cloud_sync


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
            ("📊", "实时扫描",   "scanner"),
            ("🔥", "共振检测",   "confluence"),
            ("🌍", "全量品种库", "universe"),
            ("⭐", "自选收藏",   "watchlist"),
            ("📂", "历史记录",   "history"),
            ("🔔", "告警配置",   "alerts"),
            ("☁️", "云端同步",  "cloud"),
            ("⚙️", "系统设置",  "settings"),
        ]
        p = st.session_state.get("page", "scanner")
        for icon, label, key in NAV:
            if st.button(f"{icon}  {label}", key=f"nav_{key}", width="stretch"):
                st.session_state.page = key
                st.rerun()

        # ── 云同步状态 ──────────────────────────────────────────
        st.markdown("<hr style='margin:10px 0;border-color:#e5e7eb'>", unsafe_allow_html=True)
        try:
            status = cloud_sync.sync_status()
            if status["configured"]:
                last = status["last_push"]
                nxt  = status["next_push"]
                gurl = status["gist_url"]
                st.markdown(
                    f'''<div style="font-size:11px;color:#6b7280;padding:4px 0">
                    ☁️ <b>云同步</b> · 每4小时自动备份<br>
                    上次：{last}<br>
                    下次：{nxt}
                    {"<br><a href='" + gurl + "' target='_blank' style='color:#3b82f6'>查看 Gist ↗</a>" if gurl else ""}
                    </div>''',
                    unsafe_allow_html=True,
                )
                if st.button("☁️ 立即同步", key="sidebar_push", help="立即推送到 GitHub Gist"):
                    with st.spinner("同步中…"):
                        ok, msg = cloud_sync.push_to_gist(force=True)
                    if ok:
                        st.toast(f"✅ {msg[:60]}", icon="☁️")
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.markdown(
                    '<div style="font-size:11px;color:#9ca3af;padding:4px 0">' +
                    '☁️ 云同步未配置<br>' +
                    '<a href="#" style="color:#3b82f6">→ 系统设置中配置</a></div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

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


# ── 密码门禁 ───────────────────────────────────────────────────────
import hashlib as _hashlib

def _make_token(pw: str) -> str:
    """生成密码 token（用于 URL query param 持久化登录）"""
    return _hashlib.sha256(("strx_fibo_" + pw).encode()).hexdigest()[:16]

def _check_password() -> bool:
    """
    密码验证 + 持久化登录：
    - 验证通过后将 token 写入 st.query_params
    - 刷新页面 / 新标签页时自动从 URL 读取 token 验证，无需重新输入密码
    """
    try:
        required_pw = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        required_pw = ""

    if not required_pw:
        return True

    valid_token = _make_token(required_pw)

    # 1. session_state 已验证（当前会话）
    if st.session_state.get("_authenticated"):
        return True

    # 2. URL query param 中有 token（刷新/新标签自动恢复）
    try:
        url_token = st.query_params.get("_t", "")
        if url_token == valid_token:
            st.session_state["_authenticated"] = True
            return True
    except Exception:
        pass

    # 3. 显示登录界面
    st.markdown("""
    <div style="max-width:360px;margin:100px auto 0;text-align:center;">
      <div style="background:linear-gradient(135deg,#e85d04,#f97316);color:#fff;
           width:56px;height:56px;border-radius:14px;display:flex;align-items:center;
           justify-content:center;font-weight:900;font-size:24px;margin:0 auto 16px;">F↗</div>
      <div style="font-size:20px;font-weight:800;color:#111;margin-bottom:4px">STRX Fibo Scanner</div>
      <div style="font-size:13px;color:#6b7280;margin-bottom:28px">请输入访问密码</div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        pw_input = st.text_input(
            "密码", type="password", label_visibility="collapsed",
            placeholder="请输入访问密码…", key="_pw_input"
        )
        if st.button("🔓 进入", type="primary", use_container_width=True, key="_pw_btn"):
            if pw_input == required_pw:
                st.session_state["_authenticated"] = True
                # 将 token 写入 URL，刷新/新标签页自动保持登录
                try:
                    st.query_params["_t"] = valid_token
                except Exception:
                    pass
                st.rerun()
            else:
                st.error("❌ 密码错误，请重试")

    st.stop()
    return False


# ── 路由 ──────────────────────────────────────────────────────────
def main():
    _check_password()

    # ── 启动时：从 GitHub Gist 自动恢复所有数据（云备份）──────────
    if not st.session_state.get("_cloud_pulled"):
        try:
            ok, msg = cloud_sync.auto_pull_on_startup()
            if ok and "成功" in msg:
                st.toast(f"☁️ 云端数据已恢复：{msg}", icon="✅")
        except Exception as e:
            pass   # 云端恢复失败不影响正常使用

    # ── 旧 Secrets 收藏夹恢复（兼容旧版本）────────────────────────
    if not st.session_state.get("_secrets_restored"):
        try:
            ok, msg = storage.restore_from_secrets()
        except Exception:
            pass
        st.session_state["_secrets_restored"] = True

    # ── 每次渲染：检查是否需要自动 Push（4小时一次）────────────────
    try:
        result = cloud_sync.auto_push_if_due()
        if result:
            ok, msg = result
            if ok:
                st.toast("☁️ 数据已自动同步到云端", icon="✅")
    except Exception:
        pass

    if "page" not in st.session_state:
        st.session_state.page = "scanner"

    sidebar()

    p = st.session_state.get("page", "scanner")
    dispatch = {
        "scanner":    page_scanner.render,
        "confluence": page_confluence.render,
        "universe":   page_universe.render,
        "watchlist":  page_watchlist.render,
        "history":    page_history.render,
        "alerts":     page_alerts.render,
        "cloud":      page_cloud.render,
        "settings":   page_settings.render,
    }
    dispatch.get(p, page_scanner.render)()


if __name__ == "__main__":
    main()
