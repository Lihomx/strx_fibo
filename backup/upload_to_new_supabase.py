"""
一键将本地备份数据迁移上传至全新 Supabase 项目
运行方式：
python backup/upload_to_new_supabase.py
"""
import os
import sys
import json
import time
import requests

BACKUP_DIR = os.path.dirname(os.path.abspath(__file__))

# 在此处填入新 Supabase 项目的配置，或通过环境变量传入
NEW_SUPABASE_URL = os.environ.get("NEW_SUPABASE_URL", "")
NEW_SUPABASE_KEY = os.environ.get("NEW_SUPABASE_KEY", "")
NEW_SUPABASE_BUCKET = os.environ.get("NEW_SUPABASE_BUCKET", "strx-backup")

# 待迁移上传的文件清单
SYNC_FILES = [
    "watchlist.json",
    "watchlist_archive.json",
    "wl_categories.json",
    "hotlist.json",
    "hotlist_archive.json",
    "hl_categories.json",
    "config.json",
    "data_starred.json",
    "data_ticker_notes.json",
    "data_alerts.json",
    "data_triple_bottom.json",
    "data_tb_batch_state.json",
    "data_chartink.json",
    "data_link_clicks.json",
    "sync_meta.json",
]

def find_latest_snapshot_dir():
    """查找 backup/ 目录下最新的 snapshot 目录"""
    candidates = []
    if os.path.exists(BACKUP_DIR):
        for name in os.listdir(BACKUP_DIR):
            p = os.path.join(BACKUP_DIR, name)
            if os.path.isdir(p) and name.startswith("snapshot_"):
                candidates.append(p)
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
    return None

def ensure_bucket(url: str, key: str, bucket: str) -> bool:
    """确保新 Supabase 中的存储桶已创建且为公开/可读写"""
    bucket_url = f"{url}/storage/v1/bucket"
    hdrs = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    try:
        r = requests.get(f"{bucket_url}/{bucket}", headers=hdrs, timeout=10)
        if r.status_code == 200:
            print(f"  📦 Bucket '{bucket}' 存在验证成功。")
            return True
        print(f"  📦 Bucket '{bucket}' 不存在，正在自动创建...")
        create_r = requests.post(
            bucket_url, headers=hdrs,
            json={"id": bucket, "name": bucket, "public": True}, timeout=10
        )
        if create_r.status_code in (200, 201):
            print(f"  ✅ Bucket '{bucket}' 创建成功！")
            return True
        print(f"  ❌ Bucket 创建失败 (HTTP {create_r.status_code}): {create_r.text}")
        return False
    except Exception as e:
        print(f"  ❌ 验证/创建 Bucket 异常: {e}")
        return False

def main():
    print("=" * 60)
    print("🚀 开始迁移备份数据至新 Supabase 项目...")
    print("=" * 60)
    
    url = NEW_SUPABASE_URL.strip().rstrip("/")
    key = NEW_SUPABASE_KEY.strip()
    bucket = NEW_SUPABASE_BUCKET.strip()
    
    if not url or not key:
        print("💡 请输入新 Supabase 项目的连接信息：")
        url = input("  1. 新 Project URL (如 https://xxxx.supabase.co): ").strip().rstrip("/")
        key = input("  2. 新 service_role key (或 anon key): ").strip()
        b_input = input(f"  3. Bucket 名称 (直接回车默认 '{bucket}'): ").strip()
        if b_input:
            bucket = b_input
            
    if not url or not key:
        print("❌ 错误：缺少新 Supabase 的 URL 或 Key！")
        sys.exit(1)
        
    source_dir = find_latest_snapshot_dir()
    if not source_dir:
        # 如果没有 snapshot 目录，检查本地 data/ 目录作为备选源
        local_data_dir = os.path.join(os.path.dirname(BACKUP_DIR), "data")
        if os.path.exists(local_data_dir):
            source_dir = local_data_dir
            print(f"💡 未找到 snapshot 备份目录，将使用本地 data/ 目录: {source_dir}")
        else:
            print("❌ 错误：未找到任何可用的本地备份或 data 目录！请先运行 backup_from_supabase.py")
            sys.exit(1)
    else:
        print(f"📂 使用备份源目录: {source_dir}")
        
    print(f"📡 目标新 Supabase: {url}")
    print(f"📦 目标 Bucket: {bucket}\n")
    
    if not ensure_bucket(url, key, bucket):
        print("⚠️ 无法确认 Bucket 状态，尝试直接上传...\n")
        
    hdrs = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/octet-stream",
        "x-upsert": "true",
    }
    
    success_count = 0
    fail_count = 0
    
    for fname in SYNC_FILES:
        local_file = os.path.join(source_dir, fname)
        if not os.path.exists(local_file):
            print(f"  ⚪ [跳过] {fname:<25} (本地源文件不存在)")
            continue
            
        try:
            with open(local_file, "rb") as f:
                payload = f.read()
                
            # 特殊优化：针对 data_tb_batch_state.json，剔除 all_tickers 以减少体积
            if fname == "data_tb_batch_state.json":
                try:
                    state_obj = json.loads(payload.decode("utf-8"))
                    if isinstance(state_obj, dict) and "all_tickers" in state_obj:
                        state_obj["all_tickers"] = [] # 清空大体积数组，本地自动按 symbol_groups 重建
                        payload = json.dumps(state_obj, ensure_ascii=False).encode("utf-8")
                except Exception:
                    pass
                    
            path = f"latest/{fname}"
            obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
            
            r = requests.post(obj_url, headers=hdrs, data=payload, timeout=30)
            if r.status_code in (200, 201):
                print(f"  ✅ [上传成功] {fname:<25} ({len(payload)/1024.0:8.2f} KB)")
                success_count += 1
            else:
                # 尝试 PUT
                r2 = requests.put(obj_url, headers=hdrs, data=payload, timeout=30)
                if r2.status_code in (200, 201):
                    print(f"  ✅ [覆盖成功] {fname:<25} ({len(payload)/1024.0:8.2f} KB)")
                    success_count += 1
                else:
                    print(f"  ❌ [失败] {fname:<25} (HTTP {r.status_code} / {r2.status_code})")
                    fail_count += 1
        except Exception as e:
            print(f"  ❌ [异常] {fname:<25} ({e})")
            fail_count += 1
            
    print("\n" + "=" * 60)
    print(f"🎉 迁移上传完成！")
    print(f"  - 成功上传: {success_count} 个文件")
    print(f"  - 失败/异常: {fail_count} 个文件")
    print("=" * 60)
    print("\n👉 接下来的步骤：")
    print("1. 登录 Streamlit Cloud (https://share.streamlit.io/)")
    print("2. 进入 strx_fibo 应用的 Settings -> Secrets")
    print("3. 将 SUPABASE_URL 与 SUPABASE_KEY 更新为新项目的 URL 与 Key！")

if __name__ == "__main__":
    main()
