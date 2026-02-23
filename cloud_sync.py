"""
cloud_sync.py — Supabase 云端自动备份同步
================================================================
平台：Supabase Storage（文件存储）
免费层：500MB DB + 1GB 文件存储，永不过期，无需信用卡

备份文件（bucket: strx-backup）：
  watchlist.json         自选收藏夹（每次修改立即同步）
  watchlist_archive.json 已删除存档
  scan_history.json      扫描会话列表
  scan_results.json      全量扫描结果
  scan_groups.json       已扫描品种组
  config.json            用户配置
  sync_meta.json         同步元数据

Streamlit Secrets 配置（Settings -> Secrets）：
  SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"
  SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  SUPABASE_BUCKET = "strx-backup"
================================================================
"""

import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SEC = 4 * 3600   # 4 小时

_CLOUD_FILES = {
    "watchlist":         "watchlist.json",
    "watchlist_archive": "watchlist_archive.json",
    "scan_history":      "scan_history.json",
    "scan_results":      "scan_results.json",
    "scan_groups":       "scan_groups.json",
    "config":            "config.json",
    "meta":              "sync_meta.json",
}

_client_cache = None
_last_sync_ts: float = 0.0


# ── 配置读取 ──────────────────────────────────────────────────────────
def _get_secrets() -> Tuple[str, str, str]:
    try:
        import streamlit as st
        url    = st.secrets.get("SUPABASE_URL",    "")
        key    = st.secrets.get("SUPABASE_KEY",    "")
        bucket = st.secrets.get("SUPABASE_BUCKET", "strx-backup")
        return str(url).strip(), str(key).strip(), str(bucket).strip()
    except Exception:
        pass
    return (
        os.environ.get("SUPABASE_URL",    ""),
        os.environ.get("SUPABASE_KEY",    ""),
        os.environ.get("SUPABASE_BUCKET", "strx-backup"),
    )


def is_configured() -> bool:
    url, key, _ = _get_secrets()
    return bool(url and key)


# ── Supabase 客户端 ───────────────────────────────────────────────────
def _get_client():
    global _client_cache
    if _client_cache is not None:
        return _client_cache
    url, key, _ = _get_secrets()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client_cache = create_client(url, key)
        return _client_cache
    except ImportError:
        logger.warning("supabase 未安装，请在 requirements.txt 中添加 supabase>=2.0.0")
        return None
    except Exception as e:
        logger.warning(f"Supabase 连接失败：{e}")
        return None


# ── Bucket 初始化 ─────────────────────────────────────────────────────
def ensure_bucket() -> bool:
    client = _get_client()
    if not client:
        return False
    _, _, bucket = _get_secrets()
    try:
        buckets = client.storage.list_buckets()
        names   = [b.name for b in (buckets or [])]
        if bucket not in names:
            client.storage.create_bucket(bucket, options={"public": False})
        return True
    except Exception as e:
        logger.warning(f"ensure_bucket: {e}")
        return False


# ── 上传 / 下载 ───────────────────────────────────────────────────────
def _upload(file_key: str, data: Any) -> bool:
    client = _get_client()
    if not client:
        return False
    _, _, bucket = _get_secrets()
    fname   = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    opts    = {"content-type": "application/json", "upsert": "true"}
    try:
        client.storage.from_(bucket).upload(path=fname, file=payload, file_options=opts)
        return True
    except Exception:
        try:
            client.storage.from_(bucket).update(path=fname, file=payload,
                                                 file_options={"content-type": "application/json"})
            return True
        except Exception as e2:
            logger.warning(f"_upload {file_key}: {e2}")
            return False


def _download(file_key: str) -> Optional[Any]:
    client = _get_client()
    if not client:
        return None
    _, _, bucket = _get_secrets()
    fname = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    try:
        raw = client.storage.from_(bucket).download(fname)
        if isinstance(raw, (bytes, bytearray)):
            return json.loads(raw.decode("utf-8"))
        return None
    except Exception as e:
        logger.debug(f"_download {file_key}: {e}")
        return None


# ── 收藏夹即时同步 ────────────────────────────────────────────────────
def push_watchlist() -> bool:
    """修改收藏夹后立即调用，将最新数据推送到云端。"""
    try:
        import storage as loc
        ok1 = _upload("watchlist",         loc.load_watchlist())
        ok2 = _upload("watchlist_archive", loc.load_watchlist_archive())
        return ok1 and ok2
    except Exception as e:
        logger.warning(f"push_watchlist: {e}")
        return False


def pull_watchlist() -> Tuple[bool, str]:
    """从云端拉取收藏夹，与本地数据合并（不覆盖本地独有记录）。"""
    try:
        import storage as loc
        cloud_items = _download("watchlist")
        if not isinstance(cloud_items, list):
            return False, "云端无收藏夹数据"
        payload = json.dumps({"watchlist": cloud_items, "archive": []}, ensure_ascii=False)
        ok, msg = loc.import_watchlist_json(payload, merge=True)

        cloud_arch = _download("watchlist_archive")
        if isinstance(cloud_arch, list):
            local_arch = loc.load_watchlist_archive()
            local_tks  = {a["ticker"].upper() for a in local_arch if isinstance(a, dict)}
            added = 0
            for item in cloud_arch:
                if isinstance(item, dict) and item.get("ticker"):
                    if item["ticker"].upper() not in local_tks:
                        local_arch.append(item)
                        added += 1
            if added:
                loc.save_watchlist_archive(local_arch)
        return ok, msg
    except Exception as e:
        return False, f"pull_watchlist 失败：{e}"


# ── 全量推送 ──────────────────────────────────────────────────────────
def push_all() -> Dict[str, bool]:
    """将所有本地数据文件上传到 Supabase Storage。"""
    import storage as loc
    results: Dict[str, bool] = {}
    try:
        results["watchlist"]         = _upload("watchlist",         loc.load_watchlist())
        results["watchlist_archive"] = _upload("watchlist_archive", loc.load_watchlist_archive())
        results["scan_history"]      = _upload("scan_history",      loc._load(loc.F_HIST,   []))
        results["scan_results"]      = _upload("scan_results",      loc._load(loc.F_ALLRES, []))
        results["scan_groups"]       = _upload("scan_groups",       loc.load_scanned_groups())
        results["config"]            = _upload("config",            loc._load(loc.F_CFG,    {}))
        results["meta"]              = _upload("meta", {
            "last_sync":     time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_sync_ts":  time.time(),
            "version":       "2",
            "watchlist_cnt": len(loc.load_watchlist()),
            "scan_results_cnt": len(loc._load(loc.F_ALLRES, [])),
        })
    except Exception as e:
        logger.warning(f"push_all: {e}")
    return results


# ── 全量拉取 ──────────────────────────────────────────────────────────
def pull_all() -> Dict[str, Any]:
    """从 Supabase 拉取所有数据，合并到本地。"""
    import storage as loc
    results: Dict[str, Any] = {}
    try:
        # 收藏夹
        ok, msg = pull_watchlist()
        results["watchlist"] = (ok, msg)

        # 扫描历史
        cloud_hist = _download("scan_history")
        if isinstance(cloud_hist, list):
            local_hist = loc._load(loc.F_HIST, [])
            if not isinstance(local_hist, list):
                local_hist = []
            local_ids = {s.get("session_id") for s in local_hist if isinstance(s, dict)}
            added = sum(1 for s in cloud_hist
                        if isinstance(s, dict) and s.get("session_id") not in local_ids
                        and local_hist.append(s) is None)
            if added:
                local_hist = local_hist[-50:]
                loc._save(loc.F_HIST, local_hist)
            results["scan_history"] = (True, f"合并 {added} 条会话")
        else:
            results["scan_history"] = (False, "无云端扫描历史")

        # 扫描结果
        cloud_res = _download("scan_results")
        if isinstance(cloud_res, list):
            local_res = loc._load(loc.F_ALLRES, [])
            if not isinstance(local_res, list):
                local_res = []
            merged_map = {(r["ticker"], r.get("timeframe", "")): r
                          for r in local_res if isinstance(r, dict) and r.get("ticker")}
            added = 0
            for r in cloud_res:
                if isinstance(r, dict) and r.get("ticker"):
                    key = (r["ticker"], r.get("timeframe", ""))
                    if key not in merged_map:
                        merged_map[key] = r
                        added += 1
            if added:
                loc._save(loc.F_ALLRES, list(merged_map.values()))
            results["scan_results"] = (True, f"合并 {added} 条记录，共 {len(merged_map)} 条")
        else:
            results["scan_results"] = (False, "无云端扫描结果")

        # 品种组
        cloud_grp = _download("scan_groups")
        if isinstance(cloud_grp, list):
            local_grp = loc.load_scanned_groups()
            merged_g  = list(set(local_grp) | set(cloud_grp))
            loc._save(loc.F_GROUPS, merged_g)
            results["scan_groups"] = (True, f"{len(merged_g)} 个品种组")
        else:
            results["scan_groups"] = (False, "无品种组数据")

        # 配置（本地有则不覆盖）
        local_cfg = loc._load(loc.F_CFG, {})
        if not local_cfg:
            cloud_cfg = _download("config")
            if isinstance(cloud_cfg, dict):
                loc._save(loc.F_CFG, cloud_cfg)
                results["config"] = (True, "已恢复配置")
            else:
                results["config"] = (False, "无云端配置")
        else:
            results["config"] = (True, "本地配置存在，已跳过")

    except Exception as e:
        logger.warning(f"pull_all: {e}")
        results["_error"] = str(e)
    return results


# ── 定时同步入口 ──────────────────────────────────────────────────────
def auto_sync_if_due(force: bool = False) -> Optional[Dict]:
    """
    每 4 小时触发一次全量上传。
    在 app.py 每次页面渲染时调用，零感知后台运行。
    force=True 立即执行，忽略时间限制。
    """
    global _last_sync_ts
    if not is_configured():
        return None
    now = time.time()
    # 进程内快速节流
    if not force and (now - _last_sync_ts) < SYNC_INTERVAL_SEC:
        return None
    # 跨进程节流（读云端 meta）
    if not force:
        meta = _download("meta")
        if isinstance(meta, dict):
            last_ts = float(meta.get("last_sync_ts", 0))
            if (now - last_ts) < SYNC_INTERVAL_SEC:
                _last_sync_ts = now
                return None
    _last_sync_ts = now
    ensure_bucket()
    return push_all()


def startup_restore() -> Dict[str, Any]:
    """App 启动时调用一次，从云端恢复所有数据到本地。"""
    if not is_configured():
        return {"configured": False, "msg": "Supabase 未配置"}
    ensure_bucket()
    results = pull_all()
    results["configured"] = True
    return results


# ── 状态信息 ──────────────────────────────────────────────────────────
def get_sync_status() -> Dict[str, Any]:
    if not is_configured():
        return {"configured": False, "status": "未配置"}
    meta = _download("meta")
    if not meta:
        return {"configured": True, "status": "尚未同步", "last_sync": "—"}
    elapsed_h = (time.time() - float(meta.get("last_sync_ts", 0))) / 3600
    return {
        "configured":       True,
        "status":           "正常",
        "last_sync":        meta.get("last_sync", "—"),
        "last_sync_ts":     meta.get("last_sync_ts", 0),
        "watchlist_cnt":    meta.get("watchlist_cnt", 0),
        "scan_results_cnt": meta.get("scan_results_cnt", 0),
        "elapsed_h":        round(elapsed_h, 1),
    }


def time_to_next_sync_str() -> str:
    if not is_configured():
        return "未配置"
    meta = _download("meta")
    if not meta or not meta.get("last_sync_ts"):
        return "立即同步"
    remain = max(0, SYNC_INTERVAL_SEC - (time.time() - float(meta["last_sync_ts"])))
    if remain <= 0:
        return "已到期，下次访问触发"
    h, m = int(remain // 3600), int((remain % 3600) // 60)
    return f"{h}h {m:02d}m 后"
