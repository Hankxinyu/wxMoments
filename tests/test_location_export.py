from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wxmoments import (  # noqa: E402
    AccountInfo,
    OUTPUT_RUNTIME_DIR,
    ExportedPost,
    parse_datetime,
    pdf_single_image_cell_style,
    post_visual_media,
    self_username_candidates,
    load_timeline,
    write_pdf_html,
)
from wechat_decrypt_tool.modules.key_store import _KEY_STORE_PATH  # noqa: E402
from wechat_decrypt_tool.modules.wechat_emoji import emojify_wechat_shortcodes  # noqa: E402


class DateParsingTests(unittest.TestCase):
    def test_compact_date_is_not_misread_as_short_datetime(self) -> None:
        parsed = parse_datetime("20131231", end_of_day=True)

        self.assertEqual(parsed.strftime("%Y-%m-%d %H:%M:%S.%f"), "2013-12-31 23:59:59.999999")


class EmojiCompatibilityTests(unittest.TestCase):
    def test_legacy_softbank_private_use_emoji_are_converted(self) -> None:
        self.assertEqual(emojify_wechat_shortcodes("\ue443\ue022\ue112\ue033"), "🌀❤️🎁🎄")


class RuntimePathTests(unittest.TestCase):
    def test_key_store_uses_runtime_output(self) -> None:
        self.assertEqual(Path(_KEY_STORE_PATH), OUTPUT_RUNTIME_DIR / "account_keys.json")


class AccountMatchingTests(unittest.TestCase):
    def test_self_candidates_include_directory_name_without_hash_suffix(self) -> None:
        account = AccountInfo(
            account="wxid_example_ab12",
            wxid_dir=Path("C:/wechat/wxid_example_ab12"),
            db_storage_dir=Path("C:/wechat/wxid_example_ab12/db_storage"),
        )

        candidates = self_username_candidates(account, {})

        self.assertIn("wxid_example", candidates)


class TimelinePaginationTests(unittest.TestCase):
    def test_duplicate_post_across_pages_is_emitted_once(self) -> None:
        first = {"id": "1", "createTime": 1, "username": "me"}
        duplicate = {"id": "2", "createTime": 2, "username": "me"}
        last = {"id": "3", "createTime": 3, "username": "me"}
        responses = [
            {"timeline": [first, duplicate], "hasMore": True},
            {"timeline": [duplicate, last], "hasMore": False},
        ]

        with patch(
            "wechat_decrypt_tool.modules.sns_reader.list_sns_timeline",
            side_effect=responses,
        ):
            posts = load_timeline(Path("account"), ["me"], source="decrypted")

        self.assertEqual([post["id"] for post in posts], ["1", "2", "3"])


class LocationExportTests(unittest.TestCase):
    def test_html_contains_escaped_location(self) -> None:
        post = ExportedPost(
            time_text="2013-01-02 03:04:05",
            display="测试用户",
            location="上海·外滩 <观景台>",
            body="测试正文",
            images=[],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            html_path = write_pdf_html(output, [post])
            rendered = html_path.read_text(encoding="utf-8")

        self.assertIn('class="location"', rendered)
        self.assertIn("📍 上海·外滩 &lt;观景台&gt;", rendered)

    def test_html_omits_empty_location(self) -> None:
        post = ExportedPost(
            time_text="2013-01-02 03:04:05",
            display="测试用户",
            location="",
            body="测试正文",
            images=[],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            rendered = write_pdf_html(output, [post]).read_text(encoding="utf-8")

        self.assertNotIn('class="location"', rendered)

    def test_multi_image_grid_preserves_complete_image(self) -> None:
        post = ExportedPost(
            time_text="2013-01-02 03:04:05",
            display="测试用户",
            location="",
            body="多图测试",
            images=["figure/01.jpg", "figure/02.jpg"],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            rendered = write_pdf_html(Path(temp_dir), [post]).read_text(encoding="utf-8")

        self.assertIn(".image-cell img { display: block; width: 100%; height: 100%; object-fit: contain; }", rendered)
        self.assertNotIn(".image-cell img { display: block; width: 100%; height: 100%; object-fit: cover; }", rendered)

    def test_single_image_cell_matches_scaled_image_dimensions(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            image_path = output / "figure" / "01.jpg"
            image_path.parent.mkdir(parents=True)
            Image.new("RGB", (142, 142), "white").save(image_path)

            style = pdf_single_image_cell_style(output, "figure/01.jpg")

        self.assertEqual(style, ' style="width: 300.00px; height: 300.00px;"')

    def test_video_cover_is_labeled_in_pdf_html(self) -> None:
        post = ExportedPost(
            time_text="2015-01-01 22:32:35",
            display="测试用户",
            location="",
            body="视频动态",
            images=["figure/cover.jpg"],
            video_cover_count=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            rendered = write_pdf_html(Path(temp_dir), [post]).read_text(encoding="utf-8")

        self.assertIn("🎬 视频封面（视频本体未导出）", rendered)


class VisualMediaTests(unittest.TestCase):
    def test_regular_video_uses_its_thumbnail(self) -> None:
        items = post_visual_media(
            {
                "media": [
                    {
                        "type": 1,
                        "url": "https://example.video.qq.com/video.mp4",
                        "thumb": "https://example.qpic.cn/cover.jpg",
                    }
                ]
            }
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "video_cover")
        self.assertEqual(items[0][0]["thumb"], "https://example.qpic.cn/cover.jpg")

    def test_legacy_video_type_six_uses_its_thumbnail(self) -> None:
        items = post_visual_media(
            {
                "type": 15,
                "media": [
                    {
                        "type": 6,
                        "url": "https://example.video.qq.com/legacy.mp4",
                        "thumb": "https://example.qpic.cn/legacy-cover.jpg",
                    }
                ],
            }
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "video_cover")
        self.assertEqual(items[0][0]["thumb"], "https://example.qpic.cn/legacy-cover.jpg")

    def test_finder_feed_adds_cover(self) -> None:
        items = post_visual_media(
            {
                "type": 28,
                "media": [],
                "finderFeed": {"thumbUrl": "https://example.qpic.cn/finder.jpg"},
            }
        )

        self.assertEqual(items, [({"type": 2, "thumb": "https://example.qpic.cn/finder.jpg"}, "video_cover")])

    def test_video_without_cover_is_skipped(self) -> None:
        items = post_visual_media(
            {"media": [{"type": 1, "url": "https://example.video.qq.com/video.mp4"}]}
        )

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
