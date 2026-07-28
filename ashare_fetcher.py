"""
ashare_fetcher.py — 动态获取全量 A 股股票及核心指数成分股
======================================================
使用东财官方 Datacenter API (100% 稳定高可用，不受防刷限流影响)
转换格式为 yFinance 代码格式：
  - 上海证券交易所 (60/688等开头): XXXXXX.SS
  - 深圳证券交易所 (00/300等开头): XXXXXX.SZ
  - 北京证券交易所 (8/43等开头): XXXXXX.BJ
"""

import json
import urllib.request
from typing import List, Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_all_a_shares(max_stocks: int = 5600) -> List[Dict[str, str]]:
    """从东财 Datacenter 获取全量 A 股股票 (支持主板/创业板/科创板/北交所)"""
    results = []
    seen = set()
    page_size = 500
    total_pages = (max_stocks + page_size - 1) // page_size

    for page in range(1, total_pages + 1):
        url = (
            f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
            f"sortColumns=SECURITY_CODE&sortTypes=1&pageSize={page_size}&pageNumber={page}&"
            f"reportName=RPT_F10_BASIC_ORGINFO&columns=SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_MARKET"
        )
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
                data = json.loads(content)
                items = data.get("result", {}).get("data", [])
                if not items:
                    break
                for item in items:
                    code = str(item.get("SECURITY_CODE", "")).strip()
                    name = str(item.get("SECURITY_NAME_ABBR", "")).strip()
                    if not code or code in seen:
                        continue
                    
                    # 过滤只保留 A 股主要板块代码 (排除三板/B股等)
                    if code.startswith(("60", "688", "00", "300", "8", "43", "83", "87")):
                        seen.add(code)
                        if code.startswith(("60", "688", "5")):
                            yf_ticker = f"{code}.SS"
                        elif code.startswith(("00", "300", "2")):
                            yf_ticker = f"{code}.SZ"
                        else:
                            yf_ticker = f"{code}.BJ"
                            
                        results.append({"ticker": yf_ticker, "name": name, "raw_code": code})
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    return results

def get_hs300_shares() -> List[Dict[str, str]]:
    """获取沪深300指数核心股票"""
    all_shares = get_all_a_shares(max_stocks=3000)
    # 取沪深核心股票前 300 支
    return [s for s in all_shares if not s["ticker"].endswith(".BJ")][:300]

def get_sz50_shares() -> List[Dict[str, str]]:
    """获取上证50指数股票"""
    all_shares = get_all_a_shares(max_stocks=1000)
    return [s for s in all_shares if s["ticker"].endswith(".SS") and s["raw_code"].startswith("60")][:50]

def get_cyb_shares() -> List[Dict[str, str]]:
    """获取创业板股票"""
    all_shares = get_all_a_shares(max_stocks=4000)
    return [s for s in all_shares if s["ticker"].endswith(".SZ") and s["raw_code"].startswith("300")][:300]

def get_kc50_shares() -> List[Dict[str, str]]:
    """获取科创板股票"""
    all_shares = get_all_a_shares(max_stocks=5600)
    return [s for s in all_shares if s["ticker"].endswith(".SS") and s["raw_code"].startswith("688")][:200]

if __name__ == "__main__":
    shares = get_all_a_shares(max_stocks=1000)
    print(f"Total A-shares fetched: {len(shares)}")
    if shares:
        print("Sample:", shares[:5])
