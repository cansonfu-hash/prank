"""summarizer 纯函数测试（分块、Markdown 渲染）。

需要 pydantic；缺失时整体跳过，不阻塞无依赖环境下的其它测试。
"""
import unittest

try:
    import pydantic  # noqa: F401

    HAS_PYDANTIC = True
except ImportError:  # pragma: no cover
    HAS_PYDANTIC = False


@unittest.skipUnless(HAS_PYDANTIC, "需要安装 pydantic")
class SummarizerPureFnTest(unittest.TestCase):
    def setUp(self):
        from dingtalk_summarizer import config
        from dingtalk_summarizer.dingtalk_client import Message
        from dingtalk_summarizer import summarizer

        self.config = config
        self.Message = Message
        self.summarizer = summarizer

    def _info(self, **kw):
        from dingtalk_summarizer.summarizer import ActionItem, KeyInfo

        defaults = dict(
            summary="总结内容",
            topics=["话题A"],
            decisions=["决定X"],
            action_items=[ActionItem(task="修复Bug", owner="张三", due="周五")],
            open_questions=["待定Q"],
            important_dates=["6/20"],
            mentioned_links=["http://x"],
        )
        defaults.update(kw)
        return KeyInfo(**defaults)

    def test_build_transcript_skips_empty(self):
        msgs = [
            self.Message(sender="A", text="hi", timestamp="1"),
            self.Message(sender="B", text="", timestamp="2"),
        ]
        out = self.summarizer._build_transcript(msgs)
        self.assertEqual(out, "[1] A: hi")

    def test_chunk_messages_splits_by_size(self):
        self.config.CHUNK_CHAR_SIZE = 30  # 强制小分块
        msgs = [self.Message(sender="A", text="x" * 20) for _ in range(5)]
        chunks = self.summarizer._chunk_messages(msgs)
        self.assertGreater(len(chunks), 1)
        # 所有消息都被保留
        self.assertEqual(sum(len(c) for c in chunks), 5)

    def test_render_markdown_single(self):
        md = self.summarizer.render_markdown(self._info(), "cid123", 42)
        self.assertIn("# 钉钉群消息汇总", md)
        self.assertIn("`cid123`", md)
        self.assertIn("消息条数：42", md)
        self.assertIn("- [ ] 修复Bug（负责人：张三；截止：周五）", md)
        self.assertIn("## 总结", md)

    def test_render_combined_single_delegates(self):
        info = self._info()
        combined = self.summarizer.render_combined([("c1", 10, info)])
        direct = self.summarizer.render_markdown(info, "c1", 10)
        self.assertEqual(combined, direct)

    def test_render_combined_multi(self):
        md = self.summarizer.render_combined(
            [("c1", 10, self._info()), ("c2", 5, self._info(summary="第二个群"))]
        )
        self.assertIn("# 钉钉群消息汇总（共 2 个群）", md)
        self.assertIn("## 群 `c1`（10 条）", md)
        self.assertIn("## 群 `c2`（5 条）", md)
        self.assertIn("### 总结", md)  # 多群时小节降一级
        self.assertIn("第二个群", md)

    def test_empty_lists_render_placeholder(self):
        md = self.summarizer.render_markdown(
            self._info(topics=[], action_items=[]), "c", 1
        )
        self.assertIn("（无）", md)


@unittest.skipUnless(HAS_PYDANTIC, "需要安装 pydantic")
class ExpandIdsTest(unittest.TestCase):
    def test_expand_and_dedup(self):
        from dingtalk_summarizer.main import _expand_ids

        self.assertEqual(
            _expand_ids(["a,b", "c", " a "]), ["a", "b", "c"]
        )


if __name__ == "__main__":
    unittest.main()
