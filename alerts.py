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

def _calc_signal_hash(price: float, label: str) -> str:
    import hashlib
    raw = f"{price:.6f}|{label}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _is_cooldown(scanner: str, ticker: str, tf: str, minutes: int, current_hash: str = "") -> bool:
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
        cached_hash = ""
        if "|" in last_str:
            last_time_str, cached_hash = last_str.split("|", 1)
        else:
            last_time_str = last_str
            
        last = datetime.fromisoformat(last_time_str)
        
        # 如果哈希完全一致（说明价格和标签未发生任何变化，通常为周末休市或横盘），强制冷却 8 小时
        if current_hash and cached_hash == current_hash:
            if (datetime.now() - last).total_seconds() < 8 * 3600:
                return True
                
        return (datetime.now() - last).total_seconds() < minutes * 60
    except Exception:
        return False


def _mark(scanner: str, ticker: str, tf: str, current_hash: str = "") -> None:
    key = f"{scanner}::{ticker}::{tf}"
    val = datetime.now().isoformat()
    if current_hash:
        val = f"{val}|{current_hash}"
    storage.save_cooldown(key, val)


# ── 消息构建 ────────────────────────────────────────────────────────

def _get_tz_now_str() -> str:
    from zoneinfo import ZoneInfo
    try:
        cfg = storage.load_config()
        tz_name = cfg.get("timezone", "Asia/Shanghai")
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M")


def build_message(ticker: str, name: str, tf: str,
                  fibo: Dict, conf: Dict, template: str = None) -> str:
    from assets import tv_url  # 使用 assets 版本，支持 cn 域名 + 时间框架
    import storage
    is_starred = storage.is_ticker_starred(ticker)
    starred_prefix = "⭐[重点关注] " if is_starred else ""
    now = _get_tz_now_str()
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
        if starred_prefix:
            res = starred_prefix + "\n" + res
        return res
    return (
        f"{starred_prefix}📐 STRX Fibo 信号  {conf.get('label', '')}\n"
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
    import storage
    is_starred = storage.is_ticker_starred(ticker)
    starred_prefix = "⭐[重点关注] " if is_starred else ""
    now = _get_tz_now_str()
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
        if starred_prefix:
            res = starred_prefix + "\n" + res
        return res
    return (
        f"{starred_prefix}🚀 EMA20 + Daily Pivot 信号  {label}\n"
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

def send_browser_notification(title: str, body: str, target_url: str = "", timeout_seconds: int = 15) -> None:
    """
    Sends a browser notification using the native Web Notification API.
    Disappears after the specified timeout_seconds (default 15s).
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if not get_script_run_ctx():
            return
        import streamlit as st
    except ImportError:
        return

    try:
        cfg = storage.load_config()
        sound_enabled = cfg.get("browser_notification_sound_enabled", False)
    except Exception:
        sound_enabled = False

    t_esc = title.replace('"', '\\"').replace("'", "\\'")
    b_esc = body.replace('"', '\\"').replace("'", "\\'")
    u_esc = target_url.replace('"', '\\"').replace("'", "\\'")

    sound_js = ""
    if sound_enabled:
        sound_js = """
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext || window.parent.AudioContext || window.parent.webkitAudioContext;
            const ctx = new AudioContext();
            
            // Beep 1
            const osc1 = ctx.createOscillator();
            const gain1 = ctx.createGain();
            osc1.connect(gain1);
            gain1.connect(ctx.destination);
            osc1.frequency.setValueAtTime(880, ctx.currentTime);
            gain1.gain.setValueAtTime(0.08, ctx.currentTime);
            gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
            osc1.start(ctx.currentTime);
            osc1.stop(ctx.currentTime + 0.12);
            
            // Beep 2
            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            osc2.frequency.setValueAtTime(1046.5, ctx.currentTime + 0.15);
            gain2.gain.setValueAtTime(0.08, ctx.currentTime + 0.15);
            gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.32);
            osc2.start(ctx.currentTime + 0.15);
            osc2.stop(ctx.currentTime + 0.32);
        } catch (e) {
            console.error("AudioContext play failed", e);
        }
        """

    click_js = ""
    if u_esc:
        click_js = f"""
                    notification.onclick = function() {{
                        try {{
                            const win = window.parent || window;
                            win.focus();
                            win.location.href = "{u_esc}";
                        }} catch (e) {{
                            try {{
                                window.top.location.href = "{u_esc}";
                            }} catch (err) {{
                                window.location.href = "{u_esc}";
                            }}
                        }}
                    }};
        """

    js_code = f"""
    <script>
    (function() {{
        {sound_js}
        if ("Notification" in window) {{
            Notification.requestPermission().then(perm => {{
                if (perm === 'granted') {{
                    const notification = new Notification("{t_esc}", {{
                        body: "{b_esc}"
                    }});
                    {click_js}
                    setTimeout(() => {{
                        notification.close();
                    }}, {timeout_seconds * 1000});
                }}
            }});
        }}
    }})();
    </script>
    """
    try:
        from streamlit.components.v1 import html as _html
        _html(js_code, width=0, height=0)
    except Exception as e:
        pass


def dispatch_alerts(ticker: str, name: str, timeframe: str,
                    fibo: Dict, conf: Dict, cfg: Dict) -> None:
    cooldown = int(cfg.get("alert_cooldown_fibo", cfg.get("alert_cooldown", 240)))
    cur_price = fibo.get("current", 0.0) if fibo.get("current") is not None else 0.0
    cur_label = conf.get("label", "")
    sig_hash = _calc_signal_hash(cur_price, cur_label)

    if _is_cooldown("fibo", ticker, timeframe, cooldown, sig_hash):
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

    # Also send browser notification to the active Streamlit app session
    try:
        title = f"📐 Fibo 信号: {conf.get('label', '')}"
        body = f"{name} ({ticker}) [{timeframe}] - 价格: {cur_price}"
        send_browser_notification(title, body, timeout_seconds=15)
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to send browser notification: {e}")

    if sent:
        _mark("fibo", ticker, timeframe, sig_hash)


def dispatch_alerts_ema_pivot(ticker: str, name: str, timeframe: str,
                              price: float, ema: float, pivot: float,
                              label: str, cfg: Dict) -> None:
    cooldown = int(cfg.get("alert_cooldown_ema_pivot", cfg.get("alert_cooldown", 240)))
    sig_hash = _calc_signal_hash(price, label)
    if _is_cooldown("ema_pivot", ticker, timeframe, cooldown, sig_hash):
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

    # Also send browser notification to the active Streamlit app session
    try:
        title = f"🚀 EMA + Pivot 信号: {label}"
        body = f"{name} ({ticker}) [{timeframe}] - 价格: {price}"
        send_browser_notification(title, body, timeout_seconds=15)
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to send browser notification: {e}")

    if sent:
        _mark("ema_pivot", ticker, timeframe, sig_hash)
