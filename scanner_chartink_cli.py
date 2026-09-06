#!/usr/bin/env python3
"""
scanner_chartink_cli.py — Chartink 4H Breakout 7条突破规则无头命令行扫描器
================================================================================
专用于 GitHub Actions 定时无头调度、外部自动化系统或本地终端独立运行。
支持：
  1. 三大股票池快速切换：
     - us: 🇺🇸 全量美股 (约 6,000+ 支)
     - cn: 🇨🇳 全量 A 股 (约 5,000+ 支)
     - all: 🌐 全量市场去重合并 (11,000+ 支)
  2. 流动性均量自动过滤，防止仙股/僵尸股耗时
  3. 64 线程极速并发与智能重采样 (1H -> 4H / 2H)
  4. 7 条规则 100% 严苛突破判定、阶段划分与跑势进度计算
  5. 扫描完成后直连上传至 Supabase Storage，自动覆盖更新并保留时间戳快照
"""

import os
import sys
import time
import json
import socket
import argparse
import logging
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
import pandas as pd
import numpy as np

# ⏱️ 强制全局网络超时防卡死 (8秒自动熔断)
socket.setdefaulttimeout(8)

# 🌐 Windows 终端兼容性：防止 GBK 编码输出 Emoji 时崩溃
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 🤫 全局静音警告
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
logging.captureWarnings(True)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# ── 直连 Yahoo v8 API Session ─────────────────────────────────────────
_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=1)
_SESSION.mount("https://", _adapter)
_SESSION.mount("http://", _adapter)
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def _fetch_direct_chart(ticker: str, range_str: str = "60d", interval: str = "1h") -> pd.DataFrame:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval}&indicators=quote&includeTimestamps=true"
        r = _SESSION.get(url, timeout=(2.5, 4.0))
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result")
            if result:
                res = result[0]
                timestamps = res.get("timestamp", [])
                if timestamps:
                    quote = res.get("indicators", {}).get("quote", [{}])[0]
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", [])
                    vols = quote.get("volume", [])
                    
                    df = pd.DataFrame({
                        "open": opens,
                        "high": highs,
                        "low": lows,
                        "close": closes,
                        "volume": vols
                    }, index=pd.to_datetime(timestamps, unit="s")).dropna(subset=["close"])
                    return df
    except Exception:
        pass
    return None

def _fetch(ticker: str, interval: str, period: str = "6mo") -> pd.DataFrame:
    range_map = {"1y": "1y", "2mo": "60d", "6mo": "6mo", "1mo": "1mo", "5d": "5d"}
    r_str = range_map.get(period, "60d")
    return _fetch_direct_chart(ticker, range_str=r_str, interval=interval)

# ── 指标计算 ──────────────────────────────────────────────────────────
def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _ichimoku(high: pd.Series, low: pd.Series, t: int = 9, k: int = 26, s: int = 52):
    tenkan  = (high.rolling(t).max() + low.rolling(t).min()) / 2
    kijun   = (high.rolling(k).max() + low.rolling(k).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(k)
    senkou_b = ((high.rolling(s).max() + low.rolling(s).min()) / 2).shift(k)
    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    return cloud_top, cloud_bot

def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 7, multiplier: float = 3.0) -> pd.Series:
    hl2 = (high + low) / 2
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    basic_upper = (hl2 + (multiplier * atr)).values
    basic_lower = (hl2 - (multiplier * atr)).values
    c = close.values
    n = len(c)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    st_line = np.zeros(n)
    trend = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(basic_upper[i]):
            continue
        final_upper[i] = basic_upper[i] if (basic_upper[i] < final_upper[i-1] or c[i-1] > final_upper[i-1]) else final_upper[i-1]
        final_lower[i] = basic_lower[i] if (basic_lower[i] > final_lower[i-1] or c[i-1] < final_lower[i-1]) else final_lower[i-1]
        if trend[i-1] == 1:
            if c[i] < final_lower[i]:
                trend[i] = -1
                st_line[i] = final_upper[i]
            else:
                trend[i] = 1
                st_line[i] = final_lower[i]
        else:
            if c[i] > final_upper[i]:
                trend[i] = 1
                st_line[i] = final_lower[i]
            else:
                trend[i] = -1
                st_line[i] = final_upper[i]
    return pd.Series(st_line, index=close.index)

# ── 7条规则突破校验核心 ──────────────────────────────────────────────
def _check_ticker_chartink(ticker: str, min_volume: int = 100000) -> dict:
    res = {
        "ticker": ticker,
        "symbol": ticker,
        "passed": False,
        "details": [],
        "error": None,
        "close": None,
        "volume_4h": None,
        "avg_volume_20": 0.0,
        "turnover": 0.0,
        "rsi": None,
        "cloud_top": None,
        "cloud_bot": None,
        "supertrend": None,
        "close_2h_m2": None,
        "vol_ratio_0": None,
        "vol_ratio_1": None,
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        # 1. 获取日线数据 (1y)
        df_1d = _fetch(ticker, "1d", "1y")
        if df_1d is None or len(df_1d) < 60:
            res["error"] = "日线数据不足"
            return res

        # 均量过滤
        vols_d = df_1d["volume"].dropna().values
        avg_v20 = float(np.mean(vols_d[-20:])) if len(vols_d) >= 20 else float(np.mean(vols_d))
        latest_c = float(df_1d["close"].iloc[-1])
        res["avg_volume_20"] = avg_v20
        res["turnover"] = avg_v20 * latest_c

        if min_volume > 0 and avg_v20 < min_volume:
            res["error"] = f"均量不足 ({avg_v20:,.0f} < {min_volume:,.0f})"
            return res

        # 2. 获取 1H 数据并重采样为 4H 与 2H
        df_1h = _fetch(ticker, "1h", "2mo")
        df_4h = None
        if df_1h is not None and len(df_1h) >= 4:
            try:
                df_4h = df_1h.resample("4h").agg({
                    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                }).dropna(subset=["close"])
            except Exception:
                pass

        if df_4h is None or len(df_4h) < 5:
            df_4h = _fetch(ticker, "4h", "6mo")

        if df_4h is None or len(df_4h) < 5:
            res["error"] = "4H 数据不足"
            return res

        # 2H 重采样
        df_2h = None
        if df_1h is not None and len(df_1h) >= 2:
            try:
                df_2h = df_1h.resample("2h").agg({
                    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
                }).dropna(subset=["close"])
            except Exception:
                pass

        close_d = df_1d["close"]
        high_d  = df_1d["high"]
        low_d   = df_1d["low"]

        rsi_ser = _rsi(close_d, 14)
        cloud_top, cloud_bot = _ichimoku(high_d, low_d, 9, 26, 52)
        supertrend_ser = _supertrend(high_d, low_d, close_d, 7, 3.0)

        c_d   = float(close_d.iloc[-1])
        rsi_v = float(rsi_ser.iloc[-1])    if not pd.isna(rsi_ser.iloc[-1])    else None
        ct_v  = float(cloud_top.iloc[-1])  if not pd.isna(cloud_top.iloc[-1])  else None
        cb_v  = float(cloud_bot.iloc[-1])  if not pd.isna(cloud_bot.iloc[-1])  else None
        st_v  = float(supertrend_ser.iloc[-1]) if not pd.isna(supertrend_ser.iloc[-1]) else None

        vol_4h = df_4h["volume"]
        v0 = float(vol_4h.iloc[-1])
        v1 = float(vol_4h.iloc[-2])
        v2 = float(vol_4h.iloc[-3])
        v3 = float(vol_4h.iloc[-4]) if len(vol_4h) >= 4 else v2

        c_2h_m2 = None
        if df_2h is not None and len(df_2h) >= 3:
            c_2h_m2 = float(df_2h["close"].iloc[-3])

        vr0 = (v0 / max(v1, 1.0)) if v0 > v1 * 2 else (v1 / max(v2, 1.0))
        vr1 = (v1 / max(v2, 1.0)) if v1 > v2 * 1.5 else (v2 / max(v3, 1.0))

        res["close"]       = c_d
        res["volume_4h"]   = v0
        res["vol_ratio_0"] = round(vr0, 2)
        res["vol_ratio_1"] = round(vr1, 2)
        res["rsi"]         = rsi_v
        res["cloud_top"]   = ct_v
        res["cloud_bot"]   = cb_v
        res["supertrend"]  = st_v
        res["close_2h_m2"] = c_2h_m2

        # 7条突破规则判定
        rules = [
            {
                "id": "[0]",
                "desc": "4H Volume[0] > 4H Volume[-1] × 2 (或已完成根 > ×2)",
                "ok": bool((v0 > v1 * 2) or (v1 > v2 * 2)),
                "val": f"{v0:,.0f} vs {v1:,.0f}×2={v1*2:,.0f}" if (v0 > v1 * 2) else f"前根: {v1:,.0f} vs {v2:,.0f}×2={v2*2:,.0f}",
            },
            {
                "id": "[1]",
                "desc": "4H Volume[-1] > 4H Volume[-2] × 1.5 (或已完成根 > ×1.5)",
                "ok": bool((v1 > v2 * 1.5) or (v2 > v3 * 1.5)),
                "val": f"{v1:,.0f} vs {v2:,.0f}×1.5={v2*1.5:,.0f}" if (v1 > v2 * 1.5) else f"前前根: {v2:,.0f} vs {v3:,.0f}×1.5={v3*1.5:,.0f}",
            },
            {
                "id": "[2]",
                "desc": "Daily Close > Ichimoku Cloud Top(9,26,52)",
                "ok": bool((ct_v is not None) and (c_d > ct_v)),
                "val": f"Close={c_d:.4f}  CloudTop={ct_v:.4f}" if ct_v else "数据不足",
            },
            {
                "id": "[3]",
                "desc": "Daily RSI(14) > 50",
                "ok": bool((rsi_v is not None) and (rsi_v > 50)),
                "val": f"RSI={rsi_v:.2f}" if rsi_v else "数据不足",
            },
            {
                "id": "[4]",
                "desc": "Daily Close > Supertrend(7,3)",
                "ok": bool((st_v is not None) and (c_d > st_v)),
                "val": f"Close={c_d:.4f}  ST={st_v:.4f}" if st_v else "数据不足",
            },
            {
                "id": "[5]",
                "desc": "Daily Close > Ichimoku Cloud Bottom(9,26,52)",
                "ok": bool((cb_v is not None) and (c_d > cb_v)),
                "val": f"Close={c_d:.4f}  CloudBot={cb_v:.4f}" if cb_v else "数据不足",
            },
            {
                "id": "[6]",
                "desc": "Daily Close > 2H Close[-2]",
                "ok": bool((c_2h_m2 is not None) and (c_d > c_2h_m2)),
                "val": f"Close={c_d:.4f}  2H[-2]={c_2h_m2:.4f}" if c_2h_m2 else "2H数据不足",
            },
        ]

        is_passed = all(r["ok"] for r in rules)

        ref_p = ct_v if (ct_v and ct_v > 0) else (st_v if (st_v and st_v > 0) else c_d)
        if c_d and ref_p and c_d >= ref_p:
            prog = round(max(0.0, ((c_d - ref_p) / ref_p) * 100.0), 1)
        else:
            prog = 0.0

        if not is_passed or prog == 0.0:
            if cb_v and c_d < cb_v:
                status_str = "invalidated"
            else:
                status_str = "active"
        else:
            status_str = "confirmed"

        res["details"] = rules
        res["passed"]  = is_passed
        res["status"]  = status_str
        res["breakout_progress"] = prog
    except Exception as e:
        res["error"] = str(e)

    return res

# ── 股票池装载 ────────────────────────────────────────────────────────
def load_pool_tickers(pool: str = "us", base_dir: str = ".") -> list[str]:
    """根据选项读取股票池代码"""
    clean_pool = pool.strip().lower()
    groups_path = os.path.join(base_dir, "data_symbol_groups.json")
    symbols_path = os.path.join(base_dir, "data_symbols.json")
    
    a_tickers = []
    us_tickers = []

    # 1. 尝试从 groups 读取标准全量分组
    if os.path.exists(groups_path):
        try:
            with open(groups_path, "r", encoding="utf-8") as f:
                groups = json.load(f)
                for g in groups:
                    name = g.get("name", "")
                    if "全量A股" in name:
                        a_tickers.extend(g.get("tickers", []))
                    elif "全量美股" in name:
                        us_tickers.extend(g.get("tickers", []))
        except Exception as e:
            print(f"⚠️ 读取 {groups_path} 失败: {e}")

    # 2. 如果分组未命中，从 symbols.json 划分
    if (not a_tickers or not us_tickers) and os.path.exists(symbols_path):
        try:
            with open(symbols_path, "r", encoding="utf-8") as f:
                syms = json.load(f)
                for s in syms:
                    tk = str(s.get("ticker", "")).strip().upper()
                    if not tk:
                        continue
                    if tk.endswith((".SS", ".SZ", ".BJ")) or tk.isdigit():
                        if not a_tickers:
                            a_tickers.append(tk)
                    else:
                        if not us_tickers:
                            us_tickers.append(tk)
        except Exception as e:
            print(f"⚠️ 读取 {symbols_path} 失败: {e}")

    # 去重
    a_tickers = list(dict.fromkeys([t.strip().upper() for t in a_tickers if t]))
    us_tickers = list(dict.fromkeys([t.strip().upper() for t in us_tickers if t]))

    if clean_pool in ("cn", "a", "ashare"):
        return a_tickers
    elif clean_pool in ("us", "usa"):
        return us_tickers
    elif clean_pool in ("all", "global"):
        merged = list(dict.fromkeys(us_tickers + a_tickers))
        return merged
    else:
        print(f"⚠️ 未知股票池 '{pool}'，默认使用美股全量。")
        return us_tickers or ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

# ── 上传至 Supabase ──────────────────────────────────────────────────
def upload_to_supabase(data_dict: dict, url: str, key: str, bucket: str = "strx-backup") -> bool:
    if not url or not key:
        print("⚠️ 未配置 SUPABASE_URL 或 SUPABASE_KEY，跳过云端直传。")
        return False

    url = url.strip().rstrip("/")
    key = key.strip()
    bucket = bucket.strip()

    payload = json.dumps(data_dict, ensure_ascii=False).encode("utf-8")
    hdrs = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/octet-stream",
        "x-upsert": "true",
    }

    # 1. 覆盖 latest/data_chartink.json
    target_path = "latest/data_chartink.json"
    obj_url = f"{url}/storage/v1/object/{bucket}/{target_path}"
    
    print(f"☁️ 正在上传结果至 Supabase: {target_path} ...")
    success = False
    try:
        r = requests.post(obj_url, headers=hdrs, data=payload, timeout=30)
        if r.status_code in (200, 201):
            success = True
        elif r.status_code in (400, 409, 422):
            r2 = requests.put(obj_url, headers=hdrs, data=payload, timeout=30)
            if r2.status_code in (200, 201):
                success = True
            else:
                print(f"❌ 上传 latest 失败 (PUT {r2.status_code}): {r2.text[:200]}")
        else:
            print(f"❌ 上传 latest 失败 (POST {r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"❌ 上传网络异常: {e}")

    # 2. 写入快照 backups/chartink_{ts}_{size}.json
    if success:
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        size_b = len(payload)
        size_label = f"{size_b // 1024}kB" if size_b >= 1024 else f"{size_b}B"
        snap_path = f"backups/chartink_{ts_str}_{size_label}.json"
        snap_url = f"{url}/storage/v1/object/{bucket}/{snap_path}"
        try:
            requests.post(snap_url, headers=hdrs, data=payload, timeout=20)
            print(f"📁 云端快照备份成功: {snap_path}")
        except Exception:
            pass

    return success

# ── 主执行逻辑 ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Chartink 4H Breakout 7条规则突破无头扫描器")
    parser.add_argument("--pool", choices=["us", "cn", "all"], default="us", help="扫描股票池 (us=美股全量, cn=A股全量, all=全量市场)")
    parser.add_argument("--min-volume", type=int, default=100000, help="最低 20 日成交均量过滤 (默认 100,000)")
    parser.add_argument("--workers", type=int, default=64, help="并发扫描线程数 (默认 64)")
    parser.add_argument("--limit", type=int, default=0, help="测试用限制扫描支数 (0 表示不限制)")
    parser.add_argument("--no-upload", action="store_true", help="跳过 Supabase 上传")
    parser.add_argument("--supabase-url", default="", help="Supabase Project URL")
    parser.add_argument("--supabase-key", default="", help="Supabase API Key")
    parser.add_argument("--supabase-bucket", default="", help="Supabase Bucket")
    parser.add_argument("--output-csv", default="colab_chartink_results.csv", help="本地导出 CSV 路径")
    parser.add_argument("--output-json", default="data_chartink.json", help="本地导出 JSON 路径")
    
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    tickers = load_pool_tickers(args.pool, base_dir=base_dir)
    
    if args.limit > 0:
        tickers = tickers[:args.limit]

    total_tickers = len(tickers)
    pool_name_map = {"us": "🇺🇸 全量美股", "cn": "🇨🇳 全量 A 股", "all": "🌐 A股 + 美股全量市场"}
    print(f"\n" + "="*80)
    print(f"🚀 Chartink 4H Breakout 7条规则突破无头并发扫描启动")
    print(f"🎯 选定股票池: {pool_name_map.get(args.pool, args.pool)} (共 {total_tickers} 支标的)")
    print(f"📊 均量过滤: ≥ {args.min_volume:,} 股 | 线程并发: {args.workers}")
    print(f"⏱️ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"="*80 + "\n")
    sys.stdout.flush()

    if not tickers:
        print("❌ 未发现待扫描股票标的，退出。")
        sys.exit(1)

    start_time = time.time()
    completed = 0
    passed_records = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(_check_ticker_chartink, tk, args.min_volume): tk for tk in tickers}
        for future in as_completed(future_map):
            completed += 1
            tk = future_map[future]
            try:
                res = future.result()
                if res.get("passed"):
                    passed_records.append(res)
                    print(f"  🔥 [发现突破] {tk:8s} | Close: ${res['close']:.2f} | 4H Vol: {res['volume_4h']:,.0f} | RSI: {res['rsi']:.1f} | 阶段: {res['status']} ({res['breakout_progress']}%)")
                    sys.stdout.flush()
            except Exception:
                pass

            print_step = 100 if total_tickers > 1000 else 25
            if completed % print_step == 0 or completed == total_tickers:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 1
                rem = (total_tickers - completed) / rate
                speed = completed / elapsed if elapsed > 0 else 0
                pct = completed * 100 // total_tickers
                print(f"[{completed:5d}/{total_tickers}] 进度: {pct:3d}% ({speed:4.1f}只/秒) | 已检出 7条全达成: {len(passed_records):3d} 支 | 剩余约: {int(rem//60)}分{int(rem%60)}秒")
                sys.stdout.flush()

    total_min = (time.time() - start_time) / 60
    print(f"\n" + "="*80)
    print(f"🎉 扫描全部完成！总耗时 {total_min:.1f} 分钟")
    print(f"🏆 100% 满足全部 7 条 4H 突破规则标的: 共 {len(passed_records)} 支")
    print(f"="*80 + "\n")

    # 构建标准 JSON 结构
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out_payload = {
        "passed": passed_records,
        "failed": [],
        "errors": [],
        "scanned_at": now_str,
        "total": len(passed_records),
        "done_count": len(passed_records),
        "pool": args.pool,
        "min_volume": args.min_volume
    }

    # 1. 保存本地 JSON
    local_json_path = os.path.join(base_dir, args.output_json)
    try:
        with open(local_json_path, "w", encoding="utf-8") as f:
            json.dump(out_payload, f, ensure_ascii=False, indent=2)
        print(f"💾 本地 JSON 结果已保存: {local_json_path}")
    except Exception as e:
        print(f"⚠️ 保存本地 JSON 失败: {e}")

    # 2. 导出 CSV
    if passed_records:
        csv_rows = []
        for r in passed_records:
            details_str = json.dumps(r.get("details", []), ensure_ascii=False)
            csv_rows.append({
                "ticker": r.get("ticker", ""),
                "symbol": r.get("ticker", ""),
                "passed": 1 if r.get("passed") else 0,
                "status": r.get("status", "confirmed"),
                "breakout_progress": r.get("breakout_progress", 0.0),
                "close": r.get("close", ""),
                "volume_4h": r.get("volume_4h", ""),
                "vol_ratio_0": r.get("vol_ratio_0", ""),
                "vol_ratio_1": r.get("vol_ratio_1", ""),
                "avg_volume_20": r.get("avg_volume_20", 0),
                "turnover": r.get("turnover", 0),
                "rsi": r.get("rsi", ""),
                "cloud_top": r.get("cloud_top", ""),
                "cloud_bot": r.get("cloud_bot", ""),
                "supertrend": r.get("supertrend", ""),
                "close_2h_m2": r.get("close_2h_m2", ""),
                "details_json": details_str,
                "scan_time": r.get("scan_time", now_str)
            })
        out_df = pd.DataFrame(csv_rows)
        local_csv_path = os.path.join(base_dir, args.output_csv)
        out_df.to_csv(local_csv_path, index=False, encoding="utf-8-sig")
        print(f"💾 本地 CSV 结果已导出: {local_csv_path}")

    # 3. 直传 Supabase
    if not args.no_upload:
        sb_url = args.supabase_url or os.environ.get("SUPABASE_URL", "")
        sb_key = args.supabase_key or os.environ.get("SUPABASE_KEY", "")
        sb_bucket = args.supabase_bucket or os.environ.get("SUPABASE_BUCKET", "")
        
        # 尝试从 .streamlit/secrets.toml 读取 fallback
        if not sb_url or not sb_key or not sb_bucket:
            secrets_path = os.path.join(base_dir, ".streamlit", "secrets.toml")
            if os.path.exists(secrets_path):
                try:
                    import toml
                    sec = toml.load(secrets_path)
                    sb_url = sb_url or sec.get("SUPABASE_URL", "")
                    sb_key = sb_key or sec.get("SUPABASE_KEY", "")
                    sb_bucket = sb_bucket or sec.get("SUPABASE_BUCKET", "strx")
                except Exception:
                    pass

        sb_bucket = sb_bucket or "strx"

        if sb_url and sb_key:
            ok = upload_to_supabase(out_payload, sb_url, sb_key, sb_bucket)
            if ok:
                print("🎉 Supabase 全量覆盖上传完成！现在前往 Streamlit 页面点击「☁️ 从云端同步」即可立即看到最新突破品种！")
            else:
                print("⚠️ Supabase 上传失败，请检查网络或凭证配置。")
        else:
            print("💡 未检测到 Supabase 配置，跳过云端直传。如需直传，请设置环境变量 SUPABASE_URL 与 SUPABASE_KEY。")

if __name__ == "__main__":
    main()
