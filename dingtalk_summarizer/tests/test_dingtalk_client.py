"""dingtalk_client 的纯逻辑测试（不依赖 dws / 网络 / anthropic）。"""
import unittest

from dingtalk_summarizer.dingtalk_client import (
    Message,
    _extract_text,
    _iter_message_objects,
    _normalize,
)


class IterMessageObjectsTest(unittest.TestCase):
    def test_top_level_list(self):
        payload = [{"text": "a"}, {"text": "b"}, "garbage"]
        self.assertEqual(len(_iter_message_objects(payload)), 2)

    def test_messages_key(self):
        payload = {"messages": [{"text": "a"}]}
        self.assertEqual(len(_iter_message_objects(payload)), 1)

    def test_nested_data_list(self):
        payload = {"data": {"list": [{"text": "a"}, {"text": "b"}]}}
        self.assertEqual(len(_iter_message_objects(payload)), 2)

    def test_records_key(self):
        payload = {"records": [{"from": "x"}]}
        self.assertEqual(len(_iter_message_objects(payload)), 1)

    def test_empty(self):
        self.assertEqual(_iter_message_objects({"foo": "bar"}), [])


class ExtractTextTest(unittest.TestCase):
    def test_direct_text(self):
        self.assertEqual(_extract_text({"text": "hello"}), "hello")

    def test_nested_text_content(self):
        self.assertEqual(_extract_text({"text": {"content": "hi"}}), "hi")

    def test_content_field(self):
        self.assertEqual(_extract_text({"content": "yo"}), "yo")

    def test_markdown(self):
        self.assertEqual(_extract_text({"markdown": {"text": "**md**"}}), "**md**")

    def test_non_text_fallback(self):
        self.assertEqual(_extract_text({"msgtype": "picture"}), "<picture>")

    def test_unknown_fallback(self):
        self.assertEqual(_extract_text({}), "<非文本消息>")


class NormalizeTest(unittest.TestCase):
    def test_full_message(self):
        msg = _normalize(
            {"senderNick": "张三", "text": {"content": "上线 v2"}, "createTime": "10:00"}
        )
        self.assertEqual(msg.sender, "张三")
        self.assertEqual(msg.text, "上线 v2")
        self.assertEqual(msg.timestamp, "10:00")
        self.assertEqual(msg.as_line(), "[10:00] 张三: 上线 v2")

    def test_missing_sender_defaults(self):
        msg = _normalize({"text": "x"})
        self.assertEqual(msg.sender, "未知成员")

    def test_as_line_without_timestamp(self):
        self.assertEqual(Message(sender="李四", text="hi").as_line(), "李四: hi")


if __name__ == "__main__":
    unittest.main()
