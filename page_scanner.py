"""
page_scanner.py — 实时扫描（支持 20 组分批扫描 + 自定义品种 + 结果收藏）
"""
import pandas as pd
import streamlit as st
import json
import base64
import time
import os
import webbrowser
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

import storage
import scanner as sc
import bg_scan_manager
from streamlit_autorefresh import st_autorefresh
from assets import ASSET_GROUPS, ASSETS, TIMEFRAMES, CATEGORY_LABELS, tv_url


# ════════════════════════════════════════════════════════════════════
# 徽章辅助
# ════════════════════════════════════════════════════════════════════
def _badge(in_zone: bool, dist) -> str:
    try:    dist = float(dist) if dist is not None else 999.0
    except: dist = 999.0
    if in_zone:  return '<span class="badge b-green">✅ 黄金区</span>'
    if dist < 5: return '<span class="badge b-yellow">👀 接近</span>'
    return '<span class="badge b-gray">—</span>'

def _conf_badge(label: str) -> str:
    label = label or "—"
    if "三" in label: return f'<span class="badge b-red">{label}</span>'
    if "双" in label: return f'<span class="badge b-orange">{label}</span>'
    if "单" in label or "接近" in label: return f'<span class="badge b-yellow">{label}</span>'
    return f'<span class="badge b-gray">{label}</span>'

def _cat_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, cat)


def _batch_open_launcher_url(urls: list[str]) -> str:
    """Build a one-click launcher page as a data URL to open tabs in browser context."""
    payload = json.dumps(urls, ensure_ascii=False)
    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>TV Batch Open</title></head>
<body>
<script>
const urls = {payload};
for (let i = 0; i < urls.length; i++) {{
  window.open(urls[i], '_blank');
}}
window.close();
</script>
<p>If tabs did not open, please allow pop-ups for this site and retry.</p>
</body>
</html>"""
    b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{b64}"


def _trigger_batch_open_in_parent(urls: list[str]):
    """Try opening tabs from the parent window to reduce iframe popup blocking."""
    if not urls:
        return
    payload = json.dumps(urls, ensure_ascii=False)
    st.markdown(
        f"""<script>
const urls = {payload};
const op = (window.parent && window.parent.open) ? window.parent.open.bind(window.parent) : window.open.bind(window);
for (let i = 0; i < urls.length; i++) {{
  setTimeout(() => op(urls[i], '_blank'), i * 120);
}}
</script>""",
        unsafe_allow_html=True,
    )


def _open_urls_via_system(urls: list[str]) -> int:
    """Open URLs via OS default browser, returns success count."""
    ok = 0
    for u in urls:
        try:
            if os.name == "nt":
                os.startfile(u)  # type: ignore[attr-defined]
                ok += 1
            elif webbrowser.open_new_tab(u):
                ok += 1
            time.sleep(0.08)
        except Exception:
            pass
    return ok


def _find_browser_executable() -> str | None:
    """Prefer Chrome, then Edge."""
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _open_urls_via_browser_process(urls: list[str]) -> int:
    """
    Strong batch open: launch browser process with multiple URLs.
    Works around in-page popup blockers.
    """
    if not urls:
        return 0
    browser = _find_browser_executable()
    if not browser:
        return 0
    try:
        subprocess.Popen([browser, *urls])
        return len(urls)
    except Exception:
        return 0


def _render_tv_open_list(urls: list[str]):
    """Reliable fallback: render clickable links instead of popup-based batch open."""
    if not urls:
        return
    st.markdown("#### 待打开链接")
    joined = "\n".join(urls)
    st.text_area("复制全部链接", value=joined, height=120, key="_tv_urls_copy")
    for i, u in enumerate(urls, start=1):
        st.link_button(f"打开 TV {i}", u, type="secondary")


def _render_tv_batch_opener(df: pd.DataFrame):
    if df.empty:
        return

    tv_items = []
    tv_seen = set()
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        tf = str(row.get("timeframe", "")).strip()
        if not ticker or not tf:
            continue
        key = (ticker, tf)
        if key in tv_seen:
            continue
        tv_seen.add(key)
        name = str(row.get("name", ticker)).strip() or ticker
        tv_items.append((name, ticker, tf, tv_url(ticker, tf)))

    if not tv_items:
        return

    st.markdown("### 批量打开 TradingView")
    base_labels = [f"{n} ({t} | {tf})" for n, t, tf, _ in tv_items]
    label_to_url = {f"{n} ({t} | {tf})": u for n, t, tf, u in tv_items}

    today_key = datetime.now().date().isoformat()
    opened_map_key = "tv_opened_by_day"
    cfg = storage.load_config()
    opened_map = cfg.get(opened_map_key, {})
    if not isinstance(opened_map, dict):
        opened_map = {}
    opened_today = set(opened_map.get(today_key, []))

    show_opened_key = "_tv_batch_show_opened"
    all_key = "_tv_batch_all"
    ms_key = "_tv_batch_selected"
    if show_opened_key not in st.session_state:
        st.session_state[show_opened_key] = False
    if all_key not in st.session_state:
        st.session_state[all_key] = False
    if ms_key not in st.session_state:
        st.session_state[ms_key] = []

    display_labels = []
    display_to_base = {}
    for lb in base_labels:
        is_opened = label_to_url.get(lb) in opened_today
        disp = f"✅ 今日已打开 | {lb}" if is_opened else lb
        display_labels.append(disp)
        display_to_base[disp] = lb

    st.session_state[ms_key] = [x for x in st.session_state[ms_key] if x in display_labels]

    col_a, col_b = st.columns([1, 1.6])
    with col_a:
        sel_all = st.checkbox("全选", key=all_key)
    with col_b:
        st.checkbox("显示已打开项", key=show_opened_key)
    if sel_all:
        st.session_state[ms_key] = list(display_labels)

    st.caption(f"今日已打开：{len(opened_today)} | 当前可选：{len(display_labels)}")

    selected_display = st.multiselect(
        "选择要打开的品种（基于当前筛选结果）",
        options=display_labels,
        key=ms_key,
    )

    if st.button("打开选中 TV 链接", key="_open_selected_tv_batch", type="primary"):
        selected_base = [display_to_base[x] for x in selected_display if x in display_to_base]
        urls = [label_to_url[x] for x in selected_base if x in label_to_url]
        if not urls:
            st.warning("请先至少选择 1 个品种。")
            return

        max_open = 30
        open_urls = urls[:max_open]
        proc_opened = _open_urls_via_browser_process(open_urls)
        sys_opened = proc_opened if proc_opened > 0 else _open_urls_via_system(open_urls)
        if sys_opened < len(open_urls):
            _render_tv_open_list(open_urls)

        opened_today.update(open_urls)
        opened_map[today_key] = sorted(opened_today)
        cfg[opened_map_key] = opened_map
        storage.save_config(cfg)

        if proc_opened > 0:
            st.success(f"已通过浏览器进程批量打开 {proc_opened} 个链接。")
        elif sys_opened > 0:
            st.success(f"已尝试系统方式打开 {sys_opened} 个链接。")
        if len(urls) > max_open:
            st.info(f"已打开前 {max_open} 个链接（本次最多 30 个）。")
        elif sys_opened < len(open_urls):
            st.success(f"已准备 {len(open_urls)} 个 TradingView 链接，请点击下方按钮逐个打开。")


def _load_restorable_sessions(limit: int = 50) -> list[dict]:
    """读取可恢复的扫描批次（必须存在快照）。"""
    sessions = storage.load_sessions(limit=limit)
    return [
        s for s in sessions
        if isinstance(s, dict)
        and s.get("session_id")
        and storage.has_scan_snapshot(s.get("session_id"))
    ]


def _render_restore_session_controls():
    sessions = _load_restorable_sessions(limit=50)
    options = []
    sid_map = {}
    for s in sessions:
        sid = str(s.get("session_id", "")).strip()
        scan_time = s.get("scan_time") or s.get("scan_date") or "—"
        inz = s.get("inzone_count", 0)
        tri = s.get("triple_conf", 0)
        label = f"{scan_time} | 黄金区 {inz} | 三共振 {tri} | {sid[:12]}…"
        options.append(label)
        sid_map[label] = sid

    if not options:
        st.selectbox(
            "恢复批次",
            ["暂无可恢复批次（无快照）"],
            key="restore_session_picker_empty",
            disabled=True,
            label_visibility="collapsed",
        )
        st.button(
            "♻️ 恢复所选批次",
            key="restore_selected_scan_btn_disabled",
            disabled=True,
            use_container_width=True,
        )
        return

    selected_label = st.selectbox(
        "恢复批次",
        options,
        key="restore_session_picker",
        label_visibility="collapsed",
    )
    sid = sid_map.get(selected_label, "")
    if st.button(
        "♻️ 恢复所选批次",
        key="restore_selected_scan_btn",
        help="恢复你当前选择的扫描批次快照",
        type="secondary",
        use_container_width=True,
        disabled=not sid,
    ):
        ok, msg, n = storage.restore_scan_snapshot(sid, replace_allres=True)
        if ok:
            st.session_state["_scanner_active_session_id"] = sid
            st.session_state["_scanner_restore_notice"] = (
                f"已恢复批次 {sid[:12]}…（{n} 条）"
            )
            st.rerun()
        st.error(msg)


def _render_clear_scan_button(btn_key: str, use_container_width: bool = True):
    if st.button(
        "🗑️ 清空扫描结果",
        key=btn_key,
        help="仅清除本次扫描结果缓存，不影响自选收藏和系统配置",
        type="secondary",
        use_container_width=use_container_width,
    ):
        # 清空前先把当前结果备份成可恢复批次
        rows = storage.load_latest_results(inzone_only=False)
        sessions = storage.load_sessions(limit=1)
        last_s = sessions[0] if sessions else {}
        now = datetime.now()
        backup_sid = f"clearbak_{now.strftime('%Y%m%d_%H%M%S')}"

        backup_session = {
            "session_id": backup_sid,
            "scan_date": str(now.date()),
            "scan_time": now.isoformat(timespec="seconds"),
            "total_checks": len(rows),
            "inzone_count": sum(1 for r in rows if r.get("in_zone")),
            "triple_conf": int(last_s.get("triple_conf", 0) or 0),
            "elapsed_ms": 0,
            "data_source": last_s.get("data_source", "yfinance"),
            "note": "backup_before_clear",
            "asset_count": len(set(r.get("ticker") for r in rows if r.get("ticker"))),
            "timeframes": sorted(
                {
                    str(r.get("timeframe"))
                    for r in rows
                    if isinstance(r, dict) and r.get("timeframe")
                }
            ),
        }

        snap_ok = bool(rows) and storage.save_scan_snapshot(backup_session, rows)
        storage.clear_all_scan_data()

        # 清空会删除 history；写回这条备份批次，确保可在“恢复批次”中选择
        if snap_ok:
            storage._save(storage.F_HIST, [backup_session])
            st.toast(
                f"✅ 已先备份批次 {backup_sid[:18]}…，再完成清空",
                icon="🗑️",
            )
        else:
            st.toast("✅ 扫描结果已清空（无可备份数据）", icon="🗑️")

        # 避免刷新后被“云端旧扫描数据”自动回填：清空后立即覆盖同步扫描相关 latest
        try:
            import cloud_sync
            _r1 = cloud_sync._upload_latest("scan_history", storage._load(storage.F_HIST, []))
            _r2 = cloud_sync._upload_latest("scan_results", [])
            _r3 = cloud_sync._upload_latest("scan_groups", [])
            if not (_r1 and _r1[0] and _r2 and _r2[0] and _r3 and _r3[0]):
                st.warning("已清空本地；云端扫描缓存覆盖未完全成功，刷新后可能被云端旧数据补回。")
        except Exception:
            st.warning("已清空本地；云端同步异常，刷新后可能被云端旧数据补回。")
        st.rerun()


# ════════════════════════════════════════════════════════════════════
# 后台扫描 Worker
# ════════════════════════════════════════════════════════════════════
def fibo_scan_worker(params, update_progress, cancel_check):
    cfg = params["cfg"]
    assets = params["assets"]
    note = params["note"]
    timeframe_names = params["timeframe_names"]
    
    import re as _re
    
    def cb(pct, text):
        if cancel_check():
            raise bg_scan_manager.CancelException("Scan cancelled by user")
        
        m = _re.search(r"(\d+)/(\d+)", text)
        if m:
            done_count = int(m.group(1))
            total_count = int(m.group(2))
        else:
            done_count = int(pct * 100)
            total_count = 100
            
        update_progress(done_count, total_count, text)
        
    try:
        summary, err = sc.run_full_scan(
            cfg=cfg,
            assets=assets,
            note=note,
            timeframe_names=timeframe_names,
            progress_callback=cb,
        )
        if err:
            raise Exception(err)
        
        sel_list = params.get("sel_list")
        if sel_list:
            storage.save_scanned_groups(sel_list)
            
    except bg_scan_manager.CancelException:
        pass


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    # ── 移动端触发扫描分流 ──
    if st.session_state.get("_trigger_mobile_scan"):
        sel = st.session_state.get("_scan_sel", set())
        if sel:
            st.session_state["_trigger_mobile_batch"] = True
        else:
            st.session_state["_trigger_mobile_custom"] = True
        st.session_state.pop("_trigger_mobile_scan", None)

    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        st_autorefresh(interval=3000, key="fibo_scan_auto_refresh")
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="fibo_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status["job_type"] == "fibo_scan":
        if status["status"] == "done":
            st.success(f"✅ 后台扫描任务已完成!")
        elif status["status"] == "error":
            st.error(f"❌ 后台扫描任务出错! 错误信息: {status.get('error', '')}")
        elif status["status"] == "cancelled":
            st.warning("⚠️ 后台扫描任务已被取消。")
            
        if st.button("清除状态提示", key="fibo_clear_status_btn"):
            bg_scan_manager.reset_to_idle()
            st.rerun()

    st.markdown("## 📊 Fibonacci 实时扫描")
    st.caption("Scanner UI v2026-05-13-2")
    cfg = storage.load_config()
    restored_msg = st.session_state.pop("_scanner_restore_notice", "")
    if restored_msg:
        st.success(restored_msg)

    # ── 分批扫描控制区 ──────────────────────────────────────────────
    with st.expander("📦 选择扫描批次（点击展开/收起）", expanded=True):
        _render_batch_selector(cfg)

    # ── 自定义品种扫描区 ────────────────────────────────────────────
    with st.expander("🔎 自定义品种扫描（输入单个品种代码）", expanded=False):
        _render_custom_scan(cfg)

    with st.expander("📂 从 Doc/symbol 批量扫描（支持仅月图）", expanded=False):
        _render_symbol_path_scan(cfg)

    # ── 工具栏 ──────────────────────────────────────────────────────
    col_kw, col_tf, col_cat, col_zone, col_sort = st.columns([3, 2, 2, 2, 2])
    with col_kw:
        default_kw = st.session_state.pop("scanner_search", "")
        kw = st.text_input("🔍 搜索", value=default_kw, placeholder="名称 / 代码…",
                           label_visibility="collapsed")
    with col_tf:
        tf_sel = st.selectbox("框架", ["全部","Daily","Weekly","Monthly"],
                              label_visibility="collapsed")
    with col_cat:
        all_cat_keys = ["全部"] + sorted(set(CATEGORY_LABELS.keys()))
        cat_sel = st.selectbox("类别", all_cat_keys, label_visibility="collapsed",
                               format_func=lambda x: _cat_label(x) if x != "全部" else "全部类别")
    with col_zone:
        zone_only = st.checkbox("仅黄金区", value=False)
    with col_sort:
        sort_by = st.selectbox("排序", ["共振评分↓","回撤%↑","距离%↑","名称"],
                               label_visibility="collapsed")

    action_col1, action_col2, action_col3 = st.columns([2, 4, 2])
    with action_col1:
        _render_clear_scan_button("clear_scan_results_top_btn")
    with action_col2:
        _render_restore_session_controls()
    with action_col3:
        st.write("")

    # ── 数据展示区 ───────────────────────────────────────────────────
    if not storage.has_scan_data():
        st.markdown('<div class="n-info">💡 尚无数据，请选择品种组后点击「🚀 扫描选中组」，或在上方「自定义品种扫描」中输入品种代码。</div>',
                    unsafe_allow_html=True)
        _metrics(0, 0, 0, 0)
        return

    # load_latest_results 已内置"同 ticker+timeframe 取最新"合并逻辑
    # 直接使用，比 session 循环更健壮（session_id 过滤不一定覆盖所有来源）
    sessions = storage.load_sessions(limit=20)
    if "_scanner_active_session_id" not in st.session_state:
        st.session_state["_scanner_active_session_id"] = (
            sessions[0].get("session_id") if sessions else ""
        )
    active_sid = str(st.session_state.get("_scanner_active_session_id") or "").strip()

    sid_options = []
    sid_map = {}
    for s in sessions:
        sid = str(s.get("session_id") or "").strip()
        if not sid:
            continue
        scan_time = s.get("scan_time") or s.get("scan_date") or "-"
        lb = f"{scan_time} | {sid[:12]}..."
        sid_options.append(lb)
        sid_map[lb] = sid
    if sid_options:
        default_idx = 0
        for i, lb in enumerate(sid_options):
            if sid_map.get(lb) == active_sid:
                default_idx = i
                break
        selected_sid_lb = st.selectbox("Current Session", sid_options, index=default_idx, key="_scanner_active_sid_picker")
        selected_sid = sid_map.get(selected_sid_lb, active_sid)
        if selected_sid and selected_sid != active_sid:
            st.session_state["_scanner_active_session_id"] = selected_sid
            active_sid = selected_sid

    merged_rows = storage.load_session_results(active_sid) if active_sid else []
    if not merged_rows:
        merged_rows = storage.load_latest_results(inzone_only=False)
    last_s = next((s for s in sessions if str(s.get("session_id") or "") == active_sid), (sessions[0] if sessions else {}))

    # 检查原始数据中是否全是空价格（用于判定数据拉取是否完全失败）
    raw_total_len = len(merged_rows)
    raw_has_price = any(r.get("current_price") is not None for r in merged_rows)

    # 过滤掉抓取失败（价格为None）的脏记录，只保留有价格的有效记录渲染到列表中
    merged_rows = [r for r in merged_rows if r.get("current_price") is not None]

    total  = len(set(r["ticker"] for r in merged_rows))
    inzone = sum(1 for r in merged_rows if r.get("in_zone"))
    near   = sum(1 for r in merged_rows
                 if not r.get("in_zone") and (r.get("dist_pct") or 999) < 5)
    triple = sum(
        1 for t in set(r["ticker"] for r in merged_rows)
        if sum(1 for r in merged_rows
               if r["ticker"] == t and r.get("in_zone")) == 3
    )
    _metrics(total, inzone, near, triple)

    scanned_groups = storage.load_scanned_groups()
    if scanned_groups:
        st.caption(f"📦 已扫描组：{'、'.join(scanned_groups[-8:])}  "
                   f"| 品种：{total}  | 更新：{last_s.get('scan_time','—')}")

    # data quality check
    if raw_total_len > 0 and not raw_has_price:
        _warn_lines = [
            "⚠️ **数据获取失败**：所有品种的价格数据均为空。",
            "",
            "**可能原因**：",
            "- 数据服务器暂时无法连接（AKShare / Yahoo Finance 超时）",
            "- A股代码格式有误，需带交易所后缀，如 600048.SS",
            "",
            "**解决方法**：",
            "1. 点击下方[清空扫描结果]清除旧缓存",
            "2. 等待 1-2 分钟后重新扫描",
            "3. 先用[自定义品种扫描]测试单个品种（如 AAPL 或 600519.SS）",
        ]
        st.warning("\n".join(_warn_lines))

    # ── 过滤 ─────────────────────────────────────────────────────────
    df = pd.DataFrame(merged_rows)
    if zone_only:           df = df[df["in_zone"]]
    if tf_sel != "全部":    df = df[df["timeframe"] == tf_sel]
    if cat_sel != "全部":   df = df[df["category"]  == cat_sel]
    if kw:
        mask = (df["name"].str.contains(kw, case=False, na=False) |
                df["ticker"].str.contains(kw, case=False, na=False))
        df = df[mask]

    # 排序
    def safe_float(v, default=999.0):
        try: return float(v) if v is not None else default
        except: return default

    try:
        if sort_by == "共振评分↓":
            if "confluence_score" in df.columns:
                df = df.sort_values("confluence_score", ascending=False)
        elif sort_by == "回撤%↑":
            if "retrace_pct" in df.columns:
                df["_r"] = df["retrace_pct"].apply(lambda x: safe_float(x, 999))
                df = df.sort_values("_r")
        elif sort_by == "距离%↑":
            if "dist_pct" in df.columns:
                df["_d"] = df["dist_pct"].apply(lambda x: safe_float(x, 999))
                df = df.sort_values("_d")
        elif "name" in df.columns:
            df = df.sort_values("name")
    except Exception:
        pass

    if df.empty:
        st.info("没有符合条件的结果"); return

    # 确保必需列存在（兼容旧格式数据）
    for _col in ["in_zone","current_price","retrace_pct","dist_pct",
                 "confluence_score","confluence_label","timeframe","category",
                 "ticker","name"]:
        if _col not in df.columns:
            df[_col] = None

    _render_results_table(df, last_s, safe_float)


# ════════════════════════════════════════════════════════════════════
# 结果表（含逐行收藏按钮）
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — st.columns 逐行渲染，收藏按钮与数据天然同行同高，彻底解决错位
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — HTML 表格 + 内嵌可点击收藏按钮（彻底同行对齐）
# 方案：主内容用 HTML 表格渲染（完美对齐）
#       收藏列用 st.columns 逐行对应，通过 CSS margin-top 精确校准
# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# 结果表 — 完全 HTML 表格方案，收藏通过 query_params 触发，永远同行对齐
# ════════════════════════════════════════════════════════════════════
def _render_results_table(df: pd.DataFrame, last_s: dict, safe_float):

    # ── 处理 query_params 收藏指令（页面渲染前执行）────────────
    try:
        from urllib.parse import unquote as _uq
        import re as _re
        fav_act = st.query_params.get("_fav", "")
        if fav_act:
            fav_act = _uq(fav_act)          # URL decode
            parts = fav_act.split("|", 2)   # "add|TICKER|NAME"
            if len(parts) == 3:
                act, tk, nm = parts
                # 安全校验：action 只允许 add/del，ticker 只允许字母数字符号
                if act in ("add", "del") and _re.match(r"^[\w.\-\^=]+$", tk):
                    if act == "add":
                        storage.add_to_watchlist(ticker=tk, name=nm[:60])
                        # 收藏成功：触发新标签页打开自选页并定位
                        _t_val = st.query_params.get("_t", "")
                        st.session_state["_open_wl_tab"] = (tk, nm[:40], _t_val)
                    else:
                        storage.remove_from_watchlist(tk)
                        st.toast(f"已移除：{nm[:40]}", icon="🗑️")
            try:
                del st.query_params["_fav"]
            except Exception:
                pass
            st.rerun()
    except Exception:
        pass

    # 新标签页打开自选页（收藏成功时）
    _open_wl = st.session_state.pop("_open_wl_tab", None)
    if _open_wl:
        if len(_open_wl) == 3:
            _highlight_tk, _display_nm, _t_val = _open_wl
        else:
            _highlight_tk, _t_val = _open_wl
            _display_nm = _highlight_tk
        _wl_url = f"/?_t={_t_val}&_page=watchlist&_anchor={_highlight_tk}"
        st.markdown(
            f"""<script>
            try {{ window.open('{_wl_url}', '_blank'); }} catch(e) {{}}
            </script>""",
            unsafe_allow_html=True,
        )
        st.success(f"⭐ 已收藏「{_display_nm}」| 自选页已在新标签页打开，已自动定位到该品种")

    # 兼容旧的 session_state 方式
    _pending = st.session_state.pop("_fav_action", None)
    if _pending:
        act, tk, nm = _pending
        if act == "add":
            storage.add_to_watchlist(ticker=tk, name=nm)
            st.toast(f"已收藏：{nm}", icon="⭐")
        else:
            storage.remove_from_watchlist(tk)
            st.toast(f"已移除：{nm}", icon="🗑️")
        st.rerun()

    watchlist         = storage.load_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist if isinstance(w, dict)}
    _render_tv_batch_opener(df)

    # 批量打开 TradingView（基于当前筛选结果）
    if False and not df.empty:
        tv_items = []
        tv_seen = set()
        for _, _r in df.iterrows():
            _ticker = str(_r.get("ticker", "")).strip()
            _tf = str(_r.get("timeframe", "")).strip()
            if not _ticker or not _tf:
                continue
            _k = (_ticker, _tf)
            if _k in tv_seen:
                continue
            tv_seen.add(_k)
            _name = str(_r.get("name", _ticker)).strip() or _ticker
            tv_items.append((_name, _ticker, _tf, tv_url(_ticker, _tf)))

        if tv_items:
            st.markdown("### 批量打开 TradingView")
            labels = [f"{n} ({t} | {tf})" for n, t, tf, _ in tv_items]
            label_to_url = {f"{n} ({t} | {tf})": u for n, t, tf, u in tv_items}
            today_key = datetime.now().date().isoformat()
            opened_map_key = "tv_opened_by_day"
            _cfg = storage.load_config()
            _opened_map = _cfg.get(opened_map_key, {})
            if not isinstance(_opened_map, dict):
                _opened_map = {}
            opened_today = set(_opened_map.get(today_key, []))
            filtered_labels = [lb for lb in labels if label_to_url.get(lb) not in opened_today]
            all_key = "_tv_batch_all"
            ms_key = "_tv_batch_selected"
            if all_key not in st.session_state:
                st.session_state[all_key] = False
            if ms_key not in st.session_state:
                st.session_state[ms_key] = []
            st.session_state[ms_key] = [x for x in st.session_state[ms_key] if x in filtered_labels]

            col_a, _ = st.columns([1, 3])
            with col_a:
                sel_all = st.checkbox("全选", key=all_key)
            if sel_all:
                st.session_state[ms_key] = filtered_labels

            st.caption(f"今日已打开：{len(opened_today)} | 当前可选：{len(filtered_labels)}")

            selected_labels = st.multiselect(
                "选择要打开的品种（基于当前筛选结果）",
                options=filtered_labels,
                key=ms_key,
            )

            if st.button("打开选中 TV 链接", key="_open_selected_tv_batch", type="primary"):
                urls = [label_to_url[x] for x in selected_labels if x in label_to_url]
                if not urls:
                    st.warning("请先至少选择 1 个品种。")
                else:
                    max_open = 30
                    open_urls = urls[:max_open]
                    sys_opened = _open_urls_via_system(open_urls)
                    if sys_opened == 0:
                        _trigger_batch_open_in_parent(open_urls)
                    launcher_url = _batch_open_launcher_url(open_urls)
                    st.link_button("若未自动打开，点这里手动触发", launcher_url, type="secondary")
                    st.caption("若浏览器拦截弹窗，请允许当前站点弹窗后重试。")
                    opened_today.update(open_urls)
                    _opened_map[today_key] = sorted(opened_today)
                    _cfg[opened_map_key] = _opened_map
                    storage.save_config(_cfg)
                    if sys_opened > 0:
                        st.success(f"系统方式已打开 {sys_opened} 个 TradingView 标签页。")
                    elif len(urls) > max_open:
                        st.info(f"已打开前 {max_open} 个链接（本次最多 30 个）。")
                    else:
                        st.success(f"已打开 {len(open_urls)} 个 TradingView 标签页。")

    # ── CSS ──────────────────────────────────────────────────────
    st.markdown("""
    <style>
    /* ── 全站移动端适配 ── */
    @media(max-width:768px){
      /* 卡片间距收紧 */
      .block-container{padding:0.5rem 0.5rem 2rem !important;}
      /* 指标卡手机竖排 */
      .m-card{padding:10px 8px !important;margin:4px 2px !important;}
      .m-val{font-size:24px !important;}
      .m-lbl{font-size:11px !important;}
      /* 表格滚动 */
      .rt3-wrap,.ut2-wrap,.cf3-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;}
      /* 减小字体 */
      .rt3,.ut2,.cf3{font-size:11px !important;}
      .rt3 th,.rt3 td,.ut2 th,.ut2 td{padding:5px 4px !important;}
      /* 按钮满宽 */
      .stButton>button{width:100% !important;font-size:12px !important;padding:6px 4px !important;}
      /* 收藏按钮 */
      .fav-btn{font-size:18px;}
      /* 标题缩小 */
      h2{font-size:1.2rem !important;}
      h3{font-size:1rem !important;}
      /* 隐藏次要列在极窄屏 */
    }
    @media(max-width:480px){
      .rt3{min-width:360px;}
      .block-container{padding:0.3rem !important;}
    }
    /* 扫描结果表 */
    .rt3-wrap{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch;}
    .rt3{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed;min-width:560px;color:var(--text-color, #111);}
    .rt3 th{padding:9px 6px;background:var(--secondary-background-color, #f9fafb);border-bottom:2px solid var(--border-color, #e5e7eb);
            font-size:12px;color:var(--text-color, #374151);font-weight:600;white-space:nowrap}
    .rt3 td{padding:9px 6px;border-bottom:1px solid var(--border-color, #f3f4f6);vertical-align:middle;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .rt3 tr.zone td{background:rgba(234,179,8,0.1)}
    .rt3 tr:hover td{background:rgba(107,114,128,0.05)}
    .rt3 tr.zone:hover td{background:rgba(234,179,8,0.18)}
    .fav-btn{font-size:20px;cursor:pointer;text-decoration:none;line-height:1;
             display:block;text-align:center;padding:2px 0;transition:transform .1s}
    .fav-btn:hover{transform:scale(1.3)}
    .fav-star{color:#f59e0b}
    .fav-empty{color:var(--text-color, #6b7280);opacity:0.3;}
    </style>
    """, unsafe_allow_html=True)

    from html import escape as _he
    seen: set = set()
    rows_html = []

    all_clicks_data = storage.get_all_link_clicks()
    today_str_val = storage.get_today_str()

    for _, r in df.iterrows():
        in_zone   = bool(r.get("in_zone", False))
        dist      = safe_float(r.get("dist_pct"))
        price     = r.get("current_price")
        retrace   = r.get("retrace_pct")
        conf_l    = r.get("confluence_label", "—") or "—"
        cat       = r.get("category", "")
        ticker    = str(r.get("ticker", ""))
        name      = str(r.get("name", ""))
        tf        = r.get("timeframe", "")
        # 始终从 ticker+timeframe 实时生成 TV 链接（不依赖存储的旧 URL）
        tv_lnk    = tv_url(ticker, tf) if ticker else "#"
        # XSS 防护：转义用户可控字段
        name_s    = _he(name)
        ticker_s  = _he(ticker)

        price_s   = f"{float(price):,.4f}"   if price   is not None else "—"
        retrace_s = f"{float(retrace):.1f}%" if retrace is not None else "—"
        dist_s    = "区间内" if in_zone else (f"{dist:.1f}%" if dist < 999 else "—")

        is_first = ticker not in seen
        seen.add(ticker)
        is_fav   = ticker in watchlist_tickers

        # 点击统计 HTML
        click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
        total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
        by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
        today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0
        if total_c > 0:
            click_badge_html = f' <span style="font-size:10px;color:#4ade80;">({today_c}/{total_c})</span>'
        else:
            click_badge_html = ' <span style="font-size:10px;color:#64748b;">(0/0)</span>'

        # 收藏列：用 <a href> 触发 query_params
        from urllib.parse import quote as _qu
        _t = _he(st.query_params.get("_t", ""))
        if is_first:
            # URL encode ticker+name 防止注入
            fav_enc = _qu(f"{'del' if is_fav else 'add'}|{ticker}|{name}", safe="")
            _icon  = "★" if is_fav else "☆"
            _cls   = "fav-star" if is_fav else "fav-empty"
            _tip   = _he(f"{'取消收藏' if is_fav else '收藏'}：{name}")
            fav_html = (
                f'<a href="?_t={_t}&_fav={fav_enc}" '
                f'class="fav-btn {_cls}" title="{_tip}">{_icon}</a>'
            )
        else:
            fav_html = ""

        t_token = st.query_params.get("_t", "")
        ticker_url = f"/?_page=ticker&_ticker={ticker}&_t={t_token}"
        ticker_link = (
            f"<a href='{ticker_url}' target='_self' style='color:inherit;text-decoration:none;transition:color 0.2s;' "
            f"onmouseover='this.style.color=\"#38bdf8\"' onmouseout='this.style.color=\"inherit\"'>"
            f"<b>{name_s}</b><br><small style='color:#9ca3af;font-family:monospace'>{ticker_s}</small></a>"
        )

        zone_cls = ' class="zone"' if in_zone else ""
        rows_html.append(
            f"<tr{zone_cls}>"
            f"<td style='width:20%'>{ticker_link}</td>"
            f"<td style='width:8%'><span class='badge b-gray'>{_cat_label(cat)}</span></td>"
            f"<td style='width:7%'><span class='badge b-gray'>{_he(tf)}</span></td>"
            f"<td style='width:9%'>{_badge(in_zone, dist)}</td>"
            f"<td style='width:12%;font-family:monospace;font-size:12px;text-align:right'>{price_s}</td>"
            f"<td style='width:8%;text-align:right'>{retrace_s}</td>"
            f"<td style='width:8%;text-align:right'>{dist_s}</td>"
            f"<td style='width:13%'>{_conf_badge(conf_l)}</td>"
            f"<td style='width:9%'><a href='{tv_lnk}' target='_blank' class='tv-btn' data-ticker='{ticker_s}' "
            f"style='color:#38bdf8;font-size:12px;text-decoration:none;font-weight:600;'>📈 TV{click_badge_html}</a></td>"
            f"<td style='width:5%;text-align:center'>{fav_html}</td>"
            f"</tr>"
        )

    thead = (
        "<tr>"
        "<th style='width:20%'>资产</th>"
        "<th style='width:8%'>类别</th>"
        "<th style='width:7%'>框架</th>"
        "<th style='width:9%'>状态</th>"
        "<th style='width:12%;text-align:right'>当前价格</th>"
        "<th style='width:8%;text-align:right'>回撤%</th>"
        "<th style='width:8%;text-align:right'>距区间</th>"
        "<th style='width:13%'>共振</th>"
        "<th style='width:9%'>TV (今日/总)</th>"
        "<th style='width:5%;text-align:center'>收藏</th>"
        "</tr>"
    )
    st.markdown(
        f"<div class='rt3-wrap'><table class='rt3'><thead>{thead}</thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    # 💡 隐形事件监听组件：捕捉原链接点击，能在后台落盘计数，同时在前台秒级实时更新 (今日/总) 数字
    import streamlit.components.v1 as _components
    _components.html(r"""
    <script>
    (function() {
        try {
            var pDoc = window.parent.document;
            if (pDoc._tv_click_handler) {
                pDoc.removeEventListener('click', pDoc._tv_click_handler, true);
            }
            pDoc._tv_click_handler = function(e) {
                var btn = e.target.closest('.tv-btn, .sina-btn');
                if (btn) {
                    var tk = btn.getAttribute('data-ticker');
                    if (tk) {
                        tk = tk.trim().toUpperCase();
                        var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);

                        // 1. fetch 强制 no-store 穿透所有浏览器/CDN 缓存
                        try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}

                        // 2. sendBeacon 后台保障发送
                        try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}

                        // 3. IFrame 静音发送
                        try {
                            var f = pDoc.createElement('iframe');
                            f.style.display = 'none';
                            f.src = cbUrl;
                            pDoc.body.appendChild(f);
                            setTimeout(function() {
                                try { f.remove(); } catch(err) {}
                            }, 6000);
                        } catch(err) {}

                        // 4. 前台 DOM 瞬间更新该 ticker 所有对应按钮数值 (秒级反馈)
                        try {
                            var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');
                            for (var i = 0; i < allBtns.length; i++) {
                                var b = allBtns[i];
                                var bTk = b.getAttribute('data-ticker');
                                if (bTk && bTk.trim().toUpperCase() === tk) {
                                    var spans = b.getElementsByTagName('span');
                                    if (spans && spans.length > 0) {
                                        var span = spans[spans.length - 1];
                                        var txt = span.innerText || span.textContent || "";
                                        var m = txt.match(/\((\d+)\/(\d+)\)/);
                                        if (m) {
                                            var today = parseInt(m[1], 10) + 1;
                                            var total = parseInt(m[2], 10) + 1;
                                            span.innerText = '(' + today + '/' + total + ')';
                                            span.style.color = '#4ade80';
                                            span.style.fontWeight = '600';
                                        }
                                    }
                                }
                            }
                        } catch(err) {}
                    }
                }
            };
            pDoc.addEventListener('click', pDoc._tv_click_handler, true);
        } catch(err) {}
    })();
    </script>
    """, height=0)

    st.markdown(
        f'<div style="color:#9ca3af;font-size:11px;margin-top:6px">'
        f'共 {len(df)} 条 &nbsp;｜&nbsp; 点击 ☆/★ 收藏/取消收藏</div>',
        unsafe_allow_html=True,
    )

    csv = df.drop(columns=[c for c in ["_r", "_d"] if c in df.columns],
                  errors="ignore").to_csv(index=False).encode("utf-8-sig")
    _dl_col, _spacer = st.columns([3, 5])
    with _dl_col:
        st.download_button(
            "⬇️ 下载 CSV", csv,
            file_name=f"strx_fibo_{last_s.get('scan_date', 'today')}.csv",
            mime="text/csv",
        )

# ════════════════════════════════════════════════════════════════════

# 常见格式错误规则：(pattern, 修正函数, 说明)
_CORRECTION_RULES = [
    # A 股：6位数字 → 根据首位数字自动判断交易所
    # 6开头 = 上交所(SS)，0/3开头 = 深交所(SZ)，4/8/9开头 = 北交所(BJ)
    (r"^(\d{6})$",
     lambda m: (
         [f"{m.group(1)}.SS"] if m.group(1)[0] == "6"
         else [f"{m.group(1)}.SZ"] if m.group(1)[0] in ("0","3")
         else [f"{m.group(1)}.BJ"]
     ),
     "A股代码自动识别交易所（6开头→上交所.SS / 0/3开头→深交所.SZ / 4/8/9开头→北交所.BJ）"),
    # 港股：去掉 .HK 前导零不够4位
    (r"^(\d{1,3})\.HK$",   lambda m: [f"{int(m.group(1)):04d}.HK"],
     "港股代码需补全为4位数字（如 700.HK → 0700.HK）"),
    # 港股：纯数字 1-4 位没有 .HK 后缀
    (r"^(\d{1,4})$",       lambda m: [f"{int(m.group(1)):04d}.HK"],
     "纯数字可能是港股，建议加 .HK 后缀"),
    # 外汇：EURUSD 没有 =X
    (r"^([A-Z]{6})$",      lambda m: [f"{m.group(1)}=X"],
     "外汇品种代码通常需在末尾加 =X（如 EURUSD=X）"),
    # 加密：BTC/ETH 没有 -USD（需先于通用2-3字母规则）
    (r"^(BTC|ETH|BNB|SOL|ADA|XRP|DOGE|AVAX|DOT|LINK)$",
     lambda m: [f"{m.group(1)}-USD"],
     "加密货币代码通常需加 -USD（如 BTC-USD）"),
    # 期货：GC / CL / SI 没有 =F
    (r"^([A-Z]{2,3})$",    lambda m: [f"{m.group(1)}=F"],
     "期货品种代码通常需在末尾加 =F（如 GC=F / CL=F）"),
]

# 常见品种名称/别名 → yfinance ticker 映射
_NAME_ALIAS: dict[str, tuple[str, str]] = {
    "黄金": ("GC=F", "黄金期货"),
    "GOLD": ("GC=F", "黄金期货"),
    "白银": ("SI=F", "白银期货"),
    "SILVER": ("SI=F", "白银期货"),
    "原油": ("CL=F", "原油期货"),
    "OIL": ("CL=F", "原油期货"),
    "比特币": ("BTC-USD", "比特币"),
    "BITCOIN": ("BTC-USD", "比特币"),
    "以太坊": ("ETH-USD", "以太坊"),
    "ETHEREUM": ("ETH-USD", "以太坊"),
    "纳斯达克": ("^IXIC", "纳斯达克综合"),
    "NASDAQ": ("^IXIC", "纳斯达克综合"),
    "标普": ("^GSPC", "标普500"),
    "SP500": ("^GSPC", "标普500"),
    "S&P": ("^GSPC", "标普500"),
    "道琼斯": ("^DJI", "道琼斯"),
    "DJI": ("^DJI", "道琼斯"),
    "上证": ("000001.SS", "上证指数"),
    "沪深300": ("000300.SS", "沪深300"),
    "恒生": ("^HSI", "恒生指数"),
    "HSI": ("^HSI", "恒生指数"),
    "欧元美元": ("EURUSD=X", "欧元/美元"),
    "EURUSD": ("EURUSD=X", "欧元/美元"),
    "美元日元": ("USDJPY=X", "美元/日元"),
    "USDJPY": ("USDJPY=X", "美元/日元"),
    "VIX": ("^VIX", "VIX恐慌指数"),
    "苹果": ("AAPL", "苹果"),
    "特斯拉": ("TSLA", "特斯拉"),
    "英伟达": ("NVDA", "英伟达"),
    "NVIDIA": ("NVDA", "英伟达"),
    "腾讯": ("0700.HK", "腾讯控股"),
    "茅台": ("600519.SS", "贵州茅台"),
}


import re

def _suggest_corrections(raw: str) -> list[dict]:
    """返回修正建议列表，每项 {ticker, reason}"""
    raw = raw.strip().upper()
    suggestions = []

    # 1. 名称/别名匹配
    alias_match = _NAME_ALIAS.get(raw) or _NAME_ALIAS.get(raw.upper())
    if alias_match:
        suggestions.append({
            "ticker": alias_match[0],
            "name":   alias_match[1],
            "reason": f"识别为「{alias_match[1]}」的常用名称",
        })

    # 2. 格式规则匹配
    for pattern, fix_fn, reason in _CORRECTION_RULES:
        m = re.match(pattern, raw)
        if m:
            try:
                candidates = fix_fn(m)
                for c in candidates:
                    if c != raw and not any(s["ticker"] == c for s in suggestions):
                        suggestions.append({"ticker": c, "name": "", "reason": reason})
            except Exception:
                pass

    # 3. 从品种库中模糊匹配
    try:
        from assets import ASSETS
        kw = raw.lower()
        for tk, (nm, _cat) in ASSETS.items():
            if (kw in tk.lower() or kw in nm.lower()) and tk != raw:
                if not any(s["ticker"] == tk for s in suggestions):
                    suggestions.append({
                        "ticker": tk,
                        "name":   nm,
                        "reason": f"品种库中找到相似品种：{nm}",
                    })
                if len(suggestions) >= 5:
                    break
    except Exception:
        pass

    return suggestions[:5]


_SCAN_TF_OPTIONS = ["Daily", "Weekly", "Monthly"]


def _normalize_scan_timeframes(selected) -> list[str]:
    tf_names = [t for t in (selected or _SCAN_TF_OPTIONS) if t in TIMEFRAMES]
    if not tf_names:
        tf_names = list(TIMEFRAMES.keys())
    return tf_names


def _resolve_symbol_token(token: str) -> tuple[str, tuple[str, str]] | None:
    key = token.strip()
    if not key:
        return None

    upper = key.upper()
    if upper in ASSETS:
        return upper, ASSETS[upper]

    # exact name match in assets
    for tk, (nm, cat) in ASSETS.items():
        if nm.strip().lower() == key.lower():
            return tk, (nm, cat)

    # alias fallback
    alias_match = _NAME_ALIAS.get(key) or _NAME_ALIAS.get(upper)
    if alias_match:
        tk = alias_match[0].upper()
        if tk in ASSETS:
            return tk, ASSETS[tk]
        return tk, (alias_match[1], "custom")

    # correction fallback
    suggestions = _suggest_corrections(key)
    if suggestions:
        tk = suggestions[0].get("ticker", "").upper()
        if tk:
            if tk in ASSETS:
                return tk, ASSETS[tk]
            return tk, (suggestions[0].get("name") or tk, "custom")
    return None


def _list_symbol_files() -> list[Path]:
    base = Path.cwd() / "Doc" / "symbol"
    files: list[Path] = []
    if base.exists() and base.is_dir():
        for ext in ("*.txt", "*.csv", "*.list"):
            files.extend(sorted(base.glob(ext)))
    return files


def _resolve_symbol_input_path(path_text: str) -> Path:
    raw = (path_text or "").strip().strip('"').strip("'")
    if not raw:
        return Path.cwd() / "Doc" / "symbol"

    candidates: list[Path] = []
    p = Path(raw).expanduser()
    candidates.append(p)

    if not p.is_absolute():
        candidates.append(Path.cwd() / raw)

    normalized = raw.replace("\\", "/")
    marker = "/doc/symbol/"
    low = normalized.lower()
    if marker in low:
        idx = low.index(marker)
        tail = normalized[idx + len(marker):].strip("/")
        mapped_base = Path.cwd() / "Doc" / "symbol"
        candidates.append(mapped_base / tail if tail else mapped_base)
    elif ":" in raw:
        candidates.append(Path.cwd() / "Doc" / "symbol" / Path(raw).name)

    for c in candidates:
        if c.exists():
            return c

    tried = " | ".join(str(c) for c in candidates[:4])
    raise FileNotFoundError(f"路径不存在：{raw}（尝试：{tried}）")


def _parse_symbol_text(text: str) -> tuple[dict, list[str], dict]:
    assets_map: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []
    seen_tokens: set[str] = set()
    stats = {
        "total_lines": 0,
        "blank_or_comment": 0,
        "parsed_tokens": 0,
        "duplicate_tokens": 0,
        "resolved_hits": 0,
        "duplicate_ticker_overwrites": 0,
        "unresolved_count": 0,
        "unique_tickers": 0,
        "source_files": 1,
    }

    for raw in text.splitlines():
        stats["total_lines"] += 1
        line = raw.strip()
        if not line or line.startswith("#"):
            stats["blank_or_comment"] += 1
            continue

        token = line
        if "," in token:
            token = token.split(",", 1)[0].strip()
        if "\t" in token:
            token = token.split("\t", 1)[0].strip()
        if not token:
            stats["blank_or_comment"] += 1
            continue

        stats["parsed_tokens"] += 1
        if token in seen_tokens:
            stats["duplicate_tokens"] += 1
        else:
            seen_tokens.add(token)

        resolved = _resolve_symbol_token(token)
        if resolved:
            stats["resolved_hits"] += 1
            tk, meta = resolved
            if tk in assets_map:
                stats["duplicate_ticker_overwrites"] += 1
            assets_map[tk] = meta
        else:
            unresolved.append(token)

    stats["unresolved_count"] = len(unresolved)
    stats["unique_tickers"] = len(assets_map)
    return assets_map, unresolved, stats


def _load_symbols_assets_from_path(path_text: str) -> tuple[dict, list[str], dict]:
    p = _resolve_symbol_input_path(path_text)

    files: list[Path] = []
    if p.is_file():
        files = [p]
    else:
        for ext in ("*.txt", "*.csv", "*.list"):
            files.extend(sorted(p.glob(ext)))
    if not files:
        raise ValueError("未找到可读取的 symbol 文件（支持 .txt/.csv/.list）")

    assets_map: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []
    merged_stats = {
        "total_lines": 0,
        "blank_or_comment": 0,
        "parsed_tokens": 0,
        "duplicate_tokens": 0,
        "resolved_hits": 0,
        "duplicate_ticker_overwrites": 0,
        "unresolved_count": 0,
        "unique_tickers": 0,
        "source_files": len(files),
    }

    for file in files:
        text = file.read_text(encoding="utf-8", errors="ignore")
        parsed_assets, parsed_unresolved, part_stats = _parse_symbol_text(text)
        cross_file_dup = len(set(assets_map.keys()) & set(parsed_assets.keys()))
        assets_map.update(parsed_assets)
        unresolved.extend(parsed_unresolved)
        merged_stats["total_lines"] += part_stats["total_lines"]
        merged_stats["blank_or_comment"] += part_stats["blank_or_comment"]
        merged_stats["parsed_tokens"] += part_stats["parsed_tokens"]
        merged_stats["duplicate_tokens"] += part_stats["duplicate_tokens"]
        merged_stats["resolved_hits"] += part_stats["resolved_hits"]
        merged_stats["duplicate_ticker_overwrites"] += (
            part_stats["duplicate_ticker_overwrites"] + cross_file_dup
        )
        merged_stats["unresolved_count"] += part_stats["unresolved_count"]

    merged_stats["unique_tickers"] = len(assets_map)
    return assets_map, unresolved, merged_stats


def _try_fetch_ticker(ticker: str) -> bool:
    """尝试用 yfinance 获取该 ticker 最近1条数据，判断是否有效。"""
    try:
        import yfinance as yf
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = yf.download(ticker, period="5d", interval="1d",
                             progress=False, auto_adjust=True)
        return df is not None and not df.empty
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# 自定义品种扫描
# ════════════════════════════════════════════════════════════════════
def _render_custom_scan(cfg):
    st.markdown("""
    <div class="n-info">
    💡 输入任意 <b>yfinance 品种代码</b>进行单独扫描。<br>
    示例：<code>AAPL</code>（苹果）、<code>BTC-USD</code>（比特币）、
    <code>000001.SS</code>（上证指数）、<code>0700.HK</code>（腾讯）、
    <code>EURUSD=X</code>（欧元/美元）、<code>GC=F</code>（黄金期货）
    </div>
    """, unsafe_allow_html=True)

    col_ticker, col_name, col_btn = st.columns([3, 3, 2])

    # 提前处理移动端触发，避免渲染后直接修改 text_input 关联的 session_state
    if st.session_state.get("_trigger_mobile_custom"):
        if not st.session_state.get("custom_ticker_input"):
            st.session_state["custom_ticker_prefill"] = "AAPL"

    with col_ticker:
        # 若用户刚点了建议代码，将其预填入输入框
        if "custom_ticker_prefill" in st.session_state:
            st.session_state["custom_ticker_input"] = st.session_state.pop("custom_ticker_prefill")
        raw_input = st.text_input(
            "品种代码",
            placeholder="如：TSLA / 600519.SS / GC=F / 腾讯",
            key="custom_ticker_input",
        ).strip()
        custom_ticker = raw_input.upper()

    with col_name:
        custom_name = st.text_input(
            "自定义名称（可选）",
            placeholder="如：特斯拉 / 贵州茅台 / 黄金",
            key="custom_name_input",
        ).strip()

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        do_custom = st.button("🔍 立即扫描", type="primary",
                              width="stretch", key="custom_scan_btn", disabled=bg_scan_manager.is_running())
        if st.session_state.pop("_trigger_mobile_custom", False):
            if not custom_ticker:
                custom_ticker = "AAPL"
            do_custom = True

    tf_selected = st.multiselect(
        "扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("custom_scan_tfs", _SCAN_TF_OPTIONS),
        key="custom_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    # 自动触发扫描（来自"建议代码"按钮或"扫描 XX.SS"按钮点击）
    _auto_trig = st.session_state.pop("_auto_scan_trigger", None)
    if _auto_trig:
        do_custom = True
        custom_ticker = _auto_trig.upper()
        # 同步更新 custom_name 若已预置
        if st.session_state.get("custom_name_confirmed"):
            custom_name = st.session_state["custom_name_confirmed"]

    # ── 实时修正提示（输入时即显示建议，无需点扫描）──────────────
    confirmed_ticker = custom_ticker  # 最终使用的 ticker

    if custom_ticker and not do_custom:
        suggestions = _suggest_corrections(custom_ticker)
        if suggestions:
            st.markdown(
                '<div style="background:#fffbeb;border:1px solid #fde68a;'
                'border-radius:8px;padding:10px 14px;margin:6px 0;">'
                '<b style="color:#92400e">💡 格式建议</b>',
                unsafe_allow_html=True,
            )
            for i, sug in enumerate(suggestions):
                c1, c2 = st.columns([5, 2])
                with c1:
                    name_part = f" — {sug['name']}" if sug.get("name") else ""
                    st.markdown(
                        f'<span style="font-family:monospace;font-weight:600;color:#1d4ed8">'
                        f'{sug["ticker"]}</span>{name_part}'
                        f'<br><span style="color:#6b7280;font-size:11px">{sug["reason"]}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(f"使用 {sug['ticker']}", key=f"use_sug_{i}_{sug['ticker']}"):
                        # 将选定代码写入 prefill，下次 rerun 时自动填入输入框
                        st.session_state["custom_ticker_prefill"]  = sug["ticker"]
                        st.session_state["custom_name_confirmed"]  = sug.get("name", "")
                        # 清除之前的确认状态
                        st.session_state.pop("custom_ticker_confirmed", None)
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # 检查是否有已确认的修正代码（来自扫描失败后点击建议）
    confirmed_ticker = custom_ticker
    if st.session_state.get("custom_ticker_confirmed"):
        confirmed_ticker = st.session_state["custom_ticker_confirmed"]
        if not custom_name and st.session_state.get("custom_name_confirmed"):
            custom_name = st.session_state["custom_name_confirmed"]
        col_info, col_cancel = st.columns([6, 2])
        with col_info:
            st.info(f"ℹ️ 将使用修正后的代码：**{confirmed_ticker}**")
        with col_cancel:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✖ 取消修正", key="cancel_correction"):
                st.session_state.pop("custom_ticker_confirmed", None)
                st.session_state.pop("custom_name_confirmed", None)
                st.rerun()

    if not do_custom:
        return

    # ── 执行扫描 ────────────────────────────────────────────────
    final_ticker = confirmed_ticker or custom_ticker
    if not final_ticker:
        st.warning("请输入品种代码"); return

    display_name  = custom_name or final_ticker

    # 先验证 ticker 是否可以取到数据
    with st.spinner(f"🔍 验证品种代码 {final_ticker}…"):
        valid = _try_fetch_ticker(final_ticker)

    if not valid:
        suggestions = _suggest_corrections(final_ticker)
        st.error(
            f"❌ 无法获取 **{final_ticker}** 的数据（可能是代码格式错误或已退市）"
        )
        if suggestions:
            st.markdown("**💡 您是否想扫描以下品种？**")
            for i, sug in enumerate(suggestions):
                c1, c2 = st.columns([6, 2])
                with c1:
                    name_part = f" — {sug['name']}" if sug.get("name") else ""
                    st.markdown(
                        f'**{sug["ticker"]}**{name_part}  '
                        f'<span style="color:#6b7280;font-size:12px">{sug["reason"]}</span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button(f"✅ 扫描 {sug['ticker']}", key=f"err_sug_{i}_{sug['ticker']}",
                                 type="primary"):
                        # 清除旧 widget state，用 prefill 机制更新输入框
                        st.session_state.pop("custom_ticker_input", None)
                        st.session_state["custom_ticker_prefill"]  = sug["ticker"]
                        st.session_state["custom_name_confirmed"]  = sug.get("name", "")
                        st.session_state["custom_ticker_confirmed"]= sug["ticker"]
                        st.session_state["_auto_scan_trigger"]     = sug["ticker"]
                        st.rerun()
        return

    # 清除确认状态
    st.session_state.pop("custom_ticker_confirmed", None)
    st.session_state.pop("custom_name_confirmed", None)

    custom_assets = {final_ticker: (display_name, "custom")}
    
    params = {
        "cfg": cfg,
        "assets": custom_assets,
        "note": f"custom:{final_ticker}",
        "timeframe_names": tf_names
    }
    
    ok, msg = bg_scan_manager.submit_job(
        job_type="fibo_scan",
        label=f"自定义品种扫描 ({display_name})",
        params=params,
        worker_fn=fibo_scan_worker
    )
    if ok:
        st.success(msg)
        time.sleep(1)
        st.rerun()
    else:
        st.error(msg)



def _render_symbol_path_scan(cfg):
    st.caption("支持读取文件或目录（.txt/.csv/.list），每行一个 ticker 或品种名称。")
    tf_selected = st.multiselect(
        "文件扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("symbol_file_scan_tfs", _SCAN_TF_OPTIONS),
        key="symbol_file_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    uploaded = st.file_uploader(
        "上传 symbol 文件（可选）",
        type=["txt", "csv", "list"],
        key="symbol_file_upload",
        help="云端推荐：直接上传 MG.txt，无需依赖服务器路径",
    )
    pasted_symbols = st.text_area(
        "或直接粘贴 symbols（可选）",
        value="",
        key="symbol_pasted_text",
        height=110,
        placeholder="每行一个代码或名称，例如：\nAAPL\nTSLA\n0700.HK\n贵州茅台",
    ).strip()

    path_text = st.text_input(
        "symbol 文件路径",
        value=st.session_state.get("symbol_file_path", "Doc/symbol"),
        key="symbol_file_path",
        placeholder="Doc/symbol 或 Doc/symbol/MG.txt",
    ).strip()

    do_file_scan = st.button("📂 扫描该路径中的品种", key="scan_from_symbol_path", type="primary", disabled=bg_scan_manager.is_running())
    if not do_file_scan:
        return

    file_assets: dict[str, tuple[str, str]] = {}
    unresolved: list[str] = []
    parse_stats = None
    source_label = ""

    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        file_assets, unresolved, parse_stats = _parse_symbol_text(text)
        source_label = f"upload:{uploaded.name}"
    elif pasted_symbols:
        file_assets, unresolved, parse_stats = _parse_symbol_text(pasted_symbols)
        source_label = "paste"
    else:
        try:
            file_assets, unresolved, parse_stats = _load_symbols_assets_from_path(path_text)
            source_label = f"path:{path_text}"
        except Exception as e:
            st.error(f"读取失败：{e}")
            files = _list_symbol_files()
            if files:
                sample = "、".join(f.name for f in files[:12])
                st.caption(f"可用文件：{sample}")
                st.caption("建议输入相对路径，例如：`Doc/symbol/MG.txt`")
            else:
                st.caption("当前部署环境未发现 `Doc/symbol` 文件。请改用“上传 symbol 文件”或直接粘贴 symbols。")
            return

    if not file_assets:
        st.warning("未解析到有效品种，请检查文件内容。")
        if parse_stats:
            st.caption(
                f"解析统计：总行 {parse_stats['total_lines']} | 可解析行 {parse_stats['parsed_tokens']} | "
                f"空行/注释 {parse_stats['blank_or_comment']} | 未识别 {parse_stats['unresolved_count']}"
            )
        if unresolved:
            st.caption("未识别条目示例: " + "、".join(unresolved[:10]))
        return

    st.info(f"将扫描 {len(file_assets)} 个品种，周期：{' / '.join(tf_names)}")
    if parse_stats:
        st.caption(
            f"解析统计：总行 {parse_stats['total_lines']} | 可解析行 {parse_stats['parsed_tokens']} | "
            f"空行/注释 {parse_stats['blank_or_comment']} | 重复行 {parse_stats['duplicate_tokens']} | "
            f"识别成功 {parse_stats['resolved_hits']} | 去重覆盖 {parse_stats['duplicate_ticker_overwrites']} | "
            f"未识别 {parse_stats['unresolved_count']} | 最终唯一品种 {parse_stats['unique_tickers']}"
        )
    params = {
        "cfg": cfg,
        "assets": file_assets,
        "note": source_label,
        "timeframe_names": tf_names
    }
    
    ok, msg = bg_scan_manager.submit_job(
        job_type="fibo_scan",
        label=f"文件/批量扫描 ({source_label})",
        params=params,
        worker_fn=fibo_scan_worker
    )
    if ok:
        st.success(msg)
        time.sleep(1)
        st.rerun()
    else:
        st.error(msg)
        
    if unresolved:
        st.caption("未识别条目: " + "、".join(unresolved[:20]))


# ════════════════════════════════════════════════════════════════════
# 分批扫描选择器  ── 重新设计 v2
#
# 架构：
#   1. 唯一 session_state key：`_scan_sel`（set，存已选组名）
#   2. 快捷按钮直接写 `_scan_sel`，无第二个 key
#   3. 分类折叠面板：每个顶级分类独立一行，行内 checkbox 选子组
#   4. 底部固定状态栏 + 扫描按钮
# ════════════════════════════════════════════════════════════════════
def _render_batch_selector(cfg):
    """
    分批扫描选择器 v3 — 修复全选/扫描按钮失效问题
    ─────────────────────────────────────────────
    根本原因：
      Streamlit checkbox 有自己的 widget key，rerun 后 widget state 优先于 value=。
      旧代码：全选按钮写 _scan_sel → rerun → checkbox widget state 仍是旧值（False）
              → checkbox 返回 False → _new.discard(g) 把刚加进去的组立刻删掉。
    
    修复方案：
      1. checkbox 不使用固定 key（每次渲染重新生成），强制 value= 参数生效
      2. checkbox 变化时用 st.rerun() 让整个 UI 刷新，保证视觉一致
      3. 全选/快捷按钮 → 更新 _scan_sel → rerun（同上，无 key 冲突）
    """
    from collections import defaultdict

    custom_groups = storage.load_symbol_groups()
    ASSET_GROUPS = {}
    if custom_groups:
        sym_map = {s["ticker"]: s["name"] for s in storage.load_symbols()}
        for g in custom_groups:
            g_assets = {}
            for tk in g.get("tickers", []):
                g_assets[tk] = (sym_map.get(tk, tk), "custom")
            ASSET_GROUPS[g["name"]] = g_assets

    if not ASSET_GROUPS:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        st.warning("⚠️ 自定义品种库中没有任何分组！请先前往「💎 品种库」页面创建分组、导入内置品种或添加品种。")
        col_nav, _ = st.columns([2, 5])
        with col_nav:
            if st.button("👉 前往品种库页面", key="go_to_symbols_btn", type="primary", use_container_width=True):
                st.session_state["page"] = "symbols"
                st.rerun()
        return

    group_names  = list(ASSET_GROUPS.keys())
    total_assets = sum(len(v) for v in ASSET_GROUPS.values())
    n_groups     = len(group_names)

    # ── session state 初始化 ─────────────────────────────────────
    if "_scan_sel" not in st.session_state:
        st.session_state["_scan_sel"] = set()

    # 读取当前已选（过滤无效组名）
    sel: set = {g for g in st.session_state["_scan_sel"] if g in ASSET_GROUPS}
    st.session_state["_scan_sel"] = sel   # 写回清洁版

    # ── 信息栏 ───────────────────────────────────────────────────
    st.markdown(
        f'<div class="n-info">📦 品种库：共 <b>{total_assets}</b> 个品种，分 '
        f'<b>{n_groups}</b> 组。每组约 13–30 个品种 × 3 框架，单批约 1–3 分钟。'
        f'多次扫描结果自动缓存合并，无需一次全部完成。</div>',
        unsafe_allow_html=True,
    )

    st.markdown("**📅 批量扫描周期（可只选 Monthly）**")
    tf_selected = st.multiselect(
        "批量扫描周期",
        options=_SCAN_TF_OPTIONS,
        default=st.session_state.get("batch_scan_tfs", _SCAN_TF_OPTIONS),
        key="batch_scan_tfs",
        help="可只选择 Monthly 实现仅月图扫描",
    )
    tf_names = _normalize_scan_timeframes(tf_selected)

    # ── 快捷选择按钮 ─────────────────────────────────────────────
    _QUICK = [
        ("☑️ 全选",      lambda g: True),
        ("🥇 期货+指数",  lambda g: any(k in g for k in ["期货","指数","全球","ETF"])),
        ("🇺🇸 美股+ETF",  lambda g: "美股" in g or "ETF" in g),
        ("🇨🇳 中股",      lambda g: any(k in g for k in ["中概","港股","A股","中国","中国指数"])),
        ("💱 外汇",       lambda g: "外汇" in g),
        ("₿ 加密",       lambda g: "加密" in g),
        ("🌏 亚太",       lambda g: any(k in g for k in ["日本","韩国","台湾","印度","澳大利亚","东南亚"])),
        ("🌍 欧洲",       lambda g: any(k in g for k in ["英国","德国","法国","北欧","欧洲"])),
        ("🌎 新兴",       lambda g: any(k in g for k in ["加拿大","拉美","新兴","非洲","中东"])),
        ("🔲 清空",       None),
    ]

    st.markdown("""
    <style>
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] > div > div > button {
        padding: 4px 8px !important; font-size: 12px !important;
        min-height: 32px !important;
    }
    </style>""", unsafe_allow_html=True)

    cols = st.columns(len(_QUICK))
    for i, (label, fn) in enumerate(_QUICK):
        with cols[i]:
            if st.button(label, key=f"_qbtn_{i}", use_container_width=True):
                if fn is None:
                    st.session_state["_scan_sel"] = set()
                else:
                    st.session_state["_scan_sel"] = {g for g in group_names if fn(g)}
                st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── 构建 顶级分类 → [组名列表] ──────────────────────────────
    cat_groups: dict = defaultdict(list)
    for g in group_names:
        parts = g.split(" - ", 1)
        cat_groups[parts[0].strip()].append(g)

    sorted_cats = sorted(cat_groups.items(), key=lambda x: -len(x[1]))

    # ── 分类面板 ─────────────────────────────────────────────────
    scanned = storage.load_scanned_groups()
    st.markdown("**📋 按分类选择品种组**（点击分类名展开/收起）：")

    # 用于收集本轮 checkbox 产生的变更
    _pending_add    = set()
    _pending_remove = set()

    for cat, groups in sorted_cats:
        n_in_cat   = len(groups)
        sel_in_cat = sum(1 for g in groups if g in sel)
        all_sel    = (sel_in_cat == n_in_cat)

        with st.expander(
            f"{'✅' if all_sel else ('☑' if sel_in_cat > 0 else '⬜')} "
            f"{cat}  "
            f"{'（已全选）' if all_sel else f'（{sel_in_cat}/{n_in_cat}）'}",
            expanded=(sel_in_cat > 0),
        ):
            # ── 该分类全选 / 取消全选 ───────────────────────────
            c_all, c_none, _ = st.columns([2, 2, 6])
            with c_all:
                if st.button(f"全选 {n_in_cat} 组", key=f"_cat_all_{cat}",
                             use_container_width=True):
                    st.session_state["_scan_sel"] = sel | set(groups)
                    st.rerun()
            with c_none:
                if sel_in_cat > 0:
                    if st.button("取消全选", key=f"_cat_none_{cat}",
                                 use_container_width=True):
                        st.session_state["_scan_sel"] = sel - set(groups)
                        st.rerun()

            # ── 子组 checkbox（关键修复：不使用固定 key）────────
            # 不传 key 参数，Streamlit 每次重新渲染时不保留 widget state，
            # value= 参数始终生效，与 _scan_sel 完全同步。
            if n_in_cat == 1:
                g = groups[0]
                short      = g.split(" - ", 1)[-1] if " - " in g else g
                n_assets   = len(ASSET_GROUPS[g])
                is_scanned = g in scanned
                label_txt  = f"{short}  ({n_assets} 品种)" + (" ✅缓存" if is_scanned else "")
                new_checked = st.checkbox(label_txt, value=(g in sel))
                if new_checked != (g in sel):
                    if new_checked: _pending_add.add(g)
                    else:           _pending_remove.add(g)
            else:
                _cols = st.columns(3)
                for ci, g in enumerate(groups):
                    short      = g.split(" - ", 1)[-1] if " - " in g else g
                    n_assets   = len(ASSET_GROUPS[g])
                    is_scanned = g in scanned
                    label_txt  = f"{short}  ({n_assets})" + (" ✅" if is_scanned else "")
                    with _cols[ci % 3]:
                        new_checked = st.checkbox(label_txt, value=(g in sel))
                        if new_checked != (g in sel):
                            if new_checked: _pending_add.add(g)
                            else:           _pending_remove.add(g)

    # ── 应用 checkbox 变更（如有则 rerun 刷新 UI）────────────────
    if _pending_add or _pending_remove:
        new_sel = (sel | _pending_add) - _pending_remove
        st.session_state["_scan_sel"] = new_sel
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── 状态栏 + 扫描按钮（始终渲染，即使 sel 为空也显示提示）──
    sel_list   = sorted(sel, key=lambda g: group_names.index(g))
    sel_assets: dict = {}
    for g in sel_list:
        sel_assets.update(ASSET_GROUPS[g])
    checks = len(sel_assets) * len(tf_names)

    scanned_list = storage.load_scanned_groups()
    already   = [g for g in sel_list if g in scanned_list]
    unscanned = [g for g in sel_list if g not in scanned_list]

    col_info, col_btn = st.columns([5, 2])
    with col_info:
        if sel_list:
            st.markdown(
                f"**已选：{len(sel_list)} 组 · {len(sel_assets)} 个品种 · {checks} 次检查**"
            )
            st.caption(f"周期：{' / '.join(tf_names) if tf_names else '未选择'}")
            if already:
                st.caption(
                    f"✅ 已缓存（可跳过）：{'、'.join(g.split(' - ')[-1] for g in already[:5])}"
                    + (f" 等{len(already)}组" if len(already) > 5 else "")
                )
            if unscanned:
                st.caption(
                    f"🆕 未扫描：{'、'.join(g.split(' - ')[-1] for g in unscanned[:5])}"
                    + (f" 等{len(unscanned)}组" if len(unscanned) > 5 else "")
                )
        else:
            st.info("💡 请在上方选择至少一个品种组，或使用快捷按钮批量选择。")

    with col_btn:
        do_scan = st.button(
            f"🚀 扫描选中 {len(sel_assets)} 品种" if sel_assets else "🚀 扫描（请先选择组）",
            type="primary",
            use_container_width=True,
            disabled=(len(sel_assets) == 0 or len(tf_names) == 0 or bg_scan_manager.is_running()),
        )
        if st.session_state.pop("_trigger_mobile_batch", False):
            do_scan = True

    if sel_assets and not tf_names:
        st.warning("请至少选择一个扫描周期。")

    if do_scan and sel_assets and tf_names:
        group_label = "、".join(g.split(" - ")[-1] for g in sel_list[:3]) + \
                      (f"等{len(sel_list)}组" if len(sel_list) > 3 else "")
        
        params = {
            "cfg": cfg,
            "assets": sel_assets,
            "note": f"batch:{group_label}",
            "timeframe_names": tf_names,
            "sel_list": sel_list
        }
        
        ok, msg = bg_scan_manager.submit_job(
            job_type="fibo_scan",
            label=f"分批扫描 ({group_label})",
            params=params,
            worker_fn=fibo_scan_worker
        )
        if ok:
            st.success(msg)
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)


# ════════════════════════════════════════════════════════════════════
# 指标卡
# ════════════════════════════════════════════════════════════════════
def _metrics(total, inzone, near, triple):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="m-card"><div class="m-lbl">监控品种</div>'
                    f'<div class="m-val">{total}</div>'
                    f'<div class="m-sub">×3 框架</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="m-card teal"><div class="m-lbl">黄金区间</div>'
                    f'<div class="m-val" style="color:#059669">{inzone}</div>'
                    f'<div class="m-sub">0.500–0.618</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="m-card gold"><div class="m-lbl">接近区间</div>'
                    f'<div class="m-val" style="color:#d97706">{near}</div>'
                    f'<div class="m-sub">距离&lt;5%</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="m-card red"><div class="m-lbl">三框架共振</div>'
                    f'<div class="m-val" style="color:#dc2626">{triple}</div>'
                    f'<div class="m-sub">最强信号</div></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
