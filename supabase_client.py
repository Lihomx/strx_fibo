"""
core/supabase_client.py
Supabase 数据库客户端 — 使用 supabase-py 官方 SDK
支持 Streamlit secrets / 环境变量 两种配置方式
"""

import os
import time
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import streamlit as st

# ── Supabase 客户端（懒加载）────────────────────────────────────
_client = None

def _get_secrets() -> Tuple[str, str]:
    """从 Streamlit secrets 或环境变量读取 Supabase 配置"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return url, key
    except Exception:
        pass
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def init_supabase() -> bool:
    """初始化 Supabase 客户端（幂等）"""
    global _client
    if _client is not None:
        return True
    url, key = _get_secrets()
    if not url or not key:
        return False
    try:
        from supabase import create_client
        _client = create_client(url, key)
        logging.info("Supabase client initialized")
        return True
    except ImportError:
        logging.error("supabase-py not installed: pip install supabase")
        return False
    except Exception as e:
        logging.error(f"Supabase init failed: {e}")
        return False


def supabase_ok() -> Tuple[bool, str]:
    """检查 Supabase 连接状态"""
    url, key = _get_secrets()
    if not url or not key:
        return False, "未配置 SUPABASE_URL / SUPABASE_KEY"
    if _client is None:
        ok = init_supabase()
        if not ok:
            return False, "supabase-py 未安装或连接失败"
    try:
        # 轻量连通性测试
        _client.table("scan_sessions").select("id").limit(1).execute()
        return True, "connected"
    except Exception as e:
        return False, str(e)


def get_client():
    """获取 Supabase 客户端实例"""
    if _client is None:
        init_supabase()
    return _client


# ════════════════════════════════════════════════════════════════
# DDL — Supabase SQL (在 Supabase Dashboard → SQL Editor 执行一次)
# ════════════════════════════════════════════════════════════════
SUPABASE_DDL = """
-- ① 扫描批次表
CREATE TABLE IF NOT EXISTS scan_sessions (
    id              BIGSERIAL PRIMARY KEY,
    session_id      TEXT UNIQUE NOT NULL,
    scan_date       DATE NOT NULL,
    scan_time       TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_checks    INTEGER DEFAULT 0,
    inzone_count    INTEGER DEFAULT 0,
    triple_conf     INTEGER DEFAULT 0,
    duration_ms     INTEGER DEFAULT 0,
    data_source     TEXT DEFAULT 'yfinance',
    note            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sess_date ON scan_sessions(scan_date DESC);

-- ② 扫描结果表
CREATE TABLE IF NOT EXISTS scan_results (
    id               BIGSERIAL PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES scan_sessions(session_id),
    scan_date        DATE NOT NULL,
    ticker           TEXT NOT NULL,
    name             TEXT NOT NULL,
    category         TEXT NOT NULL,
    timeframe        TEXT NOT NULL,
    in_zone          BOOLEAN DEFAULT FALSE,
    current_price    NUMERIC,
    swing_high       NUMERIC,
    swing_low        NUMERIC,
    zone_top         NUMERIC,
    zone_bot         NUMERIC,
    retrace_pct      NUMERIC,
    dist_pct         NUMERIC,
    nearest_fibo     NUMERIC,
    confluence_score INTEGER DEFAULT 0,
    confluence_label TEXT DEFAULT '',
    tv_symbol        TEXT
);
CREATE INDEX IF NOT EXISTS idx_res_session  ON scan_results(session_id);
CREATE INDEX IF NOT EXISTS idx_res_date     ON scan_results(scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_res_inzone   ON scan_results(in_zone);

-- ③ 告警日志表
CREATE TABLE IF NOT EXISTS alert_log (
    id          BIGSERIAL PRIMARY KEY,
    alert_time  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    channel     TEXT NOT NULL,
    status      TEXT NOT NULL,
    message     TEXT DEFAULT ''
);

-- ④ 应用配置表
CREATE TABLE IF NOT EXISTS app_config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


# ════════════════════════════════════════════════════════════════
# CONFIG CRUD
# ════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "lookback":          "100",
    "fibo_low":          "0.500",
    "fibo_high":         "0.618",
    "watch_pct":         "5.0",
    "data_source":       "yfinance",
    "twelvedata_key":    "",
    "dingtalk_enabled":  "false",
    "dingtalk_webhook":  "",
    "dingtalk_secret":   "",
    "telegram_enabled":  "false",
    "telegram_token":    "",
    "telegram_chat_id":  "",
    "scan_enabled":      "false",
    "scan_hour":         "9",
    "scan_minute":       "0",
    "alert_cooldown":    "240",
}


def load_config() -> Dict[str, Any]:
    """从 Supabase app_config 表读取配置，合并默认值"""
    cfg = dict(DEFAULT_CONFIG)
    db  = get_client()
    if db is None:
        return cfg
    try:
        res = db.table("app_config").select("key,value").execute()
        for row in (res.data or []):
            cfg[row["key"]] = row["value"]
    except Exception as e:
        logging.warning(f"load_config: {e}")
    # 类型转换
    int_keys   = ["lookback","scan_hour","scan_minute","alert_cooldown"]
    float_keys = ["fibo_low","fibo_high","watch_pct"]
    bool_keys  = ["dingtalk_enabled","telegram_enabled","scan_enabled"]
    for k in int_keys:
        try: cfg[k] = int(cfg[k])
        except: cfg[k] = int(DEFAULT_CONFIG.get(k, 0))
    for k in float_keys:
        try: cfg[k] = float(cfg[k])
        except: cfg[k] = float(DEFAULT_CONFIG.get(k, 0))
    for k in bool_keys:
        cfg[k] = str(cfg[k]).lower() in ("true","1","yes")
    return cfg


def save_config(updates: Dict[str, Any]) -> bool:
    """批量 upsert 配置项"""
    db = get_client()
    if db is None:
        return False
    try:
        rows = [{"key": k, "value": str(v), "updated_at": datetime.utcnow().isoformat()}
                for k, v in updates.items()]
        db.table("app_config").upsert(rows, on_conflict="key").execute()
        return True
    except Exception as e:
        logging.error(f"save_config: {e}")
        return False


# ════════════════════════════════════════════════════════════════
# SCAN SESSION CRUD
# ════════════════════════════════════════════════════════════════

def save_scan_session(session: Dict) -> bool:
    db = get_client()
    if db is None:
        return False
    try:
        db.table("scan_sessions").insert(session).execute()
        return True
    except Exception as e:
        logging.error(f"save_scan_session: {e}")
        return False


def save_scan_results(rows: List[Dict]) -> bool:
    """批量插入扫描结果（分批，每批500条）"""
    db = get_client()
    if db is None:
        return False
    try:
        batch = 500
        for i in range(0, len(rows), batch):
            db.table("scan_results").insert(rows[i:i+batch]).execute()
        return True
    except Exception as e:
        logging.error(f"save_scan_results: {e}")
        return False


def get_sessions(date_from: str = "", date_to: str = "",
                 limit: int = 100) -> List[Dict]:
    db = get_client()
    if db is None:
        return []
    try:
        q = db.table("scan_sessions").select("*").order("scan_time", desc=True)
        if date_from:
            q = q.gte("scan_date", date_from)
        if date_to:
            q = q.lte("scan_date", date_to)
        res = q.limit(limit).execute()
        return res.data or []
    except Exception as e:
        logging.error(f"get_sessions: {e}")
        return []


def get_latest_session_id() -> Optional[str]:
    sessions = get_sessions(limit=1)
    return sessions[0]["session_id"] if sessions else None


def get_results(session_id: str, only_inzone: bool = False) -> List[Dict]:
    db = get_client()
    if db is None:
        return []
    try:
        q = db.table("scan_results").select("*").eq("session_id", session_id)
        if only_inzone:
            q = q.eq("in_zone", True)
        q = q.order("confluence_score", desc=True)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logging.error(f"get_results: {e}")
        return []


def get_results_by_date(date_from: str = "", date_to: str = "",
                        only_inzone: bool = False) -> List[Dict]:
    db = get_client()
    if db is None:
        return []
    try:
        q = db.table("scan_results").select("*")
        if date_from:
            q = q.gte("scan_date", date_from)
        if date_to:
            q = q.lte("scan_date", date_to)
        if only_inzone:
            q = q.eq("in_zone", True)
        q = q.order("scan_date", desc=True).limit(5000)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logging.error(f"get_results_by_date: {e}")
        return []


def get_confluence_latest() -> List[Dict]:
    """最新批次的共振汇总（评分≥3）"""
    sid = get_latest_session_id()
    if not sid:
        return []
    rows = get_results(sid)
    # 聚合
    from collections import defaultdict
    grouped: Dict[str, Dict] = defaultdict(lambda: {
        "name": "", "category": "", "ticker": "",
        "daily_in": False, "weekly_in": False, "monthly_in": False,
        "conf_score": 0, "conf_label": "", "price": None,
    })
    for r in rows:
        t  = r["ticker"]
        tf = r["timeframe"]
        grouped[t]["ticker"]   = t
        grouped[t]["name"]     = r["name"]
        grouped[t]["category"] = r["category"]
        grouped[t]["conf_score"]  = max(grouped[t]["conf_score"], r.get("confluence_score",0))
        grouped[t]["conf_label"]  = r.get("confluence_label","")
        if tf == "Daily":
            grouped[t]["daily_in"]  = bool(r["in_zone"])
            grouped[t]["price"]     = r.get("current_price")
        elif tf == "Weekly":
            grouped[t]["weekly_in"] = bool(r["in_zone"])
        elif tf == "Monthly":
            grouped[t]["monthly_in"]= bool(r["in_zone"])
    result = [v for v in grouped.values() if v["conf_score"] >= 3]
    result.sort(key=lambda x: -x["conf_score"])
    return result


def get_db_stats() -> Dict:
    db = get_client()
    if db is None:
        return {}
    try:
        sess_cnt = len(db.table("scan_sessions").select("id").execute().data or [])
        inz_cnt  = len(db.table("scan_results").select("id").eq("in_zone", True).execute().data or [])
        latest   = get_sessions(limit=1)
        return {
            "total_sessions": sess_cnt,
            "total_inzone":   inz_cnt,
            "latest_session": latest[0] if latest else None,
        }
    except Exception as e:
        logging.error(f"get_db_stats: {e}")
        return {}


# ════════════════════════════════════════════════════════════════
# ALERT LOG
# ════════════════════════════════════════════════════════════════

def log_alert(ticker: str, name: str, timeframe: str,
              channel: str, status: str, message: str = "") -> None:
    db = get_client()
    if db is None:
        return
    try:
        db.table("alert_log").insert({
            "alert_time": datetime.utcnow().isoformat(),
            "ticker": ticker, "name": name, "timeframe": timeframe,
            "channel": channel, "status": status, "message": message,
        }).execute()
    except Exception as e:
        logging.warning(f"log_alert: {e}")


def get_alert_log(limit: int = 100) -> List[Dict]:
    db = get_client()
    if db is None:
        return []
    try:
        res = db.table("alert_log").select("*").order("alert_time", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logging.error(f"get_alert_log: {e}")
        return []
