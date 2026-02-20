"""pages/page_schedule.py — 定时任务配置"""

import streamlit as st
from core.supabase_client import load_config, save_config
from core.scheduler import get_scheduler_status, restart_scheduler


def render():
    st.markdown("## ⏰ 定时扫描任务")
    st.markdown("配置每日自动扫描时间，结果自动存入 Supabase 数据库并触发告警。")

    st.markdown("""
    <div class="notice-warn">
    ⚠️ <b>依赖说明：</b>需安装 APScheduler：<code>pip install apscheduler</code><br>
    定时任务在 Streamlit 后台线程运行。<b>修改时间后需重启应用生效。</b><br>
    Streamlit Cloud 部署时：建议改用 Supabase Edge Functions 或外部 Cron 服务（见下方说明）。
    </div>
    """, unsafe_allow_html=True)

    cfg = load_config()

    # 当前调度状态
    status = get_scheduler_status()
    if status["running"]:
        jobs = status.get("jobs", [])
        next_run = jobs[0]["next_run"] if jobs else "—"
        st.markdown(f'<div class="notice-ok">✅ 定时器运行中 · 下次执行：{next_run}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="notice-warn">⏸ 定时器未启动（已停用或 APScheduler 未安装）</div>',
                    unsafe_allow_html=True)

    st.markdown("---")

    # 配置表单
    col1, col2, col3 = st.columns(3)
    with col1:
        enabled = st.toggle("启用每日定时扫描", value=bool(cfg.get("scan_enabled")))
    with col2:
        hour = st.number_input("扫描小时（24h制）", min_value=0, max_value=23,
                               value=int(cfg.get("scan_hour", 9)))
    with col3:
        minute = st.number_input("扫描分钟", min_value=0, max_value=59,
                                 value=int(cfg.get("scan_minute", 0)))

    st.caption(f"当前设置：每天 **{hour:02d}:{minute:02d}** 北京时间 (Asia/Shanghai) 自动扫描")

    if st.button("💾 保存并重启定时器", type="primary"):
        ok = save_config({
            "scan_enabled": enabled,
            "scan_hour":    hour,
            "scan_minute":  minute,
        })
        if ok:
            if enabled:
                restart_scheduler(hour, minute)
                st.success(f"✅ 已保存，定时器已重启：每天 {hour:02d}:{minute:02d} CST 自动扫描")
            else:
                st.success("✅ 已保存，定时扫描已停用")
        else:
            st.error("❌ 保存失败，请检查 Supabase 连接")

    st.divider()

    # 云端 Cron 方案说明
    st.markdown("### ☁️ 生产环境推荐：外部 Cron 触发")
    st.markdown("""
    Streamlit Cloud 不保证后台线程持续运行，建议使用以下方案之一触发定时扫描：

    **方案 A：Supabase Edge Functions + pg_cron（推荐）**
    ```sql
    -- 在 Supabase SQL Editor 中执行：
    SELECT cron.schedule(
      'daily-fibo-scan',
      '0 1 * * *',   -- 每天 UTC 01:00 = 北京时间 09:00
      $$
      SELECT net.http_post(
        'https://YOUR_APP.streamlit.app/api/trigger_scan',
        '{}', 'application/json'
      );
      $$
    );
    ```

    **方案 B：GitHub Actions 定时触发**
    ```yaml
    # .github/workflows/daily_scan.yml
    on:
      schedule:
        - cron: '0 1 * * *'   # UTC 01:00 = CST 09:00
    jobs:
      scan:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v3
          - run: pip install -r requirements.txt
          - run: python run_scan_only.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
    ```

    **方案 C：cron-job.org（免费外部定时服务）**
    - 注册 https://cron-job.org → 创建任务 → 每天 09:00 访问你的扫描触发 URL
    """)
