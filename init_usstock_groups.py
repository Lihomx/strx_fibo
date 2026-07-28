"""
init_usstock_groups.py — 预置全量美股分组及全量品种库
"""
import uuid
import sys
import storage
import usstock_fetcher

sys.stdout.reconfigure(encoding='utf-8')

def populate_usstock_groups():
    print("开始获取全量美股 (NASDAQ / NYSE / AMEX) 数据...")
    
    # 1. 拉取全量美股
    all_us = usstock_fetcher.get_all_us_shares()
    print(f"已成功获取 {len(all_us)} 支美股股票")
    if not all_us:
        print("未获取到美股数据，跳过")
        return

    # 2. 存入品种明细 data_symbols.json
    existing_symbols = storage.load_symbols()
    existing_map = {s["ticker"]: s for s in existing_symbols}
    
    added_sym_count = 0
    for item in all_us:
        tk = item["ticker"]
        nm = item["name"]
        if tk not in existing_map:
            existing_symbols.append({
                "ticker": tk,
                "name": nm,
                "source": "美股全量自动导入",
                "added_at": storage._now_str()
            })
            existing_map[tk] = True
            added_sym_count += 1
            
    storage.save_symbols(existing_symbols)
    print(f"成功保存 {added_sym_count} 个新美股品种到品种库")
    
    # 3. 准备美股全量分组并存盘
    group_name = "🇺🇸 美股 - 全量美股 (NASDAQ/NYSE/AMEX)"
    tickers = [s["ticker"] for s in all_us]
    
    existing_groups = storage.load_symbol_groups()
    target_g = next((g for g in existing_groups if g["name"] == group_name), None)
    if not target_g:
        target_g = {
            "id": str(uuid.uuid4())[:8],
            "name": group_name,
            "tickers": [],
            "created_at": storage._now_str()
        }
        existing_groups.append(target_g)
        
    t_set = set(target_g.get("tickers", []))
    t_set.update(tickers)
    target_g["tickers"] = list(t_set)
    print(f"分组 [{repr(group_name)}] 现有 {len(target_g['tickers'])} 个代码")
    
    storage.save_symbol_groups(existing_groups)
    print("全量美股分组预置导入成功！")

if __name__ == "__main__":
    populate_usstock_groups()
