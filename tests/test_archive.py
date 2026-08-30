from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wxmoments import ExportedPost  # noqa: E402
from wxmoments_archive import (  # noqa: E402
    ArchiveItem,
    apply_pending,
    archive_post_key,
    atomic_write_json,
    build_pdf_candidate,
    filter_raw_posts,
    keys_digest,
    largest_fitting_prefix,
    mib_bytes,
    new_state,
    pair_unexported,
    validate_pdf,
    volume_filename,
)


def make_exported(time_text: str) -> ExportedPost:
    return ExportedPost(
        time_text=time_text,
        display="测试用户",
        location="上海",
        body="测试正文",
        images=[],
    )


def make_one_page_pdf(_output: Path, posts: list[ExportedPost], path: Path) -> None:
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(str(path))
    canvas.drawString(72, 760, posts[0].time_text if posts else "empty")
    canvas.save()


class ArchivePrimitiveTests(unittest.TestCase):
    def test_mib_uses_binary_bytes(self) -> None:
        self.assertEqual(mib_bytes(50), 52_428_800)

    def test_volume_filename_is_stable(self) -> None:
        self.assertEqual(volume_filename(7), "微信朋友圈正式备份_第007卷.pdf")

    def test_post_key_prefers_stable_timeline_id(self) -> None:
        first = archive_post_key({"id": "123", "contentDesc": "old"})
        second = archive_post_key({"id": "123", "contentDesc": "changed"})
        self.assertEqual(first, second)

    def test_filter_is_inclusive_and_oldest_first(self) -> None:
        posts = [
            {"id": "2", "createTime": int(datetime(2020, 1, 2).timestamp())},
            {"id": "1", "createTime": int(datetime(2020, 1, 1).timestamp())},
        ]
        selected = filter_raw_posts(posts, datetime(2020, 1, 1), datetime(2020, 1, 2))
        self.assertEqual([item["id"] for item in selected], ["1", "2"])

    def test_same_second_unexported_post_is_not_lost(self) -> None:
        timestamp = int(datetime(2020, 1, 1, 12, 0, 0).timestamp())
        raw = [
            {"id": "1", "createTime": timestamp},
            {"id": "2", "createTime": timestamp},
        ]
        exported = [make_exported("2020-01-01 12:00:00"), make_exported("2020-01-01 12:00:00")]
        items = pair_unexported(raw, exported, {archive_post_key(raw[0])})
        self.assertEqual([item.key for item in items], [archive_post_key(raw[1])])

    def test_atomic_json_replaces_complete_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            atomic_write_json(path, {"value": 1})
            atomic_write_json(path, {"value": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": 2})


class ArchiveTransactionTests(unittest.TestCase):
    def test_apply_pending_updates_volume_and_global_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state = new_state("account", Path(temp_dir), 45, 50)
            state["pending"] = {
                "volume": {
                    "number": 1,
                    "filename": volume_filename(1),
                    "times": ["2020-01-01 00:00:00"],
                    "post_keys": ["a"],
                },
                "added_keys": ["a"],
            }
            apply_pending(state)

        self.assertEqual(state["post_count"], 1)
        self.assertEqual(state["archive_start_time"], "2020-01-01 00:00:00")
        self.assertEqual(state["last_exported_time"], "2020-01-01 00:00:00")
        self.assertIsNone(state["pending"])


class ArchivePdfTests(unittest.TestCase):
    def test_candidate_is_stamped_and_reopens(self) -> None:
        item = ArchiveItem(
            key="a" * 64,
            time_text="2020-01-01 12:00:00",
            exported=make_exported("2020-01-01 12:00:00"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "candidate.pdf"
            with patch("wxmoments_archive.core.render_pdf", side_effect=make_one_page_pdf):
                build_pdf_candidate(root, [item], destination)
            result = validate_pdf(destination, [item.time_text], [item.key])

        self.assertEqual(result["pages"], 1)
        self.assertGreater(result["bytes"], 100)
        self.assertEqual(keys_digest([item.key]), keys_digest([item.key]))

    def test_active_volume_that_cannot_fit_one_post_requests_new_volume(self) -> None:
        item = ArchiveItem(
            key="b" * 64,
            time_text="2020-01-02 12:00:00",
            exported=make_exported("2020-01-02 12:00:00"),
        )

        def fake_candidate(
            _content: Path,
            _items: list[ArchiveItem],
            destination: Path,
            *_args: object,
        ) -> None:
            destination.write_bytes(b"x" * 200)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = root / "existing.pdf"
            existing.write_bytes(b"old")
            previous = {"times": ["2020-01-01 00:00:00"], "post_keys": ["a" * 64]}
            with patch("wxmoments_archive.build_pdf_candidate", side_effect=fake_candidate):
                count, candidate = largest_fitting_prefix(
                    root,
                    [item],
                    root,
                    100,
                    previous,
                    existing,
                )

        self.assertEqual(count, 0)
        self.assertIsNone(candidate)


if __name__ == "__main__":
    unittest.main()
