"""
alerts.py — 告警引擎
DingTalk / Telegram，带冷却机制
"""

import hmac
import time
import base64
import hashlib
import logging
import urllib.parse
from datetime import datetime
from typing import Dict, Tuple

import storage

# ── 冷却缓存（进程内存）────────────────────────────────────────────
_cooldown: Dict[str, datetime] = {}


def _is_cooldown(ticker: str, tf: str, minutes: int) -> bool:
    key  = f"{ticker}::{tf}"
    last = _cooldown.get(key)
    if not last:
        return False
    return (datetime.now() - last).total_seconds() < minutes * 60


def _mark(ticker: str, tf: str) -> None:
    _cooldown[f"{ticker}::{tf}"] = datetime.now()


# ── 消息构建 ────────────────────────────────────────────────────────

def build_message(ticker: str, name: str, tf: str,
                  fibo: Dict, conf: Dict) -> str:
    from scanner import tv_url
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"📐 STRX Fibo 信号  {conf['label']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷  {name} ({ticker})\n"
        f"📅 框架: {tf}\n"
        f"💰 价格: {fibo['current']:,.4f}\n"
        f"📏 黄金区: {fibo['zone_bot']:,.4f} – {fibo['zone_top']:,.4f}\n"
        f"📉 回撤: {fibo['retrace_pct']:.1f}%\n"
        f"🔗 {tv_url(ticker)}\n"
        f"🕐 {now}"
    )


# ── DingTalk ────────────────────────────────────────────────────────

def send_dingtalk(text: str, cfg: Dict) -> Tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "requests 未安装"

    webhook = cfg.get("dingtalk_webhook", "").strip()
    secret  = cfg.get("dingtalk_secret",  "").strip()
    if not webhook:
        return False, "webhook 未配置"

    url = webhook
    if secret:
        ts  = str(round(time.time() * 1000))
        sig = base64.b64encode(
            hmac.new(secret.encode(),
                      f"{ts}\n{secret}".encode(),
                      digestmod=hashlib.sha256).digest()
        ).decode()
        url += f"&timestamp={ts}&sign={urllib.parse.quote_plus(sig)}"

    try:
        r    = requests.post(url, json={
            "msgtype":"text","text":{"content":text},"at":{"isAtAll":False}
        }, timeout=10)
        d = r.json()
        if d.get("errcode") == 0:
            return True, "ok"
        return False, f"errcode={d.get('errcode')} {d.get('errmsg','')}"
    except Exception as e:
        return False, str(e)


# ── Telegram ────────────────────────────────────────────────────────

def send_telegram(text: str, cfg: Dict) -> Tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "requests 未安装"

    token   = cfg.get("telegram_token",   "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return False, "token/chat_id 未配置"

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":text,
                  "parse_mode":"HTML","disable_web_page_preview":True},
            timeout=10,
        )
        if r.status_code == 200:
            return True, "ok"
        return False, r.text[:200]
    except Exception as e:
        return False, str(e)


# ── 调度器 ──────────────────────────────────────────────────────────

def dispatch_alerts(ticker: str, name: str, timeframe: str,
                    fibo: Dict, conf: Dict, cfg: Dict) -> None:
    cooldown = int(cfg.get("alert_cooldown", 240))
    if _is_cooldown(ticker, timeframe, cooldown):
        return

    text = build_message(ticker, name, timeframe, fibo, conf)
    sent = False

    if cfg.get("dingtalk_enabled"):
        ok, msg = send_dingtalk(text, cfg)
        storage.log_alert(ticker, name, timeframe, "dingtalk",
                          "ok" if ok else "fail", msg)
        sent = sent or ok

    if cfg.get("telegram_enabled"):
        ok, msg = send_telegram(text, cfg)
        storage.log_alert(ticker, name, timeframe, "telegram",
                          "ok" if ok else "fail", msg)
        sent = sent or ok

    if sent:
        _mark(ticker, timeframe)
