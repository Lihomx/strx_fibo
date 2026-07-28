"""
init_ashare_groups.py — 方案一落地脚本
生成 A 股核心指数与全量分组数据，存储在 storage 中
"""
import uuid
import sys
import storage
import ashare_fetcher

sys.stdout.reconfigure(encoding='utf-8')

def populate_ashare_groups():
    print("开始获取 A 股全量及核心指数数据...")
    
    # 1. 拉取全量 A 股
    all_a = ashare_fetcher.get_all_a_shares(max_stocks=5600)
    print(f"1. 已成功获取 {len(all_a)} 支 A 股股票")
    
    # 2. 分筛选板块
    hs300 = [s for s in all_a if not s["ticker"].endswith(".BJ")][:300]
    sz50 = [s for s in all_a if s["ticker"].endswith(".SS") and s["raw_code"].startswith("60")][:50]
    cyb = [s for s in all_a if s["ticker"].endswith(".SZ") and s["raw_code"].startswith("300")][:300]
    kc50 = [s for s in all_a if s["ticker"].endswith(".SS") and s["raw_code"].startswith("688")][:200]
    
    print(f"   - 沪深300精选: {len(hs300)} 支")
    print(f"   - 上证50超大盘: {len(sz50)} 支")
    print(f"   - 创业板精选: {len(cyb)} 支")
    print(f"   - 科创板精选: {len(kc50)} 支")

    # 3. 准备合并写入品种库明细 data_symbols.json
    existing_symbols = storage.load_symbols()
    existing_map = {s["ticker"]: s for s in existing_symbols}
    
    added_sym_count = 0
    for item in all_a:
        tk = item["ticker"]
        nm = item["name"]
        if tk not in existing_map:
            existing_symbols.append({
                "ticker": tk,
                "name": nm,
                "source": "A股自动导入",
                "added_at": storage._now_str()
            })
            existing_map[tk] = True
            added_sym_count += 1
            
    storage.save_symbols(existing_symbols)
    print(f"成功保存 {added_sym_count} 个新品种到品种库")
    
    # 4. 准备分组并存盘
    group_defs = [
        ("🇨🇳 A股 - 全量A股 (主板/创业/科创/北交)", all_a),
        ("🇨🇳 A股 - 沪深300 (核心蓝筹)", hs300),
        ("🇨🇳 A股 - 上证50 (超大盘)", sz50),
        ("🇨🇳 A股 - 创业板精选", cyb),
        ("🇨🇳 A股 - 科创板精选", kc50),
    ]
    
    existing_groups = storage.load_symbol_groups()
    
    for g_name, stock_list in group_defs:
        if not stock_list:
            continue
        tickers = [s["ticker"] for s in stock_list]
        target_g = next((g for g in existing_groups if g["name"] == g_name), None)
        if not target_g:
            target_g = {
                "id": str(uuid.uuid4())[:8],
                "name": g_name,
                "tickers": [],
                "created_at": storage._now_str()
            }
            existing_groups.append(target_g)
        
        t_set = set(target_g.get("tickers", []))
        t_set.update(tickers)
        target_g["tickers"] = list(t_set)
        print(f"Group [{repr(g_name)}] now has {len(target_g['tickers'])} tickers")
        
    storage.save_symbol_groups(existing_groups)
    print("A-share stock groups successfully pre-populated!")

if __name__ == "__main__":
    populate_ashare_groups()
