"""
page_cloud.py — 云端同步管理 v6
"""
import time
import streamlit as st
import cloud_sync


def render():
    st.markdown("## ☁️ 云端同步")
    st.markdown(
        '<p style="color:#6b7280;font-size:13px;margin-top:-8px">'
        '使用 Supabase（免费永不过期）手动备份所有数据，重启后自动恢复。</p>',
        unsafe_allow_html=True,
    )

    configured = cloud_sync.is_configured()
    status     = cloud_sync.get_sync_status() if configured else {}

    if configured:
        c1, c2, c3 = st.columns(3)
        c1.markdown(_card("云端状态", "✅ 已连接",                          "green"), unsafe_allow_html=True)
        c2.markdown(_card("上次同步", status.get("last_sync", "—"),         "blue"),  unsafe_allow_html=True)
        c3.markdown(_card("云端收藏", f"{status.get('watchlist_cnt',0)} 个", "teal"),  unsafe_allow_html=True)
    else:
        st.warning("⚠️ 尚未配置 Supabase — 请查看配置教程完成设置")

    st.markdown("---")
    tab_a, tab_b, tab_c, tab_d = st.tabs(
        ["🔧 配置教程", "🚀 同步控制", "📦 历史快照", "📋 同步状态"]
    )
    with tab_a:
        _setup()
    with tab_b:
        _control(configured)
    with tab_c:
        _snapshots(configured)
    with tab_d:
        _status_tab(configured, status)


# ════════════════════════════════════════════════════════════════════
# 配置教程
# ════════════════════════════════════════════════════════════════════
def _setup():
    st.markdown("### Supabase 配置教程（约5分钟，永久免费）")
    st.error(
        "重要：必须使用 **service_role key**，不能用 anon key\n\n"
        "Supabase 默认开启 RLS（行级安全策略），anon key 无权限操作 Storage，"
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
        "3. 找到 **service_role** → 点击 Reveal → 复制这个 key\n"
        "4. ⚠️ 不要用 anon/public key，那个会报 403 RLS 错误\n\n"
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
        "SUPABASE_KEY 填写 **service_role secret key**（以 eyJhbG 开头的长字符串）\n\n"
        "**第四步：保存并验证**\n"
        "1. 点 Save → App 自动重启\n"
        "2. 切换到「同步控制」Tab → 点击「测试 Supabase 连接」\n"
        "3. 看到 连接成功 → 点「立即全量上传」完成首次备份\n\n"
        "Bucket strx-backup 会在首次同步时自动创建，无需手动操作。\n\n"
        "**备份策略说明**\n"
        "- 每次手动上传都会在 `backups/` 目录创建带时间戳的新快照文件（不覆盖旧文件）\n"
        "- `latest/` 目录始终保存最新版本，供 App 重启时自动恢复\n"
        "- 文件名格式：`watchlist_20250115_143022_2048B.json`（含大小和时间戳）\n"
        "- 可在「历史快照」Tab 查看和恢复任意历史版本"
    )


# ════════════════════════════════════════════════════════════════════
# 同步控制
# ════════════════════════════════════════════════════════════════════
def _control(configured):
    if not configured:
        st.warning("请先完成配置教程中的 Secrets 设置")
        return

    # ── 测试连接 ────────────────────────────────────────────────
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

    # ── 手动同步 ────────────────────────────────────────────────
    st.markdown("#### 手动同步")
    st.markdown(
        '<div class="n-info" style="background:#fefce8;border:1px solid #fde047;'
        'border-radius:8px;padding:10px 14px;font-size:12px;margin-bottom:12px">'
        '💡 <b>每次上传都会自动创建新快照</b>（不覆盖旧文件），可在「历史快照」Tab 查看和恢复任意版本。'
        '</div>',
        unsafe_allow_html=True,
    )

    col_up, col_dn = st.columns(2)
    with col_up:
        st.markdown(
            '<div style="background:#f0fdf4;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬆️ 上传到云端</b><br>'
            '<span style="font-size:12px;color:#6b7280">推送所有数据 + 创建历史快照</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬆️ 立即全量上传", type="primary", key="push_all", use_container_width=True):
            with st.spinner("上传中…"):
                ok, msg = cloud_sync.push_all()
            (st.success if ok else st.error)(("✅ " if ok else "❌ ") + msg)
            if ok:
                st.rerun()

    with col_dn:
        st.markdown(
            '<div style="background:#eff6ff;border-radius:10px;padding:12px 14px;margin-bottom:6px">'
            '<b>⬇️ 从云端恢复</b><br>'
            '<span style="font-size:12px;color:#6b7280">从最新版本合并到本地（不覆盖本地独有数据）</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("⬇️ 立即从云端恢复", type="secondary", key="pull_all", use_container_width=True):
            with st.spinner("恢复中…"):
                res = cloud_sync.pull_all()
            st.success("✅ 云端恢复完成")
            for k, v in res.items():
                if isinstance(v, tuple):
                    ok2, msg2 = v
                    st.markdown(("✅" if ok2 else "⚠️") + f" **{k}**：{msg2}")
            st.rerun()

    st.markdown("---")

    # ── 分项同步 ────────────────────────────────────────────────
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
                r1 = cloud_sync._upload_latest("scan_history", loc._load(loc.F_HIST,   []))
                r2 = cloud_sync._upload_latest("scan_results", loc._load(loc.F_ALLRES, []))
                r3 = cloud_sync._upload_latest("scan_groups",  loc.load_scanned_groups())
            all_ok = all(o for o, _ in [r1, r2, r3])
            (st.success if all_ok else st.error)(
                "✅ 扫描记录已同步" if all_ok else f"❌ 部分失败：{r1[1]}"
            )

    with c3:
        if st.button("⚙️ 仅同步配置", key="push_cfg", use_container_width=True):
            import storage as loc
            with st.spinner("同步配置…"):
                ok, msg = cloud_sync._upload_latest("config", loc._load(loc.F_CFG, {}))
            (st.success if ok else st.error)("✅ 配置已同步" if ok else f"❌ {msg}")


# ════════════════════════════════════════════════════════════════════
# 历史快照 Tab（原"危险操作"改为此）
# ════════════════════════════════════════════════════════════════════
def _snapshots(configured):
    if not configured:
        st.info("配置 Supabase 后可使用历史快照功能。")
        return

    st.markdown("### 📦 历史快照管理")
    st.markdown(
        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
        'padding:10px 14px;font-size:13px;margin-bottom:12px">'
        '每次上传都会在云端 <code>backups/</code> 目录创建新快照（不覆盖旧文件）。'
        '文件名包含时间戳和大小，可恢复任意历史版本。'
        '</div>',
        unsafe_allow_html=True,
    )

    col_refresh, col_spacer = st.columns([2, 6])
    with col_refresh:
        if st.button("🔄 刷新快照列表", key="refresh_snaps", use_container_width=True):
            st.rerun()

    with st.spinner("加载快照列表…"):
        snapshots = cloud_sync.list_backup_snapshots()

    if not snapshots:
        st.info("暂无历史快照。请先点击「立即全量上传」创建第一个快照。")
        return

    # 按 file_key 分组显示
    from collections import defaultdict
    by_key = defaultdict(list)
    for s in snapshots:
        by_key[s["file_key"]].append(s)

    # 关键文件优先显示
    KEY_PRIORITY = ["watchlist", "wl_categories", "watchlist_archive", "config"]
    all_keys = KEY_PRIORITY + [k for k in by_key if k not in KEY_PRIORITY]

    KEY_LABELS = {
        "watchlist":         "⭐ 收藏夹",
        "wl_categories":     "🏷️ 分类",
        "watchlist_archive": "🗂️ 存档",
        "config":            "⚙️ 配置",
    }

    for fk in all_keys:
        if fk not in by_key:
            continue
        snaps = by_key[fk]
        label = KEY_LABELS.get(fk, f"📄 {fk}")

        with st.expander(
            f"{label}  —  共 {len(snaps)} 个快照  "
            f"（最新：{snaps[0]['ts_str']}）",
            expanded=(fk == "watchlist"),
        ):
            for i, snap in enumerate(snaps):
                is_newest = (i == 0)
                age_days  = (time.time() - snap["ts_epoch"]) / 86400 if snap["ts_epoch"] > 0 else 0
                too_old   = age_days > 30

                col_info, col_restore = st.columns([7, 2])
                with col_info:
                    age_str = f"{int(age_days)}天前" if snap["ts_epoch"] > 0 else "时间未知"
                    newest_badge = ' <span style="background:#dcfce7;color:#16a34a;font-size:10px;padding:1px 6px;border-radius:8px">最新</span>' if is_newest else ""
                    old_badge    = ' <span style="background:#fef9c3;color:#92400e;font-size:10px;padding:1px 6px;border-radius:8px">可清理</span>' if too_old and not is_newest else ""
                    st.markdown(
                        f'<div style="font-size:13px;padding:4px 0">'
                        f'<span style="font-family:monospace;color:#374151">{snap["ts_str"]}</span>'
                        f'  <span style="color:#9ca3af;font-size:11px">{snap["size_label"]} · {age_str}</span>'
                        f'{newest_badge}{old_badge}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with col_restore:
                    if fk in ("watchlist", "wl_categories", "watchlist_archive", "config"):
                        if st.button(
                            "⬇️ 恢复此版本",
                            key=f"restore_{snap['path'].replace('/','_')}",
                            help=f"将本地 {label} 替换为此快照版本",
                            use_container_width=True,
                        ):
                            st.session_state[f"_confirm_restore_{snap['path']}"] = True

                # 恢复确认对话框
                confirm_key = f"_confirm_restore_{snap['path']}"
                if st.session_state.get(confirm_key):
                    st.warning(
                        f"⚠️ 确认用 **{snap['ts_str']}** 的快照覆盖本地 {label}？\n"
                        f"（此操作会替换本地当前数据，建议先上传备份）"
                    )
                    cy, cn = st.columns(2)
                    if cy.button("✅ 确认恢复", key=f"yes_restore_{snap['path']}", type="primary"):
                        with st.spinner("恢复中…"):
                            ok, msg = cloud_sync.restore_from_snapshot(snap["path"], fk)
                        st.session_state.pop(confirm_key, None)
                        (st.success if ok else st.error)(("✅ " if ok else "❌ ") + msg)
                        if ok:
                            st.rerun()
                    if cn.button("取消", key=f"no_restore_{snap['path']}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()

    # ── 清理旧快照（只删1个月前的）────────────────────────────
    st.markdown("---")
    st.markdown("#### 🗑️ 清理旧快照")
    st.markdown(
        '<div style="background:#fefce8;border:1px solid #fde047;border-radius:8px;'
        'padding:10px 14px;font-size:13px;margin-bottom:10px">'
        '⚠️ <b>安全清理</b>：只删除 <b>30天前</b> 的旧快照。<br>'
        '每个文件类型的<b>最新快照永远不会被删除</b>，确保随时可以恢复最新版本。'
        '</div>',
        unsafe_allow_html=True,
    )

    # 统计可清理数量
    now = time.time()
    cutoff = now - 30 * 86400
    from collections import defaultdict as _dd
    by_key2 = _dd(list)
    for s in snapshots:
        by_key2[s["file_key"]].append(s)

    deletable = []
    for fk, snaps in by_key2.items():
        for i, s in enumerate(snaps):
            if i > 0 and s["ts_epoch"] > 0 and s["ts_epoch"] < cutoff:
                deletable.append(s)

    st.markdown(
        f'当前共 **{len(snapshots)}** 个快照 | '
        f'30天前的旧快照：**{len(deletable)}** 个（可清理）| '
        f'最新快照（受保护）：**{len(snapshots) - len(deletable)}** 个'
    )

    if not deletable:
        st.info("✅ 没有超过30天的旧快照，无需清理。")
        return

    if st.button(
        f"🗑️ 清理 {len(deletable)} 个30天前的旧快照",
        key="clean_old_btn",
        help="只删除30天前的旧快照，最新快照不会被删除",
    ):
        st.session_state["_confirm_clean_old"] = True

    if st.session_state.get("_confirm_clean_old"):
        st.warning(
            f"确认删除 **{len(deletable)} 个**超过30天的旧快照？\n\n"
            f"每个文件类型的最新快照不会被删除，可随时恢复最新版本。"
        )
        cy2, cn2 = st.columns(2)
        if cy2.button("✅ 确认清理旧快照", key="clean_old_yes", type="primary"):
            with st.spinner("清理中…"):
                deleted, skipped, errors = cloud_sync.delete_old_snapshots(days=30)
            st.session_state.pop("_confirm_clean_old", None)
            if errors:
                st.warning(f"⚠️ 已删 {deleted} 个，{len(errors)} 个失败：{errors[0]}")
            else:
                st.success(f"✅ 已清理 {deleted} 个旧快照，保留 {skipped} 个（含最新版本）")
            st.rerun()
        if cn2.button("取消", key="clean_old_no"):
            st.session_state.pop("_confirm_clean_old", None)
            st.rerun()


# ════════════════════════════════════════════════════════════════════
# 状态 Tab
# ════════════════════════════════════════════════════════════════════
def _status_tab(configured, status):
    if not configured:
        st.info("配置 Supabase 后显示实时状态。")
        return

    if st.button("🔄 刷新状态", key="refresh_stat"):
        st.rerun()

    if status.get("status") == "正常":
        eh        = status.get("elapsed_h", 0)
        color     = "#16a34a" if eh < 4 else "#d97706"
        last_sync = status.get("last_sync", "—")
        wl_cnt    = status.get("watchlist_cnt", 0)
        res_cnt   = status.get("scan_results_cnt", 0)
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
        '<b>同步说明</b><br>'
        '⬆️ 点击「立即全量上传」→ 推送所有数据 + 创建历史快照<br>'
        '🔄 App 冷启动重启 → 自动从 latest/ 拉取恢复所有数据<br>'
        '📦 每次备份均创建新快照文件（不覆盖），可在「历史快照」Tab 查看'
        '</div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 卡片组件
# ════════════════════════════════════════════════════════════════════
def _card(label, value, color):
    COLORS = {
        "green": ("#f0fdf4", "#16a34a"),
        "blue":  ("#eff6ff", "#1d4ed8"),
        "teal":  ("#f0fdfa", "#0d9488"),
        "gray":  ("#f9fafb", "#4b5563"),
    }
    bg, fg = COLORS.get(color, ("#f9fafb", "#374151"))
    return (
        f'<div style="background:{bg};border-radius:10px;padding:14px 12px;text-align:center">'
        f'<div style="font-size:11px;color:#6b7280">{label}</div>'
        f'<div style="font-size:16px;font-weight:700;color:{fg};margin-top:4px">{value}</div>'
        f'</div>'
    )
