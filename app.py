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
/* ── 移动端适配 ─────────────────────────────────────────────── */
@media (max-width: 768px) {
    /* 收起侧栏，用汉堡菜单代替 */
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 0.5rem !important;
    }
    /* 增大正文内边距 */
    .main .block-container {
        padding: 0.5rem 0.8rem 2rem !important;
        max-width: 100% !important;
    }
    /* 指标卡：移动端 2×2 布局，减小字体 */
    .m-card { padding: 10px 10px !important; margin-bottom: 6px !important; }
    .m-val  { font-size: 20px !important; }
    .m-lbl  { font-size: 10px !important; }
    .m-sub  { font-size: 10px !important; }
    /* 结果表：移动端隐藏非核心列，启用横向滚动 */
    .rt3 { font-size: 11px !important; display: block; overflow-x: auto; }
    .rt3 th, .rt3 td { padding: 6px 4px !important; white-space: nowrap; }
    /* 品种库表格横向滚动 */
    .ut2 { font-size: 11px !important; display: block; overflow-x: auto; }
    .ut2 th, .ut2 td { padding: 5px 4px !important; }
    /* 徽章：移动端更小 */
    .badge { font-size: 10px !important; padding: 1px 5px !important; }
    /* 按钮：增大触摸区域 */
    .stButton > button {
        min-height: 38px !important;
        font-size: 12px !important;
        padding: 6px 8px !important;
    }
    /* 输入框：全宽 */
    .stTextInput input {
        font-size: 14px !important;
    }
    /* 工具栏：允许换行 */
    div[data-testid="column"] { min-width: 0 !important; }
    /* pills 标签：换行 */
    div[data-testid="stPills"] { flex-wrap: wrap !important; gap: 4px !important; }
    div[data-testid="stPills"] button {
        font-size: 11px !important;
        padding: 3px 8px !important;
    }
    /* expander 头部 */
    .streamlit-expanderHeader { font-size: 13px !important; }
    /* tabs */
    div[data-testid="stTabs"] button { font-size: 12px !important; padding: 6px 8px !important; }
    /* 信息框 */
    .n-info, .n-ok, .n-warn { font-size: 12px !important; padding: 7px 10px !important; }
    /* 卡片内标题 */
    div[data-testid="stMarkdownContainer"] span { max-width: 100% !important; }
}
@media (max-width: 480px) {
    /* 超小屏（iPhone SE 等） */
    .m-val { font-size: 18px !important; }
    .rt3   { font-size: 10px !important; }
    .ut2   { font-size: 10px !important; }
    .main .block-container { padding: 0.3rem 0.5rem 2rem !important; }
    h2 { font-size: 18px !important; }
    .stButton > button { font-size: 11px !important; padding: 5px 6px !important; }
}
</style>
""", unsafe_allow_html=True)

# ── 移动端 viewport meta 注入（Streamlit 默认不设置，必须手动注入）─
import streamlit.components.v1 as _stcv1
_stcv1.html("""<script>
if (!document.querySelector('meta[name="viewport"]')) {
    var m = document.createElement('meta');
    m.name = 'viewport';
    m.content = 'width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes';
    document.head.appendChild(m);
}
</script>""", height=0)

# ── 导入页面模块（直接 import，无子文件夹）──────────────────────────
import storage
import page_scanner
import page_confluence
import page_history
import page_alerts
import page_settings
import page_watchlist
import page_universe
import page_cloud
import page_chartink
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
            ("📊", "实时扫描",           "scanner"),
            ("🔥", "共振检测",           "confluence"),
            ("📈", "4H Breakout",        "chartink"),
            ("🌍", "全量品种库",         "universe"),
            ("⭐", "自选收藏",           "watchlist"),
            ("📂", "历史记录",           "history"),
            ("🔔", "告警配置",           "alerts"),
            ("☁️", "云端同步",           "cloud"),
            ("⚙️", "系统设置",           "settings"),
        ]
        p = st.session_state.get("page", "scanner")
        for icon, label, key in NAV:
            if st.button(f"{icon} {label}", key=f"nav_{key}", width="stretch"):
                st.session_state.page = key
                st.session_state.pop("_url_routed", None)
                st.rerun()

        st.markdown("---")

        # 品种统计
        try:
            from assets import ASSET_GROUPS
            total  = sum(len(g) for g in ASSET_GROUPS.values())
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
import hmac    as _hmac

_TOKEN_SALT = "STRX_F1b0_S3cur3_S4lt_2025"

def _make_token(pw: str) -> str:
    return _hmac.new(
        _TOKEN_SALT.encode(),
        pw.encode(),
        _hashlib.sha256
    ).hexdigest()[:32]

def _check_password() -> bool:
    try:
        required_pw = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        required_pw = ""
    if not required_pw:
        return True

    valid_token = _make_token(required_pw)

    if st.session_state.get("_authenticated"):
        return True

    try:
        url_token = st.query_params.get("_t", "")
        if url_token and _hmac.compare_digest(
            url_token.encode("utf-8"),
            valid_token.encode("utf-8")
        ):
            st.session_state["_authenticated"] = True
            return True
    except Exception:
        pass

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

    _fail_key   = "_login_fails"
    _fail_count = st.session_state.get(_fail_key, 0)
    if _fail_count >= 5:
        st.error("🔒 登录尝试过多，请刷新页面后重试。")
        st.stop()

    if st.button("🔓 进入", type="primary", use_container_width=True, key="_pw_btn"):
        if pw_input and _hmac.compare_digest(pw_input.encode(), required_pw.encode()):
            st.session_state["_authenticated"] = True
            st.session_state.pop(_fail_key, None)
            try:
                st.query_params["_t"] = valid_token
            except Exception:
                pass
            st.rerun()
        else:
            st.session_state[_fail_key] = _fail_count + 1
            remaining = 5 - st.session_state[_fail_key]
            if remaining > 0:
                st.error(f"❌ 密码错误，还剩 {remaining} 次机会")
            else:
                st.error("🔒 登录已锁定，请刷新页面后重试。")
            st.stop()

    return False


# ── 路由 ──────────────────────────────────────────────────────────
def main():
    _check_password()

    # ── 启动时：从云端自动恢复所有数据 ──────────────────────────
    if not st.session_state.get("_cloud_pulled"):
        try:
            ok, msg = cloud_sync.auto_pull_on_startup()
            if ok and "成功" in msg:
                st.toast(f"☁️ 云端数据已恢复：{msg}", icon="✅")
        except Exception:
            pass

    # ── 旧 Secrets 收藏夹恢复（兼容旧版本）────────────────────────
    if not st.session_state.get("_secrets_restored"):
        try:
            ok, msg = storage.restore_from_secrets()
        except Exception:
            pass
        st.session_state["_secrets_restored"] = True

    # ── 处理 _fav 收藏指令 ──────────────────────────────────────
    from urllib.parse import unquote as _uq
    import re as _re

    _fav_raw = st.query_params.get("_fav", "")
    if _fav_raw:
        try:
            _fav_act   = _uq(_fav_raw)
            _fav_parts = _fav_act.split("|", 2)
            if len(_fav_parts) == 3:
                _fav_op, _fav_tk, _fav_nm = _fav_parts
                if _fav_op in ("add", "del") and _re.match(r"^[\w.\-\^=]+$", _fav_tk):
                    if _fav_op == "add":
                        storage.add_to_watchlist(ticker=_fav_tk, name=_fav_nm[:60])
                        _t_val = st.query_params.get("_t", "")
                        st.session_state["_open_wl_tab"] = (_fav_tk, _fav_nm[:40], _t_val)
                    else:
                        storage.remove_from_watchlist(_fav_tk)
                        st.toast(f"已移除：{_fav_nm[:40]}", icon="🗑️")
        except Exception:
            pass
        st.query_params.pop("_fav", None)
        st.rerun()

    # ── URL 参数跳转 ────────────────────────────────────────────
    _VALID_PAGES = ("watchlist","scanner","confluence","alerts","settings",
                    "history","cloud","universe","chartink")
    _url_page = st.query_params.get("_page", "")
    _anchor   = st.query_params.get("_anchor", "")
    if _url_page and _url_page in _VALID_PAGES:
        st.session_state["page"] = _url_page
        if _anchor and not st.session_state.get("_wl_highlight"):
            st.session_state["_wl_highlight"] = _anchor
        if not st.session_state.get("_url_routed"):
            st.session_state["_url_routed"] = True
            try:
                st.query_params.pop("_page",   None)
                st.query_params.pop("_anchor", None)
            except Exception:
                pass
    elif "page" not in st.session_state:
        st.session_state.page = "watchlist"

    # ── 收藏成功后：新标签打开自选页 ──────────────────────────────
    _open_wl = st.session_state.pop("_open_wl_tab", None)
    if _open_wl:
        _hl_tk, _hl_nm, _t_val = (_open_wl if len(_open_wl) == 3 else (*_open_wl, ""))
        _wl_url = f"/?_t={_t_val}&_page=watchlist&_anchor={_hl_tk}"
        import streamlit.components.v1 as _stcv1
        _stcv1.html(
            f"<script>try{{window.open('{_wl_url}','_blank');}}catch(e){{}}</script>",
            height=0,
        )
        st.success(f"⭐ 已收藏「{_hl_nm}」— 自选页已在新标签打开")

    sidebar()

    p = st.session_state.get("page", "scanner")
    dispatch = {
        "scanner":    page_scanner.render,
        "confluence": page_confluence.render,
        "chartink":   page_chartink.render,
        "universe":   page_universe.render,
        "watchlist":  page_watchlist.render,
        "history":    page_history.render,
        "alerts":     page_alerts.render,
        "cloud":      page_cloud.render,
        "settings":   page_settings.render,
    }
    dispatch.get(p, page_scanner.render)()

    # ── 移动端底部导航栏（仅小屏显示）────────────────────────────
    _cur_page  = st.session_state.get("page", "scanner")
    _t_nav     = st.query_params.get("_t", "")
    _nav_items = [
        ("📊", "扫描",   "scanner"),
        ("🔥", "共振",   "confluence"),
        ("🌍", "品种库", "universe"),
        ("⭐", "自选",   "watchlist"),
        ("⚙️", "设置",   "settings"),
    ]
    _nav_html = "".join(
        f'<a href="/?_t={_t_nav}&_page={k}" class="mob-nav-item{" active" if k == _cur_page else ""}">'
        f'<span class="mob-nav-icon">{ic}</span>'
        f'<span class="mob-nav-lbl">{lb}</span></a>'
        for ic, lb, k in _nav_items
    )
    st.markdown(f"""
    <style>
    .mob-nav{{display:none;position:fixed;bottom:0;left:0;right:0;z-index:9999;
              background:#fff;border-top:1px solid #e5e7eb;padding:4px 0 env(safe-area-inset-bottom);
              box-shadow:0 -2px 8px rgba(0,0,0,.08)}}
    .mob-nav-item{{flex:1;display:flex;flex-direction:column;align-items:center;
                  justify-content:center;padding:4px 2px;text-decoration:none;color:#6b7280;
                  font-size:10px;transition:color .15s;min-width:0}}
    .mob-nav-item.active{{color:#e85d04}}
    .mob-nav-icon{{font-size:18px;line-height:1.2}}
    .mob-nav-lbl{{font-size:10px;margin-top:1px;white-space:nowrap}}
    @media(max-width:768px){{
        .mob-nav{{display:flex !important}}
        .main .block-container{{padding-bottom:70px !important}}
    }}
    </style>
    <div class="mob-nav">{_nav_html}</div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
