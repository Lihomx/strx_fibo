# 📐 STRX Automatic Fibo Scanner Pro

**Streamlit Cloud 原生版 · JSON 文件存储 · 零配置部署**

Fibonacci 黄金区间自动扫描工具，公式与 STRX Pine Script 完全对应：
```
fp(r) = swingHigh − r × (swingHigh − swingLow)
黄金区间：fp(0.618) ≤ 当前价格 ≤ fp(0.500)
```

---

## 🚀 部署到 Streamlit Cloud（3 步）

### 第一步：Fork / Push 到 GitHub

将以下文件推送到你的 GitHub 仓库（**全部放在根目录**，无子文件夹）：

```
your-repo/
├── app.py              ← 主入口
├── scanner.py          ← Fibonacci 扫描引擎
├── alerts.py           ← 钉钉 / Telegram 告警
├── storage.py          ← JSON 存储层
├── page_scanner.py     ← 实时扫描页面
├── page_confluence.py  ← 共振检测页面
├── page_history.py     ← 历史记录页面
├── page_alerts.py      ← 告警配置页面
├── page_settings.py    ← 系统设置页面
├── requirements.txt    ← 依赖清单
└── .gitignore
```

### 第二步：Streamlit Cloud 部署

1. 登录 [share.streamlit.io](https://share.streamlit.io)
2. New App → 选择你的 GitHub 仓库
3. Main file path: `app.py`
4. 点击 **Deploy**

### 第三步：完成 ✅

无需任何环境变量或 Secrets 配置，直接可用！

---

## 📁 文件结构说明

| 文件 | 说明 |
|------|------|
| `app.py` | Streamlit 入口，导航路由 |
| `scanner.py` | Fibo 计算引擎 + 资产列表 + yfinance/TwelveData 数据获取 |
| `alerts.py` | 钉钉 / Telegram 告警，带冷却机制 |
| `storage.py` | JSON 文件读写（替代 Supabase） |
| `page_*.py` | 各功能页面（单层，直接 import） |
| `data_*.json` | 运行时自动生成（不需要提交 GitHub） |

---

## ⚙️ 功能页面

| 页面 | 功能 |
|------|------|
| 📊 实时扫描 | 一键扫描 36 资产 × 3 框架，实时进度 |
| 🔥 共振检测 | 多时间框架共振排行，识别最强信号 |
| 📂 历史记录 | 查看最近 30 次扫描，CSV 下载 |
| 🔔 告警配置 | 钉钉 / Telegram 配置与测试 |
| ⚙️ 系统设置 | Fibo 参数、数据源、存储管理 |

---

## 📊 监控资产（36 个）

- **大宗商品**：黄金、白银、原油、天然气、铜、小麦、玉米
- **外汇**：EUR/USD, GBP/USD, USD/JPY, USD/CNH, AUD/USD, USD/CAD
- **指数**：S&P500, NASDAQ100, 道琼斯, 上证, 深证, 恒生
- **美股**：AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA
- **中概/港股**：百度, PDD, 京东, 阿里HK, 腾讯HK
- **加密**：BTC, ETH, SOL, BNB

---

## 💾 存储架构

```
当前：JSON 文件（Streamlit Cloud 本地）
         ↓  后期升级只需替换 storage.py
未来：Supabase PostgreSQL（云端持久化）
```

**⚠️ 注意**：Streamlit Cloud 容器重启时本地 JSON 文件会丢失，
适合演示和日常使用。如需持久存储，升级到 Supabase 即可。

---

## 🔮 后期升级到 Supabase

只需替换 `storage.py` 中的以下函数，其余代码**完全不变**：
- `load_config()` / `save_config()`
- `save_scan()` / `load_sessions()` / `load_results()`
- `log_alert()` / `load_alert_log()`

---

## 📐 Fibonacci 参数说明

| 级别 | 含义 |
|------|------|
| 0.0 | 结构高点（Swing High） |
| 0.136 | 机构算法入场 |
| 0.236 | 浅回撤 |
| 0.382 | 标准回撤 |
| **0.500** | **黄金区上沿** |
| **0.618** | **黄金区下沿（黄金分割）** |
| 0.705 | OTE 最优交易入场 |
| 0.786 | 深度回撤 |
| 0.886 | Shark/深度机构 |
| 1.0 | 结构低点（Swing Low） |
