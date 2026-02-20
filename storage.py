"""
storage.py — JSON 文件存储层
替代 Supabase，所有数据持久化到本地 JSON 文件。
Streamlit Cloud: 数据在重启后重置（无状态容器），
适合开发/演示阶段；后期升级到 Supabase 只需替换本模块。
"""

import json
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# ── 数据文件路径（统一放在项目根目录）──────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
F_CFG   = os.path.join(_DIR, "data_config.json")
F_HIST  = os.path.join(_DIR, "data_history.json")
F_ALERT = os.path.join(_DIR, "data_alerts.json")

# ── 默认配置 ────────────────────────────────────────────────────────
_DEFAULT_CFG: Dict[str, Any] = {
    # 扫描参数
    "lookback":       100,
    "fibo_low":       0.5,
    "fibo_high":      0.618,
    "watch_dist":     5.0,
    "data_source":    "yfinance",
    "twelvedata_key": "",
    # 告警
    "dingtalk_enabled": False,
    "dingtalk_webhook": "",
    "dingtalk_secret":  "",
    "telegram_enabled": False,
    "telegram_token":   "",
    "telegram_chat_id": "",
    "alert_cooldown":   240,
    # 定时（仅记录设置，Streamlit Cloud 不能后台运行 APScheduler）
    "sched_hour":   9,
    "sched_minute": 30,
}


# ════════════════════════════════════════════════════════════════════
# 通用 JSON 读写
# ════════════════════════════════════════════════════════════════════

def _read(path: str, default: Any) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.warning(f"storage._read {path}: {e}")
    return default


def _write(path: str, data: Any) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return True
    except Exception as e:
        logging.warning(f"storage._write {path}: {e}")
        return False


# ════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════

def load_config() -> Dict[str, Any]:
    """加载配置，缺失字段自动填充默认值"""
    saved = _read(F_CFG, {})
    cfg = dict(_DEFAULT_CFG)
    cfg.update(saved)
    return cfg


def save_config(cfg: Dict[str, Any]) -> bool:
    current = load_config()
    current.update(cfg)
    return _write(F_CFG, current)


def reset_config() -> bool:
    return _write(F_CFG, dict(_DEFAULT_CFG))


# ════════════════════════════════════════════════════════════════════
# SCAN HISTORY
# ════════════════════════════════════════════════════════════════════

def save_scan(session: Dict, results: List[Dict]) -> bool:
    """
    保存扫描结果到历史文件。
    结构：{"sessions": [...], "results": [...]}
    为控制文件大小，最多保留最近 30 次扫描。
    """
    hist = _read(F_HIST, {"sessions": [], "results": []})
    sessions: List[Dict] = hist.get("sessions", [])
    all_res:  List[Dict] = hist.get("results",  [])

    sessions.append(session)
    all_res.extend(results)

    # 保留最近 30 次扫描
    MAX = 30
    if len(sessions) > MAX:
        keep_ids = {s["session_id"] for s in sessions[-MAX:]}
        sessions = sessions[-MAX:]
        all_res  = [r for r in all_res if r.get("session_id") in keep_ids]

    return _write(F_HIST, {"sessions": sessions, "results": all_res})


def load_sessions(limit: int = 30) -> List[Dict]:
    hist = _read(F_HIST, {"sessions": [], "results": []})
    sessions = hist.get("sessions", [])
    return list(reversed(sessions[-limit:]))


def load_results(session_id: Optional[str] = None,
                 inzone_only: bool = False) -> List[Dict]:
    hist = _read(F_HIST, {"sessions": [], "results": []})
    rows = hist.get("results", [])
    if session_id:
        rows = [r for r in rows if r.get("session_id") == session_id]
    if inzone_only:
        rows = [r for r in rows if r.get("in_zone")]
    return rows


def load_latest_results(inzone_only: bool = False) -> List[Dict]:
    sessions = load_sessions(limit=1)
    if not sessions:
        return []
    return load_results(sessions[0]["session_id"], inzone_only)


def has_scan_data() -> bool:
    sessions = load_sessions(limit=1)
    return len(sessions) > 0


# ════════════════════════════════════════════════════════════════════
# ALERT LOG
# ════════════════════════════════════════════════════════════════════

def log_alert(ticker: str, name: str, timeframe: str,
              channel: str, status: str, message: str) -> bool:
    logs: List[Dict] = _read(F_ALERT, [])
    logs.append({
        "time":      datetime.now().isoformat(timespec="seconds"),
        "ticker":    ticker,
        "name":      name,
        "timeframe": timeframe,
        "channel":   channel,
        "status":    status,
        "message":   message,
    })
    # 保留最近 200 条告警
    if len(logs) > 200:
        logs = logs[-200:]
    return _write(F_ALERT, logs)


def load_alert_log(limit: int = 100) -> List[Dict]:
    logs: List[Dict] = _read(F_ALERT, [])
    return list(reversed(logs[-limit:]))


def clear_alert_log() -> bool:
    return _write(F_ALERT, [])
