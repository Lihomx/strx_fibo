"""
从旧 Supabase 数据库一键完整备份所有核心数据到本地 backup/ 目录
运行方式：
python backup/backup_from_supabase.py
"""
import os
import sys
import json
import time
import requests

BACKUP_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BACKUP_DIR, f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}")

# 支持从 secrets.toml 或环境变量读取，也可以直接在这里填写
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "strx-backup")

# 如果环境变量未设置，尝试读取 .streamlit/secrets.toml
if not SUPABASE_URL or not SUPABASE_KEY:
    secrets_path = os.path.join(os.path.dirname(BACKUP_DIR), ".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPABASE_URL"):
                        SUPABASE_URL = line.split("=", 1)[1].strip().strip('"\'')
                    elif line.startswith("SUPABASE_KEY"):
                        SUPABASE_KEY = line.split("=", 1)[1].strip().strip('"\'')
                    elif line.startswith("SUPABASE_BUCKET"):
                        SUPABASE_BUCKET = line.split("=", 1)[1].strip().strip('"\'')
        except Exception as e:
            print(f"读取 secrets.toml 异常: {e}")

# 需备份的文件清单（存储在 latest/ 目录下）
BACKUP_FILES = [
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

def main():
    print("=" * 60)
    print("🚀 开始从 Supabase 备份数据到本地...")
    print("=" * 60)
    
    url = SUPABASE_URL.strip().rstrip("/")
    key = SUPABASE_KEY.strip()
    bucket = SUPABASE_BUCKET.strip()
    
    if not url or not key:
        print("❌ 错误：未获取到 SUPABASE_URL 或 SUPABASE_KEY！")
        print("请在 .streamlit/secrets.toml 中配置，或设置系统环境变量 SUPABASE_URL 与 SUPABASE_KEY。")
        sys.exit(1)
        
    print(f"📡 连接目标 Supabase: {url}")
    print(f"📦 存储 Bucket: {bucket}")
    
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"💾 本地备份保存路径: {OUT_DIR}\n")
    
    hdrs = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    
    success_count = 0
    fail_count = 0
    total_bytes = 0
    
    for fname in BACKUP_FILES:
        path = f"latest/{fname}"
        obj_url = f"{url}/storage/v1/object/{bucket}/{path}"
        try:
            r = requests.get(obj_url, headers=hdrs, timeout=30)
            if r.status_code == 200:
                content = r.content
                out_file = os.path.join(OUT_DIR, fname)
                with open(out_file, "wb") as f:
                    f.write(content)
                size_kb = len(content) / 1024.0
                total_bytes += len(content)
                print(f"  ✅ [成功] {fname:<25} ({size_kb:8.2f} KB)")
                success_count += 1
            elif r.status_code in (400, 404):
                print(f"  ⚪ [跳过] {fname:<25} (云端不存在此文件)")
            else:
                print(f"  ❌ [失败] {fname:<25} (HTTP {r.status_code}: {r.text[:100]})")
                fail_count += 1
        except Exception as e:
            print(f"  ❌ [异常] {fname:<25} ({e})")
            fail_count += 1
            
    print("\n" + "=" * 60)
    print(f"🎉 备份完成！")
    print(f"  - 成功下载: {success_count} 个文件")
    print(f"  - 失败/异常: {fail_count} 个文件")
    print(f"  - 总数据体积: {total_bytes / (1024 * 1024):.2f} MB")
    print(f"  - 备份目录: {OUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
