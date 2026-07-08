# 热门品种 (Hot Assets) 页面添加需求与设计方案

本方案旨在系统中新增一个“热门品种”页面（Hot Assets Library），用于独立管理中国（A股/港股）和美股的热门股票。由于热门股票的构成每个月变化不大，但支持用户随时进行增加、删除、分类标记和复盘笔记。

## User Review Required

> [!IMPORTANT]
> **1. 是否沿用自选收藏夹的分类体系？**
> 热门品种的分类（如“A股热门”、“美股热门”等）是否需要独立的分类配置文件（如 `data_hl_categories.json`），还是可以和自选收藏夹共用同一个分类配置？
> *   *本方案建议*：采用独立的 `data_hl_categories.json` 进行管理，这样“自选”与“热门”的分类节点不会互相干扰，且操作完全独立。
>
> **2. 是否同步上传云端？**
> *   *本方案建议*：将热门品种的数据文件 `data_hotlist.json`、分类文件 `data_hl_categories.json` 以及存档文件 `data_hotlist_archive.json` 自动并入 Supabase 云同步体系，确保多端和重启自愈一致性。

---

## Open Questions

> [!NOTE]
> *   关于数据迁移：我们是否需要预置一些常见的热门中美股票（如 A 股贵州茅台、宁德时代，美股特斯拉、苹果、英伟达等）作为初始列表，还是默认提供空白列表供您自行添加或批量导入？

---

## Proposed Changes

### 1. 存储层 (Storage Layer)

#### [MODIFY] [storage.py](file:///d:/Google/strxfibo/storage.py)
*   定义新的文件路径常量：
    *   `F_HOTLIST`: `data_hotlist.json` (当前热门品种列表)
    *   `F_HOTLIST_ARCHIVE`: `data_hotlist_archive.json` (热门品种已删除归档)
    *   `F_HL_CATS`: `data_hl_categories.json` (热门品种专属分类)
    *   `F_HL_VIEWED`: `data_hl_viewed.json` (热门品种今日巡视进度记录)
*   实现以下独立的 Hotlist 管理接口（结构和行为对标 Watchlist 接口）：
    *   `load_hotlist()` / `save_hotlist(items)`
    *   `load_hotlist_archive()` / `save_hotlist_archive(items)`
    *   `load_hl_categories()` / `save_hl_categories(cats)`
    *   `add_to_hotlist(ticker, name, note, img_url)`
    *   `remove_from_hotlist(ticker)` (移入存档)
    *   `restore_from_hotlist_archive(ticker)`
    *   `add_hotlist_note(ticker, note_text, img_url)`
    *   `toggle_pin_hotlist(ticker)`
    *   `set_hotlist_item_category(ticker, category_id)`
    *   `load_hl_viewed_today()` / `mark_hl_viewed(ticker)` / `unmark_hl_viewed(ticker)`

---

### 2. 云同步层 (Cloud Sync Layer)

#### [MODIFY] [cloud_sync.py](file:///d:/Google/strxfibo/cloud_sync.py)
*   在 `_LATEST_FILES` 字典中注册三个新增的数据文件，建立云端与本地的同步通道：
    ```python
    "hotlist":           "hotlist.json",
    "hotlist_archive":   "hotlist_archive.json",
    "hl_categories":     "hl_categories.json",
    ```
*   在 `_SNAPSHOT_KEYS` 中追加 `"hotlist"`, `"hotlist_archive"`, `"hl_categories"`，使它们享受 2 小时定时快照及冷启动自动回填策略。
*   在 `cloud_sync.py` 中新增 `push_hotlist()` 和 `push_hl_categories()` 推送函数，并在 `save_hotlist()` 等接口写入成功时异步调用。

---

### 3. 主页面与路由 (App Page & Routing)

#### [MODIFY] [app.py](file:///d:/Google/strxfibo/app.py)
*   在侧边栏导航数组 `NAV` 中注册“热门品种”：
    ```python
    ("🔥", "热门品种", "hotlist"), # 区别于共振检测(confluence) 的图标
    ```
    *注：原共振检测使用 “🔥”，可将共振检测图标改为 “⚡” 或 “🎯”，热门品种使用 “🔥” 或 “📌”*。
*   在 `_VALID_PAGES` 中追加 `"hotlist"`，允许 URL 参数跳转（如 `/?_page=hotlist`）。
*   在 `dispatch` 页面渲染分发字典中注册 `"hotlist": page_hotlist.render`。
*   （可选）在移动端底部导航栏增加热门品种入口或替换掉使用率低的入口。

---

### 4. 独立 UI 页面 (New UI Page)

#### [NEW] [page_hotlist.py](file:///d:/Google/strxfibo/page_hotlist.py)
*   新建独立页面文件，移植并重构 `page_watchlist.py`：
    *   **主页签：🔥 当前热门**。列表式展示热门品种，关联 `data_allresults.json` 中的多周期 Fibonacci 黄金区间突破状态。
    *   **今日巡视进度条**：上方展示当前热门品种的今日浏览完成比例，点击 `👁️` 按钮标记为已读，帮助每日/每周有计划地遍历盘面。
    *   **编辑与笔记**：点击品种名称快速就地重命名，展开历史笔记卡片，支持记录图表截图 URL 和复盘心得。
    *   **页签：🏷️ 分类管理**。管理热门股专属分类（如“中港股核心”、“美股AI主线”、“高股息蓝筹”等），支持三级子分类、排序与重命名。
    *   **页签：🗂️ 已删除存档**。支持误删恢复（软删除机制）。
    *   **页签：💾 备份与恢复**。支持导入、导出 JSON 以及本地备份历史还原。

---

## Verification Plan

### Manual Verification
1.  **功能完整性**：
    *   在“热门品种”页新增 Ticker（如 AAPL、600519.SS），验证是否能够正常解析出短名称。
    *   为热门品种指派分类，查看折叠与展示是否与 Watchlist 体验一致。
    *   在实时扫描完之后，打开热门品种页，检查是否能够显示各个时间周期（日/周/月）的距离黄金区间百分比与雷达标记（如 `D ⚡ 2%`）。
2.  **云端备份**：
    *   修改热门品种后，点击侧边栏的“立即同步”，检查 Supabase bucket 中是否产生 `latest/hotlist.json` 等快照文件。
3.  **路由**：
    *   检查侧边栏点击是否能流畅切换。
    *   在移动端测试底部栏及表格展示是否有错位或超出边界。
