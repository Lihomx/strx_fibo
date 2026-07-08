import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import storage


class TestStorage(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
        # Patch all file paths in storage to point to files in the temp directory
        self.patches = [
            patch("storage.F_CFG", os.path.join(self.test_dir, "data_config.json")),
            patch("storage.F_HIST", os.path.join(self.test_dir, "data_history.json")),
            patch("storage.F_RES", os.path.join(self.test_dir, "data_results.json")),
            patch("storage.F_ALLRES", os.path.join(self.test_dir, "data_allresults.json")),
            patch("storage.F_ALERTS", os.path.join(self.test_dir, "data_alerts.json")),
            patch("storage.F_GROUPS", os.path.join(self.test_dir, "data_groups.json")),
            patch("storage.F_WATCHLIST", os.path.join(self.test_dir, "data_watchlist.json")),
            patch("storage.F_WATCHLIST_ARCHIVE", os.path.join(self.test_dir, "data_watchlist_archive.json")),
            patch("storage.F_TRIPLE_BOTTOM", os.path.join(self.test_dir, "data_triple_bottom.json")),
            patch("storage._BACKUP_DIR", os.path.join(self.test_dir, "backups")),
            patch("storage.F_SCAN_SNAPSHOT_DIR", os.path.join(self.test_dir, "scan_snapshots")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        # Stop all patches
        for p in self.patches:
            p.stop()
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_config_operations(self):
        # Default config should be returned if file doesn't exist
        cfg = storage.load_config()
        self.assertEqual(cfg["lookback"], 100)

        # Save config and verify it's loaded correctly
        cfg["lookback"] = 150
        self.assertTrue(storage.save_config(cfg))
        loaded_cfg = storage.load_config()
        self.assertEqual(loaded_cfg["lookback"], 150)

    def test_watchlist_operations(self):
        # Watchlist should be empty initially
        self.assertEqual(storage.load_watchlist(), [])

        # Add item to watchlist
        self.assertTrue(storage.add_to_watchlist("AAPL", "Apple Inc.", "Test Note"))
        watchlist = storage.load_watchlist()
        self.assertEqual(len(watchlist), 1)
        self.assertEqual(watchlist[0]["ticker"], "AAPL")
        self.assertEqual(watchlist[0]["name"], "Apple Inc.")
        self.assertEqual(len(watchlist[0]["notes"]), 1)
        self.assertEqual(watchlist[0]["notes"][0]["text"], "Test Note")

        # Duplicate item should not be added
        self.assertFalse(storage.add_to_watchlist("AAPL", "Apple Inc."))

        # Add notes
        self.assertTrue(storage.add_watchlist_note("AAPL", "Second Note"))
        watchlist = storage.load_watchlist()
        self.assertEqual(len(watchlist[0]["notes"]), 2)
        self.assertEqual(watchlist[0]["notes"][1]["text"], "Second Note")

        # Remove item (should move to archive)
        self.assertTrue(storage.remove_from_watchlist("AAPL"))
        self.assertEqual(storage.load_watchlist(), [])
        archive = storage.load_watchlist_archive()
        self.assertEqual(len(archive), 1)
        self.assertEqual(archive[0]["ticker"], "AAPL")

        # Restore from archive
        self.assertTrue(storage.restore_from_archive("AAPL"))
        self.assertEqual(len(storage.load_watchlist()), 1)
        self.assertEqual(storage.load_watchlist_archive(), [])

    def test_sharded_results(self):
        # Initial results should be empty
        self.assertEqual(storage.load_latest_results(), [])
        
        session_row = {"session_id": "test_session_1", "scan_date": "2026-07-08"}
        result_rows = [
            {"session_id": "test_session_1", "scan_date": "2026-07-08", "ticker": "AAPL", "timeframe": "Daily", "in_zone": True},
            {"session_id": "test_session_1", "scan_date": "2026-07-08", "ticker": "MSFT", "timeframe": "Weekly", "in_zone": False}
        ]
        
        # Save scan
        self.assertTrue(storage.save_scan(session_row, result_rows))
        
        # Verify latest results loaded
        latest = storage.load_latest_results()
        self.assertEqual(len(latest), 2)
        
        # Verify session results loaded
        session_res = storage.load_session_results("test_session_1")
        self.assertEqual(len(session_res), 2)

    def test_triple_bottom_operations(self):
        # Should be empty initially
        self.assertEqual(storage.load_triple_bottom(), [])

        test_data = [
            {
                "symbol": "AAPL",
                "period": "Daily",
                "pattern": "完美三重底 (Perfect Triple Bottom)",
                "confidence": 0.9,
                "low1": 150.0,
                "low2": 150.2,
                "low3": 149.9,
                "note": "测试完美三重底",
            }
        ]

        # Save and load
        self.assertTrue(storage.save_triple_bottom(test_data))
        loaded = storage.load_triple_bottom()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["symbol"], "AAPL")
        self.assertEqual(loaded[0]["pattern"], "完美三重底 (Perfect Triple Bottom)")


if __name__ == "__main__":
    unittest.main()
