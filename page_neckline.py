"""
page_neckline.py — 4小时 (4H) 结构颈线突破扫描 (问财/量化选股)
========================================================================================
核心突破规则：
  [0] 颈线突破: 4H收盘价突破结构颈线 (箱体上沿 / 双底中峰 / 头肩底颈线)
  [1] 突破幅度: 突破幅度有效过滤假刺穿 (Close > 颈线 + 0.8×ATR 或 幅度>1%)
  [2] 增量放大: 4H成交量放大 (VOL > 1.3×MA5 或 前根1.5倍)
  [3] 异常天量过滤: 避免天量脉冲后衰竭 (VOL < 2.8×MA20)
  [4] 趋势共振: 4H均线多头共振排列 (MA5 ≥ MA10 ≥ MA20)
  [5] 站稳确认: 收盘价在颈线上方持续站稳 (过滤单针冲高回落)
  [6] 形态结构: 识别到有效底部/整理结构 (箱体 / 双底 / 头肩底)
"""

import time
import datetime
import streamlit as st
import pandas as pd
import numpy as np
import storage
import bg_scan_manager
from neckline_scanner import check_ticker_neckline, _YF_OK


def _safe_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        f = float(val)
        return default if np.isnan(f) else f
    except Exception:
        return default


# ════════════════════════════════════════════════════════════════════
# 辅助 UI 组件
# ════════════════════════════════════════════════════════════════════
def _stat_card(label: str, value: str, color: str = "blue") -> str:
    color_map = {
        "blue":  ("rgba(56,189,248,0.12)",  "#38bdf8", "rgba(56,189,248,0.3)"),
        "green": ("rgba(74,222,128,0.12)",  "#4ade80", "rgba(74,222,128,0.3)"),
        "red":   ("rgba(248,113,113,0.12)", "#f87171", "rgba(248,113,113,0.3)"),
        "gray":  ("rgba(148,163,184,0.08)", "#94a3b8", "rgba(148,163,184,0.2)"),
    }
    bg, fg, border = color_map.get(color, color_map["blue"])
    return f"""
    <div style="background:{bg};border:1px solid {border};border-radius:8px;
                padding:10px 14px;text-align:center;margin-bottom:8px;">
        <div style="font-size:11px;color:#94a3b8;margin-bottom:2px;">{label}</div>
        <div style="font-size:20px;font-weight:700;color:{fg};font-family:monospace;">{value}</div>
    </div>
    """


def _render_details(details: list):
    for r in details:
        ok = r.get("ok", False)
        icon = "✅" if ok else "❌"
        color = "#4ade80" if ok else "#f87171"
        bg = "rgba(74,222,128,0.07)" if ok else "rgba(248,113,113,0.07)"
        bd = "rgba(74,222,128,0.25)" if ok else "rgba(248,113,113,0.25)"
        cond_name = r.get('id', '')
        logic_desc = r.get('desc', '')
        purpose = r.get('purpose', '')
        val_str = r.get('val', '')
        st.markdown(
            f"""<div style="background:{bg};border:1px solid {bd};border-radius:6px;padding:8px 12px;margin:4px 0;font-size:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
                    <span style="font-weight:700;color:{color};">{icon} {cond_name} <span style="font-size:11px;color:#94a3b8;font-weight:normal;margin-left:6px;">({purpose})</span></span>
                    <span style="font-family:monospace;color:#f8fafc;font-size:12px;font-weight:600;">{val_str}</span>
                </div>
                <div style="font-family:monospace;color:#94a3b8;font-size:11px;">源码逻辑: {logic_desc}</div>
            </div>""",
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════════
# 后台扫描 Worker
# ════════════════════════════════════════════════════════════════════
def neckline_worker(params, update_progress, cancel_check):
    import gc
    tickers = params["tickers"]
    passed_list = []
    failed_list = []
    error_list = []
    
    total = len(tickers)
    for i, tk in enumerate(tickers):
        if cancel_check():
            break
            
        update_progress(i, total, f"扫描中 {i}/{total}: {tk}")
        
        try:
            res = check_ticker_neckline(tk)
            if res.get("error"):
                error_list.append(res)
            elif res.get("passed"):
                passed_list.append(res)
            else:
                failed_list.append(res)
        except Exception as e:
            error_list.append({"ticker": tk, "passed": False, "pattern": "—", "details": [], "error": str(e)})

        # 每 25 个品种增量保存一次
        if (i + 1) % 25 == 0 or (i + 1) == total:
            partial_results = {
                "passed": passed_list,
                "failed": failed_list,
                "errors": error_list,
                "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "done_count": i + 1,
            }
            storage.save_neckline(partial_results)
            
        if (i + 1) % 50 == 0:
            gc.collect()
            
        time.sleep(0.08)
        
    final_results = {
        "passed": passed_list,
        "failed": failed_list,
        "errors": error_list,
        "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "done_count": total if not cancel_check() else i + 1,
    }
    storage.save_neckline(final_results)
    try:
        storage.backup_neckline(final_results)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
# 页面主渲染入口
# ════════════════════════════════════════════════════════════════════
def render():
    render_page_neckline()


def render_page_neckline():
    st.markdown("## 📐 4H 结构颈线突破扫描 (问财/量化选股)")
    
    # ── 状态轮询与展示 ──
    status = bg_scan_manager.get_status()
    if status["status"] == "running":
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, key="neckline_scan_auto_refresh")
        except Exception:
            pass
        st.info(f"🔄 后台扫描正在进行中: **{status['job_label']}**")
        st.progress(status["progress"])
        st.caption(f"当前正在扫描: {status['current']} ({status['done_count']}/{status['total_count']})")
        st.caption("💡 扫描会在后台持续运行，您可以安全关闭此页面。结果将自动保存。")
        if st.button("⏹ 取消后台扫描", key="neckline_cancel_btn"):
            bg_scan_manager.request_cancel()
            st.warning("正在请求取消，请稍候...")
            st.rerun()
            
    elif status["status"] in ("done", "error", "cancelled") and status.get("job_type") == "neckline_scan":
        if status["status"] == "done":
            st.success("✅ 4H 结构颈线后台扫描任务已完成!")

    # ── 策略说明面板 ──
    with st.expander("📖 4H 结构颈线突破确认 6 条核心源码条件说明（问财 / 价格行为学模型）", expanded=False):
        st.markdown("""
        #### 💡 核心原则：突破颈线不能只看一根K线刺穿，必须通过多重严格条件确认！
        """)
        conditions = [
            ("价格突破", "CLOSE > NECKLINE 或 HIGH > NECKLINE", "判断价格是否跨过颈线"),
            ("突破幅度", "CLOSE > NECKLINE * 1.01 或 CLOSE > NECKLINE + 1.2 * ATR", "过滤盘中假刺穿"),
            ("成交量放大", "VOL > MA(VOL,5) * 1.3 或 VOL > REF(HHV(VOL,2),1)", "确认增量资金进场"),
            ("站稳天数", "连续3根四小时K线收盘价在颈线上方", "避免单日冲高回落"),
            ("均线趋势", "MA5 > MA10，MA10 > MA20", "确认趋势方向一致"),
            ("波动率过滤", "突破幅度 ≥ 1.2 * ATR(14)", "排除低波动假突破"),
        ]
        rows = [{"条件": c[0], "源码逻辑": c[1], "作用": c[2]} for c in conditions]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 载入分组品种 ──
    groups = storage.load_symbol_groups() or []
    all_symbols = storage.load_symbols() or []

    # 计算全部分组合并去重后的品种数
    all_group_tickers_raw = [t.strip().upper() for g in groups for t in g.get("tickers", []) if t and isinstance(t, str)]
    total_unique_in_groups = len(dict.fromkeys(all_group_tickers_raw)) if all_group_tickers_raw else 0

    def _on_neckline_group_change():
        sel = st.session_state.get("neckline_load_grp_sel")
        if sel and sel != "— 选择载入分组 —":
            grps = storage.load_symbol_groups() or []
            if "全部分组合并" in sel:
                all_tks = []
                for g in grps:
                    for tk in g.get("tickers", []):
                        if tk and isinstance(tk, str):
                            all_tks.append(tk.strip().upper())
                unique_tks = list(dict.fromkeys(all_tks))
                st.session_state["neckline_tickers"] = " ".join(unique_tks)
                st.toast(f"🌐 已合并载入全部分组共 {len(unique_tks)} 支品种 (自动去重)", icon="🌐")
            else:
                target = next((g for g in grps if g["name"] == sel), None)
                if target:
                    tickers = target.get("tickers", [])
                    st.session_state["neckline_tickers"] = " ".join(tickers)
            st.session_state["neckline_load_grp_sel"] = "— 选择载入分组 —"

    if groups:
        grp_names = ["— 选择载入分组 —", f"🌐 全部分组合并 ({len(groups)}个组·去重共 {total_unique_in_groups} 支)"] + [g["name"] for g in groups]
        if "neckline_load_grp_sel" not in st.session_state:
            st.session_state["neckline_load_grp_sel"] = "— 选择载入分组 —"
        st.selectbox(
            "📥 从品种库分组载入股票池",
            grp_names,
            key="neckline_load_grp_sel",
            on_change=_on_neckline_group_change,
        )

    # ── 股票池设置 ──────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 1])
    with col_left:
        if "neckline_tickers" not in st.session_state:
            syms = [s["ticker"] for s in storage.load_symbols()]
            if syms:
                st.session_state["neckline_tickers"] = " ".join(syms)
            else:
                st.session_state["neckline_tickers"] = "AAPL MSFT NVDA AMZN GOOGL TSLA 600519.SS 000858.SZ"
        ticker_input = st.text_area(
            "扫描股票池（空格或换行分隔，支持 yfinance 格式如 600519.SS / 9988.HK / AAPL）",
            height=100,
            key="neckline_tickers",
        )
    is_running = bg_scan_manager.is_running()
    with col_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        run_btn  = st.button("🚀 开始扫描", type="primary", use_container_width=True, key="neckline_run", disabled=is_running)
        if st.session_state.pop("_trigger_mobile_scan", False):
            run_btn = True
        clear_btn = st.button("🗑️ 清空结果", type="secondary", use_container_width=True, key="neckline_clear", disabled=is_running)

    if clear_btn:
        storage.clear_neckline_results()
        st.toast("🗑️ 已自动创建备份快照并成功清空！", icon="✅")
        time.sleep(0.5)
        st.rerun()

    # ── 🌐 Google Colab 独立大规模扫描渠道 ──
    with st.expander("☁️ Google Colab 算力扫描渠道 (全美股 / 全A股 / 全部分组合并 极速 4H 颈线突破扫描与结果导入)", expanded=False):
        colab_c1, colab_c2 = st.columns([1.2, 1], gap="medium")
        with colab_c1:
            st.markdown("##### 1. 选择股票池并获取专属 Colab 4H 扫描脚本")
            st.caption("利用 Google Colab 免费高性能多核算力极速扫描数百上千只全市场股票，完全不受 Streamlit Cloud 内存配额与执行时长限制。")
            
            pool_options = [
                f"🌐 全部分组合并 (全部 {len(groups)} 个组·去重共 {total_unique_in_groups} 支)",
                "🎯 自定义勾选多个分组 (多选并去重合并)",
                "🇺🇸 全量美股 (系统内置)",
                "🇨🇳 全量A股 (系统内置)",
            ]
            grp_name_list = [g["name"] for g in groups if g.get("name")]
            for gn in grp_name_list:
                if gn not in pool_options:
                    pool_options.append(f"📁 分组: {gn}")
            pool_options.append("⭐ 我的自选关注列表")
            
            cfg = storage.load_config()
            saved_pool_neckline = cfg.get("colab_selected_pool_neckline", "")
            pool_def_idx = 0
            if saved_pool_neckline and saved_pool_neckline in pool_options:
                pool_def_idx = pool_options.index(saved_pool_neckline)

            def _on_neckline_colab_pool_change():
                p_val = st.session_state.get("neckline_colab_selected_pool")
                if p_val:
                    storage.save_config({"colab_selected_pool_neckline": p_val})

            p_col1, p_col2 = st.columns([1.5, 1])
            with p_col1:
                selected_pool = st.selectbox(
                    "选择需要导出的扫描股票池",
                    options=pool_options,
                    index=pool_def_idx,
                    key="neckline_colab_selected_pool",
                    on_change=_on_neckline_colab_pool_change,
                    help="系统会自动将选定股票池中的所有股票代码注入到 Colab 脚本中，无需在 Colab 中重复拉取"
                )
            with p_col2:
                st.text_input(
                    "扫描周期 (固定)",
                    value="4h (4小时 突破)",
                    disabled=True,
                    help="4H 结构颈线突破专用于 4小时 (4H) 周期突破检测"
                )
            
            # 如果选择了自定义勾选多个分组 (带持久记忆功能)
            selected_custom_groups = []
            if "自定义勾选多个分组" in selected_pool:
                all_grp_names = [g["name"] for g in groups if g.get("name")]
                saved_grps = cfg.get("colab_custom_groups_neckline") or cfg.get("colab_custom_groups") or []
                valid_defaults = [gn for gn in saved_grps if gn in all_grp_names]
                if not valid_defaults and all_grp_names:
                    valid_defaults = all_grp_names[:2] if len(all_grp_names) >= 2 else all_grp_names
                
                if "neckline_colab_custom_groups" not in st.session_state:
                    st.session_state["neckline_colab_custom_groups"] = valid_defaults
                
                def _on_neckline_colab_custom_groups_change():
                    chosen = st.session_state.get("neckline_colab_custom_groups", [])
                    storage.save_config({"colab_custom_groups_neckline": chosen, "colab_custom_groups": chosen})

                selected_custom_groups = st.multiselect(
                    "勾选要合并扫描的分组 (可任意多选，系统自动去重合并并持久记忆)",
                    options=all_grp_names,
                    key="neckline_colab_custom_groups",
                    on_change=_on_neckline_colab_custom_groups_change,
                    help="选中的分组会自动记忆保存，下次打开页面无需重新勾选"
                )

            # 提取对应股票代码
            export_tickers = []
            if "全部分组合并" in selected_pool:
                all_tks = []
                for g in groups:
                    for tk in g.get("tickers", []):
                        if tk and isinstance(tk, str):
                            all_tks.append(tk.strip().upper())
                export_tickers = list(dict.fromkeys(all_tks))
            elif "自定义勾选多个分组" in selected_pool:
                all_tks = []
                for gn in selected_custom_groups:
                    target_g = next((g for g in groups if g.get("name") == gn), None)
                    if target_g:
                        for tk in target_g.get("tickers", []):
                            if tk and isinstance(tk, str):
                                all_tks.append(tk.strip().upper())
                export_tickers = list(dict.fromkeys(all_tks))
            elif "全量美股" in selected_pool:
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
                export_tickers = [s["ticker"] for s in all_symbols[:500]] if all_symbols else ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]
                
            export_tickers = list(dict.fromkeys([t.strip().upper() for t in export_tickers if t and isinstance(t, str)]))
            
            st.info(f"📋 选定股票池: **{len(export_tickers)}** 支品种 (已自动合并去重) | 周期: **4h** (已直接生成于下方代码中)：")
            
            import colab_neckline_script
            colab_code = colab_neckline_script.generate_colab_neckline_script(export_tickers, pool_name=selected_pool)
            st.code(colab_code, language="python", line_numbers=True)
            st.markdown(
                """
                <div style="font-size:12px;color:#94a3b8;margin-top:-6px;margin-bottom:10px;">
                    👉 <b>操作指引：</b> 点击代码框右上角<b>复制</b> ➔ 打开 <a href="https://colab.research.google.com/" target="_blank" style="color:#38bdf8;text-decoration:underline;">Google Colab</a> 新建笔记本粘贴并运行 ➔ 运行完毕将自动下载 <code>colab_neckline_results.csv</code>。
                </div>
                """,
                unsafe_allow_html=True
            )
        
        with colab_c2:
            st.markdown("##### 2. 导入 Colab 扫描结果 CSV")
            st.caption("上传从 Google Colab 导出的扫描结果 CSV 文件，系统将自动进行格式校验并展示 4H 颈线突破匹配结果。")
            uploaded_file = st.file_uploader(
                "选择或拖拽 Colab 导出的 CSV 文件",
                type=["csv"],
                key="neckline_colab_csv_uploader",
                help="支持导入 colab_neckline_results.csv"
            )
            
            if uploaded_file is not None:
                try:
                    import io
                    import csv
                    import json
                    df_up = pd.read_csv(uploaded_file)
                    
                    if "ticker" not in df_up.columns:
                        st.error("❌ CSV 文件格式不符合要求，缺少 ticker 列")
                    else:
                        passed_list = []
                        failed_list = []
                        errors_list = []
                        
                        for _, r in df_up.iterrows():
                            tk = str(r.get("ticker", "")).strip().upper()
                            if not tk:
                                continue
                            
                            is_passed = bool(r.get("passed", 0) == 1 or str(r.get("passed", "")).lower() in ("true", "1"))
                            err_msg = str(r.get("error", "")) if pd.notna(r.get("error")) and str(r.get("error", "")).strip() else None
                            
                            details = []
                            details_json_str = str(r.get("details_json", ""))
                            if details_json_str and details_json_str != "nan":
                                try:
                                    details = json.loads(details_json_str)
                                except Exception:
                                    pass
                            
                            item = {
                                "ticker": tk,
                                "passed": is_passed,
                                "pattern": str(r.get("pattern", "—")),
                                "neckline": float(r.get("neckline", 0.0)) if pd.notna(r.get("neckline")) and r.get("neckline") != "" else None,
                                "close": float(r.get("close", 0.0)) if pd.notna(r.get("close")) and r.get("close") != "" else None,
                                "volume_4h": float(r.get("volume_4h", 0.0)) if pd.notna(r.get("volume_4h")) and r.get("volume_4h") != "" else None,
                                "vol_ratio": float(r.get("vol_ratio", 0.0)) if pd.notna(r.get("vol_ratio")) and r.get("vol_ratio") != "" else None,
                                "atr14": float(r.get("atr14", 0.0)) if pd.notna(r.get("atr14")) and r.get("atr14") != "" else None,
                                "breakout_pct": float(r.get("breakout_pct", 0.0)) if pd.notna(r.get("breakout_pct")) and r.get("breakout_pct") != "" else None,
                                "error": err_msg,
                                "details": details,
                                "scan_time": str(r.get("scan_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            }
                            
                            if err_msg:
                                errors_list.append(item)
                            elif is_passed:
                                passed_list.append(item)
                            else:
                                failed_list.append(item)
                                
                        total_cnt = len(passed_list) + len(failed_list) + len(errors_list)
                        st.markdown(f"📊 **检测到 CSV 记录**: 共 `{total_cnt}` 支 | 🔥 通过突破: `{len(passed_list)}` 支 | ❌ 未通过: `{len(failed_list)}` 支 | ⚠️ 错误: `{len(errors_list)}` 支")
                        
                        if st.button("📥 确认导入并覆盖为当前结果", key="neckline_colab_confirm_import_btn", type="primary", use_container_width=True):
                            try:
                                final_res = {
                                    "passed": passed_list,
                                    "failed": failed_list,
                                    "errors": errors_list,
                                    "scanned_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "total": total_cnt,
                                    "done_count": total_cnt
                                }
                                ok = storage.save_neckline(final_res)
                                if ok:
                                    try:
                                        storage.backup_neckline(final_res)
                                    except Exception:
                                        pass
                                    st.toast(f"✅ 成功导入 {len(passed_list)} 条 4H 结构颈线突破扫描结果！", icon="🎉")
                                    time.sleep(0.8)
                                    st.rerun()
                                else:
                                    st.error("❌ 写入存储失败: storage.save_neckline 返回 False。")
                            except Exception as save_err:
                                st.error(f"❌ 写入存储异常: {save_err}")
                except Exception as ex:
                    st.error(f"❌ 解析 CSV 文件失败: {ex}")

    # ── 📦 扫描批次历史与恢复 ───────────────────────────────────────
    snapshots = storage.load_neckline_snapshots()
    options = []
    sid_map = {}
    for s in snapshots:
        sid = s.get("session_id", "")
        scan_time = s.get("scan_time", "—")
        tot = s.get("total", 0)
        pas = s.get("passed_count", 0)
        label = f"{scan_time} | 扫描 {tot} 支 | 通过 {pas} 支 | {sid[:18]}"
        options.append(label)
        sid_map[label] = sid

    with st.expander("📦 选择历史扫描批次（备份与恢复）", expanded=True if not storage.load_neckline() else False):
        if not storage.load_neckline():
            st.warning("⚠️ 检测到当前无本地扫描结果。可能由于服务器容器重启/登录失效重置导致。您可以尝试从下方历史批次恢复，或点击右侧从 Supabase 云端拉取最新结果。")
            
        col_snap1, col_snap2, col_snap3 = st.columns([2.5, 1, 1])
        with col_snap1:
            if not options:
                st.caption("💡 暂无可恢复批次（无本地快照）。每次扫描或清空时都会自动创建快照备份。")
                selected_label = None
            else:
                selected_label = st.selectbox(
                    "恢复批次",
                    options,
                    key="neckline_restore_picker",
                    label_visibility="collapsed",
                )
        with col_snap2:
            selected_sid = sid_map.get(selected_label, "") if selected_label else ""
            if st.button("♻️ 恢复批次", key="neckline_restore_btn", use_container_width=True, disabled=not selected_sid or is_running):
                ok, msg, n = storage.restore_neckline_snapshot(selected_sid)
                if ok:
                    st.toast(f"✅ 成功恢复批次：通过 {n} 个品种！", icon="♻️")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ 恢复失败：{msg}")
        with col_snap3:
            if st.button("☁️ 从云端拉取", key="neckline_cloud_pull_btn", use_container_width=True, disabled=is_running):
                try:
                    import cloud_sync
                    if not cloud_sync.is_configured():
                        st.warning("⚠️ 未配置 Supabase 云端同步")
                    else:
                        ok, msg = cloud_sync.pull_neckline()
                        if ok:
                            st.toast(f"✅ {msg}", icon="☁️")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"❌ 云端拉取失败: {msg}")
                except Exception as ex:
                    st.error(f"❌ 云端拉取异常: {ex}")

    tickers = [t.strip().upper() for t in ticker_input.replace("\n", " ").split() if t.strip()]

    # ── 执行扫描 ────────────────────────────────────────────────────
    if run_btn:
        if not _YF_OK:
            st.error("❌ yfinance 未安装，请在 requirements.txt 中添加 yfinance")
            return
        if not tickers:
            st.warning("请输入至少一个股票代码")
            return

        params = {
            "tickers": tickers
        }
        
        ok, msg = bg_scan_manager.submit_job(
            job_type="neckline_scan",
            label=f"4H 结构颈线突破扫描 ({len(tickers)}支)",
            params=params,
            worker_fn=neckline_worker
        )
        if ok:
            st.success(msg)
            time.sleep(1)
            st.rerun()
        else:
            st.error(msg)

    # ── 结果展示 ────────────────────────────────────────────────────
    cache = storage.load_neckline()
    if not cache:
        st.markdown(
            '<div class="n-info" style="margin-top:16px">'
            '💡 输入股票池后点击「开始扫描」，满足 4H 结构颈线突破条件的品种会显示在下方。'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    passed = cache.get("passed", [])
    failed = cache.get("failed", [])
    errors = cache.get("errors", [])
    total  = cache.get("total", 0)
    scanned_at = cache.get("scanned_at", "—")

    # 顶部统计
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_stat_card("扫描品种", str(total),       "blue"),  unsafe_allow_html=True)
    c2.markdown(_stat_card("突破通过", str(len(passed)), "green"), unsafe_allow_html=True)
    c3.markdown(_stat_card("未通过",   str(len(failed)), "gray"),  unsafe_allow_html=True)
    c4.markdown(_stat_card("数据错误", str(len(errors)), "red"),   unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:11px;color:#9ca3af;text-align:right;margin-top:4px">'
        f'扫描时间：{scanned_at}</div>',
        unsafe_allow_html=True,
    )

    # ── 过滤、搜索与分页控制栏 ──────────────────────────────────────
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1.2, 1.2, 1.1])
    with col_f1:
        search_q = st.text_input("🔍 搜索品种代码", key="neckline_search_q", placeholder="输入代码如 AAPL, 600519...")
    with col_f2:
        pattern_filter = st.selectbox("🏷️ 突破形态筛选", options=["全部形态", "箱体突破", "双底突破", "头肩底突破"], key="neckline_pat_filter")
    with col_f3:
        sort_by = st.selectbox("↕️ 排序方式", options=["突破幅度 (高到低)", "4H成交量 (大到小)", "代码 (A-Z)"], key="neckline_sort_by")
    with col_f4:
        page_size = st.selectbox("📄 每页条数", options=[25, 50, 100, "全部"], index=0, key="neckline_page_size")

    # 过滤通过列表
    filtered_passed = passed
    if search_q:
        q = search_q.strip().upper()
        filtered_passed = [r for r in filtered_passed if q in str(r.get("ticker", "")).upper()]
    if pattern_filter != "全部形态":
        filtered_passed = [r for r in filtered_passed if pattern_filter in str(r.get("pattern", ""))]
    
    # 排序
    if sort_by == "突破幅度 (高到低)":
        filtered_passed = sorted(filtered_passed, key=lambda x: _safe_float(x.get("breakout_pct"), 0.0), reverse=True)
    elif sort_by == "4H成交量 (大到小)":
        filtered_passed = sorted(filtered_passed, key=lambda x: _safe_float(x.get("volume_4h"), 0.0), reverse=True)
    elif sort_by == "代码 (A-Z)":
        filtered_passed = sorted(filtered_passed, key=lambda x: str(x.get("ticker", "")))

    total_passed_cnt = len(filtered_passed)

    # ── 通过的品种 ──────────────────────────────────────────────────
    col_pass_hdr1, col_pass_hdr2 = st.columns([3, 1])
    with col_pass_hdr1:
        st.markdown(f"### 🚀 突破 4H 结构颈线的品种 ({total_passed_cnt} 支)")
    with col_pass_hdr2:
        if filtered_passed:
            if st.button("⭐ 批量收藏当前筛选品种", key="neckline_fav_all_passed", use_container_width=True):
                added_cnt = 0
                for r in filtered_passed:
                    tk = r["ticker"]
                    if storage.add_to_watchlist(ticker=tk, name=tk, note="4H 结构颈线突破扫描匹配"):
                        added_cnt += 1
                st.toast(f"✅ 成功将 {added_cnt} 个品种加入自选收藏夹！", icon="⭐")
                time.sleep(1)
                st.rerun()

    if not filtered_passed:
        if passed and (search_q or pattern_filter != "全部形态"):
            st.markdown('<div class="n-warn">未找到符合搜索/筛选条件的突破品种。</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="n-warn">本次扫描无品种满足 4H 结构颈线突破条件。</div>', unsafe_allow_html=True)
    else:
        # 分页切片计算
        if page_size == "全部":
            page_items = filtered_passed
            total_pages = 1
            curr_page_idx = 1
        else:
            ps = int(page_size)
            total_pages = max(1, (total_passed_cnt + ps - 1) // ps)
            
            if "neckline_page_idx" not in st.session_state:
                st.session_state["neckline_page_idx"] = 1
            if st.session_state["neckline_page_idx"] > total_pages:
                st.session_state["neckline_page_idx"] = total_pages
            if st.session_state["neckline_page_idx"] < 1:
                st.session_state["neckline_page_idx"] = 1
                
            curr_page_idx = st.session_state["neckline_page_idx"]
            
            if total_pages > 1:
                col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
                with col_p1:
                    if st.button("⬅️ 上一页", key="nl_prev_p", disabled=(curr_page_idx <= 1), use_container_width=True):
                        st.session_state["neckline_page_idx"] = max(1, curr_page_idx - 1)
                        st.rerun()
                with col_p2:
                    st.markdown(f"<div style='text-align:center;padding-top:6px;font-size:13px;color:#94a3b8;'>第 <b style='color:#38bdf8;'>{curr_page_idx}</b> / {total_pages} 页 (共 {total_passed_cnt} 支，当前显示第 {(curr_page_idx-1)*ps+1} - {min(curr_page_idx*ps, total_passed_cnt)} 支)</div>", unsafe_allow_html=True)
                with col_p3:
                    if st.button("下一页 ➡️", key="nl_next_p", disabled=(curr_page_idx >= total_pages), use_container_width=True):
                        st.session_state["neckline_page_idx"] = min(total_pages, curr_page_idx + 1)
                        st.rerun()
                    
            start_i = (curr_page_idx - 1) * ps
            end_i = start_i + ps
            page_items = filtered_passed[start_i:end_i]

        all_clicks_data = storage.get_all_link_clicks()
        today_str_val = storage.get_today_str()
        from assets import tv_url, sina_url
        
        wl_items = storage.load_watchlist()
        wl_set = {item["ticker"].upper() for item in wl_items if isinstance(item, dict)}
        
        _t_val = st.query_params.get("_t", "")
        _t_param = f"&_t={_t_val}" if _t_val else ""

        # 汇总表 (仅渲染当前页数据，极速流畅)
        rows_html = []
        for r in page_items:
            ticker = r["ticker"]
            pat = r.get("pattern", "箱体突破")
            
            p_val = _safe_float(r.get("close"), None)
            price_s = f"{p_val:.4f}" if p_val is not None else "—"
            
            nl_val = _safe_float(r.get("neckline"), None)
            nl_s = f"{nl_val:.4f}" if nl_val is not None else "—"
            
            bk_pct = _safe_float(r.get("breakout_pct"), 0.0)
            bk_s = f"<span style='color:#4ade80;font-weight:700;'>+{bk_pct:.2f}%</span>" if bk_pct >= 0 else f"<span style='color:#f87171;'>{bk_pct:.2f}%</span>"
            
            v_val = _safe_float(r.get("volume_4h"), None)
            vol_s = f"{v_val:,.0f}" if v_val is not None else "—"
            
            vr_val = _safe_float(r.get("vol_ratio"), None)
            ratio_s = f"<span style='color:#fbbf24;font-weight:600;'>{vr_val:.2f}x</span>" if vr_val is not None else "—"
            
            click_entry = all_clicks_data.get(f"{ticker.upper()}:tv", {}) if isinstance(all_clicks_data, dict) else {}
            total_c = click_entry.get("total", 0) if isinstance(click_entry, dict) else 0
            by_date_map = click_entry.get("by_date", {}) if isinstance(click_entry, dict) else {}
            today_c = by_date_map.get(today_str_val, 0) if isinstance(by_date_map, dict) else 0
            if total_c > 0:
                click_badge = f' <span style="font-size:11px;color:#4ade80;font-weight:600;">({today_c}/{total_c})</span>'
            else:
                click_badge = ' <span style="font-size:11px;color:#64748b;font-weight:500;">(0/0)</span>'
            
            tv_lnk = tv_url(ticker, "4h")
            tv_html = f'<a href="{tv_lnk}" target="_blank" class="tv-btn" data-ticker="{ticker}" style="color:#38bdf8;text-decoration:none;font-weight:600;font-size:12px;background:rgba(56,189,248,0.1);padding:4px 10px;border-radius:4px;border:1px solid rgba(56,189,248,0.2);">📈 TV{click_badge}</a>'
            
            sina_lnk = sina_url(ticker)
            sina_html = f'<a href="{sina_lnk}" target="_blank" class="sina-btn" data-ticker="{ticker}" style="color:#f87171;text-decoration:none;font-weight:600;font-size:12px;background:rgba(239,68,68,0.1);padding:4px 8px;border-radius:4px;border:1px solid rgba(239,68,68,0.2);margin-left:4px;">🏦 新浪</a>' if sina_lnk else ""
            
            is_fav = ticker.upper() in wl_set
            if is_fav:
                fav_html = f'<a href="/?_page=watchlist&_fav=del|{ticker}|{ticker}{_t_param}&_anchor={ticker}" target="_blank" style="color:#f59e0b;text-decoration:none;font-weight:600;font-size:12px;background:rgba(245,158,11,0.15);padding:4px 10px;border-radius:4px;border:1px solid rgba(245,158,11,0.3);">★ 已收藏</a>'
            else:
                fav_html = f'<a href="/?_page=watchlist&_fav=add|{ticker}|{ticker}{_t_param}&_anchor={ticker}" target="_blank" style="color:#eab308;text-decoration:none;font-weight:600;font-size:12px;background:rgba(234,179,8,0.1);padding:4px 10px;border-radius:4px;border:1px solid rgba(234,179,8,0.2);">⭐ 收藏</a>'
            
            pat_badge = f'<span style="background:rgba(56,189,248,0.15);color:#38bdf8;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:600;border:1px solid rgba(56,189,248,0.3);">🏷️ {pat}</span>'

            rows_html.append(
                f"<tr>"
                f"<td style='padding:10px;font-weight:bold;'><a href='/?_page=ticker&_ticker={ticker}{_t_param}' target='_parent' style='color:#38bdf8;text-decoration:none;'>{ticker}</a></td>"
                f"<td style='padding:10px;'>{pat_badge}</td>"
                f"<td style='padding:10px;font-family:monospace;font-weight:700;'>{price_s}</td>"
                f"<td style='padding:10px;font-family:monospace;color:#94a3b8;'>{nl_s}</td>"
                f"<td style='padding:10px;'>{bk_s}</td>"
                f"<td style='padding:10px;'>{vol_s} ({ratio_s})</td>"
                f"<td style='padding:10px;'>{fav_html}</td>"
                f"<td style='padding:10px;'>{tv_html}{sina_html}</td>"
                f"</tr>"
            )
            
        thead = (
            "<tr style='background:rgba(255,255,255,0.05);text-align:left;border-bottom:2px solid rgba(255,255,255,0.1);'>"
            "<th style='padding:10px;'>品种代码</th>"
            "<th style='padding:10px;'>识别结构</th>"
            "<th style='padding:10px;'>4H收盘价</th>"
            "<th style='padding:10px;'>颈线位</th>"
            "<th style='padding:10px;'>突破幅度</th>"
            "<th style='padding:10px;'>4H量 (量比)</th>"
            "<th style='padding:10px;'>自选收藏</th>"
            "<th style='padding:10px;'>行情图表 (今日/总)</th>"
            "</tr>"
        )
        st.markdown(
            f"<div style='width:100%;overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:13px;'><thead>{thead}</thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

        # 💡 隐形事件监听组件：捕捉原链接点击，能在后台落盘计数，同时在前台秒级实时更新 (今日/总) 数字
        _js_code = (
            "<script>\n"
            "(function() {\n"
            "    try {\n"
            "        var pDoc = window.parent.document;\n"
            "        if (pDoc._tv_click_handler) {\n"
            "            pDoc.removeEventListener('click', pDoc._tv_click_handler, true);\n"
            "        }\n"
            "        pDoc._tv_click_handler = function(e) {\n"
            "            var btn = e.target.closest('.tv-btn, .sina-btn');\n"
            "            if (btn) {\n"
            "                var tk = btn.getAttribute('data-ticker');\n"
            "                if (tk) {\n"
            "                    tk = tk.trim().toUpperCase();\n"
            "                    var cbUrl = '/?_tv_click=' + encodeURIComponent(tk) + '&_cb=' + Date.now() + '_' + Math.floor(Math.random()*10000);\n"
            "                    try { fetch(cbUrl, { cache: 'no-store', mode: 'no-cors' }); } catch(err) {}\n"
            "                    try { if (navigator.sendBeacon) { navigator.sendBeacon(cbUrl); } } catch(err) {}\n"
            "                    try {\n"
            "                        var f = pDoc.createElement('iframe');\n"
            "                        f.style.display = 'none';\n"
            "                        f.src = cbUrl;\n"
            "                        pDoc.body.appendChild(f);\n"
            "                        setTimeout(function() { try { f.remove(); } catch(err) {} }, 6000);\n"
            "                    } catch(err) {}\n"
            "                    try {\n"
            "                        var allBtns = pDoc.querySelectorAll('.tv-btn, .sina-btn');\n"
            "                        for (var i = 0; i < allBtns.length; i++) {\n"
            "                            var b = allBtns[i];\n"
            "                            var bTk = b.getAttribute('data-ticker');\n"
            "                            if (bTk && bTk.trim().toUpperCase() === tk) {\n"
            "                                var spans = b.getElementsByTagName('span');\n"
            "                                if (spans && spans.length > 0) {\n"
            "                                    var span = spans[spans.length - 1];\n"
            "                                    var txt = span.innerText || span.textContent || '';\n"
            "                                    var m = txt.match(/\\((\\d+)\\/(\\d+)\\)/);\n"
            "                                    if (m) {\n"
            "                                        var today = parseInt(m[1], 10) + 1;\n"
            "                                        var total = parseInt(m[2], 10) + 1;\n"
            "                                        span.innerText = '(' + today + '/' + total + ')';\n"
            "                                        span.style.color = '#4ade80';\n"
            "                                        span.style.fontWeight = '600';\n"
            "                                    }\n"
            "                                }\n"
            "                            }\n"
            "                        }\n"
            "                    } catch(err) {}\n"
            "                }\n"
            "            }\n"
            "        };\n"
            "        pDoc.addEventListener('click', pDoc._tv_click_handler, true);\n"
            "    } catch(err) {}\n"
            "})();\n"
            "</script>"
        )
        if hasattr(st, "html"):
            st.html(_js_code)
        else:
            import streamlit.components.v1 as _components
            _components.html(_js_code, height=0)

        # 详细条件展开 (仅对当前页的品种提供展开查看，避免过大 DOM 卡顿)
        with st.expander(f"🔍 查看当前页 ({len(page_items)} 支) 6 条突破确认条件明细与检测值", expanded=False):
            for r in page_items:
                with st.expander(f"📊 {r['ticker']} — 4H 结构颈线突破明细 ({r.get('pattern', '—')})", expanded=False):
                    col_d1, col_d2 = st.columns([4, 1])
                    with col_d1:
                        _render_details(r.get("details", []))
                    with col_d2:
                        if r['ticker'].upper() in wl_set:
                            if st.button(f"🗑️ 移除收藏", key=f"neckline_fav_det_del_{r['ticker']}", use_container_width=True):
                                storage.remove_from_watchlist(r['ticker'])
                                st.toast(f"已将 {r['ticker']} 从自选收藏夹移除", icon="🗑️")
                                st.rerun()
                        else:
                            if st.button(f"⭐ 加入收藏", key=f"neckline_fav_det_add_{r['ticker']}", use_container_width=True):
                                storage.add_to_watchlist(ticker=r['ticker'], name=r['ticker'], note="4H 结构颈线突破扫描匹配")
                                st.toast(f"⭐ 已将 {r['ticker']} 加入自选收藏夹", icon="⭐")
                                st.rerun()

    # ── 未通过品种（高性能 DataFrame 展示）────────────────────────
    if failed:
        with st.expander(f"❌ 未通过品种（共 {len(failed)} 个）", expanded=False):
            failed_df_rows = []
            for r in failed:
                p_val = _safe_float(r.get("close"), None)
                nl_val = _safe_float(r.get("neckline"), None)
                vr_val = _safe_float(r.get("vol_ratio"), None)
                failed_df_rows.append({
                    "品种代码": r.get("ticker", ""),
                    "识别形态": r.get("pattern", "—"),
                    "4H收盘价": f"{p_val:.4f}" if p_val is not None else "—",
                    "颈线位": f"{nl_val:.4f}" if nl_val is not None else "—",
                    "4H量比": f"{vr_val:.2f}x" if vr_val is not None else "—",
                    "扫描状态": r.get("error") or "未满足全部突破确认条件"
                })
            st.dataframe(pd.DataFrame(failed_df_rows), use_container_width=True, height=320, hide_index=True)
            
            # 单独点选查看某一个未通过品种的 6 条规则明细
            failed_tickers = [r.get("ticker", "") for r in failed if r.get("ticker")]
            if failed_tickers:
                sel_f_tk = st.selectbox("🔍 选择查看未通过品种的 6 条规则检测值", options=["— 请选择品种 —"] + failed_tickers, key="nl_failed_inspect_picker")
                if sel_f_tk and sel_f_tk != "— 请选择品种 —":
                    target_f = next((r for r in failed if r.get("ticker") == sel_f_tk), None)
                    if target_f and target_f.get("details"):
                        _render_details(target_f["details"])

    # ── 数据错误 ────────────────────────────────────────────────────
    if errors:
        with st.expander(f"⚠️ 数据获取失败（共 {len(errors)} 个）", expanded=False):
            err_df_rows = [{"品种代码": r.get("ticker", ""), "错误原因": r.get("error", "")} for r in errors]
            st.dataframe(pd.DataFrame(err_df_rows), use_container_width=True, height=200, hide_index=True)
