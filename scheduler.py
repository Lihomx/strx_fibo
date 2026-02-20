"""
core/scheduler.py
APScheduler 定时扫描 — 在 Streamlit 中安全启动（只启动一次）
"""

import logging
import threading
from datetime import datetime
from typing import Optional

# ── 全局单例 ─────────────────────────────────────────────────────
_scheduler  = None
_lock       = threading.Lock()
_started    = False   # 防止 Streamlit rerun 重复启动


def start_scheduler_if_needed() -> bool:
    """
    在 Streamlit 应用启动时调用一次。
    APScheduler BackgroundScheduler 在 daemon 线程中运行，
    不阻塞 Streamlit 主线程。
    """
    global _scheduler, _started

    if _started:
        return True

    with _lock:
        if _started:
            return True

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logging.warning("APScheduler not installed: pip install apscheduler")
            return False

        from core.supabase_client import load_config

        cfg = load_config()
        if not cfg.get("scan_enabled"):
            return False

        hour   = int(cfg.get("scan_hour",   9))
        minute = int(cfg.get("scan_minute", 0))

        _scheduler = BackgroundScheduler(
            timezone="Asia/Shanghai",
            job_defaults={"misfire_grace_time": 300, "coalesce": True},
        )
        _scheduler.add_job(
            _run_scheduled_scan,
            CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai"),
            id="daily_fibo_scan",
            replace_existing=True,
        )
        _scheduler.start()
        _started = True
        logging.info(f"Scheduler started: daily at {hour:02d}:{minute:02d} CST")
        return True


def restart_scheduler(hour: int, minute: int) -> bool:
    """重启调度器（修改时间后调用）"""
    global _scheduler, _started

    with _lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
        _started = False

    return start_scheduler_if_needed()


def get_scheduler_status() -> dict:
    if _scheduler is None:
        return {"running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id":       job.id,
            "next_run": str(next_run) if next_run else "—",
        })
    return {"running": _scheduler.running, "jobs": jobs}


def _run_scheduled_scan() -> None:
    """定时任务执行体"""
    logging.info(f"[Scheduler] 定时扫描启动: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        from core.scanner import run_full_scan
        from core.supabase_client import load_config
        cfg = load_config()
        summary, err = run_full_scan(cfg=cfg, note="scheduled")
        if err:
            logging.error(f"[Scheduler] 扫描失败: {err}")
        else:
            logging.info(f"[Scheduler] 扫描完成: {summary['note']}")
    except Exception as e:
        logging.exception(f"[Scheduler] 异常: {e}")
