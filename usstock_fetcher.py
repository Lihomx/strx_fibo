"""
usstock_fetcher.py — 动态获取全量美股 (NASDAQ / NYSE / AMEX ~7000+ 支)
================================================================
数据源：NASDAQ 官方 OpenAPI (https://api.nasdaq.com/api/screener/stocks)
自动清洗 symbol（如将 / 替换为 -、过滤权证等），生成 yFinance 标准格式
"""

import json
import urllib.request
from typing import List, Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

def get_all_us_shares(limit: int = 7500) -> List[Dict[str, str]]:
    """从 Nasdaq 官方 Screener API 获取全量美股列表"""
    url = f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit={limit}"
    req = urllib.request.Request(url, headers=HEADERS)
    results = []
    seen = set()

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8")
            data = json.loads(content)
            rows = data.get("data", {}).get("table", {}).get("rows", [])
            
            for row in rows:
                raw_sym = str(row.get("symbol", "")).strip()
                name = str(row.get("name", "")).strip()
                if not raw_sym or raw_sym in seen:
                    continue
                
                # 清洗特殊字符 (例如 BRK/B -> BRK-B)
                yf_ticker = raw_sym.replace("/", "-").replace("^", "-")
                
                # 过滤测试代码或长度异常代码
                if len(yf_ticker) > 6 and "-" in yf_ticker:
                    continue
                if any(w in name.lower() for w in ["warrant", "right", "unit"]):
                    continue
                    
                seen.add(raw_sym)
                results.append({"ticker": yf_ticker, "name": name, "raw_symbol": raw_sym})
                
    except Exception as e:
        print(f"Error fetching US stocks: {e}")

    return results

if __name__ == "__main__":
    stocks = get_all_us_shares()
    print(f"Total US shares fetched: {len(stocks)}")
    if stocks:
        print("Sample:", stocks[:5])
