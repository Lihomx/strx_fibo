#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
daemon.py — 实时推送常驻守护进程
24/7 在后台运行，定期扫描自选收藏(Watchlist)与热门品种(Hotlist)并触发实时告警；
支持每日定时全量扫描，自动执行 Supabase 云同步，保证远程 Streamlit Cloud 页面实时更新。

用法:
    python daemon.py [--interval 15] [--once] [--full] [--force-sync]
"""

import os
import sys
import time
import argparse
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta

# 确保项目根目录在 sys.path 中以支持平级导入
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 自动从 Doc/System.txt 加载 Supabase 环境变量 (本地无配置时的智能降级)
def load_env_from_system_doc():
    doc_path = os.path.join(BASE_DIR, "Doc", "System.txt")
    if os.path.exists(doc_path):
        try:
            with open(doc_path, "r", encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("SUPABASE_URL="):
                    val = line.split("=", 1)[1].strip('"').strip("'")
                    os.environ.setdefault("SUPABASE_URL", val)
                elif line.startswith("SUPABASE_KEY="):
                    val = line.split("=", 1)[1].strip('"').strip("'")
                    os.environ.setdefault("SUPABASE_KEY", val)
                elif line.startswith("SUPABASE_BUCKET="):
                    val = line.split("=", 1)[1].strip('"').strip("'")
                    os.environ.setdefault("SUPABASE_BUCKET", val)
        except Exception as e:
            print(f"[Warning] Failed to parse Doc/System.txt: {e}")

load_env_from_system_doc()

# 导入本地功能模块
try:
    import storage
    import scanner
    import cloud_sync
    import alerts
    from assets import ASSETS
except ImportError as e:
    print(f"❌ 导入依赖模块失败，请确保在项目根目录运行该脚本: {e}")
    sys.exit(1)


def setup_logging(verbose: bool):
    """配置日志处理器 (输出至终端 + 滚动日志文件 daemon.log)"""
    # 强制将标准输出/错误流重构为 UTF-8 编码，防止 Windows 终端因 GBK 编码引发 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    
    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 移除已有的 handlers 避免重复打印
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # 终端输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # 滚动文件输出 (最多 5MB，保留 3 个备份)
    file_path = os.path.join(BASE_DIR, "daemon.log")
    file_handler = RotatingFileHandler(file_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.INFO)  # 文件记录 INFO 及以上
    logger.addHandler(file_handler)

    logging.info(f"📝 日志初始化成功。文件输出路径: {file_path}")


def get_scan_targets() -> dict:
    """加载自选收藏与热门品种，去重合并，转换为 scanner 能够接受的 assets 字典格式"""
    watchlist = storage.load_watchlist()
    hotlist = storage.load_hotlist()
    
    assets_to_scan = {}
    
    # 加载 Watchlist 品种
    for item in watchlist:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker", "").strip().upper()
        if ticker:
            name = item.get("name") or ticker
            assets_to_scan[ticker] = (name.strip(), "Watchlist")

    # 合并 Hotlist 品种
    for item in hotlist:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker", "").strip().upper()
        if ticker:
            name = item.get("name") or ticker
            if ticker in assets_to_scan:
                # 保留各自的原名称，但分类合并为 Watchlist+Hotlist 以做标记
                assets_to_scan[ticker] = (assets_to_scan[ticker][0], "Watchlist+Hotlist")
            else:
                assets_to_scan[ticker] = (name.strip(), "Hotlist")

    return assets_to_scan


def execute_scan(assets: dict, note: str, skip_sync: bool, force_sync: bool):
    """运行实际扫描，并同步至 Supabase 云端"""
    if not assets:
        logging.info("⚠️ 当前无扫描目标资产 (Watchlist 与 Hotlist 均为空)，略过本次扫描。")
        return

    logging.info(f"🚀 开始执行扫描批次 ({note})，共 {len(assets)} 个资产品种...")
    t0 = time.time()
    
    # 调用 scanner 执行扫描，并自动触发内部的 alerts 逻辑
    summary, err = scanner.run_full_scan(
        cfg=storage.load_config(),
        assets=assets,
        note=note
    )
    
    elapsed = time.time() - t0
    if err:
        logging.error(f"❌ 扫描过程中发生错误: {err}")
        return

    logging.info(f"✅ 扫描完成！共命中黄金区 {summary.get('inzone_count', 0)} 个，共振 {summary.get('triple_conf', 0)} 个。耗时 {elapsed:.2f}秒。")

    # Supabase 云端同步
    if skip_sync:
        logging.info("ℹ️ 已配置跳过云同步。")
        return

    if not cloud_sync.is_configured():
        logging.warning("⚠️ 未配置 Supabase 环境变量，跳过云同步。")
        return

    logging.info("🔄 正在将本地最新扫描数据与快照同步至 Supabase 云端...")
    sync_ok, sync_msg = cloud_sync.push_all(force=force_sync)
    if sync_ok:
        logging.info(f"✅ 云端同步成功: {sync_msg}")
    else:
        logging.error(f"❌ 云端同步失败: {sync_msg}")


def main():
    parser = argparse.ArgumentParser(description="STRX Fibo Scanner Resident Daemon")
    parser.add_argument("--interval", type=int, default=15, help="自选/热门资产的循环扫描间隔 (分钟，默认15)")
    parser.add_argument("--once", action="store_true", help="单次扫描模式：运行一次后立即退出")
    parser.add_argument("--full", action="store_true", help="立即运行一次完整的全球超级品种注册库扫描 (耗时较长)")
    parser.add_argument("--no-sync", action="store_true", help="本地离线运行，跳过向 Supabase 同步")
    parser.add_argument("--force-sync", action="store_true", help="强制云同步，跳过本地/云端降幅安全拦截机制")
    parser.add_argument("--verbose", action="store_true", help="启用 DEBUG 级别日志输出")
    args = parser.parse_args()

    setup_logging(args.verbose)

    logging.info("=" * 60)
    logging.info("   STRX Fibo Scanner Pro — Background Resident Daemon")
    logging.info(f"   PID: {os.getpid()}  |  Interval: {args.interval}m")
    logging.info("=" * 60)

    # 1. 验证并同步初始 Supabase 配置
    if not args.no_sync:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if url and key:
            logging.info(f"☁️ Supabase 配置已载入。URL: {url[:30]}...")
            logging.info("🔄 正在执行启动全量云同步拉取 (Restore local cache)...")
            res = cloud_sync.pull_all()
            logging.info(f"✅ 启动云同步拉取完成: {res}")
        else:
            logging.warning("⚠️ 未检测到 Supabase 配置，数据将仅在本地保存，Streamlit Cloud 无法获取最新状态。")

    # 2. 如果强制执行 Full registry 扫描
    if args.full:
        logging.info("🔥 启动强制全量扫描模式 (扫描全球所有预设品种)...")
        execute_scan(ASSETS, "daemon_full_manual", args.no_sync, args.force_sync)
        if args.once:
            logging.info("👋 单次运行结束，守护进程退出。")
            sys.exit(0)

    # 3. 如果只是单次运行
    if args.once:
        if not args.no_sync and cloud_sync.is_configured():
            logging.info("🔄 从 Supabase 拉取最新自选和热门配置...")
            cloud_sync.pull_watchlist()
            cloud_sync.pull_hotlist()
        targets = get_scan_targets()
        logging.info(f"📊 自选+热门合并资产清单: 共加载 {len(targets)} 个独特品种")
        execute_scan(targets, "daemon_once", args.no_sync, args.force_sync)
        logging.info("👋 单次运行结束，守护进程退出。")
        sys.exit(0)

    # 4. 进入 24/7 守护运行逻辑
    last_daily_scan_date = None
    last_interval_scan_time = None
    interval_delta = timedelta(minutes=args.interval)

    logging.info("💫 守护进程开始挂起监听中...")
    try:
        while True:
            now = datetime.now()
            current_date = now.date()

            # A. 检查每日定时扫描是否到期 (由 data_config.json 的 scan_enabled / scan_hour / scan_minute 决定)
            cfg = storage.load_config()
            if cfg.get("scan_enabled", False):
                hour = int(cfg.get("scan_hour", 9))
                minute = int(cfg.get("scan_minute", 0))
                # 检查当前时间是否达到设定的小时 and 分钟，且今天还未进行过全量扫描
                if now.hour == hour and now.minute == minute and last_daily_scan_date != current_date:
                    logging.info(f"⏰ 触发每日定时全量扫描 (计划时间 {hour:02d}:{minute:02d})...")
                    try:
                        execute_scan(ASSETS, "daemon_daily_cron", args.no_sync, args.force_sync)
                        last_daily_scan_date = current_date
                    except Exception as e:
                        logging.error(f"❌ 每日全量扫描执行异常: {e}")

            # B. 检查周期性自选+热门扫描是否到期
            if last_interval_scan_time is None or (now - last_interval_scan_time) >= interval_delta:
                if not args.no_sync and cloud_sync.is_configured():
                    logging.info("🔄 从 Supabase 拉取最新自选和热门配置...")
                    cloud_sync.pull_watchlist()
                    cloud_sync.pull_hotlist()
                targets = get_scan_targets()
                logging.info(f"🔄 触发周期性自选+热门扫描 (共 {len(targets)} 个品种)...")
                try:
                    execute_scan(targets, "daemon_interval", args.no_sync, args.force_sync)
                    last_interval_scan_time = now
                except Exception as e:
                    logging.error(f"❌ 周期扫描执行异常: {e}")

            # C. 短暂休眠，避免死循环高负荷 CPU
            time.sleep(10)

    except KeyboardInterrupt:
        logging.info("👋 接收到 KeyboardInterrupt 中断信号，守护进程正在安全退出。")
        sys.exit(0)
    except Exception as e:
        logging.critical(f"💥 守护进程因未捕获的严重异常崩溃: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
