# Background Resident Daemon for Real-Time Alerts and Scans

This plan outlines the design and implementation of a background resident daemon (`daemon.py`) that runs 24/7 on a local server or PC. It automatically scans Watchlist and Hotlist assets, sends real-time Fibo alerts via configured Telegram/DingTalk channels, and synchronizes the results to Supabase so that they are instantly available on the Streamlit Cloud web interface.

---

## Proposed Changes

### 1. ⚙️ Background Daemon Script
Create a new standalone resident script [NEW] [daemon.py](file:///d:/Google/strxfibo/daemon.py).

#### Features:
1. **Ticker Aggregation**: Automatically loads all active tickers from:
   - Watchlist (`data_watchlist.json`)
   - Hotlist (`data_hotlist.json`)
   This ensures fast execution (usually < 2 minutes) and minimizes API rate-limiting issues.
2. **Periodic Interval Execution**: Runs a full scan on the aggregated tickers every $N$ minutes (configurable, default is 15 minutes).
3. **Daily Full Scan (Optional)**: If `scan_enabled` is set to `true` in `data_config.json`, the daemon can run a daily full scan of the entire global asset registry (`ASSETS` from `assets.py`) at the specified `scan_hour` and `scan_minute`.
4. **Real-time Alerts**: Triggers `alerts.dispatch_alerts()` to notify the user via DingTalk and Telegram if any ticker enters the Golden Retracement Zone (with cooldown check to prevent spamming).
5. **Cloud Sync Pipeline**: Runs `cloud_sync.push_all()` after each scan to upload results, history, and alert logs to Supabase, enabling the remote Streamlit Cloud app to display the latest status.
6. **Robustness**: Catches network and API exceptions, logs errors to both stdout and a rolling `daemon.log` file, and keeps running without crashing.

---

### 2. 🗂️ Stale Files Cleanup
Refactor or clean up [scheduler.py](file:///d:/Google/strxfibo/scheduler.py) and [run_scan_only.py](file:///d:/Google/strxfibo/run_scan_only.py):
- Update import paths in `run_scan_only.py` (change `from core.scanner` to `import scanner`, etc.) to match the flattened root directory structure so they can still be used as simple one-off cron tasks.
- Keep them as optional helper files or document them in the walkthrough.

---

## Verification Plan

### Manual Verification
1. **Dry Run**: Run the daemon script locally with a test environment (`python daemon.py --once --verbose`) to verify it loads tickers, fetches data, performs Fibo calculations, and checks cooldown.
2. **Alert Triggering**: Temporarily enable DingTalk/Telegram test webhook in `data_config.json` and verify the daemon sends alerts for any newly matched tickers.
3. **Cloud Upload Verification**: Verify the logs show successful Supabase sync (`cloud_sync.push_all()`) and check that the Streamlit Cloud Web UI displays the matching results and logs.
