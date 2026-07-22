"""
cloud_sync.py — Supabase 云端备份同步 v6.3

================================================================
v6.3 变更：
- 恢复自动备份：每 2 小时自动全量备份一次（含快照）
- 恢复手动同步按钮支持（auto_push_if_due 正常执行）
- SYNC_INTERVAL_SEC = 2 * 3600

v6.1 修复（保留）：
- pull_watchlist() 改为"云端权威"策略，不再把已删除品种补回来

v6 架构（保留）：
- 快照式备份：每次不覆盖旧文件，新建带时间戳的快照文件
- latest/ 目录保存最新版本，供启动恢复使用
================================================================
"""

import json, logging, os, time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
import requests

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SEC = 2 * 3600  # 2 小时自动备份一次

STARTUP_GRACE_SEC = int(os.environ.get("CLOUD_SYNC_STARTUP_GRACE_SEC", "900"))
PUSH_DROP_RATIO_LIMIT = float(os.environ.get("CLOUD_SYNC_PUSH_DROP_RATIO_LIMIT", "0.5"))
MIN_LOCAL_WATCHLIST_FOR_PUSH = int(os.environ.get("CLOUD_SYNC_MIN_LOCAL_WATCHLIST", "1"))
_LATEST_DIR = "latest"
_BACKUP_DIR  = "backups"
_LATEST_FILES = {
    "watchlist":           "watchlist.json",
    "watchlist_archive":   "watchlist_archive.json",
    "wl_categories":       "wl_categories.json",
    "scan_history":        "scan_history.json",
    "scan_results":        "scan_results.json",
    "scan_groups":         "scan_groups.json",
    "config":              "config.json",
    "meta":                "sync_meta.json",
    "hotlist":             "hotlist.json",
    "hotlist_archive":     "hotlist_archive.json",
    "hl_categories":       "hl_categories.json",
    "symbols":             "symbols.json",
    "symbol_groups":       "symbol_groups.json",
    "triple_bottom":       "data_triple_bottom.json",
    "alerts":              "data_alerts.json",
    "starred":             "data_starred.json",
    "ticker_notes":        "data_ticker_notes.json",
}

_SNAPSHOT_KEYS = ["watchlist", "watchlist_archive", "wl_categories", "config", "hotlist", "hotlist_archive", "hl_categories", "symbols", "symbol_groups", "triple_bottom", "alerts", "starred", "ticker_notes"]
_APP_BOOT_TS = time.time()
_CLOUD_FILES   = _LATEST_FILES  # 兼容旧接口

# ════════════════════════════════════════════════════════════════════
# 配置读取
# ════════════════════════════════════════════════════════════════════

def _get_secrets() -> Tuple[str, str, str]:
    try:
        import streamlit as st
        url    = st.secrets.get("SUPABASE_URL",    "")
        key    = st.secrets.get("SUPABASE_KEY",    "")
        bucket = st.secrets.get("SUPABASE_BUCKET", "strx-backup")
        return str(url).strip().rstrip("/"), str(key).strip(), str(bucket).strip()
    except Exception:
        pass
    return (
        os.environ.get("SUPABASE_URL",    "").strip().rstrip("/"),
        os.environ.get("SUPABASE_KEY",    "").strip(),
        os.environ.get("SUPABASE_BUCKET", "strx-backup").strip(),
    )

def is_configured() -> bool:
    url, key, _ = _get_secrets()
    return bool(url and key)

def _hdrs(key: str) -> dict:
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }

# ════════════════════════════════════════════════════════════════════
# Bucket 管理
# ════════════════════════════════════════════════════════════════════

def ensure_bucket() -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未填写 SUPABASE_URL / SUPABASE_KEY"
    bucket_url = f"{url}/storage/v1/bucket"
    r = requests.get(f"{bucket_url}/{bucket}", headers=_hdrs(key), timeout=10)
    if r.status_code == 200:
        return True, f"Bucket '{bucket}' 已存在"
    if r.status_code == 401:
        return False, "认证失败(401)：请使用 service_role key"
    create_r = requests.post(
        bucket_url, headers=_hdrs(key),
        json={"id": bucket, "name": bucket, "public": True}, timeout=10,
    )
    if create_r.status_code in (200, 201):
        return True, f"Bucket '{bucket}' 已创建"
    try:
        msg = create_r.json().get("message", create_r.text[:200])
    except Exception:
        msg = create_r.text[:200]
    return False, f"创建 bucket 失败 {create_r.status_code}：{msg}"

# ════════════════════════════════════════════════════════════════════
# 底层读写删
# ════════════════════════════════════════════════════════════════════

def _upload_path(path: str, data: Any) -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未配置"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
    hdrs = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/octet-stream", "x-upsert": "true",
    }
    try:
        r = requests.post(obj_url, headers=hdrs, data=payload, timeout=30)
        if r.status_code in (200, 201):
            return True, "OK"
        if r.status_code in (400, 409, 422):
            r2 = requests.put(obj_url, headers=hdrs, data=payload, timeout=30)
            if r2.status_code in (200, 201):
                return True, "OK(PUT)"
            return False, f"POST {r.status_code}/PUT {r2.status_code}: {r2.text[:200]}"
        if r.status_code == 401:
            return False, "认证失败(401)"
        if r.status_code == 403:
            return False, "权限不足(403)：请使用 service_role key"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.exceptions.ConnectionError:
        return False, "网络连接失败"
    except Exception as e:
        return False, f"上传异常：{e}"

def _download_path(path: str) -> Optional[Any]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return None
    obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
    try:
        r = requests.get(obj_url, headers=_hdrs(key), timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"_download_path {path}: {e}")
    return None

def _delete_path(path: str) -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未配置"
    obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
    try:
        r = requests.delete(obj_url, headers=_hdrs(key), timeout=15)
        if r.status_code in (200, 204):
            return True, "已删除"
        return False, f"HTTP {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, f"删除异常：{e}"

def _list_objects(prefix: str) -> List[Dict]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return []
    list_url = f"{url}/storage/v1/object/list/{bucket}"
    all_rows: List[Dict] = []
    limit = 1000
    offset = 0
    max_total = 20000
    try:
        while True:
            r = requests.post(
                list_url, headers=_hdrs(key),
                json={"prefix": prefix, "limit": limit, "offset": offset,
                      "sortBy": {"column": "name", "order": "asc"}},
                timeout=20,
            )
            if r.status_code != 200:
                break
            rows = r.json() or []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < limit or len(all_rows) >= max_total:
                break
            offset += limit
    except Exception as e:
        logger.debug(f"_list_objects {prefix}: {e}")
    return all_rows

# ════════════════════════════════════════════════════════════════════
# latest/ 读写
# ════════════════════════════════════════════════════════════════════

def _upload_latest(file_key: str, data: Any) -> Tuple[bool, str]:
    fname = _LATEST_FILES.get(file_key, f"{file_key}.json")
    return _upload_path(f"{_LATEST_DIR}/{fname}", data)

def _download_latest(file_key: str) -> Optional[Any]:
    fname = _LATEST_FILES.get(file_key, f"{file_key}.json")
    return _download_path(f"{_LATEST_DIR}/{fname}")

# ════════════════════════════════════════════════════════════════════
# backups/ 快照
# ════════════════════════════════════════════════════════════════════

def _make_snapshot_path(file_key: str, payload_bytes: bytes) -> str:
    ts_str     = time.strftime("%Y%m%d_%H%M%S")
    size_b     = len(payload_bytes)
    size_label = f"{size_b // 1024}kB" if size_b >= 1024 else f"{size_b}B"
    return f"{_BACKUP_DIR}/{file_key}_{ts_str}_{size_label}.json"

def _upload_snapshot(file_key: str, data: Any) -> Tuple[bool, str]:
    payload   = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    snap_path = _make_snapshot_path(file_key, payload)
    ok, msg   = _upload_path(snap_path, data)
    return ok, f"{snap_path}: {msg}"

# ════════════════════════════════════════════════════════════════════
# 快照列表 / 删除旧快照
# ════════════════════════════════════════════════════════════════════

def list_backup_snapshots() -> List[Dict]:
    objects = _list_objects(_BACKUP_DIR + "/")
    result  = []
    for obj in objects:
        name = obj.get("name", "")
        if not name:
            continue
        full_path = name if name.startswith(_BACKUP_DIR + "/") else f"{_BACKUP_DIR}/{name}"
        basename  = full_path.split("/")[-1].replace(".json", "")
        parts     = basename.rsplit("_", 3)
        if len(parts) == 4:
            file_key, date_s, time_s, size_label = parts
            ts_str = (f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:8]} "
                      f"{time_s[:2]}:{time_s[2:4]}:{time_s[4:]}")
            try:
                ts_epoch = time.mktime(time.strptime(date_s + time_s, "%Y%m%d%H%M%S"))
            except Exception:
                ts_epoch = 0
        else:
            file_key   = basename
            ts_str     = "—"
            size_label = "?"
            ts_epoch   = 0
        result.append({
            "path":       full_path,
            "file_key":   file_key,
            "ts_str":     ts_str,
            "size_label": size_label,
            "ts_epoch":   ts_epoch,
        })
    result.sort(key=lambda x: x["ts_epoch"], reverse=True)
    return result

def delete_old_snapshots(days: int = 30) -> Tuple[int, int, List[str]]:
    snapshots    = list_backup_snapshots()
    cutoff_epoch = time.time() - days * 86400
    deleted, skipped = 0, 0
    errors: List[str] = []
    by_key: Dict[str, List[Dict]] = defaultdict(list)
    for s in snapshots:
        by_key[s["file_key"]].append(s)
    for file_key, snaps in by_key.items():
        for i, snap in enumerate(snaps):
            if i == 0:
                skipped += 1
                continue
            if snap["ts_epoch"] <= 0 or snap["ts_epoch"] >= cutoff_epoch:
                skipped += 1
                continue
            ok, msg = _delete_path(snap["path"])
            if ok:
                deleted += 1
            else:
                errors.append(f"{snap['path']}: {msg}")
                skipped += 1
    return deleted, skipped, errors

# ════════════════════════════════════════════════════════════════════
# 从历史快照恢复
# ════════════════════════════════════════════════════════════════════

def restore_from_snapshot(snapshot_path: str, file_key: str) -> Tuple[bool, str]:
    import storage as loc
    data = _download_path(snapshot_path)
    if data is None:
        return False, f"无法下载快照：{snapshot_path}"
    try:
        if file_key == "watchlist":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save_with_backup(loc.F_WATCHLIST, data)
            return True, f"已从快照恢复收藏夹，共 {len(data)} 个品种"
        elif file_key == "watchlist_archive":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_WATCHLIST_ARCHIVE, data)
            return True, f"已从快照恢复存档，共 {len(data)} 个品种"
        elif file_key == "wl_categories":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_WL_CATS, data)
            return True, f"已从快照恢复分类，共 {len(data)} 个分类"
        elif file_key == "config":
            if not isinstance(data, dict):
                return False, "格式错误（期望字典）"
            loc._save(loc.F_CFG, data)
            return True, "已从快照恢复配置"
        elif file_key == "hotlist":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save_with_backup(loc.F_HOTLIST, data)
            return True, f"已从快照恢复热门品种，共 {len(data)} 个品种"
        elif file_key == "hotlist_archive":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_HOTLIST_ARCHIVE, data)
            return True, f"已从快照恢复热门品种存档，共 {len(data)} 个品种"
        elif file_key == "hl_categories":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_HL_CATS, data)
            return True, f"已从快照恢复热门分类，共 {len(data)} 个分类"
        elif file_key == "symbols":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_SYMBOLS, data)
            return True, f"已从快照恢复品种库，共 {len(data)} 个品种"
        elif file_key == "symbol_groups":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_SYMBOL_GROUPS, data)
            return True, f"已从快照恢复自定义分组，共 {len(data)} 个分组"
        elif file_key == "alerts":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            loc._save(loc.F_ALERTS, data)
            return True, f"已从快照恢复告警日志，共 {len(data)} 条记录"
        else:
            return False, f"不支持恢复类型：{file_key}"
    except Exception as e:
        return False, f"恢复失败：{e}"

# ════════════════════════════════════════════════════════════════════
# 收藏夹分类专项推送 / 拉取
# ════════════════════════════════════════════════════════════════════

def push_wl_categories() -> Tuple[bool, str]:
    try:
        import storage as loc
        cats     = loc.load_wl_categories()
        ok1, m1  = _upload_latest("wl_categories", cats)
        _upload_snapshot("wl_categories", cats)
        if ok1:
            return True, f"分类 {len(cats)} 个已同步 + 快照已创建"
        return False, f"wl_categories: {m1}"
    except Exception as e:
        return False, f"push_wl_categories 异常：{e}"


def push_symbols() -> Tuple[bool, str]:
    try:
        import storage as loc
        items = loc.load_symbols()
        ok, msg = _upload_latest("symbols", items)
        _upload_snapshot("symbols", items)
        if ok:
            return True, f"品种库已同步 {len(items)} 个品种"
        return False, f"symbols: {msg}"
    except Exception as e:
        return False, f"push_symbols 异常：{e}"


def pull_symbols() -> Tuple[bool, str]:
    try:
        from storage import F_SYMBOLS, _save
        cloud_items = _download_latest("symbols")
        if not isinstance(cloud_items, list):
            return False, "云端无品种库数据"
        _save(F_SYMBOLS, cloud_items)
        return True, f"品种库已恢复 {len(cloud_items)} 个品种"
    except Exception as e:
        return False, f"pull_symbols 异常：{e}"


def push_symbol_groups() -> Tuple[bool, str]:
    try:
        import storage as loc
        groups = loc.load_symbol_groups()
        ok, msg = _upload_latest("symbol_groups", groups)
        _upload_snapshot("symbol_groups", groups)
        if ok:
            return True, f"自定义分组已同步 {len(groups)} 个分组"
        return False, f"symbol_groups: {msg}"
    except Exception as e:
        return False, f"push_symbol_groups 异常：{e}"


def pull_symbol_groups() -> Tuple[bool, str]:
    try:
        from storage import F_SYMBOL_GROUPS, _save
        cloud_groups = _download_latest("symbol_groups")
        if not isinstance(cloud_groups, list):
            return False, "云端无自定义分组数据"
        _save(F_SYMBOL_GROUPS, cloud_groups)
        return True, f"自定义分组已恢复 {len(cloud_groups)} 个"
    except Exception as e:
        return False, f"pull_symbol_groups 异常：{e}"


def pull_wl_categories() -> Tuple[bool, str]:
    """以云端为权威，直接覆盖本地（v6.1 修复）"""
    try:
        from storage import F_WL_CATS, _save
        cloud_cats = _download_latest("wl_categories")
        if not isinstance(cloud_cats, list):
            return False, "云端无分类数据"
        _save(F_WL_CATS, cloud_cats)
        return True, f"分类已恢复 {len(cloud_cats)} 个"
    except Exception as e:
        return False, f"pull_wl_categories 异常：{e}"


def push_triple_bottom() -> Tuple[bool, str]:
    try:
        import storage as loc
        items = loc.load_triple_bottom()
        ok, msg = _upload_latest("triple_bottom", items)
        if ok:
            return True, f"三重底已同步 {len(items)} 个结果"
        return False, f"triple_bottom: {msg}"
    except Exception as e:
        return False, f"push_triple_bottom 异常：{e}"


def pull_triple_bottom() -> Tuple[bool, str]:
    try:
        from storage import F_TRIPLE_BOTTOM, _save
        cloud_items = _download_latest("triple_bottom")
        if not isinstance(cloud_items, list):
            return False, "云端无三重底数据"
        _save(F_TRIPLE_BOTTOM, cloud_items)
        return True, f"三重底已恢复 {len(cloud_items)} 个结果"
    except Exception as e:
        return False, f"pull_triple_bottom 异常：{e}"


def push_tb_snapshot(session_id: str, payload: dict) -> bool:
    """上传单个三重底快照到云端"""
    try:
        path = f"tb_snapshots/{session_id}.json"
        ok, msg = _upload_path(path, payload)
        return ok
    except Exception as e:
        logger.error(f"push_tb_snapshot {session_id} failed: {e}")
        return False


def pull_tb_snapshots() -> Tuple[bool, str]:
    """从云端下载所有三重底快照到本地"""
    try:
        import storage as loc
        loc._ensure_tb_snapshot_dir()
        objs = _list_objects("tb_snapshots/")
        count = 0
        for obj in objs:
            name = obj.get("name", "")
            if not name.endswith(".json"):
                continue
            basename = os.path.basename(name)
            local_path = os.path.join(loc.F_TB_SNAPSHOT_DIR, basename)
            if not os.path.exists(local_path):
                full_cloud_path = name if name.startswith("tb_snapshots/") else f"tb_snapshots/{name}"
                data = _download_path(full_cloud_path)
                if data:
                    loc._save(local_path, data)
                    count += 1
        return True, f"已从云端同步了 {count} 个历史快照到本地"
    except Exception as e:
        return False, f"pull_tb_snapshots 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 收藏夹专项推送
# ════════════════════════════════════════════════════════════════════

def _cloud_list_len(file_key: str) -> int:
    data = _download_latest(file_key)
    return len(data) if isinstance(data, list) else 0

def _validate_push_safety(force: bool = False) -> Tuple[bool, str]:
    if force:
        return True, "force push"
    try:
        import storage as loc
        local_cnt = len(loc.load_watchlist())
        local_cat_cnt = len(loc.load_wl_categories())
        cloud_cnt = _cloud_list_len("watchlist")
        cloud_cat_cnt = _cloud_list_len("wl_categories")
    except Exception as e:
        return False, f"safety check failed: {e}"

    if local_cnt < MIN_LOCAL_WATCHLIST_FOR_PUSH and cloud_cnt >= MIN_LOCAL_WATCHLIST_FOR_PUSH:
        return False, (
            f"已拦截：本地收藏仅 {local_cnt}，云端为 {cloud_cnt}。"
            "请先执行云端恢复，或在确认无误后使用强制上传。"
        )
    if cloud_cnt >= 5 and local_cnt == 0:
        return False, "已拦截：本地收藏为 0，但云端有历史数据。"
    if cloud_cnt > 0 and local_cnt < max(1, int(cloud_cnt * PUSH_DROP_RATIO_LIMIT)):
        return False, (
            f"已拦截：本地收藏 {local_cnt} 相比云端 {cloud_cnt} 降幅过大。"
            "请先核对数据，必要时使用强制上传。"
        )
    if cloud_cat_cnt > 0 and local_cat_cnt == 0:
        return False, "已拦截：本地分类为空，但云端存在分类数据。"
    return True, "safety check passed"

def push_watchlist(force: bool = False) -> Tuple[bool, str]:
    try:
        safe_ok, safe_msg = _validate_push_safety(force=force)
        if not safe_ok:
            return False, safe_msg
        import storage as loc
        items   = loc.load_watchlist()
        archive = loc.load_watchlist_archive()
        for item in items:
            if not isinstance(item.get("notes"), list):
                item["notes"] = []
            for note in item["notes"]:
                note.setdefault("text", ""); note.setdefault("img_url", ""); note.setdefault("ts", "")
        ok1, m1 = _upload_latest("watchlist", items)
        ok2, m2 = _upload_latest("watchlist_archive", archive)
        _upload_snapshot("watchlist", items)
        _upload_snapshot("watchlist_archive", archive)
        cats = loc.load_wl_categories()
        _upload_latest("wl_categories", cats)
        _upload_snapshot("wl_categories", cats)
        note_cnt = sum(len(i.get("notes", [])) for i in items)
        if ok1 and ok2:
            return True, f"收藏 {len(items)} 个品种、{note_cnt} 条备注、{len(cats)} 个分类已同步"
        return False, f"watchlist:{m1} / archive:{m2}"
    except Exception as e:
        return False, f"push_watchlist 异常：{e}"

def pull_watchlist() -> Tuple[bool, str]:
    """
    以云端为权威覆盖本地（v6.1 修复）。
    本地有但云端没有的备注（本次会话新增）会合并保留。
    """
    try:
        import storage as loc
        cloud_items = _download_latest("watchlist")
        if not isinstance(cloud_items, list):
            return False, "云端无收藏夹数据"

        local_items = loc.load_watchlist()
        local_notes_map: Dict[str, List] = {}
        for li in local_items:
            if isinstance(li, dict) and li.get("ticker"):
                local_notes_map[li["ticker"].upper()] = li.get("notes", [])

        merged_notes_count = 0
        for ci in cloud_items:
            if not isinstance(ci, dict) or not ci.get("ticker"):
                continue
            tk = ci["ticker"].upper()
            cloud_note_ts = {n.get("ts") for n in ci.get("notes", [])
                             if isinstance(n, dict) and n.get("ts")}
            for ln in local_notes_map.get(tk, []):
                if isinstance(ln, dict) and ln.get("ts") and ln["ts"] not in cloud_note_ts:
                    ci.setdefault("notes", []).append(ln)
                    merged_notes_count += 1
            if ci.get("notes"):
                ci["notes"] = sorted(ci["notes"], key=lambda x: x.get("ts", ""))

        from storage import F_WATCHLIST, _save_with_backup
        _save_with_backup(F_WATCHLIST, cloud_items)

        cloud_arch = _download_latest("watchlist_archive")
        arch_msg = ""
        if isinstance(cloud_arch, list):
            loc._save(loc.F_WATCHLIST_ARCHIVE, cloud_arch)
            arch_msg = f"，存档 {len(cloud_arch)} 个"

        cat_ok, cat_msg = pull_wl_categories()
        cat_suffix = f"，分类：{cat_msg}" if cat_ok else ""

        return True, (f"收藏夹已恢复 {len(cloud_items)} 个品种"
                      f"（补入本地新备注 {merged_notes_count} 条）"
                      f"{arch_msg}{cat_suffix}")
    except Exception as e:
        return False, f"pull_watchlist 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 热门品种专项推送 / 拉取
# ════════════════════════════════════════════════════════════════════

def push_hl_categories() -> Tuple[bool, str]:
    try:
        import storage as loc
        cats     = loc.load_hl_categories()
        ok1, m1  = _upload_latest("hl_categories", cats)
        _upload_snapshot("hl_categories", cats)
        if ok1:
            return True, f"分类 {len(cats)} 个已同步 + 快照已创建"
        return False, f"hl_categories: {m1}"
    except Exception as e:
        return False, f"push_hl_categories 异常：{e}"


def pull_hl_categories() -> Tuple[bool, str]:
    try:
        from storage import F_HL_CATS, _save
        cloud_cats = _download_latest("hl_categories")
        if not isinstance(cloud_cats, list):
            return False, "云端无热门分类数据"
        _save(F_HL_CATS, cloud_cats)
        return True, f"热门分类已恢复 {len(cloud_cats)} 个"
    except Exception as e:
        return False, f"pull_hl_categories 异常：{e}"


def push_hotlist(force: bool = False) -> Tuple[bool, str]:
    try:
        import storage as loc
        items   = loc.load_hotlist()
        archive = loc.load_hotlist_archive()
        for item in items:
            if not isinstance(item.get("notes"), list):
                item["notes"] = []
            for note in item["notes"]:
                note.setdefault("text", ""); note.setdefault("img_url", ""); note.setdefault("ts", "")
        ok1, m1 = _upload_latest("hotlist", items)
        ok2, m2 = _upload_latest("hotlist_archive", archive)
        _upload_snapshot("hotlist", items)
        _upload_snapshot("hotlist_archive", archive)
        cats = loc.load_hl_categories()
        _upload_latest("hl_categories", cats)
        _upload_snapshot("hl_categories", cats)
        note_cnt = sum(len(i.get("notes", [])) for i in items)
        if ok1 and ok2:
            return True, f"热门 {len(items)} 个品种、{note_cnt} 条备注、{len(cats)} 个分类已同步"
        return False, f"hotlist:{m1} / archive:{m2}"
    except Exception as e:
        return False, f"push_hotlist 异常：{e}"


def pull_hotlist() -> Tuple[bool, str]:
    try:
        import storage as loc
        cloud_items = _download_latest("hotlist")
        if not isinstance(cloud_items, list):
            return False, "云端无热门品种数据"

        local_items = loc.load_hotlist()
        local_notes_map: Dict[str, List] = {}
        for li in local_items:
            if isinstance(li, dict) and li.get("ticker"):
                local_notes_map[li["ticker"].upper()] = li.get("notes", [])

        merged_notes_count = 0
        for ci in cloud_items:
            if not isinstance(ci, dict) or not ci.get("ticker"):
                continue
            tk = ci["ticker"].upper()
            cloud_note_ts = {n.get("ts") for n in ci.get("notes", [])
                             if isinstance(n, dict) and n.get("ts")}
            for ln in local_notes_map.get(tk, []):
                if isinstance(ln, dict) and ln.get("ts") and ln["ts"] not in cloud_note_ts:
                    ci.setdefault("notes", []).append(ln)
                    merged_notes_count += 1
            if ci.get("notes"):
                ci["notes"] = sorted(ci["notes"], key=lambda x: x.get("ts", ""))

        from storage import F_HOTLIST, _save_with_backup
        _save_with_backup(F_HOTLIST, cloud_items)

        cloud_arch = _download_latest("hotlist_archive")
        arch_msg = ""
        if isinstance(cloud_arch, list):
            loc._save(loc.F_HOTLIST_ARCHIVE, cloud_arch)
            arch_msg = f"，存档 {len(cloud_arch)} 个"

        cat_ok, cat_msg = pull_hl_categories()
        cat_suffix = f"，分类：{cat_msg}" if cat_ok else ""

        return True, (f"热门品种已恢复 {len(cloud_items)} 个品种"
                      f"（补入本地新备注 {merged_notes_count} 条）"
                      f"{arch_msg}{cat_suffix}")
    except Exception as e:
        return False, f"pull_hotlist 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 全量推送 / 拉取
# ════════════════════════════════════════════════════════════════════

def push_all(force: bool = False) -> Tuple[bool, str]:
    import storage as loc
    errors = []
    ok, msg = push_watchlist(force=force)
    if not ok:
        errors.append(f"watchlist: {msg}")
    ok_hl, msg_hl = push_hotlist(force=force)
    if not ok_hl:
        errors.append(f"hotlist: {msg_hl}")
    for file_key, loader in [
        ("wl_categories", lambda: loc.load_wl_categories()),
        ("hl_categories", lambda: loc.load_hl_categories()),
        ("scan_history",  lambda: loc._load(loc.F_HIST,   [])),
        ("scan_results",  lambda: loc._load(loc.F_ALLRES, [])),
        ("scan_groups",   lambda: loc.load_scanned_groups()),
        ("config",        lambda: loc._load(loc.F_CFG,    {})),
        ("symbols",       lambda: loc.load_symbols()),
        ("symbol_groups", lambda: loc.load_symbol_groups()),
        ("triple_bottom", lambda: loc.load_triple_bottom()),
        ("alerts",        lambda: loc._load(loc.F_ALERTS, [])),
        ("starred",       lambda: loc._load(loc.F_STARRED, [])),
        ("ticker_notes",  lambda: loc._load(loc.F_TICKER_NOTES, {})),
    ]:
        try:
            data      = loader()
            ok2, msg2 = _upload_latest(file_key, data)
            if not ok2:
                errors.append(f"{file_key}: {msg2}")
            if file_key in ("config", "wl_categories", "hl_categories", "symbols", "symbol_groups", "triple_bottom", "alerts", "starred", "ticker_notes"):
                _upload_snapshot(file_key, data)
        except Exception as e:
            errors.append(f"{file_key}: {e}")
    try:
        _upload_latest("meta", {
            "last_sync":        time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_sync_ts":     time.time(),
            "version":          "6.3",
            "watchlist_cnt":    len(loc.load_watchlist()),
            "hotlist_cnt":      len(loc.load_hotlist()),
            "scan_results_cnt": len(loc._load(loc.F_ALLRES, [])),
            "alerts_cnt":       len(loc._load(loc.F_ALERTS, [])),
        })
    except Exception as e:
        errors.append(f"meta: {e}")
    if errors:
        return False, "部分失败：" + " / ".join(errors[:3])
    _invalidate_status_cache()   # 推送成功 → 清除缓存，侧边栏立刻显示最新时间
    return True, "全量上传 + 快照完成"

def pull_all() -> Dict[str, Any]:
    import storage as loc
    results: Dict[str, Any] = {}

    ok, msg = pull_watchlist()
    results["watchlist"] = (ok, msg)

    ok_hl, msg_hl = pull_hotlist()
    results["hotlist"] = (ok_hl, msg_hl)

    cloud_hist = _download_latest("scan_history")
    if isinstance(cloud_hist, list):
        local_hist = loc._load(loc.F_HIST, []) or []
        local_ids  = {s.get("session_id") for s in local_hist if isinstance(s, dict)}
        added = sum(1 for s in cloud_hist
                    if isinstance(s, dict) and s.get("session_id") not in local_ids
                    and local_hist.append(s) is None)
        if added:
            loc._save(loc.F_HIST, local_hist[-50:])
        results["scan_history"] = (True, f"补充 {added} 条")
    else:
        results["scan_history"] = (False, "无云端数据")

    cloud_res = _download_latest("scan_results")
    if isinstance(cloud_res, list):
        local_res = loc._load(loc.F_ALLRES, []) or []
        m = {(r["ticker"], r.get("timeframe","")): r for r in local_res
             if isinstance(r, dict) and r.get("ticker")}
        added = sum(1 for r in cloud_res
                    if isinstance(r, dict) and r.get("ticker") and
                    (r["ticker"], r.get("timeframe","")) not in m and
                    m.update({(r["ticker"], r.get("timeframe","")): r}) is None)
        if added:
            loc._save(loc.F_ALLRES, list(m.values()))
        results["scan_results"] = (True, f"补充 {added} 条，共 {len(m)} 条")
    else:
        results["scan_results"] = (False, "无云端数据")

    cloud_grp = _download_latest("scan_groups")
    if isinstance(cloud_grp, list):
        merged = list(set(loc.load_scanned_groups()) | set(cloud_grp))
        loc._save(loc.F_GROUPS, merged)
        results["scan_groups"] = (True, f"{len(merged)} 组")
    else:
        results["scan_groups"] = (False, "无云端数据")

    cloud_alerts = _download_latest("alerts")
    if isinstance(cloud_alerts, list):
        local_alerts = loc._load(loc.F_ALERTS, []) or []
        seen = set()
        for a in local_alerts:
            if isinstance(a, dict):
                k = (a.get("time"), a.get("ticker"), a.get("timeframe"), a.get("scanner"), a.get("channel"))
                seen.add(k)
        
        added = 0
        for a in cloud_alerts:
            if isinstance(a, dict):
                k = (a.get("time"), a.get("ticker"), a.get("timeframe"), a.get("scanner"), a.get("channel"))
                if k not in seen:
                    local_alerts.append(a)
                    seen.add(k)
                    added += 1
        
        if added or not os.path.exists(loc.F_ALERTS):
            def parse_time(x):
                try:
                    return x.get("time", "")
                except Exception:
                    return ""
            local_alerts.sort(key=parse_time)
            if len(local_alerts) > loc._MAX_ALERTS:
                local_alerts = local_alerts[-loc._MAX_ALERTS:]
            loc._save(loc.F_ALERTS, local_alerts)
        results["alerts"] = (True, f"补充 {added} 条，共 {len(local_alerts)} 条")
    else:
        results["alerts"] = (False, "无云端数据")

    if not loc._load(loc.F_CFG, {}):
        cloud_cfg = _download_latest("config")
        if isinstance(cloud_cfg, dict):
            loc._save(loc.F_CFG, cloud_cfg)
            results["config"] = (True, "已恢复")
        else:
            results["config"] = (False, "无云端数据")
    else:
        results["config"] = (True, "本地已有，跳过")

    if not results.get("watchlist", (False,))[0]:
        cat_ok2, cat_msg2 = pull_wl_categories()
        results["wl_categories"] = (cat_ok2, cat_msg2)

    if not results.get("hotlist", (False,))[0]:
        cat_ok3, cat_msg3 = pull_hl_categories()
        results["hl_categories"] = (cat_ok3, cat_msg3)

    ok_sym, msg_sym = pull_symbols()
    results["symbols"] = (ok_sym, msg_sym)

    ok_sgrp, msg_sgrp = pull_symbol_groups()
    results["symbol_groups"] = (ok_sgrp, msg_sgrp)

    ok_tb, msg_tb = pull_triple_bottom()
    results["triple_bottom"] = (ok_tb, msg_tb)

    ok_tbsnap, msg_tbsnap = pull_tb_snapshots()
    results["tb_snapshots"] = (ok_tbsnap, msg_tbsnap)

    # 重点关注品种
    try:
        cloud_starred = _download_latest("starred")
        if isinstance(cloud_starred, list):
            merged = list(set(loc.load_starred_tickers()) | set(cloud_starred))
            loc.save_starred_tickers(merged)
            results["starred"] = (True, f"合并后共 {len(merged)} 个")
        else:
            results["starred"] = (False, "无云端数据")
    except Exception as e:
        results["starred"] = (False, str(e))

    # 品种备注
    try:
        cloud_notes = _download_latest("ticker_notes")
        if isinstance(cloud_notes, dict):
            local_notes = loc._load(loc.F_TICKER_NOTES, {}) or {}
            for k, v in cloud_notes.items():
                if k not in local_notes or not local_notes[k]:
                    local_notes[k] = v
            loc._save(loc.F_TICKER_NOTES, local_notes)
            results["ticker_notes"] = (True, f"合并后共 {len(local_notes)} 个")
        else:
            results["ticker_notes"] = (False, "无云端数据")
    except Exception as e:
        results["ticker_notes"] = (False, str(e))

    return results

# ════════════════════════════════════════════════════════════════════
# 连接测试
# ════════════════════════════════════════════════════════════════════

def _test_connection() -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url:  return False, "SUPABASE_URL 未填写"
    if not key:  return False, "SUPABASE_KEY 未填写"
    if not url.startswith("https://"):
        return False, f"SUPABASE_URL 格式错误（应 https:// 开头）：{url[:40]}"
    try:
        r = requests.get(f"{url}/storage/v1/bucket", headers=_hdrs(key), timeout=10)
    except Exception as e:
        return False, f"无法连接 Supabase：{e}"
    if r.status_code == 401:
        return False, "API Key 无效(401)：⚠️ 请使用 service_role key"
    ok, msg = ensure_bucket()
    if not ok:
        return False, msg
    ok2, msg2 = _upload_latest("meta", {
        "last_sync":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts": time.time(), "version": "6.2", "test": True,
    })
    if ok2:
        return True, f"✅ 连接成功！Bucket='{bucket}'，读写测试通过"
    return False, f"连接成功但写入失败：{msg2}"

# ════════════════════════════════════════════════════════════════════
# 启动恢复（仅保留 pull，自动 push 已移除）
# ════════════════════════════════════════════════════════════════════

def auto_pull_on_startup() -> Tuple[bool, str]:
    """App 冷启动时从 latest/ 恢复所有数据，每次会话只执行一次"""
    try:
        import streamlit as st
        if st.session_state.get("_cloud_pulled"):
            return True, "已恢复（本次会话已完成）"
        st.session_state["_cloud_pulled"] = True
    except Exception:
        pass
    if not is_configured():
        return False, "未配置云端"
    try:
        ensure_bucket()
        results   = pull_all()
        ok_count  = sum(1 for v in results.values() if isinstance(v, tuple) and v[0])
        fail_msgs = [f"{k}:{v[1]}" for k, v in results.items()
                     if isinstance(v, tuple) and not v[0] and "无云端数据" not in v[1]]
        if ok_count == 0 and fail_msgs:
            return False, "云端恢复失败：" + " / ".join(fail_msgs[:2])
        return True, f"成功恢复 {ok_count} 项数据"
    except Exception as e:
        return False, f"启动恢复异常：{e}"

# ── 自动备份（每2小时一次） ───────────────────────────────────────

_last_sync_ts: float = 0.0

def auto_push_if_due(force: bool = False) -> Optional[Tuple[bool, str]]:
    """每 2 小时自动全量备份一次（含快照）"""
    global _last_sync_ts
    if not is_configured():
        return None
    now = time.time()
    if not force and (now - _APP_BOOT_TS) < STARTUP_GRACE_SEC:
        return None
    if not force and (now - _last_sync_ts) < SYNC_INTERVAL_SEC:
        return None
    if not force:
        meta = _download_latest("meta")
        if isinstance(meta, dict):
            if (now - float(meta.get("last_sync_ts", 0))) < SYNC_INTERVAL_SEC:
                _last_sync_ts = now
                return None
    _last_sync_ts = now
    ensure_bucket()
    return push_all(force=force)

def auto_sync_if_due(force: bool = False) -> Optional[Dict]:
    """兼容旧调用"""
    result = auto_push_if_due(force=force)
    if result is None:
        return None
    ok, msg = result
    return {"_result": (ok, msg)}

def startup_restore() -> Dict[str, Any]:
    """兼容旧调用"""
    if not is_configured():
        return {"configured": False}
    ensure_bucket()
    r = pull_all()
    r["configured"] = True
    return r

# ════════════════════════════════════════════════════════════════════
# 状态查询（带内存缓存，避免侧边栏每次 rerun 都发起 HTTP 请求）
# ════════════════════════════════════════════════════════════════════

_status_cache: Dict[str, Any] = {}
_status_cache_ts: float = 0.0
_STATUS_CACHE_TTL = 120  # 2 分钟内复用缓存，无需再请求云端

def _invalidate_status_cache():
    """推送成功后主动清除缓存，确保下次侧边栏立刻显示最新同步时间"""
    global _status_cache, _status_cache_ts
    _status_cache = {}
    _status_cache_ts = 0.0

def get_sync_status() -> Dict[str, Any]:
    global _status_cache, _status_cache_ts
    if not is_configured():
        return {"configured": False, "status": "未配置"}
    now = time.time()
    # 缓存未过期：直接返回，无网络请求
    if _status_cache and (now - _status_cache_ts) < _STATUS_CACHE_TTL:
        # elapsed_h 是时间敏感字段，每次实时计算
        result = dict(_status_cache)
        if result.get("last_sync_ts"):
            result["elapsed_h"] = round((now - float(result["last_sync_ts"])) / 3600, 1)
        return result
    # 缓存过期：请求云端
    meta = _download_latest("meta")
    if not meta:
        result = {"configured": True, "status": "尚未同步", "last_sync": "—",
                  "watchlist_cnt": 0, "scan_results_cnt": 0, "elapsed_h": 0,
                  "last_sync_ts": 0}
    else:
        elapsed_h = (now - float(meta.get("last_sync_ts", 0))) / 3600
        result = {
            "configured":       True,
            "status":           "正常",
            "last_sync":        meta.get("last_sync", "—"),
            "last_sync_ts":     meta.get("last_sync_ts", 0),
            "watchlist_cnt":    meta.get("watchlist_cnt", 0),
            "scan_results_cnt": meta.get("scan_results_cnt", 0),
            "alerts_cnt":       meta.get("alerts_cnt", 0),
            "elapsed_h":        round(elapsed_h, 1),
        }
    _status_cache    = result
    _status_cache_ts = now
    return result

def time_to_next_sync_str() -> str:
    if not is_configured():
        return "未配置"
    # 直接复用已缓存的 last_sync_ts，不再单独请求云端
    status = get_sync_status()
    last_ts = float(status.get("last_sync_ts", 0))
    if not last_ts:
        return "立即同步"
    remain = max(0.0, SYNC_INTERVAL_SEC - (time.time() - last_ts))
    if remain <= 0:
        return "已到期，下次访问触发"
    h, m = int(remain // 3600), int((remain % 3600) // 60)
    return f"{h}h {m:02d}m 后"
