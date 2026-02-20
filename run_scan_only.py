"""
run_scan_only.py
独立扫描脚本 — 用于 GitHub Actions / 外部 Cron 触发
不需要启动 Streamlit，直接运行即可

用法:
    python run_scan_only.py

环境变量:
    SUPABASE_URL  — Supabase Project URL
    SUPABASE_KEY  — Supabase anon key
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ── 模拟 Streamlit secrets 环境（非 Streamlit 运行时）────────────
class _FakeSecrets:
    def __getitem__(self, key):
        if key == "supabase":
            return {
                "url": os.environ.get("SUPABASE_URL", ""),
                "key": os.environ.get("SUPABASE_KEY", ""),
            }
        raise KeyError(key)

try:
    import streamlit as st
    # 如果 streamlit 已初始化，正常使用
except Exception:
    pass

# 注入环境变量到 secrets
try:
    import streamlit as st
    if not hasattr(st, "secrets") or not st.secrets.get("supabase"):
        class _MockSecrets:
            def get(self, key, default=None):
                return {"supabase": {
                    "url": os.environ.get("SUPABASE_URL",""),
                    "key": os.environ.get("SUPABASE_KEY",""),
                }}.get(key, default)
            def __getitem__(self, key):
                return self.get(key)
except Exception:
    pass


def main():
    logging.info("=" * 50)
    logging.info("STRX Fibo Scanner — Standalone Run")
    logging.info("=" * 50)

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    if not url or not key:
        logging.error("❌ 缺少环境变量 SUPABASE_URL / SUPABASE_KEY")
        sys.exit(1)

    # 初始化 Supabase
    from supabase import create_client
    from core import supabase_client as sc
    sc._client = create_client(url, key)
    logging.info("✅ Supabase 连接成功")

    # 执行扫描
    from core.scanner import run_full_scan
    from core.supabase_client import load_config

    cfg = load_config()
    logging.info(f"配置加载完成: lookback={cfg['lookback']}, source={cfg['data_source']}")

    def progress(pct, msg):
        logging.info(f"[{pct*100:.0f}%] {msg}")

    summary, err = run_full_scan(cfg=cfg, note="cron", progress_callback=progress)

    if err:
        logging.error(f"❌ 扫描失败: {err}")
        sys.exit(1)

    logging.info(f"✅ 扫描完成: {summary['note']}")
    logging.info(f"   区间内信号: {summary['inzone_count']}")
    logging.info(f"   三框架共振: {summary['triple_conf']}")
    logging.info(f"   耗时: {summary['elapsed_ms']}ms")


if __name__ == "__main__":
    main()
