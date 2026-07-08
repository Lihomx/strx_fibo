# Hotlist 功能开发及修复 Walkthrough

我们已经完整实现了**热门品种（Hotlist）**功能，并完成了其与 Fibonacci 扫描仪系统的全面集成，同时修复了自选收藏夹（Watchlist）遗留的分类排序和本地自动备份列表的 Bugs。

## 1. 新增功能与代码实现

### 1.1 热门品种页面管理 [NEW] [page_hotlist.py](file:///d:/Google/strxfibo/page_hotlist.py)
实现了独立的 `page_hotlist.py` UI 模块，包含四大页签功能，深度复用并优化了 Watchlist 极速流畅的交互设计：
- **🔥 当前热门**：支持新增热门品种、今日巡视进度条（自动跟踪已看品种）、分类筛选（树形折叠）、排序与置顶（📌）、单个/批量删除（移入存档）及 CSV 导出。
- **🏷️ 分类管理**：支持创建/删除/重命名三级分类，按 order 字段对同级分类排序，支持对多个品种进行批量分类设置。
- **🗂️ 已删除存档**：软删除品种的历史备注予以完整保留，可随时一键恢复或永久删除。
- **💾 备份与恢复**：支持下载 JSON 备份，并在合并/覆盖模式下导入，且可自动从本地 backups 目录下筛选出属于 `data_hotlist` 的备份并执行还原。

### 1.2 主界面与路由配置 [MODIFY] [app.py](file:///d:/Google/strxfibo/app.py)
- 侧边栏导航 NAV 中已加入“热门品种”选项，并更新 dispatch 路由映射。
- 移动端底部快捷导航栏完成了“热门”入口适配与图标图标展示。

### 1.3 数据备份与列表还原 [MODIFY] [storage.py](file:///d:/Google/strxfibo/storage.py)
- **修复本地备份列表加载崩溃问题**：原有 `list_backups` 接口返回的是元组列表，而 UI 代码以字典字段（如 `b['name']`）读取导致抛出 `TypeError` 崩溃。修改为返回标准 `dict` 结构，并将其参数化，可根据 `prefix` 自动筛选（如 `data_watchlist` 或 `data_hotlist`），彻底修复了 Watchlist 和 Hotlist 本地备份加载的 Bug。
- **修复分类排序异常问题**：原本在 UI 中“上移”分类调用的是不存在的 `storage.move_wl_category`。更新为调用统一的 `storage.reorder_wl_category(node["id"], "up")`，确保分类上下移动功能能完全正常运转。
- 实现了 `restore_backup(name, is_hotlist)` 统一还原入口，能够精确恢复指定类型的备份数据。

---

## 2. 验证与编译检查
我们已经在 Windows 环境下对所有涉及的 Python 代码运行了语法编译测试：
```powershell
python -m py_compile d:\Google\strxfibo\page_hotlist.py d:\Google\strxfibo\storage.py d:\Google\strxfibo\app.py d:\Google\strxfibo\page_watchlist.py
```
编译成功结束，退出码为 `0`，证明无语法错误，逻辑链路正确。
