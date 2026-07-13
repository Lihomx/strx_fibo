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
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logging.warning("APScheduler not installed: pip install apscheduler")
            return False

        import storage

        cfg = storage.load_config()
        if not cfg.get("scan_enabled"):
            return False

        hour   = int(cfg.get("scan_hour",   9))
        minute = int(cfg.get("scan_minute", 0))
        interval_min = int(cfg.get("scan_interval_minutes", 17))

        _scheduler = BackgroundScheduler(
            timezone="Asia/Shanghai",
            job_defaults={"misfire_grace_time": 300, "coalesce": True},
        )
        added_jobs = []
        if cfg.get("daily_scan_enabled", True):
            _scheduler.add_job(
                _run_scheduled_scan,
                CronTrigger(hour=hour, minute=minute, timezone="Asia/Shanghai"),
                id="daily_fibo_scan",
                replace_existing=True,
            )
            added_jobs.append(f"daily at {hour:02d}:{minute:02d} CST")
        if cfg.get("periodic_scan_enabled", True):
            _scheduler.add_job(
                _run_periodic_watchlist_scan,
                IntervalTrigger(minutes=interval_min, timezone="Asia/Shanghai"),
                id="periodic_watchlist_scan",
                replace_existing=True,
            )
            added_jobs.append(f"periodic every {interval_min}m")

        if not added_jobs:
            logging.info("Scheduler has no jobs enabled, not starting.")
            return False

        _scheduler.start()
        _started = True
        logging.info(f"Scheduler started with jobs: {', '.join(added_jobs)}")
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
        from scanner import run_full_scan
        import storage
        cfg = storage.load_config()
        summary, err = run_full_scan(cfg=cfg, note="scheduled")
        if err:
            logging.error(f"[Scheduler] 扫描失败: {err}")
        else:
            logging.info(f"[Scheduler] 扫描完成: {summary['session_id']}")
        
        # 同时进行定时三重底扫描（针对自选收藏和热门品种）
        try:
            logging.info("[Scheduler] 启动定时三重底扫描...")
            wl_items = storage.load_watchlist()
            hl_items = storage.load_hotlist()
            tickers = list({i["ticker"].upper() for i in wl_items + hl_items if i.get("ticker")})
            if tickers:
                from scanner import fetch_data
                from triple_bottom_scanner import scan_triple_bottoms
                
                # 默认扫描 4h 和 1d 周期
                periods = ["4h", "1d"]
                timeframe_configs = {
                    "4h": ("4h", "2y"),
                    "1d": ("1d", "2y")
                }
                
                tb_results = []
                for ticker in tickers:
                    for period_key in periods:
                        interval, yf_period = timeframe_configs[period_key]
                        try:
                            df = fetch_data(ticker, interval=interval, period=yf_period)
                            if df is not None and not df.empty:
                                matches = scan_triple_bottoms(df, symbol=ticker, swing_window=3, lookback_bars=120, max_spacing=60)
                                for m in matches:
                                    if m.confidence >= 0.6:
                                        tb_results.append({
                                            "symbol": m.symbol,
                                            "period": period_key,
                                            "pattern": m.pattern,
                                            "confidence": m.confidence,
                                            "idx1": int(m.idx1),
                                            "idx2": int(m.idx2),
                                            "idx3": int(m.idx3),
                                            "low1": float(m.low1),
                                            "low2": float(m.low2),
                                            "low3": float(m.low3),
                                            "mid_high": float(m.mid_high),
                                            "note": m.note,
                                            "status": m.status,
                                            "status_reason": m.status_reason,
                                            "bars_since_low3": int(m.bars_since_low3),
                                            "latest_close": float(m.latest_close),
                                            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                        except Exception:
                            pass
                storage.save_triple_bottom(tb_results)
                logging.info(f"[Scheduler] 定时三重底扫描完成：发现 {len(tb_results)} 个形态候选")
        except Exception as ex_tb:
            logging.exception(f"[Scheduler] 定时三重底扫描异常: {ex_tb}")
    except Exception as e:
        logging.exception(f"[Scheduler] 异常: {e}")


def _run_periodic_watchlist_scan() -> None:
    """每隔指定分钟扫描一次已收藏的品种，使用 EMA20 + Daily Pivot Point 策略 (15分钟)"""
    logging.info(f"[Scheduler] 周期自选扫描启动: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    try:
        import storage
        import scanner
        from alerts import dispatch_alerts_ema_pivot
        
        cfg = storage.load_config()
        if not cfg.get("scan_enabled"):
            logging.info("[Scheduler] 扫描开关未开启，跳过本次周期扫描")
            return
            
        wl_items = storage.load_watchlist()
        if not wl_items:
            logging.info("[Scheduler] 自选列表为空，跳过本次周期扫描")
            return
            
        for item in wl_items:
            ticker = item.get("ticker")
            if not ticker:
                continue
            name = item.get("name", ticker)
            
            try:
                res = scanner.scan_ema_pivot(ticker=ticker, cfg=cfg)
                if res and res["is_signal"]:
                    dispatch_alerts_ema_pivot(
                        ticker=ticker,
                        name=name,
                        timeframe="15m",
                        price=res["price"],
                        ema=res["ema"],
                        pivot=res["pivot"],
                        label="多头突破",
                        cfg=cfg
                    )
            except Exception as e:
                logging.warning(f"[Scheduler] 扫描 {ticker} 出错: {e}")
                
    except Exception as e:
        logging.exception(f"[Scheduler] 周期自选扫描异常: {e}")

