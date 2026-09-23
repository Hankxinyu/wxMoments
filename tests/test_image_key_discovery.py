from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wechat_decrypt_tool.modules.constants import IMAGE_AES_KEY_LENGTH  # noqa: E402
from wechat_decrypt_tool.modules.image_key_resolver import (  # noqa: E402
    V2_CIPHERTEXT_START,
    V2_MAGIC,
    scan_v2_templates,
)


class SnsTemplateDiscoveryTests(unittest.TestCase):
    def test_extensionless_sns_v2_cache_is_used_as_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account = Path(temp_dir)
            image_path = account / "cache" / "2026-09" / "Sns" / "Img" / "ab" / "0123456789abcdef"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(
                V2_MAGIC
                + b"\x00" * (V2_CIPHERTEXT_START - len(V2_MAGIC))
                + b"x" * IMAGE_AES_KEY_LENGTH
                + b"payload"
                + b"\xff\xd8"
            )

            result = scan_v2_templates(account)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(len(result.templates), 1)
        self.assertEqual(result.templates[0].path, image_path)


if __name__ == "__main__":
    unittest.main()
