import faulthandler
faulthandler.enable()

import pandas as pd
try:
    pd.options.future.infer_string = False
except Exception:
    pass
try:
    pd.options.mode.string_storage = "python"
except Exception:
    pass

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
.m-card{
    background: var(--background-color, #fff);
    border: 1px solid var(--border-color, #e5e7eb);
    color: var(--text-color, #111);
    border-radius: 12px;
    padding: 16px 18px;
    text-align: center;
    margin-bottom: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: transform 0.2s, box-shadow 0.2s;
}
.m-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.m-card.teal{border-color:#10b981;background:rgba(16,185,129,0.08);color:var(--text-color, #111);}
.m-card.gold{border-color:#f59e0b;background:rgba(245,158,11,0.08);color:var(--text-color, #111);}
.m-card.red {border-color:#ef4444;background:rgba(239,68,68,0.08);color:var(--text-color, #111);}
.m-card.blue{border-color:#3b82f6;background:rgba(59,130,246,0.08);color:var(--text-color, #111);}
.m-val{font-size:28px;font-weight:800;line-height:1.1;margin:4px 0;}
.m-lbl{font-size:11px;font-weight:700;color:var(--text-color, #6b7280);opacity:0.8;text-transform:uppercase;letter-spacing:.06em;}
.m-sub{font-size:11px;color:#9ca3af;font-family:'IBM Plex Mono',monospace;}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700;white-space:nowrap;}
.b-green {background:rgba(34,197,94,0.1);color:#22c55e;border:1px solid rgba(34,197,94,0.3);}
.b-yellow{background:rgba(234,179,8,0.1);color:#eab308;border:1px solid rgba(234,179,8,0.3);}
.b-gray  {background:rgba(107,114,128,0.1);color:#6b7280;}
.b-red   {background:rgba(239,68,68,0.1);color:#ef4444;border:1px solid rgba(239,68,68,0.3);}
.b-orange{background:rgba(249,115,22,0.1);color:#f97316;border:1px solid rgba(249,115,22,0.3);}
.b-blue  {background:rgba(59,130,246,0.1);color:#3b82f6;border:1px solid rgba(59,130,246,0.3);}
.n-ok  {background:rgba(34,197,94,0.08);color:#22c55e;border:1px solid rgba(34,197,94,0.3);border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
.n-warn{background:rgba(234,179,8,0.08);color:#ca8a04;border:1px solid rgba(234,179,8,0.3);border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
.n-info{background:rgba(59,130,246,0.08);color:#2563eb;border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:9px 14px;font-size:13px;margin:6px 0;}
div[data-testid="stSidebar"] .stButton>button{
    border-radius:8px!important;font-weight:600!important;width:100%;
    margin-bottom:4px;border:1px solid var(--border-color, #e5e7eb);background:var(--background-color, #fff);
    color:var(--text-color, #111);text-align:left!important;justify-content:flex-start!important;padding:8px 12px!important;
}
div[data-testid="stSidebar"] .stButton>button:hover{background:var(--secondary-background-color, #f9fafb)!important;}
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

# ── 移动端 viewport meta 与 PWA manifest 注入 ───────────────────────
st.markdown("""<script>
if (!document.querySelector('meta[name="viewport"]')) {
    var m = document.createElement('meta');
    m.name = 'viewport';
    m.content = 'width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes';
    document.head.appendChild(m);
}
if (!document.querySelector('link[rel="manifest"]')) {
    var l = document.createElement('link');
    l.rel = 'manifest';
    l.href = '/manifest.json';
    document.head.appendChild(l);
}
if (!document.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
    var cap = document.createElement('meta');
    cap.name = 'apple-mobile-web-app-capable';
    cap.content = 'yes';
    document.head.appendChild(cap);
}
if (!document.querySelector('meta[name="theme-color"]')) {
    var tc = document.createElement('meta');
    tc.name = 'theme-color';
    tc.content = '#e85d04';
    document.head.appendChild(tc);
}

// ── 禁止 Streamlit rerun 后自动滚动到触发按钮位置 ──────────────
(function() {
    var _lastY = 0;
    // 每次页面变化前记录滚动位置
    var _mainDoc = function() {
        try { return window.parent.document; } catch(e) { return document; }
    };
    var _getMain = function() {
        var d = _mainDoc();
        return d.querySelector('.main') || d.querySelector('[data-testid="stAppViewContainer"]') || d.scrollingElement || d.documentElement;
    };
    // MutationObserver 监听 Streamlit 的 rerun 动作（DOM 更新）
    // rerun 开始时保存 Y，rerun 结束后恢复 Y
    var _saved = null;
    var _obs = new MutationObserver(function(mutations) {
        var el = _getMain();
        if (_saved !== null) {
            el.scrollTop = _saved;
        }
    });
    // 监听按钮点击：点击前保存滚动位置
    _mainDoc().addEventListener('click', function(e) {
        if (e.target && (e.target.tagName === 'BUTTON' || e.target.closest('button'))) {
            _saved = _getMain().scrollTop;
        }
    }, true);
    // 500ms 后清除保存的位置（rerun应已完成）
    var _clearSaved = function() {
        setTimeout(function() { _saved = null; }, 500);
    };
    // 监听 Streamlit 的 stale/fresh 状态切换
    var _appEl = _mainDoc().querySelector('[data-testid="stApp"]');
    if (_appEl) {
        _obs.observe(_appEl, { attributes: true, attributeFilter: ['data-st-state'] });
        _appEl.addEventListener('DOMAttrModified', _clearSaved);
    }
    // 兜底：监听全局 DOM 子树变化，rerun 完成后 500ms 清除
    var _obsBody = new MutationObserver(function() { _clearSaved(); });
    try {
        _obsBody.observe(_mainDoc().body, { childList: true, subtree: false });
    } catch(e) {}
})();
</script>""", unsafe_allow_html=True)

# ── 导入页面模块（直接 import，无子文件夹）──────────────────────────
import storage
import page_scanner
import page_confluence
import page_history
import page_alerts
import page_settings
import page_watchlist
import page_hotlist
import page_universe
import page_cloud
import page_chartink
import page_schedule
import page_triple_bottom
import page_symbols
import page_ticker
import cloud_sync



def inject_custom_theme():
    cfg = storage.load_config()
    font_size_opt = cfg.get("font_size", "默认 (14px)")
    theme_opt = cfg.get("theme_style", "原厂默认")
    
    size_map = {
        "默认 (14px)": {"body": "14px", "header": "20px", "table": "14px", "badge": "11px", "sub": "11px"},
        "大 (16px)": {"body": "16px", "header": "22px", "table": "16px", "badge": "12px", "sub": "12px"},
        "超大 (18px)": {"body": "18px", "header": "24px", "table": "18px", "badge": "14px", "sub": "13px"}
    }
    s = size_map.get(font_size_opt, size_map["默认 (14px)"])
    
    theme_css = ""
    if theme_opt == "极简深邃 (Minimal Dark)":
        theme_css = """
        :root {
            --background-color: #0f172a !important;
            --secondary-background-color: #1e293b !important;
            --text-color: #f1f5f9 !important;
            --primary-color: #38bdf8 !important;
            --border-color: rgba(255, 255, 255, 0.08) !important;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
            background-color: #0f172a !important;
            color: #f1f5f9 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #1e293b !important;
            border-right: 1px solid rgba(255,255,255,0.05) !important;
        }
        [data-testid="stSidebar"] * {
            color: #e2e8f0 !important;
        }
        .m-card {
            background-color: #1e293b !important;
            border-color: rgba(255,255,255,0.08) !important;
            color: #f1f5f9 !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06) !important;
        }
        .m-lbl {
            color: #94a3b8 !important;
        }
        .alert-log-container {
            border-color: rgba(255, 255, 255, 0.08) !important;
        }
        .alert-log-table th {
            background-color: #1e293b !important;
            color: #94a3b8 !important;
            border-bottom: 2px solid rgba(255, 255, 255, 0.08) !important;
        }
        .alert-log-table td {
            color: #e2e8f0 !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
        }
        .alert-log-row-odd {
            background-color: rgba(56, 189, 248, 0.03) !important;
        }
        .alert-log-row-even {
            background-color: transparent !important;
        }
        .alert-log-table tr:hover {
            background-color: rgba(255, 255, 255, 0.04) !important;
        }
        """
    elif theme_opt == "温暖护眼 (Warm Sepia)":
        theme_css = """
        :root {
            --background-color: #f5eee2 !important;
            --secondary-background-color: #eadac6 !important;
            --text-color: #3e362e !important;
            --primary-color: #d97706 !important;
            --border-color: rgba(220, 210, 190, 0.6) !important;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
            background-color: #f5eee2 !important;
            color: #3e362e !important;
        }
        [data-testid="stSidebar"] {
            background-color: #eadac6 !important;
            border-right: 1px solid rgba(0,0,0,0.05) !important;
        }
        [data-testid="stSidebar"] * {
            color: #5c4f43 !important;
        }
        .m-card {
            background-color: #f5eee2 !important;
            border-color: rgba(220, 210, 190, 0.6) !important;
            color: #3e362e !important;
            box-shadow: 0 2px 8px rgba(60,50,40,0.04) !important;
        }
        .m-lbl {
            color: #7e6e5f !important;
        }
        .alert-log-container {
            border-color: rgba(220, 210, 190, 0.6) !important;
        }
        .alert-log-table th {
            background-color: #eadac6 !important;
            color: #7e6e5f !important;
            border-bottom: 2px solid rgba(220, 210, 190, 0.6) !important;
        }
        .alert-log-table td {
            color: #3e362e !important;
            border-bottom: 1px solid rgba(0, 0, 0, 0.05) !important;
        }
        .alert-log-row-odd {
            background-color: rgba(217, 119, 6, 0.04) !important;
        }
        .alert-log-row-even {
            background-color: transparent !important;
        }
        .alert-log-table tr:hover {
            background-color: rgba(0, 0, 0, 0.02) !important;
        }
        """
    elif theme_opt == "清新雅致 (Sage Forest)":
        theme_css = """
        :root {
            --background-color: #e5ece9 !important;
            --secondary-background-color: #d2ded9 !important;
            --text-color: #242d2a !important;
            --primary-color: #0d9488 !important;
            --border-color: rgba(180, 195, 190, 0.5) !important;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
            background-color: #e5ece9 !important;
            color: #242d2a !important;
        }
        [data-testid="stSidebar"] {
            background-color: #d2ded9 !important;
            border-right: 1px solid rgba(0,0,0,0.05) !important;
        }
        [data-testid="stSidebar"] * {
            color: #40524c !important;
        }
        .m-card {
            background-color: #e5ece9 !important;
            border-color: rgba(180, 195, 190, 0.5) !important;
            color: #242d2a !important;
            box-shadow: 0 2px 8px rgba(20,30,25,0.03) !important;
        }
        .m-lbl {
            color: #5c7068 !important;
        }
        .alert-log-container {
            border-color: rgba(180, 195, 190, 0.5) !important;
        }
        .alert-log-table th {
            background-color: #d2ded9 !important;
            color: #5c7068 !important;
            border-bottom: 2px solid rgba(180, 195, 190, 0.5) !important;
        }
        .alert-log-table td {
            color: #242d2a !important;
            border-bottom: 1px solid rgba(0, 0, 0, 0.04) !important;
        }
        .alert-log-row-odd {
            background-color: rgba(13, 148, 136, 0.03) !important;
        }
        .alert-log-row-even {
            background-color: transparent !important;
        }
        .alert-log-table tr:hover {
            background-color: rgba(0, 0, 0, 0.02) !important;
        }
        """

    if theme_opt != "原厂默认":
        # 针对这三套自定义主题通用覆盖组件样式（使用 CSS variables）
        theme_css += """
        /* 统一输入框、选择框、下拉菜单、日期控件的背景与文字颜色 */
        div[data-baseweb="select"] > div,
        div[data-baseweb="select"] ul,
        div[data-baseweb="select"] li,
        div[data-testid="stDateInput"] > div,
        div[data-baseweb="popover"] *,
        div[role="listbox"] *,
        li[role="option"],
        input, 
        textarea, 
        select {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: var(--border-color) !important;
        }
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div {
            color: var(--text-color) !important;
        }
        div[data-baseweb="calendar"] * {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }
        label, .stWidgetLabel, div[data-testid="stWidgetLabel"] p {
            color: var(--text-color) !important;
        }
        
        /* ══ 全局按钮统一深色背景（消除白色） ══ */
        button,
        .stButton > button,
        div[data-testid="stHorizontalBlock"] button,
        div[data-testid="stHorizontalBlock"] a,
        div[data-testid="stSegmentedControl"] button {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        button:hover,
        .stButton > button:hover,
        div[data-testid="stHorizontalBlock"] a:hover,
        div[data-testid="stSegmentedControl"] button:hover {
            background-color: var(--primary-color) !important;
            color: var(--background-color) !important;
            border-color: var(--primary-color) !important;
        }

        /* ══ 自选收藏夹专用按钮（高特异性 0,0,2,2 覆盖全局 0,0,1,2） ══ */
        div[data-testid="stHorizontalBlock"] button[id*="wl_v_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_pin_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_del_"] {
            background: rgba(128,128,128,0.12) !important;
            border: 1px solid rgba(128,128,128,0.3) !important;
            border-radius: 8px !important;
            color: var(--text-color) !important;
            font-size: 17px !important;
            min-height: 40px !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stHorizontalBlock"] button[id*="wl_v_"]:hover {
            background: rgba(34,197,94,0.22) !important;
            border-color: rgba(34,197,94,0.6) !important;
            color: #4ade80 !important;
        }
        div[data-testid="stHorizontalBlock"] button[id*="wl_pin_"]:hover {
            background: rgba(234,179,8,0.22) !important;
            border-color: rgba(234,179,8,0.6) !important;
            color: #fbbf24 !important;
        }
        div[data-testid="stHorizontalBlock"] button[id*="wl_del_"]:hover {
            background: rgba(239,68,68,0.22) !important;
            border-color: rgba(239,68,68,0.6) !important;
            color: #f87171 !important;
        }
        div[data-testid="stHorizontalBlock"] button[id*="wl_cat_btn_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_tags_btn_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_note_btn_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_hist_btn_"],
        div[data-testid="stHorizontalBlock"] button[id*="wl_chart_btn_"] {
            background: rgba(99,102,241,0.12) !important;
            border: 1px solid rgba(99,102,241,0.3) !important;
            border-radius: 6px !important;
            color: #a5b4fc !important;
            font-size: 15px !important;
            min-height: 34px !important;
        }
        div[data-testid="stHorizontalBlock"] button[id*="wl_cat_btn_"]:hover,
        div[data-testid="stHorizontalBlock"] button[id*="wl_tags_btn_"]:hover,
        div[data-testid="stHorizontalBlock"] button[id*="wl_note_btn_"]:hover,
        div[data-testid="stHorizontalBlock"] button[id*="wl_hist_btn_"]:hover,
        div[data-testid="stHorizontalBlock"] button[id*="wl_chart_btn_"]:hover {
            background: rgba(99,102,241,0.28) !important;
            border-color: rgba(99,102,241,0.65) !important;
            color: #c7d2fe !important;
        }

        
        /* 分段选择控件的激活选中状态 */
        div[data-testid="stSegmentedControl"] button[aria-checked="true"],
        div[data-testid="stSegmentedControl"] button[aria-checked="true"] * {
            background-color: var(--primary-color) !important;
            color: var(--background-color) !important;
        }

        /* 标签页 Tab 控件的背景与底部线条 */
        div[data-testid="stTabs"] button {
            background-color: transparent !important;
            color: var(--text-color) !important;
            border: none !important;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--primary-color) !important;
            border-bottom: 2px solid var(--primary-color) !important;
        }

        /* ── Metric 指标卡 ── */
        div[data-testid="stMetric"] {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            padding: 12px 16px !important;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricValue"] *,
        div[data-testid="stMetricDelta"] * {
            color: var(--text-color) !important;
        }

        /* ── Expander 展开面板 ── */
        div[data-testid="stExpander"] {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
        }
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary *,
        .streamlit-expanderHeader,
        .streamlit-expanderHeader * {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }
        div[data-testid="stExpander"] > div {
            background-color: var(--secondary-background-color) !important;
        }

        /* ── Checkbox / Radio 复选框 ── */
        div[data-testid="stCheckbox"] *,
        div[data-testid="stRadio"] * {
            color: var(--text-color) !important;
        }
        div[data-testid="stCheckbox"] label,
        div[data-testid="stRadio"] label {
            color: var(--text-color) !important;
        }

        /* ── Multiselect 多选框 ── */
        div[data-baseweb="tag"] {
            background-color: var(--primary-color) !important;
            color: var(--background-color) !important;
        }
        div[data-baseweb="tag"] span {
            color: var(--background-color) !important;
        }
        div[data-baseweb="multi-select"] > div {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: var(--border-color) !important;
        }

        /* ── Date Input 日期选择框 ── */
        div[data-testid="stDateInput"] input,
        div[data-testid="stDateInput"] * {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: var(--border-color) !important;
        }

        /* ── Form 表单容器 ── */
        div[data-testid="stForm"] {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            padding: 16px !important;
        }

        /* ── Slider 滑块 ── */
        div[data-testid="stSlider"] * {
            color: var(--text-color) !important;
        }
        div[data-testid="stSlider"] div[role="slider"] {
            background-color: var(--primary-color) !important;
        }

        /* ── stInfo / stSuccess / stWarning / stError 信息框 ── */
        div[data-testid="stAlert"] {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }
        div[data-testid="stAlert"] * {
            color: var(--text-color) !important;
        }

        /* ── 代码块 ── */
        code, pre, .stCode {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }

        /* ── Caption / Small Text 小字 ── */
        div[data-testid="stCaptionContainer"] *,
        small, .caption {
            color: var(--text-color) !important;
            opacity: 0.7;
        }

        /* ── stMarkdownContainer 内联 HTML 文字 ── */
        div[data-testid="stMarkdownContainer"] * {
            color: var(--text-color) !important;
        }

        /* ── Container 通用容器 ── */
        div[data-testid="stVerticalBlock"],
        div[data-testid="stHorizontalBlock"] {
            color: var(--text-color) !important;
        }

        /* ── Popover / Tooltip 弹出浮层 ── */
        div[data-baseweb="popover"] > div,
        div[data-baseweb="tooltip"] > div,
        div[data-baseweb="tooltip"],
        div[role="tooltip"],
        .stTooltipContent,
        [data-testid="stTooltipContent"] {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        div[data-baseweb="tooltip"] *,
        div[role="tooltip"] *,
        div[data-baseweb="popover"] *,
        .stTooltipContent *,
        [data-testid="stTooltipContent"] * {
            color: var(--text-color) !important;
            background-color: transparent !important;
        }

        /* ── Toast 提示 ── */
        div[data-testid="stToast"] {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        """

    font_css = f"""
    html, body, [class*="css"], [class*="st-"], span, p, div, label, input, select, textarea, button {{
        font-size: {s['body']} !important;
    }}
    h1, h2, h3, h4, h5, h6 {{
        font-size: {s['header']} !important;
    }}
    .m-lbl {{
        font-size: {s['badge']} !important;
    }}
    .m-sub {{
        font-size: {s['sub']} !important;
    }}
    .badge {{
        font-size: {s['badge']} !important;
    }}
    .alert-log-table {{
        font-size: {s['table']} !important;
    }}
    .alert-log-table th {{
        font-size: calc({s['table']} - 1px) !important;
    }}
    """
    
    st.markdown(f"""
    <style>
    {theme_css}
    {font_css}
    </style>
    """, unsafe_allow_html=True)


# ── 侧边栏 ─────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;padding:6px 0 18px">
            <div style="background:linear-gradient(135deg,#e85d04,#f97316);color:#fff;
                        width:38px;height:38px;border-radius:10px;display:flex;align-items:center;
                        justify-content:center;font-weight:900;font-size:17px;">F↗</div>
            <div>
                <div style="font-weight:800;font-size:15px;color:var(--text-color, #111)">STRX <span style="color:#e85d04">Fibo</span></div>
                <div style="font-size:10px;color:#9ca3af;font-family:monospace">SCANNER PRO v3.0</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── 全局搜索 ──────────────────────────────────────────────
        import re as _re_side
        search_query = st.text_input(
            "global_search",
            placeholder="🔍 搜索代码或名称…",
            label_visibility="collapsed",
            key="global_search_input"
        ).strip().upper()

        if search_query:
            st.markdown("<div style='font-size:12px;font-weight:bold;margin-bottom:4px;'>🔍 搜索结果:</div>", unsafe_allow_html=True)
            found_any = False

            # 0. 详情跳转
            try:
                symbols_list = storage.load_symbols()
                dt_matches = [s for s in symbols_list if search_query in s["ticker"].upper() or search_query in s.get("name", "").upper()]
                if dt_matches:
                    found_any = True
                    st.markdown("<div style='font-size:11px;color:#9ca3af;'>💎 详情</div>", unsafe_allow_html=True)
                    for item in dt_matches[:2]:
                        tk = item["ticker"]
                        nm = item.get("name") or tk
                        if st.button(f"💎 {nm} ({tk})", key=f"gs_dt_{tk}", use_container_width=True):
                            st.session_state.page = "ticker"
                            st.query_params["_page"] = "ticker"
                            st.query_params["_ticker"] = tk
                            st.rerun()
            except Exception:
                pass
            
            # 1. 自选
            try:
                wl_items = storage.load_watchlist()
                wl_matches = [i for i in wl_items if search_query in i["ticker"].upper() or search_query in i.get("name", "").upper()]
                if wl_matches:
                    found_any = True
                    st.markdown("<div style='font-size:11px;color:#9ca3af;'>⭐ 自选</div>", unsafe_allow_html=True)
                    for item in wl_matches[:3]:
                        tk = item["ticker"]
                        nm = item.get("name") or tk
                        if st.button(f"📌 {nm} ({tk})", key=f"gs_wl_{tk}", use_container_width=True):
                            st.session_state.page = "watchlist"
                            st.query_params["_page"] = "watchlist"
                            st.session_state["_wl_focus_anchor"] = f"wl_row_{_re_side.sub(r'[^0-9A-Za-z_-]', '_', tk.upper())}"
                            st.rerun()
            except Exception:
                pass

            # 2. 热门
            try:
                hl_items = storage.load_hotlist()
                hl_matches = [i for i in hl_items if search_query in i["ticker"].upper() or search_query in i.get("name", "").upper()]
                if hl_matches:
                    found_any = True
                    st.markdown("<div style='font-size:11px;color:#9ca3af;'>🔥 热门</div>", unsafe_allow_html=True)
                    for item in hl_matches[:3]:
                        tk = item["ticker"]
                        nm = item.get("name") or tk
                        if st.button(f"🔥 {nm} ({tk})", key=f"gs_hl_{tk}", use_container_width=True):
                            st.session_state.page = "hotlist"
                            st.query_params["_page"] = "hotlist"
                            st.session_state["_hl_focus_anchor"] = f"hl_row_{_re_side.sub(r'[^0-9A-Za-z_-]', '_', tk.upper())}"
                            st.rerun()
            except Exception:
                pass

            # 3. 信号
            try:
                scan_res = storage.load_latest_results()
                scan_matches = [r for r in scan_res if search_query in r.get("ticker", "").upper()]
                if scan_matches:
                    found_any = True
                    st.markdown("<div style='font-size:11px;color:#9ca3af;'>📊 信号</div>", unsafe_allow_html=True)
                    seen_tk = set()
                    count = 0
                    for r in scan_matches:
                        tk = r.get("ticker", "").upper()
                        if tk in seen_tk: continue
                        seen_tk.add(tk)
                        count += 1
                        if count > 3: break
                        tf = r.get("timeframe", "")
                        dist = r.get("dist_pct", 0)
                        if st.button(f"📊 {tk} ({tf} · {dist:.0f}%)", key=f"gs_scan_{tk}", use_container_width=True):
                            st.session_state.page = "scanner"
                            st.query_params["_page"] = "scanner"
                            st.session_state["scanner_search"] = tk
                            st.rerun()
            except Exception:
                pass

            if not found_any:
                st.caption("无匹配记录")
            st.markdown("<hr style='margin:10px 0;border-color:#e5e7eb'>", unsafe_allow_html=True)

        NAV = [
            ("📊", "实时扫描",           "scanner"),
            ("⚡", "共振检测",           "confluence"),
            ("📐", "三重底扫描",         "triple_bottom"),
            ("📈", "4H Breakout",        "chartink"),
            ("⏰", "定时扫描",           "schedule"),
            ("🌍", "全量品种库",         "universe"),
            ("💎", "品种库",             "symbols"),
            ("⭐", "自选收藏",           "watchlist"),
            ("🔥", "热门品种",           "hotlist"),
            ("📂", "历史记录",           "history"),
            ("📋", "告警日志",           "alert_logs"),
            ("🔔", "告警配置",           "alerts"),
            ("☁️", "云端同步",           "cloud"),
            ("⚙️", "系统设置",           "settings"),
        ]
        p = st.session_state.get("page", "scanner")
        for icon, label, key in NAV:
            if st.button(f"{icon} {label}", key=f"nav_{key}", width="stretch"):
                st.session_state.page = key
                st.query_params["_page"] = key
                st.session_state.pop("_url_routed", None)
                st.rerun()

        # ── 云同步状态 + 立即同步 ──────────────────────────────
        st.markdown("<hr style='margin:10px 0;border-color:#e5e7eb'>", unsafe_allow_html=True)
        try:
            status = cloud_sync.get_sync_status()
            if status.get("configured"):
                last_sync = status.get("last_sync", "—")
                wl_cnt    = status.get("watchlist_cnt", 0)
                elapsed_h = status.get("elapsed_h", 0)
                next_h    = max(0.0, 2.0 - elapsed_h)
                next_str  = f"{int(next_h)}h {int((next_h % 1)*60):02d}m 后" if next_h > 0 else "即将触发"
                st.markdown(
                    f'<div style="font-size:11px;color:#6b7280;padding:4px 0">'
                    f'☁️ <b>云同步</b> · 每2小时自动备份<br>'
                    f'上次：{last_sync}<br>'
                    f'下次：{next_str}<br>'
                    f'收藏：{wl_cnt} 个品种'
                    f'</div>',
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

import datetime as _datetime
import time as _time

def _make_token(pw: str, date_str: str = "") -> str:
    if not date_str:
        date_str = _time.strftime("%Y-%m-%d")
    msg = f"{pw}:{date_str}"
    return _hmac.new(
        _TOKEN_SALT.encode(),
        msg.encode(),
        _hashlib.sha256
    ).hexdigest()[:32]

def _check_password() -> bool:
    try:
        required_pw = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        required_pw = ""
    if not required_pw:
        return True

    today_str = _time.strftime("%Y-%m-%d")
    valid_token = _make_token(required_pw, today_str)

    if st.session_state.get("_authenticated"):
        return True

    try:
        url_token = st.query_params.get("_t", "")
        if url_token:
            yesterday_str = (_datetime.date.today() - _datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_token = _make_token(required_pw, yesterday_str)
            if _hmac.compare_digest(url_token.encode("utf-8"), valid_token.encode("utf-8")) or \
               _hmac.compare_digest(url_token.encode("utf-8"), yesterday_token.encode("utf-8")):
                st.session_state["_authenticated"] = True
                return True
    except Exception:
        pass

    st.markdown("""
    <div style="max-width:360px;margin:100px auto 0;text-align:center;">
        <div style="background:linear-gradient(135deg,#e85d04,#f97316);color:#fff;
                    width:56px;height:56px;border-radius:14px;display:flex;align-items:center;
                    justify-content:center;font-weight:900;font-size:24px;margin:0 auto 16px;">F↗</div>
        <div style="font-size:20px;font-weight:800;color:var(--text-color, #111);margin-bottom:4px">STRX Fibo Scanner</div>
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
            import time
            st.session_state[_fail_key] = _fail_count + 1
            remaining = 5 - st.session_state[_fail_key]
            time.sleep(1.0 + _fail_count * 0.5)
            if remaining > 0:
                st.error(f"❌ 密码错误，还剩 {remaining} 次机会")
            else:
                st.error("🔒 登录已锁定，请刷新页面后重试。")
            st.stop()

    return False


# ── 路由 ──────────────────────────────────────────────────────────
def main():
    # ── 行情链接点击计数（后台静音 fetch 计数）──────────────────
    tv_click = st.query_params.get("_tv_click", "")
    if tv_click:
        ticker = str(tv_click).strip().upper()
        try:
            storage.increment_link_click(ticker, "tv")
        except Exception:
            pass
        st.stop()
        return

    # ── 处理 _trigger 定时扫描指令 (放在密码检查之前，避免被登录阻拦) ──
    _trigger_val = st.query_params.get("_trigger", "")
    if _trigger_val:
        if _trigger_val == "periodic":
            import scheduler
            st.write("🔄 收到外部触发：正在执行自选周期扫描 (EMA20 + Daily Pivot 15m)...")
            try:
                scheduler._run_periodic_watchlist_scan()
                st.success("✅ 自选周期扫描已执行并推送告警！")
            except Exception as e:
                st.error(f"❌ 扫描异常: {e}")
            st.stop()
            return
        elif _trigger_val == "daily":
            import scheduler
            st.write("🔄 收到外部触发：正在执行每日全量扫描...")
            try:
                scheduler._run_scheduled_scan()
                st.success("✅ 每日全量扫描已执行！")
            except Exception as e:
                st.error(f"❌ 扫描异常: {e}")
            st.stop()
            return

    if not _check_password():
        st.stop()
        return

    # ── 应用显示风格和字体大小设置 ──────────────────────────────
    inject_custom_theme()

    # ── 全局浏览器桌面通知监听器 ──────────────────────────────
    try:
        import alerts as alt
        all_logs = storage.load_alert_log(limit=50)
        current_log_ids = {
            f"{log.get('time','')}::{log.get('ticker','')}::{log.get('scanner','')}"
            for log in all_logs if log
        }
        
        if "prev_alert_log_ids" not in st.session_state:
            # 首次载入页面时仅初始化缓存，不触发弹窗
            st.session_state["prev_alert_log_ids"] = current_log_ids
        else:
            prev_ids = st.session_state["prev_alert_log_ids"]
            new_ids = current_log_ids - prev_ids
            if new_ids:
                for log in all_logs:
                    log_key = f"{log.get('time','')}::{log.get('ticker','')}::{log.get('scanner','')}"
                    if log_key in new_ids:
                        scanner_type = log.get("scanner", "")
                        label = log.get("label", "信号")
                        ticker = log.get("ticker", "")
                        name = log.get("name", "")
                        tf = log.get("timeframe", "")
                        status = log.get("status", "ok")
                        
                        if status == "ok":
                            is_starred = storage.is_ticker_starred(ticker)
                            prefix = "⭐[重点关注] " if is_starred else ""
                            if scanner_type == "ema_pivot":
                                title = f"{prefix}🚀 EMA + Pivot 信号: {label}"
                            else:
                                title = f"{prefix}📐 Fibo 信号: {label}"
                            body = f"{name} ({ticker}) [{tf}] - 价格/触发状态已更新"
                            
                            t_val = st.query_params.get("_t", "")
                            target_url = f"/?_page=alert_logs&_t={t_val}" if t_val else "/?_page=alert_logs"
                            
                            alt.send_browser_notification(title, body, target_url=target_url, timeout_seconds=15)
                st.session_state["prev_alert_log_ids"] = current_log_ids
    except Exception as e:
        pass

    # ── 非扫描页面启用全局 60 秒轮询（保持页面活跃及通知更新） ──
    try:
        current_p = st.session_state.get("page", "scanner")
        refresh_pages = {"scanner", "triple_bottom", "chartink", "universe", "alerts", "alert_logs"}
        if current_p not in refresh_pages:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=60000, key="global_notification_autorefresh")
    except Exception:
        pass

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

    # ── 每次渲染：检查是否需要自动 Push（2小时一次）────────────────
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
                        st.toast(f"⭐ 已收藏：{_fav_nm[:40]}", icon="⭐")
                    else:
                        storage.remove_from_watchlist(_fav_tk)
                        st.toast(f"已移除：{_fav_nm[:40]}", icon="🗑️")
        except Exception:
            pass
        st.query_params.pop("_fav", None)
        st.rerun()

    _toggle_star = st.query_params.get("_toggle_star", "")
    if _toggle_star:
        try:
            storage.toggle_starred_ticker(_toggle_star)
            st.toast(f"重点关注状态已更新：{_toggle_star}", icon="⭐")
        except Exception:
            pass
        st.query_params.pop("_toggle_star", None)
        st.rerun()

    # ── URL 参数跳转与同步 ────────────────────────────────────────────
    _VALID_PAGES = ("watchlist","hotlist","scanner","confluence","alerts","settings",
                    "history","cloud","universe","chartink","schedule","triple_bottom","symbols","alert_logs","ticker")
    _url_page = st.query_params.get("_page", "")
    if _url_page and _url_page in _VALID_PAGES:
        st.session_state["page"] = _url_page
    else:
        if "page" not in st.session_state:
            cfg = storage.load_config()
            st.session_state.page = cfg.get("homepage", "watchlist")
        st.query_params["_page"] = st.session_state.page


    sidebar()

    # ── 启动后台定时任务（仅一次） ──────────────────────────────
    try:
        import scheduler
        scheduler.start_scheduler_if_needed()
    except Exception:
        pass

    # ── 强行重载修改过的子页面模块 ──────────────────────────────
    import importlib
    for m in [page_triple_bottom, page_chartink, page_settings, page_watchlist, page_ticker]:
        try:
            importlib.reload(m)
        except Exception:
            pass

    p = st.session_state.get("page", "scanner")
    dispatch = {
        "scanner":       page_scanner.render,
        "confluence":    page_confluence.render,
        "triple_bottom": page_triple_bottom.render_triple_bottom_page,
        "chartink":      page_chartink.render,
        "universe":      page_universe.render,
        "watchlist":     page_watchlist.render,
        "hotlist":       page_hotlist.render,
        "history":       page_history.render,
        "alerts":        page_alerts.render,
        "alert_logs":    page_alerts.render_log_page,
        "cloud":         page_cloud.render,
        "settings":      page_settings.render,
        "schedule":      page_schedule.render,
        "symbols":       page_symbols.render,
        "ticker":        page_ticker.render,
    }
    dispatch.get(p, page_scanner.render)()

    # ── 动态更新浏览器标签页标题 ──
    try:
        st.markdown(f"""
        <script>
        (function() {{
            var parentDoc = window.parent.document;
            var pageNames = {{
                "scanner": "实时扫描",
                "confluence": "共振检测",
                "triple_bottom": "三重底扫描",
                "chartink": "4H Breakout",
                "schedule": "定时扫描",
                "universe": "全量品种库",
                "watchlist": "自选收藏",
                "hotlist": "热门品种",
                "history": "历史记录",
                "alerts": "告警配置",
                "alert_logs": "告警日志",
                "cloud": "云端同步",
                "settings": "系统设置",
                "symbols": "品种库"
            }};
            var title = pageNames["{p}"] || "扫描";
            parentDoc.title = title + " - STRX Fibo Scanner";
        }})();
        </script>
        """, unsafe_allow_html=True)
    except Exception:
        pass


    # ── 移动端悬浮扫描按钮（FAB） ────────────────────────────────
    _support_scan_pages = {"scanner", "triple_bottom", "chartink", "universe"}
    if p in _support_scan_pages:
        import bg_scan_manager
        is_running = bg_scan_manager.is_running()
        if is_running:
            fab_text = "🔄 扫描中..."
            btn_disabled = True
        else:
            if p == "scanner":
                fab_text = "⚡ 立即扫描"
            elif p == "triple_bottom":
                fab_text = "📐 分析扫描"
            elif p == "chartink":
                fab_text = "📈 4H扫描"
            else:
                fab_text = "🌍 批量扫描"
            btn_disabled = False

        # 1. 隐藏的 Streamlit 原生按钮，用来接收点击事件并刷新 state
        st.markdown("""
        <style>
        .hidden-mobile-fab {
            display: none !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="hidden-mobile-fab">', unsafe_allow_html=True)
        if st.button(fab_text, key=f"_mobile_fab_{p}", disabled=btn_disabled):
            st.session_state["_trigger_mobile_scan"] = True
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. 注入 JS，动态把真实的悬浮按钮移到 body 层级，彻底解除 Streamlit 的 transform 限制
        btn_style = "background: linear-gradient(135deg, #ff4b4b, #ff758c) !important;"
        if btn_disabled:
            btn_style = "background: #cccccc !important; color: #888888 !important; cursor: not-allowed !important; pointer-events: none !important; box-shadow: none !important;"

        st.markdown(f"""
        <script>
        (function() {{
            var doc = window.parent.document;
            if (!doc) doc = window.document;
            
            // 移除旧按钮
            var oldBtn = doc.getElementById('global-mobile-fab');
            if (oldBtn) oldBtn.remove();
            
            // 插入 CSS 样式到 head
            var styleId = 'global-mobile-fab-style';
            var oldStyle = doc.getElementById(styleId);
            if (!oldStyle) {{
                var style = doc.createElement('style');
                style.id = styleId;
                style.innerHTML = `
                    #global-mobile-fab {{
                        display: none;
                        position: fixed;
                        bottom: 72px;
                        right: 20px;
                        z-index: 999999;
                    }}
                    @media (max-width: 768px) {{
                        #global-mobile-fab {{
                            display: block !important;
                        }}
                    }}
                    .my-fab-inner-btn {{
                        color: white;
                        border: none;
                        border-radius: 25px;
                        padding: 10px 20px;
                        font-weight: bold;
                        font-size: 14px;
                        box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
                        height: 48px;
                        min-width: 110px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s ease-in-out;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }}
                    .my-fab-inner-btn:active {{
                        transform: scale(0.92);
                        box-shadow: 0 2px 6px rgba(255, 75, 75, 0.4);
                    }}
                `;
                doc.head.appendChild(style);
            }}
            
            // 创建悬浮容器 and 按钮
            var fab = doc.createElement('div');
            fab.id = 'global-mobile-fab';
            
            var innerBtn = doc.createElement('button');
            innerBtn.className = 'my-fab-inner-btn';
            innerBtn.style.cssText = '{btn_style}';
            innerBtn.innerHTML = '{fab_text}';
            
            innerBtn.onclick = function() {{
                // 模拟点击 Streamlit 隐藏按钮
                var buttons = Array.from(doc.querySelectorAll('button'));
                var stBtn = buttons.find(function(b) {{
                    return b.textContent.trim() === '{fab_text}';
                }});
                if (stBtn) {{
                    stBtn.click();
                }} else {{
                    console.log('Streamlit trigger button not found');
                }}
            }};
            
            fab.appendChild(innerBtn);
            doc.body.appendChild(fab);
        }})();
        </script>
        """, unsafe_allow_html=True)
    else:
        # 如果不是扫描页面，确保从 parent document 中移除任何残留的 FAB 按钮
        st.markdown("""
        <script>
        (function() {
            var doc = window.parent.document;
            if (!doc) doc = window.document;
            var oldBtn = doc.getElementById('global-mobile-fab');
            if (oldBtn) oldBtn.remove();
        })();
        </script>
        """, unsafe_allow_html=True)

    # ── 移动端底部导航栏（仅小屏显示）────────────────────────────
    _cur_page  = st.session_state.get("page", "scanner")
    _t_nav     = st.query_params.get("_t", "")
    _nav_items = [
        ("📊", "扫描",   "scanner"),
        ("⚡", "共振",   "confluence"),
        ("🔥", "热门",   "hotlist"),
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
              background:var(--background-color, #fff);border-top:1px solid var(--border-color, #e5e7eb);padding:4px 0 env(safe-area-inset-bottom);
              box-shadow:0 -2px 8px rgba(0,0,0,.08)}}
    .mob-nav-item{{flex:1;display:flex;flex-direction:column;align-items:center;
                  justify-content:center;padding:4px 2px;text-decoration:none;color:var(--text-color, #6b7280);opacity:0.7;
                  font-size:10px;transition:color .15s;min-width:0}}
    .mob-nav-item.active{{color:#e85d04;opacity:1;}}
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
