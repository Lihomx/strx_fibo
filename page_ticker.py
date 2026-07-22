"""
page_ticker.py — 品种详细信息页面
=========================================
实现功能：
  1. 显示品种基本信息、外部行情链接、星标（重点关注）开关。
  2. 📝 品种备注：支持针对该品种添加、编辑和保存个人笔记和备注，并与自选收藏备忘录联动。
  3. 🔔 告警历史：展示该品种触发的全部历史告警日志。
  4. 📊 扫描历史：展示该品种在最新扫描器中的信号状态和指标详情。
"""

import streamlit as st
import pandas as pd
import time
import storage
from assets import tv_url, sina_url

# ── CSS 注入 ──
def _inject_ticker_css():
    st.markdown("""
    <style>
    .ticker-header-card {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.01) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
    }
    .ticker-title {
        font-size: 28px;
        font-weight: 700;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .ticker-subtitle {
        font-family: monospace;
        font-size: 16px;
        color: #9ca3af;
        margin-bottom: 16px;
    }
    .link-group {
        display: flex;
        gap: 10px;
        margin-top: 10px;
    }
    .ticker-btn {
        display: inline-flex;
        align-items: center;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        text-decoration: none !important;
        transition: all 0.2s;
    }
    .ticker-btn-tv {
        background-color: rgba(30, 144, 255, 0.15);
        color: #38bdf8 !important;
        border: 1px solid rgba(30, 144, 255, 0.3);
    }
    .ticker-btn-tv:hover {
        background-color: rgba(30, 144, 255, 0.3);
        color: #60a5fa !important;
    }
    .ticker-btn-sina {
        background-color: rgba(255, 69, 0, 0.15);
        color: #ff6347 !important;
        border: 1px solid rgba(255, 69, 0, 0.3);
    }
    .ticker-btn-sina:hover {
        background-color: rgba(255, 69, 0, 0.3);
        color: #ff7f50 !important;
    }
    .timeline-card {
        border-left: 3px solid rgba(59, 130, 246, 0.5);
        background: rgba(255, 255, 255, 0.02);
        padding: 14px 18px;
        margin-bottom: 12px;
        border-radius: 0 8px 8px 0;
        transition: background 0.2s;
    }
    .timeline-card:hover {
        background: rgba(255, 255, 255, 0.04);
    }
    .timeline-time {
        font-size: 12px;
        color: #9ca3af;
        margin-bottom: 4px;
        font-family: monospace;
    }
    .timeline-content {
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)


def render(ticker: str = None):
    _inject_ticker_css()
    
    # 1. 提取品种代码
    if not ticker:
        ticker = st.query_params.get("_ticker", "").strip().upper()
        
    if not ticker:
        st.error("⚠️ 未指定有效的品种代码！")
        if st.button("⬅️ 返回行情扫描"):
            st.query_params["_page"] = "scanner"
            st.rerun()
        return

    # 2. 查询品种友好名称
    name = ticker
    symbols = storage.load_symbols()
    sym_info = next((s for s in symbols if s["ticker"] == ticker), None)
    if sym_info and sym_info.get("name"):
        name = sym_info["name"]
    else:
        # 在自选列表中寻找友好名称
        wl = storage.load_watchlist()
        wl_info = next((w for w in wl if w["ticker"] == ticker), None)
        if wl_info and wl_info.get("name"):
            name = wl_info["name"]

    is_starred = storage.is_ticker_starred(ticker)
    
    # 3. 头部信息卡片
    st.markdown('<div class="ticker-header-card">', unsafe_allow_html=True)
    
    c_title, c_star = st.columns([8, 2])
    with c_title:
        st.markdown(f'<div class="ticker-title">💎 {name} <span style="font-size:16px;color:#9ca3af;font-weight:normal;">({ticker})</span></div>', unsafe_allow_html=True)
    with c_star:
        # 星标重点关注交互按钮
        t_token = st.query_params.get("_t", "")
        star_btn_text = "⭐ 已设为重点" if is_starred else "☆ 设为重点关注"
        if st.button(star_btn_text, key="ticker_star_toggle_btn", use_container_width=True):
            storage.toggle_starred_ticker(ticker)
            st.toast(f"重点关注状态已更新：{ticker}", icon="⭐")
            time.sleep(0.5)
            st.rerun()
            
    # 外部链接按钮
    tv_href = tv_url(ticker, "15m")
    sina_href = sina_url(ticker)
    
    st.markdown('<div class="link-group">', unsafe_allow_html=True)
    links_html = f'<a href="{tv_href}" target="_blank" class="ticker-btn ticker-btn-tv">📈 TradingView 图表</a>'
    if sina_href:
        links_html += f'<a href="{sina_href}" target="_blank" class="ticker-btn ticker-btn-sina">🏦 新浪财经</a>'
    st.markdown(links_html + '</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # 4. 功能 Tab 页
    t1, t2, t3 = st.tabs(["📝 品种备注/备忘", "🔔 历史告警记录", "📊 最新扫描指标"])
    
    # --- Tab 1: 品种备注/备忘 ---
    with t1:
        st.markdown("### 📝 品种备忘录")
        st.caption("在此记录关于该品种的分析随笔、策略心得或操作日志。数据会自动进行云端备份。")
        
        # 载入备注内容
        note_text = storage.load_ticker_notes(ticker)
        
        # 备注文本框
        with st.form("ticker_note_form", clear_on_submit=False):
            new_note = st.text_area("编辑备注信息", value=note_text, height=260, placeholder="写下关于此品种的跟踪计划，例如：已建仓，止损位设在... 或 回撤至0.618时考虑吸纳...")
            submitted = st.form_submit_button("💾 保存备注信息", use_container_width=True, type="primary")
            if submitted:
                storage.save_ticker_note(ticker, new_note)
                st.success("✅ 备注保存成功，已同步至云端！")
                
        # 联动自选收藏的备注 (如果该品种在收藏夹中，顺便显示收藏夹历史备注)
        wl = storage.load_watchlist()
        wl_item = next((w for w in wl if w["ticker"] == ticker), None)
        if wl_item and wl_item.get("notes"):
            st.markdown("##### 📂 关联的自选收藏夹备注历史")
            for idx, wl_note in enumerate(wl_item["notes"]):
                st.info(f"💡 {wl_note}")

    # --- Tab 2: 历史告警记录 ---
    with t2:
        st.markdown("### 🔔 本品种历史告警记录")
        all_logs = storage.load_alert_log(limit=0) # 0 代表加载全部
        ticker_logs = [log for log in all_logs if log and log.get("ticker", "").strip().upper() == ticker]
        
        if not ticker_logs:
            st.info("💡 暂无该品种的告警推送历史。")
        else:
            # 按时间倒序展示
            ticker_logs = sorted(ticker_logs, key=lambda x: x.get("time", ""), reverse=True)
            
            for idx, log in enumerate(ticker_logs):
                # 时区格式化
                t_str = log.get("time", "")
                try:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    cfg = storage.load_config()
                    tz_name = cfg.get("timezone", "Asia/Shanghai")
                    if "T" in t_str:
                        dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                        dt_local = dt.astimezone(ZoneInfo(tz_name))
                        time_display = dt_local.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        time_display = t_str
                except Exception:
                    time_display = t_str
                
                scanner = log.get("scanner", "fibo")
                scanner_label = "EMA + Pivot" if scanner == "ema_pivot" else "Fibonacci"
                tf = log.get("timeframe", "")
                status = log.get("status", "")
                status_icon = "✅ 成功" if status in ("ok", "成功") else "❌ 失败"
                channel = log.get("channel", "")
                msg = log.get("message", "")
                
                st.markdown(f"""
                <div class="timeline-card">
                    <div class="timeline-time">⏰ {time_display}  |  框架: {tf}  |  通道: {channel} ({status_icon})</div>
                    <div class="timeline-content">
                        <b>{scanner_label} 信号触发</b>：{msg}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # --- Tab 3: 最新扫描指标 ---
    with t3:
        st.markdown("### 📊 最新扫描缓存")
        st.caption("展示此品种在全部周期和扫描器下的最新运算结果。")
        
        allres = storage._load(storage.F_ALLRES, [])
        ticker_res = [r for r in allres if isinstance(r, dict) and r.get("ticker", "").strip().upper() == ticker]
        
        if not ticker_res:
            st.info("💡 暂无该品种在各框架的扫描结果缓存。")
        else:
            # 转换为 DataFrame 展示
            display_data = []
            for r in ticker_res:
                signals = r.get("signals", [])
                signal_str = "、".join(signals) if isinstance(signals, list) else str(signals)
                if not signal_str:
                    signal_str = "无信号/观望"
                    
                display_data.append({
                    "周期": r.get("timeframe", ""),
                    "最新价格": f"{r.get('current', 0.0):,.4f}" if r.get("current") is not None else "—",
                    "黄金区下沿": f"{r.get('zone_bot', 0.0):,.4f}" if r.get("zone_bot") is not None else "—",
                    "黄金区上沿": f"{r.get('zone_top', 0.0):,.4f}" if r.get("zone_top") is not None else "—",
                    "回撤幅度": f"{r.get('retrace_pct', 0.0):.1f}%" if r.get("retrace_pct") is not None else "—",
                    "当前触发信号": signal_str,
                    "计算时间": r.get("time", "")
                })
                
            res_df = pd.DataFrame(display_data)
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            
    st.divider()
    if st.button("⬅️ 返回行情扫描主页"):
        st.query_params["_page"] = "scanner"
        st.rerun()
