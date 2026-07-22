"""
page_cloud.py - Cloud sync management page
"""

import time
from collections import defaultdict

import streamlit as st

import cloud_sync


def render() -> None:
    st.markdown("## ☁️ 云端同步")
    st.caption("使用 Supabase 进行手动备份与恢复，应用重启后可从云端恢复。")

    configured = cloud_sync.is_configured()
    status = cloud_sync.get_sync_status() if configured else {}

    if configured:
        c1, c2, c3 = st.columns(3)
        c1.metric("云端状态", "已连接")
        c2.metric("上次同步", status.get("last_sync", "-"))
        c3.metric("云端收藏", int(status.get("watchlist_cnt", 0)))
    else:
        st.warning("未检测到 Supabase 配置，请先在 Secrets 中配置 SUPABASE_URL / SUPABASE_KEY / SUPABASE_BUCKET。")

    st.divider()
    tab_setup, tab_control, tab_snaps, tab_status = st.tabs([
        "🔧 配置教程",
        "🚀 同步控制",
        "📦 历史快照",
        "📋 同步状态",
    ])

    with tab_setup:
        _setup_help()
    with tab_control:
        _control(configured)
    with tab_snaps:
        _snapshots(configured)
    with tab_status:
        _status_tab(configured)


def _setup_help() -> None:
    st.markdown("### Supabase 配置")
    st.info("需要使用 service_role key，不能使用 anon/public key。")
    st.code(
        'SUPABASE_URL = "https://xxxx.supabase.co"\n'
        'SUPABASE_KEY = "eyJ..."\n'
        'SUPABASE_BUCKET = "strx-backup"',
        language="toml",
    )


def _control(configured: bool) -> None:
    if not configured:
        st.warning("请先完成 Supabase 配置。")
        return

    st.markdown("### 连接测试")
    if st.button("测试 Supabase 连接", key="test_conn"):
        with st.spinner("测试中..."):
            ok, msg = cloud_sync._test_connection()
        (st.success if ok else st.error)(msg)

    st.divider()
    st.markdown("### 全量同步")

    force_push = st.checkbox(
        "强制覆盖上传（绕过安全保护）",
        key="force_push_all",
        value=False,
        help="仅在你确认本地数据正确时使用。",
    )
    if force_push:
        st.warning("强制模式会跳过空数据/骤减保护，可能覆盖云端历史数据。")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⬆️ 立即全量上传", type="primary", key="push_all", use_container_width=True):
            with st.spinner("上传中..."):
                ok, msg = cloud_sync.push_all(force=force_push)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    with c2:
        if st.button("⬇️ 从云端恢复", key="pull_all", use_container_width=True):
            with st.spinner("恢复中..."):
                res = cloud_sync.pull_all()
            st.success("恢复完成")
            for k, v in res.items():
                if isinstance(v, tuple):
                    ok, msg = v
                    st.markdown(("✅" if ok else "⚠️") + f" **{k}**: {msg}")
            st.rerun()

    st.divider()
    st.markdown("### 分项同步")
    d1, d2, d3 = st.columns(3)

    with d1:
        if st.button("⭐ 仅同步收藏夹", key="push_wl", use_container_width=True):
            with st.spinner("同步收藏夹..."):
                ok, msg = cloud_sync.push_watchlist(force=False)
            (st.success if ok else st.error)(msg)

    with d2:
        if st.button("📈 仅同步扫描与告警记录", key="push_scan", use_container_width=True):
            import storage as loc

            with st.spinner("同步扫描与告警记录..."):
                r1 = cloud_sync._upload_latest("scan_history", loc._load(loc.F_HIST, []))
                r2 = cloud_sync._upload_latest("scan_results", loc._load(loc.F_ALLRES, []))
                r3 = cloud_sync._upload_latest("scan_groups", loc.load_scanned_groups())
                r4 = cloud_sync._upload_latest("alerts", loc._load(loc.F_ALERTS, []))
                cloud_sync._upload_snapshot("alerts", loc._load(loc.F_ALERTS, []))
                r5 = cloud_sync._upload_latest("starred", loc._load(loc.F_STARRED, []))
                cloud_sync._upload_snapshot("starred", loc._load(loc.F_STARRED, []))
                r6 = cloud_sync._upload_latest("ticker_notes", loc._load(loc.F_TICKER_NOTES, {}))
                cloud_sync._upload_snapshot("ticker_notes", loc._load(loc.F_TICKER_NOTES, {}))
            all_ok = all(ok for ok, _ in [r1, r2, r3, r4, r5, r6])
            (st.success if all_ok else st.error)("扫描/告警/关注/备注同步完成" if all_ok else f"部分失败: {r1[1]}")

    with d3:
        if st.button("⚙️ 仅同步配置", key="push_cfg", use_container_width=True):
            import storage as loc

            with st.spinner("同步配置..."):
                ok, msg = cloud_sync._upload_latest("config", loc._load(loc.F_CFG, {}))
            (st.success if ok else st.error)("配置同步完成" if ok else msg)


def _snapshots(configured: bool) -> None:
    if not configured:
        st.info("配置 Supabase 后可查看历史快照。")
        return

    st.markdown("### 历史快照")
    snaps = cloud_sync.list_backup_snapshots()
    if not snaps:
        st.info("暂无历史快照。")
        return

    groups = defaultdict(list)
    for s in snaps:
        groups[s.get("file_key", "unknown")].append(s)

    key_order = ["watchlist", "wl_categories", "watchlist_archive", "config"]
    sorted_keys = key_order + [k for k in groups.keys() if k not in key_order]

    for fk in sorted_keys:
        if fk not in groups:
            continue
        rows = groups[fk]
        with st.expander(f"{fk} - {len(rows)} 个快照（最新：{rows[0].get('ts_str', '-')})", expanded=(fk == "watchlist")):
            for i, snap in enumerate(rows[:200]):
                is_newest = i == 0
                age_days = int((time.time() - snap.get("ts_epoch", 0)) / 86400) if snap.get("ts_epoch", 0) > 0 else -1
                age_text = f"{age_days}天前" if age_days >= 0 else "时间未知"
                label = f"{snap.get('ts_str', '-')}  {snap.get('size_label', '?')}  {age_text}"

                c_info, c_btn = st.columns([7, 2])
                c_info.write(("最新 · " if is_newest else "") + label)
                if c_btn.button("恢复", key=f"restore_{fk}_{i}", use_container_width=True):
                    with st.spinner("恢复中..."):
                        ok, msg = cloud_sync.restore_from_snapshot(snap["path"], fk)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

    st.divider()
    if st.button("🗑️ 清理 30 天前旧快照", key="cleanup_old_snaps"):
        with st.spinner("清理中..."):
            deleted, skipped, errors = cloud_sync.delete_old_snapshots(days=30)
        st.success(f"清理完成: 删除 {deleted} 个，跳过 {skipped} 个")
        if errors:
            st.warning("部分文件删除失败（仅显示前3条）")
            for e in errors[:3]:
                st.code(e)


def _status_tab(configured: bool) -> None:
    if not configured:
        st.info("未配置云端同步。")
        return

    status = cloud_sync.get_sync_status()
    st.json(status)
    st.caption(f"下次自动备份：{cloud_sync.time_to_next_sync_str()}")
