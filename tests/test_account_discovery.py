from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wxmoments import find_account  # noqa: E402


def _make_sns_db(root: Path, account: str, *, size: int, mtime_ns: int) -> Path:
    sns_db = root / account / "db_storage" / "sns" / "sns.db"
    sns_db.parent.mkdir(parents=True)
    sns_db.write_bytes(b"x" * size)
    os.utime(sns_db, ns=(mtime_ns, mtime_ns))
    return sns_db


class AccountDiscoveryTests(unittest.TestCase):
    def test_most_recent_account_wins_over_larger_stale_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _make_sns_db(root, "wxid_old", size=4096, mtime_ns=100_000_000_000)
            _make_sns_db(root, "wxid_current", size=128, mtime_ns=200_000_000_000)

            selected = find_account({"wechat_data_root": str(root)})

        self.assertEqual(selected.wxid_dir.name, "wxid_current")

    def test_recent_wal_activity_counts_as_current_account_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _make_sns_db(root, "wxid_old", size=4096, mtime_ns=300_000_000_000)
            current_db = _make_sns_db(root, "wxid_current", size=128, mtime_ns=100_000_000_000)
            wal = Path(f"{current_db}-wal")
            wal.write_bytes(b"active")
            os.utime(wal, ns=(400_000_000_000, 400_000_000_000))

            selected = find_account({"wechat_data_root": str(root)})

        self.assertEqual(selected.wxid_dir.name, "wxid_current")

    def test_explicit_account_hint_overrides_activity_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _make_sns_db(root, "wxid_requested", size=128, mtime_ns=100_000_000_000)
            _make_sns_db(root, "wxid_newer", size=128, mtime_ns=200_000_000_000)

            selected = find_account(
                {"wechat_data_root": str(root), "account": "wxid_requested"}
            )

        self.assertEqual(selected.wxid_dir.name, "wxid_requested")


if __name__ == "__main__":
    unittest.main()
