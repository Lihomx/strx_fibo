# STRX Automatic Fibo Scanner Pro v3 系统分析报告

本报告针对 **STRX Automatic Fibo Scanner Pro v3** 进行全面的系统分析。该系统是一个基于 **Streamlit** 开发的全球斐波那契（Fibonacci）黄金区间自动扫描与多周期共振交易系统。

---

## 一、 系统概述

STRX Automatic Fibo Scanner Pro v3 旨在自动扫描全球多达 1500+ 精选金融资产（包括大宗商品、外汇、指数、美股、中港股、A股以及加密货币等），在日线、周线、月线时间框架下计算斐波那契回撤，并在资产价格落入黄金区间（0.500 - 0.618）时发出告警，同时计算多框架下的共振信号。

### 📐 核心公式与区间定义
1. **斐波那契回撤位公式**：
   $$\text{fp}(r) = \text{Swing High} - r \times (\text{Swing High} - \text{Swing Low})$$
2. **黄金分割区间定义**：
   $$\text{fp}(0.618) \le \text{当前价格} \le \text{fp}(0.500)$$
   * 其中 $0.500$ 为黄金区上沿，$0.618$ 为黄金区下沿。

---

## 二、 技术架构与技术栈

系统采用**“轻量级前端 + 高性能并发引擎 + 混合文件/云端备份存储”**的设计架构：

```mermaid
graph TD
    subgraph UI_Layer [用户界面层 (Streamlit)]
        A[app.py 主路由] --> B[📊 实时扫描 page_scanner.py]
        A --> C[🔥 共振检测 page_confluence.py]
        A --> D[⭐ 自选收藏 page_watchlist.py]
        A --> E[☁️ 云端同步 page_cloud.py]
        A --> F[🔔 告警配置 page_alerts.py]
        A --> G[⚙️ 系统设置 page_settings.py]
    end

    subgraph Logic_Layer [逻辑计算与抓取引擎]
        H[scanner.py 扫描引擎] --> I[ThreadPoolExecutor 并发抓取]
        I --> J1[AKShare 东方财富]
        I --> J2[yfinance 雅虎财经]
        I --> J3[网易/新浪/TwelveData 备用]
        H --> K[斐波那契/共振计算]
    end

    subgraph Storage_Layer [数据存储与云同步]
        M[storage.py 本地存储] --> N[data_*.json 扁平文件]
        O[cloud_sync.py 同步引擎] --> P[Supabase Object Storage]
        N -.->|自动/手动同步| P
    end

    B --> H
    M --> B
    M --> C
    M --> D
    O --> E
```

### 1. 核心技术组件
*   **前端展示**：使用 Streamlit 框架，结合 CSS 和少量 JavaScript 实现响应式布局。
*   **并发加速**：使用 Python `concurrent.futures.ThreadPoolExecutor` 实现多线程数据拉取与计算，防限流最大线程数设为 5。
*   **多级数据路由 (Failover)**：
    *   **中国/美股市场**：优先采用 `AKShare` 接口，零成本获取高频历史数据。
    *   **国际/加密/期货**：使用 `yfinance` 进行全品种覆盖。
    *   **兜底方案**：AKShare 或 yfinance 超时时，自动降级至网易财经 CSV 或新浪财经 K 线接口，极大地提高了数据获取的成功率。
*   **轻量存储与灾备**：
    *   本地采用 `json` 格式的扁平文件存储。
    *   云端依托 `Supabase Object Storage` 进行多版本快照同步，利用 Streamlit Cloud 启动钩子自动回填恢复本地丢失的缓存。

---

## 三、 核心功能模块解析

### 1. 📊 实时扫描模块 (`page_scanner.py`)
*   **分批与自定义扫描**：支持 40 组共计 1500+ 个品种的分批一键扫描，亦支持输入任意代码（如 A股 600519.SS，美股 AAPL）进行即时扫描。
*   **边扫边存 (Save-as-you-scan)**：采用线程安全的锁机制，每完成一个品种的拉取和计算立即写入 `data_allresults.json`，即使中途取消或超时，已扫出的数据也不会丢失。
*   **TradingView 联动**：支持生成全球/中国版 TradingView 链接，支持批量开启 TV 标签页，并具备今日已打开链接去重和弹窗拦截提醒。
*   **历史批次恢复**：自动将历史扫描明细归档快照，用户可从下拉菜单中一键恢复以往的任意一次扫描结果。

### 2. 🔥 多框架共振检测 (`page_confluence.py`)
*   多周期聚合日线、周线、月线指标。
*   **评分公式**：
    $$\text{Confluence Score} = \min(\text{in\_zone\_count} \times 3 + \text{near\_zone\_count}, 10)$$
*   **信号级别划分**：
    *   **三框架共振** (9~10 分，红色 Badge)：三个周期全部进入黄金分割区，代表最强潜在入场区间。
    *   **双框架共振** (6~8 分，橙色 Badge)：两个时间级别在黄金区。
    *   **单框架/接近** (1~5 分，绿色/黄色 Badge)：单个级别或价格接近区间（<5%）。

### 3. ⭐ 自选收藏夹 (`page_watchlist.py` & `storage.py`)
*   **树形分类体系**：支持用户自定义多层分类树（扁平结构，通过 `parent_id` 关联），品种与分类通过 UUID 绑定。
*   **软删除/归档机制**：删除的品种会放入 `data_watchlist_archive.json` 存档中，保留其所有的备注与笔记，可随时一键原样恢复。
*   **富文本笔记系统**：支持用户为特定收藏股追加带时间戳的富文本备注和图床链接，以便进行周期性的趋势复盘。

### 4. 🔔 告警系统 (`alerts.py` & `page_alerts.py`)
*   **通道集成**：深度接入了**钉钉群 Webhook（包含 HMAC-SHA256 加签校验）**和 **Telegram Bot**。
*   **信号冷却机制**：使用进程级全局缓存 `_cooldown`，防范同一品种在同一框架内高频发送警报（默认冷却 240 分钟，可在系统配置中定制）。

---

## 四、 关键设计亮点

> [!TIP]
> **1. JS 注入防自动回滚**
> Streamlit 在数据 rerun 时，页面往往会突兀地重置到页面顶端。本系统通过向主页面注入 MutationObserver，并在按钮点击前保存滚动条的 `scrollTop`，实现 rerun 后的滚动条位置自动还原，极大地改善了表单/按钮频繁提交时的操作体验。

> [!NOTE]
> **2. 数据推送安全锁 (Push Safety Check)**
> 在 `cloud_sync.py` 中，为了防止本地临时清空缓存后同步导致云端备份也被置空的灾难性后果，设置了安全检测。如果本地收藏夹的降幅超过 $50\%$ 或者本地数量为 $0$ 而云端存有较多数据，同步会被安全锁自动截断并提示告警。

> [!IMPORTANT]
> **3. 极致的移动端自适应**
> 大量采用了原生 HTML table 和手写移动端导航栏 `mob-nav`，并利用 CSS 注入屏蔽了原生 Streamlit 侧边栏在手机上的展示。使得图表数据和操作表单在移动端通过左右滑动即可完成查看。

---

## 五、 系统后期演进方向
1.  **向 Supabase DB 升级**：当前仍然使用 Supabase Object Storage 存储 JSON 文件。后期如果需要多用户并发或多设备高频读写，需重写 `storage.py` 中的 `load` 与 `save` 接口，无缝切换到 Supabase PostgreSQL 关系型数据库。
2.  **增加实时推送常驻守护进程**：目前告警依赖于用户在 Web 端手动点击或轮询页面触发。如需真正的 24 小时全自动运行，可在服务器后台通过 `run_scan_only.py` 配置 `cron` 定时任务。
