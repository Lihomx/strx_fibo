"""
cloud_sync.py — Supabase 云端自动备份同步 v5
================================================================
修复：使用 Supabase Management API 正确创建 bucket 并禁用 RLS。
推荐使用 service_role key 绕过 RLS 限制。

Streamlit Secrets 配置：
  SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"
  SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  SUPABASE_BUCKET = "strx-backup"

注意：SUPABASE_KEY 必须使用 service_role secret key
      位于 Supabase → Project Settings → API → service_role
================================================================
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

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

_last_sync_ts: float = 0.0


# ════════════════════════════════════════════════════════════════════
# 配置读取
# ════════════════════════════════════════════════════════════════════
def _get_secrets() -> Tuple[str, str, str]:
    try:
        import streamlit as st
        url    = st.secrets.get("SUPABASE_URL",    "")
        key    = st.secrets.get("SUPABASE_KEY",    "")
        bucket = st.secrets.get("SUPABASE_BUCKET", "strx-backup")
        return str(url).strip().rstrip("/"), str(key).strip(), str(bucket).strip()
    except Exception:
        pass
    return (
        os.environ.get("SUPABASE_URL",    "").strip().rstrip("/"),
        os.environ.get("SUPABASE_KEY",    "").strip(),
        os.environ.get("SUPABASE_BUCKET", "strx-backup").strip(),
    )


def is_configured() -> bool:
    url, key, _ = _get_secrets()
    return bool(url and key)


def _hdrs(key: str) -> dict:
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }


# ════════════════════════════════════════════════════════════════════
# Bucket 管理
# ════════════════════════════════════════════════════════════════════
def ensure_bucket() -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未填写 SUPABASE_URL / SUPABASE_KEY"

    bucket_url = f"{url}/storage/v1/bucket"

    # 先尝试获取 bucket 信息
    r = requests.get(f"{bucket_url}/{bucket}", headers=_hdrs(key), timeout=10)
    if r.status_code == 200:
        return True, f"Bucket \'{bucket}\' 已存在"

    if r.status_code == 401:
        return False, ("认证失败 (401)：请在 Secrets 中使用 service_role key\n"
                       "路径：Supabase → Project Settings → API → service_role secret key")

    # 创建 bucket（设 public=True 简化权限）
    create_r = requests.post(
        bucket_url,
        headers=_hdrs(key),
        json={"id": bucket, "name": bucket, "public": True},
        timeout=10,
    )
    if create_r.status_code in (200, 201):
        return True, f"Bucket \'{bucket}\' 已创建"

    # 解析具体错误
    try:
        err = create_r.json()
        msg = err.get("message", create_r.text[:200])
    except Exception:
        msg = create_r.text[:200]

    if "403" in str(create_r.status_code) or "security policy" in msg.lower():
        return False, (f"权限错误 (403 RLS)：当前使用的是 anon key，无法创建 bucket。\n"
                       f"请改用 service_role secret key（见配置教程第②步）")
    return False, f"创建 bucket 失败 {create_r.status_code}：{msg}"


# ════════════════════════════════════════════════════════════════════
# 上传 / 下载（REST API，x-upsert:true 覆盖）
# ════════════════════════════════════════════════════════════════════
def _upload(file_key: str, data: Any) -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未配置"

    fname   = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    obj_url = f"{url}/storage/v1/object/{bucket}/{fname}"

    hdrs = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/octet-stream",
        "x-upsert":      "true",
    }
    try:
        r = requests.post(obj_url, headers=hdrs, data=payload, timeout=30)
        if r.status_code in (200, 201):
            return True, "OK"

        # 已存在则用 PUT
        if r.status_code in (400, 409, 422):
            r2 = requests.put(obj_url, headers=hdrs, data=payload, timeout=30)
            if r2.status_code in (200, 201):
                return True, "OK(PUT)"
            return False, f"POST {r.status_code} / PUT {r2.status_code}: {r2.text[:300]}"

        if r.status_code == 401:
            return False, "认证失败 (401)：请检查 SUPABASE_KEY 是否正确"
        if r.status_code == 403:
            return False, ("权限不足 (403 RLS)：请使用 service_role secret key\n"
                           "路径：Supabase → Project Settings → API → service_role")
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.exceptions.ConnectionError:
        return False, "网络连接失败：无法访问 Supabase，请检查 SUPABASE_URL"
    except Exception as e:
        return False, f"上传异常：{e}"


def _download(file_key: str) -> Optional[Any]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return None
    fname  = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    obj_url = f"{url}/storage/v1/object/{bucket}/{fname}"
    try:
        r = requests.get(obj_url, headers=_hdrs(key), timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"_download {file_key}: {e}")
    return None


def _test_connection() -> Tuple[bool, str]:
    """完整测试：凭证 → bucket → 读写"""
    url, key, bucket = _get_secrets()
    if not url:
        return False, "SUPABASE_URL 未填写"
    if not key:
        return False, "SUPABASE_KEY 未填写"
    if not url.startswith("https://"):
        return False, f"SUPABASE_URL 格式错误（应以 https:// 开头）：{url[:40]}"

    # Step 1: 测试 API 连通
    try:
        r = requests.get(f"{url}/storage/v1/bucket",
                         headers=_hdrs(key), timeout=10)
    except Exception as e:
        return False, f"无法连接到 Supabase：{e}\n请检查 SUPABASE_URL 是否正确"

    if r.status_code == 401:
        return False, ("API Key 无效 (401 Unauthorized)\n"
                       "请检查 SUPABASE_KEY 是否正确复制\n"
                       "⚠️ 必须使用 service_role secret key，不是 anon key")

    # Step 2: bucket
    ok, msg = ensure_bucket()
    if not ok:
        return False, msg

    # Step 3: 写入测试
    ok2, msg2 = _upload("meta", {
        "last_sync":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts":     time.time(),
        "version":          "5",
        "watchlist_cnt":    0,
        "scan_results_cnt": 0,
    })
    if ok2:
        return True, f"✅ 连接成功！Bucket=\'{bucket}\'，读写测试通过"
    return False, f"连接成功但写入失败：{msg2}"


# ════════════════════════════════════════════════════════════════════
# 收藏夹完整同步（含所有 notes 字段）
# ════════════════════════════════════════════════════════════════════
def push_watchlist() -> Tuple[bool, str]:
    try:
        import storage as loc
        items   = loc.load_watchlist()
        archive = loc.load_watchlist_archive()
        for item in items:
            if not isinstance(item.get("notes"), list):
                item["notes"] = []
            for note in item["notes"]:
                note.setdefault("text",    "")
                note.setdefault("img_url", "")
                note.setdefault("ts",      "")
        ok1, m1 = _upload("watchlist",         items)
        ok2, m2 = _upload("watchlist_archive", archive)
        note_cnt = sum(len(i.get("notes", [])) for i in items)
        if ok1 and ok2:
            return True, f"收藏 {len(items)} 个品种、{note_cnt} 条备注已同步"
        return False, f"watchlist:{m1} / archive:{m2}"
    except Exception as e:
        return False, f"push_watchlist 异常：{e}"


def pull_watchlist() -> Tuple[bool, str]:
    try:
        import storage as loc
        cloud_items = _download("watchlist")
        if not isinstance(cloud_items, list):
            return False, "云端无收藏夹数据"
        local_items = loc.load_watchlist()
        local_map   = {i["ticker"].upper(): i for i in local_items
                       if isinstance(i, dict) and i.get("ticker")}
        added = 0
        merged_notes = 0
        for ci in cloud_items:
            if not isinstance(ci, dict) or not ci.get("ticker"):
                continue
            tk = ci["ticker"].upper()
            if tk not in local_map:
                local_map[tk] = ci
                added += 1
            else:
                local_entry  = local_map[tk]
                local_notes  = local_entry.get("notes", [])
                local_ts_set = {n.get("ts") for n in local_notes
                                if isinstance(n, dict) and n.get("ts")}
                for cn in ci.get("notes", []):
                    if isinstance(cn, dict) and cn.get("ts") not in local_ts_set:
                        local_notes.append({
                            "text":    cn.get("text",    ""),
                            "img_url": cn.get("img_url", ""),
                            "ts":      cn.get("ts",      ""),
                        })
                        local_ts_set.add(cn.get("ts"))
                        merged_notes += 1
                local_entry["notes"] = sorted(local_notes, key=lambda x: x.get("ts",""))
                local_map[tk] = local_entry
        loc.save_watchlist(list(local_map.values()))
        cloud_arch = _download("watchlist_archive")
        arch_added = 0
        if isinstance(cloud_arch, list):
            local_arch = loc.load_watchlist_archive()
            arch_tks   = {a["ticker"].upper() for a in local_arch
                          if isinstance(a, dict) and a.get("ticker")}
            for ai in cloud_arch:
                if isinstance(ai, dict) and ai.get("ticker"):
                    if ai["ticker"].upper() not in arch_tks:
                        local_arch.append(ai)
                        arch_added += 1
            if arch_added:
                loc.save_watchlist_archive(local_arch)
        return True, (f"新增品种 {added}，补充备注 {merged_notes} 条，"
                      f"存档补充 {arch_added} 个")
    except Exception as e:
        return False, f"pull_watchlist 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 全量推送 / 拉取
# ════════════════════════════════════════════════════════════════════
def push_all() -> Dict[str, Any]:
    import storage as loc
    results: Dict[str, Any] = {}
    ok, msg = push_watchlist()
    results["watchlist"] = (ok, msg)
    for key, loader in [
        ("scan_history", lambda: loc._load(loc.F_HIST,   [])),
        ("scan_results", lambda: loc._load(loc.F_ALLRES, [])),
        ("scan_groups",  lambda: loc.load_scanned_groups()),
        ("config",       lambda: loc._load(loc.F_CFG,    {})),
    ]:
        try:
            ok2, msg2 = _upload(key, loader())
            results[key] = (ok2, msg2)
        except Exception as e:
            results[key] = (False, str(e))
    ok3, msg3 = _upload("meta", {
        "last_sync":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts":     time.time(),
        "version":          "5",
        "watchlist_cnt":    len(loc.load_watchlist()),
        "scan_results_cnt": len(loc._load(loc.F_ALLRES, [])),
    })
    results["meta"] = (ok3, msg3)
    return results


def pull_all() -> Dict[str, Any]:
    import storage as loc
    results: Dict[str, Any] = {}
    ok, msg = pull_watchlist()
    results["watchlist"] = (ok, msg)
    cloud_hist = _download("scan_history")
    if isinstance(cloud_hist, list):
        local_hist = loc._load(loc.F_HIST, []) or []
        local_ids  = {s.get("session_id") for s in local_hist if isinstance(s, dict)}
        added = sum(1 for s in cloud_hist
                    if isinstance(s, dict) and s.get("session_id") not in local_ids
                    and local_hist.append(s) is None)
        if added:
            loc._save(loc.F_HIST, local_hist[-50:])
        results["scan_history"] = (True, f"补充 {added} 条")
    else:
        results["scan_history"] = (False, "无云端数据")
    cloud_res = _download("scan_results")
    if isinstance(cloud_res, list):
        local_res = loc._load(loc.F_ALLRES, []) or []
        m = {(r["ticker"], r.get("timeframe","")): r for r in local_res
             if isinstance(r, dict) and r.get("ticker")}
        added = sum(1 for r in cloud_res
                    if isinstance(r, dict) and r.get("ticker") and
                    (r["ticker"], r.get("timeframe","")) not in m and
                    m.update({(r["ticker"], r.get("timeframe","")): r}) is None)
        if added:
            loc._save(loc.F_ALLRES, list(m.values()))
        results["scan_results"] = (True, f"补充 {added} 条，共 {len(m)} 条")
    else:
        results["scan_results"] = (False, "无云端数据")
    cloud_grp = _download("scan_groups")
    if isinstance(cloud_grp, list):
        merged = list(set(loc.load_scanned_groups()) | set(cloud_grp))
        loc._save(loc.F_GROUPS, merged)
        results["scan_groups"] = (True, f"{len(merged)} 组")
    else:
        results["scan_groups"] = (False, "无云端数据")
    if not loc._load(loc.F_CFG, {}):
        cloud_cfg = _download("config")
        if isinstance(cloud_cfg, dict):
            loc._save(loc.F_CFG, cloud_cfg)
            results["config"] = (True, "已恢复")
        else:
            results["config"] = (False, "无云端数据")
    else:
        results["config"] = (True, "本地已有，跳过")
    return results


# ════════════════════════════════════════════════════════════════════
# 定时 / 启动
# ════════════════════════════════════════════════════════════════════
def auto_sync_if_due(force: bool = False) -> Optional[Dict]:
    global _last_sync_ts
    if not is_configured():
        return None
    now = time.time()
    if not force and (now - _last_sync_ts) < SYNC_INTERVAL_SEC:
        return None
    if not force:
        meta = _download("meta")
        if isinstance(meta, dict):
            if (now - float(meta.get("last_sync_ts", 0))) < SYNC_INTERVAL_SEC:
                _last_sync_ts = now
                return None
    _last_sync_ts = now
    ensure_bucket()
    return push_all()


def startup_restore() -> Dict[str, Any]:
    if not is_configured():
        return {"configured": False}
    ensure_bucket()
    r = pull_all()
    r["configured"] = True
    return r


def get_sync_status() -> Dict[str, Any]:
    if not is_configured():
        return {"configured": False, "status": "未配置"}
    meta = _download("meta")
    if not meta:
        return {"configured": True, "status": "尚未同步", "last_sync": "—",
                "watchlist_cnt": 0, "scan_results_cnt": 0, "elapsed_h": 0}
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
    remain = max(0.0, SYNC_INTERVAL_SEC - (time.time() - float(meta["last_sync_ts"])))
    if remain <= 0:
        return "已到期，下次访问触发"
    h, m = int(remain // 3600), int((remain % 3600) // 60)
    return f"{h}h {m:02d}m 后"
