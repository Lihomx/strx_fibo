"""
page_cloud.py — ☁️ 云端同步管理
Supabase Storage 自动备份配置与控制面板
"""

import time
import streamlit as st

import storage
import cloud_sync


# ════════════════════════════════════════════════════════════════════
# 主渲染
# ════════════════════════════════════════════════════════════════════
def render():
    st.markdown("## ☁️ 云端自动同步")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '使用 <b>Supabase</b>（免费，永不过期）自动备份所有数据，'
        '重启后自动恢复，无需手动操作。</p>',
        unsafe_allow_html=True,
    )

    # ── 状态总览 ─────────────────────────────────────────────────
    configured = cloud_sync.is_configured()
    status     = cloud_sync.get_sync_status()

    if configured:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(
                _metric_card("☁️ 云端状态", "已连接", "green"),
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(
                _metric_card("🕐 上次同步", status.get("last_sync", "—"), "blue"),
                unsafe_allow_html=True,
            )
        with col3:
            st.markdown(
                _metric_card("⏱️ 距下次同步", cloud_sync.time_to_next_sync_str(), "gray"),
                unsafe_allow_html=True,
            )
        with col4:
            cnt = status.get("scan_results_cnt", 0)
            st.markdown(
                _metric_card("📊 云端扫描记录", f"{cnt:,} 条", "teal"),
                unsafe_allow_html=True,
            )
    else:
        st.markdown("""
        <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;
                    padding:16px 20px;margin-bottom:16px">
        <b>⚠️ 尚未配置 Supabase 云同步</b><br>
        配置后可实现：每4小时自动备份 · App重启自动恢复 · 收藏夹实时同步
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Tabs ────────────────────────────────────────────────────
    tab_setup, tab_control, tab_status = st.tabs(
        ["🔧 配置教程", "🚀 同步控制", "📋 同步状态"]
    )

    with tab_setup:
        _render_setup()

    with tab_control:
        _render_control(configured)

    with tab_status:
        _render_status(configured, status)


# ════════════════════════════════════════════════════════════════════
# Tab1：配置教程
# ════════════════════════════════════════════════════════════════════
def _render_setup():
    st.markdown("### 🔧 第一步：注册 Supabase（免费，2分钟）")

    st.markdown("""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:14px 18px;margin-bottom:12px">
    <b>✅ Supabase 免费层资源（永不过期）</b><br><br>
    <table style="font-size:13px;width:100%">
    <tr><td>📦 文件存储</td><td><b>1 GB</b>（存所有 JSON 备份，够用几十年）</td></tr>
    <tr><td>🗄️ 数据库</td><td><b>500 MB</b></td></tr>
    <tr><td>🔑 API 请求</td><td><b>无限制</b></td></tr>
    <tr><td>💳 需要信用卡</td><td><b>不需要</b></td></tr>
    <tr><td>⏰ 会过期吗</td><td><b>不会</b>（活跃项目永久免费）</td></tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
**操作步骤：**

**① 注册并创建项目**
1. 打开 [supabase.com](https://supabase.com) → 点击 **Start your project**
2. 用 GitHub 账号登录（一键授权）
3. 点击 **New project** → 填写项目名（如 `strx-fibo`）→ 设置数据库密码 → 选区域（Singapore 延迟最低）→ **Create new project**（约30秒）

**② 获取 API 凭证**
1. 进入项目后，左侧菜单 → **Project Settings**（齿轮图标）
2. 点击 **API** 选项卡
3. 复制以下两项：
   - **Project URL**（格式：`https://xxxxxxxxxxxx.supabase.co`）
   - **anon/public** 下的 **API Key**（`eyJhbG...`开头的长字符串）

**③ 在 Streamlit Cloud 中配置 Secrets**
1. 打开 Streamlit Cloud → 你的 App → 右上角 **⋮** → **Settings** → **Secrets**
2. 追加以下内容（保留已有的 `APP_PASSWORD` 行）：
    """)

    st.code("""# Supabase 云同步配置
SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
SUPABASE_BUCKET = "strx-backup"
""", language="toml")

    st.markdown("""
3. 点击 **Save** → App 自动重启 → 云同步立即生效 ✅

**④ 首次同步**

App 重启后会自动：
- 拉取云端已有数据（如有）→ 合并到本地
- 等待下次修改收藏夹或扫描时 → 自动上传到云端

也可在「🚀 同步控制」Tab 手动触发立即同步。
    """)

    st.info("💡 Supabase 的 Storage bucket `strx-backup` 会在首次同步时**自动创建**，无需手动操作。")


# ════════════════════════════════════════════════════════════════════
# Tab2：同步控制
# ════════════════════════════════════════════════════════════════════
def _render_control(configured: bool):
    if not configured:
        st.warning("⚠️ 请先完成「配置教程」中的 Secrets 设置后，再使用此功能。")
        return

    st.markdown("### 🚀 手动同步操作")

    col_up, col_down = st.columns(2)

    with col_up:
        st.markdown(
            '<div style="background:#f0fdf4;border-radius:10px;padding:14px 16px;margin-bottom:8px">'
            '<b>⬆️ 上传到云端</b><br>'
            '<span style="color:#6b7280;font-size:12px">将本地所有数据推送到 Supabase</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬆️ 立即全量上传", type="primary", key="manual_push", use_container_width=True):
            with st.spinner("正在上传到 Supabase…"):
                results = cloud_sync.push_all()
            ok_count = sum(1 for v in results.values() if v is True)
            fail_count = sum(1 for v in results.values() if v is False)
            if fail_count == 0:
                st.success(f"✅ 上传成功！共 {ok_count} 个文件已同步到云端")
            else:
                st.warning(f"⚠️ 部分上传失败：成功 {ok_count} 个，失败 {fail_count} 个")
                for k, v in results.items():
                    if v is False:
                        st.error(f"  · {k} 上传失败")
            st.rerun()

    with col_down:
        st.markdown(
            '<div style="background:#eff6ff;border-radius:10px;padding:14px 16px;margin-bottom:8px">'
            '<b>⬇️ 从云端恢复</b><br>'
            '<span style="color:#6b7280;font-size:12px">将云端数据合并到本地（不覆盖本地独有数据）</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬇️ 立即从云端恢复", type="secondary", key="manual_pull", use_container_width=True):
            with st.spinner("正在从 Supabase 恢复数据…"):
                results = cloud_sync.pull_all()
            st.success("✅ 云端恢复完成")
            for k, (ok, msg) in results.items():
                if k.startswith("_"):
                    continue
                icon = "✅" if ok else "⚠️"
                st.markdown(f"{icon} **{k}**：{msg}")
            st.rerun()

    st.markdown("---")
    st.markdown("### 💾 分项同步")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⭐ 仅同步收藏夹", key="push_wl", use_container_width=True):
            with st.spinner("同步收藏夹…"):
                ok = cloud_sync.push_watchlist()
            st.success("✅ 收藏夹已同步" if ok else "❌ 同步失败")

    with c2:
        if st.button("📊 仅同步扫描记录", key="push_scan", use_container_width=True):
            import storage as loc
            with st.spinner("同步扫描记录…"):
                ok1 = cloud_sync._upload("scan_history", loc._load(loc.F_HIST,   []))
                ok2 = cloud_sync._upload("scan_results", loc._load(loc.F_ALLRES, []))
                ok3 = cloud_sync._upload("scan_groups",  loc.load_scanned_groups())
            st.success("✅ 扫描记录已同步" if (ok1 and ok2 and ok3) else "❌ 部分同步失败")

    with c3:
        if st.button("⚙️ 仅同步配置", key="push_cfg", use_container_width=True):
            import storage as loc
            with st.spinner("同步配置…"):
                ok = cloud_sync._upload("config", loc._load(loc.F_CFG, {}))
            st.success("✅ 配置已同步" if ok else "❌ 同步失败")

    st.markdown("---")
    st.markdown("### ⚠️ 危险操作")
    with st.expander("展开危险操作区", expanded=False):
        st.warning("以下操作不可撤销，请谨慎操作！")
        if st.button("🗑️ 清空云端所有数据", type="secondary", key="clear_cloud"):
            confirm = st.session_state.get("_clear_confirm", False)
            if not confirm:
                st.session_state["_clear_confirm"] = True
                st.rerun()
        if st.session_state.get("_clear_confirm"):
            st.error("⚠️ 确认要清空云端所有数据吗？此操作不可恢复！")
            if st.button("确认清空", type="primary", key="confirm_clear"):
                for key in cloud_sync._CLOUD_FILES:
                    try:
                        cloud_sync._upload(key, [] if key != "meta" and key != "config" else {})
                    except Exception:
                        pass
                st.session_state.pop("_clear_confirm", None)
                st.success("✅ 云端数据已清空")
                st.rerun()
            if st.button("取消", key="cancel_clear"):
                st.session_state.pop("_clear_confirm", None)
                st.rerun()


# ════════════════════════════════════════════════════════════════════
# Tab3：同步状态
# ════════════════════════════════════════════════════════════════════
def _render_status(configured: bool, status: dict):
    if not configured:
        st.info("配置 Supabase 后，此处将显示实时同步状态。")
        return

    st.markdown("### 📋 云端同步状态详情")

    # 刷新按钮
    col_r, _ = st.columns([2, 8])
    with col_r:
        if st.button("🔄 刷新状态", key="refresh_status"):
            st.rerun()

    if status.get("status") == "正常":
        elapsed_h = status.get("elapsed_h", 0)
        color = "#16a34a" if elapsed_h < 4 else "#d97706"
        st.markdown(f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
                    padding:16px 20px;margin:8px 0">
        <table style="font-size:13px;width:100%;border-collapse:collapse">
        <tr><td style="padding:5px 0;color:#6b7280;width:40%">☁️ 连接状态</td>
            <td style="color:#16a34a;font-weight:600">● 已连接</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">🕐 上次同步时间</td>
            <td style="font-weight:600">{status.get('last_sync', '—')}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⏱️ 距上次同步</td>
            <td style="color:{color};font-weight:600">{elapsed_h:.1f} 小时前</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⏳ 距下次自动同步</td>
            <td>{cloud_sync.time_to_next_sync_str()}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⭐ 云端收藏品种</td>
            <td><b>{status.get('watchlist_cnt', 0)}</b> 个</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">📊 云端扫描记录</td>
            <td><b>{status.get('scan_results_cnt', 0):,}</b> 条</td></tr>
        </table>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning(f"⚠️ 状态：{status.get('status', '未知')}  — 请检查 Supabase 配置或手动触发一次同步")

    st.markdown("### 📁 本地数据概览")
    wl_items  = storage.load_watchlist()
    wl_arch   = storage.load_watchlist_archive()
    sessions  = storage.load_sessions(limit=5)
    scanned_g = storage.load_scanned_groups()

    import storage as loc
    allres = loc._load(loc.F_ALLRES, [])
    if not isinstance(allres, list):
        allres = []

    st.markdown(f"""
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
                padding:16px 20px;margin:8px 0">
    <table style="font-size:13px;width:100%;border-collapse:collapse">
    <tr><td style="padding:5px 0;color:#6b7280;width:40%">⭐ 当前收藏品种</td>
        <td><b>{len(wl_items)}</b> 个</td></tr>
    <tr><td style="padding:5px 0;color:#6b7280">🗂️ 已删除存档</td>
        <td><b>{len(wl_arch)}</b> 个</td></tr>
    <tr><td style="padding:5px 0;color:#6b7280">📊 本地扫描记录</td>
        <td><b>{len(allres):,}</b> 条</td></tr>
    <tr><td style="padding:5px 0;color:#6b7280">📅 扫描会话</td>
        <td><b>{len(sessions)}</b> 条（最近5条）</td></tr>
    <tr><td style="padding:5px 0;color:#6b7280">📦 已扫描品种组</td>
        <td><b>{len(scanned_g)}</b> 个</td></tr>
    </table>
    </div>
    """, unsafe_allow_html=True)

    # 自动同步说明
    st.markdown("""
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;
                padding:12px 16px;margin-top:12px;font-size:13px">
    <b>📅 自动同步触发时机</b><br>
    <table style="margin-top:8px;font-size:12px;width:100%">
    <tr><td>⭐ 修改收藏夹</td><td>→ <b>立即</b>上传到 Supabase</td></tr>
    <tr><td>📊 完成一次扫描</td><td>→ 如距上次同步 ≥ 4小时，<b>自动</b>全量上传</td></tr>
    <tr><td>🌐 每次访问 App</td><td>→ 如距上次同步 ≥ 4小时，<b>自动</b>全量上传</td></tr>
    <tr><td>🔄 App 重启/冷启动</td><td>→ 自动从云端<b>拉取恢复</b>所有数据</td></tr>
    </table>
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════════════════════
def _metric_card(label: str, value: str, color: str) -> str:
    colors = {
        "green": ("#f0fdf4", "#16a34a"),
        "blue":  ("#eff6ff", "#1d4ed8"),
        "teal":  ("#f0fdfa", "#0d9488"),
        "gray":  ("#f9fafb", "#4b5563"),
    }
    bg, fg = colors.get(color, ("#f9fafb", "#374151"))
    return (
        f'<div style="background:{bg};border-radius:10px;padding:14px 16px;'
        f'text-align:center;margin-bottom:8px">'
        f'<div style="font-size:11px;color:#6b7280">{label}</div>'
        f'<div style="font-size:18px;font-weight:700;color:{fg};margin-top:4px">{value}</div>'
        f'</div>'
    )
