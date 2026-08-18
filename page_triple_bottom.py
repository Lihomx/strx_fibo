"""
page_triple_bottom.py — 三重底多周期扫描页面
=========================================
实现思路：
  - 新增独立页面展现，避免对原有实时扫描页造成性能卡顿
  - 支持多周期切换：30分钟、1小时、4小时、日线
  - 支持对自选股、热门品种或指定股票进行多周期即时扫描
  - 提供形态子类型分类过滤 (7种 Al Brooks 三重底变体)
  - 集成 Plotly 交互 K 线图，在图表上以标记点 (Scatter) 突出展示 3 个低点、支撑线与形态特征
  - 一键同步/添加到自选收藏夹，并自动附带 "TripleBottom" 与具体形态标签
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime
import plotly.graph_objects as go

import storage
import bg_scan_manager
from streamlit_autorefresh import st_autorefresh
from scanner import fetch_data
from triple_bottom_scanner import scan_triple_bottoms, PatternMatch

# ── 支持的时间框架配置 ──
TRIPLE_BOTTOM_TIMEFRAMES = {
    "30m": ("30m", "60d", "30分钟"),
    "60m": ("60m", "720d", "1小时"),
    "4h":  ("4h",  "2y",   "4小时"),
    "1d":  ("1d",  "2y",   "日线"),
    "1w":  ("1wk", "5y",   "周线"),
    "1mo": ("1mo", "10y",  "月线"),
}

# ── TradingView 周期映射（period key → TV interval 参数） ──
_TB_TV_INTERVAL = {
    "30m": "30",
    "60m": "60",
    "4h":  "240",
    "1d":  "D",
    "1w":  "W",
    "1mo": "M",
}

def _tv_link(ticker: str, period: str = "1d") -> str:
    """生成带周期参数的 TradingView CN 链接"""
    try:
        from assets import tv_symbol
        sym = tv_symbol(ticker)
    except Exception:
        sym = ticker
    interval = _TB_TV_INTERVAL.get(period, "D")
    return f"https://cn.tradingview.com/chart/?symbol={sym}&interval={interval}"


def _render_tb_restore_session_controls():
    try:
        import cloud_sync
        if cloud_sync.is_configured():
            cloud_sync.pull_tb_snapshots()
    except Exception:
        pass
    sessions = storage.load_tb_snapshots()
    options = []
    sid_map = {}
    for s in sessions:
        sid = str(s.get("session_id", "")).strip()
        scan_time = s.get("scan_time") or "—"
        count = s.get("count", 0)
        label = f"{scan_time} | 数量 {count} | {sid[:15]}…"
        options.append(label)
        sid_map[label] = sid

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🗑️ 清空扫描结果", key="tb_clear_results_btn", help="清空当前所有扫描结果，清空前会自动备份快照", use_container_width=True):
            storage.clear_triple_bottom_results()
            storage.clear_tb_batch_state()
            st.success("已成功清空当前扫描结果（已自动备份）")
            time.sleep(1)
            st.rerun()


    with col2:
        if not options:
            st.selectbox(
                "恢复批次",
                ["暂无可恢复批次（无快照）"],
                key="tb_restore_session_picker_empty",
                disabled=True,
                label_visibility="collapsed",
            )
            st.button(
                "♻️ 恢复所选批次",
                key="tb_restore_selected_scan_btn_disabled",
                disabled=True,
                use_container_width=True,
            )
        else:
            sub_col1, sub_col2 = st.columns([2, 1])
            with sub_col1:
                selected_label = st.selectbox(
                    "恢复批次",
                    options,
                    key="tb_restore_session_picker",
                    label_visibility="collapsed",
                )
            with sub_col2:
                sid = sid_map.get(selected_label, "")
                if st.button(
                    "♻️ 恢复所选批次",
                    key="tb_restore_selected_scan_btn",
                    help="恢复你当前选择的三重底扫描批次快照",
                    type="secondary",
                    use_container_width=True,
                    disabled=not sid,
                ):
                    ok, msg, n = storage.restore_tb_snapshot(sid)
                    if ok:
                        st.toast(f"已恢复批次 {sid[:12]}…（{n} 条）", icon="♻️")
                        time.sleep(1)
                        st.rerun()
                    st.error(msg)


def _row_anchor_id(ticker: str, period: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", f"{ticker}_{period}".upper())
    return f"tb_row_{safe}"

def _fetch_name(ticker: str) -> str:
    """复用 Watchlist 的公司名获取逻辑，带 session_state 缓存"""
    cache = st.session_state.setdefault("_yfname_cache", {})
    key = ticker.upper().strip()
    if key in cache:
        return cache[key]
    
    # 简单新浪/yfinance查名
    name = key
    if key.isdigit() and len(key) == 6:
        # A股
        try:
            import requests
            prefix = "sh" if key.startswith("6") or key.startswith("5") else "sz"
            r = requests.get(f"https://hq.sinajs.cn/list={prefix}{key}", headers={"Referer": "https://finance.sina.com.cn"}, timeout=3)
            r.encoding = "gbk"
            text = r.text
            start = text.find('"')
            end = text.rfind('"')
            if start != -1 and end > start:
                fields = text[start+1:end].split(",")
                if fields and fields[0]:
                    name = fields[0]
        except Exception:
            pass
    cache[key] = name
    return name

import gc

def _check_memory_guard() -> tuple[bool, float]:
    """
    检查系统内存使用率。
    如果超过 85%，先触发强制垃圾回收并休眠等待；如果仍超过 90% 返回 False。
    返回 (is_safe, mem_percent)
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        if mem.percent > 85.0:
            gc.collect()
            time.sleep(2.0)
            mem = psutil.virtual_memory()
            if mem.percent > 90.0:
                return False, mem.percent
        return True, mem.percent
    except Exception:
        return True, 0.0


def triple_bottom_batch_worker(params, update_progress, cancel_check):
    """
    分批执行三重底扫描（每次只执行 50 只股票），彻底释放内存，防止 Streamlit Cloud 内存超标。
    """
    batch_tickers = params["batch_tickers"]
    batch_index = params.get("batch_index", 1)
    total_batches = params.get("total_batches", 1)
    selected_periods = params["selected_periods"]
    swing_win = params["swing_win"]
    lookback = params["lookback"]
    max_sp = params["max_sp"]
    min_conf = params["min_conf"]
    flat_tol = params.get("flat_tol", 0.02)
    break_tol = params.get("break_tol", 0.01)
    
    total_steps = len(batch_tickers) * len(selected_periods)
    step = 0
    batch_results = []
    
    start_time = time.time()
    ticker_count = 0
    
    for ticker in batch_tickers:
        if cancel_check():
            break
            
        ticker_count += 1
        
        # 内存安全守卫
        safe_mem, mem_pct = _check_memory_guard()
        if not safe_mem:
            update_progress(step, total_steps, f"[第{batch_index}/{total_batches}批] ⚠️ 内存缓冲降载({mem_pct:.1f}%)...")
            gc.collect()
            time.sleep(3.0)

        for period_key in selected_periods:
            if cancel_check():
                break
            step += 1
            interval, yf_period, period_desc = TRIPLE_BOTTOM_TIMEFRAMES[period_key]
            
            # 计算剩余时间
            elapsed = time.time() - start_time
            if ticker_count > 1 and step > 0:
                avg_time = elapsed / ticker_count
                rem_sec = int((len(batch_tickers) - ticker_count) * avg_time)
                eta_str = f" | 本批预计剩余 {rem_sec // 60}分{rem_sec % 60}秒" if rem_sec > 0 else ""
            else:
                eta_str = ""
                
            update_progress(
                step, 
                total_steps, 
                f"[第{batch_index}/{total_batches}批] {ticker} ({period_desc}) [{step}/{total_steps}]{eta_str}"
            )
            
            df = None
            try:
                df = fetch_data(ticker, interval=interval, period=yf_period)
                if df is not None and not df.empty:
                    # ✂️ 列裁剪，仅提取计算必需列
                    needed_cols = [c for c in ("close", "high", "low", "volume") if c in df.columns]
                    if len(needed_cols) >= 3:
                        df = df[needed_cols].copy()
                        
                    matches = scan_triple_bottoms(
                        df,
                        symbol=ticker,
                        swing_window=int(swing_win),
                        lookback_bars=int(lookback),
                        max_spacing=int(max_sp),
                        flat_tol=flat_tol,
                        break_tol=break_tol,
                    )
                    for m in matches:
                        if m.confidence >= min_conf:
                            batch_results.append({
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
            finally:
                if df is not None:
                    del df
                    df = None
            
            # 频控休眠
            time.sleep(0.4)
            
        # 单只股票完成立即回收
        gc.collect()
        
    # 增量合并保存本批次扫描结果
    if batch_results:
        storage.append_triple_bottom_results(batch_results, with_backup=True)
        
    # 更新持久化分批扫描状态
    try:
        bstate = storage.load_tb_batch_state()
        all_tickers = bstate.get("all_tickers", [])
        total_tickers = len(all_tickers) if all_tickers else bstate.get("total_tickers", 0)
        batch_size = bstate.get("batch_size", 50)
        calc_total_batches = (total_tickers + batch_size - 1) // batch_size if total_tickers > 0 else total_batches
        
        done_set = set(bstate.get("done_tickers", []))
        done_set.update(batch_tickers)
        bstate["done_tickers"] = list(done_set)
        bstate["current_batch"] = batch_index
        bstate["total_tickers"] = total_tickers
        bstate["total_batches"] = calc_total_batches
        bstate["last_batch_match_count"] = len(batch_results)
        bstate["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if cancel_check():
            bstate["status"] = "cancelled"
        elif calc_total_batches > 0 and batch_index >= calc_total_batches:
            bstate["status"] = "all_done"
        elif total_tickers > 0 and len(bstate["done_tickers"]) >= total_tickers:
            bstate["status"] = "all_done"
        else:
            bstate["status"] = "batch_done"
            
        storage.save_tb_batch_state(bstate)
    except Exception:
        pass

        
    # 🚀 关键：每批完成立即同步推送到 Supabase 云端，防止应用休眠丢失数据
    try:
        import cloud_sync
        if cloud_sync.is_configured():
            if batch_results:
                cloud_sync.push_triple_bottom()
            cloud_sync.push_tb_batch_state()
    except Exception:
        pass

    gc.collect()





def _start_new_tb_batch_scan(tickers: list[str], selected_periods: list[str], scan_params: dict, auto_continue: bool) -> tuple[bool, str]:
    """初始化并启动全新分批扫描任务"""
    BATCH_SIZE = 50
    total_tickers = len(tickers)
    total_batches = (total_tickers + BATCH_SIZE - 1) // BATCH_SIZE
    
    bstate = {
        "all_tickers": tickers,
        "total_tickers": total_tickers,
        "selected_periods": selected_periods,
        "batch_size": BATCH_SIZE,
        "current_batch": 0,
        "total_batches": total_batches,
        "done_tickers": [],
        "scan_params": scan_params,
        "auto_continue": auto_continue,
        "status": "in_progress",
        "last_batch_match_count": 0,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    storage.save_tb_batch_state(bstate)
    return _trigger_tb_batch(bstate, 1)


def _trigger_tb_batch(bstate: dict, batch_idx: int) -> tuple[bool, str]:
    """触发指定批次的后台扫描"""
    batch_size = bstate.get("batch_size", 50)
    all_tickers = bstate.get("all_tickers", [])
    
    # 容错保障：若 all_tickers 为空（从云端瘦身拉取），尝试根据已配置的分组自动重建
    if not all_tickers:
        selected_grp = bstate.get("scan_params", {}).get("selected_group")
        if selected_grp:
            all_groups = storage.load_symbol_groups()
            for g in all_groups:
                if g.get("name") == selected_grp:
                    all_tickers = g.get("tickers", [])
                    bstate["all_tickers"] = all_tickers
                    break
        if not all_tickers:
            all_tickers = storage.load_symbols_list()
            bstate["all_tickers"] = all_tickers
            
    total_tickers = len(all_tickers)
    total_batches = (total_tickers + batch_size - 1) // batch_size if total_tickers > 0 else bstate.get("total_batches", 1)
    bstate["total_batches"] = total_batches
    bstate["total_tickers"] = total_tickers
    
    start_i = (batch_idx - 1) * batch_size
    end_i = min(start_i + batch_size, len(all_tickers))
    batch_tickers = all_tickers[start_i:end_i]
    
    if not batch_tickers:
        bstate["status"] = "all_done"
        storage.save_tb_batch_state(bstate)
        return False, "所有批次已扫描完毕"

        
    scan_params = bstate.get("scan_params", {})
    selected_periods = bstate.get("selected_periods", ["1d", "1w", "1mo"])
    
    params = {
        "batch_tickers": batch_tickers,
        "batch_index": batch_idx,
        "total_batches": total_batches,
        "selected_periods": selected_periods,
        "swing_win": scan_params.get("swing_win", 3),
        "lookback": scan_params.get("lookback", 150),
        "max_sp": scan_params.get("max_sp", 80),
        "min_conf": scan_params.get("min_conf", 0.5),
        "flat_tol": scan_params.get("flat_tol", 0.02),
        "break_tol": scan_params.get("break_tol", 0.01),
    }
    
    bstate["status"] = "in_progress"
    storage.save_tb_batch_state(bstate)
    
    label = f"三重底分批扫描 [第 {batch_idx}/{total_batches} 批]"
    return bg_scan_manager.submit_job(
        job_type="triple_bottom",
        label=label,
        params=params,
        worker_fn=triple_bottom_batch_worker
    )


def render_triple_bottom_page():
    # ── 数据初始化与安全保障 ──
    results = storage.load_triple_bottom() or []
    
    # ── 状态轮询与分批流水线自动推进 ──
    bg_status = bg_scan_manager.get_status()
    bstate = storage.load_tb_batch_state()
    is_running = (bg_status["status"] == "running")

    
    # 自动流水线推进检测
    if not is_running and bstate.get("status") == "batch_done":
        cur_b = bstate.get("current_batch", 0)

        tot_b = bstate.get("total_batches", 1)
        if cur_b < tot_b and bstate.get("auto_continue", True):
            st_autorefresh(interval=2500, key="tb_batch_auto_advance")
            st.info(f"⚡ **自动流水线运行中**：第 {cur_b}/{tot_b} 批已完成，已释放内存，正在自动启动第 {cur_b + 1} 批...")
            time.sleep(1.0)
            ok, msg = _trigger_tb_batch(bstate, cur_b + 1)
            if ok:
                st.rerun()

    if is_running and bg_status.get("job_type") == "triple_bottom":
        st_autorefresh(interval=3000, key="triple_bottom_auto_refresh")
        st.info(f"🔄 **后台扫描正在进行中**: **{bg_status['job_label']}**")
        st.progress(bg_status["progress"])
        st.caption(f"当前进度: {bg_status['current']} ({bg_status['done_count']}/{bg_status['total_count']})")
        st.caption("💡 每次仅扫描 50 只股票并即时释放内存，绝不超限。您可以安全关闭页面或切换标签。")
        if st.button("⏹ 取消当前批次扫描", key="tb_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif bstate.get("status") in ("batch_done", "all_done", "in_progress") and not is_running:
        cur_b = bstate.get("current_batch", 0)
        tot_b = bstate.get("total_batches", 1)
        done_cnt = len(bstate.get("done_tickers", []))
        all_tks = bstate.get("all_tickers", [])
        total_cnt = len(all_tks) if all_tks else bstate.get("total_tickers", 0)
        last_match = bstate.get("last_batch_match_count", 0)
        
        if bstate.get("status") == "all_done" or (tot_b > 0 and cur_b >= tot_b):
            st.success(f"🎊 **全部分批扫描已全部完成！** 共扫描完成 {done_cnt}/{total_cnt} 只品种，结果已全部增量保存。")
            if st.button("🔄 完成并重置分批状态", key="tb_all_done_reset_btn", type="primary"):
                storage.clear_tb_batch_state()
                bg_scan_manager.reset_to_idle()
                st.rerun()

        elif bstate.get("status") == "batch_done":
            st.markdown(
                f"""
                <div style="background:rgba(34, 197, 94, 0.12); border:1px solid rgba(34, 197, 94, 0.3); border-radius:10px; padding:16px; margin-bottom:15px;">
                    <div style="font-weight:700; color:#4ade80; font-size:16px; margin-bottom:6px;">
                        ✅ 第 {cur_b} 批 / 共 {tot_b} 批已扫描完毕！(本批新发现 {last_match} 个形态)
                    </div>
                    <div style="color:#cbd5e1; font-size:13px; margin-bottom:10px;">
                        已完成 <b>{done_cnt}</b> 只 / 总计 <b>{total_cnt}</b> 只品种。当前批次内存已彻底释放归还系统。
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1:
                next_batch_btn = st.button(
                    f"▶️ 立即开始扫描第 {cur_b + 1} 批 (下 50 只)", 
                    key="tb_manual_next_batch_btn", 
                    type="primary", 
                    use_container_width=True
                )
                if next_batch_btn:
                    ok, msg = _trigger_tb_batch(bstate, cur_b + 1)
                    if ok:
                        st.success(f"第 {cur_b + 1} 批已启动！")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
            with col_b2:
                if st.button("⏹ 结束本次分批任务", key="tb_stop_batch_btn", use_container_width=True):
                    bstate["status"] = "all_done"
                    storage.save_tb_batch_state(bstate)
                    bg_scan_manager.reset_to_idle()
                    st.rerun()

    # ── 0. 全局视觉样式注入 ──
    st.markdown(
        """
        <style>
        /* Hero Banner Container */
        .tb-hero-banner {
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.8) 100%);
            border: 1px solid rgba(245, 158, 11, 0.25);
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }
        .tb-hero-title {
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 50%, #d97706 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0 0 6px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .tb-hero-sub {
            font-size: 13px;
            color: #94a3b8;
            margin: 0;
            max-width: 650px;
            line-height: 1.5;
        }
        .tb-stat-box {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 8px 16px;
            text-align: center;
            min-width: 100px;
        }
        .tb-stat-val {
            font-size: 20px;
            font-weight: 700;
            color: #f59e0b;
            font-family: 'JetBrains Mono', monospace, sans-serif;
        }
        .tb-stat-lbl {
            font-size: 11px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        /* 空状态玻璃图层 */
        .tb-empty-card {
            background: rgba(15, 23, 42, 0.4);
            border: 1px dashed rgba(245, 158, 11, 0.3);
            border-radius: 12px;
            padding: 45px 20px;
            text-align: center;
            margin: 20px 0;
        }
        .tb-empty-icon {
            font-size: 48px;
            margin-bottom: 12px;
            display: inline-block;
            filter: drop-shadow(0 0 10px rgba(245, 158, 11, 0.4));
        }
        .tb-empty-title {
            font-size: 16px;
            font-weight: 600;
            color: #e2e8f0;
            margin-bottom: 8px;
        }
        .tb-empty-desc {
            font-size: 13px;
            color: #64748b;
            max-width: 450px;
            margin: 0 auto;
        }
        /* 数据行对比度盒子 */
        .tb-metrics-row {
            display: flex;
            gap: 12px;
            margin-top: 10px;
            margin-bottom: 6px;
            flex-wrap: wrap;
        }
        .tb-metric-chip {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            color: #cbd5e1;
            flex: 1;
            min-width: 120px;
        }
        .tb-metric-chip b {
            color: #f59e0b;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ── 1. 顶部 Hero Banner 与数据加载 ──
    all_patterns = storage.load_triple_bottom()
    if not isinstance(all_patterns, list):
        all_patterns = []
    active_count = sum(1 for r in all_patterns if r.get("status") == "active")
    confirmed_count = sum(1 for r in all_patterns if r.get("status") == "confirmed")
    latest_time = all_patterns[0].get("scan_time", "无记录")[:16] if all_patterns else "暂未扫描"

    st.markdown(
        f"""
        <div class="tb-hero-banner">
            <div>
                <div class="tb-hero-title">
                    <span>📐 三重底多周期智能扫描</span>
                </div>
                <div class="tb-hero-sub">
                    基于 Al Brooks 价格行为学模型，自动定位支撑带附近的三次下探尝试。支持每批 50 只流水线安全分批扫描，彻底解决云端内存限制。
                </div>
            </div>
            <div style="display:flex; gap:12px;">
                <div class="tb-stat-box">
                    <div class="tb-stat-val">{len(all_patterns)}</div>
                    <div class="tb-stat-lbl">累计形态</div>
                </div>
                <div class="tb-stat-box">
                    <div class="tb-stat-val" style="color:#38bdf8;">{active_count}</div>
                    <div class="tb-stat-lbl">观望中</div>
                </div>
                <div class="tb-stat-box">
                    <div class="tb-stat-val" style="color:#4ade80;">{confirmed_count}</div>
                    <div class="tb-stat-lbl">已突破</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── 恢复/清空扫描结果控件 ──
    _render_tb_restore_session_controls()
    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # ── 🌐 Google Colab 独立大规模扫描渠道 ──
    with st.expander("☁️ Google Colab 算力扫描渠道 (全美股 / 全A股 极速扫描与结果导入)", expanded=True):
        colab_c1, colab_c2 = st.columns([1.2, 1], gap="medium")
        with colab_c1:
            st.markdown("##### 1. 选择股票池并获取专属 Colab 脚本")
            st.caption("利用 Google Colab 免费高性能算力扫描数百上千只全市场股票，完全不受 Streamlit Cloud 内存配额限制。")
            
            # 从系统已有品种库与分组中提取
            groups = storage.load_symbol_groups() or []
            all_symbols = storage.load_symbols() or []
            
            pool_options = ["🇺🇸 全量美股 (系统内置)", "🇨🇳 全量A股 (系统内置)"]
            grp_name_list = [g["name"] for g in groups if g.get("name")]
            for gn in grp_name_list:
                if gn not in pool_options:
                    pool_options.append(f"📁 分组: {gn}")
            pool_options.append("⭐ 我的自选关注列表")
            
            selected_pool = st.selectbox(
                "选择需要导出的扫描股票池",
                options=pool_options,
                index=0,
                key="tb_colab_selected_pool",
                help="系统会自动将选定股票池中的所有股票代码注入到 Colab 脚本中，无需在 Colab 中重复拉取"
            )
            
            # 提取对应股票代码
            export_tickers = []
            if "全量美股" in selected_pool:
                # 寻找美股分组或过滤美股
                us_grp = next((g for g in groups if "全量美股" in g.get("name", "")), None)
                if us_grp and us_grp.get("tickers"):
                    export_tickers = us_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if not s["ticker"].endswith(".SS") and not s["ticker"].endswith(".SZ") and not s["ticker"].endswith(".BJ") and not s["ticker"].isdigit()]
            elif "全量A股" in selected_pool:
                a_grp = next((g for g in groups if "全量A股" in g.get("name", "")), None)
                if a_grp and a_grp.get("tickers"):
                    export_tickers = a_grp["tickers"]
                else:
                    export_tickers = [s["ticker"] for s in all_symbols if s["ticker"].endswith(".SS") or s["ticker"].endswith(".SZ") or s["ticker"].endswith(".BJ") or s["ticker"].isdigit()]
            elif "自选关注" in selected_pool:
                wl = storage.load_watchlist() or []
                export_tickers = [w["ticker"] for w in wl if w.get("ticker")]
            elif selected_pool.startswith("📁 分组:"):
                g_target_name = selected_pool.replace("📁 分组: ", "").strip()
                target_g = next((g for g in groups if g.get("name") == g_target_name), None)
                if target_g:
                    export_tickers = target_g.get("tickers", [])
                    
            if not export_tickers:
                # 兜底：如果为空，取所有 symbols
                export_tickers = [s["ticker"] for s in all_symbols[:500]] if all_symbols else ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]
                
            export_tickers = list(dict.fromkeys([t.strip().upper() for t in export_tickers if t and isinstance(t, str)]))
            
            st.info(f"📋 当前选定股票池包含 **{len(export_tickers)}** 支品种代码，已直接内置写入以下脚本：")
            
            import colab_scan_script
            colab_code = colab_scan_script.generate_colab_script_for_tickers(export_tickers, pool_name=selected_pool)
            st.code(colab_code, language="python", line_numbers=True)
            st.markdown(
                """
                <div style="font-size:12px;color:#94a3b8;margin-top:-6px;margin-bottom:10px;">
                    👉 <b>操作指引：</b> 点击代码框右上角<b>复制</b> ➔ 打开 <a href="https://colab.research.google.com/" target="_blank" style="color:#38bdf8;text-decoration:underline;">Google Colab</a> 新建笔记本粘贴并运行 ➔ 运行完毕将自动下载 <code>colab_triple_bottom_results.csv</code>。
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with colab_c2:
            st.markdown("##### 2. 导入 Colab 扫描结果 CSV")
            st.caption("上传从 Google Colab 导出的扫描结果 CSV 文件，系统将自动进行格式校验并增量合并到当前三重底结果库中。")
            uploaded_file = st.file_uploader(
                "选择或拖拽 Colab 导出的 CSV 文件",
                type=["csv"],
                key="tb_colab_csv_uploader",
                help="支持导入 colab_triple_bottom_results_*.csv"
            )
            
            if uploaded_file is not None:
                try:
                    import io
                    import csv
                    df_up = pd.read_csv(uploaded_file)
                    
                    # 字段校验
                    required_fields = ["symbol", "period", "pattern", "confidence", "idx1", "idx2", "idx3", "low1", "low2", "low3", "mid_high"]
                    missing = [f for f in required_fields if f not in df_up.columns]
                    
                    if missing:
                        st.error(f"❌ CSV 文件格式不符合要求，缺少关键列: {', '.join(missing)}")
                    else:
                        valid_items = []
                        for _, r in df_up.iterrows():
                            sym = str(r.get("symbol", "")).strip().upper()
                            if not sym:
                                continue
                            item = {
                                "symbol": sym,
                                "period": str(r.get("period", "1d")).strip().lower(),
                                "pattern": str(r.get("pattern", "三重底")).strip(),
                                "confidence": float(r.get("confidence", 0.7)),
                                "idx1": int(r.get("idx1", 0)),
                                "idx2": int(r.get("idx2", 0)),
                                "idx3": int(r.get("idx3", 0)),
                                "low1": float(r.get("low1", 0.0)),
                                "low2": float(r.get("low2", 0.0)),
                                "low3": float(r.get("low3", 0.0)),
                                "mid_high": float(r.get("mid_high", 0.0)),
                                "note": str(r.get("note", "")),
                                "status": str(r.get("status", "active")),
                                "status_reason": str(r.get("status_reason", "")),
                                "bars_since_low3": int(r.get("bars_since_low3", 0)),
                                "latest_close": float(r.get("latest_close", 0.0)),
                                "scan_time": str(r.get("scan_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            }
                            valid_items.append(item)
                            
                        st.markdown(f"📊 **检测到有效形态记录**: `{len(valid_items)}` 条")
                        if st.button("📥 确认增量导入并合并", key="tb_colab_confirm_import_btn", type="primary", use_container_width=True):
                            ok = storage.append_triple_bottom_results(valid_items, with_backup=True)
                            if ok:
                                try:
                                    import cloud_sync
                                    if cloud_sync.is_configured():
                                        cloud_sync.push_triple_bottom()
                                except Exception:
                                    pass
                                st.toast(f"✅ 成功导入 {len(valid_items)} 条来自 Google Colab 的扫描结果！", icon="🎉")
                                time.sleep(1.0)
                                st.rerun()
                            else:
                                st.error("❌ 写入存储失败，请重试。")
                except Exception as ex:
                    st.error(f"❌ 解析 CSV 文件失败: {ex}")

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # ── 2. 顶部控制面板（扫描配置与控制） ──
    with st.expander("⚙️ 扫描参数与分批目标配置", expanded=True):
        col_cfg1, col_cfg2 = st.columns([3, 2], gap="large")
        
        with col_cfg1:
            st.markdown("#### ⚙️ 扫描参数配置")
            c1, c2 = st.columns(2)
            with c1:
                selected_periods = st.multiselect(
                    "选择扫描周期",
                    options=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
                    default=["1d", "1w", "1mo"],
                    format_func=lambda x: TRIPLE_BOTTOM_TIMEFRAMES[x][2]
                )
                min_conf = st.slider("置信度阈值", 0.3, 1.0, 0.5, 0.05,
                    help="置信度越低，筛选越宽松。建议先用 0.4~0.5 试扫")
                swing_win = st.number_input("分形阶数 (Window)", 2, 10, 3,
                    help="左右各看几根K线来确认局部低点，越小越灵敏")
            
            with c2:
                max_sp = st.number_input("三点最大跨度 (K线数)", 20, 200, 80,
                    help="三个探底低点最大允许间隔，越大形态跨度越长")
                lookback = st.number_input("扫描回溯长度 (Bars)", 50, 500, 150,
                    help="向前看多少根K线内的数据")
                
                with st.popover("📐 形态宽松度设置"):
                    flat_tol_pct = st.slider("低点容差 (%)", 0.5, 10.0, 2.0, 0.5,
                        help="三个低点之间允许的最大百分比差异。越大越容易匹配，建议 1.5~3%")
                    break_tol_pct = st.slider("跌破容差 (%)", 0.2, 5.0, 1.0, 0.2,
                        help="失败突破型：允许价格跌破支撑多少百分比后被视为'失败突破'")
            
            flat_tol = flat_tol_pct / 100.0
            break_tol = break_tol_pct / 100.0

        with col_cfg2:
            st.markdown("#### ⚡ 扫描目标与分批控制")
            scan_target = st.radio("扫描目标", ["品种库分组", "指定代码"], horizontal=True)

            custom_ticker_input = ""
            selected_grp_names = []
            if scan_target == "指定代码":
                custom_ticker_input = st.text_input("输入代码 (多个用逗号隔开)", "AAPL,BTC-USD,000001.SS")
            elif scan_target == "品种库分组":
                groups = storage.load_symbol_groups()
                if not groups:
                    st.warning("⚠️ 暂无分组，请前往 品种库 页面创建。")
                else:
                    ALL_GROUPS_LABEL = "🔥 全部品种组 (一键合并)"
                    group_options = [ALL_GROUPS_LABEL] + [g["name"] for g in groups]
                    selected_grp_names = st.multiselect(
                        "选择分组 (可多选/一键全选)",
                        options=group_options,
                        default=[ALL_GROUPS_LABEL],
                        help="可以多选多个品种组，也可以选择全选合并扫描"
                    )

            auto_continue_flag = st.checkbox(
                "⚡ 自动连续扫描下一批 (流水线全自动模式)", 
                value=bstate.get("auto_continue", True),
                help="开启后，每完成 50 只自动休息冷却并开始下一批，无需手动点击"
            )


            st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
            
            start_scan_clicked = st.button(
                "🚀 开始分批安全扫描 (每批50只)", 
                type="primary", 
                use_container_width=True, 
                disabled=is_running
            )

            if st.session_state.pop("_trigger_mobile_scan", False):
                start_scan_clicked = True

    # ── 3. 触发扫描执行 ──
    if start_scan_clicked:
        if not selected_periods:
            st.error("请至少选择一个扫描周期！")
            return

        tickers_to_scan = []
        if scan_target == "品种库分组":
            groups = storage.load_symbol_groups()
            tickers_set = set()
            if selected_grp_names:
                ALL_GROUPS_LABEL = "🔥 全部品种组 (一键合并)"
                if ALL_GROUPS_LABEL in selected_grp_names:
                    for g in groups:
                        tickers_set.update(g.get("tickers", []))
                else:
                    grp_map = {g["name"]: g for g in groups}
                    for g_name in selected_grp_names:
                        if g_name in grp_map:
                            tickers_set.update(grp_map[g_name].get("tickers", []))
            tickers_to_scan = [t.strip().upper() for t in tickers_set if t and isinstance(t, str)]
        else:
            tickers_to_scan = [t.strip().upper() for t in custom_ticker_input.split(",") if t.strip()]

        if not tickers_to_scan:
            st.warning("扫描队列为空，未找到任何代码。")
            return

        scan_params = {
            "swing_win": swing_win,
            "lookback": lookback,
            "max_sp": max_sp,
            "min_conf": min_conf,
            "flat_tol": flat_tol,
            "break_tol": break_tol,
        }

        ok, msg = _start_new_tb_batch_scan(
            tickers=tickers_to_scan,
            selected_periods=selected_periods,
            scan_params=scan_params,
            auto_continue=auto_continue_flag
        )
        if ok:
            st.success(f"分批扫描已成功启动！共 {len(tickers_to_scan)} 只品种，分为 {(len(tickers_to_scan) + 49) // 50} 批。")
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)


    # ── 4. 主界面形态展示与过滤 ──
    if not all_patterns:
        st.markdown(
            """
            <div class="tb-empty-card">
                <div class="tb-empty-icon">🔍</div>
                <div class="tb-empty-title">暂无三重底匹配形态</div>
                <div class="tb-empty-desc">
                    尚未运行扫描或在设定参数下未检出匹配形态。<br>
                    请在上方选择目标品种组与周期，然后点击「🚀 开始分析扫描」。
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    # 按置信度降序排列
    sorted_patterns = sorted(all_patterns, key=lambda x: x.get("confidence", 0.0), reverse=True)

    # 选项卡过滤：形态细分过滤
    pattern_types = [
        "全部",
        "完美三重底 (Perfect Triple Bottom)",
        "头肩底/截断楔形 (Head & Shoulders Bottom)",
        "双底跌破失败型 (Failed BO below DB)",
        "双底回调型 (Double Bottom Pullback)",
        "抬高双底失败突破型 (Failed BO below HL DB)",
        "楔形三重底 (Wedge)",
        "三角形三重底 (Triangle)",
        "未分类三次探底 (Unclassified 3-push)"
    ]

    col_f1, col_f2, col_f3 = st.columns([1.2, 1.2, 1.6])
    with col_f1:
        sel_patt = st.selectbox("筛选形态类别", pattern_types)
    with col_f2:
        st_period = st.multiselect(
            "筛选周期",
            options=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
            default=list(TRIPLE_BOTTOM_TIMEFRAMES.keys()),
            format_func=lambda x: TRIPLE_BOTTOM_TIMEFRAMES[x][2]
        )
    with col_f3:
        st_status = st.multiselect(
            "筛选有效状态",
            options=["观望中 (active)", "已突破 (confirmed)", "已失效 (invalidated)", "已过期 (expired)"],
            default=["观望中 (active)", "已突破 (confirmed)"],
            help="失效或过期的形态默认被隐藏，勾选即可恢复显示"
        )

    # 映射 status
    selected_statuses = []
    for s in st_status:
        if "active" in s:
            selected_statuses.append("active")
        elif "confirmed" in s:
            selected_statuses.append("confirmed")
        elif "invalidated" in s:
            selected_statuses.append("invalidated")
        elif "expired" in s:
            selected_statuses.append("expired")

    # 执行前端形态与周期、状态筛选
    filtered = []
    for r in sorted_patterns:
        if sel_patt != "全部" and sel_patt not in r.get("pattern", ""):
            continue
        if r.get("period") not in st_period:
            continue
        status_val = r.get("status", "active")
        if status_val not in selected_statuses:
            continue
        filtered.append(r)


    # ── 搜索、排序与分页配置 ──
    col_s1, col_s2, col_s3 = st.columns([2, 1.2, 1])
    with col_s1:
        search_query = st.text_input("🔍 搜索代码 / 名称", "", placeholder="输入股票代码或名称关键词过滤...", key="tb_search_query")
    with col_s2:
        sort_by = st.selectbox(
            "排序方式",
            ["置信度 (高 → 低)", "最新扫描时间 (新 → 旧)", "股票代码 (A → Z)"],
            index=0,
            key="tb_sort_by"
        )
    with col_s3:
        page_size = st.selectbox(
            "每页条数",
            [20, 50, 100],
            index=0,
            key="tb_page_size"
        )

    # 执行文本搜索过滤
    if search_query.strip():
        q = search_query.strip().upper()
        filtered = [
            r for r in filtered 
            if q in str(r.get("symbol", "")).upper() or q in _fetch_name(str(r.get("symbol", ""))).upper()
        ]

    # 执行排序
    if sort_by == "置信度 (高 → 低)":
        filtered.sort(key=lambda x: float(x.get("confidence", 0.0)), reverse=True)
    elif sort_by == "最新扫描时间 (新 → 旧)":
        filtered.sort(key=lambda x: str(x.get("scan_time", "")), reverse=True)
    elif sort_by == "股票代码 (A → Z)":
        filtered.sort(key=lambda x: str(x.get("symbol", "")).upper())

    total_items = len(filtered)
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    # 页码状态管理
    if "tb_current_page" not in st.session_state:
        st.session_state.tb_current_page = 1
    if st.session_state.tb_current_page > total_pages:
        st.session_state.tb_current_page = total_pages
    if st.session_state.tb_current_page < 1:
        st.session_state.tb_current_page = 1

    current_page = st.session_state.tb_current_page

    # 分页导航条（顶部）
    col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns([1, 1.2, 3, 1.2, 1])
    with col_p1:
        if st.button("⏮ 首页", disabled=(current_page == 1), key="tb_first_page_top", use_container_width=True):
            st.session_state.tb_current_page = 1
            st.rerun()
    with col_p2:
        if st.button("◀ 上一页", disabled=(current_page == 1), key="tb_prev_page_top", use_container_width=True):
            st.session_state.tb_current_page = max(1, current_page - 1)
            st.rerun()
    with col_p3:
        st.markdown(
            f"<div style='text-align:center; line-height:36px; color:#cbd5e1; font-size:14px; font-weight:600;'>"
            f"📄 第 <span style='color:#f59e0b;'>{current_page}</span> / {total_pages} 页 "
            f"(共 <span style='color:#38bdf8;'>{total_items}</span> 条，显示 {(current_page-1)*page_size + 1 if total_items > 0 else 0} - {min(current_page*page_size, total_items)} 条)"
            f"</div>",
            unsafe_allow_html=True
        )
    with col_p4:
        if st.button("下一页 ▶", disabled=(current_page == total_pages), key="tb_next_page_top", use_container_width=True):
            st.session_state.tb_current_page = min(total_pages, current_page + 1)
            st.rerun()
    with col_p5:
        if st.button("末页 ⏭", disabled=(current_page == total_pages), key="tb_last_page_top", use_container_width=True):
            st.session_state.tb_current_page = total_pages
            st.rerun()

    # 切片当前页数据
    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = filtered[start_idx:end_idx]

    # 准备共享数据提升循环渲染效率
    all_clicks_data = storage.get_all_link_clicks()
    wl = storage.load_watchlist()
    today_str_val = storage.get_today_str()

    # 循环渲染当前页切片结果卡片
    for i, r in enumerate(page_items):
        item_idx = start_idx + i

        ticker = r["symbol"]
        period = r["period"]
        patt_desc = r["pattern"]
        conf = r["confidence"]
        note = r["note"]
        status_val = r.get("status", "active")
        status_reason = r.get("status_reason", "")
        period_desc = TRIPLE_BOTTOM_TIMEFRAMES[period][2]
        name = _fetch_name(ticker)

        anchor = _row_anchor_id(ticker, period)
        st.markdown(f"<div id='{anchor}'></div>", unsafe_allow_html=True)

        # 构造状态徽章与颜色指示
        if status_val == "active":
            status_badge = "<span style='font-size:12px;background-color:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>观望中</span>"
        elif status_val == "confirmed":
            status_badge = "<span style='font-size:12px;background-color:rgba(34,197,94,0.15);color:#86efac;border:1px solid rgba(34,197,94,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>已突破 🚀</span>"
        elif status_val == "invalidated":
            status_badge = "<span style='font-size:12px;background-color:rgba(239,68,68,0.15);color:#fca5a5;border:1px solid rgba(239,68,68,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>已失效 ❌</span>"
        else: # expired
            status_badge = "<span style='font-size:12px;background-color:rgba(100,116,139,0.15);color:#94a3b8;border:1px solid rgba(100,116,139,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>已过期 ⏰</span>"

        with st.container(border=True):
            # 卡片标题栏与控制按钮
            col_t1, col_t2 = st.columns([5, 3])
            with col_t1:
                st.markdown(
                    f"<div style='margin-bottom:6px;'>"
                    f"<span style='font-size:18px;font-weight:800;color:#f8fafc;'>{ticker}</span> "
                    f"<span style='font-size:14px;color:#94a3b8;margin-right:8px;'>· {name}</span> "
                    f"<span style='font-size:12px;background-color:rgba(59,130,246,0.15);color:#93c5fd;border:1px solid rgba(59,130,246,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>{period_desc}</span> "
                    f"<span style='font-size:12px;background-color:rgba(245,158,11,0.15);color:#fde047;border:1px solid rgba(245,158,11,0.3);padding:2px 8px;border-radius:4px;font-weight:600;'>置信度: {conf:.0%}</span> "
                    f"{status_badge}"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with col_t2:
                # ── 按钮区：K线图 / TradingView / 收藏 ──
                chart_key = f"tb_chart_open_{ticker}_{period}"
                is_open = st.session_state.get(chart_key, False)

                btn_col1, btn_col2, btn_col3 = st.columns(3)
                
                with btn_col1:
                    if st.button("📊 K线图" if not is_open else "❌ 关闭图", key=f"tb_chart_btn_{item_idx}", use_container_width=True):
                        st.session_state[chart_key] = not is_open
                        st.rerun()

                with btn_col2:
                    click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
                    total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
                    by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
                    today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0

                    if total_c > 0:
                        click_badge_html = f' <span class="click-count-badge" style="font-size:11px;color:#4ade80;font-weight:600;">({today_c}/{total_c})</span>'
                    else:
                        click_badge_html = ' <span class="click-count-badge" style="font-size:11px;color:#64748b;font-weight:500;">(0/0)</span>'
                    tv_url_val = _tv_link(ticker, period)
                    st.markdown(
                        f'<a href="{tv_url_val}" target="_blank" class="tv-btn" data-ticker="{ticker}" '
                        f'style="display:block;text-align:center;padding:6px 0;background:rgba(30,144,255,0.15);'
                        f'color:#38bdf8;border-radius:4px;text-decoration:none;font-weight:600;font-size:13px;'
                        f'border:1px solid rgba(30,144,255,0.3);">📈 TV{click_badge_html}</a>',
                        unsafe_allow_html=True
                    )


                with btn_col3:
                    is_in_wl = any(item["ticker"].upper() == ticker.upper() for item in wl)
                    
                    if not is_in_wl:
                        if st.button("⭐ 收藏", key=f"tb_add_wl_{item_idx}", help="将该品种加入自选收藏夹，并标记 TripleBottom 标签", use_container_width=True):
                            ok = storage.add_to_watchlist(
                                ticker=ticker,
                                name=name,
                                note=f"三重底自动扫描导入：{patt_desc}"
                            )
                            if ok:
                                wl2 = storage.load_watchlist()
                                for wl_item in wl2:
                                    if wl_item["ticker"].upper() == ticker.upper():
                                        tags = wl_item.setdefault("tags", [])
                                        if "TripleBottom" not in tags:
                                            tags.append("TripleBottom")
                                        sub_patt = patt_desc.split(" (")[0]
                                        if sub_patt not in tags:
                                            tags.append(sub_patt)
                                        break
                                storage.save_watchlist(wl2)
                                st.toast(f"已成功添加 {ticker} 至自选收藏夹", icon="⭐")
                            else:
                                st.toast(f"添加失败（{ticker} 可能已在收藏夹中）", icon="⚠️")
                            st.rerun()
                    else:
                        if st.button("✅ 已加", key=f"tb_sync_tag_{item_idx}", help="该股票已在自选收藏夹中，点击为该股票追加 TripleBottom 与形态标签", use_container_width=True):
                            for item in wl:
                                if item["ticker"].upper() == ticker.upper():
                                    tags = item.setdefault("tags", [])
                                    added_any = False
                                    if "TripleBottom" not in tags:
                                        tags.append("TripleBottom")
                                        added_any = True
                                    sub_patt = patt_desc.split(" (")[0]
                                    if sub_patt not in tags:
                                        tags.append(sub_patt)
                                        added_any = True
                                    if added_any:
                                        item.setdefault("notes", []).append({
                                            "text": f"三重底自动扫描更新标签：{patt_desc}",
                                            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        })
                            storage.save_watchlist(wl)
                            st.toast(f"已成功为 {ticker} 追加三重底识别标签", icon="🏷️")
                            st.rerun()

            # 卡片结构化详情展示
            st.markdown(
                f"""
                <div style="font-size:13px; line-height:1.7; color:#cbd5e1; margin-top: 4px;">
                    <div>🏷️ <b>形态分类</b>：<span style="color:#f59e0b; font-weight:600;">{patt_desc}</span></div>
                    <div>🔍 <b>跟踪观察</b>：{status_reason if status_reason else '处于支撑位与突破颈线之间动态运行'}</div>
                    <div style="color:#94a3b8; font-size:12px; margin-top:2px;">📝 <b>特征说明</b>：{note}</div>
                </div>
                <div class="tb-metrics-row">
                    <div class="tb-metric-chip">探底① <b>Low1</b>: {r['low1']:.3f}</div>
                    <div class="tb-metric-chip">探底② <b>Low2</b>: {r['low2']:.3f}</div>
                    <div class="tb-metric-chip">探底③ <b>Low3</b>: {r['low3']:.3f}</div>
                    <div class="tb-metric-chip" style="border-color:rgba(245,158,11,0.2);">颈线高点 <b>MidHigh</b>: {r['mid_high']:.3f}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ── 展开 K 线图展示（核心高光） ──
            if st.session_state.get(chart_key):
                with st.container(border=True):
                    st.markdown(f"##### 📊 {ticker} - {period_desc} 蜡烛形态图")
                    with st.spinner("拉取数据并标绘形态中..."):
                        try:
                            interval, yf_period, _ = TRIPLE_BOTTOM_TIMEFRAMES[period]
                            df = fetch_data(ticker, interval=interval, period=yf_period)
                            if df is not None and not df.empty:
                                df_slice = df.tail(lookback).copy()
                                if isinstance(df_slice.columns, pd.MultiIndex):
                                    df_slice.columns = [c[0].lower() for c in df_slice.columns]
                                else:
                                    df_slice.columns = [c.lower() for c in df_slice.columns]
                                
                                df_slice = df_slice.reset_index()
                                date_col = df_slice.columns[0]
                                
                                fig = go.Figure()
                                fig.add_trace(go.Candlestick(
                                    x=df_slice[date_col],
                                    open=df_slice['open'],
                                    high=df_slice['high'],
                                    low=df_slice['low'],
                                    close=df_slice['close'],
                                    name='K线',
                                    increasing_line_color='#22c55e',
                                    decreasing_line_color='#ef4444'
                                ))

                                pts_idx = [p for p in pts_idx if 0 <= p < len(df_slice)]
                                
                                if len(pts_idx) == 3:
                                    dates = df_slice.loc[pts_idx, date_col]
                                    lows = df_slice.loc[pts_idx, 'low']
                                    
                                    fig.add_trace(go.Scatter(
                                        x=dates,
                                        y=lows,
                                        mode='markers+text',
                                        marker=dict(symbol='circle-open', size=15, color='#f59e0b', line=dict(width=3)),
                                        text=["Low1", "Low2", "Low3"],
                                        textposition="bottom center",
                                        textfont=dict(color="#f59e0b", size=12, family="Outfit, Inter"),
                                        name='探底支撑点'
                                    ))

                                    min_low = min(r["low1"], r["low2"])
                                    fig.add_hline(
                                        y=min_low,
                                        line_dash="dash",
                                        line_color="#d97706",
                                        annotation_text=f"支撑带: {min_low:.3f}",
                                        annotation_position="bottom right"
                                    )

                                fig.update_layout(
                                    xaxis_rangeslider_visible=False,
                                    height=320,
                                    margin=dict(l=10, r=10, t=20, b=10),
                                    template="plotly_dark",
                                    plot_bgcolor="rgba(0,0,0,0)"
                                )
                                st.plotly_chart(fig, use_container_width=True, key=f"tb_fig_{ticker}_{period}_{i}")
                            else:
                                st.warning("未找到足够长的历史 K 线数据，无法还原形态图。")
                        except Exception as ex:
                            st.error(f"渲染图形出错: {ex}")

    # ── 底部快捷翻页栏 ──
    if total_pages > 1:
        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        col_pb1, col_pb2, col_pb3, col_pb4, col_pb5 = st.columns([1, 1.2, 3, 1.2, 1])
        with col_pb1:
            if st.button("⏮ 首页", disabled=(current_page == 1), key="tb_first_page_bot", use_container_width=True):
                st.session_state.tb_current_page = 1
                st.rerun()
        with col_pb2:
            if st.button("◀ 上一页", disabled=(current_page == 1), key="tb_prev_page_bot", use_container_width=True):
                st.session_state.tb_current_page = max(1, current_page - 1)
                st.rerun()
        with col_pb3:
            st.markdown(
                f"<div style='text-align:center; line-height:36px; color:#cbd5e1; font-size:14px; font-weight:600;'>"
                f"📄 第 <span style='color:#f59e0b;'>{current_page}</span> / {total_pages} 页 "
                f"(共 <span style='color:#38bdf8;'>{total_items}</span> 条)"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_pb4:
            if st.button("下一页 ▶", disabled=(current_page == total_pages), key="tb_next_page_bot", use_container_width=True):
                st.session_state.tb_current_page = min(total_pages, current_page + 1)
                st.rerun()
        with col_pb5:
            if st.button("末页 ⏭", disabled=(current_page == total_pages), key="tb_last_page_bot", use_container_width=True):
                st.session_state.tb_current_page = total_pages
                st.rerun()

    # 💡 隐形事件监听组件：捕捉原链接点击，能在后台落盘计数，同时在前台秒级实时更新 (今日/总) 数字

    _js_code = r"""
    <script>
    (function() {
        try {
            var pDoc = window.parent.document;
            if (pDoc._tv_click_handler) {
                pDoc.removeEventListener('click', pDoc._tv_click_handler, true);
            }
            pDoc._tv_click_handler = function(e) {
                var btn = e.target.closest('.tv-btn, .sina-btn');
                if (btn) {
                    var tk = btn.getAttribute('data-ticker');
                    if (tk) {
                        tk = tk.trim().toUpperCase();
                        var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);

                        // 1. fetch 强制 no-store 穿透所有浏览器/CDN 缓存
                        try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}

                        // 2. sendBeacon 后台保障发送
                        try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}

                        // 3. IFrame 静音发送
                        try {
                            var f = pDoc.createElement('iframe');
                            f.style.display = 'none';
                            f.src = cbUrl;
                            pDoc.body.appendChild(f);
                            setTimeout(function() {
                                try { f.remove(); } catch(err) {}
                            }, 6000);
                        } catch(err) {}

                        // 4. 前台 DOM 瞬间更新该 ticker 所有对应按钮数值 (秒级反馈)
                        try {
                            var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');
                            for (var i = 0; i < allBtns.length; i++) {
                                var b = allBtns[i];
                                var bTk = b.getAttribute('data-ticker');
                                if (bTk && bTk.trim().toUpperCase() === tk) {
                                    var spans = b.getElementsByTagName('span');
                                    if (spans && spans.length > 0) {
                                        var span = spans[spans.length - 1];
                                        var txt = span.innerText || span.textContent || "";
                                        var m = txt.match(/\((\d+)\/(\d+)\)/);
                                        if (m) {
                                            var today = parseInt(m[1], 10) + 1;
                                            var total = parseInt(m[2], 10) + 1;
                                            span.innerText = '(' + today + '/' + total + ')';
                                            span.style.color = '#4ade80';
                                            span.style.fontWeight = '600';
                                        }
                                    }
                                }
                            }
                        } catch(err) {}
                    }
                }
            };
            pDoc.addEventListener('click', pDoc._tv_click_handler, true);
        } catch(err) {}
    })();
    </script>
    """
    if hasattr(st, "html"):
        st.html(_js_code)
    else:
        import streamlit.components.v1 as _components
        _components.html(_js_code, height=0)
