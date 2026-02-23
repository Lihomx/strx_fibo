"""
page_cloud.py — 云端同步管理
"""
import streamlit as st
import cloud_sync


def render():
    st.markdown("## ☁️ 云端自动同步")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '使用 Supabase（免费永不过期）自动备份所有数据，重启后自动恢复。</p>',
        unsafe_allow_html=True,
    )

    configured = cloud_sync.is_configured()
    status     = cloud_sync.get_sync_status() if configured else {}

    if configured:
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(_card("云端状态",   "已连接",                                  "green"), unsafe_allow_html=True)
        c2.markdown(_card("上次同步",   status.get("last_sync", "—"),              "blue"),  unsafe_allow_html=True)
        c3.markdown(_card("距下次同步", cloud_sync.time_to_next_sync_str(),         "gray"),  unsafe_allow_html=True)
        c4.markdown(_card("云端记录",   str(status.get("scan_results_cnt", 0)) + " 条", "teal"), unsafe_allow_html=True)
    else:
        st.warning("尚未配置 Supabase — 请查看配置教程完成设置")

    st.markdown("---")
    tab_a, tab_b, tab_c = st.tabs(["🔧 配置教程", "🚀 同步控制", "📋 同步状态"])
    with tab_a:
        _setup()
    with tab_b:
        _control(configured)
    with tab_c:
        _status_tab(configured, status)


def _setup():
    st.markdown("### Supabase 配置教程（约5分钟，永久免费）")
    st.error(
        "重要：必须使用 service_role key，不能用 anon key\n\n"
        "Supabase 默认开启 RLS（行级安全策略），anon key 无权限操作 Storage bucket，"
        "会报 403 错误。service_role key 可绕过 RLS。"
    )
    st.markdown("---")
    st.markdown(
        "**第一步：注册并创建项目**\n"
        "1. 打开 supabase.com → Start your project → GitHub 登录\n"
        "2. New project → 项目名 strx-fibo → 设密码 → 区域选 Singapore → Create\n"
        "3. 等待约 30 秒\n\n"
        "**第二步：获取 service_role key（重要！）**\n"
        "1. 左侧菜单 → Project Settings（齿轮图标）→ API\n"
        "2. 复制 Project URL（格式：https://xxxx.supabase.co）\n"
        "3. 找到 service_role → 点击 Reveal → 复制这个 key\n"
        "4. 不要用 anon/public key，那个 key 会报 403 RLS 错误\n\n"
        "**第三步：配置 Streamlit Secrets**\n"
        "Streamlit Cloud → 你的 App → 右上角 ⋮ → Settings → Secrets → 追加以下内容："
    )
    st.code(
        "# 追加到 Secrets（APP_PASSWORD 那行不要删）\n"
        'SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"\n'
        'SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."\n'
        'SUPABASE_BUCKET = "strx-backup"',
        language="toml",
    )
    st.markdown(
        "SUPABASE_KEY 填写 service_role secret key（以 eyJhbG 开头的长字符串）\n\n"
        "**第四步：保存并验证**\n"
        "1. 点 Save → App 自动重启\n"
        "2. 切换到「同步控制」Tab → 点击「测试 Supabase 连接」\n"
        "3. 看到 连接成功 → 点「立即全量上传」完成首次备份\n\n"
        "Bucket strx-backup 会在首次同步时自动创建，无需手动操作。"
    )


def _control(configured):
    if not configured:
        st.warning("请先完成配置教程中的 Secrets 设置")
        return

    st.markdown("#### 第一步：测试连接")
    if st.button("🔌 测试 Supabase 连接", key="test_conn"):
        with st.spinner("测试中…"):
            ok, msg = cloud_sync._test_connection()
        if ok:
            st.success("✅ " + msg)
        else:
            st.error("❌ " + msg)
            with st.expander("解决方案", expanded=True):
                st.markdown(
                    "**报 403 / RLS 错误：**\n"
                    "- 请改用 service_role secret key（不是 anon key）\n"
                    "- 路径：Supabase → Project Settings → API → service_role → Reveal\n\n"
                    "**报 401 Unauthorized：**\n"
                    "- KEY 填写错误，请重新完整复制\n\n"
                    "**报网络错误：**\n"
                    "- 检查 SUPABASE_URL 格式（https://xxxx.supabase.co，末尾无斜杠）"
                )

    st.markdown("---")
    st.markdown("#### 手动同步")
    col_up, col_dn = st.columns(2)

    with col_up:
        st.markdown(
            '<div style="background:#f0fdf4;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬆️ 上传到云端</b><br>'
            '<span style="font-size:12px;color:#6b7280">将本地所有数据推送到 Supabase</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬆️ 立即全量上传", type="primary", key="push_all", use_container_width=True):
            with st.spinner("上传中…"):
                res = cloud_sync.push_all()
            fails = [(k, m) for k, (ok, m) in res.items() if isinstance(ok, bool) and not ok]
            if not fails:
                st.success("✅ 全量上传成功！" + str(len(res)) + " 个文件已同步")
            else:
                for k, m in fails:
                    st.error("❌ " + k + "：" + m)
            st.rerun()

    with col_dn:
        st.markdown(
            '<div style="background:#eff6ff;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬇️ 从云端恢复</b><br>'
            '<span style="font-size:12px;color:#6b7280">将云端数据合并到本地（不覆盖本地独有数据）</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬇️ 立即从云端恢复", type="secondary", key="pull_all", use_container_width=True):
            with st.spinner("恢复中…"):
                res = cloud_sync.pull_all()
            st.success("✅ 云端恢复完成")
            for k, v in res.items():
                if isinstance(v, tuple):
                    ok, msg = v
                    icon = "✅" if ok else "⚠️"
                    st.markdown(icon + " **" + k + "**：" + msg)
            st.rerun()

    st.markdown("---")
    st.markdown("#### 分项同步")
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("⭐ 仅同步收藏夹", key="push_wl", use_container_width=True):
            with st.spinner("同步收藏夹…"):
                ok, msg = cloud_sync.push_watchlist()
            (st.success if ok else st.error)(("✅ " if ok else "❌ ") + msg)

    with c2:
        if st.button("📊 仅同步扫描记录", key="push_scan", use_container_width=True):
            import storage as loc
            with st.spinner("同步扫描记录…"):
                r1 = cloud_sync._upload("scan_history", loc._load(loc.F_HIST,   []))
                r2 = cloud_sync._upload("scan_results", loc._load(loc.F_ALLRES, []))
                r3 = cloud_sync._upload("scan_groups",  loc.load_scanned_groups())
            all_ok = all(o for o, _ in [r1, r2, r3])
            (st.success if all_ok else st.error)("✅ 扫描记录已同步" if all_ok else "❌ 部分失败：" + r1[1])

    with c3:
        if st.button("⚙️ 仅同步配置", key="push_cfg", use_container_width=True):
            import storage as loc
            with st.spinner("同步配置…"):
                ok, msg = cloud_sync._upload("config", loc._load(loc.F_CFG, {}))
            (st.success if ok else st.error)("✅ 配置已同步" if ok else "❌ " + msg)

    st.markdown("---")
    with st.expander("⚠️ 危险操作", expanded=False):
        st.warning("清空云端数据后无法恢复！")
        if st.button("🗑️ 清空云端所有数据", key="clear_btn"):
            st.session_state["_confirm_clear"] = True
        if st.session_state.get("_confirm_clear"):
            st.error("确认清空？此操作不可撤销")
            cy, cn = st.columns(2)
            if cy.button("确认清空", type="primary", key="confirm_yes"):
                for k in cloud_sync._CLOUD_FILES:
                    cloud_sync._upload(k, [] if k not in ("meta", "config") else {})
                st.session_state.pop("_confirm_clear", None)
                st.success("✅ 已清空")
                st.rerun()
            if cn.button("取消", key="confirm_no"):
                st.session_state.pop("_confirm_clear", None)
                st.rerun()


def _status_tab(configured, status):
    if not configured:
        st.info("配置 Supabase 后显示实时状态。")
        return

    if st.button("🔄 刷新状态", key="refresh_stat"):
        st.rerun()

    if status.get("status") == "正常":
        eh = status.get("elapsed_h", 0)
        color = "#16a34a" if eh < 4 else "#d97706"
        last_sync = status.get("last_sync", "—")
        wl_cnt    = status.get("watchlist_cnt", 0)
        res_cnt   = status.get("scan_results_cnt", 0)
        next_sync = cloud_sync.time_to_next_sync_str()
        st.markdown(
            '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;'
            'padding:16px 20px;margin:8px 0">'
            '<table style="font-size:13px;width:100%;border-collapse:collapse">'
            '<tr><td style="padding:5px 0;color:#6b7280;width:40%">☁️ 连接状态</td>'
            '<td style="color:#16a34a;font-weight:600">● 已连接</td></tr>'
            f'<tr><td style="padding:5px 0;color:#6b7280">🕐 上次同步</td>'
            f'<td style="font-weight:600">{last_sync}</td></tr>'
            f'<tr><td style="padding:5px 0;color:#6b7280">⏱️ 距上次</td>'
            f'<td style="color:{color};font-weight:600">{eh:.1f} 小时前</td></tr>'
            f'<tr><td style="padding:5px 0;color:#6b7280">⏳ 下次自动同步</td>'
            f'<td>{next_sync}</td></tr>'
            f'<tr><td style="padding:5px 0;color:#6b7280">⭐ 云端收藏品种</td>'
            f'<td><b>{wl_cnt}</b> 个</td></tr>'
            f'<tr><td style="padding:5px 0;color:#6b7280">📊 云端扫描记录</td>'
            f'<td><b>{res_cnt:,}</b> 条</td></tr>'
            '</table></div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("状态：" + status.get("status", "—") + " — 请在同步控制 Tab 完成首次上传")

    st.markdown("### 本地数据概览")
    import storage as loc
    wl     = loc.load_watchlist()
    arch   = loc.load_watchlist_archive()
    allres = loc._load(loc.F_ALLRES, []) or []
    note_c = sum(len(i.get("notes", [])) for i in wl)
    img_c  = sum(1 for i in wl for n in i.get("notes", [])
                 if isinstance(n, dict) and n.get("img_url"))
    st.markdown(
        '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;'
        'padding:14px 18px;margin:8px 0">'
        '<table style="font-size:13px;width:100%;border-collapse:collapse">'
        f'<tr><td style="padding:4px 0;color:#6b7280;width:45%">⭐ 收藏品种</td>'
        f'<td><b>{len(wl)}</b> 个</td></tr>'
        f'<tr><td style="padding:4px 0;color:#6b7280">📝 备注 / 图片</td>'
        f'<td><b>{note_c}</b> 条（含 {img_c} 个图片链接）</td></tr>'
        f'<tr><td style="padding:4px 0;color:#6b7280">🗂️ 已删除存档</td>'
        f'<td><b>{len(arch)}</b> 个</td></tr>'
        f'<tr><td style="padding:4px 0;color:#6b7280">📊 本地扫描记录</td>'
        f'<td><b>{len(allres):,}</b> 条</td></tr>'
        '</table></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;'
        'padding:12px 16px;margin-top:10px;font-size:12px">'
        '<b>自动同步时机</b><br>'
        '⭐ 修改收藏夹 → 立即推送到 Supabase<br>'
        '📊 完成扫描 / 每次访问 App → 如距上次 ≥4h 则自动全量上传<br>'
        '🔄 App 冷启动重启 → 自动从云端拉取恢复所有数据'
        '</div>',
        unsafe_allow_html=True,
    )


def _card(label, value, color):
    COLORS = {
        "green": ("#f0fdf4", "#16a34a"),
        "blue":  ("#eff6ff", "#1d4ed8"),
        "teal":  ("#f0fdfa", "#0d9488"),
        "gray":  ("#f9fafb", "#4b5563"),
    }
    bg, fg = COLORS.get(color, ("#f9fafb", "#374151"))
    return (
        '<div style="background:' + bg + ';border-radius:10px;padding:14px 12px;text-align:center">'
        '<div style="font-size:11px;color:#6b7280">' + label + '</div>'
        '<div style="font-size:17px;font-weight:700;color:' + fg + ';margin-top:4px">' + value + '</div>'
        '</div>'
    )
