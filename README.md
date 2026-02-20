# 📐 STRX Fibo Scanner Pro
### Streamlit + Supabase Production Edition

基于 STRX Automatic Fibo Pine Script 指标的自动化 Fibonacci 黄金区间扫描系统。

---

## 🗂️ 项目结构

```
strx_fibo_app/
├── app.py                      # Streamlit 主入口
├── run_scan_only.py            # 独立扫描脚本（GitHub Actions / Cron 用）
├── requirements.txt
├── .streamlit/
│   └── secrets.toml.example    # 密钥配置模板
├── core/
│   ├── supabase_client.py      # Supabase 数据库 CRUD + 配置管理
│   ├── scanner.py              # Fibonacci 扫描引擎（对应 Pine Script 公式）
│   ├── alerts.py               # 钉钉 / Telegram 告警发送
│   └── scheduler.py            # APScheduler 后台定时任务
└── pages/
    ├── page_scanner.py         # 实时扫描页
    ├── page_confluence.py      # 多框架共振检测
    ├── page_history.py         # 历史记录 + CSV 下载
    ├── page_alerts.py          # 告警配置 + 告警日志
    ├── page_schedule.py        # 定时任务配置
    ├── page_settings.py        # 数据源 + Fibo 参数 + Supabase 配置
    └── page_roadmap.py         # 功能路线图
```

---

## ⚡ 快速启动

### 步骤 1：安装依赖
```bash
pip install -r requirements.txt
```

### 步骤 2：配置 Supabase

1. 注册 [supabase.com](https://supabase.com)（免费 Free tier 足够）
2. 新建项目 → **Settings → API** → 复制 Project URL 和 anon key
3. 创建 `.streamlit/secrets.toml`：
   ```toml
   [supabase]
   url = "https://xxxxxxxxxxxx.supabase.co"
   key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```
4. 在 Supabase **SQL Editor** 执行数据库初始化（在 app 设置页可复制 DDL）

### 步骤 3：运行
```bash
streamlit run app.py
```

浏览器打开 `http://localhost:8501`

---

## ☁️ Streamlit Cloud 部署

1. 将项目推送到 GitHub（**确保 `secrets.toml` 已在 `.gitignore` 中！**）
2. 登录 [share.streamlit.io](https://share.streamlit.io) → New app → 选择仓库
3. 在 App **Settings → Secrets** 粘贴：
   ```toml
   [supabase]
   url = "https://xxxxxxxxxxxx.supabase.co"
   key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```
4. Deploy ✅

---

## 🗄️ 数据库表结构（Supabase PostgreSQL）

| 表名 | 说明 |
|------|------|
| `scan_sessions` | 扫描批次记录，命名格式：`YYYYMMDD_总检查数_区间内数_来源` |
| `scan_results`  | 每个资产×时间框架的扫描结果，关联 session |
| `alert_log`     | 钉钉/Telegram 告警发送记录 |
| `app_config`    | 应用配置键值对，在 Web 界面修改后实时生效 |

---

## 📐 Fibonacci 公式（与 Pine Script 完全对应）

```
swingHigh = ta.highest(high, lookback)   ← Python: df["High"].max()
swingLow  = ta.lowest(low,  lookback)    ← Python: df["Low"].min()

fp(r) = swingHigh - r × (swingHigh - swingLow)

黄金区间（IN ZONE）：fp(0.618) ≤ close ≤ fp(0.500)
```

---

## ⏰ 生产环境定时扫描方案

### 方案 A：GitHub Actions（推荐免费方案）
```yaml
# .github/workflows/daily_scan.yml
on:
  schedule:
    - cron: '0 1 * * *'   # UTC 01:00 = 北京时间 09:00
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements.txt
      - run: python run_scan_only.py
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
```

### 方案 B：Supabase pg_cron（数据库层触发）
```sql
-- 需在 Supabase Dashboard 开启 pg_cron 扩展
SELECT cron.schedule('daily-scan', '0 1 * * *',
  $$ SELECT net.http_post('https://YOUR.supabase.co/functions/v1/scan', '{}') $$
);
```

### 方案 C：APScheduler（适合自托管服务器）
在 Web 界面的「定时任务」页开启，Streamlit 后台线程每天自动执行。

---

## 🚀 可扩展的后续功能

见应用内「功能路线图」页面，共 15 个计划功能，分三个阶段：

- **Phase 1（近期）**：自定义 Watchlist、更多告警层级、企业微信/飞书、多频扫描
- **Phase 2（中期）**：K线可视化、历史回测、每日摘要报告、突破告警
- **Phase 3（高级）**：AI 评论生成、多用户登录、TradingView Webhook、策略规则引擎

---

## 🔐 安全注意事项

- `.streamlit/secrets.toml` 必须加入 `.gitignore`
- Supabase 使用 `anon` key，不要使用 `service_role` key
- 钉钉 Secret 和 Telegram Token 建议仅存储在 Supabase，不写入代码
