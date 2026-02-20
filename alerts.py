"""
core/alerts.py
告警引擎 — DingTalk / Telegram，带冷却机制
"""

import time
import hmac
import base64
import hashlib
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

# ── 冷却缓存（进程内存，重启后重置）────────────────────────────
_cooldown_cache: Dict[str, datetime] = {}


def _is_cooldown(ticker: str, tf: str, minutes: int) -> bool:
    key  = f"{ticker}::{tf}"
    last = _cooldown_cache.get(key)
    if last is None:
        return False
    return (datetime.now() - last).total_seconds() < minutes * 60


def _mark_alerted(ticker: str, tf: str) -> None:
    _cooldown_cache[f"{ticker}::{tf}"] = datetime.now()


# ════════════════════════════════════════════════════════════════
# 消息构建
# ════════════════════════════════════════════════════════════════

def build_message(ticker: str, name: str, tf: str,
                  fibo: Dict, conf: Dict) -> str:
    from core.scanner import tv_url
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"📐 STRX Fibo 信号  {conf['label']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷  {name} ({ticker})\n"
        f"📅 时间框架: {tf}\n"
        f"💰 当前价格: {fibo['current']:,.4f}\n"
        f"📏 黄金区间: {fibo['zone_bot']:,.4f} – {fibo['zone_top']:,.4f}\n"
        f"📉 回撤深度: {fibo['retrace_pct']:.1f}%\n"
        f"🔗 {tv_url(ticker)}\n"
        f"🕐 {now}"
    )


# ════════════════════════════════════════════════════════════════
# DINGTALK
# ════════════════════════════════════════════════════════════════

def send_dingtalk(text: str, cfg: Dict) -> Tuple[bool, str]:
    """
    钉钉自定义机器人 Webhook。
    支持「加签」安全验证（Secret）。
    免费，无需付费，消息直达群聊。
    """
    try:
        import requests
    except ImportError:
        return False, "requests 未安装"

    webhook = cfg.get("dingtalk_webhook", "").strip()
    secret  = cfg.get("dingtalk_secret",  "").strip()
    if not webhook:
        return False, "dingtalk_webhook 未配置"

    url = webhook
    if secret:
        ts       = str(round(time.time() * 1000))
        sign_str = f"{ts}\n{secret}"
        sign     = base64.b64encode(
            hmac.new(secret.encode("utf-8"),
                      sign_str.encode("utf-8"),
                      digestmod=hashlib.sha256).digest()
        ).decode()
        url += f"&timestamp={ts}&sign={urllib.parse.quote_plus(sign)}"

    payload = {
        "msgtype": "text",
        "text":    {"content": text},
        "at":      {"isAtAll": False},
    }
    try:
        r    = requests.post(url, json=payload, timeout=10)
        data = r.json()
        if data.get("errcode") == 0:
            return True, "ok"
        return False, f"errcode={data.get('errcode')} {data.get('errmsg','')}"
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════════════════════════

def send_telegram(text: str, cfg: Dict) -> Tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "requests 未安装"

    token   = cfg.get("telegram_token",   "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return False, "telegram_token / telegram_chat_id 未配置"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text":    text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        if r.status_code == 200:
            return True, "ok"
        return False, r.text[:200]
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════
# DISPATCHER
# ════════════════════════════════════════════════════════════════

def dispatch_alerts(ticker: str, name: str, timeframe: str,
                    fibo: Dict, conf: Dict, cfg: Dict) -> None:
    cooldown = int(cfg.get("alert_cooldown", 240))
    if _is_cooldown(ticker, timeframe, cooldown):
        return

    text = build_message(ticker, name, timeframe, fibo, conf)
    sent = False

    from core.supabase_client import log_alert

    if cfg.get("dingtalk_enabled"):
        ok, msg = send_dingtalk(text, cfg)
        log_alert(ticker, name, timeframe, "dingtalk",
                  "ok" if ok else "fail", msg)
        sent = sent or ok

    if cfg.get("telegram_enabled"):
        ok, msg = send_telegram(text, cfg)
        log_alert(ticker, name, timeframe, "telegram",
                  "ok" if ok else "fail", msg)
        sent = sent or ok

    if sent:
        _mark_alerted(ticker, timeframe)
