from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import prefilter_comments as prefilter  # noqa: E402
import prepare_topic_bundle as bundle  # noqa: E402


class PrefilterTests(unittest.TestCase):
    def test_contextless_reaction_is_rejected(self) -> None:
        self.assertEqual("纯反应或缺少讨论对象", prefilter.rejection_reason("已经中招了，这个怎么办？"))

    def test_concrete_short_question_is_kept(self) -> None:
        self.assertIsNone(prefilter.rejection_reason("彩礼能退吗？"))

    def test_compact_candidate_omits_author_and_raw_metadata(self) -> None:
        item = {
            "comment_id": "c1",
            "content": "恋爱期间转账分手后能追回吗？",
            "author": "某用户",
            "raw_text": "很长的界面原文",
            "source_url": "https://example.com/video/1",
            "platform": "generic",
        }
        result = prefilter.compact_candidate(item, item["content"])
        self.assertEqual("c1", result["comment_id"])
        self.assertNotIn("author", result)
        self.assertNotIn("raw_text", result)


class PortableBundleTests(unittest.TestCase):
    def test_xiaohongshu_platform_is_detected(self) -> None:
        prefix, label = bundle.detect_platform(
            {"source_url": "https://www.xiaohongshu.com/explore/abc"}
        )
        self.assertEqual("xhs", prefix)
        self.assertEqual("小红书", label)

    def test_non_legal_category_uses_generic_outline(self) -> None:
        outline = bundle.make_outline("护肤成分选择")
        self.assertIn("判断标准", outline)
        self.assertNotIn("法律关系", outline)


if __name__ == "__main__":
    unittest.main()
