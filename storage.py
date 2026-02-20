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
    allres: List[Dict] = _load(F_ALLRES, [])
    existing = {(r["ticker"], r["timeframe"]): r for r in allres}
    for r in result_rows:
        key = (r["ticker"], r["timeframe"])
        existing[key] = r
    merged = list(existing.values())
    if len(merged) > _MAX_ALLRES:
        merged = merged[-_MAX_ALLRES:]
    _save(F_ALLRES, merged)

    # 保存会话摘要
    hist: List[Dict] = _load(F_HIST, [])
    hist.append(session_row)
    if len(hist) > _MAX_HIST:
        hist = hist[-_MAX_HIST:]
    return _save(F_HIST, hist)


def load_sessions(limit: int = 10) -> List[Dict]:
    hist = _load(F_HIST, [])
    return list(reversed(hist))[:limit]


def load_latest_results(inzone_only: bool = False) -> List[Dict]:
    # 优先返回全量合并缓存
    allres = _load(F_ALLRES, [])
    if not allres:
        allres = _load(F_RES, [])
    if inzone_only:
        return [r for r in allres if r.get("in_zone")]
    return allres


def load_session_results(session_id: str) -> List[Dict]:
    """读取全量缓存中属于特定会话的记录"""
    allres = _load(F_ALLRES, [])
    filtered = [r for r in allres if r.get("session_id") == session_id]
    if not filtered:
        # 降级：读最新明细
        results = _load(F_RES, [])
        filtered = [r for r in results if r.get("session_id") == session_id]
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
