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
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 文件路径 ─────────────────────────────────────────────────────────
_BASE     = os.path.dirname(os.path.abspath(__file__))
F_CFG     = os.path.join(_BASE, "data_config.json")
F_HIST    = os.path.join(_BASE, "data_history.json")
F_RES     = os.path.join(_BASE, "data_results.json")
F_ALLRES  = os.path.join(_BASE, "data_allresults.json")
F_ALERTS  = os.path.join(_BASE, "data_alerts.json")
F_GROUPS  = os.path.join(_BASE, "data_groups.json")
F_SCAN_SNAPSHOT_DIR = os.path.join(_BASE, "scan_snapshots")

def get_allres_path(date_str: str) -> str:
    clean_date = "".join(c for c in str(date_str) if c.isalnum() or c in ("-", "_"))
    return os.path.join(os.path.dirname(F_CFG), f"data_allresults_{clean_date}.json")


_MAX_HIST   = 50
_MAX_ALERTS = 2000
_MAX_ALLRES = 5000   # 所有品种×框架合并缓存上限
_MAX_SCAN_SNAPSHOTS = 200
_MAX_IO_CACHE_SIZE = 100

# ── 备份目录 ─────────────────────────────────────────────────────────
_BACKUP_DIR = os.path.join(_BASE, "backups")


def _ensure_backup_dir():
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def _ensure_scan_snapshot_dir():
    os.makedirs(F_SCAN_SNAPSHOT_DIR, exist_ok=True)


IO_LOCK = threading.Lock()

_IO_CACHE: Dict[str, Tuple[float, Any]] = {}

def _prune_io_cache_if_needed():
    if len(_IO_CACHE) > _MAX_IO_CACHE_SIZE:
        keys_to_remove = list(_IO_CACHE.keys())[: len(_IO_CACHE) // 2]
        for k in keys_to_remove:
            _IO_CACHE.pop(k, None)

# ── 通用 IO ──────────────────────────────────────────────────────────
def _load(path: str, default):
    with IO_LOCK:
        try:
            if os.path.exists(path):
                mtime = os.path.getmtime(path)
                cached = _IO_CACHE.get(path)
                if cached and cached[0] == mtime:
                    return cached[1]
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _prune_io_cache_if_needed()
                _IO_CACHE[path] = (mtime, data)
                return data
        except Exception as e:
            logger.debug(f"_load error on {path}: {e}")
        return default


def _save(path: str, data) -> bool:
    with IO_LOCK:
        try:
            with open(path, "w", encoding="utf-8") as f:
                if isinstance(data, list) and len(data) > 500:
                    json.dump(data, f, ensure_ascii=False)
                else:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                mtime = os.path.getmtime(path)
                _prune_io_cache_if_needed()
                _IO_CACHE[path] = (mtime, data)
            except Exception:
                _IO_CACHE.pop(path, None)
            return True
        except Exception as e:
            logger.error(f"_save error writing to {path}: {e}")
            return False


# ── 告警冷却持久化 ───────────────────────────────────────────────────
F_COOLDOWN = os.path.join(_BASE, "data_cooldown.json")

def load_cooldowns() -> Dict[str, str]:
    return _load(F_COOLDOWN, {})

def save_cooldown(key: str, val_str: str) -> bool:
    data = load_cooldowns()
    data[key] = val_str
    
    # 仅当缓存 key 数量较多 (>300) 时执行过期清理，降低全量 isoformat 解析频次
    if len(data) > 300:
        now = datetime.now()
        pruned = {}
        for k, v in data.items():
            try:
                ts_str = v.split("|")[0] if "|" in v else v
                dt = datetime.fromisoformat(ts_str)
                # 保留 24 小时内的冷却记录
                if (now - dt).total_seconds() < 86400:
                    pruned[k] = v
            except Exception:
                pass
        data = pruned
    return _save(F_COOLDOWN, data)


def _save_with_backup(path: str, data) -> bool:
    """写入文件，同时在 backups/ 目录保留带时间戳的副本（仅限自选收藏相关文件）。"""
    ok = _save(path, data)
    if ok:
        def bg_backup():
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
        _async_push(bg_backup)
    return ok


# ── 异步推送工具（有界线程池）───────────────────────────────────────
from concurrent.futures import ThreadPoolExecutor

# 最多 3 个 IO 线程并发（备份、云同步等），防止线程池耗尽
_io_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="strx_io")


def _async_push(fn, *args, **kwargs):
    """将指定函数提交到有界线程池异步执行，防止线程池耗尽导致崩溃。"""
    try:
        _io_executor.submit(fn, *args, **kwargs)
    except RuntimeError:
        # executor 已关闭（死锁）：直接同步执行
        try:
            fn(*args, **kwargs)
        except Exception:
            pass
    except Exception:
        pass


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
    "dingtalk_webhooks_pool": [],   # 多机器人轮换池，空则使用上方单一配置
    "telegram_token":   "",
    "telegram_chat_id": "",
    "scan_enabled":     False,
    "scan_hour":        9,
    "scan_minute":      0,
    "scan_interval_minutes": 17,
    "daily_scan_enabled": True,
    "periodic_scan_enabled": True,
    "chartink_scan_enabled": True,
    "chartink_scan_interval_minutes": 60,
    "alert_cooldown_chartink": 240,
    "filter_4h_ema20": False,
    "filter_1h_ema20": False,
    "filter_15m_ema20": False,
    "filter_4h_ema20_bear": False,
    "filter_1h_ema20_bear": False,
    "filter_15m_ema20_bear": False,
    "homepage": "watchlist",
    "theme_style": "极简深邃 (Minimal Dark)",
    "font_size": "默认 (14px)",
    "alert_template": "📐 STRX Fibo 信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📏 黄金区: {zone_bot} – {zone_top}\n📉 回撤: {retrace_pct}%\n🔗 {url}\n🕐 {time}",
    "alert_template_ema_pivot": "🚀 EMA20 + Daily Pivot 信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📈 EMA20: {ema}\n🎯 Pivot: {pivot}\n🔗 {url}\n🕐 {time}",
    "alert_template_chartink": "📈 Chartink 4H Breakout 突破信号 {label}\n━━━━━━━━━━━━━━━━━━━━\n🏷 {name} ({ticker})\n📅 框架: {tf}\n💰 价格: {price}\n📊 4H成交量: {volume_4h}\n📈 RSI: {rsi}\n🔗 {url}\n🕐 {time}",
}


def load_config() -> Dict:
    cfg = _load(F_CFG, {})
    return {**DEFAULT_CFG, **cfg}


def save_config(cfg: Dict) -> bool:
    current = _load(F_CFG, {})
    current.update(cfg)
    ok = _save(F_CFG, current)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_config)
        except Exception:
            pass
    return ok


# ── 扫描会话 ─────────────────────────────────────────────────────────
def _load_all_results() -> List[Dict]:
    """读取所有分片数据并合并，同 ticker+timeframe 取最新的那个，自动清理多余 14 天的旧分片"""
    import glob
    merged_map = {}
    
    base_dir = os.path.dirname(F_CFG)
    files = glob.glob(os.path.join(base_dir, "data_allresults_*.json"))
    legacy_file = os.path.join(base_dir, "data_allresults.json")
    if os.path.exists(legacy_file):
        files.append(legacy_file)
        
    # 按文件修改时间排序
    files.sort(key=lambda x: os.path.getmtime(x))
    # 限制最多加载/保留最近 14 个分片，清理更旧的分片
    if len(files) > 14:
        to_delete = files[:-14]
        files = files[-14:]
        for df in to_delete:
            try:
                os.remove(df)
            except Exception:
                pass
        
    for fpath in files:
        rows = _load(fpath, [])
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and r.get("ticker") and r.get("timeframe"):
                    merged_map[(r["ticker"], r["timeframe"])] = r
                    
    return list(merged_map.values())


# ── 扫描会话 ─────────────────────────────────────────────────────────
def save_scan(session_row: Dict, result_rows: List[Dict]) -> bool:
    # 给每条结果打扫描时间戳
    scan_ts = _now_str()
    for r in result_rows:
        r.setdefault("scan_time", scan_ts)

    # 保存最新明细
    _save(F_RES, result_rows)

    # 合并到全量缓存（同 ticker+timeframe 只保留最新，新结果无条件覆盖旧结果）
    scan_date = session_row.get("scan_date") or time.strftime("%Y-%m-%d")
    shard_path = get_allres_path(scan_date)
    
    allres = _load(shard_path, [])
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
    _save(shard_path, merged)

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
    # 优先返回分片合并缓存
    allres = _load_all_results()
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
    """读取全量分片缓存中属于特定会话的记录"""
    snap_rows = load_scan_snapshot_rows(session_id)
    if snap_rows:
        return snap_rows

    allres = _load_all_results()
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

        # 异步清理旧快照，最多保留 _MAX_SCAN_SNAPSHOTS 个
        def bg_cleanup_snaps():
            try:
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
            except Exception:
                pass
        _async_push(bg_cleanup_snaps)
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


def find_latest_snapshot_session(exclude_session_ids: Optional[List[str]] = None) -> Optional[str]:
    """按快照时间倒序返回最近可恢复的 session_id。"""
    try:
        _ensure_scan_snapshot_dir()
        excludes = {
            str(s).strip() for s in (exclude_session_ids or [])
            if str(s).strip()
        }

        candidates = []
        for fname in os.listdir(F_SCAN_SNAPSHOT_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(F_SCAN_SNAPSHOT_DIR, fname)
            stem = os.path.splitext(fname)[0]

            data = _load(fpath, {})
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            sid = str(meta.get("session_id") or stem).strip()
            if not sid or sid in excludes:
                continue

            scan_time = ""
            if isinstance(meta, dict):
                scan_time = str(meta.get("scan_time") or meta.get("scan_date") or "")
            if not scan_time and isinstance(data, dict):
                scan_time = str(data.get("saved_at") or "")

            try:
                mtime = os.path.getmtime(fpath)
            except Exception:
                mtime = 0
            candidates.append((scan_time, mtime, sid))

        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates[0][2]
    except Exception:
        return None


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
    import glob
    base_dir = os.path.dirname(F_CFG)
    shards = glob.glob(os.path.join(base_dir, "data_allresults_*.json"))
    if shards:
        return True
    if os.path.exists(F_ALLRES):
        d = _load(F_ALLRES, [])
        if d: return True
    if os.path.exists(F_RES):
        d = _load(F_RES, [])
        if d: return True
    return False


def clear_all_data() -> bool:
    import glob
    ok = True
    for f in [F_HIST, F_RES, F_ALLRES, F_ALERTS, F_GROUPS]:
        if os.path.exists(f):
            try: os.remove(f)
            except: ok = False
    base_dir = os.path.dirname(F_CFG)
    shards = glob.glob(os.path.join(base_dir, "data_allresults_*.json"))
    for f in shards:
        if os.path.exists(f):
            try: os.remove(f)
            except: ok = False
    return ok


def clear_all_scan_data() -> bool:
    """清空扫描结果（保留自选收藏和配置），用于「清空扫描结果」按钮"""
    import glob
    ok = True
    for f in [F_HIST, F_RES, F_ALLRES, F_GROUPS]:
        if os.path.exists(f):
            try: os.remove(f)
            except: ok = False
    base_dir = os.path.dirname(F_CFG)
    shards = glob.glob(os.path.join(base_dir, "data_allresults_*.json"))
    for f in shards:
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


def log_alert(ticker_or_entry, name=None, timeframe=None, channel=None, status=None, message=None, scanner=None, label=None) -> bool:
    from datetime import datetime, timezone
    if isinstance(ticker_or_entry, dict):
        entry = ticker_or_entry
    else:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker_or_entry,
            "name": name or "",
            "timeframe": timeframe or "",
            "channel": channel or "",
            "status": status or "",
            "message": message or "",
            "scanner": scanner or "",
            "label": label or ""
        }
    logs: List[Dict] = _load(F_ALERTS, [])
    logs.append(entry)
    if len(logs) > _MAX_ALERTS:
        logs = logs[-_MAX_ALERTS:]
    ok = _save(F_ALERTS, logs)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync._upload_latest("alerts", logs)
        except Exception:
            pass
    return ok


def load_alerts(limit: int = 100) -> List[Dict]:
    logs = _load(F_ALERTS, [])
    logs_rev = list(reversed(logs))
    if limit == 0:
        return logs_rev
    return logs_rev[:limit]


def load_alert_log(limit: int = 100) -> List[Dict]:
    return load_alerts(limit)


def clear_alerts() -> bool:
    return _save(F_ALERTS, [])


def clear_alert_log() -> bool:
    return clear_alerts()


F_LINK_CLICKS = os.path.join(_BASE, "data_link_clicks.json")

def format_timestamp(ts_str: str, target_tz: str = None) -> str:
    """将 UTC ISO 时间戳转换为用户配置时区的标准可读格式 YYYY-MM-DD HH:MM:SS"""
    if not ts_str:
        return "—"
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        if not target_tz:
            cfg = load_config()
            target_tz = cfg.get("timezone") or cfg.get("display_timezone") or "Asia/Shanghai"
        
        s = str(ts_str).strip()
        if "T" in s or "+" in s or "Z" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_local = dt.astimezone(ZoneInfo(target_tz))
            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
        return s[:19].replace("T", " ")
    except Exception:
        return str(ts_str)[:19].replace("T", " ")

def get_today_str() -> str:
    """按用户配置时区返回当前日期字符串 YYYY-MM-DD"""
    try:
        cfg = load_config()
        tz_name = cfg.get("timezone") or cfg.get("display_timezone") or "Asia/Shanghai"
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
    except Exception:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

def increment_link_click(ticker: str, link_type: str = "tv") -> None:
    """记录一次行情链接点击，ticker维度，按日期分组并推送云端"""
    if not ticker:
        return
    today = get_today_str()

    data = _load(F_LINK_CLICKS, {})
    if not data:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.pull_link_clicks()
                data = _load(F_LINK_CLICKS, {})
        except Exception:
            pass

    if not isinstance(data, dict):
        data = {}
    key = f"{str(ticker).upper()}:{link_type}"
    if key not in data or not isinstance(data[key], dict):
        data[key] = {"total": 0, "by_date": {}}
    data[key]["total"] = data[key].get("total", 0) + 1
    by_date = data[key].get("by_date", {})
    if not isinstance(by_date, dict):
        by_date = {}
    by_date[today] = by_date.get(today, 0) + 1
    data[key]["by_date"] = by_date
    _save_with_backup(F_LINK_CLICKS, data)
    try:
        import cloud_sync
        if cloud_sync.is_configured():
            _async_push(cloud_sync.push_link_clicks)
    except Exception:
        pass


def get_link_clicks(ticker: str, link_type: str = "tv") -> dict:
    """获取某 ticker 的点击统计 {total, today}"""
    if not ticker:
        return {"total": 0, "today": 0}
    today = get_today_str()
    data = get_all_link_clicks()
    if not isinstance(data, dict):
        return {"total": 0, "today": 0}
    key = f"{str(ticker).upper()}:{link_type}"
    entry = data.get(key, {})
    if not isinstance(entry, dict):
        return {"total": 0, "today": 0}
    by_date = entry.get("by_date", {})
    today_count = by_date.get(today, 0) if isinstance(by_date, dict) else 0
    return {
        "total": entry.get("total", 0),
        "today": today_count
    }

def get_all_link_clicks() -> dict:
    """返回全量点击数据（如本地为空，尝试从云端恢复）"""
    res = _load(F_LINK_CLICKS, {})
    if not res:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.pull_link_clicks()
                res = _load(F_LINK_CLICKS, {})
        except Exception:
            pass
    return res if isinstance(res, dict) else {}


import threading as _threading

import time as _time

_FAV_LOCK_DICT = {}
_FAV_LOCK_OBJ = _threading.Lock()
F_FAV_LOG = os.path.join(_BASE, "data_fav_log.json")

def acquire_fav_lock(ticker: str, ttl_seconds: float = 0.1) -> bool:
    """获取指定 ticker 的自选操作内存锁，防止高频并发冲突（基于时间戳懒清理，无额外线程开销）"""
    t = ticker.strip().upper()
    if not t:
        return True
    now = _time.monotonic()
    with _FAV_LOCK_OBJ:
        # 清理过期锁
        expired = [k for k, exp in _FAV_LOCK_DICT.items() if exp <= now]
        for k in expired:
            del _FAV_LOCK_DICT[k]
        
        # 检查并设置锁
        if t in _FAV_LOCK_DICT:
            return False
        _FAV_LOCK_DICT[t] = now + ttl_seconds
        return True

def log_fav_action(ticker: str, op: str, success: bool = True, from_ajax: bool = False) -> None:
    """记录自选表/重点关注操作审计日志"""
    try:
        logs = _load(F_FAV_LOG, [])
        if not isinstance(logs, list):
            logs = []
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "ticker": ticker.strip().upper(),
            "op": op,
            "success": success,
            "from_ajax": from_ajax
        }
        logs.append(entry)
        if len(logs) > 200:
            logs = logs[-200:]
        _save(F_FAV_LOG, logs)
    except Exception:
        pass


F_STARRED = os.path.join(_BASE, "data_starred.json")
F_TICKER_NOTES = os.path.join(_BASE, "data_ticker_notes.json")

def load_starred_tickers() -> List[str]:
    res = _load(F_STARRED, [])
    if not isinstance(res, list):
        return []
    return [str(x).strip().upper() for x in res if x]

def save_starred_tickers(tickers: List[str]) -> bool:
    seen = set()
    clean = []
    for x in tickers:
        v = str(x).strip().upper()
        if v and v not in seen:
            seen.add(v)
            clean.append(v)
    ok = _save(F_STARRED, clean)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync._upload_latest("starred", clean)
                cloud_sync._upload_snapshot("starred", clean)
        except Exception:
            pass
    return ok

def star_ticker(ticker: str) -> bool:
    """显式添加重点关注状态"""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    starred = load_starred_tickers()
    if ticker not in starred:
        starred.append(ticker)
        return save_starred_tickers(starred)
    return True

def unstar_ticker(ticker: str) -> bool:
    """显式取消重点关注状态"""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    starred = load_starred_tickers()
    if ticker in starred:
        starred.remove(ticker)
        return save_starred_tickers(starred)
    return True

def toggle_starred_ticker(ticker: str) -> bool:
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    starred = load_starred_tickers()
    if ticker in starred:
        starred.remove(ticker)
    else:
        starred.append(ticker)
    return save_starred_tickers(starred)

def is_ticker_starred(ticker: str) -> bool:
    ticker = ticker.strip().upper()
    return ticker in load_starred_tickers()

def load_ticker_notes(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    all_notes = _load(F_TICKER_NOTES, {})
    if not isinstance(all_notes, dict):
        return {"text": "", "img_url": ""}
    val = all_notes.get(ticker, "")
    if isinstance(val, dict):
        return {"text": val.get("text", ""), "img_url": val.get("img_url", "")}
    return {"text": str(val).strip(), "img_url": ""}

def save_ticker_note(ticker: str, text: str, img_url: str = "") -> bool:
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    all_notes = _load(F_TICKER_NOTES, {})
    if not isinstance(all_notes, dict):
        all_notes = {}
    all_notes[ticker] = {
        "text": text.strip(),
        "img_url": img_url.strip()
    }
    return _save(F_TICKER_NOTES, all_notes)




# ── 自选收藏夹 ──────────────────────────────────────────────────────
F_WATCHLIST = os.path.join(_BASE, "data_watchlist.json")
F_WATCHLIST_ARCHIVE = os.path.join(_BASE, "data_watchlist_archive.json")
F_TRIPLE_BOTTOM = os.path.join(_BASE, "data_triple_bottom.json")
F_TB_SNAPSHOT_DIR = os.path.join(_BASE, "triple_bottom_snapshots")
F_TRIPLE_PATTERN = os.path.join(_BASE, "data_triple_pattern.json")
F_TP_SNAPSHOT_DIR = os.path.join(_BASE, "triple_pattern_snapshots")
F_FAILED_BREAKDOWN = os.path.join(_BASE, "data_failed_breakdown.json")
F_FB_SNAPSHOT_DIR = os.path.join(_BASE, "failed_breakdown_snapshots")



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
                cloud_sync.push_watchlist()  # 同步推送，确保实时落盘至云端
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
    ok = save_watchlist(new_items)
    # 取消自选时，同时自动取消重点关注
    unstar_ticker(ticker)
    return ok


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


def load_starred_tickers() -> List[str]:
    """获取所有已收藏的 ticker 列表（大写）"""
    items = load_watchlist()
    return [str(i.get("ticker", "")).strip().upper() for i in items if i.get("ticker")]


def toggle_star_ticker(ticker: str, name: str = "", note: str = "") -> bool:
    """切换收藏状态：未收藏则添加，已收藏则移除"""
    ticker = ticker.strip().upper()
    starred = set(load_starred_tickers())
    if ticker in starred:
        return remove_from_watchlist(ticker)
    else:
        return add_to_watchlist(ticker=ticker, name=name, note=note)


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


def list_backups(prefix: str = "data_watchlist") -> list:
    _ensure_backup_dir()
    result = []
    try:
        for fname in sorted(os.listdir(_BACKUP_DIR), reverse=True):
            if not fname.endswith(".json") or not fname.startswith(prefix):
                continue
            fpath   = os.path.join(_BACKUP_DIR, fname)
            size_kb = os.path.getsize(fpath) // 1024
            mtime   = time.strftime("%Y-%m-%d %H:%M",
                                    time.localtime(os.path.getmtime(fpath)))
            result.append({
                "name": fname,
                "path": fpath,
                "size_kb": size_kb,
                "time": mtime
            })
    except Exception:
        pass
    return result


def restore_backup(name: str, is_hotlist: bool = False) -> Tuple[bool, str]:
    _ensure_backup_dir()
    fpath = os.path.join(_BACKUP_DIR, name)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            json_str = f.read()
        if is_hotlist:
            return import_hotlist_json(json_str, merge=False)
        else:
            return import_watchlist_json(json_str, merge=False)
    except FileNotFoundError:
        return False, "备份文件不存在"
    except Exception as e:
        return False, f"读取备份失败：{e}"




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


# ════════════════════════════════════════════════════════════════════
# 热门品种 (Hot Assets) 管理层
# ════════════════════════════════════════════════════════════════════
F_HOTLIST = os.path.join(_BASE, "data_hotlist.json")
F_HOTLIST_ARCHIVE = os.path.join(_BASE, "data_hotlist_archive.json")
F_HL_CATS = os.path.join(_BASE, "data_hl_categories.json")


def load_hotlist() -> List[Dict]:
    """返回热门品种列表，每项: {ticker, name, notes:[], added_at}"""
    items = _load(F_HOTLIST, [])
    if not isinstance(items, list):
        items = []
    items = [i for i in items if isinstance(i, dict) and i.get("ticker")]
    return items


def save_hotlist(items: List[Dict]) -> bool:
    ok = _save_with_backup(F_HOTLIST, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_hotlist)  # 异步，不阻塞 UI
        except Exception:
            pass
    return ok


def load_hotlist_archive() -> List[Dict]:
    """返回已软删除的品种存档"""
    items = _load(F_HOTLIST_ARCHIVE, [])
    if not isinstance(items, list):
        items = []
    return [i for i in items if isinstance(i, dict) and i.get("ticker")]


def save_hotlist_archive(items: List[Dict]) -> bool:
    return _save(F_HOTLIST_ARCHIVE, items)


def add_to_hotlist(ticker: str, name: str = "", note: str = "",
                   img_url: str = "") -> bool:
    """添加品种到热门品种列表。notes 字段为列表，每条含 {text, img_url, ts}。
    若品种已在存档中，自动恢复。"""
    ticker = ticker.strip().upper()
    if not ticker:
        return False

    items = load_hotlist()
    existing = [i for i in items if i["ticker"].upper() == ticker]
    if existing:
        return False  # 已存在

    # 检查是否在存档中，如在则恢复
    archive = load_hotlist_archive()
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
    ok = save_hotlist(items)

    # 从存档移除（已恢复）
    if restored and ok:
        new_archive = [a for a in archive if a["ticker"].upper() != ticker]
        save_hotlist_archive(new_archive)

    return ok


def remove_from_hotlist(ticker: str) -> bool:
    """软删除：将品种移入存档，保留所有历史备注。"""
    ticker = ticker.strip().upper()
    items   = load_hotlist()
    target  = next((i for i in items if i["ticker"].upper() == ticker), None)
    if not target:
        return False

    # 写入存档
    archive = load_hotlist_archive()
    new_archive = [a for a in archive if a["ticker"].upper() != ticker]
    archived_entry = target.copy()
    archived_entry["deleted_at"] = _now_str()
    new_archive.append(archived_entry)
    save_hotlist_archive(new_archive)

    # 从活跃列表移除
    new_items = [i for i in items if i["ticker"].upper() != ticker]
    return save_hotlist(new_items)


def restore_hotlist_from_archive(ticker: str) -> bool:
    """从存档恢复品种到热门品种。"""
    ticker  = ticker.strip().upper()
    archive = load_hotlist_archive()
    target  = next((a for a in archive if a["ticker"].upper() == ticker), None)
    if not target:
        return False

    items = load_hotlist()
    if any(i["ticker"].upper() == ticker for i in items):
        return False  # 已在活跃列表

    entry = target.copy()
    entry["deleted_at"] = None
    items.append(entry)
    ok = save_hotlist(items)

    if ok:
        new_archive = [a for a in archive if a["ticker"].upper() != ticker]
        save_hotlist_archive(new_archive)

    return ok


def add_hotlist_note(ticker: str, note_text: str,
                     img_url: str = "") -> bool:
    """向热门品种追加一条带时间戳的备注。"""
    ticker = ticker.strip().upper()
    if not note_text.strip():
        return False
    items = load_hotlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item.setdefault("notes", []).append({
                "text":    note_text.strip(),
                "img_url": img_url.strip(),
                "ts":      _now_str(),
            })
            return save_hotlist(items)
    return False


def toggle_pin_hotlist(ticker: str) -> bool:
    """切换品种置顶状态（pinned=True/False）。返回操作后的 pinned 值。"""
    ticker = ticker.strip().upper()
    items  = load_hotlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item["pinned"] = not item.get("pinned", False)
            save_hotlist(items)
            return item["pinned"]
    return False


# ── 热门品种分类管理 ──
def load_hl_categories() -> List[Dict]:
    """加载热门品种分类列表（扁平列表，带 parent_id 构成树）"""
    cats = _load(F_HL_CATS, [])
    if not isinstance(cats, list):
        cats = []
    valid = []
    for c in cats:
        if isinstance(c, dict) and c.get("id") and c.get("name"):
            c.setdefault("parent_id", None)
            c.setdefault("order", 0)
            valid.append(c)
    return valid


def save_hl_categories(cats: List[Dict]) -> bool:
    ok = _save(F_HL_CATS, cats)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_hl_categories)  # 异步，不阻塞 UI
        except Exception:
            pass
    return ok


def add_hl_category(name: str, parent_id=None) -> Optional[str]:
    import uuid
    name = name.strip()
    if not name:
        return None
    cats = load_hl_categories()
    siblings = [c for c in cats if c.get("parent_id") == parent_id]
    if any(c["name"] == name for c in siblings):
        return None
    new_id  = str(uuid.uuid4())[:8]
    max_ord = max((c.get("order", 0) for c in siblings), default=-1) + 1
    cats.append({"id": new_id, "name": name, "parent_id": parent_id, "order": max_ord})
    save_hl_categories(cats)
    return new_id


def rename_hl_category(cat_id: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    cats = load_hl_categories()
    for c in cats:
        if c["id"] == cat_id:
            c["name"] = new_name
            return save_hl_categories(cats)
    return False


def delete_hl_category(cat_id: str, reassign_to=None) -> bool:
    cats = load_hl_categories()
    to_del = _collect_descendants(cats, cat_id) | {cat_id}
    cats = [c for c in cats if c["id"] not in to_del]
    save_hl_categories(cats)
    items = load_hotlist()
    changed = False
    for item in items:
        if item.get("category_id") in to_del:
            item["category_id"] = reassign_to
            changed = True
    if changed:
        save_hotlist(items)
    return True


def reorder_hl_category(cat_id: str, direction: str) -> bool:
    cats = load_hl_categories()
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
    return save_hl_categories(cats)


def set_hotlist_item_category(ticker: str, category_id) -> bool:
    ticker = ticker.strip().upper()
    items  = load_hotlist()
    for item in items:
        if item["ticker"].upper() == ticker:
            item["category_id"] = category_id
            return save_hotlist(items)
    return False


# ── 热门品种今日已看 ──
def _hl_viewed_file() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_hl_viewed.json")


def load_hl_viewed_today() -> set:
    data = _load(_hl_viewed_file(), {})
    return set(data.get(_today_str(), []))


def save_hl_viewed_today(viewed: set) -> bool:
    fp = _hl_viewed_file()
    data = _load(fp, {})
    today = _today_str()
    data[today] = sorted(viewed)
    cutoff = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
    data = {k: v for k, v in data.items() if k >= cutoff}
    return _save(fp, data)


def mark_hl_viewed(ticker: str) -> bool:
    viewed = load_hl_viewed_today()
    viewed.add(ticker.strip().upper())
    return save_hl_viewed_today(viewed)


def unmark_hl_viewed(ticker: str) -> bool:
    viewed = load_hl_viewed_today()
    viewed.discard(ticker.strip().upper())
    return save_hl_viewed_today(viewed)


def export_hotlist_json() -> str:
    items   = load_hotlist()
    archive = load_hotlist_archive()
    payload = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version":     2,
        "hotlist":     items,
        "archive":     archive,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_hotlist_json(json_str: str, merge: bool = True):
    try:
        payload = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, f"JSON 格式错误：{e}"
    if isinstance(payload, list):
        imported_items = payload
        imported_arch  = []
    elif isinstance(payload, dict):
        imported_items = payload.get("hotlist", [])
        imported_arch  = payload.get("archive", [])
    else:
        return False, "不支持的 JSON 格式"
    if not isinstance(imported_items, list):
        return False, "hotlist 字段必须是列表"
    if merge:
        existing = load_hotlist()
        existing_tickers = {i["ticker"].upper() for i in existing}
        added = 0
        for item in imported_items:
            if isinstance(item, dict) and item.get("ticker"):
                if item["ticker"].upper() not in existing_tickers:
                    existing.append(item)
                    existing_tickers.add(item["ticker"].upper())
                    added += 1
        ok = save_hotlist(existing)
        return ok, f"合并完成：新增 {added} 个品种，已跳过重复 {len(imported_items)-added} 个"
    else:
        ok = save_hotlist(imported_items)
        if ok and imported_arch:
            save_hotlist_archive(imported_arch)
        return ok, f"替换完成：导入 {len(imported_items)} 个品种"


def load_triple_bottom() -> List[Dict]:
    """返回三重底扫描结果，自动去重并按置信度排序，保证极速读取"""
    res = _load(F_TRIPLE_BOTTOM, [])
    if not isinstance(res, list):
        return []
    seen = {}
    for r in res:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        k = (str(r.get("symbol")).upper(), str(r.get("period", "")).lower(), str(r.get("pattern", "")))
        if k not in seen or float(r.get("confidence", 0)) > float(seen[k].get("confidence", 0)):
            seen[k] = r
    deduped = list(seen.values())
    deduped.sort(key=lambda x: float(x.get("confidence", 0.0)), reverse=True)
    return deduped


def save_triple_bottom(items: List[Dict], with_backup: bool = True) -> bool:
    """保存三重底扫描结果"""
    if with_backup:
        ok = _save_with_backup(F_TRIPLE_BOTTOM, items)
    else:
        ok = _save(F_TRIPLE_BOTTOM, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_triple_bottom)
        except Exception:
            pass
    return ok


def append_triple_bottom_results(new_items: List[Dict], with_backup: bool = True) -> bool:
    """增量合并三重底扫描结果：按 (symbol, period, pattern) 去重合并，保留最高置信度结果"""
    if not new_items:
        return True
    current = load_triple_bottom()
    item_map = {}
    for it in current:
        k = (str(it.get("symbol", "")).upper(), str(it.get("period", "")).lower(), str(it.get("pattern", "")))
        item_map[k] = it
    for it in new_items:
        k = (str(it.get("symbol", "")).upper(), str(it.get("period", "")).lower(), str(it.get("pattern", "")))
        if k not in item_map or float(it.get("confidence", 0.0)) >= float(item_map[k].get("confidence", 0.0)):
            item_map[k] = it
            
    merged = list(item_map.values())
    merged.sort(key=lambda x: float(x.get("confidence", 0.0)), reverse=True)
    return save_triple_bottom(merged, with_backup=with_backup)

def clear_triple_bottom_results() -> bool:
    """清空当前三重底扫描结果（清空前会自动进行备份快照）"""
    current_items = load_triple_bottom()
    if current_items:
        backup_triple_bottom(current_items)
    return save_triple_bottom([])

# ── 三重底分批扫描状态持久化 ────────────────────────────────────
F_TB_BATCH_STATE = os.path.join(_BASE, "data_tb_batch_state.json")

def load_tb_batch_state() -> Dict:
    """读取三重底分批扫描状态"""
    default = {
        "all_tickers": [],
        "total_tickers": 0,
        "selected_periods": ["1d", "1w", "1mo"],
        "batch_size": 50,
        "current_batch": 0,
        "total_batches": 0,
        "done_tickers": [],
        "scan_params": {},
        "auto_continue": True,
        "status": "idle", # idle | in_progress | batch_done | all_done
        "updated_at": None,
    }
    st = _load(F_TB_BATCH_STATE, default)
    if not isinstance(st, dict):
        return default
    return {**default, **st}

def save_tb_batch_state(state: Dict) -> bool:
    """保存三重底分批扫描状态（自动确保 total_tickers / total_batches 准确无误）"""
    if isinstance(state, dict):
        all_tks = state.get("all_tickers", [])
        if all_tks:
            state["total_tickers"] = len(all_tks)
            bsize = state.get("batch_size", 50)
            state["total_batches"] = (len(all_tks) + bsize - 1) // bsize
    return _save(F_TB_BATCH_STATE, state)


def clear_tb_batch_state() -> bool:
    """清除三重底分批扫描状态"""
    return _save(F_TB_BATCH_STATE, {})


def _ensure_tb_snapshot_dir():
    os.makedirs(F_TB_SNAPSHOT_DIR, exist_ok=True)

def backup_triple_bottom(items: List[Dict]) -> str:
    """备份当前三重底扫描批次到快照文件夹，返回备份产生的 session_id"""
    if not items:
        return ""
    try:
        _ensure_tb_snapshot_dir()
        sid = f"tb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fpath = os.path.join(F_TB_SNAPSHOT_DIR, f"{sid}.json")
        payload = {
            "session_id": sid,
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rows": items,
            "saved_at": _now_str()
        }
        if _save(fpath, payload):
            try:
                import cloud_sync
                if cloud_sync.is_configured():
                    _async_push(lambda: cloud_sync.push_tb_snapshot(sid, payload))
            except Exception:
                pass
            # 异步/同步清理旧快照，最多保留 100 个
            try:
                snaps = []
                for fname in os.listdir(F_TB_SNAPSHOT_DIR):
                    if fname.endswith(".json"):
                        fp = os.path.join(F_TB_SNAPSHOT_DIR, fname)
                        mtime = os.path.getmtime(fp)
                        snaps.append((mtime, fp))
                snaps.sort(reverse=True)
                for _, old_path in snaps[100:]:
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            except Exception:
                pass
            return sid
    except Exception as e:
        import logging
        logging.error(f"backup_triple_bottom error: {e}")
    return ""

def load_tb_snapshots() -> List[Dict]:
    """获取所有三重底的快照批次列表，按时间倒序排列"""
    try:
        _ensure_tb_snapshot_dir()
        candidates = []
        for fname in os.listdir(F_TB_SNAPSHOT_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(F_TB_SNAPSHOT_DIR, fname)
                data = _load(fpath, {})
                if isinstance(data, dict):
                    sid = data.get("session_id", os.path.splitext(fname)[0])
                    scan_time = data.get("scan_time") or data.get("saved_at") or "—"
                    rows = data.get("rows", [])
                    candidates.append({
                        "session_id": sid,
                        "scan_time": scan_time,
                        "count": len(rows),
                        "mtime": os.path.getmtime(fpath)
                    })
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        return candidates
    except Exception as e:
        import logging
        logging.error(f"load_tb_snapshots error: {e}")
        return []

def restore_tb_snapshot(session_id: str) -> tuple:
    """从备份批次恢复三重底扫描结果"""
    try:
        _ensure_tb_snapshot_dir()
        sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
        fpath = os.path.join(F_TB_SNAPSHOT_DIR, f"{sid}.json")
        if not os.path.exists(fpath):
            return False, "备份批次不存在", 0
        data = _load(fpath, {})
        rows = data.get("rows", []) if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return False, "无效的快照文件格式", 0
        ok = save_triple_bottom(rows)
        if ok:
            return True, "恢复成功", len(rows)
        return False, "保存失败", 0
    except Exception as e:
        return False, f"恢复异常: {e}", 0


# ── 🌟 三重顶底 (Triple Pattern: Bottom & Top) 双向扫描持久化 ─────────

def _ensure_tp_progress(r: Dict) -> Dict:
    """确保三重顶底记录包含正确的 breakout_progress 跑势进度 (0%~300%+)"""
    bp = r.get("breakout_progress")
    if bp is not None:
        try:
            val = float(bp)
            import math
            if not math.isnan(val):
                r["breakout_progress"] = round(val, 1)
                return r
        except Exception:
            pass

    st_val = str(r.get("status", "active")).lower()
    if st_val != "confirmed":
        r["breakout_progress"] = 0.0
        return r

    try:
        direction = str(r.get("direction", "bullish")).lower()
        close = float(r.get("latest_close", 0.0))
        neckline = float(r.get("neckline", 0.0))
        p1 = float(r.get("p1", r.get("pt1", 0.0)))
        p2 = float(r.get("p2", r.get("pt3", 0.0)))
        p3 = float(r.get("p3", r.get("pt5", 0.0)))

        if direction == "bullish":
            min_low = min(p1, p2, p3) if (p1 > 0 and p2 > 0 and p3 > 0) else (neckline * 0.95)
            h = max(neckline - min_low, neckline * 0.01)
            prog = max(0.0, (close - neckline) / h * 100.0)
        else:
            max_high = max(p1, p2, p3) if (p1 > 0 and p2 > 0 and p3 > 0) else (neckline * 1.05)
            h = max(max_high - neckline, neckline * 0.01)
            prog = max(0.0, (neckline - close) / h * 100.0)
        r["breakout_progress"] = round(prog, 1)
    except Exception:
        r["breakout_progress"] = 0.0
    return r


def load_triple_pattern() -> List[Dict]:
    """返回三重顶底双向扫描结果，按 (symbol, period, direction, pattern) 自动去重并按置信度排序"""
    res = _load(F_TRIPLE_PATTERN, [])
    if not isinstance(res, list):
        return []
    seen = {}
    for r in res:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        r = _ensure_tp_progress(r)
        k = (
            str(r.get("symbol")).upper(),
            str(r.get("period", "")).lower(),
            str(r.get("direction", "bullish")).lower(),
            str(r.get("pattern", ""))
        )
        if k not in seen or float(r.get("confidence", 0)) > float(seen[k].get("confidence", 0)):
            seen[k] = r
    deduped = list(seen.values())
    deduped.sort(key=lambda x: (float(x.get("confidence", 0.0)), float(x.get("risk_reward", 1.0))), reverse=True)
    return deduped


def save_triple_pattern(items: List[Dict], with_backup: bool = True) -> bool:
    """保存三重顶底双向扫描结果"""
    items = [_ensure_tp_progress(r) for r in items if isinstance(r, dict)]
    if with_backup:
        ok = _save_with_backup(F_TRIPLE_PATTERN, items)
    else:
        ok = _save(F_TRIPLE_PATTERN, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_triple_pattern)
        except Exception:
            pass
    return ok


def append_triple_pattern_results(new_items: List[Dict], with_backup: bool = True) -> bool:
    """增量合并三重顶底扫描结果：去重合并，保留最高置信度结果"""
    if not new_items:
        return True
    current = load_triple_pattern()
    item_map = {}
    for it in current:
        k = (
            str(it.get("symbol", "")).upper(),
            str(it.get("period", "")).lower(),
            str(it.get("direction", "bullish")).lower(),
            str(it.get("pattern", ""))
        )
        item_map[k] = it
    for it in new_items:
        if not isinstance(it, dict) or not it.get("symbol"):
            continue
        it = _ensure_tp_progress(it)
        k = (
            str(it.get("symbol", "")).upper(),
            str(it.get("period", "")).lower(),
            str(it.get("direction", "bullish")).lower(),
            str(it.get("pattern", ""))
        )
        if k not in item_map or float(it.get("confidence", 0.0)) >= float(item_map[k].get("confidence", 0.0)):
            item_map[k] = it
            
    merged = list(item_map.values())
    merged.sort(key=lambda x: (float(x.get("confidence", 0.0)), float(x.get("risk_reward", 1.0))), reverse=True)
    return save_triple_pattern(merged, with_backup=with_backup)


def clear_triple_pattern_results() -> bool:
    """清空当前三重顶底扫描结果（清空前会自动进行备份快照）"""
    current_items = load_triple_pattern()
    if current_items:
        backup_triple_pattern(current_items)
    return save_triple_pattern([])


# ── 三重顶底分批扫描状态持久化 ────────────────────────────────────
F_TP_BATCH_STATE = os.path.join(_BASE, "data_tp_batch_state.json")

def load_tp_batch_state() -> Dict:
    """读取三重顶底分批扫描状态"""
    default = {
        "all_tickers": [],
        "total_tickers": 0,
        "selected_periods": ["1d", "1w", "1mo"],
        "batch_size": 50,
        "current_batch": 0,
        "total_batches": 0,
        "done_tickers": [],
        "scan_params": {},
        "auto_continue": True,
        "status": "idle",
        "updated_at": None,
    }
    st = _load(F_TP_BATCH_STATE, default)
    if not isinstance(st, dict):
        return default
    return {**default, **st}


def save_tp_batch_state(state: Dict) -> bool:
    """保存三重顶底分批扫描状态"""
    if isinstance(state, dict):
        all_tks = state.get("all_tickers", [])
        if all_tks:
            state["total_tickers"] = len(all_tks)
            bs = max(1, int(state.get("batch_size", 50)))
            state["total_batches"] = (len(all_tks) + bs - 1) // bs
        state["updated_at"] = _now_str()
    return _save(F_TP_BATCH_STATE, state)


def reset_tp_batch_state() -> bool:
    """重置三重顶底分批扫描状态"""
    return _save(F_TP_BATCH_STATE, {})


def _ensure_tp_snapshot_dir():
    os.makedirs(F_TP_SNAPSHOT_DIR, exist_ok=True)


def backup_triple_pattern(items: List[Dict]) -> str:
    """备份当前三重顶底扫描批次到快照文件夹，返回 session_id"""
    if not items:
        return ""
    try:
        _ensure_tp_snapshot_dir()
        sid = f"tp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fpath = os.path.join(F_TP_SNAPSHOT_DIR, f"{sid}.json")
        payload = {
            "session_id": sid,
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rows": items,
            "saved_at": _now_str()
        }
        _save(fpath, payload)
        return sid
    except Exception as e:
        logger.error(f"backup_triple_pattern error: {e}")
        return ""


def load_tp_snapshots() -> List[Dict]:
    """获取所有三重顶底快照批次列表"""
    try:
        _ensure_tp_snapshot_dir()
        candidates = []
        for fname in os.listdir(F_TP_SNAPSHOT_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(F_TP_SNAPSHOT_DIR, fname)
                data = _load(fpath, {})
                if isinstance(data, dict):
                    sid = data.get("session_id", os.path.splitext(fname)[0])
                    scan_time = data.get("scan_time") or data.get("saved_at") or "—"
                    rows = data.get("rows", [])
                    candidates.append({
                        "session_id": sid,
                        "scan_time": scan_time,
                        "count": len(rows),
                        "mtime": os.path.getmtime(fpath)
                    })
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        return candidates
    except Exception as e:
        logger.error(f"load_tp_snapshots error: {e}")
        return []


def restore_tp_snapshot(session_id: str) -> tuple:
    """从备份快照恢复三重顶底扫描结果"""
    try:
        _ensure_tp_snapshot_dir()
        sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
        fpath = os.path.join(F_TP_SNAPSHOT_DIR, f"{sid}.json")
        if not os.path.exists(fpath):
            return False, f"快照文件不存在: {sid}", 0
        data = _load(fpath, {})
        rows = data.get("rows", [])
        if not rows:
            return False, "快照数据为空", 0
        if save_triple_pattern(rows):
            return True, f"成功恢复批次 {sid} (共 {len(rows)} 条)", len(rows)
        return False, "保存失败", 0
    except Exception as e:
        return False, f"恢复异常: {e}", 0


# ── 💥 假跌破 + 4.236 爆发扫描数据管理 ────────────────────────────────────

def _ensure_fb_progress(r: Dict) -> Dict:
    if not isinstance(r, dict):
        return r
    try:
        p0 = float(r.get("pt_low_0", 0.0))
        p1 = float(r.get("pt_high_1", r.get("neckline", 0.0)))
        h = max(p1 - p0, p1 * 0.001)
        fib_4236 = float(r.get("fib_4236", p0 + h * 4.236))
        max_h = float(r.get("max_high_post", r.get("latest_close", 0.0)))
        close = float(r.get("latest_close", max_h))
        
        # 4.236 触达判断
        if max_h >= fib_4236 * 0.998:
            r["status"] = "completed"
            r["is_hit_4236"] = True
            r["status_reason"] = f"已达成 4.236 延伸位 ({fib_4236:.2f})，最高 {max_h:.2f}"
        else:
            r["status"] = "active"
            r["is_hit_4236"] = False
            r["status_reason"] = f"突破 1点 ({p1:.2f})，正朝 4.236 ({fib_4236:.2f}) 推进"
            
        if p1 > 0:
            r["gain_pct"] = round((max_h - p1) / p1 * 100.0, 2)
            
        ext_mult = (max_h - p0) / h if h > 0 else 0.0
        r["fibo_multiple"] = round(ext_mult, 3)
    except Exception:
        pass
    return r


def load_failed_breakdown() -> List[Dict]:
    """返回假跌破 4.236 爆发扫描结果，按 (symbol, period) 自动去重并按涨幅/置信度排序"""
    res = _load(F_FAILED_BREAKDOWN, [])
    if not isinstance(res, list):
        return []
    seen = {}
    for r in res:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        r = _ensure_fb_progress(r)
        k = (
            str(r.get("symbol")).upper(),
            str(r.get("period", "15m")).lower(),
            str(r.get("breakout_time", r.get("scan_time", "")))
        )
        if k not in seen or float(r.get("gain_pct", 0)) > float(seen[k].get("gain_pct", 0)):
            seen[k] = r
    deduped = list(seen.values())
    deduped.sort(key=lambda x: (x.get("is_hit_4236", False), float(x.get("gain_pct", 0.0))), reverse=True)
    return deduped


def save_failed_breakdown(items: List[Dict], with_backup: bool = True) -> bool:
    """保存假跌破 4.236 爆发扫描结果"""
    items = [_ensure_fb_progress(r) for r in items if isinstance(r, dict)]
    if with_backup:
        ok = _save_with_backup(F_FAILED_BREAKDOWN, items)
    else:
        ok = _save(F_FAILED_BREAKDOWN, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_failed_breakdown)
        except Exception:
            pass
    return ok


def append_failed_breakdown_results(new_items: List[Dict], with_backup: bool = True) -> bool:
    """增量合并假跌破扫描结果：去重合并，保留最优记录"""
    if not new_items:
        return True
    current = load_failed_breakdown()
    item_map = {}
    for it in current:
        k = (
            str(it.get("symbol", "")).upper(),
            str(it.get("period", "15m")).lower(),
            str(it.get("breakout_time", it.get("scan_time", "")))
        )
        item_map[k] = it
    for it in new_items:
        if not isinstance(it, dict) or not it.get("symbol"):
            continue
        it = _ensure_fb_progress(it)
        k = (
            str(it.get("symbol", "")).upper(),
            str(it.get("period", "15m")).lower(),
            str(it.get("breakout_time", it.get("scan_time", "")))
        )
        if k not in item_map or float(it.get("gain_pct", 0.0)) >= float(item_map[k].get("gain_pct", 0.0)):
            item_map[k] = it
            
    merged = list(item_map.values())
    merged.sort(key=lambda x: (x.get("is_hit_4236", False), float(x.get("gain_pct", 0.0))), reverse=True)
    return save_failed_breakdown(merged, with_backup=with_backup)


def clear_failed_breakdown_results() -> bool:
    """清空当前假跌破扫描结果（清空前会自动进行备份快照）"""
    current_items = load_failed_breakdown()
    if current_items:
        backup_failed_breakdown(current_items)
    return save_failed_breakdown([])


def _ensure_fb_snapshot_dir():
    os.makedirs(F_FB_SNAPSHOT_DIR, exist_ok=True)


def backup_failed_breakdown(items: List[Dict]) -> str:
    """备份当前假跌破扫描批次到快照文件夹，返回 session_id"""
    if not items:
        return ""
    try:
        _ensure_fb_snapshot_dir()
        sid = f"fb_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fpath = os.path.join(F_FB_SNAPSHOT_DIR, f"{sid}.json")
        payload = {
            "session_id": sid,
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rows": items,
            "saved_at": _now_str()
        }
        _save(fpath, payload)
        return sid
    except Exception as e:
        logger.error(f"backup_failed_breakdown error: {e}")
        return ""


def load_fb_snapshots() -> List[Dict]:
    """获取所有假跌破快照批次列表"""
    try:
        _ensure_fb_snapshot_dir()
        candidates = []
        for fname in os.listdir(F_FB_SNAPSHOT_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(F_FB_SNAPSHOT_DIR, fname)
                data = _load(fpath, {})
                if isinstance(data, dict):
                    sid = data.get("session_id", os.path.splitext(fname)[0])
                    scan_time = data.get("scan_time") or data.get("saved_at") or "—"
                    rows = data.get("rows", [])
                    candidates.append({
                        "session_id": sid,
                        "scan_time": scan_time,
                        "count": len(rows),
                        "mtime": os.path.getmtime(fpath)
                    })
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        return candidates
    except Exception as e:
        logger.error(f"load_fb_snapshots error: {e}")
        return []


def restore_fb_snapshot(session_id: str) -> tuple:
    """从备份快照恢复假跌破扫描结果"""
    try:
        _ensure_fb_snapshot_dir()
        sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
        fpath = os.path.join(F_FB_SNAPSHOT_DIR, f"{sid}.json")
        if not os.path.exists(fpath):
            return False, f"快照文件不存在: {sid}", 0
        data = _load(fpath, {})
        rows = data.get("rows", [])
        if not rows:
            return False, "快照数据为空", 0
        if save_failed_breakdown(rows):
            return True, f"成功恢复批次 {sid} (共 {len(rows)} 条)", len(rows)
        return False, "保存失败", 0
    except Exception as e:
        return False, f"恢复异常: {e}", 0


# ── Chartink 4H 突破扫描数据与快照 ─────────────────────────────────────
F_CHARTINK = os.path.join(_BASE, "data_chartink.json")
F_CHARTINK_SNAPSHOT_DIR = os.path.join(_BASE, "snapshots_chartink")

def _ensure_chartink_snapshot_dir():
    os.makedirs(F_CHARTINK_SNAPSHOT_DIR, exist_ok=True)

def backup_chartink(data: Dict) -> str:
    """备份当前 Chartink 扫描批次到快照文件夹，返回备份产生的 session_id"""
    if not data or not isinstance(data, dict):
        return ""
    if not data.get("passed") and not data.get("total"):
        return ""
    try:
        _ensure_chartink_snapshot_dir()
        sid = f"ci_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fpath = os.path.join(F_CHARTINK_SNAPSHOT_DIR, f"{sid}.json")
        scan_time = data.get("scanned_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        passed_cnt = len(data.get("passed", []))
        total_cnt = data.get("total", 0)
        
        payload = {
            "session_id": sid,
            "scan_time": scan_time,
            "total": total_cnt,
            "passed_count": passed_cnt,
            "data": data,
            "saved_at": _now_str()
        }
        if _save(fpath, payload):
            try:
                import cloud_sync
                if cloud_sync.is_configured():
                    _async_push(lambda: cloud_sync._upload_snapshot("chartink", data))
            except Exception:
                pass
            # 保留最多 100 个快照
            try:
                snaps = []
                for fname in os.listdir(F_CHARTINK_SNAPSHOT_DIR):
                    if fname.endswith(".json"):
                        fp = os.path.join(F_CHARTINK_SNAPSHOT_DIR, fname)
                        mtime = os.path.getmtime(fp)
                        snaps.append((mtime, fp))
                snaps.sort(reverse=True)
                for _, old_path in snaps[100:]:
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            except Exception:
                pass
            return sid
    except Exception as e:
        import logging
        logging.error(f"backup_chartink error: {e}")
    return ""

def load_chartink_snapshots() -> List[Dict]:
    """获取所有 Chartink 的快照批次列表，按时间倒序排列"""
    try:
        _ensure_chartink_snapshot_dir()
        candidates = []
        for fname in os.listdir(F_CHARTINK_SNAPSHOT_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(F_CHARTINK_SNAPSHOT_DIR, fname)
                data = _load(fpath, {})
                if isinstance(data, dict):
                    sid = data.get("session_id", os.path.splitext(fname)[0])
                    scan_time = data.get("scan_time") or data.get("saved_at") or "—"
                    total = data.get("total", 0)
                    passed_cnt = data.get("passed_count", 0)
                    candidates.append({
                        "session_id": sid,
                        "scan_time": scan_time,
                        "total": total,
                        "passed_count": passed_cnt,
                        "mtime": os.path.getmtime(fpath)
                    })
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        return candidates
    except Exception as e:
        import logging
        logging.error(f"load_chartink_snapshots error: {e}")
        return []

def restore_chartink_snapshot(session_id: str) -> tuple:
    """从备份批次恢复 Chartink 扫描结果"""
    try:
        _ensure_chartink_snapshot_dir()
        sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
        fpath = os.path.join(F_CHARTINK_SNAPSHOT_DIR, f"{sid}.json")
        if not os.path.exists(fpath):
            return False, "备份批次不存在", 0
        payload = _load(fpath, {})
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(data, dict) or not data:
            return False, "快照文件内容无效", 0
        ok = save_chartink(data)
        if ok:
            passed_cnt = len(data.get("passed", []))
            return True, "恢复成功", passed_cnt
        return False, "保存恢复数据失败", 0
    except Exception as e:
        return False, f"恢复异常: {e}", 0

def load_chartink() -> Dict:
    """返回上次 Chartink 扫描结果"""
    res = _load(F_CHARTINK, {})
    if not isinstance(res, dict):
        return {}
    return res

def save_chartink(data: Dict) -> bool:
    """保存 Chartink 扫描结果并实时同步推送到云端"""
    ok = _save_with_backup(F_CHARTINK, data)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.push_chartink()
        except Exception as e:
            logging.error(f"save_chartink push_chartink error: {e}")
    return ok


def clear_chartink_results() -> bool:
    """清空当前 Chartink 扫描结果（清空前会自动生成快照并同步至云端）"""
    data = load_chartink()
    if data and isinstance(data, dict) and (data.get("passed") or data.get("total")):
        backup_chartink(data)
    ok = save_chartink({})
    try:
        import cloud_sync
        if cloud_sync.is_configured():
            cloud_sync.push_chartink()
    except Exception:
        pass
    return ok


# ── 4H 结构颈线突破扫描数据与快照 ─────────────────────────────────────
F_NECKLINE = os.path.join(_BASE, "data_neckline.json")
F_NECKLINE_SNAPSHOT_DIR = os.path.join(_BASE, "snapshots_neckline")

def _ensure_neckline_snapshot_dir():
    os.makedirs(F_NECKLINE_SNAPSHOT_DIR, exist_ok=True)

def backup_neckline(data: Dict) -> str:
    """备份当前 4H 结构颈线扫描批次到快照文件夹，返回备份产生的 session_id"""
    if not data or not isinstance(data, dict):
        return ""
    if not data.get("passed") and not data.get("total"):
        return ""
    try:
        _ensure_neckline_snapshot_dir()
        sid = f"nl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fpath = os.path.join(F_NECKLINE_SNAPSHOT_DIR, f"{sid}.json")
        scan_time = data.get("scanned_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        passed_cnt = len(data.get("passed", []))
        total_cnt = data.get("total", 0)
        
        payload = {
            "session_id": sid,
            "scan_time": scan_time,
            "total": total_cnt,
            "passed_count": passed_cnt,
            "data": data,
            "saved_at": _now_str()
        }
        if _save(fpath, payload):
            try:
                import cloud_sync
                if cloud_sync.is_configured():
                    _async_push(lambda: cloud_sync._upload_snapshot("neckline", data))
            except Exception:
                pass
            # 保留最多 100 个快照
            try:
                snaps = []
                for fname in os.listdir(F_NECKLINE_SNAPSHOT_DIR):
                    if fname.endswith(".json"):
                        fp = os.path.join(F_NECKLINE_SNAPSHOT_DIR, fname)
                        mtime = os.path.getmtime(fp)
                        snaps.append((mtime, fp))
                snaps.sort(reverse=True)
                for _, old_path in snaps[100:]:
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
            except Exception:
                pass
            return sid
    except Exception as e:
        import logging
        logging.error(f"backup_neckline error: {e}")
    return ""

def load_neckline_snapshots() -> List[Dict]:
    """获取所有 4H 结构颈线的快照批次列表，按时间倒序排列"""
    try:
        _ensure_neckline_snapshot_dir()
        candidates = []
        for fname in os.listdir(F_NECKLINE_SNAPSHOT_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(F_NECKLINE_SNAPSHOT_DIR, fname)
                data = _load(fpath, {})
                if isinstance(data, dict):
                    sid = data.get("session_id", os.path.splitext(fname)[0])
                    scan_time = data.get("scan_time") or data.get("saved_at") or "—"
                    total = data.get("total", 0)
                    passed_cnt = data.get("passed_count", 0)
                    candidates.append({
                        "session_id": sid,
                        "scan_time": scan_time,
                        "total": total,
                        "passed_count": passed_cnt,
                        "mtime": os.path.getmtime(fpath)
                    })
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        return candidates
    except Exception as e:
        import logging
        logging.error(f"load_neckline_snapshots error: {e}")
        return []

def restore_neckline_snapshot(session_id: str) -> tuple:
    """从备份批次恢复 4H 结构颈线扫描结果"""
    try:
        _ensure_neckline_snapshot_dir()
        sid = "".join(ch for ch in str(session_id) if ch.isalnum() or ch in ("_", "-"))
        fpath = os.path.join(F_NECKLINE_SNAPSHOT_DIR, f"{sid}.json")
        if not os.path.exists(fpath):
            return False, "备份批次不存在", 0
        payload = _load(fpath, {})
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(data, dict) or not data:
            return False, "快照文件内容无效", 0
        ok = save_neckline(data)
        if ok:
            passed_cnt = len(data.get("passed", []))
            return True, "恢复成功", passed_cnt
        return False, "保存恢复数据失败", 0
    except Exception as e:
        return False, f"恢复异常: {e}", 0

def load_neckline() -> Dict:
    """返回上次 4H 结构颈线扫描结果"""
    res = _load(F_NECKLINE, {})
    if not isinstance(res, dict):
        return {}
    return res

def save_neckline(data: Dict) -> bool:
    """保存 4H 结构颈线扫描结果并实时同步推送到云端"""
    ok = _save_with_backup(F_NECKLINE, data)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                cloud_sync.push_neckline()
        except Exception as e:
            logging.error(f"save_neckline push_neckline error: {e}")
    return ok

def clear_neckline_results() -> bool:
    """清空当前 4H 结构颈线扫描结果（清空前会自动生成快照并同步至云端）"""
    data = load_neckline()
    if data and isinstance(data, dict) and (data.get("passed") or data.get("total")):
        backup_neckline(data)
    ok = save_neckline({})
    try:
        import cloud_sync
        if cloud_sync.is_configured():
            cloud_sync.push_neckline()
    except Exception:
        pass
    return ok


# ── 自定义品种库与分组 ─────────────────────────────────────────
F_SYMBOLS = os.path.join(_BASE, "data_symbols.json")
F_SYMBOL_GROUPS = os.path.join(_BASE, "data_symbol_groups.json")

def load_symbols() -> List[Dict]:
    """返回自定义品种库列表，每项: {ticker, name, source, added_at}"""
    items = _load(F_SYMBOLS, [])
    if not isinstance(items, list):
        items = []
    return [i for i in items if isinstance(i, dict) and i.get("ticker")]

def save_symbols(items: List[Dict]) -> bool:
    ok = _save(F_SYMBOLS, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_symbols)  # 异步同步
        except Exception:
            pass
    return ok

def load_symbol_groups() -> List[Dict]:
    """返回自定义分组列表，每项: {id, name, tickers: [], created_at}"""
    items = _load(F_SYMBOL_GROUPS, [])
    if not isinstance(items, list):
        items = []
    return [i for i in items if isinstance(i, dict) and i.get("id") and i.get("name")]

def save_symbol_groups(items: List[Dict]) -> bool:
    ok = _save(F_SYMBOL_GROUPS, items)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_symbol_groups)  # 异步同步
        except Exception:
            pass
    return ok

def add_symbol(ticker: str, name: str = "", source: str = "manual") -> bool:
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    items = load_symbols()
    if any(i["ticker"] == ticker for i in items):
        return False
    items.append({
        "ticker": ticker,
        "name": name.strip() or ticker,
        "source": source,
        "added_at": _now_str()
    })
    return save_symbols(items)

def update_symbol_name(ticker: str, new_name: str) -> bool:
    """更新指定品种的名称（同步更新自定义品种库、自选收藏夹、热门品种库，并推送到云端）"""
    ticker = ticker.strip().upper()
    new_name = new_name.strip()
    if not ticker or not new_name:
        return False
    
    updated = False
    
    # 1. 更新自定义品种库 (F_SYMBOLS)
    symbols = load_symbols()
    found_in_sym = False
    for s in symbols:
        if s.get("ticker", "").strip().upper() == ticker:
            s["name"] = new_name
            found_in_sym = True
            updated = True
            break
    if not found_in_sym:
        symbols.append({
            "ticker": ticker,
            "name": new_name,
            "source": "manual",
            "added_at": _now_str()
        })
        updated = True
    save_symbols(symbols)
    
    # 2. 更新自选收藏夹 (F_WATCHLIST)
    wl_items = load_watchlist()
    wl_changed = False
    for item in wl_items:
        if item.get("ticker", "").strip().upper() == ticker:
            item["name"] = new_name
            wl_changed = True
            updated = True
    if wl_changed:
        save_watchlist(wl_items)
        
    # 3. 更新热门品种库 (F_HOTLIST)
    try:
        hot_items = load_hotlist()
        hot_changed = False
        for item in hot_items:
            if item.get("ticker", "").strip().upper() == ticker:
                item["name"] = new_name
                hot_changed = True
                updated = True
        if hot_changed:
            save_hotlist(hot_items)
    except Exception:
        pass
        
    return updated

def remove_symbol(ticker: str) -> bool:
    ticker = ticker.strip().upper()
    items = load_symbols()
    new_items = [i for i in items if i["ticker"] != ticker]
    if len(new_items) == len(items):
        return False
    # 从所有分组中也移除该品种
    groups = load_symbol_groups()
    group_changed = False
    for g in groups:
        if ticker in g.get("tickers", []):
            g["tickers"] = [t for t in g["tickers"] if t != ticker]
            group_changed = True
    if group_changed:
        save_symbol_groups(groups)
    return save_symbols(new_items)

def add_symbol_group(name: str) -> Optional[str]:
    import uuid
    name = name.strip()
    if not name:
        return None
    groups = load_symbol_groups()
    if any(g["name"] == name for g in groups):
        return None
    new_id = str(uuid.uuid4())[:8]
    groups.append({
        "id": new_id,
        "name": name,
        "tickers": [],
        "created_at": _now_str()
    })
    save_symbol_groups(groups)
    return new_id

def rename_symbol_group(group_id: str, new_name: str) -> bool:
    new_name = new_name.strip()
    if not new_name:
        return False
    groups = load_symbol_groups()
    for g in groups:
        if g["id"] == group_id:
            g["name"] = new_name
            return save_symbol_groups(groups)
    return False

def delete_symbol_group(group_id: str) -> bool:
    groups = load_symbol_groups()
    new_groups = [g for g in groups if g["id"] != group_id]
    if len(new_groups) == len(groups):
        return False
    return save_symbol_groups(new_groups)

def add_tickers_to_group(group_id: str, tickers: List[str]) -> bool:
    groups = load_symbol_groups()
    target = next((g for g in groups if g["id"] == group_id), None)
    if not target:
        return False
    t_set = set(target.get("tickers", []))
    added = False
    for t in tickers:
        t = t.strip().upper()
        if t and t not in t_set:
            t_set.add(t)
            added = True
    if added:
        target["tickers"] = list(t_set)
        return save_symbol_groups(groups)
    return False

def remove_tickers_from_group(group_id: str, tickers: List[str]) -> bool:
    groups = load_symbol_groups()
    target = next((g for g in groups if g["id"] == group_id), None)
    if not target:
        return False
    t_set = set(target.get("tickers", []))
    removed = False
    for t in tickers:
        t = t.strip().upper()
        if t in t_set:
            t_set.remove(t)
            removed = True
    if removed:
        target["tickers"] = list(t_set)
        return save_symbol_groups(groups)
    return False


# ── 退市与无效代码管理 ──────────────────────────────────────────
F_DELISTED = os.path.join(_BASE, "data_delisted.json")
F_FAILURES = os.path.join(_BASE, "data_scan_failures.json")

def load_delisted_tickers() -> List[str]:
    """返回已被判定为退市或无效的代码列表"""
    return _load(F_DELISTED, [])

def save_delisted_tickers(tickers: List[str]) -> bool:
    return _save(F_DELISTED, sorted(list(set(tickers))))

def is_ticker_delisted(ticker: str) -> bool:
    t = ticker.strip().upper()
    if not t:
        return False
    delisted = load_delisted_tickers()
    return t in delisted

def add_delisted_ticker(ticker: str) -> bool:
    t = ticker.strip().upper()
    if not t:
        return False
    delisted = load_delisted_tickers()
    if t not in delisted:
        delisted.append(t)
        return save_delisted_tickers(delisted)
    return True

def remove_delisted_ticker(ticker: str) -> bool:
    t = ticker.strip().upper()
    if not t:
        return False
    delisted = load_delisted_tickers()
    if t in delisted:
        delisted.remove(t)
        return save_delisted_tickers(delisted)
    return True

def increment_scan_failure(ticker: str) -> int:
    """递增指定代码的扫描失败次数，若连续失败次数达到阈值（如5次），则自动加入退市/无效列表"""
    t = ticker.strip().upper()
    if not t:
        return 0
    failures = _load(F_FAILURES, {})
    count = failures.get(t, 0) + 1
    failures[t] = count
    _save(F_FAILURES, failures)
    
    if count >= 5:
        add_delisted_ticker(t)
    return count

def reset_scan_failure(ticker: str) -> None:
    """重置指定代码的扫描失败次数"""
    t = ticker.strip().upper()
    if not t:
        return
    failures = _load(F_FAILURES, {})
    if t in failures:
        failures.pop(t)
        _save(F_FAILURES, failures)


# ── 大批量扫描断点续扫支持 ───────────────────────────────────
F_SCAN_CHECKPOINT = os.path.join(_BASE, "scan_checkpoint.json")

def save_scan_checkpoint(job_type: str, done_tickers: List[str], total_tickers: List[str], current_results: List[Dict]) -> bool:
    """保存当前扫描任务断点，并同步到 Supabase 云端"""
    data = {
        "job_type": job_type,
        "done_tickers": list(set(done_tickers)),
        "total_tickers": total_tickers,
        "current_results": current_results,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    ok = _save(F_SCAN_CHECKPOINT, data)
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_scan_checkpoint)
        except Exception:
            pass
    return ok

def load_scan_checkpoint(job_type: str = "") -> Dict:
    """读取扫描任务断点"""
    data = _load(F_SCAN_CHECKPOINT, {})
    if not isinstance(data, dict):
        return {}
    if job_type and data.get("job_type") != job_type:
        return {}
    return data

def clear_scan_checkpoint() -> bool:
    """清空扫描任务断点，并同步清空云端断点"""
    ok = _save(F_SCAN_CHECKPOINT, {})
    if ok:
        try:
            import cloud_sync
            if cloud_sync.is_configured():
                _async_push(cloud_sync.push_scan_checkpoint)
        except Exception:
            pass
    return ok




