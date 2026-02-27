"""
cloud_sync.py — Supabase 云端备份同步 v6
================================================================
架构改动（v6）：
  - 快照式备份：每次不覆盖旧文件，新建带时间戳+大小的快照文件
    文件名：backups/watchlist_20250115_143022_2048B.json
  - latest/ 目录保存最新版本，供启动恢复使用
  - 每 4 小时自动全量备份一次
  - 删除接口只删除 1 个月前的快照（最新快照永远保留）
  - 修复 auto_pull_on_startup / auto_push_if_due 缺失问题

目录结构：
  latest/watchlist.json                              ← 最新，供恢复
  latest/watchlist_archive.json
  latest/config.json  /  latest/sync_meta.json
  backups/watchlist_20250115_143022_2048B.json       ← 历史快照
  backups/watchlist_archive_20250115_143022_1024B.json
  backups/config_20250115_143022_512B.json
================================================================
"""

import json, logging, os, time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import requests

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SEC = 4 * 3600   # 4 小时

_LATEST_DIR = "latest"
_BACKUP_DIR = "backups"

_LATEST_FILES = {
    "watchlist":         "watchlist.json",
    "watchlist_archive": "watchlist_archive.json",
    "wl_categories":     "wl_categories.json",    # ← 收藏夹分类结构
    "scan_history":      "scan_history.json",
    "scan_results":      "scan_results.json",
    "scan_groups":       "scan_groups.json",
    "config":            "config.json",
    "meta":              "sync_meta.json",
}

# 需要做历史快照的核心文件
_SNAPSHOT_KEYS = ["watchlist", "watchlist_archive", "wl_categories", "config"]

# 兼容旧接口
_CLOUD_FILES = _LATEST_FILES

_last_sync_ts: float = 0.0


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
# 底层读写删（按完整路径）
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
    # Supabase Storage DELETE 接口：DELETE /object/{bucket}/{path}
    obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
    try:
        r = requests.delete(obj_url, headers=_hdrs(key), timeout=15)
        if r.status_code in (200, 204):
            return True, "已删除"
        # 也支持批量删除接口
        return False, f"HTTP {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, f"删除异常：{e}"


def _list_objects(prefix: str) -> List[Dict]:
    """列出 bucket 内指定前缀下的所有对象"""
    url, key, bucket = _get_secrets()
    if not url or not key:
        return []
    list_url = f"{url}/storage/v1/object/list/{bucket}"
    try:
        r = requests.post(
            list_url, headers=_hdrs(key),
            json={"prefix": prefix, "limit": 1000, "offset": 0,
                  "sortBy": {"column": "name", "order": "asc"}},
            timeout=20,
        )
        if r.status_code == 200:
            return r.json() or []
    except Exception as e:
        logger.debug(f"_list_objects {prefix}: {e}")
    return []


# ════════════════════════════════════════════════════════════════════
# latest/ 读写（最新版本，供恢复）
# ════════════════════════════════════════════════════════════════════
def _upload_latest(file_key: str, data: Any) -> Tuple[bool, str]:
    fname = _LATEST_FILES.get(file_key, f"{file_key}.json")
    return _upload_path(f"{_LATEST_DIR}/{fname}", data)


def _download_latest(file_key: str) -> Optional[Any]:
    fname = _LATEST_FILES.get(file_key, f"{file_key}.json")
    return _download_path(f"{_LATEST_DIR}/{fname}")


# ════════════════════════════════════════════════════════════════════
# backups/ 快照（新文件，不覆盖旧文件）
# 文件名格式：backups/{file_key}_{YYYYMMDD}_{HHMMSS}_{size}B.json
# ════════════════════════════════════════════════════════════════════
def _make_snapshot_path(file_key: str, payload_bytes: bytes) -> str:
    ts_str = time.strftime("%Y%m%d_%H%M%S")
    size_b = len(payload_bytes)
    size_label = f"{size_b // 1024}kB" if size_b >= 1024 else f"{size_b}B"
    return f"{_BACKUP_DIR}/{file_key}_{ts_str}_{size_label}.json"


def _upload_snapshot(file_key: str, data: Any) -> Tuple[bool, str]:
    """创建历史快照（新文件，绝不覆盖旧快照）"""
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    snap_path = _make_snapshot_path(file_key, payload)
    ok, msg = _upload_path(snap_path, data)
    return ok, f"{snap_path}: {msg}"


# ════════════════════════════════════════════════════════════════════
# 快照列表 / 删除旧快照（仅删1个月前，最新永不删）
# ════════════════════════════════════════════════════════════════════
def list_backup_snapshots() -> List[Dict]:
    """返回所有历史快照，按时间倒序
    每项: {path, file_key, ts_str, size_label, ts_epoch}
    """
    objects = _list_objects(_BACKUP_DIR + "/")
    result  = []
    for obj in objects:
        name = obj.get("name", "")
        if not name:
            continue
        # 归一化：有些 API 版本会返回不含前缀的名字
        full_path = name if name.startswith(_BACKUP_DIR + "/") else f"{_BACKUP_DIR}/{name}"
        basename  = full_path.split("/")[-1].replace(".json", "")

        # 解析 {file_key}_{YYYYMMDD}_{HHMMSS}_{size}
        parts = basename.rsplit("_", 3)
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
    """只删除超过 days 天的快照（默认30天=1个月）。
    保护规则：每个 file_key 的最新1个快照永不删除。
    返回：(deleted, skipped, errors)
    """
    snapshots    = list_backup_snapshots()
    cutoff_epoch = time.time() - days * 86400
    deleted, skipped = 0, 0
    errors: List[str] = []

    by_key: Dict[str, List[Dict]] = defaultdict(list)
    for s in snapshots:
        by_key[s["file_key"]].append(s)

    for file_key, snaps in by_key.items():
        # snaps 已按 ts_epoch 倒序，snaps[0] 是最新的
        for i, snap in enumerate(snaps):
            if i == 0:
                # 最新的永不删除
                skipped += 1
                continue
            if snap["ts_epoch"] <= 0 or snap["ts_epoch"] >= cutoff_epoch:
                # 时间解析失败或未超过阈值
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
    """从历史快照文件恢复数据到本地。
    注意：直接写文件，不触发云端推送（恢复操作不应产生新快照）。
    """
    import storage as loc
    data = _download_path(snapshot_path)
    if data is None:
        return False, f"无法下载快照：{snapshot_path}"
    try:
        if file_key == "watchlist":
            if not isinstance(data, list):
                return False, "格式错误（期望列表）"
            # 直接写文件，不用 save_watchlist（避免触发云端推送）
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
            # 直接写文件，不用 save_wl_categories（避免触发云端推送）
            loc._save(loc.F_WL_CATS, data)
            return True, f"已从快照恢复分类，共 {len(data)} 个分类"
        elif file_key == "config":
            if not isinstance(data, dict):
                return False, "格式错误（期望字典）"
            loc._save(loc.F_CFG, data)
            return True, "已从快照恢复配置"
        else:
            return False, f"不支持恢复类型：{file_key}"
    except Exception as e:
        return False, f"恢复失败：{e}"



# ════════════════════════════════════════════════════════════════════
# 收藏夹分类专项推送 / 拉取
# ════════════════════════════════════════════════════════════════════
def push_wl_categories() -> Tuple[bool, str]:
    """推送分类树 → latest/ + 快照"""
    try:
        import storage as loc
        cats = loc.load_wl_categories()
        ok1, m1 = _upload_latest("wl_categories", cats)
        _upload_snapshot("wl_categories", cats)
        if ok1:
            return True, f"分类 {len(cats)} 个已同步 + 快照已创建"
        return False, f"wl_categories: {m1}"
    except Exception as e:
        return False, f"push_wl_categories 异常：{e}"


def pull_wl_categories() -> Tuple[bool, str]:
    """从云端拉取分类树，恢复到本地（直接写文件，不触发云端推送）
    策略：云端优先 + 本地独有保留。重启后本地为空时完全用云端数据。
    """
    try:
        from storage import F_WL_CATS, _save, load_wl_categories
        cloud_cats = _download_latest("wl_categories")
        if not isinstance(cloud_cats, list):
            return False, "云端无分类数据"

        local_cats = load_wl_categories()
        cloud_ids  = {c["id"] for c in cloud_cats if c.get("id")}

        # 以云端为主，补充本地独有（例如本次会话新建但尚未同步的）
        merged_map = {c["id"]: c for c in cloud_cats if c.get("id")}
        added = 0
        for lc in local_cats:
            if lc.get("id") and lc["id"] not in cloud_ids:
                merged_map[lc["id"]] = lc
                added += 1

        merged = list(merged_map.values())
        # !! 直接写文件，绝对不能调用 save_wl_categories（会触发云端推送死循环）
        _save(F_WL_CATS, merged)
        return True, f"分类已恢复 {len(merged)} 个（云端 {len(cloud_cats)} + 本地新增 {added}）"
    except Exception as e:
        return False, f"pull_wl_categories 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 收藏夹专项推送（双写 latest + snapshot）
# ════════════════════════════════════════════════════════════════════
def push_watchlist() -> Tuple[bool, str]:
    try:
        import storage as loc
        items   = loc.load_watchlist()
        archive = loc.load_watchlist_archive()
        for item in items:
            if not isinstance(item.get("notes"), list):
                item["notes"] = []
            for note in item["notes"]:
                note.setdefault("text", ""); note.setdefault("img_url", ""); note.setdefault("ts", "")

        ok1, m1 = _upload_latest("watchlist",         items)
        ok2, m2 = _upload_latest("watchlist_archive", archive)
        _upload_snapshot("watchlist",         items)
        _upload_snapshot("watchlist_archive", archive)

        # 同步分类数据（与 watchlist 一起备份，确保 UUID 和名称的对应关系不丢失）
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
    try:
        import storage as loc
        cloud_items = _download_latest("watchlist")
        if not isinstance(cloud_items, list):
            return False, "云端无收藏夹数据"
        local_items = loc.load_watchlist()
        local_map   = {i["ticker"].upper(): i for i in local_items
                       if isinstance(i, dict) and i.get("ticker")}
        added = 0; merged_notes = 0
        for ci in cloud_items:
            if not isinstance(ci, dict) or not ci.get("ticker"):
                continue
            tk = ci["ticker"].upper()
            if tk not in local_map:
                local_map[tk] = ci; added += 1
            else:
                le = local_map[tk]
                ln = le.get("notes", [])
                lt = {n.get("ts") for n in ln if isinstance(n, dict) and n.get("ts")}
                for cn in ci.get("notes", []):
                    if isinstance(cn, dict) and cn.get("ts") not in lt:
                        ln.append({"text": cn.get("text",""), "img_url": cn.get("img_url",""), "ts": cn.get("ts","")})
                        lt.add(cn.get("ts")); merged_notes += 1
                le["notes"] = sorted(ln, key=lambda x: x.get("ts",""))
                local_map[tk] = le
        # !! 直接写文件，不能用 save_watchlist（会触发 push_watchlist 死循环）
        from storage import F_WATCHLIST, _save_with_backup
        _save_with_backup(F_WATCHLIST, list(local_map.values()))

        cloud_arch = _download_latest("watchlist_archive")
        arch_added = 0
        if isinstance(cloud_arch, list):
            local_arch = loc.load_watchlist_archive()
            arch_tks   = {a["ticker"].upper() for a in local_arch if isinstance(a, dict) and a.get("ticker")}
            for ai in cloud_arch:
                if isinstance(ai, dict) and ai.get("ticker") and ai["ticker"].upper() not in arch_tks:
                    local_arch.append(ai); arch_added += 1
            if arch_added:
                loc.save_watchlist_archive(local_arch)
        # 分类数据也一起恢复（必须在 save_watchlist 之后，避免 UUID 找不到名称）
        cat_ok, cat_msg = pull_wl_categories()
        _cat_suffix = f"，分类：{cat_msg}" if cat_ok else ""
        return True, f"新增品种 {added}，补充备注 {merged_notes} 条，存档补充 {arch_added} 个{_cat_suffix}"
    except Exception as e:
        return False, f"pull_watchlist 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 全量推送 / 拉取
# ════════════════════════════════════════════════════════════════════
def push_all() -> Tuple[bool, str]:
    """全量备份：latest/ 更新 + 核心文件创建快照"""
    import storage as loc
    errors = []

    ok, msg = push_watchlist()
    if not ok:
        errors.append(f"watchlist: {msg}")

    for file_key, loader in [
        ("wl_categories", lambda: loc.load_wl_categories()),   # ← 分类：独立备份
        ("scan_history",  lambda: loc._load(loc.F_HIST,   [])),
        ("scan_results",  lambda: loc._load(loc.F_ALLRES, [])),
        ("scan_groups",   lambda: loc.load_scanned_groups()),
        ("config",        lambda: loc._load(loc.F_CFG,    {})),
    ]:
        try:
            data = loader()
            ok2, msg2 = _upload_latest(file_key, data)
            if not ok2:
                errors.append(f"{file_key}: {msg2}")
            # 核心文件也创建快照
            if file_key in ("config", "wl_categories"):
                _upload_snapshot(file_key, data)
        except Exception as e:
            errors.append(f"{file_key}: {e}")

    try:
        _upload_latest("meta", {
            "last_sync":        time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_sync_ts":     time.time(),
            "version":          "6",
            "watchlist_cnt":    len(loc.load_watchlist()),
            "scan_results_cnt": len(loc._load(loc.F_ALLRES, [])),
        })
    except Exception as e:
        errors.append(f"meta: {e}")

    if errors:
        return False, "部分失败：" + " / ".join(errors[:3])
    return True, "全量上传 + 快照完成"


def pull_all() -> Dict[str, Any]:
    import storage as loc
    results: Dict[str, Any] = {}

    ok, msg = pull_watchlist()
    results["watchlist"] = (ok, msg)

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

    if not loc._load(loc.F_CFG, {}):
        cloud_cfg = _download_latest("config")
        if isinstance(cloud_cfg, dict):
            loc._save(loc.F_CFG, cloud_cfg)
            results["config"] = (True, "已恢复")
        else:
            results["config"] = (False, "无云端数据")
    else:
        results["config"] = (True, "本地已有，跳过")

    # wl_categories 分类数据（pull_watchlist 内部已处理，但 pull_all 直接调用时也要补充）
    # 注意：pull_watchlist 已调用 pull_wl_categories，此处不重复调用，results 里已有记录
    # 如果 pull_watchlist 失败（无云端数据），也要尝试单独恢复分类
    if not results.get("watchlist", (False,))[0]:
        cat_ok2, cat_msg2 = pull_wl_categories()
        results["wl_categories"] = (cat_ok2, cat_msg2)

    return results


# ════════════════════════════════════════════════════════════════════
# 连接测试
# ════════════════════════════════════════════════════════════════════
def _test_connection() -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url: return False, "SUPABASE_URL 未填写"
    if not key: return False, "SUPABASE_KEY 未填写"
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
        "last_sync": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts": time.time(), "version": "6", "test": True,
    })
    if ok2:
        return True, f"✅ 连接成功！Bucket='{bucket}'，读写测试通过"
    return False, f"连接成功但写入失败：{msg2}"


# ════════════════════════════════════════════════════════════════════
# 定时备份 / 启动恢复（app.py 调用）
# ════════════════════════════════════════════════════════════════════
def auto_push_if_due(force: bool = False) -> Optional[Tuple[bool, str]]:
    """每 4 小时自动全量备份一次（含快照）"""
    global _last_sync_ts
    if not is_configured():
        return None
    now = time.time()
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
    return push_all()


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


def startup_restore() -> Dict[str, Any]:
    """兼容旧调用"""
    if not is_configured():
        return {"configured": False}
    ensure_bucket()
    r = pull_all()
    r["configured"] = True
    return r


def auto_sync_if_due(force: bool = False) -> Optional[Dict]:
    """兼容旧调用"""
    result = auto_push_if_due(force=force)
    if result is None:
        return None
    ok, msg = result
    return {"_result": (ok, msg)}


# ════════════════════════════════════════════════════════════════════
# 状态查询
# ════════════════════════════════════════════════════════════════════
def get_sync_status() -> Dict[str, Any]:
    if not is_configured():
        return {"configured": False, "status": "未配置"}
    meta = _download_latest("meta")
    if not meta:
        return {"configured": True, "status": "尚未同步", "last_sync": "—",
                "watchlist_cnt": 0, "scan_results_cnt": 0, "elapsed_h": 0}
    elapsed_h = (time.time() - float(meta.get("last_sync_ts", 0))) / 3600
    return {
        "configured":       True,
        "status":           "正常",
        "last_sync":        meta.get("last_sync", "—"),
        "last_sync_ts":     meta.get("last_sync_ts", 0),
        "watchlist_cnt":    meta.get("watchlist_cnt", 0),
        "scan_results_cnt": meta.get("scan_results_cnt", 0),
        "elapsed_h":        round(elapsed_h, 1),
    }


def time_to_next_sync_str() -> str:
    if not is_configured():
        return "未配置"
    meta = _download_latest("meta")
    if not meta or not meta.get("last_sync_ts"):
        return "立即同步"
    remain = max(0.0, SYNC_INTERVAL_SEC - (time.time() - float(meta["last_sync_ts"])))
    if remain <= 0:
        return "已到期，下次访问触发"
    h, m = int(remain // 3600), int((remain % 3600) // 60)
    return f"{h}h {m:02d}m 后"
