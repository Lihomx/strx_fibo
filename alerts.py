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

# ── 冷却缓存（文件持久化）────────────────────────────────────────────
def _is_cooldown(scanner: str, ticker: str, tf: str, minutes: int) -> bool:
    key = f"{scanner}::{ticker}::{tf}"
    cooldowns = storage.load_cooldowns()
    last_str = cooldowns.get(key)
    if not last_str:
        # 兼容旧版本格式 (无 scanner 前缀)
        legacy_key = f"{ticker}::{tf}"
        last_str = cooldowns.get(legacy_key)
        if not last_str:
            return False
    try:
        last = datetime.fromisoformat(last_str)
        return (datetime.now() - last).total_seconds() < minutes * 60
    except Exception:
        return False


def _mark(scanner: str, ticker: str, tf: str) -> None:
    key = f"{scanner}::{ticker}::{tf}"
    storage.save_cooldown(key, datetime.now().isoformat())


# ── 消息构建 ────────────────────────────────────────────────────────

def build_message(ticker: str, name: str, tf: str,
                  fibo: Dict, conf: Dict, template: str = None) -> str:
    from assets import tv_url  # 使用 assets 版本，支持 cn 域名 + 时间框架
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if template:
        res = template
        res = res.replace("{label}", str(conf.get("label", "")))
        res = res.replace("{name}", str(name))
        res = res.replace("{ticker}", str(ticker))
        res = res.replace("{tf}", str(tf))
        res = res.replace("{price}", f"{fibo.get('current', 0.0):,.4f}" if fibo.get("current") is not None else "—")
        res = res.replace("{zone_bot}", f"{fibo.get('zone_bot', 0.0):,.4f}" if fibo.get("zone_bot") is not None else "—")
        res = res.replace("{zone_top}", f"{fibo.get('zone_top', 0.0):,.4f}" if fibo.get("zone_top") is not None else "—")
        res = res.replace("{retrace_pct}", f"{fibo.get('retrace_pct', 0.0):.1f}" if fibo.get("retrace_pct") is not None else "—")
        res = res.replace("{url}", tv_url(ticker, tf))
        res = res.replace("{time}", now)
        return res
    return (
        f"📐 STRX Fibo 信号  {conf.get('label', '')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷  {name} ({ticker})\n"
        f"📅 框架: {tf}\n"
        f"💰 价格: {fibo['current']:,.4f}\n"
        f"📏 黄金区: {fibo['zone_bot']:,.4f} – {fibo['zone_top']:,.4f}\n"
        f"📉 回撤: {fibo['retrace_pct']:.1f}%\n"
        f"🔗 {tv_url(ticker, tf)}\n"
        f"🕐 {now}"
    )


def build_message_ema_pivot(ticker: str, name: str, tf: str,
                            price: float, ema: float, pivot: float,
                            label: str, template: str = None) -> str:
    from assets import tv_url  # 使用 assets 版本，支持 cn 域名 + 时间框架
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if template:
        res = template
        res = res.replace("{label}", str(label))
        res = res.replace("{name}", str(name))
        res = res.replace("{ticker}", str(ticker))
        res = res.replace("{tf}", str(tf))
        res = res.replace("{price}", f"{price:,.4f}")
        res = res.replace("{ema}", f"{ema:,.4f}")
        res = res.replace("{pivot}", f"{pivot:,.4f}")
        res = res.replace("{url}", tv_url(ticker, tf))
        res = res.replace("{time}", now)
        return res
    return (
        f"🚀 EMA20 + Daily Pivot 信号  {label}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷  {name} ({ticker})\n"
        f"📅 框架: {tf}\n"
        f"💰 价格: {price:,.4f}\n"
        f"📈 EMA20: {ema:,.4f}\n"
        f"🎯 Pivot: {pivot:,.4f}\n"
        f"🔗 {tv_url(ticker, tf)}\n"
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
    cooldown = int(cfg.get("alert_cooldown_fibo", cfg.get("alert_cooldown", 240)))
    if _is_cooldown("fibo", ticker, timeframe, cooldown):
        return

    tmpl = cfg.get("alert_template", "").strip()
    text = build_message(ticker, name, timeframe, fibo, conf, template=tmpl if tmpl else None)
    sent = False

    if cfg.get("dingtalk_enabled"):
        ok, msg = send_dingtalk(text, cfg)
        storage.log_alert(ticker, name, timeframe, "dingtalk",
                          "ok" if ok else "fail", msg, scanner="fibo")
        sent = sent or ok

    if cfg.get("telegram_enabled"):
        ok, msg = send_telegram(text, cfg)
        storage.log_alert(ticker, name, timeframe, "telegram",
                          "ok" if ok else "fail", msg, scanner="fibo")
        sent = sent or ok

    if sent:
        _mark("fibo", ticker, timeframe)


def dispatch_alerts_ema_pivot(ticker: str, name: str, timeframe: str,
                              price: float, ema: float, pivot: float,
                              label: str, cfg: Dict) -> None:
    cooldown = int(cfg.get("alert_cooldown_ema_pivot", cfg.get("alert_cooldown", 240)))
    if _is_cooldown("ema_pivot", ticker, timeframe, cooldown):
        return

    tmpl = cfg.get("alert_template_ema_pivot", "").strip()
    text = build_message_ema_pivot(ticker, name, timeframe, price, ema, pivot, label, template=tmpl if tmpl else None)
    sent = False

    if cfg.get("dingtalk_enabled"):
        ok, msg = send_dingtalk(text, cfg)
        storage.log_alert(ticker, name, timeframe, "dingtalk",
                          "ok" if ok else "fail", msg, scanner="ema_pivot")
        sent = sent or ok

    if cfg.get("telegram_enabled"):
        ok, msg = send_telegram(text, cfg)
        storage.log_alert(ticker, name, timeframe, "telegram",
                          "ok" if ok else "fail", msg, scanner="ema_pivot")
        sent = sent or ok

    if sent:
        _mark("ema_pivot", ticker, timeframe)
