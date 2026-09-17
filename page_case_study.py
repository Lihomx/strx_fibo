"""
page_case_study.py — 趋势启动案例库与跨周期分析系统 (Case Study Lab)
======================================================================
实现功能：
  1. 案例标准化录入：支持品种、启动时间、大级别(月/周)与小级别(天/4H)截图、结构化指标特征勾选与心得笔记。
  2. 案例画廊 (Gallery View)：卡片式多周期对比展示，支持图表缩略与放大。
  3. 指标对比矩阵 (Comparison Matrix)：横向对齐各品种启动特征，自动计算指标共性概率（公约数）。
  4. 一键生成 AI 复盘 Prompt：将选定案例自动生成结构化复盘指令，供在对话中进行算法级深度挖掘。
  5. 数据备份与导出：支持导出案例库为 JSON 及 CSV 文件。
======================================================================
"""

import os
import io
import json
import time
import uuid
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import Dict, List, Any

import importlib
import storage
if not hasattr(storage, "load_case_studies"):
    try:
        storage = importlib.reload(storage)
    except Exception:
        pass

# 预设常见长周期趋势启动指标与形态特征
PRESET_INDICATORS = [
    "均线粘合走平",
    "EMA多头发散",
    "站上关键均线 (EMA20/50)",
    "布林带极致收口(Squeeze)",
    "Keltner通道突破",
    "ATR爆发突破",
    "MACD零轴二次金叉",
    "MACD大级别底背驰",
    "RSI突破50中轴",
    "长期箱体/颈线放量突破",
    "假跌破快速拉回 (Spring/假动作)",
    "多重底结构 (W底/三重底)",
    "放量突破筹码密集区",
    "缩量筑底后首次异动放量"
]

CATEGORIES = [
    "Crypto 加密货币",
    "US Stock 美股",
    "A-Share A股",
    "Commodity 大宗商品/外汇",
    "Index 全球指数",
    "Other 其他"
]


def _inject_custom_css():
    st.markdown("""
    <style>
    .case-card {
        background: var(--background-color, #ffffff);
        border: 1px solid var(--border-color, #e5e7eb);
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .case-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    }
    .case-title {
        font-size: 19px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
    }
    .case-badge {
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 6px;
        display: inline-block;
    }
    .badge-long { background: rgba(34,197,94,0.12); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
    .badge-short { background: rgba(239,68,68,0.12); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); }
    .badge-cat { background: rgba(59,130,246,0.12); color: #3b82f6; border: 1px solid rgba(59,130,246,0.3); }
    .badge-time { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); font-family: monospace; }
    .tag-pill {
        display: inline-block;
        background: var(--secondary-background-color, #f3f4f6);
        color: var(--text-color, #374151);
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        margin: 2px 4px 2px 0;
        border: 1px solid var(--border-color, #e5e7eb);
    }
    .tag-pill-custom {
        background: rgba(168, 85, 247, 0.1);
        color: #9333ea;
        border-color: rgba(168, 85, 247, 0.3);
    }
    .stat-box {
        background: var(--secondary-background-color, #f9fafb);
        border: 1px solid var(--border-color, #e5e7eb);
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
    }
    .stat-val { font-size: 22px; font-weight: 800; color: #e85d04; }
    .stat-lbl { font-size: 11px; color: #6b7280; text-transform: uppercase; font-weight: 600; margin-top: 2px; }
    .prompt-box {
        font-family: monospace;
        background: #111827;
        color: #f3f4f6;
        padding: 16px;
        border-radius: 8px;
        font-size: 12px;
        line-height: 1.6;
        overflow-x: auto;
    }
    </style>
    """, unsafe_allow_html=True)


def _save_uploaded_image(file_obj, prefix: str) -> str:
    """保存上传的图片并返回存储路径"""
    if not file_obj:
        return ""
    storage._ensure_case_snapshot_dir()
    ext = os.path.splitext(file_obj.name)[1].lower() or ".png"
    filename = f"{prefix}_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}{ext}"
    filepath = os.path.join(storage.CASE_SNAPSHOT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(file_obj.getbuffer())
    return filepath


def render():
    _inject_custom_css()

    # 标题栏
    st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:16px;">
        <div>
            <h1 style="margin:0; font-size:26px;">🔬 启动案例库与跨周期复盘</h1>
            <p style="margin:4px 0 0; color:#6b7280; font-size:13px;">
                长周期 (周图/月图) 趋势启动点样本库 · 多周期图表穿透 · 指标共性对比分析 · AI 算法级复盘联动
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 读取案例数据
    cases = storage.load_case_studies()

    # 顶层 Tab 导航
    tab_gallery, tab_matrix, tab_create, tab_ai_export = st.tabs([
        f"📊 案例画廊 ({len(cases)})",
        "📐 指标对比矩阵",
        "➕ 录入/编辑案例",
        "🤖 AI 复盘 Prompt 导出"
    ])

    # ────────────────────────────────────────────────────────────────
    # TAB 1: 案例画廊 (Gallery View)
    # ────────────────────────────────────────────────────────────────
    with tab_gallery:
        if not cases:
            st.info("💡 暂无案例，请前往「➕ 录入/编辑案例」添加第一个趋势启动样本，或点击下方按钮恢复示例案例。")
            if st.button("🔄 恢复内置示范案例", key="btn_reset_demos"):
                storage.init_demo_case_studies()
                st.rerun()
        else:
            # 过滤筛选栏
            f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
            with f_col1:
                cat_filter = st.selectbox("分类筛选", ["全部"] + CATEGORIES, key="gal_cat_filter")
            with f_col2:
                dir_filter = st.selectbox("方向筛选", ["全部", "做多 (Long)", "做空 (Short)"], key="gal_dir_filter")
            with f_col3:
                kw_search = st.text_input("关键词搜索 (代码/名称/指标)", key="gal_kw_search", placeholder="输入 Ticker 或指标名称...").strip().lower()

            filtered_cases = []
            for c in cases:
                if cat_filter != "全部" and c.get("category") != cat_filter:
                    continue
                if dir_filter != "全部" and c.get("direction") != dir_filter:
                    continue
                if kw_search:
                    text_blob = f"{c.get('ticker','')} {c.get('name','')} {c.get('notes','')} {' '.join(c.get('indicators',[]))} {' '.join(c.get('custom_indicators',[]))}".lower()
                    if kw_search not in text_blob:
                        continue
                filtered_cases.append(c)

            st.caption(f"共筛选出 {len(filtered_cases)} / {len(cases)} 个案例")

            # 遍历渲染每个案例卡片
            for idx, c in enumerate(filtered_cases):
                cid = c.get("id", f"case_{idx}")
                ticker = c.get("ticker", "UNKNOWN")
                name = c.get("name", "")
                cat = c.get("category", "Other")
                launch_time = c.get("launch_time", "")
                direction = c.get("direction", "做多 (Long)")
                trend_scale = c.get("trend_scale", "")
                indicators = c.get("indicators", [])
                custom_inds = c.get("custom_indicators", [])
                notes = c.get("notes", "")
                img_htf = c.get("img_htf", "")
                img_ltf = c.get("img_ltf", "")

                is_long = "做多" in direction or "Long" in direction
                dir_badge_cls = "badge-long" if is_long else "badge-short"

                with st.container():
                    st.markdown(f"""
                    <div class="case-card">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                            <div class="case-title">
                                <span>{ticker}</span>
                                <span style="font-size:15px; font-weight:normal; color:#6b7280;">{name}</span>
                                <span class="case-badge {dir_badge_cls}">{'🟢 做多' if is_long else '🔴 做空'}</span>
                                <span class="case-badge badge-cat">{cat}</span>
                                <span class="case-badge badge-time">📅 启动时间: {launch_time}</span>
                            </div>
                            <div style="font-size:13px; font-weight:600; color:#e85d04;">
                                🚀 启动后规模: {trend_scale}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 双周期图表对比展示
                    img_col1, img_col2 = st.columns(2)
                    with img_col1:
                        st.markdown("**🌐 大级别全景图 (月图 / 周图)**")
                        if img_htf and os.path.exists(img_htf):
                            st.image(img_htf, caption=f"{ticker} 月/周图长期趋势启动背景", use_container_width=True)
                        else:
                            st.markdown("""
                            <div style="background:var(--secondary-background-color, #f3f4f6); border:1px dashed #9ca3af; border-radius:8px; padding:30px 10px; text-align:center; color:#6b7280; font-size:12px;">
                                🖼️ 暂未上传大级别图表截图<br>
                                <span style="font-size:11px;">(请在编辑或录入页面上传周线/月线全景图)</span>
                            </div>
                            """, unsafe_allow_html=True)

                    with img_col2:
                        st.markdown("**🔬 小级别触发图 (天图 / 4小时图)**")
                        if img_ltf and os.path.exists(img_ltf):
                            st.image(img_ltf, caption=f"{ticker} 日线/4H 启动触发微观细节", use_container_width=True)
                        else:
                            st.markdown("""
                            <div style="background:var(--secondary-background-color, #f3f4f6); border:1px dashed #9ca3af; border-radius:8px; padding:30px 10px; text-align:center; color:#6b7280; font-size:12px;">
                                🔍 暂未上传微观级别图表截图<br>
                                <span style="font-size:11px;">(请在编辑或录入页面上传天图/4H启动点细节图)</span>
                            </div>
                            """, unsafe_allow_html=True)

                    # 指标标签与笔记
                    st.markdown("<div style='margin-top:10px;'>", unsafe_allow_html=True)
                    st.markdown("**📐 捕获该启动点的指标与特征：**")
                    tag_html = "".join([f'<span class="tag-pill">✅ {ind}</span>' for ind in indicators])
                    tag_html += "".join([f'<span class="tag-pill tag-pill-custom">⚡ {ci}</span>' for ci in custom_inds if ci])
                    if not tag_html:
                        tag_html = '<span style="color:#9ca3af; font-size:12px;">未勾选特定指标</span>'
                    st.markdown(f"<div>{tag_html}</div>", unsafe_allow_html=True)

                    if notes:
                        st.markdown(f"""
                        <div style="margin-top:8px; font-size:13px; color:var(--text-color, #374151); background:var(--secondary-background-color, #f9fafb); border-left:3px solid #e85d04; padding:8px 12px; border-radius:0 6px 6px 0;">
                            <b>📝 复盘笔记与观察：</b> {notes}
                        </div>
                        """, unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                    # 操作按钮栏
                    b_col1, b_col2, b_col3 = st.columns([1, 1, 6])
                    with b_col1:
                        if st.button("✏️ 编辑", key=f"btn_edit_{cid}", use_container_width=True):
                            st.session_state["case_edit_id"] = cid
                            st.rerun()
                    with b_col2:
                        if st.button("🗑️ 删除", key=f"btn_del_{cid}", use_container_width=True):
                            storage.delete_case_study(cid)
                            st.toast(f"🗑️ 已删除案例：{ticker}", icon="🗑️")
                            st.rerun()

                    st.markdown("<hr style='margin:18px 0; border-color:var(--border-color, #e5e7eb)'>", unsafe_allow_html=True)

    # ────────────────────────────────────────────────────────────────
    # TAB 2: 指标对比矩阵 (Comparison Matrix)
    # ────────────────────────────────────────────────────────────────
    with tab_matrix:
        if not cases:
            st.info("💡 暂无案例数据，请录入案例后查看横向指标对比。")
        else:
            st.markdown("### 📊 启动特征出现频率与「公约数」统计")
            st.caption("统计所有案例在周图/月图大趋势启动前，各项指标特征出现的频率与共性概率。")

            # 统计所有指标频次
            all_case_inds = []
            for c in cases:
                inds = set(c.get("indicators", []) + c.get("custom_indicators", []))
                all_case_inds.append(inds)

            ind_counts = {}
            for preset in PRESET_INDICATORS:
                cnt = sum(1 for s in all_case_inds if preset in s)
                if cnt > 0:
                    ind_counts[preset] = cnt

            # 也统计高频 custom indicators
            custom_counter = {}
            for c in cases:
                for ci in c.get("custom_indicators", []):
                    if ci.strip():
                        custom_counter[ci.strip()] = custom_counter.get(ci.strip(), 0) + 1
            for ci, cnt in custom_counter.items():
                if cnt >= 2 and ci not in ind_counts:
                    ind_counts[f"[自定义] {ci}"] = cnt

            # 排序
            sorted_inds = sorted(ind_counts.items(), key=lambda x: x[1], reverse=True)

            # 核心数据看板
            top_ind_name = sorted_inds[0][0] if sorted_inds else "无"
            top_ind_pct = f"{(sorted_inds[0][1]/len(cases))*100:.0f}%" if sorted_inds else "0%"

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.markdown(f"""
                <div class="stat-box">
                    <div class="stat-val">{len(cases)}</div>
                    <div class="stat-lbl">已录入案例样本总数</div>
                </div>
                """, unsafe_allow_html=True)
            with sc2:
                st.markdown(f"""
                <div class="stat-box">
                    <div class="stat-val" style="color:#10b981;">{top_ind_name}</div>
                    <div class="stat-lbl">最高频启动前置指标</div>
                </div>
                """, unsafe_allow_html=True)
            with sc3:
                st.markdown(f"""
                <div class="stat-box">
                    <div class="stat-val" style="color:#3b82f6;">{top_ind_pct}</div>
                    <div class="stat-lbl">最高频指标重合度 (共性占比)</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("#### 🏆 指标出现概率排行榜")
            ranking_rows = []
            for ind_name, count in sorted_inds:
                pct = (count / len(cases)) * 100
                matching_tickers = [
                    c.get("ticker") for c in cases
                    if ind_name in c.get("indicators", []) or ind_name.replace("[自定义] ", "") in c.get("custom_indicators", [])
                ]
                ranking_rows.append({
                    "指标 / 启动特征": ind_name,
                    "出现频次": f"{count} / {len(cases)}",
                    "共性占比": f"{pct:.1f}%",
                    "符合品种": ", ".join(matching_tickers)
                })
            st.dataframe(pd.DataFrame(ranking_rows), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("#### 📐 多品种横向对比宽表 (Matrix View)")

            # 构建对比大宽表
            active_presets = [p for p in PRESET_INDICATORS if any(p in c.get("indicators", []) for c in cases)]

            matrix_rows = []
            for c in cases:
                row = {
                    "品种代码": c.get("ticker", ""),
                    "名称": c.get("name", ""),
                    "启动时间": c.get("launch_time", ""),
                    "方向": c.get("direction", ""),
                    "涨幅级别": c.get("trend_scale", "")[:30],
                }
                c_inds = set(c.get("indicators", []))
                for p in active_presets:
                    row[p] = "✅" if p in c_inds else "—"
                if c.get("custom_indicators"):
                    row["自定义指标"] = " | ".join(c.get("custom_indicators", []))
                matrix_rows.append(row)

            st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

    # ────────────────────────────────────────────────────────────────
    # TAB 3: 录入 / 编辑案例 (Case Intake Form)
    # ────────────────────────────────────────────────────────────────
    with tab_create:
        edit_id = st.session_state.get("case_edit_id")
        editing_case = next((c for c in cases if c.get("id") == edit_id), None) if edit_id else None

        if editing_case:
            st.info(f"✏️ 正在编辑案例：**{editing_case.get('ticker')} ({editing_case.get('launch_time')})**")
            if st.button("❌ 取消编辑，新建案例", key="btn_cancel_edit"):
                st.session_state.pop("case_edit_id", None)
                st.rerun()
        else:
            st.markdown("### ➕ 标准化案例录入")
            st.caption("按照统一标准录入你的周图/月图大级别趋势启动案例，便于横向复盘。")

        # 案例表单
        with st.form(key="case_form"):
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                f_ticker = st.text_input(
                    "品种代码 (Ticker) *",
                    value=editing_case.get("ticker", "") if editing_case else "",
                    placeholder="如: BTCUSDT, XAUUSD, NVDA, 600519.SS"
                ).strip().upper()
            with col_b2:
                f_name = st.text_input(
                    "品种名称 / 描述",
                    value=editing_case.get("name", "") if editing_case else "",
                    placeholder="如: 比特币, 现货黄金, 英伟达"
                ).strip()
            with col_b3:
                curr_cat = editing_case.get("category", CATEGORIES[0]) if editing_case else CATEGORIES[0]
                cat_idx = CATEGORIES.index(curr_cat) if curr_cat in CATEGORIES else 0
                f_cat = st.selectbox("市场分类", CATEGORIES, index=cat_idx)

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                f_launch_time = st.text_input(
                    "启动时间 (Launch Time) *",
                    value=editing_case.get("launch_time", "") if editing_case else "",
                    placeholder="如: 2020-10, 2023-10-16, 2019-06"
                ).strip()
            with col_t2:
                curr_dir = editing_case.get("direction", "做多 (Long)") if editing_case else "做多 (Long)"
                dir_options = ["做多 (Long)", "做空 (Short)"]
                dir_idx = dir_options.index(curr_dir) if curr_dir in dir_options else 0
                f_direction = st.selectbox("趋势方向", dir_options, index=dir_idx)
            with col_t3:
                f_trend_scale = st.text_input(
                    "启动后级别 / 涨幅结果",
                    value=editing_case.get("trend_scale", "") if editing_case else "",
                    placeholder="如: 周线单边上涨300%, 月线翻倍"
                ).strip()

            st.markdown("---")
            st.markdown("#### 📐 启动前夕指标与结构特征 (复选勾选)")
            selected_preset_inds = editing_case.get("indicators", []) if editing_case else []

            chk_cols = st.columns(2)
            new_selected_inds = []
            for i, ind in enumerate(PRESET_INDICATORS):
                with chk_cols[i % 2]:
                    checked = ind in selected_preset_inds
                    if st.checkbox(ind, value=checked, key=f"chk_ind_{i}"):
                        new_selected_inds.append(ind)

            f_custom_inds_str = st.text_input(
                "自定义专属指标 / 形态特征 (多个用逗号隔开)",
                value=", ".join(editing_case.get("custom_indicators", [])) if editing_case else "",
                placeholder="如: 200周均线支撑, Cup and Handle杯柄形态突破, 资金费率极度负费率"
            )

            st.markdown("---")
            st.markdown("#### 🖼️ 多周期案例截图上传")
            img_c1, img_c2 = st.columns(2)
            with img_c1:
                st.markdown("**大级别全景图 (月图 / 周图)**")
                if editing_case and editing_case.get("img_htf") and os.path.exists(editing_case.get("img_htf")):
                    st.caption(f"当前图片已存在: `{os.path.basename(editing_case.get('img_htf'))}`")
                up_htf = st.file_uploader("选择月/周图截图 (PNG/JPG/WEBP)", type=["png", "jpg", "jpeg", "webp"], key="up_htf")

            with img_c2:
                st.markdown("**小级别触发图 (天图 / 4小时图)**")
                if editing_case and editing_case.get("img_ltf") and os.path.exists(editing_case.get("img_ltf")):
                    st.caption(f"当前图片已存在: `{os.path.basename(editing_case.get('img_ltf'))}`")
                up_ltf = st.file_uploader("选择天/4H图截图 (PNG/JPG/WEBP)", type=["png", "jpg", "jpeg", "webp"], key="up_ltf")

            st.markdown("---")
            f_notes = st.text_area(
                "📝 启动前后微观复盘笔记 (当时的K线行为、假动作、量能等)",
                value=editing_case.get("notes", "") if editing_case else "",
                placeholder="详细记录你在启动点观察到的核心线索...",
                height=110
            )

            submit_label = "💾 保存修改" if editing_case else "➕ 保存案例到样本库"
            submitted = st.form_submit_button(submit_label, use_container_width=True)

            if submitted:
                if not f_ticker or not f_launch_time:
                    st.error("❌ 品种代码 (Ticker) 和 启动时间 不能为空！")
                else:
                    htf_path = editing_case.get("img_htf", "") if editing_case else ""
                    ltf_path = editing_case.get("img_ltf", "") if editing_case else ""

                    if up_htf:
                        htf_path = _save_uploaded_image(up_htf, f"{f_ticker}_htf")
                    if up_ltf:
                        ltf_path = _save_uploaded_image(up_ltf, f"{f_ticker}_ltf")

                    custom_inds_list = [x.strip() for x in f_custom_inds_str.split(",") if x.strip()]

                    case_payload = {
                        "id": editing_case.get("id") if editing_case else f"case_{int(time.time()*1000)}",
                        "ticker": f_ticker,
                        "name": f_name or f_ticker,
                        "category": f_cat,
                        "launch_time": f_launch_time,
                        "direction": f_direction,
                        "trend_scale": f_trend_scale or "大级别趋势启动",
                        "indicators": new_selected_inds,
                        "custom_indicators": custom_inds_list,
                        "notes": f_notes,
                        "img_htf": htf_path,
                        "img_ltf": ltf_path,
                    }

                    if editing_case and "created_at" in editing_case:
                        case_payload["created_at"] = editing_case["created_at"]

                    ok = storage.save_case_study(case_payload)
                    if ok:
                        st.success(f"✅ 案例 {f_ticker} ({f_launch_time}) 已成功保存！")
                        st.session_state.pop("case_edit_id", None)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ 保存失败，请检查写入权限。")

    # ────────────────────────────────────────────────────────────────
    # TAB 4: 🤖 AI 复盘 Prompt 生成器与数据备份
    # ────────────────────────────────────────────────────────────────
    with tab_ai_export:
        st.markdown("### 🤖 一键生成 AI 复盘 Prompt")
        st.caption("系统自动将当前录入的所有品种启动时间、多周期特征与指标状态，组装为高标准的复盘指令，复制后直接发到聊天框中即可开展深度挖掘。")

        prompt_lines = [
            "# 📈 多品种长周期趋势启动点（周图/月图）横向深度复盘任务",
            "",
            "## 背景与目标",
            "我收集了一批在周图/月图级别走出长期大趋势行情的真实启动点案例。请你根据各品种的**启动时间点**与**多周期形态**，进行横向归纳与算法级对比：",
            "1. 对比分析哪些技术指标能最先、最敏锐且最准确地捕捉到周图/月图大趋势要启动的信号（过滤假突破）。",
            "2. 归纳启动前夕的「充要共性特征」（如均线结构、波动率收缩、动能背驰、量价假动作等）。",
            "3. 给出从大级别过滤 (月/周图) 到小级别精确切入 (天图/4H) 的多周期共振指标策略组合建议与量化规则。",
            "",
            "## 案例样本库数据",
        ]

        for i, c in enumerate(cases, 1):
            tk = c.get("ticker")
            nm = c.get("name")
            lt = c.get("launch_time")
            d = c.get("direction")
            ts = c.get("trend_scale")
            inds = ", ".join(c.get("indicators", [])) or "无"
            cinds = ", ".join(c.get("custom_indicators", [])) or "无"
            nt = c.get("notes", "无")
            prompt_lines.append(f"### 案例 {i}: {tk} ({nm})")
            prompt_lines.append(f"- **启动时间**: {lt}")
            prompt_lines.append(f"- **趋势方向**: {d}")
            prompt_lines.append(f"- **启动后趋势级别**: {ts}")
            prompt_lines.append(f"- **勾选的启动指标**: {inds}")
            if cinds != "无":
                prompt_lines.append(f"- **专属特征/自定义指标**: {cinds}")
            prompt_lines.append(f"- **微观复盘观察**: {nt}")
            prompt_lines.append("")

        prompt_lines.extend([
            "## 深度复盘要求",
            "请基于上述所有品种在对应启动时间段的历史盘面特征，逐一解答以下问题：",
            "1. **【公约数归纳】**：在这批案例启动前 1~3 个月，周线/月线级别出现概率最高的前三大共性指标形态是什么？",
            "2. **【小周期穿透】**：切换到日线或 4 小时图时，启动K线出现的前夕，微观上最常见的买入触发信号是什么？（例如二次探底、假跌破Spring、布林带张口确认等）",
            "3. **【假突破过滤】**：大级别启动往往伴随震荡洗盘，哪些指标能最有效过滤掉假启动和诱多/诱空陷阱？",
            "4. **【落地策略规则】**：请总结出一套可以直接编写为扫描脚本或盯盘规则的「趋势启动三步验证法」（大周期条件 + 中周期形态 + 小周期触发）。"
        ])

        full_prompt_text = "\n".join(prompt_lines)

        st.text_area("📋 生成的 AI 复盘 Prompt 内容 (可直接复制):", full_prompt_text, height=320)

        c_exp1, c_exp2 = st.columns(2)
        with c_exp1:
            json_str = json.dumps(cases, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 导出完整案例库为 JSON 文件",
                data=json_str,
                file_name=f"case_studies_backup_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
                use_container_width=True
            )
        with c_exp2:
            csv_rows = []
            for c in cases:
                csv_rows.append({
                    "ticker": c.get("ticker"),
                    "name": c.get("name"),
                    "category": c.get("category"),
                    "launch_time": c.get("launch_time"),
                    "direction": c.get("direction"),
                    "trend_scale": c.get("trend_scale"),
                    "indicators": "; ".join(c.get("indicators", [])),
                    "custom_indicators": "; ".join(c.get("custom_indicators", [])),
                    "notes": c.get("notes")
                })
            df_export = pd.DataFrame(csv_rows)
            csv_buf = io.StringIO()
            df_export.to_csv(csv_buf, index=False, encoding="utf-8-sig")
            st.download_button(
                label="📊 导出案例库为 CSV 表格",
                data=csv_buf.getvalue(),
                file_name=f"case_studies_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
