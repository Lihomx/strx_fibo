# 品种库分组过滤计划

## 🔍 问题分析

**用户期望的流程**：
1. 在批量操作区的下拉框中选择一个分组（如"金融服务"）
2. 下方品种列表**自动过滤**，只显示该分组内的品种
3. 在过滤后的视图中方便地查看、编辑、删除组内品种

**当前实际行为**：
- 下拉框选择分组后，下方列表仍然显示**全部 1749 个品种**
- 分组选择器的唯一作用是"把勾选的品种分配到该组"
- 用户完全看不到选中分组里有哪些品种

**根因**：第 339-342 行的过滤逻辑只考虑了搜索关键字 `kw`，没有读取分组选择器的值来过滤。

---

## 📋 修改计划

### 改动范围
仅修改 `page_symbols.py` 的 **Tab 1「品种库明细」** 部分（约第 290-435 行）。

### 具体步骤

#### 步骤 1：将分组选择器从"批量操作区"提升到搜索过滤区域

将现有的分组下拉框改为**双功能**：
- 选择"全部品种"：显示品种库所有品种（当前行为）
- 选择某个分组：**过滤列表仅显示该分组内的品种**

**改动位置**：第 330-342 行（搜索与分页展示区域）

```python
# 搜索 + 分组过滤 + 排序
col_grp_filter, col_search, col_sort, col_page_size = st.columns([2, 3, 2, 1])

with col_grp_filter:
    grp_filter_options = ["📋 全部品种"] + [g["name"] for g in groups]
    grp_filter_sel = st.selectbox("按分组筛选", grp_filter_options, key="sym_grp_filter_sel")

with col_search:
    kw = st.text_input("🔍 搜索品种", ...)

# 过滤逻辑：先按分组过滤，再按关键字过滤
filtered = symbols
if grp_filter_sel != "📋 全部品种":
    target_grp = next((g for g in groups if g["name"] == grp_filter_sel), None)
    if target_grp:
        grp_ticker_set = set(target_grp.get("tickers", []))
        filtered = [s for s in filtered if s["ticker"] in grp_ticker_set]

if kw:
    filtered = [s for s in filtered if kw in s["ticker"] or kw in s["name"]]
```

#### 步骤 2：在过滤到分组视图时，调整批量操作区的行为

当用户选中了某个分组时：
- **批量操作区的"删除"按钮**改为"从该分组移除"（而不是从品种库删除）
- 新增一个"➕ 添加品种到该分组"的快捷入口
- 保持"分配到其他分组"功能不变

```python
# 当处于分组过滤视图时
if grp_filter_sel != "📋 全部品种":
    # "批量删除"变为"从分组移除"
    if st.button("❌ 从该分组移除选中品种"):
        storage.remove_tickers_from_group(target_id, list(selected_set))
```

#### 步骤 3：列表行中的操作按钮也联动

当过滤到某个分组时：
- 每行末尾的 🗑️ 按钮改为"❌ 移出分组"（而非删除品种）
- 让用户在列表中直接操作

---

## 📌 对比：改动前 vs 改动后

| 功能 | 改动前 | 改动后 |
|------|--------|--------|
| 分组过滤 | ❌ 没有 | ✅ 下拉选组后列表只显示组内品种 |
| 查看分组内容 | 需要切 Tab 2 | ✅ Tab 1 直接选组查看 |
| 从分组移除 | 需要切 Tab 2 逐个❌ | ✅ Tab 1 批量勾选 + 一键移除 |
| 添加到分组 | 选品种 → 选组 → 确认（三步） | ✅ 选组过滤 → 显示非组内品种 → 勾选添加 |
| 全部品种视图 | 默认就是 | ✅ 选"全部品种"恢复 |

---

## ⚠️ 注意事项

- **不改 Tab 2**：Tab 2 的分组编辑面板保留不动（已有手动添加、搜索选择、CSV导入功能）
- **不改 storage.py**：所有需要的存储 API 已存在
- **向下兼容**：默认选"全部品种"时，行为与改动前完全一致
