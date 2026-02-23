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

_MAX_HIST   = 50
_MAX_ALERTS = 200
_MAX_ALLRES = 5000   # 所有品种×框架合并缓存上限

# ── 备份目录 ─────────────────────────────────────────────────────────
_BACKUP_DIR = os.path.join(_BASE, "backups")


def _ensure_backup_dir():
    os.makedirs(_BACKUP_DIR, exist_ok=True)


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
    # 保存最新明细
    _save(F_RES, result_rows)

    # 合并到全量缓存（按 ticker+timeframe 去重，保留最新）
    allres = _load(F_ALLRES, [])
    if not isinstance(allres, list):
        allres = []
    existing = {(r["ticker"], r["timeframe"]): r
                for r in allres if isinstance(r, dict) and r.get("ticker")}
    for r in result_rows:
        key = (r["ticker"], r["timeframe"])
        existing[key] = r
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
    # 扫描完成后触发云端同步检查
    try:
        import cloud_sync
        cloud_sync.auto_sync_if_due()
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
    return [i for i in items if isinstance(i, dict) and i.get("ticker")]


def save_watchlist(items: List[Dict]) -> bool:
    ok = _save_with_backup(F_WATCHLIST, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.push_watchlist()
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
