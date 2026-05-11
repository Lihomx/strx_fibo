"""
storage.py — JSON 本地存储（支持分批缓存合并）
文件：
  data_config.json   — 用户设置
  data_history.json  — 扫描会话列表（最多 50 条）
  data_results.json  — 最新一次扫描明细
  data_allresults.json — 所有会话明细（合并缓存，最多 2000 条）
  data_alerts.json   — 告警日志（最多 200 条）
  data_groups.json   — 已扫描品种组记录
"""

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

# ── 文件路径 ─────────────────────────────────────────────────────────
_BASE     = os.path.dirname(os.path.abspath(__file__))
F_CFG     = os.path.join(_BASE, "data_config.json")
F_HIST    = os.path.join(_BASE, "data_history.json")
F_RES     = os.path.join(_BASE, "data_results.json")
F_ALLRES  = os.path.join(_BASE, "data_allresults.json")
F_ALERTS  = os.path.join(_BASE, "data_alerts.json")
F_GROUPS  = os.path.join(_BASE, "data_groups.json")
F_SCAN_SNAPSHOT_DIR = os.path.join(_BASE, "scan_snapshots")

_MAX_HIST   = 50
_MAX_ALERTS = 200
_MAX_ALLRES = 5000   # 所有品种×框架合并缓存上限
_MAX_SCAN_SNAPSHOTS = 200

# ── 备份目录 ─────────────────────────────────────────────────────────
_BACKUP_DIR = os.path.join(_BASE, "backups")


def _ensure_backup_dir():
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def _ensure_scan_snapshot_dir():
    os.makedirs(F_SCAN_SNAPSHOT_DIR, exist_ok=True)


# ── 通用 IO ──────────────────────────────────────────────────────────
def _load(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save(path: str, data) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _save_with_backup(path: str, data) -> bool:
    """写入文件，同时在 backups/ 目录保留带时间戳的副本（仅限自选收藏相关文件）。"""
    ok = _save(path, data)
    if ok:
        try:
            _ensure_backup_dir()
            ts       = time.strftime("%Y%m%d_%H%M%S")
            basename = os.path.splitext(os.path.basename(path))[0]
            bak_path = os.path.join(_BACKUP_DIR, f"{basename}_{ts}.json")
            _save(bak_path, data)
            # 只保留最近 30 个备份（按文件名倒序）
            all_baks = sorted(
                [f for f in os.listdir(_BACKUP_DIR) if f.startswith(basename)],
                reverse=True,
            )
            for old_bak in all_baks[30:]:
                try:
                    os.remove(os.path.join(_BACKUP_DIR, old_bak))
                except Exception:
                    pass
        except Exception:
            pass   # 备份失败不影响主流程
    return ok


# ── 异步推送工具 ────────────────────────────────────────────────────

def _async_push(fn, *args, **kwargs):
    """在后台守护线程中执行推送，不阻塞主线程。"""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


# ── 配置 ─────────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "lookback":         100,
    "fibo_low":         0.5,
    "fibo_high":        0.618,
    "watch_dist":       5.0,
    "alert_cooldown":   240,
    "data_source":      "yfinance",
    "twelvedata_key":   "",
    "dingtalk_webhook": "",
    "dingtalk_secret":  "",
    "telegram_token":   "",
    "telegram_chat_id": "",
}


def load_config() -> Dict:
    cfg = _load(F_CFG, {})
    return {**DEFAULT_CFG, **cfg}


def save_config(cfg: Dict) -> bool:
    return _save(F_CFG, cfg)


# ── 扫描会话 ─────────────────────────────────────────────────────────
def save_scan(session_row: Dict, result_rows: List[Dict]) -> bool:
    # 给每条结果打扫描时间戳
    scan_ts = _now_str()
    for r in result_rows:
        r.setdefault("scan_time", scan_ts)

    # 保存最新明细
    _save(F_RES, result_rows)

    # 合并到全量缓存（同 ticker+timeframe 只保留最新，新结果无条件覆盖旧结果）
    allres = _load(F_ALLRES, [])
    if not isinstance(allres, list):
        allres = []
    existing = {(r["ticker"], r["timeframe"]): r
                for r in allres if isinstance(r, dict) and r.get("ticker")}
    for r in result_rows:
        if isinstance(r, dict) and r.get("ticker") and r.get("timeframe"):
            existing[(r["ticker"], r["timeframe"])] = r  # 新结果覆盖旧结果
    merged = list(existing.values())
    if len(merged) > _MAX_ALLRES:
        merged = merged[-_MAX_ALLRES:]
    _save(F_ALLRES, merged)

    # 保存会话摘要（防御：旧数据可能是dict格式，强制转为list）
    hist = _load(F_HIST, [])
    if not isinstance(hist, list):
        hist = []
    hist.append(session_row)
    if len(hist) > _MAX_HIST:
        hist = hist[-_MAX_HIST:]
    result = _save(F_HIST, hist)

    # 扫描完成后触发云端同步检查（异步，不阻塞扫描结果展示）
    try:
        import cloud_sync
        _async_push(cloud_sync.auto_sync_if_due)
    except Exception:
        pass

    return result


def load_sessions(limit: int = 10) -> List[Dict]:
    hist = _load(F_HIST, [])
    if not isinstance(hist, list):
        hist = []
    # 只保留有效的dict记录
    hist = [s for s in hist if isinstance(s, dict) and s.get("session_id")]
    return list(reversed(hist))[:limit]


def load_latest_results(inzone_only: bool = False) -> List[Dict]:
    # 优先返回全量合并缓存（防御：确保是list of dict）
    allres = _load(F_ALLRES, [])
    if not isinstance(allres, list):
        allres = []
    if not allres:
        allres = _load(F_RES, [])
        if not isinstance(allres, list):
            allres = []
    # 只保留有效dict记录
    allres = [r for r in allres if isinstance(r, dict) and r.get("ticker")]
    if inzone_only:
        return [r for r in allres if r.get("in_zone")]
    return allres


def load_session_results(session_id: str) -> List[Dict]:
    """读取全量缓存中属于特定会话的记录"""
    snap_rows = load_scan_snapshot_rows(session_id)
    if snap_rows:
        return snap_rows

    allres = _load(F_ALLRES, [])
    if not isinstance(allres, list):
        allres = []
    allres = [r for r in allres if isinstance(r, dict)]
    filtered = [r for r in allres if r.get("session_id") == session_id]
    if not filtered:
        # 降级：读最新明细
        results = _load(F_RES, [])
        if not isinstance(results, list):
            results = []
        filtered = [r for r in results
                    if isinstance(r, dict) and r.get("session_id") == session_id]
    return filtered


def _scan_snapshot_file(session_id: str) -> str:
    sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
    return os.path.join(F_SCAN_SNAPSHOT_DIR, f"{sid}.json")


def save_scan_snapshot(session_row: Dict, result_rows: List[Dict]) -> bool:
    """按 session 保存完整扫描明细快照，支持后续一键恢复。"""
    sid = session_row.get("session_id")
    if not sid:
        return False
    try:
        _ensure_scan_snapshot_dir()
        payload = {
            "meta": dict(session_row or {}),
            "rows": [r for r in (result_rows or []) if isinstance(r, dict)],
            "saved_at": _now_str(),
        }
        ok = _save(_scan_snapshot_file(sid), payload)
        if not ok:
            return False

        # 清理旧快照，最多保留 _MAX_SCAN_SNAPSHOTS 个
        snaps = []
        for fname in os.listdir(F_SCAN_SNAPSHOT_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(F_SCAN_SNAPSHOT_DIR, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except Exception:
                mtime = 0
            snaps.append((mtime, fpath))
        snaps.sort(reverse=True)
        for _, old_path in snaps[_MAX_SCAN_SNAPSHOTS:]:
            try:
                os.remove(old_path)
            except Exception:
                pass
        return True
    except Exception:
        return False


def load_scan_snapshot_rows(session_id: str) -> List[Dict]:
    """读取某次扫描的完整快照明细（若存在）。"""
    try:
        fp = _scan_snapshot_file(session_id)
        if not os.path.exists(fp):
            return []
        data = _load(fp, {})
        rows = data.get("rows", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict) and r.get("ticker")]
    except Exception:
        return []


def has_scan_snapshot(session_id: str) -> bool:
    try:
        return os.path.exists(_scan_snapshot_file(session_id))
    except Exception:
        return False


def restore_scan_snapshot(session_id: str, replace_allres: bool = True) -> tuple:
    """恢复某次扫描快照到当前监控面板数据。"""
    rows = load_scan_snapshot_rows(session_id)
    if not rows:
        return False, "未找到该批次快照或快照为空", 0

    ok_res = _save(F_RES, rows)
    if not ok_res:
        return False, "写入当前结果失败", 0

    if replace_allres:
        ok_all = _save(F_ALLRES, rows)
    else:
        allres = _load(F_ALLRES, [])
        if not isinstance(allres, list):
            allres = []
        existing = {(r.get("ticker"), r.get("timeframe")): r for r in allres if isinstance(r, dict)}
        for r in rows:
            existing[(r.get("ticker"), r.get("timeframe"))] = r
        merged = list(existing.values())
        if len(merged) > _MAX_ALLRES:
            merged = merged[-_MAX_ALLRES:]
        ok_all = _save(F_ALLRES, merged)
    if not ok_all:
        return False, "写入全量缓存失败", 0

    return True, "恢复成功", len(rows)


def has_scan_data() -> bool:
    if os.path.exists(F_ALLRES):
        d = _load(F_ALLRES, [])
        if d: return True
    if os.path.exists(F_RES):
        d = _load(F_RES, [])
        if d: return True
    return False


def clear_all_data() -> bool:
    ok = True
    for f in [F_HIST, F_RES, F_ALLRES, F_ALERTS, F_GROUPS]:
        if os.path.exists(f):
            try: os.remove(f)
            except: ok = False
    return ok


def clear_all_scan_data() -> bool:
    """清空扫描结果（保留自选收藏和配置），用于「清空扫描结果」按钮"""
    ok = True
    for f in [F_HIST, F_RES, F_ALLRES, F_GROUPS]:
        if os.path.exists(f):
            try: os.remove(f)
            except: ok = False
    return ok


# ── 已扫描组记录（用于标注哪些组已缓存）────────────────────────────
def load_scanned_groups() -> List[str]:
    return _load(F_GROUPS, [])


def save_scanned_groups(groups: List[str]) -> bool:
    existing = set(_load(F_GROUPS, []))
    existing.update(groups)
    return _save(F_GROUPS, list(existing))


def clear_scanned_groups() -> bool:
    return _save(F_GROUPS, [])


# ── 告警日志 ─────────────────────────────────────────────────────────
def log_alert(entry: Dict) -> bool:
    logs: List[Dict] = _load(F_ALERTS, [])
    logs.append(entry)
    if len(logs) > _MAX_ALERTS:
        logs = logs[-_MAX_ALERTS:]
    return _save(F_ALERTS, logs)


def load_alerts(limit: int = 100) -> List[Dict]:
    logs = _load(F_ALERTS, [])
    return list(reversed(logs))[:limit]


def clear_alerts() -> bool:
    return _save(F_ALERTS, [])


# ── 自选收藏夹 ──────────────────────────────────────────────────────
F_WATCHLIST = os.path.join(_BASE, "data_watchlist.json")
F_WATCHLIST_ARCHIVE = os.path.join(_BASE, "data_watchlist_archive.json")


def load_watchlist() -> List[Dict]:
    """返回收藏夹列表，每项: {ticker, name, notes:[], added_at}"""
    items = _load(F_WATCHLIST, [])
    if not isinstance(items, list):
        items = []
    items = [i for i in items if isinstance(i, dict) and i.get("ticker")]

    # ── 自动迁移：若 category_id 存的是分类名称而非 UUID，修正为 UUID ──
    # 兼容旧版本数据（新版本统一用 UUID）
    try:
        cats = _load(F_WL_CATS, [])
        if cats:
            name_to_id = {c["name"]: c["id"] for c in cats if c.get("name") and c.get("id")}
            all_ids    = {c["id"] for c in cats if c.get("id")}
            migrated   = False
            for item in items:
                cid = item.get("category_id")
                if cid and cid not in all_ids and cid in name_to_id:
                    item["category_id"] = name_to_id[cid]
                    migrated = True
            if migrated:
                _save_with_backup(F_WATCHLIST, items)
    except Exception:
        pass

    return items


def save_watchlist(items: List[Dict]) -> bool:
    ok = _save_with_backup(F_WATCHLIST, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_watchlist)  # 异步，不阻塞 UI
        except Exception:
            pass
    return ok


def load_watchlist_archive() -> List[Dict]:
    """返回已软删除的品种存档"""
    items = _load(F_WATCHLIST_ARCHIVE, [])
    if not isinstance(items, list):
        items = []
    return [i for i in items if isinstance(i, dict) and i.get("ticker")]


def save_watchlist_archive(items: List[Dict]) -> bool:
    return _save(F_WATCHLIST_ARCHIVE, items)


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def add_to_watchlist(ticker: str, name: str = "", note: str = "",
                     img_url: str = "") -> bool:
    """添加品种到收藏夹。notes 字段为列表，每条含 {text, img_url, ts}。
    若品种已在存档中，自动恢复。"""
    ticker = ticker.strip().upper()
    if not ticker:
        return False

    items = load_watchlist()
    existing = [i for i in items if i["ticker"].upper() == ticker]
    if existing:
        return False  # 已存在

    # 检查是否在存档中，如在则恢复
    archive = load_watchlist_archive()
    restored = next((a for a in archive if a["ticker"].upper() == ticker), None)

    if restored:
        entry = restored.copy()
        entry["deleted_at"] = None
        # 更新名称（如有）
        if name.strip():
            entry["name"] = name.strip()
    else:
        entry = {
            "ticker":   ticker,
            "name":     name.strip(),
            "notes":    [],
            "added_at": _now_str(),
        }

    # 追加首条备注
    if note.strip():
        entry.setdefault("notes", []).append({
            "text":    note.strip(),
            "img_url": img_url.strip(),
            "ts":      _now_str(),
        })

    items.append(entry)
    ok = save_watchlist(items)

    # 从存档移除（已恢复）
    if restored and ok:
        new_archive = [a for a in archive if a["ticker"].upper() != ticker]
        save_watchlist_archive(new_archive)

    return ok


def remove_from_watchlist(ticker: str) -> bool:
    """软删除：将品种移入存档，保留所有历史备注。"""
    ticker = ticker.strip().upper()
    items   = load_watchlist()
    target  = next((i for i in items if i["ticker"].upper() == ticker), None)
    if not target:
        return False

    # 写入存档
    archive = load_watchlist_archive()
    # 更新或追加
    new_archive = [a for a in archive if a["ticker"].upper() != ticker]
    archived_entry = target.copy()
    archived_entry["deleted_at"] = _now_str()
    new_archive.append(archived_entry)
    save_watchlist_archive(new_archive)

    # 从活跃列表移除
    new_items = [i for i in items if i["ticker"].upper() != ticker]
    return save_watchlist(new_items)


def restore_from_archive(ticker: str) -> bool:
    """从存档恢复品种到收藏夹。"""
    ticker  = ticker.strip().upper()
    archive = load_watchlist_archive()
    target  = next((a for a in archive if a["ticker"].upper() == ticker), None)
    if not target:
        return False

    items = load_watchlist()
    if any(i["ticker"].upper() == ticker for i in items):
        return False  # 已在活跃列表

    entry = target.copy()
    entry["deleted_at"] = None
    items.append(entry)
    ok = save_watchlist(items)

    if ok:
        new_archive = [a for a in archive if a["ticker"].upper() != ticker]
        save_watchlist_archive(new_archive)

    return ok


def add_watchlist_note(ticker: str, note_text: str,
                       img_url: str = "") -> bool:
    """向已收藏品种追加一条带时间戳的备注。"""
    ticker = ticker.strip().upper()
    if not note_text.strip():
        return False
    items = load_watchlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item.setdefault("notes", []).append({
                "text":    note_text.strip(),
                "img_url": img_url.strip(),
                "ts":      _now_str(),
            })
            return save_watchlist(items)
    return False


def update_watchlist_note(ticker: str, note: str) -> bool:
    """兼容旧接口：等同于追加一条备注。"""
    return add_watchlist_note(ticker, note)

# ── 备份 / 导出 / 导入 ──────────────────────────────────────────────

def export_watchlist_json() -> str:
    items   = load_watchlist()
    archive = load_watchlist_archive()
    payload = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version":     2,
        "watchlist":   items,
        "archive":     archive,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_watchlist_json(json_str: str, merge: bool = True):
    try:
        payload = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, f"JSON 格式错误：{e}"
    if isinstance(payload, list):
        imported_items = payload
        imported_arch  = []
    elif isinstance(payload, dict):
        imported_items = payload.get("watchlist", [])
        imported_arch  = payload.get("archive", [])
    else:
        return False, "不支持的 JSON 格式"
    if not isinstance(imported_items, list):
        return False, "watchlist 字段必须是列表"
    if merge:
        existing = load_watchlist()
        existing_tickers = {i["ticker"].upper() for i in existing}
        added = 0
        for item in imported_items:
            if isinstance(item, dict) and item.get("ticker"):
                if item["ticker"].upper() not in existing_tickers:
                    existing.append(item)
                    existing_tickers.add(item["ticker"].upper())
                    added += 1
        ok = save_watchlist(existing)
        return ok, f"合并完成：新增 {added} 个品种，已跳过重复 {len(imported_items)-added} 个"
    else:
        ok = save_watchlist(imported_items)
        if ok and imported_arch:
            save_watchlist_archive(imported_arch)
        return ok, f"替换完成：导入 {len(imported_items)} 个品种"


def list_backups() -> list:
    _ensure_backup_dir()
    result = []
    try:
        for fname in sorted(os.listdir(_BACKUP_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            fpath   = os.path.join(_BACKUP_DIR, fname)
            size_kb = os.path.getsize(fpath) // 1024
            mtime   = time.strftime("%Y-%m-%d %H:%M",
                                    time.localtime(os.path.getmtime(fpath)))
            result.append((fname, fpath, size_kb, mtime))
    except Exception:
        pass
    return result


def restore_from_backup_file(abs_path: str, merge: bool = True):
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            json_str = f.read()
        return import_watchlist_json(json_str, merge=merge)
    except FileNotFoundError:
        return False, "备份文件不存在"
    except Exception as e:
        return False, f"读取备份失败：{e}"


def get_watchlist_b64() -> str:
    import base64
    return base64.b64encode(export_watchlist_json().encode("utf-8")).decode("ascii")


def restore_from_secrets() -> tuple:
    import base64
    try:
        import streamlit as st
        b64 = st.secrets.get("WATCHLIST_BACKUP", "")
        if not b64:
            return False, "Secrets 中无 WATCHLIST_BACKUP"
        json_str = base64.b64decode(b64.encode("ascii")).decode("utf-8")
        return import_watchlist_json(json_str, merge=True)
    except Exception as e:
        return False, f"从 Secrets 恢复失败：{e}"


def save_to_secrets_hint() -> str:
    b64 = get_watchlist_b64()
    line1 = "# 粘贴到 Streamlit Cloud → Settings → Secrets"
    line2 = 'WATCHLIST_BACKUP = "' + b64 + '"'
    return line1 + "\n" + line2



# ── 存储统计 ─────────────────────────────────────────────────────────
def storage_stats() -> Dict[str, Any]:
    def fsize(p):
        try: return os.path.getsize(p) if os.path.exists(p) else 0
        except: return 0

    allres = _load(F_ALLRES, [])
    hist   = _load(F_HIST, [])
    return {
        "total_cached_results": len(allres),
        "unique_tickers": len(set(r["ticker"] for r in allres)),
        "sessions": len(hist),
        "allres_kb": fsize(F_ALLRES) // 1024,
        "config_kb": fsize(F_CFG) // 1024,
        "alerts_kb": fsize(F_ALERTS) // 1024,
        "scanned_groups": load_scanned_groups(),
    }


def toggle_pin_watchlist(ticker: str) -> bool:
    """切换品种置顶状态（pinned=True/False）。返回操作后的 pinned 值。"""
    ticker = ticker.strip().upper()
    items  = load_watchlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item["pinned"] = not item.get("pinned", False)
            save_watchlist(items)
            return item["pinned"]
    return False


# ════════════════════════════════════════════════════════════════════
# 自选收藏夹分类管理
# 分类树结构：[{id, name, parent_id, order, children:[]}, ...]
# 品种的分类通过 watchlist item 的 "category_id" 字段关联
# ════════════════════════════════════════════════════════════════════
F_WL_CATS = os.path.join(_BASE, "data_wl_categories.json")

_DEFAULT_CATS: List[Dict] = []   # 默认空分类（用户自定义）


def load_wl_categories() -> List[Dict]:
    """加载分类列表（扁平列表，带 parent_id 构成树）"""
    cats = _load(F_WL_CATS, _DEFAULT_CATS)
    if not isinstance(cats, list):
        cats = []
    # 确保每个分类有必要字段
    valid = []
    for c in cats:
        if isinstance(c, dict) and c.get("id") and c.get("name"):
            c.setdefault("parent_id", None)
            c.setdefault("order", 0)
            valid.append(c)
    return valid


def save_wl_categories(cats: List[Dict]) -> bool:
    ok = _save(F_WL_CATS, cats)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_wl_categories)  # 异步，不阻塞 UI
        except Exception:
            pass
    return ok


def add_wl_category(name: str, parent_id=None) -> Optional[str]:
    """新增分类，返回新分类 id；名称重复（同级）则返回 None"""
    import uuid
    name = name.strip()
    if not name:
        return None
    cats = load_wl_categories()
    # 同级不允许重名
    siblings = [c for c in cats if c.get("parent_id") == parent_id]
    if any(c["name"] == name for c in siblings):
        return None
    new_id  = str(uuid.uuid4())[:8]
    max_ord = max((c.get("order", 0) for c in siblings), default=-1) + 1
    cats.append({"id": new_id, "name": name, "parent_id": parent_id, "order": max_ord})
    save_wl_categories(cats)
    return new_id


def rename_wl_category(cat_id: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    cats = load_wl_categories()
    for c in cats:
        if c["id"] == cat_id:
            c["name"] = new_name
            return save_wl_categories(cats)
    return False


def delete_wl_category(cat_id: str, reassign_to=None) -> bool:
    """删除分类（及其所有子孙分类），品种重置为未分类"""
    cats = load_wl_categories()
    # 收集要删除的 id（含后代）
    to_del = _collect_descendants(cats, cat_id) | {cat_id}
    cats = [c for c in cats if c["id"] not in to_del]
    save_wl_categories(cats)
    # 清除品种中引用了被删分类的字段
    items = load_watchlist()
    changed = False
    for item in items:
        if item.get("category_id") in to_del:
            item["category_id"] = reassign_to
            changed = True
    if changed:
        save_watchlist(items)
    return True


def _collect_descendants(cats: List[Dict], parent_id: str) -> set:
    """递归收集所有后代 id"""
    result = set()
    for c in cats:
        if c.get("parent_id") == parent_id:
            result.add(c["id"])
            result |= _collect_descendants(cats, c["id"])
    return result


def reorder_wl_category(cat_id: str, direction: str) -> bool:
    """上移(up)/下移(down)同级分类"""
    cats = load_wl_categories()
    target = next((c for c in cats if c["id"] == cat_id), None)
    if not target:
        return False
    pid = target.get("parent_id")
    siblings = sorted([c for c in cats if c.get("parent_id") == pid],
                      key=lambda x: x.get("order", 0))
    idx = next((i for i, c in enumerate(siblings) if c["id"] == cat_id), -1)
    if idx < 0:
        return False
    if direction == "up" and idx > 0:
        siblings[idx]["order"], siblings[idx-1]["order"] = \
            siblings[idx-1].get("order", 0), siblings[idx].get("order", 0)
    elif direction == "down" and idx < len(siblings) - 1:
        siblings[idx]["order"], siblings[idx+1]["order"] = \
            siblings[idx+1].get("order", 0), siblings[idx].get("order", 0)
    else:
        return False
    return save_wl_categories(cats)


def set_watchlist_item_category(ticker: str, category_id) -> bool:
    """设置品种所属分类（None = 未分类）"""
    ticker = ticker.strip().upper()
    items  = load_watchlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item["category_id"] = category_id
            return save_watchlist(items)
    return False


def build_cat_tree(cats: List[Dict]) -> List[Dict]:
    """将扁平分类列表构建为树状结构（用于展示）"""
    cat_map = {c["id"]: dict(c, children=[]) for c in cats}
    roots = []
    for c in sorted(cats, key=lambda x: x.get("order", 0)):
        pid = c.get("parent_id")
        if pid and pid in cat_map:
            cat_map[pid]["children"].append(cat_map[c["id"]])
        else:
            roots.append(cat_map[c["id"]])
    return roots


# ── 今日已看（文件持久化，跨 session_state 重置不丢失）──────────────
import datetime as _dt

def _viewed_file() -> str:
    """每次动态获取路径，避免模块级变量未定义问题"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_wl_viewed.json")

def _today_str() -> str:
    return _dt.date.today().isoformat()

def load_viewed_today() -> set:
    """读取今日已看 ticker 集合"""
    data = _load(_viewed_file(), {})
    return set(data.get(_today_str(), []))

def save_viewed_today(viewed: set) -> bool:
    """保存今日已看 ticker 集合（只保留最近 7 天）"""
    fp = _viewed_file()
    data = _load(fp, {})
    today = _today_str()
    data[today] = sorted(viewed)
    cutoff = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
    data = {k: v for k, v in data.items() if k >= cutoff}
    return _save(fp, data)

def mark_viewed(ticker: str) -> bool:
    """标记某品种今日已看"""
    viewed = load_viewed_today()
    viewed.add(ticker.strip().upper())
    return save_viewed_today(viewed)

def unmark_viewed(ticker: str) -> bool:
    """取消某品种今日已看"""
    viewed = load_viewed_today()
    viewed.discard(ticker.strip().upper())
    return save_viewed_today(viewed)


def _tv_link_for_mark(ticker: str) -> str:
    """给 app.py 中转跳转用：根据 ticker 生成 TradingView URL"""
    try:
        import assets
        return assets.tv_url(ticker)
    except Exception:
        return f"https://cn.tradingview.com/chart/?symbol={ticker}"
