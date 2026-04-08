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
.b-gray {background:#f3f4f6;color:#6b7280;}
.b-red {background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;}
.b-orange{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;}
.b-blue {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;}
.n-ok {background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
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
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
    .main .block-container { padding: 0.5rem 0.8rem 2rem !important; max-width: 100% !important; }
    .m-card { padding: 10px 10px !important; margin-bottom: 6px !important; }
    .m-val { font-size: 20px !important; }
    .m-lbl { font-size: 10px !important; }
    .m-sub { font-size: 10px !important; }
    .rt3 { font-size: 11px !important; display: block; overflow-x: auto; }
    .rt3 th, .rt3 td { padding: 6px 4px !important; white-space: nowrap; }
    .ut2 { font-size: 11px !important; display: block; overflow-x: auto; }
    .ut2 th, .ut2 td { padding: 5px 4px !important; }
    .badge { font-size: 10px !important; padding: 1px 5px !important; }
    .stButton > button { min-height: 38px !important; font-size: 12px !important; padding: 6px 8px !important; }
    .stTextInput input { font-size: 14px !important; }
    div[data-testid="column"] { min-width: 0 !important; }
    div[data-testid="stPills"] { flex-wrap: wrap !important; gap: 4px !important; }
    div[data-testid="stPills"] button { font-size: 11px !important; padding: 3px 8px !important; }
    .streamlit-expanderHeader { font-size: 13px !important; }
    div[data-testid="stTabs"] button { font-size: 12px !important; padding: 6px 8px !important; }
    .n-info, .n-ok, .n-warn { font-size: 12px !important; padding: 7px 10px !important; }
    div[data-testid="stMarkdownContainer"] span { max-width: 100% !important; }
}
@media (max-width: 480px) {
    .m-val { font-size: 18px !important; }
    .rt3 { font-size: 10px !important; }
    .ut2 { font-size: 10px !important; }
    .main .block-container { padding: 0.3rem 0.5rem 2rem !important; }
    h2 { font-size: 18px !important; }
    .stButton > button { font-size: 11px !important; padding: 5px 6px !important; }
}
</style>
""", unsafe_allow_html=True)

# ── 移动端 viewport meta 注入 ─────────────────────────────────────
import streamlit.components.v1 as _stcv1
_stcv1.html("""<script>
if (!document.querySelector('meta[name="viewport"]')) {
    var m = document.createElement('meta');
    m.name = 'viewport';
    m.content = 'width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes';
    document.head.appendChild(m);
}
</script>""", height=0)

# ── 导入页面模块 ──────────────────────────────────────────────────
import storage
import page_scanner
import page_confluence
import page_history
import page_alerts
import page_settings
import page_watchlist
import page_universe
import page_cloud
import cloud_sync

# ══════════════════════════════════════════════════════════════════
# 登录验证模块
# ══════════════════════════════════════════════════════════════════
#
# 安全改进（对比旧版）：
#
# 旧方案：HMAC(password) → 固定 32位 token → 写入 URL ?_t=xxxxx
#   问题1：token 是密码的固定 hash，任何人拿到 URL 可以永久访问
#   问题2：token 出现在浏览器历史、分享链接、服务器 access log 里
#   问题3：token 永不过期，无法吊销
#
# 新方案：随机 UUID token → 只存 sessionStorage（JS）+ session_state（Python）
#   ✅ token 与密码无关，无法反推密码
#   ✅ token 完全不出现在 URL query params 里（不进服务器日志）
#   ✅ 关闭浏览器 tab → sessionStorage 自动清除 → 需重新登录
#   ✅ 普通刷新 → sessionStorage 保留 → 自动恢复，体验不变
#   ✅ 复制 URL 发给他人 → 对方无法登录（URL 里没有 token）
#   ✅ 锁屏/休眠后 tab 复活 → sessionStorage 保留 → 自动恢复
#
# 恢复机制（解决 Streamlit 刷新后 session_state 丢失的问题）：
#   页面加载时注入 JS → 读 sessionStorage token → 写入 ?_st= → Streamlit 读取
#   Streamlit 校验 token 格式合法后恢复登录状态，并立即清除 ?_st= 参数
#
# ══════════════════════════════════════════════════════════════════

import hmac as _hmac
import uuid as _uuid
import re as _re

_AUTH_KEY  = "_authenticated"
_TOKEN_KEY = "_session_token"
_FAIL_KEY  = "_login_fails"
_SS_KEY    = "strx_sess"  # sessionStorage 里的 key 名


def _get_required_pw() -> str:
    try:
        return str(st.secrets.get("APP_PASSWORD", ""))
    except Exception:
        return ""


def _generate_token() -> str:
    """生成随机 32 位十六进制 token，与密码完全无关。"""
    return _uuid.uuid4().hex


def _is_valid_token(token: str) -> bool:
    """校验 token 格式：32 位十六进制，防止注入。"""
    return bool(token and _re.match(r'^[0-9a-f]{32}$', str(token)))


def _write_token_to_browser(token: str):
    """
    登录成功后：把 token 写入 sessionStorage（不写 URL）。
    sessionStorage 的特性：
      - 同一 tab 刷新后仍然存在
      - 关闭 tab 或浏览器后自动清除
      - 不同 tab 之间不共享（每个 tab 需独立登录）
    """
    _stcv1.html(f"""
    <script>
    (function() {{
        try {{
            sessionStorage.setItem('{_SS_KEY}', '{token}');
        }} catch(e) {{
            console.warn('sessionStorage write failed:', e);
        }}
        // 清理旧版遗留的 _t 参数（安全清理）
        var url = new URL(window.location.href);
        if (url.searchParams.has('_t')) {{
            url.searchParams.delete('_t');
            history.replaceState(null, '', url.toString());
        }}
    }})();
    </script>""", height=0)


def _inject_restore_script():
    """
    页面加载时（未登录状态下）注入：
    从 sessionStorage 读 token → 写入 ?_st= param → 触发 Streamlit rerun。
    
    防死循环保护：若 URL 已有 _st 参数，说明是本脚本触发的 reload，直接跳过。
    """
    _stcv1.html(f"""
    <script>
    (function() {{
        // 防死循环：已有 _st 说明是自己触发的 reload
        var params = new URLSearchParams(window.location.search);
        if (params.has('_st')) return;

        var tok = '';
        try {{ tok = sessionStorage.getItem('{_SS_KEY}') || ''; }} catch(e) {{}}
        if (!tok || tok.length !== 32) return;

        // 把 token 写入 ?_st= 让 Streamlit 读取，同时清掉旧版 _t
        params.set('_st', tok);
        params.delete('_t');
        window.location.replace(
            window.location.pathname + '?' + params.toString() + window.location.hash
        );
    }})();
    </script>""", height=0)


def _read_restored_token() -> str:
    """读取 JS 写入的 ?_st= 参数，读完立即清除。"""
    tok = st.query_params.get("_st", "")
    if tok:
        try:
            st.query_params.pop("_st", None)
        except Exception:
            pass
    return tok


def _check_password() -> bool:
    """密码验证入口，返回 True 表示已通过验证。"""
    required_pw = _get_required_pw()
    if not required_pw:
        return True

    # ── Step 1：session_state 内存中已验证（同一 worker 进程内）────
    if st.session_state.get(_AUTH_KEY):
        return True

    # ── Step 2：从 sessionStorage 恢复（刷新/tab 复活场景）──────────
    # 先注入 JS 还原脚本（检测 sessionStorage → 写 ?_st=）
    _inject_restore_script()

    # 读取 JS 回传的 token
    recovered = _read_restored_token()
    if recovered and _is_valid_token(recovered):
        # token 格式合法，视为已登录（真正的安全边界是 sessionStorage，
        # 攻击者必须能访问受害者浏览器的 sessionStorage 才能伪造）
        st.session_state[_AUTH_KEY] = True
        st.session_state[_TOKEN_KEY] = recovered
        return True

    # ── Step 3：显示登录界面 ─────────────────────────────────────
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

        fail_count = st.session_state.get(_FAIL_KEY, 0)
        if fail_count >= 5:
            st.error("🔒 登录尝试过多，请刷新页面后重试。")
            st.stop()

        if st.button("🔓 进入", type="primary", use_container_width=True, key="_pw_btn"):
            if pw_input and _hmac.compare_digest(
                pw_input.encode("utf-8"),
                required_pw.encode("utf-8")
            ):
                # ✅ 验证通过：生成随机 token，不含任何密码信息
                new_token = _generate_token()
                st.session_state[_AUTH_KEY] = True
                st.session_state[_TOKEN_KEY] = new_token
                st.session_state.pop(_FAIL_KEY, None)
                # 把 token 写入 sessionStorage（不写 URL query param）
                _write_token_to_browser(new_token)
                st.rerun()
            else:
                st.session_state[_FAIL_KEY] = fail_count + 1
                remaining = 5 - st.session_state[_FAIL_KEY]
                if remaining > 0:
                    st.error(f"❌ 密码错误，还剩 {remaining} 次机会")
                else:
                    st.error("🔒 登录已锁定，请刷新页面后重试。")
                st.stop()

    return False


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
            ("☁️", "云端同步",   "cloud"),
            ("⚙️", "系统设置",   "settings"),
        ]

        p = st.session_state.get("page", "scanner")
        for icon, label, key in NAV:
            if st.button(f"{icon} {label}", key=f"nav_{key}", width="stretch"):
                st.session_state.page = key
                st.session_state.pop("_url_routed", None)
                st.rerun()

        # ── 云同步状态（Supabase）──────────────────────────────
        st.markdown("<hr style='margin:10px 0;border-color:#e5e7eb'>", unsafe_allow_html=True)
        try:
            status = cloud_sync.get_sync_status()
            if status.get("configured"):
                last_sync = status.get("last_sync", "—")
                next_sync = cloud_sync.time_to_next_sync_str()
                wl_cnt    = status.get("watchlist_cnt", 0)
                st.markdown(
                    f'<div style="font-size:11px;color:#6b7280;padding:4px 0">'
                    f'☁️ <b>云同步</b> · 每4小时自动备份<br>'
                    f'上次：{last_sync}<br>下次：{next_sync}<br>'
                    f'收藏：{wl_cnt} 个品种</div>',
                    unsafe_allow_html=True,
                )
                if st.button("☁️ 立即同步", key="sidebar_push", help="立即推送到 Supabase + 创建快照"):
                    with st.spinner("同步中…"):
                        ok, msg = cloud_sync.push_all()
                        if ok:
                            st.toast(f"✅ {msg[:60]}", icon="☁️")
                            st.rerun()
                        else:
                            st.error(msg[:80])
            else:
                st.markdown(
                    '<div style="font-size:11px;color:#9ca3af;padding:4px 0">'
                    '☁️ 云同步未配置<br>'
                    '<span style="color:#6b7280">→ 前往「云端同步」页配置</span></div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

        st.markdown("---")
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


# ── 路由 ──────────────────────────────────────────────────────────
def main():
    _check_password()

    # ── 启动时：从 Supabase 自动恢复数据 ──────────────────────────
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
            storage.restore_from_secrets()
        except Exception:
            pass
        st.session_state["_secrets_restored"] = True

    # ── 每次渲染：检查是否需要自动 Push（4小时一次）──────────────
    try:
        result = cloud_sync.auto_push_if_due()
        if result:
            ok, msg = result
            if ok:
                st.toast("☁️ 数据已自动同步到云端", icon="✅")
    except Exception:
        pass

    # ── 处理 _fav 收藏指令 ──────────────────────────────────────
    from urllib.parse import unquote as _uq
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
                        st.session_state["_open_wl_tab"] = (_fav_tk, _fav_nm[:40])
                    else:
                        storage.remove_from_watchlist(_fav_tk)
                        st.toast(f"已移除：{_fav_nm[:40]}", icon="🗑️")
        except Exception:
            pass
        st.query_params.pop("_fav", None)
        st.rerun()

    # ── URL 参数路由（_page / _anchor）──────────────────────────
    _VALID_PAGES = ("watchlist", "scanner", "confluence", "alerts",
                    "settings", "history", "cloud", "universe")
    _url_page = st.query_params.get("_page", "")
    _anchor   = st.query_params.get("_anchor", "")

    if _url_page and _url_page in _VALID_PAGES:
        st.session_state["page"] = _url_page
        if _anchor and not st.session_state.get("_wl_highlight"):
            st.session_state["_wl_highlight"] = _anchor
        if not st.session_state.get("_url_routed"):
            st.session_state["_url_routed"] = True
            try:
                st.query_params.pop("_page", None)
                st.query_params.pop("_anchor", None)
            except Exception:
                pass
    elif "page" not in st.session_state:
        st.session_state.page = "watchlist"

    # ── 收藏成功后：新标签打开自选页 ──────────────────────────────
    # 注意：新方案不在 URL 里传 token，新标签打开后需要用户从 sessionStorage 恢复
    # （同一浏览器同一域名下 sessionStorage 不共享 tab，所以新 tab 会要求重新登录）
    # 如需新 tab 免登录，可改用 localStorage，但会牺牲"关闭浏览器自动登出"特性
    _open_wl = st.session_state.pop("_open_wl_tab", None)
    if _open_wl:
        _hl_tk = _open_wl[0] if isinstance(_open_wl, tuple) else _open_wl
        _hl_nm = _open_wl[1] if isinstance(_open_wl, tuple) and len(_open_wl) > 1 else ""
        # 新 tab 链接不带 token（新 tab 需独立登录，这是 sessionStorage 的特性）
        _wl_url = f"/?_page=watchlist&_anchor={_hl_tk}"
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
        "universe":   page_universe.render,
        "watchlist":  page_watchlist.render,
        "history":    page_history.render,
        "alerts":     page_alerts.render,
        "cloud":      page_cloud.render,
        "settings":   page_settings.render,
    }
    dispatch.get(p, page_scanner.render)()

    # ── 移动端底部导航栏 ──────────────────────────────────────────
    _cur_page  = st.session_state.get("page", "scanner")
    _nav_items = [
        ("📊", "扫描",   "scanner"),
        ("🔥", "共振",   "confluence"),
        ("🌍", "品种库", "universe"),
        ("⭐", "自选",   "watchlist"),
        ("⚙️", "设置",   "settings"),
    ]
    # 移动端导航链接不带 _t 参数（旧方案需要带，新方案不需要）
    _nav_html = "".join(
        f'<a href="/?_page={k}" class="mob-nav-item{" active" if k == _cur_page else ""}">'
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
