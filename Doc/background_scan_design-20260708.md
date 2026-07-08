# 后台扫描升级方案 — Streamlit Cloud 版

## Streamlit Cloud 平台限制分析

| 方案 | 本地服务器 | Streamlit Cloud |
|------|-----------|----------------|
| `subprocess` 独立进程 | ✅ 完美支持 | ❌ 不支持 |
| 持久化文件进度 | ✅ 文件系统持久 | ⚠️ 文件系统重启后清空 |
| **Python `threading`** | ✅ | ✅ **可用** |
| **模块级共享状态** | ✅ | ✅ **可用** |
| **Supabase 持久进度** | ✅ | ✅ **最佳** |

> [!IMPORTANT]
> Streamlit Cloud 上，应用进程是**持续运行**的（只要有人部署，进程不会停）。在一个 session 中启动的 `threading.Thread` 会在该 session 关闭后**继续存活**，直到应用重启或部署更新。这是实现后台扫描的关键。

> [!WARNING]
> **唯一风险**：如果 Streamlit Cloud 因代码更新重新部署应用，后台线程会被终止。这对于几分钟到几小时的扫描任务来说是可接受的风险，因为结果会实时写入 Supabase，重开后可恢复已完成部分。

---

## 推荐架构：线程 + 模块级状态 + Supabase 持久化

```
[用户点击「后台扫描」]
         ↓
   bg_scan_manager.submit_job(job_type, params)
         ↓
   创建 daemon=True 的后台线程
         ↓
   立即返回，页面显示「✅ 扫描已在后台运行」
         ↓
   用户可关闭页面 ← 线程继续跑
         ↓
   线程每扫一个 ticker → 写进度到 _GLOBAL_STATE (内存)
   线程每完成一批 → 写结果到 Supabase (持久)
         ↓
   [重新打开页面] → 读 _GLOBAL_STATE 或 Supabase 获取进度
```

---

## 核心模块：`bg_scan_manager.py`（新建）

```python
# 模块级单例状态（跨所有 session 共享）
_GLOBAL_STATE = {
    "status": "idle",        # idle | running | done | error | cancelled
    "job_id": None,
    "job_type": None,        # "fibo" | "triple_bottom" | "universe" | "chartink"
    "job_label": "",
    "progress": 0.0,         # 0.0 ~ 1.0
    "current": "",           # 当前正在扫描的品种
    "done_count": 0,
    "total_count": 0,
    "results_count": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "_cancel_flag": False,
    "_thread": None,
}

def submit_job(job_type, label, params, worker_fn) -> (bool, str):
    """提交后台扫描任务，返回 (成功, 消息)"""

def get_status() -> dict:
    """读取当前扫描状态（页面轮询用）"""

def request_cancel():
    """请求取消当前扫描"""

def is_running() -> bool:
    """当前是否有任务在运行"""
```

---

## 各扫描页改造计划

### 1. `page_triple_bottom.py` — 三重底扫描

**现状**：`run_scan` 按钮 → 同步循环 → 页面必须保持打开

**改造**：
- 按钮触发 `bg_scan_manager.submit_job("triple_bottom", ...)`
- 进度通过 `st_autorefresh(3000)` 轮询 `_GLOBAL_STATE`
- 结果写入 `storage.save_triple_bottom()` + Supabase

```python
# 新 UI 逻辑（伪代码）
status = bg_scan_manager.get_status()

if status["status"] == "running" and status["job_type"] == "triple_bottom":
    # 显示实时进度
    st.info(f"🔄 后台扫描中：{status['current']}  ({status['done_count']}/{status['total_count']})")
    st.progress(status["progress"])
    st.caption("✅ 可安全关闭此页面，扫描将继续在后台运行")
    if st.button("⏹ 取消扫描"):
        bg_scan_manager.request_cancel()

elif status["status"] == "running":
    st.warning("⚠️ 当前有其他扫描任务正在后台运行")
    # 禁用开始按钮

else:
    # 正常显示配置 + 开始按钮
    if st.sidebar.button("🚀 开始后台扫描"):
        ok, msg = bg_scan_manager.submit_job(...)
        st.success(msg) if ok else st.error(msg)
```

---

### 2. `page_scanner.py` — Fibonacci 分批扫描

**现状**：`_render_batch_selector()` 中点击扫描按钮 → 同步执行

**改造**：
- 分批扫描（选中组）→ 后台化
- 单支自定义扫描 → 保持同步（速度快，无需后台化）
- Doc/symbol 批量扫描 → 后台化

---

### 3. `page_universe.py` — 品种库批量扫描

**现状**：`_run_batch()` 同步执行，有"建议≤50支"提示

**改造**：
- 取消 50 支限制提示
- 后台化后可以安全扫描 200+ 支
- 进度持久化到 Supabase（中途重开页面也能接续查看）

---

### 4. `page_chartink.py` — Chartink 4H 突破扫描

**现状**：`run_btn` → 同步逐个检测

**改造**：
- S&P 500 全量扫描约 500 只，约需 10-20 分钟
- 后台化，结果实时写入 `session_state`（或 Supabase）

---

## Supabase 表设计（可选，用于进度持久化）

```sql
-- 后台扫描任务状态表
CREATE TABLE bg_scan_jobs (
    job_id       TEXT PRIMARY KEY,
    job_type     TEXT,
    status       TEXT DEFAULT 'running',
    progress     FLOAT DEFAULT 0,
    current_tk   TEXT DEFAULT '',
    done_count   INT DEFAULT 0,
    total_count  INT DEFAULT 0,
    results_count INT DEFAULT 0,
    started_at   TIMESTAMPTZ DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    error        TEXT,
    params       JSONB
);
```

> [!NOTE]
> Supabase 表是可选的。如果不建表，用模块级内存状态就够了。只是应用重启后进度会丢失（但结果已写入本地 JSON）。

---

## 实施步骤

| 步骤 | 文件 | 工作量 |
|------|------|--------|
| 1 | 新建 `bg_scan_manager.py` | 核心模块，约 150 行 |
| 2 | 改造 `page_triple_bottom.py` | 扫描循环改为线程，UI 加轮询 |
| 3 | 改造 `page_scanner.py` 分批扫描 | 同上 |
| 4 | 改造 `page_universe.py` 批量扫描 | 同上 |
| 5 | 改造 `page_chartink.py` | 同上 |
| 6 | `app.py` 全局状态栏 | 顶部显示后台任务进度条（可选） |

---

## 用户体验示意

```
[页面打开]
  ┌─────────────────────────────────────────────┐
  │ 🔄 后台扫描运行中：三重底 · 600206 (4小时)   │
  │ ████████████░░░░░░░ 63%  (82/130)           │
  │ ✅ 您可以安全关闭此页面，结果自动保存          │
  │                          [⏹ 取消扫描]       │
  └─────────────────────────────────────────────┘

[用户关闭页面，线程继续跑...]

[15分钟后重新打开页面]
  ┌─────────────────────────────────────────────┐
  │ ✅ 后台扫描已完成！                           │
  │ 三重底扫描 · 耗时 18分23秒                    │
  │ 共发现 23 个形态候选 · 已自动保存             │
  │                          [查看结果]          │
  └─────────────────────────────────────────────┘
```

---

## 关键技术点

### 线程安全
- 所有对 `_GLOBAL_STATE` 的读写用 `threading.Lock()` 保护
- `_cancel_flag` 通过 `threading.Event` 实现，worker 定期检查

### 防重入
- 同一时刻只能有一个后台任务运行
- 新提交任务前检查 `is_running()`，若有则拒绝

### 错误恢复
- worker 内部全程 `try/except`，异常写入 `_GLOBAL_STATE["error"]`
- 已完成的结果（partial）正常保存，不因最后一个报错而丢弃

### 自动刷新轮询
```python
from streamlit_autorefresh import st_autorefresh
# 仅在后台有任务时激活自动刷新（3秒一次）
if bg_scan_manager.is_running():
    st_autorefresh(interval=3000, key="bg_scan_poll")
```
> `streamlit-autorefresh` 已在很多 Streamlit 项目中使用，需添加到 requirements.txt

---

## 结论

✅ **完全可以在 Streamlit Cloud 上实现**，无需任何外部服务。  
✅ **不依赖 subprocess**，纯 Python threading 方案。  
✅ **关闭页面后继续扫描**，下次打开可看到进度/结果。  
⚠️ **唯一限制**：Streamlit Cloud 重新部署时线程会被终止（但结果已持久化）。
