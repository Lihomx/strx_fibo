"""
page_cloud.py — ☁️ 云端同步管理
"""
import time
import streamlit as st
import storage
import cloud_sync


def render():
    st.markdown("## ☁️ 云端自动同步")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '使用 <b>Supabase</b>（免费永不过期）自动备份所有数据，重启后自动恢复。</p>',
        unsafe_allow_html=True,
    )

    configured = cloud_sync.is_configured()
    status     = cloud_sync.get_sync_status() if configured else {}

    # ── 状态卡片 ─────────────────────────────────────────────────
    if configured:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(_card("☁️ 云端状态",    "已连接",
                          status.get("last_sync","—"), "green"), unsafe_allow_html=True)
        c2.markdown(_card("🕐 上次同步",    status.get("last_sync","—"),
                          "", "blue"), unsafe_allow_html=True)
        c3.markdown(_card("⏱️ 距下次同步",  cloud_sync.time_to_next_sync_str(),
                          "", "gray"), unsafe_allow_html=True)
        c4.markdown(_card("📊 云端扫描记录", f"{status.get('scan_results_cnt',0):,} 条",
                          "", "teal"), unsafe_allow_html=True)
    else:
        st.warning("⚠️ 尚未配置 Supabase — 请查看「配置教程」Tab 完成设置")

    st.markdown("---")

    tab_setup, tab_ctrl, tab_stat = st.tabs(["🔧 配置教程", "🚀 同步控制", "📋 同步状态"])

    with tab_setup:
        _render_setup()
    with tab_ctrl:
        _render_control(configured)
    with tab_stat:
        _render_status(configured, status)


# ════════════════════════════════════════════════════════════════════
# 配置教程
# ════════════════════════════════════════════════════════════════════
def _render_setup():
    st.markdown("### 🔧 Supabase 配置步骤（5分钟，永久免费）")

    st.markdown("""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
                padding:14px 18px;margin-bottom:16px;font-size:13px">
    <b>✅ Supabase 免费层资源（永不过期，无需信用卡）</b><br><br>
    📦 文件存储 <b>1 GB</b> · 🗄️ 数据库 <b>500 MB</b> · 🔑 API 请求 <b>无限制</b>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
**① 注册并创建项目**
1. 打开 [supabase.com](https://supabase.com) → **Start your project**
2. GitHub 账号一键登录
3. **New project** → 填项目名（如 `strx-fibo`）→ 设置数据库密码 → 选区域 **Singapore**
4. 等待约 30 秒项目创建完成

**② 获取 API 凭证**
1. 左侧菜单 → **Project Settings**（齿轮图标）→ **API**
2. 复制两项：
   - **Project URL**（`https://xxxxxxxxxxxx.supabase.co`）
   - **anon / public** 下的 **API Key**（`eyJhbG...` 开头）

**③ 配置 Streamlit Secrets**
1. Streamlit Cloud → 你的 App → 右上角 **⋮** → **Settings** → **Secrets**
2. 追加以下内容（保留已有的 `APP_PASSWORD` 行）：
    """)

    st.code('''# Supabase 云同步（追加到现有 Secrets 内容之后）
SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
SUPABASE_BUCKET = "strx-backup"
''', language="toml")

    st.markdown("""
3. **Save** → App 自动重启 → 云同步立即生效

**④ 验证连接**：切换到「🚀 同步控制」Tab → 点击「🔌 测试 Supabase 连接」

> ✅ Bucket `strx-backup` 会**首次同步时自动创建**，无需手动操作。
    """)


# ════════════════════════════════════════════════════════════════════
# 同步控制
# ════════════════════════════════════════════════════════════════════
def _render_control(configured: bool):
    if not configured:
        st.warning("⚠️ 请先完成「配置教程」中的 Secrets 设置")
        return

    # 连接测试
    st.markdown("#### 🔌 第一步：测试连接")
    if st.button("🔌 测试 Supabase 连接", key="test_conn"):
        with st.spinner("连接测试中…"):
            ok, msg = cloud_sync._test_connection()
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.error(f"❌ {msg}")
            st.markdown("""
**排查建议：**
- `SUPABASE_URL` 格式须为 `https://xxxx.supabase.co`，不含尾部 `/`
- `SUPABASE_KEY` 使用 **anon public key**，不是 `service_role` key
- KEY 是单行字符串，Secrets 中不能有换行
            """)
    st.markdown("---")

    # 同步说明
    st.markdown("""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                padding:12px 16px;margin-bottom:14px;font-size:13px">
    <b>☁️ 同步内容</b><br>
    ⭐ <b>收藏夹</b>：品种代码、名称、所有备注（文字 + 图片链接 + 时间戳）<br>
    📊 <b>扫描记录</b>：Fibonacci 实时扫描 + 全量品种库的所有扫描结果<br>
    📦 <b>扫描组 & 配置</b>：已扫描品种组 + 系统配置
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 🔄 手动同步")
    col_up, col_dn = st.columns(2)

    with col_up:
        st.markdown(
            '<div style="background:#f0fdf4;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬆️ 上传到云端</b><br>'
            '<span style="font-size:12px;color:#6b7280">将本地所有数据推送到 Supabase</span>'
            '</div>', unsafe_allow_html=True)
        if st.button("⬆️ 立即全量上传", type="primary",
                     key="push_all", use_container_width=True):
            with st.spinner("上传中…"):
                res = cloud_sync.push_all()
            fails = [(k, m) for k, (ok, m) in res.items()
                     if isinstance(ok, bool) and not ok]
            if not fails:
                st.success(f"✅ 全量上传成功！{len(res)} 个文件已同步")
            else:
                st.warning(f"⚠️ 部分失败：")
                for k, m in fails:
                    st.error(f"  · {k}：{m}")
            st.rerun()

    with col_dn:
        st.markdown(
            '<div style="background:#eff6ff;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬇️ 从云端恢复</b><br>'
            '<span style="font-size:12px;color:#6b7280">将云端数据合并到本地（不覆盖本地独有数据）</span>'
            '</div>', unsafe_allow_html=True)
        if st.button("⬇️ 立即从云端恢复", type="secondary",
                     key="pull_all", use_container_width=True):
            with st.spinner("恢复中…"):
                res = cloud_sync.pull_all()
            st.success("✅ 云端恢复完成")
            for k, v in res.items():
                if not isinstance(v, tuple):
                    continue
                ok, msg = v
                st.markdown(f"{'✅' if ok else '⚠️'} **{k}**：{msg}")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 💾 分项同步")
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("⭐ 仅同步收藏夹", key="push_wl", use_container_width=True):
            with st.spinner("同步收藏夹（含备注/图片）…"):
                ok, msg = cloud_sync.push_watchlist()
            (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")

    with c2:
        if st.button("📊 仅同步扫描记录", key="push_scan", use_container_width=True):
            import storage as loc
            with st.spinner("同步扫描记录…"):
                ok1, m1 = cloud_sync._upload("scan_history", loc._load(loc.F_HIST,   []))
                ok2, m2 = cloud_sync._upload("scan_results", loc._load(loc.F_ALLRES, []))
                ok3, m3 = cloud_sync._upload("scan_groups",  loc.load_scanned_groups())
            if ok1 and ok2 and ok3:
                st.success("✅ 扫描记录已同步")
            else:
                st.error(f"❌ 部分失败：history={m1} / results={m2} / groups={m3}")

    with c3:
        if st.button("⚙️ 仅同步配置", key="push_cfg", use_container_width=True):
            import storage as loc
            with st.spinner("同步配置…"):
                ok, msg = cloud_sync._upload("config", loc._load(loc.F_CFG, {}))
            (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")

    st.markdown("---")
    with st.expander("⚠️ 危险操作", expanded=False):
        st.warning("清空云端数据后无法撤销！")
        if st.button("🗑️ 清空云端所有数据", key="clear_cloud_btn"):
            st.session_state["_confirm_clear"] = True
        if st.session_state.get("_confirm_clear"):
            st.error("确认清空云端所有数据？")
            col_y, col_n = st.columns(2)
            if col_y.button("确认清空", type="primary", key="confirm_clear_yes"):
                empty_data = {"watchlist": [], "watchlist_archive": [],
                              "scan_history": [], "scan_results": [],
                              "scan_groups": [], "config": {},
                              "meta": {"cleared": True}}
                for k, v in empty_data.items():
                    cloud_sync._upload(k, v)
                st.session_state.pop("_confirm_clear", None)
                st.success("✅ 云端数据已清空")
                st.rerun()
            if col_n.button("取消", key="confirm_clear_no"):
                st.session_state.pop("_confirm_clear", None)
                st.rerun()


# ════════════════════════════════════════════════════════════════════
# 同步状态
# ════════════════════════════════════════════════════════════════════
def _render_status(configured: bool, status: dict):
    if not configured:
        st.info("配置 Supabase 后，此处显示实时同步状态。")
        return

    if st.button("🔄 刷新状态", key="refresh_stat"):
        st.rerun()

    if status.get("status") == "正常":
        eh = status.get("elapsed_h", 0)
        color = "#16a34a" if eh < 4 else "#d97706"
        st.markdown(f"""
        <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
                    padding:16px 20px;margin:8px 0">
        <table style="font-size:13px;width:100%;border-collapse:collapse">
        <tr><td style="padding:5px 0;color:#6b7280;width:40%">☁️ 连接状态</td>
            <td style="color:#16a34a;font-weight:600">● 已连接</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">🕐 上次同步</td>
            <td style="font-weight:600">{status.get("last_sync","—")}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⏱️ 距上次</td>
            <td style="color:{color};font-weight:600">{eh:.1f} 小时前</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⏳ 距下次自动同步</td>
            <td>{cloud_sync.time_to_next_sync_str()}</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">⭐ 云端收藏品种</td>
            <td><b>{status.get("watchlist_cnt",0)}</b> 个</td></tr>
        <tr><td style="padding:5px 0;color:#6b7280">📊 云端扫描记录</td>
            <td><b>{status.get("scan_results_cnt",0):,}</b> 条</td></tr>
        </table></div>
        """, unsafe_allow_html=True)
    elif status.get("status") == "尚未同步":
        st.info("🕐 尚未完成首次同步，请在「同步控制」Tab 点击「立即全量上传」")
    else:
        st.warning(f"状态：{status.get('status','—')} — 请检查配置或手动触发同步")

    # 本地数据统计
    st.markdown("### 📁 本地数据概览")
    wl  = storage.load_watchlist()
    arch = storage.load_watchlist_archive()
    note_cnt = sum(len(i.get("notes", [])) for i in wl)
    img_cnt  = sum(1 for i in wl for n in i.get("notes", [])
                   if isinstance(n, dict) and n.get("img_url"))
    import storage as loc
    allres = loc._load(loc.F_ALLRES, []) or []

    st.markdown(f"""
    <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;
                padding:16px 20px;margin:8px 0">
    <table style="font-size:13px;width:100%;border-collapse:collapse">
    <tr><td style="padding:4px 0;color:#6b7280;width:45%">⭐ 收藏品种</td>
        <td><b>{len(wl)}</b> 个</td></tr>
    <tr><td style="padding:4px 0;color:#6b7280">📝 备注总数</td>
        <td><b>{note_cnt}</b> 条（含 {img_cnt} 个图片链接）</td></tr>
    <tr><td style="padding:4px 0;color:#6b7280">🗂️ 已删除存档</td>
        <td><b>{len(arch)}</b> 个</td></tr>
    <tr><td style="padding:4px 0;color:#6b7280">📊 本地扫描记录</td>
        <td><b>{len(allres):,}</b> 条</td></tr>
    </table></div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;
                padding:12px 16px;margin-top:12px;font-size:12px">
    <b>📅 自动同步时机</b><br>
    ⭐ 修改收藏夹 → <b>立即</b>推送到 Supabase<br>
    📊 完成一次扫描 → 如 ≥4h 未同步，<b>自动</b>全量上传<br>
    🌐 每次访问 App → 如 ≥4h 未同步，<b>自动</b>全量上传<br>
    🔄 App 冷启动 → 自动从云端<b>拉取恢复</b>所有数据
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════════════════════
def _card(label: str, value: str, sub: str, color: str) -> str:
    COLORS = {
        "green": ("#f0fdf4", "#16a34a"),
        "blue":  ("#eff6ff", "#1d4ed8"),
        "teal":  ("#f0fdfa", "#0d9488"),
        "gray":  ("#f9fafb", "#4b5563"),
    }
    bg, fg = COLORS.get(color, ("#f9fafb", "#374151"))
    return (
        f'<div style="background:{bg};border-radius:10px;padding:14px 12px;'
        f'text-align:center">'
        f'<div style="font-size:11px;color:#6b7280">{label}</div>'
        f'<div style="font-size:17px;font-weight:700;color:{fg};margin-top:4px">{value}</div>'
        f'</div>'
    )
