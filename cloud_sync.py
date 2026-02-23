"""
cloud_sync.py — Supabase 云端自动备份同步
================================================================
关键修复（v4）：
  1. 上传改用 REST API 直接 PUT（避免 supabase-py 版本差异）
  2. 收藏夹同步包含所有 notes 字段：text / img_url / ts
  3. 启动/定时自动同步，4小时一次

Streamlit Secrets 配置：
  SUPABASE_URL    = "https://xxxxxxxxxxxx.supabase.co"
  SUPABASE_KEY    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  SUPABASE_BUCKET = "strx-backup"
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


def _headers(key: str) -> dict:
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }


def _storage_url(url: str, bucket: str, fname: str) -> str:
    return f"{url}/storage/v1/object/{bucket}/{fname}"


# ════════════════════════════════════════════════════════════════════
# Bucket 自动创建（REST API）
# ════════════════════════════════════════════════════════════════════
def ensure_bucket() -> Tuple[bool, str]:
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未配置 Supabase"
    try:
        # 检查 bucket 是否存在
        r = requests.get(
            f"{url}/storage/v1/bucket/{bucket}",
            headers=_headers(key), timeout=10,
        )
        if r.status_code == 200:
            return True, f"Bucket '{bucket}' 已存在"
        if r.status_code == 400 or r.status_code == 404:
            # 创建 bucket
            cr = requests.post(
                f"{url}/storage/v1/bucket",
                headers=_headers(key),
                json={"id": bucket, "name": bucket, "public": False},
                timeout=10,
            )
            if cr.status_code in (200, 201):
                return True, f"Bucket '{bucket}' 已创建"
            return False, f"创建 bucket 失败：{cr.status_code} {cr.text[:200]}"
        return False, f"检查 bucket 失败：{r.status_code} {r.text[:200]}"
    except Exception as e:
        return False, f"ensure_bucket 异常：{e}"


# ════════════════════════════════════════════════════════════════════
# 上传 / 下载（纯 REST，不依赖 supabase-py 版本）
# ════════════════════════════════════════════════════════════════════
def _upload(file_key: str, data: Any) -> Tuple[bool, str]:
    """
    上传 JSON 数据到 Supabase Storage。
    使用 REST PUT + x-upsert:true，完全绕过 supabase-py 版本问题。
    """
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "未配置 Supabase"

    fname   = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    target  = _storage_url(url, bucket, fname)
    hdrs = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "x-upsert":      "true",          # ← 关键：覆盖已有文件
    }
    try:
        r = requests.post(target, headers=hdrs, data=payload, timeout=30)
        if r.status_code in (200, 201):
            return True, "OK"
        # 如果是 already exists，用 PUT 覆盖
        if r.status_code in (400, 409):
            r2 = requests.put(target, headers=hdrs, data=payload, timeout=30)
            if r2.status_code in (200, 201):
                return True, "OK(PUT)"
            return False, f"POST {r.status_code} / PUT {r2.status_code}: {r2.text[:300]}"
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, f"请求异常：{e}"


def _download(file_key: str) -> Optional[Any]:
    """从 Supabase Storage 下载 JSON 文件。"""
    url, key, bucket = _get_secrets()
    if not url or not key:
        return None
    fname  = _CLOUD_FILES.get(file_key, f"{file_key}.json")
    target = _storage_url(url, bucket, fname)
    hdrs   = _headers(key)
    try:
        r = requests.get(target, headers=hdrs, timeout=30)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        logger.debug(f"_download {file_key}: {e}")
        return None


def _test_connection() -> Tuple[bool, str]:
    """测试 Supabase 连接，返回 (ok, 详细信息)。"""
    url, key, bucket = _get_secrets()
    if not url or not key:
        return False, "SUPABASE_URL 或 SUPABASE_KEY 未在 Secrets 中配置"

    # 1. 测试 API 连通性
    try:
        r = requests.get(
            f"{url}/storage/v1/bucket",
            headers=_headers(key), timeout=10,
        )
        if r.status_code == 401:
            return False, "认证失败：SUPABASE_KEY 不正确（请使用 anon/public key）"
        if r.status_code not in (200, 400, 404):
            return False, f"API 返回异常状态：{r.status_code}，请检查 SUPABASE_URL 是否正确"
    except Exception as e:
        return False, f"无法连接到 Supabase：{e}"

    # 2. 确保 bucket 存在
    ok, msg = ensure_bucket()
    if not ok:
        return False, f"Bucket 操作失败：{msg}"

    # 3. 测试写入
    ok, msg = _upload("meta", {
        "test": True, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts": time.time(),
        "watchlist_cnt": 0, "scan_results_cnt": 0, "version": "4",
    })
    if ok:
        return True, f"连接正常 ✅  Bucket='{bucket}'，读写测试通过"
    return False, f"连接成功但写入失败：{msg}"


# ════════════════════════════════════════════════════════════════════
# 收藏夹完整同步（含所有 notes 字段）
# ════════════════════════════════════════════════════════════════════
def push_watchlist() -> Tuple[bool, str]:
    """
    上传完整收藏夹到 Supabase。
    同步所有字段：ticker / name / added_at / notes[]
      每条 note 包含：text（备注文字）/ img_url（图片链接）/ ts（时间戳）
    """
    try:
        import storage as loc
        items   = loc.load_watchlist()        # 完整列表，含 notes
        archive = loc.load_watchlist_archive()

        # 验证 notes 结构完整性
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
            return True, (f"收藏 {len(items)} 个品种、"
                          f"{note_cnt} 条备注（含图片链接）已同步到云端")
        return False, f"watchlist:{m1} / archive:{m2}"
    except Exception as e:
        return False, f"push_watchlist 异常：{e}"


def pull_watchlist() -> Tuple[bool, str]:
    """
    从云端拉取收藏夹，完整合并到本地。
    合并规则：
      · 本地有、云端也有 → 合并 notes（按 ts 去重，追加云端独有的备注）
      · 云端有、本地没有 → 追加到本地
      · 本地有、云端没有 → 保留本地（不删除）
    """
    try:
        import storage as loc

        cloud_items = _download("watchlist")
        if not isinstance(cloud_items, list):
            return False, "云端无收藏夹数据"

        local_items = loc.load_watchlist()
        local_map   = {i["ticker"].upper(): i
                       for i in local_items if isinstance(i, dict) and i.get("ticker")}
        added_cnt  = 0
        merged_notes = 0

        for ci in cloud_items:
            if not isinstance(ci, dict) or not ci.get("ticker"):
                continue
            tk = ci["ticker"].upper()

            if tk not in local_map:
                # 云端独有品种：完整追加（含所有备注）
                local_map[tk] = ci
                added_cnt += 1
            else:
                # 已存在：合并 notes（按 ts 去重）
                local_entry  = local_map[tk]
                local_notes  = local_entry.get("notes", [])
                local_ts_set = {n.get("ts") for n in local_notes
                                if isinstance(n, dict) and n.get("ts")}
                for cn in ci.get("notes", []):
                    if not isinstance(cn, dict):
                        continue
                    ts = cn.get("ts", "")
                    if ts and ts not in local_ts_set:
                        local_notes.append({
                            "text":    cn.get("text",    ""),
                            "img_url": cn.get("img_url", ""),
                            "ts":      ts,
                        })
                        local_ts_set.add(ts)
                        merged_notes += 1
                local_entry["notes"] = sorted(local_notes,
                                              key=lambda x: x.get("ts", ""))
                local_map[tk] = local_entry

        merged_list = list(local_map.values())
        loc.save_watchlist(merged_list)

        # 同步存档
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

        return True, (f"恢复完成：新增品种 {added_cnt} 个，"
                      f"补充备注 {merged_notes} 条，"
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

    wl_cnt = len(loc.load_watchlist())

    for key, loader in [
        ("scan_history", lambda: loc._load(loc.F_HIST,   [])),
        ("scan_results", lambda: loc._load(loc.F_ALLRES,  [])),
        ("scan_groups",  lambda: loc.load_scanned_groups()),
        ("config",       lambda: loc._load(loc.F_CFG,     {})),
    ]:
        try:
            data = loader()
            ok2, msg2 = _upload(key, data)
            results[key] = (ok2, msg2)
        except Exception as e:
            results[key] = (False, str(e))

    res_cnt = len(loc._load(loc.F_ALLRES, []))
    ok3, msg3 = _upload("meta", {
        "last_sync":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_sync_ts":     time.time(),
        "version":          "4",
        "watchlist_cnt":    wl_cnt,
        "scan_results_cnt": res_cnt,
    })
    results["meta"] = (ok3, msg3)
    return results


def pull_all() -> Dict[str, Any]:
    import storage as loc
    results: Dict[str, Any] = {}

    ok, msg = pull_watchlist()
    results["watchlist"] = (ok, msg)

    # 扫描历史
    cloud_hist = _download("scan_history")
    if isinstance(cloud_hist, list):
        local_hist = loc._load(loc.F_HIST, [])
        if not isinstance(local_hist, list):
            local_hist = []
        local_ids = {s.get("session_id") for s in local_hist if isinstance(s, dict)}
        added = 0
        for s in cloud_hist:
            if isinstance(s, dict) and s.get("session_id") not in local_ids:
                local_hist.append(s)
                added += 1
        if added:
            loc._save(loc.F_HIST, local_hist[-50:])
        results["scan_history"] = (True, f"补充 {added} 条会话")
    else:
        results["scan_history"] = (False, "无云端扫描历史")

    # 扫描结果
    cloud_res = _download("scan_results")
    if isinstance(cloud_res, list):
        local_res = loc._load(loc.F_ALLRES, [])
        if not isinstance(local_res, list):
            local_res = []
        merged_map = {
            (r["ticker"], r.get("timeframe", "")): r
            for r in local_res if isinstance(r, dict) and r.get("ticker")
        }
        added = 0
        for r in cloud_res:
            if isinstance(r, dict) and r.get("ticker"):
                k = (r["ticker"], r.get("timeframe", ""))
                if k not in merged_map:
                    merged_map[k] = r
                    added += 1
        if added:
            loc._save(loc.F_ALLRES, list(merged_map.values()))
        results["scan_results"] = (True, f"补充 {added} 条，共 {len(merged_map)} 条")
    else:
        results["scan_results"] = (False, "无云端扫描结果")

    # 品种组
    cloud_grp = _download("scan_groups")
    if isinstance(cloud_grp, list):
        merged_g = list(set(loc.load_scanned_groups()) | set(cloud_grp))
        loc._save(loc.F_GROUPS, merged_g)
        results["scan_groups"] = (True, f"{len(merged_g)} 个品种组")
    else:
        results["scan_groups"] = (False, "无品种组数据")

    # 配置
    if not loc._load(loc.F_CFG, {}):
        cloud_cfg = _download("config")
        if isinstance(cloud_cfg, dict):
            loc._save(loc.F_CFG, cloud_cfg)
            results["config"] = (True, "配置已恢复")
        else:
            results["config"] = (False, "无配置数据")
    else:
        results["config"] = (True, "本地配置存在，已跳过")

    return results


# ════════════════════════════════════════════════════════════════════
# 定时同步 / 启动恢复
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
            last_ts = float(meta.get("last_sync_ts", 0))
            if (now - last_ts) < SYNC_INTERVAL_SEC:
                _last_sync_ts = now
                return None
    _last_sync_ts = now
    ensure_bucket()
    return push_all()


def startup_restore() -> Dict[str, Any]:
    if not is_configured():
        return {"configured": False, "msg": "Supabase 未配置"}
    ok, msg = ensure_bucket()
    results = pull_all()
    results["configured"] = True
    results["bucket"]     = (ok, msg)
    return results


# ════════════════════════════════════════════════════════════════════
# 状态查询
# ════════════════════════════════════════════════════════════════════
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
        return "已到期，下次访问自动触发"
    h, m = int(remain // 3600), int((remain % 3600) // 60)
    return f"{h}h {m:02d}m 后"
