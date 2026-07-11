"""
page_symbols.py — 自定义品种库与分组管理
=========================================
实现功能：
  1. 品种库管理：支持手动添加单个品种，或上传 CSV/Excel 文件批量导入。
  2. 自定义分组：创建、重命名、删除分组，维护各组的品种列表。
  3. 批量操作：支持勾选品种批量分配到分组、批量从分组移除、批量删除。
  4. 响应式与玻璃化设计：适配桌面与移动端。
"""

import streamlit as st
import pandas as pd
import time
import io
import re
from datetime import datetime
import storage

# ── 玻璃化 & 深色风格 CSS 注入 ──
def _inject_symbols_css():
    st.markdown("""
    <style>
    /* 玻璃化容器 */
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
    }
    
    /* 列表表头 */
    .symbols-hdr {
        display: grid;
        grid-template-columns: 50px 140px 1fr 100px 140px 80px;
        gap: 8px;
        padding: 8px 12px;
        background: rgba(255, 255, 255, 0.08);
        border-bottom: 2px solid rgba(255, 255, 255, 0.15);
        border-radius: 8px 8px 0 0;
        font-size: 13px;
        font-weight: 600;
        align-items: center;
    }
    
    .symbols-body {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-top: none;
        border-radius: 0 0 8px 8px;
        margin-bottom: 16px;
        overflow: hidden;
    }
    
    .symbols-row {
        display: grid;
        grid-template-columns: 50px 140px 1fr 100px 140px 80px;
        gap: 8px;
        padding: 6px 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        font-size: 13px;
        align-items: center;
    }
    
    .symbols-row:hover {
        background: rgba(255, 255, 255, 0.03);
    }
    
    /* 移动端响应式 */
    @media (max-width: 768px) {
        .symbols-hdr {
            grid-template-columns: 40px 110px 1fr 80px;
            font-size: 11px;
        }
        .symbols-hdr .hide-mobile, .symbols-row .hide-mobile {
            display: none !important;
        }
        .symbols-row {
            grid-template-columns: 40px 110px 1fr 80px;
            font-size: 11px;
        }
    }
    </style>
    """, unsafe_allow_html=True)


def _parse_uploaded_file(uploaded_file) -> list:
    """解析上传的 CSV 或 Excel，提取 ticker & name"""
    if uploaded_file is None:
        return []
    
    fname = uploaded_file.name.lower()
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif fname.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("⚠️ 仅支持 CSV, XLS, XLSX 格式文件")
            return []
    except Exception as e:
        st.error(f"❌ 读取文件失败: {e}")
        if "openpyxl" in str(e) or "xlrd" in str(e):
            st.info("💡 提示: 您的运行环境可能缺少 Excel 解析依赖，建议使用 CSV 格式上传")
        return []

    # 寻找可能的代码和名称列
    col_mapping = {
        "ticker": ["ticker", "代码", "symbol", "code", "股票代码", "品种代码"],
        "name": ["name", "名称", "title", "name", "股票名称", "品种名称"]
    }
    
    ticker_col = None
    name_col = None
    
    # 查找 ticker 列
    for col in df.columns:
        if str(col).lower().strip() in col_mapping["ticker"]:
            ticker_col = col
            break
            
    # 查找 name 列
    for col in df.columns:
        if str(col).lower().strip() in col_mapping["name"]:
            name_col = col
            break
            
    # 如果没找到，默认取第一列为 ticker，第二列（如有）为 name
    if ticker_col is None and len(df.columns) > 0:
        ticker_col = df.columns[0]
    if name_col is None and len(df.columns) > 1:
        name_col = df.columns[1]
        
    if ticker_col is None:
        st.error("⚠️ 未在文件中找到包含品种代码的列")
        return []
        
    results = []
    for _, row in df.iterrows():
        tk = str(row[ticker_col]).strip()
        if pd.isna(row[ticker_col]) or not tk or tk.lower() in ("nan", "none", "null"):
            continue
        # 清洗 ticker 代码
        tk = tk.upper()
        # 处理可能被 Excel 误识别为数字的代码，比如 A股 600519 变成 600519.0
        if tk.endswith(".0"):
            tk = tk[:-2]
        
        nm = str(row[name_col]).strip() if name_col is not None and not pd.isna(row[name_col]) else tk
        if nm.lower() in ("nan", "none", "null"):
            nm = tk
            
        results.append({"ticker": tk, "name": nm})
        
    return results


def render():
    _inject_symbols_css()
    st.markdown("## 💎 自定义品种库与分组")
    st.markdown(
        "<p style='color:#6b7280;font-size:13px;margin-top:-8px'>"
        "在这里建立属于您的专属云端品种库，自定义分组，并在各扫描器中自由选择对应的分组进行即时/定时扫描。"
        "</p>",
        unsafe_allow_html=True
    )
    
    # ── 导入系统内置品种和分组 ──
    with st.expander("📦 导入系统内置的 1985 个品种和 64 个分组"):
        st.markdown(
            "如果您是第一次使用，或者想对系统默认的 64 个分类分组进行**修改、删除、增加品种**，"
            "可以点击下方按钮将它们一键导入到您的自定义库中。"
        )
        col_import_builtin, _ = st.columns([2, 2])
        with col_import_builtin:
            if st.button("📥 一键导入内置 64 组 / 1985 品种", key="import_builtin_btn", type="secondary", use_container_width=True):
                import assets
                import uuid
                progress_text = st.empty()
                progress_text.info("正在导入，请稍候...")
                
                builtin_groups = assets.ASSET_GROUPS
                
                # 1. 批量加载已有的 symbols，去重并添加
                existing_symbols = storage.load_symbols()
                existing_tickers = {s["ticker"] for s in existing_symbols}
                
                all_added = 0
                for g_name, g_assets in builtin_groups.items():
                    for tk, (nm, cat) in g_assets.items():
                        tk_upper = tk.strip().upper()
                        if tk_upper and tk_upper not in existing_tickers:
                            existing_symbols.append({
                                "ticker": tk_upper,
                                "name": nm.strip() or tk_upper,
                                "source": "built_in",
                                "added_at": storage._now_str()
                            })
                            existing_tickers.add(tk_upper)
                            all_added += 1
                
                # 批量保存 symbols (仅写盘 & 同步一次)
                storage.save_symbols(existing_symbols)
                
                # 2. 批量加载并填充分组
                existing_groups = storage.load_symbol_groups()
                
                for g_name, g_assets in builtin_groups.items():
                    # 查找或新建组
                    target_g = next((g for g in existing_groups if g["name"] == g_name), None)
                    if not target_g:
                        target_g = {
                            "id": str(uuid.uuid4())[:8],
                            "name": g_name,
                            "tickers": [],
                            "created_at": storage._now_str()
                        }
                        existing_groups.append(target_g)
                    
                    # 合并 tickers
                    t_set = set(target_g.get("tickers", []))
                    for tk in g_assets.keys():
                        tk_upper = tk.strip().upper()
                        if tk_upper:
                            t_set.add(tk_upper)
                    target_g["tickers"] = list(t_set)
                
                # 批量保存 groups (仅写盘 & 同步一次)
                storage.save_symbol_groups(existing_groups)
                
                progress_text.success(f"✅ 成功导入 {all_added} 个新内置品种，并同步了 {len(builtin_groups)} 个分组！")
                time.sleep(1)
                st.rerun()

    # ── 初始化分类/选择 Session State ──
    if "symbols_selected" not in st.session_state:
        st.session_state["symbols_selected"] = set()
        
    tab1, tab2 = st.tabs(["📋 品种库明细", "📂 分组管理"])
    
    # 加载底层数据
    symbols = storage.load_symbols()
    groups = storage.load_symbol_groups()
    
    with tab1:
        st.markdown("### 🔍 品种库管理")
        
        # 1. 顶部操作卡：新增与批量导入
        col_manual, col_import = st.columns([1, 1])
        
        with col_manual:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown("**➕ 手动添加单个品种**")
            m_ticker = st.text_input("代码 (如: AAPL, BTC-USD, 600519.SS)", key="sym_manual_tk").strip().upper()
            m_name = st.text_input("名称 (如: 苹果, 比特币, 贵州茅台)", key="sym_manual_nm").strip()
            if st.button("➕ 添加到品种库", key="sym_manual_add_btn", type="primary", use_container_width=True):
                if not m_ticker:
                    st.error("请输入品种代码")
                else:
                    if storage.add_symbol(m_ticker, m_name, source="manual"):
                        st.success(f"✅ 品种 {m_ticker} 添加成功")
                        st.session_state.pop("sym_manual_tk", None)
                        st.session_state.pop("sym_manual_nm", None)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ 添加失败，可能 {m_ticker} 已存在于品种库中")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_import:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown("**📥 批量导入品种**")
            st.caption("文件格式：首列为代码 (ticker)，次列为名称 (name)。")
            uploaded_file = st.file_uploader("选择 CSV / Excel 文件", type=["csv", "xls", "xlsx"], key="sym_uploader")
            if uploaded_file is not None:
                parsed = _parse_uploaded_file(uploaded_file)
                if parsed:
                    st.success(f"已识别 {len(parsed)} 个品种")
                    if st.button(f"🚀 导入这 {len(parsed)} 个品种", key="sym_import_confirm_btn", type="primary", use_container_width=True):
                        added_cnt = 0
                        for item in parsed:
                            if storage.add_symbol(item["ticker"], item["name"], source="csv_import"):
                                added_cnt += 1
                        st.success(f"✅ 成功导入 {added_cnt} 个新品种！")
                        time.sleep(1)
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 2. 搜索与筛选区
        st.markdown("### 🔍 搜索与筛选")
        col_grp_filter, col_search, col_sort, col_page_size = st.columns([2.5, 2.5, 1.8, 1.2])
        
        with col_grp_filter:
            grp_filter_options = ["📋 全部品种库"] + [g["name"] for g in groups]
            grp_filter_val = st.selectbox("按分组筛选", grp_filter_options, key="sym_grp_filter_sel")
            
        with col_search:
            kw = st.text_input("🔍 搜索关键字", placeholder="输入代码或名称关键字...", key="sym_search_kw").strip().upper()
            
        with col_sort:
            sort_mode = st.selectbox("排序规则", ["按添加时间倒序", "按代码 A-Z", "按来源"], key="sym_sort_sel")
            
        with col_page_size:
            page_size = st.selectbox("单页显示", [20, 50, 100, 200], key="sym_ps_sel")
            
        # 根据分组筛选
        filtered = symbols
        current_filter_grp_id = None
        current_filter_grp_name = None
        if grp_filter_val != "📋 全部品种库":
            target_filter_grp = next((g for g in groups if g["name"] == grp_filter_val), None)
            if target_filter_grp:
                current_filter_grp_id = target_filter_grp["id"]
                current_filter_grp_name = target_filter_grp["name"]
                grp_tickers = set(target_filter_grp.get("tickers", []))
                filtered = [s for s in filtered if s["ticker"] in grp_tickers]
                
        # 根据关键字筛选
        if kw:
            filtered = [s for s in filtered if kw in s["ticker"].upper() or kw in s["name"].upper()]
            
        # 排序
        if sort_mode == "按代码 A-Z":
            filtered = sorted(filtered, key=lambda x: x["ticker"])
        elif sort_mode == "按来源":
            filtered = sorted(filtered, key=lambda x: x.get("source", ""))
        else:
            filtered = list(reversed(filtered))
            
        # 3. 批量操作工具条
        st.markdown("### 🛠️ 批量操作区")
        selected_set = st.session_state["symbols_selected"]
        
        col_sel_stat, col_sel_act, col_sel_del = st.columns([1.5, 3, 2.5])
        with col_sel_stat:
            st.markdown(f"已勾选 **{len(selected_set)}** 个品种")
            
        with col_sel_act:
            if current_filter_grp_id:
                # 处于特定分组视图，批量操作是“批量移出当前组”
                if st.button("❌ 从当前分组批量移出", key="sym_bulk_remove_grp_btn", type="secondary", use_container_width=True):
                    if not selected_set:
                        st.warning("请先勾选品种")
                    else:
                        storage.remove_tickers_from_group(current_filter_grp_id, list(selected_set))
                        st.success(f"✅ 已成功从分组 [{current_filter_grp_name}] 中移出 {len(selected_set)} 个品种")
                        st.session_state["symbols_selected"] = set()
                        time.sleep(1)
                        st.rerun()
            else:
                # 处于“全部品种库”视图，批量分配到分组
                if groups:
                    grp_names = {g["name"]: g["id"] for g in groups}
                    target_grp_name = st.selectbox("添加到分组", ["— 选择分组 —"] + list(grp_names.keys()), key="sym_assign_grp_sel")
                    if target_grp_name != "— 选择分组 —":
                        target_id = grp_names[target_grp_name]
                        if st.button("📥 确认分配到该组", key="sym_assign_confirm_btn", use_container_width=True):
                            if not selected_set:
                                st.warning("请先在下方列表中勾选品种")
                            else:
                                storage.add_tickers_to_group(target_id, list(selected_set))
                                st.success(f"✅ 已成功分配 {len(selected_set)} 个品种到分组 [{target_grp_name}]")
                                st.session_state["symbols_selected"] = set()
                                time.sleep(1)
                                st.rerun()
                else:
                    st.info("💡 请先在「分组管理」中创建分组")
                    
        with col_sel_del:
            # 始终允许从品种库中彻底删除品种
            if st.button("🗑️ 从品种库彻底删除选中", key="sym_bulk_del_btn", type="secondary", use_container_width=True):
                if not selected_set:
                    st.warning("请先勾选品种")
                else:
                    for tk in list(selected_set):
                        storage.remove_symbol(tk)
                    st.success(f"🗑️ 已成功从品种库中移除 {len(selected_set)} 个品种")
                    st.session_state["symbols_selected"] = set()
                    time.sleep(1)
                    st.rerun()
                    
        st.markdown("---")
        
        total_f = len(filtered)
        n_pages = max(1, (total_f + page_size - 1) // page_size)
        
        page_idx = st.number_input(f"页码 (共 {n_pages} 页，{total_f} 个品种)", min_value=1, max_value=n_pages, value=1, key="sym_page_idx") - 1
        page_items = filtered[page_idx * page_size : (page_idx + 1) * page_size]
        
        # 全选当页 / 取消全选
        col_pg_all, col_pg_none, _ = st.columns([2, 2, 4])
        with col_pg_all:
            if st.button(f"☑️ 全选当前页 ({len(page_items)} 支)", key="sym_pg_all_btn"):
                for item in page_items:
                    selected_set.add(item["ticker"])
                st.session_state["symbols_selected"] = selected_set
                st.rerun()
        with col_pg_none:
            if st.button("🔲 取消全选", key="sym_pg_none_btn"):
                for item in page_items:
                    selected_set.discard(item["ticker"])
                st.session_state["symbols_selected"] = selected_set
                st.rerun()
                
        # 4. 品种列表渲染
        if not page_items:
            st.info("💡 暂无匹配的品种记录。")
        else:
            # 列表布局
            st.markdown("""
            <div class="symbols-hdr">
              <span>选择</span>
              <span>代码</span>
              <span>名称</span>
              <span class="hide-mobile">来源</span>
              <span class="hide-mobile">添加时间</span>
              <span>操作</span>
            </div>
            <div class="symbols-body">
            """, unsafe_allow_html=True)
            
            for i, item in enumerate(page_items):
                tk = item["ticker"]
                nm = item["name"]
                src = item.get("source", "manual")
                added_at = item.get("added_at", "—")
                is_checked = tk in selected_set
                
                # 区分奇偶行背景
                row_bg = "background:rgba(255,255,255,0.02)" if i % 2 == 0 else "background:transparent"
                if is_checked:
                    row_bg = "background:rgba(59,130,246,0.12)"
                    
                st.markdown(f'<div class="symbols-row" style="{row_bg}">', unsafe_allow_html=True)
                
                col_chk, col_tk, col_nm, col_src, col_time, col_act = st.columns([50, 140, 300, 100, 140, 80], gap="small")
                
                with col_chk:
                    new_chk = st.checkbox("", value=is_checked, key=f"sym_chk_{tk}_{i}", label_visibility="collapsed")
                    if new_chk != is_checked:
                        if new_chk:
                            selected_set.add(tk)
                        else:
                            selected_set.discard(tk)
                        st.session_state["symbols_selected"] = selected_set
                        st.rerun()
                        
                with col_tk:
                    st.markdown(f'<span style="font-family:monospace;font-weight:600">{tk}</span>', unsafe_allow_html=True)
                with col_nm:
                    st.markdown(f'<span>{nm}</span>', unsafe_allow_html=True)
                with col_src:
                    st.markdown(f'<span class="hide-mobile" style="color:#9ca3af;font-size:11px">{src}</span>', unsafe_allow_html=True)
                with col_time:
                    st.markdown(f'<span class="hide-mobile" style="color:#9ca3af;font-size:11px">{added_at}</span>', unsafe_allow_html=True)
                with col_act:
                    if current_filter_grp_id:
                        # 提供 ❌ 移出该分组
                        if st.button("❌", key=f"sym_rm_grp_{tk}_{i}", help=f"从分组 [{current_filter_grp_name}] 移出 {nm}"):
                            storage.remove_tickers_from_group(current_filter_grp_id, [tk])
                            selected_set.discard(tk)
                            st.session_state["symbols_selected"] = selected_set
                            st.success(f"已移出分组: {nm}")
                            time.sleep(0.5)
                            st.rerun()
                    else:
                        # 提供 🗑️ 彻底删除
                        if st.button("🗑️", key=f"sym_del_{tk}_{i}", help=f"从品种库彻底删除 {nm}"):
                            storage.remove_symbol(tk)
                            selected_set.discard(tk)
                            st.session_state["symbols_selected"] = selected_set
                            st.success(f"已删除 {nm}")
                            time.sleep(0.5)
                            st.rerun()
                        
                st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown("### 📂 自定义分组管理")
        
        # 1. 创建新分组
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        col_gname, col_gbtn = st.columns([3, 1])
        with col_gname:
            new_grp_name = st.text_input("新建分组名称 (如: 美股半导体, A股大蓝筹)", key="new_grp_name_input").strip()
        with col_gbtn:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("➕ 创建分组", key="create_grp_btn", type="primary", use_container_width=True):
                if not new_grp_name:
                    st.error("请输入分组名称")
                else:
                    new_id = storage.add_symbol_group(new_grp_name)
                    if new_id:
                        st.success(f"✅ 分组 [{new_grp_name}] 创建成功！")
                        st.session_state.pop("new_grp_name_input", None)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ 创建失败，名称已存在")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 2. 分组列表与管理
        if not groups:
            st.info("💡 尚未创建任何自定义分组。请在上方输入名称并点击「创建分组」。")
        else:
            from collections import defaultdict
            
            # 按前缀进行分组归类 (e.g. "🇨🇳 A股 - 银行业" -> "🇨🇳 A股" : "银行业")
            cat_groups = defaultdict(list)
            for g in groups:
                parts = g["name"].split(" - ", 1)
                if len(parts) == 2:
                    cat = parts[0].strip()
                else:
                    cat = "📌 其它/自定义"
                cat_groups[cat].append(g)
            
            st.markdown("**📋 按分类查看/管理分组：**")
            
            # 获取当前选中的编辑分组 ID
            active_id = st.session_state.get("active_edit_group_id")
            
            # 渲染各个大分类折叠栏
            for cat, cat_grp_list in sorted(cat_groups.items(), key=lambda x: (x[0] == "📌 其它/自定义", x[0])):
                n_grp = len(cat_grp_list)
                # 默认折叠，标题栏更清晰
                with st.expander(f"📁 {cat} （共 {n_grp} 个分组）"):
                    # 使用 3 列布局
                    _cols = st.columns(3)
                    for idx, g in enumerate(sorted(cat_grp_list, key=lambda x: x["name"])):
                        g_id = g["id"]
                        g_name = g["name"]
                        short_name = g_name.split(" - ", 1)[-1] if " - " in g_name else g_name
                        g_tickers = g.get("tickers", [])
                        
                        is_active = (active_id == g_id)
                        btn_label = f"🎯 {short_name} ({len(g_tickers)})"
                        
                        with _cols[idx % 3]:
                            if st.button(
                                btn_label, 
                                key=f"sel_grp_btn_{g_id}", 
                                type="primary" if is_active else "secondary",
                                use_container_width=True
                            ):
                                st.session_state["active_edit_group_id"] = g_id
                                st.rerun()
            
            st.markdown("<hr style='margin:20px 0; border-color:rgba(255,255,255,0.1)'>", unsafe_allow_html=True)
            
            # 3. 选定分组的具体编辑面板
            active_grp = next((g for g in groups if g["id"] == active_id), None) if active_id else None
            
            if not active_grp:
                st.info("💡 请在上方分类折叠栏中展开并点击任一子分组进行编辑与管理。")
            else:
                g_id = active_grp["id"]
                g_name = active_grp["name"]
                g_tickers = active_grp.get("tickers", [])
                g_tickers_set = set(g_tickers)
                
                st.markdown(f'<div class="glass-card" style="border: 1px solid rgba(59,130,246,0.3)">', unsafe_allow_html=True)
                st.markdown(f"#### ⚙️ 正在配置分组: `{g_name}`")
                
                # 重命名与删除
                col_ren_inp, col_ren_btn, col_del_btn = st.columns([3, 1, 1])
                with col_ren_inp:
                    rename_val = st.text_input("修改分组名称", value=g_name, key=f"grp_active_rename_val").strip()
                with col_ren_btn:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("💾 保存修改", key=f"grp_active_save_btn", type="primary", use_container_width=True):
                        if rename_val and rename_val != g_name:
                            if storage.rename_symbol_group(g_id, rename_val):
                                st.success("重命名成功！")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("重命名失败，名称可能已存在")
                with col_del_btn:
                    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                    if st.button("🗑️ 删除该组", key=f"grp_active_del_btn", type="secondary", use_container_width=True):
                        storage.delete_symbol_group(g_id)
                        st.session_state.pop("active_edit_group_id", None)
                        st.success(f"已成功删除分组 [{g_name}]")
                        time.sleep(0.5)
                        st.rerun()
                
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
                st.markdown("---")
                st.markdown("**➕ 向分组添加品种**")

                # ── 方式一：手动输入代码直接添加 ──
                with st.expander("✏️ 手动输入代码添加", expanded=True):
                    col_tk_in, col_nm_in, col_add_btn = st.columns([2, 2, 1])
                    with col_tk_in:
                        manual_tk = st.text_input(
                            "品种代码", placeholder="如: AAPL, 600519.SS, BTC-USD",
                            key="grp_manual_tk_input"
                        ).strip().upper()
                    with col_nm_in:
                        manual_nm = st.text_input(
                            "品种名称（可选）", placeholder="如: 苹果, 贵州茅台",
                            key="grp_manual_nm_input"
                        ).strip()
                    with col_add_btn:
                        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                        if st.button("➕ 添加", key="grp_manual_add_btn", type="primary", use_container_width=True):
                            if not manual_tk:
                                st.error("请输入品种代码")
                            elif manual_tk in g_tickers_set:
                                st.warning(f"{manual_tk} 已在该分组中")
                            else:
                                # 同时加入品种库（若不存在）和分组
                                storage.add_symbol(manual_tk, manual_nm or manual_tk, source="manual")
                                storage.add_tickers_to_group(g_id, [manual_tk])
                                st.success(f"✅ 已将 {manual_tk} 添加到分组 [{g_name}]")
                                time.sleep(0.5)
                                st.rerun()

                    # 支持逗号/换行批量输入
                    batch_input = st.text_area(
                        "批量输入代码（逗号或换行分隔）",
                        placeholder="例：AAPL, TSLA, NVDA\n或每行一个",
                        key="grp_batch_tk_input",
                        height=80
                    )
                    if st.button("📥 批量添加以上代码", key="grp_batch_add_btn", use_container_width=True):
                        raw_list = re.split(r"[,\n]+", batch_input)
                        to_add = [t.strip().upper() for t in raw_list if t.strip()]
                        new_ones = [t for t in to_add if t not in g_tickers_set]
                        if not new_ones:
                            st.warning("所有输入代码均已在分组中，无新增")
                        else:
                            for tk_item in new_ones:
                                storage.add_symbol(tk_item, tk_item, source="manual")
                            storage.add_tickers_to_group(g_id, new_ones)
                            st.success(f"✅ 已添加 {len(new_ones)} 个品种到 [{g_name}]（跳过重复 {len(to_add)-len(new_ones)} 个）")
                            time.sleep(0.5)
                            st.rerun()

                # ── 方式二：从现有品种库搜索并选择 ──
                with st.expander("🔎 从品种库中搜索选择"):
                    lib_kw = st.text_input(
                        "搜索品种库", placeholder="输入代码或名称关键字...",
                        key="grp_lib_search_kw"
                    ).strip().upper()
                    # 过滤品种库，排除已在分组中的
                    lib_filtered = [
                        s for s in symbols
                        if s["ticker"] not in g_tickers_set
                        and (not lib_kw or lib_kw in s["ticker"].upper() or lib_kw in s["name"].upper())
                    ][:200]  # 最多展示200个避免过慢
                    if not lib_filtered:
                        st.caption("所有品种库品种已在该分组中，或搜索结果为空。")
                    else:
                        options_map = {f"{s['ticker']}  {s['name']}": s["ticker"] for s in lib_filtered}
                        selected_labels = st.multiselect(
                            f"选择品种（共 {len(lib_filtered)} 个可选）",
                            list(options_map.keys()),
                            key="grp_lib_multisel",
                            placeholder="从下拉列表选择或输入代码搜索..."
                        )
                        if selected_labels:
                            chosen_tickers = [options_map[lb] for lb in selected_labels]
                            if st.button(
                                f"📥 确认将以上 {len(chosen_tickers)} 个品种添加到分组",
                                key="grp_lib_confirm_add_btn",
                                type="primary",
                                use_container_width=True
                            ):
                                storage.add_tickers_to_group(g_id, chosen_tickers)
                                st.success(f"✅ 已将 {len(chosen_tickers)} 个品种添加到 [{g_name}]")
                                time.sleep(0.5)
                                st.rerun()

                # ── 方式三：CSV 批量导入 ──
                with st.expander("📥 上传 CSV / Excel 批量导入"):
                    uploaded_grp_file = st.file_uploader("选择 CSV / Excel 文件", type=["csv", "xls", "xlsx"], key=f"grp_active_uploader")
                    if uploaded_grp_file is not None:
                        parsed_grp = _parse_uploaded_file(uploaded_grp_file)
                        if parsed_grp:
                            st.success(f"已识别 {len(parsed_grp)} 个品种")
                            if st.button(f"🚀 确认导入这 {len(parsed_grp)} 个品种", key=f"grp_active_import_confirm", type="primary", use_container_width=True):
                                added_cnt = 0
                                tickers_to_add = []
                                for item in parsed_grp:
                                    storage.add_symbol(item["ticker"], item["name"], source="csv_import")
                                    tickers_to_add.append(item["ticker"])
                                    added_cnt += 1
                                storage.add_tickers_to_group(g_id, tickers_to_add)
                                st.success(f"✅ 成功导入并添加 {added_cnt} 个品种！")
                                time.sleep(1)
                                st.rerun()

                st.markdown("---")
                
                # 品种明细与移出功能
                st.markdown(f"**组内品种明细 (共 {len(g_tickers)} 个品种)**")
                if not g_tickers:
                    st.caption("📂 当前分组为空。请用上方方式添加品种。")
                else:
                    # 搜索过滤组内品种
                    grp_kw = st.text_input("🔍 搜索组内品种", placeholder="输入代码关键字...", key="grp_inner_search").strip().upper()
                    visible_tickers = [tk for tk in g_tickers if not grp_kw or grp_kw in tk] if grp_kw else g_tickers

                    # 批量移出
                    col_rmall, _ = st.columns([2, 4])
                    with col_rmall:
                        if st.button(f"🗑️ 清空整个分组 ({len(g_tickers)} 个)", key="grp_clear_all_btn", type="secondary", use_container_width=True):
                            storage.remove_tickers_from_group(g_id, g_tickers)
                            st.success(f"已清空分组 [{g_name}] 中的所有品种")
                            time.sleep(0.5)
                            st.rerun()

                    sub_cols = st.columns(4)
                    for idx, tk in enumerate(visible_tickers):
                        sym_info = next((s for s in symbols if s["ticker"] == tk), None)
                        nm_hint = sym_info["name"] if sym_info else tk
                        with sub_cols[idx % 4]:
                            st.markdown(
                                f'<div style="background:rgba(255,255,255,0.03);padding:6px;border-radius:6px;'
                                f'margin-bottom:6px;">'
                                f'<span style="font-family:monospace;font-size:12px;font-weight:600">{tk}</span><br>'
                                f'<span style="font-size:10px;color:#9ca3af">{nm_hint}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                            if st.button("❌ 移除", key=f"grp_active_rm_{tk}_{idx}", help=f"从该组移除 {tk}"):
                                storage.remove_tickers_from_group(g_id, [tk])
                                st.success(f"已从组 [{g_name}] 移除 {tk}")
                                time.sleep(0.5)
                                st.rerun()
                                
                st.markdown('</div>', unsafe_allow_html=True)
